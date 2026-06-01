"""
Medicines Router - API for Counsellor Medicine List Management

Endpoints for:
- Counsellor medicine list CRUD
- CSV upload
- School medicine list management
- Medicine matching test
- Feedback submission and review
"""

import os
import uuid
import logging
from typing import List, Optional, Union
from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Depends, Request
from pydantic import BaseModel, Field

from models.auth_models import ClientContext
from dependencies.auth import require_admin
from services.auth_service import get_counsellor_school_id

# Conditional EHR auth imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import EHRCounsellorAccessChecker, get_current_client

    _doctor_checker = EHRCounsellorAccessChecker()

    async def verify_counsellor_access(request: Request, counsellor_id: Optional[str] = None):  # type: ignore[misc]
        """Verify EHR client has access to counsellor data."""
        counsellor_uuid = uuid.UUID(counsellor_id) if counsellor_id else None
        client = get_current_client(request)
        return await _doctor_checker(request, counsellor_uuid, client)

    async def verify_school_access(request: Request, school_id: Optional[str] = None):  # type: ignore[misc]
        """Verify client has access to school data. Allows admin, web_app, and EHR (with school scoping)."""
        client = get_current_client(request)
        if school_id and client.client_type == "ehr":
            school_uuid = uuid.UUID(school_id)
            if not client.can_access_school(school_uuid):
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )
        return client
else:
    async def verify_counsellor_access(request: Request = None, counsellor_id: Optional[str] = None):  # type: ignore[misc]
        return None

    async def verify_school_access(request: Request = None, school_id: Optional[str] = None):  # type: ignore[misc]
        return None

from services.medicine_service import (
    # Counsellor medicines
    create_counsellor_medicine,
    update_counsellor_medicine,
    delete_counsellor_medicine,
    list_counsellor_medicines,
    copy_school_medicine_to_counsellor,
    upload_medicine_list,
    upload_medicine_list_json,
    # School medicines
    create_school_medicine,
    list_school_medicines,
    upload_school_medicine_list,
    # Matching
    match_medicine_name,
    get_medicine_list_for_prompt,
    # Feedback
    submit_medicine_feedback,
    list_pending_feedback,
    list_feedback_history,
    # Backfill
    backfill_counsellor_medicines_from_school,
)

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/medicines", tags=["Medicine Lists"])


# ============================================================================
# Request/Response Models
# ============================================================================

class MedicineCreate(BaseModel):
    medicine_name: str = Field(..., description="Medicine name")
    common_names: Optional[List[str]] = Field(default=None, description="Alternative names")
    category: Optional[str] = Field(default=None, description="Category (e.g., Antihypertensive)")
    typical_dosage: Optional[str] = Field(default=None, description="Typical dosage")
    form: Optional[str] = Field(default=None, description="Form (tablet, syrup, etc.)")
    snomed_code: Optional[str] = Field(default=None, description="SNOMED CT code")
    formulary_name: Optional[str] = Field(default=None, description="Official formulary name")
    medicine_type: Optional[str] = Field(default=None, description="generic or branded")


class MedicineUpdate(BaseModel):
    medicine_name: Optional[str] = None
    common_names: Optional[List[str]] = None
    category: Optional[str] = None
    typical_dosage: Optional[str] = None
    form: Optional[str] = None
    snomed_code: Optional[str] = None
    formulary_name: Optional[str] = None
    medicine_type: Optional[str] = None


class UploadOptions(BaseModel):
    replace_existing: bool = Field(default=False, description="Replace all existing medicines")


class MatchTestRequest(BaseModel):
    medicine_name: str = Field(..., description="Medicine name to test")
    diagnosis: Optional[str] = Field(default="", description="Diagnosis context")


class FeedbackSubmit(BaseModel):
    feedback_status: str = Field(..., description="agreed or disagreed")
    correct_medicine_id: Optional[str] = Field(default=None, description="Correct medicine UUID if disagreed")
    correct_medicine_name: Optional[str] = Field(default=None, description="Manual entry if disagreed")


class MedicineBulkItem(BaseModel):
    name: str = Field(..., description="Medicine name (required)")
    external_id: str = Field(..., description="External ID (required)")
    common_name: Optional[Union[List[str], str]] = Field(default=None, description="Alternative names (list or comma-separated string)")
    category: Optional[str] = None
    typical_dosage: Optional[str] = None
    form: Optional[str] = None
    snomed_code: Optional[str] = None
    formulary_name: Optional[str] = None
    type: Optional[str] = Field(default=None, description="generic or branded")


class MedicineBulkUpload(BaseModel):
    medicines: List[MedicineBulkItem]


class SchoolMedicineCreate(MedicineCreate):
    pass


# ============================================================================
# Counsellor Medicine Endpoints
# ============================================================================

@router.get("/{counsellor_id}")
async def get_counsellor_medicines(
    request: Request,
    counsellor_id: str,
    category: Optional[str] = None,
    search: Optional[str] = None,
    _auth = Depends(verify_counsellor_access)
):
    """
    List all medicines for a counsellor.
    """
    try:
        medicines = list_counsellor_medicines(
            counsellor_id=uuid.UUID(counsellor_id),
            category=category,
            search=search
        )
        return {"medicines": medicines, "count": len(medicines)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.get("/{counsellor_id}/combined")
async def get_combined_medicines(
    request: Request,
    counsellor_id: str,
    category: Optional[str] = None,
    search: Optional[str] = None,
    _auth = Depends(verify_counsellor_access)
):
    """
    List combined medicines for a counsellor (counsellor list + school list, deduplicated).

    Counsellor medicines take priority over school medicines when duplicates exist.
    Deduplication is based on normalized_name.
    """
    try:
        counsellor_uuid = uuid.UUID(counsellor_id)

        # Get counsellor's own medicines
        counsellor_medicines = list_counsellor_medicines(
            counsellor_id=counsellor_uuid,
            category=category,
            search=search
        )

        # Get counsellor's school_id and fetch school medicines
        school_id = await get_counsellor_school_id(counsellor_uuid)
        if school_id:
            hospital_medicines = list_school_medicines(
                school_id=school_id,
                category=category
            )
        else:
            hospital_medicines = []

        # Deduplicate: counsellor medicines take priority
        seen_names = {m["normalized_name"] for m in counsellor_medicines}
        combined = list(counsellor_medicines)
        for med in hospital_medicines:
            if med["normalized_name"] not in seen_names:
                # Filter by search if provided (school list doesn't support search natively)
                if search and search.lower() not in med.get("medicine_name", "").lower():
                    continue
                seen_names.add(med["normalized_name"])
                combined.append(med)

        return {
            "medicines": combined,
            "count": len(combined),
            "counsellor_count": len(counsellor_medicines),
            "hospital_count": len(hospital_medicines),
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/{counsellor_id}")
async def add_counsellor_medicine(
    request: Request,
    counsellor_id: str,
    data: MedicineCreate,
    _auth = Depends(verify_counsellor_access)
):
    """
    Add a single medicine to counsellor's list.
    """
    try:
        medicine = create_counsellor_medicine(
            counsellor_id=uuid.UUID(counsellor_id),
            medicine_name=data.medicine_name,
            common_names=data.common_names,
            category=data.category,
            typical_dosage=data.typical_dosage,
            form=data.form,
            snomed_code=data.snomed_code,
            formulary_name=data.formulary_name,
            medicine_type=data.medicine_type
        )
        return {"message": "Medicine added", "medicine": medicine}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to add medicine: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.put("/{counsellor_id}/{medicine_id}")
async def update_medicine(
    request: Request,
    counsellor_id: str,
    medicine_id: str,
    data: MedicineUpdate,
    _auth = Depends(verify_counsellor_access)
):
    """
    Update a medicine in counsellor's list.
    """
    try:
        medicine = update_counsellor_medicine(
            medicine_id=uuid.UUID(medicine_id),
            medicine_name=data.medicine_name,
            common_names=data.common_names,
            category=data.category,
            typical_dosage=data.typical_dosage,
            form=data.form,
            snomed_code=data.snomed_code,
            formulary_name=data.formulary_name,
            medicine_type=data.medicine_type
        )
        return {"message": "Medicine updated", "medicine": medicine}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to update medicine: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.delete("/{counsellor_id}/{medicine_id}")
async def remove_medicine(
    request: Request,
    counsellor_id: str,
    medicine_id: str,
    _auth = Depends(verify_counsellor_access)
):
    """
    Soft delete a medicine from counsellor's list.
    """
    try:
        success = delete_counsellor_medicine(uuid.UUID(medicine_id))
        if not success:
            raise HTTPException(status_code=400, detail="Failed to delete medicine")
        return {"message": "Medicine deleted"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/{counsellor_id}/upload")
async def upload_csv(
    request: Request,
    counsellor_id: str,
    file: UploadFile = File(...),
    replace_existing: bool = Query(default=False),
    _auth = Depends(verify_counsellor_access)
):
    """
    Upload CSV file with medicines.

    Expected columns: name, common_name, category, typical_dosage, form, snomed_code, formulary_name, type
    """
    try:
        # Read file content
        content = await file.read()
        csv_content = content.decode('utf-8')

        result = upload_medicine_list(
            counsellor_id=uuid.UUID(counsellor_id),
            csv_content=csv_content,
            filename=file.filename or "upload.csv",
            replace_existing=replace_existing
        )
        # If all rows were rejected by validation, return 400 with error details
        if result.get("successful", 0) == 0 and result.get("errors"):
            error_msg = result["errors"][0].get("error", "Upload validation failed") if result["errors"] else "Upload validation failed"
            raise HTTPException(status_code=400, detail=error_msg)
        return result
    except HTTPException:
        raise
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded CSV")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.post("/{counsellor_id}/upload-json")
async def upload_json(
    request: Request,
    counsellor_id: str,
    data: MedicineBulkUpload,
    replace_existing: bool = Query(default=False),
    _auth = Depends(verify_counsellor_access)
):
    """
    Upload medicines via JSON body.

    Accepts an array of medicine objects with the same fields as CSV columns.
    Applies identical enrichment, normalization, dedup, and upsert logic.
    """
    try:
        # Convert Pydantic models to dicts matching service expectations
        medicines = []
        for item in data.medicines:
            # Parse common_name: accept list or comma-separated string
            common_names = []
            if item.common_name:
                if isinstance(item.common_name, list):
                    common_names = [n.strip() for n in item.common_name if n.strip()]
                else:
                    common_names = [n.strip() for n in item.common_name.split(',') if n.strip()]

            medicines.append({
                "medicine_name": item.name.strip(),
                "common_names": common_names,
                "category": item.category.strip() if item.category else None,
                "typical_dosage": item.typical_dosage.strip() if item.typical_dosage else None,
                "form": item.form.strip() if item.form else None,
                "snomed_code": item.snomed_code.strip() if item.snomed_code else None,
                "formulary_name": item.formulary_name.strip() if item.formulary_name else None,
                "medicine_type": item.type.strip().lower() if item.type else None,
                "external_id": item.external_id.strip(),
            })

        result = upload_medicine_list_json(
            counsellor_id=uuid.UUID(counsellor_id),
            medicines=medicines,
            replace_existing=replace_existing
        )
        if result.get("successful", 0) == 0 and result.get("errors"):
            error_msg = result["errors"][0].get("error", "Upload validation failed") if result["errors"] else "Upload validation failed"
            raise HTTPException(status_code=400, detail=error_msg)
        return result
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"JSON upload failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.post("/{counsellor_id}/copy-from-school/{school_medicine_id}")
async def copy_from_school(
    request: Request,
    counsellor_id: str,
    school_medicine_id: str,
    _auth = Depends(verify_counsellor_access)
):
    """
    Copy a school medicine to counsellor's personal list.
    """
    try:
        result = copy_school_medicine_to_counsellor(
            school_medicine_id=uuid.UUID(school_medicine_id),
            counsellor_id=uuid.UUID(counsellor_id)
        )
        if not result:
            raise HTTPException(status_code=400, detail="Failed to copy medicine")
        return {"message": "Medicine copied", "result": result}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/{counsellor_id}/test-match")
async def test_match(
    request: Request,
    counsellor_id: str,
    data: MatchTestRequest,
    _auth = Depends(verify_counsellor_access)
):
    """
    Test medicine matching without saving.

    Useful for debugging and testing the matching algorithm.
    """
    try:
        result = await match_medicine_name(
            extracted_name=data.medicine_name,
            counsellor_id=uuid.UUID(counsellor_id),
            diagnosis=data.diagnosis or ""
        )
        return {
            "input": data.medicine_name,
            "diagnosis": data.diagnosis,
            "match_result": result
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Match test failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.get("/{counsellor_id}/prompt-injection")
async def get_prompt_injection(
    request: Request,
    counsellor_id: str,
    max_medicines: int = Query(default=3500),
    _auth = Depends(verify_counsellor_access)
):
    """
    Get medicine list formatted for prompt injection.

    This is the exact text that will be injected into the extraction prompt.
    """
    try:
        prompt_text = get_medicine_list_for_prompt(
            counsellor_id=uuid.UUID(counsellor_id),
            max_medicines=max_medicines
        )
        return {
            "counsellor_id": counsellor_id,
            "prompt_text": prompt_text,
            "character_count": len(prompt_text)
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


# ============================================================================
# School Medicine Endpoints
# ============================================================================

@router.get("/school/{school_id}")
async def get_school_medicines(
    request: Request,
    school_id: str,
    category: Optional[str] = None,
    _auth = Depends(verify_school_access)
):
    """
    List all medicines for a school.
    """
    try:
        medicines = list_school_medicines(
            school_id=uuid.UUID(school_id),
            category=category
        )
        return {"medicines": medicines, "count": len(medicines)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/school/{school_id}")
async def add_school_medicine(
    school_id: str,
    data: SchoolMedicineCreate,
    created_by: str = Query(..., description="Admin counsellor ID"),
    client: ClientContext = Depends(require_admin)
):
    """
    Add a single medicine to school's list.
    """
    try:
        medicine = create_school_medicine(
            school_id=uuid.UUID(school_id),
            created_by=uuid.UUID(created_by),
            medicine_name=data.medicine_name,
            common_names=data.common_names,
            category=data.category,
            typical_dosage=data.typical_dosage,
            form=data.form,
            snomed_code=data.snomed_code,
            formulary_name=data.formulary_name,
            medicine_type=data.medicine_type
        )
        return {"message": "School medicine added", "medicine": medicine}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to add school medicine: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.post("/school/{school_id}/upload")
async def upload_school_csv(
    school_id: str,
    file: UploadFile = File(...),
    created_by: str = Query(..., description="Admin counsellor ID"),
    replace_existing: bool = Query(default=False),
    client: ClientContext = Depends(require_admin)
):
    """
    Upload CSV file with school medicines.
    """
    try:
        content = await file.read()
        csv_content = content.decode('utf-8')

        result = upload_school_medicine_list(
            school_id=uuid.UUID(school_id),
            csv_content=csv_content,
            filename=file.filename or "upload.csv",
            created_by=uuid.UUID(created_by),
            replace_existing=replace_existing
        )
        return result
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded CSV")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"School upload failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.put("/school/{school_id}/{medicine_id}")
async def update_school_medicine(
    school_id: str,
    medicine_id: str,
    data: MedicineUpdate,
    client: ClientContext = Depends(require_admin)
):
    """
    Update a school medicine.
    """
    from services.medicine_service import supabase, normalize_medicine_name, generate_search_tokens

    try:
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}

        # Regenerate normalized name and tokens if medicine_name changed
        if 'medicine_name' in update_data:
            update_data['normalized_name'] = normalize_medicine_name(update_data['medicine_name'])
            update_data['search_tokens'] = generate_search_tokens(
                update_data['medicine_name'],
                update_data.get('common_names')
            )

        result = supabase.table('school_medicine_lists').update(
            update_data
        ).eq('id', medicine_id).eq('school_id', school_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="School medicine not found")

        return {"message": "School medicine updated", "medicine": result.data[0]}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to update school medicine: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.delete("/school/{school_id}/{medicine_id}")
async def delete_school_medicine(
    school_id: str,
    medicine_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Soft delete a school medicine (sets is_active=False).
    """
    from services.medicine_service import supabase

    try:
        result = supabase.table('school_medicine_lists').update({
            'is_active': False
        }).eq('id', medicine_id).eq('school_id', school_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="School medicine not found")

        return {"message": "School medicine deleted"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to delete school medicine: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


# ============================================================================
# Feedback Endpoints
# ============================================================================

@router.get("/feedback/{counsellor_id}/pending")
async def get_pending_feedback(
    request: Request,
    counsellor_id: str,
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    include_exact_matches: bool = Query(default=False, description="Include exact and common_name matches (default: only fuzzy and doctor_edit)"),
    _auth = Depends(verify_counsellor_access)
):
    """
    Get matches pending feedback for a counsellor.

    By default, only returns matches that NEED counsellor action:
    - 'fuzzy' matches: System guessed a correction → Agree/Disagree
    - 'no_match' matches: New medicine not in any list → Add to list or Correct
    - 'doctor_edit_*' matches: FYI only (counsellor already corrected in UI)

    Does NOT return by default (no action needed):
    - 'exact' matches: Gemini used exact name from list
    - 'common_name' matches: Gemini used a known alias

    Set `include_exact_matches=true` to include all pending matches.
    """
    try:
        records = list_pending_feedback(
            counsellor_id=uuid.UUID(counsellor_id),
            limit=limit,
            offset=offset,
            include_exact_matches=include_exact_matches
        )
        return {
            "records": records,
            "count": len(records),
            "limit": limit,
            "offset": offset,
            "include_exact_matches": include_exact_matches
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.get("/feedback/{counsellor_id}/history")
async def get_feedback_history(
    request: Request,
    counsellor_id: str,
    feedback_status: Optional[str] = None,
    confidence_min: Optional[float] = None,
    confidence_max: Optional[float] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    include_exact_matches: bool = Query(default=False, description="Include exact and common_name matches (default: only fuzzy, no_match, doctor_edit)"),
    _auth = Depends(verify_counsellor_access)
):
    """
    Get feedback history with filters for the review screen.

    By default, only returns matches that NEED/NEEDED counsellor action:
    - 'fuzzy' matches: System guessed a correction
    - 'no_match' matches: New medicine not in any list
    - 'doctor_edit_*' matches: Counsellor corrected in UI

    Does NOT return by default (no action needed):
    - 'exact' matches: Gemini used exact name from list
    - 'common_name' matches: Gemini used a known alias

    Set `include_exact_matches=true` to include all matches.
    """
    try:
        result = list_feedback_history(
            counsellor_id=uuid.UUID(counsellor_id),
            feedback_status=feedback_status,
            confidence_min=confidence_min,
            confidence_max=confidence_max,
            source=source,
            search=search,
            limit=limit,
            offset=offset,
            include_exact_matches=include_exact_matches
        )
        return result
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/feedback/{match_log_id}")
async def submit_feedback(
    request: Request,
    match_log_id: str,
    data: FeedbackSubmit,
    counsellor_id: str = Query(..., description="Counsellor ID for EHR access verification"),
    _auth = Depends(verify_counsellor_access)
):
    """
    Submit feedback for a medicine match.

    If agreed with school match, auto-copies to counsellor's personal list.
    """
    try:
        correct_id = uuid.UUID(data.correct_medicine_id) if data.correct_medicine_id else None

        result = submit_medicine_feedback(
            match_log_id=uuid.UUID(match_log_id),
            feedback_status=data.feedback_status,
            correct_medicine_id=correct_id,
            correct_medicine_name=data.correct_medicine_name
        )
        return {"message": "Feedback submitted", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"Feedback submission failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.post("/feedback/bulk-agree")
async def bulk_agree_feedback(
    request: Request,
    match_log_ids: List[str],
    counsellor_id: str = Query(..., description="Counsellor ID for EHR access verification"),
    _auth = Depends(verify_counsellor_access)
):
    """
    Bulk agree with multiple matches.
    """
    results = []
    for log_id in match_log_ids:
        try:
            result = submit_medicine_feedback(
                match_log_id=uuid.UUID(log_id),
                feedback_status='agreed'
            )
            results.append({"id": log_id, "status": "success"})
        except Exception as e:
            results.append({"id": log_id, "status": "error", "message": str(e)})

    return {
        "results": results,
        "success_count": len([r for r in results if r['status'] == 'success']),
        "error_count": len([r for r in results if r['status'] == 'error'])
    }


# ============================================================================
# Backfill - Enrich common_names with abbreviations
# ============================================================================

@router.post("/{counsellor_id}/backfill-abbreviations")
async def backfill_abbreviations(
    counsellor_id: str,
    dry_run: bool = Query(True, description="If true, only report what would be updated without making changes"),
    _admin = Depends(require_admin)
):
    """
    Backfill existing counsellor medicines with enriched common_names from
    the expanded abbreviation dictionary. Admin only.

    Use dry_run=true first to preview changes, then dry_run=false to apply.
    """
    try:
        from services.medicine_service import backfill_medicine_abbreviations
        result = backfill_medicine_abbreviations(
            counsellor_id=uuid.UUID(counsellor_id),
            dry_run=dry_run
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"Abbreviation backfill failed for counsellor {counsellor_id}: {e}")
        raise HTTPException(status_code=500, detail="Backfill failed")


# ============================================================================
# Backfill - Enrich counsellor medicines from school list
# ============================================================================

@router.post("/{counsellor_id}/backfill-from-school")
async def backfill_medicines_from_school(
    counsellor_id: str,
    dry_run: bool = Query(True, description="If true, only report what would be updated without making changes"),
    _admin = Depends(require_admin)
):
    """
    Backfill counsellor medicine entries that have no external_id by matching
    against the school medicine list. Admin only.

    Use dry_run=true first to preview changes, then dry_run=false to apply.
    """
    try:
        result = backfill_counsellor_medicines_from_school(
            counsellor_id=uuid.UUID(counsellor_id),
            dry_run=dry_run
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"Medicine backfill failed for counsellor {counsellor_id}: {e}")
        raise HTTPException(status_code=500, detail="Backfill failed")

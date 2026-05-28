"""
Medicines Router - API for Doctor Medicine List Management

Endpoints for:
- Doctor medicine list CRUD
- CSV upload
- Hospital medicine list management
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
from services.auth_service import get_doctor_hospital_id

# Conditional EHR auth imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import EHRDoctorAccessChecker, get_current_client

    _doctor_checker = EHRDoctorAccessChecker()

    async def verify_doctor_access(request: Request, doctor_id: Optional[str] = None):  # type: ignore[misc]
        """Verify EHR client has access to doctor data."""
        doctor_uuid = uuid.UUID(doctor_id) if doctor_id else None
        client = get_current_client(request)
        return await _doctor_checker(request, doctor_uuid, client)

    async def verify_hospital_access(request: Request, hospital_id: Optional[str] = None):  # type: ignore[misc]
        """Verify client has access to hospital data. Allows admin, web_app, and EHR (with hospital scoping)."""
        client = get_current_client(request)
        if hospital_id and client.client_type == "ehr":
            hospital_uuid = uuid.UUID(hospital_id)
            if not client.can_access_hospital(hospital_uuid):
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )
        return client
else:
    async def verify_doctor_access(request: Request = None, doctor_id: Optional[str] = None):  # type: ignore[misc]
        return None

    async def verify_hospital_access(request: Request = None, hospital_id: Optional[str] = None):  # type: ignore[misc]
        return None

from services.medicine_service import (
    # Doctor medicines
    create_doctor_medicine,
    update_doctor_medicine,
    delete_doctor_medicine,
    list_doctor_medicines,
    copy_hospital_medicine_to_doctor,
    upload_medicine_list,
    upload_medicine_list_json,
    # Hospital medicines
    create_hospital_medicine,
    list_hospital_medicines,
    upload_hospital_medicine_list,
    # Matching
    match_medicine_name,
    get_medicine_list_for_prompt,
    # Feedback
    submit_medicine_feedback,
    list_pending_feedback,
    list_feedback_history,
    # Backfill
    backfill_doctor_medicines_from_hospital,
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


class HospitalMedicineCreate(MedicineCreate):
    pass


# ============================================================================
# Doctor Medicine Endpoints
# ============================================================================

@router.get("/{doctor_id}")
async def get_doctor_medicines(
    request: Request,
    doctor_id: str,
    category: Optional[str] = None,
    search: Optional[str] = None,
    _auth = Depends(verify_doctor_access)
):
    """
    List all medicines for a doctor.
    """
    try:
        medicines = list_doctor_medicines(
            doctor_id=uuid.UUID(doctor_id),
            category=category,
            search=search
        )
        return {"medicines": medicines, "count": len(medicines)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.get("/{doctor_id}/combined")
async def get_combined_medicines(
    request: Request,
    doctor_id: str,
    category: Optional[str] = None,
    search: Optional[str] = None,
    _auth = Depends(verify_doctor_access)
):
    """
    List combined medicines for a doctor (doctor list + hospital list, deduplicated).

    Doctor medicines take priority over hospital medicines when duplicates exist.
    Deduplication is based on normalized_name.
    """
    try:
        doctor_uuid = uuid.UUID(doctor_id)

        # Get doctor's own medicines
        doctor_medicines = list_doctor_medicines(
            doctor_id=doctor_uuid,
            category=category,
            search=search
        )

        # Get doctor's hospital_id and fetch hospital medicines
        hospital_id = await get_doctor_hospital_id(doctor_uuid)
        if hospital_id:
            hospital_medicines = list_hospital_medicines(
                hospital_id=hospital_id,
                category=category
            )
        else:
            hospital_medicines = []

        # Deduplicate: doctor medicines take priority
        seen_names = {m["normalized_name"] for m in doctor_medicines}
        combined = list(doctor_medicines)
        for med in hospital_medicines:
            if med["normalized_name"] not in seen_names:
                # Filter by search if provided (hospital list doesn't support search natively)
                if search and search.lower() not in med.get("medicine_name", "").lower():
                    continue
                seen_names.add(med["normalized_name"])
                combined.append(med)

        return {
            "medicines": combined,
            "count": len(combined),
            "doctor_count": len(doctor_medicines),
            "hospital_count": len(hospital_medicines),
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/{doctor_id}")
async def add_doctor_medicine(
    request: Request,
    doctor_id: str,
    data: MedicineCreate,
    _auth = Depends(verify_doctor_access)
):
    """
    Add a single medicine to doctor's list.
    """
    try:
        medicine = create_doctor_medicine(
            doctor_id=uuid.UUID(doctor_id),
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


@router.put("/{doctor_id}/{medicine_id}")
async def update_medicine(
    request: Request,
    doctor_id: str,
    medicine_id: str,
    data: MedicineUpdate,
    _auth = Depends(verify_doctor_access)
):
    """
    Update a medicine in doctor's list.
    """
    try:
        medicine = update_doctor_medicine(
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


@router.delete("/{doctor_id}/{medicine_id}")
async def remove_medicine(
    request: Request,
    doctor_id: str,
    medicine_id: str,
    _auth = Depends(verify_doctor_access)
):
    """
    Soft delete a medicine from doctor's list.
    """
    try:
        success = delete_doctor_medicine(uuid.UUID(medicine_id))
        if not success:
            raise HTTPException(status_code=400, detail="Failed to delete medicine")
        return {"message": "Medicine deleted"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/{doctor_id}/upload")
async def upload_csv(
    request: Request,
    doctor_id: str,
    file: UploadFile = File(...),
    replace_existing: bool = Query(default=False),
    _auth = Depends(verify_doctor_access)
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
            doctor_id=uuid.UUID(doctor_id),
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


@router.post("/{doctor_id}/upload-json")
async def upload_json(
    request: Request,
    doctor_id: str,
    data: MedicineBulkUpload,
    replace_existing: bool = Query(default=False),
    _auth = Depends(verify_doctor_access)
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
            doctor_id=uuid.UUID(doctor_id),
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


@router.post("/{doctor_id}/copy-from-hospital/{hospital_medicine_id}")
async def copy_from_hospital(
    request: Request,
    doctor_id: str,
    hospital_medicine_id: str,
    _auth = Depends(verify_doctor_access)
):
    """
    Copy a hospital medicine to doctor's personal list.
    """
    try:
        result = copy_hospital_medicine_to_doctor(
            hospital_medicine_id=uuid.UUID(hospital_medicine_id),
            doctor_id=uuid.UUID(doctor_id)
        )
        if not result:
            raise HTTPException(status_code=400, detail="Failed to copy medicine")
        return {"message": "Medicine copied", "result": result}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/{doctor_id}/test-match")
async def test_match(
    request: Request,
    doctor_id: str,
    data: MatchTestRequest,
    _auth = Depends(verify_doctor_access)
):
    """
    Test medicine matching without saving.

    Useful for debugging and testing the matching algorithm.
    """
    try:
        result = await match_medicine_name(
            extracted_name=data.medicine_name,
            doctor_id=uuid.UUID(doctor_id),
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


@router.get("/{doctor_id}/prompt-injection")
async def get_prompt_injection(
    request: Request,
    doctor_id: str,
    max_medicines: int = Query(default=3500),
    _auth = Depends(verify_doctor_access)
):
    """
    Get medicine list formatted for prompt injection.

    This is the exact text that will be injected into the extraction prompt.
    """
    try:
        prompt_text = get_medicine_list_for_prompt(
            doctor_id=uuid.UUID(doctor_id),
            max_medicines=max_medicines
        )
        return {
            "doctor_id": doctor_id,
            "prompt_text": prompt_text,
            "character_count": len(prompt_text)
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


# ============================================================================
# Hospital Medicine Endpoints
# ============================================================================

@router.get("/hospital/{hospital_id}")
async def get_hospital_medicines(
    request: Request,
    hospital_id: str,
    category: Optional[str] = None,
    _auth = Depends(verify_hospital_access)
):
    """
    List all medicines for a hospital.
    """
    try:
        medicines = list_hospital_medicines(
            hospital_id=uuid.UUID(hospital_id),
            category=category
        )
        return {"medicines": medicines, "count": len(medicines)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/hospital/{hospital_id}")
async def add_hospital_medicine(
    hospital_id: str,
    data: HospitalMedicineCreate,
    created_by: str = Query(..., description="Admin doctor ID"),
    client: ClientContext = Depends(require_admin)
):
    """
    Add a single medicine to hospital's list.
    """
    try:
        medicine = create_hospital_medicine(
            hospital_id=uuid.UUID(hospital_id),
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
        return {"message": "Hospital medicine added", "medicine": medicine}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to add hospital medicine: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.post("/hospital/{hospital_id}/upload")
async def upload_hospital_csv(
    hospital_id: str,
    file: UploadFile = File(...),
    created_by: str = Query(..., description="Admin doctor ID"),
    replace_existing: bool = Query(default=False),
    client: ClientContext = Depends(require_admin)
):
    """
    Upload CSV file with hospital medicines.
    """
    try:
        content = await file.read()
        csv_content = content.decode('utf-8')

        result = upload_hospital_medicine_list(
            hospital_id=uuid.UUID(hospital_id),
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
        logger.error(f"Hospital upload failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.put("/hospital/{hospital_id}/{medicine_id}")
async def update_hospital_medicine(
    hospital_id: str,
    medicine_id: str,
    data: MedicineUpdate,
    client: ClientContext = Depends(require_admin)
):
    """
    Update a hospital medicine.
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

        result = supabase.table('hospital_medicine_lists').update(
            update_data
        ).eq('id', medicine_id).eq('hospital_id', hospital_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Hospital medicine not found")

        return {"message": "Hospital medicine updated", "medicine": result.data[0]}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to update hospital medicine: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.delete("/hospital/{hospital_id}/{medicine_id}")
async def delete_hospital_medicine(
    hospital_id: str,
    medicine_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Soft delete a hospital medicine (sets is_active=False).
    """
    from services.medicine_service import supabase

    try:
        result = supabase.table('hospital_medicine_lists').update({
            'is_active': False
        }).eq('id', medicine_id).eq('hospital_id', hospital_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Hospital medicine not found")

        return {"message": "Hospital medicine deleted"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to delete hospital medicine: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


# ============================================================================
# Feedback Endpoints
# ============================================================================

@router.get("/feedback/{doctor_id}/pending")
async def get_pending_feedback(
    request: Request,
    doctor_id: str,
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    include_exact_matches: bool = Query(default=False, description="Include exact and common_name matches (default: only fuzzy and doctor_edit)"),
    _auth = Depends(verify_doctor_access)
):
    """
    Get matches pending feedback for a doctor.

    By default, only returns matches that NEED doctor action:
    - 'fuzzy' matches: System guessed a correction → Agree/Disagree
    - 'no_match' matches: New medicine not in any list → Add to list or Correct
    - 'doctor_edit_*' matches: FYI only (doctor already corrected in UI)

    Does NOT return by default (no action needed):
    - 'exact' matches: Gemini used exact name from list
    - 'common_name' matches: Gemini used a known alias

    Set `include_exact_matches=true` to include all pending matches.
    """
    try:
        records = list_pending_feedback(
            doctor_id=uuid.UUID(doctor_id),
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


@router.get("/feedback/{doctor_id}/history")
async def get_feedback_history(
    request: Request,
    doctor_id: str,
    feedback_status: Optional[str] = None,
    confidence_min: Optional[float] = None,
    confidence_max: Optional[float] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    include_exact_matches: bool = Query(default=False, description="Include exact and common_name matches (default: only fuzzy, no_match, doctor_edit)"),
    _auth = Depends(verify_doctor_access)
):
    """
    Get feedback history with filters for the review screen.

    By default, only returns matches that NEED/NEEDED doctor action:
    - 'fuzzy' matches: System guessed a correction
    - 'no_match' matches: New medicine not in any list
    - 'doctor_edit_*' matches: Doctor corrected in UI

    Does NOT return by default (no action needed):
    - 'exact' matches: Gemini used exact name from list
    - 'common_name' matches: Gemini used a known alias

    Set `include_exact_matches=true` to include all matches.
    """
    try:
        result = list_feedback_history(
            doctor_id=uuid.UUID(doctor_id),
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
    doctor_id: str = Query(..., description="Doctor ID for EHR access verification"),
    _auth = Depends(verify_doctor_access)
):
    """
    Submit feedback for a medicine match.

    If agreed with hospital match, auto-copies to doctor's personal list.
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
    doctor_id: str = Query(..., description="Doctor ID for EHR access verification"),
    _auth = Depends(verify_doctor_access)
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

@router.post("/{doctor_id}/backfill-abbreviations")
async def backfill_abbreviations(
    doctor_id: str,
    dry_run: bool = Query(True, description="If true, only report what would be updated without making changes"),
    _admin = Depends(require_admin)
):
    """
    Backfill existing doctor medicines with enriched common_names from
    the expanded abbreviation dictionary. Admin only.

    Use dry_run=true first to preview changes, then dry_run=false to apply.
    """
    try:
        from services.medicine_service import backfill_medicine_abbreviations
        result = backfill_medicine_abbreviations(
            doctor_id=uuid.UUID(doctor_id),
            dry_run=dry_run
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"Abbreviation backfill failed for doctor {doctor_id}: {e}")
        raise HTTPException(status_code=500, detail="Backfill failed")


# ============================================================================
# Backfill - Enrich doctor medicines from hospital list
# ============================================================================

@router.post("/{doctor_id}/backfill-from-hospital")
async def backfill_medicines_from_hospital(
    doctor_id: str,
    dry_run: bool = Query(True, description="If true, only report what would be updated without making changes"),
    _admin = Depends(require_admin)
):
    """
    Backfill doctor medicine entries that have no external_id by matching
    against the hospital medicine list. Admin only.

    Use dry_run=true first to preview changes, then dry_run=false to apply.
    """
    try:
        result = backfill_doctor_medicines_from_hospital(
            doctor_id=uuid.UUID(doctor_id),
            dry_run=dry_run
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"Medicine backfill failed for doctor {doctor_id}: {e}")
        raise HTTPException(status_code=500, detail="Backfill failed")

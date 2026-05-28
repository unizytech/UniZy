"""
Investigations Router - API for Doctor Investigation List Management

Endpoints for:
- Doctor investigation list CRUD
- CSV upload
- Hospital investigation list management
- Investigation matching test
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

from services.investigation_service import (
    # Doctor investigations
    create_doctor_investigation,
    update_doctor_investigation,
    delete_doctor_investigation,
    list_doctor_investigations,
    copy_hospital_investigation_to_doctor,
    upload_investigation_list,
    upload_investigation_list_json,
    # Hospital investigations
    create_hospital_investigation,
    list_hospital_investigations,
    update_hospital_investigation,
    delete_hospital_investigation,
    upload_hospital_investigation_list,
    # Matching
    match_investigation_name,
    get_investigation_list_for_prompt,
    # Feedback
    submit_investigation_feedback,
    list_pending_investigation_feedback,
    list_investigation_feedback_history,
    # Backfill
    backfill_doctor_investigations_from_hospital,
)

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/investigations", tags=["Investigation Lists"])


# ============================================================================
# Request/Response Models
# ============================================================================

class InvestigationCreate(BaseModel):
    investigation_name: str = Field(..., description="Investigation name")
    investigation_type: str = Field(..., description="Type: laboratory, imaging, or other")
    common_names: Optional[List[str]] = Field(default=None, description="Alternative names (e.g., CBC for Complete Blood Count)")
    category: Optional[str] = Field(default=None, description="Category (e.g., Hematology, Radiology)")
    normal_range: Optional[str] = Field(default=None, description="Normal range for lab tests")
    loinc_code: Optional[str] = Field(default=None, description="LOINC code for lab tests")
    cpt_code: Optional[str] = Field(default=None, description="CPT code for procedures")


class InvestigationUpdate(BaseModel):
    investigation_name: Optional[str] = None
    investigation_type: Optional[str] = None
    common_names: Optional[List[str]] = None
    category: Optional[str] = None
    normal_range: Optional[str] = None
    loinc_code: Optional[str] = None
    cpt_code: Optional[str] = None


class MatchTestRequest(BaseModel):
    investigation_name: str = Field(..., description="Investigation name to test")
    investigation_type: Optional[str] = Field(default=None, description="Filter by type")


class FeedbackSubmit(BaseModel):
    feedback_status: str = Field(..., description="agreed or disagreed")
    correct_investigation_id: Optional[str] = Field(default=None, description="Correct investigation UUID if disagreed")
    correct_investigation_name: Optional[str] = Field(default=None, description="Manual entry if disagreed")


class InvestigationBulkItem(BaseModel):
    name: str = Field(..., description="Investigation name (required)")
    external_id: str = Field(..., description="External ID (required)")
    common_names: Optional[Union[List[str], str]] = Field(default=None, description="Alternative names (list or comma-separated string)")
    type: Optional[str] = Field(default=None, description="laboratory, imaging, or other")
    category: Optional[str] = None
    normal_range: Optional[str] = None
    loinc_code: Optional[str] = None
    cpt_code: Optional[str] = None


class InvestigationBulkUpload(BaseModel):
    investigations: List[InvestigationBulkItem]


class HospitalInvestigationCreate(InvestigationCreate):
    pass


# ============================================================================
# Doctor Investigation Endpoints
# ============================================================================

@router.get("/{doctor_id}")
async def get_doctor_investigations(
    request: Request,
    doctor_id: str,
    investigation_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    _auth = Depends(verify_doctor_access)
):
    """
    List all investigations for a doctor.

    Query params:
    - investigation_type: Filter by type (laboratory, imaging, other)
    - category: Filter by category
    - search: Search in names
    """
    try:
        investigations = list_doctor_investigations(
            doctor_id=uuid.UUID(doctor_id),
            investigation_type=investigation_type,
            category=category,
            search=search
        )
        return {"investigations": investigations, "count": len(investigations)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.get("/{doctor_id}/combined")
async def get_combined_investigations(
    request: Request,
    doctor_id: str,
    investigation_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    _auth = Depends(verify_doctor_access)
):
    """
    List combined investigations for a doctor (doctor list + hospital list, deduplicated).

    Doctor investigations take priority over hospital investigations when duplicates exist.
    Deduplication is based on normalized_name.
    """
    try:
        doctor_uuid = uuid.UUID(doctor_id)

        # Get doctor's own investigations
        doctor_investigations = list_doctor_investigations(
            doctor_id=doctor_uuid,
            investigation_type=investigation_type,
            category=category,
            search=search
        )

        # Get doctor's hospital_id and fetch hospital investigations
        hospital_id = await get_doctor_hospital_id(doctor_uuid)
        if hospital_id:
            hospital_investigations = list_hospital_investigations(
                hospital_id=hospital_id,
                investigation_type=investigation_type,
                category=category
            )
        else:
            hospital_investigations = []

        # Deduplicate: doctor investigations take priority
        seen_names = {i["normalized_name"] for i in doctor_investigations}
        combined = list(doctor_investigations)
        for inv in hospital_investigations:
            if inv["normalized_name"] not in seen_names:
                # Filter by search if provided (hospital list doesn't support search natively)
                if search and search.lower() not in inv.get("investigation_name", "").lower():
                    continue
                seen_names.add(inv["normalized_name"])
                combined.append(inv)

        return {
            "investigations": combined,
            "count": len(combined),
            "doctor_count": len(doctor_investigations),
            "hospital_count": len(hospital_investigations),
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/{doctor_id}")
async def add_doctor_investigation(
    request: Request,
    doctor_id: str,
    data: InvestigationCreate,
    _auth = Depends(verify_doctor_access)
):
    """
    Add a single investigation to doctor's list.
    """
    try:
        investigation = create_doctor_investigation(
            doctor_id=uuid.UUID(doctor_id),
            investigation_name=data.investigation_name,
            investigation_type=data.investigation_type,
            common_names=data.common_names,
            category=data.category,
            normal_range=data.normal_range,
            loinc_code=data.loinc_code,
            cpt_code=data.cpt_code
        )
        return {"message": "Investigation added", "investigation": investigation}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to add investigation: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.put("/{doctor_id}/{investigation_id}")
async def update_investigation(
    request: Request,
    doctor_id: str,
    investigation_id: str,
    data: InvestigationUpdate,
    _auth = Depends(verify_doctor_access)
):
    """
    Update an investigation in doctor's list.
    """
    try:
        investigation = update_doctor_investigation(
            investigation_id=uuid.UUID(investigation_id),
            investigation_name=data.investigation_name,
            investigation_type=data.investigation_type,
            common_names=data.common_names,
            category=data.category,
            normal_range=data.normal_range,
            loinc_code=data.loinc_code,
            cpt_code=data.cpt_code
        )
        return {"message": "Investigation updated", "investigation": investigation}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to update investigation: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.delete("/{doctor_id}/{investigation_id}")
async def remove_investigation(
    request: Request,
    doctor_id: str,
    investigation_id: str,
    _auth = Depends(verify_doctor_access)
):
    """
    Soft delete an investigation from doctor's list.
    """
    try:
        success = delete_doctor_investigation(uuid.UUID(investigation_id))
        if not success:
            raise HTTPException(status_code=400, detail="Failed to delete investigation")
        return {"message": "Investigation deleted"}
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
    Upload CSV file with investigations.

    Expected columns: name, common_names, type, category, normal_range, loinc_code, cpt_code
    """
    try:
        # Read file content
        content = await file.read()
        csv_content = content.decode('utf-8')

        result = upload_investigation_list(
            doctor_id=uuid.UUID(doctor_id),
            csv_content=csv_content,
            filename=file.filename or "upload.csv",
            replace_existing=replace_existing
        )
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
    data: InvestigationBulkUpload,
    replace_existing: bool = Query(default=False),
    _auth = Depends(verify_doctor_access)
):
    """
    Upload investigations via JSON body.

    Accepts an array of investigation objects with the same fields as CSV columns.
    Applies identical enrichment, normalization, dedup, and upsert logic.
    """
    try:
        # Convert Pydantic models to dicts matching service expectations
        investigations = []
        for item in data.investigations:
            # Parse common_names: accept list or comma-separated string
            common_names = []
            if item.common_names:
                if isinstance(item.common_names, list):
                    common_names = [n.strip() for n in item.common_names if n.strip()]
                else:
                    common_names = [n.strip() for n in item.common_names.split(',') if n.strip()]

            investigations.append({
                "investigation_name": item.name.strip(),
                "common_names": common_names,
                "investigation_type": item.type.strip().lower() if item.type else None,
                "category": item.category.strip() if item.category else None,
                "normal_range": item.normal_range.strip() if item.normal_range else None,
                "loinc_code": item.loinc_code.strip() if item.loinc_code else None,
                "cpt_code": item.cpt_code.strip() if item.cpt_code else None,
                "external_id": item.external_id.strip(),
            })

        result = upload_investigation_list_json(
            doctor_id=uuid.UUID(doctor_id),
            investigations=investigations,
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


@router.post("/{doctor_id}/copy-from-hospital/{hospital_investigation_id}")
async def copy_from_hospital(
    request: Request,
    doctor_id: str,
    hospital_investigation_id: str,
    _auth = Depends(verify_doctor_access)
):
    """
    Copy a hospital investigation to doctor's personal list.
    """
    try:
        result = copy_hospital_investigation_to_doctor(
            hospital_investigation_id=uuid.UUID(hospital_investigation_id),
            doctor_id=uuid.UUID(doctor_id)
        )
        if not result:
            raise HTTPException(status_code=400, detail="Failed to copy investigation")
        return {"message": "Investigation copied", "result": result}
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
    Test investigation matching without saving.

    Useful for debugging and testing the matching algorithm.
    """
    try:
        result = await match_investigation_name(
            extracted_name=data.investigation_name,
            doctor_id=uuid.UUID(doctor_id),
            investigation_type=data.investigation_type
        )
        return {
            "input": data.investigation_name,
            "investigation_type": data.investigation_type,
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
    max_investigations: int = Query(default=100),
    _auth = Depends(verify_doctor_access)
):
    """
    Get investigation list formatted for prompt injection.

    This is the exact text that will be injected into the extraction prompt.
    """
    try:
        prompt_text = get_investigation_list_for_prompt(
            doctor_id=uuid.UUID(doctor_id),
            max_investigations=max_investigations
        )
        return {
            "doctor_id": doctor_id,
            "prompt_text": prompt_text,
            "character_count": len(prompt_text)
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


# ============================================================================
# Hospital Investigation Endpoints
# ============================================================================

@router.get("/hospital/{hospital_id}")
async def get_hospital_investigations(
    request: Request,
    hospital_id: str,
    investigation_type: Optional[str] = None,
    category: Optional[str] = None,
    _auth = Depends(verify_hospital_access)
):
    """
    List all investigations for a hospital.
    """
    try:
        investigations = list_hospital_investigations(
            hospital_id=uuid.UUID(hospital_id),
            investigation_type=investigation_type,
            category=category
        )
        return {"investigations": investigations, "count": len(investigations)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/hospital/{hospital_id}")
async def add_hospital_investigation(
    hospital_id: str,
    data: HospitalInvestigationCreate,
    created_by: str = Query(..., description="Admin doctor ID"),
    client: ClientContext = Depends(require_admin)
):
    """
    Add a single investigation to hospital's list.
    """
    try:
        investigation = create_hospital_investigation(
            hospital_id=uuid.UUID(hospital_id),
            created_by=uuid.UUID(created_by),
            investigation_name=data.investigation_name,
            investigation_type=data.investigation_type,
            common_names=data.common_names,
            category=data.category,
            normal_range=data.normal_range,
            loinc_code=data.loinc_code,
            cpt_code=data.cpt_code
        )
        return {"message": "Hospital investigation added", "investigation": investigation}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to add hospital investigation: {e}")
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
    Upload CSV file with hospital investigations.
    """
    try:
        content = await file.read()
        csv_content = content.decode('utf-8')

        result = upload_hospital_investigation_list(
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


@router.put("/hospital/{hospital_id}/{investigation_id}")
async def update_hospital_investigation_endpoint(
    hospital_id: str,
    investigation_id: str,
    data: InvestigationUpdate,
    client: ClientContext = Depends(require_admin)
):
    """
    Update a hospital investigation.
    """
    try:
        investigation = update_hospital_investigation(
            investigation_id=uuid.UUID(investigation_id),
            investigation_name=data.investigation_name,
            investigation_type=data.investigation_type,
            common_names=data.common_names,
            category=data.category,
            normal_range=data.normal_range,
            loinc_code=data.loinc_code,
            cpt_code=data.cpt_code
        )
        return {"message": "Hospital investigation updated", "investigation": investigation}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to update hospital investigation: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.delete("/hospital/{hospital_id}/{investigation_id}")
async def delete_hospital_investigation_endpoint(
    hospital_id: str,
    investigation_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Soft delete a hospital investigation (sets is_active=False).
    """
    try:
        success = delete_hospital_investigation(uuid.UUID(investigation_id))
        if not success:
            raise HTTPException(status_code=404, detail="Hospital investigation not found")
        return {"message": "Hospital investigation deleted"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to delete hospital investigation: {e}")
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
    - 'no_match' matches: New investigation not in any list → Add to list or Correct
    - 'doctor_edit' matches: FYI only (doctor already corrected in UI)

    Does NOT return by default (no action needed):
    - 'exact' matches: Gemini used exact name from list
    - 'common_name' matches: Gemini used a known alias

    Set `include_exact_matches=true` to include all pending matches.
    """
    try:
        records = list_pending_investigation_feedback(
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
    investigation_type: Optional[str] = None,
    confidence_min: Optional[float] = None,
    confidence_max: Optional[float] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    include_exact_matches: bool = Query(default=False, description="Include exact and common_name matches (default: only fuzzy, no_match, and doctor_edit)"),
    _auth = Depends(verify_doctor_access)
):
    """
    Get feedback history with filters for the review screen.

    By default, only returns matches that need/needed doctor action:
    - 'fuzzy' matches: System guessed a correction
    - 'no_match' matches: New investigation not in any list
    - 'doctor_edit_*' matches: FYI only (doctor already corrected in UI)

    Does NOT return by default (no action needed):
    - 'exact' matches: Gemini used exact name from list
    - 'common_name' matches: Gemini used a known alias

    Set `include_exact_matches=true` to include all matches.
    """
    try:
        result = list_investigation_feedback_history(
            doctor_id=uuid.UUID(doctor_id),
            feedback_status=feedback_status,
            investigation_type=investigation_type,
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
    _auth = Depends(verify_doctor_access)
):
    """
    Submit feedback for an investigation match.

    If agreed with hospital match, auto-copies to doctor's personal list.
    """
    try:
        correct_id = uuid.UUID(data.correct_investigation_id) if data.correct_investigation_id else None

        result = submit_investigation_feedback(
            match_log_id=uuid.UUID(match_log_id),
            feedback_status=data.feedback_status,
            correct_investigation_id=correct_id,
            correct_investigation_name=data.correct_investigation_name
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
            result = submit_investigation_feedback(
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
# Backfill - Enrich doctor investigations from hospital list
# ============================================================================

@router.post("/{doctor_id}/backfill-from-hospital")
async def backfill_investigations_from_hospital(
    doctor_id: str,
    dry_run: bool = Query(True, description="If true, only report what would be updated without making changes"),
    _admin = Depends(require_admin)
):
    """
    Backfill doctor investigation entries that have no external_id by matching
    against the hospital investigation list. Admin only.

    Use dry_run=true first to preview changes, then dry_run=false to apply.
    """
    try:
        result = backfill_doctor_investigations_from_hospital(
            doctor_id=uuid.UUID(doctor_id),
            dry_run=dry_run
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"Investigation backfill failed for doctor {doctor_id}: {e}")
        raise HTTPException(status_code=500, detail="Backfill failed")

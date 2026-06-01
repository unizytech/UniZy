"""
Investigations Router - API for Counsellor Investigation List Management

Endpoints for:
- Counsellor investigation list CRUD
- CSV upload
- School investigation list management
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

from services.investigation_service import (
    # Counsellor investigations
    create_counsellor_investigation,
    update_counsellor_investigation,
    delete_counsellor_investigation,
    list_counsellor_investigations,
    copy_school_investigation_to_counsellor,
    upload_investigation_list,
    upload_investigation_list_json,
    # School investigations
    create_school_investigation,
    list_school_investigations,
    update_school_investigation,
    delete_school_investigation,
    upload_school_investigation_list,
    # Matching
    match_investigation_name,
    get_investigation_list_for_prompt,
    # Feedback
    submit_investigation_feedback,
    list_pending_investigation_feedback,
    list_investigation_feedback_history,
    # Backfill
    backfill_counsellor_investigations_from_school,
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


class SchoolInvestigationCreate(InvestigationCreate):
    pass


# ============================================================================
# Counsellor Investigation Endpoints
# ============================================================================

@router.get("/{counsellor_id}")
async def get_counsellor_investigations(
    request: Request,
    counsellor_id: str,
    investigation_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    _auth = Depends(verify_counsellor_access)
):
    """
    List all investigations for a counsellor.

    Query params:
    - investigation_type: Filter by type (laboratory, imaging, other)
    - category: Filter by category
    - search: Search in names
    """
    try:
        investigations = list_counsellor_investigations(
            counsellor_id=uuid.UUID(counsellor_id),
            investigation_type=investigation_type,
            category=category,
            search=search
        )
        return {"investigations": investigations, "count": len(investigations)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.get("/{counsellor_id}/combined")
async def get_combined_investigations(
    request: Request,
    counsellor_id: str,
    investigation_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    _auth = Depends(verify_counsellor_access)
):
    """
    List combined investigations for a counsellor (counsellor list + school list, deduplicated).

    Counsellor investigations take priority over school investigations when duplicates exist.
    Deduplication is based on normalized_name.
    """
    try:
        counsellor_uuid = uuid.UUID(counsellor_id)

        # Get counsellor's own investigations
        counsellor_investigations = list_counsellor_investigations(
            counsellor_id=counsellor_uuid,
            investigation_type=investigation_type,
            category=category,
            search=search
        )

        # Get counsellor's school_id and fetch school investigations
        school_id = await get_counsellor_school_id(counsellor_uuid)
        if school_id:
            hospital_investigations = list_school_investigations(
                school_id=school_id,
                investigation_type=investigation_type,
                category=category
            )
        else:
            hospital_investigations = []

        # Deduplicate: counsellor investigations take priority
        seen_names = {i["normalized_name"] for i in counsellor_investigations}
        combined = list(counsellor_investigations)
        for inv in hospital_investigations:
            if inv["normalized_name"] not in seen_names:
                # Filter by search if provided (school list doesn't support search natively)
                if search and search.lower() not in inv.get("investigation_name", "").lower():
                    continue
                seen_names.add(inv["normalized_name"])
                combined.append(inv)

        return {
            "investigations": combined,
            "count": len(combined),
            "counsellor_count": len(counsellor_investigations),
            "hospital_count": len(hospital_investigations),
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/{counsellor_id}")
async def add_counsellor_investigation(
    request: Request,
    counsellor_id: str,
    data: InvestigationCreate,
    _auth = Depends(verify_counsellor_access)
):
    """
    Add a single investigation to counsellor's list.
    """
    try:
        investigation = create_counsellor_investigation(
            counsellor_id=uuid.UUID(counsellor_id),
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


@router.put("/{counsellor_id}/{investigation_id}")
async def update_investigation(
    request: Request,
    counsellor_id: str,
    investigation_id: str,
    data: InvestigationUpdate,
    _auth = Depends(verify_counsellor_access)
):
    """
    Update an investigation in counsellor's list.
    """
    try:
        investigation = update_counsellor_investigation(
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


@router.delete("/{counsellor_id}/{investigation_id}")
async def remove_investigation(
    request: Request,
    counsellor_id: str,
    investigation_id: str,
    _auth = Depends(verify_counsellor_access)
):
    """
    Soft delete an investigation from counsellor's list.
    """
    try:
        success = delete_counsellor_investigation(uuid.UUID(investigation_id))
        if not success:
            raise HTTPException(status_code=400, detail="Failed to delete investigation")
        return {"message": "Investigation deleted"}
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
    Upload CSV file with investigations.

    Expected columns: name, common_names, type, category, normal_range, loinc_code, cpt_code
    """
    try:
        # Read file content
        content = await file.read()
        csv_content = content.decode('utf-8')

        result = upload_investigation_list(
            counsellor_id=uuid.UUID(counsellor_id),
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


@router.post("/{counsellor_id}/upload-json")
async def upload_json(
    request: Request,
    counsellor_id: str,
    data: InvestigationBulkUpload,
    replace_existing: bool = Query(default=False),
    _auth = Depends(verify_counsellor_access)
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
            counsellor_id=uuid.UUID(counsellor_id),
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


@router.post("/{counsellor_id}/copy-from-school/{school_investigation_id}")
async def copy_from_school(
    request: Request,
    counsellor_id: str,
    school_investigation_id: str,
    _auth = Depends(verify_counsellor_access)
):
    """
    Copy a school investigation to counsellor's personal list.
    """
    try:
        result = copy_school_investigation_to_counsellor(
            school_investigation_id=uuid.UUID(school_investigation_id),
            counsellor_id=uuid.UUID(counsellor_id)
        )
        if not result:
            raise HTTPException(status_code=400, detail="Failed to copy investigation")
        return {"message": "Investigation copied", "result": result}
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
    Test investigation matching without saving.

    Useful for debugging and testing the matching algorithm.
    """
    try:
        result = await match_investigation_name(
            extracted_name=data.investigation_name,
            counsellor_id=uuid.UUID(counsellor_id),
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


@router.get("/{counsellor_id}/prompt-injection")
async def get_prompt_injection(
    request: Request,
    counsellor_id: str,
    max_investigations: int = Query(default=100),
    _auth = Depends(verify_counsellor_access)
):
    """
    Get investigation list formatted for prompt injection.

    This is the exact text that will be injected into the extraction prompt.
    """
    try:
        prompt_text = get_investigation_list_for_prompt(
            counsellor_id=uuid.UUID(counsellor_id),
            max_investigations=max_investigations
        )
        return {
            "counsellor_id": counsellor_id,
            "prompt_text": prompt_text,
            "character_count": len(prompt_text)
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


# ============================================================================
# School Investigation Endpoints
# ============================================================================

@router.get("/school/{school_id}")
async def get_school_investigations(
    request: Request,
    school_id: str,
    investigation_type: Optional[str] = None,
    category: Optional[str] = None,
    _auth = Depends(verify_school_access)
):
    """
    List all investigations for a school.
    """
    try:
        investigations = list_school_investigations(
            school_id=uuid.UUID(school_id),
            investigation_type=investigation_type,
            category=category
        )
        return {"investigations": investigations, "count": len(investigations)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/school/{school_id}")
async def add_school_investigation(
    school_id: str,
    data: SchoolInvestigationCreate,
    created_by: str = Query(..., description="Admin counsellor ID"),
    client: ClientContext = Depends(require_admin)
):
    """
    Add a single investigation to school's list.
    """
    try:
        investigation = create_school_investigation(
            school_id=uuid.UUID(school_id),
            created_by=uuid.UUID(created_by),
            investigation_name=data.investigation_name,
            investigation_type=data.investigation_type,
            common_names=data.common_names,
            category=data.category,
            normal_range=data.normal_range,
            loinc_code=data.loinc_code,
            cpt_code=data.cpt_code
        )
        return {"message": "School investigation added", "investigation": investigation}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to add school investigation: {e}")
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
    Upload CSV file with school investigations.
    """
    try:
        content = await file.read()
        csv_content = content.decode('utf-8')

        result = upload_school_investigation_list(
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


@router.put("/school/{school_id}/{investigation_id}")
async def update_school_investigation_endpoint(
    school_id: str,
    investigation_id: str,
    data: InvestigationUpdate,
    client: ClientContext = Depends(require_admin)
):
    """
    Update a school investigation.
    """
    try:
        investigation = update_school_investigation(
            investigation_id=uuid.UUID(investigation_id),
            investigation_name=data.investigation_name,
            investigation_type=data.investigation_type,
            common_names=data.common_names,
            category=data.category,
            normal_range=data.normal_range,
            loinc_code=data.loinc_code,
            cpt_code=data.cpt_code
        )
        return {"message": "School investigation updated", "investigation": investigation}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to update school investigation: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.delete("/school/{school_id}/{investigation_id}")
async def delete_school_investigation_endpoint(
    school_id: str,
    investigation_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Soft delete a school investigation (sets is_active=False).
    """
    try:
        success = delete_school_investigation(uuid.UUID(investigation_id))
        if not success:
            raise HTTPException(status_code=404, detail="School investigation not found")
        return {"message": "School investigation deleted"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to delete school investigation: {e}")
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
    - 'no_match' matches: New investigation not in any list → Add to list or Correct
    - 'doctor_edit' matches: FYI only (counsellor already corrected in UI)

    Does NOT return by default (no action needed):
    - 'exact' matches: Gemini used exact name from list
    - 'common_name' matches: Gemini used a known alias

    Set `include_exact_matches=true` to include all pending matches.
    """
    try:
        records = list_pending_investigation_feedback(
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
    investigation_type: Optional[str] = None,
    confidence_min: Optional[float] = None,
    confidence_max: Optional[float] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    include_exact_matches: bool = Query(default=False, description="Include exact and common_name matches (default: only fuzzy, no_match, and doctor_edit)"),
    _auth = Depends(verify_counsellor_access)
):
    """
    Get feedback history with filters for the review screen.

    By default, only returns matches that need/needed counsellor action:
    - 'fuzzy' matches: System guessed a correction
    - 'no_match' matches: New investigation not in any list
    - 'doctor_edit_*' matches: FYI only (counsellor already corrected in UI)

    Does NOT return by default (no action needed):
    - 'exact' matches: Gemini used exact name from list
    - 'common_name' matches: Gemini used a known alias

    Set `include_exact_matches=true` to include all matches.
    """
    try:
        result = list_investigation_feedback_history(
            counsellor_id=uuid.UUID(counsellor_id),
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
    _auth = Depends(verify_counsellor_access)
):
    """
    Submit feedback for an investigation match.

    If agreed with school match, auto-copies to counsellor's personal list.
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
    counsellor_id: str = Query(..., description="Counsellor ID for EHR access verification"),
    _auth = Depends(verify_counsellor_access)
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
# Backfill - Enrich counsellor investigations from school list
# ============================================================================

@router.post("/{counsellor_id}/backfill-from-school")
async def backfill_investigations_from_school(
    counsellor_id: str,
    dry_run: bool = Query(True, description="If true, only report what would be updated without making changes"),
    _admin = Depends(require_admin)
):
    """
    Backfill counsellor investigation entries that have no external_id by matching
    against the school investigation list. Admin only.

    Use dry_run=true first to preview changes, then dry_run=false to apply.
    """
    try:
        result = backfill_counsellor_investigations_from_school(
            counsellor_id=uuid.UUID(counsellor_id),
            dry_run=dry_run
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"Investigation backfill failed for counsellor {counsellor_id}: {e}")
        raise HTTPException(status_code=500, detail="Backfill failed")

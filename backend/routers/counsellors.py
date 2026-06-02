"""
Counsellor Management Router

REST API endpoints for counsellor CRUD operations.
"""

import os
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uuid
import re

from models.auth_models import ClientContext
from dependencies.auth import require_admin, require_any_scope, get_current_client

from services.counsellor_service import (
    get_all_counsellors,
    search_counsellors,
    get_counsellor,
    create_counsellor,
    update_counsellor,
    deactivate_counsellor,
    get_counsellor_all_configurations
)
from services.supabase_service import invalidate_counsellor_school_cache
from services.auth_service import invalidate_auth_counsellor_school_cache

# Conditional EHR auth imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import EHRCounsellorAccessChecker, get_current_client

    _counsellor_checker = EHRCounsellorAccessChecker()

    async def verify_counsellor_access(request: Request, counsellor_id: Optional[str] = None):  # type: ignore[misc]
        """Verify EHR client has access to counsellor data."""
        counsellor_uuid = uuid.UUID(counsellor_id) if counsellor_id else None
        client = get_current_client(request)
        return await _counsellor_checker(request, counsellor_uuid, client)
else:
    async def verify_counsellor_access(request: Request = None, counsellor_id: Optional[str] = None):  # type: ignore[misc]
        return None

router = APIRouter(prefix="/api/v1/counsellors", tags=["Counsellor Management"])

# Columns to fetch for template listings (excludes large internal fields like assembled_full_prompt)
TEMPLATE_LIST_COLUMNS = "id, template_code, template_name, description, consultation_type_id, is_active, is_default, use_case, specialization, school_id, counsellor_id, estimated_extraction_time_seconds, created_at, updated_at"


def auto_share_school_templates(counsellor_id: str, school_id: str) -> Dict[str, Any]:
    """
    Auto-share all school templates with a newly created counsellor.

    Shares:
    1. The school's default template (from schools.default_template_id)
    2. All templates previously shared with other counsellors in the same school

    Returns dict with shared_count and default_template_shared flag.
    """
    from services.supabase_service import supabase
    import logging
    logger = logging.getLogger(__name__)

    templates_to_share: set = set()  # set of template_ids

    # Query 1: Get school's default template
    school_result = (
        supabase.table("schools")
        .select("default_template_id")
        .eq("id", school_id)
        .execute()
    )

    default_template_id = None
    if school_result.data and school_result.data[0].get("default_template_id"):
        default_template_id = school_result.data[0]["default_template_id"]
        templates_to_share.add(default_template_id)

    # Query 2: Get all other active counsellors in this school
    other_counsellors = (
        supabase.table("counsellors")
        .select("id")
        .eq("school_id", school_id)
        .eq("is_active", True)
        .neq("id", counsellor_id)
        .execute()
    )

    if other_counsellors.data:
        other_counsellor_ids = [d["id"] for d in other_counsellors.data]

        # Query 3: Get all active templates shared with those counsellors
        shared_entries = (
            supabase.table("counsellor_templates")
            .select("template_id")
            .in_("counsellor_id", other_counsellor_ids)
            .eq("is_active", True)
            .execute()
        )

        if shared_entries.data:
            for entry in shared_entries.data:
                templates_to_share.add(entry["template_id"])

    if not templates_to_share:
        return {"shared_count": 0, "default_template_shared": False}

    # Query 4: Upsert all templates for the new counsellor
    upsert_data = [
        {
            "counsellor_id": counsellor_id,
            "template_id": tid,
            "access_level": "use",
            "is_active": True,
        }
        for tid in templates_to_share
    ]

    supabase.table("counsellor_templates").upsert(
        upsert_data,
        on_conflict="counsellor_id,template_id"
    ).execute()

    logger.info(f"Auto-shared {len(templates_to_share)} template(s) with new counsellor {counsellor_id} in school {school_id}")

    return {
        "shared_count": len(templates_to_share),
        "default_template_shared": default_template_id is not None
    }


def get_school_default_ehr_type_id(school_id: str) -> Optional[str]:
    """
    Get the default EHR type ID for a school.

    Returns the ehr_type_id of the school_ehr record marked as is_default=true.
    Returns None if no default is configured.
    """
    from services.supabase_service import supabase

    result = (
        supabase.table("school_ehr")
        .select("ehr_type_id")
        .eq("school_id", school_id)
        .eq("is_default", True)
        .eq("is_enabled", True)
        .limit(1)
        .execute()
    )

    if result.data and result.data[0].get("ehr_type_id"):
        return result.data[0]["ehr_type_id"]

    return None


# ============================================================================
# Request/Response Models
# ============================================================================

class CounsellorCreateRequest(BaseModel):
    """Request model for creating a counsellor"""
    email: str = Field(..., description="Doctor's email address")
    full_name: str = Field(..., min_length=2, max_length=255, description="Doctor's full name")
    specialization: Optional[str] = Field(None, max_length=100, description="Medical specialization")
    default_template: Optional[str] = Field(None, description="Default template")
    default_transcription_engine: str = Field("gemini", description="Default transcription engine")
    default_transcription_model: str = Field("gemini-2.5-flash", description="Default transcription model")


class CounsellorCreateWithSchoolRequest(BaseModel):
    """Request model for creating a counsellor with school code lookup"""
    id: str = Field(..., description="Counsellor UUID (provided by caller)")
    school_code: str = Field(..., min_length=1, max_length=50, description="School code to lookup school_id")
    full_name: str = Field(..., min_length=2, max_length=255, description="Doctor's full name")
    email: str = Field(..., description="Doctor's email address")
    specialization: Optional[str] = Field(None, max_length=100, description="Medical specialization")


class CounsellorCreateEHRRequest(BaseModel):
    """Request model for EHR integration - auto-generates UUID"""
    school_code: str = Field(..., min_length=1, max_length=50, description="School code to lookup school_id")
    full_name: str = Field(..., min_length=2, max_length=255, description="Doctor's full name")
    email: str = Field(..., description="Doctor's email address")
    specialization: Optional[str] = Field(None, max_length=100, description="Medical specialization")


class CounsellorUpdateRequest(BaseModel):
    """Request model for updating a counsellor"""
    email: Optional[str] = Field(None, description="New email address")
    full_name: Optional[str] = Field(None, min_length=2, max_length=255, description="New full name")
    specialization: Optional[str] = Field(None, max_length=100, description="New specialization")
    default_template: Optional[str] = Field(None, description="New default template")
    default_transcription_engine: Optional[str] = Field(None, description="New default engine")
    default_transcription_model: Optional[str] = Field(None, description="New default model")
    is_active: Optional[bool] = Field(None, description="Active status")
    op_consultation_fee: Optional[float] = Field(None, ge=0, description="OP consultation fee")
    ip_primary_consultation_fee: Optional[float] = Field(None, ge=0, description="IP primary consultation fee")
    ip_secondary_consultation_fee: Optional[float] = Field(None, ge=0, description="IP secondary consultation fee")
    translation_language: Optional[str] = Field(None, max_length=20, description="Target Indic language for extraction translation (e.g., tamil, hindi, telugu)")


class TemplateCreateRequest(BaseModel):
    """Request model for creating a template"""
    template_code: str = Field(..., description="Unique template code for this counsellor")
    template_name: str = Field(..., description="Display name for the template")
    consultation_type_id: str = Field(..., description="Consultation type UUID")
    description: Optional[str] = Field(None, description="Template description")


class TemplateUpdateRequest(BaseModel):
    """Request model for updating a template"""
    template_name: Optional[str] = Field(None, description="New template name")
    description: Optional[str] = Field(None, description="New description")
    is_active: Optional[bool] = Field(None, description="Active status")


class CounsellorSegmentRequest(BaseModel):
    """Request model for counsellors to create segment requests (without schema)"""
    segment_name: str = Field(..., min_length=1, max_length=255, description="Display name for the segment")
    description: str = Field(..., min_length=10, description="Description of what to extract from the consultation")
    default_category: str = Field("additional", pattern="^(core|additional)$", description="Default category")
    default_brevity: str = Field("balanced", pattern="^(concise|balanced|detailed)$", description="Brevity level")
    default_terminology: str = Field("medical_terms", pattern="^(medical_terms|simple_terms|as_spoken)$", description="Terminology style")


class SetCounsellorDefaultTemplateRequest(BaseModel):
    """Request model for setting counsellor's default template"""
    template_id: Optional[str] = Field(None, description="Template UUID to set as default (null to clear)")


# ============================================================================
# Counsellor CRUD Endpoints
# ============================================================================

@router.get("")
async def list_counsellors(
    active_only: bool = Query(True, description="Filter by active status"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get all counsellors.

    **Query Parameters:**
    - `active_only`: Filter to show only active counsellors (default: true)

    **Returns:**
    - List of counsellor records with metadata
    """
    try:
        counsellors = get_all_counsellors(is_active=active_only)

        return {
            "success": True,
            "counsellors": counsellors,
            "count": len(counsellors)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch counsellors")


@router.get("/search")
async def search_counsellors_endpoint(
    q: str = Query(..., min_length=2, description="Search query (name or email)"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Search counsellors by name or email.

    **Query Parameters:**
    - `q`: Search term (case-insensitive, minimum 2 characters)

    **Returns:**
    - List of matching counsellor records
    """
    try:
        results = search_counsellors(q)

        return {
            "success": True,
            "query": q,
            "counsellors": results,
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Search failed")


# ============================================================================
# List Endpoints for Sharing Templates (MUST be before /{counsellor_id})
# ============================================================================

@router.get("/list-all")
async def list_all_counsellors_for_sharing(
    school_id: Optional[str] = Query(None, description="Filter by school ID"),
    client: ClientContext = Depends(get_current_client)  # Changed from require_admin - any authenticated user
) -> Dict[str, Any]:
    """
    Get list of all active counsellors for sharing templates and filtering.

    Returns simplified counsellor list with id, name, email, specialization, school_id, and ehr_type_id.
    Used by ShareTemplateModal to display counsellor checkboxes and dashboard counsellor dropdown.

    **Query Parameters:**
    - school_id: Optional filter by school

    **Response:**
    ```json
    {
        "success": true,
        "counsellors": [
            {
                "id": "uuid",
                "full_name": "Dr. John Doe",
                "email": "john@example.com",
                "specialization": "Cardiology",
                "school_id": "uuid",
                "ehr_type_id": "uuid"
            }
        ],
        "count": 10
    }
    ```
    """
    try:
        from services.supabase_service import supabase

        query = (
            supabase.table("counsellors")
            .select("id, full_name, email, specialization, school_id, ehr_type_id")
            .eq("is_active", True)
        )

        # Filter by school_id if provided
        if school_id:
            query = query.eq("school_id", school_id)

        response = query.order("full_name").execute()

        return {
            "success": True,
            "counsellors": response.data or [],
            "count": len(response.data or [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch counsellors")


@router.get("/schools")
async def list_schools(
    client: ClientContext = Depends(get_current_client)  # Any authenticated user
) -> Dict[str, Any]:
    """
    Get list of all active schools.

    Returns school list with id, name, and location info.
    Used by ShareTemplateModal to display school checkboxes.

    **Response:**
    ```json
    {
        "success": true,
        "schools": [
            {
                "id": "uuid",
                "school_name": "City General School",
                "city": "Mumbai",
                "state": "Maharashtra"
            }
        ],
        "count": 5
    }
    ```
    """
    try:
        from services.supabase_service import supabase

        response = (
            supabase.table("schools")
            .select("id, school_name, school_code, city, state, default_template_id, use_ffmpeg_stitching, enable_realtime_subscription, audio_quality_block_threshold, min_transcript_length, max_silence_ratio, min_snr_db, min_rms_db, min_speech_ratio, enable_audio_validation, silence_thresh_dbfs, min_silence_len_ms, silence_padding_ms")
            .eq("is_active", True)
            .order("school_name")
            .execute()
        )

        return {
            "success": True,
            "schools": response.data or [],
            "count": len(response.data or [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch schools")


@router.get("/specializations")
async def list_specializations(
    client: ClientContext = Depends(get_current_client)  # Any authenticated user
) -> Dict[str, Any]:
    """
    Get list of distinct specializations from active counsellors.

    Returns unique specialization values currently in use.
    Used by ShareTemplateModal to display specialization checkboxes.

    **Response:**
    ```json
    {
        "success": true,
        "specializations": [
            "Cardiology",
            "Psychiatry",
            "Pediatrics",
            "Orthopedics",
            "General Practice"
        ],
        "count": 5
    }
    ```
    """
    try:
        from services.supabase_service import supabase

        # Get distinct specializations from active counsellors
        response = (
            supabase.table("counsellors")
            .select("specialization")
            .eq("is_active", True)
            .execute()
        )

        # Extract unique non-null specializations
        specializations = set()
        for counsellor in (response.data or []):
            spec = counsellor.get("specialization")
            if spec and spec.strip():
                specializations.add(spec.strip())

        specializations_list = sorted(list(specializations))

        return {
            "success": True,
            "specializations": specializations_list,
            "count": len(specializations_list)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch specializations")


@router.get("/{counsellor_id}")
async def get_counsellor_endpoint(
    request: Request,
    counsellor_id: str,
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Get counsellor by ID.

    **Path Parameters:**
    - `counsellor_id`: Counsellor UUID

    **Returns:**
    - Counsellor record with full details
    """
    try:
        counsellor = get_counsellor(counsellor_id)

        if not counsellor:
            raise HTTPException(status_code=404, detail="Counsellor not found")

        return {
            "success": True,
            "doctor": counsellor
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch counsellor")


@router.post("")
async def create_counsellor_endpoint(
    request: CounsellorCreateRequest,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Create new counsellor with random UUID.

    **Request Body:**
    ```json
    {
        "email": "counsellor@school.com",
        "full_name": "Dr. John Smith",
        "specialization": "Psychiatry",
        "default_template": null,
        "default_transcription_engine": "gemini",
        "default_transcription_model": "gemini-2.5-flash"
    }
    ```

    **Returns:**
    - Created counsellor record with generated UUID

    **Notes:**
    - No Supabase auth integration (uses random UUID)
    - Email must be unique
    """
    try:
        counsellor = create_counsellor(
            email=request.email,
            full_name=request.full_name,
            specialization=request.specialization,
            default_template=request.default_template,
            default_transcription_engine=request.default_transcription_engine,
            default_transcription_model=request.default_transcription_model
        )

        return {
            "success": True,
            "message": f"Counsellor '{request.full_name}' created successfully",
            "doctor": counsellor
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create counsellor")


@router.post("/with-school")
async def create_counsellor_with_school(
    request: CounsellorCreateWithSchoolRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Create new counsellor with provided UUID and school code lookup.

    **Auth:** Admin, Web, and EHR (EHR restricted to own school)

    **Request Body:**
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "school_code": "HOSP001",
        "full_name": "Dr. John Smith",
        "email": "counsellor@school.com",
        "specialization": "Psychiatry"
    }
    ```

    **Returns:**
    - success: True if counsellor created
    - message: Success message
    - counsellor_id: UUID of created counsellor

    **Notes:**
    - UUID is provided by caller (not auto-generated)
    - school_id is looked up from schools table using school_code
    - Email must be unique
    """
    try:
        from services.supabase_service import supabase
        from datetime import datetime

        # Validate UUID format
        try:
            counsellor_uuid = uuid.UUID(request.id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID format")

        # Lookup school_id from school_code
        school_response = (
            supabase.table("schools")
            .select("id")
            .eq("school_code", request.school_code)
            .eq("is_active", True)
            .execute()
        )

        if not school_response.data or len(school_response.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="School not found or inactive"
            )

        school_id = school_response.data[0]["id"]

        # EHR clients can only create counsellors in their own school
        if client.client_type == "ehr":
            if client.school_id is None or str(client.school_id) != school_id:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )

        # Check if counsellor ID already exists
        existing_id = (
            supabase.table("counsellors")
            .select("id")
            .eq("id", str(counsellor_uuid))
            .execute()
        )

        if existing_id.data and len(existing_id.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Counsellor with this ID already exists"
            )

        # Check if email already exists
        existing_email = (
            supabase.table("counsellors")
            .select("id")
            .eq("email", request.email)
            .execute()
        )

        if existing_email.data and len(existing_email.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Counsellor with this email already exists"
            )

        # Get school's default EHR type (if any)
        default_ehr_type_id = get_school_default_ehr_type_id(school_id)

        # Create counsellor with provided UUID and school_id
        counsellor_data = {
            "id": str(counsellor_uuid),
            "school_id": school_id,
            "full_name": request.full_name,
            "email": request.email,
            "specialization": request.specialization,
            "ehr_type_id": default_ehr_type_id,  # Auto-assign school's default EHR
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        response = supabase.table("counsellors").insert(counsellor_data).execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to create counsellor")

        # Auto-share school templates with new counsellor
        share_result = auto_share_school_templates(str(counsellor_uuid), school_id)

        message = f"Counsellor '{request.full_name}' created successfully"
        if share_result["shared_count"] > 0:
            message += f" ({share_result['shared_count']} school template(s) auto-shared)"
        if default_ehr_type_id:
            message += " (school default EHR type auto-assigned)"

        return {
            "success": True,
            "message": message,
            "counsellor_id": str(counsellor_uuid),
            "hospital_templates_shared": share_result["shared_count"],
            "ehr_type_id": default_ehr_type_id
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create counsellor")


@router.post("/ehr")
async def create_counsellor_ehr(
    request: CounsellorCreateEHRRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Create new counsellor for EHR integration with auto-generated UUID.

    **Auth:** Admin, Web, and EHR (EHR restricted to own school)

    **Request Body:**
    ```json
    {
        "school_code": "HOSP001",
        "full_name": "Dr. John Smith",
        "email": "counsellor@school.com",
        "specialization": "Psychiatry"
    }
    ```

    **Returns:**
    - success: True if counsellor created
    - message: Success message
    - counsellor_id: Auto-generated UUID of created counsellor

    **Notes:**
    - UUID is auto-generated (not provided by caller)
    - school_id is looked up from schools table using school_code
    - Email must be unique
    - Returns 409 if email already exists
    - Returns 404 if school_code not found
    """
    try:
        from services.supabase_service import supabase
        from datetime import datetime

        # Generate new UUID
        counsellor_uuid = uuid.uuid4()

        # Lookup school_id from school_code
        school_response = (
            supabase.table("schools")
            .select("id")
            .eq("school_code", request.school_code)
            .eq("is_active", True)
            .execute()
        )

        if not school_response.data or len(school_response.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="School not found or inactive"
            )

        school_id = school_response.data[0]["id"]

        # EHR clients can only create counsellors in their own school
        if client.client_type == "ehr":
            if client.school_id is None or str(client.school_id) != school_id:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )

        # Check if email already exists
        existing_email = (
            supabase.table("counsellors")
            .select("id")
            .eq("email", request.email)
            .execute()
        )

        if existing_email.data and len(existing_email.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Counsellor with this email already exists"
            )

        # Get school's default EHR type (if any)
        default_ehr_type_id = get_school_default_ehr_type_id(school_id)

        # Create counsellor with auto-generated UUID and school_id
        counsellor_data = {
            "id": str(counsellor_uuid),
            "school_id": school_id,
            "full_name": request.full_name,
            "email": request.email,
            "specialization": request.specialization,
            "ehr_type_id": default_ehr_type_id,  # Auto-assign school's default EHR
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        response = supabase.table("counsellors").insert(counsellor_data).execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to create counsellor")

        # Auto-share school templates with new counsellor
        share_result = auto_share_school_templates(str(counsellor_uuid), school_id)

        message = f"Counsellor '{request.full_name}' created successfully"
        if share_result["shared_count"] > 0:
            message += f" ({share_result['shared_count']} school template(s) auto-shared)"
        if default_ehr_type_id:
            message += " (school default EHR type auto-assigned)"

        return {
            "success": True,
            "message": message,
            "counsellor_id": str(counsellor_uuid),
            "hospital_templates_shared": share_result["shared_count"],
            "ehr_type_id": default_ehr_type_id
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create counsellor")


@router.put("/{counsellor_id}")
async def update_counsellor_endpoint(
    http_request: Request,
    counsellor_id: str,
    request: CounsellorUpdateRequest,
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Update counsellor information.

    **Path Parameters:**
    - `counsellor_id`: Counsellor UUID

    **Request Body:**
    - Any fields to update (all optional)

    **Returns:**
    - Updated counsellor record
    """
    try:
        counsellor = update_counsellor(
            counsellor_id=counsellor_id,
            email=request.email,
            full_name=request.full_name,
            specialization=request.specialization,
            default_template=request.default_template,
            default_transcription_engine=request.default_transcription_engine,
            default_transcription_model=request.default_transcription_model,
            is_active=request.is_active,
            op_consultation_fee=request.op_consultation_fee,
            ip_primary_consultation_fee=request.ip_primary_consultation_fee,
            ip_secondary_consultation_fee=request.ip_secondary_consultation_fee,
            translation_language=request.translation_language,
        )

        return {
            "success": True,
            "message": f"Counsellor updated successfully",
            "doctor": counsellor
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update counsellor")


@router.delete("/{counsellor_id}/permanent")
async def hard_delete_counsellor(
    counsellor_id: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Permanently delete a counsellor. This is irreversible.

    **Auth:** Admin only

    Blocks deletion if counsellor has:
    - Recording sessions
    - extractions

    Cascades deletion of:
    - counsellor_templates, counsellor_medicines, counsellor_investigations
    - counsellor_layer_preferences, counsellor_practice_styles
    - assistant_counsellors associations
    - LLM usage logs, match logs
    - Segment definitions created by counsellor
    """
    try:
        from services.supabase_service import supabase

        # Validate counsellor exists
        existing = (
            supabase.table("counsellors")
            .select("id, full_name")
            .eq("id", counsellor_id)
            .execute()
        )

        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="Counsellor not found")

        counsellor_name = existing.data[0]["full_name"]

        # Block if recording sessions exist
        sessions_check = (
            supabase.table("recording_sessions")
            .select("id")
            .eq("counsellor_id", counsellor_id)
            .limit(1)
            .execute()
        )

        if sessions_check.data and len(sessions_check.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete: Counsellor has recording sessions. Deactivate instead."
            )

        # Block if extractions exist
        extractions_check = (
            supabase.table("extractions")
            .select("id")
            .eq("counsellor_id", counsellor_id)
            .limit(1)
            .execute()
        )

        if extractions_check.data and len(extractions_check.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete: Counsellor has extractions. Deactivate instead."
            )

        # Cascade delete config/association data
        for table in [
            "counsellor_templates",
            "counsellor_medicines",
            "counsellor_investigations",
            "counsellor_layer_preferences",
            "counsellor_practice_styles",
            "assistant_counsellors",
            "llm_usage_log",
            "medicine_match_log",
            "investigation_match_log",
            "medicine_list_uploads",
            "investigation_list_uploads",
            "student_sharing",
            "triage_feedback",
            "triage_suggestion_log",
            "qa_query_history",
            "extraction_embeddings",
            "segment_embeddings",
            "realtime_extraction_responses",
        ]:
            try:
                supabase.table(table).delete().eq("counsellor_id", counsellor_id).execute()
            except Exception:
                pass

        # Handle segment_definitions (counsellor_id and approved_by_admin_id)
        try:
            supabase.table("segment_definitions").delete().eq("counsellor_id", counsellor_id).execute()
        except Exception:
            pass

        # Handle templates owned by counsellor
        try:
            supabase.table("templates").delete().eq("counsellor_id", counsellor_id).execute()
        except Exception:
            pass

        # Finally delete the counsellor
        supabase.table("counsellors").delete().eq("id", counsellor_id).execute()

        return {
            "success": True,
            "message": f"Counsellor '{counsellor_name}' permanently deleted"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete counsellor")


@router.delete("/{counsellor_id}")
async def deactivate_counsellor_endpoint(
    counsellor_id: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Soft delete counsellor (set is_active to false).

    **Path Parameters:**
    - `counsellor_id`: Counsellor UUID

    **Returns:**
    - Updated counsellor record with is_active=false

    **Notes:**
    - This is a soft delete - counsellor record is preserved
    - Counsellor will not appear in active counsellor lists
    """
    try:
        counsellor = deactivate_counsellor(counsellor_id)

        return {
            "success": True,
            "message": f"Counsellor '{counsellor['full_name']}' deactivated successfully",
            "doctor": counsellor
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Counsellor not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to deactivate counsellor")


# ============================================================================
# Counsellor Configuration Endpoints
# ============================================================================

@router.get("/{counsellor_id}/configurations")
async def get_counsellor_configurations(
    request: Request,
    counsellor_id: str,
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Get all segment configurations for a counsellor.

    **Path Parameters:**
    - `counsellor_id`: Counsellor UUID

    **Returns:**
    - Counsellor info
    - Global configuration (applies across all consultation types)
    - Consultation-specific configurations (OP, DISCHARGE, RESPIRATORY)

    **Response Structure:**
    ```json
    {
        "success": true,
        "doctor": {...},
        "global_config": [...],
        "consultation_configs": {
            "OP": [...],
            "DISCHARGE": [...],
            "RESPIRATORY": [...]
        }
    }
    ```

    **Configuration Levels:**
    - **Global**: consultation_type_id = NULL (applies to all types)
    - **Consultation-Specific**: Overrides global for specific type
    """
    try:
        config_data = get_counsellor_all_configurations(counsellor_id)

        return {
            "success": True,
            **config_data
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch configurations")


# ============================================================================
# Template Management Endpoints (NEW - Replaces activated-templates)
# ============================================================================

@router.get("/{counsellor_id}/templates")
async def get_counsellor_templates(
    request: Request,
    counsellor_id: str,
    active_only: bool = Query(True, description="Filter by active status"),
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Get all templates owned by a counsellor.

    **Path Parameters:**
    - `counsellor_id`: Counsellor UUID

    **Query Parameters:**
    - `active_only`: Show only active templates (default: true)

    **Returns:**
    - List of templates owned by the counsellor
    - Includes template metadata and consultation type information

    **Response Structure:**
    ```json
    {
        "success": true,
        "templates": [
            {
                "id": "template-uuid",
                "template_code": "PSYCHIATRY_CORE",
                "template_name": "Psychiatry Core Template",
                "consultation_type_id": "type-uuid",
                "consultation_type_code": "OP",
                "consultation_type_name": "Outpatient Consultation",
                "description": "Template description",
                "is_active": true,
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z"
            }
        ],
        "count": 1
    }
    ```

    **Note:** In the new architecture, templates are directly owned by counsellors
    via the `counsellor_id` column. No separate activation table needed.
    """
    try:
        from services.supabase_service import supabase

        # Query templates table with counsellor_id filter
        query = (
            supabase.table("templates")
            .select("""
                id,
                template_code,
                template_name,
                description,
                consultation_type_id,
                counsellor_id,
                is_active,
                created_at,
                updated_at,
                consultation_types(
                    id,
                    type_code,
                    type_name
                )
            """)
            .eq("counsellor_id", counsellor_id)
        )

        if active_only:
            query = query.eq("is_active", True)

        response = query.order("updated_at", desc=True).execute()

        # Build template list with full metadata
        templates = []
        for row in response.data:
            consultation_type = row.get("consultation_types") or {}

            templates.append({
                "id": row["id"],
                "template_code": row.get("template_code"),
                "template_name": row.get("template_name"),
                "description": row.get("description"),
                "consultation_type_id": row.get("consultation_type_id"),
                "consultation_type_code": consultation_type.get("type_code"),
                "consultation_type_name": consultation_type.get("type_name"),
                "counsellor_id": row.get("counsellor_id"),
                "is_active": row.get("is_active", True),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at")
            })

        return {
            "success": True,
            "templates": templates,
            "count": len(templates)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch templates")


@router.post("/{counsellor_id}/templates")
async def create_counsellor_template(
    http_request: Request,
    counsellor_id: str,
    request: TemplateCreateRequest,
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Create a new template for a counsellor.

    **Path Parameters:**
    - `counsellor_id`: Counsellor UUID

    **Request Body:**
    ```json
    {
        "template_code": "MY_CUSTOM_TEMPLATE",
        "template_name": "My Custom Template",
        "consultation_type_id": "consultation-type-uuid",
        "description": "Template description"
    }
    ```

    **Returns:**
    - Created template record

    **Notes:**
    - Template code must be unique per counsellor (enforced by database constraint)
    - Template is automatically set to is_active=true
    """
    try:
        from services.supabase_service import supabase

        # Verify counsellor exists
        counsellor = get_counsellor(counsellor_id)
        if not counsellor:
            raise ValueError("Counsellor not found")

        # Create template
        template_data = {
            "counsellor_id": counsellor_id,
            "template_code": request.template_code,
            "template_name": request.template_name,
            "consultation_type_id": request.consultation_type_id,
            "is_active": True
        }

        if request.description:
            template_data["description"] = request.description

        response = (
            supabase.table("templates")
            .insert(template_data)
            .execute()
        )

        if not response.data:
            raise ValueError("Failed to create template")

        return {
            "success": True,
            "message": f"Template '{request.template_name}' created successfully",
            "template": response.data[0]
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        # Handle unique constraint violation
        if "duplicate key" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail="Template with this code already exists for this counsellor"
            )
        raise HTTPException(status_code=500, detail="Failed to create template")


@router.get("/{counsellor_id}/templates/{template_id}")
async def get_counsellor_template(
    request: Request,
    counsellor_id: str,
    template_id: str,
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Get a specific template owned by a counsellor.

    **Path Parameters:**
    - `counsellor_id`: Counsellor UUID
    - `template_id`: Template UUID

    **Returns:**
    - Template record with full details
    """
    try:
        from services.supabase_service import supabase

        # Use explicit columns to exclude large internal fields (assembled_full_prompt, assembled_schema_json)
        response = (
            supabase.table("templates")
            .select(f"""
                {TEMPLATE_LIST_COLUMNS},
                consultation_types(
                    id,
                    type_code,
                    type_name
                )
            """)
            .eq("id", template_id)
            .eq("counsellor_id", counsellor_id)
            .execute()
        )

        if not response.data:
            raise ValueError(f"Template not found or does not belong to counsellor")

        return {
            "success": True,
            "template": response.data[0]
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Template not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch template")


@router.put("/{counsellor_id}/templates/{template_id}")
async def update_counsellor_template(
    http_request: Request,
    counsellor_id: str,
    template_id: str,
    request: TemplateUpdateRequest,
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Update a template owned by a counsellor.

    **Path Parameters:**
    - `counsellor_id`: Counsellor UUID
    - `template_id`: Template UUID

    **Request Body:**
    - All fields optional (update only what's provided)

    **Returns:**
    - Updated template record

    **Notes:**
    - Cannot update template_code (immutable after creation)
    - Cannot change counsellor_id (templates cannot be transferred)
    """
    try:
        from services.supabase_service import supabase

        # Verify template exists and belongs to counsellor
        existing = (
            supabase.table("templates")
            .select("id")
            .eq("id", template_id)
            .eq("counsellor_id", counsellor_id)
            .execute()
        )

        if not existing.data:
            raise ValueError(f"Template not found or does not belong to counsellor")

        # Build update data
        update_data = {}
        if request.template_name is not None:
            update_data["template_name"] = request.template_name
        if request.description is not None:
            update_data["description"] = request.description
        if request.is_active is not None:
            update_data["is_active"] = request.is_active

        if not update_data:
            raise ValueError("No update fields provided")

        # Update template
        response = (
            supabase.table("templates")
            .update(update_data)
            .eq("id", template_id)
            .eq("counsellor_id", counsellor_id)
            .execute()
        )

        if not response.data:
            raise ValueError("Failed to update template")

        return {
            "success": True,
            "message": "Template updated successfully",
            "template": response.data[0]
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update template")


@router.delete("/{counsellor_id}/templates/{template_id}")
async def delete_counsellor_template(
    request: Request,
    counsellor_id: str,
    template_id: str,
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Soft delete a template (set is_active=false).

    **Path Parameters:**
    - `counsellor_id`: Counsellor UUID
    - `template_id`: Template UUID

    **Returns:**
    - Updated template record with is_active=false

    **Notes:**
    - This is a soft delete - template record is preserved
    - Template will not appear in active template lists
    - Associated segment configurations are preserved
    """
    try:
        from services.supabase_service import supabase

        # Verify template exists and belongs to counsellor
        existing = (
            supabase.table("templates")
            .select("id, template_name")
            .eq("id", template_id)
            .eq("counsellor_id", counsellor_id)
            .execute()
        )

        if not existing.data:
            raise ValueError(f"Template not found or does not belong to counsellor")

        template_name = existing.data[0].get("template_name", "Unknown")

        # Soft delete
        response = (
            supabase.table("templates")
            .update({"is_active": False})
            .eq("id", template_id)
            .eq("counsellor_id", counsellor_id)
            .execute()
        )

        if not response.data:
            raise ValueError("Failed to delete template")

        return {
            "success": True,
            "message": f"Template '{template_name}' deactivated successfully",
            "template": response.data[0]
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Template not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete template")


# ============================================================================
# Segment Request Endpoints (NEW)
# ============================================================================

@router.post("/{counsellor_id}/segments/request")
async def request_new_segment(
    http_request: Request,
    counsellor_id: str,
    request: CounsellorSegmentRequest,
    template_code: str = Query(..., description="Template code (context for segment creation)"),
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Request a new segment (Counsellor - No Schema Required).

    Counsellors can request new segments from within their activated template.
    The segment is created with status='pending_approval' and awaits admin review.

    **Workflow:**
    1. Counsellor submits simplified segment request (no schema)
    2. Segment is stored with template_id (links it to the requesting counsellor's template)
    3. Admin reviews pending requests via GET /api/v1/admin/segments/pending
    4. Admin adds JSON schema and approves via PUT /api/v1/admin/segments/{segment_code}/approve
    5. Upon approval, segment is automatically added to template_segments junction table
    6. Segment becomes available in the template

    **Path Parameters:**
    - counsellor_id: Counsellor UUID creating the request

    **Query Parameters:**
    - template_code: Template under which segment is being created (to derive consultation type and link to template)

    **Request Body:**
    - segment_name: Display name for the segment
    - description: What to extract from consultation
    - default_category: core or additional
    - default_brevity: concise/balanced/detailed
    - default_terminology: medical_terms/simple_terms/as_spoken

    **Returns:**
    - success: True if segment request created
    - message: Confirmation message
    - segment: Created segment record with template_id and status='pending_approval'
    """
    try:
        from services.supabase_service import create_segment_request, get_template_by_code

        counsellor_uuid = uuid.UUID(counsellor_id)

        # Get template to derive consultation type and template_id
        template = get_template_by_code(template_code)
        if not template:
            raise ValueError("Template not found")

        # Verify the template belongs to this counsellor
        if str(template.get("counsellor_id")) != counsellor_id:
            raise ValueError("Template does not belong to this counsellor")

        consultation_type_code = template.get("consultation_type_code")
        if not consultation_type_code:
            raise ValueError("Template has no consultation type")

        template_id = template.get("id")
        if not template_id:
            raise ValueError("Template has no ID")

        # Auto-generate segment_code from segment_name
        # Convert to uppercase, replace spaces with underscores, remove special chars
        segment_code_base = re.sub(r'[^A-Z0-9_]', '', request.segment_name.upper().replace(' ', '_'))
        segment_code = f"{segment_code_base}_{consultation_type_code}"

        segment = create_segment_request(
            segment_code=segment_code,
            segment_name=request.segment_name,
            consultation_type_code=consultation_type_code,
            prompt_section_text=request.description,
            default_category=request.default_category,
            display_order=999,  # Auto-assign to end
            default_brevity_level=request.default_brevity,
            default_terminology_style=request.default_terminology,
            counsellor_id=counsellor_uuid,  # Changed from created_by_counsellor_id (migration 20251123000200)
            template_id=uuid.UUID(template_id)  # NEW: Link to template
        )

        return {
            "success": True,
            "message": "Segment request submitted for admin review",
            "segment": segment,
            "template_id": template_id
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create segment request")


@router.get("/{counsellor_id}/segment-requests")
async def get_counsellor_segment_requests(
    request: Request,
    counsellor_id: str,
    pending_only: bool = Query(True, description="Show only pending requests (not yet approved)"),
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Get segment requests submitted by a counsellor.

    **Path Parameters:**
    - `counsellor_id`: Counsellor UUID

    **Query Parameters:**
    - `pending_only`: Show only pending (unapproved) requests (default: true)

    **Returns:**
    - List of segment definitions created by the counsellor

    **Response Structure:**
    ```json
    {
        "success": true,
        "segments": [
            {
                "id": "segment-uuid",
                "segment_code": "CUSTOM_SEGMENT",
                "segment_name": "My Custom Segment",
                "description": "Segment description",
                "segment_type": "doctor",
                "counsellor_id": "counsellor-uuid",
                "is_active": false,
                "created_at": "2025-01-01T00:00:00Z"
            }
        ],
        "count": 1
    }
    ```

    **Notes:**
    - Pending requests have is_active=false and segment_type='doctor'
    - Once approved by admin, is_active is set to true
    """
    try:
        from services.supabase_service import supabase

        # Query segment_definitions for counsellor-created segments
        query = (
            supabase.table("segment_definitions")
            .select("*")
            .eq("segment_type", "doctor")
            .eq("counsellor_id", counsellor_id)
        )

        if pending_only:
            query = query.eq("is_active", False)

        response = query.order("created_at", desc=True).execute()

        return {
            "success": True,
            "segments": response.data,
            "count": len(response.data)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch segment requests")


# ============================================================================
# Counsellor Default Template Endpoints
# ============================================================================

@router.put("/{counsellor_id}/default-template")
async def set_counsellor_default_template(
    request: Request,
    counsellor_id: str,
    body: SetCounsellorDefaultTemplateRequest = None,
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Set or clear the default template for a counsellor.

    **Path Parameters:**
    - counsellor_id: Counsellor UUID

    **Request Body:**
    ```json
    {
        "template_id": "uuid-of-template"  // or null to clear
    }
    ```

    **Returns:**
    - success: True if updated
    - message: Success message
    - default_template_id: The set template ID (or null if cleared)

    **Notes:**
    - Counsellor default takes priority over school default
    - The template must be accessible to the counsellor (owned, shared, or common)
    """
    from services.supabase_service import supabase
    from services.counsellor_templates_service import get_counsellor_accessible_templates

    try:
        counsellor_uuid = uuid.UUID(counsellor_id)

        # Validate counsellor exists
        counsellor_result = (
            supabase.table("counsellors")
            .select("id, full_name, school_id")
            .eq("id", counsellor_id)
            .execute()
        )

        if not counsellor_result.data or len(counsellor_result.data) == 0:
            raise HTTPException(status_code=404, detail="Counsellor not found")

        counsellor = counsellor_result.data[0]
        template_id = body.template_id if body else None

        # If template_id provided, validate counsellor has access to it
        if template_id:
            # Get all accessible templates for this counsellor
            accessible = get_counsellor_accessible_templates(counsellor_uuid, include_common=True)
            accessible_ids = {t.get("id") for t in accessible}

            if template_id not in accessible_ids:
                raise HTTPException(
                    status_code=403,
                    detail="Counsellor does not have access to this template"
                )

            # Also verify template is active
            template_result = (
                supabase.table("templates")
                .select("id, template_code, is_active")
                .eq("id", template_id)
                .execute()
            )

            if not template_result.data or len(template_result.data) == 0:
                raise HTTPException(status_code=404, detail="Template not found")

            template = template_result.data[0]
            if not template.get("is_active"):
                raise HTTPException(status_code=400, detail="Cannot set inactive template as default")

        # Update counsellor's default_template_id
        update_result = (
            supabase.table("counsellors")
            .update({"default_template_id": template_id})
            .eq("id", counsellor_id)
            .execute()
        )

        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to update counsellor default template")

        if template_id:
            return {
                "success": True,
                "message": f"Default template set for counsellor '{counsellor['full_name']}'",
                "default_template_id": template_id
            }
        else:
            return {
                "success": True,
                "message": f"Default template cleared for counsellor '{counsellor['full_name']}'",
                "default_template_id": None
            }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to set counsellor default template")


# ============================================================================
# Counsellor EHR Assignment Endpoints
# ============================================================================

class CounsellorEhrTypeRequest(BaseModel):
    """Request model for setting counsellor's EHR type"""
    ehr_type_id: Optional[str] = Field(None, description="EHR type UUID to assign (null to clear)")


@router.put("/{counsellor_id}/ehr-type")
async def update_counsellor_ehr_type(
    request: Request,
    counsellor_id: str,
    body: CounsellorEhrTypeRequest = None,
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Assign or remove EHR type for a counsellor.

    **Path Parameters:**
    - counsellor_id: Counsellor UUID

    **Request Body:**
    ```json
    {
        "ehr_type_id": "uuid-of-ehr-type"  // or null to remove EHR sync
    }
    ```

    **Returns:**
    - success: True if updated
    - message: Success message
    - ehr_type_id: The assigned EHR type ID (or null if cleared)

    **Notes:**
    - Setting ehr_type_id to null disables EHR sync for this counsellor
    - The ehr_type must be configured for the counsellor's school
    """
    from services.supabase_service import supabase

    try:
        counsellor_uuid = uuid.UUID(counsellor_id)

        # Validate counsellor exists and get school_id
        counsellor_result = (
            supabase.table("counsellors")
            .select("id, full_name, school_id")
            .eq("id", counsellor_id)
            .execute()
        )

        if not counsellor_result.data or len(counsellor_result.data) == 0:
            raise HTTPException(status_code=404, detail="Counsellor not found")

        counsellor = counsellor_result.data[0]
        ehr_type_id = body.ehr_type_id if body else None

        # If ehr_type_id provided, validate it exists and is configured for this school
        if ehr_type_id:
            # Validate EHR type exists
            ehr_type_result = (
                supabase.table("ehr_types")
                .select("id, ehr_code, ehr_name")
                .eq("id", ehr_type_id)
                .eq("is_active", True)
                .execute()
            )

            if not ehr_type_result.data:
                raise HTTPException(status_code=404, detail="EHR type not found")

            ehr_type = ehr_type_result.data[0]

            # Validate school has this EHR type configured
            school_ehr_result = (
                supabase.table("school_ehr")
                .select("id")
                .eq("school_id", counsellor["school_id"])
                .eq("ehr_type_id", ehr_type_id)
                .eq("is_enabled", True)
                .execute()
            )

            if not school_ehr_result.data:
                raise HTTPException(
                    status_code=400,
                    detail="EHR type is not configured for this counsellor's school"
                )

        # Update counsellor's ehr_type_id
        update_result = (
            supabase.table("counsellors")
            .update({"ehr_type_id": ehr_type_id})
            .eq("id", counsellor_id)
            .execute()
        )

        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to update counsellor EHR type")

        if ehr_type_id:
            return {
                "success": True,
                "message": f"EHR type assigned to counsellor '{counsellor['full_name']}'",
                "ehr_type_id": ehr_type_id
            }
        else:
            return {
                "success": True,
                "message": f"EHR type removed for counsellor '{counsellor['full_name']}'",
                "ehr_type_id": None
            }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update counsellor EHR type")


@router.get("/{counsellor_id}/ehr-type")
async def get_counsellor_ehr_type(
    request: Request,
    counsellor_id: str,
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Get the current EHR type assignment for a counsellor.

    **Path Parameters:**
    - counsellor_id: Counsellor UUID

    **Returns:**
    - ehr_type: EHR type info (id, code, name) or null if not assigned
    """
    from services.supabase_service import supabase

    try:
        # Get counsellor with EHR type info
        result = (
            supabase.table("counsellors")
            .select("id, full_name, ehr_type_id, ehr_types(id, ehr_code, ehr_name)")
            .eq("id", counsellor_id)
            .execute()
        )

        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=404, detail="Counsellor not found")

        counsellor = result.data[0]
        ehr_type = counsellor.get("ehr_types")

        return {
            "success": True,
            "counsellor_id": counsellor_id,
            "counsellor_name": counsellor["full_name"],
            "ehr_type": ehr_type
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get counsellor EHR type")

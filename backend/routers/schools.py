"""
School Management Router

REST API endpoints for school CRUD operations.
"""

from fastapi import APIRouter, HTTPException, Depends, Path
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from uuid import UUID

from models.auth_models import ClientContext
from dependencies.auth import require_admin, get_current_client, require_any_scope
from services.supabase_service import supabase, get_school_settings_cached, invalidate_school_settings_cache

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/schools", tags=["School Management"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SchoolCreateRequest(BaseModel):
    """Request model for creating a school"""
    school_code: str = Field(..., min_length=1, max_length=50, description="Unique school code")
    school_name: str = Field(..., min_length=2, max_length=255, description="School name")


class SchoolUpdateRequest(BaseModel):
    """Request model for updating a school"""
    school_code: Optional[str] = Field(None, min_length=1, max_length=50, description="Unique school code")
    school_name: Optional[str] = Field(None, min_length=2, max_length=255, description="School name")
    op_registration_fee: Optional[float] = Field(None, ge=0, description="OP registration fee")
    ip_admission_fee: Optional[float] = Field(None, ge=0, description="IP admission fee")


class SchoolCreateResponse(BaseModel):
    """Response model for school creation"""
    success: bool
    message: str
    school_id: str


class FeatureFlagsUpdateRequest(BaseModel):
    """Request model for updating feature flags (partial merge)"""
    feature_flags: Dict[str, bool] = Field(..., description="Feature flags to merge (partial update)")


class SetDefaultTemplateRequest(BaseModel):
    """Request model for setting default template"""
    template_id: Optional[str] = Field(None, description="Template UUID to set as default (null to clear)")


class SchoolSettingsUpdateRequest(BaseModel):
    """Request model for updating school settings"""
    use_ffmpeg_stitching: Optional[bool] = Field(None, description="Enable FFmpeg for audio stitching")
    audio_quality_block_threshold: Optional[str] = Field(
        None,
        description="Block if audio quality is at/below this level: 'poor', 'fair', or 'none' (never block)"
    )
    min_transcript_length: Optional[int] = Field(
        None,
        ge=0,
        le=500,
        description="Minimum transcript length (chars) to proceed with extraction. Default: 20"
    )
    max_silence_ratio: Optional[float] = Field(
        None,
        ge=0.5,
        le=1.0,
        description="Block if silence ratio exceeds this threshold (0.5-1.0). Default: 0.90"
    )
    min_snr_db: Optional[float] = Field(
        None,
        ge=-10.0,
        le=60.0,
        description="Min SNR (dB). Block if below. Default: 10.0"
    )
    min_rms_db: Optional[float] = Field(
        None,
        ge=-60.0,
        le=0.0,
        description="Min RMS volume (dB). Block if below. Default: -57.0"
    )
    min_speech_ratio: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Min speech frame ratio (0-1). Block if below. Default: 0.10"
    )
    silence_thresh_dbfs: Optional[float] = Field(
        None,
        ge=-80.0,
        le=-20.0,
        description="Silence removal: volume threshold (dBFS) below which audio is silence. Default: -57"
    )
    min_silence_len_ms: Optional[int] = Field(
        None,
        ge=500,
        le=30000,
        description="Silence removal: minimum continuous silence (ms) to remove. Default: 5000"
    )
    silence_padding_ms: Optional[int] = Field(
        None,
        ge=0,
        le=2000,
        description="Silence removal: padding around speech segments (ms). Default: 200"
    )
    enable_realtime_subscription: Optional[bool] = Field(
        None,
        description="Enable Supabase Realtime subscription for extraction results"
    )
    enable_audio_validation: Optional[bool] = Field(
        None,
        description="Enable audio quality validation before extraction (default: true)"
    )
    enable_early_quality_abort: Optional[bool] = Field(
        None,
        description="Hard-stop recording early (~30s) if audio is clearly unusable (dead/silent/no speech). Default: false"
    )
    early_quality_check_seconds: Optional[int] = Field(
        None,
        ge=10,
        le=120,
        description="Seconds of audio after which the early quality check fires (10-120). Default: 30"
    )


# ============================================================================
# EHR Type Models
# ============================================================================

class EhrTypeCreateRequest(BaseModel):
    """Request model for creating an EHR type"""
    ehr_code: str = Field(..., min_length=1, max_length=50, description="Unique EHR code identifier")
    ehr_name: str = Field(..., min_length=1, max_length=255, description="Display name for the EHR type")
    default_api_url: Optional[str] = Field(None, description="Default API URL for this EHR type")
    description: Optional[str] = Field(None, description="Description of the EHR type")


class EhrTypeUpdateRequest(BaseModel):
    """Request model for updating an EHR type"""
    ehr_name: Optional[str] = Field(None, min_length=1, max_length=255, description="Display name")
    default_api_url: Optional[str] = Field(None, description="Default API URL (send empty string to clear)")
    description: Optional[str] = Field(None, description="Description (send empty string to clear)")
    is_active: Optional[bool] = Field(None, description="Whether EHR type is active")


# ============================================================================
# EHR Integration Models
# ============================================================================

class EhrIntegrationCreateRequest(BaseModel):
    """Request model for creating an EHR integration"""
    ehr_type_id: str = Field(..., description="EHR type UUID from ehr_types table")
    api_url: Optional[str] = Field(None, description="API endpoint URL (overrides ehr_types.default_api_url)")
    api_key: Optional[str] = Field(None, description="API key for authentication")
    is_enabled: bool = Field(True, description="Whether integration is enabled")
    is_default: bool = Field(False, description="Set as default EHR for new counsellors")


class EhrIntegrationUpdateRequest(BaseModel):
    """Request model for updating an EHR integration"""
    api_url: Optional[str] = Field(None, description="API endpoint URL (send empty string to clear)")
    api_key: Optional[str] = Field(None, description="API key for authentication (send empty string to clear)")
    is_enabled: Optional[bool] = Field(None, description="Whether integration is enabled")
    is_default: Optional[bool] = Field(None, description="Set as default EHR for new counsellors")


class EhrIntegrationResponse(BaseModel):
    """Response model for EHR integration"""
    id: str
    school_id: str
    ehr_type_id: str
    ehr_code: str
    ehr_name: str
    api_url: Optional[str]
    has_api_key: bool  # Don't expose the actual key
    is_enabled: bool
    is_default: bool
    created_at: str
    updated_at: str


# ============================================================================
# EHR Types Endpoints (Global - not school-specific)
# ============================================================================

@router.get("/ehr-types")
async def list_ehr_types(
    include_inactive: bool = False,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    List all available EHR types for dropdown selection.

    **Auth:** Any authenticated user

    **Query Parameters:**
    - include_inactive: If true, include inactive EHR types (admin UI)

    **Returns:**
    - ehr_types: List of EHR type records with id, code, name, and default URL
    """
    try:
        query = (
            supabase.table("ehr_types")
            .select("id, ehr_code, ehr_name, default_api_url, description, is_active, created_at")
        )

        if not include_inactive:
            query = query.eq("is_active", True)

        result = query.order("ehr_name").execute()

        return {
            "success": True,
            "ehr_types": result.data or [],
            "count": len(result.data or [])
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to list EHR types")


@router.post("/ehr-types")
async def create_ehr_type(
    request: EhrTypeCreateRequest,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Create a new EHR type.

    **Auth:** Admin only

    **Request Body:**
    ```json
    {
        "ehr_code": "my_ehr",
        "ehr_name": "My EHR System",
        "default_api_url": "https://api.example.com",
        "description": "Optional description"
    }
    ```
    """
    try:
        # Check uniqueness of ehr_code
        existing = (
            supabase.table("ehr_types")
            .select("id")
            .eq("ehr_code", request.ehr_code)
            .execute()
        )

        if existing.data and len(existing.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="EHR type with this code already exists"
            )

        insert_data = {
            "ehr_code": request.ehr_code,
            "ehr_name": request.ehr_name,
            "default_api_url": request.default_api_url,
            "description": request.description,
            "is_active": True,
        }

        result = supabase.table("ehr_types").insert(insert_data).execute()

        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to create EHR type")

        return {
            "success": True,
            "message": f"EHR type '{request.ehr_name}' created successfully",
            "ehr_type": result.data[0]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create EHR type")


@router.put("/ehr-types/{ehr_type_id}")
async def update_ehr_type(
    ehr_type_id: str = Path(..., description="EHR type UUID"),
    request: EhrTypeUpdateRequest = ...,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Update an EHR type. Cannot change ehr_code.

    **Auth:** Admin only
    """
    try:
        # Validate EHR type exists
        existing = (
            supabase.table("ehr_types")
            .select("id, ehr_code, ehr_name")
            .eq("id", ehr_type_id)
            .execute()
        )

        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="EHR type not found")

        # Build update payload
        update_data = {}
        if request.ehr_name is not None:
            update_data["ehr_name"] = request.ehr_name
        if request.default_api_url is not None:
            update_data["default_api_url"] = request.default_api_url if request.default_api_url else None
        if request.description is not None:
            update_data["description"] = request.description if request.description else None
        if request.is_active is not None:
            update_data["is_active"] = request.is_active

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields provided to update")

        result = (
            supabase.table("ehr_types")
            .update(update_data)
            .eq("id", ehr_type_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update EHR type")

        return {
            "success": True,
            "message": f"EHR type '{result.data[0].get('ehr_name', '')}' updated successfully",
            "ehr_type": result.data[0]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update EHR type")


@router.delete("/ehr-types/{ehr_type_id}")
async def deactivate_ehr_type(
    ehr_type_id: str = Path(..., description="EHR type UUID"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Soft-delete (deactivate) an EHR type. Checks for usage before deactivating.

    **Auth:** Admin only
    """
    try:
        # Validate EHR type exists
        existing = (
            supabase.table("ehr_types")
            .select("id, ehr_code, ehr_name, is_active")
            .eq("id", ehr_type_id)
            .execute()
        )

        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="EHR type not found")

        ehr_type = existing.data[0]

        if not ehr_type.get("is_active"):
            raise HTTPException(status_code=400, detail="EHR type is already inactive")

        # Check if in use by school_ehr
        school_usage = (
            supabase.table("school_ehr")
            .select("id")
            .eq("ehr_type_id", ehr_type_id)
            .eq("is_enabled", True)
            .execute()
        )

        if school_usage.data and len(school_usage.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot deactivate: EHR type is in use by school integrations"
            )

        # Check if in use by counsellors
        counsellor_usage = (
            supabase.table("counsellors")
            .select("id")
            .eq("ehr_type_id", ehr_type_id)
            .eq("is_active", True)
            .execute()
        )

        if counsellor_usage.data and len(counsellor_usage.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot deactivate: EHR type is assigned to active counsellors"
            )

        # Soft-delete: set is_active = false
        supabase.table("ehr_types").update({"is_active": False}).eq("id", ehr_type_id).execute()

        return {
            "success": True,
            "message": f"EHR type '{ehr_type['ehr_name']}' deactivated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to deactivate EHR type")


# ============================================================================
# School CRUD Endpoints
# ============================================================================

@router.post("", response_model=SchoolCreateResponse)
async def create_school(
    request: SchoolCreateRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Create a new school.

    **Auth:** Admin and Web only (EHR not allowed)

    **Request Body:**
    ```json
    {
        "school_code": "HOSP001",
        "school_name": "City General School"
    }
    ```

    **Returns:**
    - success: True if school created
    - message: Success message
    - school_id: UUID of created school

    **Notes:**
    - school_code must be unique
    - school_name must be unique
    """
    # EHR clients cannot create schools
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to create schools"
        )

    try:
        # Check if school_code already exists
        existing_code = (
            supabase.table("schools")
            .select("id")
            .eq("school_code", request.school_code)
            .execute()
        )

        if existing_code.data and len(existing_code.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="School with this code already exists"
            )

        # Check if school_name already exists
        existing_name = (
            supabase.table("schools")
            .select("id")
            .eq("school_name", request.school_name)
            .execute()
        )

        if existing_name.data and len(existing_name.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="School with this name already exists"
            )

        # Create school
        school_data = {
            "school_code": request.school_code,
            "school_name": request.school_name,
            "is_active": True
        }

        response = supabase.table("schools").insert(school_data).execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to create school")

        created_school = response.data[0]

        return {
            "success": True,
            "message": f"School '{request.school_name}' created successfully",
            "school_id": created_school["id"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create school")


@router.put("/{school_id}")
async def update_school(
    school_id: str = Path(..., description="School UUID"),
    request: SchoolUpdateRequest = ...,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Update school name and/or code.

    **Auth:** Admin and Web only (EHR not allowed)
    """
    # EHR clients cannot update schools
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to update schools"
        )

    try:
        # Validate school exists
        existing = (
            supabase.table("schools")
            .select("id, school_name, school_code")
            .eq("id", school_id)
            .execute()
        )

        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="School not found")

        school = existing.data[0]

        # Build update payload
        update_data = {}

        if request.school_code is not None and request.school_code != school["school_code"]:
            # Check uniqueness of new code
            code_check = (
                supabase.table("schools")
                .select("id")
                .eq("school_code", request.school_code)
                .neq("id", school_id)
                .execute()
            )
            if code_check.data and len(code_check.data) > 0:
                raise HTTPException(
                    status_code=409,
                    detail="School with this code already exists"
                )
            update_data["school_code"] = request.school_code

        if request.school_name is not None and request.school_name != school["school_name"]:
            # Check uniqueness of new name
            name_check = (
                supabase.table("schools")
                .select("id")
                .eq("school_name", request.school_name)
                .neq("id", school_id)
                .execute()
            )
            if name_check.data and len(name_check.data) > 0:
                raise HTTPException(
                    status_code=409,
                    detail="School with this name already exists"
                )
            update_data["school_name"] = request.school_name

        if request.op_registration_fee is not None:
            update_data["op_registration_fee"] = request.op_registration_fee
        if request.ip_admission_fee is not None:
            update_data["ip_admission_fee"] = request.ip_admission_fee

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields provided to update")

        result = (
            supabase.table("schools")
            .update(update_data)
            .eq("id", school_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update school")

        return {
            "success": True,
            "message": f"School updated successfully",
            "hospital": result.data[0]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update school")


@router.delete("/{school_id}/permanent")
async def hard_delete_school(
    school_id: str = Path(..., description="School UUID"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Permanently delete a school. This is irreversible.

    **Auth:** Admin only

    Blocks deletion if school has:
    - Active counsellors assigned
    - Recording sessions or extractions via counsellors
    - API clients configured

    Cascades deletion of:
    - school_ehr integrations
    - school_medicine_lists, school_investigation_lists
    - school_specialty_patterns, school_intervention_pricing
    - template_ehr mappings (via templates)
    - qa_engine_settings
    """
    try:
        # Validate school exists
        existing = (
            supabase.table("schools")
            .select("id, school_name")
            .eq("id", school_id)
            .execute()
        )

        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="School not found")

        school_name = existing.data[0]["school_name"]

        # Block if counsellors are assigned to this school
        counsellors_check = (
            supabase.table("counsellors")
            .select("id")
            .eq("school_id", school_id)
            .execute()
        )

        if counsellors_check.data and len(counsellors_check.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete: counsellors are assigned to this school. Remove or reassign them first."
            )

        # Block if API clients exist
        api_clients_check = (
            supabase.table("api_clients")
            .select("id")
            .eq("school_id", school_id)
            .execute()
        )

        if api_clients_check.data and len(api_clients_check.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete: API clients are configured for this school. Remove them first."
            )

        # Cascade delete config data (order matters for FK constraints)
        for table in [
            "school_ehr",
            "school_medicine_lists",
            "school_investigation_lists",
            "school_specialty_patterns",
            "school_intervention_pricing",
            "qa_engine_settings",
            "investigation_list_uploads",
        ]:
            try:
                supabase.table(table).delete().eq("school_id", school_id).execute()
            except Exception:
                pass  # Table may not have data, continue

        # Delete students (nullable school_id, but clean up)
        try:
            supabase.table("students").delete().eq("school_id", school_id).execute()
        except Exception:
            pass

        # Delete assistants
        try:
            supabase.table("assistants").delete().eq("school_id", school_id).execute()
        except Exception:
            pass

        # Finally delete the school
        supabase.table("schools").delete().eq("id", school_id).execute()

        return {
            "success": True,
            "message": f"School '{school_name}' permanently deleted"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete school")


@router.delete("/{school_id}")
async def deactivate_school(
    school_id: str = Path(..., description="School UUID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Soft-delete (deactivate) a school by setting is_active=false.

    **Auth:** Admin and Web only (EHR not allowed)
    """
    # EHR clients cannot deactivate schools
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to deactivate schools"
        )

    try:
        # Validate school exists
        existing = (
            supabase.table("schools")
            .select("id, school_name, is_active")
            .eq("id", school_id)
            .execute()
        )

        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="School not found")

        school = existing.data[0]

        if not school.get("is_active"):
            raise HTTPException(status_code=400, detail="School is already inactive")

        # Soft-delete
        supabase.table("schools").update({"is_active": False}).eq("id", school_id).execute()

        return {
            "success": True,
            "message": f"School '{school['school_name']}' deactivated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to deactivate school")


# ============================================================================
# School Default Template Endpoints
# ============================================================================

@router.put("/{school_id}/default-template")
async def set_school_default_template(
    school_id: str = Path(..., description="School UUID"),
    request: SetDefaultTemplateRequest = None,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Set or clear the default template for a school.

    **Auth:** Admin, Web, and EHR (EHR restricted to own school)

    **Path Parameters:**
    - school_id: School UUID

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
    """
    try:
        # EHR clients can only modify their own school
        if client.client_type == "ehr":
            if client.school_id is None or str(client.school_id) != school_id:
                raise HTTPException(
                    status_code=403,
                    detail="EHR clients can only modify their own school's default template"
                )

        # Validate school exists
        school_result = (
            supabase.table("schools")
            .select("id, school_name")
            .eq("id", school_id)
            .execute()
        )

        if not school_result.data or len(school_result.data) == 0:
            raise HTTPException(status_code=404, detail="School not found")

        school = school_result.data[0]
        template_id = request.template_id if request else None

        # If template_id provided, validate it exists and is active
        if template_id:
            template_result = (
                supabase.table("templates")
                .select("id, template_code, template_name, is_active")
                .eq("id", template_id)
                .execute()
            )

            if not template_result.data or len(template_result.data) == 0:
                raise HTTPException(status_code=404, detail="Template not found")

            template = template_result.data[0]
            if not template.get("is_active"):
                raise HTTPException(status_code=400, detail="Cannot set inactive template as default")

        # Update school's default_template_id
        update_result = (
            supabase.table("schools")
            .update({"default_template_id": template_id})
            .eq("id", school_id)
            .execute()
        )

        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to update school default template")

        # Auto-share template with all counsellors in this school (optimized batch operation)
        counsellors_shared = 0
        if template_id:
            # Query 1: Get all active counsellor IDs in this school
            counsellors_result = (
                supabase.table("counsellors")
                .select("id")
                .eq("school_id", school_id)
                .eq("is_active", True)
                .execute()
            )

            if counsellors_result.data:
                counsellor_ids = {d["id"] for d in counsellors_result.data}

                # Query 2: Get counsellor IDs that already have access to this template
                existing_result = (
                    supabase.table("counsellor_templates")
                    .select("counsellor_id")
                    .eq("template_id", template_id)
                    .in_("counsellor_id", list(counsellor_ids))
                    .execute()
                )

                existing_counsellor_ids = {e["counsellor_id"] for e in (existing_result.data or [])}

                # Calculate counsellors needing new access
                counsellors_to_share = counsellor_ids - existing_counsellor_ids

                # Query 3: Batch insert all new counsellor_templates entries
                if counsellors_to_share:
                    insert_data = [
                        {
                            "counsellor_id": counsellor_id,
                            "template_id": template_id,
                            "access_level": "use",
                            "is_active": True,
                        }
                        for counsellor_id in counsellors_to_share
                    ]
                    supabase.table("counsellor_templates").insert(insert_data).execute()
                    counsellors_shared = len(counsellors_to_share)

        if template_id:
            return {
                "success": True,
                "message": f"Default template set for school '{school['school_name']}'. Auto-shared with {counsellors_shared} counsellor(s).",
                "default_template_id": template_id,
                "doctors_shared": counsellors_shared
            }
        else:
            return {
                "success": True,
                "message": f"Default template cleared for school '{school['school_name']}'",
                "default_template_id": None
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to set school default template")


# ============================================================================
# School Settings Endpoints
# ============================================================================

@router.put("/{school_id}/settings")
async def update_school_settings(
    school_id: str = Path(..., description="School UUID"),
    request: SchoolSettingsUpdateRequest = None,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Update school settings (e.g., FFmpeg stitching).

    **Auth:** Admin and Web only (EHR not allowed)

    **Path Parameters:**
    - school_id: School UUID

    **Request Body:**
    ```json
    {
        "use_ffmpeg_stitching": true
    }
    ```

    **Returns:**
    - success: True if updated
    - message: Success message
    - settings: Updated settings object
    """
    # EHR clients cannot modify school settings
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to modify school settings"
        )

    try:
        # Validate school exists
        school_result = (
            supabase.table("schools")
            .select("id, school_name")
            .eq("id", school_id)
            .execute()
        )

        if not school_result.data or len(school_result.data) == 0:
            raise HTTPException(status_code=404, detail="School not found")

        school = school_result.data[0]

        # Build update payload with only provided fields
        update_data = {}
        if request:
            if request.use_ffmpeg_stitching is not None:
                update_data["use_ffmpeg_stitching"] = request.use_ffmpeg_stitching
            if request.audio_quality_block_threshold is not None:
                # Validate threshold value
                valid_thresholds = ["poor", "fair", "none"]
                if request.audio_quality_block_threshold not in valid_thresholds:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid audio_quality_block_threshold. Must be one of: poor, fair, none"
                    )
                update_data["audio_quality_block_threshold"] = request.audio_quality_block_threshold
            if request.min_transcript_length is not None:
                update_data["min_transcript_length"] = request.min_transcript_length
            if request.max_silence_ratio is not None:
                update_data["max_silence_ratio"] = request.max_silence_ratio
            if request.min_snr_db is not None:
                update_data["min_snr_db"] = request.min_snr_db
            if request.min_rms_db is not None:
                update_data["min_rms_db"] = request.min_rms_db
            if request.min_speech_ratio is not None:
                update_data["min_speech_ratio"] = request.min_speech_ratio
            if request.silence_thresh_dbfs is not None:
                update_data["silence_thresh_dbfs"] = request.silence_thresh_dbfs
            if request.min_silence_len_ms is not None:
                update_data["min_silence_len_ms"] = request.min_silence_len_ms
            if request.silence_padding_ms is not None:
                update_data["silence_padding_ms"] = request.silence_padding_ms
            if request.enable_realtime_subscription is not None:
                update_data["enable_realtime_subscription"] = request.enable_realtime_subscription
            if request.enable_audio_validation is not None:
                update_data["enable_audio_validation"] = request.enable_audio_validation
            if request.enable_early_quality_abort is not None:
                update_data["enable_early_quality_abort"] = request.enable_early_quality_abort
            if request.early_quality_check_seconds is not None:
                update_data["early_quality_check_seconds"] = request.early_quality_check_seconds

        if not update_data:
            raise HTTPException(status_code=400, detail="No settings provided to update")

        # Update school settings
        update_result = (
            supabase.table("schools")
            .update(update_data)
            .eq("id", school_id)
            .execute()
        )

        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to update school settings")

        # Invalidate school settings cache (infinite TTL cache needs explicit invalidation)
        from services.supabase_service import invalidate_school_settings_cache
        invalidate_school_settings_cache(school_id)

        # Invalidate realtime subscription cache if that setting was updated
        if "enable_realtime_subscription" in update_data:
            from services.realtime_publisher_service import invalidate_school_realtime_cache
            invalidate_school_realtime_cache(school_id)

        return {
            "success": True,
            "message": f"Settings updated for school '{school['school_name']}'",
            "settings": update_data
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update school settings")


# ============================================================================
# School EHR Integration Endpoints
# ============================================================================

@router.get("/{school_id}/ehr-integrations")
async def list_school_ehr_integrations(
    school_id: str = Path(..., description="School UUID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    List all EHR integrations for a school.

    **Auth:** Admin, Web, and EHR (EHR restricted to own school)

    **Returns:**
    - integrations: List of EHR integration configs (api_key masked)
    """
    try:
        # EHR clients can only view their own school's integrations
        if client.client_type == "ehr":
            if client.school_id is None or str(client.school_id) != school_id:
                raise HTTPException(
                    status_code=403,
                    detail="EHR clients can only view their own school's integrations"
                )

        # Validate school exists
        school_result = (
            supabase.table("schools")
            .select("id")
            .eq("id", school_id)
            .execute()
        )

        if not school_result.data:
            raise HTTPException(status_code=404, detail="School not found")

        # Get all integrations for this school with ehr_types join
        result = (
            supabase.table("school_ehr")
            .select("""
                id, school_id, ehr_type_id, ehr_integration_type, api_url, api_key,
                is_enabled, is_default, created_at, updated_at,
                ehr_types(ehr_code, ehr_name)
            """)
            .eq("school_id", school_id)
            .order("created_at", desc=True)
            .execute()
        )

        # Mask api_key in response and flatten ehr_types
        integrations = []
        for row in (result.data or []):
            ehr_type = row.get("ehr_types") or {}
            integrations.append({
                "id": row["id"],
                "school_id": row["school_id"],
                "ehr_type_id": row.get("ehr_type_id"),
                "ehr_code": ehr_type.get("ehr_code") or row.get("ehr_integration_type"),
                "ehr_name": ehr_type.get("ehr_name") or row.get("ehr_integration_type", "").title(),
                "api_url": row["api_url"],
                "has_api_key": bool(row.get("api_key")),
                "is_enabled": row["is_enabled"],
                "is_default": row.get("is_default", False),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            })

        return {
            "success": True,
            "integrations": integrations
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to list EHR integrations")


@router.post("/{school_id}/ehr-integrations")
async def create_school_ehr_integration(
    school_id: str = Path(..., description="School UUID"),
    request: EhrIntegrationCreateRequest = ...,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Create a new EHR integration for a school.

    **Auth:** Admin and Web only (EHR not allowed)

    **Request Body:**
    ```json
    {
        "ehr_type_id": "uuid-of-ehr-type",
        "api_url": "https://api.example.com/v1/save",
        "api_key": "optional-api-key",
        "is_enabled": true,
        "is_default": false
    }
    ```

    **Notes:**
    - If is_default is true, any existing default for this school will be unset
    - New counsellors created in this school will be auto-assigned the default EHR type
    """
    # EHR clients cannot create integrations
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to create integrations"
        )

    try:
        # Validate school exists
        school_result = (
            supabase.table("schools")
            .select("id, school_name")
            .eq("id", school_id)
            .execute()
        )

        if not school_result.data:
            raise HTTPException(status_code=404, detail="School not found")

        school = school_result.data[0]

        # Validate ehr_type_id exists
        ehr_type_result = (
            supabase.table("ehr_types")
            .select("id, ehr_code, ehr_name")
            .eq("id", request.ehr_type_id)
            .eq("is_active", True)
            .execute()
        )

        if not ehr_type_result.data:
            raise HTTPException(status_code=404, detail="EHR type not found")

        ehr_type = ehr_type_result.data[0]

        # Check if this ehr_type already exists for this school
        existing = (
            supabase.table("school_ehr")
            .select("id")
            .eq("school_id", school_id)
            .eq("ehr_type_id", request.ehr_type_id)
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=409,
                detail="This EHR type is already configured for this school"
            )

        # If setting as default, unset any existing default
        if request.is_default:
            supabase.table("school_ehr").update({"is_default": False}).eq("school_id", school_id).execute()

        # Create the integration
        insert_data = {
            "school_id": school_id,
            "ehr_type_id": request.ehr_type_id,
            "ehr_integration_type": ehr_type["ehr_code"],  # For backward compatibility
            "api_url": request.api_url,
            "api_key": request.api_key,
            "is_enabled": request.is_enabled,
            "is_default": request.is_default
        }

        result = supabase.table("school_ehr").insert(insert_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create EHR integration")

        created = result.data[0]

        return {
            "success": True,
            "message": f"EHR integration '{ehr_type['ehr_name']}' created for school '{school['school_name']}'",
            "integration": {
                "id": created["id"],
                "school_id": created["school_id"],
                "ehr_type_id": created["ehr_type_id"],
                "ehr_code": ehr_type["ehr_code"],
                "ehr_name": ehr_type["ehr_name"],
                "api_url": created["api_url"],
                "has_api_key": bool(created.get("api_key")),
                "is_enabled": created["is_enabled"],
                "is_default": created.get("is_default", False),
                "created_at": created["created_at"],
                "updated_at": created["updated_at"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create EHR integration")


@router.put("/{school_id}/ehr-integrations/{integration_id}")
async def update_school_ehr_integration(
    school_id: str = Path(..., description="School UUID"),
    integration_id: str = Path(..., description="Integration UUID"),
    request: EhrIntegrationUpdateRequest = ...,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Update an EHR integration.

    **Auth:** Admin and Web only (EHR not allowed)

    **Request Body:**
    ```json
    {
        "api_url": "https://new-api.example.com/v1/save",
        "api_key": "new-api-key",
        "is_enabled": false,
        "is_default": true
    }
    ```

    **Notes:**
    - Send empty string for api_url or api_key to clear it
    - If is_default is true, any existing default for this school will be unset
    """
    # EHR clients cannot update integrations
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to update integrations"
        )

    try:
        # Validate integration exists and belongs to school (include ehr_types join)
        existing = (
            supabase.table("school_ehr")
            .select("id, school_id, ehr_type_id, ehr_integration_type, ehr_types(ehr_code, ehr_name)")
            .eq("id", integration_id)
            .eq("school_id", school_id)
            .execute()
        )

        if not existing.data:
            raise HTTPException(
                status_code=404,
                detail="Integration not found"
            )

        integration = existing.data[0]
        ehr_type = integration.get("ehr_types") or {}

        # If setting as default, unset any existing default first
        if request.is_default is True:
            supabase.table("school_ehr").update({"is_default": False}).eq("school_id", school_id).execute()

        # Build update payload
        update_data = {}
        if request.api_url is not None:
            update_data["api_url"] = request.api_url if request.api_url else None
        if request.api_key is not None:
            # Empty string clears the key, non-empty sets it
            update_data["api_key"] = request.api_key if request.api_key else None
        if request.is_enabled is not None:
            update_data["is_enabled"] = request.is_enabled
        if request.is_default is not None:
            update_data["is_default"] = request.is_default

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields provided to update")

        # Perform update
        result = (
            supabase.table("school_ehr")
            .update(update_data)
            .eq("id", integration_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update EHR integration")

        updated = result.data[0]

        return {
            "success": True,
            "message": f"EHR integration '{ehr_type.get('ehr_name') or integration['ehr_integration_type']}' updated",
            "integration": {
                "id": updated["id"],
                "school_id": updated["school_id"],
                "ehr_type_id": updated.get("ehr_type_id"),
                "ehr_code": ehr_type.get("ehr_code") or updated.get("ehr_integration_type"),
                "ehr_name": ehr_type.get("ehr_name") or updated.get("ehr_integration_type", "").title(),
                "api_url": updated["api_url"],
                "has_api_key": bool(updated.get("api_key")),
                "is_enabled": updated["is_enabled"],
                "is_default": updated.get("is_default", False),
                "created_at": updated["created_at"],
                "updated_at": updated["updated_at"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update EHR integration")


@router.delete("/{school_id}/ehr-integrations/{integration_id}")
async def delete_school_ehr_integration(
    school_id: str = Path(..., description="School UUID"),
    integration_id: str = Path(..., description="Integration UUID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Delete an EHR integration.

    **Auth:** Admin and Web only (EHR not allowed)
    """
    # EHR clients cannot delete integrations
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to delete integrations"
        )

    try:
        # Validate integration exists and belongs to school
        existing = (
            supabase.table("school_ehr")
            .select("id, school_id, ehr_integration_type")
            .eq("id", integration_id)
            .eq("school_id", school_id)
            .execute()
        )

        if not existing.data:
            raise HTTPException(
                status_code=404,
                detail="Integration not found"
            )

        integration = existing.data[0]

        # Delete the integration
        supabase.table("school_ehr").delete().eq("id", integration_id).execute()

        return {
            "success": True,
            "message": f"EHR integration '{integration['ehr_integration_type']}' deleted"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete EHR integration")


# ============================================================================
# Template EHR URL Suffix Endpoints
# ============================================================================

class TemplateEhrCreateRequest(BaseModel):
    """Request model for creating a template EHR suffix mapping"""
    template_id: str = Field(..., description="Template UUID")
    ehr_type_id: str = Field(..., description="EHR type UUID")
    url_suffix: Optional[str] = Field(None, description="URL suffix to append (e.g., '/store-daycare-transcribed-data')")


class TemplateEhrUpdateRequest(BaseModel):
    """Request model for updating a template EHR suffix mapping"""
    url_suffix: Optional[str] = Field(None, description="URL suffix to append (empty string or null to clear)")


@router.get("/template-ehr")
async def list_template_ehr_mappings(
    template_id: Optional[str] = None,
    ehr_type_id: Optional[str] = None,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    List template-EHR URL suffix mappings.

    **Auth:** Admin and Web only

    **Query Parameters:**
    - template_id: Filter by template UUID (optional)
    - ehr_type_id: Filter by EHR type UUID (optional)

    **Returns:**
    - mappings: List of template_ehr records with template and EHR details
    """
    # EHR clients cannot view template EHR mappings
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to view template EHR mappings"
        )

    try:
        # Build query with joins
        query = (
            supabase.table("template_ehr")
            .select("""
                id, template_id, ehr_type_id, url_suffix, created_at,
                templates(template_code, template_name),
                ehr_types(ehr_code, ehr_name)
            """)
        )

        # Apply filters
        if template_id:
            query = query.eq("template_id", template_id)
        if ehr_type_id:
            query = query.eq("ehr_type_id", ehr_type_id)

        result = query.order("created_at", desc=True).execute()

        # Flatten the response
        mappings = []
        for row in (result.data or []):
            template = row.get("templates") or {}
            ehr_type = row.get("ehr_types") or {}
            mappings.append({
                "id": row["id"],
                "template_id": row["template_id"],
                "template_code": template.get("template_code"),
                "template_name": template.get("template_name"),
                "ehr_type_id": row["ehr_type_id"],
                "ehr_code": ehr_type.get("ehr_code"),
                "ehr_name": ehr_type.get("ehr_name"),
                "url_suffix": row["url_suffix"],
                "created_at": row["created_at"]
            })

        return {
            "success": True,
            "mappings": mappings,
            "count": len(mappings)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to list template EHR mappings")


@router.post("/template-ehr")
async def create_template_ehr_mapping(
    request: TemplateEhrCreateRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Create a template-EHR URL suffix mapping.

    **Auth:** Admin and Web only

    **Request Body:**
    ```json
    {
        "template_id": "uuid-of-template",
        "ehr_type_id": "uuid-of-ehr-type",
        "url_suffix": "/store-daycare-transcribed-data"
    }
    ```

    **Notes:**
    - Each template-EHR combination can only have one suffix mapping
    - Used primarily for Neopead which has different endpoints per template
    """
    # EHR clients cannot create template EHR mappings
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to create template EHR mappings"
        )

    try:
        # Validate template exists
        template_result = (
            supabase.table("templates")
            .select("id, template_code, template_name")
            .eq("id", request.template_id)
            .execute()
        )

        if not template_result.data:
            raise HTTPException(status_code=404, detail="Template not found")

        template = template_result.data[0]

        # Validate EHR type exists
        ehr_type_result = (
            supabase.table("ehr_types")
            .select("id, ehr_code, ehr_name")
            .eq("id", request.ehr_type_id)
            .eq("is_active", True)
            .execute()
        )

        if not ehr_type_result.data:
            raise HTTPException(status_code=404, detail="EHR type not found")

        ehr_type = ehr_type_result.data[0]

        # Check if mapping already exists
        existing = (
            supabase.table("template_ehr")
            .select("id")
            .eq("template_id", request.template_id)
            .eq("ehr_type_id", request.ehr_type_id)
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=409,
                detail="Mapping already exists for this template and EHR type combination"
            )

        # Create the mapping
        insert_data = {
            "template_id": request.template_id,
            "ehr_type_id": request.ehr_type_id,
            "url_suffix": request.url_suffix
        }

        result = supabase.table("template_ehr").insert(insert_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create template EHR mapping")

        created = result.data[0]

        return {
            "success": True,
            "message": f"Template EHR mapping created for '{template['template_code']}' -> '{ehr_type['ehr_code']}'",
            "mapping": {
                "id": created["id"],
                "template_id": created["template_id"],
                "template_code": template["template_code"],
                "template_name": template["template_name"],
                "ehr_type_id": created["ehr_type_id"],
                "ehr_code": ehr_type["ehr_code"],
                "ehr_name": ehr_type["ehr_name"],
                "url_suffix": created["url_suffix"],
                "created_at": created["created_at"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create template EHR mapping")


@router.put("/template-ehr/{mapping_id}")
async def update_template_ehr_mapping(
    mapping_id: str = Path(..., description="Template EHR mapping UUID"),
    request: TemplateEhrUpdateRequest = ...,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Update a template-EHR URL suffix mapping.

    **Auth:** Admin and Web only

    **Request Body:**
    ```json
    {
        "url_suffix": "/new-endpoint-suffix"
    }
    ```

    **Notes:**
    - Send empty string or null to clear the suffix
    """
    # EHR clients cannot update template EHR mappings
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to update template EHR mappings"
        )

    try:
        # Validate mapping exists and get details
        existing = (
            supabase.table("template_ehr")
            .select("""
                id, template_id, ehr_type_id,
                templates(template_code, template_name),
                ehr_types(ehr_code, ehr_name)
            """)
            .eq("id", mapping_id)
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Template EHR mapping not found")

        mapping = existing.data[0]
        template = mapping.get("templates") or {}
        ehr_type = mapping.get("ehr_types") or {}

        # Build update payload
        update_data = {}
        if request.url_suffix is not None:
            update_data["url_suffix"] = request.url_suffix if request.url_suffix else None

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields provided to update")

        # Perform update
        result = (
            supabase.table("template_ehr")
            .update(update_data)
            .eq("id", mapping_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update template EHR mapping")

        updated = result.data[0]

        return {
            "success": True,
            "message": f"Template EHR mapping updated for '{template.get('template_code')}' -> '{ehr_type.get('ehr_code')}'",
            "mapping": {
                "id": updated["id"],
                "template_id": updated["template_id"],
                "template_code": template.get("template_code"),
                "template_name": template.get("template_name"),
                "ehr_type_id": updated["ehr_type_id"],
                "ehr_code": ehr_type.get("ehr_code"),
                "ehr_name": ehr_type.get("ehr_name"),
                "url_suffix": updated["url_suffix"],
                "created_at": updated["created_at"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update template EHR mapping")


@router.delete("/template-ehr/{mapping_id}")
async def delete_template_ehr_mapping(
    mapping_id: str = Path(..., description="Template EHR mapping UUID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Delete a template-EHR URL suffix mapping.

    **Auth:** Admin and Web only
    """
    # EHR clients cannot delete template EHR mappings
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to delete template EHR mappings"
        )

    try:
        # Validate mapping exists
        existing = (
            supabase.table("template_ehr")
            .select("""
                id, template_id, ehr_type_id,
                templates(template_code),
                ehr_types(ehr_code)
            """)
            .eq("id", mapping_id)
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Template EHR mapping not found")

        mapping = existing.data[0]
        template = mapping.get("templates") or {}
        ehr_type = mapping.get("ehr_types") or {}

        # Delete the mapping
        supabase.table("template_ehr").delete().eq("id", mapping_id).execute()

        return {
            "success": True,
            "message": f"Template EHR mapping deleted for '{template.get('template_code')}' -> '{ehr_type.get('ehr_code')}'"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete template EHR mapping")


# ============================================================================
# Room Rate Master Endpoints
# ============================================================================

class RoomRateCreateRequest(BaseModel):
    """Request model for creating a room rate"""
    room_category: str = Field(..., min_length=1, max_length=100, description="Room category (e.g., General Ward, Private, ICU)")
    room_sub_category: Optional[str] = Field(None, max_length=100, description="Room sub-category (e.g., Deluxe Private, HDU)")
    rate_per_day: float = Field(..., gt=0, description="Rate per day")


class RoomRateUpdateRequest(BaseModel):
    """Request model for updating a room rate"""
    room_category: Optional[str] = Field(None, min_length=1, max_length=100)
    room_sub_category: Optional[str] = Field(None, max_length=100)
    rate_per_day: Optional[float] = Field(None, gt=0)
    is_active: Optional[bool] = Field(None)


@router.get("/{school_id}/room-rates")
async def list_room_rates(
    school_id: str = Path(..., description="School UUID"),
    include_inactive: bool = False,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    List room rates for a school.

    **Auth:** Admin + Web + EHR
    """
    try:
        query = (
            supabase.table("room_rate_master")
            .select("*")
            .eq("school_id", school_id)
            .order("room_category")
        )

        if not include_inactive:
            query = query.eq("is_active", True)

        result = query.execute()

        return {
            "success": True,
            "room_rates": result.data or [],
            "count": len(result.data or []),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to list room rates")


@router.post("/{school_id}/room-rates")
async def create_room_rate(
    school_id: str = Path(..., description="School UUID"),
    request: RoomRateCreateRequest = ...,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Create a room rate entry.

    **Auth:** Admin + Web + EHR
    """
    try:
        insert_data = {
            "school_id": school_id,
            "room_category": request.room_category,
            "room_sub_category": request.room_sub_category,
            "rate_per_day": request.rate_per_day,
            "is_active": True,
        }

        result = supabase.table("room_rate_master").insert(insert_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create room rate")

        return {
            "success": True,
            "message": f"Room rate for '{request.room_category}' created",
            "room_rate": result.data[0],
        }

    except HTTPException:
        raise
    except Exception as e:
        if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail=f"Room rate for '{request.room_category}' already exists for this school"
            )
        raise HTTPException(status_code=500, detail="Failed to create room rate")


@router.put("/{school_id}/room-rates/{rate_id}")
async def update_room_rate(
    school_id: str = Path(..., description="School UUID"),
    rate_id: str = Path(..., description="Room rate UUID"),
    request: RoomRateUpdateRequest = ...,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Update a room rate entry.

    **Auth:** Admin + Web + EHR
    """
    try:
        existing = (
            supabase.table("room_rate_master")
            .select("id")
            .eq("id", rate_id)
            .eq("school_id", school_id)
            .limit(1)
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Room rate not found")

        from datetime import datetime
        update_data = {"updated_at": datetime.utcnow().isoformat()}

        if request.room_category is not None:
            update_data["room_category"] = request.room_category
        if request.room_sub_category is not None:
            update_data["room_sub_category"] = request.room_sub_category or None
        if request.rate_per_day is not None:
            update_data["rate_per_day"] = request.rate_per_day
        if request.is_active is not None:
            update_data["is_active"] = request.is_active

        result = (
            supabase.table("room_rate_master")
            .update(update_data)
            .eq("id", rate_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update room rate")

        return {
            "success": True,
            "message": "Room rate updated",
            "room_rate": result.data[0],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update room rate")


@router.delete("/{school_id}/room-rates/{rate_id}")
async def delete_room_rate(
    school_id: str = Path(..., description="School UUID"),
    rate_id: str = Path(..., description="Room rate UUID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Soft-delete a room rate (set is_active=false).

    **Auth:** Admin + Web + EHR
    """
    try:
        existing = (
            supabase.table("room_rate_master")
            .select("id, room_category, is_active")
            .eq("id", rate_id)
            .eq("school_id", school_id)
            .limit(1)
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Room rate not found")

        if not existing.data[0].get("is_active"):
            raise HTTPException(status_code=400, detail="Room rate is already inactive")

        from datetime import datetime
        supabase.table("room_rate_master").update({
            "is_active": False,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", rate_id).execute()

        return {
            "success": True,
            "message": f"Room rate '{existing.data[0]['room_category']}' deactivated",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete room rate")


# ============================================================================
# School Feature Flags Endpoints
# ============================================================================

@router.get("/{school_id}/features")
async def get_school_features(
    school_id: str = Path(..., description="School UUID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Get feature flags for a school.

    **Auth:** Admin + Web only (EHR/mobile not allowed)

    Uses cached school settings — zero DB hit on hot path.

    **Returns:**
    - feature_flags: Dict of feature key → enabled boolean
    """
    if client.client_type not in ("admin", "web_app", "ehr"):
        raise HTTPException(status_code=403, detail="Only admin, web, and EHR clients can access feature flags")

    try:
        settings = get_school_settings_cached(school_id)
        return {
            "success": True,
            "school_id": school_id,
            "feature_flags": settings.get("feature_flags", {}),
        }
    except Exception as e:
        logger.error(f"[FEATURES] Failed to get features for {school_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get feature flags")


@router.put("/{school_id}/features")
async def update_school_features(
    request: FeatureFlagsUpdateRequest,
    school_id: str = Path(..., description="School UUID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Update feature flags for a school (partial merge).

    **Auth:** Super admin only

    Merges provided flags with existing flags. Keys not in the request are left unchanged.
    New keys can be added — the system is extensible.

    **Request Body:**
    ```json
    {
        "feature_flags": {
            "ocr": true,
            "billing": true,
            "my_new_feature": true
        }
    }
    ```
    """
    # Super admin only
    if client.user_role != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admins can update feature flags")

    try:
        # Validate school exists
        existing = (
            supabase.table("schools")
            .select("id, school_name, feature_flags")
            .eq("id", school_id)
            .execute()
        )

        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="School not found")

        school = existing.data[0]
        current_flags = school.get("feature_flags") or {}

        # Merge: existing flags + new flags (new wins)
        merged_flags = {**current_flags, **request.feature_flags}

        # Update in DB
        update_result = (
            supabase.table("schools")
            .update({"feature_flags": merged_flags})
            .eq("id", school_id)
            .execute()
        )

        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to update feature flags")

        # Invalidate cache
        invalidate_school_settings_cache(school_id)

        logger.info(f"[FEATURES] Updated feature flags for school {school_id}: {list(request.feature_flags.keys())}")

        return {
            "success": True,
            "school_id": school_id,
            "feature_flags": merged_flags,
            "message": f"Feature flags updated for '{school['school_name']}'",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FEATURES] Failed to update features for {school_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update feature flags")

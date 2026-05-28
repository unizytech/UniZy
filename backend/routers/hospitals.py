"""
Hospital Management Router

REST API endpoints for hospital CRUD operations.
"""

from fastapi import APIRouter, HTTPException, Depends, Path
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from uuid import UUID

from models.auth_models import ClientContext
from dependencies.auth import require_admin, get_current_client, require_any_scope
from services.supabase_service import supabase, get_hospital_settings_cached, invalidate_hospital_settings_cache

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/hospitals", tags=["Hospital Management"])


# ============================================================================
# Request/Response Models
# ============================================================================

class HospitalCreateRequest(BaseModel):
    """Request model for creating a hospital"""
    hospital_code: str = Field(..., min_length=1, max_length=50, description="Unique hospital code")
    hospital_name: str = Field(..., min_length=2, max_length=255, description="Hospital name")


class HospitalUpdateRequest(BaseModel):
    """Request model for updating a hospital"""
    hospital_code: Optional[str] = Field(None, min_length=1, max_length=50, description="Unique hospital code")
    hospital_name: Optional[str] = Field(None, min_length=2, max_length=255, description="Hospital name")
    op_registration_fee: Optional[float] = Field(None, ge=0, description="OP registration fee")
    ip_admission_fee: Optional[float] = Field(None, ge=0, description="IP admission fee")


class HospitalCreateResponse(BaseModel):
    """Response model for hospital creation"""
    success: bool
    message: str
    hospital_id: str


class FeatureFlagsUpdateRequest(BaseModel):
    """Request model for updating feature flags (partial merge)"""
    feature_flags: Dict[str, bool] = Field(..., description="Feature flags to merge (partial update)")


class SetDefaultTemplateRequest(BaseModel):
    """Request model for setting default template"""
    template_id: Optional[str] = Field(None, description="Template UUID to set as default (null to clear)")


class HospitalSettingsUpdateRequest(BaseModel):
    """Request model for updating hospital settings"""
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
    is_default: bool = Field(False, description="Set as default EHR for new doctors")


class EhrIntegrationUpdateRequest(BaseModel):
    """Request model for updating an EHR integration"""
    api_url: Optional[str] = Field(None, description="API endpoint URL (send empty string to clear)")
    api_key: Optional[str] = Field(None, description="API key for authentication (send empty string to clear)")
    is_enabled: Optional[bool] = Field(None, description="Whether integration is enabled")
    is_default: Optional[bool] = Field(None, description="Set as default EHR for new doctors")


class EhrIntegrationResponse(BaseModel):
    """Response model for EHR integration"""
    id: str
    hospital_id: str
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
# EHR Types Endpoints (Global - not hospital-specific)
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

        # Check if in use by hospital_ehr
        hospital_usage = (
            supabase.table("hospital_ehr")
            .select("id")
            .eq("ehr_type_id", ehr_type_id)
            .eq("is_enabled", True)
            .execute()
        )

        if hospital_usage.data and len(hospital_usage.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot deactivate: EHR type is in use by hospital integrations"
            )

        # Check if in use by doctors
        doctor_usage = (
            supabase.table("doctors")
            .select("id")
            .eq("ehr_type_id", ehr_type_id)
            .eq("is_active", True)
            .execute()
        )

        if doctor_usage.data and len(doctor_usage.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot deactivate: EHR type is assigned to active doctors"
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
# Hospital CRUD Endpoints
# ============================================================================

@router.post("", response_model=HospitalCreateResponse)
async def create_hospital(
    request: HospitalCreateRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Create a new hospital.

    **Auth:** Admin and Web only (EHR not allowed)

    **Request Body:**
    ```json
    {
        "hospital_code": "HOSP001",
        "hospital_name": "City General Hospital"
    }
    ```

    **Returns:**
    - success: True if hospital created
    - message: Success message
    - hospital_id: UUID of created hospital

    **Notes:**
    - hospital_code must be unique
    - hospital_name must be unique
    """
    # EHR clients cannot create hospitals
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to create hospitals"
        )

    try:
        # Check if hospital_code already exists
        existing_code = (
            supabase.table("hospitals")
            .select("id")
            .eq("hospital_code", request.hospital_code)
            .execute()
        )

        if existing_code.data and len(existing_code.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Hospital with this code already exists"
            )

        # Check if hospital_name already exists
        existing_name = (
            supabase.table("hospitals")
            .select("id")
            .eq("hospital_name", request.hospital_name)
            .execute()
        )

        if existing_name.data and len(existing_name.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Hospital with this name already exists"
            )

        # Create hospital
        hospital_data = {
            "hospital_code": request.hospital_code,
            "hospital_name": request.hospital_name,
            "is_active": True
        }

        response = supabase.table("hospitals").insert(hospital_data).execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to create hospital")

        created_hospital = response.data[0]

        return {
            "success": True,
            "message": f"Hospital '{request.hospital_name}' created successfully",
            "hospital_id": created_hospital["id"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create hospital")


@router.put("/{hospital_id}")
async def update_hospital(
    hospital_id: str = Path(..., description="Hospital UUID"),
    request: HospitalUpdateRequest = ...,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Update hospital name and/or code.

    **Auth:** Admin and Web only (EHR not allowed)
    """
    # EHR clients cannot update hospitals
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to update hospitals"
        )

    try:
        # Validate hospital exists
        existing = (
            supabase.table("hospitals")
            .select("id, hospital_name, hospital_code")
            .eq("id", hospital_id)
            .execute()
        )

        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="Hospital not found")

        hospital = existing.data[0]

        # Build update payload
        update_data = {}

        if request.hospital_code is not None and request.hospital_code != hospital["hospital_code"]:
            # Check uniqueness of new code
            code_check = (
                supabase.table("hospitals")
                .select("id")
                .eq("hospital_code", request.hospital_code)
                .neq("id", hospital_id)
                .execute()
            )
            if code_check.data and len(code_check.data) > 0:
                raise HTTPException(
                    status_code=409,
                    detail="Hospital with this code already exists"
                )
            update_data["hospital_code"] = request.hospital_code

        if request.hospital_name is not None and request.hospital_name != hospital["hospital_name"]:
            # Check uniqueness of new name
            name_check = (
                supabase.table("hospitals")
                .select("id")
                .eq("hospital_name", request.hospital_name)
                .neq("id", hospital_id)
                .execute()
            )
            if name_check.data and len(name_check.data) > 0:
                raise HTTPException(
                    status_code=409,
                    detail="Hospital with this name already exists"
                )
            update_data["hospital_name"] = request.hospital_name

        if request.op_registration_fee is not None:
            update_data["op_registration_fee"] = request.op_registration_fee
        if request.ip_admission_fee is not None:
            update_data["ip_admission_fee"] = request.ip_admission_fee

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields provided to update")

        result = (
            supabase.table("hospitals")
            .update(update_data)
            .eq("id", hospital_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update hospital")

        return {
            "success": True,
            "message": f"Hospital updated successfully",
            "hospital": result.data[0]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update hospital")


@router.delete("/{hospital_id}/permanent")
async def hard_delete_hospital(
    hospital_id: str = Path(..., description="Hospital UUID"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Permanently delete a hospital. This is irreversible.

    **Auth:** Admin only

    Blocks deletion if hospital has:
    - Active doctors assigned
    - Recording sessions or extractions via doctors
    - API clients configured

    Cascades deletion of:
    - hospital_ehr integrations
    - hospital_medicine_lists, hospital_investigation_lists
    - hospital_specialty_patterns, hospital_intervention_pricing
    - template_ehr mappings (via templates)
    - qa_engine_settings
    """
    try:
        # Validate hospital exists
        existing = (
            supabase.table("hospitals")
            .select("id, hospital_name")
            .eq("id", hospital_id)
            .execute()
        )

        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="Hospital not found")

        hospital_name = existing.data[0]["hospital_name"]

        # Block if doctors are assigned to this hospital
        doctors_check = (
            supabase.table("doctors")
            .select("id")
            .eq("hospital_id", hospital_id)
            .execute()
        )

        if doctors_check.data and len(doctors_check.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete: doctors are assigned to this hospital. Remove or reassign them first."
            )

        # Block if API clients exist
        api_clients_check = (
            supabase.table("api_clients")
            .select("id")
            .eq("hospital_id", hospital_id)
            .execute()
        )

        if api_clients_check.data and len(api_clients_check.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete: API clients are configured for this hospital. Remove them first."
            )

        # Cascade delete config data (order matters for FK constraints)
        for table in [
            "hospital_ehr",
            "hospital_medicine_lists",
            "hospital_investigation_lists",
            "hospital_specialty_patterns",
            "hospital_intervention_pricing",
            "qa_engine_settings",
            "investigation_list_uploads",
        ]:
            try:
                supabase.table(table).delete().eq("hospital_id", hospital_id).execute()
            except Exception:
                pass  # Table may not have data, continue

        # Delete patients (nullable hospital_id, but clean up)
        try:
            supabase.table("patients").delete().eq("hospital_id", hospital_id).execute()
        except Exception:
            pass

        # Delete nurses
        try:
            supabase.table("nurses").delete().eq("hospital_id", hospital_id).execute()
        except Exception:
            pass

        # Finally delete the hospital
        supabase.table("hospitals").delete().eq("id", hospital_id).execute()

        return {
            "success": True,
            "message": f"Hospital '{hospital_name}' permanently deleted"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete hospital")


@router.delete("/{hospital_id}")
async def deactivate_hospital(
    hospital_id: str = Path(..., description="Hospital UUID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Soft-delete (deactivate) a hospital by setting is_active=false.

    **Auth:** Admin and Web only (EHR not allowed)
    """
    # EHR clients cannot deactivate hospitals
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to deactivate hospitals"
        )

    try:
        # Validate hospital exists
        existing = (
            supabase.table("hospitals")
            .select("id, hospital_name, is_active")
            .eq("id", hospital_id)
            .execute()
        )

        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="Hospital not found")

        hospital = existing.data[0]

        if not hospital.get("is_active"):
            raise HTTPException(status_code=400, detail="Hospital is already inactive")

        # Soft-delete
        supabase.table("hospitals").update({"is_active": False}).eq("id", hospital_id).execute()

        return {
            "success": True,
            "message": f"Hospital '{hospital['hospital_name']}' deactivated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to deactivate hospital")


# ============================================================================
# Hospital Default Template Endpoints
# ============================================================================

@router.put("/{hospital_id}/default-template")
async def set_hospital_default_template(
    hospital_id: str = Path(..., description="Hospital UUID"),
    request: SetDefaultTemplateRequest = None,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Set or clear the default template for a hospital.

    **Auth:** Admin, Web, and EHR (EHR restricted to own hospital)

    **Path Parameters:**
    - hospital_id: Hospital UUID

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
        # EHR clients can only modify their own hospital
        if client.client_type == "ehr":
            if client.hospital_id is None or str(client.hospital_id) != hospital_id:
                raise HTTPException(
                    status_code=403,
                    detail="EHR clients can only modify their own hospital's default template"
                )

        # Validate hospital exists
        hospital_result = (
            supabase.table("hospitals")
            .select("id, hospital_name")
            .eq("id", hospital_id)
            .execute()
        )

        if not hospital_result.data or len(hospital_result.data) == 0:
            raise HTTPException(status_code=404, detail="Hospital not found")

        hospital = hospital_result.data[0]
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

        # Update hospital's default_template_id
        update_result = (
            supabase.table("hospitals")
            .update({"default_template_id": template_id})
            .eq("id", hospital_id)
            .execute()
        )

        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to update hospital default template")

        # Auto-share template with all doctors in this hospital (optimized batch operation)
        doctors_shared = 0
        if template_id:
            # Query 1: Get all active doctor IDs in this hospital
            doctors_result = (
                supabase.table("doctors")
                .select("id")
                .eq("hospital_id", hospital_id)
                .eq("is_active", True)
                .execute()
            )

            if doctors_result.data:
                doctor_ids = {d["id"] for d in doctors_result.data}

                # Query 2: Get doctor IDs that already have access to this template
                existing_result = (
                    supabase.table("doctor_templates")
                    .select("doctor_id")
                    .eq("template_id", template_id)
                    .in_("doctor_id", list(doctor_ids))
                    .execute()
                )

                existing_doctor_ids = {e["doctor_id"] for e in (existing_result.data or [])}

                # Calculate doctors needing new access
                doctors_to_share = doctor_ids - existing_doctor_ids

                # Query 3: Batch insert all new doctor_templates entries
                if doctors_to_share:
                    insert_data = [
                        {
                            "doctor_id": doctor_id,
                            "template_id": template_id,
                            "access_level": "use",
                            "is_active": True,
                        }
                        for doctor_id in doctors_to_share
                    ]
                    supabase.table("doctor_templates").insert(insert_data).execute()
                    doctors_shared = len(doctors_to_share)

        if template_id:
            return {
                "success": True,
                "message": f"Default template set for hospital '{hospital['hospital_name']}'. Auto-shared with {doctors_shared} doctor(s).",
                "default_template_id": template_id,
                "doctors_shared": doctors_shared
            }
        else:
            return {
                "success": True,
                "message": f"Default template cleared for hospital '{hospital['hospital_name']}'",
                "default_template_id": None
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to set hospital default template")


# ============================================================================
# Hospital Settings Endpoints
# ============================================================================

@router.put("/{hospital_id}/settings")
async def update_hospital_settings(
    hospital_id: str = Path(..., description="Hospital UUID"),
    request: HospitalSettingsUpdateRequest = None,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Update hospital settings (e.g., FFmpeg stitching).

    **Auth:** Admin and Web only (EHR not allowed)

    **Path Parameters:**
    - hospital_id: Hospital UUID

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
    # EHR clients cannot modify hospital settings
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to modify hospital settings"
        )

    try:
        # Validate hospital exists
        hospital_result = (
            supabase.table("hospitals")
            .select("id, hospital_name")
            .eq("id", hospital_id)
            .execute()
        )

        if not hospital_result.data or len(hospital_result.data) == 0:
            raise HTTPException(status_code=404, detail="Hospital not found")

        hospital = hospital_result.data[0]

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

        if not update_data:
            raise HTTPException(status_code=400, detail="No settings provided to update")

        # Update hospital settings
        update_result = (
            supabase.table("hospitals")
            .update(update_data)
            .eq("id", hospital_id)
            .execute()
        )

        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to update hospital settings")

        # Invalidate hospital settings cache (infinite TTL cache needs explicit invalidation)
        from services.supabase_service import invalidate_hospital_settings_cache
        invalidate_hospital_settings_cache(hospital_id)

        # Invalidate realtime subscription cache if that setting was updated
        if "enable_realtime_subscription" in update_data:
            from services.realtime_publisher_service import invalidate_hospital_realtime_cache
            invalidate_hospital_realtime_cache(hospital_id)

        return {
            "success": True,
            "message": f"Settings updated for hospital '{hospital['hospital_name']}'",
            "settings": update_data
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update hospital settings")


# ============================================================================
# Hospital EHR Integration Endpoints
# ============================================================================

@router.get("/{hospital_id}/ehr-integrations")
async def list_hospital_ehr_integrations(
    hospital_id: str = Path(..., description="Hospital UUID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    List all EHR integrations for a hospital.

    **Auth:** Admin, Web, and EHR (EHR restricted to own hospital)

    **Returns:**
    - integrations: List of EHR integration configs (api_key masked)
    """
    try:
        # EHR clients can only view their own hospital's integrations
        if client.client_type == "ehr":
            if client.hospital_id is None or str(client.hospital_id) != hospital_id:
                raise HTTPException(
                    status_code=403,
                    detail="EHR clients can only view their own hospital's integrations"
                )

        # Validate hospital exists
        hospital_result = (
            supabase.table("hospitals")
            .select("id")
            .eq("id", hospital_id)
            .execute()
        )

        if not hospital_result.data:
            raise HTTPException(status_code=404, detail="Hospital not found")

        # Get all integrations for this hospital with ehr_types join
        result = (
            supabase.table("hospital_ehr")
            .select("""
                id, hospital_id, ehr_type_id, ehr_integration_type, api_url, api_key,
                is_enabled, is_default, created_at, updated_at,
                ehr_types(ehr_code, ehr_name)
            """)
            .eq("hospital_id", hospital_id)
            .order("created_at", desc=True)
            .execute()
        )

        # Mask api_key in response and flatten ehr_types
        integrations = []
        for row in (result.data or []):
            ehr_type = row.get("ehr_types") or {}
            integrations.append({
                "id": row["id"],
                "hospital_id": row["hospital_id"],
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


@router.post("/{hospital_id}/ehr-integrations")
async def create_hospital_ehr_integration(
    hospital_id: str = Path(..., description="Hospital UUID"),
    request: EhrIntegrationCreateRequest = ...,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Create a new EHR integration for a hospital.

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
    - If is_default is true, any existing default for this hospital will be unset
    - New doctors created in this hospital will be auto-assigned the default EHR type
    """
    # EHR clients cannot create integrations
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to create integrations"
        )

    try:
        # Validate hospital exists
        hospital_result = (
            supabase.table("hospitals")
            .select("id, hospital_name")
            .eq("id", hospital_id)
            .execute()
        )

        if not hospital_result.data:
            raise HTTPException(status_code=404, detail="Hospital not found")

        hospital = hospital_result.data[0]

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

        # Check if this ehr_type already exists for this hospital
        existing = (
            supabase.table("hospital_ehr")
            .select("id")
            .eq("hospital_id", hospital_id)
            .eq("ehr_type_id", request.ehr_type_id)
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=409,
                detail="This EHR type is already configured for this hospital"
            )

        # If setting as default, unset any existing default
        if request.is_default:
            supabase.table("hospital_ehr").update({"is_default": False}).eq("hospital_id", hospital_id).execute()

        # Create the integration
        insert_data = {
            "hospital_id": hospital_id,
            "ehr_type_id": request.ehr_type_id,
            "ehr_integration_type": ehr_type["ehr_code"],  # For backward compatibility
            "api_url": request.api_url,
            "api_key": request.api_key,
            "is_enabled": request.is_enabled,
            "is_default": request.is_default
        }

        result = supabase.table("hospital_ehr").insert(insert_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create EHR integration")

        created = result.data[0]

        return {
            "success": True,
            "message": f"EHR integration '{ehr_type['ehr_name']}' created for hospital '{hospital['hospital_name']}'",
            "integration": {
                "id": created["id"],
                "hospital_id": created["hospital_id"],
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


@router.put("/{hospital_id}/ehr-integrations/{integration_id}")
async def update_hospital_ehr_integration(
    hospital_id: str = Path(..., description="Hospital UUID"),
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
    - If is_default is true, any existing default for this hospital will be unset
    """
    # EHR clients cannot update integrations
    if client.client_type == "ehr":
        raise HTTPException(
            status_code=403,
            detail="EHR clients are not authorized to update integrations"
        )

    try:
        # Validate integration exists and belongs to hospital (include ehr_types join)
        existing = (
            supabase.table("hospital_ehr")
            .select("id, hospital_id, ehr_type_id, ehr_integration_type, ehr_types(ehr_code, ehr_name)")
            .eq("id", integration_id)
            .eq("hospital_id", hospital_id)
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
            supabase.table("hospital_ehr").update({"is_default": False}).eq("hospital_id", hospital_id).execute()

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
            supabase.table("hospital_ehr")
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
                "hospital_id": updated["hospital_id"],
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


@router.delete("/{hospital_id}/ehr-integrations/{integration_id}")
async def delete_hospital_ehr_integration(
    hospital_id: str = Path(..., description="Hospital UUID"),
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
        # Validate integration exists and belongs to hospital
        existing = (
            supabase.table("hospital_ehr")
            .select("id, hospital_id, ehr_integration_type")
            .eq("id", integration_id)
            .eq("hospital_id", hospital_id)
            .execute()
        )

        if not existing.data:
            raise HTTPException(
                status_code=404,
                detail="Integration not found"
            )

        integration = existing.data[0]

        # Delete the integration
        supabase.table("hospital_ehr").delete().eq("id", integration_id).execute()

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


@router.get("/{hospital_id}/room-rates")
async def list_room_rates(
    hospital_id: str = Path(..., description="Hospital UUID"),
    include_inactive: bool = False,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    List room rates for a hospital.

    **Auth:** Admin + Web + EHR
    """
    try:
        query = (
            supabase.table("room_rate_master")
            .select("*")
            .eq("hospital_id", hospital_id)
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


@router.post("/{hospital_id}/room-rates")
async def create_room_rate(
    hospital_id: str = Path(..., description="Hospital UUID"),
    request: RoomRateCreateRequest = ...,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Create a room rate entry.

    **Auth:** Admin + Web + EHR
    """
    try:
        insert_data = {
            "hospital_id": hospital_id,
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
                detail=f"Room rate for '{request.room_category}' already exists for this hospital"
            )
        raise HTTPException(status_code=500, detail="Failed to create room rate")


@router.put("/{hospital_id}/room-rates/{rate_id}")
async def update_room_rate(
    hospital_id: str = Path(..., description="Hospital UUID"),
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
            .eq("hospital_id", hospital_id)
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


@router.delete("/{hospital_id}/room-rates/{rate_id}")
async def delete_room_rate(
    hospital_id: str = Path(..., description="Hospital UUID"),
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
            .eq("hospital_id", hospital_id)
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
# Hospital Feature Flags Endpoints
# ============================================================================

@router.get("/{hospital_id}/features")
async def get_hospital_features(
    hospital_id: str = Path(..., description="Hospital UUID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Get feature flags for a hospital.

    **Auth:** Admin + Web only (EHR/mobile not allowed)

    Uses cached hospital settings — zero DB hit on hot path.

    **Returns:**
    - feature_flags: Dict of feature key → enabled boolean
    """
    if client.client_type not in ("admin", "web_app", "ehr"):
        raise HTTPException(status_code=403, detail="Only admin, web, and EHR clients can access feature flags")

    try:
        settings = get_hospital_settings_cached(hospital_id)
        return {
            "success": True,
            "hospital_id": hospital_id,
            "feature_flags": settings.get("feature_flags", {}),
        }
    except Exception as e:
        logger.error(f"[FEATURES] Failed to get features for {hospital_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get feature flags")


@router.put("/{hospital_id}/features")
async def update_hospital_features(
    request: FeatureFlagsUpdateRequest,
    hospital_id: str = Path(..., description="Hospital UUID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Update feature flags for a hospital (partial merge).

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
        # Validate hospital exists
        existing = (
            supabase.table("hospitals")
            .select("id, hospital_name, feature_flags")
            .eq("id", hospital_id)
            .execute()
        )

        if not existing.data or len(existing.data) == 0:
            raise HTTPException(status_code=404, detail="Hospital not found")

        hospital = existing.data[0]
        current_flags = hospital.get("feature_flags") or {}

        # Merge: existing flags + new flags (new wins)
        merged_flags = {**current_flags, **request.feature_flags}

        # Update in DB
        update_result = (
            supabase.table("hospitals")
            .update({"feature_flags": merged_flags})
            .eq("id", hospital_id)
            .execute()
        )

        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to update feature flags")

        # Invalidate cache
        invalidate_hospital_settings_cache(hospital_id)

        logger.info(f"[FEATURES] Updated feature flags for hospital {hospital_id}: {list(request.feature_flags.keys())}")

        return {
            "success": True,
            "hospital_id": hospital_id,
            "feature_flags": merged_flags,
            "message": f"Feature flags updated for '{hospital['hospital_name']}'",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FEATURES] Failed to update features for {hospital_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update feature flags")

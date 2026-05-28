"""
Doctor Templates Router

Handles template sharing and activation operations:
- Share templates with individual doctors
- Bulk share templates (hospital/specialization)
- Activate/deactivate templates for doctors
- Get accessible templates for doctors
- Revoke template access
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel, Field
import uuid
import os

# Conditional authentication imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"

# Type stubs for when AUTH_ENABLED is False - these are no-op functions
if AUTH_ENABLED:
    from dependencies.auth import require_admin, EHRDoctorAccessChecker, get_current_client
    _doctor_checker = EHRDoctorAccessChecker()

    async def verify_doctor_access(request: Request, doctor_id: Optional[str] = None):  # type: ignore[misc]
        doctor_uuid = uuid.UUID(doctor_id) if doctor_id else None
        client = get_current_client(request)
        return await _doctor_checker(request, doctor_uuid, client)

    async def verify_sharing_doctor_access(request: Request, sharing_doctor_id: Optional[str] = None):  # type: ignore[misc]
        """For revoke endpoint where sharing_doctor_id is the actor"""
        doctor_uuid = uuid.UUID(sharing_doctor_id) if sharing_doctor_id else None
        client = get_current_client(request)
        return await _doctor_checker(request, doctor_uuid, client)

    async def verify_doctor_access_from_body(request: Request):  # type: ignore[misc]
        """For endpoints where doctor_id is in request body - validation happens in endpoint"""
        client = get_current_client(request)
        return await _doctor_checker(request, None, client)
else:
    from dependencies.auth import require_admin  # type: ignore[no-redef]

    async def verify_doctor_access(request: Request = None, doctor_id: Optional[str] = None):  # type: ignore[misc]
        return None

    async def verify_sharing_doctor_access(request: Request = None, sharing_doctor_id: Optional[str] = None):  # type: ignore[misc]
        return None

    async def verify_doctor_access_from_body(request: Request = None):  # type: ignore[misc]
        return None
from services.doctor_templates_service import (
    share_template_with_doctor,
    bulk_share_template,
    share_template_with_hospital,
    share_template_with_specialization,
    activate_template_for_doctor,
    deactivate_template_for_doctor,
    get_doctor_accessible_templates,
    get_doctor_default_template,
    revoke_template_access,
    activate_from_consultation_type,
    clone_template,
    get_doctor_dashboard_data,
    get_template_shares,
    assign_template_ownership
)
from services.supabase_service import strip_internal_template_fields


router = APIRouter(prefix="/api/v1/doctor-templates", tags=["Doctor Templates"])


# =============================================================================
# Request/Response Models
# =============================================================================

class ShareTemplateRequest(BaseModel):
    """Request to share template with individual doctors"""
    sharing_doctor_id: str = Field(..., description="Doctor UUID who is sharing the template (must own the template)")
    template_id: str = Field(..., description="Template ID to share")
    doctor_ids: List[str] = Field(..., min_items=1, description="List of doctor UUIDs")
    new_owner_id: Optional[str] = Field(None, description="If provided, assigns ownership of a global template to this doctor before sharing")

    class Config:
        json_schema_extra = {
            "example": {
                "sharing_doctor_id": "123e4567-e89b-12d3-a456-426614174000",
                "template_id": "123e4567-e89b-12d3-a456-426614174000",
                "doctor_ids": ["223e4567-e89b-12d3-a456-426614174000"],
                "new_owner_id": None
            }
        }


class ShareHospitalRequest(BaseModel):
    """Request to share template with all doctors in a hospital"""
    sharing_doctor_id: str = Field(..., description="Doctor UUID who is sharing the template (must own the template)")
    template_id: str = Field(..., description="Template ID to share")
    hospital_id: str = Field(..., description="Hospital UUID")
    new_owner_id: Optional[str] = Field(None, description="If provided, assigns ownership of a global template to this doctor before sharing")


class ShareSpecializationRequest(BaseModel):
    """Request to share template with all doctors of a specialization"""
    sharing_doctor_id: str = Field(..., description="Doctor UUID who is sharing the template (must own the template)")
    template_id: str = Field(..., description="Template ID to share")
    specialization: str = Field(..., description="Specialization name (e.g., 'Cardiology')")
    new_owner_id: Optional[str] = Field(None, description="If provided, assigns ownership of a global template to this doctor before sharing")


class ActivateTemplateRequest(BaseModel):
    """Request to activate a template for a doctor"""
    doctor_id: str = Field(..., description="Doctor UUID")
    template_id: str = Field(..., description="Template ID to activate")
    consultation_type_id: str = Field(..., description="Consultation type UUID")


class RevokeAccessRequest(BaseModel):
    """Request to revoke doctor's access to template"""
    doctor_id: str = Field(..., description="Doctor UUID")
    template_id: str = Field(..., description="Template ID")


class ActivateFromConsultationTypeRequest(BaseModel):
    """Request to create and activate template from consultation type"""
    doctor_id: str = Field(..., description="Doctor UUID")
    consultation_type_id: str = Field(..., description="Consultation type UUID")
    template_name: Optional[str] = Field(None, description="Custom template name (optional)")

    class Config:
        json_schema_extra = {
            "example": {
                "doctor_id": "223e4567-e89b-12d3-a456-426614174000",
                "consultation_type_id": "323e4567-e89b-12d3-a456-426614174000",
                "template_name": "My Custom OP Template"
            }
        }


class CloneTemplateRequest(BaseModel):
    """Request to clone a template"""
    doctor_id: str = Field(..., description="Doctor UUID")
    source_template_id: str = Field(..., description="Template UUID to clone")
    template_name: Optional[str] = Field(None, description="Custom name for cloned template (optional)")

    class Config:
        json_schema_extra = {
            "example": {
                "doctor_id": "223e4567-e89b-12d3-a456-426614174000",
                "source_template_id": "423e4567-e89b-12d3-a456-426614174000",
                "template_name": "My Customized Template"
            }
        }


# =============================================================================
# Template Sharing Endpoints
# =============================================================================

@router.get("/template-shares/{template_id}")
async def get_shares(
    request: Request,
    template_id: str,
    _auth = Depends(require_admin)
):
    """
    Get all shares for a template.

    Returns individual doctor shares, hospitals, and specializations
    that have access to this template.

    **Path Parameters:**
    - template_id: Template UUID

    **Returns:**
    - doctors: List of individual doctor shares
    - hospital_ids: List of hospital IDs with doctors who have this template
    - specializations: List of specializations with doctors who have this template
    - total_shares: Total number of individual doctor shares
    """
    try:
        template_uuid = uuid.UUID(template_id)
        shares = get_template_shares(template_uuid)

        return {
            "success": True,
            "shares": shares
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get template shares")


@router.post("/share")
async def share_template(
    http_request: Request,
    request: ShareTemplateRequest,
    _auth = Depends(verify_doctor_access_from_body)
):
    """
    Share template with individual doctors.

    **Request Body:**
    - sharing_doctor_id: Doctor UUID who is sharing (must own the template)
    - template_id: Template to share
    - doctor_ids: List of doctor UUIDs to share with
    - new_owner_id: (Optional) If sharing a global template, assign ownership to this doctor first

    **Returns:**
    - success: Boolean
    - shared_count: Number of doctors successfully shared with
    - failed: List of doctors that failed (with reasons)
    - ownership_assigned: (If new_owner_id provided) Details of ownership assignment
    """
    try:
        template_uuid = uuid.UUID(request.template_id)
        doctor_uuids = [uuid.UUID(d) for d in request.doctor_ids]

        ownership_result = None

        # If new_owner_id provided, assign ownership first (converts global to doctor-owned)
        if request.new_owner_id:
            new_owner_uuid = uuid.UUID(request.new_owner_id)
            ownership_result = assign_template_ownership(
                template_id=template_uuid,
                new_owner_id=new_owner_uuid,
            )

        result = bulk_share_template(
            template_id=template_uuid,
            doctor_ids=doctor_uuids,
        )

        response = {
            "success": True,
            "message": f"Template shared with {result['successful']} doctor(s)",
            "shared_count": result['successful'],
            "failed_count": result['failed'],
            "failures": result.get('failures', [])
        }

        if ownership_result:
            response["ownership_assigned"] = ownership_result

        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to share template")


@router.post("/share-hospital")
async def share_template_hospital(
    http_request: Request,
    request: ShareHospitalRequest,
    _auth = Depends(verify_doctor_access_from_body)
):
    """
    Share template with all doctors in a hospital.

    **Request Body:**
    - sharing_doctor_id: Doctor UUID who is sharing (must own the template)
    - template_id: Template to share
    - hospital_id: Hospital UUID
    - new_owner_id: (Optional) If sharing a global template, assign ownership to this doctor first

    **Returns:**
    - success: Boolean
    - shared_count: Number of doctors in hospital who received access
    - ownership_assigned: (If new_owner_id provided) Details of ownership assignment
    """
    try:
        template_uuid = uuid.UUID(request.template_id)
        hospital_uuid = uuid.UUID(request.hospital_id)

        ownership_result = None

        # If new_owner_id provided, assign ownership first (converts global to doctor-owned)
        if request.new_owner_id:
            new_owner_uuid = uuid.UUID(request.new_owner_id)
            ownership_result = assign_template_ownership(
                template_id=template_uuid,
                new_owner_id=new_owner_uuid,
            )

        result = share_template_with_hospital(
            template_id=template_uuid,
            hospital_id=hospital_uuid,
        )

        # Handle case when no doctors found
        shared_count = result.get('successful', result.get('total_doctors', 0))

        response = {
            "success": True,
            "message": f"Template shared with {shared_count} doctors in hospital",
            "shared_count": shared_count,
            "hospital_id": request.hospital_id
        }

        if ownership_result:
            response["ownership_assigned"] = ownership_result

        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to share template with hospital")


@router.post("/share-specialization")
async def share_template_spec(
    http_request: Request,
    request: ShareSpecializationRequest,
    _auth = Depends(verify_doctor_access_from_body)
):
    """
    Share template with all doctors of a specialization.

    **Request Body:**
    - sharing_doctor_id: Doctor UUID who is sharing (must own the template)
    - template_id: Template to share
    - specialization: Specialization name (e.g., 'Cardiology', 'Psychiatry')
    - new_owner_id: (Optional) If sharing a global template, assign ownership to this doctor first

    **Returns:**
    - success: Boolean
    - shared_count: Number of doctors in specialization who received access
    - ownership_assigned: (If new_owner_id provided) Details of ownership assignment
    """
    try:
        template_uuid = uuid.UUID(request.template_id)

        ownership_result = None

        # If new_owner_id provided, assign ownership first (converts global to doctor-owned)
        if request.new_owner_id:
            new_owner_uuid = uuid.UUID(request.new_owner_id)
            ownership_result = assign_template_ownership(
                template_id=template_uuid,
                new_owner_id=new_owner_uuid,
            )

        result = share_template_with_specialization(
            template_id=template_uuid,
            specialization=request.specialization,
        )

        # Handle case when no doctors found
        shared_count = result.get('successful', result.get('total_doctors', 0))

        response = {
            "success": True,
            "message": f"Template shared with {shared_count} doctors in {request.specialization}",
            "shared_count": shared_count,
            "specialization": request.specialization
        }

        if ownership_result:
            response["ownership_assigned"] = ownership_result

        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to share template with specialization")


# =============================================================================
# Template Activation Endpoints
# =============================================================================

@router.post("/activate")
async def activate_template(
    http_request: Request,
    request: ActivateTemplateRequest,
    _auth = Depends(verify_doctor_access_from_body)
):
    """
    Activate a template for a doctor (ensure doctor_templates entry exists with is_active=True).

    **Request Body:**
    - doctor_id: Doctor UUID
    - template_id: Template to activate
    - consultation_type_id: Consultation type UUID

    **Returns:**
    - success: Boolean
    - activated_template_id: Template UUID
    """
    try:
        doctor_uuid = uuid.UUID(request.doctor_id)
        template_uuid = uuid.UUID(request.template_id)
        consultation_type_uuid = uuid.UUID(request.consultation_type_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        activate_template_for_doctor(
            doctor_id=doctor_uuid,
            template_id=template_uuid,
            consultation_type_id=consultation_type_uuid
        )

        return {
            "success": True,
            "is_active": True,
            "message": "Template activated successfully",
            "activated_template_id": request.template_id,
        }

    except ValueError as e:
        error_msg = str(e).lower()
        if "deactivated" in error_msg:
            raise HTTPException(status_code=400, detail="Template has been deactivated by admin")
        elif "not found" in error_msg:
            raise HTTPException(status_code=400, detail="Template not found")
        else:
            raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to activate template")


@router.post("/deactivate")
async def deactivate_template(
    request: Request,
    doctor_id: str = Query(..., description="Doctor UUID"),
    template_id: str = Query(..., description="Template ID to deactivate"),
    _auth = Depends(verify_doctor_access)
):
    """
    Remove a template from a doctor's list (soft-delete the doctor-template link).

    **Query Parameters:**
    - doctor_id: Doctor UUID
    - template_id: Template to remove

    **Returns:**
    - success: Boolean
    """
    try:
        doctor_uuid = uuid.UUID(doctor_id)
        template_uuid = uuid.UUID(template_id)

        deactivate_template_for_doctor(
            doctor_id=doctor_uuid,
            template_id=template_uuid
        )

        return {
            "success": True,
            "is_active": False,
            "message": "Template removed successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to deactivate template")


# =============================================================================
# Template Access Endpoints
# =============================================================================

@router.get("/accessible")
async def get_accessible_templates(
    request: Request,
    doctor_id: str = Query(..., description="Doctor UUID"),
    consultation_type_id: Optional[str] = Query(None, description="Filter by consultation type"),
    include_common: bool = Query(True, description="Include common templates"),
    active_only: bool = Query(False, description="Return only active templates"),
    _auth = Depends(verify_doctor_access)
):
    """
    Get all templates accessible to a doctor.

    **Returns templates that are:**
    - Owned by the doctor (doctor_id = doctor)
    - Shared with the doctor (via doctor_templates junction table)
    - Common templates (doctor_id = NULL) if include_common=True

    **Query Parameters:**
    - doctor_id: Doctor UUID (required)
    - consultation_type_id: Filter by consultation type (optional)
    - include_common: Include common templates (default: true)
    - active_only: Return only active templates (default: false)

    **Returns:**
    - success: Boolean
    - templates: List of template objects with access info
    - count: Total number of accessible templates
    - default_template_id: Default template UUID (doctor default > hospital default > null)
    - default_template_code: Default template code (or null)
    """
    try:
        doctor_uuid = uuid.UUID(doctor_id)
        consultation_type_uuid = uuid.UUID(consultation_type_id) if consultation_type_id else None

        templates = get_doctor_accessible_templates(
            doctor_id=doctor_uuid,
            consultation_type_id=consultation_type_uuid,
            include_common=include_common
        )

        # Filter to only active templates if requested
        if active_only:
            templates = [t for t in templates if t.get("is_active") is True]

        # Get the default template for this doctor (doctor default > hospital default > null)
        default_template = get_doctor_default_template(doctor_uuid)

        return {
            "success": True,
            "templates": templates,
            "count": len(templates),
            "default_template_id": default_template.get("id") if default_template else None,
            "default_template_code": default_template.get("template_code") if default_template else None
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get accessible templates")


@router.delete("/revoke")
async def revoke_access(
    request: Request,
    sharing_doctor_id: str = Query(..., description="Doctor UUID who is revoking (must own the template)"),
    doctor_id: str = Query(..., description="Doctor UUID whose access is being revoked"),
    template_id: str = Query(..., description="Template ID"),
    _auth = Depends(verify_sharing_doctor_access)
):
    """
    Revoke a doctor's access to a template.

    **Query Parameters:**
    - sharing_doctor_id: Doctor UUID who is revoking (must own the template)
    - doctor_id: Doctor UUID whose access is being revoked
    - template_id: Template ID (UUID)

    **Note:**
    - Cannot revoke access to owned templates (doctor_id matches template.doctor_id)
    - Cannot revoke access to common templates (doctor_id = NULL)
    - Only revokes shared access via doctor_templates junction table

    **Returns:**
    - success: Boolean
    - revoked: Boolean - Whether an entry was actually deleted
    - details: Additional details about the revoke operation
    """
    try:
        doctor_uuid = uuid.UUID(doctor_id)
        template_uuid = uuid.UUID(template_id)

        result = revoke_template_access(
            doctor_id=doctor_uuid,
            template_id=template_uuid
        )

        return {
            "success": True,
            "message": "Template access revoked successfully" if result.get("revoked") else "No access entry found to revoke",
            "revoked": result.get("revoked", False),
            "details": result
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail="Access denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to revoke template access")


# =============================================================================
# Template Creation Endpoints (NEW)
# =============================================================================

@router.post("/activate-from-consultation-type")
async def activate_from_type(
    http_request: Request,
    request: ActivateFromConsultationTypeRequest,
    _auth = Depends(verify_doctor_access_from_body)
):
    """
    Create and activate a new doctor-owned template from a consultation type.

    **Workflow:**
    1. Verify doctor has visibility to consultation type
    2. Create new template owned by doctor
    3. Clone all segments from consultation_type_segments junction
    4. Auto-activate for doctor

    **Request Body:**
    - doctor_id: Doctor UUID
    - consultation_type_id: Consultation type UUID
    - template_name: Optional custom name

    **Returns:**
    - success: Boolean
    - template: Created template object
    - segment_count: Number of segments cloned
    - is_activated: Boolean

    **Errors:**
    - 403: Doctor doesn't have visibility to consultation type
    - 404: Consultation type not found
    """
    try:
        doctor_uuid = uuid.UUID(request.doctor_id)
        consultation_type_uuid = uuid.UUID(request.consultation_type_id)

        template = activate_from_consultation_type(
            doctor_id=doctor_uuid,
            consultation_type_id=consultation_type_uuid,
            template_name=request.template_name
        )

        return {
            "success": True,
            "template": strip_internal_template_fields(template),
            "message": f"Template created and activated for doctor {request.doctor_id}"
        }

    except PermissionError as e:
        raise HTTPException(status_code=403, detail="Access denied")
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Not found")
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create template from consultation type")


@router.post("/clone")
async def clone_template_endpoint(
    http_request: Request,
    request: CloneTemplateRequest,
    _auth = Depends(verify_doctor_access_from_body)
):
    """
    Clone a template to create a doctor-owned copy.

    **Doctor can clone:**
    - Shared templates
    - Global templates (doctor_id = NULL)
    - Their own templates (for versioning)

    **Workflow:**
    1. Verify doctor has access to source template
    2. Create new template owned by doctor
    3. Copy all segments from template_segments junction
    4. Auto-activate for doctor

    **Request Body:**
    - doctor_id: Doctor UUID
    - source_template_id: Template UUID to clone
    - template_name: Optional custom name

    **Returns:**
    - success: Boolean
    - template: Created template object
    - source_template_id: Original template UUID
    - segment_count: Number of segments cloned
    - is_activated: Boolean

    **Errors:**
    - 403: Doctor doesn't have access to source template
    - 404: Source template not found
    """
    try:
        doctor_uuid = uuid.UUID(request.doctor_id)
        source_template_uuid = uuid.UUID(request.source_template_id)

        template = clone_template(
            doctor_id=doctor_uuid,
            source_template_id=source_template_uuid,
            template_name=request.template_name
        )

        return {
            "success": True,
            "template": strip_internal_template_fields(template),
            "message": f"Template cloned successfully for doctor {request.doctor_id}"
        }

    except PermissionError as e:
        raise HTTPException(status_code=403, detail="Access denied")
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Not found")
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to clone template")


@router.get("/dashboard/{doctor_id}")
async def get_dashboard(
    request: Request,
    doctor_id: str,
    _auth = Depends(verify_doctor_access)
):
    """
    Get comprehensive dashboard data for a doctor.

    **Returns two types of items:**
    1. **Visible Consultation Types** - Based on visibility settings
       - Can activate to create new owned template
       - Badge: "Activate"

    2. **Accessible Templates** - Owned, shared, and global templates
       - Owned templates: Badge "Owned"
       - Global templates: Badge "Global"
       - Shared templates: Badge "Shared"

    **Query Parameters:**
    - doctor_id: Doctor UUID (path parameter)

    **Returns:**
    - success: Boolean
    - consultation_types: List of visible consultation types with action badges
    - templates: List of accessible templates with access info and badges
    - consultation_types_count: Count
    - templates_count: Count
    """
    try:
        doctor_uuid = uuid.UUID(doctor_id)

        dashboard_data = get_doctor_dashboard_data(doctor_id=doctor_uuid)

        return {
            "success": True,
            **dashboard_data
        }

    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Not found")
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get dashboard data")


# ============================================================================
# Doctor Template Segment Management APIs
# ============================================================================

class AddSegmentsFromTypeRequest(BaseModel):
    """Request model for adding segments from consultation type to template"""
    segment_codes: Optional[List[str]] = Field(default=None, description="Specific segment codes to add")
    add_all_missing: bool = Field(default=False, description="Add all segments not yet in template")
    default_category: str = Field(default="excluded", description="Category for new segments")


@router.get("/{template_id}/segments/available")
async def get_available_segments_for_doctor_template(
    request: Request,
    template_id: str,
    doctor_id: str = Query(..., description="Doctor ID requesting the segments"),
    _auth = Depends(verify_doctor_access)
) -> Dict[str, Any]:
    """
    Get segments available to add to a doctor's template.

    **Use Case:** Before adding segments to a doctor-owned template, show which segments
    are available. Validates doctor has access to the template.

    **Path Parameters:**
    - template_id: Template UUID

    **Query Parameters:**
    - doctor_id: Doctor UUID (validates access)

    **Returns:**
    - available_segments: List of segments that can be added
    - consultation_type_code: The template's consultation type
    - count: Number of available segments

    **Errors:**
    - 403: Doctor doesn't have access to this template
    - 404: Template not found
    """
    try:
        from services.supabase_service import (
            get_available_segments_for_template,
            get_template_by_id,
            check_doctor_template_access
        )

        template_uuid = uuid.UUID(template_id)
        doctor_uuid = uuid.UUID(doctor_id)

        # Check if template exists
        template = get_template_by_id(template_uuid)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Check if doctor owns or has access to template
        if template.get("doctor_id"):
            template_doctor_id = uuid.UUID(template["doctor_id"]) if isinstance(template["doctor_id"], str) else template["doctor_id"]
            if template_doctor_id != doctor_uuid:
                # Not the owner, check if shared
                has_access = check_doctor_template_access(doctor_uuid, template_uuid)
                if not has_access:
                    raise HTTPException(status_code=403, detail="Doctor doesn't have access to this template")

        result = get_available_segments_for_template(template_uuid)
        return result

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get available segments")


@router.post("/{template_id}/segments/add-from-type")
async def add_segments_to_doctor_template(
    http_request: Request,
    template_id: str,
    request: AddSegmentsFromTypeRequest,
    doctor_id: str = Query(..., description="Doctor ID adding the segments"),
    _auth = Depends(verify_doctor_access)
) -> Dict[str, Any]:
    """
    Add segments from consultation type to doctor's template.

    **Use Case:** Allow doctors to add new segments to their templates without
    using "Inherit from Type" (which replaces all segments).

    **Path Parameters:**
    - template_id: Template UUID

    **Query Parameters:**
    - doctor_id: Doctor UUID (validates access)

    **Request Body:**
    - segment_codes: List of specific segment codes to add (optional)
    - add_all_missing: If true, add ALL segments not yet in template
    - default_category: Category for new segments (default: 'excluded')

    **Example:**
    ```bash
    POST /api/v1/doctor-templates/uuid/segments/add-from-type?doctor_id=uuid
    {
      "segment_codes": ["NEW_SEGMENT"],
      "default_category": "excluded"
    }
    ```

    **Returns:**
    - segments_added: List of added segments
    - count: Number of segments added

    **Errors:**
    - 403: Doctor doesn't have access to this template
    - 404: Template not found
    """
    try:
        from services.supabase_service import (
            add_segments_to_template_from_type,
            get_template_by_id,
            check_doctor_template_access
        )

        template_uuid = uuid.UUID(template_id)
        doctor_uuid = uuid.UUID(doctor_id)

        # Check if template exists
        template = get_template_by_id(template_uuid)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Check if doctor owns or has edit access to template
        if template.get("doctor_id"):
            template_doctor_id = uuid.UUID(template["doctor_id"]) if isinstance(template["doctor_id"], str) else template["doctor_id"]
            if template_doctor_id != doctor_uuid:
                raise HTTPException(status_code=403, detail="Only template owner can add segments")
        else:
            # Global template - doctors can't modify
            raise HTTPException(status_code=403, detail="Cannot modify global templates")

        result = add_segments_to_template_from_type(
            template_id=template_uuid,
            segment_codes=request.segment_codes,
            add_all_missing=request.add_all_missing,
            default_category=request.default_category
        )

        return result

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to add segments")

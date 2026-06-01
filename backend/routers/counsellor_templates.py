"""
Counsellor Templates Router

Handles template sharing and activation operations:
- Share templates with individual counsellors
- Bulk share templates (school/specialization)
- Activate/deactivate templates for counsellors
- Get accessible templates for counsellors
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
    from dependencies.auth import require_admin, EHRCounsellorAccessChecker, get_current_client
    _doctor_checker = EHRCounsellorAccessChecker()

    async def verify_counsellor_access(request: Request, counsellor_id: Optional[str] = None):  # type: ignore[misc]
        counsellor_uuid = uuid.UUID(counsellor_id) if counsellor_id else None
        client = get_current_client(request)
        return await _doctor_checker(request, counsellor_uuid, client)

    async def verify_sharing_counsellor_access(request: Request, sharing_counsellor_id: Optional[str] = None):  # type: ignore[misc]
        """For revoke endpoint where sharing_counsellor_id is the actor"""
        counsellor_uuid = uuid.UUID(sharing_counsellor_id) if sharing_counsellor_id else None
        client = get_current_client(request)
        return await _doctor_checker(request, counsellor_uuid, client)

    async def verify_counsellor_access_from_body(request: Request):  # type: ignore[misc]
        """For endpoints where counsellor_id is in request body - validation happens in endpoint"""
        client = get_current_client(request)
        return await _doctor_checker(request, None, client)
else:
    from dependencies.auth import require_admin  # type: ignore[no-redef]

    async def verify_counsellor_access(request: Request = None, counsellor_id: Optional[str] = None):  # type: ignore[misc]
        return None

    async def verify_sharing_counsellor_access(request: Request = None, sharing_counsellor_id: Optional[str] = None):  # type: ignore[misc]
        return None

    async def verify_counsellor_access_from_body(request: Request = None):  # type: ignore[misc]
        return None
from services.counsellor_templates_service import (
    share_template_with_counsellor,
    bulk_share_template,
    share_template_with_school,
    share_template_with_specialization,
    activate_template_for_counsellor,
    deactivate_template_for_counsellor,
    get_counsellor_accessible_templates,
    get_counsellor_default_template,
    revoke_template_access,
    activate_from_consultation_type,
    clone_template,
    get_counsellor_dashboard_data,
    get_template_shares,
    assign_template_ownership
)
from services.supabase_service import strip_internal_template_fields


router = APIRouter(prefix="/api/v1/counsellor-templates", tags=["Counsellor Templates"])


# =============================================================================
# Request/Response Models
# =============================================================================

class ShareTemplateRequest(BaseModel):
    """Request to share template with individual counsellors"""
    sharing_counsellor_id: str = Field(..., description="Counsellor UUID who is sharing the template (must own the template)")
    template_id: str = Field(..., description="Template ID to share")
    counsellor_ids: List[str] = Field(..., min_items=1, description="List of counsellor UUIDs")
    new_owner_id: Optional[str] = Field(None, description="If provided, assigns ownership of a global template to this counsellor before sharing")

    class Config:
        json_schema_extra = {
            "example": {
                "sharing_counsellor_id": "123e4567-e89b-12d3-a456-426614174000",
                "template_id": "123e4567-e89b-12d3-a456-426614174000",
                "counsellor_ids": ["223e4567-e89b-12d3-a456-426614174000"],
                "new_owner_id": None
            }
        }


class ShareSchoolRequest(BaseModel):
    """Request to share template with all counsellors in a school"""
    sharing_counsellor_id: str = Field(..., description="Counsellor UUID who is sharing the template (must own the template)")
    template_id: str = Field(..., description="Template ID to share")
    school_id: str = Field(..., description="School UUID")
    new_owner_id: Optional[str] = Field(None, description="If provided, assigns ownership of a global template to this counsellor before sharing")


class ShareSpecializationRequest(BaseModel):
    """Request to share template with all counsellors of a specialization"""
    sharing_counsellor_id: str = Field(..., description="Counsellor UUID who is sharing the template (must own the template)")
    template_id: str = Field(..., description="Template ID to share")
    specialization: str = Field(..., description="Specialization name (e.g., 'Cardiology')")
    new_owner_id: Optional[str] = Field(None, description="If provided, assigns ownership of a global template to this counsellor before sharing")


class ActivateTemplateRequest(BaseModel):
    """Request to activate a template for a counsellor"""
    counsellor_id: str = Field(..., description="Counsellor UUID")
    template_id: str = Field(..., description="Template ID to activate")
    consultation_type_id: str = Field(..., description="Consultation type UUID")


class RevokeAccessRequest(BaseModel):
    """Request to revoke counsellor's access to template"""
    counsellor_id: str = Field(..., description="Counsellor UUID")
    template_id: str = Field(..., description="Template ID")


class ActivateFromConsultationTypeRequest(BaseModel):
    """Request to create and activate template from consultation type"""
    counsellor_id: str = Field(..., description="Counsellor UUID")
    consultation_type_id: str = Field(..., description="Consultation type UUID")
    template_name: Optional[str] = Field(None, description="Custom template name (optional)")

    class Config:
        json_schema_extra = {
            "example": {
                "counsellor_id": "223e4567-e89b-12d3-a456-426614174000",
                "consultation_type_id": "323e4567-e89b-12d3-a456-426614174000",
                "template_name": "My Custom OP Template"
            }
        }


class CloneTemplateRequest(BaseModel):
    """Request to clone a template"""
    counsellor_id: str = Field(..., description="Counsellor UUID")
    source_template_id: str = Field(..., description="Template UUID to clone")
    template_name: Optional[str] = Field(None, description="Custom name for cloned template (optional)")

    class Config:
        json_schema_extra = {
            "example": {
                "counsellor_id": "223e4567-e89b-12d3-a456-426614174000",
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

    Returns individual counsellor shares, schools, and specializations
    that have access to this template.

    **Path Parameters:**
    - template_id: Template UUID

    **Returns:**
    - counsellors: List of individual counsellor shares
    - school_ids: List of school IDs with counsellors who have this template
    - specializations: List of specializations with counsellors who have this template
    - total_shares: Total number of individual counsellor shares
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
    _auth = Depends(verify_counsellor_access_from_body)
):
    """
    Share template with individual counsellors.

    **Request Body:**
    - sharing_counsellor_id: Counsellor UUID who is sharing (must own the template)
    - template_id: Template to share
    - counsellor_ids: List of counsellor UUIDs to share with
    - new_owner_id: (Optional) If sharing a global template, assign ownership to this counsellor first

    **Returns:**
    - success: Boolean
    - shared_count: Number of counsellors successfully shared with
    - failed: List of counsellors that failed (with reasons)
    - ownership_assigned: (If new_owner_id provided) Details of ownership assignment
    """
    try:
        template_uuid = uuid.UUID(request.template_id)
        counsellor_uuids = [uuid.UUID(d) for d in request.counsellor_ids]

        ownership_result = None

        # If new_owner_id provided, assign ownership first (converts global to counsellor-owned)
        if request.new_owner_id:
            new_owner_uuid = uuid.UUID(request.new_owner_id)
            ownership_result = assign_template_ownership(
                template_id=template_uuid,
                new_owner_id=new_owner_uuid,
            )

        result = bulk_share_template(
            template_id=template_uuid,
            counsellor_ids=counsellor_uuids,
        )

        response = {
            "success": True,
            "message": f"Template shared with {result['successful']} counsellor(s)",
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


@router.post("/share-school")
async def share_template_school(
    http_request: Request,
    request: ShareSchoolRequest,
    _auth = Depends(verify_counsellor_access_from_body)
):
    """
    Share template with all counsellors in a school.

    **Request Body:**
    - sharing_counsellor_id: Counsellor UUID who is sharing (must own the template)
    - template_id: Template to share
    - school_id: School UUID
    - new_owner_id: (Optional) If sharing a global template, assign ownership to this counsellor first

    **Returns:**
    - success: Boolean
    - shared_count: Number of counsellors in school who received access
    - ownership_assigned: (If new_owner_id provided) Details of ownership assignment
    """
    try:
        template_uuid = uuid.UUID(request.template_id)
        school_uuid = uuid.UUID(request.school_id)

        ownership_result = None

        # If new_owner_id provided, assign ownership first (converts global to counsellor-owned)
        if request.new_owner_id:
            new_owner_uuid = uuid.UUID(request.new_owner_id)
            ownership_result = assign_template_ownership(
                template_id=template_uuid,
                new_owner_id=new_owner_uuid,
            )

        result = share_template_with_school(
            template_id=template_uuid,
            school_id=school_uuid,
        )

        # Handle case when no counsellors found
        shared_count = result.get('successful', result.get('total_counsellors', 0))

        response = {
            "success": True,
            "message": f"Template shared with {shared_count} counsellors in school",
            "shared_count": shared_count,
            "school_id": request.school_id
        }

        if ownership_result:
            response["ownership_assigned"] = ownership_result

        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to share template with school")


@router.post("/share-specialization")
async def share_template_spec(
    http_request: Request,
    request: ShareSpecializationRequest,
    _auth = Depends(verify_counsellor_access_from_body)
):
    """
    Share template with all counsellors of a specialization.

    **Request Body:**
    - sharing_counsellor_id: Counsellor UUID who is sharing (must own the template)
    - template_id: Template to share
    - specialization: Specialization name (e.g., 'Cardiology', 'Psychiatry')
    - new_owner_id: (Optional) If sharing a global template, assign ownership to this counsellor first

    **Returns:**
    - success: Boolean
    - shared_count: Number of counsellors in specialization who received access
    - ownership_assigned: (If new_owner_id provided) Details of ownership assignment
    """
    try:
        template_uuid = uuid.UUID(request.template_id)

        ownership_result = None

        # If new_owner_id provided, assign ownership first (converts global to counsellor-owned)
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

        # Handle case when no counsellors found
        shared_count = result.get('successful', result.get('total_counsellors', 0))

        response = {
            "success": True,
            "message": f"Template shared with {shared_count} counsellors in {request.specialization}",
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
    _auth = Depends(verify_counsellor_access_from_body)
):
    """
    Activate a template for a counsellor (ensure counsellor_templates entry exists with is_active=True).

    **Request Body:**
    - counsellor_id: Counsellor UUID
    - template_id: Template to activate
    - consultation_type_id: Consultation type UUID

    **Returns:**
    - success: Boolean
    - activated_template_id: Template UUID
    """
    try:
        counsellor_uuid = uuid.UUID(request.counsellor_id)
        template_uuid = uuid.UUID(request.template_id)
        consultation_type_uuid = uuid.UUID(request.consultation_type_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        activate_template_for_counsellor(
            counsellor_id=counsellor_uuid,
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
    counsellor_id: str = Query(..., description="Counsellor UUID"),
    template_id: str = Query(..., description="Template ID to deactivate"),
    _auth = Depends(verify_counsellor_access)
):
    """
    Remove a template from a counsellor's list (soft-delete the counsellor-template link).

    **Query Parameters:**
    - counsellor_id: Counsellor UUID
    - template_id: Template to remove

    **Returns:**
    - success: Boolean
    """
    try:
        counsellor_uuid = uuid.UUID(counsellor_id)
        template_uuid = uuid.UUID(template_id)

        deactivate_template_for_counsellor(
            counsellor_id=counsellor_uuid,
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
    counsellor_id: str = Query(..., description="Counsellor UUID"),
    consultation_type_id: Optional[str] = Query(None, description="Filter by consultation type"),
    include_common: bool = Query(True, description="Include common templates"),
    active_only: bool = Query(False, description="Return only active templates"),
    _auth = Depends(verify_counsellor_access)
):
    """
    Get all templates accessible to a counsellor.

    **Returns templates that are:**
    - Owned by the counsellor (counsellor_id = counsellor)
    - Shared with the counsellor (via counsellor_templates junction table)
    - Common templates (counsellor_id = NULL) if include_common=True

    **Query Parameters:**
    - counsellor_id: Counsellor UUID (required)
    - consultation_type_id: Filter by consultation type (optional)
    - include_common: Include common templates (default: true)
    - active_only: Return only active templates (default: false)

    **Returns:**
    - success: Boolean
    - templates: List of template objects with access info
    - count: Total number of accessible templates
    - default_template_id: Default template UUID (counsellor default > school default > null)
    - default_template_code: Default template code (or null)
    """
    try:
        counsellor_uuid = uuid.UUID(counsellor_id)
        consultation_type_uuid = uuid.UUID(consultation_type_id) if consultation_type_id else None

        templates = get_counsellor_accessible_templates(
            counsellor_id=counsellor_uuid,
            consultation_type_id=consultation_type_uuid,
            include_common=include_common
        )

        # Filter to only active templates if requested
        if active_only:
            templates = [t for t in templates if t.get("is_active") is True]

        # Get the default template for this counsellor (counsellor default > school default > null)
        default_template = get_counsellor_default_template(counsellor_uuid)

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
    sharing_counsellor_id: str = Query(..., description="Counsellor UUID who is revoking (must own the template)"),
    counsellor_id: str = Query(..., description="Counsellor UUID whose access is being revoked"),
    template_id: str = Query(..., description="Template ID"),
    _auth = Depends(verify_sharing_counsellor_access)
):
    """
    Revoke a counsellor's access to a template.

    **Query Parameters:**
    - sharing_counsellor_id: Counsellor UUID who is revoking (must own the template)
    - counsellor_id: Counsellor UUID whose access is being revoked
    - template_id: Template ID (UUID)

    **Note:**
    - Cannot revoke access to owned templates (counsellor_id matches template.counsellor_id)
    - Cannot revoke access to common templates (counsellor_id = NULL)
    - Only revokes shared access via counsellor_templates junction table

    **Returns:**
    - success: Boolean
    - revoked: Boolean - Whether an entry was actually deleted
    - details: Additional details about the revoke operation
    """
    try:
        counsellor_uuid = uuid.UUID(counsellor_id)
        template_uuid = uuid.UUID(template_id)

        result = revoke_template_access(
            counsellor_id=counsellor_uuid,
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
    _auth = Depends(verify_counsellor_access_from_body)
):
    """
    Create and activate a new counsellor-owned template from a consultation type.

    **Workflow:**
    1. Verify counsellor has visibility to consultation type
    2. Create new template owned by counsellor
    3. Clone all segments from consultation_type_segments junction
    4. Auto-activate for counsellor

    **Request Body:**
    - counsellor_id: Counsellor UUID
    - consultation_type_id: Consultation type UUID
    - template_name: Optional custom name

    **Returns:**
    - success: Boolean
    - template: Created template object
    - segment_count: Number of segments cloned
    - is_activated: Boolean

    **Errors:**
    - 403: Counsellor doesn't have visibility to consultation type
    - 404: Consultation type not found
    """
    try:
        counsellor_uuid = uuid.UUID(request.counsellor_id)
        consultation_type_uuid = uuid.UUID(request.consultation_type_id)

        template = activate_from_consultation_type(
            counsellor_id=counsellor_uuid,
            consultation_type_id=consultation_type_uuid,
            template_name=request.template_name
        )

        return {
            "success": True,
            "template": strip_internal_template_fields(template),
            "message": f"Template created and activated for counsellor {request.counsellor_id}"
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
    _auth = Depends(verify_counsellor_access_from_body)
):
    """
    Clone a template to create a counsellor-owned copy.

    **Counsellor can clone:**
    - Shared templates
    - Global templates (counsellor_id = NULL)
    - Their own templates (for versioning)

    **Workflow:**
    1. Verify counsellor has access to source template
    2. Create new template owned by counsellor
    3. Copy all segments from template_segments junction
    4. Auto-activate for counsellor

    **Request Body:**
    - counsellor_id: Counsellor UUID
    - source_template_id: Template UUID to clone
    - template_name: Optional custom name

    **Returns:**
    - success: Boolean
    - template: Created template object
    - source_template_id: Original template UUID
    - segment_count: Number of segments cloned
    - is_activated: Boolean

    **Errors:**
    - 403: Counsellor doesn't have access to source template
    - 404: Source template not found
    """
    try:
        counsellor_uuid = uuid.UUID(request.counsellor_id)
        source_template_uuid = uuid.UUID(request.source_template_id)

        template = clone_template(
            counsellor_id=counsellor_uuid,
            source_template_id=source_template_uuid,
            template_name=request.template_name
        )

        return {
            "success": True,
            "template": strip_internal_template_fields(template),
            "message": f"Template cloned successfully for counsellor {request.counsellor_id}"
        }

    except PermissionError as e:
        raise HTTPException(status_code=403, detail="Access denied")
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Not found")
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to clone template")


@router.get("/dashboard/{counsellor_id}")
async def get_dashboard(
    request: Request,
    counsellor_id: str,
    _auth = Depends(verify_counsellor_access)
):
    """
    Get comprehensive dashboard data for a counsellor.

    **Returns two types of items:**
    1. **Visible Consultation Types** - Based on visibility settings
       - Can activate to create new owned template
       - Badge: "Activate"

    2. **Accessible Templates** - Owned, shared, and global templates
       - Owned templates: Badge "Owned"
       - Global templates: Badge "Global"
       - Shared templates: Badge "Shared"

    **Query Parameters:**
    - counsellor_id: Counsellor UUID (path parameter)

    **Returns:**
    - success: Boolean
    - consultation_types: List of visible consultation types with action badges
    - templates: List of accessible templates with access info and badges
    - consultation_types_count: Count
    - templates_count: Count
    """
    try:
        counsellor_uuid = uuid.UUID(counsellor_id)

        dashboard_data = get_counsellor_dashboard_data(counsellor_id=counsellor_uuid)

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
# Counsellor Template Segment Management APIs
# ============================================================================

class AddSegmentsFromTypeRequest(BaseModel):
    """Request model for adding segments from consultation type to template"""
    segment_codes: Optional[List[str]] = Field(default=None, description="Specific segment codes to add")
    add_all_missing: bool = Field(default=False, description="Add all segments not yet in template")
    default_category: str = Field(default="excluded", description="Category for new segments")


@router.get("/{template_id}/segments/available")
async def get_available_segments_for_counsellor_template(
    request: Request,
    template_id: str,
    counsellor_id: str = Query(..., description="Counsellor ID requesting the segments"),
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Get segments available to add to a counsellor's template.

    **Use Case:** Before adding segments to a counsellor-owned template, show which segments
    are available. Validates counsellor has access to the template.

    **Path Parameters:**
    - template_id: Template UUID

    **Query Parameters:**
    - counsellor_id: Counsellor UUID (validates access)

    **Returns:**
    - available_segments: List of segments that can be added
    - consultation_type_code: The template's consultation type
    - count: Number of available segments

    **Errors:**
    - 403: Counsellor doesn't have access to this template
    - 404: Template not found
    """
    try:
        from services.supabase_service import (
            get_available_segments_for_template,
            get_template_by_id,
            check_counsellor_template_access
        )

        template_uuid = uuid.UUID(template_id)
        counsellor_uuid = uuid.UUID(counsellor_id)

        # Check if template exists
        template = get_template_by_id(template_uuid)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Check if counsellor owns or has access to template
        if template.get("counsellor_id"):
            template_counsellor_id = uuid.UUID(template["counsellor_id"]) if isinstance(template["counsellor_id"], str) else template["counsellor_id"]
            if template_counsellor_id != counsellor_uuid:
                # Not the owner, check if shared
                has_access = check_counsellor_template_access(counsellor_uuid, template_uuid)
                if not has_access:
                    raise HTTPException(status_code=403, detail="Counsellor doesn't have access to this template")

        result = get_available_segments_for_template(template_uuid)
        return result

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get available segments")


@router.post("/{template_id}/segments/add-from-type")
async def add_segments_to_counsellor_template(
    http_request: Request,
    template_id: str,
    request: AddSegmentsFromTypeRequest,
    counsellor_id: str = Query(..., description="Counsellor ID adding the segments"),
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Add segments from consultation type to counsellor's template.

    **Use Case:** Allow counsellors to add new segments to their templates without
    using "Inherit from Type" (which replaces all segments).

    **Path Parameters:**
    - template_id: Template UUID

    **Query Parameters:**
    - counsellor_id: Counsellor UUID (validates access)

    **Request Body:**
    - segment_codes: List of specific segment codes to add (optional)
    - add_all_missing: If true, add ALL segments not yet in template
    - default_category: Category for new segments (default: 'excluded')

    **Example:**
    ```bash
    POST /api/v1/counsellor-templates/uuid/segments/add-from-type?counsellor_id=uuid
    {
      "segment_codes": ["NEW_SEGMENT"],
      "default_category": "excluded"
    }
    ```

    **Returns:**
    - segments_added: List of added segments
    - count: Number of segments added

    **Errors:**
    - 403: Counsellor doesn't have access to this template
    - 404: Template not found
    """
    try:
        from services.supabase_service import (
            add_segments_to_template_from_type,
            get_template_by_id,
            check_counsellor_template_access
        )

        template_uuid = uuid.UUID(template_id)
        counsellor_uuid = uuid.UUID(counsellor_id)

        # Check if template exists
        template = get_template_by_id(template_uuid)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Check if counsellor owns or has edit access to template
        if template.get("counsellor_id"):
            template_counsellor_id = uuid.UUID(template["counsellor_id"]) if isinstance(template["counsellor_id"], str) else template["counsellor_id"]
            if template_counsellor_id != counsellor_uuid:
                raise HTTPException(status_code=403, detail="Only template owner can add segments")
        else:
            # Global template - counsellors can't modify
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

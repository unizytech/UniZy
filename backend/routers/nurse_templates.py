"""
Nurse Templates Router

Handles template sharing and activation operations for nurses:
- Share templates with individual nurses
- Bulk share templates
- Activate/deactivate templates for nurses
- Get accessible templates for nurses
- Revoke template access
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel, Field
import uuid

from dependencies.auth import require_admin, get_current_client
from models.auth_models import ClientContext

from services.nurse_templates_service import (
    share_template_with_nurse,
    bulk_share_template_with_nurses,
    activate_template_for_nurse,
    deactivate_template_for_nurse,
    get_nurse_accessible_templates,
    get_nurse_active_template,
    revoke_nurse_template_access,
    validate_nurse_template_access,
    get_template_nurse_shares
)


router = APIRouter(prefix="/api/v1/nurse-templates", tags=["Nurse Templates"])


# =============================================================================
# Request/Response Models
# =============================================================================

class ShareTemplateWithNurseRequest(BaseModel):
    """Request to share template with individual nurses"""
    template_id: str = Field(..., description="Template ID to share")
    template_code: str = Field(..., description="Template code (for readability)")
    nurse_ids: List[str] = Field(..., min_length=1, description="List of nurse UUIDs")

    class Config:
        json_schema_extra = {
            "example": {
                "template_id": "123e4567-e89b-12d3-a456-426614174000",
                "template_code": "PSYCHIATRY_OP",
                "nurse_ids": ["223e4567-e89b-12d3-a456-426614174000"]
            }
        }


class ActivateNurseTemplateRequest(BaseModel):
    """Request to activate a template for a nurse"""
    nurse_id: str = Field(..., description="Nurse UUID")
    template_id: str = Field(..., description="Template ID to activate")


class RevokeNurseAccessRequest(BaseModel):
    """Request to revoke nurse's access to template"""
    nurse_id: str = Field(..., description="Nurse UUID")
    template_id: str = Field(..., description="Template ID")


# =============================================================================
# Template Sharing Endpoints
# =============================================================================

@router.get("/template-shares/{template_id}")
async def get_nurse_shares(
    template_id: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get all nurses who have access to a template.

    **Path Parameters:**
    - template_id: Template UUID

    **Returns:**
    - nurses: List of nurse shares
    - total_shares: Total number of nurse shares
    """
    try:
        template_uuid = uuid.UUID(template_id)
        shares = get_template_nurse_shares(template_uuid)

        return {
            "success": True,
            "shares": shares.get("nurses", [])  # Return just the nurses array
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get template shares")


@router.post("/share")
async def share_template_with_nurses(
    request: ShareTemplateWithNurseRequest,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Share template with individual nurses.

    **Request Body:**
    - template_id: Template to share
    - template_code: Template code (stored for readability)
    - nurse_ids: List of nurse UUIDs to share with

    **Returns:**
    - success: Boolean
    - shared_count: Number of nurses successfully shared with
    - failed: List of nurses that failed (with reasons)
    """
    try:
        template_uuid = uuid.UUID(request.template_id)
        nurse_uuids = [uuid.UUID(n) for n in request.nurse_ids]

        result = bulk_share_template_with_nurses(
            template_id=template_uuid,
            template_code=request.template_code,
            nurse_ids=nurse_uuids,
        )

        return {
            "success": True,
            "message": f"Template shared with {result['successful']} nurse(s)",
            "shared_count": result['successful'],
            "failed_count": result['failed'],
            "failures": result.get('failed_records', [])
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to share template")


# =============================================================================
# Template Activation Endpoints
# =============================================================================

@router.post("/activate")
async def activate_nurse_template(
    request: ActivateNurseTemplateRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Activate (link) a template for a nurse.

    **Behavior:**
    - Sets is_active=True on the nurse_templates entry
    - Multiple templates can be active simultaneously

    **Request Body:**
    - nurse_id: Nurse UUID
    - template_id: Template to activate

    **Returns:**
    - success: Boolean
    - is_active: Boolean
    - message: Status message
    """
    try:
        nurse_uuid = uuid.UUID(request.nurse_id)
        template_uuid = uuid.UUID(request.template_id)

        result = activate_template_for_nurse(
            nurse_id=nurse_uuid,
            template_id=template_uuid
        )

        return {
            "success": True,
            "is_active": True,
            "message": "Template activated successfully",
            "activated_template_id": request.template_id
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to activate template")


class DeactivateNurseTemplateRequest(BaseModel):
    """Request to deactivate a template for a nurse"""
    nurse_id: str = Field(..., description="Nurse UUID")
    template_id: str = Field(..., description="Template ID to deactivate")


@router.post("/deactivate")
async def deactivate_nurse_template(
    request: DeactivateNurseTemplateRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Deactivate a template for a nurse.

    **Request Body:**
    - nurse_id: Nurse UUID
    - template_id: Template to deactivate

    **Returns:**
    - success: Boolean
    - is_active: Boolean (false)
    """
    try:
        nurse_uuid = uuid.UUID(request.nurse_id)
        template_uuid = uuid.UUID(request.template_id)

        deactivate_template_for_nurse(
            nurse_id=nurse_uuid,
            template_id=template_uuid
        )

        return {
            "success": True,
            "is_active": False,
            "message": "Template deactivated successfully"
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
    nurse_id: str = Query(..., description="Nurse UUID"),
    active_only: bool = Query(False, description="Return only active templates"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Get all templates accessible to a nurse.

    **Query Parameters:**
    - nurse_id: Nurse UUID (required)
    - active_only: Return only active templates (default: false)

    **Returns:**
    - success: Boolean
    - templates: List of template objects with access info
    - count: Total number of accessible templates
    """
    try:
        nurse_uuid = uuid.UUID(nurse_id)

        templates = get_nurse_accessible_templates(nurse_id=nurse_uuid)

        # Filter to only active templates if requested
        if active_only:
            templates = [t for t in templates if t.get("is_active") is True]

        return {
            "success": True,
            "templates": templates,
            "count": len(templates)
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get accessible templates")


@router.get("/active")
async def get_active_template(
    nurse_id: str = Query(..., description="Nurse UUID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Get the currently active template for a nurse.

    **Query Parameters:**
    - nurse_id: Nurse UUID (required)

    **Returns:**
    - success: Boolean
    - template: Active template or null if none active
    """
    try:
        nurse_uuid = uuid.UUID(nurse_id)

        template = get_nurse_active_template(nurse_id=nurse_uuid)

        return {
            "success": True,
            "template": template
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get active template")


@router.delete("/revoke")
async def revoke_nurse_access(
    nurse_id: str = Query(..., description="Nurse UUID whose access is being revoked"),
    template_id: str = Query(..., description="Template ID"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Revoke a nurse's access to a template.

    **Query Parameters:**
    - nurse_id: Nurse UUID whose access is being revoked
    - template_id: Template ID (UUID)

    **Returns:**
    - success: Boolean
    - revoked: Boolean - Whether an entry was actually deleted
    - details: Additional details about the revoke operation
    """
    try:
        nurse_uuid = uuid.UUID(nurse_id)
        template_uuid = uuid.UUID(template_id)

        result = revoke_nurse_template_access(
            nurse_id=nurse_uuid,
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
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to revoke template access")


# =============================================================================
# Validation Endpoint
# =============================================================================

@router.get("/validate-access")
async def validate_template_access(
    nurse_id: str = Query(..., description="Nurse UUID"),
    template_id: str = Query(..., description="Template ID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Check if a nurse has access to a template.

    **Query Parameters:**
    - nurse_id: Nurse UUID
    - template_id: Template ID

    **Returns:**
    - success: Boolean
    - has_access: Boolean - Whether nurse can use this template
    """
    try:
        has_access = validate_nurse_template_access(
            nurse_id=nurse_id,
            template_id=template_id
        )

        return {
            "success": True,
            "has_access": has_access
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to validate access")

"""
Assistant Templates Router

Handles template sharing and activation operations for assistants:
- Share templates with individual assistants
- Bulk share templates
- Activate/deactivate templates for assistants
- Get accessible templates for assistants
- Revoke template access
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel, Field
import uuid

from dependencies.auth import require_admin, get_current_client
from models.auth_models import ClientContext

from services.assistant_templates_service import (
    share_template_with_assistant,
    bulk_share_template_with_assistants,
    activate_template_for_assistant,
    deactivate_template_for_assistant,
    get_assistant_accessible_templates,
    get_assistant_active_template,
    revoke_assistant_template_access,
    validate_assistant_template_access,
    get_template_assistant_shares
)


router = APIRouter(prefix="/api/v1/assistant-templates", tags=["Assistant Templates"])


# =============================================================================
# Request/Response Models
# =============================================================================

class ShareTemplateWithAssistantRequest(BaseModel):
    """Request to share template with individual assistants"""
    template_id: str = Field(..., description="Template ID to share")
    template_code: str = Field(..., description="Template code (for readability)")
    assistant_ids: List[str] = Field(..., min_length=1, description="List of assistant UUIDs")

    class Config:
        json_schema_extra = {
            "example": {
                "template_id": "123e4567-e89b-12d3-a456-426614174000",
                "template_code": "PSYCHIATRY_OP",
                "assistant_ids": ["223e4567-e89b-12d3-a456-426614174000"]
            }
        }


class ActivateAssistantTemplateRequest(BaseModel):
    """Request to activate a template for an assistant"""
    assistant_id: str = Field(..., description="Assistant UUID")
    template_id: str = Field(..., description="Template ID to activate")


class RevokeAssistantAccessRequest(BaseModel):
    """Request to revoke assistant's access to template"""
    assistant_id: str = Field(..., description="Assistant UUID")
    template_id: str = Field(..., description="Template ID")


# =============================================================================
# Template Sharing Endpoints
# =============================================================================

@router.get("/template-shares/{template_id}")
async def get_assistant_shares(
    template_id: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get all assistants who have access to a template.

    **Path Parameters:**
    - template_id: Template UUID

    **Returns:**
    - assistants: List of assistant shares
    - total_shares: Total number of assistant shares
    """
    try:
        template_uuid = uuid.UUID(template_id)
        shares = get_template_assistant_shares(template_uuid)

        return {
            "success": True,
            "shares": shares.get("assistants", [])  # Return just the assistants array
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get template shares")


@router.post("/share")
async def share_template_with_assistants(
    request: ShareTemplateWithAssistantRequest,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Share template with individual assistants.

    **Request Body:**
    - template_id: Template to share
    - template_code: Template code (stored for readability)
    - assistant_ids: List of assistant UUIDs to share with

    **Returns:**
    - success: Boolean
    - shared_count: Number of assistants successfully shared with
    - failed: List of assistants that failed (with reasons)
    """
    try:
        template_uuid = uuid.UUID(request.template_id)
        assistant_uuids = [uuid.UUID(n) for n in request.assistant_ids]

        result = bulk_share_template_with_assistants(
            template_id=template_uuid,
            template_code=request.template_code,
            assistant_ids=assistant_uuids,
        )

        return {
            "success": True,
            "message": f"Template shared with {result['successful']} assistant(s)",
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
async def activate_assistant_template(
    request: ActivateAssistantTemplateRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Activate (link) a template for an assistant.

    **Behavior:**
    - Sets is_active=True on the assistant_templates entry
    - Multiple templates can be active simultaneously

    **Request Body:**
    - assistant_id: Assistant UUID
    - template_id: Template to activate

    **Returns:**
    - success: Boolean
    - is_active: Boolean
    - message: Status message
    """
    try:
        assistant_uuid = uuid.UUID(request.assistant_id)
        template_uuid = uuid.UUID(request.template_id)

        result = activate_template_for_assistant(
            assistant_id=assistant_uuid,
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


class DeactivateAssistantTemplateRequest(BaseModel):
    """Request to deactivate a template for an assistant"""
    assistant_id: str = Field(..., description="Assistant UUID")
    template_id: str = Field(..., description="Template ID to deactivate")


@router.post("/deactivate")
async def deactivate_assistant_template(
    request: DeactivateAssistantTemplateRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Deactivate a template for an assistant.

    **Request Body:**
    - assistant_id: Assistant UUID
    - template_id: Template to deactivate

    **Returns:**
    - success: Boolean
    - is_active: Boolean (false)
    """
    try:
        assistant_uuid = uuid.UUID(request.assistant_id)
        template_uuid = uuid.UUID(request.template_id)

        deactivate_template_for_assistant(
            assistant_id=assistant_uuid,
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
    assistant_id: str = Query(..., description="Assistant UUID"),
    active_only: bool = Query(False, description="Return only active templates"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Get all templates accessible to an assistant.

    **Query Parameters:**
    - assistant_id: Assistant UUID (required)
    - active_only: Return only active templates (default: false)

    **Returns:**
    - success: Boolean
    - templates: List of template objects with access info
    - count: Total number of accessible templates
    """
    try:
        assistant_uuid = uuid.UUID(assistant_id)

        templates = get_assistant_accessible_templates(assistant_id=assistant_uuid)

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
    assistant_id: str = Query(..., description="Assistant UUID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Get the currently active template for an assistant.

    **Query Parameters:**
    - assistant_id: Assistant UUID (required)

    **Returns:**
    - success: Boolean
    - template: Active template or null if none active
    """
    try:
        assistant_uuid = uuid.UUID(assistant_id)

        template = get_assistant_active_template(assistant_id=assistant_uuid)

        return {
            "success": True,
            "template": template
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get active template")


@router.delete("/revoke")
async def revoke_assistant_access(
    assistant_id: str = Query(..., description="Assistant UUID whose access is being revoked"),
    template_id: str = Query(..., description="Template ID"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Revoke an assistant's access to a template.

    **Query Parameters:**
    - assistant_id: Assistant UUID whose access is being revoked
    - template_id: Template ID (UUID)

    **Returns:**
    - success: Boolean
    - revoked: Boolean - Whether an entry was actually deleted
    - details: Additional details about the revoke operation
    """
    try:
        assistant_uuid = uuid.UUID(assistant_id)
        template_uuid = uuid.UUID(template_id)

        result = revoke_assistant_template_access(
            assistant_id=assistant_uuid,
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
    assistant_id: str = Query(..., description="Assistant UUID"),
    template_id: str = Query(..., description="Template ID"),
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Check if an assistant has access to a template.

    **Query Parameters:**
    - assistant_id: Assistant UUID
    - template_id: Template ID

    **Returns:**
    - success: Boolean
    - has_access: Boolean - Whether assistant can use this template
    """
    try:
        has_access = validate_assistant_template_access(
            assistant_id=assistant_id,
            template_id=template_id
        )

        return {
            "success": True,
            "has_access": has_access
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to validate access")

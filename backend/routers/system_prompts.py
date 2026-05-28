"""
System Prompts Router - Admin API for Dynamic System Prompt Management

Endpoints for managing:
- Prompt components (CRUD)
- Prompt configurations (CRUD)
- Component assignments to configurations
- Configuration activation for consultation types
- Preview and metrics
"""

import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from models.auth_models import ClientContext
from dependencies.auth import require_admin

from services.system_prompt_service import (
    # Retrieval
    get_system_prompt_with_fallback,
    preview_assembled_prompt,
    assemble_system_prompt,
    # Components CRUD
    create_prompt_component,
    update_prompt_component,
    delete_prompt_component,
    list_prompt_components,
    get_prompt_component,
    clone_prompt_component,
    list_component_types,
    # Configurations CRUD
    create_prompt_configuration,
    update_prompt_configuration,
    delete_prompt_configuration,
    list_prompt_configurations,
    get_prompt_configuration,
    clone_prompt_configuration,
    # Config <-> Components junction
    assign_component_to_config,
    remove_component_from_config,
    reorder_config_components,
    get_config_components,
    toggle_component_inclusion,
    # Consultation Type <-> Config junction
    assign_config_to_consultation_type,
    remove_config_from_consultation_type,
    get_configs_for_consultation_type,
    get_active_config_for_consultation_type,
    toggle_assignment_active,
    # Activation
    activate_config_for_consultation_type,
    deactivate_config_for_consultation_type,
    # Metrics
    get_consultation_type_prompt_status,
    get_all_consultation_type_assignments,
)

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/system-prompts", tags=["System Prompts"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ComponentCreate(BaseModel):
    component_code: str = Field(..., description="Unique code (e.g., 'ROLE_MEDICAL_AI')")
    component_name: str = Field(..., description="Display name")
    component_type: str = Field(..., description="Type (role, capabilities, critical_guidelines, etc.)")
    content_text: str = Field(..., description="The actual prompt text")
    content_version: str = Field(default="1.0.0", description="Version string")
    description: Optional[str] = Field(default=None, description="Optional description")
    is_base_component: bool = Field(default=False, description="Whether this is a template/base component")


class ComponentUpdate(BaseModel):
    component_name: Optional[str] = None
    component_type: Optional[str] = None
    content_text: Optional[str] = None
    description: Optional[str] = None
    is_base_component: Optional[bool] = None
    is_active: Optional[bool] = None  # For soft delete/reactivate


class ComponentClone(BaseModel):
    source_component_id: str = Field(..., description="Source component UUID to clone")
    new_component_code: str = Field(..., description="New code for cloned component")
    new_version: str = Field(default="1.0.0", description="Version for cloned component")


class ConfigurationCreate(BaseModel):
    config_code: str = Field(..., description="Unique code (e.g., 'OP_STANDARD_V2')")
    config_name: str = Field(..., description="Display name")
    # Accept both 'version' and 'config_version' for flexibility
    config_version: Optional[str] = Field(default=None, description="Version string (backend field)")
    version: Optional[str] = Field(default=None, description="Version string (frontend field)")
    # Accept both 'description' and 'config_description' for flexibility
    description: Optional[str] = Field(default=None, description="Optional description (backend field)")
    config_description: Optional[str] = Field(default=None, description="Optional description (frontend field)")
    is_draft: bool = Field(default=True, description="Whether this is a draft")
    is_active: bool = Field(default=True, description="Whether this is active")
    inherits_from_id: Optional[str] = Field(default=None, description="Parent config UUID to inherit from")
    # Component IDs to assign to this configuration
    component_ids: Optional[List[str]] = Field(default=None, description="List of component UUIDs to assign")


class ConfigurationUpdate(BaseModel):
    config_name: Optional[str] = None
    description: Optional[str] = None
    config_description: Optional[str] = None  # Frontend field alias
    is_draft: Optional[bool] = None
    is_active: Optional[bool] = None
    component_ids: Optional[List[str]] = None  # Component IDs to update (replaces existing)


class ConfigurationClone(BaseModel):
    source_config_id: str = Field(..., description="Source config UUID to clone")
    new_config_code: str = Field(..., description="New code for cloned config")
    new_version: str = Field(default="1.0.0", description="Version for cloned config")


class ComponentAssignment(BaseModel):
    component_id: str = Field(..., description="Component UUID")
    display_order: int = Field(..., description="Order in prompt assembly")
    is_included: bool = Field(default=True, description="Whether to include in assembly")


class ComponentReorder(BaseModel):
    component_id: str = Field(..., description="Component UUID")
    display_order: int = Field(..., description="New display order")


class ConsultationTypeAssignment(BaseModel):
    config_id: str = Field(..., description="Configuration UUID")


class ActivationRequest(BaseModel):
    config_id: str = Field(..., description="Configuration UUID to activate")


# ============================================================================
# Component Endpoints
# ============================================================================

@router.get("/components")
async def get_components(
    component_type: Optional[str] = None,
    client: ClientContext = Depends(require_admin)
):
    """
    List all prompt components, optionally filtered by type.
    """
    components = list_prompt_components(component_type)
    return {"components": components, "count": len(components)}


@router.get("/components/types")
async def get_component_types(
    client: ClientContext = Depends(require_admin)
):
    """
    Get all unique component types in use.
    """
    types = list_component_types()
    return {"types": types}


@router.get("/components/{component_id}")
async def get_component(
    component_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Get a single prompt component by ID.
    """
    try:
        component = get_prompt_component(uuid.UUID(component_id))
        if not component:
            raise HTTPException(status_code=404, detail="Component not found")
        return component
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/components")
async def create_component(
    data: ComponentCreate,
    client: ClientContext = Depends(require_admin)
):
    """
    Create a new prompt component.
    """
    try:
        component = create_prompt_component(
            component_code=data.component_code,
            component_name=data.component_name,
            component_type=data.component_type,
            content_text=data.content_text,
            content_version=data.content_version,
            description=data.description,
            is_base_component=data.is_base_component
        )
        return {"message": "Component created", "component": component}
    except Exception as e:
        logger.error(f"Failed to create component: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.put("/components/{component_id}")
async def update_component(
    component_id: str,
    data: ComponentUpdate,
    client: ClientContext = Depends(require_admin)
):
    """
    Update a prompt component.
    """
    try:
        component = update_prompt_component(
            component_id=uuid.UUID(component_id),
            component_name=data.component_name,
            component_type=data.component_type,
            content_text=data.content_text,
            description=data.description,
            is_base_component=data.is_base_component,
            is_active=data.is_active
        )
        return {"message": "Component updated", "component": component}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to update component: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.post("/components/{component_id}/toggle-active")
async def toggle_component_active(
    component_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Toggle component's is_active status (activate/deactivate).
    """
    try:
        # Get current status
        from services.system_prompt_service import supabase
        current = supabase.table('system_prompt_components').select('is_active').eq('id', component_id).single().execute()
        if not current.data:
            raise HTTPException(status_code=404, detail="Component not found")

        # Handle NULL as True (active), then toggle
        current_status = current.data.get('is_active')
        if current_status is None:
            current_status = True  # Treat NULL as active
        new_status = not current_status
        component = update_prompt_component(
            component_id=uuid.UUID(component_id),
            is_active=new_status
        )
        return {
            "message": f"Component {'activated' if new_status else 'deactivated'}",
            "component": component,
            "is_active": new_status
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to toggle component: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.delete("/components/{component_id}")
async def remove_component(
    component_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Delete a prompt component.

    Note: Will fail if component is in use by any configuration.
    """
    try:
        success = delete_prompt_component(uuid.UUID(component_id))
        if not success:
            raise HTTPException(status_code=400, detail="Failed to delete component (may be in use)")
        return {"message": "Component deleted"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/components/clone")
async def clone_component(
    data: ComponentClone,
    client: ClientContext = Depends(require_admin)
):
    """
    Clone an existing component with a new code/version.
    """
    try:
        component = clone_prompt_component(
            source_component_id=uuid.UUID(data.source_component_id),
            new_component_code=data.new_component_code,
            new_version=data.new_version
        )
        return {"message": "Component cloned", "component": component}
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"Failed to clone component: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


# ============================================================================
# Configuration Endpoints
# ============================================================================

@router.get("/configurations")
async def get_configurations(
    client: ClientContext = Depends(require_admin)
):
    """
    List all prompt configurations with component counts.
    """
    configs = list_prompt_configurations()
    return {"configurations": configs, "count": len(configs)}


@router.get("/configurations/{config_id}")
async def get_configuration(
    config_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Get a single prompt configuration by ID.
    """
    try:
        config = get_prompt_configuration(uuid.UUID(config_id))
        if not config:
            raise HTTPException(status_code=404, detail="Configuration not found")
        return config
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/configurations")
async def create_configuration(
    data: ConfigurationCreate,
    client: ClientContext = Depends(require_admin)
):
    """
    Create a new prompt configuration.

    Accepts component_ids to assign components during creation.
    """
    try:
        inherits_from = uuid.UUID(data.inherits_from_id) if data.inherits_from_id else None

        # Accept version from either field (frontend uses 'version', backend uses 'config_version')
        version = data.config_version or data.version or "1.0.0"

        # Accept description from either field
        description = data.description or data.config_description

        config = create_prompt_configuration(
            config_code=data.config_code,
            config_name=data.config_name,
            config_version=version,
            description=description,
            is_draft=data.is_draft,
            inherits_from_id=inherits_from
        )

        # Assign components if provided
        if data.component_ids and config.get('id'):
            config_id = uuid.UUID(config['id'])
            for order, component_id_str in enumerate(data.component_ids):
                try:
                    assign_component_to_config(
                        config_id=config_id,
                        component_id=uuid.UUID(component_id_str),
                        display_order=order,
                        is_included=True
                    )
                except Exception as comp_err:
                    logger.warning(f"Failed to assign component {component_id_str}: {comp_err}")

            logger.info(f"[SystemPrompt] Assigned {len(data.component_ids)} components to config {config['id']}")

        return {"message": "Configuration created", "configuration": config}
    except Exception as e:
        logger.error(f"Failed to create configuration: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.put("/configurations/{config_id}")
async def update_configuration(
    config_id: str,
    data: ConfigurationUpdate,
    client: ClientContext = Depends(require_admin)
):
    """
    Update a prompt configuration.

    If component_ids is provided, replaces all existing component assignments.
    """
    try:
        config_uuid = uuid.UUID(config_id)

        # Accept description from either field
        description = data.description or data.config_description

        config = update_prompt_configuration(
            config_id=config_uuid,
            config_name=data.config_name,
            description=description,
            is_draft=data.is_draft,
            is_active=data.is_active
        )

        # Update component assignments if provided
        if data.component_ids is not None:
            # Remove all existing assignments
            existing = get_config_components(config_uuid)
            for comp in existing:
                remove_component_from_config(config_uuid, uuid.UUID(comp['component_id']))

            # Add new assignments
            for order, component_id_str in enumerate(data.component_ids):
                try:
                    assign_component_to_config(
                        config_id=config_uuid,
                        component_id=uuid.UUID(component_id_str),
                        display_order=order,
                        is_included=True
                    )
                except Exception as comp_err:
                    logger.warning(f"Failed to assign component {component_id_str}: {comp_err}")

            logger.info(f"[SystemPrompt] Updated config {config_id} with {len(data.component_ids)} components")

        return {"message": "Configuration updated", "configuration": config}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to update configuration: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.delete("/configurations/{config_id}")
async def remove_configuration(
    config_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Delete a prompt configuration.

    Note: Will fail if configuration is assigned to any consultation type.
    """
    try:
        success = delete_prompt_configuration(uuid.UUID(config_id))
        if not success:
            raise HTTPException(status_code=400, detail="Failed to delete configuration (may be in use)")
        return {"message": "Configuration deleted"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/configurations/clone")
async def clone_configuration(
    data: ConfigurationClone,
    client: ClientContext = Depends(require_admin)
):
    """
    Clone a configuration with all its component assignments.
    """
    try:
        config = clone_prompt_configuration(
            source_config_id=uuid.UUID(data.source_config_id),
            new_config_code=data.new_config_code,
            new_version=data.new_version
        )
        return {"message": "Configuration cloned", "configuration": config}
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"Failed to clone configuration: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.get("/configurations/{config_id}/preview")
async def preview_configuration(
    config_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Preview the assembled prompt for a configuration.

    Does NOT save to database - useful for preview before activation.
    """
    try:
        prompt = preview_assembled_prompt(uuid.UUID(config_id))
        return {
            "config_id": config_id,
            "assembled_prompt": prompt,
            "character_count": len(prompt),
            "estimated_tokens": len(prompt) // 4
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/configurations/{config_id}/assemble")
async def assemble_configuration(
    config_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Assemble a prompt from components and save to database.

    This materializes the prompt by joining all assigned components.
    """
    try:
        prompt = assemble_system_prompt(uuid.UUID(config_id))
        if not prompt:
            raise HTTPException(status_code=400, detail="No components assigned or assembly failed")
        return {
            "message": "Configuration assembled",
            "config_id": config_id,
            "assembled_prompt": prompt,
            "character_count": len(prompt),
            "estimated_tokens": len(prompt) // 4
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        logger.error(f"Failed to assemble configuration: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


# ============================================================================
# Config <-> Component Junction Endpoints
# ============================================================================

@router.get("/configurations/{config_id}/components")
async def get_config_component_list(
    config_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Get all components assigned to a configuration.
    """
    try:
        components = get_config_components(uuid.UUID(config_id))
        return {"components": components, "count": len(components)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/configurations/{config_id}/components")
async def assign_component(
    config_id: str,
    data: ComponentAssignment,
    client: ClientContext = Depends(require_admin)
):
    """
    Assign a component to a configuration.

    Triggers auto-reassembly of the prompt.
    """
    try:
        assignment = assign_component_to_config(
            config_id=uuid.UUID(config_id),
            component_id=uuid.UUID(data.component_id),
            display_order=data.display_order,
            is_included=data.is_included
        )
        return {"message": "Component assigned", "assignment": assignment}
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"Failed to assign component: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.delete("/configurations/{config_id}/components/{component_id}")
async def unassign_component(
    config_id: str,
    component_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Remove a component from a configuration.

    Triggers auto-reassembly of the prompt.
    """
    try:
        success = remove_component_from_config(
            config_id=uuid.UUID(config_id),
            component_id=uuid.UUID(component_id)
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to remove component")
        return {"message": "Component removed"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.put("/configurations/{config_id}/components/reorder")
async def reorder_components(
    config_id: str,
    orders: List[ComponentReorder],
    client: ClientContext = Depends(require_admin)
):
    """
    Reorder components in a configuration.

    Triggers auto-reassembly of the prompt.
    """
    try:
        component_orders = [
            {"component_id": uuid.UUID(o.component_id), "display_order": o.display_order}
            for o in orders
        ]
        success = reorder_config_components(
            config_id=uuid.UUID(config_id),
            component_orders=component_orders
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to reorder components")
        return {"message": "Components reordered"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.patch("/configurations/{config_id}/components/{component_id}/toggle")
async def toggle_component(
    config_id: str,
    component_id: str,
    is_included: bool,
    client: ClientContext = Depends(require_admin)
):
    """
    Toggle the is_included flag for a component in a configuration.

    Triggers auto-reassembly of the prompt.
    """
    try:
        success = toggle_component_inclusion(
            config_id=uuid.UUID(config_id),
            component_id=uuid.UUID(component_id),
            is_included=is_included
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to toggle component")
        return {"message": f"Component {'included' if is_included else 'excluded'}"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


# ============================================================================
# Consultation Type <-> Config Junction Endpoints
# ============================================================================

@router.get("/consultation-types")
async def get_consultation_type_statuses(
    client: ClientContext = Depends(require_admin)
):
    """
    Get prompt status for all consultation types.
    """
    statuses = get_consultation_type_prompt_status()
    return {"consultation_types": statuses}


@router.get("/consultation-type-assignments")
async def get_all_assignments(
    client: ClientContext = Depends(require_admin)
):
    """
    Get all consultation type to system prompt config assignments.
    Returns a flat list of all assignments with their config details.
    """
    assignments = get_all_consultation_type_assignments()
    return {"assignments": assignments, "count": len(assignments)}


@router.get("/consultation-types/{consultation_type_code}/configs")
async def get_consultation_type_configs(
    consultation_type_code: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Get all configs assigned to a consultation type.
    """
    configs = get_configs_for_consultation_type(consultation_type_code)
    return {"configs": configs, "count": len(configs)}


@router.get("/consultation-types/{consultation_type_code}/active")
async def get_active_config(
    consultation_type_code: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Get the currently active config for a consultation type.
    """
    config = get_active_config_for_consultation_type(consultation_type_code)
    if not config:
        return {"active_config": None, "message": "No active config"}
    return {"active_config": config}


@router.post("/consultation-types/{consultation_type_code}/configs")
async def assign_config_to_type(
    consultation_type_code: str,
    data: ConsultationTypeAssignment,
    client: ClientContext = Depends(require_admin)
):
    """
    Assign a configuration to a consultation type (inactive by default).
    """
    try:
        assignment = assign_config_to_consultation_type(
            consultation_type_code=consultation_type_code,
            config_id=uuid.UUID(data.config_id)
        )
        return {"message": "Config assigned", "assignment": assignment}
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"Failed to assign config: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


# Alias endpoint for frontend compatibility
@router.post("/consultation-types/{consultation_type_code}/assign")
async def assign_config_to_type_alias(
    consultation_type_code: str,
    data: ConsultationTypeAssignment,
    client: ClientContext = Depends(require_admin)
):
    """
    Assign a configuration to a consultation type (alias for /configs endpoint).
    """
    return await assign_config_to_type(consultation_type_code, data, client)


@router.delete("/consultation-types/{consultation_type_code}/configs/{config_id}")
async def unassign_config_from_type(
    consultation_type_code: str,
    config_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Remove a config assignment from a consultation type.
    """
    try:
        success = remove_config_from_consultation_type(
            consultation_type_code=consultation_type_code,
            config_id=uuid.UUID(config_id)
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to remove config assignment")
        return {"message": "Config assignment removed"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.post("/consultation-types/{consultation_type_code}/configs/{config_id}/toggle-active")
async def toggle_assignment_active_endpoint(
    consultation_type_code: str,
    config_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Toggle the is_active status of a consultation type assignment.
    """
    try:
        result = toggle_assignment_active(
            consultation_type_code=consultation_type_code,
            config_id=uuid.UUID(config_id)
        )
        return {
            "message": f"Assignment toggled to {'active' if result.get('is_active') else 'inactive'}",
            "is_active": result.get('is_active', False)
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.error(f"Failed to toggle assignment: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


# ============================================================================
# Activation Endpoints
# ============================================================================

@router.post("/consultation-types/{consultation_type_code}/activate")
async def activate_config(
    consultation_type_code: str,
    data: ActivationRequest,
    client: ClientContext = Depends(require_admin)
):
    """
    Activate a config for a consultation type.

    DEACTIVATES any existing active config first.
    """
    try:
        result = activate_config_for_consultation_type(
            consultation_type_code=consultation_type_code,
            config_id=uuid.UUID(data.config_id)
        )
        return {"message": "Config activated", "active_config": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"Failed to activate config: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")


@router.post("/consultation-types/{consultation_type_code}/deactivate")
async def deactivate_current_config(
    consultation_type_code: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Deactivate the current active config for a consultation type.
    """
    success = deactivate_config_for_consultation_type(consultation_type_code)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to deactivate config")
    return {"message": "Config deactivated"}


# ============================================================================
# Utility Endpoints
# ============================================================================

@router.get("/prompt/{consultation_type_code}")
async def get_prompt(
    consultation_type_code: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Get the system prompt for a consultation type (with fallback).

    This is the same logic used during extraction.
    """
    prompt = get_system_prompt_with_fallback(consultation_type_code)
    return {
        "consultation_type_code": consultation_type_code,
        "system_prompt": prompt,
        "character_count": len(prompt),
        "estimated_tokens": len(prompt) // 4
    }

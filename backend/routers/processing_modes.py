"""
Processing Modes Admin Router

Handles administrative operations for managing processing modes:
- List all processing modes
- Create new processing modes
- Update existing modes
- Delete (soft) modes
- Set default mode
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
import uuid

from models.auth_models import ClientContext
from services.supabase_service import supabase, retry_on_network_error, invalidate_processing_mode_cache
from dependencies.auth import require_admin


router = APIRouter(tags=["Processing Modes Admin"])


# =============================================================================
# Pydantic Models
# =============================================================================

class ProcessingModeCreate(BaseModel):
    """Request model for creating a processing mode"""
    mode_code: str = Field(..., min_length=1, max_length=50, description="Unique code identifier")
    mode_name: str = Field(..., min_length=1, max_length=100, description="Display name")
    description: Optional[str] = Field(None, description="Optional description")
    transcription_api: str = Field(..., description="gemini_batch or gemini_live")
    transcription_model: str = Field(..., description="Model for transcription")
    extraction_model: str = Field(..., description="Model for extraction")
    triage_model: Optional[str] = Field(None, description="Model for triage analysis")
    merge_model: Optional[str] = Field(None, description="Model for merge operations")
    compare_model: Optional[str] = Field(None, description="Model for compare operations")
    emotion_model: Optional[str] = Field(None, description="Model for emotion analysis")
    insights_model: Optional[str] = Field(None, description="Model for consultation insights")
    validator_model: Optional[str] = Field(None, description="Model for continuation merge validator")
    estimated_time_seconds: Optional[int] = Field(None, ge=0, description="Estimated processing time")
    display_order: int = Field(999, ge=0, description="Display order in UI")
    is_active: bool = Field(True, description="Whether mode is active")


class ProcessingModeUpdate(BaseModel):
    """Request model for updating a processing mode"""
    mode_code: Optional[str] = Field(None, min_length=1, max_length=50)
    mode_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    transcription_api: Optional[str] = None
    transcription_model: Optional[str] = None
    extraction_model: Optional[str] = None
    triage_model: Optional[str] = None
    merge_model: Optional[str] = None
    compare_model: Optional[str] = None
    emotion_model: Optional[str] = None
    insights_model: Optional[str] = None
    validator_model: Optional[str] = None
    estimated_time_seconds: Optional[int] = Field(None, ge=0)
    display_order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


# =============================================================================
# Valid Models Configuration
# =============================================================================

VALID_BATCH_MODELS = [
    "gemini-3-pro",           # Vertex AI
    "gemini-3.1-pro-preview", # Gemini API (replaces deprecated gemini-3-pro-preview)
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

VALID_LIVE_MODELS = [
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-2.0-flash-live-001",
]

# Modes that are kept in DB but hidden from all API responses
HIDDEN_MODE_CODES = {"ultra", "ultra_fast"}


def validate_transcription_model(transcription_api: str, transcription_model: str) -> None:
    """Validate that transcription model matches the API type"""
    if transcription_api == "gemini_live":
        if transcription_model not in VALID_LIVE_MODELS:
            raise HTTPException(
                status_code=400,
                detail="Invalid model for this API type"
            )
    elif transcription_api == "gemini_batch":
        if transcription_model not in VALID_BATCH_MODELS:
            raise HTTPException(
                status_code=400,
                detail="Invalid model for this API type"
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="transcription_api must be 'gemini_batch' or 'gemini_live'"
        )


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/processing-modes")
async def list_processing_modes(
    include_inactive: bool = Query(True, description="Include inactive modes"),
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    List all processing modes.

    **Query Parameters:**
    - include_inactive: Whether to include inactive modes (default: true for admin)

    **Returns:**
    - modes: List of processing mode records
    - count: Total number of modes
    """
    try:
        query = supabase.table("processing_modes").select("*")

        if not include_inactive:
            query = query.eq("is_active", True)

        result = retry_on_network_error(
            lambda: query.order("display_order", desc=False).order("mode_code", desc=False).execute()
        )

        # Filter out hidden modes (ultra, ultra_fast) from API responses
        modes = [m for m in (result.data or []) if m.get("mode_code") not in HIDDEN_MODE_CODES]

        return {
            "success": True,
            "modes": modes,
            "count": len(modes),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to list processing modes")


@router.get("/processing-modes/{mode_id}")
async def get_processing_mode(
    mode_id: str,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Get a specific processing mode by ID.

    **Path Parameters:**
    - mode_id: UUID of the processing mode

    **Returns:**
    - mode: Processing mode details
    """
    try:
        result = retry_on_network_error(
            lambda: supabase.table("processing_modes")
            .select("*")
            .eq("id", mode_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Processing mode not found")

        return {
            "success": True,
            "mode": result.data[0],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get processing mode")


@router.post("/processing-modes")
async def create_processing_mode(
    data: ProcessingModeCreate,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Create a new processing mode.

    **Request Body:**
    - mode_code: Unique identifier code
    - mode_name: Display name
    - transcription_api: 'gemini_batch' or 'gemini_live'
    - transcription_model: Model for transcription
    - extraction_model: Model for extraction
    - triage_model, merge_model, compare_model: Optional additional models
    - estimated_time_seconds: Optional time estimate
    - display_order: Display order in UI
    - is_active: Whether mode is active

    **Returns:**
    - mode: Created processing mode
    """
    try:
        # Validate transcription model matches API
        validate_transcription_model(data.transcription_api, data.transcription_model)

        # Check for duplicate mode_code
        existing = retry_on_network_error(
            lambda: supabase.table("processing_modes")
            .select("id")
            .eq("mode_code", data.mode_code)
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=409,
                detail="Processing mode with this code already exists"
            )

        # Prepare insert data
        insert_data = {
            "id": str(uuid.uuid4()),
            "mode_code": data.mode_code,
            "mode_name": data.mode_name,
            "description": data.description,
            "transcription_api": data.transcription_api,
            "transcription_model": data.transcription_model,
            "extraction_model": data.extraction_model,
            "triage_model": data.triage_model,
            "merge_model": data.merge_model,
            "compare_model": data.compare_model,
            "emotion_model": data.emotion_model,
            "insights_model": data.insights_model,
            "validator_model": data.validator_model,
            "estimated_time_seconds": data.estimated_time_seconds,
            "display_order": data.display_order,
            "is_active": data.is_active,
            "is_default": False,  # New modes are never default
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = retry_on_network_error(
            lambda: supabase.table("processing_modes")
            .insert(insert_data)
            .execute()
        )

        # Invalidate cache for the new mode
        invalidate_processing_mode_cache(data.mode_code)

        return {
            "success": True,
            "message": f"Processing mode '{data.mode_code}' created successfully",
            "mode": result.data[0] if result.data else insert_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create processing mode")


@router.put("/processing-modes/{mode_id}")
async def update_processing_mode(
    mode_id: str,
    data: ProcessingModeUpdate,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Update an existing processing mode.

    **Path Parameters:**
    - mode_id: UUID of the processing mode

    **Request Body:**
    - Any field from ProcessingModeUpdate (all optional)

    **Returns:**
    - mode: Updated processing mode
    """
    try:
        # Get existing mode to validate
        existing = retry_on_network_error(
            lambda: supabase.table("processing_modes")
            .select("*")
            .eq("id", mode_id)
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Processing mode not found")

        existing_mode = existing.data[0]

        # Build update data
        update_data = data.model_dump(exclude_unset=True)

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Validate transcription model if either API or model is being updated
        transcription_api = update_data.get("transcription_api", existing_mode["transcription_api"])
        transcription_model = update_data.get("transcription_model", existing_mode["transcription_model"])

        if "transcription_api" in update_data or "transcription_model" in update_data:
            validate_transcription_model(transcription_api, transcription_model)

        # Check for duplicate mode_code if being updated
        if "mode_code" in update_data and update_data["mode_code"] != existing_mode["mode_code"]:
            duplicate = retry_on_network_error(
                lambda: supabase.table("processing_modes")
                .select("id")
                .eq("mode_code", update_data["mode_code"])
                .neq("id", mode_id)
                .execute()
            )
            if duplicate.data:
                raise HTTPException(
                    status_code=409,
                    detail="Processing mode with this code already exists"
                )

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        result = retry_on_network_error(
            lambda: supabase.table("processing_modes")
            .update(update_data)
            .eq("id", mode_id)
            .execute()
        )

        # Invalidate cache for old mode_code (always) and new mode_code (if changed)
        invalidate_processing_mode_cache(existing_mode["mode_code"])
        if "mode_code" in update_data and update_data["mode_code"] != existing_mode["mode_code"]:
            invalidate_processing_mode_cache(update_data["mode_code"])

        return {
            "success": True,
            "message": "Processing mode updated successfully",
            "mode": result.data[0] if result.data else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update processing mode")


@router.delete("/processing-modes/{mode_id}")
async def delete_processing_mode(
    mode_id: str,
    hard_delete: bool = Query(False, description="Permanently delete (vs soft delete)"),
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Delete (deactivate) a processing mode.

    **Path Parameters:**
    - mode_id: UUID of the processing mode

    **Query Parameters:**
    - hard_delete: If true, permanently removes. Default: soft delete (set is_active=false)

    **Note:** Cannot delete the default mode.
    """
    try:
        # Check if this is the default mode
        existing = retry_on_network_error(
            lambda: supabase.table("processing_modes")
            .select("mode_code, is_default")
            .eq("id", mode_id)
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Processing mode not found")

        if existing.data[0].get("is_default"):
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the default processing mode. Set another mode as default first."
            )

        if hard_delete:
            result = retry_on_network_error(
                lambda: supabase.table("processing_modes")
                .delete()
                .eq("id", mode_id)
                .execute()
            )
            message = f"Processing mode '{existing.data[0]['mode_code']}' permanently deleted"
        else:
            result = retry_on_network_error(
                lambda: supabase.table("processing_modes")
                .update({
                    "is_active": False,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                })
                .eq("id", mode_id)
                .execute()
            )
            message = f"Processing mode '{existing.data[0]['mode_code']}' deactivated"

        # Invalidate cache for the deleted/deactivated mode
        invalidate_processing_mode_cache(existing.data[0]["mode_code"])

        return {
            "success": True,
            "message": message,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete processing mode")


@router.patch("/processing-modes/{mode_id}/set-default")
async def set_default_processing_mode(
    mode_id: str,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Set a processing mode as the default.

    **Path Parameters:**
    - mode_id: UUID of the processing mode to set as default

    **Note:** This will unset the current default mode.
    """
    try:
        # Verify the mode exists and is active
        target = retry_on_network_error(
            lambda: supabase.table("processing_modes")
            .select("mode_code, is_active")
            .eq("id", mode_id)
            .execute()
        )

        if not target.data:
            raise HTTPException(status_code=404, detail="Processing mode not found")

        if not target.data[0].get("is_active"):
            raise HTTPException(
                status_code=400,
                detail="Cannot set an inactive mode as default. Activate it first."
            )

        # Clear current default(s)
        retry_on_network_error(
            lambda: supabase.table("processing_modes")
            .update({
                "is_default": False,
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            .eq("is_default", True)
            .execute()
        )

        # Set new default
        result = retry_on_network_error(
            lambda: supabase.table("processing_modes")
            .update({
                "is_default": True,
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            .eq("id", mode_id)
            .execute()
        )

        return {
            "success": True,
            "message": f"Processing mode '{target.data[0]['mode_code']}' set as default",
            "mode": result.data[0] if result.data else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to set default mode")


@router.get("/processing-modes/models/available")
async def get_available_models(
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Get available models grouped by use_for category from models_master table.

    **Returns:**
    - batch_models: Models for Batch API transcription
    - live_models: Models for Live API transcription
    - extraction_models: Models for extraction (Gemini + Claude + GPT)
    - merge_models: Models for merge (Gemini + Claude + GPT)
    - triage_models: Models for triage (Gemini only)
    - compare_models: Models for compare (Gemini only)
    - emotion_models: Models for emotion analysis (Gemini only)
    - insights_models: Models for consultation insights (Gemini only)
    - validator_models: Models for continuation merge validator (Gemini only)
    - transcription_apis: Available transcription API types
    """
    try:
        result = retry_on_network_error(
            lambda: supabase.table('models_master')
            .select('*')
            .eq('is_active', True)
            .order('display_order')
            .execute()
        )
        models = result.data or []

        def to_option(m):
            return {"value": m["model_id"], "label": m["display_name"], "tier": m["tier"]}

        batch_models = [to_option(m) for m in models if "transcription" in m["use_for"]]
        live_models = [to_option(m) for m in models if "transcription_live" in m["use_for"]]
        extraction_models = [to_option(m) for m in models if "extraction" in m["use_for"]]
        merge_models = [to_option(m) for m in models if "merge" in m["use_for"]]
        triage_models = [to_option(m) for m in models if "triage" in m["use_for"]]
        compare_models = [to_option(m) for m in models if "compare" in m["use_for"]]
        emotion_models = [to_option(m) for m in models if "emotion" in m["use_for"]]
        insights_models = [to_option(m) for m in models if "insights" in m["use_for"]]
        validator_models = [to_option(m) for m in models if "validator" in m["use_for"]]

        return {
            "success": True,
            "batch_models": batch_models,
            "live_models": live_models,
            "extraction_models": extraction_models,
            "merge_models": merge_models,
            "triage_models": triage_models,
            "compare_models": compare_models,
            "emotion_models": emotion_models,
            "insights_models": insights_models,
            "validator_models": validator_models,
            "transcription_apis": [
                {"value": "gemini_batch", "label": "Gemini Batch API"},
                {"value": "gemini_live", "label": "Gemini Live API (Real-time)"},
            ],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch available models")

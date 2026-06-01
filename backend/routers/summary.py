"""
Multi-Consultation Type Summary Extraction Router

This router provides endpoints for:
1. Dynamic medical summary extraction for all consultation types (OP, DISCHARGE, RESPIRATORY)
2. Consultation type management (list available types)
3. Segment configuration management per consultation type
4. Template management per consultation type

All extraction uses database-driven segment configuration with user customization support.
"""

import os
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Query, Body, Path, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
import uuid
import traceback

_template_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="template")

from models.auth_models import ClientContext
from dependencies.auth import require_admin, get_current_client
from services.audit_service import audit_service

# Conditional EHR auth imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import EHRCounsellorAccessChecker, EHRSubmissionAccessChecker, get_current_client

    _doctor_checker = EHRCounsellorAccessChecker()
    _submission_checker = EHRSubmissionAccessChecker()

    async def verify_counsellor_access(request: Request, counsellor_id: Optional[str] = None):  # type: ignore[misc]
        """Verify EHR client has access to counsellor data."""
        counsellor_uuid = uuid.UUID(counsellor_id) if counsellor_id else None
        # Resolve the client first, then pass to checker
        client = get_current_client(request)
        return await _doctor_checker(request, counsellor_uuid, client)

    async def verify_submission_access(request: Request, submission_id: Optional[str] = None):  # type: ignore[misc]
        """Verify EHR client has access to submission data."""
        submission_uuid = uuid.UUID(submission_id) if submission_id else None
        # Resolve the client first, then pass to checker
        client = get_current_client(request)
        return await _submission_checker(request, submission_uuid, client)

    def require_counsellor_id_for_ehr(request: Request, counsellor_id: Optional[str]):  # type: ignore[misc]
        """
        Require counsellor_id for EHR clients.
        Admin/Mobile/Web clients can access without counsellor_id.
        Raises HTTPException 400 if EHR client and no counsellor_id.
        """
        client = get_current_client(request)
        if client.client_type == "ehr" and not counsellor_id:
            raise HTTPException(
                status_code=400,
                detail="counsellor_id is required for EHR clients"
            )
else:
    async def verify_counsellor_access(request: Request = None, counsellor_id: Optional[str] = None):  # type: ignore[misc]
        return None

    async def verify_submission_access(request: Request = None, submission_id: Optional[str] = None):  # type: ignore[misc]
        return None

    def require_counsellor_id_for_ehr(request: Request = None, counsellor_id: Optional[str] = None):  # type: ignore[misc]
        pass  # No-op when auth disabled

from services.gemini_service import extract_summary_dynamic
from services.supabase_service import (
    get_consultation_types,
    get_consultation_type_by_code,
    get_segment_definitions,
    get_templates,
    get_template_by_code,
    get_template_configuration,
    validate_segment_configuration,
    clone_template,
    strip_internal_template_fields,
    # Template admin functions
    create_template,
    update_template,
    delete_template,
    update_template_segment_config,
    bulk_update_template_segments,
    inherit_from_consultation_type,
    # Consultation type segment admin functions
    get_consultation_type_segments,
    update_consultation_type_segment,
    bulk_update_consultation_type_segments,
    # Bulk clone function
    bulk_clone_segments,
    # Delete functions
    delete_segment,
    delete_consultation_type,
    # Reactivate functions
    reactivate_template,
    reactivate_segment,
    reactivate_consultation_type,
    # Cache invalidation functions
    invalidate_consultation_type_cache,
    invalidate_template_cache,
    invalidate_counsellor_school_cache,
    invalidate_processing_mode_cache,
    # Supabase client
    supabase
)
from services.uuid_utils import normalize_counsellor_id
from services.counsellor_templates_service import activate_template_for_counsellor

router = APIRouter(prefix="/api/v1/summary", tags=["Medical Summary - Multi-Type"])
logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================

class ExtractionRequest(BaseModel):
    """
    Request model for medical summary extraction.

    Required: transcript, submission_id

    Note: Standalone extraction without submission_id is NOT supported.
    All extractions must be linked to a recording session via submission_id.

    submission_id is returned from:
    - /chunk endpoint when is_last=true (chunked recording flow)
    - /live/session endpoint (WebSocket/RecordTab flow - where submission_id = correlation_id)
    """
    transcript: str = Field(..., min_length=10, description="Consultation transcript text")
    counsellor_id: Optional[str] = Field(None, description="Counsellor ID for personalized configuration")
    student_id: Optional[str] = Field(None, description="Student ID for Live API flow")
    template_code: Optional[str] = Field(None, description="Doctor's activated template code (unique identifier for DB lookups)")
    template_name: Optional[str] = Field(None, description="Template display name (for human readability)")
    processing_mode: Optional[str] = Field(None, description="Processing mode code (fast, default, thorough, ultra, ultra_fast)")
    mode: str = Field("full", pattern="^(core|additional|full)$", description="Extraction mode")
    submission_id: Optional[str] = Field(None, description="Submission ID from processing_jobs (required - links extraction to recording session)")
    assistant_id: Optional[str] = Field(None, description="Optional assistant UUID if extraction is initiated by an assistant")


class CreateConsultationTypeRequest(BaseModel):
    """Request model for creating a new consultation type with optional visibility controls"""
    type_code: str = Field(..., min_length=1, max_length=50, description="Unique type code (uppercase, underscores)")
    type_name: str = Field(..., min_length=1, max_length=255, description="Display name for the consultation type")
    description: Optional[str] = Field(None, description="Detailed description of the consultation type")
    specialty_applicable: Optional[List[str]] = Field(None, description="List of applicable specialties")
    display_order: int = Field(..., ge=1, le=100, description="Display order in UI (1-100)")
    icon_name: Optional[str] = Field(None, max_length=50, description="Icon name for UI display")
    color_code: Optional[str] = Field(None, max_length=20, description="Color code for UI theme (e.g., #4F46E5)")
    clone_from_consultation_type_id: Optional[str] = Field(None, description="UUID of consultation type to clone segments from")
    # Visibility controls (optional - if all empty/None, everyone can see this consultation type)
    visible_to_schools: Optional[List[str]] = Field(None, description="School UUIDs that can see this consultation type")
    visible_to_counsellors: Optional[List[str]] = Field(None, description="Counsellor UUIDs that can see this consultation type")
    visible_to_specializations: Optional[List[str]] = Field(None, description="Specializations that can see this consultation type")


class SegmentConfigUpdate(BaseModel):
    """Request model for updating segment configuration"""
    category: Optional[str] = Field(None, pattern="^(core|additional)$")
    brevity_level: Optional[str] = Field(None, pattern="^(concise|balanced|detailed)$")
    terminology_style: Optional[str] = Field(None, pattern="^(medical_terms|simple_terms|as_spoken)$")


class SegmentMoveRequest(BaseModel):
    """Request model for moving segment between categories"""
    segment_code: str = Field(..., description="Segment code (e.g., 'DIAGNOSIS')")
    new_category: str = Field(..., pattern="^(core|additional|excluded)$", description="New category: core, additional, or excluded")


class CreateTemplateRequest(BaseModel):
    """Request model for creating a new template"""
    template_code: str = Field(..., min_length=1, max_length=50, description="Unique template code (e.g., 'PSYCHIATRY_CORE')")
    template_name: str = Field(..., min_length=1, max_length=255, description="Display name")
    description: str = Field(..., description="Template description")
    consultation_type_code: str = Field(..., description="Consultation type code (OP, DISCHARGE, RESPIRATORY)")
    use_case: Optional[str] = Field(None, max_length=100, description="Use case (e.g., 'quick_consultation')")
    specialization: Optional[str] = Field(None, max_length=100, description="Specialization for visibility filtering")
    school_id: Optional[str] = Field(None, description="School ID for school-specific templates")
    estimated_extraction_time_seconds: Optional[float] = Field(None, description="Performance hint")
    is_active: bool = Field(True, description="Whether template is active and visible to counsellors (default: true)")
    inherit_from_type: Optional[str] = Field(None, pattern="^(consultation_type|template)$", description="Type to inherit from: 'consultation_type' or 'template'")
    inherit_from_id: Optional[str] = Field(None, description="Consultation type code or template code to inherit from")
    # Deprecated: kept for backwards compatibility
    inherit_from_consultation_type: Optional[bool] = Field(None, description="Deprecated: Use inherit_from_type='consultation_type' instead")


class UpdateTemplateRequest(BaseModel):
    """Request model for updating template metadata"""
    template_name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    use_case: Optional[str] = Field(None, max_length=100)
    specialization: Optional[str] = Field(None, max_length=100, description="Specialization for visibility filtering")
    estimated_extraction_time_seconds: Optional[float] = None


class TemplateSegmentConfigUpdate(BaseModel):
    """Request model for updating template segment configuration"""
    category: str = Field(..., pattern="^(core|additional|excluded)$")
    display_order: int = Field(..., ge=0)
    brevity_level: Optional[str] = Field(None, pattern="^(concise|balanced|detailed)$")
    terminology_style: Optional[str] = Field(None, pattern="^(medical_terms|simple_terms|as_spoken)$")


class BulkSegmentUpdate(BaseModel):
    """Request model for bulk segment configuration update"""
    segments: List[Dict[str, Any]] = Field(..., description="List of segment configs")


class ConsultationTypeSegmentUpdate(BaseModel):
    """Request model for updating consultation type segment definition"""
    segment_name: Optional[str] = Field(None, max_length=255, description="Segment display name")
    default_category: Optional[str] = Field(None, pattern="^(core|additional|excluded)$", description="Default category")
    display_order: Optional[int] = Field(None, ge=0, description="Display order")
    default_brevity_level: Optional[str] = Field(None, pattern="^(concise|balanced|detailed)$", description="Default brevity level")
    default_terminology_style: Optional[str] = Field(None, pattern="^(medical_terms|simple_terms|as_spoken)$", description="Default terminology style")
    prompt_section_text: Optional[str] = Field(None, description="Prompt text for this segment")
    schema_definition_json: Optional[Dict[str, Any]] = Field(None, description="JSON schema for this segment")
    is_required: Optional[bool] = Field(None, description="Whether this segment is required")


# ============================================================================
# Cache Management Endpoints
# ============================================================================

@router.post("/admin/cache/refresh")
async def refresh_all_caches(
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Invalidate all pipeline caches immediately.

    This clears all in-memory caches without waiting for TTL expiry:
    - Consultation type cache
    - Template cache
    - Counsellor-school cache
    - Processing mode cache
    - List availability cache (medicines/investigations)
    - Medicine caches (counsellor and school)
    - Investigation caches (counsellor and school)
    - Live prompt cache (RecordTab parallel prompt generation)

    **Use Cases:**
    - After direct database updates (bypassing API)
    - When settings changes aren't taking effect
    - To force fresh data fetch on next request

    **Note:** Gemini context cache (30-min TTL) is managed by Google API and cannot be invalidated here.
    """
    try:
        from services.extraction_service import invalidate_list_cache_by_school
        from services.medicine_service import (
            invalidate_all_school_medicine_caches,
            invalidate_all_counsellor_medicine_caches,
        )
        from services.investigation_service import (
            invalidate_all_counsellor_investigation_caches,
            invalidate_all_school_investigation_caches,
        )
        from routers.recording_session import invalidate_all_live_prompt_cache

        results = {}

        # 1. Consultation type caches
        ct_count = invalidate_consultation_type_cache()
        results["consultation_type_cache"] = ct_count

        # 2. Template caches
        template_count = invalidate_template_cache()
        results["template_cache"] = template_count

        # 3. Counsellor-school cache
        dh_count = invalidate_counsellor_school_cache()
        results["doctor_hospital_cache"] = dh_count

        # 4. Processing mode caches (extraction, triage, emotion, insights models)
        pm_count = invalidate_processing_mode_cache()
        results["processing_mode_cache"] = pm_count

        # 5. School medicine caches
        hosp_med_count = invalidate_all_school_medicine_caches()
        results["hospital_medicine_cache"] = hosp_med_count

        # 6. Counsellor medicine caches
        doc_med_count = invalidate_all_counsellor_medicine_caches()
        results["doctor_medicine_cache"] = doc_med_count

        # 7. List availability cache (medicine/investigation existence checks)
        # Pass a dummy UUID to clear all - invalidate_list_cache_by_school clears everything
        list_count = invalidate_list_cache_by_school(uuid.UUID('00000000-0000-0000-0000-000000000000'))
        results["list_availability_cache"] = list_count

        # 8. School investigation caches
        hosp_inv_count = invalidate_all_school_investigation_caches()
        results["hospital_investigation_cache"] = hosp_inv_count

        # 9. Counsellor investigation caches
        doc_inv_count = invalidate_all_counsellor_investigation_caches()
        results["doctor_investigation_cache"] = doc_inv_count

        # 10. Live prompt cache (RecordTab parallel prompt generation)
        live_prompt_count = invalidate_all_live_prompt_cache()
        results["live_prompt_cache"] = live_prompt_count

        total_cleared = sum(results.values())

        logger.debug(f"[CACHE_REFRESH] All caches invalidated: {results}")

        return {
            "success": True,
            "message": f"All pipeline caches refreshed ({total_cleared} entries cleared)",
            "details": results
        }

    except Exception as e:
        logger.error(f"[CACHE_REFRESH] Error refreshing caches: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to refresh caches"
        )


# ============================================================================
# Consultation Type Endpoints
# ============================================================================

@router.get("/consultation-types")
async def list_consultation_types(
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get all available consultation types (Admin only).

    **Returns:**
    - List of consultation types with metadata (code, name, description, icon, color)
    """
    try:
        types = get_consultation_types(include_inactive=False)

        return {
            "success": True,
            "consultation_types": types,
            "count": len(types)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch consultation types")


@router.get("/consultation-types/{type_code}")
async def get_consultation_type(
    type_code: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get details for a specific consultation type (Admin only).

    **Path Parameters:**
    - `type_code`: Consultation type code (OP, DISCHARGE, RESPIRATORY)
    """
    try:
        consultation_type = get_consultation_type_by_code(type_code)

        if not consultation_type:
            raise HTTPException(status_code=404, detail="Consultation type not found")

        return {
            "success": True,
            "consultation_type": consultation_type
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.post("/admin/consultation-types")
async def create_new_consultation_type(
    request: CreateConsultationTypeRequest,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Create a new consultation type.

    **Request Body:**
    - `type_code`: Unique type code (uppercase, underscores)
    - `type_name`: Display name
    - `description`: Optional description
    - `specialty_applicable`: Optional list of specialties
    - `display_order`: Display order in UI (1-100)
    - `icon_name`: Optional icon name
    - `color_code`: Optional color code (e.g., #4F46E5)
    - `clone_from_consultation_type_id`: Optional UUID to clone segments from existing consultation type

    **Response:**
    - `success`: Boolean indicating success
    - `consultation_type`: Created consultation type object
    - `message`: Success message

    **Notes:**
    - If `clone_from_consultation_type_id` is provided, ALL segments from source consultation type will be cloned
    - If NOT provided, only common segments will be copied (default behavior)
    - Cloned segments maintain parent tracking for future updates
    """
    try:
        from services.supabase_service import create_consultation_type

        consultation_type = create_consultation_type(
            type_code=request.type_code,
            type_name=request.type_name,
            description=request.description,
            specialty_applicable=request.specialty_applicable,
            display_order=request.display_order,
            icon_name=request.icon_name,
            color_code=request.color_code,
            clone_from_consultation_type_id=request.clone_from_consultation_type_id,
            # Visibility controls (optional - if all empty/None, everyone can see it)
            visible_to_schools=request.visible_to_schools,
            visible_to_counsellors=request.visible_to_counsellors,
            visible_to_specializations=request.visible_to_specializations,
        )

        # Invalidate consultation_type cache
        invalidate_consultation_type_cache(type_code=request.type_code)

        # Determine message based on clone source
        if request.clone_from_consultation_type_id:
            message = f"Consultation type '{request.type_code}' created successfully with segments cloned from source consultation type"
        else:
            message = f"Consultation type '{request.type_code}' created successfully with common segments"

        return {
            "success": True,
            "consultation_type": consultation_type,
            "message": message
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create consultation type")


@router.patch("/admin/consultation-types/{consultation_type_code}/emotion-analysis")
async def toggle_emotion_analysis(
    consultation_type_code: str,
    enable: bool = Query(..., description="Enable or disable emotion analysis"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Toggle emotion analysis for a consultation type.

    This endpoint enables or disables background emotion extraction for a specific
    consultation type. When enabled, the system will automatically extract 5 emotion
    segments 20 seconds after extraction completes.

    **Path Parameters:**
    - `consultation_type_code`: Consultation type code (OP, OP_CONCISE, DISCHARGE, RESPIRATORY)

    **Query Parameters:**
    - `enable`: true to enable emotion analysis, false to disable

    **Emotion Segments Extracted:**
    1. Pre-consultation anxiety level
    2. Post-consultation anxiety level
    3. Other emotions detected (medically relevant)
    4. Financial concerns
    5. Treatment compliance likelihood

    **Response:**
    - `success`: Boolean indicating success
    - `consultation_type_code`: Updated consultation type code
    - `enable_emotion_analysis`: New value of the flag
    - `message`: Success message

    **Example:**
    ```
    PATCH /api/v1/summary/admin/consultation-types/OP/emotion-analysis?enable=true
    ```
    """
    try:
        from services.supabase_service import get_consultation_type_by_code

        # Get consultation type
        consultation_type = get_consultation_type_by_code(consultation_type_code)
        if not consultation_type:
            raise HTTPException(
                status_code=404,
                detail="Consultation type not found"
            )

        # Update enable_emotion_analysis flag
        consultation_type_id = consultation_type["id"]

        response = supabase.table("consultation_types").update({
            "enable_emotion_analysis": enable
        }).eq("id", consultation_type_id).execute()

        if not response.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to update emotion analysis setting"
            )

        # Invalidate consultation_type cache so new settings take effect immediately
        invalidate_consultation_type_cache(type_code=consultation_type_code)

        action = "enabled" if enable else "disabled"
        return {
            "success": True,
            "consultation_type_code": consultation_type_code,
            "enable_emotion_analysis": enable,
            "message": f"Emotion analysis {action} for {consultation_type_code}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to toggle emotion analysis"
        )


# NOTE: emotion_extraction_mode endpoint removed (Jan 2026)
# Simplified to combined-only mode - use emotion-analysis toggle endpoint instead
# The /emotion-analysis endpoint (above) now controls a simple on/off boolean


@router.patch("/admin/consultation-types/{consultation_type_code}/triage-analysis")
async def update_triage_analysis_setting(
    consultation_type_code: str,
    enable: bool = Query(..., description="Enable or disable triage analysis"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Enable/disable triage analysis for a consultation type.

    **Path Parameters:**
    - `consultation_type_code`: Consultation type code (OP, OP_CONCISE, DISCHARGE, etc.)

    **Query Parameters:**
    - `enable`: true to enable triage analysis, false to disable

    **Triage Analysis Features:**
    - Red flag detection (critical symptoms, warning signs)
    - Missing investigation suggestions
    - Treatment recommendations based on diagnosis
    - Rule-based clinical decision support

    **Note:** Disabling triage does NOT disable consultation insights/interventions.
    Each setting is independent.
    """
    try:
        from services.supabase_service import get_consultation_type_by_code

        # Get consultation type
        consultation_type = get_consultation_type_by_code(consultation_type_code)
        if not consultation_type:
            raise HTTPException(
                status_code=404,
                detail="Consultation type not found"
            )

        consultation_type_id = consultation_type["id"]

        response = supabase.table("consultation_types").update({
            "enable_triage_analysis": enable
        }).eq("id", consultation_type_id).execute()

        if not response.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to update triage analysis setting"
            )

        # Invalidate consultation_type cache so new settings take effect immediately
        invalidate_consultation_type_cache(type_code=consultation_type_code)

        action = "enabled" if enable else "disabled"
        return {
            "success": True,
            "consultation_type_code": consultation_type_code,
            "enable_triage_analysis": enable,
            "message": f"Triage analysis {action} for {consultation_type_code}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to toggle triage analysis"
        )


@router.patch("/admin/consultation-types/{consultation_type_code}/consultation-insights")
async def update_consultation_insights_setting(
    consultation_type_code: str,
    enable: bool = Query(..., description="Enable or disable consultation insights and interventions"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Enable/disable consultation insights extraction and interventions for a consultation type.

    **Path Parameters:**
    - `consultation_type_code`: Consultation type code (OP, OP_CONCISE, DISCHARGE, etc.)

    **Query Parameters:**
    - `enable`: true to enable, false to disable

    **When Enabled:**
    - Gemini API extracts 14 clinical signal groups from transcript
    - Clinical severity assessment calculated
    - Allied health needs identified
    - Student dropoff risk assessed
    - Care quality risk evaluated
    - REVENUE, RETENTION, and QUALITY interventions generated

    **When Disabled:**
    - No Gemini call for consultation insights
    - No downstream assessments run
    - No interventions generated
    - Triage analysis may still run if separately enabled

    **Note:** This is independent of triage analysis toggle.
    """
    try:
        from services.supabase_service import get_consultation_type_by_code

        # Get consultation type
        consultation_type = get_consultation_type_by_code(consultation_type_code)
        if not consultation_type:
            raise HTTPException(
                status_code=404,
                detail="Consultation type not found"
            )

        consultation_type_id = consultation_type["id"]

        response = supabase.table("consultation_types").update({
            "enable_consultation_insights": enable
        }).eq("id", consultation_type_id).execute()

        if not response.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to update consultation insights setting"
            )

        # Invalidate consultation_type cache so new settings take effect immediately
        invalidate_consultation_type_cache(type_code=consultation_type_code)

        action = "enabled" if enable else "disabled"
        return {
            "success": True,
            "consultation_type_code": consultation_type_code,
            "enable_consultation_insights": enable,
            "message": f"Consultation insights and interventions {action} for {consultation_type_code}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to toggle consultation insights"
        )


@router.patch("/admin/consultation-types/{consultation_type_code}/skip-transcription")
async def update_skip_transcription_setting(
    consultation_type_code: str,
    enable: bool = Query(..., description="Enable or disable skip transcription (direct audio extraction)"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Enable/disable skip transcription for a consultation type.

    **Path Parameters:**
    - `consultation_type_code`: Consultation type code (OP, OP_CONCISE, DISCHARGE, etc.)

    **Query Parameters:**
    - `enable`: true to enable (skip transcription), false to disable

    **When Enabled:**
    - Transcription step is skipped entirely
    - Insights extracted directly from audio using Gemini multimodal
    - Emotion analysis, triage, and consultation insights are auto-disabled
    - Useful for high-volume scenarios where transcript is not needed

    **When Disabled:**
    - Normal pipeline: transcribe → extract insights
    - Emotion/triage/insights can be individually re-enabled
    """
    try:
        from services.supabase_service import get_consultation_type_by_code

        # Get consultation type
        consultation_type = get_consultation_type_by_code(consultation_type_code)
        if not consultation_type:
            raise HTTPException(
                status_code=404,
                detail="Consultation type not found"
            )

        consultation_type_id = consultation_type["id"]

        # Build update data
        update_data = {"skip_transcription": enable}

        # When enabling skip_transcription, auto-disable dependent features
        if enable:
            update_data.update({
                "enable_emotion_analysis": False,
                "enable_triage_analysis": False,
                "enable_consultation_insights": False,
            })

        response = supabase.table("consultation_types").update(update_data).eq("id", consultation_type_id).execute()

        if not response.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to update skip transcription setting"
            )

        # Invalidate consultation_type cache so new settings take effect immediately
        invalidate_consultation_type_cache(type_code=consultation_type_code)

        action = "enabled" if enable else "disabled"
        return {
            "success": True,
            "consultation_type_code": consultation_type_code,
            "skip_transcription": enable,
            "message": f"Skip transcription {action} for {consultation_type_code}" + (
                " (emotion/triage/insights auto-disabled)" if enable else ""
            )
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to toggle skip transcription"
        )


# ============================================================================
# Extraction Endpoints
# ============================================================================

@router.post("/extract")
async def extract_medical_summary(
    http_request: Request,
    request: ExtractionRequest,
    _auth = Depends(verify_submission_access)
) -> Dict[str, Any]:
    """
    Extract medical consultation summary using dynamic database-driven configuration.

    **Required:** `submission_id` must be provided to link extraction to a recording session.
    Standalone extraction without submission_id is NOT supported.

    **Workflow:**
    1. Recording session is created and returns correlation_id
    2. When recording completes (is_last=true for chunks, or /live/session for WebSocket):
       - A processing_job is created with submission_id
       - submission_id is returned to frontend
    3. Frontend calls this endpoint with the submission_id
    4. Extraction is saved to `extractions` table
    5. Emotion analysis is scheduled based on consultation type settings

    **Request Parameters:**
    - `transcript`: Consultation transcript text (required)
    - `submission_id`: Processing job submission ID (required - from /chunk is_last=true or /live/session)
    - `template_code`: Counsellor's activated template code for segment configuration
    - `template_name`: Template display name for readability
    - `processing_mode`: Processing mode (fast, default, thorough, ultra, ultra_fast)
    - `counsellor_id`: Counsellor ID for personalized configuration
    - `mode`: Extraction mode - core, additional, or full

    **Features:**
    - Multi-consultation type support (OP, DISCHARGE, RESPIRATORY, etc.)
    - Template-based extraction with counsellor activation system
    - User-customizable segment selection (CORE/ADDITIONAL/FULL)
    - Per-segment brevity control (concise/balanced/detailed)
    - Per-segment terminology control (medical_terms/simple_terms/as_spoken)
    - Processing mode-based model selection

    **Modes:**
    - `core`: Extract essential clinical segments
    - `additional`: Extract supplementary segments
    - `full`: Extract all segments

    **Returns:**
    - `data`: Extracted insights (JSON structure based on selected segments)
    - `metadata`: Extraction metadata (consultation_type, mode, segment_count, extraction_id, submission_id)
    """
    try:
        # ========================================================================
        # Extraction flow using submission_id
        # ========================================================================
        if request.submission_id:
            logger.info(f"[EXTRACT] Extraction flow - submission_id: {request.submission_id}")

            from services.supabase_service import supabase
            from services.extraction_service import perform_template_extraction

            # Step 1: Look up processing_job by submission_id to get session_id
            submission_uuid = uuid.UUID(request.submission_id)
            job_response = supabase.table("processing_jobs")\
                .select("submission_id, session_id")\
                .eq("submission_id", request.submission_id)\
                .limit(1)\
                .execute()

            if not job_response.data:
                raise HTTPException(
                    status_code=404,
                    detail="Processing job not found"
                )

            job = job_response.data[0]
            session_id = uuid.UUID(job['session_id'])
            logger.debug(f"[EXTRACT] Found processing_job - submission_id: {request.submission_id}, session_id: {session_id}")

            # Step 2: Look up recording session by session_id
            session_response = supabase.table("recording_sessions")\
                .select("*")\
                .eq("id", str(session_id))\
                .limit(1)\
                .execute()

            if not session_response.data:
                raise HTTPException(
                    status_code=404,
                    detail="Recording session not found"
                )

            session = session_response.data[0]
            logger.debug(f"[EXTRACT] Found session: {session_id}, template: {session.get('template_name')}")

            # ⭐ Auto-save transcript to session if not already saved
            # This enables transcript persistence for all workflows (VHR Mic, VHR File, RecordTab)
            if not session.get('transcript_text'):
                logger.debug(f"[EXTRACT] Saving transcript to session {session_id} ({len(request.transcript)} chars)")
                supabase.table('recording_sessions')\
                    .update({'transcript_text': request.transcript})\
                    .eq('id', str(session_id))\
                    .execute()
                logger.debug(f"[EXTRACT] ✓ Transcript saved to session {session_id}")
            else:
                logger.debug(f"[EXTRACT] Transcript already exists in session {session_id}, skipping save")

            # ⭐ Update session with template and extraction mode from request (for VHR Mic workflow)
            # VHR Mic creates session with TRANSCRIPT_ONLY during recording, then updates here
            update_data = {}
            if request.template_code and session.get('template_code') == 'TRANSCRIPT_ONLY':
                update_data['template_code'] = request.template_code
                logger.debug(f"[EXTRACT] Updating session template_code from TRANSCRIPT_ONLY to {request.template_code}")
            if request.template_name and session.get('template_name') == 'TRANSCRIPT_ONLY':
                update_data['template_name'] = request.template_name
                logger.debug(f"[EXTRACT] Updating session template_name from TRANSCRIPT_ONLY to {request.template_name}")
            if request.mode and not session.get('extraction_mode'):
                update_data['extraction_mode'] = request.mode
                logger.debug(f"[EXTRACT] Updating session extraction_mode to {request.mode}")

            if update_data:
                supabase.table('recording_sessions')\
                    .update(update_data)\
                    .eq('id', str(session_id))\
                    .execute()
                logger.debug(f"[EXTRACT] ✓ Session updated with extraction configuration")
                # Update local session dict with changes for passing to extraction service
                session.update(update_data)

            # Determine extraction model from processing_mode
            from services.supabase_service import get_processing_mode
            processing_mode = request.processing_mode or "default"
            pm_config = get_processing_mode(processing_mode)
            extraction_model = pm_config['extraction_model']

            # Pre-generate extraction_id for triage/emotion scheduling
            # This ensures extraction_id is available before DB save completes
            extraction_id = uuid.uuid4()
            logger.debug(f"[EXTRACT] Pre-generated extraction_id: {extraction_id}")

            # ============================================================================
            # LIVE SESSION AUDIO: Schedule async audio processing (non-blocking)
            # For RecordTab sessions that uploaded audio chunks during Gemini streaming
            # ============================================================================
            if session.get('transcription_model') == 'gemini-live-api':
                correlation_id = session.get('correlation_id')
                if correlation_id:
                    from services.chunk_memory_store import get_chunks_sorted

                    chunks = get_chunks_sorted(correlation_id)
                    if chunks and len(chunks) > 0:
                        logger.debug(f"[EXTRACT] Found {len(chunks)} audio chunks for live session - scheduling async processing")

                        # Schedule async processing (stitch → emotion → insights)
                        # Does NOT block extraction - runs in background
                        from services.background_tasks import schedule_live_audio_emotion

                        # Get template_id from session_context_json (stored during /live/session)
                        session_context = session.get('session_context_json') or {}
                        template_id = session_context.get('template_id')

                        asyncio.create_task(
                            schedule_live_audio_emotion(
                                correlation_id=correlation_id,
                                chunks=chunks,
                                session_id=session_id,
                                consultation_type_id=session.get('consultation_type_id'),
                                template_id=template_id,  # From session_context_json
                                counsellor_id=session.get('counsellor_id'),
                                transcript=request.transcript,  # For combined emotion analysis
                                extraction_id=extraction_id,  # Pre-generated extraction_id
                            )
                        )
                    else:
                        logger.debug(f"[EXTRACT] No audio chunks for live session {correlation_id} - emotion will use transcript only")

            # Call shared extraction service
            # This handles: template lookup, consultation_type_id update, DB save, emotion scheduling
            result = await perform_template_extraction(
                transcript=request.transcript,
                session_id=session_id,
                extraction_model=extraction_model,
                submission_id=submission_uuid,
                # OPTIMIZATION: Pass session data to avoid re-querying
                session_data=session,
                # Pass pre-generated extraction_id for triage/emotion
                extraction_id=extraction_id,
            )

            if not result:
                raise HTTPException(
                    status_code=400,
                    detail="Extraction failed - session may be in TRANSCRIPT_ONLY mode without proper configuration"
                )

            # Build standardized metadata (same structure for API and webhook)
            from datetime import datetime
            session_info = result['session_info']

            # Fetch audio quality from session (may be None if analysis not complete or failed)
            audio_quality = session.get('audio_quality_json')

            # Lookup student preferred_language
            _extract_patient_id = session_info.get('student_id')
            _extract_preferred_lang = None
            if _extract_patient_id:
                try:
                    from services.supabase_service import supabase as _sb
                    _plr = _sb.table("students").select("preferred_language").eq("id", _extract_patient_id).limit(1).execute()
                    if _plr.data:
                        _extract_preferred_lang = _plr.data[0].get("preferred_language")
                except Exception:
                    pass

            standardized_metadata = {
                "correlation_id": session_info.get('correlation_id'),
                "submission_id": request.submission_id,
                "extraction_id": result["extraction_id"],
                "session_id": str(session_id),
                "counsellor_id": session_info.get('counsellor_id'),
                "student_id": _extract_patient_id,  # External varchar, not DB id
                "template_code": session_info.get('template_code'),
                "mode": session_info.get('extraction_mode'),
                "segment_count": result["metadata"].get('segment_count', 0),
                "processing_mode": session_info.get('processing_mode'),
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "audio_quality": audio_quality,  # Audio quality analysis (may be null)
                "preferred_language": _extract_preferred_lang,
            }

            # Filter excluded segments from response
            excluded_codes = result.get('excluded_segment_codes', set())
            insights_data = result['data']
            if excluded_codes and isinstance(insights_data, dict):
                # Convert excluded codes to camelCase for matching (segment codes are UPPER_SNAKE_CASE)
                # e.g., "CAUTION" -> "caution", "SUMMARY" -> "summary"
                excluded_camel = set()
                for code in excluded_codes:
                    parts = code.lower().split('_')
                    camel = parts[0] + ''.join(p.capitalize() for p in parts[1:])
                    excluded_camel.add(camel)

                filtered_insights = {
                    key: value for key, value in insights_data.items()
                    if key not in excluded_camel
                }
                logger.debug(f"[EXTRACT] Filtered {len(excluded_codes)} excluded segments: {excluded_codes} -> {excluded_camel}")
            else:
                filtered_insights = insights_data

            # Send webhook with standardized metadata (also filter excluded segments)
            # Check if realtime is enabled (skip webhook if so)
            from services.webhook_service import send_insights_webhook
            from services.realtime_publisher_service import is_realtime_enabled_for_school
            from services.supabase_service import get_counsellor_school_id_cached
            _doctor_id = session_info.get('counsellor_id')
            _hospital_id = get_counsellor_school_id_cached(uuid.UUID(_doctor_id)) if _doctor_id else None
            if _hospital_id and is_realtime_enabled_for_school(_hospital_id):
                logger.info(f"[EXTRACT:WEBHOOK] ⏭️ Skipping webhook - realtime subscription enabled for school")
            else:
                await send_insights_webhook(
                    insights=filtered_insights,
                    metadata=standardized_metadata,
                    source='transcript_only_extraction',
                    excluded_segment_codes=excluded_codes
                )

            # HIPAA Audit: log extraction creation
            client_ctx = getattr(http_request.state, "client", None)
            if client_ctx:
                try:
                    asyncio.create_task(audit_service.log_phi_access(
                        client_context=client_ctx, request=http_request, response_status=200,
                        response_time_ms=0, resource_type="extraction", action="create",
                        resource_id=result.get("extraction_id"),
                        counsellor_id=uuid.UUID(_doctor_id) if _doctor_id else None,
                        student_id=session_info.get("student_id"),
                    ))
                except Exception:
                    pass

            return {
                "success": True,
                "insights": filtered_insights,
                "metadata": standardized_metadata
            }

        # No submission_id provided - this endpoint requires submission_id
        else:
            raise HTTPException(
                status_code=400,
                detail="submission_id is required for extraction. Use the recording workflow to get submission_id from /chunk (is_last=true) or /live/session."
            )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Extraction failed")


# ============================================================================
# Processing Modes Endpoint
# ============================================================================

@router.get("/processing-modes")
async def get_processing_modes(
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Get all available processing modes from database.

    This is a global configuration endpoint - any authenticated client can access.
    No counsellor/school scoping required.

    **Returns:**
    - List of processing modes with model configuration, description, and estimated time

    **Processing Modes:**
    - `ultra_fast`: Fastest with Flash models (~15-20s)
    - `fast`: Fast with Flash models (~20-30s)
    - `default`: Balanced Flash transcription + Pro extraction (~30-45s)
    - `thorough`: Maximum quality with Pro models (~45-60s)
    - `ultra`: Native audio + Pro (Coming soon)
    """
    try:
        from services.supabase_service import get_all_processing_modes
        from routers.processing_modes import HIDDEN_MODE_CODES

        modes = [m for m in get_all_processing_modes() if m.get("mode_code") not in HIDDEN_MODE_CODES]

        return {
            "success": True,
            "processing_modes": modes,
            "count": len(modes)
        }
    except Exception as e:
        logger.error(f"[GET_PROCESSING_MODES] Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch processing modes")


# ============================================================================
# Segment Configuration Endpoints (Per Consultation Type)
# ============================================================================

@router.get("/segments/{consultation_type_code}")
async def get_segments(
    request: Request,
    consultation_type_code: str,
    counsellor_id: Optional[str] = Query(None, description="User ID for personalized config"),
    template_code: Optional[str] = Query(None, description="Template code for template-specific configuration (unique identifier)"),
    mode: str = Query("full", pattern="^(core|additional|full)$"),
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Get segment definitions for a consultation type with optional user customization.

    **Path Parameters:**
    - `consultation_type_code`: Consultation type (OP, DISCHARGE, RESPIRATORY)

    **Query Parameters:**
    - `counsellor_id`: Optional counsellor ID for personalized configuration
    - `template_code`: Optional template code for template-specific configuration (unique identifier)
    - `mode`: Filter by mode (core, additional, full)

    **Returns:**
    - List of segments with configuration (category, brevity, terminology)

    **EHR Access:**
    EHR clients MUST provide counsellor_id. Admin/Mobile/Web clients can access without.
    """
    try:
        # EHR clients must provide counsellor_id
        require_counsellor_id_for_ehr(request, counsellor_id)

        logger.info(f"[GET_SEGMENTS] Starting - consultation_type_code={consultation_type_code}, counsellor_id={counsellor_id}, template_code='{template_code}', mode={mode}")

        # Get consultation type
        consultation_type = get_consultation_type_by_code(consultation_type_code)
        if not consultation_type:
            logger.error(f"[GET_SEGMENTS] Consultation type not found: {consultation_type_code}")
            raise HTTPException(status_code=404, detail="Consultation type not found")

        logger.debug(f"[GET_SEGMENTS] Found consultation type: {consultation_type.get('type_name')} (ID: {consultation_type.get('id')})")

        consultation_type_id = uuid.UUID(consultation_type["id"])
        counsellor_uuid = normalize_counsellor_id(counsellor_id) if counsellor_id else None

        logger.debug(f"[GET_SEGMENTS] Normalized counsellor_id: {counsellor_uuid}")

        # Get segments with template-specific configuration
        logger.debug(f"[GET_SEGMENTS] Calling get_segment_definitions with template_code='{template_code}'...")
        result = get_segment_definitions(
            consultation_type_id=consultation_type_id,
            counsellor_id=counsellor_uuid,
            template_code=template_code,
            mode=mode
        )
        segments = result.get("segments", [])

        logger.debug(f"[GET_SEGMENTS] Retrieved {len(segments)} segments")

        # Log segment categories
        core_count = sum(1 for s in segments if s.get("default_category") == "core")
        additional_count = sum(1 for s in segments if s.get("default_category") == "additional")
        excluded_count = sum(1 for s in segments if s.get("default_category") == "excluded")
        logger.debug(f"[GET_SEGMENTS] Categories - CORE: {core_count}, ADDITIONAL: {additional_count}, EXCLUDED: {excluded_count}")

        return {
            "success": True,
            "consultation_type_code": consultation_type_code,
            "consultation_type_name": consultation_type["type_name"],
            "mode": mode,
            "segments": segments,
            "count": len(segments)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GET_SEGMENTS] Exception occurred: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch segments")


# REMOVED: PUT /segments/{segment_code}
# Reason: doctor_segment_configurations table removed in migration 20251123000000
# Use: PUT /admin/templates/{template_code}/segments/{segment_code} instead

# REMOVED: POST /segments/move
# Reason: doctor_segment_configurations table removed in migration 20251123000000
# Use: PUT /admin/templates/{template_code}/segments/{segment_code} instead (update category field)


# ============================================================================
# Template Endpoints (Per Consultation Type)
# ============================================================================

@router.get("/templates")
async def get_all_templates(
    request: Request,
    counsellor_id: Optional[str] = Query(None, description="Counsellor ID for junction table filtering"),
    filter_type: Optional[str] = Query(None, description="Filter type: 'admin', 'doctor', 'all', or None (defaults to 'doctor' if counsellor_id provided)"),
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Get all available templates across all consultation types.

    **Filter Types:**
    - 'admin': Only templates created by admin (counsellor_id = NULL)
    - 'doctor': Counsellor's active templates (junction table with is_active=True + owned + global)
    - 'all': All active templates (admin + counsellor-owned, ignores counsellor_id)
    - None: Defaults to 'doctor' behavior if counsellor_id provided, else all templates

    If counsellor_id is NOT provided and no filter_type, returns all templates (admin view).

    **Query Parameters:**
    - `counsellor_id`: Optional counsellor UUID for junction table filtering
    - `filter_type`: Optional filter type ('admin', 'doctor', 'all')

    **Performance Optimization:**
    When filter_type='doctor', uses optimized single-query approach instead of querying per consultation type.

    **EHR Access:**
    EHR clients MUST provide counsellor_id. Admin/Mobile/Web clients can access without.
    """
    try:
        # EHR clients must provide counsellor_id
        require_counsellor_id_for_ehr(request, counsellor_id)

        counsellor_uuid = normalize_counsellor_id(counsellor_id) if counsellor_id else None

        # Run templates + consultation types queries in parallel
        loop = asyncio.get_event_loop()

        templates, consultation_types = await asyncio.gather(
            loop.run_in_executor(
                _template_executor,
                lambda: get_templates(
                    consultation_type_id=None,
                    counsellor_id=counsellor_uuid,
                    filter_type=filter_type,
                )
            ),
            loop.run_in_executor(
                _template_executor,
                lambda: get_consultation_types(include_inactive=False)
            ),
        )

        # Enrich templates with consultation type info
        consultation_type_map = {ct["id"]: ct for ct in consultation_types}
        for template in templates:
            consult_type_id = template.get("consultation_type_id")
            if consult_type_id:
                consult_type = consultation_type_map.get(consult_type_id)
                if consult_type:
                    template["consultation_type_code"] = consult_type["type_code"]
                    template["consultation_type_name"] = consult_type["type_name"]
            else:
                template["consultation_type_code"] = None
                template["consultation_type_name"] = "Universal"

        return {
            "success": True,
            "counsellor_id": counsellor_id,
            "templates": templates,
            "count": len(templates)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch templates")


@router.get("/templates/{consultation_type_code}")
async def get_consultation_templates(
    request: Request,
    consultation_type_code: str,
    counsellor_id: Optional[str] = Query(None, description="Counsellor ID for junction table filtering"),
    filter_type: Optional[str] = Query(None, description="Filter type: 'admin', 'doctor', 'all'"),
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Get available templates for a consultation type with school-based visibility.

    **Filter Types:**
    - `admin`: Only templates created by admin (counsellor_id = NULL)
    - `doctor`: Only templates from templates table with is_active=True (active counsellor templates)
    - `all`: Both admin and counsellor templates (default)
    - None: School-based visibility filtering (if counsellor_id provided)

    **Visibility Rules (if counsellor_id provided and no filter_type):**
    1. Platform-wide common templates (specialization=NULL)
    2. Specialization-specific templates matching counsellor's specialization
    3. School-specific templates created by peers in the same school

    **Path Parameters:**
    - `consultation_type_code`: Consultation type (OP, DISCHARGE, RESPIRATORY)

    **Query Parameters:**
    - `counsellor_id`: Optional counsellor UUID for visibility filtering
    - `filter_type`: Optional filter ('admin', 'doctor', 'all')

    **EHR Access:**
    EHR clients MUST provide counsellor_id. Admin/Mobile/Web clients can access without.
    """
    try:
        # EHR clients must provide counsellor_id
        require_counsellor_id_for_ehr(request, counsellor_id)

        # Get consultation type
        consultation_type = get_consultation_type_by_code(consultation_type_code)
        if not consultation_type:
            raise HTTPException(status_code=404, detail="Consultation type not found")

        consultation_type_id = uuid.UUID(consultation_type["id"])
        counsellor_uuid = normalize_counsellor_id(counsellor_id) if counsellor_id else None

        # Validate counsellor exists when filter_type='doctor' and counsellor_id provided
        if counsellor_uuid and filter_type == 'doctor':
            counsellor_check = supabase.table("counsellors")\
                .select("id")\
                .eq("id", str(counsellor_uuid))\
                .limit(1)\
                .execute()
            if not counsellor_check.data:
                return {
                    "success": True,
                    "consultation_type_code": consultation_type_code,
                    "counsellor_id": counsellor_id,
                    "filter_type": filter_type,
                    "templates": [],
                    "count": 0,
                    "message": "Counsellor does not exist"
                }

        # Get templates based on filter type
        templates = get_templates(
            consultation_type_id=consultation_type_id,
            counsellor_id=counsellor_uuid,
            filter_type=filter_type
        )

        return {
            "success": True,
            "consultation_type_code": consultation_type_code,
            "counsellor_id": counsellor_id,
            "filter_type": filter_type,
            "templates": templates,
            "count": len(templates)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch templates")


@router.post("/templates/{consultation_type_code}/activate/{template_code}")
async def activate_template_endpoint(
    request: Request,
    consultation_type_code: str,
    template_code: str,
    counsellor_id: str = Query(..., description="Counsellor ID"),
    request_body: Optional[Dict[str, Any]] = None,
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Activate a template configuration for a user and consultation type.

    **Path Parameters:**
    - `consultation_type_code`: Consultation type
    - `template_code`: Template code (e.g., 'PSYCHIATRY_CORE', 'FULL_EXTRACTION')

    **Query Parameters:**
    - `counsellor_id`: Counsellor ID (required)

    **Request Body:**
    ```json
    {
      "custom_name": "My Custom Template Name"
    }
    ```

    **Notes:**
    - Counsellors can activate the same template multiple times with different custom names
    - Custom names must be unique per counsellor
    - Custom names are required and cannot be empty
    """
    try:
        # Validate request body
        if not request_body or 'custom_name' not in request_body:
            raise HTTPException(status_code=400, detail="Missing 'custom_name' in request body")

        custom_name = request_body['custom_name'].strip()
        if not custom_name:
            raise HTTPException(status_code=400, detail="Custom name cannot be empty")

        # Get consultation type
        consultation_type = get_consultation_type_by_code(consultation_type_code)
        if not consultation_type:
            raise HTTPException(status_code=404, detail="Consultation type not found")

        # Get Template
        template = get_template_by_code(template_code)

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        counsellor_uuid = normalize_counsellor_id(counsellor_id)
        template_id = uuid.UUID(template["id"])
        consultation_type_id = uuid.UUID(consultation_type["id"])

        # Clone template with custom name (creates counsellor-owned template)
        cloned_template = clone_template(
            source_template_id=template_id,
            counsellor_id=counsellor_uuid,
            new_template_name=custom_name,
            new_template_code=f"{template['template_code']}_CLONE_{counsellor_uuid}"[:50]
        )

        cloned_template_id = uuid.UUID(cloned_template["id"])

        # Activate cloned template for counsellor
        activation_result = activate_template_for_counsellor(
            counsellor_id=counsellor_uuid,
            template_id=cloned_template_id,
            consultation_type_id=consultation_type_id
        )

        return {
            "success": True,
            "message": f"Template '{custom_name}' cloned and activated for {consultation_type_code}",
            "template": strip_internal_template_fields(template),
            "cloned_template": strip_internal_template_fields(cloned_template),
            "activation": activation_result
        }

    except ValueError as e:
        # Handle duplicate name error
        raise HTTPException(status_code=400, detail="Invalid request")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Template activation failed")


@router.put("/templates/instances/{active_template_id}/rename")
async def rename_template_instance(
    request: Request,
    active_template_id: str,
    counsellor_id: str = Query(..., description="Counsellor ID"),
    request_body: Optional[Dict[str, Any]] = None,
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Rename a specific activated template instance for a counsellor.

    **Path Parameters:**
    - `active_template_id`: Template ID (UUID from templates table)

    **Query Parameters:**
    - `counsellor_id`: Counsellor ID (required)

    **Request Body:**
    ```json
    {
        "new_name": "My Custom Template Name"
    }
    ```

    **Returns:**
    - Updated template instance information

    **Notes:**
    - Since counsellors can have multiple instances of the same template, we use the instance ID
    - New name must be unique across all of counsellor's activated templates
    """
    try:
        from services.supabase_service import supabase, check_template_name_available
        import uuid

        # Validate request body
        if not request_body or 'new_name' not in request_body:
            raise HTTPException(status_code=400, detail="Missing 'new_name' in request body")

        new_name = request_body['new_name'].strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Template name cannot be empty")

        # Normalize IDs
        try:
            counsellor_uuid = uuid.UUID(counsellor_id)
            instance_uuid = uuid.UUID(active_template_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ID format")

        # Check if new name is available (excluding current template)
        if not check_template_name_available(counsellor_uuid, new_name, exclude_template_id=instance_uuid):
            raise HTTPException(
                status_code=400,
                detail="A template with this name already exists for this counsellor"
            )

        # Update template name in templates table
        response = (
            supabase.table("templates")
            .update({"template_name": new_name})
            .eq("id", str(instance_uuid))
            .eq("counsellor_id", str(counsellor_uuid))
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=404,
                detail="Template instance not found or does not belong to this counsellor"
            )

        return {
            "success": True,
            "message": f"Template renamed to '{new_name}'",
            "instance": response.data[0]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to rename template")


# ============================================================================
# Template Admin Endpoints (CRUD Operations)
# ============================================================================

@router.post("/admin/templates")
async def create_new_template(
    request: CreateTemplateRequest,
    counsellor_id: Optional[str] = Query(None, description="Counsellor creating the template"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Create a new template (Admin).

    **Features:**
    - Create template with metadata
    - Optionally inherit segment configuration from consultation type defaults
    - Or configure segments manually later

    **Request Body:**
    ```json
    {
        "template_code": "PSYCHIATRY_CORE",
        "template_name": "Psychiatry Standard - Core Only",
        "description": "Optimized for quick psychiatry consultations",
        "consultation_type_code": "OP",
        "use_case": "quick_consultation",
        "specialization": "psychiatry",
        "inherit_from_consultation_type": true
    }
    ```
    """
    try:
        # Get consultation type
        consultation_type = get_consultation_type_by_code(request.consultation_type_code)
        if not consultation_type:
            raise HTTPException(
                status_code=404,
                detail="Consultation type not found"
            )

        consultation_type_id = uuid.UUID(consultation_type["id"])

        # Parse optional UUIDs
        school_uuid = uuid.UUID(request.school_id) if request.school_id else None
        # Only use counsellor_id if it's a valid UUID (admin users like "admin-user-1" create global templates with NULL counsellor_id)
        from services.uuid_utils import is_valid_uuid
        counsellor_uuid = uuid.UUID(counsellor_id) if counsellor_id and is_valid_uuid(counsellor_id) else None

        # ⭐ Validate template_code is unique (for counsellor-owned or common templates)
        from services.supabase_service import check_template_code_available
        if not check_template_code_available(counsellor_uuid, request.template_code):
            raise HTTPException(
                status_code=400,
                detail="Template code is already in use. Please choose a different code."
            )

        # Create template
        template = create_template(
            template_code=request.template_code,
            template_name=request.template_name,
            description=request.description,
            consultation_type_id=consultation_type_id,
            use_case=request.use_case,
            specialization=request.specialization,
            school_id=school_uuid,
            counsellor_id=counsellor_uuid,  # ⭐ Now using counsellor_id from query param
            estimated_extraction_time_seconds=request.estimated_extraction_time_seconds,
            is_active=request.is_active
        )

        template_id = uuid.UUID(template["id"])

        # Handle inheritance - new style (inherit_from_type + inherit_from_id)
        if request.inherit_from_type and request.inherit_from_id:
            from services.supabase_service import inherit_from_template

            if request.inherit_from_type == "consultation_type":
                # Look up the source consultation type to inherit FROM (may differ from template's target type)
                source_consultation_type = get_consultation_type_by_code(request.inherit_from_id)
                if not source_consultation_type:
                    raise HTTPException(
                        status_code=404,
                        detail="Source consultation type not found for inheritance"
                    )
                source_consultation_type_id = uuid.UUID(source_consultation_type["id"])

                logger.info(f"[CREATE_TEMPLATE] Inheriting segments from consultation type: {request.inherit_from_id} (ID: {source_consultation_type_id})")

                segments = inherit_from_consultation_type(
                    template_id=template_id,
                    consultation_type_id=source_consultation_type_id  # Use the SOURCE type, not the target
                )
                # Invalidate template cache
                invalidate_template_cache(template_code=request.template_code)
                return {
                    "success": True,
                    "message": f"Template '{request.template_code}' created with inherited configuration from '{request.inherit_from_id}'",
                    "template": strip_internal_template_fields(template),
                    "segments_configured": len(segments)
                }
            elif request.inherit_from_type == "template":
                segments = inherit_from_template(
                    target_template_id=template_id,
                    source_template_code=request.inherit_from_id
                )
                # Invalidate template cache
                invalidate_template_cache(template_code=request.template_code)
                return {
                    "success": True,
                    "message": f"Template '{request.template_code}' created with inherited configuration from template '{request.inherit_from_id}'",
                    "template": strip_internal_template_fields(template),
                    "segments_configured": len(segments)
                }

        # Handle inheritance - old style (backwards compatibility)
        elif request.inherit_from_consultation_type:
            segments = inherit_from_consultation_type(
                template_id=template_id,
                consultation_type_id=consultation_type_id
            )

            # Invalidate template cache
            invalidate_template_cache(template_code=request.template_code)
            return {
                "success": True,
                "message": f"Template '{request.template_code}' created with inherited configuration from consultation type",
                "template": strip_internal_template_fields(template),
                "segments_configured": len(segments)
            }

        # Invalidate template cache
        invalidate_template_cache(template_code=request.template_code)
        return {
            "success": True,
            "message": f"Template '{request.template_code}' created (configure segments manually)",
            "template": strip_internal_template_fields(template)
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Template creation failed")


class ImportTemplateFromSourceRequest(BaseModel):
    source_template_code: str = Field(..., description="template_code on the source DB")


@router.get("/admin/templates/import-source/list")
async def list_source_templates_endpoint(
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """List templates available on the configured source Supabase project."""
    from services.template_import_service import list_source_templates
    try:
        rows = list_source_templates()
        return {"success": True, "templates": rows, "count": len(rows)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[TEMPLATE_IMPORT] list_source_templates failed")
        raise HTTPException(status_code=500, detail="Failed to list source templates")


@router.post("/admin/templates/import-from-source")
async def import_template_from_source_endpoint(
    payload: ImportTemplateFromSourceRequest,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """Import a template (and its dependency graph) from the source DB to the target DB."""
    from services.template_import_service import import_template_from_source
    try:
        result = import_template_from_source(payload.source_template_code)
        # Invalidate template cache for the freshly imported code
        invalidate_template_cache(template_code=result["template_code"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[TEMPLATE_IMPORT] import_template_from_source failed")
        raise HTTPException(status_code=500, detail="Template import failed")


@router.put("/admin/templates/{template_code}")
async def update_template_endpoint(
    template_code: str,
    request: UpdateTemplateRequest,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Update template metadata (Admin).

    **Path Parameters:**
    - `template_code`: Template code to update

    **Request Body:**
    ```json
    {
        "template_name": "New Template Name",
        "description": "Updated description",
        "specialization": "cardiology",
        "estimated_extraction_time_seconds": 35.5
    }
    ```
    """
    try:
        template = update_template(
            template_code=template_code,
            template_name=request.template_name,
            description=request.description,
            use_case=request.use_case,
            specialization=request.specialization,
            estimated_extraction_time_seconds=request.estimated_extraction_time_seconds
        )

        # Invalidate template cache
        invalidate_template_cache(template_code=template_code)

        return {
            "success": True,
            "message": f"Template '{template_code}' updated successfully",
            "template": strip_internal_template_fields(template)
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Template update failed")


@router.delete("/admin/templates/{template_code}")
async def delete_template_endpoint(
    template_code: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Delete a template (Admin - soft delete).

    **Path Parameters:**
    - `template_code`: Template code to delete

    **Note:** Default templates cannot be deleted.
    """
    try:
        delete_template(template_code)

        # Invalidate template cache
        invalidate_template_cache(template_code=template_code)

        return {
            "success": True,
            "message": f"Template '{template_code}' deleted successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Template deletion failed")


@router.delete("/admin/segments/{segment_id}")
async def delete_segment_endpoint(
    segment_id: str = Path(..., description="Segment ID to delete"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Delete a segment definition (Admin - soft delete).

    **Path Parameters:**
    - `segment_id`: Segment ID (UUID) to delete

    **Note:**
    - Required segments cannot be deleted
    - Common segments cannot be deleted (shared across all consultation types)

    **Example:**
    ```
    DELETE /api/v1/summary/admin/segments/439118b8-8bfb-4b14-b7a7-4e4c65b6e8a1
    ```
    """
    try:
        delete_segment(segment_id)

        return {
            "success": True,
            "message": f"Segment deleted successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Segment deletion failed")


@router.delete("/admin/consultation-types/{consultation_type_code}")
async def delete_consultation_type_endpoint(
    consultation_type_code: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Delete a consultation type (Admin - soft delete).

    **Path Parameters:**
    - `consultation_type_code`: Consultation type code to delete

    **Note:** Default consultation types (OP, DISCHARGE, RESPIRATORY) cannot be deleted.

    **Example:**
    ```
    DELETE /api/v1/summary/admin/consultation-types/CUSTOM_TYPE
    ```
    """
    try:
        delete_consultation_type(consultation_type_code)

        # Invalidate consultation_type cache
        invalidate_consultation_type_cache(type_code=consultation_type_code)

        return {
            "success": True,
            "message": f"Consultation type '{consultation_type_code}' deleted successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Consultation type deletion failed")


# ============================================================================
# REACTIVATE ENDPOINTS (Restore soft-deleted entities)
# ============================================================================

@router.post("/admin/templates/{template_code}/reactivate")
async def reactivate_template_endpoint(
    template_code: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Reactivate a soft-deleted template (set is_active = true).

    **Path Parameters:**
    - `template_code`: Template code to reactivate
    """
    try:
        reactivate_template(template_code)

        # Invalidate template cache
        invalidate_template_cache(template_code=template_code)

        return {
            "success": True,
            "message": f"Template '{template_code}' reactivated successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Template reactivation failed")


@router.post("/admin/segments/{segment_id}/reactivate")
async def reactivate_segment_endpoint(
    segment_id: str = Path(..., description="Segment ID to reactivate"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Reactivate a soft-deleted segment (set is_active = true).

    **Path Parameters:**
    - `segment_id`: Segment ID (UUID) to reactivate
    """
    try:
        reactivate_segment(segment_id)

        return {
            "success": True,
            "message": f"Segment reactivated successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Segment reactivation failed")


@router.post("/admin/consultation-types/{consultation_type_code}/reactivate")
async def reactivate_consultation_type_endpoint(
    consultation_type_code: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Reactivate a soft-deleted consultation type (set is_active = true).

    **Path Parameters:**
    - `consultation_type_code`: Consultation type code to reactivate
    """
    try:
        reactivate_consultation_type(consultation_type_code)

        # Invalidate consultation_type cache
        invalidate_consultation_type_cache(type_code=consultation_type_code)

        return {
            "success": True,
            "message": f"Consultation type '{consultation_type_code}' reactivated successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Consultation type reactivation failed")


@router.get("/admin/templates/{template_code}/segments")
async def get_template_segments(
    template_code: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get segment configuration for a template (Admin).

    **Path Parameters:**
    - `template_code`: Template code

    **Returns:**
    - List of segment configurations for the template
    """
    try:
        template = get_template_by_code(template_code)

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        template_id = uuid.UUID(template["id"])

        segments = get_template_configuration(template_id)

        return {
            "success": True,
            "template_code": template_code,
            "template_name": template["template_name"],
            "segments": segments,
            "count": len(segments)
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = {
            "message": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }
        logger.error(f"[TEMPLATE_SEGMENTS] Error fetching segments for template '{template_code}': {error_detail}")
        raise HTTPException(status_code=500, detail="Failed to fetch template segments")


@router.put("/admin/templates/{template_code}/segments/{segment_code}")
async def update_template_segment(
    template_code: str,
    segment_code: str,
    config: TemplateSegmentConfigUpdate,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Update a segment configuration for a template (Admin).

    **Path Parameters:**
    - `template_code`: Template code
    - `segment_code`: Segment code to update

    **Request Body:**
    ```json
    {
        "category": "core",
        "display_order": 1,
        "brevity_level": "balanced",
        "terminology_style": "medical_terms"
    }
    ```
    """
    try:
        template = get_template_by_code(template_code)

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        template_id = uuid.UUID(template["id"])

        result = update_template_segment_config(
            template_id=template_id,
            segment_code=segment_code,
            category=config.category,
            display_order=config.display_order,
            brevity_level=config.brevity_level,
            terminology_style=config.terminology_style
        )

        return {
            "success": True,
            "message": f"Segment '{segment_code}' updated for template '{template_code}'",
            "configuration": result
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Segment update failed")


@router.post("/admin/templates/{template_code}/segments/bulk")
async def bulk_update_segments(
    template_code: str,
    request: BulkSegmentUpdate,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Bulk update segment configurations for a template (Admin).

    **Path Parameters:**
    - `template_code`: Template code

    **Request Body:**
    ```json
    {
        "segments": [
            {
                "segment_code": "DIAGNOSIS",
                "category": "core",
                "display_order": 1,
                "brevity_level": "balanced",
                "terminology_style": "medical_terms"
            },
            // ... more segments
        ]
    }
    ```
    """
    try:
        template = get_template_by_code(template_code)

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        template_id = uuid.UUID(template["id"])

        results = bulk_update_template_segments(
            template_id=template_id,
            segments=request.segments
        )

        return {
            "success": True,
            "message": f"Bulk updated {len(results)} segments for template '{template_code}'",
            "configurations": results
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Bulk update failed")


@router.post("/admin/templates/{template_code}/inherit")
async def inherit_configuration(
    template_code: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Inherit segment configuration from consultation type defaults (Admin).

    This replaces all existing segment configurations for the template
    with the default configuration from the consultation type.

    **Path Parameters:**
    - `template_code`: Template code

    **Warning:** This will delete all existing segment configurations for the template.
    """
    try:
        template = get_template_by_code(template_code)

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        template_id = uuid.UUID(template["id"])
        consultation_type_id = uuid.UUID(template["consultation_type_id"])

        segments = inherit_from_consultation_type(
            template_id=template_id,
            consultation_type_id=consultation_type_id
        )

        return {
            "success": True,
            "message": f"Template '{template_code}' inherited configuration from consultation type",
            "segments_configured": len(segments),
            "segments": segments
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Inheritance failed")


# REMOVED: POST /segments/reset
# Reason: doctor_segment_configurations table removed in migration 20251123000000
# Use: POST /admin/templates/{template_code}/inherit to re-inherit from consultation type defaults
# Or: Delete template and create new one from consultation type


# ============================================================================
# Field-level config: gap analysis + empty-payload trim (Admin)
# Drives the public EHR endpoints:
#   GET /api/v1/ehr/extraction-gaps/{extraction_id}  (gap_analysis_fields_json)
#   GET /api/v1/ehr/template-schema                  (include_in_empty_payload)
# ============================================================================


class SegmentFieldConfigUpdate(BaseModel):
    gap_analysis_fields_json: Optional[List[str]] = None
    include_in_empty_payload: Optional[bool] = None


class BulkSegmentFieldConfigUpdate(BaseModel):
    segments: List[Dict[str, Any]]


@router.get("/admin/templates/{template_code}/field-config")
async def get_template_field_config(
    template_code: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    from services.supabase_service import supabase
    from services.gap_analysis_service import (
        classify_segment_shape,
        default_leaves_for_shape,
        walk_schema_leaves,
    )

    template = get_template_by_code(template_code)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    template_id = template["id"]

    result = supabase.table("template_segments").select(
        "id, category, display_order, gap_analysis_fields_json, include_in_empty_payload, "
        "segment_definitions!inner(id, segment_code, segment_name, schema_definition_json, is_active)"
    ).eq("template_id", str(template_id)).execute()

    segments = []
    for row in (result.data or []):
        seg_def = row.get("segment_definitions") or {}
        if not seg_def.get("is_active", True):
            continue
        schema = seg_def.get("schema_definition_json") or {}
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except Exception:
                schema = {}

        shape = classify_segment_shape(schema)
        schema_leaves = walk_schema_leaves(schema) if schema else []
        default_leaves = default_leaves_for_shape(shape, schema)
        segments.append({
            "segment_code": seg_def.get("segment_code", ""),
            "segment_name": seg_def.get("segment_name", ""),
            "category": row.get("category", "additional"),
            "display_order": row.get("display_order", 999),
            "shape": shape,
            "schema_leaves": schema_leaves,
            "default_leaves": default_leaves,
            "gap_analysis_fields_json": row.get("gap_analysis_fields_json"),
            "include_in_empty_payload": row.get("include_in_empty_payload"),
        })

    segments.sort(key=lambda s: s["display_order"])

    return {
        "success": True,
        "template_code": template_code,
        "template_name": template.get("template_name", template_code),
        "segments": segments,
        "count": len(segments),
    }


@router.put("/admin/templates/{template_code}/field-config/{segment_code}")
async def update_segment_field_config(
    template_code: str,
    segment_code: str,
    config: SegmentFieldConfigUpdate,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    from services.supabase_service import supabase

    template = get_template_by_code(template_code)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    payload = config.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Match on template_segments.segment_code (denormalized) scoped by template_id.
    # segment_definitions.segment_code is not unique, so looking up segment_id
    # globally by segment_code can pick the wrong row.
    update_result = supabase.table("template_segments").update(payload)\
        .eq("template_id", template["id"])\
        .eq("segment_code", segment_code)\
        .execute()

    if not update_result.data:
        raise HTTPException(status_code=404, detail="template_segments row not found for this template+segment")

    return {
        "success": True,
        "template_code": template_code,
        "segment_code": segment_code,
        "configuration": update_result.data[0],
    }


@router.post("/admin/templates/{template_code}/field-config/bulk")
async def bulk_update_template_field_config(
    template_code: str,
    request: BulkSegmentFieldConfigUpdate,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    from services.supabase_service import supabase

    template = get_template_by_code(template_code)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if not request.segments:
        raise HTTPException(status_code=400, detail="No segments provided")

    updated = []
    errors = []
    for item in request.segments:
        segment_code = item.get("segment_code")
        if not segment_code:
            errors.append({"item": item, "error": "segment_code missing"})
            continue

        payload = {k: v for k, v in item.items() if k in ("gap_analysis_fields_json", "include_in_empty_payload")}
        if not payload:
            continue

        # Match on template_segments.segment_code (denormalized) scoped by
        # template_id — segment_definitions.segment_code is not unique globally.
        res = supabase.table("template_segments").update(payload)\
            .eq("template_id", template["id"])\
            .eq("segment_code", segment_code)\
            .execute()
        if res.data:
            updated.extend(res.data)
        else:
            errors.append({"segment_code": segment_code, "error": "template_segments row not found"})

    return {
        "success": True,
        "template_code": template_code,
        "updated": updated,
        "update_count": len(updated),
        "errors": errors,
    }


# ============================================================================
# Counsellor Template Segment Configuration (EHR-authenticated)
# These endpoints are for counsellors to configure their own templates via EHR integration
# ============================================================================

@router.get("/counsellor/templates/{template_code}/segments")
async def get_counsellor_template_segments(
    request: Request,
    template_code: str,
    counsellor_id: str = Query(..., description="Counsellor ID for EHR access verification"),
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Get segment configuration for a counsellor's template (EHR-authenticated).

    **Path Parameters:**
    - `template_code`: Template code

    **Query Parameters:**
    - `counsellor_id`: Counsellor ID for EHR access verification

    **Returns:**
    - List of segment configurations for the template
    """
    try:
        template = get_template_by_code(template_code)

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        template_id = uuid.UUID(template["id"])

        segments = get_template_configuration(template_id)

        return {
            "success": True,
            "template_code": template_code,
            "template_name": template["template_name"],
            "segments": segments,
            "count": len(segments)
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = {
            "message": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }
        logger.error(f"[DOCTOR_TEMPLATE_SEGMENTS] Error fetching segments for template '{template_code}': {error_detail}")
        raise HTTPException(status_code=500, detail="Failed to fetch template segments")


@router.put("/counsellor/templates/{template_code}/segments/{segment_code}")
async def update_counsellor_template_segment(
    request: Request,
    template_code: str,
    segment_code: str,
    config: TemplateSegmentConfigUpdate,
    counsellor_id: str = Query(..., description="Counsellor ID for EHR access verification"),
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Update a segment configuration for a counsellor's template (EHR-authenticated).

    **Path Parameters:**
    - `template_code`: Template code
    - `segment_code`: Segment code to update

    **Query Parameters:**
    - `counsellor_id`: Counsellor ID for EHR access verification

    **Request Body:**
    ```json
    {
        "category": "core",
        "display_order": 1,
        "brevity_level": "balanced",
        "terminology_style": "medical_terms"
    }
    ```
    """
    try:
        template = get_template_by_code(template_code)

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        template_id = uuid.UUID(template["id"])

        result = update_template_segment_config(
            template_id=template_id,
            segment_code=segment_code,
            category=config.category,
            display_order=config.display_order,
            brevity_level=config.brevity_level,
            terminology_style=config.terminology_style
        )

        return {
            "success": True,
            "message": f"Updated segment '{segment_code}' for template '{template_code}'",
            "configuration": result
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Segment update failed")


@router.post("/counsellor/templates/{template_code}/segments/bulk")
async def bulk_update_counsellor_segments(
    request: Request,
    template_code: str,
    bulk_request: BulkSegmentUpdate,
    counsellor_id: str = Query(..., description="Counsellor ID for EHR access verification"),
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Bulk update segment configurations for a counsellor's template (EHR-authenticated).

    **Path Parameters:**
    - `template_code`: Template code

    **Query Parameters:**
    - `counsellor_id`: Counsellor ID for EHR access verification

    **Request Body:**
    ```json
    {
        "segments": [
            {
                "segment_code": "DIAGNOSIS",
                "category": "core",
                "display_order": 1,
                "brevity_level": "balanced",
                "terminology_style": "medical_terms"
            }
        ]
    }
    ```
    """
    try:
        template = get_template_by_code(template_code)

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        template_id = uuid.UUID(template["id"])

        results = bulk_update_template_segments(
            template_id=template_id,
            segments=bulk_request.segments
        )

        return {
            "success": True,
            "message": f"Bulk updated {len(results)} segments for template '{template_code}'",
            "configurations": results
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Bulk update failed")


@router.post("/counsellor/templates/{template_code}/inherit")
async def inherit_counsellor_configuration(
    request: Request,
    template_code: str,
    counsellor_id: str = Query(..., description="Counsellor ID for EHR access verification"),
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Inherit segment configuration from consultation type defaults (EHR-authenticated).

    This replaces all existing segment configurations for the template
    with the default configuration from the consultation type.

    **Path Parameters:**
    - `template_code`: Template code

    **Query Parameters:**
    - `counsellor_id`: Counsellor ID for EHR access verification

    **Warning:** This will delete all existing segment configurations for the template.
    """
    try:
        template = get_template_by_code(template_code)

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        template_id = uuid.UUID(template["id"])
        consultation_type_id = uuid.UUID(template["consultation_type_id"])

        segments = inherit_from_consultation_type(
            template_id=template_id,
            consultation_type_id=consultation_type_id
        )

        return {
            "success": True,
            "message": f"Template '{template_code}' inherited configuration from consultation type",
            "segments_configured": len(segments),
            "segments": segments
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Inheritance failed")


# ============================================================================
# Validation Endpoint
# ============================================================================

@router.get("/segments/validate")
async def validate_config(
    request: Request,
    counsellor_id: str = Query(..., description="Counsellor ID"),
    _auth = Depends(verify_counsellor_access)
) -> Dict[str, Any]:
    """
    Validate counsellor's segment configuration for clinical safety.

    **Query Parameters:**
    - `counsellor_id`: Counsellor ID (required)

    **Returns:**
    - Validation result with any errors or warnings
    """
    try:
        counsellor_uuid = normalize_counsellor_id(counsellor_id)

        validation = validate_segment_configuration(counsellor_uuid)

        return {
            "success": True,
            "validation": validation
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Validation failed")

# NOTE: /extract-split endpoint removed - was unused legacy endpoint.
# The main /extract endpoint handles progressive extraction (CORE then ADDITIONAL) when needed.


# ============================================================================
# Consultation Type Segment Configuration (Admin)
# ============================================================================

@router.get("/admin/consultation-types/{consultation_type_code}/segments")
async def get_consultation_type_segment_definitions(
    consultation_type_code: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get all segment definitions for a consultation type (Admin).

    This returns the base segment definitions that templates can inherit from.
    **Includes excluded segments** for admin UI management.

    **Path Parameters:**
    - `consultation_type_code`: Consultation type code (OP, DISCHARGE, RESPIRATORY)

    **Returns:**
    - List of segment definitions with full details including prompt text and schemas
    - Includes segments with default_category='excluded' for admin management

    **Example:**
    ```
    GET /api/v1/summary/admin/consultation-types/OP/segments
    ```
    """
    try:
        # Admin endpoint includes excluded segments for UI management
        segments = get_consultation_type_segments(consultation_type_code, include_excluded=True)

        return {
            "success": True,
            "consultation_type_code": consultation_type_code,
            "segments": segments,
            "count": len(segments)
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get segments")


@router.put("/admin/consultation-types/{consultation_type_code}/segments/{segment_code}")
async def update_consultation_type_segment_definition(
    consultation_type_code: str,
    segment_code: str,
    config: ConsultationTypeSegmentUpdate,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Update a segment definition for a consultation type (Admin).

    This updates the base definition that templates inherit from.

    **Path Parameters:**
    - `consultation_type_code`: Consultation type code (OP, DISCHARGE, RESPIRATORY)
    - `segment_code`: Segment code to update (e.g., 'DIAGNOSIS')

    **Body:**
    - Any combination of segment definition fields to update

    **Returns:**
    - Updated segment definition

    **Example:**
    ```json
    PUT /api/v1/summary/admin/consultation-types/OP/segments/DIAGNOSIS
    {
        "segment_name": "Primary Diagnosis",
        "default_category": "core",
        "display_order": 1,
        "default_brevity_level": "balanced",
        "is_required": true
    }
    ```
    """
    try:
        updated_segment = update_consultation_type_segment(
            consultation_type_code=consultation_type_code,
            segment_code=segment_code,
            segment_name=config.segment_name,
            default_category=config.default_category,
            display_order=config.display_order,
            default_brevity_level=config.default_brevity_level,
            default_terminology_style=config.default_terminology_style,
            prompt_section_text=config.prompt_section_text,
            schema_definition_json=config.schema_definition_json,
            is_required=config.is_required
        )

        return {
            "success": True,
            "message": f"Segment '{segment_code}' updated successfully",
            "segment": updated_segment
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update segment")


@router.post("/admin/consultation-types/{consultation_type_code}/segments/bulk")
async def bulk_update_consultation_type_segment_definitions(
    consultation_type_code: str,
    request: BulkSegmentUpdate,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Bulk update segment definitions for a consultation type (Admin).

    This allows updating multiple segment definitions at once.

    **Path Parameters:**
    - `consultation_type_code`: Consultation type code (OP, DISCHARGE, RESPIRATORY)

    **Body:**
    ```json
    {
        "segments": [
            {
                "segment_code": "DIAGNOSIS",
                "segment_name": "Primary Diagnosis",
                "default_category": "core",
                "display_order": 1
            },
            {
                "segment_code": "PRESCRIPTION",
                "default_brevity_level": "detailed",
                "display_order": 6
            }
        ]
    }
    ```

    **Returns:**
    - List of updated segment definitions
    """
    try:
        updated_segments = bulk_update_consultation_type_segments(
            consultation_type_code=consultation_type_code,
            segments=request.segments
        )

        return {
            "success": True,
            "message": f"{len(updated_segments)} segments updated successfully",
            "segments": updated_segments,
            "count": len(updated_segments)
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Bulk update failed")


# =============================================================================
# Admin - Get All Segments
# =============================================================================

@router.get("/admin/segments")
async def get_all_segment_definitions(
    consultation_type_code: Optional[str] = None,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get all segment definitions across all consultation types (Admin).

    **JUNCTION TABLE ARCHITECTURE**: All segments retrieved via consultation_type_segments.

    Query Parameters:
    - consultation_type_code (optional): Filter by consultation type (OP, DISCHARGE, RESPIRATORY)

    Example:
        GET /api/v1/summary/admin/segments
        GET /api/v1/summary/admin/segments?consultation_type_code=OP

    Returns:
        {
            "success": true,
            "segments": [...],
            "count": 42
        }
    """
    try:
        from services.supabase_service import get_all_segments

        segments = get_all_segments(
            consultation_type_code=consultation_type_code
        )

        return {
            "success": True,
            "segments": segments,
            "count": len(segments)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch segments")


# =============================================================================
# Admin - Create Segment Definition
# =============================================================================

class CreateSegmentRequest(BaseModel):
    segment_code: str
    segment_name: str
    consultation_type_code: Optional[str] = None  # Required if not template-specific
    template_code: Optional[str] = None  # For template-specific segments
    prompt_section_text: str
    schema_definition_json: Dict[str, Any]
    default_category: str = "core"
    display_order: int = 999
    default_brevity_level: str = "balanced"
    default_terminology_style: str = "medical_terms"
    is_required: bool = False


@router.post("/admin/segments")
async def create_segment(
    request: CreateSegmentRequest,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Create a new segment definition (Admin).

    **JUNCTION TABLE ARCHITECTURE**: Segment created in master table, then linked via junction tables.

    Body:
        {
            "segment_code": "NEW_SEGMENT_OP",
            "segment_name": "New Segment",
            "consultation_type_code": "OP",
            "prompt_section_text": "Extract new segment...",
            "schema_definition_json": {...},
            "default_category": "core",
            "display_order": 10,
            "default_brevity_level": "balanced",
            "default_terminology_style": "medical_terms",
            "is_required": false
        }

    Returns:
        {
            "success": true,
            "segment": {...}
        }
    """
    try:
        from services.supabase_service import create_segment_definition

        # Validation: Must specify either consultation_type_code or template_code
        if not request.consultation_type_code and not request.template_code:
            raise ValueError("Must specify either consultation_type_code or template_code")

        if request.template_code and request.consultation_type_code:
            raise ValueError("Cannot specify both template_code and consultation_type_code")

        segment = create_segment_definition(
            segment_code=request.segment_code,
            segment_name=request.segment_name,
            consultation_type_code=request.consultation_type_code,
            template_code=request.template_code,
            prompt_section_text=request.prompt_section_text,
            schema_definition_json=request.schema_definition_json,
            default_category=request.default_category,
            display_order=request.display_order,
            default_brevity_level=request.default_brevity_level,
            default_terminology_style=request.default_terminology_style,
            is_required=request.is_required
        )

        return {
            "success": True,
            "segment": segment
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create segment")


# =============================================================================
# Admin - Update Segment Definition
# =============================================================================

class UpdateSegmentRequest(BaseModel):
    segment_name: Optional[str] = None
    prompt_section_text: Optional[str] = None
    schema_definition_json: Optional[Dict[str, Any]] = None
    default_category: Optional[str] = None
    display_order: Optional[int] = None
    default_brevity_level: Optional[str] = None
    default_terminology_style: Optional[str] = None
    is_required: Optional[bool] = None


@router.put("/admin/segments/{segment_id}")
async def update_segment(
    segment_id: str,
    request: UpdateSegmentRequest,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Update a segment definition (Admin).

    **JUNCTION TABLE ARCHITECTURE**: Updates master segment_definitions table only.

    Path Parameters:
    - segment_id: Segment UUID to update (unique identifier)

    Body (all fields optional):
        {
            "segment_name": "Updated Name",
            "prompt_section_text": "Updated prompt...",
            "schema_definition_json": {...},
            "default_category": "additional",
            "display_order": 20,
            "default_brevity_level": "detailed",
            "default_terminology_style": "simple_terms",
            "is_required": true
        }

    Returns:
        {
            "success": true,
            "segment": {...}
        }
    """
    try:
        from services.supabase_service import update_segment_definition

        segment = update_segment_definition(
            segment_id=segment_id,
            segment_name=request.segment_name,
            prompt_section_text=request.prompt_section_text,
            schema_definition_json=request.schema_definition_json,
            default_category=request.default_category,
            display_order=request.display_order,
            default_brevity_level=request.default_brevity_level,
            default_terminology_style=request.default_terminology_style,
            is_required=request.is_required
        )

        # Trigger template reassembly for emotion segments
        segment_code = segment.get('segment_code', '')
        if segment_code.startswith('AUDIO_'):
            try:
                from services.template_assembly_service import on_audio_segment_updated
                on_audio_segment_updated(segment_code, 'update')
                logger.info(f"[SEGMENT_UPDATE] Triggered audio reassembly for {segment_code}")
            except Exception as e:
                logger.warning(f"[SEGMENT_UPDATE] Failed to trigger audio reassembly for {segment_code}: {e}")
        elif segment_code.startswith('COMBINED_'):
            try:
                from services.template_assembly_service import on_combined_segment_updated
                on_combined_segment_updated(segment_code, 'update')
                logger.info(f"[SEGMENT_UPDATE] Triggered combined emotion reassembly for {segment_code}")
            except Exception as e:
                logger.warning(f"[SEGMENT_UPDATE] Failed to trigger combined emotion reassembly for {segment_code}: {e}")

        return {
            "success": True,
            "segment": segment
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update segment")


# ============================================================================
# Segment Parent Tracking - Middle-Ground Approach
# ============================================================================

class CloneSegmentRequest(BaseModel):
    """Request model for cloning a segment"""
    parent_segment_code: str = Field(..., description="Segment code to clone from")
    source_consultation_type_id: str = Field(..., description="Consultation type ID where the parent segment is defined (required for proper lookup)")
    new_segment_code: str = Field(..., max_length=50, description="Code for the new segment")
    new_segment_name: str = Field(..., max_length=255, description="Display name for the new segment")
    consultation_type_id: Optional[str] = Field(None, description="Consultation type ID for the new segment (NULL for common)")
    template_id: Optional[str] = Field(None, description="Template ID if this is template-specific")
    # Optional overrides - if provided, use these instead of copying from parent
    prompt_section_text: Optional[str] = Field(None, description="Custom prompt text (if not provided, copies from parent)")
    schema_definition_json: Optional[Dict[str, Any]] = Field(None, description="Custom schema JSON (if not provided, copies from parent)")


class PropagateChangesRequest(BaseModel):
    """Request model for propagating changes from parent to children"""
    segment_codes: List[str] = Field(..., description="List of child segment codes to update")
    force_update_diverged: bool = Field(False, description="If TRUE, update even diverged segments")


@router.post("/admin/segments/clone")
async def clone_segment(
    request: CloneSegmentRequest,
    admin_id: str = Query(..., description="Admin ID performing the clone"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Clone an existing segment to create a new one with parent tracking.

    **Use case:** Create DIAGNOSIS_CARDIOLOGY based on DIAGNOSIS

    **Request Body:**
    - parent_segment_code: Segment to clone from (e.g., 'DIAGNOSIS')
    - new_segment_code: New segment code (e.g., 'DIAGNOSIS_CARDIOLOGY')
    - new_segment_name: Display name (e.g., 'Diagnosis (Cardiology)')
    - consultation_type_id: Optional consultation type for the new segment
    - template_id: Optional template if this is template-specific

    **Actions:**
    - Copies prompt_section_text and schema_definition_json from parent
    - Sets parent_segment_code, is_cloned_from_parent, cloned_at
    - Creates new segment with same defaults as parent
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.debug(f"[CLONE_SEGMENT] Starting clone request: parent={request.parent_segment_code}, new={request.new_segment_code}, admin_id={admin_id}")
        logger.debug(f"[CLONE_SEGMENT] Request data: source_ct_id={request.source_consultation_type_id}, target_ct_id={request.consultation_type_id}, template_id={request.template_id}")
        logger.debug(f"[CLONE_SEGMENT] consultation_type_id type: {type(request.consultation_type_id)}, value: '{request.consultation_type_id}', is None: {request.consultation_type_id is None}")

        from services.supabase_service import clone_segment_with_parent_tracking, supabase

        logger.debug(f"[CLONE_SEGMENT] Normalizing admin_id: {admin_id}")
        admin_uuid = normalize_counsellor_id(admin_id)
        logger.debug(f"[CLONE_SEGMENT] Normalized admin_uuid: {admin_uuid}")

        # Look up the parent segment via junction table using source_consultation_type_id
        logger.debug(f"[CLONE_SEGMENT] Looking up parent segment via junction table...")
        junction_response = (
            supabase.table("consultation_type_segments")
            .select("segment_id")
            .eq("consultation_type_id", request.source_consultation_type_id)
            .eq("segment_code", request.parent_segment_code)
            .execute()
        )

        if not junction_response.data or len(junction_response.data) == 0:
            raise ValueError(f"Parent segment '{request.parent_segment_code}' not found in source consultation type '{request.source_consultation_type_id}'")

        parent_segment_id = junction_response.data[0]["segment_id"]
        logger.debug(f"[CLONE_SEGMENT] Found parent segment_id: {parent_segment_id}")

        # Get full parent segment data by its unique ID
        parent_response = (
            supabase.table("segment_definitions")
            .select("*")
            .eq("id", parent_segment_id)
            .execute()
        )

        if not parent_response.data or len(parent_response.data) == 0:
            raise ValueError(f"Parent segment with ID '{parent_segment_id}' not found in segment_definitions")

        parent_segment_data = parent_response.data[0]
        logger.debug(f"[CLONE_SEGMENT] Loaded parent segment data: {parent_segment_data.get('segment_name')}")

        logger.debug(f"[CLONE_SEGMENT] Calling clone_segment_with_parent_tracking...")
        new_segment = clone_segment_with_parent_tracking(
            parent_segment_code=request.parent_segment_code,
            new_segment_code=request.new_segment_code,
            new_segment_name=request.new_segment_name,
            consultation_type_id=request.consultation_type_id,
            template_id=request.template_id,
            counsellor_id=admin_uuid,  # Changed from created_by_counsellor_id (migration 20251123000200)
            parent_segment_data=parent_segment_data,  # Pass pre-fetched parent data
            custom_prompt_section_text=request.prompt_section_text,  # Optional custom prompt
            custom_schema_definition_json=request.schema_definition_json  # Optional custom schema
        )
        logger.info(f"[CLONE_SEGMENT] Successfully cloned segment: {new_segment.get('id')}")

        return {
            "success": True,
            "message": f"Segment '{request.new_segment_code}' cloned from '{request.parent_segment_code}'",
            "segment": new_segment
        }

    except ValueError as e:
        logger.error(f"[CLONE_SEGMENT] ValueError: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"[CLONE_SEGMENT] Exception: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to clone segment")


# ============================================================================
# Combine Segments - AI-Powered Merge
# ============================================================================

class CombineSegmentSource(BaseModel):
    """Source segment info for combining"""
    segment_id: str = Field(..., description="Segment UUID")
    consultation_type_id: str = Field(..., description="Consultation type ID where segment is defined")

class CombineSegmentsRequest(BaseModel):
    """Request model for combining multiple segments into one"""
    segments: List[CombineSegmentSource] = Field(..., min_items=2, max_items=5, description="List of segments to combine (2-5 segments)")


@router.post("/admin/segments/combine")
async def combine_segments(
    request: CombineSegmentsRequest,
    admin_id: str = Query(..., description="Admin ID performing the combine"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Combine multiple segments into one using AI to intelligently merge prompts and schemas.

    **Use Case:** Create a comprehensive segment by combining related segments like
    HISTORY + EXAMINATION + DIAGNOSIS into a single CLINICAL_SUMMARY segment.

    **Request Body:**
    - segments: List of segment sources (2-5 segments), each with segment_id and consultation_type_id

    **Actions:**
    - Fetches all specified segments from the database
    - Uses Gemini AI to intelligently merge:
      - Prompts are consolidated into a cohesive extraction prompt
      - Schemas are merged logically, avoiding duplication
    - Returns the merged prompt and schema for user review before creating

    **Response:**
    - merged_prompt: AI-generated combined prompt
    - merged_schema: AI-generated combined schema
    - source_segments: Details of segments that were combined
    """
    from services.gemini_service import generate_content_with_gemini

    try:
        logger.info(f"[COMBINE_SEGMENTS] Starting combine request for {len(request.segments)} segments")

        # Fetch all segments
        source_segments = []
        for seg_source in request.segments:
            # Look up segment via junction table
            junction_response = (
                supabase.table("consultation_type_segments")
                .select("segment_id, segment_code")
                .eq("consultation_type_id", seg_source.consultation_type_id)
                .eq("segment_id", seg_source.segment_id)
                .execute()
            )

            if not junction_response.data:
                raise ValueError(f"Segment {seg_source.segment_id} not found in consultation type {seg_source.consultation_type_id}")

            # Get full segment data
            segment_response = (
                supabase.table("segment_definitions")
                .select("*")
                .eq("id", seg_source.segment_id)
                .execute()
            )

            if not segment_response.data:
                raise ValueError(f"Segment {seg_source.segment_id} not found")

            source_segments.append(segment_response.data[0])

        logger.debug(f"[COMBINE_SEGMENTS] Fetched {len(source_segments)} segments: {[s['segment_name'] for s in source_segments]}")

        # Build the AI prompt for merging
        segments_info = []
        for seg in source_segments:
            segments_info.append(f"""
### Segment: {seg['segment_name']} ({seg['segment_code']})

**Prompt:**
{seg.get('prompt_section_text', 'No prompt defined')}

**Schema:**
```json
{json.dumps(seg.get('schema_definition_json', {}), indent=2)}
```
""")

        merge_prompt = f"""You are an expert at designing medical data extraction prompts and schemas.

I need you to COMBINE the following {len(source_segments)} extraction segments into a SINGLE cohesive segment.

## Source Segments to Combine:
{''.join(segments_info)}

## Your Task:

Create a SINGLE combined segment that:

1. **Merged Prompt**: Write a unified extraction prompt that:
   - Combines the extraction goals of all source segments
   - Is well-organized and logically structured
   - Removes redundancy while preserving all important extraction instructions
   - Maintains consistent terminology and style
   - Is comprehensive but not repetitive

2. **Merged Schema**: Create a unified JSON schema that:
   - Combines all properties from source schemas logically
   - Groups related fields together
   - Avoids duplicate fields (merge similar fields intelligently)
   - Preserves important field descriptions and constraints
   - Uses a clear, hierarchical structure where appropriate
   - Maintains proper JSON Schema format with "type": "object" and "properties"

## Response Format:

Return your response in this exact JSON format:
```json
{{
  "merged_prompt": "Your combined extraction prompt here...",
  "merged_schema": {{
    "type": "object",
    "properties": {{
      // Your merged schema properties here
    }}
  }},
  "merge_notes": "Brief notes on how you combined the segments and any decisions made"
}}
```

Important: Return ONLY the JSON, no additional text before or after."""

        # Call Gemini to generate merged content
        # Use merge_model from processing_modes table (defaults to gemini-3.1-pro-preview for quality)
        from services.supabase_service import get_merge_model_by_mode
        merge_model = get_merge_model_by_mode("default")
        logger.debug(f"[COMBINE_SEGMENTS] Calling Gemini for intelligent merge (model: {merge_model})...")
        ai_response = await generate_content_with_gemini(
            prompt=merge_prompt,
            model=merge_model,
            temperature=0.2
        )

        # Parse the AI response
        # Clean up the response - remove markdown code blocks if present
        cleaned_response = ai_response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]
        if cleaned_response.startswith('```'):
            cleaned_response = cleaned_response[3:]
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]
        cleaned_response = cleaned_response.strip()

        try:
            merge_result = json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error(f"[COMBINE_SEGMENTS] Failed to parse AI response: {e}")
            logger.error(f"[COMBINE_SEGMENTS] Raw response: {ai_response[:500]}")
            raise ValueError(f"Failed to parse AI merge response. Please try again.")

        logger.info("[COMBINE_SEGMENTS] Successfully merged segments")

        return {
            "success": True,
            "merged_prompt": merge_result.get("merged_prompt", ""),
            "merged_schema": merge_result.get("merged_schema", {}),
            "merge_notes": merge_result.get("merge_notes", ""),
            "source_segments": [
                {
                    "id": s["id"],
                    "segment_code": s["segment_code"],
                    "segment_name": s["segment_name"]
                }
                for s in source_segments
            ],
            "message": f"Successfully merged {len(source_segments)} segments"
        }

    except ValueError as e:
        logger.error(f"[COMBINE_SEGMENTS] ValueError: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"[COMBINE_SEGMENTS] Exception: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to combine segments")


class BulkCloneSegmentsRequest(BaseModel):
    """Request model for bulk cloning segments"""
    source_consultation_type_code: str = Field(..., description="Source consultation type code (e.g., 'OP')")
    segment_codes: List[str] = Field(..., min_items=1, description="List of segment codes to clone")


@router.post("/admin/consultation-types/{target_consultation_type_code}/segments/clone-bulk")
async def bulk_clone_segments_endpoint(
    target_consultation_type_code: str,
    request: BulkCloneSegmentsRequest,
    admin_id: str = Query(..., description="Admin ID performing the bulk clone"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Bulk clone segments from source consultation type to target consultation type.

    **Use Case:** When creating a new consultation type (e.g., EMERGENCY), you want to quickly
    add segments from an existing consultation type (e.g., OP) without manually cloning each one.

    **Path Parameters:**
    - target_consultation_type_code: Target consultation type code (e.g., 'EMERGENCY')

    **Query Parameters:**
    - admin_id: Admin UUID performing the bulk clone

    **Request Body:**
    - source_consultation_type_code: Source consultation type (e.g., 'OP')
    - segment_codes: List of segment codes to clone (e.g., ['DIAGNOSIS', 'HISTORY', 'PRESCRIPTION'])

    **Example:**
    ```bash
    POST /api/v1/summary/admin/consultation-types/EMERGENCY/segments/clone-bulk?admin_id=admin-uuid
    {
      "source_consultation_type_code": "OP",
      "segment_codes": ["DIAGNOSIS", "HISTORY", "PRESCRIPTION"]
    }
    ```

    **What Happens:**
    - Each segment is cloned from source to target consultation type
    - New segment codes are generated: DIAGNOSIS_EMERGENCY, HISTORY_EMERGENCY, etc.
    - Parent tracking is maintained for all cloned segments
    - Failed clones are reported with error messages

    **Response:**
    ```json
    {
      "success": [
        {
          "original_segment_code": "DIAGNOSIS",
          "new_segment_code": "DIAGNOSIS_EMERGENCY",
          "segment_name": "Diagnosis",
          "segment_id": "uuid"
        }
      ],
      "failed": [
        {
          "segment_code": "INVALID_SEGMENT",
          "error": "Segment not found"
        }
      ],
      "summary": {
        "total_requested": 3,
        "successful": 2,
        "failed": 1,
        "source_consultation_type": "OP",
        "target_consultation_type": "EMERGENCY"
      }
    }
    ```

    **Actions:**
    - Copies prompt_section_text and schema_definition_json from each parent segment
    - Sets parent_segment_code, is_cloned_from_parent, cloned_at for each
    - Creates new segments with same defaults as parents
    - Returns detailed success/failure report
    """
    try:
        admin_uuid = normalize_counsellor_id(admin_id)

        result = bulk_clone_segments(
            source_consultation_type_code=request.source_consultation_type_code,
            target_consultation_type_code=target_consultation_type_code,
            segment_codes=request.segment_codes,
            admin_id=admin_uuid  # Changed from created_by_admin_id (migration 20251123000200)
        )

        return {
            "success": result["success"],
            "failed": result["failed"],
            "summary": result["summary"],
            "message": f"Bulk clone completed: {result['summary']['successful']}/{result['summary']['total_requested']} segments cloned successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"Bulk clone failed: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to bulk clone segments")


# ============================================================================
# Segment Assignment APIs (No Duplication)
# ============================================================================

class AssignSegmentRequest(BaseModel):
    """Request model for assigning segment to consultation type"""
    segment_id: Optional[str] = Field(default=None, description="Segment UUID - REQUIRED when segment_code is not unique (e.g., 'HISTORY' exists in multiple consultation types)")
    category: str = Field(default="additional", description="Default category: core, additional, or excluded")
    display_order: Optional[int] = Field(default=None, description="Display order (auto-calculated if None)")
    brevity_level: str = Field(default="balanced", description="Default brevity level: concise, balanced, or detailed")
    terminology_style: str = Field(default="medical_terms", description="Default terminology: medical_terms, simple_terms, or as_spoken")


@router.post("/admin/consultation-types/{consultation_type_code}/segments/{segment_code}/assign")
async def assign_segment_to_consultation_type_endpoint(
    consultation_type_code: str,
    segment_code: str,
    request: AssignSegmentRequest,
    admin_id: Optional[str] = Query(default=None, description="Admin ID performing the assignment (optional)"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Assign an existing segment to a consultation type WITHOUT duplicating segment_definitions.

    **Use Case:** You have a segment that should be shared across multiple consultation types.
    Instead of cloning (which creates duplicate entries), this assigns the same segment to another type.

    **Path Parameters:**
    - consultation_type_code: Target consultation type code (e.g., 'EMERGENCY')
    - segment_code: Existing segment code to assign (e.g., 'DIAGNOSIS')

    **Query Parameters:**
    - admin_id: Admin UUID performing the assignment

    **Request Body:**
    - category: Default category (core/additional/excluded)
    - display_order: Display order (auto-calculated if None)
    - brevity_level: Default brevity level
    - terminology_style: Default terminology style

    **Example:**
    ```bash
    POST /api/v1/summary/admin/consultation-types/EMERGENCY/segments/DIAGNOSIS/assign?admin_id=uuid
    {
      "category": "core",
      "brevity_level": "balanced"
    }
    ```

    **What Happens:**
    1. Creates junction entry in consultation_type_segments (NO duplication in segment_definitions)
    2. Auto-syncs segment as 'excluded' to ALL templates of the consultation type
    3. Returns sync results showing which templates were updated

    **vs. Bulk Clone:**
    - bulk_clone: Creates NEW segment_definitions entries with same segment_code (uniqueness via junction table)
    - assign: Reuses SAME segment_definitions entry (shared across types)
    """
    try:
        from services.supabase_service import (
            assign_segment_to_consultation_type,
            get_consultation_type_by_code
        )

        # Get consultation type ID
        ct = get_consultation_type_by_code(consultation_type_code)
        if not ct:
            raise HTTPException(status_code=404, detail="Consultation type not found")

        consultation_type_id = uuid.UUID(ct["id"])

        # Convert segment_id string to UUID if provided
        segment_uuid = uuid.UUID(request.segment_id) if request.segment_id else None

        result = assign_segment_to_consultation_type(
            segment_code=segment_code,
            consultation_type_id=consultation_type_id,
            category=request.category,
            display_order=request.display_order,
            brevity_level=request.brevity_level,
            terminology_style=request.terminology_style,
            segment_id=segment_uuid
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to assign segment: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to assign segment")


@router.delete("/admin/consultation-types/{consultation_type_code}/segments/{segment_code}/unassign")
async def unassign_segment_from_consultation_type(
    consultation_type_code: str,
    segment_code: str,
    admin_id: Optional[str] = Query(default=None, description="Admin ID performing the unassignment"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Unassign a segment from a consultation type (removes junction table entry only).

    **Use Case:** Remove a segment's association with a consultation type without deleting the segment itself.

    **Path Parameters:**
    - consultation_type_code: Consultation type code (e.g., 'OP')
    - segment_code: Segment code to unassign (e.g., 'DIAGNOSIS')

    **What Happens:**
    1. Deletes entry from consultation_type_segments junction table
    2. Does NOT delete the segment from segment_definitions
    3. Segment remains available for assignment to other consultation types
    """
    try:
        from services.supabase_service import get_consultation_type_by_code

        # Get consultation type ID
        ct = get_consultation_type_by_code(consultation_type_code)
        if not ct:
            raise HTTPException(status_code=404, detail="Consultation type not found")

        consultation_type_id = ct["id"]

        # Delete the junction table entry
        result = supabase.table("consultation_type_segments").delete().eq(
            "consultation_type_id", consultation_type_id
        ).eq("segment_code", segment_code).execute()

        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="Segment is not assigned to this consultation type"
            )

        logger.info(f"[UNASSIGN] Removed segment '{segment_code}' from consultation type '{consultation_type_code}' by admin {admin_id}")

        # Trigger reassembly for ALL templates under this consultation type
        templates_reassembled = 0
        try:
            # Get all templates for this consultation type
            templates_result = supabase.table("templates").select("id").eq(
                "consultation_type_id", consultation_type_id
            ).execute()

            if templates_result.data and len(templates_result.data) > 0:
                from services.template_assembly_service import trigger_reassembly_async
                template_ids = [uuid.UUID(t["id"]) for t in templates_result.data]
                trigger_source = f"consultation_type_segment:{consultation_type_id}:{segment_code}:unassign"
                asyncio.create_task(trigger_reassembly_async(template_ids, trigger_source))
                templates_reassembled = len(template_ids)
                logger.info(f"[UNASSIGN] Triggered reassembly for {templates_reassembled} templates under consultation type {consultation_type_code}")
        except Exception as e:
            logger.error(f"[UNASSIGN] Failed to trigger reassembly hook: {e}")

        return {
            "success": True,
            "message": f"Successfully unassigned '{segment_code}' from '{consultation_type_code}'",
            "segment_code": segment_code,
            "consultation_type_code": consultation_type_code,
            "unassigned_by": admin_id,
            "templates_reassembled": templates_reassembled
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unassign segment: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to unassign segment")


@router.delete("/admin/templates/{template_code}/segments/{segment_code}/unassign")
async def unassign_segment_from_template(
    template_code: str,
    segment_code: str,
    admin_id: Optional[str] = Query(default=None, description="Admin ID performing the unassignment"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Unassign a segment from a template (removes junction table entry only).

    **Use Case:** Remove a segment's association with a specific template without affecting the segment itself.

    **Path Parameters:**
    - template_code: Template code (e.g., 'OP_HOSP1')
    - segment_code: Segment code to unassign (e.g., 'DIAGNOSIS')

    **What Happens:**
    1. Deletes entry from template_segments junction table
    2. Does NOT delete the segment from segment_definitions
    3. Does NOT affect segment's association with the parent consultation type
    4. Triggers template reassembly
    """
    try:
        from services.supabase_service import get_template_by_code

        # Get template
        template = get_template_by_code(template_code)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        template_id = template["id"]

        # Delete the junction table entry
        result = supabase.table("template_segments").delete().eq(
            "template_id", template_id
        ).eq("segment_code", segment_code).execute()

        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="Segment is not assigned to this template"
            )

        logger.info(f"[UNASSIGN] Removed segment '{segment_code}' from template '{template_code}' by admin {admin_id}")

        # Trigger reassembly for this template
        try:
            from services.template_assembly_service import trigger_reassembly_async
            trigger_source = f"template_segment:{template_id}:{segment_code}:unassign"
            asyncio.create_task(trigger_reassembly_async([uuid.UUID(template_id)], trigger_source))
            logger.info(f"[UNASSIGN] Triggered reassembly for template {template_id}")
        except Exception as e:
            logger.error(f"[UNASSIGN] Failed to trigger reassembly hook: {e}")

        return {
            "success": True,
            "message": f"Successfully unassigned '{segment_code}' from template '{template_code}'",
            "segment_code": segment_code,
            "template_code": template_code,
            "unassigned_by": admin_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unassign segment from template: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to unassign segment")


class AddSegmentsFromTypeRequest(BaseModel):
    """Request model for adding segments from consultation type to template"""
    segment_codes: Optional[List[str]] = Field(default=None, description="Specific segment codes to add")
    add_all_missing: bool = Field(default=False, description="Add all segments not yet in template")
    default_category: str = Field(default="excluded", description="Category for new segments")


@router.get("/admin/templates/{template_code}/segments/available")
async def get_available_segments_for_template_endpoint(
    template_code: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get segments that are in the template's consultation type but NOT yet in the template.

    **Use Case:** Before adding segments to a template, show which segments are available to add.
    This populates the "Add Segments" modal in the UI.

    **Path Parameters:**
    - template_code: Template code (e.g., 'OP_HOSP1')

    **Returns:**
    - available_segments: List of segments that can be added
    - consultation_type_code: The template's consultation type
    - count: Number of available segments

    **Example Response:**
    ```json
    {
      "template_code": "OP_HOSP1",
      "consultation_type_code": "OP",
      "available_segments": [
        {
          "segment_id": "uuid",
          "segment_code": "NEW_SEGMENT",
          "segment_name": "New Segment Name",
          "default_category": "additional",
          "default_brevity_level": "balanced"
        }
      ],
      "count": 1
    }
    ```

    **Note:** If count is 0, all segments from the consultation type are already in the template.
    """
    try:
        from services.supabase_service import (
            get_available_segments_for_template,
            get_template_by_code
        )

        # Get template by code
        template = get_template_by_code(template_code)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        template_id = uuid.UUID(template["id"])
        result = get_available_segments_for_template(template_id)

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get available segments: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to get available segments")


@router.post("/admin/templates/{template_code}/segments/add-from-type")
async def add_segments_from_type_endpoint(
    template_code: str,
    request: AddSegmentsFromTypeRequest,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Add individual segments from consultation type to template.

    **Use Case:** Add specific segments to a template without using "Inherit from Type"
    (which deletes all existing segments and replaces them).

    **Path Parameters:**
    - template_code: Template code (e.g., 'OP_HOSP1')

    **Request Body:**
    - segment_codes: List of specific segment codes to add (optional)
    - add_all_missing: If true, add ALL segments not yet in template
    - default_category: Category for new segments (default: 'excluded')

    **Example - Add specific segments:**
    ```bash
    POST /api/v1/summary/admin/templates/OP_HOSP1/segments/add-from-type
    {
      "segment_codes": ["NEW_SEGMENT_1", "NEW_SEGMENT_2"],
      "default_category": "excluded"
    }
    ```

    **Example - Add all missing:**
    ```bash
    POST /api/v1/summary/admin/templates/OP_HOSP1/segments/add-from-type
    {
      "add_all_missing": true,
      "default_category": "excluded"
    }
    ```

    **Response:**
    ```json
    {
      "success": true,
      "template_code": "OP_HOSP1",
      "segments_added": [
        {
          "segment_code": "NEW_SEGMENT_1",
          "segment_name": "New Segment 1",
          "category": "excluded"
        }
      ],
      "count": 1
    }
    ```

    **Note:** New segments are added as 'excluded' by default. Use drag-and-drop
    in the UI to move them to Core or Additional categories.
    """
    try:
        from services.supabase_service import (
            add_segments_to_template_from_type,
            get_template_by_code
        )

        # Get template by code
        template = get_template_by_code(template_code)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        template_id = uuid.UUID(template["id"])

        result = add_segments_to_template_from_type(
            template_id=template_id,
            segment_codes=request.segment_codes,
            add_all_missing=request.add_all_missing,
            default_category=request.default_category
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add segments from type: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to add segments from type")


@router.get("/admin/segments/{segment_code}/with-parent")
async def get_segment_with_parent(
    segment_code: str,
    consultation_type_id: Optional[str] = Query(None, description="Consultation type ID for type-specific segments"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get a segment along with its parent for comparison.

    **Use case:** Show differences between DIAGNOSIS_CARDIOLOGY and its parent DIAGNOSIS

    **Query Parameters:**
    - consultation_type_id: Required if the segment is consultation-type-specific

    **Returns:**
    - segment: The child segment details
    - parent: The parent segment details (if exists)
    - relationship: Metadata about the parent-child relationship
    """
    try:
        from services.supabase_service import get_segment_with_parent_info

        result = get_segment_with_parent_info(
            segment_code=segment_code,
            consultation_type_id=consultation_type_id
        )

        return {
            "success": True,
            "data": result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get segment with parent")


@router.get("/admin/segments/{segment_code}/children")
async def get_segment_children(
    segment_code: str,
    include_diverged: bool = Query(True, description="Include segments that have diverged from parent"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get all child segments that were cloned from a parent segment.

    **Use case:** Find all segments cloned from DIAGNOSIS (DIAGNOSIS_CARDIOLOGY, DIAGNOSIS_PEDIATRICS, etc.)

    **Query Parameters:**
    - include_diverged: If FALSE, only return children that are still in sync

    **Returns:**
    - children: List of child segments with relationship metadata
    - counts: Summary of total, in_sync, and diverged children
    """
    try:
        from services.supabase_service import get_segment_children_list

        children = get_segment_children_list(
            parent_segment_code=segment_code,
            include_diverged=include_diverged
        )

        in_sync_count = sum(1 for c in children if not c.get('diverged_from_parent', False))
        diverged_count = sum(1 for c in children if c.get('diverged_from_parent', False))

        return {
            "success": True,
            "parent_segment_code": segment_code,
            "children": children,
            "counts": {
                "total": len(children),
                "in_sync": in_sync_count,
                "diverged": diverged_count
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get segment children")


@router.post("/admin/segments/{segment_code}/propagate")
async def propagate_changes_to_children(
    segment_code: str,
    request: PropagateChangesRequest,
    admin_id: str = Query(..., description="Admin ID performing the propagation"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Propagate changes from a parent segment to selected child segments.

    **Use case:** After fixing a bug in DIAGNOSIS, update all child segments that haven't diverged

    **Path Parameters:**
    - segment_code: Parent segment code to propagate from

    **Request Body:**
    - segment_codes: List of child segment codes to update
    - force_update_diverged: If TRUE, update even segments that have been manually edited

    **Actions:**
    - Updates prompt_section_text and schema_definition_json from parent
    - Sets last_parent_sync_at to NOW()
    - For diverged segments: only updates if force_update_diverged=TRUE
    """
    try:
        from services.supabase_service import propagate_parent_changes

        admin_uuid = normalize_counsellor_id(admin_id)

        results = propagate_parent_changes(
            parent_segment_code=segment_code,
            child_segment_codes=request.segment_codes,
            force_update_diverged=request.force_update_diverged,
            updated_by_admin_id=admin_uuid
        )

        return {
            "success": True,
            "message": f"Propagated changes from '{segment_code}' to {len(results['updated'])} segment(s)",
            "updated": results['updated'],
            "skipped": results['skipped'],
            "errors": results['errors']
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to propagate changes")


@router.post("/admin/segments/{segment_code}/sync-from-parent")
async def sync_segment_from_parent_endpoint(
    segment_code: str,
    consultation_type_id: Optional[str] = Query(None, description="Consultation type ID for type-specific segments"),
    force_sync: bool = Query(False, description="If TRUE, sync even if segment has diverged"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Sync a single child segment from its parent.

    **Use case:** Pull latest changes from DIAGNOSIS into DIAGNOSIS_CARDIOLOGY

    **Query Parameters:**
    - consultation_type_id: Required if the segment is consultation-type-specific
    - force_sync: If TRUE, sync even if the segment has been manually edited (loses customizations)

    **Actions:**
    - Updates prompt and schema from parent
    - Resets diverged_from_parent to FALSE
    - Sets last_parent_sync_at to NOW()

    **Warning:** If force_sync=TRUE, this will overwrite any customizations!
    """
    try:
        from services.supabase_service import sync_segment_from_parent

        updated_segment = sync_segment_from_parent(
            segment_code=segment_code,
            consultation_type_id=consultation_type_id,
            force_sync=force_sync
        )

        return {
            "success": True,
            "message": f"Segment '{segment_code}' synced from parent",
            "segment": updated_segment
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to sync from parent")

# =====================================================
# Association-Specific Configuration Endpoints
# =====================================================

@router.get("/admin/consultation-type-segments/{consultation_type_id}/{segment_code}")
async def get_consultation_type_segment_config(
    consultation_type_id: str,
    segment_code: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get junction table configuration for a specific consultation type - segment association.
    
    Returns association-specific configuration from consultation_type_segments table:
    - category
    - display_order
    - brevity_level
    - terminology_style
    """
    try:
        from services.supabase_service import supabase
        
        response = (
            supabase.table("consultation_type_segments")
            .select("*")
            .eq("consultation_type_id", consultation_type_id)
            .eq("segment_code", segment_code)
            .limit(1)
            .execute()
        )
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="No association found between consultation type and segment"
            )

        config = response.data[0]

        return {
            "success": True,
            "category": config.get("default_category"),
            "display_order": config.get("default_display_order"),
            "brevity_level": config.get("default_brevity_level"),
            "terminology_style": config.get("default_terminology_style"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get configuration")


class UpdateJunctionConfigRequest(BaseModel):
    category: Optional[str] = Field(None, description="Segment category (core/additional)")
    display_order: Optional[int] = Field(None, description="Display order")
    brevity_level: Optional[str] = Field(None, description="Brevity level")
    terminology_style: Optional[str] = Field(None, description="Terminology style")


@router.put("/admin/consultation-type-segments/{consultation_type_id}/{segment_code}")
async def update_consultation_type_segment_config(
    consultation_type_id: str,
    segment_code: str,
    request: UpdateJunctionConfigRequest,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Update junction table configuration for a consultation type - segment association.
    
    Updates ONLY association-specific fields in consultation_type_segments table.
    Does NOT modify global segment definition fields (prompt, schema).
    """
    try:
        from services.supabase_service import supabase
        
        # Build update data
        update_data = {}
        if request.category is not None:
            update_data["default_category"] = request.category
        if request.display_order is not None:
            update_data["default_display_order"] = request.display_order
        if request.brevity_level is not None:
            update_data["default_brevity_level"] = request.brevity_level
        if request.terminology_style is not None:
            update_data["default_terminology_style"] = request.terminology_style
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Update junction table
        response = (
            supabase.table("consultation_type_segments")
            .update(update_data)
            .eq("consultation_type_id", consultation_type_id)
            .eq("segment_code", segment_code)
            .execute()
        )
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="No association found between consultation type and segment"
            )

        # Map database column names back to API field names for response
        updated_fields = {}
        if request.category is not None:
            updated_fields["category"] = request.category
        if request.display_order is not None:
            updated_fields["display_order"] = request.display_order
        if request.brevity_level is not None:
            updated_fields["brevity_level"] = request.brevity_level
        if request.terminology_style is not None:
            updated_fields["terminology_style"] = request.terminology_style

        return {
            "success": True,
            "message": "Configuration updated successfully",
            "updated": updated_fields
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update configuration")


@router.get("/admin/template-segments/{template_id}/{segment_code}")
async def get_template_segment_config(
    template_id: str,
    segment_code: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get junction table configuration for a specific template - segment association.
    
    Returns association-specific configuration from template_segments table:
    - category
    - display_order
    - brevity_level
    - terminology_style
    """
    try:
        from services.supabase_service import supabase
        
        response = (
            supabase.table("template_segments")
            .select("*")
            .eq("template_id", template_id)
            .eq("segment_code", segment_code)
            .limit(1)
            .execute()
        )
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="No association found between template and segment"
            )

        config = response.data[0]
        
        return {
            "success": True,
            "category": config.get("category"),
            "display_order": config.get("display_order"),
            "brevity_level": config.get("brevity_level"),
            "terminology_style": config.get("terminology_style"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get configuration")


@router.put("/admin/template-segments/{template_id}/{segment_code}")
async def update_template_segment_config_by_uuid(
    template_id: str,
    segment_code: str,
    request: UpdateJunctionConfigRequest,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Update junction table configuration for a template - segment association (by UUID).

    Updates ONLY association-specific fields in template_segments table.
    Does NOT modify global segment definition fields (prompt, schema).
    """
    try:
        from services.supabase_service import supabase
        
        # Build update data
        update_data = {}
        if request.category is not None:
            update_data["category"] = request.category
        if request.display_order is not None:
            update_data["display_order"] = request.display_order
        if request.brevity_level is not None:
            update_data["brevity_level"] = request.brevity_level
        if request.terminology_style is not None:
            update_data["terminology_style"] = request.terminology_style
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Update junction table
        response = (
            supabase.table("template_segments")
            .update(update_data)
            .eq("template_id", template_id)
            .eq("segment_code", segment_code)
            .execute()
        )
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="No association found between template and segment"
            )

        return {
            "success": True,
            "message": "Configuration updated successfully",
            "updated": update_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update configuration")

# =====================================================
# HARD DELETE ENDPOINTS (Admin Only)
# =====================================================

@router.get(
    "/admin/soft-deleted/{entity_type}",
    summary="List soft-deleted entities",
    description="Get all soft-deleted segments, templates, or consultation types (is_active=false)"
)
async def list_soft_deleted_entities(
    entity_type: str = Path(..., description="Entity type: segment, template, or consultation_type"),
    client: ClientContext = Depends(require_admin)
):
    """
    List all soft-deleted entities of the specified type.

    - **segment**: Lists segment_definitions with is_active=false
    - **template**: Lists templates with is_active=false
    - **consultation_type**: Lists consultation_types with is_active=false
    """
    try:
        if entity_type not in ["segment", "template", "consultation_type"]:
            raise HTTPException(status_code=400, detail="Invalid entity_type. Must be: segment, template, or consultation_type")

        if entity_type == "segment":
            response = (
                supabase.table("segment_definitions")
                .select("id, segment_code, segment_name, default_category, created_at, updated_at")
                .eq("is_active", False)
                .order("updated_at", desc=True)
                .execute()
            )
        elif entity_type == "template":
            response = (
                supabase.table("templates")
                .select("id, template_code, template_name, consultation_type_id, counsellor_id, created_at, updated_at")
                .eq("is_active", False)
                .order("updated_at", desc=True)
                .execute()
            )
        else:  # consultation_type
            response = (
                supabase.table("consultation_types")
                .select("id, type_code, type_name, description, created_at, updated_at")
                .eq("is_active", False)
                .order("updated_at", desc=True)
                .execute()
            )

        return {
            "entity_type": entity_type,
            "count": len(response.data) if response.data else 0,
            "items": response.data or []
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to list soft-deleted entities")


@router.get(
    "/admin/relationships/{entity_type}/{entity_id}",
    summary="Get entity relationships",
    description="Show all relationships (junction table links) for an entity before hard deletion"
)
async def get_entity_relationships(
    entity_type: str,
    entity_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Get all relationships for an entity to show what will be affected by hard deletion.

    Shows:
    - For segments: consultation types, templates using this segment
    - For templates: counsellors who have activated this template, segments in this template
    - For consultation types: templates based on this type, segments linked to this type
    """
    try:
        if entity_type not in ["segment", "template", "consultation_type"]:
            raise HTTPException(status_code=400, detail="Invalid entity_type")

        relationships = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "relationships": {}
        }

        if entity_type == "segment":
            # Get consultation types using this segment
            ct_segments = (
                supabase.table("consultation_type_segments")
                .select("consultation_type_id, segment_code")
                .eq("segment_id", entity_id)
                .execute()
            ).data or []

            # Get consultation type details
            if ct_segments:
                ct_ids = [r["consultation_type_id"] for r in ct_segments if r.get("consultation_type_id")]
                if ct_ids:
                    consultation_types = (
                        supabase.table("consultation_types")
                        .select("id, type_code, type_name")
                        .in_("id", ct_ids)
                        .execute()
                    ).data or []
                    relationships["relationships"]["consultation_types"] = consultation_types

            # Get templates using this segment
            template_segments = (
                supabase.table("template_segments")
                .select("template_id, segment_code")
                .eq("segment_id", entity_id)
                .execute()
            ).data or []

            # Get template details
            if template_segments:
                template_ids = [r["template_id"] for r in template_segments if r.get("template_id")]
                if template_ids:
                    templates = (
                        supabase.table("templates")
                        .select("id, template_code, template_name, counsellor_id")
                        .in_("id", template_ids)
                        .execute()
                    ).data or []
                    relationships["relationships"]["templates"] = templates

        elif entity_type == "template":
            # Get counsellors who activated this template
            counsellor_templates = (
                supabase.table("counsellor_templates")
                .select("counsellor_id, is_active")
                .eq("template_id", entity_id)
                .eq("is_active", True)
                .execute()
            ).data or []

            # Get counsellor details
            if counsellor_templates:
                counsellor_ids = [r["counsellor_id"] for r in counsellor_templates if r.get("counsellor_id")]
                if counsellor_ids:
                    doctors = (
                        supabase.table("counsellors")
                        .select("id, full_name, email, specialization")
                        .in_("id", counsellor_ids)
                        .execute()
                    ).data or []
                    # Normalize field names for frontend compatibility
                    for doc in doctors:
                        doc["name"] = doc.pop("full_name", "")
                        doc["specialty"] = doc.pop("specialization", "")
                    relationships["relationships"]["counsellors"] = doctors

            # Get segments in this template
            template_segments = (
                supabase.table("template_segments")
                .select("segment_id, segment_code, category")
                .eq("template_id", entity_id)
                .execute()
            ).data or []

            relationships["relationships"]["segments"] = template_segments

        else:  # consultation_type
            # Get templates based on this consultation type
            templates = (
                supabase.table("templates")
                .select("id, template_code, template_name, counsellor_id")
                .eq("consultation_type_id", entity_id)
                .execute()
            ).data or []

            relationships["relationships"]["templates"] = templates

            # Get segments linked to this consultation type
            ct_segments = (
                supabase.table("consultation_type_segments")
                .select("segment_id, segment_code, default_category")
                .eq("consultation_type_id", entity_id)
                .execute()
            ).data or []

            relationships["relationships"]["segments"] = ct_segments

            # Get extractions referencing this consultation type
            try:
                extractions = (
                    supabase.table("extractions")
                    .select("id, created_at")
                    .eq("consultation_type_id", entity_id)
                    .limit(100)
                    .execute()
                ).data or []
                if extractions:
                    relationships["relationships"]["extractions"] = {
                        "count": len(extractions),
                        "note": "These extractions will have consultation_type_id set to NULL (data preserved)"
                    }
            except Exception:
                pass  # Table might not exist

        return relationships

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get relationships")


@router.delete(
    "/admin/hard-delete/{entity_type}/{entity_id}",
    summary="Hard delete entity (PERMANENT)",
    description="Permanently delete an entity from the database. This will CASCADE delete all junction table entries."
)
async def hard_delete_entity(
    entity_type: str,
    entity_id: str,
    admin_id: str = Query(..., description="Admin user ID for audit logging"),
    client: ClientContext = Depends(require_admin)
):
    """
    **DANGER: PERMANENT DELETE**

    Permanently removes an entity from the database. This operation:
    - Cannot be undone
    - Cascades to all junction tables
    - Should only be used for entities that are soft-deleted (is_active=false)

    Entity types:
    - **segment**: Deletes from segment_definitions, cascades to consultation_type_segments and template_segments
    - **template**: Deletes from templates, cascades to template_segments and counsellor_templates
    - **consultation_type**: Deletes from consultation_types, cascades to consultation_type_segments
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        if entity_type not in ["segment", "template", "consultation_type"]:
            raise HTTPException(status_code=400, detail="Invalid entity_type")

        # Verify entity exists and is soft-deleted
        if entity_type == "segment":
            entity_response = (
                supabase.table("segment_definitions")
                .select("id, segment_code, segment_name, is_active")
                .eq("id", entity_id)
                .execute()
            )
        elif entity_type == "template":
            entity_response = (
                supabase.table("templates")
                .select("id, template_code, template_name, is_active")
                .eq("id", entity_id)
                .execute()
            )
        else:  # consultation_type
            entity_response = (
                supabase.table("consultation_types")
                .select("id, type_code, type_name, is_active")
                .eq("id", entity_id)
                .execute()
            )

        if not entity_response.data or len(entity_response.data) == 0:
            raise HTTPException(status_code=404, detail="Entity not found")

        entity = entity_response.data[0]

        # Check if entity is soft-deleted (recommended but not enforced)
        if entity.get("is_active", True):
            logger.warning(f"[HARD_DELETE] Entity {entity_type}/{entity_id} is still active (is_active=true). Proceeding with hard delete anyway.")

        # Get relationships before deletion for audit log (non-blocking)
        relationships = {"entity_type": entity_type, "entity_id": entity_id, "relationships": {}}
        try:
            relationships = await get_entity_relationships(entity_type, entity_id)
        except Exception as rel_error:
            logger.warning(f"[HARD_DELETE] Could not fetch relationships (non-blocking): {rel_error}")

        # Perform hard delete with explicit junction table cleanup
        if entity_type == "segment":
            table_name = "segment_definitions"
            entity_name = entity.get("segment_code")

            # Explicitly delete from junction tables (don't rely on CASCADE)
            # 1. Delete from consultation_type_segments
            try:
                supabase.table("consultation_type_segments").delete().eq("segment_id", entity_id).execute()
                logger.debug(f"[HARD_DELETE] Deleted consultation_type_segments for segment {entity_id}")
            except Exception as e:
                logger.warning(f"[HARD_DELETE] Could not delete consultation_type_segments: {e}")

            # 2. Delete from template_segments
            try:
                supabase.table("template_segments").delete().eq("segment_id", entity_id).execute()
                logger.debug(f"[HARD_DELETE] Deleted template_segments for segment {entity_id}")
            except Exception as e:
                logger.warning(f"[HARD_DELETE] Could not delete template_segments: {e}")

        elif entity_type == "template":
            table_name = "templates"
            entity_name = entity.get("template_code")
        else:  # consultation_type
            table_name = "consultation_types"
            entity_name = entity.get("type_code")

            # Unlink/delete related records before deletion
            # 1. Unlink extractions (preserve extraction data)
            try:
                supabase.table("extractions").update({
                    "consultation_type_id": None
                }).eq("consultation_type_id", entity_id).execute()
                logger.debug(f"[HARD_DELETE] Unlinked extractions from consultation_type {entity_id}")
            except Exception as e:
                logger.warning(f"[HARD_DELETE] Could not unlink extractions: {e}")

            # 2. Unlink recording_sessions (preserve session data)
            try:
                supabase.table("recording_sessions").update({
                    "consultation_type_id": None
                }).eq("consultation_type_id", entity_id).execute()
                logger.debug(f"[HARD_DELETE] Unlinked recording_sessions from consultation_type {entity_id}")
            except Exception as e:
                logger.warning(f"[HARD_DELETE] Could not unlink recording_sessions: {e}")

            # 3. Unlink templates (preserve template data)
            try:
                supabase.table("templates").update({
                    "consultation_type_id": None
                }).eq("consultation_type_id", entity_id).execute()
                logger.debug(f"[HARD_DELETE] Unlinked templates from consultation_type {entity_id}")
            except Exception as e:
                logger.warning(f"[HARD_DELETE] Could not unlink templates: {e}")

            # 4. Delete consultation_type_system_prompts (junction data, safe to delete)
            try:
                supabase.table("consultation_type_system_prompts").delete().eq("consultation_type_id", entity_id).execute()
                logger.debug(f"[HARD_DELETE] Deleted consultation_type_system_prompts for consultation_type {entity_id}")
            except Exception as e:
                logger.warning(f"[HARD_DELETE] Could not delete consultation_type_system_prompts: {e}")

            # 5. Delete consultation_type_segments (junction data, safe to delete)
            try:
                supabase.table("consultation_type_segments").delete().eq("consultation_type_id", entity_id).execute()
                logger.debug(f"[HARD_DELETE] Deleted consultation_type_segments for consultation_type {entity_id}")
            except Exception as e:
                logger.warning(f"[HARD_DELETE] Could not delete consultation_type_segments: {e}")

        delete_response = (
            supabase.table(table_name)
            .delete()
            .eq("id", entity_id)
            .execute()
        )

        logger.info(f"[HARD_DELETE] Deleted {entity_type} '{entity_name}' (ID: {entity_id}) by admin {admin_id}")
        logger.debug(f"[HARD_DELETE] Cascade deleted relationships: {relationships['relationships']}")

        return {
            "success": True,
            "message": f"Successfully deleted {entity_type}: {entity_name}",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "deleted_by_admin": admin_id,
            "cascade_affected": relationships["relationships"]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[HARD_DELETE] Failed to delete {entity_type}/{entity_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to hard delete")


# ============================================================================
# Template Assembly Admin Endpoints
# ============================================================================

@router.get("/admin/templates/{template_code}/preview-prompt")
async def preview_template_prompt(
    template_code: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Preview the assembled full prompt for a template.
    Returns the stored assembled_full_prompt without triggering reassembly.
    """
    try:
        result = supabase.table("templates").select(
            "template_code, template_name, assembled_full_prompt, prompt_assembled_at"
        ).eq("template_code", template_code).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Template not found")

        row = result.data[0]
        return {
            "success": True,
            "template_code": row["template_code"],
            "template_name": row["template_name"],
            "assembled_full_prompt": row.get("assembled_full_prompt"),
            "prompt_assembled_at": row.get("prompt_assembled_at"),
            "has_prompt": row.get("assembled_full_prompt") is not None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ADMIN] Preview prompt failed for template {template_code}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to preview prompt")


@router.post("/admin/templates/{template_id}/reassemble")
async def reassemble_template(
    template_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Manually trigger full reassembly (prompt + schema) for a template.

    This endpoint is for admin use to force re-assembly after manual database changes
    or when automatic hooks may have failed.
    """
    from services.template_assembly_service import assemble_single_template

    try:
        tid = uuid.UUID(template_id)
        result = assemble_single_template(tid, "manual_api_call")
        logger.info(f"[ADMIN] Manual reassembly triggered for template {template_id}")
        return {
            "success": True,
            "template_id": template_id,
            "template_code": result.get("template_code"),
            "prompt_assembled_at": result.get("prompt_assembled_at"),
            "schema_assembled_at": result.get("schema_assembled_at"),
            "property_count": result.get("property_count", 0)
        }
    except ValueError as e:
        logger.error(f"[ADMIN] Reassembly failed for template {template_id}: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"[ADMIN] Reassembly failed for template {template_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Reassembly failed")


@router.post("/admin/templates/{template_id}/reassemble-prompt")
async def reassemble_template_prompt(
    template_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Manually trigger prompt-only reassembly for a template.

    Use this when only segment text or system prompt changes were made.
    """
    from services.template_assembly_service import assemble_template_full_prompt

    try:
        tid = uuid.UUID(template_id)
        result = assemble_template_full_prompt(tid, "manual_api_call")
        logger.info(f"[ADMIN] Manual prompt reassembly triggered for template {template_id}")
        return {
            "success": True,
            "template_id": template_id,
            "template_code": result.get("template_code"),
            "prompt_assembled_at": result.get("prompt_assembled_at"),
            "prompt_length": len(result.get("assembled_full_prompt", ""))
        }
    except ValueError as e:
        logger.error(f"[ADMIN] Prompt reassembly failed for template {template_id}: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"[ADMIN] Prompt reassembly failed for template {template_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Prompt reassembly failed")


@router.post("/admin/templates/{template_id}/reassemble-schema")
async def reassemble_template_schema(
    template_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Manually trigger schema-only reassembly for a template.

    Use this when only schema_definition_json changes were made.
    """
    from services.template_assembly_service import assemble_template_schema

    try:
        tid = uuid.UUID(template_id)
        result = assemble_template_schema(tid, "manual_api_call")
        logger.info(f"[ADMIN] Manual schema reassembly triggered for template {template_id}")
        return {
            "success": True,
            "template_id": template_id,
            "template_code": result.get("template_code"),
            "schema_assembled_at": result.get("schema_assembled_at"),
            "property_count": result.get("property_count", 0)
        }
    except ValueError as e:
        logger.error(f"[ADMIN] Schema reassembly failed for template {template_id}: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"[ADMIN] Schema reassembly failed for template {template_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Schema reassembly failed")


@router.post("/admin/templates/reassemble-all")
async def reassemble_all_templates(
    client: ClientContext = Depends(require_admin)
):
    """
    Reassemble all active templates (both prompt and schema).

    Use this after migration or for bulk refresh operations.
    This operation may take several seconds for many templates.
    """
    from services.template_assembly_service import assemble_all_templates

    try:
        result = await assemble_all_templates()
        logger.info(f"[ADMIN] Bulk reassembly completed: {result['success']} success, {result['failed']} failed")
        return {
            "success": True,
            "templates_assembled": result["success"],
            "templates_failed": result["failed"],
            "errors": result.get("errors", [])
        }
    except Exception as e:
        logger.error(f"[ADMIN] Bulk reassembly failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Bulk reassembly failed")

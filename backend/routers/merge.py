"""
Merge Router - API Endpoints for Extraction Merge Feature

Provides REST API endpoints for merging multiple extractions
into a single consolidated output using AI-powered contextual merging.

Endpoints:
- POST /api/v1/extractions/merge - Merge extractions and save
- POST /api/v1/extractions/merge/preview - Preview merge without saving
- POST /api/v1/extractions/transform-schema - Transform JSON to target schema
- POST /api/v1/extractions/detect-schema - Detect schema type of JSON data
- GET /api/v1/extractions/student/{student_id}/timeline - List student extractions
- GET /api/v1/extractions/{extraction_id}/merge-info - Get merge lineage

Author: System
Date: 2025-11-19
Updated: 2025-12-02 - Added schema transformation endpoints
"""

import os
import logging
import asyncio
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel

# Conditional EHR auth imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import (
        EHRCounsellorAccessChecker, EHRStudentAccessChecker,
        EHRExtractionAccessChecker, EHRSubmissionAccessChecker,
        get_current_client
    )
    from services.auth_service import validate_ehr_counsellor_access
    from models.auth_models import ClientContext

    _counsellor_checker = EHRCounsellorAccessChecker()
    _student_checker = EHRStudentAccessChecker()
    _extraction_checker = EHRExtractionAccessChecker()
    _submission_checker = EHRSubmissionAccessChecker()

    async def verify_counsellor_access(request: Request, counsellor_id: str = None):  # type: ignore[misc]
        """Verify EHR client has access to counsellor data."""
        counsellor_uuid = uuid.UUID(counsellor_id) if counsellor_id else None
        client = get_current_client(request)
        return await _counsellor_checker(request, counsellor_uuid, client)

    async def verify_student_access(request: Request, student_id: str = None):  # type: ignore[misc]
        """Verify EHR client has access to student data."""
        # EHRStudentAccessChecker expects str, not UUID
        client = get_current_client(request)
        return await _student_checker(request, student_id, client)

    async def verify_extraction_access(request: Request, extraction_id: str = None):  # type: ignore[misc]
        """Verify EHR client has access to extraction data."""
        extraction_uuid = uuid.UUID(extraction_id) if extraction_id else None
        client = get_current_client(request)
        return await _extraction_checker(request, extraction_uuid, client)

    async def verify_submission_access(request: Request, submission_id: str = None):  # type: ignore[misc]
        """Verify EHR client has access to submission data."""
        submission_uuid = uuid.UUID(submission_id) if submission_id else None
        client = get_current_client(request)
        return await _submission_checker(request, submission_uuid, client)

    async def verify_session_access(request: Request, session_id: str = None):  # type: ignore[misc]
        """Verify EHR client has access to session data."""
        session_uuid = uuid.UUID(session_id) if session_id else None
        client = get_current_client(request)
        return await _submission_checker(request, session_uuid, client)

    async def validate_counsellor_from_body(http_request: Request, counsellor_id: str):  # type: ignore[misc]
        """
        Validate counsellor_id access after body is parsed.
        Use this for endpoints where counsellor_id is in request body.
        Raises HTTPException 403 if access denied.
        """
        client = get_current_client(http_request)
        if client.client_type == "ehr":
            counsellor_uuid = uuid.UUID(counsellor_id)
            if not await validate_ehr_counsellor_access(client, counsellor_uuid):
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )
else:
    async def verify_counsellor_access(request: Request, counsellor_id: str = None):  # type: ignore[misc]
        return None

    async def verify_student_access(request: Request, student_id: str = None):  # type: ignore[misc]
        return None

    async def verify_extraction_access(request: Request, extraction_id: str = None):  # type: ignore[misc]
        return None

    async def verify_submission_access(request: Request, submission_id: str = None):  # type: ignore[misc]
        return None

    async def verify_session_access(request: Request, session_id: str = None):  # type: ignore[misc]
        return None

    async def validate_counsellor_from_body(http_request: Request = None, counsellor_id: str = None):  # type: ignore[misc]
        pass  # No-op when auth disabled

from services.audit_service import audit_service

from models.merge_models import (
    MergeRequest,
    MergePreviewRequest,
    MergeResponse,
    MergeErrorResponse,
    MergeAsyncResponse,
    MergeStatusResponse,
    MergeLineageResponse,
    StudentTimelineResponse,
    StudentTimelineExtraction,
    SourceExtractionInfo,
    MergeMetadata,
    UploadedJsonSource,
    UploadType,
    MAX_MERGE_SOURCES,
    get_merge_strategy
)
from services import merge_service
from services.merge_service import SchemaCompatibilityError
from services.supabase_service import supabase
from services.schema_transformer import SchemaTransformer, detect_schema_type, transform_for_merge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/extractions", tags=["Extraction Merge"])

# Track active merge processing tasks
_active_merge_tasks: Dict[str, asyncio.Task] = {}


# =====================================================
# Template Resolution Helper
# =====================================================

async def resolve_template_to_consultation_type(
    template_code: str,
    counsellor_id: str,
    supabase_client
) -> Tuple[str, str, str]:
    """
    Resolve template_code to consultation_type_code and validate counsellor access.

    Args:
        template_code: Template code (e.g., 'OP_GENERAL', 'OP_SMITH_1225141530')
        counsellor_id: Counsellor UUID performing the merge
        supabase_client: Supabase client instance

    Returns:
        Tuple of (template_id, consultation_type_id, consultation_type_code)

    Raises:
        HTTPException: If template not found or counsellor doesn't have access
    """
    # Lookup template with joined consultation type
    result = supabase_client.table('templates')\
        .select('id, template_code, counsellor_id, consultation_type_id, consultation_types(id, type_code)')\
        .eq('template_code', template_code)\
        .eq('is_active', True)\
        .execute()

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="Template not found or inactive"
        )

    template = result.data[0]
    template_id = template['id']
    template_counsellor_id = template.get('counsellor_id')
    consultation_type = template.get('consultation_types')

    if not consultation_type:
        raise HTTPException(
            status_code=400,
            detail="Template has no associated consultation type"
        )

    consultation_type_id = consultation_type['id']
    consultation_type_code = consultation_type['type_code']

    # Validate counsellor access (owned, shared, or common)
    is_owned = template_counsellor_id == counsellor_id
    is_common = template_counsellor_id is None

    if not is_owned and not is_common:
        # Check if shared via counsellor_templates junction
        shared_result = supabase_client.table('counsellor_templates')\
            .select('id')\
            .eq('template_id', template_id)\
            .eq('counsellor_id', counsellor_id)\
            .eq('is_active', True)\
            .execute()

        if not shared_result.data:
            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

    logger.debug(
        f"[MergeAPI] Resolved template: {template_code} → "
        f"consultation_type: {consultation_type_code}, "
        f"access: {'owned' if is_owned else 'common' if is_common else 'shared'}"
    )

    return (template_id, consultation_type_id, consultation_type_code)


# =====================================================
# Main Merge Endpoints
# =====================================================

@router.post("/merge", response_model=MergeAsyncResponse, status_code=202)
async def merge_extractions(
    http_request: Request,
    request: MergeRequest,
    _auth = Depends(verify_counsellor_access)
):
    """
    Merge multiple extractions into a single consolidated output.

    **ASYNC BEHAVIOR:** This endpoint returns immediately with an extraction_id.
    The actual merge processing happens in the background.

    **Flow:**
    1. Validate request and resolve submission_ids
    2. Generate extraction_id upfront
    3. Create pending merge job in database
    4. Start background processing
    5. Return immediately with extraction_id
    6. Webhook sent when merge completes (with same extraction_id)

    **Tracking:**
    - Use `GET /merge/status/{extraction_id}` to poll status
    - Or wait for webhook with matching extraction_id

    **Merge Process (background):**
    1. Validate all source extractions belong to same student
    2. Load extraction data and sort chronologically
    3. Generate AI merge prompt with field-specific strategies
    4. Call Gemini API for contextual merging
    5. Save merged extraction with relationship tracking
    6. Send webhook notification

    **Example Request:**
    ```json
    {
        "source_extraction_ids": ["uuid1", "uuid2"],
        "target_template_code": "OP_GENERAL",
        "counsellor_id": "uuid",
        "merge_notes": "Follow-up consolidation"
    }
    ```

    **Example Response:**
    ```json
    {
        "success": true,
        "extraction_id": "generated-uuid",
        "status": "processing",
        "message": "Merge operation started. Use extraction_id to check status or receive webhook."
    }
    ```
    """
    try:
        # =====================================================
        # Validate EHR client has access to this counsellor (school-scoped)
        # =====================================================
        await validate_counsellor_from_body(http_request, request.counsellor_id)

        # =====================================================
        # Resolve submission_ids to extraction_ids if provided
        # =====================================================
        source_extraction_ids = list(request.source_extraction_ids)  # Copy to avoid mutation

        if request.source_submission_ids:
            if source_extraction_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot use both source_extraction_ids and source_submission_ids. Use one or the other."
                )

            # Resolve submission_ids to extraction_ids
            resolved_ids, failed_ids = await resolve_submission_ids_to_extraction_ids(
                request.source_submission_ids
            )

            if failed_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Some submissions could not be resolved. They may still be processing."
                )

            source_extraction_ids = resolved_ids
            logger.debug(f"[MergeAPI] Resolved {len(resolved_ids)} submission_ids to extraction_ids")

        # =====================================================
        # Build uploaded JSON sources list
        # =====================================================
        uploaded_json_sources: List[Dict[str, Any]] = []

        for src in request.uploaded_json_sources:
            uploaded_json_sources.append({
                "data": src.data,
                "upload_type": src.upload_type.value,
                "merge_strategy": get_merge_strategy(src.upload_type),
                "source_name": src.source_name,
                "source_date": src.source_date,
                "consultation_type_code": src.consultation_type_code
            })

        total_sources = len(source_extraction_ids) + len(uploaded_json_sources)

        # =====================================================
        # Validate source count (min 2, max 4)
        # =====================================================
        if total_sources < 2:
            raise HTTPException(
                status_code=400,
                detail="At least 2 sources required for merge"
            )

        if total_sources > MAX_MERGE_SOURCES:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {MAX_MERGE_SOURCES} sources allowed for merge"
            )

        # =====================================================
        # Validate student_id requirement for JSON-only merges
        # =====================================================
        student_id = request.student_id
        if len(source_extraction_ids) == 0:
            # JSON-only merge - student_id is required
            if not student_id:
                raise HTTPException(
                    status_code=400,
                    detail="student_id is required when merging only JSON uploads (no extractions provided)"
                )
            logger.debug(f"[MergeAPI] JSON-only merge with provided student_id: {student_id}")

        # =====================================================
        # Resolve template_code to consultation_type_code and validate access
        # =====================================================
        template_id, consultation_type_id, target_consultation_type_code = await resolve_template_to_consultation_type(
            template_code=request.target_template_code,
            counsellor_id=request.counsellor_id,
            supabase_client=supabase
        )

        # =====================================================
        # Generate extraction_id upfront
        # =====================================================
        extraction_id = str(uuid.uuid4())
        logger.info(f"[MergeAPI] Generated extraction_id: {extraction_id} for {total_sources} sources ({len(source_extraction_ids)} extractions + {len(uploaded_json_sources)} JSON) → template:{request.target_template_code} (type:{target_consultation_type_code})")

        # =====================================================
        # Create pending merge job in database
        # =====================================================
        try:
            merge_job = {
                "id": extraction_id,
                "status": "processing",
                "source_extraction_ids": source_extraction_ids,
                "target_template_code": request.target_template_code,
                "counsellor_id": request.counsellor_id,
                "merge_notes": request.merge_notes,
                "uploaded_json_count": len(uploaded_json_sources),
                "student_id": student_id,
                "created_at": datetime.utcnow().isoformat(),
            }
            supabase.table("merge_jobs").insert(merge_job).execute()
            logger.debug(f"[MergeAPI] Created merge job: {extraction_id}")
        except Exception as db_err:
            logger.warning(f"[MergeAPI] Could not create merge_jobs record (table may not exist): {db_err}")
            # Continue anyway - the merge will still work

        # =====================================================
        # Trigger background processing
        # =====================================================
        task = asyncio.create_task(
            _run_background_merge(
                extraction_id=extraction_id,
                source_extraction_ids=source_extraction_ids,
                target_template_code=request.target_template_code,
                target_consultation_type_code=target_consultation_type_code,
                counsellor_id=request.counsellor_id,
                merge_notes=request.merge_notes,
                uploaded_json_sources=uploaded_json_sources,
                student_id=student_id
            )
        )
        _active_merge_tasks[extraction_id] = task
        logger.debug(f"[MergeAPI] Background merge task created for: {extraction_id}")

        # =====================================================
        # HIPAA Audit: log merge creation
        # =====================================================
        client_ctx = getattr(http_request.state, "client", None)
        if client_ctx:
            try:
                asyncio.create_task(audit_service.log_phi_access(
                    client_context=client_ctx, request=http_request, response_status=200,
                    response_time_ms=0, resource_type="merge", action="create",
                    resource_id=extraction_id,
                    counsellor_id=uuid.UUID(request.counsellor_id) if request.counsellor_id else None,
                    student_id=student_id,
                ))
            except Exception:
                pass

        # =====================================================
        # Return immediately
        # =====================================================
        return MergeAsyncResponse(
            success=True,
            extraction_id=extraction_id,
            status="processing",
            message="Merge operation started. Use extraction_id to check status or receive webhook."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MergeAPI] ❌ Error starting merge: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to start merge")


async def _run_background_merge(
    extraction_id: str,
    source_extraction_ids: List[str],
    target_template_code: str,
    target_consultation_type_code: str,
    counsellor_id: str,
    merge_notes: Optional[str],
    uploaded_json_sources: List[Dict[str, Any]],
    student_id: Optional[str] = None
):
    """
    Background task to perform the actual merge operation.

    Args:
        extraction_id: Pre-generated extraction ID
        source_extraction_ids: List of extraction UUIDs to merge
        target_template_code: Target template code (for metadata)
        target_consultation_type_code: Derived consultation type code (for internal logic)
        counsellor_id: Counsellor performing the merge
        merge_notes: Optional notes
        uploaded_json_sources: List of JSON source dicts with upload_type and merge_strategy
        student_id: Optional student_id (required for JSON-only merges)
    """
    try:
        logger.debug(f"[MergeAPI] Starting background merge for: {extraction_id}")

        # Perform merge with pre-generated extraction_id
        result = await merge_service.merge_extractions(
            source_extraction_ids=source_extraction_ids,
            target_consultation_type_code=target_consultation_type_code,
            counsellor_id=counsellor_id,
            merge_notes=merge_notes,
            preview_only=False,
            supabase_client=supabase,
            uploaded_json_sources=uploaded_json_sources,
            extraction_id=extraction_id,
            student_id=student_id,
            target_template_code=target_template_code
        )

        if not result['success']:
            logger.error(f"[MergeAPI] Background merge failed for {extraction_id}: {result.get('error')}")
            # Update merge job status to failed
            try:
                supabase.table("merge_jobs").update({
                    "status": "failed",
                    "error": result.get('error'),
                    "completed_at": datetime.utcnow().isoformat()
                }).eq("id", extraction_id).execute()
            except Exception:
                pass
            # Send error webhook to notify EHR systems
            try:
                from services.webhook_service import send_error_webhook
                await send_error_webhook(
                    error_message=result.get('error', 'Merge failed'),
                    submission_id=extraction_id,
                    session_data={"counsellor_id": counsellor_id, "student_id": student_id},
                    source="merge",
                    error_code="MERGE_FAILED",
                )
            except Exception as webhook_err:
                logger.warning(f"[MergeAPI:WEBHOOK] Failed to send error webhook: {webhook_err}")
            return

        logger.info(f"[MergeAPI] ✅ Background merge completed: {extraction_id}")

        # Update merge job status to completed
        try:
            supabase.table("merge_jobs").update({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat()
            }).eq("id", extraction_id).execute()
        except Exception:
            pass

        # ⭐ Send webhook with standardized metadata
        try:
            from services.webhook_service import send_insights_webhook
            from datetime import datetime

            # Lookup student preferred_language for webhook
            _merge_student_id = result.get('student_id') or student_id
            _merge_preferred_language = None
            if _merge_student_id:
                try:
                    from services.supabase_service import supabase as sb
                    _plang_res = sb.table("students").select("preferred_language").eq("id", _merge_student_id).limit(1).execute()
                    if _plang_res.data:
                        _merge_preferred_language = _plang_res.data[0].get("preferred_language")
                except Exception:
                    pass

            # Build standardized metadata (same structure as API response)
            standardized_metadata = {
                "correlation_id": None,  # Merges don't have correlation_id
                "submission_id": None,  # Merged extractions don't have submission_id
                "extraction_id": extraction_id,
                "session_id": None,  # Merges don't have a single session
                "counsellor_id": counsellor_id,
                "student_id": _merge_student_id,
                "template_code": target_template_code,  # Target template for merge
                "mode": "merge",  # Special mode for merged extractions
                "segment_count": len(result.get('merged_data', {})),
                "processing_mode": None,  # Merges don't have processing_mode
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "preferred_language": _merge_preferred_language,
            }

            # Check if realtime is enabled (skip webhook if so)
            from services.realtime_publisher_service import is_realtime_enabled_for_school
            from services.supabase_service import get_counsellor_school_id_cached
            import uuid as uuid_mod
            _school_id = get_counsellor_school_id_cached(uuid_mod.UUID(counsellor_id)) if counsellor_id else None
            if _school_id and is_realtime_enabled_for_school(_school_id):
                logger.debug(f"[MergeAPI] Skipping webhook - realtime subscription enabled for school")
            else:
                await send_insights_webhook(
                    insights=result['merged_data'],
                    metadata=standardized_metadata,
                    source="merge"
                )
                logger.debug(f"[MergeAPI] Webhook sent for: {extraction_id}")

        except Exception as webhook_err:
            logger.warning(f"[MergeAPI] ⚠️ Webhook failed for {extraction_id}: {webhook_err}")

        # Publish to realtime table (fire-and-forget) - use extraction_id as submission_id for merges
        try:
            from services.realtime_publisher_service import publish_extraction_response_fire_and_forget
            from services.supabase_service import get_counsellor_school_id_cached
            import uuid as uuid_mod
            school_id_for_realtime = get_counsellor_school_id_cached(uuid_mod.UUID(counsellor_id)) if counsellor_id else None
            if school_id_for_realtime:
                # Look up UHID from students table
                _merge_uhid = ""
                _merge_student_id = result.get('student_id') or student_id
                if _merge_student_id:
                    try:
                        _p_result = supabase.table("students").select("student_id").eq("id", _merge_student_id).limit(1).execute()
                        if _p_result.data:
                            _merge_uhid = _p_result.data[0].get("student_id", "")
                    except Exception:
                        pass
                _rt_recording_metadata = None
                try:
                    _me_result = supabase.table("extractions").select(
                        "recording_metadata_json"
                    ).eq("id", extraction_id).limit(1).execute()
                    if _me_result.data:
                        _rt_recording_metadata = _me_result.data[0].get("recording_metadata_json") or {}
                except Exception:
                    pass
                asyncio.create_task(publish_extraction_response_fire_and_forget(
                    submission_id=extraction_id,  # extraction_id used as submission_id (merges have no processing job)
                    school_id=school_id_for_realtime,
                    counsellor_id=counsellor_id,
                    extraction_id=extraction_id,
                    insights=result['merged_data'],
                    uhid=_merge_uhid,
                    recording_metadata=_rt_recording_metadata,
                ))
        except Exception as e:
            logger.warning(f"[MergeAPI] Failed to schedule realtime publish: {e}")

        # EHR Integration: Push merged extraction to EHR (fire-and-forget)
        try:
            from services.ehr_routing_service import schedule_ehr_sync

            # Build patient_info from students table + most recent source extraction metadata
            _ehr_student_info = {}
            _ehr_student_uuid = result.get('student_id') or student_id
            if _ehr_student_uuid:
                try:
                    _p_result = supabase.table("students").select("student_id, add_info").eq("id", _ehr_student_uuid).limit(1).execute()
                    if _p_result.data:
                        _ehr_student_info["student_id"] = _p_result.data[0].get("student_id", "")  # UHID
                        _add_info = _p_result.data[0].get("add_info") or {}
                        _ehr_student_info["neopead_add_info"] = _add_info
                        _ehr_student_info["visit_number"] = _add_info.get("visit_number", "")
                        _ehr_student_info["consultant_id"] = _add_info.get("consultant_id", 0)
                        _ehr_student_info["modified_user_id"] = _add_info.get("modified_user_id", 0)
                except Exception:
                    pass

            # Reconstruct recording_metadata_json from DB (merges have no live session).
            # Primary: most recent source extraction's recording_metadata_json.
            # Fallback: merged extraction's own recording_metadata_json if populated.
            _rec_meta = {}
            if source_extraction_ids:
                try:
                    _latest_src = supabase.table("extractions")\
                        .select("recording_metadata_json")\
                        .in_("id", source_extraction_ids)\
                        .order("created_at", desc=True)\
                        .limit(1).execute()
                    if _latest_src.data:
                        _rec_meta = _latest_src.data[0].get("recording_metadata_json") or {}
                except Exception:
                    pass

            if not _rec_meta:
                try:
                    _me_result = supabase.table("extractions")\
                        .select("recording_metadata_json")\
                        .eq("id", extraction_id).limit(1).execute()
                    if _me_result.data:
                        _rec_meta = _me_result.data[0].get("recording_metadata_json") or {}
                except Exception:
                    pass

            if _rec_meta:
                # Aosta fields
                _ehr_student_info["ip_id"] = _rec_meta.get("ip_id")
                _ehr_student_info["op_id"] = _rec_meta.get("op_id")
                # KG fields (visit_id + role are required by the KG formatter)
                _ehr_student_info["visit_id"] = _rec_meta.get("visit_id", "")
                _ehr_student_info["role"] = _rec_meta.get("role", "")
                _ehr_student_info["school_code"] = _rec_meta.get("school_code", "")
                # Raster fields — recording_metadata wins over students.add_info defaults
                if "visit_number" in _rec_meta:
                    _ehr_student_info["visit_number"] = _rec_meta.get("visit_number", "")
                if "consultant_id" in _rec_meta:
                    _ehr_student_info["consultant_id"] = _rec_meta.get("consultant_id", 0)
                _rm_cuid = _rec_meta.get("created_user_id") or _rec_meta.get("modified_user_id")
                if _rm_cuid is not None:
                    _ehr_student_info["created_user_id"] = _rm_cuid
                    _ehr_student_info["modified_user_id"] = _rm_cuid
                if "sex" in _rec_meta:
                    _ehr_student_info["sex"] = _rec_meta.get("sex")
                from services.raster_api_service import extract_raster_template_id
                _ehr_student_info["template_id_raster"] = extract_raster_template_id(_rec_meta)
                # GEM_CASE_SHEET / GCC_REVIEW fields (sent to Aosta URL with Template_id/Template_Name)
                _ehr_student_info["template_id_aosta"] = _rec_meta.get("template_id") or _rec_meta.get("Template_id") or ""
                _ehr_student_info["template_name_aosta"] = _rec_meta.get("template_name") or _rec_meta.get("Template_Name") or ""

            # KG requires patient_uuid (the extractions.student_id UUID, not the UHID string)
            if _ehr_student_uuid:
                _ehr_student_info["patient_uuid"] = _ehr_student_uuid

            # school_code: prefer the counsellor's school (mirrors extraction_service.py:2018-2024).
            # KG source extractions don't store school_code in recording_metadata_json, so the
            # _rec_meta fallback above resolves to "" — fetch from the counsellors → schools join instead.
            if counsellor_id and not _ehr_student_info.get("school_code"):
                try:
                    _doc = supabase.table("counsellors")\
                        .select("schools(school_code)")\
                        .eq("id", str(counsellor_id)).limit(1).execute()
                    if _doc.data:
                        _h = _doc.data[0].get("schools") or {}
                        _ehr_student_info["school_code"] = _h.get("school_code", "")
                except Exception as _e:
                    logger.warning(f"[MergeAPI] Failed to fetch school_code from counsellor join: {_e}")

            _ehr_student_info["counsellor_id"] = counsellor_id

            _ehr_scheduled = schedule_ehr_sync(
                counsellor_id=counsellor_id,
                extraction_data=result['merged_data'],
                patient_info=_ehr_student_info,
                template_code=target_template_code,
                is_edit=False,
                extraction_id=extraction_id,
            )
            if _ehr_scheduled:
                logger.info(f"[MergeAPI] EHR sync scheduled for merged extraction {extraction_id}")
        except Exception as e:
            logger.warning(f"[MergeAPI] Failed to schedule EHR sync for merge: {e}")

    except Exception as e:
        logger.error(f"[MergeAPI] ❌ Background merge error for {extraction_id}: {str(e)}")
        # Update merge job status to failed
        try:
            supabase.table("merge_jobs").update({
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.utcnow().isoformat()
            }).eq("id", extraction_id).execute()
        except Exception:
            pass
        # Send error webhook to notify EHR systems
        try:
            from services.webhook_service import send_error_webhook
            await send_error_webhook(
                error_message=str(e),
                submission_id=extraction_id,
                session_data={"counsellor_id": counsellor_id, "student_id": student_id},
                source="merge",
                error_code="MERGE_FAILED",
            )
        except Exception as webhook_err:
            logger.warning(f"[MergeAPI:WEBHOOK] Failed to send error webhook: {webhook_err}")

    finally:
        # Clean up task tracking
        if extraction_id in _active_merge_tasks:
            del _active_merge_tasks[extraction_id]


@router.get("/merge/status/{extraction_id}", response_model=MergeStatusResponse, status_code=200)
async def get_merge_status(
    request: Request,
    extraction_id: str,
    counsellor_id: str = Query(None, description="Counsellor ID for EHR access verification"),
    _auth = Depends(verify_counsellor_access)
):
    """
    Check the status of a merge operation.

    **Returns:**
    - `processing`: Merge is in progress
    - `completed`: Merge finished successfully (includes merged_data)
    - `failed`: Merge failed (includes error message)

    **Use Cases:**
    - Poll after calling `/merge` to wait for completion
    - Check if merge completed before webhook arrived
    """
    try:
        # Check if merge is still processing
        if extraction_id in _active_merge_tasks:
            task = _active_merge_tasks[extraction_id]
            if not task.done():
                return MergeStatusResponse(
                    extraction_id=extraction_id,
                    status="processing",
                    progress="Merge in progress..."
                )

        # Check merge_jobs table for status
        try:
            job_result = supabase.table("merge_jobs").select("*").eq("id", extraction_id).limit(1).execute()
            if job_result.data:
                job = job_result.data[0]
                if job["status"] == "failed":
                    return MergeStatusResponse(
                        extraction_id=extraction_id,
                        status="failed",
                        error=job.get("error"),
                        created_at=job.get("created_at")
                    )
        except Exception:
            pass  # Table might not exist

        # Check if extraction exists in extractions
        extraction_result = supabase.table("extractions").select(
            "id, original_extraction_json, merge_metadata, is_merged, created_at"
        ).eq("id", extraction_id).limit(1).execute()

        if extraction_result.data:
            extraction = extraction_result.data[0]
            if extraction.get("is_merged"):
                # Build merge_metadata from stored data
                stored_metadata = extraction.get("merge_metadata", {})
                merge_metadata = None
                if stored_metadata:
                    try:
                        merge_metadata = MergeMetadata(
                            source_count=stored_metadata.get("source_count", 0),
                            target_type_code=stored_metadata.get("target_type_code", ""),
                            merge_timestamp=stored_metadata.get("merge_timestamp", ""),
                            doctor_confirmed=stored_metadata.get("doctor_confirmed", True),
                            merge_notes=stored_metadata.get("merge_notes"),
                            conflict_count=stored_metadata.get("conflict_count", 0),
                            conflicts_resolved=stored_metadata.get("conflicts_resolved", []),
                            cross_type_scenario=stored_metadata.get("cross_type_scenario", ""),
                            consultation_types_merged=stored_metadata.get("consultation_types_merged", [])
                        )
                    except Exception:
                        pass

                return MergeStatusResponse(
                    extraction_id=extraction_id,
                    status="completed",
                    merged_data=extraction.get("original_extraction_json"),
                    merge_metadata=merge_metadata,
                    created_at=extraction.get("created_at"),
                    completed_at=extraction.get("created_at")  # Same as created for merged
                )

        # Not found - might still be processing or invalid ID
        if extraction_id in _active_merge_tasks:
            return MergeStatusResponse(
                extraction_id=extraction_id,
                status="processing",
                progress="Merge in progress..."
            )

        raise HTTPException(
            status_code=404,
            detail="Merge job not found"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MergeAPI] Error checking merge status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to check merge status")


@router.post("/merge/preview", response_model=MergeResponse, status_code=200)
async def preview_merge(
    http_request: Request,
    request: MergePreviewRequest,
    _auth = Depends(verify_counsellor_access)
):
    """
    Preview merge without saving to database.

    This endpoint performs AI-powered contextual merging but does NOT save
    the result. Use this to show counsellors the merged result before confirming.

    **Use Cases:**
    - Counsellor wants to review merged extraction before committing
    - Check for conflicts or missing data before save
    - Validate merge quality before final approval

    **Process:**
    - Same as /merge endpoint, but preview_only=True
    - No database writes
    - Returns merged data and metadata

    **Returns:**
    - Merged data (not saved)
    - Merge metadata
    - preview=True flag

    **Example:**
    ```json
    {
        "source_extraction_ids": ["uuid1", "uuid2"],
        "target_template_code": "DISCHARGE_GENERAL",
        "counsellor_id": "uuid"
    }
    ```

    Or using submission_ids:
    ```json
    {
        "source_submission_ids": ["submission-uuid1", "submission-uuid2"],
        "target_template_code": "DISCHARGE_GENERAL",
        "counsellor_id": "uuid"
    }
    ```
    """
    try:
        # =====================================================
        # Validate EHR client has access to this counsellor (school-scoped)
        # =====================================================
        await validate_counsellor_from_body(http_request, request.counsellor_id)

        # =====================================================
        # Resolve submission_ids to extraction_ids if provided
        # =====================================================
        source_extraction_ids = list(request.source_extraction_ids)  # Copy to avoid mutation

        if request.source_submission_ids:
            if source_extraction_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot use both source_extraction_ids and source_submission_ids. Use one or the other."
                )

            # Resolve submission_ids to extraction_ids
            resolved_ids, failed_ids = await resolve_submission_ids_to_extraction_ids(
                request.source_submission_ids
            )

            if failed_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Some submissions could not be resolved. They may still be processing."
                )

            source_extraction_ids = resolved_ids
            logger.debug(f"[MergeAPI] Resolved {len(resolved_ids)} submission_ids to extraction_ids")

        # =====================================================
        # Build uploaded JSON sources list
        # =====================================================
        uploaded_json_sources: List[Dict[str, Any]] = []

        for src in request.uploaded_json_sources:
            uploaded_json_sources.append({
                "data": src.data,
                "upload_type": src.upload_type.value,
                "merge_strategy": get_merge_strategy(src.upload_type),
                "source_name": src.source_name,
                "source_date": src.source_date,
                "consultation_type_code": src.consultation_type_code
            })

        total_sources = len(source_extraction_ids) + len(uploaded_json_sources)
        logger.info(f"[MergeAPI] Received preview request: {total_sources} sources ({len(source_extraction_ids)} DB + {len(uploaded_json_sources)} uploaded) → template:{request.target_template_code}")

        # =====================================================
        # Validate source count (min 2, max 4)
        # =====================================================
        if total_sources < 2:
            raise HTTPException(
                status_code=400,
                detail="At least 2 sources required for merge"
            )

        if total_sources > MAX_MERGE_SOURCES:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {MAX_MERGE_SOURCES} sources allowed for merge"
            )

        # =====================================================
        # Validate student_id requirement for JSON-only merges
        # =====================================================
        student_id = request.student_id
        if len(source_extraction_ids) == 0 and not student_id:
            raise HTTPException(
                status_code=400,
                detail="student_id is required when merging only JSON uploads (no extractions provided)"
            )

        # =====================================================
        # Resolve template_code to consultation_type_code and validate access
        # =====================================================
        template_id, consultation_type_id, target_consultation_type_code = await resolve_template_to_consultation_type(
            template_code=request.target_template_code,
            counsellor_id=request.counsellor_id,
            supabase_client=supabase
        )

        # Perform merge (preview=True, no save)
        result = await merge_service.merge_extractions(
            source_extraction_ids=source_extraction_ids,
            target_consultation_type_code=target_consultation_type_code,
            counsellor_id=request.counsellor_id,
            merge_notes=None,
            preview_only=True,
            supabase_client=supabase,
            uploaded_json_sources=uploaded_json_sources,
            student_id=student_id,
            target_template_code=request.target_template_code
        )

        if not result['success']:
            logger.error(f"[MergeAPI] Preview failed: {result.get('error')}")
            from services.error_utils import sanitize_error_message
            raise HTTPException(status_code=400, detail=sanitize_error_message(result.get('error', 'Merge failed')))

        logger.info(f"[MergeAPI] ✅ Preview successful: {result['source_count']} sources merged")

        # Build response
        merge_context = result['merge_metadata']
        merge_metadata = MergeMetadata(
            source_count=merge_context['source_count'],
            target_template_code=request.target_template_code,
            merge_timestamp=merge_context['latest_date'],
            doctor_confirmed=False,
            merge_notes="Preview only - not saved",
            conflict_count=len(merge_context.get('conflict_map', {})),
            conflicts_resolved=list(merge_context.get('conflict_map', {}).keys()),
            cross_type_scenario=merge_context['cross_type_scenario'],
            consultation_types_merged=merge_context['consultation_types']
        )

        return MergeResponse(
            success=True,
            extraction_id=None,
            submission_id=None,  # Preview doesn't create a submission
            merged_data=result['merged_data'],
            merge_metadata=merge_metadata,
            preview=True
        )

    except HTTPException:
        raise
    except SchemaCompatibilityError as e:
        # Schema incompatibility (e.g., OPHTHAL_OCR source with non-OPHTHAL target)
        logger.error(f"[MergeAPI] ❌ Schema compatibility error in preview: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail="Schema incompatibility detected"
        )
    except Exception as e:
        logger.error(f"[MergeAPI] ❌ Unexpected preview error: {str(e)}")
        raise HTTPException(status_code=500, detail="Preview failed")


# =====================================================
# Query Endpoints
# =====================================================

@router.get("/student/{student_id}/timeline", response_model=StudentTimelineResponse, status_code=200)
async def get_student_timeline(
    request: Request,
    student_id: str,
    consultation_type_code: Optional[str] = None,
    _auth = Depends(verify_student_access)
):
    """
    Get chronological timeline of all extractions for a student.

    This endpoint returns all extractions for a specific student, ordered
    chronologically from newest to oldest. Useful for:
    - Displaying student history
    - Selecting extractions to merge
    - Viewing merged vs original extractions

    **Query Parameters:**
    - `consultation_type_code` (optional): Filter by consultation type

    **Returns:**
    - List of extractions with metadata
    - Includes merge status (is_merged, source_count)
    - Ordered by creation date (newest first)

    **Example:**
    ```
    GET /api/v1/extractions/student/550e8400-e29b-41d4-a716-446655440050/timeline
    GET /api/v1/extractions/student/550e8400-e29b-41d4-a716-446655440050/timeline?consultation_type_code=OP
    ```
    """
    try:
        logger.info(f"[MergeAPI] Fetching timeline for student: {student_id}")

        # Call database function
        result = supabase.rpc(
            'get_student_extraction_timeline',
            {'p_student_identifier': student_id}
        ).execute()

        if not result.data:
            logger.debug(f"[MergeAPI] No extractions found for student: {student_id}")
            return StudentTimelineResponse(
                student_id=student_id,
                extractions=[],
                total_count=0
            )

        # Filter by consultation type if specified
        extractions_data = result.data
        if consultation_type_code:
            extractions_data = [e for e in extractions_data if e['consultation_type_code'] == consultation_type_code]

        # Build response
        extractions = [
            StudentTimelineExtraction(
                extraction_id=e['extraction_id'],
                consultation_type_code=e['consultation_type_code'],
                consultation_type_name=e['consultation_type_name'],
                created_at=e['created_at'],
                counsellor_name=e['counsellor_name'],
                is_merged=e['is_merged'],
                source_count=e['source_count'],
                segment_count=e['segment_count']
            )
            for e in extractions_data
        ]

        logger.debug(f"[MergeAPI] Found {len(extractions)} extractions for student timeline")

        # HIPAA Audit: log student timeline access
        client_ctx = getattr(request.state, "client", None)
        if client_ctx:
            try:
                asyncio.create_task(audit_service.log_phi_access(
                    client_context=client_ctx, request=request, response_status=200,
                    response_time_ms=0, resource_type="patient", action="read",
                    student_id=student_id,
                ))
            except Exception:
                pass

        return StudentTimelineResponse(
            student_id=student_id,
            extractions=extractions,
            total_count=len(extractions)
        )

    except Exception as e:
        logger.error(f"[MergeAPI] ❌ Error fetching timeline: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Failed to fetch student timeline")


@router.get("/{extraction_id}/merge-info", response_model=MergeLineageResponse, status_code=200)
async def get_merge_info(
    request: Request,
    extraction_id: str,
    _auth = Depends(verify_extraction_access)
):
    """
    Get merge lineage information for a merged extraction.

    This endpoint returns details about which extractions were merged
    to create this extraction, including:
    - Source extraction IDs
    - Chronological order
    - Merge strategy used
    - Merge metadata (conflicts, notes, etc.)

    **Only works for merged extractions** (is_merged=TRUE)

    **Returns:**
    - List of source extractions with metadata
    - Merge metadata
    - Chronological ordering (1=oldest, N=newest)

    **Example:**
    ```
    GET /api/v1/extractions/550e8400-e29b-41d4-a716-446655440003/merge-info
    ```
    """
    try:
        logger.debug(f"[MergeAPI] Fetching merge info for extraction: {extraction_id}")

        # Get extraction record
        extraction_result = supabase.table('extractions').select('*').eq('id', extraction_id).single().execute()

        if not extraction_result.data:
            raise HTTPException(status_code=404, detail="Extraction not found")

        extraction = extraction_result.data

        # Check if this is a merged extraction
        if not extraction.get('is_merged'):
            raise HTTPException(status_code=400, detail="Extraction is not a merged extraction")

        # Get merge lineage using database function
        lineage_result = supabase.rpc(
            'get_merge_lineage',
            {'p_merged_extraction_id': extraction_id}
        ).execute()

        if not lineage_result.data:
            raise HTTPException(status_code=404, detail="No merge lineage found for this extraction")

        # Build source extractions list
        source_extractions = [
            SourceExtractionInfo(
                source_extraction_id=s['source_extraction_id'],
                consultation_type_code=s['consultation_type_code'],
                consultation_type_name=s.get('consultation_type_name', s['consultation_type_code']),
                created_at=s['created_at'],
                counsellor_name=s.get('counsellor_name'),
                merge_order=s['merge_order'],
                merge_strategy=s['merge_strategy']
            )
            for s in lineage_result.data
        ]

        # Build merge metadata
        merge_metadata_json = extraction.get('merge_metadata', {})
        merge_metadata = MergeMetadata(**merge_metadata_json)

        logger.debug(f"[MergeAPI] Found {len(source_extractions)} source extractions for {extraction_id}")

        return MergeLineageResponse(
            merged_extraction_id=extraction_id,
            is_merged=True,
            source_extractions=source_extractions,
            merge_metadata=merge_metadata
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MergeAPI] ❌ Error fetching merge info: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch merge info")


# =====================================================
# Schema Transformation Endpoints
# =====================================================

class TransformSchemaRequest(BaseModel):
    """Request model for schema transformation."""
    data: Dict[str, Any]
    target_schema: str


class TransformSchemaResponse(BaseModel):
    """Response model for schema transformation."""
    success: bool
    transformed_data: Optional[Dict[str, Any]] = None
    original_data: Optional[Dict[str, Any]] = None
    source_schema_detected: Optional[str] = None
    transformation_applied: bool
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class DetectSchemaRequest(BaseModel):
    """Request model for schema detection."""
    data: Dict[str, Any]


class DetectSchemaResponse(BaseModel):
    """Response model for schema detection."""
    schema_type: str
    confidence: float


@router.post("/transform-schema", response_model=TransformSchemaResponse, status_code=200)
async def transform_schema_endpoint(
    http_request: Request,
    request: TransformSchemaRequest,
    counsellor_id: str = Query(..., description="Counsellor ID for EHR access verification"),
    _auth = Depends(verify_counsellor_access)
):
    """
    Transform JSON data from one schema format to another.

    This endpoint detects the source schema format and transforms it to the
    target schema format. Useful for:
    - Previewing how uploaded JSON will be transformed before merge
    - Converting external data formats to internal schema
    - Validating data compatibility

    **Supported Transformations:**
    - OPHTHAL_OCR → OPHTHAL_FULL (ophthalmology records)

    **Request:**
    ```json
    {
        "data": { ... },
        "target_schema": "OPHTHAL_FULL"
    }
    ```

    **Returns:**
    - Transformed data in target schema format
    - Original data preserved for reference
    - Metadata about the transformation (field counts, unmapped fields)
    """
    try:
        logger.info(f"[SchemaTransformAPI] Received transform request: target={request.target_schema}")

        data = request.data
        target_schema = request.target_schema

        if not data:
            return TransformSchemaResponse(
                success=False,
                transformation_applied=False,
                error="No data provided"
            )

        # Detect source schema
        source_schema = detect_schema_type(data)
        logger.debug(f"[SchemaTransformAPI] Detected source schema: {source_schema}")

        # Check if transformation is needed/supported
        if source_schema == "UNKNOWN":
            return TransformSchemaResponse(
                success=True,
                transformed_data=data,
                original_data=data,
                source_schema_detected=source_schema,
                transformation_applied=False,
                metadata={
                    "message": "Unknown source schema - no transformation applied",
                    "original_field_count": len(data)
                }
            )

        # Check if already in target format
        if (source_schema == target_schema or
            (source_schema == "OPHTHAL_FULL" and "OPHTHAL" in target_schema) or
            (source_schema == "OPHTHAL_FULL_FLAT" and "OPHTHAL" in target_schema)):
            return TransformSchemaResponse(
                success=True,
                transformed_data=data,
                original_data=data,
                source_schema_detected=source_schema,
                transformation_applied=False,
                metadata={
                    "message": "Source already in target format - no transformation needed",
                    "original_field_count": len(data)
                }
            )

        # Perform transformation
        transformer = SchemaTransformer()
        transformed_data = transformer.transform_to_ophthal_full(data, source_schema)

        # Gather unmapped fields
        unmapped_fields = list(transformer.unmapped_fields.keys()) if transformer.unmapped_fields else []

        logger.info(
            f"[SchemaTransformAPI] ✅ Transformation complete: "
            f"{source_schema} → {target_schema}, "
            f"{len(data)} fields → {len(transformed_data)} fields"
        )

        return TransformSchemaResponse(
            success=True,
            transformed_data=transformed_data,
            original_data=data,
            source_schema_detected=source_schema,
            transformation_applied=True,
            metadata={
                "original_field_count": len(data),
                "transformed_field_count": len(transformed_data),
                "unmapped_fields": unmapped_fields
            }
        )

    except Exception as e:
        logger.error(f"[SchemaTransformAPI] ❌ Transformation failed: {str(e)}")
        return TransformSchemaResponse(
            success=False,
            transformation_applied=False,
            error=str(e)
        )


@router.post("/detect-schema", response_model=DetectSchemaResponse, status_code=200)
async def detect_schema_endpoint(
    http_request: Request,
    request: DetectSchemaRequest,
    counsellor_id: str = Query(..., description="Counsellor ID for EHR access verification"),
    _auth = Depends(verify_counsellor_access)
):
    """
    Detect the schema type of JSON data.

    This endpoint analyzes JSON data and returns the detected schema type.
    Useful for:
    - Determining if data needs transformation before merge
    - Validating data format
    - UI decisions about how to display/process data

    **Detectable Schema Types:**
    - OPHTHAL_OCR - External OCR-extracted format (snake_case, separate OD/OS keys)
    - OPHTHAL_FULL - Internal ophthalmology format (camelCase, nested rightEye/leftEye)
    - OPHTHAL_FULL_FLAT - Flattened internal format (underscore-joined keys)
    - UNKNOWN - Unrecognized format

    **Request:**
    ```json
    {
        "data": { ... }
    }
    ```

    **Returns:**
    - schema_type: Detected schema type
    - confidence: Confidence score (0.0 to 1.0)
    """
    try:
        logger.info(f"[SchemaDetectAPI] Received detect request")

        data = request.data

        if not data:
            return DetectSchemaResponse(
                schema_type="UNKNOWN",
                confidence=0.0
            )

        # Detect schema type
        schema_type = detect_schema_type(data)

        # Calculate confidence based on matching indicators
        ophthal_ocr_indicators = [
            "patient_info", "visual_acuity_od", "visual_acuity_os",
            "slit_lamp_od", "slit_lamp_os", "fundus_od", "fundus_os",
            "iop_measurements", "additional_tests", "form_subtype",
            "low_confidence_fields"
        ]

        ophthal_full_indicators = [
            "patientDemographics", "visualAcuityAndRefraction",
            "slitLampExamination", "fundusExamination", "intraocularpressure",
            "binocularVisionTests", "dryEyeAssessment"
        ]

        ophthal_full_flat_indicators = [
            "patientDemographics_name",
            "visualAcuityAndRefraction_rightEye_unaidedVision",
            "slitLampExamination_rightEye_lids"
        ]

        # Count matching indicators
        if schema_type == "OPHTHAL_OCR":
            matches = sum(1 for key in ophthal_ocr_indicators if key in data)
            confidence = min(matches / 5.0, 1.0)  # 5 matches = 100% confidence
        elif schema_type == "OPHTHAL_FULL":
            matches = sum(1 for key in ophthal_full_indicators if key in data)
            confidence = min(matches / 4.0, 1.0)  # 4 matches = 100% confidence
        elif schema_type == "OPHTHAL_FULL_FLAT":
            matches = sum(1 for key in ophthal_full_flat_indicators if key in data)
            confidence = min(matches / 2.0, 1.0)  # 2 matches = 100% confidence
        else:
            confidence = 0.0

        logger.info(f"[SchemaDetectAPI] ✅ Detected schema: {schema_type} (confidence: {confidence:.2f})")

        return DetectSchemaResponse(
            schema_type=schema_type,
            confidence=round(confidence, 2)
        )

    except Exception as e:
        logger.error(f"[SchemaDetectAPI] ❌ Detection failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Schema detection failed")


# =====================================================
# Lookup Endpoints
# =====================================================

class ExtractionLookupResponse(BaseModel):
    """Response model for extraction lookup by submission_id or session_id."""
    extraction_id: Optional[str] = None
    submission_id: Optional[str] = None
    session_id: Optional[str] = None
    consultation_type_code: Optional[str] = None
    counsellor_id: Optional[str] = None
    student_id: Optional[str] = None
    created_at: Optional[str] = None
    found: bool
    message: Optional[str] = None


async def _lookup_extraction_by_submission_id(submission_id: str) -> ExtractionLookupResponse:
    """
    Internal helper to lookup extraction by submission_id.
    Reused by both the GET endpoint and merge resolution.
    """
    # Query extractions by submission_id
    result = supabase.table('extractions').select(
        'id, submission_id, session_id, consultation_type_id, counsellor_id, student_id, created_at'
    ).eq('submission_id', submission_id).execute()

    if not result.data or len(result.data) == 0:
        # Check if submission_id exists in processing_jobs (maybe still processing)
        job_result = supabase.table('processing_jobs').select(
            'id, submission_id, session_id, status, progress_percentage'
        ).eq('submission_id', submission_id).execute()

        if job_result.data and len(job_result.data) > 0:
            job = job_result.data[0]
            status = job.get('status', 'UNKNOWN')
            progress = job.get('progress_percentage', 0)

            return ExtractionLookupResponse(
                extraction_id=None,
                submission_id=submission_id,
                session_id=job.get('session_id'),
                found=False,
                message=f"Processing in progress: {status} ({progress}%). Extraction not yet available."
            )

        return ExtractionLookupResponse(
            extraction_id=None,
            submission_id=submission_id,
            found=False,
            message="No extraction found for this submission_id"
        )

    extraction = result.data[0]

    # Get consultation type code
    consultation_type_code = None
    if extraction.get('consultation_type_id'):
        ct_result = supabase.table('consultation_types').select('type_code').eq(
            'id', extraction['consultation_type_id']
        ).execute()
        if ct_result.data:
            consultation_type_code = ct_result.data[0]['type_code']

    return ExtractionLookupResponse(
        extraction_id=extraction['id'],
        submission_id=submission_id,
        session_id=extraction.get('session_id'),
        consultation_type_code=consultation_type_code,
        counsellor_id=extraction.get('counsellor_id'),
        student_id=extraction.get('student_id'),
        created_at=extraction.get('created_at'),
        found=True,
        message=None
    )


async def resolve_submission_ids_to_extraction_ids(
    submission_ids: List[str]
) -> Tuple[List[str], List[str]]:
    """
    Resolve multiple submission_ids to extraction_ids using the shared lookup helper.

    Args:
        submission_ids: List of submission UUIDs from recording flow

    Returns:
        Tuple of (resolved_extraction_ids, failed_submission_ids)
    """
    if not submission_ids:
        return [], []

    resolved_ids = []
    failed_ids = []

    for submission_id in submission_ids:
        try:
            lookup_result = await _lookup_extraction_by_submission_id(submission_id)

            if lookup_result.found and lookup_result.extraction_id:
                resolved_ids.append(lookup_result.extraction_id)
                logger.debug(f"[MergeAPI] Resolved submission_id {submission_id} → extraction_id {lookup_result.extraction_id}")
            else:
                logger.warning(f"[MergeAPI] Failed to resolve submission_id {submission_id}: {lookup_result.message}")
                failed_ids.append(submission_id)

        except Exception as e:
            logger.error(f"[MergeAPI] Error resolving submission_id {submission_id}: {str(e)}")
            failed_ids.append(submission_id)

    return resolved_ids, failed_ids


@router.get("/by-submission/{submission_id}", response_model=ExtractionLookupResponse, status_code=200)
async def get_extraction_by_submission_id(
    request: Request,
    submission_id: str,
    _auth = Depends(verify_submission_access)
):
    """
    Get extraction_id from a submission_id.

    This endpoint allows clients who only have a submission_id (from the
    recording/processing flow) to look up the corresponding extraction_id
    for use with merge APIs.

    **Relationship Chain:**
    - `submission_id` is generated when recording is submitted for processing
    - `processing_jobs` table tracks the processing with this submission_id
    - `extractions` table stores the extraction result with submission_id foreign key

    **Use Case:**
    After completing a recording session and receiving a submission_id from
    `/api/v1/option1/recording/chunk` (with is_last=true), use this endpoint
    to get the extraction_id for merge operations.

    **Example:**
    ```
    GET /api/v1/extractions/by-submission/550e8400-e29b-41d4-a716-446655440050
    ```

    **Returns:**
    - extraction_id: UUID of the extraction (for use with merge APIs)
    - session_id: Recording session UUID
    - consultation_type_code: Type of consultation (e.g., OP, OPHTHAL_FULL)
    - counsellor_id, student_id: Associated entities
    - found: Boolean indicating if extraction was found
    - message: Error message if not found
    """
    try:
        logger.info(f"[LookupAPI] Looking up extraction for submission_id: {submission_id}")

        # Use shared helper function
        result = await _lookup_extraction_by_submission_id(submission_id)

        if result.found:
            logger.debug(f"[LookupAPI] Found extraction {result.extraction_id} for submission_id {submission_id}")
        else:
            logger.debug(f"[LookupAPI] {result.message}")

        return result

    except Exception as e:
        logger.error(f"[LookupAPI] ❌ Error looking up extraction: {str(e)}")
        raise HTTPException(status_code=500, detail="Lookup failed")


@router.get("/by-session/{session_id}", response_model=ExtractionLookupResponse, status_code=200)
async def get_extraction_by_session_id(
    request: Request,
    session_id: str,
    _auth = Depends(verify_session_access)
):
    """
    Get extraction_id from a recording session_id.

    This endpoint allows clients who have a session_id (correlation_id from
    recording start) to look up the corresponding extraction_id.

    **Use Case:**
    If you started a recording and have the correlation_id/session_id but
    not the submission_id, use this endpoint to find the extraction.

    **Example:**
    ```
    GET /api/v1/extractions/by-session/550e8400-e29b-41d4-a716-446655440050
    ```

    **Returns:**
    - extraction_id: UUID of the extraction (for use with merge APIs)
    - submission_id: The processing job submission ID
    - consultation_type_code: Type of consultation
    - found: Boolean indicating if extraction was found
    """
    try:
        logger.info(f"[LookupAPI] Looking up extraction for session_id: {session_id}")

        # Query extractions by session_id
        result = supabase.table('extractions').select(
            'id, submission_id, session_id, consultation_type_id, counsellor_id, student_id, created_at'
        ).eq('session_id', session_id).order('created_at', desc=True).limit(1).execute()

        if not result.data or len(result.data) == 0:
            # Check recording_sessions status
            session_result = supabase.table('recording_sessions').select(
                'id, correlation_id, status'
            ).eq('id', session_id).execute()

            if session_result.data and len(session_result.data) > 0:
                session = session_result.data[0]
                status = session.get('status', 'UNKNOWN')

                logger.debug(f"[LookupAPI] Session {session_id} found: status={status}")

                return ExtractionLookupResponse(
                    extraction_id=None,
                    submission_id=None,
                    session_id=session_id,
                    found=False,
                    message=f"Session status: {status}. Extraction not yet available."
                )

            logger.warning(f"[LookupAPI] No extraction or session found for session_id: {session_id}")
            return ExtractionLookupResponse(
                extraction_id=None,
                submission_id=None,
                session_id=session_id,
                found=False,
                message="No extraction found for this session_id"
            )

        extraction = result.data[0]

        # Get consultation type code
        consultation_type_code = None
        if extraction.get('consultation_type_id'):
            ct_result = supabase.table('consultation_types').select('type_code').eq(
                'id', extraction['consultation_type_id']
            ).execute()
            if ct_result.data:
                consultation_type_code = ct_result.data[0]['type_code']

        logger.debug(f"[LookupAPI] Found extraction {extraction['id']} for session_id {session_id}")

        return ExtractionLookupResponse(
            extraction_id=extraction['id'],
            submission_id=extraction.get('submission_id'),
            session_id=session_id,
            consultation_type_code=consultation_type_code,
            counsellor_id=extraction.get('counsellor_id'),
            student_id=extraction.get('student_id'),
            created_at=extraction.get('created_at'),
            found=True,
            message=None
        )

    except Exception as e:
        logger.error(f"[LookupAPI] ❌ Error looking up extraction: {str(e)}")
        raise HTTPException(status_code=500, detail="Lookup failed")


# =====================================================
# Health Check
# =====================================================

@router.get("/merge/health", status_code=200)
async def merge_health():
    """
    Health check endpoint for merge service.

    Returns basic status information about the merge service.
    """
    return {
        "service": "Extraction Merge API",
        "status": "healthy",
        "version": "1.1.0",
        "features": [
            "AI-powered contextual merging",
            "Cross-type merge support",
            "Merge preview",
            "Student timeline",
            "Merge lineage tracking",
            "Schema transformation (OPHTHAL_OCR → OPHTHAL_FULL)",
            "Schema detection"
        ]
    }

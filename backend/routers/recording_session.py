"""
Recording Session API Router

FastAPI endpoints for live recording functionality:
- Start recording session
- Upload audio chunks
- Get processing status (polling fallback)
- Cancel recording session

Progress updates are delivered via Supabase Realtime (WebSocket) through
the processing_jobs.progress_json column. Frontend subscribes to table changes.

All endpoints are under /api/v1/option1/recording/
"""

import os
import uuid
import asyncio
import traceback
import logging
import datetime
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Body, Depends, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Auth imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import EHRCounsellorAccessChecker, EHRSubmissionAccessChecker, EHRCorrelationAccessChecker, get_current_client
    from services.auth_service import validate_ehr_correlation_access, validate_ehr_counsellor_access
    from models.auth_models import ClientContext

    _counsellor_checker = EHRCounsellorAccessChecker()
    _submission_checker = EHRSubmissionAccessChecker()
    _correlation_checker = EHRCorrelationAccessChecker()

    async def verify_counsellor_access(request: Request, counsellor_id: Optional[str] = None):  # type: ignore[misc]
        """Verify EHR client has access to counsellor data."""
        counsellor_uuid = uuid.UUID(counsellor_id) if counsellor_id else None
        client = get_current_client(request)
        return await _counsellor_checker(request, counsellor_uuid, client)

    async def verify_submission_access(request: Request, submission_id: Optional[str] = None):  # type: ignore[misc]
        """Verify EHR client has access to submission data."""
        submission_uuid = uuid.UUID(submission_id) if submission_id else None
        client = get_current_client(request)
        return await _submission_checker(request, submission_uuid, client)

    async def verify_correlation_access(request: Request, correlation_id: Optional[str] = None):  # type: ignore[misc]
        """Verify EHR client has access to recording session via correlation_id."""
        client = get_current_client(request)
        return await _correlation_checker(request, correlation_id, client)

    async def validate_correlation_from_body(http_request: Request, correlation_id: str):  # type: ignore[misc]
        """
        Validate correlation_id access after body is parsed.
        Use this for endpoints where correlation_id is in request body.
        Raises HTTPException 403 if access denied.
        """
        client = get_current_client(http_request)
        if client.client_type == "ehr":
            if not await validate_ehr_correlation_access(client, correlation_id):
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )

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
    async def verify_counsellor_access(request: Request = None, counsellor_id: Optional[str] = None):  # type: ignore[misc]
        return None

    async def verify_submission_access(request: Request = None, submission_id: Optional[str] = None):  # type: ignore[misc]
        return None

    async def verify_correlation_access(request: Request = None, correlation_id: Optional[str] = None):  # type: ignore[misc]
        return None

    async def validate_correlation_from_body(http_request: Request = None, correlation_id: str = None):  # type: ignore[misc]
        pass  # No-op when auth disabled

    async def validate_counsellor_from_body(http_request: Request = None, counsellor_id: str = None):  # type: ignore[misc]
        pass  # No-op when auth disabled

from services.supabase_service import (
    create_recording_session,
    create_minimal_recording_session,
    get_session_by_correlation_id,
    save_audio_chunk,
    update_session_status,
    cancel_session,
    create_processing_job,
    get_job_by_submission_id,
    get_processing_mode,
    get_extraction_by_submission_id,  # For /status polling endpoint
)
from services.recording_processor import RecordingProcessor
from services.audit_service import audit_service
from services.audio_validation_service import (
    detect_audio_format,
    mime_matches_format,
    is_supported_mime_type,
    log_validation_warning,
    validate_chunk_size,
    detect_empty_audio,
    validate_codec,
    SUPPORTED_MIME_TYPES,
)


# ============================================================================
# Request/Response Models
# ============================================================================

class StartRecordingRequest(BaseModel):
    """Request to start a new recording session"""
    counsellor_id: str = Field(..., description="Counsellor UUID")
    student_id: str = Field(..., description="Student identifier")
    template_code: Optional[str] = Field(
        default=None,
        description="Template code for database lookups (unique identifier) or 'TRANSCRIPT_ONLY'. If omitted, resolves from counsellor/school default, then falls back to OP_CORE."
    )
    template_name: Optional[str] = Field(
        None,
        description="Template display name (optional, for human readability)"
    )
    processing_mode: str = Field(
        default="default",
        description="Processing mode: 'fast', 'default', 'thorough' (default: 'default')"
    )
    extraction_mode: str = Field(
        default="full",
        description="Extraction mode: 'core', 'additional', 'full' (default: 'full')"
    )
    chunk_duration_seconds: int = Field(
        default=10,
        ge=0,
        le=60,
        description="Duration of each audio chunk in seconds (0 = file upload)"
    )
    assistant_id: Optional[str] = Field(
        None,
        description="Optional assistant UUID if recording is initiated by an assistant"
    )
    recording_metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata (student info, counsellor info, custom fields) that flows through to /status response"
    )
    correlation_id: Optional[str] = Field(
        None,
        description="Optional correlation ID (UUID). If not provided, a new UUID will be generated."
    )
    is_continuation: bool = Field(
        default=False,
        description="Whether this recording continues a prior consultation for the same student in the same visit. "
                    "When true, the system finds prior extractions within the time window and uses continuation mode "
                    "(restricted context injection). When false (default), prior context is used normally."
    )


class StartRecordingResponse(BaseModel):
    """Response containing correlation ID for the session"""
    correlation_id: str = Field(..., description="Unique session identifier")
    session_id: str = Field(..., description="Database session ID")
    message: str = Field(default="Recording session started")


class UploadChunkRequest(BaseModel):
    """Request to upload an audio chunk"""
    correlation_id: str = Field(..., description="Session correlation ID")
    chunk_index: int = Field(..., ge=0, description="Sequential chunk index (0-based)")
    audio_data: str = Field(..., description="Base64-encoded audio data")
    mime_type: str = Field(default="audio/webm", description="Audio MIME type")
    duration_seconds: Optional[float] = Field(None, description="Chunk duration in seconds")
    is_last: bool = Field(default=False, description="Is this the last chunk?")


class UploadChunkResponse(BaseModel):
    """Response after uploading a chunk"""
    message: str
    chunk_index: int = Field(alias="chunkIndex")
    total_chunks: int = Field(alias="totalChunks")
    submission_id: Optional[str] = Field(None, alias="submissionId")  # Only present if is_last=True

    model_config = {"populate_by_name": True}


class CancelRecordingRequest(BaseModel):
    """Request to cancel a recording session"""
    correlation_id: str = Field(..., description="Session correlation ID")


class CancelRecordingResponse(BaseModel):
    """Response after canceling a session"""
    message: str
    correlation_id: str


class ProcessingStatusResponse(BaseModel):
    """Current status of a processing job"""
    submission_id: str
    status: str
    progress: int
    message: str
    extraction_id: Optional[str] = None
    transcript: Optional[str] = None
    insights: Optional[dict] = None
    metrics: Optional[dict] = None


class CreateLiveSessionRequest(BaseModel):
    """Request to create a live recording session (WebSocket/RecordTab)"""
    counsellor_id: str = Field(..., description="Counsellor UUID")
    student_id: str = Field(..., description="Student identifier")
    template_code: str = Field(..., description="Template code for database lookups (unique identifier)")
    template_name: Optional[str] = Field(None, description="Template display name (optional)")
    processing_mode: str = Field(default="default", description="Processing mode: 'fast', 'default', 'thorough'")
    assistant_id: Optional[str] = Field(None, description="Optional assistant UUID if session is initiated by an assistant")
    correlation_id: Optional[str] = Field(None, description="Pre-generated correlation_id (for audio chunk upload during recording)")


class CreateLiveSessionResponse(BaseModel):
    """Response containing correlation ID for live session"""
    correlation_id: str
    session_id: str
    message: str = "Live session created"


class LiveChunkRequest(BaseModel):
    """Request to upload audio chunk during live Gemini streaming (parallel to transcription)"""
    correlation_id: Optional[str] = Field(
        default=None,
        description="Required for chunk_index > 0. Omit on first chunk (index=0) - backend generates."
    )
    chunk_index: int = Field(..., ge=0, description="Sequential chunk index (0-based)")
    audio_data: str = Field(..., description="Base64-encoded PCM audio data")
    mime_type: str = Field(default="audio/pcm;rate=16000", description="Audio MIME type (default: PCM 16kHz)")
    # Optional context - sent with first chunk (index=0) for parallel prompt generation
    counsellor_id: Optional[str] = Field(default=None, description="Counsellor UUID (for parallel prompt generation)")
    template_code: Optional[str] = Field(default=None, description="Template code (for parallel prompt generation)")
    student_id: Optional[str] = Field(default=None, description="Student ID (for student context injection)")


class LiveChunkResponse(BaseModel):
    """Response after uploading a live audio chunk"""
    message: str
    chunk_index: int
    correlation_id: str = Field(..., description="Backend-generated correlation_id (use for subsequent chunks)")


# ============================================================================
# Live Prompt Cache (for parallel prompt generation)
# ============================================================================

import time as time_module

# In-memory cache for pre-generated prompts (keyed by correlation_id)
_live_prompt_cache: Dict[str, Dict[str, Any]] = {}
_LIVE_PROMPT_CACHE_TTL = 300  # 5 minutes TTL


async def _generate_and_cache_live_prompts(
    correlation_id: str,
    counsellor_id: str,
    template_code: str,
    student_id: Optional[str],
):
    """
    Generate prompts in background and cache by correlation_id.
    Called when first chunk arrives with context.

    This pre-generates all transcript-independent artifacts:
    - System prompt (from pre-assembled template)
    - Schema (from pre-assembled template)
    - User prompt template (with {transcript} and {patient_context} placeholders)
    - Medicine/investigation list availability

    NOTE: Student context is NOT cached here - it will be fetched fresh at extraction time
    to ensure we always have the most recent prescriptions, summaries, etc.
    """
    try:
        start = time_module.time()
        logger.debug(f"[LIVE_PROMPT] Starting parallel prompt generation for {correlation_id[:8]}...")

        from services.supabase_service import get_active_template_by_code_cached
        from services.extraction_service import check_list_availability_parallel
        from services.segment_registry import generate_extraction_artifacts_without_transcript

        counsellor_uuid = uuid.UUID(counsellor_id)

        # Get template info (cached)
        template = get_active_template_by_code_cached(counsellor_uuid, template_code)
        if not template:
            logger.warning(f"[LIVE_PROMPT] Template not found: {template_code}")
            return

        consultation_type_id_str = template.get('consultation_type_id')
        consultation_type_uuid = uuid.UUID(consultation_type_id_str) if consultation_type_id_str else None
        template_id = template.get('template_id') or template.get('id')

        if not consultation_type_uuid:
            logger.warning(f"[LIVE_PROMPT] No consultation_type_id for template {template_code}")
            return

        # Check list availability (parallel, cached)
        list_availability = await check_list_availability_parallel(counsellor_uuid)

        # Generate artifacts WITHOUT transcript and WITHOUT student context
        # - Transcript will be injected at extraction time
        # - Student context will be fetched FRESH at extraction time (to get latest prescriptions/summaries)
        # Pass student_id=None to skip student context injection during caching
        artifacts = generate_extraction_artifacts_without_transcript(
            consultation_type_id=consultation_type_uuid,
            counsellor_id=counsellor_uuid,  # Pass UUID, not string
            template_code=template_code,
            mode="full",
            student_id=None,  # ⚡ Skip student context - will inject fresh at extraction time
            has_medicine_list=list_availability.get("has_medicine_list", True),
            has_investigation_list=list_availability.get("has_investigation_list", True),
        )

        if not artifacts:
            logger.warning(f"[LIVE_PROMPT] Failed to generate artifacts for {correlation_id[:8]}")
            return

        # Cache by correlation_id
        # Store resolved student_id for fresh context injection at extraction time
        _live_prompt_cache[correlation_id] = {
            "artifacts": artifacts,
            "template_id": template_id,
            "consultation_type_id": consultation_type_id_str,  # Store as string for JSON compatibility
            "list_availability": list_availability,
            "student_id": student_id,  # ⚡ Store for fresh context injection at extraction time
            "generated_at": time_module.time(),
        }

        duration = time_module.time() - start
        logger.debug(f"[LIVE_PROMPT] Pre-generated prompts for {correlation_id[:8]}... in {duration:.3f}s")

    except Exception as e:
        logger.error(f"[LIVE_PROMPT] Failed to pre-generate prompts: {e}", exc_info=True)


def get_cached_live_prompts(correlation_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve pre-generated prompts from cache.
    Returns None if not found or expired.
    Pops from cache (one-time use).
    """
    cached = _live_prompt_cache.pop(correlation_id, None)
    if cached:
        # Check TTL
        age = time_module.time() - cached.get("generated_at", 0)
        if age > _LIVE_PROMPT_CACHE_TTL:
            logger.warning(f"[LIVE_PROMPT] Cache EXPIRED for {correlation_id[:8]}... (age={age:.1f}s)")
            return None
        logger.debug(f"[LIVE_PROMPT] Cache HIT for {correlation_id[:8]}... (age={age:.1f}s)")
    return cached


def cleanup_expired_live_prompts():
    """Remove expired entries from cache. Called periodically."""
    now = time_module.time()
    expired = [
        cid for cid, data in _live_prompt_cache.items()
        if now - data.get("generated_at", 0) > _LIVE_PROMPT_CACHE_TTL
    ]
    for cid in expired:
        del _live_prompt_cache[cid]
    if expired:
        logger.debug(f"[LIVE_PROMPT] Cleaned up {len(expired)} expired cache entries")


def invalidate_all_live_prompt_cache() -> int:
    """Invalidate ALL live prompt caches. Used for global cache refresh."""
    count = len(_live_prompt_cache)
    _live_prompt_cache.clear()
    if count:
        logger.debug(f"[LIVE_PROMPT] Invalidated ALL live prompt caches ({count} entries)")
    return count


# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(
    prefix="/api/v1/option1/recording",
    tags=["Recording Session"],
)


# ============================================================================
# API Endpoints
# ============================================================================

async def _validate_session_background(
    session_id: str,
    counsellor_id: str,
    template_code: Optional[str],
    processing_mode: str,
    extraction_mode: Optional[str],
    assistant_id: Optional[str],
    is_continuation: bool = False,
):
    """
    Background task to validate and enrich the session with template/model data.

    All blocking DB work runs inside asyncio.to_thread() to avoid blocking the event loop.

    Updates the session record with:
    - transcription_model, extraction_model (from processing mode config)
    - consultation_type_id, session_context_json (from template lookup)
    - template_code/template_name (fallback if requested template not found)
    - validation_status = 'completed' or 'failed'
    """
    import time
    bg_start = time.time()

    def _do_validation():
        """Synchronous validation work - runs in thread pool to avoid blocking event loop."""
        from services.supabase_service import (
            supabase,
            get_templates,
            get_active_template_by_code_cached,
        )

        counsellor_uuid = uuid.UUID(counsellor_id)
        update_data: Dict[str, Any] = {}

        # 1. Resolve processing mode -> models
        try:
            pm_config = get_processing_mode(processing_mode)
            update_data["transcription_model"] = pm_config['transcription_model']
            update_data["extraction_model"] = pm_config['extraction_model']
        except ValueError as e:
            logger.warning(f"[VALIDATE_BG] Invalid processing mode '{processing_mode}': {e}, using defaults")
            update_data["transcription_model"] = "gemini-2.5-flash"
            update_data["extraction_model"] = "gemini-2.5-flash"

        # 2. Template validation (skip for TRANSCRIPT_ONLY)
        template_code_to_use = template_code
        template_name_to_use = None
        consultation_type_id = None
        session_context: Dict[str, Any] = {}

        if template_code and template_code.upper() != "TRANSCRIPT_ONLY":
            try:
                all_templates = get_templates(
                    consultation_type_id=None,
                    counsellor_id=counsellor_uuid,
                    filter_type='doctor'
                )
                active_templates = [t for t in all_templates if t.get('is_active', False)]

                if not active_templates:
                    raise ValueError(
                        "Counsellor must have at least one active template before starting a recording session."
                    )

                # Check if requested template exists
                matched_template = None
                for template in active_templates:
                    if template.get("template_code") == template_code:
                        matched_template = template
                        break

                if not matched_template:
                    fallback_source = "active_list"

                    # ASSISTANT FALLBACK (when assistant_id present)
                    if assistant_id:
                        from services.assistant_templates_service import get_assistant_default_template
                        assistant_default = get_assistant_default_template(uuid.UUID(assistant_id), counsellor_uuid)
                        if assistant_default:
                            assistant_code = assistant_default["template_code"]
                            for t in active_templates:
                                if t.get("template_code") == assistant_code:
                                    matched_template = t
                                    fallback_source = "assistant_default"
                                    break
                            if not matched_template:
                                template_code_to_use = assistant_code
                                fallback_source = "assistant_default"

                    # COUNSELLOR FALLBACK (existing, runs if assistant didn't resolve)
                    if not matched_template and fallback_source != "assistant_default":
                        from services.counsellor_templates_service import get_counsellor_default_template
                        default_template_info = get_counsellor_default_template(counsellor_uuid)

                        if default_template_info:
                            default_code = default_template_info["template_code"]
                            for t in active_templates:
                                if t.get("template_code") == default_code:
                                    matched_template = t
                                    fallback_source = "default"
                                    break

                    # If still no match, prefer OP_CORE from active list
                    if not matched_template:
                        for t in active_templates:
                            if t.get("template_code") == "OP_CORE":
                                matched_template = t
                                break

                    # Last resort: first active template
                    if not matched_template:
                        matched_template = active_templates[0]

                    template_code_to_use = matched_template.get("template_code", template_code)
                    template_name_to_use = matched_template.get("template_name")
                    logger.warning(
                        f"[VALIDATE_BG] Template '{template_code}' not found, "
                        f"falling back to '{template_code_to_use}' (source: {fallback_source})"
                    )
                else:
                    template_name_to_use = matched_template.get("template_name")

                update_data["template_code"] = template_code_to_use
                if template_name_to_use:
                    update_data["template_name"] = template_name_to_use

            except ValueError:
                raise
            except Exception as e:
                logger.warning(f"[VALIDATE_BG] Template list lookup failed: {e}, continuing with raw template_code")

            # 3. Build session context from template
            try:
                active_template_record = get_active_template_by_code_cached(counsellor_uuid, template_code_to_use)
                if active_template_record:
                    consultation_type_id = active_template_record.get('consultation_type_id')
                    if not template_name_to_use:
                        template_name_to_use = active_template_record.get('template_name')
                        if template_name_to_use:
                            update_data["template_name"] = template_name_to_use

                    session_context = {
                        "template_id": active_template_record.get('id'),
                        "template_code": template_code_to_use,
                        "consultation_type_id": str(consultation_type_id) if consultation_type_id else None,
                        "source": active_template_record.get('source', 'unknown'),
                        "prompt_assembly_hash": active_template_record.get('prompt_assembly_hash'),
                        "schema_assembly_hash": active_template_record.get('schema_assembly_hash'),
                        "has_preassembled": bool(active_template_record.get('assembled_full_prompt')),
                        "loaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    }
                    update_data["consultation_type_id"] = str(consultation_type_id) if consultation_type_id else None
                    update_data["session_context_json"] = session_context
            except Exception as e:
                logger.warning(f"[VALIDATE_BG] Template context lookup failed: {e}")

            # 4. Assistant validation (non-blocking - just log warning if fails)
            if assistant_id and session_context.get("template_id"):
                try:
                    from services.assistant_templates_service import validate_assistant_template_access
                    from services.assistant_service import get_assistant

                    assistant = get_assistant(assistant_id)
                    if not assistant:
                        logger.warning(f"[VALIDATE_BG] Assistant '{assistant_id}' not found")
                    else:
                        template_id = session_context["template_id"]
                        if not validate_assistant_template_access(assistant_id, template_id):
                            logger.warning(
                                f"[VALIDATE_BG] Assistant {assistant_id} lacks access to template '{template_code_to_use}'"
                            )
                except Exception as e:
                    logger.warning(f"[VALIDATE_BG] Assistant validation failed: {e}")

        # 5. Continuation detection (resolve parent extraction IDs)
        if is_continuation:
            try:
                from services.visit_detection_service import detect_continuation_extractions
                # Get student_id from session
                session_row = supabase.table("recording_sessions")\
                    .select("student_id")\
                    .eq("id", session_id)\
                    .limit(1)\
                    .execute()
                student_uuid_str = session_row.data[0]["student_id"] if session_row.data else None

                if student_uuid_str:
                    detection = detect_continuation_extractions(
                        student_id=student_uuid_str,
                        counsellor_id=counsellor_id,
                        assistant_id=assistant_id,
                    )
                    if detection and detection["parent_extraction_ids"]:
                        session_context["is_continuation"] = True
                        session_context["parent_extraction_ids"] = detection["parent_extraction_ids"]
                        session_context["continuation_detected_by"] = detection["detection_reason"]
                        logger.info(
                            f"[VALIDATE_BG] Continuation detected: {len(detection['parent_extraction_ids'])} parent(s), "
                            f"reason={detection['detection_reason']}"
                        )
                    else:
                        session_context["is_continuation"] = False
                        session_context["parent_extraction_ids"] = []
                        logger.warning(
                            f"[VALIDATE_BG] is_continuation=True but no prior extractions found for student {student_uuid_str}"
                        )
                else:
                    session_context["is_continuation"] = False
                    session_context["parent_extraction_ids"] = []
            except Exception as e:
                logger.warning(f"[VALIDATE_BG] Continuation detection failed: {e}")
                session_context["is_continuation"] = False
                session_context["parent_extraction_ids"] = []

            # Re-save session_context with continuation info
            update_data["session_context_json"] = session_context
        else:
            session_context["is_continuation"] = False
            session_context["parent_extraction_ids"] = []
            update_data["session_context_json"] = session_context

        # 6. Update session with resolved data
        update_data["validation_status"] = "completed"
        supabase.table("recording_sessions").update(update_data).eq("id", session_id).execute()

        return template_code_to_use, update_data

    try:
        template_code_to_use, update_data = await asyncio.to_thread(_do_validation)

        elapsed = (time.time() - bg_start) * 1000
        logger.debug(
            f"[VALIDATE_BG] Session {session_id} validated in {elapsed:.0f}ms "
            f"(template={template_code_to_use}, models={update_data.get('transcription_model')}/"
            f"{update_data.get('extraction_model')})"
        )

    except Exception as e:
        elapsed = (time.time() - bg_start) * 1000
        logger.error(f"[VALIDATE_BG] Session {session_id} validation FAILED in {elapsed:.0f}ms: {e}")
        logger.error(f"[VALIDATE_BG] Traceback: {traceback.format_exc()}")

        # Mark session as failed with error details
        try:
            from services.supabase_service import supabase
            error_update = {
                "validation_status": "failed",
                "session_context_json": {"validation_error": str(e)},
            }
            await asyncio.to_thread(
                lambda: supabase.table("recording_sessions").update(error_update).eq("id", session_id).execute()
            )
        except Exception as update_err:
            logger.error(f"[VALIDATE_BG] Failed to update session with error status: {update_err}")


@router.post("/start", response_model=StartRecordingResponse)
async def start_recording(
    http_request: Request,
    request: StartRecordingRequest,
    _auth = Depends(verify_counsellor_access)
):
    """
    Start a new live recording session with template-based extraction.

    Returns a correlation_id that should be used for all subsequent chunk uploads.
    Heavy validation (template lookup, model config) is deferred to background.

    **Workflow:**
    1. Call this endpoint to get correlation_id
    2. Start recording audio on frontend
    3. Send chunks every N seconds to /chunk endpoint
    4. Mark last chunk with is_last=true
    5. Receive submission_id and subscribe to Supabase Realtime for progress updates

    **Parameters:**
    - counsellor_id: Counsellor's UUID
    - student_id: Student identifier
    - template_code: Template code for database lookups (unique identifier) or 'TRANSCRIPT_ONLY'
    - template_name: Template display name (optional)
    - processing_mode: 'fast', 'default', 'thorough', 'ultra', 'ultra_fast' (default: 'default')
    - extraction_mode: 'core', 'additional', 'full', or None (for TRANSCRIPT_ONLY)
    """
    logger.info(
        f"[START_RECORDING] Request: template_code={request.template_code}, "
        f"template_name={request.template_name}, counsellor={request.counsellor_id}, "
        f"student={request.student_id}, mode={request.processing_mode}, "
        f"extraction_mode={request.extraction_mode}, "
        f"recording_metadata={request.recording_metadata}"
    )

    try:
        # 0. Block hidden processing modes (ultra/ultra_fast are disabled)
        from routers.processing_modes import HIDDEN_MODE_CODES
        if request.processing_mode in HIDDEN_MODE_CODES:
            raise HTTPException(
                status_code=400,
                detail=f"Processing mode '{request.processing_mode}' is currently unavailable. Use 'fast', 'default', or 'thorough'."
            )

        # 0.5 Resolve counsellor_id / assistant_id: accept EITHER the internal UUID or the caller's
        # external id (counsellors.external_id / assistants.external_id) and normalise to the UUID so
        # every downstream lookup uses it. Returns a clean 400 (malformed) / 404 (unknown) instead of
        # a 500 from a Postgres uuid cast error.
        from services.supabase_service import resolve_entity_uuid
        try:
            _resolved_counsellor = resolve_entity_uuid("counsellors", request.counsellor_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"counsellor_id must be a counsellor UUID or external id; got {request.counsellor_id!r}")
        if not _resolved_counsellor:
            raise HTTPException(status_code=404, detail=f"Counsellor not found: {request.counsellor_id!r}")
        request.counsellor_id = _resolved_counsellor

        if request.assistant_id:
            try:
                _resolved_assistant = resolve_entity_uuid("assistants", request.assistant_id)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"assistant_id must be an assistant UUID or external id; got {request.assistant_id!r}")
            if not _resolved_assistant:
                raise HTTPException(status_code=404, detail=f"Assistant not found: {request.assistant_id!r}")
            request.assistant_id = _resolved_assistant

        # 1. Auth: Validate EHR client has access to this counsellor (security - keep sync)
        await validate_counsellor_from_body(http_request, request.counsellor_id)

        # 2. Generate/validate correlation_id (no DB)
        if request.correlation_id:
            try:
                correlation_id = uuid.UUID(request.correlation_id)
                logger.debug(f"[START_RECORDING] Using provided correlation_id: {correlation_id}")
            except ValueError:
                correlation_id = uuid.uuid4()
                logger.warning(f"[START_RECORDING] Invalid correlation_id '{request.correlation_id}', generated new: {correlation_id}")
        else:
            correlation_id = uuid.uuid4()

        # 3. Resolve template_code if not provided
        resolved_template_code = request.template_code
        if not resolved_template_code:
            counsellor_uuid = uuid.UUID(request.counsellor_id)

            # Assistant fallback first (when assistant_id present)
            if request.assistant_id:
                from services.assistant_templates_service import get_assistant_default_template
                assistant_uuid = uuid.UUID(request.assistant_id)
                assistant_default = await asyncio.to_thread(
                    get_assistant_default_template, assistant_uuid, counsellor_uuid
                )
                if assistant_default:
                    resolved_template_code = assistant_default["template_code"]
                    logger.info(f"[START_RECORDING] Resolved via assistant fallback: {resolved_template_code}")

            # Counsellor fallback (runs if assistant didn't resolve)
            if not resolved_template_code:
                from services.counsellor_templates_service import get_counsellor_default_template
                default_template = await asyncio.to_thread(get_counsellor_default_template, counsellor_uuid)
                if default_template:
                    resolved_template_code = default_template["template_code"]
                    logger.info(f"[START_RECORDING] No template_code provided, using counsellor/school default: {resolved_template_code}")

            if not resolved_template_code:
                # Fallback: check counsellor's active templates
                from services.supabase_service import get_templates
                active_templates = await asyncio.to_thread(
                    get_templates, consultation_type_id=None, counsellor_id=counsellor_uuid, filter_type='doctor'
                )
                active_templates = [t for t in active_templates if t.get('is_active', False)]

                # Prefer OP_CORE if counsellor has it active
                op_core = next((t for t in active_templates if t.get("template_code") == "OP_CORE"), None)
                if op_core:
                    resolved_template_code = "OP_CORE"
                    logger.info(f"[START_RECORDING] No default found, using counsellor's active OP_CORE template")
                elif active_templates:
                    resolved_template_code = active_templates[0].get("template_code", "OP_CORE")
                    logger.info(f"[START_RECORDING] No default found, using first active template: {resolved_template_code}")
                else:
                    resolved_template_code = "OP_CORE"
                    logger.warning(f"[START_RECORDING] No default or active templates found, hardcoded fallback: OP_CORE")

        # 4. Determine extraction_mode (no DB, just logic)
        if resolved_template_code.upper() == "TRANSCRIPT_ONLY":
            extraction_mode = None
        else:
            extraction_mode = request.extraction_mode

        # 5. Extract api_client_id from request context
        api_client_id = None
        if hasattr(http_request.state, 'client') and http_request.state.client:
            client_ctx = http_request.state.client
            if client_ctx.client_type != "admin":
                api_client_id = str(client_ctx.client_id)

        # 6. Create minimal session (student lookup + 1 insert = ~100-200ms)
        session = await asyncio.to_thread(
            create_minimal_recording_session,
            correlation_id=correlation_id,
            counsellor_id=request.counsellor_id,
            student_id=request.student_id,
            template_code=resolved_template_code,
            processing_mode=request.processing_mode,
            extraction_mode=extraction_mode,
            chunk_duration_seconds=request.chunk_duration_seconds,
            template_name=request.template_name,
            assistant_id=request.assistant_id,
            recording_metadata_json=request.recording_metadata,
            api_client_id=api_client_id,
        )

        # 7. Fire-and-forget: Validate template + resolve models in background
        try:
            asyncio.create_task(_validate_session_background(
                session_id=session["id"],
                counsellor_id=request.counsellor_id,
                template_code=resolved_template_code,
                processing_mode=request.processing_mode,
                extraction_mode=extraction_mode,
                assistant_id=request.assistant_id,
                is_continuation=request.is_continuation,
            ))
        except Exception as e:
            logger.warning(f"[START_RECORDING] Failed to schedule background validation: {e}")

        # 8. Fire-and-forget: Auto-link counsellor to student's counsellor_ids
        try:
            from services.supabase_service import link_counsellor_to_student
            asyncio.create_task(asyncio.to_thread(
                link_counsellor_to_student,
                patient_uuid=session["student_id"],
                counsellor_id=request.counsellor_id,
            ))
        except Exception as e:
            logger.warning(f"[START_RECORDING] Failed to schedule counsellor-student link: {e}")

        # 9. HIPAA Audit: log recording session creation
        client_ctx = getattr(http_request.state, "client", None)
        if client_ctx:
            try:
                asyncio.create_task(audit_service.log_phi_access(
                    client_context=client_ctx, request=http_request, response_status=200,
                    response_time_ms=0, resource_type="recording", action="create",
                    resource_id=session["id"],
                    counsellor_id=uuid.UUID(request.counsellor_id) if request.counsellor_id else None,
                    student_id=request.student_id,
                ))
            except Exception:
                pass

        # 9. Return immediately
        logger.info(f"[START_RECORDING] Session created: session_id={session['id']}, template={resolved_template_code} (validation deferred)")
        return StartRecordingResponse(
            correlation_id=str(correlation_id),
            session_id=session["id"],
            message="Recording session started successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[START_RECORDING] Exception: {str(e)}")
        logger.error(f"[START_RECORDING] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to start recording")


@router.post("/chunk", response_model=UploadChunkResponse, response_model_by_alias=True)
async def upload_chunk(
    http_request: Request,
    request: UploadChunkRequest,
    _auth = Depends(verify_counsellor_access)
):
    """
    Upload an audio chunk for a recording session.

    **Chunk Upload Flow (Race Condition Safe):**
    1. Frontend records audio in chunks (e.g., every 10 seconds)
    2. Each chunk is uploaded with sequential chunk_index (0, 1, 2, ...)
    3. Chunks are stored in memory (fast) + DB (async backup)
    4. When final chunk is uploaded (is_last=true):
       - Session is marked ready with expected chunk count
       - 2-minute timeout starts (in case other chunks don't arrive)
    5. Processing starts when ALL chunks 0..N-1 are present AND is_last received
       - This prevents race conditions where is_last arrives before other chunks
       - If chunks arrive in order, processing starts immediately (no delay)
    6. Webhook fires automatically when extraction completes (if enabled)

    **Parameters:**
    - correlation_id: Session ID from /start endpoint
    - chunk_index: Sequential index starting from 0
    - audio_data: Base64-encoded audio blob
    - mime_type: Audio format (audio/webm, audio/wav, etc.)
    - duration_seconds: Optional duration of this chunk
    - is_last: Set to true for the final chunk

    **Returns:**
    - message: Status message
    - chunk_index: Index of uploaded chunk
    - total_chunks: Total chunks uploaded so far
    - submission_id: Only present when all chunks received and processing starts
    """
    try:
        # Validate EHR client has access to this correlation_id (school-scoped)
        await validate_correlation_from_body(http_request, request.correlation_id)

        # Get session by correlation ID
        correlation_uuid = uuid.UUID(request.correlation_id)
        session = await asyncio.to_thread(get_session_by_correlation_id, correlation_uuid)

        if not session:
            raise HTTPException(status_code=404, detail="Recording session not found")

        if session["status"] not in ["RECORDING", "SUBMITTED"]:
            raise HTTPException(
                status_code=400,
                detail="Cannot upload chunk for this session"
            )

        session_id = uuid.UUID(session["id"])
        session_id_str = str(session_id)

        # Calculate chunk size for logging
        chunk_size_bytes = len(request.audio_data) if request.audio_data else 0
        chunk_size_kb = chunk_size_bytes / 1024

        # ============================================================================
        # STEP 1: Store chunk in memory (fast, ~0ms)
        # ============================================================================
        import time
        from services.chunk_memory_store import (
            store_chunk as store_chunk_memory,
            mark_session_ready_for_processing,
            can_start_processing_atomically,
            start_completion_timeout,
            cancel_completion_timeout,
            get_present_chunk_indices,
        )

        memory_store_start = time.time()
        memory_stored = store_chunk_memory(
            session_id=session_id_str,
            chunk_index=request.chunk_index,
            audio_data=request.audio_data,
            mime_type=request.mime_type,
            duration_seconds=request.duration_seconds,
            is_last=request.is_last,
        )
        memory_store_time = time.time() - memory_store_start

        # Fire-and-forget: Validate audio chunk in background (non-blocking)
        asyncio.create_task(
            _validate_audio_chunk_async(
                session_id=session_id_str,
                chunk_index=request.chunk_index,
                audio_data=request.audio_data,
                mime_type=request.mime_type,
            )
        )

        if not memory_stored:
            logger.warning(f"[CHUNK_MEMORY] Failed to store chunk {request.chunk_index} in memory, falling back to sync DB save")
            # Fallback: synchronous DB save if memory store fails
            chunk_save_start = time.time()
            await asyncio.to_thread(
                save_audio_chunk,
                session_id=session_id,
                chunk_index=request.chunk_index,
                audio_data=request.audio_data,
                mime_type=request.mime_type,
                duration_seconds=request.duration_seconds,
                is_last=request.is_last,
            )
            chunk_save_time = time.time() - chunk_save_start
            logger.info(f"[TIMING_CHUNK] Chunk {request.chunk_index} saved to DB (fallback): {chunk_save_time:.3f}s")
        else:
            # Fire off async DB save (fire-and-forget) - backup/persistence
            asyncio.create_task(
                _save_chunk_to_db_async(
                    session_id=session_id,
                    chunk_index=request.chunk_index,
                    audio_data=request.audio_data,
                    mime_type=request.mime_type,
                    duration_seconds=request.duration_seconds,
                    is_last=request.is_last,
                )
            )
            logger.info(
                f"[TIMING_CHUNK] Chunk {request.chunk_index} stored in memory: {memory_store_time:.3f}s "
                f"(size: {chunk_size_kb:.1f} KB, is_last: {request.is_last}, DB save: async)"
            )

        # ============================================================================
        # STEP 1b: Check if we should trigger segment transcription (long audio)
        # Byte-budget trigger: when cumulative bytes-since-last-boundary cross
        # SEGMENT_BYTE_BUDGET (12 MB), fire a background segment transcription
        # so each segment stays under Gemini's 15 MB inline cap.
        # MAX_SEGMENT_SECONDS is a safety ceiling for pathological low-bitrate
        # recordings where bytes alone would never trigger.
        # ============================================================================
        if not request.is_last:
            try:
                from services.segment_transcription_store import (
                    SEGMENT_BYTE_BUDGET as _SEG_BYTE_BUDGET,
                    MAX_SEGMENT_SECONDS as _SEG_MAX_SECONDS,
                    DEFAULT_OVERLAP_CHUNKS as _OVERLAP_CHUNKS,
                    get_next_segment_index,
                    get_last_boundary_chunk_index,
                    register_segment as register_seg,
                )
                from services.chunk_memory_store import (
                    get_session_audio_duration,
                    get_session_bytes_since_chunk,
                )

                next_seg_idx = get_next_segment_index(session_id_str)
                prev_boundary = get_last_boundary_chunk_index(session_id_str)  # -1 for first segment

                # Bytes since last boundary (or all bytes for first segment)
                bytes_since_boundary = get_session_bytes_since_chunk(session_id_str, prev_boundary)

                # Duration ceiling fallback (low-bitrate / quiet-mic case)
                cumulative_duration = get_session_audio_duration(session_id_str) or 0
                # For non-first segment, subtract the duration consumed by prior segments
                # (approximated by SEGMENT_DURATION_SECONDS × prior count). For the
                # primary trigger we only need bytes; this is the safety net.
                duration_since_boundary = cumulative_duration - (next_seg_idx * _SEG_MAX_SECONDS)

                byte_trigger = bytes_since_boundary >= _SEG_BYTE_BUDGET
                duration_trigger = duration_since_boundary >= _SEG_MAX_SECONDS

                if byte_trigger or duration_trigger:
                    if next_seg_idx == 0:
                        start_idx = 0
                    else:
                        start_idx = max(0, prev_boundary - _OVERLAP_CHUNKS + 1)

                    end_idx = request.chunk_index
                    trigger_reason = "byte_budget" if byte_trigger else "duration_ceiling"

                    if register_seg(session_id_str, next_seg_idx, start_idx, end_idx):
                        logger.info(
                            f"[SEGMENT] Triggered segment {next_seg_idx} transcription "
                            f"({trigger_reason}: bytes={bytes_since_boundary / 1024 / 1024:.1f}MB "
                            f"duration~{duration_since_boundary:.0f}s, chunks {start_idx}-{end_idx})"
                        )
                        asyncio.create_task(
                            _transcribe_segment(
                                session_id_str, next_seg_idx, start_idx, end_idx,
                                session_data=session,
                            )
                        )
            except Exception as seg_err:
                # Segment transcription is an optimization - never block chunk upload
                logger.warning(f"[SEGMENT] Segment check failed (non-fatal): {seg_err}")

        # ============================================================================
        # STEP 2: If is_last, mark session ready and start timeout
        # (but DON'T trigger processing yet - wait for all chunks)
        # ============================================================================
        total_chunks = request.chunk_index + 1

        if request.is_last:
            logger.info(
                f"[CHUNK_COMPLETE] Received is_last=true for session {session_id_str[:8]}... "
                f"(chunk_index={request.chunk_index}, expected_count={total_chunks})"
            )

            # Mark session as ready with expected chunk count
            mark_session_ready_for_processing(session_id_str, total_chunks)

            # Fire-and-forget: Update session status in DB
            asyncio.create_task(
                asyncio.to_thread(
                    update_session_status,
                    correlation_uuid,
                    "SUBMITTED",
                    total_chunks=total_chunks,
                )
            )

            # Start 2-minute timeout (in case other chunks don't arrive)
            # Pass callback for timeout webhook notification
            start_completion_timeout(
                session_id_str,
                total_chunks,
                on_timeout_callback=lambda **kwargs: _handle_chunk_timeout(
                    session=session,
                    **kwargs
                )
            )

        # ============================================================================
        # STEP 3: Check if we can start processing (runs after EVERY chunk)
        # Processing starts when: all chunks 0..N-1 present AND is_last received
        # NOTE: Using atomic version to prevent race conditions (duplicate processing)
        # ============================================================================
        can_process, reason = can_start_processing_atomically(session_id_str)

        response = UploadChunkResponse(
            message=f"Chunk {request.chunk_index} uploaded successfully",
            chunk_index=request.chunk_index,
            total_chunks=total_chunks,
        )

        if can_process:
            # All chunks present - start processing!
            final_chunk_start = time.time()

            # Cancel the timeout (we don't need it anymore)
            cancel_completion_timeout(session_id_str)

            # Pre-generate submission_id
            submission_id = uuid.uuid4()

            present_indices = get_present_chunk_indices(session_id_str)
            logger.info(
                f"[CHUNK_COMPLETE] ✅ All {len(present_indices)} chunks present for session "
                f"{session_id_str[:8]}..., starting processing. Chunks: {present_indices}"
            )

            # Fire-and-forget: Create processing job in DB (with retry)
            async def _create_processing_job_with_retry():
                """Create processing job with 2 retries to handle cold Supabase connections."""
                for attempt in range(3):
                    try:
                        await asyncio.to_thread(
                            create_processing_job,
                            session_id=session_id,
                            submission_id=submission_id,
                        )
                        logger.debug(f"[CHUNK_COMPLETE] Processing job created for submission {submission_id}")
                        return
                    except Exception as e:
                        if attempt < 2:
                            logger.warning(
                                f"[CHUNK_COMPLETE] ⚠️ create_processing_job attempt {attempt+1}/3 failed: {e}. Retrying in 1s..."
                            )
                            await asyncio.sleep(1)
                        else:
                            logger.error(
                                f"[CHUNK_COMPLETE] ❌ create_processing_job FAILED after 3 attempts for "
                                f"session={session_id}, submission={submission_id}: {e}"
                            )
            asyncio.create_task(_create_processing_job_with_retry())

            # Trigger background processing
            trigger_start = time.time()
            await _trigger_background_processing(
                submission_id=submission_id,
                session_id=session_id,
                session_data=session,
            )
            trigger_time = time.time() - trigger_start

            final_chunk_total = time.time() - final_chunk_start
            logger.info(
                f"[TIMING_UPLOAD_COMPLETE] Processing triggered: {final_chunk_total:.3f}s "
                f"(trigger={trigger_time:.3f}s)"
            )

            response.submission_id = str(submission_id)
            response.message = (
                f"All {len(present_indices)} chunks received. Processing started. "
                f"submission_id: {submission_id}"
            )
        else:
            # Still waiting for chunks
            logger.debug(f"[CHUNK_PENDING] Session {session_id_str[:8]}...: {reason}")
            if request.is_last:
                # is_last arrived but missing other chunks - this is the race condition we're fixing
                present_indices = get_present_chunk_indices(session_id_str)
                logger.warning(
                    f"[CHUNK_PENDING] is_last received but waiting for other chunks. "
                    f"Present: {present_indices}, Reason: {reason}"
                )
                response.message = f"Final chunk received. Waiting for remaining chunks ({reason})"

        return response

    except ValueError as e:
        logger.error(f"ValueError in upload_chunk: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid correlation ID")
    except Exception as e:
        logger.error(f"Exception in upload_chunk: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to upload chunk")


async def _transcribe_segment(
    session_id: str,
    segment_index: int,
    start_chunk: int,
    end_chunk: int,
    session_data: dict = None,
):
    """
    Fire-and-forget: Stitch a range of chunks and transcribe as a segment.

    Called during live recording when cumulative duration crosses a segment boundary.
    Results are stored in segment_transcription_store for later combination.
    """
    try:
        from services.chunk_memory_store import get_chunks_sorted
        from services.audio_splitter import stitch_and_get_bytes_for_chunk_range
        from services.gemini_service import transcribe_audio
        from services.segment_transcription_store import store_segment_transcript, mark_segment_failed
        from services.audio_storage_service import normalize_audio_mime_type

        # Get chunks from memory
        all_chunks = get_chunks_sorted(session_id)
        if not all_chunks:
            mark_segment_failed(session_id, segment_index, "No chunks in memory")
            return

        # Stitch the chunk range
        audio_bytes, mime_type = stitch_and_get_bytes_for_chunk_range(
            all_chunks, start_chunk, end_chunk
        )
        mime_type = normalize_audio_mime_type(mime_type)

        logger.info(
            f"[SEGMENT] Transcribing segment {segment_index} for session {session_id[:8]}... "
            f"({len(audio_bytes)} bytes, chunks {start_chunk}-{end_chunk})"
        )

        # Get counsellor_id for usage tracking
        counsellor_id = session_data.get("counsellor_id") if session_data else None

        # Transcribe
        transcript, detected_language = await transcribe_audio(
            audio_content=audio_bytes,
            mime_type=mime_type,
            target_language="English",
            session_id=session_id,
            counsellor_id=counsellor_id,
            audio_duration_seconds=len(audio_bytes) / 16000,
        )

        # Store result
        store_segment_transcript(session_id, segment_index, transcript, detected_language)

        logger.info(
            f"[SEGMENT] Segment {segment_index} transcription complete "
            f"for session {session_id[:8]}... ({len(transcript)} chars)"
        )
    except Exception as e:
        logger.error(
            f"[SEGMENT] Segment {segment_index} transcription failed "
            f"for session {session_id[:8]}...: {e}"
        )
        try:
            from services.segment_transcription_store import mark_segment_failed
            mark_segment_failed(session_id, segment_index, str(e))
        except Exception:
            pass


@router.post("/cancel", response_model=CancelRecordingResponse)
async def cancel_recording(
    http_request: Request,
    request: CancelRecordingRequest,
    _auth = Depends(verify_counsellor_access)
):
    """
    Cancel an active recording session.

    This will:
    1. Change session status to CANCELLED
    2. Delete all uploaded chunks
    3. Stop any ongoing processing

    **Note:** This cannot cancel a job that is already COMPLETED or ERROR.
    """
    try:
        # Validate EHR client has access to this correlation_id (school-scoped)
        await validate_correlation_from_body(http_request, request.correlation_id)

        correlation_uuid = uuid.UUID(request.correlation_id)

        # Get session
        session = get_session_by_correlation_id(correlation_uuid)
        if not session:
            raise HTTPException(status_code=404, detail="Recording session not found")

        # Check if session can be cancelled
        if session["status"] in ["COMPLETED", "ERROR"]:
            raise HTTPException(
                status_code=400,
                detail="Cannot cancel session in current state"
            )

        # Cancel session
        cancel_session(correlation_uuid)

        return CancelRecordingResponse(
            message="Recording session cancelled successfully",
            correlation_id=request.correlation_id,
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid correlation_id format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to cancel recording")


@router.get("/status/{submission_id}", response_model=ProcessingStatusResponse)
async def get_processing_status(
    request: Request,
    submission_id: str,
    _auth = Depends(verify_submission_access)
):
    """
    Get current processing status (polling fallback).

    **Note:** Frontend uses Supabase Realtime (WebSocket) for real-time updates.
    Use this endpoint as a fallback for polling if WebSocket is unavailable.
    """
    try:
        submission_uuid = uuid.UUID(submission_id)

        # Get job
        job = get_job_by_submission_id(submission_uuid)
        if not job:
            raise HTTPException(status_code=404, detail="Processing job not found")

        response = ProcessingStatusResponse(
            submission_id=submission_id,
            status=job["status"],
            progress=job["progress_percentage"],
            message=job.get("progress_message", "Processing..."),
        )

        # Include results if completed (fetch from extractions table)
        if job["status"] == "COMPLETED":
            extraction = await asyncio.to_thread(get_extraction_by_submission_id, submission_uuid)

            if extraction:
                response.extraction_id = extraction.get("id")
                response.transcript = extraction.get("transcript")
                response.insights = extraction.get("insights")
                response.metrics = {
                    "stitching_time": extraction.get("stitching_time_seconds"),
                    "transcription_time": extraction.get("transcription_time_seconds"),
                    "extraction_time": extraction.get("extraction_time_seconds"),
                    "total_time": extraction.get("total_processing_time_seconds"),
                    "is_continuation": extraction.get("is_continuation", False),
                    "parent_extraction_ids": extraction.get("parent_extraction_ids", []),
                }
            else:
                # Fallback for race conditions
                logger.warning(f"[STATUS] Extraction not found for submission_id: {submission_id}")
                response.extraction_id = None
                response.transcript = None
                response.insights = None
                response.metrics = None

        return response

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission_id format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get status")


# ============================================================================
# Helper Functions
# ============================================================================

# Global dictionary to track active processing tasks (prevent duplicate processing)
_active_processing_tasks: Dict[str, asyncio.Task] = {}


async def _validate_audio_chunk_async(
    session_id: str,
    chunk_index: int,
    audio_data: str,
    mime_type: str
) -> None:
    """
    Validate audio chunk in background. Logs warnings to both logs AND database.

    This is async and fire-and-forget - validation warnings are logged but don't
    block the upload process. This allows chunks to continue uploading while
    validation happens in the background.

    Validates (on first chunk only for expensive checks):
    1. MIME type against Gemini API supported formats (all chunks)
    2. Audio format detection from magic bytes (first chunk)
    3. MIME/format mismatch (first chunk)
    4. Chunk size anomalies (all chunks, lightweight)
    5. Empty/silent audio detection (first chunk)
    6. Codec compatibility (first chunk)
    7. Format detection failures (first chunk)
    """
    import base64

    try:
        # For first chunk: do comprehensive validation (decode full data)
        # For subsequent chunks: only do lightweight checks (size from base64 length)
        is_first_chunk = chunk_index == 0

        # 1. MIME type validation (lightweight - no decode needed)
        if not is_supported_mime_type(mime_type):
            message = f"Unsupported MIME type '{mime_type}'. Supported: {SUPPORTED_MIME_TYPES}"
            logger.warning(f"[CHUNK_VALIDATION] Session {session_id[:8]}... chunk {chunk_index}: {message}")
            await log_validation_warning(
                session_id=session_id,
                chunk_index=chunk_index,
                warning_type="mime_unsupported",
                declared_mime_type=mime_type,
                detected_format=None,
                message=message
            )

        # 2. Quick size check from base64 length (lightweight - no decode)
        estimated_size = len(audio_data) * 3 // 4  # base64 is ~4/3 ratio
        if estimated_size < 1000:  # Less than 1KB
            message = f"Chunk is very small (~{estimated_size} bytes) - may be empty or corrupted"
            logger.warning(f"[CHUNK_VALIDATION] Session {session_id[:8]}... chunk {chunk_index}: {message}")
            await log_validation_warning(
                session_id=session_id,
                chunk_index=chunk_index,
                warning_type="chunk_size_anomaly",
                declared_mime_type=mime_type,
                detected_format=None,
                message=message
            )

        # For non-first chunks, skip expensive validations
        if not is_first_chunk:
            return

        # === FIRST CHUNK ONLY: Comprehensive validation ===

        # 3. Format detection using partial decode (only first ~20 bytes needed for magic bytes)
        detected_format = None
        header_bytes = None
        try:
            header_b64 = audio_data[:32] if len(audio_data) >= 32 else audio_data
            # Add padding for partial base64 decode
            padding = 4 - (len(header_b64) % 4)
            if padding != 4:
                header_b64 += "=" * padding
            header_bytes = base64.b64decode(header_b64)
            detected_format = detect_audio_format(header_bytes)
        except Exception:
            # Fallback: try decoding more data
            try:
                header_bytes = base64.b64decode(audio_data[:200])
                detected_format = detect_audio_format(header_bytes)
            except:
                pass

        # 4. Format detection failure
        if not detected_format:
            message = f"Could not detect audio format from file header - may be corrupted or unusual format"
            logger.warning(f"[CHUNK_VALIDATION] Session {session_id[:8]}... chunk {chunk_index}: {message}")
            await log_validation_warning(
                session_id=session_id,
                chunk_index=chunk_index,
                warning_type="format_detection_failed",
                declared_mime_type=mime_type,
                detected_format=None,
                message=message
            )

        # 5. MIME/format mismatch
        if detected_format and not mime_matches_format(mime_type, detected_format):
            message = f"MIME mismatch - declared '{mime_type}' but detected '{detected_format}'"
            logger.warning(f"[CHUNK_VALIDATION] Session {session_id[:8]}... chunk {chunk_index}: {message}")
            await log_validation_warning(
                session_id=session_id,
                chunk_index=chunk_index,
                warning_type="mime_mismatch",
                declared_mime_type=mime_type,
                detected_format=detected_format,
                message=message
            )

        # === FULL DECODE: Only for checks that need complete data ===
        # These are more expensive but provide valuable debugging info
        # Only proceed if audio is not too large (skip for >20MB to avoid memory issues)
        if estimated_size > 20 * 1024 * 1024:
            logger.debug(f"[CHUNK_VALIDATION] Session {session_id[:8]}... chunk {chunk_index}: "
                        f"Skipping full decode for large file ({estimated_size / (1024*1024):.1f}MB)")
            return

        full_audio_bytes = None
        try:
            full_audio_bytes = base64.b64decode(audio_data)
        except Exception as decode_err:
            logger.debug(f"[CHUNK_VALIDATION] Session {session_id[:8]}... chunk {chunk_index}: "
                        f"Failed to decode full audio: {decode_err}")
            return

        # 6. Detailed chunk size validation
        size_warning = validate_chunk_size(full_audio_bytes, chunk_index)
        if size_warning:
            logger.warning(f"[CHUNK_VALIDATION] Session {session_id[:8]}... chunk {chunk_index}: {size_warning['message']}")
            await log_validation_warning(
                session_id=session_id,
                chunk_index=chunk_index,
                warning_type=size_warning["warning_type"],
                declared_mime_type=mime_type,
                detected_format=detected_format,
                message=size_warning["message"]
            )

        # 7. Empty audio detection
        empty_warning = detect_empty_audio(full_audio_bytes, mime_type)
        if empty_warning:
            logger.warning(f"[CHUNK_VALIDATION] Session {session_id[:8]}... chunk {chunk_index}: {empty_warning['message']}")
            await log_validation_warning(
                session_id=session_id,
                chunk_index=chunk_index,
                warning_type=empty_warning["warning_type"],
                declared_mime_type=mime_type,
                detected_format=detected_format,
                message=empty_warning["message"]
            )

        # 8. Codec validation (needs to scan file for codec markers)
        if detected_format:
            codec_warning = validate_codec(full_audio_bytes, detected_format, mime_type)
            if codec_warning:
                logger.warning(f"[CHUNK_VALIDATION] Session {session_id[:8]}... chunk {chunk_index}: {codec_warning['message']}")
                await log_validation_warning(
                    session_id=session_id,
                    chunk_index=chunk_index,
                    warning_type=codec_warning["warning_type"],
                    declared_mime_type=mime_type,
                    detected_format=detected_format,
                    message=codec_warning["message"]
                )

    except Exception as e:
        logger.warning(f"[CHUNK_VALIDATION] Session {session_id[:8]}... chunk {chunk_index}: "
                      f"Validation error: {e}")


async def _handle_chunk_timeout(
    session: Dict[str, Any],
    session_id: str,
    reason: str,
    expected_count: int,
    present_indices: List[int],
) -> None:
    """
    Handle timeout when chunks don't complete in time.

    Called by chunk_memory_store timeout handler. Updates session status
    and sends error webhook to EHR.

    Args:
        session: Session data dict
        session_id: Session UUID string
        reason: Reason for timeout (e.g., "missing chunks: [0, 1]")
        expected_count: Expected number of chunks
        present_indices: List of chunk indices that were received
    """
    from services.webhook_service import webhook_service
    from services.chunk_memory_store import CHUNK_COMPLETION_TIMEOUT_SECONDS

    try:
        logger.error(
            f"[CHUNK_TIMEOUT] Session {session_id[:8]}... timed out. "
            f"Expected {expected_count} chunks, got {len(present_indices)}. "
            f"Reason: {reason}"
        )

        # Update session status to CHUNK_TIMEOUT (allows retry later)
        try:
            await asyncio.to_thread(
                update_session_status,
                uuid.UUID(session.get("correlation_id", session_id)),
                "CHUNK_TIMEOUT",
            )
        except Exception as e:
            logger.error(f"[CHUNK_TIMEOUT] Failed to update session status: {e}")

        # Build error payload for webhook
        error_payload = {
            "session_id": session_id,
            "status": "CHUNK_TIMEOUT",
            "error": "CHUNK_COMPLETION_TIMEOUT",
            "message": f"Recording failed: {reason}",
            "details": {
                "expected_chunks": expected_count,
                "received_chunks": len(present_indices),
                "present_indices": present_indices,
                "missing_indices": [i for i in range(expected_count) if i not in present_indices],
                "timeout_seconds": CHUNK_COMPLETION_TIMEOUT_SECONDS,
                "can_retry": True,  # Chunks still in DB for potential retry
            },
            "recording_metadata": session.get("recording_metadata_json", {}),
        }

        # Build metadata for webhook
        metadata = {
            "correlation_id": session.get("correlation_id"),
            "counsellor_id": session.get("counsellor_id"),
            "student_id": session.get("student_id"),
            "template_code": session.get("template_code"),
            "school_id": session.get("school_id"),
        }

        # Send error webhook
        try:
            await webhook_service.send_insights_to_webhook(
                insights=error_payload,
                metadata=metadata,
                source="recording.chunk_timeout"
            )
            logger.info(f"[CHUNK_TIMEOUT] Error webhook sent for session {session_id[:8]}...")
        except Exception as e:
            logger.error(f"[CHUNK_TIMEOUT] Failed to send error webhook: {e}")

    except Exception as e:
        logger.error(f"[CHUNK_TIMEOUT] Error in timeout handler: {e}", exc_info=True)


async def _save_chunk_to_db_async(
    session_id: uuid.UUID,
    chunk_index: int,
    audio_data: str,
    mime_type: str,
    duration_seconds: Optional[float],
    is_last: bool,
) -> None:
    """
    Async wrapper for save_audio_chunk that logs errors but doesn't fail.

    This is a fire-and-forget task - errors are logged but don't affect the upload response.
    The in-memory store is the primary source; DB is backup/persistence.
    """
    import time
    try:
        save_start = time.time()
        await asyncio.to_thread(
            save_audio_chunk,
            session_id=session_id,
            chunk_index=chunk_index,
            audio_data=audio_data,
            mime_type=mime_type,
            duration_seconds=duration_seconds,
            is_last=is_last,
        )
        save_time = time.time() - save_start
        logger.info(f"[TIMING_CHUNK_ASYNC] Chunk {chunk_index} saved to DB (async): {save_time:.3f}s")
    except Exception as e:
        logger.error(f"[CHUNK_ASYNC] Failed to save chunk {chunk_index} to DB: {e}")
        # Don't re-raise - this is fire-and-forget
        # The in-memory store has the chunk; processing can still proceed


async def _run_background_processing(
    submission_id: uuid.UUID,
    session_id: Optional[uuid.UUID] = None,
    session_data: Optional[Dict[str, Any]] = None,
):
    """
    Execute the recording processing pipeline in the background.

    This function runs the full pipeline:
    1. Load chunks from database
    2. Stitch audio chunks
    3. Transcribe audio
    4. Extract medical insights
    5. Send webhook (if extraction_mode == 'full')
    6. Save results to database

    All progress is tracked in the database so SSE connections can read it.

    Args:
        submission_id: UUID of the processing job
        session_id: Optional session UUID (avoids DB query if provided)
        session_data: Optional session data dict (avoids DB query if provided)
    """
    submission_id_str = str(submission_id)

    try:
        logger.debug(f"[BACKGROUND] Starting background processing for submission_id: {submission_id_str}")

        # ============================================================================
        # OPTIMIZATION: Use passed session data if available, skip DB queries
        # ============================================================================
        session = session_data
        if session:
            logger.debug(f"[BACKGROUND] Using passed session data (no DB query)")
            logger.debug(f"[BACKGROUND] Session - Template: {session.get('template_name')}, Extraction mode: {session.get('extraction_mode')}")
        else:
            # Fallback: Query job and session from DB (for retries, server restart, etc.)
            logger.debug(f"[BACKGROUND] Session data not passed, falling back to DB query")
            job = await asyncio.to_thread(get_job_by_submission_id, submission_id)
            if not job:
                logger.error(f"[BACKGROUND] Job not found: {submission_id_str}")
                return

            logger.debug(f"[BACKGROUND] Job found - Status: {job['status']}, Session: {job.get('session_id')}")

            # If job is already completed or errored, don't reprocess
            if job['status'] in ['COMPLETED', 'ERROR']:
                logger.warning(f"[BACKGROUND] ⚠️  Job already {job['status']}, skipping: {submission_id_str}")
                return

            # If job is already processing, don't start duplicate processing
            if job['status'] not in ['PENDING', 'SUBMITTED']:
                logger.warning(f"[BACKGROUND] ⚠️  Job already processing (status: {job['status']}): {submission_id_str}")
                return

            # Get session from DB
            from services.supabase_service import supabase
            session_response = await asyncio.to_thread(
                lambda: supabase.table("recording_sessions").select("*").eq("id", str(job['session_id'])).execute()
            )
            session = session_response.data[0] if session_response.data else None

            if session:
                logger.debug(f"[BACKGROUND] Session found - Template: {session.get('template_name')}, Extraction mode: {session.get('extraction_mode')}")
            else:
                logger.warning(f"[BACKGROUND] Session not found for session_id: {job.get('session_id')}")
                # Update job to ERROR and send webhook (prevent indefinite EHR waiting)
                try:
                    from services.supabase_service import update_job_error
                    await asyncio.to_thread(
                        update_job_error,
                        submission_id,
                        error_message="Session not found in database"
                    )
                    from services.webhook_service import send_error_webhook
                    await send_error_webhook(
                        error_message="Session not found in database",
                        session_id=str(job.get('session_id')),
                        submission_id=submission_id_str,
                        source="recording",
                        error_code="SESSION_NOT_FOUND",
                    )
                except Exception as err:
                    logger.error(f"[BACKGROUND] Failed to update error for missing session: {err}")
                return

            session_id = uuid.UUID(job['session_id'])

        logger.debug(f"[BACKGROUND] Proceeding with processing")

        # Create processor and run pipeline (pass session data to avoid re-query)
        logger.debug(f"[BACKGROUND] Creating RecordingProcessor for submission_id: {submission_id_str}")
        processor = RecordingProcessor(
            submission_id=submission_id,
            session_id=session_id,
            session_data=session,
        )

        # Process and collect results (we don't stream, just process)
        final_result = None
        event_count = 0
        logger.debug(f"[BACKGROUND] Starting to iterate through processor.process() events")

        async for progress_event in processor.process():
            event_count += 1
            logger.debug(f"[BACKGROUND] Event {event_count}: {progress_event.event_type} - {progress_event.data.get('status', 'N/A')}")

            # Store the last event which should be the complete event
            if progress_event.event_type == 'complete':
                final_result = progress_event
                logger.debug(f"[BACKGROUND] Received 'complete' event")
            elif progress_event.event_type == 'error':
                error_msg = progress_event.data.get('message', '')
                # Log transient API errors as warnings, not errors
                if "temporarily unavailable" in error_msg or "Server disconnected" in error_msg:
                    logger.warning(f"[BACKGROUND] ⚠️ Transient API error: {error_msg}")
                else:
                    logger.error(f"[BACKGROUND] ❌ Received 'error' event: {error_msg}")

        logger.debug(f"[BACKGROUND] Finished processing loop. Total events: {event_count}, Final result: {'Found' if final_result else 'None'}")
        logger.debug(f"[BACKGROUND] Background processing completed for submission_id: {submission_id_str}")

    except Exception as e:
        error_msg = str(e)
        # Log transient API errors as warnings without full traceback
        if "temporarily unavailable" in error_msg or "Server disconnected" in error_msg:
            logger.warning(f"[BACKGROUND] ⚠️ Transient API error for {submission_id_str}: {error_msg}")
        else:
            logger.error(f"[BACKGROUND] Background processing failed for {submission_id_str}: {error_msg}")
            logger.error(f"[BACKGROUND] Traceback: {traceback.format_exc()}")

        # Update job with error
        try:
            from services.supabase_service import update_job_error
            await asyncio.to_thread(
                update_job_error,
                submission_id,
                error_message=f"Background processing failed: {str(e)}"
            )
        except Exception as update_error:
            logger.error(f"[BACKGROUND] Failed to update job error: {str(update_error)}")

        # Send error webhook to notify EHR systems
        try:
            from services.webhook_service import send_error_webhook
            _session = locals().get('session')
            _session_id = locals().get('session_id')
            await send_error_webhook(
                error_message=f"Background processing failed: {str(e)}",
                session_id=str(_session_id) if _session_id else None,
                submission_id=submission_id_str,
                session_data=_session if isinstance(_session, dict) else None,
                source="recording",
                error_code="BACKGROUND_PROCESSING_FAILED",
            )
        except Exception as webhook_err:
            logger.warning(f"[BACKGROUND:WEBHOOK] Failed to send error webhook: {webhook_err}")

        # Publish error to realtime_extraction_responses (for EHR Realtime subscribers)
        try:
            from services.realtime_publisher_service import publish_error_response_fire_and_forget
            from services.supabase_service import get_counsellor_school_id_cached
            import uuid as uuid_mod
            _session = locals().get('session')
            _sess_data = _session if isinstance(_session, dict) else {}
            _counsellor_id = _sess_data.get("counsellor_id")
            _school_id = get_counsellor_school_id_cached(uuid_mod.UUID(_counsellor_id)) if _counsellor_id else None
            if _school_id and submission_id_str:
                asyncio.create_task(publish_error_response_fire_and_forget(
                    submission_id=submission_id_str,
                    school_id=_school_id,
                    counsellor_id=_counsellor_id,
                    error_message=f"Background processing failed: {str(e)}",
                    error_code="BACKGROUND_PROCESSING_FAILED",
                    session_id=str(_session_id) if _session_id else None,
                ))
        except Exception as rt_err:
            logger.warning(f"[BACKGROUND:REALTIME] Failed to schedule error publish: {rt_err}")

    finally:
        # Remove from active tasks
        if submission_id_str in _active_processing_tasks:
            del _active_processing_tasks[submission_id_str]
            logger.debug(f"[BACKGROUND] Removed {submission_id_str} from active tasks")


async def _trigger_background_processing(
    submission_id: uuid.UUID,
    session_id: Optional[uuid.UUID] = None,
    session_data: Optional[Dict[str, Any]] = None,
):
    """
    Trigger background processing without waiting for it to complete.
    This is a fire-and-forget task that enables webhook functionality
    without requiring frontend SSE connection.

    Args:
        submission_id: UUID of the processing job to start
        session_id: Optional session UUID (avoids DB query if provided)
        session_data: Optional session data dict (avoids DB query if provided)
    """
    submission_id_str = str(submission_id)

    # Check if this submission is already being processed
    if submission_id_str in _active_processing_tasks:
        task = _active_processing_tasks[submission_id_str]
        if not task.done():
            logger.debug(f"[BACKGROUND] Processing already active for: {submission_id_str}")
            return
        else:
            # Task is done, remove it
            del _active_processing_tasks[submission_id_str]

    # Create and store background task (pass session data to avoid re-query)
    task = asyncio.create_task(
        _run_background_processing(
            submission_id=submission_id,
            session_id=session_id,
            session_data=session_data,
        )
    )
    _active_processing_tasks[submission_id_str] = task

    logger.debug(f"[BACKGROUND] Background processing task created for: {submission_id_str}")
    logger.debug(f"[BACKGROUND] Active processing tasks: {len(_active_processing_tasks)}")


# ============================================================================
# Live Session Endpoints (for RecordTab/WebSocket recordings)
# ============================================================================

@router.post("/live/session", response_model=CreateLiveSessionResponse)
async def create_live_session(
    http_request: Request,
    request: CreateLiveSessionRequest,
    _auth = Depends(verify_counsellor_access)
):
    """
    Create a recording session for WebSocket/live recordings (RecordTab).

    Unlike chunked recording, this creates session at END of recording,
    just before extraction. No audio chunks are uploaded - transcript comes
    from client-side WebSocket (Gemini Live API).

    Workflow:
    1. User stops RecordTab recording
    2. Frontend calls this endpoint to create session
    3. Frontend calls /extract with correlation_id (saves transcript + extracts)
    4. All workflows now use unified extraction path

    Args:
        request: CreateLiveSessionRequest with counsellor_id, student_id, template_code, template_name, processing_mode

    Returns:
        CreateLiveSessionResponse with correlation_id and session_id
    """
    try:
        # Block hidden processing modes (ultra/ultra_fast are disabled)
        from routers.processing_modes import HIDDEN_MODE_CODES
        if request.processing_mode in HIDDEN_MODE_CODES:
            raise HTTPException(
                status_code=400,
                detail=f"Processing mode '{request.processing_mode}' is currently unavailable. Use 'fast', 'default', or 'thorough'."
            )

        # Validate EHR client has access to this counsellor (school-scoped)
        await validate_counsellor_from_body(http_request, request.counsellor_id)

        logger.info(f"[LIVE_SESSION] Creating live session for counsellor: {request.counsellor_id}, template_code: {request.template_code}")

        # Validate counsellor_id is a valid UUID
        try:
            counsellor_uuid = uuid.UUID(request.counsellor_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid counsellor ID format"
            )

        # Use frontend-provided correlation_id or generate new
        # Frontend pre-generates correlation_id for audio chunk upload during recording
        if request.correlation_id:
            try:
                correlation_uuid = uuid.UUID(request.correlation_id)
                logger.debug(f"[LIVE_SESSION] Using frontend-provided correlation_id: {request.correlation_id}")

                # Validate not already used (session shouldn't exist yet)
                from services.supabase_service import supabase
                existing = supabase.table("recording_sessions")\
                    .select("id").eq("correlation_id", request.correlation_id).execute()
                if existing.data:
                    raise HTTPException(
                        status_code=400,
                        detail="Correlation ID already exists"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid correlation ID format"
                )
        else:
            correlation_uuid = uuid.uuid4()
            logger.debug(f"[LIVE_SESSION] Generated new correlation_id: {correlation_uuid}")

        # ⭐ OPTIMIZATION: Look up consultation_type_id from template for parallel prompt generation (cached)
        consultation_type_id_for_session = None
        template_name_to_use = request.template_name  # Display name (optional)
        active_template_record = None  # Initialize for assistant validation
        try:
            from services.supabase_service import get_active_template_by_code_cached

            active_template_record = get_active_template_by_code_cached(counsellor_uuid, request.template_code)
            if active_template_record:
                consultation_type_id_for_session = active_template_record.get('consultation_type_id')
                # Get template_name if not provided in request
                if not template_name_to_use:
                    template_name_to_use = active_template_record.get('template_name')
                logger.debug(
                    f"[LIVE_SESSION] Resolved consultation_type_id={consultation_type_id_for_session} "
                    f"from template '{request.template_code}' for parallel prompt generation"
                )
            else:
                logger.warning(
                    f"[LIVE_SESSION] ⚠️ Could not resolve consultation_type_id from template '{request.template_code}' "
                    f"(will fallback to lookup during extraction)"
                )
        except Exception as e:
            logger.warning(
                f"[LIVE_SESSION] ⚠️ Failed to lookup consultation_type_id: {e} "
                f"(will fallback to lookup during extraction)"
            )

        # Validate assistant template access if assistant_id is provided
        assistant_id_to_use = request.assistant_id
        if assistant_id_to_use:
            from services.assistant_templates_service import validate_assistant_template_access
            from services.assistant_service import get_assistant

            # Verify assistant exists
            assistant = get_assistant(assistant_id_to_use)
            if not assistant:
                raise HTTPException(
                    status_code=404,
                    detail="Assistant not found"
                )

            # Validate template access if we have the template ID
            if active_template_record and active_template_record.get('id'):
                template_id_for_validation = active_template_record['id']
                if not validate_assistant_template_access(assistant_id_to_use, template_id_for_validation):
                    raise HTTPException(
                        status_code=403,
                        detail="Assistant does not have access to this template"
                    )
                logger.debug(f"[LIVE_SESSION] Assistant {assistant_id_to_use} has access to template {request.template_code}")

        # ⭐ Build session_context_json with template_id for emotion analysis
        # This is needed for schedule_live_audio_emotion to find the template
        session_context = {}
        if active_template_record:
            session_context = {
                "template_id": active_template_record.get('id'),
                "template_code": request.template_code,
                "consultation_type_id": str(consultation_type_id_for_session) if consultation_type_id_for_session else None,
                "source": active_template_record.get('source', 'unknown'),
            }
            logger.debug(f"[LIVE_SESSION] Built session_context with template_id={active_template_record.get('id')}")

        # Create recording session for live recording
        # Note: No audio chunks, no extraction_mode (will use /extract endpoint)
        session = create_recording_session(
            correlation_id=correlation_uuid,
            counsellor_id=str(counsellor_uuid),
            student_id=request.student_id,
            template_code=request.template_code,  # Unique identifier for lookups
            template_name=template_name_to_use,  # Display name
            processing_mode=request.processing_mode,
            extraction_mode=None,  # Will extract via /extract endpoint with correlation_id
            transcription_model="gemini-live-api",  # RecordTab uses client-side WebSocket
            extraction_model="gemini-2.5-flash",  # Default extraction model
            chunk_duration_seconds=0,  # No chunking for live recordings
            consultation_type_id=consultation_type_id_for_session,  # ⭐ For parallel prompt generation optimization
            assistant_id=assistant_id_to_use,  # Track assistant who initiated recording
            session_context_json=session_context,  # ⭐ Contains template_id for emotion analysis
        )

        session_id = session['id']
        correlation_id = str(correlation_uuid)

        logger.info(f"[LIVE_SESSION] ✓ Live session created: {session_id}, correlation_id: {correlation_id}")

        # Fire-and-forget: Auto-link counsellor to student's counsellor_ids
        try:
            from services.supabase_service import link_counsellor_to_student
            asyncio.create_task(asyncio.to_thread(
                link_counsellor_to_student,
                patient_uuid=session["student_id"],
                counsellor_id=str(counsellor_uuid),
            ))
        except Exception as e:
            logger.warning(f"[LIVE_SESSION] Failed to schedule counsellor-student link: {e}")

        # ⭐ Create processing_job using correlation_id as submission_id
        # This unifies RecordTab with VHRScreen workflow - both now have processing_jobs
        # and extractions can link to processing_jobs.submission_id
        from services.supabase_service import create_processing_job

        processing_job = create_processing_job(
            session_id=uuid.UUID(session_id),
            submission_id=correlation_uuid,  # Use correlation_id as submission_id
        )

        logger.debug(f"[LIVE_SESSION] Processing job created with submission_id: {correlation_id}")

        return CreateLiveSessionResponse(
            correlation_id=correlation_id,
            session_id=str(session_id),
            message="Live session created successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[LIVE_SESSION] Failed to create live session: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to create live session"
        )


@router.post("/live/chunk", response_model=LiveChunkResponse)
async def upload_live_chunk(
    http_request: Request,
    request: LiveChunkRequest,
    _auth = Depends(verify_counsellor_access),
):
    """
    Upload audio chunk during live Gemini streaming (parallel to transcription).

    This endpoint stores audio chunks in memory for later stitching and emotion analysis.
    Called in parallel while Gemini Live API streams transcription.

    NOTE: No DB validation - session doesn't exist yet during recording.
    Backend generates correlation_id on first chunk, frontend uses it for subsequent chunks.
    Session created via /live/session after recording stops.

    Args:
        request: LiveChunkRequest with chunk_index, audio_data, mime_type
                 (correlation_id omitted on first chunk, required for subsequent)

    Returns:
        LiveChunkResponse with correlation_id (use for subsequent chunks)
    """
    try:
        from services.chunk_memory_store import store_chunk

        # Validate EHR client has access to counsellor (when counsellor_id provided on first chunk)
        if request.counsellor_id:
            await validate_counsellor_from_body(http_request, request.counsellor_id)

        # === CORRELATION_ID HANDLING ===
        # First chunk (index=0): Backend generates, MUST NOT be provided by frontend
        # Subsequent chunks: Frontend MUST provide the backend-generated ID
        if request.chunk_index == 0:
            if request.correlation_id:
                raise HTTPException(
                    status_code=400,
                    detail="correlation_id must not be provided for first chunk (chunk_index=0). Backend generates it."
                )
            correlation_id = str(uuid.uuid4())
            logger.info(f"[LIVE_CHUNK] Generated correlation_id: {correlation_id[:8]}...")
        else:
            # Subsequent chunks: MUST have correlation_id
            if not request.correlation_id:
                raise HTTPException(
                    status_code=400,
                    detail="correlation_id required for chunk_index > 0"
                )
            # Validate UUID format
            try:
                uuid.UUID(request.correlation_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid correlation_id format")
            correlation_id = request.correlation_id

        # Store in memory (uses correlation_id as session key)
        # No DB lookup - session doesn't exist until recording stops
        stored = store_chunk(
            session_id=correlation_id,  # Backend-generated or validated
            chunk_index=request.chunk_index,
            audio_data=request.audio_data,
            mime_type=request.mime_type,
            duration_seconds=None,
            is_last=False,  # Never triggers processing (unlike /chunk endpoint)
        )

        if stored:
            logger.debug(f"[LIVE_CHUNK] Stored chunk {request.chunk_index} for {correlation_id[:8]}...")
        else:
            logger.warning(f"[LIVE_CHUNK] Failed to store chunk {request.chunk_index} for {correlation_id[:8]}...")

        # PARALLEL PROMPT GENERATION: If first chunk with context, start pre-generating prompts
        # This saves ~1.2-1.8s by generating prompts while recording continues
        if request.chunk_index == 0 and request.counsellor_id and request.template_code:
            logger.debug(f"[LIVE_CHUNK] First chunk with context - starting parallel prompt generation")

            # Resolve student_id (display ID like "Lak123") to student UUID
            # This is needed for medicine/investigation list injection (not student context)
            resolved_student_uuid = None
            if request.student_id:
                from routers.student_history import resolve_student_id
                from services.supabase_service import get_counsellor_school_id_cached
                _school_id = get_counsellor_school_id_cached(request.counsellor_id) if request.counsellor_id else None
                resolved_student_uuid = resolve_student_id(request.student_id, school_id=_school_id)
                if resolved_student_uuid:
                    logger.debug(f"[LIVE_CHUNK] Resolved student_id '{request.student_id}' -> UUID {str(resolved_student_uuid)[:8]}...")
                else:
                    logger.warning(f"[LIVE_CHUNK] Could not resolve student_id '{request.student_id}' to UUID")

            asyncio.create_task(
                _generate_and_cache_live_prompts(
                    correlation_id=correlation_id,
                    counsellor_id=request.counsellor_id,
                    template_code=request.template_code,
                    student_id=str(resolved_student_uuid) if resolved_student_uuid else None,
                )
            )

        return LiveChunkResponse(
            message="Chunk stored",
            chunk_index=request.chunk_index,
            correlation_id=correlation_id,  # Always return for frontend to use
        )

    except Exception as e:
        logger.error(f"[LIVE_CHUNK] Failed to store chunk: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to store chunk"
        )

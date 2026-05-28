"""
Recordings Router - Endpoints for listing and reprocessing recordings

This router provides:
- GET /doctor/{doctor_id}: List recordings for a doctor (with optional patient filter)
- POST /{session_id}/reprocess: Reprocess a recording with new template/settings
"""

import logging
import os
import base64
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
import uuid

from services.supabase_service import list_recordings_for_doctor, list_recordings_for_nurse, get_session_transcript, get_session_chunks, get_chunk_count, supabase
from services.reprocess_service import reprocess_recording
from services.audio_storage_service import fetch_audio_from_url
from services.audio_stitcher import stitch_audio_chunks

# Auth setup - conditionally enabled
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import EHRDoctorAccessChecker, get_current_client
    from services.auth_service import validate_ehr_doctor_access
    from typing import Optional as OptionalType

    _doctor_checker = EHRDoctorAccessChecker()

    async def verify_doctor_access(request: Request, doctor_id: OptionalType[str] = None):  # type: ignore[misc]
        """Verify EHR client has access to doctor data."""
        doctor_uuid = uuid.UUID(doctor_id) if doctor_id else None
        client = get_current_client(request)
        return await _doctor_checker(request, doctor_uuid, client)

    async def validate_doctor_from_path(http_request: Request, doctor_id: str):  # type: ignore[misc]
        """Validate doctor_id access for path parameter."""
        client = get_current_client(http_request)
        if client.client_type == "ehr":
            doctor_uuid = uuid.UUID(doctor_id)
            if not await validate_ehr_doctor_access(client, doctor_uuid):
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )
else:
    # No-op dependencies when auth is disabled
    async def verify_doctor_access(request: Request = None, doctor_id: str = None):  # type: ignore[misc]
        return None

    async def validate_doctor_from_path(http_request: Request = None, doctor_id: str = None):  # type: ignore[misc]
        pass  # No-op when auth disabled

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/recordings", tags=["Recording Management"])


# ============================================================================
# Audio Validation Helpers
# ============================================================================

# Magic bytes for common audio formats
AUDIO_MAGIC_BYTES = {
    "audio/webm": [b"\x1a\x45\xdf\xa3"],  # EBML/Matroska header
    "video/webm": [b"\x1a\x45\xdf\xa3"],  # Browser sometimes reports video/webm
    "audio/wav": [b"RIFF"],
    "audio/mp3": [b"\xff\xfb", b"\xff\xfa", b"\xff\xf3", b"ID3"],  # Various MP3 headers
    "audio/mpeg": [b"\xff\xfb", b"\xff\xfa", b"\xff\xf3", b"ID3"],
    "audio/ogg": [b"OggS"],
    "audio/flac": [b"fLaC"],
    "audio/aac": [b"\xff\xf1", b"\xff\xf9"],
    "audio/mp4": [b"\x00\x00\x00"],  # ftyp box (check for 'ftyp' at offset 4)
    "audio/m4a": [b"\x00\x00\x00"],
}

# Minimum expected size for valid audio (1KB - anything smaller is likely corrupt)
MIN_AUDIO_SIZE_BYTES = 1024


def validate_audio_content(audio_bytes: bytes, mime_type: str) -> tuple[bool, str]:
    """
    Validate audio content by checking magic bytes and minimum size.

    Args:
        audio_bytes: Raw audio bytes
        mime_type: Expected MIME type

    Returns:
        Tuple of (is_valid, reason)
    """
    # Check minimum size
    if len(audio_bytes) < MIN_AUDIO_SIZE_BYTES:
        return False, f"Audio too small ({len(audio_bytes)} bytes, minimum {MIN_AUDIO_SIZE_BYTES})"

    # Normalize mime type (remove codec info)
    base_mime = mime_type.split(";")[0].strip().lower()

    # Get expected magic bytes for this format
    expected_magic = AUDIO_MAGIC_BYTES.get(base_mime)

    if expected_magic:
        # Check if any of the expected magic bytes match
        matches = False
        for magic in expected_magic:
            if audio_bytes[:len(magic)] == magic:
                matches = True
                break
            # Special case for MP4/M4A - check for 'ftyp' at offset 4
            if base_mime in ["audio/mp4", "audio/m4a"] and len(audio_bytes) > 8:
                if audio_bytes[4:8] == b"ftyp":
                    matches = True
                    break

        if not matches:
            return False, f"Invalid magic bytes for {base_mime}. Got: {audio_bytes[:8].hex()}"

    return True, "Valid"


def decode_and_validate_audio(audio_b64: str, mime_type: str) -> tuple[bytes | None, str]:
    """
    Decode base64 audio and validate the content.

    Args:
        audio_b64: Base64 encoded audio
        mime_type: Expected MIME type

    Returns:
        Tuple of (audio_bytes or None, error_message or "Valid")
    """
    if not audio_b64:
        return None, "No audio data"

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception as e:
        return None, f"Base64 decode failed: {e}"

    is_valid, reason = validate_audio_content(audio_bytes, mime_type)
    if not is_valid:
        return None, reason

    return audio_bytes, "Valid"


async def fetch_audio_with_fallback(
    session_id: str,
    session_data: dict,
) -> tuple[str, str, int, str]:
    """
    Fetch audio with fallback chain:
    1. Try full_audio_data from recording_sessions
    2. Try full_audio_url from temp-audio bucket
    3. Try stitching from audio_chunks

    Args:
        session_id: Recording session ID
        session_data: Session data from recording_sessions table

    Returns:
        Tuple of (audio_b64, mime_type, size_bytes, source)

    Raises:
        HTTPException if no valid audio found
    """
    mime_type = session_data.get("full_audio_mime_type") or "audio/webm"

    # === FALLBACK 1: Try full_audio_data from DB ===
    audio_b64 = session_data.get("full_audio_data")
    if audio_b64:
        audio_bytes, validation_msg = decode_and_validate_audio(audio_b64, mime_type)
        if audio_bytes:
            logger.info(f"[AUDIO_FALLBACK] Source: full_audio_data (DB column)")
            return audio_b64, mime_type, len(audio_bytes), "db_column"
        else:
            logger.warning(f"[AUDIO_FALLBACK] full_audio_data invalid: {validation_msg}")

    # === FALLBACK 2: Try full_audio_url from temp-audio bucket ===
    audio_url = session_data.get("full_audio_url")
    if audio_url:
        logger.info(f"[AUDIO_FALLBACK] Trying temp-audio bucket: {audio_url[:50]}...")
        try:
            result = fetch_audio_from_url(audio_url)
            if result:
                fetched_b64, fetched_mime = result
                audio_bytes, validation_msg = decode_and_validate_audio(fetched_b64, fetched_mime)
                if audio_bytes:
                    logger.info(f"[AUDIO_FALLBACK] Source: temp-audio bucket")
                    return fetched_b64, fetched_mime, len(audio_bytes), "temp_audio_bucket"
                else:
                    logger.warning(f"[AUDIO_FALLBACK] temp-audio bucket audio invalid: {validation_msg}")
            else:
                logger.warning(f"[AUDIO_FALLBACK] temp-audio bucket returned no data")
        except Exception as e:
            logger.warning(f"[AUDIO_FALLBACK] temp-audio bucket fetch failed: {e}")

    # === FALLBACK 3: Try stitching from audio_chunks ===
    logger.info(f"[AUDIO_FALLBACK] Trying audio_chunks for session: {session_id}")
    try:
        chunks = get_session_chunks(uuid.UUID(session_id))
        if chunks and len(chunks) > 0:
            logger.info(f"[AUDIO_FALLBACK] Found {len(chunks)} chunks, stitching...")
            stitched_b64, stitched_mime = stitch_audio_chunks(chunks, mime_type)
            audio_bytes, validation_msg = decode_and_validate_audio(stitched_b64, stitched_mime)
            if audio_bytes:
                logger.info(f"[AUDIO_FALLBACK] Source: stitched from {len(chunks)} chunks")
                return stitched_b64, stitched_mime, len(audio_bytes), f"stitched_{len(chunks)}_chunks"
            else:
                logger.warning(f"[AUDIO_FALLBACK] Stitched audio invalid: {validation_msg}")
        else:
            logger.warning(f"[AUDIO_FALLBACK] No audio chunks found for session")
    except Exception as e:
        logger.warning(f"[AUDIO_FALLBACK] Chunk stitching failed: {e}")

    # === No valid audio found ===
    raise HTTPException(
        status_code=404,
        detail="No valid audio data available"
    )


# ============================================================================
# Response Models
# ============================================================================

class RecordingInfo(BaseModel):
    """Single recording info in list response"""
    session_id: str
    correlation_id: Optional[str]
    patient_id: Optional[str]
    patient_identifier: Optional[str]
    patient_name: Optional[str]
    consultation_datetime: str
    completed_at: Optional[str]
    template_code: Optional[str]
    template_name: Optional[str]
    processing_mode: Optional[str]
    extraction_mode: Optional[str]
    transcription_model: Optional[str]
    extraction_model: Optional[str]
    has_audio: bool
    has_transcript: bool
    has_extraction: bool
    has_processed_audio: bool = False
    last_extraction_id: Optional[str]
    last_submission_id: Optional[str] = None  # For audio playback API
    status: str
    error_message: Optional[str] = None
    audio_quality: Optional[dict] = None
    chunk_count: int = 0  # Number of audio chunks (for abandoned RECORDING status)
    last_chunk_at: Optional[str] = None  # Timestamp of last chunk (to verify truly abandoned)
    is_merged: bool = False  # True for display-only merged extraction rows (no audio/reprocess)


class RecordingsListResponse(BaseModel):
    """Response model for list recordings"""
    recordings: List[RecordingInfo]
    total_count: int


class ReprocessRequest(BaseModel):
    """Request model for reprocessing a recording"""
    mode: str = Field(
        ...,
        description="Reprocess mode: 'new_extraction' (re-transcribe + extract) or 'reprocess_transcript' (extract only)"
    )
    template_code: str = Field(..., description="Template code to use for extraction")
    processing_mode: str = Field(default="default", description="Processing mode code")
    extraction_mode: str = Field(default="full", description="Extraction mode: 'core', 'additional', or 'full'")


class ReprocessResponse(BaseModel):
    """Response model for reprocess operation"""
    submission_id: str
    mode_used: str
    fallback_used: bool
    message: str


class AudioDataResponse(BaseModel):
    """Response model for audio retrieval"""
    submission_id: str
    session_id: str
    audio_data: str  # Base64 encoded audio
    mime_type: str
    size_bytes: int
    duration_seconds: Optional[float] = None
    transcript: Optional[str] = None  # Transcript text if available
    audio_source: Optional[str] = None  # Where audio was fetched from (db_column, temp_audio_bucket, stitched_N_chunks)


class ChunkInfo(BaseModel):
    """Single audio chunk metadata (excludes audio_data for lightweight response)"""
    id: str
    session_id: str
    chunk_index: int
    mime_type: Optional[str] = None
    duration_seconds: Optional[float] = None
    is_last: Optional[bool] = None
    created_at: Optional[str] = None


class SessionChunksResponse(BaseModel):
    """Response model for session audio chunks"""
    session_id: str
    chunk_count: int
    chunks: List[ChunkInfo]


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/doctor/{doctor_id}", response_model=RecordingsListResponse)
async def list_doctor_recordings(
    http_request: Request,
    doctor_id: uuid.UUID,
    patient_id: Optional[uuid.UUID] = Query(None, description="Filter by patient UUID"),
    patient_identifier: Optional[str] = Query(None, description="Filter by external patient ID (e.g., MRN)"),
    status: Optional[str] = Query("SUBMITTED", description="Filter by session status"),
    date_from: Optional[datetime] = Query(None, description="Filter recordings from this date (ISO format)"),
    date_to: Optional[datetime] = Query(None, description="Filter recordings until this date (ISO format)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    _auth = Depends(verify_doctor_access),
):
    """
    List recordings for a doctor with optional filters.

    Returns recordings with metadata about available data:
    - has_audio: True if full audio is stored (allows new_extraction)
    - has_transcript: True if transcript exists (allows reprocess_transcript)
    - has_extraction: True if extraction exists

    Date filters:
    - date_from: Filter recordings created on or after this date
    - date_to: Filter recordings created on or before this date
    """
    # Validate EHR client has access to this doctor
    await validate_doctor_from_path(http_request, str(doctor_id))

    try:
        result = list_recordings_for_doctor(
            doctor_id=doctor_id,
            patient_id=patient_id,
            patient_identifier=patient_identifier,
            status=status,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )

        return RecordingsListResponse(
            recordings=[RecordingInfo(**r) for r in result["recordings"]],
            total_count=result["total_count"]
        )

    except Exception as e:
        logger.error(f"[RECORDINGS] Failed to list recordings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.get("/nurse/{nurse_id}", response_model=RecordingsListResponse)
async def list_nurse_recordings(
    http_request: Request,
    nurse_id: uuid.UUID,
    patient_id: Optional[uuid.UUID] = Query(None, description="Filter by patient UUID"),
    patient_identifier: Optional[str] = Query(None, description="Filter by external patient ID (e.g., MRN)"),
    status: Optional[str] = Query("SUBMITTED", description="Filter by session status"),
    date_from: Optional[datetime] = Query(None, description="Filter recordings from this date (ISO format)"),
    date_to: Optional[datetime] = Query(None, description="Filter recordings until this date (ISO format)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    _auth = Depends(verify_doctor_access),
):
    """
    List recordings for a nurse with optional filters.
    Same structure as doctor recordings endpoint.
    """
    try:
        result = list_recordings_for_nurse(
            nurse_id=nurse_id,
            patient_id=patient_id,
            patient_identifier=patient_identifier,
            status=status,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )

        return RecordingsListResponse(
            recordings=[RecordingInfo(**r) for r in result["recordings"]],
            total_count=result["total_count"]
        )

    except Exception as e:
        logger.error(f"[RECORDINGS] Failed to list nurse recordings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.post("/{session_id}/reprocess", response_model=ReprocessResponse)
async def reprocess_recording_endpoint(
    http_request: Request,
    session_id: uuid.UUID,
    request: ReprocessRequest,
    _auth = Depends(verify_doctor_access),
):
    """
    Reprocess a recording with new template/settings.

    Two modes available:
    - **new_extraction**: Re-transcribe from stored audio + extract
      - Requires has_audio=true (or audio_chunks for abandoned recordings)
      - Full pipeline: transcribe → extract → triage → insights → webhook
    - **reprocess_transcript**: Use existing transcript, just re-extract
      - Requires has_transcript=true
      - Fast path: extract → triage → insights → webhook
      - Auto-fallback to new_extraction if no transcript found

    **Abandoned recordings** (status=RECORDING):
    - Only new_extraction mode is allowed (auto-forced if reprocess_transcript requested)
    - Audio chunks are stitched from audio_chunks table
    - Status updated to SUBMITTED after successful transcription

    The endpoint returns immediately with a submission_id. Use the processing_jobs
    table (via Supabase Realtime) to track progress.
    """
    # Auth: Look up session to get doctor_id and validate access
    if AUTH_ENABLED:
        session_result = supabase.table("recording_sessions").select("doctor_id").eq("id", str(session_id)).execute()
        if not session_result.data:
            raise HTTPException(status_code=404, detail="Recording session not found")
        doctor_id = session_result.data[0].get("doctor_id")
        if doctor_id:
            await validate_doctor_from_path(http_request, doctor_id)

    # Validate mode
    if request.mode not in ["new_extraction", "reprocess_transcript"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid mode. Use 'new_extraction' or 'reprocess_transcript'"
        )

    # Validate extraction_mode
    if request.extraction_mode not in ["core", "additional", "full"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid extraction_mode. Use 'core', 'additional', or 'full'"
        )

    try:
        result = await reprocess_recording(
            session_id=session_id,
            mode=request.mode,
            template_code=request.template_code,
            processing_mode=request.processing_mode,
            extraction_mode=request.extraction_mode,
        )

        return ReprocessResponse(**result)

    except ValueError as e:
        # Validation errors (session not found, template not found, no audio)
        logger.warning(f"[RECORDINGS] Reprocess validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"[RECORDINGS] Failed to reprocess recording: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.get("/audio/{submission_id}", response_model=AudioDataResponse)
async def get_recording_audio(
    http_request: Request,
    submission_id: uuid.UUID,
    audio_type: str = Query("original", description="'original' or 'processed'"),
    _auth = Depends(verify_doctor_access),
):
    """
    Retrieve the stitched audio data for a recording by submission ID.

    The submission_id is looked up in processing_jobs to find the associated
    session_id, then the audio is fetched with fallback chain:

    1. **DB Column**: Try `full_audio_data` from recording_sessions
    2. **Storage Bucket**: Try `full_audio_url` from temp-audio bucket
    3. **Chunk Stitching**: Stitch from audio_chunks table on-the-fly

    Each source is validated for corruption (magic bytes + minimum size).
    Returns the full audio as base64 encoded data along with its mime type.

    **Note**: This endpoint returns the full audio data which can be several MB.
    For very large files, consider the streaming endpoint.
    """
    try:
        # Look up session_id from processing_jobs using submission_id
        job_result = supabase.table("processing_jobs").select(
            "session_id"
        ).eq("submission_id", str(submission_id)).execute()

        if not job_result.data:
            raise HTTPException(
                status_code=404,
                detail="Processing job not found"
            )

        session_id = job_result.data[0]["session_id"]

        # Get session data including fallback sources
        result = supabase.table("recording_sessions").select(
            "id, doctor_id, full_audio_data, processed_audio_data, full_audio_url, full_audio_mime_type, full_audio_size_bytes, total_duration_seconds"
        ).eq("id", str(session_id)).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Recording session not found")

        session = result.data[0]

        # Validate EHR client has access to this doctor
        if AUTH_ENABLED:
            doctor_id = session.get("doctor_id")
            if doctor_id:
                await validate_doctor_from_path(http_request, doctor_id)

        # Fetch transcript for the session
        transcript = get_session_transcript(uuid.UUID(session_id))

        # Handle processed audio request
        if audio_type == "processed":
            processed_b64 = session.get("processed_audio_data")
            if not processed_b64:
                raise HTTPException(status_code=404, detail="No processed audio available")
            audio_bytes_raw = base64.b64decode(processed_b64)
            return AudioDataResponse(
                submission_id=str(submission_id),
                session_id=str(session["id"]),
                audio_data=processed_b64,
                mime_type=session.get("full_audio_mime_type") or "audio/webm",
                size_bytes=len(audio_bytes_raw),
                duration_seconds=float(session["total_duration_seconds"]) if session.get("total_duration_seconds") else None,
                transcript=transcript,
                audio_source="processed_audio",
            )

        # Fetch original audio with fallback chain (validates each source)
        audio_b64, mime_type, size_bytes, audio_source = await fetch_audio_with_fallback(
            session_id=session_id,
            session_data=session,
        )

        return AudioDataResponse(
            submission_id=str(submission_id),
            session_id=str(session["id"]),
            audio_data=audio_b64,
            mime_type=mime_type,
            size_bytes=size_bytes,
            duration_seconds=float(session["total_duration_seconds"]) if session.get("total_duration_seconds") else None,
            transcript=transcript,
            audio_source=audio_source,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RECORDINGS] Failed to get audio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.get("/audio/{submission_id}/stream")
async def stream_recording_audio(
    http_request: Request,
    submission_id: uuid.UUID,
    audio_type: str = Query("original", description="'original' or 'processed'"),
    _auth = Depends(verify_doctor_access),
):
    """
    Stream the audio data for a recording by submission ID.

    Returns the raw binary audio data directly as a streaming response.
    This endpoint is more efficient for playback as it avoids base64 encoding.

    Uses the same fallback chain as the base64 endpoint:
    1. **DB Column**: Try `full_audio_data` from recording_sessions
    2. **Storage Bucket**: Try `full_audio_url` from temp-audio bucket
    3. **Chunk Stitching**: Stitch from audio_chunks table on-the-fly

    The audio can be used directly as an <audio> src URL.
    """
    try:
        # Look up session_id from processing_jobs using submission_id
        job_result = supabase.table("processing_jobs").select(
            "session_id"
        ).eq("submission_id", str(submission_id)).execute()

        if not job_result.data:
            raise HTTPException(
                status_code=404,
                detail="Processing job not found"
            )

        session_id = job_result.data[0]["session_id"]

        # Get session data including fallback sources
        result = supabase.table("recording_sessions").select(
            "id, doctor_id, full_audio_data, processed_audio_data, full_audio_url, full_audio_mime_type, full_audio_size_bytes"
        ).eq("id", str(session_id)).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Recording session not found")

        session = result.data[0]

        # Validate EHR client has access to this doctor
        if AUTH_ENABLED:
            doctor_id = session.get("doctor_id")
            if doctor_id:
                await validate_doctor_from_path(http_request, doctor_id)

        # Handle processed audio request
        if audio_type == "processed":
            processed_b64 = session.get("processed_audio_data")
            if not processed_b64:
                raise HTTPException(status_code=404, detail="No processed audio available")
            audio_bytes = base64.b64decode(processed_b64)
            mime_type = session.get("full_audio_mime_type") or "audio/webm"
            simple_mime_type = mime_type.split(";")[0]
            ext_map = {"audio/webm": "webm", "audio/wav": "wav", "audio/mp3": "mp3", "audio/m4a": "m4a", "audio/mpeg": "mp3"}
            ext = ext_map.get(simple_mime_type, "webm")
            return Response(
                content=audio_bytes,
                media_type=simple_mime_type,
                headers={
                    "Content-Disposition": f'inline; filename="recording-{submission_id}-processed.{ext}"',
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(len(audio_bytes)),
                    "X-Audio-Source": "processed_audio",
                }
            )

        # Fetch original audio with fallback chain (validates each source)
        audio_b64, mime_type, size_bytes, audio_source = await fetch_audio_with_fallback(
            session_id=session_id,
            session_data=session,
        )

        # Decode base64 to binary for streaming
        audio_bytes = base64.b64decode(audio_b64)

        # Simplify MIME type - remove codec info which can cause browser issues
        simple_mime_type = mime_type.split(";")[0]

        # Determine file extension from mime type
        ext_map = {"audio/webm": "webm", "audio/wav": "wav", "audio/mp3": "mp3", "audio/m4a": "m4a", "audio/mpeg": "mp3"}
        ext = ext_map.get(simple_mime_type, "webm")

        logger.info(f"[RECORDINGS] Streaming audio from source: {audio_source}")

        # Return raw binary response
        return Response(
            content=audio_bytes,
            media_type=simple_mime_type,
            headers={
                "Content-Disposition": f'inline; filename="recording-{submission_id}.{ext}"',
                "Accept-Ranges": "bytes",
                "Content-Length": str(len(audio_bytes)),
                "X-Audio-Source": audio_source,  # Include source in header for debugging
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RECORDINGS] Failed to stream audio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.get("/{session_id}/chunks", response_model=SessionChunksResponse)
async def get_session_audio_chunks(
    http_request: Request,
    session_id: uuid.UUID,
    _auth=Depends(verify_doctor_access),
):
    """
    Get audio chunk metadata for a recording session.

    Returns chunk count and metadata (without audio_data) for chunks
    that remain in the audio_chunks table — useful when the frontend
    was disrupted and chunks were not cleaned up.
    """
    try:
        chunks = get_session_chunks(session_id)
        chunk_count = len(chunks)

        if chunk_count == 0:
            raise HTTPException(
                status_code=404,
                detail="No audio chunks found for this session"
            )

        chunk_list = [
            ChunkInfo(
                id=str(c["id"]),
                session_id=str(c["session_id"]),
                chunk_index=c["chunk_index"],
                mime_type=c.get("mime_type"),
                duration_seconds=c.get("duration_seconds"),
                is_last=c.get("is_last"),
                created_at=c.get("created_at"),
            )
            for c in chunks
        ]

        return SessionChunksResponse(
            session_id=str(session_id),
            chunk_count=chunk_count,
            chunks=chunk_list,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RECORDINGS] Failed to get session chunks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

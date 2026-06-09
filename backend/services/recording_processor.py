"""
Recording Processor Service with SSE Support

This service handles background processing of submitted recording sessions:
1. Stitches audio chunks into a single file
2. Transcribes the audio using Gemini
3. Extracts medical insights using the specified template
4. Streams progress updates via Server-Sent Events (SSE)

Usage:
    processor = RecordingProcessor(submission_id)
    async for progress_event in processor.process():
        # Send SSE event to frontend
        yield progress_event
"""

import base64
from services.b64_utils import b64decode_padded
import uuid
import time
import asyncio
import logging
import traceback
from typing import Dict, Any, AsyncGenerator, Optional, Callable
from datetime import datetime
from contextvars import ContextVar

logger = logging.getLogger(__name__)

from services.supabase_service import (
    get_job_by_submission_id,
    get_session_chunks,
    update_job_progress,
    update_job_error,
    supabase,
)
from services.audio_stitcher import (
    stitch_audio_chunks,
    stitch_audio_chunks_ffmpeg,
    validate_chunks,
    get_audio_duration_estimate,
)
from services.audio_storage_service import store_temp_audio_async, normalize_audio_mime_type
from services.gemini_service import transcribe_audio, extract_insights_from_audio_direct
from services.background_tasks import schedule_combined_emotion_extraction
from services.audio_quality_service import analyze_audio_quality
from services.audio_silence_remover import remove_silence_from_base64
# NOTE: Supabase Realtime is now handled directly in supabase_service.py
# via update_job_progress() which populates progress_json column.
# Frontend subscribes to processing_jobs table changes via WebSocket.


# ============================================================================
# Context Variable for Prompt Caching (Parallel Generation Optimization)
# ============================================================================

# Cache for dynamically generated prompts during transcription
# Automatically cleaned up when async context exits
_cached_prompt_artifacts: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    'cached_prompt_artifacts',
    default=None
)


# ============================================================================
# Async Audio Quality Check (Fire-and-Forget)
# ============================================================================

async def _run_audio_quality_check(
    session_id: uuid.UUID,
    original_audio_b64: str,
    processed_audio_b64: str,
    mime_type: str,
    silence_stats: Optional[dict] = None,
    known_duration_seconds: Optional[float] = None,
) -> None:
    """
    Run audio quality analysis on BOTH original and processed audio, store combined result.
    This runs in parallel with transcription - no latency impact.

    Args:
        session_id: Recording session UUID
        original_audio_b64: Base64-encoded original audio (before silence removal)
        processed_audio_b64: Base64-encoded processed audio (after silence removal, may be same)
        mime_type: Audio MIME type
        silence_stats: Silence removal stats dict (None if silence removal disabled)
    """
    try:
        from services.supabase_service import supabase

        # Run quality analysis on ORIGINAL audio (backward-compatible top-level keys)
        quality_result = await asyncio.to_thread(
            analyze_audio_quality, original_audio_b64, mime_type, known_duration_seconds
        )

        # If silence was actually removed, also analyze the processed audio
        if silence_stats and silence_stats.get("removed") and original_audio_b64 != processed_audio_b64:
            try:
                processed_quality = await asyncio.to_thread(
                    analyze_audio_quality, processed_audio_b64, mime_type, known_duration_seconds
                )
                # Nest processed metrics under dedicated keys
                quality_result["processed_metrics"] = processed_quality.get("metrics", {})
                quality_result["processed_quality"] = processed_quality.get("overall_quality", "unknown")
            except Exception as e:
                logger.warning(f"[QUALITY] Processed audio analysis failed (non-fatal): {e}")

        # Add silence removal stats if available
        if silence_stats:
            quality_result["silence_removal"] = silence_stats

        # Store quality result and duration in recording_sessions table
        # Use ORIGINAL audio duration (reflects actual recording length)
        update_data = {"audio_quality_json": quality_result}
        duration = quality_result.get('metrics', {}).get('duration_seconds')
        # If the decoder still returned an implausibly short duration (streaming
        # WebM where pydub only decoded the header-bearing chunk), prefer the
        # caller-provided chunk-derived duration so total_duration_seconds is
        # never written as ~0 for a multi-MB recording.
        if (not duration or duration < 1.0) and known_duration_seconds and known_duration_seconds > 0:
            duration = float(known_duration_seconds)
            quality_result.setdefault('metrics', {})['duration_seconds'] = duration
            update_data["audio_quality_json"] = quality_result
        if duration and duration > 0:
            update_data["total_duration_seconds"] = round(duration, 2)

        supabase.table("recording_sessions")\
            .update(update_data)\
            .eq("id", str(session_id))\
            .execute()

        overall_quality = quality_result.get('overall_quality', 'unknown')
        snr_db = quality_result.get('metrics', {}).get('snr_db')
        duration = quality_result.get('metrics', {}).get('duration_seconds')

        logger.debug(
            f"[QUALITY] Session {session_id}: {overall_quality}, "
            f"SNR: {snr_db:.1f}dB, Duration: {duration:.1f}s"
            if snr_db and duration else
            f"[QUALITY] Session {session_id}: {overall_quality}"
        )
    except Exception as e:
        logger.error(f"[QUALITY] Failed for session {session_id}: {e}")


# ============================================================================
# Progress Event Types
# ============================================================================

class ProgressEvent:
    """Base class for progress events sent via SSE"""

    def __init__(self, event_type: str, data: Dict[str, Any]):
        self.event_type = event_type
        self.data = data
        self.timestamp = datetime.utcnow().isoformat()

    def to_sse_format(self) -> str:
        """Convert to SSE format: event: <type>\ndata: <json>\n\n"""
        import json
        return f"event: {self.event_type}\ndata: {json.dumps(self.data)}\n\n"


# ============================================================================
# Recording Processor Class
# ============================================================================

class RecordingProcessor:
    """
    Processes submitted recording sessions in the background.
    Streams progress updates via Server-Sent Events.
    """

    def __init__(
        self,
        submission_id: uuid.UUID,
        progress_callback: Optional[Callable] = None,
        session_id: Optional[uuid.UUID] = None,
        session_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the processor.

        Args:
            submission_id: The submission ID of the job to process
            progress_callback: Optional callback for progress updates (for testing)
            session_id: Optional session UUID (avoids DB query if provided)
            session_data: Optional session data dict (avoids DB query if provided)
        """
        self.submission_id = submission_id
        self.progress_callback = progress_callback

        # Pre-passed session data (optimization: avoids DB queries)
        self._passed_session_id = session_id
        self._passed_session_data = session_data

        # Timing metrics
        self.start_time: Optional[float] = None
        self.stitching_time: Optional[float] = None
        self.transcription_time: Optional[float] = None
        self.extraction_time: Optional[float] = None

        # Audio quality (pre-fetched before extraction for webhook/complete event)
        self._audio_quality: Optional[Dict[str, Any]] = None

        # Track last progress for error reporting
        self._last_progress: int = 0
        self._last_status: str = "PENDING"

    async def process(self) -> AsyncGenerator[ProgressEvent, None]:
        """
        Main processing pipeline. Yields progress events via SSE.

        Yields:
            ProgressEvent objects for each processing stage

        Raises:
            Exception: Any processing errors are caught and sent as error events
        """
        self.start_time = time.time()

        try:
            # Emit initial event
            self._last_progress = 0
            self._last_status = "PENDING"
            yield ProgressEvent("progress", {
                "status": "PENDING",
                "progress": 0,
                "message": "Starting processing...",
            })

            # Step 1: Load job and session data
            self._last_progress = 5
            self._last_status = "LOADING"
            yield ProgressEvent("progress", {
                "status": "LOADING",
                "progress": 5,
                "message": "Loading session data...",
            })

            # ============================================================================
            # OPTIMIZATION: Use passed session data if available, skip DB queries
            # ============================================================================
            if self._passed_session_data and self._passed_session_id:
                # Fast path: Use pre-passed session data (no DB queries)
                session = self._passed_session_data
                session_id = self._passed_session_id
                logger.debug(f"[PROCESSOR] Using passed session data (no DB query)")
            else:
                # Fallback: Query from DB (for retries, server restart, SSE reconnect, etc.)
                logger.debug(f"[PROCESSOR] Session data not passed, falling back to DB query")
                job = await asyncio.to_thread(get_job_by_submission_id, self.submission_id)
                if not job:
                    raise ValueError(f"Job not found for submission_id: {self.submission_id}")

                session_id = uuid.UUID(job["session_id"])

                # Get session info from job
                from services.supabase_service import supabase
                session_response = supabase.table("recording_sessions").select("*").eq("id", str(session_id)).execute()
                if not session_response.data:
                    raise ValueError(f"Session not found: {session_id}")

                session = session_response.data[0]

            # Store session for later use (avoid re-querying in _extract_insights)
            self._session = session
            self._session_id = session_id

            # Safety net: If validation still pending, wait for background task (race condition: file uploads)
            if session.get('validation_status') == 'pending':
                logger.debug(f"[PROCESSOR] Session validation pending, waiting for background task...")
                from services.supabase_service import supabase as _supa
                for attempt in range(6):  # max 3s (6 x 500ms)
                    await asyncio.sleep(0.5)
                    refreshed = _supa.table("recording_sessions").select("*").eq("id", str(session_id)).execute()
                    if refreshed.data and refreshed.data[0].get('validation_status', 'pending') != 'pending':
                        session = refreshed.data[0]
                        self._session = session
                        logger.debug(f"[PROCESSOR] Session validation completed after {(attempt+1)*500}ms")
                        break
                else:
                    logger.warning(f"[PROCESSOR] Session validation still pending after 3s, proceeding with defaults")

            if session.get('validation_status') == 'failed':
                error_msg = (session.get('session_context_json') or {}).get('validation_error', 'Unknown')
                raise ValueError(f"Session validation failed: {error_msg}")

            # Read template system fields
            template_code = session.get("template_code")  # Use template_code for lookups
            template_name = session.get("template_name")  # Keep for display/logging
            transcription_model = session.get("transcription_model", "gemini-2.5-flash")
            extraction_model = session.get("extraction_model", "gemini-2.5-flash")

            # Step 2: Retrieve audio chunks
            yield ProgressEvent("progress", {
                "status": "LOADING",
                "progress": 10,
                "message": "Retrieving audio chunks...",
            })

            # ============================================================================
            # OPTIMIZATION: Try in-memory store first, fall back to DB
            # In-memory is ~0ms vs DB which is ~500ms
            # SAFETY: Validate chunk count matches expected to prevent data loss
            # ============================================================================
            from services.chunk_memory_store import get_chunks_sorted, clear_session

            chunk_fetch_start = time.time()

            # Get expected chunk count from session (set during final chunk upload)
            expected_chunk_count = session.get("total_chunks")

            # Try in-memory first (populated by upload_chunk endpoint)
            chunks = get_chunks_sorted(str(session_id))
            use_memory_chunks = False

            if chunks:
                memory_chunk_count = len(chunks)

                # Validate chunk count matches expected (if known)
                # This catches cases where TTL cleanup deleted early chunks
                if expected_chunk_count and memory_chunk_count != expected_chunk_count:
                    logger.warning(
                        f"[CHUNK_VALIDATION] Memory chunk count mismatch! "
                        f"Expected {expected_chunk_count}, got {memory_chunk_count}. "
                        f"Falling back to DB to recover missing chunks."
                    )
                    # Fall through to DB fallback
                else:
                    # Also verify chunk 0 exists (required for WebM EBML header)
                    chunk_indices = [c.get('chunk_index', -1) for c in chunks]
                    if 0 not in chunk_indices:
                        logger.warning(
                            f"[CHUNK_VALIDATION] Chunk 0 missing from memory! "
                            f"This would cause invalid WebM (no EBML header). "
                            f"Falling back to DB."
                        )
                        # Fall through to DB fallback
                    else:
                        use_memory_chunks = True
                        chunk_fetch_time = time.time() - chunk_fetch_start
                        total_chunk_size = sum(len(c.get('audio_data', '')) for c in chunks)
                        total_chunk_size_mb = total_chunk_size / (1024 * 1024)
                        logger.info(
                            f"[TIMING_CHUNK] Using in-memory chunks: {chunk_fetch_time:.3f}s "
                            f"({len(chunks)} chunks, {total_chunk_size_mb:.2f} MB)"
                        )

            if not use_memory_chunks:
                # Fallback to DB (server restart, multi-instance, memory TTL expiry, etc.)
                if chunks:
                    logger.debug("[CHUNK_FALLBACK] Memory chunks incomplete, falling back to DB")
                else:
                    logger.debug("[CHUNK_FALLBACK] Memory store empty, falling back to DB")
                chunks = await asyncio.to_thread(get_session_chunks, session_id)
                chunk_fetch_time = time.time() - chunk_fetch_start

                if not chunks:
                    raise ValueError(f"No audio chunks found for session: {session_id}")

                # Calculate total chunk data size
                total_chunk_size = sum(len(c.get('audio_data', '')) for c in chunks)
                total_chunk_size_mb = total_chunk_size / (1024 * 1024)
                logger.info(
                    f"[TIMING_CHUNK] Retrieved {len(chunks)} chunks from DB (fallback): "
                    f"{chunk_fetch_time:.3f}s ({total_chunk_size_mb:.2f} MB)"
                )

            # Validate chunks (auto-reindexes if there are gaps/duplicates)
            validation = validate_chunks(chunks)
            if not validation["valid"]:
                raise ValueError(f"Invalid chunks: {validation['errors']}")

            # Log warnings (e.g., if chunks were reindexed due to race condition)
            if validation.get("warnings"):
                for warning in validation["warnings"]:
                    logger.warning(f"[CHUNK_VALIDATION] {warning}")
            if validation.get("reindexed"):
                logger.debug(f"[CHUNK_VALIDATION] Chunks were auto-reindexed by timestamp order")

            # Fire-and-forget language detection on the first ~2 chunks (~20s).
            # Runs in parallel with stitching + transcription; result sets
            # self._detected_language and persists to students.preferred_language
            # by the time the webhook metadata is built. Zero latency impact.
            try:
                preview_chunks = chunks[: min(2, len(chunks))]
                preview_bytes = b"".join(
                    b64decode_padded(c.get("audio_data", "")) for c in preview_chunks
                )
                if preview_bytes:
                    _patient_id_for_lang = session.get("student_id")
                    _doctor_id_for_lang = session.get("counsellor_id")
                    _sid_for_lang = str(session_id)

                    async def _detect_language_bg(
                        audio=preview_bytes,
                        mime=session.get("full_audio_mime_type") or "audio/webm",
                        sid=_sid_for_lang,
                        did=_doctor_id_for_lang,
                        pid=_patient_id_for_lang,
                    ):
                        try:
                            from services.gemini_service import detect_language_from_audio
                            lang = await detect_language_from_audio(
                                audio_content=audio,
                                mime_type=mime,
                                session_id=sid,
                                counsellor_id=did,
                            )
                            if lang:
                                self._detected_language = lang
                                if pid:
                                    from services.supabase_service import update_student_preferred_language
                                    await asyncio.to_thread(
                                        update_student_preferred_language, pid, lang
                                    )
                        except Exception as e:
                            logger.warning(f"[LANG_DETECT] Background detection failed: {e}")

                    asyncio.create_task(_detect_language_bg())
            except Exception as e:
                logger.warning(f"[LANG_DETECT] Failed to schedule detection: {e}")

            # NOTE: estimated_duration is calculated from audio bytes after stitching (below)
            # Chunk metadata duration is unreliable (frontend may not send it)
            estimated_duration = 0.0

            # Step 3: Stitch audio chunks
            self._last_progress = 20
            self._last_status = "STITCHING"
            yield ProgressEvent("progress", {
                "status": "STITCHING",
                "progress": 20,
                "message": f"Stitching {len(chunks)} audio chunks...",
                "chunk_count": len(chunks),
                "estimated_duration": estimated_duration,
            })

            await asyncio.to_thread(
                update_job_progress,
                self.submission_id,
                "STITCHING",
                20,
                f"Stitching {len(chunks)} chunks",
            )

            # ============================================================================
            # CHECK: School Config (uses infinite TTL cache)
            # Derive school_id from counsellor_id since recording_sessions doesn't store it
            # ============================================================================
            from services.supabase_service import get_school_settings_cached, get_counsellor_school_id_cached
            counsellor_id_str = session.get("counsellor_id")
            school_id = get_counsellor_school_id_cached(counsellor_id_str) if counsellor_id_str else None
            school_config = get_school_settings_cached(str(school_id)) if school_id else {}
            logger.debug(f"[PROCESSOR] School config: counsellor={counsellor_id_str[:8] if counsellor_id_str else 'N/A'}... -> school={str(school_id)[:8] if school_id else 'N/A'}... enable_audio_validation={school_config.get('enable_audio_validation', True)}")
            use_ffmpeg = school_config.get("use_ffmpeg_stitching", False)

            stitch_start = time.time()
            if use_ffmpeg:
                logger.debug(f"[PROCESSOR] Using FFmpeg stitching for school {school_id}")
                stitched_audio_b64, mime_type = stitch_audio_chunks_ffmpeg(chunks)
            else:
                stitched_audio_b64, mime_type = stitch_audio_chunks(chunks)
            self.stitching_time = time.time() - stitch_start
            logger.info(f"[TIMING_STITCH] Audio stitching: {self.stitching_time:.3f}s ({len(chunks)} chunks, ffmpeg={use_ffmpeg})")

            # Normalize MIME type for Gemini API compatibility (e.g., audio/x-m4a -> audio/m4a)
            original_mime = mime_type
            mime_type = normalize_audio_mime_type(mime_type)
            if mime_type != original_mime:
                logger.debug(f"[PROCESSOR] Normalized MIME type: {original_mime} -> {mime_type}")

            # Check early if segment pipeline is active (skips silence removal entirely)
            from services.segment_transcription_store import has_segments as _has_segments_early
            _will_use_segment_pipeline = _has_segments_early(str(session_id))

            # ============================================================================
            # SILENCE REMOVAL: Strip silent segments to reduce transcription time & cost
            # Controlled by school config. Default: enabled with -57 dBFS threshold.
            # Skipped entirely for segment pipeline — segments use raw chunks that
            # lack proper audio container headers (ffmpeg can't decode them), and
            # emotion analysis needs original audio (silence is emotional data).
            # ============================================================================
            enable_silence_removal = school_config.get("enable_silence_removal", True)
            original_audio_b64 = stitched_audio_b64  # Keep reference for dual quality comparison
            silence_stats = {}

            if _will_use_segment_pipeline:
                # SEGMENT PIPELINE: Skip silence removal entirely.
                # - Can't run per-segment: raw chunk bytes lack audio container headers
                # - Don't need full-stitch: transcription uses segment transcripts,
                #   emotion analysis needs original audio (silence = emotional data)
                logger.info("[SEGMENT_PIPELINE] Skipping silence removal (segment pipeline active)")
                enable_silence_removal = False
                silence_stats = {"removed": False, "reason": "segment pipeline active"}

            if enable_silence_removal:
                # Duration-based early exit: skip silence removal for short audio
                from services.audio_silence_remover import MIN_DURATION_FOR_SILENCE_REMOVAL_MS
                min_duration_s = MIN_DURATION_FOR_SILENCE_REMOVAL_MS / 1000
                if estimated_duration < min_duration_s:
                    logger.info(
                        f"[SILENCE_REMOVAL] Skipping: audio duration {estimated_duration:.0f}s "
                        f"below {min_duration_s:.0f}s threshold"
                    )
                    enable_silence_removal = False
                    silence_stats = {
                        "removed": False,
                        "reason": f"duration {estimated_duration:.0f}s below {min_duration_s:.0f}s threshold",
                    }

            if enable_silence_removal:
                silence_thresh = school_config.get("silence_thresh_dbfs", -60)
                min_silence_len = school_config.get("min_silence_len_ms", 5000)
                silence_padding = school_config.get("silence_padding_ms", 200)

                silence_start = time.time()
                stitched_audio_b64, mime_type, silence_stats = await asyncio.to_thread(
                    remove_silence_from_base64,
                    stitched_audio_b64, mime_type,
                    silence_thresh_dbfs=silence_thresh,
                    min_silence_len_ms=min_silence_len,
                    padding_ms=silence_padding,
                )
                self.silence_removal_time = time.time() - silence_start

                if silence_stats.get("removed"):
                    logger.info(
                        f"[TIMING_SILENCE] Silence removal: {self.silence_removal_time:.3f}s, "
                        f"removed {silence_stats['silence_removed_pct']}% "
                        f"({silence_stats['original_duration_ms']}ms -> {silence_stats['new_duration_ms']}ms)"
                    )
                else:
                    logger.debug(
                        f"[TIMING_SILENCE] Silence removal skipped: {silence_stats.get('reason', 'unknown')} "
                        f"({self.silence_removal_time:.3f}s)"
                    )

            # ============================================================================
            # EARLY ABORT: All-silent or too-short-after-removal recordings
            # Catches before Gemini API call to save cost
            # ============================================================================
            if enable_silence_removal and silence_stats.get("all_silent"):
                raise ValueError(
                    "Audio validation failed: Recording appears to be entirely silent. "
                    f"No speech detected in {silence_stats.get('original_duration_ms', 0) / 1000:.0f}s of audio. "
                    "Please check microphone permissions and try again."
                )

            if enable_silence_removal and silence_stats.get("too_short_after_removal"):
                raise ValueError(
                    "Audio validation failed: After removing silence, only "
                    f"{silence_stats.get('would_be_duration_ms', 0) / 1000:.1f}s of speech detected "
                    f"(minimum: 10s). Recording does not contain enough speech to process."
                )

            # ============================================================================
            # ASYNC TEMP STORAGE: Store stitched audio for 24-hour debugging access
            # Fire-and-forget normally, but awaited on validation failure for debugging
            # ============================================================================
            self._temp_storage_task = asyncio.create_task(store_temp_audio_async(
                audio_data_b64=stitched_audio_b64,
                session_id=str(session_id),
                mime_type=mime_type
            ))
            logger.debug(f"[PROCESSOR] Started async temp audio storage for session {session_id}")

            # Set full_audio_mime_type early so audio playback works even if extraction fails
            try:
                from services.supabase_service import supabase
                supabase.table("recording_sessions")\
                    .update({"full_audio_mime_type": mime_type})\
                    .eq("id", str(session_id))\
                    .execute()
            except Exception as e:
                logger.warning(f"[PROCESSOR] Failed to set early full_audio_mime_type: {e}")

            # NOTE: Recording duration is now saved by the audio quality check task above
            # (uses actual audio duration from quality analysis, not chunk metadata estimates)

            # NOTE: Memory clear moved to AFTER verified DB save (Step 7)
            # This ensures we don't lose chunks if DB save fails

            yield ProgressEvent("progress", {
                "status": "STITCHING",
                "progress": 30,
                "message": "Audio chunks stitched successfully",
                "stitching_time": round(self.stitching_time, 2),
            })

            # ============================================================================
            # PRE-TRANSCRIPTION VALIDATION: Block tiny/empty audio files
            # This catches corrupted recordings BEFORE wasting Gemini API costs
            # 2KB minimum - even 1 second of low-quality audio is ~4KB
            # This would have caught the 332-byte empty MP3 headers from Ganga school
            # ============================================================================
            MIN_AUDIO_SIZE_BYTES = 2000  # 2KB minimum

            # Decode audio once for validation (will be reused later)
            stitched_audio_bytes = base64.b64decode(stitched_audio_b64)
            audio_size_bytes = len(stitched_audio_bytes)

            if audio_size_bytes < MIN_AUDIO_SIZE_BYTES:
                raise ValueError(
                    f"Audio validation failed: File too small ({audio_size_bytes} bytes). "
                    f"Minimum required: {MIN_AUDIO_SIZE_BYTES} bytes (~2KB). "
                    f"Recording appears to be empty or corrupted. "
                    f"Please check microphone permissions and try again."
                )

            # Container-decodability gate. Catches the chunked-WebM corruption case
            # where bytes look big but the container only decodes ~0 seconds (e.g.
            # session 9b32f2da: 28MB / 0.04s). Without this, Gemini emits an opaque
            # 400 INVALID_ARGUMENT after a 5s wasted call.
            from services.audio_quality_service import (
                fast_container_duration_seconds,
                PROBE_PARSEABLE_NO_DURATION,
            )
            CONTAINER_PROBE_MIN_BYTES = 100_000
            CONTAINER_PROBE_MIN_DURATION = 1.0  # seconds

            if audio_size_bytes >= CONTAINER_PROBE_MIN_BYTES:
                decoded_dur = await asyncio.to_thread(
                    fast_container_duration_seconds, stitched_audio_bytes, mime_type
                )
                # Only trip the corruption gate when ffprobe gave us a real
                # (positive) duration that is implausibly short. The
                # PROBE_PARSEABLE_NO_DURATION sentinel (< 0) means the container
                # is parseable but lacks duration metadata — common with
                # MediaRecorder WebM, NOT a corruption signal.
                if decoded_dur is not None and 0.0 <= decoded_dur < CONTAINER_PROBE_MIN_DURATION:
                    raise ValueError(
                        f"Audio container is corrupted: "
                        f"{audio_size_bytes / 1024 / 1024:.1f}MB file decodes to only "
                        f"{decoded_dur:.2f}s. The recording chunks did not merge into a "
                        f"valid audio stream — please re-record."
                    )
                if decoded_dur is None:
                    logger.warning(
                        f"[VALIDATION] ffprobe could not parse "
                        f"{audio_size_bytes // 1024}KB file ({mime_type}). Proceeding "
                        f"to Gemini, but expect possible INVALID_ARGUMENT."
                    )

            logger.debug(f"[VALIDATION] Audio size OK: {audio_size_bytes} bytes (min: {MIN_AUDIO_SIZE_BYTES})")

            # Estimate duration from decoded audio size (~16KB/s for compressed audio)
            estimated_duration = audio_size_bytes / 16000
            logger.debug(f"[VALIDATION] Estimated audio duration: {estimated_duration:.1f}s (from {audio_size_bytes} bytes)")

            # ⭐ ASYNC AUDIO QUALITY CHECK (fire-and-forget, runs in parallel with transcription)
            # Analyzes BOTH original and processed audio quality when silence removal is active
            # This has ZERO latency impact on the transcription/extraction pipeline
            # Chunk-derived duration is the streaming-WebM fallback when pydub
            # decode under-reports duration (only the first chunk has the EBML
            # header, so a concatenated stream often decodes as <1s).
            # Use the in-memory chunk list as the authoritative source for the
            # count: the upload_chunk endpoint writes total_chunks to the DB
            # fire-and-forget and then passes the *pre-update* session dict to
            # the processor, so session.get("total_chunks") is often None here.
            try:
                _chunk_dur = float(session.get("chunk_duration_seconds") or 0)
                _total_chunks = len(chunks) if chunks else int(session.get("total_chunks") or 0)
                _chunk_known_duration = (
                    _chunk_dur * _total_chunks if _chunk_dur > 0 and _total_chunks > 0 else None
                )
            except (TypeError, ValueError):
                _chunk_known_duration = None
            quality_check_task = asyncio.create_task(
                _run_audio_quality_check(
                    session_id,
                    original_audio_b64,       # Original (before silence removal)
                    stitched_audio_b64,        # Processed (after silence removal, may be same)
                    mime_type,
                    silence_stats if enable_silence_removal else None,
                    _chunk_known_duration,
                )
            )
            # Store task reference to prevent garbage collection (but don't await)
            self._quality_check_task = quality_check_task
            logger.debug(f"[QUALITY] Launched async audio quality check for session {session_id}")

            # ============================================================================
            # CHECK: Skip Transcription Mode (Direct Audio Extraction)
            # ============================================================================
            consultation_type_id = session.get("consultation_type_id")
            skip_transcription = False

            if consultation_type_id:
                from services.supabase_service import get_consultation_type_by_id_cached
                ct_data = get_consultation_type_by_id_cached(uuid.UUID(consultation_type_id))
                if ct_data:
                    skip_transcription = ct_data.get("skip_transcription", False)

            if skip_transcription:
                # ============================================================================
                # DIRECT AUDIO EXTRACTION PATH (skip transcription)
                # Includes all 5 prompt injections (same as normal pipeline):
                # 1. Medicine list, 2. Investigation list, 3. Caution/Warnings,
                # 4. Past prescriptions, 5. Past summaries
                # ============================================================================
                logger.info(f"[TIMING_SKIP_TRANSCRIPTION] Direct audio extraction mode enabled")

                yield ProgressEvent("progress", {
                    "status": "EXTRACTING",
                    "progress": 40,
                    "message": "Extracting insights directly from audio (no transcription)...",
                })

                await asyncio.to_thread(
                    update_job_progress,
                    self.submission_id,
                    "EXTRACTING",
                    40,
                    "Direct audio extraction (no transcription)",
                )

                # Decode audio bytes
                audio_bytes = stitched_audio_bytes  # Already decoded during validation

                # Get pre-assembled prompt and schema from template
                from services.supabase_service import get_template_assembled_data
                template_data = get_template_assembled_data(template_code)

                if not template_data:
                    raise ValueError(f"Template {template_code} not found or missing assembled data for direct audio extraction")

                extract_start = time.time()
                counsellor_id = session.get("counsellor_id")
                student_id = session.get("student_id")

                # Check list availability (same as normal pipeline)
                list_availability = {"has_medicine_list": False, "has_investigation_list": False}
                if counsellor_id:
                    try:
                        from services.extraction_service import check_list_availability_parallel
                        counsellor_uuid = uuid.UUID(counsellor_id) if isinstance(counsellor_id, str) else counsellor_id
                        list_availability = await check_list_availability_parallel(counsellor_uuid)
                        logger.debug(
                            f"[SKIP_TRANSCRIPTION] List availability: medicine={list_availability.get('has_medicine_list')}, "
                            f"investigation={list_availability.get('has_investigation_list')}"
                        )
                    except Exception as e:
                        logger.warning(f"[SKIP_TRANSCRIPTION] Failed to check list availability: {e}")

                insights_result = await extract_insights_from_audio_direct(
                    audio_content=audio_bytes,
                    mime_type=mime_type,
                    system_prompt=template_data['assembled_full_prompt'],
                    response_schema=template_data['assembled_schema_json'],
                    model=extraction_model,
                    session_id=str(session_id),
                    counsellor_id=counsellor_id,
                    student_id=student_id,
                    has_medicine_list=list_availability.get("has_medicine_list", False),
                    has_investigation_list=list_availability.get("has_investigation_list", False),
                    audio_duration_seconds=estimated_duration,
                    template_code=template_code,
                )

                insights = insights_result.get("data", {})
                transcript = None  # No transcription in this mode
                self.transcription_time = 0
                self.extraction_time = time.time() - extract_start

                logger.info(
                    f"[TIMING_SKIP_TRANSCRIPTION] Direct extraction completed: "
                    f"{self.extraction_time:.2f}s (model: {extraction_model})"
                )

                # Generate extraction_id for DB save (needed for post-processing)
                extraction_id = uuid.uuid4()

                # ============================================================================
                # POST-PROCESSING: Medicine and Investigation matching (same as normal pipeline)
                # ============================================================================
                counsellor_uuid = uuid.UUID(counsellor_id) if counsellor_id and isinstance(counsellor_id, str) else counsellor_id

                # Medicine post-processing
                if counsellor_uuid and isinstance(insights, dict) and list_availability.get("has_medicine_list"):
                    try:
                        postprocess_start = time.time()
                        from services.medicine_service import postprocess_prescription_extraction

                        # Get diagnosis for context
                        diagnosis = ""
                        if 'diagnosis' in insights:
                            diag_val = insights['diagnosis']
                            if isinstance(diag_val, dict):
                                diagnosis = diag_val.get('data', str(diag_val))
                            else:
                                diagnosis = str(diag_val) if diag_val else ""

                        logger.debug(f"[SKIP_TRANSCRIPTION] Running medicine post-processing")
                        insights = await postprocess_prescription_extraction(
                            extraction_data=insights,
                            counsellor_id=counsellor_uuid,
                            extraction_id=extraction_id,
                            submission_id=str(self.submission_id) if self.submission_id else str(session_id),
                            diagnosis=diagnosis,
                            template_id=None,
                            log_matches=True
                        )
                        logger.info(f"[TIMING_POSTPROCESS] Medicine post-processing: {time.time() - postprocess_start:.3f}s")
                    except Exception as e:
                        logger.warning(f"[SKIP_TRANSCRIPTION] Medicine post-processing failed (non-fatal): {e}")

                # Investigation post-processing
                if counsellor_uuid and isinstance(insights, dict) and list_availability.get("has_investigation_list"):
                    try:
                        postprocess_start = time.time()
                        from services.investigation_service import postprocess_investigations_extraction

                        logger.debug(f"[SKIP_TRANSCRIPTION] Running investigation post-processing")
                        insights = await postprocess_investigations_extraction(
                            extraction_data=insights,
                            counsellor_id=counsellor_uuid,
                            extraction_id=extraction_id,
                            submission_id=str(self.submission_id) if self.submission_id else str(session_id),
                            template_id=None,
                            log_matches=True
                        )
                        logger.info(f"[TIMING_POSTPROCESS] Investigation post-processing: {time.time() - postprocess_start:.3f}s")
                    except Exception as e:
                        logger.warning(f"[SKIP_TRANSCRIPTION] Investigation post-processing failed (non-fatal): {e}")

                yield ProgressEvent("progress", {
                    "status": "EXTRACTING",
                    "progress": 90,
                    "message": "Insights extracted from audio",
                    "extraction_time": round(self.extraction_time, 2),
                })

                # Save extraction to database using existing columns
                from services.supabase_service import supabase
                extraction_record = {
                    "id": str(extraction_id),
                    "session_id": str(session_id),
                    "consultation_type_id": session.get("consultation_type_id"),
                    "counsellor_id": counsellor_id,
                    "student_id": student_id,
                    "transcript_text": None,  # No transcript in skip_transcription mode
                    "original_extraction_json": insights,
                    "model_used": extraction_model,  # Use existing column name
                    "extraction_mode": session.get("extraction_mode", "full"),
                    "segment_count": len(insights) if isinstance(insights, dict) else 0,
                    "submission_id": str(self.submission_id) if self.submission_id else None,
                    "stitching_time_seconds": self.stitching_time,
                    "transcription_time_seconds": 0,  # No transcription
                    "extraction_time_seconds": self.extraction_time,
                    "total_processing_time_seconds": self.stitching_time + self.extraction_time,
                }

                try:
                    await asyncio.to_thread(
                        lambda: supabase.table("extractions").insert(extraction_record).execute()
                    )
                except Exception as insert_err:
                    # FK constraint violation: processing_job may not exist yet
                    err_msg = str(insert_err).lower()
                    if self.submission_id and ("fkey" in err_msg or "foreign key" in err_msg or "409" in err_msg or "conflict" in err_msg or "23503" in err_msg):
                        logger.warning(
                            f"[SKIP_TRANSCRIPTION] ⚠️ FK violation — processing_job likely missing. "
                            f"Creating it now and retrying..."
                        )
                        from services.supabase_service import create_processing_job
                        await asyncio.to_thread(
                            create_processing_job,
                            session_id=session_id,
                            submission_id=self.submission_id,
                        )
                        await asyncio.to_thread(
                            lambda: supabase.table("extractions").insert(extraction_record).execute()
                        )
                    else:
                        raise
                logger.info(f"[TIMING_SKIP_TRANSCRIPTION] Saved extraction {extraction_id}")

                # ============================================================================
                # SCHEDULE BACKGROUND TASKS: Audio-only emotion + Triage (if enabled)
                # Note: Consultation insights requires transcript, so it's skipped
                # ============================================================================
                consultation_type_id = session.get("consultation_type_id")

                # Audio-only emotion extraction has been removed — the combined (text+audio)
                # path is the only emotion path, so skip_transcription mode produces no
                # emotion analysis.

                # Schedule TRIAGE generation (works without transcript - uses extraction JSON + RPC)
                if consultation_type_id:
                    try:
                        from services.background_tasks import schedule_triage_generation
                        from services.supabase_service import is_triage_analysis_enabled

                        if is_triage_analysis_enabled(uuid.UUID(consultation_type_id)):
                            logger.debug(f"[SKIP_TRANSCRIPTION] Scheduling triage generation (uses extraction JSON)")
                            await schedule_triage_generation(
                                extraction_id=extraction_id,
                                transcript=None,  # No transcript in skip_transcription mode
                                extraction_data={"original_extraction_json": insights},
                                counsellor_id=counsellor_id,
                                student_id=student_id,
                                consultation_type_code=template_code,
                                include_gemini=False,  # Rule-based only for speed
                                enable_consultation_insights=False,  # Requires transcript
                            )
                        else:
                            logger.debug(f"[SKIP_TRANSCRIPTION] Triage analysis disabled for this consultation type")
                    except Exception as e:
                        logger.warning(f"[SKIP_TRANSCRIPTION] Failed to schedule triage (non-fatal): {e}")

                # Consultation insights SKIPPED - requires transcript
                logger.debug(f"[SKIP_TRANSCRIPTION] Consultation insights skipped (requires transcript)")

                # Send webhook for skip_transcription success (if extraction_mode is 'full')
                extraction_mode = session.get("extraction_mode", "full")
                if extraction_mode == 'full':
                    try:
                        from services.webhook_service import send_insights_webhook
                        from services.realtime_publisher_service import is_realtime_enabled_for_school
                        from services.supabase_service import get_counsellor_school_id_cached

                        standardized_metadata = {
                            "correlation_id": session.get('correlation_id'),
                            "submission_id": str(self.submission_id) if self.submission_id else None,
                            "extraction_id": str(extraction_id),
                            "session_id": str(self._session_id) if self._session_id else None,
                            "counsellor_id": counsellor_id,
                            "student_id": student_id,
                            "template_code": template_code,
                            "mode": extraction_mode,
                            "segment_count": len(insights) if isinstance(insights, dict) else 0,
                            "processing_mode": session.get('processing_mode'),
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "audio_quality": self._audio_quality,
                            "preferred_language": getattr(self, '_detected_language', None),
                        }

                        _hospital_id = get_counsellor_school_id_cached(uuid.UUID(counsellor_id)) if counsellor_id else None
                        if _hospital_id and is_realtime_enabled_for_school(_hospital_id):
                            logger.debug(f"[SKIP_TRANSCRIPTION:WEBHOOK] Skipping webhook - realtime enabled")
                        else:
                            await send_insights_webhook(
                                insights=insights,
                                metadata=standardized_metadata,
                                source='recording',
                            )
                            logger.info(f"[SKIP_TRANSCRIPTION:WEBHOOK] Success webhook sent")
                    except Exception as webhook_err:
                        logger.warning(f"[SKIP_TRANSCRIPTION:WEBHOOK] Failed to send webhook: {webhook_err}")

            # ============================================================================
            # NORMAL PATH: Transcription + Extraction (only if NOT skip_transcription)
            # ============================================================================
            if not skip_transcription:
                # Step 4: Transcribe audio + Generate prompts in parallel (OPTIMIZATION)
                self._last_progress = 40
                self._last_status = "TRANSCRIBING"
                yield ProgressEvent("progress", {
                    "status": "TRANSCRIBING",
                    "progress": 40,
                    "message": "Transcribing audio and preparing extraction configuration...",
                })

                await asyncio.to_thread(
                    update_job_progress,
                    self.submission_id,
                    "TRANSCRIBING",
                    40,
                    "Transcribing audio",
                )

                transcribe_start = time.time()

                # Decode base64 audio to bytes
                audio_bytes = stitched_audio_bytes  # Already decoded during validation

                # Get counsellor_id for LLM usage tracking
                counsellor_id = session.get("counsellor_id")
                student_id = session.get("student_id")

                # Get template_id for background emotion prompts
                template_id_for_audio = None
                if template_code and counsellor_id:
                    from services.supabase_service import get_active_template_by_code_cached
                    template = get_active_template_by_code_cached(uuid.UUID(counsellor_id), template_code)
                    if template:
                        template_id_for_audio = str(template.get("id"))
                        logger.debug(f"[TRANSCRIPTION] Found template_id={template_id_for_audio} for template_code={template_code} (cached)")

                # ============================================================================
                # CHECK: Segment transcripts from progressive segmentation (long audio)
                # During live recording, segments are transcribed in the background as
                # cumulative duration crosses 15-min boundaries. If segments exist, we
                # only need to transcribe the final segment and combine.
                # ============================================================================
                from services.segment_transcription_store import (
                    get_all_transcripts_ordered,
                    get_segment_count,
                    get_completed_segment_count,
                    get_last_boundary_chunk_index,
                    get_pending_segments,
                    register_segment as _register_segment,
                    store_segment_transcript as _store_segment_transcript,
                    clear_session as clear_segment_session,
                    DEFAULT_OVERLAP_CHUNKS,
                )
                from services.transcript_combiner import combine_transcripts

                session_id_str = str(session_id)
                _use_segment_pipeline = _will_use_segment_pipeline

                if _use_segment_pipeline:
                    # ============================================================
                    # LONG AUDIO PATH: Progressive segment transcripts exist
                    # Only need to transcribe the final segment + combine all
                    # ============================================================
                    seg_count = get_segment_count(session_id_str)
                    completed = get_completed_segment_count(session_id_str)
                    logger.info(
                        f"[SEGMENT_PIPELINE] Found {seg_count} segments "
                        f"({completed} completed) for session {session_id_str[:8]}..."
                    )

                    yield ProgressEvent("progress", {
                        "status": "TRANSCRIBING",
                        "progress": 45,
                        "message": f"Transcribing final segment ({completed}/{seg_count} pre-transcribed)...",
                    })

                    # Start prompt generation in parallel
                    prompt_generation_task = asyncio.create_task(
                        self._generate_prompts_parallel(session)
                    )

                    # Transcribe the final segment (chunks after last boundary)
                    last_boundary = get_last_boundary_chunk_index(session_id_str)
                    if last_boundary >= 0 and chunks:
                        final_start = max(0, last_boundary - DEFAULT_OVERLAP_CHUNKS + 1)
                        final_end = max(c.get("chunk_index", 0) for c in chunks)
                        final_seg_idx = get_segment_count(session_id_str)
                        _register_segment(session_id_str, final_seg_idx, final_start, final_end)

                        from services.audio_splitter import stitch_and_get_bytes_for_chunk_range
                        final_audio_bytes, final_mime = stitch_and_get_bytes_for_chunk_range(
                            chunks, final_start, final_end
                        )
                        final_mime = normalize_audio_mime_type(final_mime)

                        final_transcript, final_language = await transcribe_audio(
                            audio_content=final_audio_bytes,
                            mime_type=final_mime,
                            model=transcription_model,
                            target_language="English",
                            session_id=str(session_id),
                            counsellor_id=counsellor_id,
                            audio_duration_seconds=len(final_audio_bytes) / 16000,
                        )
                        _store_segment_transcript(
                            session_id_str, final_seg_idx, final_transcript, final_language
                        )
                        detected_language = final_language
                    else:
                        detected_language = None

                    # Wait for any still-pending segment transcriptions
                    pending = get_pending_segments(session_id_str)
                    if pending:
                        logger.info(
                            f"[SEGMENT_PIPELINE] Waiting for {len(pending)} pending segments: {pending}"
                        )
                        import time as _time_mod
                        wait_start = _time_mod.time()
                        while get_pending_segments(session_id_str) and (_time_mod.time() - wait_start) < 120:
                            await asyncio.sleep(1)
                        still_pending = get_pending_segments(session_id_str)
                        if still_pending:
                            logger.warning(
                                f"[SEGMENT_PIPELINE] {len(still_pending)} segments still pending after 120s"
                            )

                    # Combine all transcripts
                    all_transcripts = get_all_transcripts_ordered(session_id_str)
                    transcript = combine_transcripts(all_transcripts)
                    # Do not overwrite self._detected_language with None — the separate
                    # detect_language_from_audio bg task may have already set it.
                    if detected_language:
                        self._detected_language = detected_language

                    logger.info(
                        f"[SEGMENT_PIPELINE] Combined {len(all_transcripts)} segment transcripts "
                        f"({len(transcript)} chars total)"
                    )
                    clear_segment_session(session_id_str)

                    # Wait for prompt generation
                    try:
                        prompt_artifacts = await prompt_generation_task
                        if prompt_artifacts:
                            _cached_prompt_artifacts.set(prompt_artifacts)
                    except ValueError as e:
                        raise
                    except Exception as e:
                        logger.warning(f"[OPTIMIZATION] Prompt generation failed: {e}")
                        _cached_prompt_artifacts.set(None)

                else:
                    # ============================================================
                    # NORMAL PATH: Single transcription (short recording)
                    # ============================================================
                    logger.debug("[TRANSCRIPTION] Using standard transcribe_audio()")
                    transcription_task = asyncio.create_task(
                        transcribe_audio(
                            audio_bytes,
                            mime_type,
                            model=transcription_model,
                            target_language="English",
                            session_id=str(session_id),
                            counsellor_id=counsellor_id,
                            audio_duration_seconds=estimated_duration,
                        )
                    )

                    # Generate prompts in parallel
                    prompt_generation_task = asyncio.create_task(
                        self._generate_prompts_parallel(session)
                    )

                    # Wait for both to complete
                    try:
                        transcription_result, prompt_artifacts = await asyncio.gather(
                            transcription_task,
                            prompt_generation_task
                        )

                        transcript, detected_language = transcription_result
                        # Do not overwrite self._detected_language with None — the separate
                        # detect_language_from_audio bg task may have already set it.
                        if detected_language:
                            self._detected_language = detected_language

                        if prompt_artifacts:
                            _cached_prompt_artifacts.set(prompt_artifacts)
                            logger.debug(f"[OPTIMIZATION] Prompts generated in parallel: {prompt_artifacts.get('segment_count', 0)} segments")

                    except ValueError as e:
                        logger.error(f"[OPTIMIZATION] Configuration error: {e}")
                        raise
                    except Exception as e:
                        logger.warning(f"[OPTIMIZATION] Parallel prompt generation failed: {e}")
                        transcription_result = await transcription_task
                        transcript, detected_language = transcription_result
                        if detected_language:
                            self._detected_language = detected_language
                        _cached_prompt_artifacts.set(None)

                self.transcription_time = time.time() - transcribe_start
                logger.info(f"[TIMING_TRANSCRIPTION_TOTAL] Full transcription wrapper: {self.transcription_time:.2f}s (includes setup + API + parsing)")

                # Fire-and-forget: persist transcript to processing_jobs.transcript so it survives
                # extraction failures. get_session_transcript() reads this column first.
                if transcript:
                    try:
                        asyncio.create_task(
                            asyncio.to_thread(
                                update_job_progress,
                                self.submission_id,
                                "TRANSCRIBING",
                                60,
                                "Transcription persisted",
                                transcript=transcript,
                            )
                        )
                    except Exception as e:
                        logger.warning(f"[TRANSCRIPT_PERSIST] Failed to schedule transcript save: {e}")

                # Store data for background emotion analysis
                self._template_id_for_audio = template_id_for_audio
                self._audio_bytes = audio_bytes
                self._audio_mime_type = mime_type

                # Language detection now handled by the separate detect_language_from_audio
                # fire-and-forget task scheduled right after chunk validation (above).
                # transcribe_audio no longer emits [DETECTED_LANG:...] tags, so
                # detected_language from that call is always None.

                prompt_info = _cached_prompt_artifacts.get()
                segment_info = f" | Prepared {prompt_info['segment_count']} segments" if prompt_info else ""

                yield ProgressEvent("progress", {
                    "status": "TRANSCRIBING",
                    "progress": 60,
                    "message": f"Transcription completed{segment_info}",
                    "transcription_time": round(self.transcription_time, 2),
                    "transcript_length": len(transcript),
                })

                # Step 5: Extract medical insights
                # Skip extraction if template_code is TRANSCRIPT_ONLY (for frontend progressive loading)
                extraction_id = None  # Initialize for TRANSCRIPT_ONLY case
                if template_code and template_code.upper() == "TRANSCRIPT_ONLY":
                    logger.info("[EXTRACTION] Skipping extraction - TRANSCRIPT_ONLY mode (frontend will extract)")
                    insights = None
                    self.extraction_time = 0

                    yield ProgressEvent("progress", {
                        "status": "TRANSCRIPTION_COMPLETE",
                        "progress": 90,
                        "message": "Transcription complete",
                    })
                else:
                    self._last_progress = 70
                    self._last_status = "EXTRACTING"
                    yield ProgressEvent("progress", {
                        "status": "EXTRACTING",
                        "progress": 70,
                        "message": "Extracting medical insights...",
                    })

                    await asyncio.to_thread(
                        update_job_progress,
                        self.submission_id,
                        "EXTRACTING",
                        70,
                        "Extracting insights",
                    )

                    # ============================================================================
                    # PARALLEL EMOTION ANALYSIS: Start emotion extraction before extraction
                    # This runs in parallel with extraction to reduce total latency
                    # ============================================================================
                    # Generate extraction_id early so emotion analysis can use the same ID
                    pre_generated_extraction_id = uuid.uuid4()
                    logger.debug(f"[PARALLEL_EMOTION] Generated extraction_id early: {pre_generated_extraction_id}")

                    # Check if emotion analysis is enabled for this consultation type
                    consultation_type_id_str = session.get("consultation_type_id")
                    enable_emotion = False
                    template_id_for_emotion = None

                    if consultation_type_id_str:
                        try:
                            from services.supabase_service import get_consultation_type_by_id_cached

                            consultation_type_uuid = uuid.UUID(consultation_type_id_str)
                            consultation_type_data = get_consultation_type_by_id_cached(consultation_type_uuid)
                            enable_emotion = consultation_type_data.get('enable_emotion_analysis', False) if consultation_type_data else False

                            if enable_emotion:
                                # Get template_id from session context or stored value
                                session_context = session.get('session_context_json', {}) or {}
                                template_id_for_emotion = session_context.get('template_id') or getattr(self, '_template_id_for_audio', None)

                                logger.debug(
                                    f"[PARALLEL_EMOTION] Emotion analysis enabled, using combined mode"
                                )

                                # Schedule COMBINED emotion extraction (single multimodal call)
                                # This replaces the old text_only/audio_only/both modes
                                if template_id_for_emotion:
                                    emotion_audio_content = getattr(self, '_audio_bytes', None)
                                    emotion_audio_mime_type = getattr(self, '_audio_mime_type', None)
                                    if emotion_audio_content:
                                        asyncio.create_task(
                                            schedule_combined_emotion_extraction(
                                                audio_content=emotion_audio_content,
                                                audio_mime_type=emotion_audio_mime_type,
                                                transcript=transcript,
                                                extraction_id=pre_generated_extraction_id,
                                                consultation_type_id=consultation_type_uuid,
                                                template_id=template_id_for_emotion,
                                                session_id=str(self._session_id),
                                                counsellor_id=session.get('counsellor_id'),
                                            )
                                        )
                                        logger.debug(
                                            f"[PARALLEL_EMOTION] Started COMBINED emotion analysis in background "
                                            f"(extraction_id={pre_generated_extraction_id}, {len(emotion_audio_content)} bytes)"
                                        )
                                    else:
                                        logger.warning(
                                            f"[PARALLEL_EMOTION] Emotion analysis requested but no audio data available"
                                        )
                                else:
                                    logger.warning(
                                        f"[PARALLEL_EMOTION] Emotion analysis requested but no template_id available"
                                    )
                        except Exception as e:
                            logger.warning(f"[PARALLEL_EMOTION] Failed to start parallel emotion: {e}")
                            # Continue with extraction - emotion failure is non-fatal

                    # ============================================================================
                    # PRE-FETCH: Get audio quality BEFORE extraction (for webhook, no re-fetch needed)
                    # Quality check runs async during transcription, should be done by now
                    # ============================================================================
                    self._audio_quality = None
                    try:
                        def _fetch_audio_quality(sid: str):
                            """Fetch audio quality from DB (runs in thread pool)."""
                            from services.supabase_service import supabase as sb
                            return sb.table("recording_sessions")\
                                .select("audio_quality_json")\
                                .eq("id", sid)\
                                .single()\
                                .execute()

                        quality_response = await asyncio.to_thread(
                            _fetch_audio_quality, str(session_id)
                        )
                        if quality_response.data:
                            self._audio_quality = quality_response.data.get("audio_quality_json")
                        logger.debug(f"[QUALITY] Pre-fetched audio quality: {self._audio_quality.get('overall_quality') if self._audio_quality else 'None'}")
                    except Exception as e:
                        logger.warning(f"[QUALITY] Could not pre-fetch audio quality: {e}")

                    # ============================================================================
                    # PRE-EXTRACTION VALIDATION: Block if audio quality is too poor
                    # This runs AFTER transcription (cost accepted) but BEFORE extraction
                    # Saves extraction cost (~$0.01-0.05) on clearly unusable audio
                    # NOTE: Only applies to main recording flow, NOT reprocess or /extract API
                    # school_config already loaded at stitching stage (from counsellor_id -> school_id)
                    # ============================================================================
                    enable_audio_validation = school_config.get("enable_audio_validation", True)

                    # Store config for later use in exception handler
                    self._hospital_config = school_config

                    if enable_audio_validation:
                        max_silence_ratio = school_config.get("max_silence_ratio", 0.90)
                        min_transcript_length = school_config.get("min_transcript_length", 20)

                        # Validation 1: Check transcript length
                        transcript_length = len(transcript.strip()) if transcript else 0
                        if transcript_length < min_transcript_length:
                            raise ValueError(
                                f"Transcription validation failed: Transcript too short ({transcript_length} chars). "
                                f"Audio may be empty, silent, or contain no speech. "
                                f"Minimum required: {min_transcript_length} chars."
                            )
                        logger.debug(f"[VALIDATION] Transcript length OK: {transcript_length} chars (min: {min_transcript_length})")

                        # Validation 1b: Check for Gemini error markers (anti-hallucination)
                        # These markers indicate Gemini detected empty/corrupted audio
                        transcript_upper = transcript.strip().upper() if transcript else ""
                        error_markers = ["[NO_SPEECH_DETECTED]"]
                        for marker in error_markers:
                            if marker in transcript_upper:
                                raise ValueError(
                                    f"Transcription validation failed: Gemini reported {marker}. "
                                    f"Audio appears to be empty, corrupted, or contains no speech. "
                                    f"Please check microphone and try again."
                                )

                        # Validation 1c: Check for known Gemini error responses
                        # These are phrases Gemini uses when it can't process audio
                        gemini_error_phrases = [
                            "i cannot process audio",
                            "i'm sorry, but i cannot",
                            "i am sorry, but i cannot",
                            "unable to process the audio",
                            "no audio content",
                            "audio file is empty",
                        ]
                        transcript_lower = transcript.strip().lower() if transcript else ""
                        for phrase in gemini_error_phrases:
                            if phrase in transcript_lower:
                                raise ValueError(
                                    f"Transcription validation failed: Gemini could not process audio. "
                                    f"Audio appears to be empty or corrupted. "
                                    f"Please check microphone permissions and try again."
                                )

                        # Validation 1d: Check for known hallucination patterns
                        # Gemini sometimes hallucinates "Dr. Smith" or "Mr. Smith" conversations
                        # when audio is empty/corrupted - this is from its training data
                        hallucination_patterns = [
                            "mr. smith",
                            "mr smith",
                            "dr. smith",
                            "dr smith",
                            "mrs. smith",
                            "mrs smith",
                        ]
                        for pattern in hallucination_patterns:
                            if pattern in transcript_lower:
                                raise ValueError(
                                    f"Transcription validation failed: Detected likely hallucination "
                                    f"('{pattern}' found in transcript). Audio may be empty or corrupted. "
                                    f"Please check microphone and try again."
                                )

                        # Validation 2: Individual audio metric checks (configurable per school)
                        # Use PROCESSED audio metrics when silence removal was active,
                        # since that's what gets sent to Gemini for transcription
                        if self._audio_quality:
                            metrics = self._audio_quality.get("metrics", {})
                            if self._audio_quality.get("processed_metrics"):
                                metrics = self._audio_quality["processed_metrics"]
                                logger.debug("[VALIDATION] Using processed audio metrics (post-silence-removal)")

                            # Trust check: when the local audio analyzer can't decode the
                            # stitched WebM it returns sentinel values (duration≈0, SNR=0).
                            # Gemini's decoder handles the same bytes fine, so if we just
                            # produced a valid transcript, the metrics are untrustworthy
                            # and must not gate the pipeline. The quality_json is still
                            # persisted for visibility.
                            measured_duration = float(metrics.get("duration_seconds") or 0)
                            metrics_untrustworthy = (
                                measured_duration < 1.0
                                and transcript_length >= min_transcript_length
                            )

                            if metrics_untrustworthy:
                                logger.warning(
                                    f"[VALIDATION] Audio quality metrics look untrustworthy — "
                                    f"analyzer reports duration={measured_duration:.3f}s but "
                                    f"transcript has {transcript_length} chars. Skipping "
                                    f"SNR/RMS/speech/silence gates to avoid blocking a good recording."
                                )
                            else:
                                # 2a: SNR check (background noise)
                                snr_db = metrics.get("snr_db", 0)
                                min_snr = school_config.get("min_snr_db", 10.0)
                                if snr_db < min_snr:
                                    raise ValueError(
                                        f"Audio blocked: High background noise detected. "
                                        f"SNR is {snr_db:.1f} dB (minimum required: {min_snr:.1f} dB). "
                                        f"Please re-record in a quieter environment."
                                    )

                                # 2b: RMS volume check (too quiet)
                                rms_db = metrics.get("rms_db", -60)
                                min_rms = school_config.get("min_rms_db", -57.0)
                                if rms_db < min_rms:
                                    raise ValueError(
                                        f"Audio blocked: Volume is too low. "
                                        f"RMS is {rms_db:.1f} dB (minimum required: {min_rms:.1f} dB). "
                                        f"Please speak louder or move closer to the microphone."
                                    )

                                # 2c: Speech detection check
                                # Skip if RMS is below -60 dB — speech threshold (~-30.5 dB) is unreliable at low volume
                                speech_ratio = metrics.get("speech_ratio", 0)
                                min_speech = school_config.get("min_speech_ratio", 0.0)
                                if rms_db < -60.0:
                                    logger.debug(
                                        f"[VALIDATION] Speech ratio check skipped — low volume ({rms_db:.1f} dB < -60 dB) "
                                        f"makes speech detection unreliable (speech_ratio={speech_ratio*100:.0f}%)"
                                    )
                                elif speech_ratio < min_speech:
                                    raise ValueError(
                                        f"Audio blocked: Insufficient speech detected. "
                                        f"Speech ratio is {speech_ratio*100:.0f}% (minimum required: {min_speech*100:.0f}%). "
                                        f"Please ensure you are speaking clearly into the microphone."
                                    )

                                # 2d: Silence ratio check (existing)
                                # Skip if RMS is below -60 dB — silence threshold is -57 dB,
                                # so low-volume audio will always register as ~100% silence
                                silence_ratio = metrics.get("silence_ratio", 0)
                                if rms_db < -60.0:
                                    logger.debug(
                                        f"[VALIDATION] Silence ratio check skipped — low volume ({rms_db:.1f} dB < -60 dB) "
                                        f"makes silence detection unreliable (silence_ratio={silence_ratio*100:.0f}%)"
                                    )
                                elif silence_ratio > max_silence_ratio:
                                    raise ValueError(
                                        f"Audio blocked: Recording is {silence_ratio*100:.0f}% silence "
                                        f"(maximum allowed: {max_silence_ratio*100:.0f}%). "
                                        f"Audio appears to contain no speech."
                                    )

                                logger.debug(
                                    f"[VALIDATION] Audio metrics OK: SNR={snr_db:.1f}dB (min:{min_snr}), "
                                    f"RMS={rms_db:.1f}dB (min:{min_rms}), speech={speech_ratio:.2f} (min:{min_speech}), "
                                    f"silence={silence_ratio:.2f} (max:{max_silence_ratio})"
                                )
                    else:
                        logger.info(f"[AUDIO_VALIDATION] Skipped — disabled for school {school_id}")

                    # ============================================================================
                    # EXTRACTION: Run extraction with pre-generated extraction_id
                    # Results are NOT blocked by emotion analysis
                    # ============================================================================
                    extract_start = time.time()
                    insights, extraction_id = await self._extract_insights(
                        transcript, extraction_model, extraction_id=pre_generated_extraction_id
                    )
                    self.extraction_time = time.time() - extract_start

                    # NOTE: Timing is now saved directly in perform_template_extraction()
                    # (calculated_extraction_time is computed there and included in initial DB save)
                    # No separate update_extraction_timing call needed - avoids race condition

                    # Debug logging for extraction result
                    logger.debug(f"[EXTRACT_RESULT] Extraction completed:")
                    logger.debug(f"[EXTRACT_RESULT] - Type: {type(insights).__name__ if insights else 'None'}")
                    logger.debug(f"[EXTRACT_RESULT] - Is None: {insights is None}")
                    if insights:
                        logger.debug(f"[EXTRACT_RESULT] - Is dict: {isinstance(insights, dict)}")
                        if isinstance(insights, dict):
                            logger.debug(f"[EXTRACT_RESULT] - Key count: {len(insights)}")

                    yield ProgressEvent("progress", {
                        "status": "EXTRACTING",
                        "progress": 90,
                        "message": "Insights extracted successfully",
                        "extraction_time": round(self.extraction_time, 2),
                    })

            # Step 6: Save results to database
            yield ProgressEvent("progress", {
                "status": "SAVING",
                "progress": 95,
                "message": "Saving results and cleaning up chunks...",
            })

            total_time = time.time() - self.start_time

            # Use pre-fetched audio quality (already in self._audio_quality from before extraction)
            # No DB fetch needed - saves 0.2-2s latency

            # Update job status to COMPLETED
            # Include transcript and insights in progress_json for Supabase Realtime subscribers
            # (Data is ALSO saved to extractions table via perform_template_extraction)
            await asyncio.to_thread(
                update_job_progress,
                self.submission_id,
                "COMPLETED",
                100,
                "Processing completed successfully",
                # Pass transcript and insights for progress_json (Supabase Realtime)
                transcript=transcript,
                insights=insights,
                extraction_id=extraction_id,  # Include extraction_id for emotion analysis lookup
                audio_quality=self._audio_quality,  # Use pre-fetched audio quality
                stitching_time_seconds=self.stitching_time,
                transcription_time_seconds=self.transcription_time,
                extraction_time_seconds=self.extraction_time,
                total_processing_time_seconds=total_time,
            )

            # Step 7: Save full audio (fire-and-forget, non-blocking)
            # Audio save runs in background - doesn't block extraction flow
            from services.supabase_service import cleanup_chunks_and_save_full_audio

            # Save ORIGINAL audio as primary (what was actually recorded)
            # Only save processed audio separately if silence was actually removed
            audio_to_save = original_audio_b64
            full_audio_size = len(audio_to_save)
            processed_audio_to_save = None
            if enable_silence_removal and silence_stats.get("removed"):
                processed_audio_to_save = stitched_audio_b64

            async def _save_audio_and_clear_memory_async():
                """Background task: save audio with retry, clear memory on success."""
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        await asyncio.to_thread(
                            cleanup_chunks_and_save_full_audio,
                            session_id=session_id,
                            full_audio_data=audio_to_save,
                            full_audio_mime_type=mime_type,
                            full_audio_size_bytes=full_audio_size,
                            processed_audio_data=processed_audio_to_save,
                        )
                        # Clear memory only on success
                        cleared_count = clear_session(str(session_id))
                        logger.debug(
                            f"[AUDIO_SAVE] Stitched audio saved to DB successfully "
                            f"({full_audio_size} bytes), cleared {cleared_count} chunks from memory"
                        )
                        return
                    except Exception as e:
                        logger.warning(f"[AUDIO_SAVE] Attempt {attempt + 1}/{max_retries} failed: {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1)  # Wait before retry

                # All retries failed - log error but don't crash
                # Memory will be cleaned up by TTL cleanup task
                logger.error(
                    f"[AUDIO_SAVE] CRITICAL: Failed to save stitched audio after {max_retries} attempts. "
                    f"Memory will be cleared by TTL cleanup."
                )

            # Fire-and-forget: don't await, continue immediately
            asyncio.create_task(_save_audio_and_clear_memory_async())
            logger.debug(f"[AUDIO_SAVE] Background save started for session {session_id}")

            yield ProgressEvent("progress", {
                "status": "CLEANING",
                "progress": 98,
                "message": "Audio save started (background)",
            })

            # Step 7: Database save already handled by perform_template_extraction()
            # (includes extractions, extraction_segments, and emotion scheduling)

            # Step 8: Complete (audio_quality pre-fetched before extraction in self._audio_quality)
            # Debug logging for SSE complete event
            logger.debug(f"[COMPLETE_EVENT] Preparing complete event:")
            logger.debug(f"[COMPLETE_EVENT] - Transcript length: {len(transcript) if transcript else 0}")
            logger.debug(f"[COMPLETE_EVENT] - Insights type: {type(insights).__name__ if insights else 'None'}")
            logger.debug(f"[COMPLETE_EVENT] - Insights is None: {insights is None}")
            if self._audio_quality:
                logger.debug(f"[COMPLETE_EVENT] - Audio quality: {self._audio_quality.get('overall_quality', 'unknown')}")
            if insights:
                logger.debug(f"[COMPLETE_EVENT] - Insights key count: {len(insights) if isinstance(insights, dict) else 'not a dict'}")

            yield ProgressEvent("complete", {
                "status": "COMPLETED",
                "progress": 100,
                "message": "Processing completed successfully",
                "transcript": transcript,
                "insights": insights,
                "audio_quality": self._audio_quality,  # Use pre-fetched audio quality
                "metrics": {
                    "stitching_time": round(self.stitching_time, 2),
                    "transcription_time": round(self.transcription_time, 2),
                    "extraction_time": round(self.extraction_time, 2),
                    "total_time": round(total_time, 2),
                    "chunk_count": len(chunks),
                    "audio_duration": round(estimated_duration, 2),
                },
            })

        except Exception as e:
            # Handle errors - sanitize to strip LLM provider names
            from services.error_utils import sanitize_error_message
            error_message = sanitize_error_message(str(e))

            # ============================================================================
            # VALIDATION FAILURE HANDLING: Preserve chunks for debugging
            # ============================================================================
            validation_failure_phrases = [
                "Audio quality validation failed",
                "Audio validation failed",
                "Transcription validation failed",
                "Transcription failed due to model cap",
                "Audio format not compatible",
                "Video codec detected"
            ]
            is_validation_failure = any(phrase in error_message for phrase in validation_failure_phrases)

            if is_validation_failure:
                logger.warning(
                    f"[VALIDATION_FAILURE] Preserving audio chunks for session {self._session_id} - "
                    f"chunks will NOT be deleted for debugging. Error: {error_message}"
                )

                # Await temp audio storage completion (ensure we have it for debugging)
                # Check if we have a temp storage task running
                temp_storage_task = getattr(self, '_temp_storage_task', None)
                if temp_storage_task and not temp_storage_task.done():
                    try:
                        await asyncio.wait_for(temp_storage_task, timeout=30.0)
                        logger.info(f"[VALIDATION_FAILURE] Temp audio saved successfully for debugging")
                    except asyncio.TimeoutError:
                        logger.warning(f"[VALIDATION_FAILURE] Temp audio storage timed out after 30s")
                    except Exception as storage_error:
                        logger.warning(f"[VALIDATION_FAILURE] Could not save temp audio: {storage_error}")

                # Update session to mark as validation failure (prevents chunk cleanup)
                try:
                    from services.supabase_service import supabase
                    supabase.table("recording_sessions")\
                        .update({"status": "validation_failed", "error_message": error_message})\
                        .eq("id", str(self._session_id))\
                        .execute()
                    logger.info(f"[VALIDATION_FAILURE] Session {self._session_id} marked as validation_failed")
                except Exception as db_error:
                    logger.error(f"[VALIDATION_FAILURE] Failed to update session status: {db_error}")

            # Update job with error details
            await asyncio.to_thread(
                update_job_error,
                self.submission_id,
                error_message=error_message,
                error_details={
                    "exception_type": type(e).__name__,
                    "is_validation_failure": is_validation_failure,
                    "keep_chunks": is_validation_failure
                },
            )

            # Send error webhook to notify EHR systems (prevents indefinite waiting)
            try:
                from services.webhook_service import send_error_webhook
                session_data = getattr(self, '_session', None)
                session_id_str = str(getattr(self, '_session_id', None)) if getattr(self, '_session_id', None) else None
                await send_error_webhook(
                    error_message=error_message,
                    session_id=session_id_str,
                    submission_id=str(self.submission_id) if self.submission_id else None,
                    session_data=session_data,
                    source="recording",
                    error_code="VALIDATION_FAILED" if is_validation_failure else "PROCESSING_FAILED",
                )
            except Exception as webhook_err:
                logger.warning(f"[WEBHOOK:ERROR] Failed to send error webhook: {webhook_err}")

            # Publish error to realtime_extraction_responses (for EHR Realtime subscribers)
            try:
                from services.realtime_publisher_service import publish_error_response_fire_and_forget
                from services.supabase_service import get_counsellor_school_id_cached
                _session = getattr(self, '_session', None) or {}
                _doctor_id = _session.get("counsellor_id")
                _hospital_id = get_counsellor_school_id_cached(uuid.UUID(_doctor_id)) if _doctor_id else None
                if _hospital_id and self.submission_id:
                    asyncio.create_task(publish_error_response_fire_and_forget(
                        submission_id=str(self.submission_id),
                        school_id=_hospital_id,
                        counsellor_id=_doctor_id,
                        error_message=error_message,
                        error_code="VALIDATION_FAILED" if is_validation_failure else "PROCESSING_FAILED",
                        session_id=session_id_str,
                    ))
            except Exception as rt_err:
                logger.warning(f"[REALTIME:ERROR] Failed to schedule error publish: {rt_err}")

            yield ProgressEvent("error", {
                "status": "ERROR",
                "progress": self._last_progress,
                "failed_at_stage": self._last_status,
                "message": f"Processing failed at {self._last_status} stage: {error_message}",
                "error": error_message,
                "is_validation_failure": is_validation_failure,
            })

    async def _extract_insights(
        self,
        transcript: str,
        extraction_model: str = "gemini-2.5-flash",
        extraction_id: Optional[uuid.UUID] = None,
    ) -> tuple[Optional[Dict[str, Any]], Optional[uuid.UUID]]:
        """
        Extract medical insights using template-based dynamic extraction.

        This method implements a 2-tier fallback strategy:
        1. Try cached dynamic prompts (fast path - parallel generation)
        2. Use template-based extraction with counsellor configuration

        Both tiers use perform_template_extraction() for the complete workflow:
        - Update session.consultation_type_id
        - Save to extractions table
        - Schedule triage/consultation insights (if enabled)
        - Send webhook (if extraction_mode is 'full')

        NOTE: Emotion analysis is now scheduled in process() method
        in parallel with extraction for reduced latency.

        Note: Template lookup uses template_code from session (via perform_template_extraction).

        Args:
            transcript: The transcribed text
            extraction_model: Gemini model to use for extraction (default: gemini-2.5-flash)
            extraction_id: Pre-generated UUID for parallel emotion analysis (optional)
                          If provided, the database record will use this ID

        Returns:
            Tuple of (insights_dict, extraction_id):
            - insights_dict: Extracted insights as a dict (or None for TRANSCRIPT_ONLY mode)
            - extraction_id: UUID of the created extractions record (or None for TRANSCRIPT_ONLY mode)

        Raises:
            ValueError: If extraction fails
        """
        # ============================================================================
        # COMMON CODE: Get session data from instance (avoid re-querying)
        # ============================================================================
        from services.extraction_service import perform_template_extraction
        from services.webhook_service import send_insights_webhook

        # Use cached session data from process() method
        session_id = self._session_id
        session = self._session

        # ============================================================================
        # TIER 1: Try cached artifacts (FAST PATH - parallel generation)
        # ============================================================================
        cached_artifacts = _cached_prompt_artifacts.get()
        if cached_artifacts:
            try:
                consultation_type_code = cached_artifacts.get('consultation_type_code', 'UNKNOWN')
                segment_count = cached_artifacts.get('segment_count', 0)
                logger.debug(
                    f"[EXTRACTION] CACHE HIT: Using cached prompts for {consultation_type_code} "
                    f"({segment_count} segments) - Fast path active"
                )

                # Substitute transcript into user_prompt_template
                # Use .replace() instead of .format() to avoid JSON curly braces being interpreted as placeholders
                cached_artifacts_with_prompt = {
                    **cached_artifacts,
                    'user_prompt': cached_artifacts['user_prompt_template'].replace('{transcript}', transcript)
                }

                # Call shared extraction service with cached artifacts
                # This handles: template lookup, consultation_type_id update, DB save, triage scheduling
                # Note: emotion scheduling moved to process() for parallel execution
                result = await perform_template_extraction(
                    transcript=transcript,
                    session_id=session_id,
                    extraction_model=extraction_model,
                    submission_id=self.submission_id,
                    cached_artifacts=cached_artifacts_with_prompt,
                    # Pass timing metrics for SSE delivery
                    stitching_time_seconds=self.stitching_time,
                    transcription_time_seconds=self.transcription_time,
                    extraction_time_seconds=self.extraction_time,
                    total_processing_time_seconds=time.time() - self.start_time,
                    # Pass audio data for after_transcription emotion mode
                    audio_content=getattr(self, '_audio_bytes', None),
                    audio_mime_type=getattr(self, '_audio_mime_type', None),
                    # OPTIMIZATION: Pass session data to avoid re-querying
                    session_data=session,
                    # Pre-generated extraction_id for parallel emotion analysis
                    extraction_id=extraction_id,
                )

                # Handle TRANSCRIPT_ONLY mode (returns None, None)
                if not result:
                    logger.info("[EXTRACTION] TRANSCRIPT_ONLY mode - skipping extraction")
                    return (None, None)

                # Filter excluded segments from response (applies to both API and webhook)
                session_info = result['session_info']
                extraction_mode = session_info.get('extraction_mode')
                excluded_codes = result.get('excluded_segment_codes', set())
                insights_data = result['data']

                if excluded_codes and isinstance(insights_data, dict):
                    # Convert excluded codes to camelCase for matching (segment codes are UPPER_SNAKE_CASE)
                    # e.g., "CAUTION" -> "caution", "SUMMARY" -> "summary"
                    excluded_camel = set()
                    for code in excluded_codes:
                        # Convert UPPER_SNAKE_CASE to camelCase
                        parts = code.lower().split('_')
                        camel = parts[0] + ''.join(p.capitalize() for p in parts[1:])
                        excluded_camel.add(camel)

                    filtered_insights = {
                        key: value for key, value in insights_data.items()
                        if key not in excluded_camel
                    }
                    logger.debug(f"[EXTRACTION] Filtered {len(excluded_codes)} excluded segments: {excluded_codes} -> {excluded_camel}")
                else:
                    filtered_insights = insights_data

                # Send webhook ONLY if extraction_mode is 'full'
                logger.debug(f"[WEBHOOK] Checking if webhook should be sent - extraction_mode: {extraction_mode}")

                if extraction_mode == 'full':
                    logger.debug(f"[WEBHOOK] Extraction mode is 'full', sending webhook with in-memory data")

                    # Use pre-fetched audio quality (no DB fetch needed - already in self._audio_quality)
                    # Build standardized metadata (same structure as API response)
                    from datetime import datetime
                    standardized_metadata = {
                        "correlation_id": session_info.get('correlation_id'),
                        "submission_id": str(self.submission_id) if self.submission_id else None,
                        "extraction_id": result['extraction_id'],
                        "session_id": str(self._session_id) if self._session_id else None,
                        "counsellor_id": session_info.get('counsellor_id'),
                        "student_id": session_info.get('student_id'),
                        "template_code": session_info.get('template_code'),
                        "mode": extraction_mode,
                        "segment_count": len(filtered_insights) if isinstance(filtered_insights, dict) else 0,
                        "processing_mode": session_info.get('processing_mode'),
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "audio_quality": self._audio_quality,  # Use pre-fetched audio quality
                        "preferred_language": getattr(self, '_detected_language', None),
                        # For the reference envelope (career_*): transcript -> originalTranscription,
                        # audio mime/format -> mediaFormat. transcript_text is redacted from logs.
                        "transcript_text": transcript,
                        "audio_format": getattr(self, '_audio_mime_type', None),
                    }

                    # Check if realtime is enabled (skip webhook if so)
                    from services.realtime_publisher_service import is_realtime_enabled_for_school
                    from services.supabase_service import get_counsellor_school_id_cached
                    _doctor_id = session_info.get('counsellor_id')
                    _hospital_id = get_counsellor_school_id_cached(uuid.UUID(_doctor_id)) if _doctor_id else None
                    if _hospital_id and is_realtime_enabled_for_school(_hospital_id):
                        logger.debug(f"[WEBHOOK] Skipping webhook - realtime subscription enabled for school")
                    else:
                        # Send webhook with standardized metadata
                        webhook_success = await send_insights_webhook(
                            insights=filtered_insights,
                            metadata=standardized_metadata,
                            source='recording',
                            excluded_segment_codes=excluded_codes
                        )

                        if webhook_success:
                            logger.info(f"[WEBHOOK] ✅ Webhook sent successfully")
                        else:
                            logger.error(f"[WEBHOOK] ❌ Webhook failed for full extraction mode")
                else:
                    logger.debug(f"[WEBHOOK] Skipping webhook - extraction_mode is '{extraction_mode}', not 'full'")

                # Return tuple of (filtered data, extraction_id)
                extraction_id = uuid.UUID(result['extraction_id'])
                return (filtered_insights, extraction_id)

            except Exception as e:
                error_msg = str(e)
                # Check for transient Gemini API errors (don't log full traceback)
                if "temporarily unavailable" in error_msg or "Server disconnected" in error_msg:
                    logger.warning(f"[EXTRACTION] ⚠️ Transient API error: {error_msg}")
                else:
                    logger.error(f"[EXTRACTION] ❌ CACHE FAILED: {e}")
                    logger.error(f"[EXTRACTION] Full error traceback:", exc_info=True)
                # Re-raise to propagate error
                raise
        else:
            # Cache was None - check if this is a split extraction type
            # Split extraction types (NEO_OP, NEONATAL_PROFORMA, etc.) are handled by gemini_service
            # with hardcoded prompts, so cache miss is expected for them.
            from services.gemini_service import SPLIT_EXTRACTION_TYPES

            template_code = session.get("template_code")

            if template_code and template_code in SPLIT_EXTRACTION_TYPES:
                # Expected for split extraction types - fall through to gemini_service
                logger.debug(
                    f"[EXTRACTION] SPLIT EXTRACTION TYPE: {template_code} - "
                    f"falling through to gemini_service with hardcoded prompts"
                )

                # Call shared extraction service WITHOUT cached artifacts
                # gemini_service will detect split extraction types and use hardcoded prompts
                result = await perform_template_extraction(
                    transcript=transcript,
                    session_id=session_id,
                    extraction_model=extraction_model,
                    submission_id=self.submission_id,
                    cached_artifacts=None,  # Let gemini_service handle prompt generation
                    # Pass timing metrics for SSE delivery
                    stitching_time_seconds=self.stitching_time,
                    transcription_time_seconds=self.transcription_time,
                    extraction_time_seconds=self.extraction_time,
                    total_processing_time_seconds=time.time() - self.start_time,
                    # Pass audio data for after_transcription emotion mode
                    audio_content=getattr(self, '_audio_bytes', None),
                    audio_mime_type=getattr(self, '_audio_mime_type', None),
                    # OPTIMIZATION: Pass session data to avoid re-querying
                    session_data=session,
                    # Pre-generated extraction_id for parallel emotion analysis
                    extraction_id=extraction_id,
                )

                # Handle TRANSCRIPT_ONLY mode (returns None, None)
                if not result:
                    logger.info("[EXTRACTION] TRANSCRIPT_ONLY mode - skipping extraction")
                    return (None, None)

                # Get session info and extraction data
                session_info = result['session_info']
                extraction_mode = session_info.get('extraction_mode')
                insights_data = result['data']

                # Send webhook ONLY if extraction_mode is 'full'
                logger.debug(f"[WEBHOOK] Checking if webhook should be sent - extraction_mode: {extraction_mode}")

                if extraction_mode == 'full':
                    logger.debug(f"[WEBHOOK] Extraction mode is 'full', sending webhook with in-memory data")

                    # Use pre-fetched audio quality (no DB fetch needed - already in self._audio_quality)
                    # Build standardized metadata (same structure as API response)
                    from datetime import datetime
                    standardized_metadata = {
                        "correlation_id": session_info.get('correlation_id'),
                        "submission_id": str(self.submission_id) if self.submission_id else None,
                        "extraction_id": result['extraction_id'],
                        "session_id": str(self._session_id) if self._session_id else None,
                        "counsellor_id": session_info.get('counsellor_id'),
                        "student_id": session_info.get('student_id'),
                        "template_code": session_info.get('template_code'),
                        "mode": extraction_mode,
                        "segment_count": len(insights_data) if isinstance(insights_data, dict) else 0,
                        "processing_mode": session_info.get('processing_mode'),
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "audio_quality": self._audio_quality,  # Use pre-fetched audio quality
                        "preferred_language": getattr(self, '_detected_language', None),
                        # For the reference envelope (career_*): transcript -> originalTranscription,
                        # audio mime/format -> mediaFormat. transcript_text is redacted from logs.
                        "transcript_text": transcript,
                        "audio_format": getattr(self, '_audio_mime_type', None),
                    }

                    # Check if realtime is enabled (skip webhook if so)
                    from services.realtime_publisher_service import is_realtime_enabled_for_school
                    from services.supabase_service import get_counsellor_school_id_cached
                    _doctor_id = session_info.get('counsellor_id')
                    _hospital_id = get_counsellor_school_id_cached(uuid.UUID(_doctor_id)) if _doctor_id else None
                    if _hospital_id and is_realtime_enabled_for_school(_hospital_id):
                        logger.debug(f"[WEBHOOK] Skipping webhook - realtime subscription enabled for school")
                    else:
                        # Send webhook with standardized metadata
                        webhook_success = await send_insights_webhook(
                            insights=insights_data,
                            metadata=standardized_metadata,
                            source='recording',
                            excluded_segment_codes=set()  # No excluded segments for split extraction
                        )

                        if webhook_success:
                            logger.info(f"[WEBHOOK] ✅ Webhook sent successfully")
                        else:
                            logger.error(f"[WEBHOOK] ❌ Webhook failed for full extraction mode")
                else:
                    logger.debug(f"[WEBHOOK] Skipping webhook - extraction_mode is '{extraction_mode}', not 'full'")

                # Return tuple of (data, extraction_id)
                extraction_id = uuid.UUID(result['extraction_id'])
                return (insights_data, extraction_id)
            else:
                # Not a split extraction type - this is an error
                error_msg = (
                    f"[EXTRACTION] ❌ CACHE MISS: No cached prompts available for {consultation_type_code}. "
                    f"This may indicate consultation_type_id was not set during session creation."
                )
                logger.error(error_msg)
                raise Exception(error_msg)

        # ============================================================================
        # TIER 2: Template-based extraction (DISABLED FOR DEBUGGING)
        # ============================================================================
        # COMMENTED OUT TO FORCE CACHE USAGE AND DEBUG JSON PARSING ISSUES
        # Uncomment below to re-enable Tier 2 fallback
        """
        try:
            # Call shared extraction service (generates prompts from database)
            # This handles: template lookup, consultation_type_id update, DB save, triage scheduling
            result = await perform_template_extraction(
                transcript=transcript,
                session_id=session_id,
                extraction_model=extraction_model,
                submission_id=self.submission_id,
                # Pass timing metrics for SSE delivery
                stitching_time_seconds=self.stitching_time,
                transcription_time_seconds=self.transcription_time,
                extraction_time_seconds=self.extraction_time,
                total_processing_time_seconds=time.time() - self.start_time,
                # OPTIMIZATION: Pass session data to avoid re-querying
                session_data=session,
                # Pre-generated extraction_id for parallel emotion analysis
                extraction_id=extraction_id,
            )

            # Handle TRANSCRIPT_ONLY mode (returns None, None)
            if not result:
                logger.info("[EXTRACTION] TRANSCRIPT_ONLY mode - skipping extraction")
                return (None, None)

            # Send webhook ONLY if extraction_mode is 'full' (to avoid duplication)
            extraction_mode = result['session_info'].get('extraction_mode')
            logger.info(f"[WEBHOOK] Checking if webhook should be sent - extraction_mode: {extraction_mode}")

            if extraction_mode == 'full':
                # Check if realtime is enabled (skip webhook if so)
                from services.realtime_publisher_service import is_realtime_enabled_for_school
                from services.supabase_service import get_counsellor_school_id_cached
                _doctor_id = result['session_info'].get('counsellor_id')
                _hospital_id = get_counsellor_school_id_cached(uuid.UUID(_doctor_id)) if _doctor_id else None
                if _hospital_id and is_realtime_enabled_for_school(_hospital_id):
                    logger.info(f"[WEBHOOK] ⏭️ Skipping webhook - realtime subscription enabled for school")
                else:
                    logger.info(f"[WEBHOOK] ✅ Extraction mode is 'full', preparing to send webhook")

                    # Send webhook asynchronously (non-blocking)
                    webhook_success = await send_insights_webhook(
                        insights=result['data'],
                        metadata=result['session_info'],
                        source='recording'
                    )

                    if webhook_success:
                        logger.info(f"[WEBHOOK] ✅ Webhook sent successfully for full extraction mode")
                    else:
                        logger.error(f"[WEBHOOK] ❌ Webhook failed for full extraction mode")
            else:
                logger.info(f"[WEBHOOK] ⏭️  Skipping webhook - extraction_mode is '{extraction_mode}', not 'full'")

            # Return tuple of (data, extraction_id)
            extraction_id = uuid.UUID(result['extraction_id'])
            return (result['data'], extraction_id)

        except Exception as e:
            logger.error(f"[EXTRACTION] Template-based extraction failed: {str(e)}")
            logger.error(f"[EXTRACTION] Traceback: {traceback.format_exc()}")
            raise ValueError(f"Extraction failed: {str(e)}")
        """

    async def _generate_prompts_parallel(self, session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate prompts in parallel during transcription (optimization).

        This function attempts to generate dynamic prompts from database configuration.
        If the session doesn't have the required configuration (consultation_type_id, etc.),
        it returns None and the system will use static prompts.

        Args:
            session: Recording session data with configuration

        Returns:
            Prompt artifacts dict or None if dynamic generation not applicable
        """
        prompt_gen_start = time.time()
        try:
            # Check if session has dynamic extraction configuration
            consultation_type_id = session.get("consultation_type_id")
            counsellor_id = session.get("counsellor_id")
            student_id = session.get("student_id")  # For student history context injection
            template_code = session.get("template_code")  # Use template_code for DB lookups
            # FIX: Use "or" to handle None values (session may have extraction_mode=None)
            extraction_mode = session.get("extraction_mode") or "core"

            # If no consultation_type_id, can't use dynamic generation
            if not consultation_type_id:
                logger.warning(
                    f"[OPTIMIZATION] ❌ PARALLEL GENERATION SKIPPED: Session has no consultation_type_id. "
                    f"This means prompts will be regenerated during extraction (slower path). "
                    f"To enable caching, ensure consultation_type_id is set during session creation."
                )
                return None

            # Import here to avoid circular imports
            from services.segment_registry import generate_extraction_artifacts_without_transcript

            # Generate prompts without transcript (parallel optimization)
            artifacts = await asyncio.to_thread(
                generate_extraction_artifacts_without_transcript,
                consultation_type_id=uuid.UUID(consultation_type_id),
                counsellor_id=uuid.UUID(counsellor_id) if counsellor_id else None,
                template_code=template_code,
                mode=extraction_mode,
                student_id=student_id  # For student history context injection
            )

            # Validate artifacts is a dict (defensive check)
            if not isinstance(artifacts, dict):
                logger.error(
                    f"[OPTIMIZATION] ❌ Unexpected return type from generate_extraction_artifacts_without_transcript: "
                    f"got {type(artifacts).__name__} instead of dict. Value: {str(artifacts)[:200]}"
                )
                return None

            consultation_type_code = artifacts.get('consultation_type_code', 'UNKNOWN')
            segment_count = artifacts.get('segment_count', 0)

            # Check if this is a split extraction type (NEO_OP, NEONATAL_PROFORMA, etc.)
            # These types have hardcoded prompts in gemini_service and don't need caching
            if artifacts.get('is_split_extraction'):
                prompt_gen_duration = time.time() - prompt_gen_start
                logger.info(
                    f"[TIMING_PROMPT_GEN] ⚡ SPLIT TYPE {consultation_type_code}: {prompt_gen_duration:.3f}s - "
                    f"skipping prompt caching. gemini_service will handle extraction with hardcoded prompts."
                )
                return None  # Return None so gemini_service uses its own prompts

            prompt_gen_duration = time.time() - prompt_gen_start
            logger.info(
                f"[TIMING_PROMPT_GEN] ✅ Parallel generation: {prompt_gen_duration:.3f}s - "
                f"{segment_count} segments for {consultation_type_code}"
            )
            return artifacts

        except ValueError as e:
            # Re-raise ValueError for configuration errors (e.g., no system prompt assigned)
            # These should be surfaced to the user, not swallowed
            prompt_gen_duration = time.time() - prompt_gen_start
            logger.error(f"[TIMING_PROMPT_GEN] ❌ Config error after {prompt_gen_duration:.3f}s: {e}")
            raise
        except Exception as e:
            prompt_gen_duration = time.time() - prompt_gen_start
            logger.error(f"[TIMING_PROMPT_GEN] ❌ Failed after {prompt_gen_duration:.3f}s: {e}", exc_info=True)
            return None

# ============================================================================
# Standalone Processing Function (for background tasks)
# ============================================================================

async def process_recording_in_background(submission_id: uuid.UUID) -> Dict[str, Any]:
    """
    Process a recording session in the background without SSE streaming.
    Useful for background task queues.

    Args:
        submission_id: The submission ID to process

    Returns:
        Final processing results

    Raises:
        Exception: Any processing errors
    """
    processor = RecordingProcessor(submission_id)

    final_result = None
    async for event in processor.process():
        if event.event_type == "complete":
            final_result = event.data
        elif event.event_type == "error":
            raise Exception(event.data["message"])

    return final_result


# ============================================================================
# Testing Helper
# ============================================================================

async def test_processor(submission_id: uuid.UUID):
    """
    Test the processor and print progress events.

    Args:
        submission_id: The submission ID to test
    """
    processor = RecordingProcessor(submission_id)

    print(f"\n{'='*60}")
    print(f"Processing submission: {submission_id}")
    print(f"{'='*60}\n")

    async for event in processor.process():
        print(f"[{event.event_type.upper()}] {event.data['message']}")
        if event.event_type == "complete":
            print(f"\n{'='*60}")
            print("COMPLETED SUCCESSFULLY")
            print(f"{'='*60}")
            print(f"Metrics: {event.data['metrics']}")
        elif event.event_type == "error":
            print(f"\n{'='*60}")
            print("ERROR OCCURRED")
            print(f"{'='*60}")
            print(f"Error: {event.data['error']}")


if __name__ == "__main__":
    # Example usage
    import sys

    if len(sys.argv) < 2:
        print("Usage: python recording_processor.py <submission_id>")
        sys.exit(1)

    test_submission_id = uuid.UUID(sys.argv[1])
    asyncio.run(test_processor(test_submission_id))

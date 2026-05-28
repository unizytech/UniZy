"""
Recording Reprocess Service

Orchestrates reprocessing of existing recordings with new template/settings.
Two modes supported:
1. reprocess_transcript - Use existing transcript, just re-extract
2. new_extraction - Re-transcribe from stored audio + extract

Also handles abandoned recordings (RECORDING status) by:
- Stitching available audio chunks
- Running full pipeline
- Updating status to SUBMITTED after transcription

Reuses existing pipeline functions - no custom pipeline logic.
"""

import asyncio
import base64
import logging
import time
import uuid
from typing import Dict, Any, Optional

from datetime import datetime, timezone

from services.supabase_service import (
    get_session_by_id,
    get_session_transcript,
    get_session_full_audio,
    get_session_chunks,
    get_last_chunk_timestamp,
    update_session_settings,
    create_processing_job,
    update_job_progress,
    get_template_by_code,
    cleanup_chunks_and_save_full_audio,
    update_session_status,
    get_consultation_type_by_id,
)

# Minimum time since last chunk to consider a recording abandoned (5 minutes)
ABANDONED_THRESHOLD_MINUTES = 5
from services.gemini_service import transcribe_audio, extract_insights_from_audio_direct
from services.background_tasks import schedule_combined_emotion_extraction
from services.extraction_service import perform_template_extraction
from services.audio_stitcher import stitch_audio_chunks
from services.audio_silence_remover import remove_silence_from_audio
from services.webhook_service import send_insights_webhook

logger = logging.getLogger(__name__)


async def reprocess_recording(
    session_id: uuid.UUID,
    mode: str,  # "new_extraction" or "reprocess_transcript"
    template_code: str,
    processing_mode: str,
    extraction_mode: str,
) -> Dict[str, Any]:
    """
    Main reprocess orchestration.

    Validates inputs, creates processing job, and routes to appropriate
    reprocess function (transcript-only or full pipeline).

    Args:
        session_id: UUID of the recording session to reprocess
        mode: Reprocess mode - "new_extraction" or "reprocess_transcript"
        template_code: Template code to use for extraction
        processing_mode: Processing mode code
        extraction_mode: Extraction mode ('core', 'additional', 'full')

    Returns:
        Dict with:
        - submission_id: UUID of new processing job
        - mode_used: Actual mode used (may differ if fallback)
        - fallback_used: True if had to fallback to new_extraction
        - message: Status message

    Raises:
        ValueError: If session not found, template not found, or no audio for new_extraction
    """
    logger.info(
        f"[REPROCESS] Starting reprocess for session {session_id}, "
        f"mode={mode}, template={template_code}"
    )

    # 1. Validate session exists
    session = get_session_by_id(session_id)
    if not session:
        raise ValueError("Session not found")

    session_status = session.get('status')

    # Block reprocessing of quality-rejected recordings UNLESS:
    # 1. Local audio quality passed, OR
    # 2. Chunks exist with substantial total size (>1MB) — indicates the quality
    #    check ran on a broken stitched file, not genuinely empty audio
    if session_status == 'validation_failed':
        audio_quality = session.get('audio_quality_json') or {}
        local_quality_passed = audio_quality.get('is_acceptable', False)
        if local_quality_passed:
            logger.info(
                f"[REPROCESS] Session {session_id} was validation_failed but local audio quality "
                f"passed (quality={audio_quality.get('overall_quality')}). Allowing reprocess."
            )
        else:
            # Check if chunks exist with real audio data (stitching may have failed)
            # Use lightweight count query — don't fetch full audio_data blobs
            from services.supabase_service import supabase as _sb
            chunk_stats = _sb.table("audio_chunks")\
                .select("chunk_index", count="exact")\
                .eq("session_id", str(session_id))\
                .execute()
            chunk_count = chunk_stats.count if chunk_stats.count else 0
            if chunk_count > 5:  # >5 chunks ≈ >50 seconds of audio
                logger.info(
                    f"[REPROCESS] Session {session_id} was validation_failed but has "
                    f"{chunk_count} chunks. "
                    f"Quality check likely ran on broken stitch. Allowing reprocess."
                )
            else:
                original_error = session.get('error_message', 'Audio quality validation failed')
                raise ValueError(
                    f"Cannot reprocess: recording was rejected due to audio quality issues. "
                    f"Reason: {original_error}"
                )

    is_abandoned = (session_status == 'RECORDING')

    # 2. For abandoned recordings (RECORDING status), only new_extraction is allowed
    if is_abandoned and mode != "new_extraction":
        logger.info(
            f"[REPROCESS] Abandoned recording (status=RECORDING), "
            f"forcing mode to new_extraction"
        )
        mode = "new_extraction"

    # 2b. Check if skip_transcription is enabled for the consultation type
    skip_transcription = False
    consultation_type_id = session.get('consultation_type_id')
    if consultation_type_id:
        ct_data = get_consultation_type_by_id(uuid.UUID(consultation_type_id) if isinstance(consultation_type_id, str) else consultation_type_id)
        if ct_data:
            skip_transcription = ct_data.get('skip_transcription', False)

    # If skip_transcription is enabled, force new_extraction mode (can't use existing transcript)
    if skip_transcription and mode == "reprocess_transcript":
        logger.info(
            f"[REPROCESS] skip_transcription enabled for consultation type, "
            f"forcing mode to new_extraction (direct audio extraction)"
        )
        mode = "new_extraction"

    # 3. Validate template exists
    template = get_template_by_code(template_code)
    if not template:
        raise ValueError("Invalid or unknown template code")

    # 4. Update session with new settings
    update_session_settings(session_id, template_code, processing_mode, extraction_mode)
    logger.debug(f"[REPROCESS] Updated session settings: template={template_code}, mode={processing_mode}")

    # 4b. Update in-memory session dict with new settings (so perform_template_extraction uses correct template)
    session['template_code'] = template_code
    session['template_name'] = template.get('template_name', template_code)
    session['processing_mode'] = processing_mode
    session['extraction_mode'] = extraction_mode
    session['consultation_type_id'] = template.get('consultation_type_id')

    # 4c. Clear stale session_context_json so extraction_service doesn't use
    # the old template's cached template_id/consultation_type_id (fast-path bypass).
    # Without this, reprocess with a different template would still use the
    # original recording's template for extraction and EHR payload formatting.
    # PRESERVE continuation context if present (is_continuation, parent_extraction_ids)
    continuation_context = {}
    if session.get('session_context_json'):
        ctx = session['session_context_json']
        if ctx.get('is_continuation'):
            continuation_context = {
                'is_continuation': True,
                'parent_extraction_ids': ctx.get('parent_extraction_ids', []),
                'continuation_detected_by': ctx.get('continuation_detected_by'),
            }
    session['session_context_json'] = continuation_context or None

    # 5. Create new processing job
    submission_id = uuid.uuid4()
    create_processing_job(session_id, submission_id)
    logger.debug(f"[REPROCESS] Created processing job: {submission_id}")

    # 6. Get transcript (for reprocess_transcript mode)
    transcript = get_session_transcript(session_id)

    # 7. Get audio - for abandoned recordings, stitch from chunks first
    audio_b64, mime_type = None, None
    raw_chunks_for_pipeline = None  # Track chunks for segmented transcription

    if is_abandoned:
        # Abandoned recording - need to stitch chunks
        logger.debug(f"[REPROCESS] Abandoned recording - fetching and stitching audio chunks")

        # Safety check: ensure recording is truly abandoned (last chunk > 5 minutes old)
        last_chunk_time = get_last_chunk_timestamp(session_id)
        if last_chunk_time:
            now = datetime.now(timezone.utc)
            minutes_since_last_chunk = (now - last_chunk_time).total_seconds() / 60
            if minutes_since_last_chunk < ABANDONED_THRESHOLD_MINUTES:
                raise ValueError(
                    f"Recording may still be active. Last chunk was {minutes_since_last_chunk:.1f} minutes ago. "
                    f"Please wait at least {ABANDONED_THRESHOLD_MINUTES} minutes after the last chunk before reprocessing."
                )
            logger.debug(f"[REPROCESS] Last chunk was {minutes_since_last_chunk:.1f} minutes ago - safe to process")

        chunks = get_session_chunks(session_id)

        if not chunks:
            raise ValueError("No audio chunks found for this session")

        logger.debug(f"[REPROCESS] Found {len(chunks)} chunks, stitching...")

        try:
            audio_b64, mime_type = stitch_audio_chunks(chunks)
            full_audio_size = len(audio_b64)
            raw_chunks_for_pipeline = chunks  # Keep chunks for segmented transcription
            logger.debug(f"[REPROCESS] Stitched audio: {full_audio_size} bytes (b64), mime={mime_type}")

            cleanup_chunks_and_save_full_audio(
                session_id=session_id,
                full_audio_data=audio_b64,
                full_audio_mime_type=mime_type,
                full_audio_size_bytes=full_audio_size,
            )
        except Exception as e:
            from services.error_utils import sanitize_error_message
            raise ValueError(f"Failed to stitch audio chunks: {sanitize_error_message(str(e))}")
    else:
        # Normal recording - try full audio first, fallback to chunks if needed
        audio_result = get_session_full_audio(session_id)
        audio_b64, mime_type = audio_result if audio_result else (None, None)

        # Fallback: If no full audio, try to stitch from chunks
        if not audio_b64:
            logger.debug(f"[REPROCESS] No full audio found, checking for audio chunks...")
            chunks = get_session_chunks(session_id)

            if chunks:
                logger.debug(f"[REPROCESS] Found {len(chunks)} chunks, stitching...")
                try:
                    audio_b64, mime_type = stitch_audio_chunks(chunks)
                    full_audio_size = len(audio_b64)
                    raw_chunks_for_pipeline = chunks  # Keep chunks for segmented transcription
                    logger.debug(f"[REPROCESS] Stitched audio from chunks: {full_audio_size} bytes (b64), mime={mime_type}")
                except Exception as e:
                    from services.error_utils import sanitize_error_message
                    raise ValueError(f"Failed to stitch audio chunks: {sanitize_error_message(str(e))}")
            else:
                logger.warning(f"[REPROCESS] No full audio and no chunks found for session {session_id}")

    # 8. Route based on mode
    if mode == "reprocess_transcript" and transcript:
        # Fast path - extraction only
        asyncio.create_task(_reprocess_transcript_only(
            session_id=session_id,
            submission_id=submission_id,
            transcript=transcript,
            audio_b64=audio_b64,
            mime_type=mime_type,
            template=template,
            session=session,
        ))
        return {
            "submission_id": str(submission_id),
            "mode_used": "reprocess_transcript",
            "fallback_used": False,
            "message": "Reprocessing started (extraction only)"
        }
    else:
        # Full path - transcribe + extract
        if not audio_b64:
            raise ValueError("No audio available - neither full audio nor audio chunks found for this session")

        fallback_used = (mode == "reprocess_transcript")  # Fallback if transcript was missing
        if fallback_used:
            logger.warning(
                f"[REPROCESS] No transcript found for session {session_id}, "
                f"falling back to new_extraction mode"
            )

        asyncio.create_task(_reprocess_full_pipeline(
            session_id=session_id,
            submission_id=submission_id,
            audio_b64=audio_b64,
            mime_type=mime_type,
            template=template,
            session=session,
            is_abandoned=is_abandoned,  # Pass flag to update status after transcription
            skip_transcription=skip_transcription,  # Direct audio extraction mode
            raw_chunks=raw_chunks_for_pipeline,  # For segmented transcription of long audio
        ))

        message = "Reprocessing started (full pipeline)"
        if is_abandoned:
            message = "Processing abandoned recording (full pipeline from stitched chunks)"
        elif fallback_used:
            message = "Reprocessing started (fallback to full pipeline - no transcript found)"

        return {
            "submission_id": str(submission_id),
            "mode_used": "new_extraction",
            "fallback_used": fallback_used,
            "message": message
        }


async def _reprocess_transcript_only(
    session_id: uuid.UUID,
    submission_id: uuid.UUID,
    transcript: str,
    audio_b64: Optional[str],
    mime_type: Optional[str],
    template: Dict[str, Any],
    session: Dict[str, Any],
):
    """
    Fast path: Just call perform_template_extraction (handles everything).

    This function runs in background. It:
    1. Schedules emotion extraction if audio available
    2. Calls perform_template_extraction which handles:
       - Extract insights with Gemini
       - Save to medical_extractions
       - Schedule triage generation (if enabled)
       - Schedule consultation insights (if enabled)
       - Send webhook (if extraction_mode is 'full')
    """
    start_time = time.time()

    try:
        await asyncio.to_thread(
            update_job_progress, submission_id, "EXTRACTING", 30, "Starting extraction from existing transcript"
        )

        # Decode audio for emotion analysis (optional)
        audio_bytes = base64.b64decode(audio_b64) if audio_b64 else None

        # Pre-generate extraction_id for parallel emotion analysis
        extraction_id = uuid.uuid4()

        # Schedule emotion extraction (if audio available AND enabled for consultation type)
        # This is fire-and-forget - runs in background
        if audio_bytes:
            consultation_type_id = session.get('consultation_type_id') or template.get('consultation_type_id')
            if consultation_type_id:
                try:
                    # Check if emotion analysis is enabled for this consultation type (fresh DB lookup)
                    ct_uuid = uuid.UUID(consultation_type_id) if isinstance(consultation_type_id, str) else consultation_type_id
                    ct_data = get_consultation_type_by_id(ct_uuid)
                    enable_emotion = ct_data.get('enable_emotion_analysis', False) if ct_data else False

                    if enable_emotion:
                        asyncio.create_task(
                            schedule_combined_emotion_extraction(
                                audio_content=audio_bytes,
                                audio_mime_type=mime_type,
                                transcript=transcript,
                                extraction_id=extraction_id,
                                consultation_type_id=ct_uuid,
                                template_id=template.get('id'),
                                session_id=str(session_id),
                                doctor_id=session.get('doctor_id'),
                            )
                        )
                        logger.debug(f"[REPROCESS] Started combined emotion analysis in background")
                    else:
                        logger.debug(f"[REPROCESS] Emotion analysis disabled for consultation type, skipping")
                except Exception as e:
                    logger.warning(f"[REPROCESS] Failed to start emotion analysis: {e}")
                    # Continue - emotion failure is non-fatal

        await asyncio.to_thread(
            update_job_progress, submission_id, "EXTRACTING", 50, "Extracting medical insights"
        )

        # Get extraction model from session or use default
        extraction_model = session.get('extraction_model', 'gemini-2.5-flash')

        # Call perform_template_extraction - handles triage, insights internally
        result = await perform_template_extraction(
            transcript=transcript,
            session_id=session_id,
            extraction_model=extraction_model,
            submission_id=submission_id,
            audio_content=audio_bytes,
            audio_mime_type=mime_type,
            session_data=session,
            extraction_id=extraction_id,
            # No timing metrics for reprocess (no stitching/transcription time)
        )

        extraction_time = time.time() - start_time

        if result:
            # Send webhook if extraction_mode is 'full' (unless realtime is enabled)
            extraction_mode = result.get('session_info', {}).get('extraction_mode')
            if extraction_mode == 'full':
                # Check if realtime is enabled (skip webhook if so)
                from services.realtime_publisher_service import is_realtime_enabled_for_hospital
                from services.supabase_service import get_doctor_hospital_id_cached
                _doctor_id = session.get('doctor_id')
                _hospital_id = get_doctor_hospital_id_cached(uuid.UUID(_doctor_id)) if _doctor_id else None
                if _hospital_id and is_realtime_enabled_for_hospital(_hospital_id):
                    logger.debug(f"[REPROCESS:WEBHOOK] Skipping webhook - realtime subscription enabled for hospital")
                else:
                    # Inject preferred_language into session_info for webhook
                    _webhook_metadata = result.get('session_info', {})
                    _rp_patient_id = session.get('patient_id')
                    if _rp_patient_id and 'preferred_language' not in _webhook_metadata:
                        try:
                            from services.supabase_service import supabase as _sb
                            _plr = _sb.table("patients").select("preferred_language").eq("id", _rp_patient_id).limit(1).execute()
                            if _plr.data:
                                _webhook_metadata["preferred_language"] = _plr.data[0].get("preferred_language")
                        except Exception:
                            pass

                    logger.debug(f"[REPROCESS:WEBHOOK] Sending webhook for reprocess (extraction_mode=full)")
                    webhook_success = await send_insights_webhook(
                        insights=result.get('data'),
                        metadata=_webhook_metadata,
                        source='reprocess'
                    )
                    if webhook_success:
                        logger.debug(f"[REPROCESS:WEBHOOK] Webhook sent successfully")
                    else:
                        logger.error(f"[REPROCESS:WEBHOOK] Webhook failed")
            else:
                logger.debug(f"[REPROCESS:WEBHOOK] Skipping webhook - extraction_mode is '{extraction_mode}', not 'full'")

            await asyncio.to_thread(
                update_job_progress,
                submission_id,
                "COMPLETED",
                100,
                "Reprocessing complete",
                transcript=transcript,
                insights=result.get('data'),
                extraction_id=str(extraction_id),
                extraction_time_seconds=extraction_time,
                total_processing_time_seconds=extraction_time,
            )
            logger.info(
                f"[REPROCESS] Transcript reprocessing complete for session {session_id} "
                f"in {extraction_time:.2f}s"
            )
        else:
            await asyncio.to_thread(
                update_job_progress,
                submission_id,
                "COMPLETED",
                100,
                "Reprocessing complete (TRANSCRIPT_ONLY mode)",
                transcript=transcript,
            )

    except Exception as e:
        logger.error(f"[REPROCESS] Failed to reprocess transcript for session {session_id}: {e}", exc_info=True)
        from services.error_utils import sanitize_error_message
        sanitized = sanitize_error_message(str(e))
        await asyncio.to_thread(
            update_job_progress,
            submission_id,
            "ERROR",
            0,
            f"Reprocessing failed: {sanitized}",
            error_message=sanitized,
        )
        # Send error webhook to notify EHR systems
        try:
            from services.webhook_service import send_error_webhook
            await send_error_webhook(
                error_message=sanitized,
                session_id=str(session_id),
                submission_id=str(submission_id),
                session_data=session,
                source="reprocess",
                error_code="REPROCESS_FAILED",
            )
        except Exception as webhook_err:
            logger.warning(f"[REPROCESS:WEBHOOK] Failed to send error webhook: {webhook_err}")

        # Publish error to realtime_extraction_responses (for EHR Realtime subscribers)
        try:
            from services.realtime_publisher_service import publish_error_response_fire_and_forget
            from services.supabase_service import get_doctor_hospital_id_cached
            _doctor_id = session.get("doctor_id") if session else None
            _hospital_id = get_doctor_hospital_id_cached(uuid.UUID(_doctor_id)) if _doctor_id else None
            if _hospital_id and submission_id:
                asyncio.create_task(publish_error_response_fire_and_forget(
                    submission_id=str(submission_id),
                    hospital_id=_hospital_id,
                    doctor_id=_doctor_id,
                    error_message=sanitized,
                    error_code="REPROCESS_FAILED",
                    session_id=str(session_id),
                ))
        except Exception as rt_err:
            logger.warning(f"[REPROCESS:REALTIME] Failed to schedule error publish: {rt_err}")


async def _transcribe_segments_from_chunks(
    chunks: list,
    session_id: str,
    doctor_id: Optional[str],
    transcription_model: str,
    mime_type: str,
) -> tuple:
    """
    Segment-based transcription from raw chunks.

    Groups chunks into segments based on cumulative duration, stitches each
    segment, and transcribes all segments in parallel. Combines transcripts
    with overlap deduplication.

    Returns:
        Tuple of (combined_transcript, detected_language)
    """
    from services.audio_splitter import stitch_and_get_bytes_for_chunk_range
    from services.transcript_combiner import combine_transcripts
    from services.audio_stitcher import get_audio_duration_estimate
    from services.audio_storage_service import normalize_audio_mime_type
    from services.segment_transcription_store import (
        DEFAULT_OVERLAP_CHUNKS,
        MAX_SEGMENT_SECONDS,
        SEGMENT_BYTE_BUDGET,
    )

    sorted_chunks = sorted(chunks, key=lambda x: x.get("chunk_index", 0))

    # Build segment ranges using the same policy as live recording: fire a
    # boundary on cumulative bytes (keeps each segment under Gemini's 15MB
    # inline cap) OR cumulative duration (sanity ceiling for low-bitrate
    # audio that would never trip the byte budget). Pure duration-based
    # segmentation could produce a segment >15MB on high-bitrate input,
    # which is precisely the regime that motivated segment-pipeline
    # existence.
    segment_ranges = []
    cumulative_dur = 0
    cumulative_bytes_since_boundary = 0
    cumulative_dur_since_boundary = 0
    seg_start = 0

    for i, chunk in enumerate(sorted_chunks):
        chunk_dur = chunk.get("duration_seconds") or 0
        # Decoded byte size; base64 inflates by ~33%, so compressed bytes ≈ b64_len * 3/4
        audio_b64_len = len(chunk.get("audio_data", ""))
        chunk_bytes = int(audio_b64_len * 3 / 4)
        if chunk_dur == 0:
            chunk_dur = chunk_bytes / 16000  # ~16KB/s for compressed audio
        cumulative_dur += chunk_dur
        cumulative_bytes_since_boundary += chunk_bytes
        cumulative_dur_since_boundary += chunk_dur

        # Boundary fires when EITHER the byte budget is hit (12MB target keeps
        # 3MB margin under Gemini's 15MB inline cap) OR the duration ceiling
        # is reached. Mirrors segment_transcription_store's live-segmentation
        # policy.
        crossed_byte_budget = cumulative_bytes_since_boundary >= SEGMENT_BYTE_BUDGET
        crossed_duration_ceiling = cumulative_dur_since_boundary >= MAX_SEGMENT_SECONDS
        if (crossed_byte_budget or crossed_duration_ceiling) and i < len(sorted_chunks) - 1:
            segment_ranges.append((seg_start, i))
            seg_start = max(0, i - DEFAULT_OVERLAP_CHUNKS + 1)
            cumulative_bytes_since_boundary = 0
            cumulative_dur_since_boundary = 0

    # Add final segment
    if sorted_chunks:
        segment_ranges.append((seg_start, len(sorted_chunks) - 1))

    logger.info(
        f"[REPROCESS:SEGMENT] Split {len(sorted_chunks)} chunks into "
        f"{len(segment_ranges)} segments (total ~{cumulative_dur:.0f}s, "
        f"budget=12MB/{MAX_SEGMENT_SECONDS}s per segment)"
    )

    # Stitch and transcribe segments with stagger delay to avoid API rate limiting.
    # In live recording, segments naturally fire 15-20 min apart.
    # For reprocess, we add a small delay between launches.
    SEGMENT_STAGGER_SECONDS = 5

    tasks = []
    for seg_idx, (start, end) in enumerate(segment_ranges):
        start_chunk_idx = sorted_chunks[start].get("chunk_index", start)
        end_chunk_idx = sorted_chunks[end].get("chunk_index", end)

        audio_bytes, seg_mime = stitch_and_get_bytes_for_chunk_range(
            sorted_chunks, start_chunk_idx, end_chunk_idx
        )
        seg_mime = normalize_audio_mime_type(seg_mime)

        logger.debug(
            f"[REPROCESS:SEGMENT] Segment {seg_idx}: chunks {start_chunk_idx}-{end_chunk_idx} "
            f"({len(audio_bytes)} bytes)"
        )

        task = asyncio.create_task(
            transcribe_audio(
                audio_content=audio_bytes,
                mime_type=seg_mime,
                model=transcription_model,
                target_language="English",
                session_id=session_id,
                doctor_id=doctor_id,
                audio_duration_seconds=len(audio_bytes) / 16000,
            )
        )
        tasks.append(task)

        # Stagger segment launches to avoid Gemini API rate limiting
        if seg_idx < len(segment_ranges) - 1:
            await asyncio.sleep(SEGMENT_STAGGER_SECONDS)

    # Wait for all transcriptions
    results = await asyncio.gather(*tasks, return_exceptions=True)

    transcripts = []
    detected_language = None
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[REPROCESS:SEGMENT] Segment {i} transcription failed: {result}")
            continue
        seg_transcript, seg_lang = result
        transcripts.append(seg_transcript)
        if seg_lang:
            detected_language = seg_lang

    if not transcripts:
        raise ValueError("All segment transcriptions failed during reprocess")

    combined = combine_transcripts(transcripts)
    logger.info(
        f"[REPROCESS:SEGMENT] Combined {len(transcripts)} segment transcripts "
        f"({len(combined)} chars)"
    )
    return combined, detected_language


async def _reprocess_full_pipeline(
    session_id: uuid.UUID,
    submission_id: uuid.UUID,
    audio_b64: str,
    mime_type: str,
    template: Dict[str, Any],
    session: Dict[str, Any],
    is_abandoned: bool = False,
    skip_transcription: bool = False,
    raw_chunks: Optional[list] = None,
):
    """
    Full path: Transcribe + Extract using existing functions.

    This function runs in background. It:
    1. Decodes base64 audio to bytes
    2. Transcribes using transcribe_audio() (or skips if skip_transcription=True)
       - For long audio with raw_chunks: segments chunks, transcribes in parallel
       - For long audio without chunks: splits with FFmpeg, transcribes in parallel
    3. Updates status to SUBMITTED if abandoned recording (after transcription)
    4. Schedules emotion extraction (parallel, fire-and-forget)
    5. Calls perform_template_extraction
    6. Sends webhook (if extraction_mode is 'full')

    Args:
        is_abandoned: If True, previously abandoned recording (status=RECORDING).
        skip_transcription: If True, extract directly from audio (no transcription).
        raw_chunks: Raw audio chunks for segmented transcription (when no full audio).
    """
    start_time = time.time()

    try:
        # 1. Decode base64 audio to bytes
        await asyncio.to_thread(
            update_job_progress, submission_id, "STITCHING", 10, "Preparing audio for transcription"
        )
        audio_bytes = base64.b64decode(audio_b64)
        logger.debug(f"[REPROCESS] Decoded audio: {len(audio_bytes)} bytes, mime_type={mime_type}")

        # Container-decodability gate. Same protection as main pipeline — catches
        # the case where stored bytes are large but unparseable (e.g. session
        # 9b32f2da: 28MB / 0.04s decoded). Without this, reprocess wastes a
        # Gemini call and surfaces an opaque INVALID_ARGUMENT.
        from services.audio_quality_service import (
            fast_container_duration_seconds,
            PROBE_PARSEABLE_NO_DURATION,
        )
        _CONTAINER_PROBE_MIN_BYTES = 100_000
        _CONTAINER_PROBE_MIN_DURATION = 1.0
        if len(audio_bytes) >= _CONTAINER_PROBE_MIN_BYTES:
            _decoded_dur = await asyncio.to_thread(
                fast_container_duration_seconds, audio_bytes, mime_type
            )
            # Only flag corruption when ffprobe returned a real (positive)
            # duration that is pathologically short. The
            # PROBE_PARSEABLE_NO_DURATION sentinel (< 0) means parseable but
            # missing duration metadata (MediaRecorder WebM) — proceed silently.
            if _decoded_dur is not None and 0.0 <= _decoded_dur < _CONTAINER_PROBE_MIN_DURATION:
                raise ValueError(
                    f"Audio container is corrupted: "
                    f"{len(audio_bytes) / 1024 / 1024:.1f}MB file decodes to only "
                    f"{_decoded_dur:.2f}s. Stored audio cannot be transcribed — "
                    f"please re-record."
                )
            if _decoded_dur is None:
                logger.warning(
                    f"[REPROCESS] ffprobe could not parse "
                    f"{len(audio_bytes) // 1024}KB file ({mime_type}). Proceeding "
                    f"to Gemini, but expect possible INVALID_ARGUMENT."
                )

        # Determine if segmented transcription will be used
        from services.segment_transcription_store import SPLIT_TRANSCRIPTION_THRESHOLD_SECONDS
        audio_duration = float(session.get('total_duration_seconds') or 0) or len(audio_bytes) / 16000
        _use_segmented = (raw_chunks and len(raw_chunks) > 0 and audio_duration > SPLIT_TRANSCRIPTION_THRESHOLD_SECONDS)

        # Silence removal (same as main pipeline)
        # Skipped for segmented path: raw chunk bytes lack audio container headers
        # (ffmpeg can't decode them), and emotion analysis needs original audio.
        silence_stats = {}

        if _use_segmented:
            logger.info("[REPROCESS] Skipping silence removal (segmented path active)")
            silence_stats = {"removed": False, "reason": "segmented path active"}
        else:
            from services.audio_silence_remover import MIN_SIZE_FOR_SILENCE_REMOVAL_BYTES
            _skip_silence = len(audio_bytes) < MIN_SIZE_FOR_SILENCE_REMOVAL_BYTES
            if _skip_silence:
                logger.info(
                    f"[REPROCESS] Skipping silence removal: audio size {len(audio_bytes) // 1024}KB "
                    f"below 15min threshold ({MIN_SIZE_FOR_SILENCE_REMOVAL_BYTES // 1024}KB)"
                )
                silence_stats = {
                    "removed": False,
                    "reason": f"file size below 15min threshold ({len(audio_bytes) // 1024}KB)",
                }
            else:
                try:
                    processed_bytes, mime_type, silence_stats = await asyncio.to_thread(
                        remove_silence_from_audio,
                        audio_bytes, mime_type,
                    )
                    if silence_stats.get("removed"):
                        audio_bytes = processed_bytes
                        audio_b64 = base64.b64encode(processed_bytes).decode("utf-8")
                        logger.info(
                            f"[REPROCESS] Silence removed: {silence_stats['silence_removed_pct']}% "
                            f"({silence_stats['original_duration_ms']}ms -> {silence_stats['new_duration_ms']}ms)"
                        )
                except Exception as e:
                    logger.warning(f"[REPROCESS] Silence removal failed, using original audio: {e}")
                    silence_stats = {}

        # Early abort checks — only for non-segmented path
        if not _use_segmented:
            if silence_stats.get("all_silent"):
                raise ValueError(
                    "Recording is entirely silent — no speech detected."
                )
            if silence_stats.get("too_short_after_removal"):
                raise ValueError(
                    f"After removing silence, only {silence_stats.get('would_be_duration_ms', 0) / 1000:.1f}s "
                    f"of speech detected (minimum: 10s)."
                )

        # ============================================================================
        # BRANCH: Skip Transcription Mode (Direct Audio Extraction)
        # Includes all 5 prompt injections (same as normal pipeline):
        # 1. Medicine list, 2. Investigation list, 3. Caution/Warnings,
        # 4. Past prescriptions, 5. Past summaries
        # ============================================================================
        if skip_transcription:
            logger.debug(f"[REPROCESS:SKIP_TRANSCRIPTION] Direct audio extraction mode enabled")

            await asyncio.to_thread(
                update_job_progress, submission_id, "EXTRACTING", 40, "Extracting insights directly from audio (no transcription)"
            )

            # Get pre-assembled prompt and schema from template
            from services.supabase_service import get_template_assembled_data
            template_code = session.get('template_code') or template.get('template_code')
            template_data = get_template_assembled_data(template_code)

            if not template_data:
                raise ValueError("Template not found or missing required configuration")

            extract_start = time.time()
            extraction_model = session.get('extraction_model', 'gemini-2.0-flash')
            doctor_id = session.get('doctor_id')
            patient_id = session.get('patient_id')

            # Check list availability (same as normal pipeline)
            list_availability = {"has_medicine_list": False, "has_investigation_list": False}
            if doctor_id:
                try:
                    from services.extraction_service import check_list_availability_parallel
                    doctor_uuid = uuid.UUID(doctor_id) if isinstance(doctor_id, str) else doctor_id
                    list_availability = await check_list_availability_parallel(doctor_uuid)
                    logger.debug(
                        f"[REPROCESS:SKIP_TRANSCRIPTION] List availability: medicine={list_availability.get('has_medicine_list')}, "
                        f"investigation={list_availability.get('has_investigation_list')}"
                    )
                except Exception as e:
                    logger.warning(f"[REPROCESS:SKIP_TRANSCRIPTION] Failed to check list availability: {e}")

            # Estimate audio duration from size (~16KB/s for compressed audio)
            estimated_duration = len(audio_bytes) / 16000

            insights_result = await extract_insights_from_audio_direct(
                audio_content=audio_bytes,
                mime_type=mime_type,
                system_prompt=template_data['assembled_full_prompt'],
                response_schema=template_data['assembled_schema_json'],
                model=extraction_model,
                session_id=str(session_id),
                doctor_id=doctor_id,
                patient_id=patient_id,
                has_medicine_list=list_availability.get("has_medicine_list", False),
                has_investigation_list=list_availability.get("has_investigation_list", False),
                audio_duration_seconds=estimated_duration,
                template_code=template_code,
            )

            insights = insights_result.get("data", {})
            transcript = None  # No transcription
            transcription_time = 0
            extraction_time = time.time() - extract_start

            logger.debug(
                f"[REPROCESS:SKIP_TRANSCRIPTION] Direct extraction completed: "
                f"{extraction_time:.2f}s (model: {extraction_model})"
            )

            # Generate extraction_id (needed for post-processing)
            extraction_id = uuid.uuid4()

            # ============================================================================
            # POST-PROCESSING: Medicine and Investigation matching (same as normal pipeline)
            # ============================================================================
            doctor_uuid = uuid.UUID(doctor_id) if doctor_id and isinstance(doctor_id, str) else doctor_id

            # Medicine post-processing
            if doctor_uuid and isinstance(insights, dict) and list_availability.get("has_medicine_list"):
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

                    logger.debug(f"[REPROCESS:SKIP_TRANSCRIPTION] Running medicine post-processing")
                    insights = await postprocess_prescription_extraction(
                        extraction_data=insights,
                        doctor_id=doctor_uuid,
                        extraction_id=extraction_id,
                        submission_id=str(submission_id),
                        diagnosis=diagnosis,
                        template_id=None,
                        log_matches=True
                    )
                    logger.info(f"[TIMING_POSTPROCESS] Medicine post-processing: {time.time() - postprocess_start:.3f}s")
                except Exception as e:
                    logger.warning(f"[REPROCESS:SKIP_TRANSCRIPTION] Medicine post-processing failed (non-fatal): {e}")

            # Investigation post-processing
            if doctor_uuid and isinstance(insights, dict) and list_availability.get("has_investigation_list"):
                try:
                    postprocess_start = time.time()
                    from services.investigation_service import postprocess_investigations_extraction

                    logger.debug(f"[REPROCESS:SKIP_TRANSCRIPTION] Running investigation post-processing")
                    insights = await postprocess_investigations_extraction(
                        extraction_data=insights,
                        doctor_id=doctor_uuid,
                        extraction_id=extraction_id,
                        submission_id=str(submission_id),
                        template_id=None,
                        log_matches=True
                    )
                    logger.info(f"[TIMING_POSTPROCESS] Investigation post-processing: {time.time() - postprocess_start:.3f}s")
                except Exception as e:
                    logger.warning(f"[REPROCESS:SKIP_TRANSCRIPTION] Investigation post-processing failed (non-fatal): {e}")

            # Save extraction to database
            from services.supabase_service import supabase
            extraction_record = {
                "id": str(extraction_id),
                "session_id": str(session_id),
                "consultation_type_id": session.get("consultation_type_id"),
                "doctor_id": doctor_id,
                "patient_id": patient_id,
                "transcript_text": None,  # No transcript
                "original_extraction_json": insights,
                "model_used": extraction_model,
                "extraction_mode": session.get("extraction_mode", "full"),
                "segment_count": len(insights) if isinstance(insights, dict) else 0,
                "submission_id": str(submission_id),
                "transcription_time_seconds": 0,
                "extraction_time_seconds": extraction_time,
                "total_processing_time_seconds": extraction_time,
            }

            await asyncio.to_thread(
                lambda: supabase.table("medical_extractions").insert(extraction_record).execute()
            )
            logger.debug(f"[REPROCESS:SKIP_TRANSCRIPTION] Saved extraction {extraction_id}")

            # Publish to realtime table (fire-and-forget)
            try:
                from services.realtime_publisher_service import publish_extraction_response_fire_and_forget
                from services.supabase_service import get_doctor_hospital_id_cached
                hospital_id_for_realtime = get_doctor_hospital_id_cached(uuid.UUID(doctor_id)) if doctor_id else None
                if hospital_id_for_realtime and submission_id:
                    # Look up UHID from patients table
                    _reprocess_uhid = ""
                    if patient_id:
                        try:
                            _p_result = supabase.table("patients").select("patient_id").eq("id", patient_id).limit(1).execute()
                            if _p_result.data:
                                _reprocess_uhid = _p_result.data[0].get("patient_id", "")
                        except Exception:
                            pass
                    asyncio.create_task(publish_extraction_response_fire_and_forget(
                        submission_id=str(submission_id),
                        hospital_id=hospital_id_for_realtime,
                        doctor_id=doctor_id,
                        extraction_id=str(extraction_id),
                        insights=insights,
                        recording_metadata=session.get("recording_metadata_json") if session else None,
                        uhid=_reprocess_uhid,
                    ))
            except Exception as e:
                logger.warning(f"[REPROCESS:SKIP_TRANSCRIPTION] Failed to schedule realtime publish: {e}")

            # ============================================================================
            # SCHEDULE BACKGROUND TASKS: Audio-only emotion + Triage (if enabled)
            # Note: Consultation insights requires transcript, so it's skipped
            # ============================================================================
            consultation_type_id = session.get("consultation_type_id")
            template_id_for_audio = None

            # Get template_id for audio emotion prompts
            if template_code and doctor_id:
                from services.supabase_service import get_active_template_by_code_cached
                template = get_active_template_by_code_cached(uuid.UUID(doctor_id), template_code)
                if template:
                    template_id_for_audio = str(template.get("id"))

            # Schedule AUDIO-ONLY emotion extraction (if emotion analysis is enabled)
            if consultation_type_id and template_id_for_audio:
                try:
                    from services.background_tasks import schedule_audio_only_emotion_extraction
                    from services.supabase_service import is_emotion_analysis_enabled

                    if is_emotion_analysis_enabled(uuid.UUID(consultation_type_id)):
                        logger.debug(f"[REPROCESS:SKIP_TRANSCRIPTION] Scheduling audio-only emotion extraction")
                        await schedule_audio_only_emotion_extraction(
                            audio_content=audio_bytes,
                            audio_mime_type=mime_type,
                            extraction_id=extraction_id,
                            consultation_type_id=uuid.UUID(consultation_type_id),
                            template_id=template_id_for_audio,
                            session_id=str(session_id),
                            doctor_id=doctor_id,
                        )
                    else:
                        logger.debug(f"[REPROCESS:SKIP_TRANSCRIPTION] Emotion analysis disabled for this consultation type")
                except Exception as e:
                    logger.warning(f"[REPROCESS:SKIP_TRANSCRIPTION] Failed to schedule audio emotion (non-fatal): {e}")

            # Schedule TRIAGE generation (works without transcript - uses extraction JSON + RPC)
            if consultation_type_id:
                try:
                    from services.background_tasks import schedule_triage_generation
                    from services.supabase_service import is_triage_analysis_enabled

                    if is_triage_analysis_enabled(uuid.UUID(consultation_type_id)):
                        logger.debug(f"[REPROCESS:SKIP_TRANSCRIPTION] Scheduling triage generation (uses extraction JSON)")
                        await schedule_triage_generation(
                            extraction_id=extraction_id,
                            transcript=None,  # No transcript in skip_transcription mode
                            extraction_data={"original_extraction_json": insights},
                            doctor_id=doctor_id,
                            patient_id=patient_id,
                            consultation_type_code=template_code,
                            include_gemini=False,  # Rule-based only for speed
                            enable_consultation_insights=False,  # Requires transcript
                        )
                    else:
                        logger.debug(f"[REPROCESS:SKIP_TRANSCRIPTION] Triage analysis disabled for this consultation type")
                except Exception as e:
                    logger.warning(f"[REPROCESS:SKIP_TRANSCRIPTION] Failed to schedule triage (non-fatal): {e}")

            # Consultation insights SKIPPED - requires transcript
            logger.debug(f"[REPROCESS:SKIP_TRANSCRIPTION] Consultation insights skipped (requires transcript)")

            # Send webhook for skip_transcription success (if extraction_mode is 'full')
            extraction_mode = session.get("extraction_mode", "full")
            if extraction_mode == 'full':
                try:
                    from services.realtime_publisher_service import is_realtime_enabled_for_hospital
                    from services.supabase_service import get_doctor_hospital_id_cached
                    from datetime import datetime

                    # Lookup patient preferred_language
                    _reprocess_preferred_lang = None
                    if patient_id:
                        try:
                            from services.supabase_service import supabase as _sb
                            _plr = _sb.table("patients").select("preferred_language").eq("id", patient_id).limit(1).execute()
                            if _plr.data:
                                _reprocess_preferred_lang = _plr.data[0].get("preferred_language")
                        except Exception:
                            pass

                    standardized_metadata = {
                        "correlation_id": session.get('correlation_id'),
                        "submission_id": str(submission_id),
                        "extraction_id": str(extraction_id),
                        "session_id": str(session_id),
                        "doctor_id": doctor_id,
                        "patient_id": patient_id,
                        "template_code": template_code,
                        "mode": extraction_mode,
                        "segment_count": len(insights) if isinstance(insights, dict) else 0,
                        "processing_mode": session.get('processing_mode'),
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "preferred_language": _reprocess_preferred_lang,
                    }

                    _hospital_id = get_doctor_hospital_id_cached(uuid.UUID(doctor_id)) if doctor_id else None
                    if _hospital_id and is_realtime_enabled_for_hospital(_hospital_id):
                        logger.debug(f"[REPROCESS:SKIP_TRANSCRIPTION:WEBHOOK] Skipping webhook - realtime enabled")
                    else:
                        await send_insights_webhook(
                            insights=insights,
                            metadata=standardized_metadata,
                            source='reprocess',
                        )
                        logger.info(f"[REPROCESS:SKIP_TRANSCRIPTION:WEBHOOK] Success webhook sent")
                except Exception as webhook_err:
                    logger.warning(f"[REPROCESS:SKIP_TRANSCRIPTION:WEBHOOK] Failed to send webhook: {webhook_err}")

            total_time = time.time() - start_time

            # Update job to completed
            await asyncio.to_thread(
                update_job_progress,
                submission_id,
                "COMPLETED",
                100,
                "Reprocessing complete (direct audio extraction)",
                transcript=None,
                insights=insights,
                extraction_id=str(extraction_id),
                extraction_time_seconds=extraction_time,
                total_processing_time_seconds=total_time,
            )
            logger.info(
                f"[REPROCESS:SKIP_TRANSCRIPTION] Complete for session {session_id} "
                f"in {total_time:.2f}s"
            )
            return  # Exit early - skip normal path

        # ============================================================================
        # NORMAL PATH: Transcription + Extraction
        # ============================================================================

        # 2. Transcribe using existing function
        await asyncio.to_thread(
            update_job_progress, submission_id, "TRANSCRIBING", 30, "Transcribing audio"
        )
        transcription_start = time.time()

        transcription_model = session.get('transcription_model', 'gemini-2.5-flash')
        doctor_id_for_transcribe = session.get('doctor_id')

        # Fire-and-forget language detection in parallel with transcription. Uses
        # the first ~2 chunks when available (small, valid WebM) or falls back
        # to the full stitched audio. Zero latency impact.
        try:
            if raw_chunks:
                _preview_chunks = raw_chunks[: min(2, len(raw_chunks))]
                _preview_bytes = b"".join(
                    base64.b64decode(c.get("audio_data", "")) for c in _preview_chunks
                )
            else:
                _preview_bytes = audio_bytes
            if _preview_bytes:
                _patient_id_for_lang = session.get("patient_id")

                async def _detect_language_bg_reprocess(
                    audio=_preview_bytes,
                    mime=mime_type,
                    sid=str(session_id),
                    did=doctor_id_for_transcribe,
                    pid=_patient_id_for_lang,
                ):
                    try:
                        from services.gemini_service import detect_language_from_audio
                        lang = await detect_language_from_audio(
                            audio_content=audio,
                            mime_type=mime,
                            session_id=sid,
                            doctor_id=did,
                        )
                        if lang and pid:
                            from services.supabase_service import update_patient_preferred_language
                            await asyncio.to_thread(
                                update_patient_preferred_language, pid, lang
                            )
                    except Exception as e:
                        logger.warning(f"[REPROCESS:LANG_DETECT] Background detection failed: {e}")

                asyncio.create_task(_detect_language_bg_reprocess())
        except Exception as e:
            logger.warning(f"[REPROCESS:LANG_DETECT] Failed to schedule detection: {e}")

        # _use_segmented already computed before silence removal (uses audio_duration)

        # Override processing mode to 'thorough' for long audio
        if _use_segmented:
            original_mode = session.get('processing_mode', 'default')
            if original_mode != 'thorough':
                session['processing_mode'] = 'thorough'
                logger.info(
                    f"[REPROCESS] Long audio detected — overriding processing_mode "
                    f"from '{original_mode}' to 'thorough'"
                )

        if _use_segmented:
            # SEGMENTED PATH: Transcribe from chunks in parallel segments
            logger.info(
                f"[REPROCESS:SEGMENT] Using segmented transcription from {len(raw_chunks)} chunks "
                f"(duration ~{audio_duration:.0f}s)"
            )
            await asyncio.to_thread(
                update_job_progress, submission_id, "TRANSCRIBING", 35,
                f"Splitting {len(raw_chunks)} chunks for parallel transcription"
            )

            transcript, detected_language = await _transcribe_segments_from_chunks(
                chunks=raw_chunks,
                session_id=str(session_id),
                doctor_id=doctor_id_for_transcribe,
                transcription_model=transcription_model,
                mime_type=mime_type,
            )

        else:
            # NORMAL PATH: Single transcription (short audio or full audio without chunks)
            transcript, detected_language = await transcribe_audio(
                audio_content=audio_bytes,
                mime_type=mime_type,
                model=transcription_model,
                session_id=str(session_id),
                doctor_id=doctor_id_for_transcribe,
                audio_duration_seconds=audio_duration,
            )

        transcription_time = time.time() - transcription_start
        logger.debug(f"[REPROCESS] Transcription complete in {transcription_time:.2f}s")

        # 2a. Validate transcript for Gemini output issues (NO_SPEECH_DETECTED, hallucinations, too short)
        # Permissive on audio quality, strict on Gemini garbage output
        transcript_length = len(transcript.strip()) if transcript else 0
        min_transcript_length = 20
        if transcript_length < min_transcript_length:
            raise ValueError(
                f"Transcription validation failed: Transcript too short ({transcript_length} chars). "
                f"Audio may be empty, silent, or contain no speech. "
                f"Minimum required: {min_transcript_length} chars."
            )

        if transcript:
            transcript_upper = transcript.strip().upper()
            transcript_lower = transcript.strip().lower()

            # Check for Gemini error markers
            if "[NO_SPEECH_DETECTED]" in transcript_upper:
                raise ValueError(
                    "Transcription validation failed: AI service reported [NO_SPEECH_DETECTED]. "
                    "Audio appears to be empty, corrupted, or contains no speech."
                )

            # Check for Gemini error phrases
            gemini_error_phrases = [
                "i cannot process audio",
                "i'm sorry, but i cannot",
                "i am sorry, but i cannot",
                "unable to process the audio",
                "no audio content",
                "audio file is empty",
            ]
            for phrase in gemini_error_phrases:
                if phrase in transcript_lower:
                    raise ValueError(
                        "Transcription validation failed: AI service could not process audio. "
                        "Audio appears to be empty or corrupted."
                    )

            # Check for known hallucination patterns (Smith conversations)
            hallucination_patterns = [
                "mr. smith", "mr smith", "dr. smith",
                "dr smith", "mrs. smith", "mrs smith",
            ]
            for pattern in hallucination_patterns:
                if pattern in transcript_lower:
                    raise ValueError(
                        f"Transcription validation failed: Detected likely hallucination "
                        f"('{pattern}' found in transcript). Audio may be empty or corrupted."
                    )

        # Language detection is now handled by the separate detect_language_from_audio
        # fire-and-forget task scheduled before transcription (above). transcribe_audio
        # no longer emits [DETECTED_LANG:...] tags, so detected_language from it is None.
        patient_id = session.get('patient_id')

        # Fire-and-forget: persist transcript to processing_jobs.transcript so it survives
        # extraction failures. get_session_transcript() reads this column first.
        if transcript:
            try:
                asyncio.create_task(
                    asyncio.to_thread(
                        update_job_progress,
                        submission_id,
                        "TRANSCRIBING",
                        60,
                        "Transcription persisted",
                        transcript=transcript,
                    )
                )
            except Exception as e:
                logger.warning(f"[REPROCESS:TRANSCRIPT_PERSIST] Failed to schedule transcript save: {e}")

        # 2b. For abandoned recordings, update status to SUBMITTED after transcription
        if is_abandoned:
            correlation_id = session.get('correlation_id')
            if correlation_id:
                await asyncio.to_thread(
                    update_session_status, uuid.UUID(correlation_id), "SUBMITTED"
                )
                logger.debug(f"[REPROCESS] Updated abandoned recording status to SUBMITTED")

        # 3. Schedule emotion extraction (fire-and-forget, parallel) - only if enabled
        extraction_id = uuid.uuid4()
        consultation_type_id = session.get('consultation_type_id') or template.get('consultation_type_id')

        if consultation_type_id:
            try:
                # Check if emotion analysis is enabled for this consultation type (fresh DB lookup)
                ct_uuid = uuid.UUID(consultation_type_id) if isinstance(consultation_type_id, str) else consultation_type_id
                ct_data = get_consultation_type_by_id(ct_uuid)
                enable_emotion = ct_data.get('enable_emotion_analysis', False) if ct_data else False

                if enable_emotion:
                    asyncio.create_task(
                        schedule_combined_emotion_extraction(
                            audio_content=audio_bytes,
                            audio_mime_type=mime_type,
                            transcript=transcript,
                            extraction_id=extraction_id,
                            consultation_type_id=ct_uuid,
                            template_id=template.get('id'),
                            session_id=str(session_id),
                            doctor_id=session.get('doctor_id'),
                        )
                    )
                    logger.debug(f"[REPROCESS] Started combined emotion analysis in background")
                else:
                    logger.debug(f"[REPROCESS] Emotion analysis disabled for consultation type, skipping")
            except Exception as e:
                logger.warning(f"[REPROCESS] Failed to start emotion analysis: {e}")
                # Continue - emotion failure is non-fatal

        # 4. Extract using existing function
        await asyncio.to_thread(
            update_job_progress, submission_id, "EXTRACTING", 60, "Extracting medical insights"
        )
        extraction_start = time.time()

        extraction_model = session.get('extraction_model', 'gemini-2.5-flash')

        result = await perform_template_extraction(
            transcript=transcript,
            session_id=session_id,
            extraction_model=extraction_model,
            submission_id=submission_id,
            audio_content=audio_bytes,
            audio_mime_type=mime_type,
            session_data=session,
            extraction_id=extraction_id,
            transcription_time_seconds=transcription_time,
            total_processing_time_seconds=time.time() - start_time,
        )

        extraction_time = time.time() - extraction_start
        total_time = time.time() - start_time

        if result:
            # Send webhook if extraction_mode is 'full' (unless realtime is enabled)
            extraction_mode = result.get('session_info', {}).get('extraction_mode')
            if extraction_mode == 'full':
                # Check if realtime is enabled (skip webhook if so)
                from services.realtime_publisher_service import is_realtime_enabled_for_hospital
                from services.supabase_service import get_doctor_hospital_id_cached
                _doctor_id = session.get('doctor_id')
                _hospital_id = get_doctor_hospital_id_cached(uuid.UUID(_doctor_id)) if _doctor_id else None
                if _hospital_id and is_realtime_enabled_for_hospital(_hospital_id):
                    logger.debug(f"[REPROCESS:WEBHOOK] Skipping webhook - realtime subscription enabled for hospital")
                else:
                    # Inject preferred_language into session_info for webhook
                    _webhook_metadata = result.get('session_info', {})
                    _rp_patient_id = session.get('patient_id')
                    if _rp_patient_id and 'preferred_language' not in _webhook_metadata:
                        try:
                            from services.supabase_service import supabase as _sb
                            _plr = _sb.table("patients").select("preferred_language").eq("id", _rp_patient_id).limit(1).execute()
                            if _plr.data:
                                _webhook_metadata["preferred_language"] = _plr.data[0].get("preferred_language")
                        except Exception:
                            pass

                    logger.debug(f"[REPROCESS:WEBHOOK] Sending webhook for reprocess (extraction_mode=full)")
                    webhook_success = await send_insights_webhook(
                        insights=result.get('data'),
                        metadata=_webhook_metadata,
                        source='reprocess'
                    )
                    if webhook_success:
                        logger.debug(f"[REPROCESS:WEBHOOK] Webhook sent successfully")
                    else:
                        logger.error(f"[REPROCESS:WEBHOOK] Webhook failed")
            else:
                logger.debug(f"[REPROCESS:WEBHOOK] Skipping webhook - extraction_mode is '{extraction_mode}', not 'full'")

            await asyncio.to_thread(
                update_job_progress,
                submission_id,
                "COMPLETED",
                100,
                "Reprocessing complete",
                transcript=transcript,
                insights=result.get('data'),
                extraction_id=str(extraction_id),
                transcription_time_seconds=transcription_time,
                extraction_time_seconds=extraction_time,
                total_processing_time_seconds=total_time,
            )
            logger.info(
                f"[REPROCESS] Full pipeline reprocessing complete for session {session_id} "
                f"(transcription: {transcription_time:.2f}s, extraction: {extraction_time:.2f}s, "
                f"total: {total_time:.2f}s)"
            )
        else:
            await asyncio.to_thread(
                update_job_progress,
                submission_id,
                "COMPLETED",
                100,
                "Reprocessing complete (TRANSCRIPT_ONLY mode)",
                transcript=transcript,
                transcription_time_seconds=transcription_time,
                total_processing_time_seconds=total_time,
            )

    except Exception as e:
        logger.error(f"[REPROCESS] Failed full pipeline for session {session_id}: {e}", exc_info=True)
        from services.error_utils import sanitize_error_message
        sanitized = sanitize_error_message(str(e))
        await asyncio.to_thread(
            update_job_progress,
            submission_id,
            "ERROR",
            0,
            f"Reprocessing failed: {sanitized}",
            error_message=sanitized,
        )
        # Send error webhook to notify EHR systems
        try:
            from services.webhook_service import send_error_webhook
            await send_error_webhook(
                error_message=sanitized,
                session_id=str(session_id),
                submission_id=str(submission_id),
                session_data=session,
                source="reprocess",
                error_code="REPROCESS_FAILED",
            )
        except Exception as webhook_err:
            logger.warning(f"[REPROCESS:WEBHOOK] Failed to send error webhook: {webhook_err}")

        # Publish error to realtime_extraction_responses (for EHR Realtime subscribers)
        try:
            from services.realtime_publisher_service import publish_error_response_fire_and_forget
            from services.supabase_service import get_doctor_hospital_id_cached
            _doctor_id = session.get("doctor_id") if session else None
            _hospital_id = get_doctor_hospital_id_cached(uuid.UUID(_doctor_id)) if _doctor_id else None
            if _hospital_id and submission_id:
                asyncio.create_task(publish_error_response_fire_and_forget(
                    submission_id=str(submission_id),
                    hospital_id=_hospital_id,
                    doctor_id=_doctor_id,
                    error_message=sanitized,
                    error_code="REPROCESS_FAILED",
                    session_id=str(session_id),
                ))
        except Exception as rt_err:
            logger.warning(f"[REPROCESS:REALTIME] Failed to schedule error publish: {rt_err}")

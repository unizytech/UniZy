"""
Background Tasks for Extraction Pipeline

Handles asynchronous tasks that run independently of the main extraction workflow.

Architecture:
- Fire-and-forget pattern
- Triggered immediately after main extraction saves
- Non-blocking (doesn't wait for completion)
- Error-tolerant (logs and flags failures)

Features:
- Combined (multimodal) emotion extraction (single Gemini call with audio + transcript)
- Triage suggestion generation
- Consultation insights extraction
- Assessment services (severity, needs, allied health, dropoff, care quality)
- Intervention generation

Author: Claude Code
Date: 2025-11-11
Updated: 2026-01-10 (Simplified to combined-only emotion mode)
"""

import asyncio
import logging
from typing import Optional, Dict, Any
import uuid
from datetime import datetime


logger = logging.getLogger(__name__)


# ============================================================================
# Helper: Wait for Extraction to Exist
# ============================================================================

async def _wait_for_extraction_to_exist(
    extraction_id: uuid.UUID,
    max_wait_seconds: int = 60,
    poll_interval: float = 2.0,
) -> bool:
    """
    Wait for an extraction to exist in extractions table.

    This handles the race condition where parallel emotion analysis completes
    before the main extraction is saved to the database.

    Args:
        extraction_id: UUID of the extraction to wait for
        max_wait_seconds: Maximum time to wait (default 60s)
        poll_interval: Time between checks (default 2s)

    Returns:
        True if extraction exists, False if timed out
    """
    from services.supabase_service import supabase

    waited = 0.0
    while waited < max_wait_seconds:
        try:
            result = supabase.table("extractions").select("id").eq("id", str(extraction_id)).limit(1).execute()
            if result.data and len(result.data) > 0:
                logger.debug(f"[EMOTION:WAIT] Extraction exists after {waited:.1f}s wait")
                return True
        except Exception as e:
            logger.warning(f"[EMOTION:WAIT] Error checking extraction existence: {e}")

        await asyncio.sleep(poll_interval)
        waited += poll_interval

    logger.warning(f"[EMOTION:WAIT] Timed out waiting for extraction_id={extraction_id} after {max_wait_seconds}s")
    return False


# ============================================================================
# Helper: Wait for Emotion Segments to Exist
# ============================================================================

async def _wait_for_emotion_segments_to_exist(
    extraction_id: uuid.UUID,
    max_wait_seconds: int = 90,
    poll_interval: float = 3.0,
) -> bool:
    """
    Wait for emotion segments to exist in extraction_segments table.

    This handles the race condition where consultation insights pipeline
    runs before combined emotion extraction completes.

    Checks for any of the 7 unified emotion segment codes:
    - ANXIETY_POST_CONSULTATION
    - FINANCIAL_CONCERNS
    - OTHER_EMOTIONS_DETECTED
    - TREATMENT_COMPLIANCE_LIKELIHOOD
    - DOCTOR_COMMUNICATION_STYLE
    - INTERACTION_DYNAMICS
    - CONGRUENCE_SUMMARY

    Args:
        extraction_id: UUID of the extraction to check
        max_wait_seconds: Maximum time to wait (default 90s - emotion extraction can take 30-60s)
        poll_interval: Time between checks (default 3s)

    Returns:
        True if any emotion segment exists, False if timed out
    """
    from services.supabase_service import supabase

    # Any of these indicates emotion extraction completed
    emotion_segment_codes = [
        "ANXIETY_POST_CONSULTATION",
        "FINANCIAL_CONCERNS",
        "OTHER_EMOTIONS_DETECTED",
        "TREATMENT_COMPLIANCE_LIKELIHOOD",
        "DOCTOR_COMMUNICATION_STYLE",
        "INTERACTION_DYNAMICS",
        "CONGRUENCE_SUMMARY",
    ]

    waited = 0.0
    while waited < max_wait_seconds:
        try:
            result = (
                supabase.table("extraction_segments")
                .select("id, segment_code")
                .eq("extraction_id", str(extraction_id))
                .in_("segment_code", emotion_segment_codes)
                .limit(1)
                .execute()
            )
            if result.data and len(result.data) > 0:
                segment_found = result.data[0].get("segment_code", "unknown")
                logger.debug(
                    f"[EMOTION:WAIT] Emotion segments exist after {waited:.1f}s wait "
                    f"(found {segment_found}) for extraction_id={extraction_id}"
                )
                return True
        except Exception as e:
            logger.warning(f"[EMOTION:WAIT] Error checking emotion segments: {e}")

        await asyncio.sleep(poll_interval)
        waited += poll_interval

    logger.warning(
        f"[EMOTION:WAIT] Timed out waiting for emotion segments "
        f"for extraction_id={extraction_id} after {max_wait_seconds}s"
    )
    return False


async def _is_emotion_analysis_enabled_for_extraction(extraction_id: uuid.UUID) -> bool:
    """
    Check if emotion analysis is enabled for this extraction's consultation type.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        True if emotion analysis is enabled, False otherwise
    """
    from services.supabase_service import supabase

    try:
        # Get extraction with its consultation_type_id
        extraction_result = (
            supabase.table("extractions")
            .select("consultation_type_id")
            .eq("id", str(extraction_id))
            .limit(1)
            .execute()
        )
        if not extraction_result.data:
            return False

        consultation_type_id = extraction_result.data[0].get("consultation_type_id")
        if not consultation_type_id:
            return False

        # Check if emotion analysis is enabled for this consultation type
        ct_result = (
            supabase.table("consultation_types")
            .select("enable_emotion_analysis")
            .eq("id", consultation_type_id)
            .limit(1)
            .execute()
        )
        if not ct_result.data:
            return False

        return ct_result.data[0].get("enable_emotion_analysis", False)

    except Exception as e:
        logger.warning(f"[EMOTION:WAIT] Error checking emotion enabled: {e}")
        return False


# ============================================================================
# Combined Emotion Extraction (Public API)
# ============================================================================

async def schedule_combined_emotion_extraction(
    audio_content: bytes,
    audio_mime_type: str,
    transcript: str,
    extraction_id: uuid.UUID,
    consultation_type_id: uuid.UUID,
    template_id: str,
    session_id: Optional[str] = None,
    counsellor_id: Optional[str] = None,
):
    """
    Schedule COMBINED text+audio emotion extraction as background task.

    This is the single-call approach that analyzes both transcript text
    and audio simultaneously, outputting unified segments directly.

    Benefits over separate text/audio extraction:
    - Single Gemini API call instead of 2-3
    - No need for congruence analysis step
    - Better mismatch detection (model sees both inputs)

    Args:
        audio_content: Audio data bytes
        audio_mime_type: MIME type of audio (e.g., 'audio/webm', 'audio/mp3')
        transcript: Full consultation transcript text
        extraction_id: UUID of extraction to link to
        consultation_type_id: UUID of consultation type
        template_id: Template UUID for database-driven prompts (required)
        session_id: Optional session ID for LLM usage tracking
        counsellor_id: Optional counsellor ID for LLM usage tracking

    Returns:
        None (task runs in background)
    """
    from services.supabase_service import (
        get_consultation_type,
        is_emotion_analysis_enabled,
        update_extraction_emotion_status,
    )

    try:
        consultation_type = get_consultation_type(consultation_type_id)

        if not consultation_type:
            logger.warning(f"[EMOTION:COMBINED] Consultation type not found: {consultation_type_id}. Skipping.")
            return

        if not is_emotion_analysis_enabled(consultation_type_id):
            logger.info(f"[EMOTION:COMBINED] Emotion analysis disabled for {consultation_type.get('type_code')}. Skipping.")
            return

        if not template_id:
            logger.warning(f"[EMOTION:COMBINED] No template_id provided. Skipping combined emotion extraction.")
            return

        # Mark emotion extraction as started
        update_extraction_emotion_status(extraction_id, started=True)

        logger.debug(
            f"[EMOTION:COMBINED] Scheduling for extraction_id={extraction_id}, "
            f"consultation_type={consultation_type.get('type_code')}, "
            f"audio_size={len(audio_content)} bytes, transcript_len={len(transcript)} chars"
        )

        asyncio.create_task(
            _run_combined_emotion_extraction(
                audio_content=audio_content,
                audio_mime_type=audio_mime_type,
                transcript=transcript,
                extraction_id=extraction_id,
                template_id=template_id,
                session_id=session_id,
                counsellor_id=counsellor_id,
            )
        )

    except Exception as e:
        logger.error(f"[EMOTION:COMBINED] Failed to schedule: {e}")


async def _run_combined_emotion_extraction(
    audio_content: bytes,
    audio_mime_type: str,
    transcript: str,
    extraction_id: uuid.UUID,
    template_id: str,
    session_id: Optional[str] = None,
    counsellor_id: Optional[str] = None,
):
    """
    Internal: Run combined text+audio emotion extraction.

    Single Gemini call that outputs unified segments directly.
    No need for separate text/audio extraction or congruence analysis.
    """
    from services.gemini_service import extract_combined_emotions
    from services.supabase_service import (
        update_extraction_emotion_status,
        save_unified_emotion_segments,
        get_emotion_model_by_mode,
        check_extraction_exists,
    )
    from services.webhook_service import send_emotion_analysis_webhook

    # Get emotion model from processing_modes table
    emotion_model = get_emotion_model_by_mode("default")
    logger.debug(f"[EMOTION:COMBINED] Using model: {emotion_model}")

    try:
        # Wait for extraction record to exist (may be created by parallel task)
        extraction_exists = await _wait_for_extraction_to_exist(extraction_id)
        if not extraction_exists:
            logger.warning(f"[EMOTION:COMBINED] Extraction {extraction_id} not found after waiting. Proceeding anyway.")

        # Run combined emotion extraction (single attempt - no app-level retry)
        result = await extract_combined_emotions(
            audio_content=audio_content,
            audio_mime_type=audio_mime_type,
            transcript=transcript,
            template_id=template_id,
            model=emotion_model,
            session_id=session_id,
            counsellor_id=counsellor_id,
            extraction_id=str(extraction_id),
        )

        if not result or not result.get("success"):
            error_msg = result.get("error", "Unknown error") if result else "No result returned"
            logger.error(f"[EMOTION:COMBINED] Extraction failed: {error_msg}")
            update_extraction_emotion_status(
                extraction_id=extraction_id,
                failed=True,
                error=error_msg
            )
            return

        unified_segments = result.get("unified_segments", {})
        metadata = result.get("metadata", {})

        logger.debug(
            f"[EMOTION:COMBINED] Extraction successful: {len(unified_segments)} segments, "
            f"mismatch_count={metadata.get('mismatch_count', 0)}, "
            f"api_duration={metadata.get('api_duration_seconds', 0):.2f}s"
        )

        # Save unified segments to database
        try:
            if check_extraction_exists(extraction_id):
                save_unified_emotion_segments(extraction_id, unified_segments, source="combined")
                logger.debug(f"[EMOTION:COMBINED] Saved unified segments for extraction_id={extraction_id}")
            else:
                logger.warning(f"[EMOTION:COMBINED] Skipping save - extraction doesn't exist")
        except Exception as e:
            logger.warning(f"[EMOTION:COMBINED] Failed to save unified segments: {e}")

        # Update extraction status: completed
        update_extraction_emotion_status(
            extraction_id=extraction_id,
            completed=True
        )

        # Send webhook notification
        try:
            await send_emotion_analysis_webhook(extraction_id=str(extraction_id))
            logger.info(f"[EMOTION:COMBINED] Webhook sent for extraction_id={extraction_id}")
        except Exception as e:
            logger.warning(f"[EMOTION:COMBINED] Failed to send webhook: {e}")

        # Nudge API: Send emotions (fire-and-forget)
        try:
            from services.nudge_api_service import send_nudge_emotions
            send_nudge_emotions(extraction_id=str(extraction_id))
        except Exception as e:
            logger.warning(f"[EMOTION:COMBINED] Failed to schedule Nudge emotions: {e}")

    except asyncio.TimeoutError:
        error_msg = "Combined emotion extraction timed out"
        logger.error(f"[EMOTION:COMBINED] {error_msg}")
        update_extraction_emotion_status(
            extraction_id=extraction_id,
            failed=True,
            error=error_msg
        )

    except Exception as e:
        error_msg = f"Combined emotion extraction failed: {str(e)}"
        logger.error(f"[EMOTION:COMBINED] {error_msg}", exc_info=True)
        update_extraction_emotion_status(
            extraction_id=extraction_id,
            failed=True,
            error=error_msg
        )


# ============================================================================
# Live Session Audio Processing (for RecordTab Gemini Live API sessions)
# ============================================================================

async def schedule_live_audio_emotion(
    correlation_id: str,
    chunks: list,
    session_id: uuid.UUID,
    consultation_type_id: Optional[uuid.UUID],
    template_id: Optional[str],
    counsellor_id: Optional[str],
    transcript: str,
    extraction_id: uuid.UUID,  # Pre-generated extraction_id from /extract
):
    """
    Async background task for live session audio processing.

    Called from /extract for RecordTab sessions that uploaded audio chunks
    during Gemini Live streaming. Does NOT block extraction response.

    Flow: Stitch chunks → Save to DB → Audio emotion → Consultation insights
    Reuses patterns from recording_processor.py

    NOTE: Triage runs from main extraction path (not blocked by this).
    Only consultation insights (student dropoff analysis) waits for emotion.

    Args:
        correlation_id: Session correlation ID (used as key in memory store)
        chunks: List of chunk dicts from memory store
        session_id: UUID of recording session
        consultation_type_id: Optional consultation type ID
        template_id: Optional template ID for emotion prompts
        counsellor_id: Optional counsellor ID
        transcript: Full transcript (for combined emotion analysis)
        extraction_id: Pre-generated extraction_id (passed from /extract)
    """
    import base64
    from services.supabase_service import supabase, is_emotion_analysis_enabled

    try:
        logger.info(f"[LIVE_AUDIO] Starting async processing for {correlation_id} ({len(chunks)} chunks)")

        # Step 1: Stitch audio (reuses audio_stitcher.py - same as recording_processor.py)
        from services.audio_stitcher import stitch_audio_chunks
        stitched_b64, mime_type = stitch_audio_chunks(chunks)
        audio_content = base64.b64decode(stitched_b64)
        logger.debug(f"[LIVE_AUDIO] Stitched {len(audio_content)} bytes ({mime_type})")

        # Step 2: Clear memory (same pattern as recording_processor.py line 298)
        from services.chunk_memory_store import clear_session
        clear_session(correlation_id)
        logger.debug(f"[LIVE_AUDIO] Cleared memory for {correlation_id}")

        # Step 3: Save full audio to recording_sessions (async, non-blocking)
        asyncio.create_task(
            _save_live_audio_to_session(session_id, stitched_b64, mime_type)
        )

        # Step 4: Check if emotion enabled
        if not consultation_type_id:
            logger.info(f"[LIVE_AUDIO] No consultation_type_id - skipping emotion analysis")
            return

        if not is_emotion_analysis_enabled(consultation_type_id):
            logger.info(f"[LIVE_AUDIO] Emotion disabled for consultation type - skipping")
            return

        if not template_id:
            logger.info(f"[LIVE_AUDIO] No template_id - skipping emotion analysis")
            return

        # Step 5: Use pre-generated extraction_id (passed from /extract)
        # No need to query DB - extraction_id is generated before async task starts
        logger.debug(f"[LIVE_AUDIO] Using pre-generated extraction_id: {extraction_id}")

        # Step 6: Run combined emotion (audio + transcript)
        # This function handles all the emotion extraction and saves segments
        logger.debug(f"[LIVE_AUDIO] Scheduling combined emotion for extraction_id={extraction_id}")
        await schedule_combined_emotion_extraction(
            audio_content=audio_content,
            audio_mime_type=mime_type,
            transcript=transcript,
            extraction_id=extraction_id,
            consultation_type_id=consultation_type_id,
            template_id=template_id,
            session_id=str(session_id),
            counsellor_id=counsellor_id,
        )

        logger.info(f"[LIVE_AUDIO] ✓ Completed async processing for {correlation_id}")

    except Exception as e:
        logger.error(f"[LIVE_AUDIO] Failed: {e}", exc_info=True)
        # Don't raise - this is background processing, shouldn't block main flow


async def _save_live_audio_to_session(
    session_id: uuid.UUID,
    audio_b64: str,
    mime_type: str,
):
    """
    Save stitched audio to recording_sessions table (fire-and-forget).

    Uses the cleanup_chunks_after_processing RPC which handles full audio storage.
    Note: For live sessions there are no DB chunks to clean up, but we still use
    this RPC for consistency with the normal pipeline.

    Args:
        session_id: Recording session UUID
        audio_b64: Base64-encoded stitched audio
        mime_type: Audio MIME type
    """
    from services.supabase_service import cleanup_chunks_and_save_full_audio

    try:
        full_audio_size = len(audio_b64)
        cleanup_chunks_and_save_full_audio(
            session_id=session_id,
            full_audio_data=audio_b64,
            full_audio_mime_type=mime_type,
            full_audio_size_bytes=full_audio_size,
        )
        logger.debug(f"[LIVE_AUDIO] Saved audio to session {session_id} ({full_audio_size} bytes)")
    except Exception as e:
        logger.warning(f"[LIVE_AUDIO] Failed to save audio to session: {e}")
        # Don't raise - this is fire-and-forget


# ============================================================================
# Allied Health Needs - Background Processing
# ============================================================================

async def _schedule_allied_health_needs(
    extraction_id: uuid.UUID,
    counsellor_id: Optional[str] = None,
):
    """
    Schedule allied health needs assessment as a fire-and-forget task.

    This should be called AFTER emotion analysis completes since it uses
    combined emotion segments (ANXIETY_POST_CONSULTATION with nested pre/post,
    OTHER_EMOTIONS_DETECTED, FINANCIAL_CONCERNS, etc.) to determine referral needs.

    Args:
        extraction_id: UUID of the extraction
        counsellor_id: Optional counsellor ID (will be fetched from extraction if not provided)
    """
    try:
        from services.supabase_service import get_extraction_by_id, get_consultation_insights_by_extraction

        # Get extraction details for counsellor_id and student_id
        extraction = get_extraction_by_id(extraction_id)
        if not extraction:
            logger.warning(
                f"[ALLIED_HEALTH] Extraction not found: {extraction_id}. "
                f"Skipping allied health needs assessment."
            )
            return

        # Get consultation insights from database
        consultation_insights = get_consultation_insights_by_extraction(str(extraction_id))
        if not consultation_insights:
            logger.warning(
                f"[ALLIED_HEALTH] No consultation insights found for extraction_id={extraction_id}. "
                f"Skipping allied health needs assessment."
            )
            return

        # Use provided counsellor_id or get from extraction
        final_counsellor_id = counsellor_id or extraction.get('counsellor_id')
        student_id = extraction.get('student_id')

        from services.log_sanitizer import truncate_id as _tid
        logger.debug(
            f"[ALLIED_HEALTH] Scheduling assessment for extraction_id={extraction_id}, "
            f"counsellor_id={_tid(final_counsellor_id)}, student_id={_tid(student_id)}"
        )

        # Import and schedule the assessment
        from services.allied_health_needs_service import calculate_and_save_allied_needs

        asyncio.create_task(
            calculate_and_save_allied_needs(
                extraction_id=extraction_id,
                consultation_insights=consultation_insights,
                counsellor_id=uuid.UUID(final_counsellor_id) if final_counsellor_id else None,
                student_id=uuid.UUID(student_id) if student_id else None,
            )
        )

        logger.debug(
            f"[ALLIED_HEALTH] Assessment scheduled (fire-and-forget) "
            f"for extraction_id={extraction_id}"
        )

    except Exception as e:
        logger.error(
            f"[ALLIED_HEALTH] ✗ Failed to schedule assessment for extraction_id={extraction_id}: {type(e).__name__}",
            exc_info=True
        )
        # Don't raise - allied health needs are supplementary, shouldn't block main flow


# ============================================================================
# Student Dropoff Risk - Background Processing
# ============================================================================

async def _schedule_student_dropoff_risk(
    extraction_id: uuid.UUID,
    counsellor_id: Optional[str] = None,
):
    """
    Schedule student dropoff risk assessment as a fire-and-forget task.

    This should be called AFTER emotion analysis completes since it uses
    emotional segments (ANXIETY_POST_CONSULTATION, FINANCIAL_CONCERNS,
    TREATMENT_COMPLIANCE_LIKELIHOOD, etc.) to calculate churn indicators.

    Args:
        extraction_id: UUID of the extraction
        counsellor_id: Optional counsellor ID (will be fetched from extraction if not provided)
    """
    try:
        from services.supabase_service import get_extraction_by_id, get_consultation_insights_by_extraction

        # Get extraction details for counsellor_id and student_id
        extraction = get_extraction_by_id(extraction_id)
        if not extraction:
            logger.warning(
                f"[DROPOFF_RISK] Extraction not found: {extraction_id}. "
                f"Skipping dropoff risk assessment."
            )
            return

        # Get consultation insights from database
        consultation_insights = get_consultation_insights_by_extraction(str(extraction_id))
        if not consultation_insights:
            logger.warning(
                f"[DROPOFF_RISK] No consultation insights found for extraction_id={extraction_id}. "
                f"Skipping dropoff risk assessment."
            )
            return

        # Use provided counsellor_id or get from extraction
        final_counsellor_id = counsellor_id or extraction.get('counsellor_id')
        student_id = extraction.get('student_id')

        from services.log_sanitizer import truncate_id as _tid
        logger.debug(
            f"[DROPOFF_RISK] Scheduling assessment for extraction_id={extraction_id}, "
            f"counsellor_id={_tid(final_counsellor_id)}, student_id={_tid(student_id)}"
        )

        # Import and schedule the assessment
        from services.student_dropoff_service import calculate_and_save_dropoff_risk

        asyncio.create_task(
            calculate_and_save_dropoff_risk(
                extraction_id=extraction_id,
                consultation_insights=consultation_insights,
                counsellor_id=uuid.UUID(final_counsellor_id) if final_counsellor_id else None,
                student_id=uuid.UUID(student_id) if student_id else None,
            )
        )

        logger.debug(
            f"[DROPOFF_RISK] Assessment scheduled (fire-and-forget) "
            f"for extraction_id={extraction_id}"
        )

    except Exception as e:
        logger.error(
            f"[DROPOFF_RISK] ✗ Failed to schedule assessment for extraction_id={extraction_id}: {type(e).__name__}",
            exc_info=True
        )
        # Don't raise - dropoff risk is supplementary, shouldn't block main flow


# ============================================================================
# Triage Suggestions - Background Processing
# ============================================================================

async def schedule_triage_generation(
    extraction_id: uuid.UUID,
    transcript: Optional[str] = None,
    extraction_data: Optional[Dict[str, Any]] = None,
    counsellor_id: Optional[str] = None,
    student_id: Optional[str] = None,
    consultation_type_code: Optional[str] = None,
    include_gemini: bool = False,
    enable_consultation_insights: bool = True,
):
    """
    Schedule triage suggestion generation as a fire-and-forget task.

    This runs immediately after extraction completes and:
    1. Generates rule-based triage suggestions (red flags, missing investigations)
    2. Saves suggestions to triage_suggestion_log table
    3. Schedules consultation insights extraction (AI-powered clinical signals) if enabled
    4. Consultation insights then triggers all assessment services

    Args:
        extraction_id: UUID of the extraction
        transcript: Full consultation transcript (required for consultation insights)
        extraction_data: Extracted medical data dict (required for consultation insights)
        counsellor_id: Optional counsellor ID
        student_id: Optional student ID
        consultation_type_code: Optional consultation type code
        include_gemini: Whether to use Gemini AI analysis (default False for speed)
        enable_consultation_insights: Whether to chain to consultation insights (default True)
    """
    try:
        logger.debug(
            f"[TRIAGE] Scheduling generation for extraction_id={extraction_id}, "
            f"consultation_type={consultation_type_code}, include_gemini={include_gemini}, "
            f"has_transcript={bool(transcript)}, enable_insights={enable_consultation_insights}"
        )

        asyncio.create_task(
            _run_triage_generation(
                extraction_id=extraction_id,
                transcript=transcript,
                extraction_data=extraction_data,
                counsellor_id=counsellor_id,
                student_id=student_id,
                consultation_type_code=consultation_type_code,
                include_gemini=include_gemini,
                enable_consultation_insights=enable_consultation_insights,
            )
        )

        logger.debug(
            f"[TRIAGE] Generation scheduled (fire-and-forget) "
            f"for extraction_id={extraction_id}"
        )

    except Exception as e:
        logger.error(
            f"[TRIAGE] ✗ Failed to schedule generation for extraction_id={extraction_id}: {e}",
            exc_info=True
        )
        # Don't raise - triage is supplementary, shouldn't block main flow


async def _run_triage_generation(
    extraction_id: uuid.UUID,
    transcript: Optional[str] = None,
    extraction_data: Optional[Dict[str, Any]] = None,
    counsellor_id: Optional[str] = None,
    student_id: Optional[str] = None,
    consultation_type_code: Optional[str] = None,
    include_gemini: bool = False,
    enable_consultation_insights: bool = True,
):
    """
    Internal: Run triage suggestion generation.

    This generates rule-based triage suggestions (red flags, missing investigations, etc.)
    and saves them to triage_suggestion_log. After completion, schedules consultation
    insights extraction which chains to all assessment services (if enabled).
    """
    from services.supabase_service import get_extraction_by_id

    try:
        start_time = datetime.utcnow()

        # Wait for extraction to exist (handles race condition with fire-and-forget DB save)
        extraction_exists = await _wait_for_extraction_to_exist(extraction_id, max_wait_seconds=30)
        if not extraction_exists:
            logger.warning(
                f"[TRIAGE] Extraction not found after waiting: {extraction_id}. "
                f"Skipping triage generation."
            )
            return

        # Get extraction data
        extraction = get_extraction_by_id(extraction_id)
        if not extraction:
            logger.warning(
                f"[TRIAGE] Extraction not found: {extraction_id}. "
                f"Skipping triage generation."
            )
            return

        # Import multi-layer orchestrator (handles Trees → RAG → Gemini pipeline)
        from services.triage.multi_layer_orchestrator import TriageMultiLayerOrchestrator
        from services.supabase_service import supabase

        # Run triage generation via orchestrator (proper multi-layer pipeline)
        # Pipeline order: Fast Cache (Trees) → RAG Clinical Conditions → Gemini Gap Analysis
        orchestrator = TriageMultiLayerOrchestrator(supabase_client=supabase)
        triage_suggestions = await orchestrator.generate_suggestions(
            extraction=extraction,
            student_id=student_id,
            counsellor_id=counsellor_id,
            consultation_type_code=consultation_type_code,
            include_gemini_analysis=include_gemini,
            log_suggestions=True,  # Save to triage_suggestion_log
            supabase_client=supabase,
        )

        elapsed = (datetime.utcnow() - start_time).total_seconds()

        logger.info(
            f"[TRIAGE] ✓ Completed in {elapsed:.2f}s for extraction_id={extraction_id}: "
            f"critical={len(triage_suggestions.critical_actions)}, "
            f"important={len(triage_suggestions.important_considerations)}, "
            f"red_flags={len(triage_suggestions.identified_red_flags)}"
        )

        # Schedule consultation insights extraction (AI-powered clinical signals) if enabled
        # This chains to: severity → other_clinical_needs → allied_health → dropoff → care_quality
        if not enable_consultation_insights:
            logger.info(
                f"[TRIAGE] Consultation insights disabled for this consultation type - "
                f"skipping insights, assessments, and interventions for extraction_id={extraction_id}"
            )
        elif transcript:
            # Use passed extraction_data if available, otherwise fallback to database
            insights_extraction_data = extraction_data if extraction_data else extraction.get("extraction", {})
            await schedule_consultation_insights_extraction(
                extraction_id=extraction_id,
                transcript=transcript,
                extraction_data=insights_extraction_data,
                counsellor_id=counsellor_id,
                student_id=student_id,
            )
        else:
            logger.warning(
                f"[TRIAGE] No transcript provided - skipping consultation insights extraction. "
                f"Assessment services will not run for extraction_id={extraction_id}"
            )
            # Still schedule care quality risk if no transcript (uses triage data)
            # No consultation insights, so no revenue interventions possible
            await _schedule_care_quality_risk(
                extraction_id=extraction_id,
                consultation_insights={},  # Empty - no transcript means no insights
                counsellor_id=counsellor_id,
                student_id=student_id,
            )

    except Exception as e:
        logger.error(
            f"[TRIAGE] ✗ Failed for extraction_id={extraction_id}: {e}",
            exc_info=True
        )
        # Don't raise - triage is supplementary, shouldn't block main flow


# ============================================================================
# Consultation Insights - Background Processing
# ============================================================================

async def schedule_consultation_insights_extraction(
    extraction_id: uuid.UUID,
    transcript: str,
    extraction_data: Dict[str, Any],
    counsellor_id: Optional[str] = None,
    student_id: Optional[str] = None,
):
    """
    Schedule consultation insights extraction as a fire-and-forget task.

    This runs after triage generation completes and:
    1. Calls Gemini to extract 14 clinical signal groups
    2. Saves raw signals to consultation_insights table
    3. Cascades to all assessment services (severity, needs, allied, dropoff, care_quality)

    Args:
        extraction_id: UUID of the extraction
        transcript: Full consultation transcript
        extraction_data: Dict with extracted segments (DIAGNOSIS, PRESCRIPTION, etc.)
        counsellor_id: Optional counsellor ID
        student_id: Optional student ID
    """
    try:
        logger.debug(
            f"[CONSULTATION_INSIGHTS] Scheduling extraction for extraction_id={extraction_id}"
        )

        asyncio.create_task(
            _run_consultation_insights_extraction(
                extraction_id=extraction_id,
                transcript=transcript,
                extraction_data=extraction_data,
                counsellor_id=counsellor_id,
                student_id=student_id,
            )
        )

        logger.debug(
            f"[CONSULTATION_INSIGHTS] Extraction scheduled (fire-and-forget) "
            f"for extraction_id={extraction_id}"
        )

    except Exception as e:
        logger.error(
            f"[CONSULTATION_INSIGHTS] ✗ Failed to schedule extraction for extraction_id={extraction_id}: {e}",
            exc_info=True
        )
        # Don't raise - shouldn't block main flow


async def _run_consultation_insights_extraction(
    extraction_id: uuid.UUID,
    transcript: str,
    extraction_data: Dict[str, Any],
    counsellor_id: Optional[str] = None,
    student_id: Optional[str] = None,
):
    """
    Internal: Run consultation insights extraction and cascade to assessment services.

    Flow:
    1. Call Gemini to extract 14 signal groups (via extract_consultation_insights)
    2. Save raw insights to consultation_insights table
    3. Calculate clinical severity (map_insights_to_clinical_severity)
    4. Calculate other clinical needs (map_insights_to_other_clinical_needs)
    5. Calculate allied health needs (map_insights_to_allied_health_needs)
    6. Calculate dropoff risk (map_insights_to_dropoff_risk)
    7. Schedule care quality risk assessment
    """
    from services.gemini_service import extract_consultation_insights
    from services.supabase_service import save_consultation_insights, get_insights_model_by_mode

    # Get insights model from processing_modes table
    insights_model = get_insights_model_by_mode("default")

    try:
        start_time = datetime.utcnow()

        # Wait for extraction to exist (handles race condition with fire-and-forget DB save)
        # This is important because consultation_insights has FK to extractions
        extraction_exists = await _wait_for_extraction_to_exist(extraction_id, max_wait_seconds=30)
        if not extraction_exists:
            logger.warning(
                f"[CONSULTATION_INSIGHTS] Extraction not found after waiting: {extraction_id}. "
                f"Skipping insights extraction."
            )
            return

        logger.debug(
            f"[CONSULTATION_INSIGHTS] Starting Gemini extraction for extraction_id={extraction_id}"
        )

        # Step 1: Extract insights via Gemini
        insights = await extract_consultation_insights(
            transcript=transcript,
            extraction_data=extraction_data,
            model=insights_model,  # Use model from processing_modes table
            extraction_id=extraction_id,
            counsellor_id=uuid.UUID(counsellor_id) if counsellor_id else None,
        )

        # Get metadata from insights
        metadata = insights.pop("_metadata", {})
        extraction_duration_ms = metadata.get("extraction_duration_ms", 0)
        model_used = metadata.get("model_used", "gemini-2.5-flash")

        logger.info(
            f"[CONSULTATION_INSIGHTS] ✓ Gemini extraction complete in {extraction_duration_ms}ms"
        )

        # Step 2: Save raw insights to consultation_insights table
        insights_data = {
            "extraction_id": str(extraction_id),
            "student_id": student_id,
            "counsellor_id": counsellor_id,
            **insights,  # All 14 signal groups
            "model_used": model_used,
            "extraction_version": metadata.get("extraction_version", "1.0.0"),
            "extraction_duration_ms": extraction_duration_ms,
            "raw_response": insights,  # Store full response for debugging
        }
        insights_id = save_consultation_insights(insights_data)
        logger.debug(
            f"[CONSULTATION_INSIGHTS] Saved insights {insights_id} to database"
        )

        # Step 3: Calculate and save clinical severity
        from services.clinical_severity_service import calculate_and_save_severity
        await calculate_and_save_severity(
            extraction_id=extraction_id,
            extraction_data=extraction_data,
            consultation_insights=insights,
            consultation_insights_id=insights_id,
            counsellor_id=uuid.UUID(counsellor_id) if counsellor_id else None,
            student_id=uuid.UUID(student_id) if student_id else None,
        )

        # Step 4: Calculate and save other clinical needs
        from services.other_clinical_needs_service import calculate_and_save_needs
        await calculate_and_save_needs(
            extraction_id=extraction_id,
            consultation_insights=insights,
            consultation_insights_id=insights_id,
            counsellor_id=uuid.UUID(counsellor_id) if counsellor_id else None,
            student_id=uuid.UUID(student_id) if student_id else None,
        )

        # Step 5: Calculate and save allied health needs
        from services.allied_health_needs_service import calculate_and_save_allied_needs
        await calculate_and_save_allied_needs(
            extraction_id=extraction_id,
            consultation_insights=insights,
            consultation_insights_id=insights_id,
            counsellor_id=uuid.UUID(counsellor_id) if counsellor_id else None,
            student_id=uuid.UUID(student_id) if student_id else None,
        )

        # Step 6: Calculate and save dropoff risk
        # Wait for emotion segments if emotion analysis is enabled (dropoff uses emotion data)
        emotion_enabled = await _is_emotion_analysis_enabled_for_extraction(extraction_id)
        if emotion_enabled:
            logger.debug(
                f"[CONSULTATION_INSIGHTS] Emotion analysis enabled - waiting for segments "
                f"before dropoff risk calculation for extraction_id={extraction_id}"
            )
            emotion_ready = await _wait_for_emotion_segments_to_exist(
                extraction_id=extraction_id,
                max_wait_seconds=90,  # Emotion extraction can take 30-60s
                poll_interval=3.0,
            )
            if emotion_ready:
                logger.debug(
                    f"[CONSULTATION_INSIGHTS] Emotion segments ready - proceeding with dropoff risk"
                )
            else:
                logger.warning(
                    f"[CONSULTATION_INSIGHTS] ⚠ Emotion segments not ready after 90s - "
                    f"proceeding without emotion modifiers for extraction_id={extraction_id}"
                )

        from services.student_dropoff_service import calculate_and_save_dropoff_risk
        await calculate_and_save_dropoff_risk(
            extraction_id=extraction_id,
            consultation_insights=insights,
            consultation_insights_id=insights_id,
            counsellor_id=uuid.UUID(counsellor_id) if counsellor_id else None,
            student_id=uuid.UUID(student_id) if student_id else None,
        )

        # Step 7: Schedule care quality risk assessment + interventions (final step)
        # Get school_id from counsellor for revenue pricing lookup
        school_id = None
        if counsellor_id:
            from services.supabase_service import get_counsellor_school_id_cached
            school_id = get_counsellor_school_id_cached(uuid.UUID(counsellor_id))

        await _schedule_care_quality_risk(
            extraction_id=extraction_id,
            consultation_insights=insights,
            counsellor_id=counsellor_id,
            student_id=student_id,
            school_id=str(school_id) if school_id else None,
            consultation_insights_id=str(insights_id) if insights_id else None,
        )

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(
            f"[CONSULTATION_INSIGHTS] ✓ Full pipeline complete in {elapsed:.2f}s "
            f"for extraction_id={extraction_id}"
        )

    except Exception as e:
        logger.error(
            f"[CONSULTATION_INSIGHTS] ✗ Failed for extraction_id={extraction_id}: {e}",
            exc_info=True
        )
        # Still try to run care quality even if insights extraction failed
        # Pass empty insights dict as fallback
        try:
            await _schedule_care_quality_risk(
                extraction_id=extraction_id,
                consultation_insights={},  # Empty fallback
                counsellor_id=counsellor_id,
                student_id=student_id,
            )
        except Exception:
            pass


# ============================================================================
# Care Quality Risk - Background Processing
# ============================================================================

async def _schedule_care_quality_risk(
    extraction_id: uuid.UUID,
    consultation_insights: Dict[str, Any],
    counsellor_id: Optional[str] = None,
    student_id: Optional[str] = None,
    school_id: Optional[str] = None,
    consultation_insights_id: Optional[str] = None,
):
    """
    Schedule care quality risk assessment as a fire-and-forget task.

    This should be called AFTER consultation insights extraction completes
    since it uses triage suggestions and AI-extracted signals for quality indicators.

    After care quality completes, also generates REVENUE, RETENTION, and QUALITY
    interventions based on all assessment results.

    Args:
        extraction_id: UUID of the extraction
        consultation_insights: AI-extracted consultation insights (REQUIRED)
        counsellor_id: Optional counsellor ID
        student_id: Optional student ID
        school_id: Optional school ID (for revenue intervention pricing)
        consultation_insights_id: Optional consultation_insights record ID
    """
    try:
        logger.debug(
            f"[CARE_QUALITY] Scheduling assessment for extraction_id={extraction_id}"
        )

        # Schedule the combined task: care quality + interventions
        asyncio.create_task(
            _run_care_quality_and_interventions(
                extraction_id=extraction_id,
                consultation_insights=consultation_insights,
                counsellor_id=counsellor_id,
                student_id=student_id,
                school_id=school_id,
                consultation_insights_id=consultation_insights_id,
            )
        )

        logger.debug(
            f"[CARE_QUALITY] Assessment + interventions scheduled (fire-and-forget) "
            f"for extraction_id={extraction_id}"
        )

    except Exception as e:
        logger.error(
            f"[CARE_QUALITY] ✗ Failed to schedule assessment for extraction_id={extraction_id}: {e}",
            exc_info=True
        )
        # Don't raise - care quality is supplementary, shouldn't block main flow


async def _run_care_quality_and_interventions(
    extraction_id: uuid.UUID,
    consultation_insights: Dict[str, Any],
    counsellor_id: Optional[str] = None,
    student_id: Optional[str] = None,
    school_id: Optional[str] = None,
    consultation_insights_id: Optional[str] = None,
):
    """
    Run care quality assessment, then generate all interventions.

    This is the final step in the consultation insights pipeline:
    1. Calculate and save care quality risk
    2. Generate REVENUE, RETENTION, QUALITY interventions based on all assessments

    Args:
        extraction_id: UUID of the extraction
        consultation_insights: AI-extracted consultation insights
        counsellor_id: Optional counsellor ID
        student_id: Optional student ID
        school_id: Optional school ID (for revenue pricing lookup)
        consultation_insights_id: Optional consultation_insights record ID
    """
    from services.care_quality_service import calculate_and_save_care_quality
    from services.intervention_orchestrator import generate_and_save_interventions

    try:
        # Step 1: Calculate and save care quality risk
        await calculate_and_save_care_quality(
            extraction_id=extraction_id,
            consultation_insights=consultation_insights,
            counsellor_id=uuid.UUID(counsellor_id) if counsellor_id else None,
            student_id=uuid.UUID(student_id) if student_id else None,
        )

        # Step 2: Generate and save interventions (REVENUE, RETENTION, QUALITY)
        logger.debug(
            f"[INTERVENTIONS] Generating interventions for extraction_id={extraction_id}"
        )

        result = await generate_and_save_interventions(
            extraction_id=extraction_id,
            school_id=uuid.UUID(school_id) if school_id else None,
            consultation_insights_id=uuid.UUID(consultation_insights_id) if consultation_insights_id else None,
        )

        logger.info(
            f"[INTERVENTIONS] ✓ Generated {result.get('total_saved', 0)} interventions "
            f"(REVENUE={result.get('by_category', {}).get('REVENUE', 0)}, "
            f"RETENTION={result.get('by_category', {}).get('RETENTION', 0)}, "
            f"QUALITY={result.get('by_category', {}).get('QUALITY', 0)}) "
            f"for extraction_id={extraction_id}"
        )

        # Nudge API: Send interventions (fire-and-forget)
        try:
            from services.nudge_api_service import send_nudge_interventions
            send_nudge_interventions(extraction_id=str(extraction_id))
        except Exception as e:
            logger.warning(f"[INTERVENTIONS] Failed to schedule Nudge interventions: {e}")

    except Exception as e:
        logger.error(
            f"[INTERVENTIONS] ✗ Failed to run care quality + interventions "
            f"for extraction_id={extraction_id}: {e}",
            exc_info=True
        )
        # Don't raise - these are supplementary, shouldn't block main flow


# ============================================================================
# Helper Functions
# ============================================================================

def format_emotion_task_summary(
    extraction_id: uuid.UUID,
    scheduled: bool,
    reason: Optional[str] = None,
) -> dict:
    """
    Format emotion task status for API responses.

    Args:
        extraction_id: Extraction UUID
        scheduled: Whether the combined emotion task was scheduled
        reason: Reason if not scheduled

    Returns:
        Dictionary with task status
    """
    return {
        "emotion_extraction_scheduled": scheduled,
        "extraction_id": str(extraction_id),
        "reason": reason if not scheduled else "Combined emotion extraction scheduled",
    }


# ============================================================================
# Medicine Edit Feedback - Background Processing
# ============================================================================

async def schedule_medicine_edit_feedback(
    extraction_id: uuid.UUID,
    counsellor_id: uuid.UUID,
    original_extraction: Dict[str, Any],
    edited_extraction: Dict[str, Any],
):
    """
    Schedule medicine edit feedback processing as a background task.

    Compares original vs edited extraction to:
    1. Identify medicine name standardizations/spelling corrections
    2. Log to medicine_match_log with feedback_status='agreed'
    3. Auto-add corrected medicines to counsellor's personal list

    This runs in background and doesn't affect the PUT response time.

    Args:
        extraction_id: extraction UUID
        counsellor_id: Counsellor UUID who made edits
        original_extraction: AI-generated extraction JSON
        edited_extraction: Counsellor-edited extraction JSON

    Returns:
        None (task runs in background)
    """
    logger.debug(
        f"[MEDICINE_EDIT] Scheduling feedback processing for extraction_id={extraction_id}, "
        f"counsellor_id={counsellor_id}"
    )

    asyncio.create_task(
        _run_medicine_edit_feedback(
            extraction_id=extraction_id,
            counsellor_id=counsellor_id,
            original_extraction=original_extraction,
            edited_extraction=edited_extraction,
        )
    )


async def _run_medicine_edit_feedback(
    extraction_id: uuid.UUID,
    counsellor_id: uuid.UUID,
    original_extraction: Dict[str, Any],
    edited_extraction: Dict[str, Any],
):
    """
    Internal: Run medicine edit feedback processing.

    This function runs in background and compares original vs edited
    extractions to identify and log medicine name changes.
    """
    from services.medicine_service import process_medicine_edit_feedback

    try:
        start_time = datetime.utcnow()

        result = await process_medicine_edit_feedback(
            extraction_id=extraction_id,
            counsellor_id=counsellor_id,
            original_extraction=original_extraction,
            edited_extraction=edited_extraction,
        )

        elapsed = (datetime.utcnow() - start_time).total_seconds()

        logger.info(
            f"[MEDICINE_EDIT] ✓ Completed in {elapsed:.2f}s for extraction_id={extraction_id}: "
            f"logged={result['logged']} (name={result.get('logged_name_standardization', 0)}, "
            f"spelling={result.get('logged_spelling_correction', 0)}, "
            f"dosage={result.get('logged_dosage_correction', 0)}), "
            f"added_to_list={result['added_to_list']}, "
            f"skipped_different={result['skipped_different_medicine']}"
        )

    except Exception as e:
        logger.error(
            f"[MEDICINE_EDIT] ✗ Failed for extraction_id={extraction_id}: {e}",
            exc_info=True
        )
        # Don't raise - this is background processing


# ============================================================================
# Testing and Debugging
# ============================================================================

async def test_combined_emotion_scheduling():
    """
    Test function for combined emotion extraction scheduling.

    Usage (in Python shell or test):
        ```python
        import asyncio
        from services.background_tasks import test_combined_emotion_scheduling

        asyncio.run(test_combined_emotion_scheduling())
        ```
    """
    logger.info("[TEST] Starting combined emotion scheduling test...")

    # Create test data
    test_transcript = """
    Counsellor: Good morning, how are you feeling today?
    Student: I'm very worried, counsellor. I haven't been sleeping well because of these chest pains.
    Counsellor: I understand your concern. Let's talk about your symptoms. When did this start?
    Student: About a week ago. I'm really scared it might be my heart. My father had a heart attack at my age.
    Counsellor: I can see you're anxious. Let me examine you and we'll run some tests. How is your insurance coverage?
    Student: Um, actually, I'm worried about the cost. Can we do just the necessary tests?
    Counsellor: Of course. We'll prioritize the most important ones. Don't worry, we'll work this out.
    Student: Thank you, counsellor. I really appreciate that.
    Counsellor: The exam looks good. I'll order an ECG and some blood work. These should give us a clear picture.
    Student: Okay, I feel a bit better now. Thank you for explaining everything.
    """

    test_extraction_id = uuid.uuid4()
    test_consultation_type_id = uuid.uuid4()

    logger.info(
        f"[TEST] Test extraction_id={test_extraction_id}, "
        f"consultation_type_id={test_consultation_type_id}"
    )
    logger.info("[TEST] Note: This uses fake UUIDs so the scheduler will skip (consultation type not found).")
    logger.info("[TEST] For a real test, use actual IDs from the database.")

    # Would need real audio bytes and template_id to actually test
    # await schedule_combined_emotion_extraction(...)

    logger.info("[TEST] Test setup complete. Use real IDs to test full flow.")

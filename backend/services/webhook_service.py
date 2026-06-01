"""
Webhook Service for sending extracted medical insights to external endpoints.

This service provides asynchronous webhook delivery with automatic retry logic
and comprehensive error handling.
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

import httpx
from httpx import TimeoutException, HTTPStatusError

# Configure logging
logger = logging.getLogger(__name__)


class WebhookService:
    """Service for sending data to webhook endpoints with retry logic."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        webhook_token: Optional[str] = None,
        enabled: bool = True,
        timeout: int = 10,
        max_retries: int = 3
    ):
        """
        Initialize webhook service.

        Args:
            webhook_url: Target webhook URL(s) - comma-separated for multiple URLs (reads from env if not provided)
            webhook_token: Bearer token for Authorization header (reads from env if not provided)
            enabled: Whether webhook is enabled (reads from env if not provided)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        # Parse comma-separated URLs
        webhook_url_str = webhook_url or os.getenv("WEBHOOK_URL", "")
        self.webhook_urls = [url.strip() for url in webhook_url_str.split(",") if url.strip()]
        self.webhook_token = webhook_token or os.getenv("WEBHOOK_TOKEN", "")
        self.enabled = enabled and os.getenv("WEBHOOK_ENABLED", "true").lower() == "true"
        self.timeout = int(os.getenv("WEBHOOK_TIMEOUT", str(timeout)))
        self.max_retries = max_retries

        if not self.webhook_urls and self.enabled:
            logger.warning("Webhook is enabled but WEBHOOK_URL is not configured")
            self.enabled = False

        if not self.webhook_token and self.enabled:
            logger.warning("Webhook is enabled but WEBHOOK_TOKEN is not configured. Requests may be rejected by webhook endpoint.")
            # Don't disable webhook - some endpoints may not require auth

        # Log webhook configuration on startup
        if self.enabled:
            urls_display = ", ".join(self.webhook_urls) if len(self.webhook_urls) <= 3 else f"{len(self.webhook_urls)} URLs"
            logger.info(
                f"✅ Webhook service initialized: "
                f"urls=[{urls_display}], "
                f"token={'configured' if self.webhook_token else 'not configured'}, "
                f"timeout={self.timeout}s, "
                f"max_retries={self.max_retries}"
            )
        else:
            logger.info("❌ Webhook service disabled")

    async def send_insights_to_webhook(
        self,
        insights: Dict[str, Any],
        metadata: Dict[str, Any],
        source: str = "unknown",
        excluded_segment_codes: Optional[set] = None
    ) -> bool:
        """
        Send extracted insights to all webhook endpoints with retry logic.

        Args:
            insights: Extracted medical insights data
            metadata: Standardized metadata (correlation_id, submission_id, extraction_id,
                     counsellor_id, student_id, mode, segment_count, processing_mode, timestamp)
            source: Source of the extraction ("recording", "transcript_only_extraction", "merge")
            excluded_segment_codes: Set of segment codes to filter from payload (template-level exclusions)

        Returns:
            bool: True if at least one webhook was sent successfully, False otherwise
        """
        # 🔍 DEBUG: Log webhook call
        logger.info(f"[WEBHOOK] send_insights_to_webhook called - enabled={self.enabled}, urls={len(self.webhook_urls) if self.webhook_urls else 0}")
        logger.info(f"[WEBHOOK] Metadata: {metadata}")
        logger.info(f"[WEBHOOK] Source: {source}")
        logger.info(f"[WEBHOOK] Insights keys: {list(insights.keys()) if insights else 'None'}")

        if not self.enabled:
            logger.warning("[WEBHOOK] ⚠️  Webhook is disabled, skipping")
            return False

        if not self.webhook_urls:
            logger.warning("[WEBHOOK] ⚠️  Webhook URLs not configured, skipping")
            return False

        # Build webhook payload with standardized metadata
        logger.info(f"[WEBHOOK] Building payload...")
        payload = self._build_payload(insights, metadata, source, excluded_segment_codes)
        logger.info(f"[WEBHOOK] Payload built successfully. Size: {len(str(payload))} chars")

        # Send to all URLs in parallel
        logger.info(f"[WEBHOOK] Sending to {len(self.webhook_urls)} webhook URL(s)...")
        tasks = [
            self._send_to_url(url, payload, source, metadata)
            for url in self.webhook_urls
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check results
        success_count = sum(1 for result in results if result is True)
        failure_count = len(results) - success_count

        if success_count > 0:
            logger.info(
                f"[WEBHOOK] ✅ Successfully sent to {success_count}/{len(self.webhook_urls)} webhook(s)",
                extra={
                    "source": source,
                    "extraction_id": metadata.get("extraction_id"),
                    "success_count": success_count,
                    "failure_count": failure_count
                }
            )
            return True
        else:
            logger.error(
                f"[WEBHOOK] ❌ Failed to send to all {len(self.webhook_urls)} webhook(s)",
                extra={
                    "source": source,
                    "extraction_id": metadata.get("extraction_id")
                }
            )
            return False

    async def _send_to_url(
        self,
        url: str,
        payload: Dict[str, Any],
        source: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """
        Send payload to a single webhook URL with retry logic.

        Args:
            url: Webhook URL to send to
            payload: JSON payload to send
            source: Source of extraction
            metadata: Standardized metadata

        Returns:
            bool: True if request was successful, False otherwise
        """
        logger.info(f"[WEBHOOK] Attempting to send to {url}")

        for attempt in range(1, self.max_retries + 1):
            try:
                success = await self._send_request(url, payload, attempt)
                if success:
                    logger.info(
                        f"[WEBHOOK] ✅ Successfully sent to {url} on attempt {attempt}/{self.max_retries}",
                        extra={
                            "url": url,
                            "source": source,
                            "extraction_id": metadata.get("extraction_id")
                        }
                    )
                    return True

            except Exception as e:
                logger.error(
                    f"[WEBHOOK] ❌ Failed to send to {url} (attempt {attempt}/{self.max_retries}): {str(e)}",
                    extra={
                        "url": url,
                        "source": source,
                        "extraction_id": metadata.get("extraction_id"),
                        "error": str(e)
                    },
                    exc_info=True
                )

            # Wait before retry (exponential backoff: 1s, 2s, 4s)
            if attempt < self.max_retries:
                wait_time = 2 ** (attempt - 1)  # 1, 2, 4 seconds
                logger.debug(f"[WEBHOOK] Waiting {wait_time}s before retry {attempt + 1} for {url}")
                await asyncio.sleep(wait_time)

        logger.error(
            f"[WEBHOOK] ❌ Failed to send to {url} after {self.max_retries} attempts",
            extra={
                "url": url,
                "source": source,
                "extraction_id": metadata.get("extraction_id")
            }
        )
        return False

    async def _send_request(self, url: str, payload: Dict[str, Any], attempt: int) -> bool:
        """
        Send HTTP POST request to webhook URL.

        Args:
            url: Webhook URL to send to
            payload: JSON payload to send
            attempt: Current attempt number (for logging)

        Returns:
            bool: True if request was successful (2xx status code)

        Raises:
            Exception: If request fails
        """
        # Use connection limits to prevent resource exhaustion
        limits = httpx.Limits(
            max_keepalive_connections=3,
            max_connections=5,
            keepalive_expiry=10
        )
        async with httpx.AsyncClient(limits=limits) as client:
            logger.debug(
                f"Sending webhook (attempt {attempt})",
                extra={"url": url, "payload_size": len(str(payload))}
            )

            # Build headers
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "AI-Live-Recorder/3.1.0"
            }

            # Add Authorization header if token is configured
            if self.webhook_token:
                headers["Authorization"] = f"Bearer {self.webhook_token}"

            response = await client.post(
                url,
                json=payload,
                timeout=self.timeout,
                headers=headers
            )

            # Raise exception for 4xx/5xx status codes
            response.raise_for_status()

            logger.debug(
                f"Webhook response: {response.status_code}",
                extra={"status": response.status_code, "response_size": len(response.text)}
            )

            return 200 <= response.status_code < 300

    def _build_payload(
        self,
        insights: Dict[str, Any],
        metadata: Dict[str, Any],
        source: str,
        excluded_segment_codes: Optional[set] = None
    ) -> Dict[str, Any]:
        """
        Build webhook payload with insights and standardized metadata.

        Args:
            insights: Extracted medical insights
            metadata: Standardized metadata (correlation_id, submission_id, extraction_id,
                     counsellor_id, student_id, mode, segment_count, processing_mode, timestamp)
            source: Source of extraction
            excluded_segment_codes: Set of segment codes to filter from payload (template-level exclusions)

        Returns:
            dict: Complete webhook payload with structure:
            {
                "insights": { ... filtered segments ... },
                "metadata": { ... 9 standardized fields ... }
            }

        Note:
            Excluded segments (from template configuration) are filtered out before sending.
            These segments are still extracted and stored in the database.
        """
        # Filter out excluded segments from insights before sending
        if excluded_segment_codes and insights:
            # Convert excluded codes to camelCase for matching (segment codes are UPPER_SNAKE_CASE)
            # e.g., "CAUTION" -> "caution", "SUMMARY" -> "summary"
            excluded_camel = set()
            for code in excluded_segment_codes:
                parts = code.lower().split('_')
                camel = parts[0] + ''.join(p.capitalize() for p in parts[1:])
                excluded_camel.add(camel)

            filtered_insights = {
                key: value for key, value in insights.items()
                if key not in excluded_camel
            }
            # Log if any segments were filtered
            filtered_keys = [key for key in insights.keys() if key in excluded_camel]
            if filtered_keys:
                logger.info(f"[WEBHOOK] Filtered excluded segments from payload: {filtered_keys}")
        else:
            filtered_insights = insights or {}

        # Build payload with standardized metadata structure
        # Same structure as API response for consistency
        # Add source to metadata for webhook consumers
        enriched_metadata = {**metadata, "source": source}
        payload = {
            "success": True,
            "insights": filtered_insights,
            "metadata": enriched_metadata
        }

        # 🔍 DETAILED LOGGING: Log webhook payload structure
        logger.info(f"[WEBHOOK_PAYLOAD] ========== WEBHOOK PAYLOAD BUILT ==========")
        logger.info(f"[WEBHOOK_PAYLOAD] Source: {source}")
        logger.info(f"[WEBHOOK_PAYLOAD] Extraction ID: {metadata.get('extraction_id')}")
        logger.info(f"[WEBHOOK_PAYLOAD] Counsellor ID: {metadata.get('counsellor_id')}")
        logger.info(f"[WEBHOOK_PAYLOAD] Mode: {metadata.get('mode')}")
        logger.info(f"[WEBHOOK_PAYLOAD] Segment Count: {metadata.get('segment_count')}")

        # Log insights structure (keys only, no sensitive data)
        if filtered_insights:
            logger.info(f"[WEBHOOK_PAYLOAD] Insights Keys: {list(filtered_insights.keys())}")
            logger.info(f"[WEBHOOK_PAYLOAD] Total Fields: {len(filtered_insights)}")
        else:
            logger.warning(f"[WEBHOOK_PAYLOAD] ⚠️  No insights data in payload!")

        logger.info(f"[WEBHOOK_PAYLOAD] ========================================")

        return payload


# Global webhook service instance
webhook_service = WebhookService()


async def send_insights_webhook(
    insights: Dict[str, Any],
    metadata: Dict[str, Any],
    source: str = "unknown",
    excluded_segment_codes: Optional[set] = None
) -> bool:
    """
    Convenience function to send insights to webhook in non-blocking manner.

    This function creates a background task to send the webhook without blocking
    the main execution flow. Errors are logged but do not propagate.

    Args:
        insights: Extracted medical insights data
        metadata: Standardized metadata (correlation_id, submission_id, extraction_id,
                 counsellor_id, student_id, mode, segment_count, processing_mode, timestamp)
        source: Source of extraction ("recording", "transcript_only_extraction", "merge")
        excluded_segment_codes: Set of segment codes to filter from payload (template-level exclusions)

    Returns:
        bool: True if task was created successfully, False on error
    """
    try:
        # Create background task (fire-and-forget)
        asyncio.create_task(
            webhook_service.send_insights_to_webhook(insights, metadata, source, excluded_segment_codes)
        )
        return True
    except Exception as e:
        logger.error(f"Failed to create webhook task: {str(e)}", exc_info=True)
        return False


async def send_error_webhook(
    error_message: str,
    session_id: Optional[str] = None,
    submission_id: Optional[str] = None,
    session_data: Optional[Dict[str, Any]] = None,
    source: str = "recording",
    error_code: Optional[str] = None,
) -> bool:
    """
    Send an error webhook to notify EHR systems of pipeline failures.

    This ensures external systems waiting for a webhook callback are notified
    when the pipeline fails (e.g., no audio detected, transcription failure,
    extraction error) instead of waiting indefinitely.

    Args:
        error_message: Human-readable error description
        session_id: Recording session UUID string
        submission_id: Processing job submission UUID string
        session_data: Session dict (used to extract counsellor_id, student_id, etc.)
        source: Source identifier (e.g., "recording", "reprocess", "merge")
        error_code: Machine-readable error code (e.g., "NO_AUDIO", "TRANSCRIPTION_FAILED")

    Returns:
        bool: True if webhook task was created successfully
    """
    try:
        session = session_data or {}

        error_payload = {
            "session_id": session_id,
            "status": "ERROR",
            "error": error_code or "PROCESSING_FAILED",
            "message": error_message,
        }

        metadata = {
            "correlation_id": session.get("correlation_id"),
            "submission_id": submission_id,
            "counsellor_id": session.get("counsellor_id"),
            "student_id": session.get("student_id"),
            "template_code": session.get("template_code"),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        # Check if realtime is enabled (skip webhook if so - UI already gets the error)
        try:
            from services.realtime_publisher_service import is_realtime_enabled_for_school
            from services.supabase_service import get_counsellor_school_id_cached
            import uuid as uuid_mod
            _doctor_id = session.get("counsellor_id")
            _hospital_id = get_counsellor_school_id_cached(uuid_mod.UUID(_doctor_id)) if _doctor_id else None
            if _hospital_id and is_realtime_enabled_for_school(_hospital_id):
                logger.debug(f"[WEBHOOK:ERROR] Skipping error webhook - realtime enabled for school")
                return True
        except Exception:
            pass  # If realtime check fails, send webhook anyway

        logger.info(
            f"[WEBHOOK:ERROR] Sending error webhook - source={source}, "
            f"error_code={error_code or 'PROCESSING_FAILED'}, session={session_id}"
        )

        asyncio.create_task(
            webhook_service.send_insights_to_webhook(
                insights=error_payload,
                metadata=metadata,
                source=f"{source}.error"
            )
        )
        return True
    except Exception as e:
        logger.error(f"[WEBHOOK:ERROR] Failed to create error webhook task: {e}")
        return False


async def send_emotion_analysis_webhook(
    extraction_id: str
) -> bool:
    """
    Send unified emotion analysis results to webhook.

    Called after unified emotion segments are created:
    - After text_only emotion extraction
    - After audio_only emotion extraction
    - After congruence analysis (for 'both' mode)

    The unified segments already contain source info (text/audio/combined) in their data.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        bool: True if webhook sent successfully
    """
    import uuid as uuid_module
    from services.supabase_service import (
        get_extraction_by_id,
        supabase,
    )

    try:
        logger.info(f"[WEBHOOK:EMOTION] Preparing emotion analysis webhook for extraction_id={extraction_id}")

        # Get extraction details for session_info
        extraction = get_extraction_by_id(uuid_module.UUID(extraction_id))
        if not extraction:
            logger.warning(f"[WEBHOOK:EMOTION] Extraction not found: {extraction_id}")
            return False

        # Get unified emotion segments (counselling 3-speaker model) — single source of truth
        from services.supabase_service import UNIFIED_EMOTION_SEGMENT_CODES as unified_emotion_codes

        segments_response = (
            supabase.table("extraction_segments")
            .select("segment_code, segment_value, created_at")
            .eq("extraction_id", extraction_id)
            .in_("segment_code", unified_emotion_codes)
            .execute()
        )

        unified_emotions = []
        for seg in segments_response.data or []:
            unified_emotions.append({
                "segment_code": seg.get("segment_code"),
                "data": seg.get("segment_value") or {},
                "created_at": seg.get("created_at")
            })

        logger.info(f"[WEBHOOK:EMOTION] Found {len(unified_emotions)} unified emotion segments")

        if not unified_emotions:
            logger.warning(f"[WEBHOOK:EMOTION] No emotion data to send for extraction_id={extraction_id}")
            return False

        # Lookup student preferred_language
        student_preferred_language = None
        _patient_id = extraction.get("student_id")
        if _patient_id:
            try:
                pat_lang_res = (
                    supabase.table("students")
                    .select("preferred_language")
                    .eq("id", _patient_id)
                    .limit(1)
                    .execute()
                )
                if pat_lang_res.data:
                    student_preferred_language = pat_lang_res.data[0].get("preferred_language")
            except Exception as e:
                logger.debug(f"[WEBHOOK:EMOTION] Student language lookup failed: {e}")

        # Build session_info from extraction
        consultation_type = extraction.get("consultation_types", {})
        session_info = {
            "extraction_id": extraction_id,
            "submission_id": extraction.get("submission_id"),
            "counsellor_id": extraction.get("counsellor_id"),
            "student_id": _patient_id,
            "consultation_type_code": consultation_type.get("type_code"),
            "consultation_type_name": consultation_type.get("type_name"),
            "preferred_language": student_preferred_language,
        }

        # Build payload with unified emotions only
        payload = {
            "type": "emotion_analysis",
            "unified_emotions": unified_emotions,
            "session_info": session_info,
            "metadata": {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "emotion_analysis"
            }
        }

        logger.info(
            f"[WEBHOOK:EMOTION] Sending webhook - "
            f"extraction_id={extraction_id}, "
            f"unified_segments={len(unified_emotions)}"
        )

        # Send to webhook
        return await webhook_service.send_insights_to_webhook(
            insights=payload,
            metadata=session_info,
            source="emotion_analysis"
        )

    except Exception as e:
        logger.error(f"[WEBHOOK:EMOTION] Failed: {e}", exc_info=True)
        return False

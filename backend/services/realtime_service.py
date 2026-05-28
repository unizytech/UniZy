"""
Supabase Realtime Service for WebSocket-based Progress Updates

This service replaces SSE polling with Supabase Realtime:
- Backend publishes progress updates to processing_jobs table
- Frontend subscribes to changes via Supabase Realtime WebSocket
- No polling required - updates are pushed in real-time

Architecture:
1. Backend updates processing_jobs.progress_json column with full progress state
2. Supabase Realtime broadcasts the UPDATE event to subscribers
3. Frontend receives update via WebSocket (using @supabase/supabase-js)

Benefits:
- Eliminates ~80% of database requests (no more polling every 500ms)
- Lower latency for progress updates
- More scalable (WebSocket vs HTTP polling)
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class RealtimeProgressPublisher:
    """
    Publishes progress updates to processing_jobs table.

    Updates are made to the `progress_json` column which contains:
    {
        "status": "TRANSCRIBING",
        "progress": 40,
        "message": "Transcribing audio...",
        "updated_at": "2024-01-01T00:00:00Z"
    }

    Frontend subscribes to this table via Supabase Realtime to receive updates.
    """

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self._update_count = 0

    def publish_progress(
        self,
        submission_id: str,
        status: str,
        progress: int,
        message: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Publish progress update to processing_jobs table.

        This triggers a Supabase Realtime broadcast to all subscribers.

        Args:
            submission_id: UUID of the processing job
            status: Current status (LOADING, STITCHING, TRANSCRIBING, EXTRACTING, etc.)
            progress: Progress percentage (0-100)
            message: Human-readable progress message
            extra_data: Additional data to include (metrics, transcript preview, etc.)

        Returns:
            True if update was successful
        """
        try:
            progress_data = {
                "status": status,
                "progress": progress,
                "message": message,
                "updated_at": datetime.utcnow().isoformat(),
            }

            if extra_data:
                progress_data.update(extra_data)

            # Update both legacy columns AND new progress_json column
            # Legacy columns for backwards compatibility with existing code
            # progress_json for Realtime subscribers
            update_data = {
                "status": status,
                "progress_percentage": progress,
                "progress_message": message,
                "progress_json": json.dumps(progress_data),
                "updated_at": datetime.utcnow().isoformat(),
            }

            result = self.supabase.table("processing_jobs").update(
                update_data
            ).eq("submission_id", submission_id).execute()

            self._update_count += 1

            if self._update_count % 5 == 0:  # Log every 5th update to reduce noise
                logger.debug(f"[REALTIME] Published progress #{self._update_count}: {status} {progress}%")

            return True

        except Exception as e:
            logger.error(f"[REALTIME] Failed to publish progress: {e}")
            return False

    def publish_complete(
        self,
        submission_id: str,
        transcript: Optional[str] = None,
        insights: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Publish completion event.

        Includes full results in progress_json for immediate access.
        """
        try:
            progress_data = {
                "status": "COMPLETED",
                "progress": 100,
                "message": "Processing completed successfully",
                "updated_at": datetime.utcnow().isoformat(),
                "transcript": transcript,
                "insights": insights,
                "metrics": metrics,
            }

            update_data = {
                "status": "COMPLETED",
                "progress_percentage": 100,
                "progress_message": "Processing completed successfully",
                "progress_json": json.dumps(progress_data),
                "completed_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            self.supabase.table("processing_jobs").update(
                update_data
            ).eq("submission_id", submission_id).execute()

            logger.info(f"[REALTIME] Published completion for {submission_id}")
            return True

        except Exception as e:
            logger.error(f"[REALTIME] Failed to publish completion: {e}")
            return False

    def publish_error(
        self,
        submission_id: str,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Publish error event.
        """
        try:
            progress_data = {
                "status": "ERROR",
                "progress": 0,
                "message": f"Processing failed: {error_message}",
                "updated_at": datetime.utcnow().isoformat(),
                "error": error_message,
                "error_details": error_details,
            }

            update_data = {
                "status": "ERROR",
                "progress_percentage": 0,
                "progress_message": f"Error: {error_message}",
                "progress_json": json.dumps(progress_data),
                "error_message": error_message,
                "error_details": json.dumps(error_details) if error_details else None,
                "updated_at": datetime.utcnow().isoformat(),
            }

            self.supabase.table("processing_jobs").update(
                update_data
            ).eq("submission_id", submission_id).execute()

            logger.info(f"[REALTIME] Published error for {submission_id}: {error_message}")
            return True

        except Exception as e:
            logger.error(f"[REALTIME] Failed to publish error: {e}")
            return False


# Singleton instance (initialized with supabase client from supabase_service)
_publisher: Optional[RealtimeProgressPublisher] = None


def get_realtime_publisher() -> RealtimeProgressPublisher:
    """Get the singleton RealtimeProgressPublisher instance."""
    global _publisher
    if _publisher is None:
        from services.supabase_service import supabase
        _publisher = RealtimeProgressPublisher(supabase)
        logger.info("[REALTIME] RealtimeProgressPublisher initialized")
    return _publisher


def publish_progress(
    submission_id: str,
    status: str,
    progress: int,
    message: str,
    extra_data: Optional[Dict[str, Any]] = None
) -> bool:
    """Convenience function to publish progress update."""
    return get_realtime_publisher().publish_progress(
        submission_id, status, progress, message, extra_data
    )


def publish_complete(
    submission_id: str,
    transcript: Optional[str] = None,
    insights: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None
) -> bool:
    """Convenience function to publish completion."""
    return get_realtime_publisher().publish_complete(
        submission_id, transcript, insights, metrics
    )


def publish_error(
    submission_id: str,
    error_message: str,
    error_details: Optional[Dict[str, Any]] = None
) -> bool:
    """Convenience function to publish error."""
    return get_realtime_publisher().publish_error(
        submission_id, error_message, error_details
    )

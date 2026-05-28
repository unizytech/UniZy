"""
Realtime Publisher Service

Publishes extraction results to the realtime_extraction_responses table
for EHR clients that have Supabase Realtime subscriptions enabled.

This service is designed to be fire-and-forget with zero impact on
the extraction pipeline latency.
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from threading import Lock as ThreadLock

from services.supabase_service import supabase

logger = logging.getLogger(__name__)

# ============================================================================
# Cache for Hospital Realtime Subscription Setting
# ============================================================================

# Cache for hospital realtime subscription status
# Key: hospital_id (str), Value: bool (enable_realtime_subscription)
_hospital_realtime_cache: Dict[str, bool] = {}
_hospital_realtime_lock = ThreadLock()


def is_realtime_enabled_for_hospital(hospital_id: str) -> bool:
    """
    Check if realtime subscription is enabled for a hospital.

    Uses in-memory cache with infinite TTL (invalidated on settings update).

    Args:
        hospital_id: Hospital UUID string

    Returns:
        True if realtime subscription is enabled, False otherwise
    """
    if not hospital_id:
        return False

    # Check cache first (thread-safe read)
    with _hospital_realtime_lock:
        if hospital_id in _hospital_realtime_cache:
            return _hospital_realtime_cache[hospital_id]

    # Cache miss - fetch from DB
    try:
        result = supabase.table("hospitals").select(
            "enable_realtime_subscription"
        ).eq("id", hospital_id).single().execute()

        if result.data:
            enabled = result.data.get("enable_realtime_subscription", False) or False
        else:
            enabled = False

        # Store in cache (thread-safe write)
        with _hospital_realtime_lock:
            _hospital_realtime_cache[hospital_id] = enabled

        logger.info(f"[REALTIME_CACHE] Cached realtime subscription status for hospital {hospital_id[:8]}...: {enabled}")
        return enabled

    except Exception as e:
        logger.warning(f"[REALTIME_CACHE] Failed to fetch realtime subscription status for {hospital_id}: {e}")
        return False


def invalidate_hospital_realtime_cache(hospital_id: Optional[str] = None) -> int:
    """
    Invalidate cached realtime subscription status for a hospital.

    Call this when hospital settings are updated via the API.

    Args:
        hospital_id: Specific hospital to invalidate, or None to clear all

    Returns:
        Number of entries invalidated
    """
    global _hospital_realtime_cache

    with _hospital_realtime_lock:
        if hospital_id:
            if hospital_id in _hospital_realtime_cache:
                del _hospital_realtime_cache[hospital_id]
                logger.info(f"[CACHE_INVALIDATE] Cleared realtime subscription cache for {hospital_id[:8]}...")
                return 1
            return 0
        else:
            count = len(_hospital_realtime_cache)
            _hospital_realtime_cache.clear()
            logger.info(f"[CACHE_INVALIDATE] Cleared all realtime subscription cache ({count} entries)")
            return count


# ============================================================================
# Realtime Publishing Functions
# ============================================================================

async def publish_extraction_response(
    submission_id: str,
    hospital_id: str,
    doctor_id: Optional[str],
    extraction_id: str,
    insights: Dict[str, Any],
    hospital_code: Optional[str] = None,
    recording_metadata: Optional[Dict[str, Any]] = None,
    uhid: Optional[str] = None,
) -> bool:
    """
    Publish extraction response to realtime_extraction_responses table.

    This is the core publishing function that inserts the response into
    the Supabase table. Supabase Realtime automatically broadcasts the
    INSERT to any subscribed clients.

    Args:
        submission_id: The unique submission ID for this extraction
        hospital_id: Hospital UUID string
        doctor_id: Doctor UUID string (optional)
        extraction_id: Extraction UUID string
        insights: The extraction insights/results to publish
        hospital_code: Hospital code for filtering (optional)

    Returns:
        True if published successfully, False otherwise
    """
    try:
        # Check if realtime is enabled for this hospital
        if not is_realtime_enabled_for_hospital(hospital_id):
            logger.debug(f"[REALTIME_PUBLISH] Realtime not enabled for hospital {hospital_id[:8]}..., skipping")
            return False

        # Build the response payload (matches EHR status API structure)
        response_payload = {
            "submission_id": submission_id,
            "status": "COMPLETED",
            "progress": 100,
            "message": "Processing completed successfully",
            "extraction_id": extraction_id,
            "uhid": uhid or "",
            "insights": insights,
            "recording_metadata": recording_metadata or {}
        }

        # Prepare the row to insert
        insert_data = {
            "submission_id": submission_id,
            "hospital_id": hospital_id,
            "doctor_id": doctor_id,
            "extraction_id": extraction_id,
            "response": response_payload,
            "hospital_code": hospital_code
        }

        # Insert into realtime_extraction_responses table
        # Supabase Realtime will automatically broadcast this INSERT
        result = supabase.table("realtime_extraction_responses").insert(insert_data).execute()

        if result.data:
            logger.info(
                f"[REALTIME_PUBLISH] Published extraction response for submission_id={submission_id[:8]}..., "
                f"hospital={hospital_id[:8]}..., extraction_id={extraction_id[:8]}..."
            )
            return True
        else:
            logger.warning(f"[REALTIME_PUBLISH] Insert returned no data for submission_id={submission_id}")
            return False

    except Exception as e:
        # Log but don't raise - this is fire-and-forget
        logger.error(f"[REALTIME_PUBLISH] Failed to publish extraction response: {e}", exc_info=True)
        return False


async def publish_error_response(
    submission_id: str,
    hospital_id: str,
    doctor_id: Optional[str] = None,
    error_message: str = "Processing failed",
    error_code: str = "PROCESSING_FAILED",
    hospital_code: Optional[str] = None,
    session_id: Optional[str] = None,
) -> bool:
    """
    Publish error response to realtime_extraction_responses table.

    This ensures EHR clients subscribed via Supabase Realtime are notified
    of pipeline failures instead of waiting indefinitely.

    Args:
        submission_id: The unique submission ID for this extraction
        hospital_id: Hospital UUID string
        doctor_id: Doctor UUID string (optional)
        error_message: Human-readable error description
        error_code: Machine-readable error code (e.g., VALIDATION_FAILED, PROCESSING_FAILED)
        hospital_code: Hospital code for filtering (optional)
        session_id: Recording session UUID string (optional)

    Returns:
        True if published successfully, False otherwise
    """
    try:
        # Check if realtime is enabled for this hospital
        if not is_realtime_enabled_for_hospital(hospital_id):
            logger.debug(f"[REALTIME_PUBLISH] Realtime not enabled for hospital {hospital_id[:8]}..., skipping error publish")
            return False

        # Build the error response payload
        response_payload = {
            "submission_id": submission_id,
            "status": "ERROR",
            "progress": 0,
            "message": error_message,
            "error": error_code,
        }
        if session_id:
            response_payload["session_id"] = session_id

        # Prepare the row to insert
        insert_data = {
            "submission_id": submission_id,
            "hospital_id": hospital_id,
            "doctor_id": doctor_id,
            "extraction_id": None,
            "response": response_payload,
            "hospital_code": hospital_code,
        }

        # Insert into realtime_extraction_responses table
        # Supabase Realtime will automatically broadcast this INSERT
        result = supabase.table("realtime_extraction_responses").insert(insert_data).execute()

        if result.data:
            logger.info(
                f"[REALTIME_PUBLISH] Published ERROR response for submission_id={submission_id[:8]}..., "
                f"hospital={hospital_id[:8]}..., error_code={error_code}"
            )
            return True
        else:
            logger.warning(f"[REALTIME_PUBLISH] Error insert returned no data for submission_id={submission_id}")
            return False

    except Exception as e:
        # Log but don't raise - this is fire-and-forget
        logger.error(f"[REALTIME_PUBLISH] Failed to publish error response: {e}", exc_info=True)
        return False


async def publish_error_response_fire_and_forget(
    submission_id: str,
    hospital_id: str,
    doctor_id: Optional[str] = None,
    error_message: str = "Processing failed",
    error_code: str = "PROCESSING_FAILED",
    hospital_code: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """
    Fire-and-forget wrapper for publishing error responses.

    Usage:
        asyncio.create_task(publish_error_response_fire_and_forget(...))
    """
    try:
        await publish_error_response(
            submission_id=submission_id,
            hospital_id=hospital_id,
            doctor_id=doctor_id,
            error_message=error_message,
            error_code=error_code,
            hospital_code=hospital_code,
            session_id=session_id,
        )
    except Exception as e:
        logger.warning(f"[REALTIME_PUBLISH] Fire-and-forget error publish failed for submission_id={submission_id}: {e}")


async def publish_extraction_response_fire_and_forget(
    submission_id: str,
    hospital_id: str,
    doctor_id: Optional[str],
    extraction_id: str,
    insights: Dict[str, Any],
    hospital_code: Optional[str] = None,
    recording_metadata: Optional[Dict[str, Any]] = None,
    uhid: Optional[str] = None,
) -> None:
    """
    Fire-and-forget wrapper for publishing extraction responses.

    This function is designed to be called via asyncio.create_task()
    with zero impact on the extraction pipeline latency.

    Usage:
        asyncio.create_task(publish_extraction_response_fire_and_forget(...))

    Args:
        submission_id: The unique submission ID for this extraction
        hospital_id: Hospital UUID string
        doctor_id: Doctor UUID string (optional)
        extraction_id: Extraction UUID string
        insights: The extraction insights/results to publish
        hospital_code: Hospital code for filtering (optional)
    """
    try:
        await publish_extraction_response(
            submission_id=submission_id,
            hospital_id=hospital_id,
            doctor_id=doctor_id,
            extraction_id=extraction_id,
            insights=insights,
            hospital_code=hospital_code,
            recording_metadata=recording_metadata,
            uhid=uhid,
        )
    except Exception as e:
        # Catch all exceptions to ensure fire-and-forget behavior
        logger.warning(f"[REALTIME_PUBLISH] Fire-and-forget publish failed for submission_id={submission_id}: {e}")


# ============================================================================
# Cleanup Function
# ============================================================================

async def cleanup_old_realtime_responses() -> int:
    """
    Clean up realtime responses older than 24 hours.

    This can be called from a scheduled task or manually.

    Returns:
        Number of records deleted
    """
    try:
        # Call the database function that handles cleanup
        result = supabase.rpc("cleanup_old_realtime_responses").execute()

        if result.data is not None:
            deleted_count = result.data
            logger.info(f"[REALTIME_CLEANUP] Deleted {deleted_count} old realtime responses")
            return deleted_count
        return 0

    except Exception as e:
        logger.error(f"[REALTIME_CLEANUP] Failed to cleanup old responses: {e}")
        return 0

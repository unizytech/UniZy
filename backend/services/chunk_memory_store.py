"""
In-Memory Chunk Storage Service

Thread-safe in-memory storage for audio chunks to reduce latency:
- Chunks stored in memory immediately (fast)
- DB save happens asynchronously (fire-and-forget)
- Processing uses in-memory chunks (0ms retrieval vs 500ms from DB)
- DB serves as fallback if memory is unavailable (server restart, etc.)

Key Design:
- session_id is the key (not doctor_id) - isolates concurrent recordings
- Chunks ordered by chunk_index (0, 1, 2, ...)
- TTL-based cleanup prevents memory exhaustion
- Thread-safe with locks for concurrent access

Chunk Completion (Race Condition Fix - Jan 2025):
- Processing only starts when ALL chunks 0..N-1 are present AND is_last received
- Prevents race condition where is_last chunk arrives before earlier chunks
- 2-minute timeout fails session gracefully if chunks don't complete
"""

import asyncio
import threading
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple, Callable

logger = logging.getLogger(__name__)

# Thread-safe storage
_chunk_store: Dict[str, Dict[int, "ChunkData"]] = {}  # session_id → {chunk_index → ChunkData}
_session_last_activity: Dict[str, datetime] = {}  # session_id → last chunk upload time (for TTL refresh)
_chunk_lock = threading.Lock()

# Session readiness tracking (for chunk completion check)
# When is_last=true is received, we store the expected chunk count
_session_ready: Dict[str, int] = {}  # session_id → expected_chunk_count

# Timeout tasks for incomplete sessions
_session_timeout_tasks: Dict[str, asyncio.Task] = {}  # session_id → timeout task

# Configuration
# TTL increased to 30 minutes to support long recordings (previously 5 min caused data loss)
# Bug fix: Long recordings (>5 min) were losing early chunks due to TTL cleanup
CHUNK_TTL_SECONDS = 1800  # 30 minutes - supports recordings up to 30 min
MAX_CHUNKS_PER_SESSION = 500  # Increased from 100 to support long recordings (~10s chunks = 83 min max)
MAX_CHUNK_SIZE_BYTES = 50 * 1024 * 1024  # 50MB per chunk (supports file uploads)
CHUNK_COMPLETION_TIMEOUT_SECONDS = 120  # 2 minutes to wait for all chunks after is_last


@dataclass
class ChunkData:
    """Data structure for a single audio chunk."""
    audio_data: str  # base64-encoded audio
    mime_type: str
    duration_seconds: Optional[float]
    is_last: bool
    stored_at: datetime
    chunk_index: int


def store_chunk(
    session_id: str,
    chunk_index: int,
    audio_data: str,
    mime_type: str,
    duration_seconds: Optional[float] = None,
    is_last: bool = False,
) -> bool:
    """
    Store a chunk in memory.

    Args:
        session_id: Unique session ID (UUID string)
        chunk_index: Sequential chunk index (0, 1, 2, ...)
        audio_data: Base64-encoded audio data
        mime_type: Audio MIME type (e.g., 'audio/webm')
        duration_seconds: Optional duration of chunk
        is_last: Whether this is the final chunk

    Returns:
        True if stored successfully, False if rejected (size limit, etc.)
    """
    # Safety check: reject oversized chunks
    if len(audio_data) > MAX_CHUNK_SIZE_BYTES:
        logger.warning(
            f"[CHUNK_MEMORY] Rejected oversized chunk: session={session_id[:8]}..., "
            f"index={chunk_index}, size={len(audio_data)} bytes"
        )
        return False

    chunk = ChunkData(
        audio_data=audio_data,
        mime_type=mime_type,
        duration_seconds=duration_seconds,
        is_last=is_last,
        stored_at=datetime.now(timezone.utc),
        chunk_index=chunk_index,
    )

    with _chunk_lock:
        # Initialize session dict if needed
        if session_id not in _chunk_store:
            _chunk_store[session_id] = {}

        # Safety check: limit chunks per session
        if len(_chunk_store[session_id]) >= MAX_CHUNKS_PER_SESSION:
            logger.warning(
                f"[CHUNK_MEMORY] Session {session_id[:8]}... has too many chunks "
                f"({MAX_CHUNKS_PER_SESSION}), rejecting new chunk"
            )
            return False

        _chunk_store[session_id][chunk_index] = chunk

        # Refresh session activity timestamp (prevents TTL expiry during active recording)
        # This ensures long recordings don't lose early chunks
        _session_last_activity[session_id] = datetime.now(timezone.utc)

        chunk_count = len(_chunk_store[session_id])
        total_sessions = len(_chunk_store)

    logger.info(
        f"[CHUNK_MEMORY] Stored chunk {chunk_index} for session {session_id[:8]}... "
        f"(size: {len(audio_data) / 1024:.1f} KB, is_last: {is_last}, "
        f"session_chunks: {chunk_count}, total_sessions: {total_sessions})"
    )

    return True


def get_chunks_sorted(session_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Get all chunks for a session, sorted by chunk_index.

    Args:
        session_id: Unique session ID (UUID string)

    Returns:
        List of chunk dicts (matching DB format) sorted by chunk_index,
        or None if session not found in memory
    """
    with _chunk_lock:
        if session_id not in _chunk_store:
            logger.debug(f"[CHUNK_MEMORY] Session {session_id[:8]}... not found in memory")
            return None

        session_chunks = _chunk_store[session_id]

        if not session_chunks:
            logger.debug(f"[CHUNK_MEMORY] Session {session_id[:8]}... has no chunks")
            return None

        # Sort by chunk_index and convert to dict format (matching DB schema)
        sorted_chunks = sorted(session_chunks.values(), key=lambda c: c.chunk_index)

        result = []
        for chunk in sorted_chunks:
            result.append({
                "session_id": session_id,
                "chunk_index": chunk.chunk_index,
                "audio_data": chunk.audio_data,
                "mime_type": chunk.mime_type,
                "duration_seconds": chunk.duration_seconds,
                "is_last": chunk.is_last,
            })

        logger.info(
            f"[CHUNK_MEMORY] Retrieved {len(result)} chunks for session {session_id[:8]}..."
        )

        return result


def has_all_chunks(session_id: str) -> bool:
    """
    Check if all chunks (including is_last=True) are stored for a session.

    Args:
        session_id: Unique session ID (UUID string)

    Returns:
        True if session has chunks and the last chunk is marked is_last=True
    """
    with _chunk_lock:
        if session_id not in _chunk_store:
            return False

        session_chunks = _chunk_store[session_id]
        if not session_chunks:
            return False

        # Check if any chunk has is_last=True
        return any(chunk.is_last for chunk in session_chunks.values())


def clear_session(session_id: str) -> int:
    """
    Clear all chunks for a session from memory.

    Call this after successful stitching to free memory.
    Also cleans up session ready state and cancels any pending timeout.

    Args:
        session_id: Unique session ID (UUID string)

    Returns:
        Number of chunks cleared
    """
    # Cancel any pending timeout first (before acquiring lock to avoid deadlock)
    cancel_completion_timeout(session_id)

    with _chunk_lock:
        if session_id not in _chunk_store:
            # Also clean up activity and ready tracking even if chunks are gone
            _session_last_activity.pop(session_id, None)
            _session_ready.pop(session_id, None)
            return 0

        chunk_count = len(_chunk_store[session_id])
        del _chunk_store[session_id]
        # Also clean up activity and ready tracking
        _session_last_activity.pop(session_id, None)
        _session_ready.pop(session_id, None)

    logger.info(f"[CHUNK_MEMORY] Cleared {chunk_count} chunks for session {session_id[:8]}...")
    return chunk_count


def cleanup_expired() -> int:
    """
    Remove expired sessions from memory.

    Sessions are expired based on their LAST ACTIVITY timestamp (when the last chunk
    was uploaded), NOT the oldest chunk timestamp. This prevents data loss for long
    recordings where early chunks would otherwise be deleted while recording continues.

    Call this periodically (e.g., every minute) to prevent memory leaks.

    Returns:
        Number of sessions removed
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=CHUNK_TTL_SECONDS)

    expired_sessions = []

    with _chunk_lock:
        for session_id, chunks in _chunk_store.items():
            if not chunks:
                expired_sessions.append(session_id)
                continue

            # Check if session has been inactive for longer than TTL
            # Uses session activity timestamp (updated on each chunk upload)
            # Fallback to oldest chunk timestamp if activity not tracked (legacy sessions)
            last_activity = _session_last_activity.get(session_id)
            if last_activity:
                if last_activity < cutoff:
                    expired_sessions.append(session_id)
            else:
                # Fallback for sessions without activity tracking
                oldest_chunk = min(chunks.values(), key=lambda c: c.stored_at)
                if oldest_chunk.stored_at < cutoff:
                    expired_sessions.append(session_id)

        for session_id in expired_sessions:
            del _chunk_store[session_id]
            # Also clean up activity tracking
            _session_last_activity.pop(session_id, None)

    if expired_sessions:
        logger.info(f"[CHUNK_MEMORY] Cleaned up {len(expired_sessions)} expired sessions")

    return len(expired_sessions)


def get_stats() -> Dict[str, Any]:
    """
    Get memory store statistics for monitoring.

    Returns:
        Dict with session count, chunk count, memory usage estimate
    """
    with _chunk_lock:
        total_sessions = len(_chunk_store)
        total_chunks = sum(len(chunks) for chunks in _chunk_store.values())

        # Estimate memory usage (base64 data + overhead)
        total_bytes = 0
        for chunks in _chunk_store.values():
            for chunk in chunks.values():
                total_bytes += len(chunk.audio_data)

        return {
            "total_sessions": total_sessions,
            "total_chunks": total_chunks,
            "estimated_memory_mb": total_bytes / (1024 * 1024),
            "ttl_seconds": CHUNK_TTL_SECONDS,
            "max_chunks_per_session": MAX_CHUNKS_PER_SESSION,
        }


def get_session_bytes_since_chunk(session_id: str, since_chunk_index: int) -> int:
    """Sum estimated decoded byte size of chunks with index > since_chunk_index.

    Used by the segment-pipeline byte-budget trigger: a new segment fires when
    cumulative bytes since the last boundary cross the SEGMENT_BYTE_BUDGET
    target. Use ``since_chunk_index = -1`` to sum all chunks (first segment).

    Estimation: base64-encoded length × 3/4 ≈ raw bytes. Slight overestimate
    (up to 2 bytes per chunk from padding) which is fine — gives a conservative
    cap that errs toward firing segments slightly earlier rather than later.
    """
    with _chunk_lock:
        session_chunks = _chunk_store.get(session_id)
        if not session_chunks:
            return 0
        return sum(
            (len(chunk.audio_data) * 3) // 4
            for chunk in session_chunks.values()
            if chunk.chunk_index > since_chunk_index
        )


def get_session_audio_duration(session_id: str) -> Optional[float]:
    """
    Get total audio duration for a session from stored chunks.

    Used for Live API usage logging - estimates audio duration from:
    1. Sum of duration_seconds if available on chunks
    2. Fallback: estimate from base64 data size (~32KB/s for PCM 16kHz base64)

    Args:
        session_id: Unique session ID (UUID string)

    Returns:
        Total audio duration in seconds, or None if session not found
    """
    import base64

    with _chunk_lock:
        if session_id not in _chunk_store:
            logger.debug(f"[CHUNK_MEMORY] Session {session_id[:8]}... not found for duration calc")
            return None

        session_chunks = _chunk_store[session_id]
        if not session_chunks:
            return None

        # Try summing duration_seconds first
        total_duration = sum(
            chunk.duration_seconds or 0
            for chunk in session_chunks.values()
        )

        if total_duration > 0:
            logger.debug(
                f"[CHUNK_MEMORY] Session {session_id[:8]}... duration from chunks: {total_duration:.1f}s"
            )
            return total_duration

        # Fallback: estimate from base64 data size
        # PCM 16kHz mono = 16,000 samples/sec × 2 bytes = 32KB/s raw
        # Base64 encoding adds ~33% overhead, so ~42KB/s for base64-encoded PCM
        # For WebM/Opus it's ~8-16KB/s base64, so use conservative 16KB/s
        total_bytes = sum(len(chunk.audio_data) for chunk in session_chunks.values())
        estimated_duration = total_bytes / 16000  # Conservative estimate

        logger.debug(
            f"[CHUNK_MEMORY] Session {session_id[:8]}... duration estimated from size: "
            f"{estimated_duration:.1f}s ({total_bytes / 1024:.1f} KB)"
        )

        return estimated_duration


# ============================================================================
# Chunk Completion Tracking (Race Condition Fix)
# ============================================================================

def mark_session_ready_for_processing(session_id: str, expected_count: int) -> None:
    """
    Mark session as ready when is_last=true is received.

    This records the expected chunk count so we can verify all chunks 0..N-1
    are present before starting processing.

    Args:
        session_id: Unique session ID (UUID string)
        expected_count: Total number of chunks expected (chunk_index + 1 of last chunk)
    """
    with _chunk_lock:
        _session_ready[session_id] = expected_count

    logger.info(
        f"[CHUNK_MEMORY] Session {session_id[:8]}... marked ready for processing "
        f"(expected {expected_count} chunks)"
    )


def get_expected_chunk_count(session_id: str) -> Optional[int]:
    """
    Get expected chunk count if is_last has been received.

    Args:
        session_id: Unique session ID (UUID string)

    Returns:
        Expected chunk count if is_last received, None otherwise
    """
    with _chunk_lock:
        return _session_ready.get(session_id)


def are_all_chunks_present(session_id: str, expected_count: int) -> Tuple[bool, List[int]]:
    """
    Check if all chunks 0..N-1 are present in memory.

    Args:
        session_id: Unique session ID (UUID string)
        expected_count: Expected number of chunks (N)

    Returns:
        Tuple of (all_present: bool, missing_indices: List[int])
    """
    with _chunk_lock:
        if session_id not in _chunk_store:
            return False, list(range(expected_count))

        session_chunks = _chunk_store[session_id]
        present_indices = set(session_chunks.keys())
        expected_indices = set(range(expected_count))
        missing = expected_indices - present_indices

        return len(missing) == 0, sorted(missing)


def get_present_chunk_indices(session_id: str) -> List[int]:
    """
    Get list of chunk indices currently present in memory.

    Args:
        session_id: Unique session ID (UUID string)

    Returns:
        List of chunk indices present in memory
    """
    with _chunk_lock:
        if session_id not in _chunk_store:
            return []
        return sorted(_chunk_store[session_id].keys())


def can_start_processing(session_id: str) -> Tuple[bool, str]:
    """
    Check if processing can start for a session.

    Processing can start when:
    1. is_last has been received (session marked ready)
    2. All chunks 0..N-1 are present in memory
    3. Chunk 0 exists (WebM header required for valid audio)

    Args:
        session_id: Unique session ID (UUID string)

    Returns:
        Tuple of (can_start: bool, reason_if_not: str)

    NOTE: This is a read-only check. Use can_start_processing_atomically()
    to prevent race conditions when triggering processing.
    """
    with _chunk_lock:
        return _check_can_start_processing_unlocked(session_id)


def _check_can_start_processing_unlocked(session_id: str) -> Tuple[bool, str]:
    """
    Internal helper - checks if processing can start (must hold _chunk_lock).

    Returns:
        Tuple of (can_start: bool, reason_if_not: str)
    """
    # Check if is_last has been received
    expected = _session_ready.get(session_id)
    if expected is None:
        return False, "is_last not received yet"

    # Check if session has chunks in memory
    if session_id not in _chunk_store:
        return False, "no chunks in memory"

    chunks = _chunk_store[session_id]
    present = set(chunks.keys())
    expected_set = set(range(expected))
    missing = expected_set - present

    if missing:
        return False, f"missing chunks: {sorted(missing)}"

    # Verify chunk 0 exists (WebM header required)
    if 0 not in present:
        return False, "chunk 0 (WebM header) missing"

    return True, "all chunks present"


def can_start_processing_atomically(session_id: str) -> Tuple[bool, str]:
    """
    Atomically check if processing can start AND mark as started.

    This function ensures only ONE caller can trigger processing for a session.
    If processing can start, the session ready state is immediately cleared
    so subsequent calls return False.

    This prevents race conditions where multiple chunk uploads trigger
    duplicate processing jobs.

    Args:
        session_id: Unique session ID (UUID string)

    Returns:
        Tuple of (can_start: bool, reason_if_not: str)
        - If True: caller should trigger processing (state is now cleared)
        - If False: either not ready, or another caller already started processing
    """
    with _chunk_lock:
        can_start, reason = _check_can_start_processing_unlocked(session_id)

        if can_start:
            # Atomically clear ready state to prevent duplicate processing
            _session_ready.pop(session_id, None)
            logger.debug(
                f"[CHUNK_STORE] Processing started atomically for {session_id[:8]}... "
                f"(ready state cleared)"
            )

        return can_start, reason


def clear_session_ready_state(session_id: str) -> None:
    """
    Clear session readiness state after processing starts or timeout.

    Args:
        session_id: Unique session ID (UUID string)
    """
    with _chunk_lock:
        _session_ready.pop(session_id, None)


# ============================================================================
# Timeout Handling for Incomplete Sessions
# ============================================================================

async def _chunk_timeout_handler(
    session_id: str,
    expected_count: int,
    on_timeout_callback: Optional[Callable] = None
) -> None:
    """
    Background task that fails session if chunks don't arrive in time.

    Args:
        session_id: Unique session ID (UUID string)
        expected_count: Expected number of chunks
        on_timeout_callback: Optional async callback to call on timeout
    """
    try:
        await asyncio.sleep(CHUNK_COMPLETION_TIMEOUT_SECONDS)

        # Check if still incomplete
        can_start, reason = can_start_processing(session_id)
        if not can_start:
            present_indices = get_present_chunk_indices(session_id)
            logger.error(
                f"[CHUNK_TIMEOUT] Session {session_id[:8]}... timed out after "
                f"{CHUNK_COMPLETION_TIMEOUT_SECONDS}s. Reason: {reason}. "
                f"Expected {expected_count} chunks, got {len(present_indices)}: {present_indices}"
            )

            # Call timeout callback if provided (for webhook notification)
            if on_timeout_callback:
                try:
                    await on_timeout_callback(
                        session_id=session_id,
                        reason=reason,
                        expected_count=expected_count,
                        present_indices=present_indices
                    )
                except Exception as e:
                    logger.error(f"[CHUNK_TIMEOUT] Callback failed for {session_id[:8]}...: {e}")

            # Clear session state (but keep chunks in DB for retry)
            clear_session_ready_state(session_id)
            clear_session(session_id)  # Clear memory only
        else:
            # Processing already started (race condition - another path triggered it)
            logger.debug(f"[CHUNK_TIMEOUT] Session {session_id[:8]}... completed before timeout")

    except asyncio.CancelledError:
        logger.debug(f"[CHUNK_TIMEOUT] Timeout cancelled for {session_id[:8]}... (processing started)")
    except Exception as e:
        logger.error(f"[CHUNK_TIMEOUT] Error in timeout handler for {session_id[:8]}...: {e}")


def start_completion_timeout(
    session_id: str,
    expected_count: int,
    on_timeout_callback: Optional[Callable] = None
) -> None:
    """
    Start timeout countdown when is_last is received.

    If all chunks don't arrive within CHUNK_COMPLETION_TIMEOUT_SECONDS,
    the session will be failed and webhook notification sent.

    Args:
        session_id: Unique session ID (UUID string)
        expected_count: Expected number of chunks
        on_timeout_callback: Optional async callback to call on timeout
    """
    # Cancel existing timeout if any (shouldn't happen, but safety)
    cancel_completion_timeout(session_id)

    # Start new timeout task
    try:
        loop = asyncio.get_event_loop()
        task = loop.create_task(
            _chunk_timeout_handler(session_id, expected_count, on_timeout_callback)
        )
        _session_timeout_tasks[session_id] = task

        logger.info(
            f"[CHUNK_TIMEOUT] Started {CHUNK_COMPLETION_TIMEOUT_SECONDS}s timeout for "
            f"session {session_id[:8]}... (expecting {expected_count} chunks)"
        )
    except RuntimeError:
        # No event loop - we're probably in a synchronous context
        logger.warning(
            f"[CHUNK_TIMEOUT] Cannot start timeout for {session_id[:8]}... - no event loop"
        )


def cancel_completion_timeout(session_id: str) -> bool:
    """
    Cancel timeout when all chunks arrive successfully.

    Args:
        session_id: Unique session ID (UUID string)

    Returns:
        True if a timeout was cancelled, False if no timeout was active
    """
    if session_id in _session_timeout_tasks:
        task = _session_timeout_tasks.pop(session_id)
        task.cancel()
        logger.debug(f"[CHUNK_TIMEOUT] Cancelled timeout for session {session_id[:8]}...")
        return True
    return False


def cleanup_timeout_tasks() -> int:
    """
    Clean up any completed timeout tasks.
    Called periodically to prevent memory leaks.

    Returns:
        Number of tasks cleaned up
    """
    completed = []
    for session_id, task in _session_timeout_tasks.items():
        if task.done():
            completed.append(session_id)

    for session_id in completed:
        _session_timeout_tasks.pop(session_id, None)

    if completed:
        logger.debug(f"[CHUNK_TIMEOUT] Cleaned up {len(completed)} completed timeout tasks")

    return len(completed)

"""
In-Memory Segment Transcription Store

Thread-safe in-memory storage for segment transcripts during long audio processing.
Follows the same pattern as chunk_memory_store.py.

Used by:
- Live recording path: stores segment transcripts as they complete during recording
- Recording processor: retrieves and combines segment transcripts
- Reprocess path: stores segment transcripts during parallel transcription

Lifecycle:
1. register_segment() - mark segment as in-flight when transcription starts
2. store_segment_transcript() - store result when transcription completes
3. get_all_transcripts_ordered() - retrieve all transcripts in order for combining
4. clear_session() - cleanup after processing completes
"""

import threading
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Thread-safe storage
_segment_store: Dict[str, "SessionSegmentData"] = {}
_segment_lock = threading.Lock()

# Configuration
SEGMENT_TTL_SECONDS = 1800  # 30 minutes (matches chunk store)
SPLIT_TRANSCRIPTION_THRESHOLD_SECONDS = 1500  # 25 min - trigger segmentation (reprocess path)

# Live segmentation policy (Apr 2026):
# Each segment must stay under Gemini's 15 MB inline-data threshold so we keep
# transcription on the fast inline path (no Files API upload round-trip). We
# trigger primarily on cumulative bytes since the last boundary; MAX_SEGMENT_SECONDS
# is a safety ceiling that catches pathological low-bitrate cases (e.g. quiet
# room, very efficient codec) where pure byte-budget would never fire.
SEGMENT_BYTE_BUDGET = 12 * 1024 * 1024  # 12 MB target (3 MB margin under 15 MB inline cap)
MAX_SEGMENT_SECONDS = 900  # 15 min hard ceiling (sanity cap for very low bitrates)
SEGMENT_DURATION_SECONDS = 600  # 10 min — fallback when byte tracking unavailable
                                 # (legacy reprocess paths still reference this)
SEGMENT_OVERLAP_SECONDS = 60  # 1 min overlap between segments
DEFAULT_OVERLAP_CHUNKS = 6  # Default overlap chunks if duration unknown


@dataclass
class SegmentInfo:
    """Data for a single audio segment."""
    segment_index: int
    start_chunk_index: int
    end_chunk_index: int  # inclusive
    status: str  # "transcribing", "completed", "failed"
    transcript: Optional[str] = None
    detected_language: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SessionSegmentData:
    """All segment data for a session."""
    segments: Dict[int, SegmentInfo] = field(default_factory=dict)
    last_boundary_chunk_index: int = -1
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def register_segment(
    session_id: str,
    segment_index: int,
    start_chunk_index: int,
    end_chunk_index: int,
) -> bool:
    """Register a new segment for transcription. Returns False if already registered."""
    with _segment_lock:
        if session_id not in _segment_store:
            _segment_store[session_id] = SessionSegmentData()

        session_data = _segment_store[session_id]

        if segment_index in session_data.segments:
            logger.warning(
                f"[SEGMENT_STORE] Segment {segment_index} already registered "
                f"for session {session_id[:8]}..."
            )
            return False

        session_data.segments[segment_index] = SegmentInfo(
            segment_index=segment_index,
            start_chunk_index=start_chunk_index,
            end_chunk_index=end_chunk_index,
            status="transcribing",
        )
        session_data.last_boundary_chunk_index = end_chunk_index
        session_data.last_activity = datetime.now(timezone.utc)

    logger.info(
        f"[SEGMENT_STORE] Registered segment {segment_index} for session {session_id[:8]}... "
        f"(chunks {start_chunk_index}-{end_chunk_index})"
    )
    return True


def store_segment_transcript(
    session_id: str,
    segment_index: int,
    transcript: str,
    detected_language: Optional[str] = None,
) -> bool:
    """Store completed transcript for a segment."""
    with _segment_lock:
        if session_id not in _segment_store:
            logger.warning(f"[SEGMENT_STORE] Session {session_id[:8]}... not found")
            return False

        session_data = _segment_store[session_id]
        if segment_index not in session_data.segments:
            logger.warning(
                f"[SEGMENT_STORE] Segment {segment_index} not found "
                f"for session {session_id[:8]}..."
            )
            return False

        segment = session_data.segments[segment_index]
        segment.transcript = transcript
        segment.detected_language = detected_language
        segment.status = "completed"
        session_data.last_activity = datetime.now(timezone.utc)

    logger.info(
        f"[SEGMENT_STORE] Stored transcript for segment {segment_index} "
        f"of session {session_id[:8]}... ({len(transcript)} chars)"
    )
    return True


def mark_segment_failed(session_id: str, segment_index: int, error: str = "") -> None:
    """Mark a segment as failed."""
    with _segment_lock:
        if session_id in _segment_store and segment_index in _segment_store[session_id].segments:
            _segment_store[session_id].segments[segment_index].status = "failed"
            _segment_store[session_id].last_activity = datetime.now(timezone.utc)
    logger.warning(
        f"[SEGMENT_STORE] Segment {segment_index} failed "
        f"for session {session_id[:8]}...: {error}"
    )


def has_segments(session_id: str) -> bool:
    """Check if a session has any registered segments."""
    with _segment_lock:
        data = _segment_store.get(session_id)
        return data is not None and len(data.segments) > 0


def get_segment_count(session_id: str) -> int:
    """Get number of registered segments for a session."""
    with _segment_lock:
        data = _segment_store.get(session_id)
        return len(data.segments) if data else 0


def get_completed_segment_count(session_id: str) -> int:
    """Get number of completed segments for a session."""
    with _segment_lock:
        data = _segment_store.get(session_id)
        if not data:
            return 0
        return sum(1 for s in data.segments.values() if s.status == "completed")


def get_all_transcripts_ordered(session_id: str) -> List[str]:
    """Get all completed transcripts in segment order."""
    with _segment_lock:
        data = _segment_store.get(session_id)
        if not data:
            return []

        result = []
        for idx in sorted(data.segments.keys()):
            seg = data.segments[idx]
            if seg.status == "completed" and seg.transcript:
                result.append(seg.transcript)
        return result


def get_last_boundary_chunk_index(session_id: str) -> int:
    """Get the end chunk index of the last registered segment."""
    with _segment_lock:
        data = _segment_store.get(session_id)
        return data.last_boundary_chunk_index if data else -1


def get_next_segment_index(session_id: str) -> int:
    """Get the next segment index to use."""
    with _segment_lock:
        data = _segment_store.get(session_id)
        if not data or not data.segments:
            return 0
        return max(data.segments.keys()) + 1


def get_pending_segments(session_id: str) -> List[int]:
    """Get list of segment indices that are still transcribing."""
    with _segment_lock:
        data = _segment_store.get(session_id)
        if not data:
            return []
        return [
            idx for idx, seg in data.segments.items()
            if seg.status == "transcribing"
        ]


def clear_session(session_id: str) -> int:
    """Clear all segment data for a session. Returns number of segments cleared."""
    with _segment_lock:
        data = _segment_store.pop(session_id, None)
        count = len(data.segments) if data else 0
    if count:
        logger.info(f"[SEGMENT_STORE] Cleared {count} segments for session {session_id[:8]}...")
    return count


def cleanup_expired() -> int:
    """Remove expired sessions. Returns number of sessions removed."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=SEGMENT_TTL_SECONDS)
    expired = []

    with _segment_lock:
        for session_id, data in _segment_store.items():
            if data.last_activity < cutoff:
                expired.append(session_id)
        for session_id in expired:
            del _segment_store[session_id]

    if expired:
        logger.info(f"[SEGMENT_STORE] Cleaned up {len(expired)} expired sessions")
    return len(expired)

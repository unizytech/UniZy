"""Tests for the byte-budget segment-trigger helper.

Verifies get_session_bytes_since_chunk produces stable estimates for the
segment pipeline trigger added 2026-04-29.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.chunk_memory_store import (  # noqa: E402
    clear_session,
    get_session_bytes_since_chunk,
    store_chunk,
)
from services.segment_transcription_store import (  # noqa: E402
    MAX_SEGMENT_SECONDS,
    SEGMENT_BYTE_BUDGET,
    SEGMENT_DURATION_SECONDS,
)


def _b64(n_bytes: int) -> str:
    """Base64-encoded blob whose decoded size is exactly n_bytes."""
    return base64.b64encode(b"\x00" * n_bytes).decode("ascii")


def test_constants_match_design_intent():
    assert SEGMENT_BYTE_BUDGET == 12 * 1024 * 1024  # 12 MB
    assert MAX_SEGMENT_SECONDS == 900               # 15 min
    assert SEGMENT_DURATION_SECONDS == 600          # 10 min fallback


def test_bytes_since_chunk_returns_zero_for_unknown_session():
    assert get_session_bytes_since_chunk("missing-session", -1) == 0


def test_bytes_since_chunk_sums_all_when_since_negative():
    sid = "test-byte-sum-all"
    clear_session(sid)
    for idx in range(3):
        store_chunk(sid, idx, _b64(1024), "audio/webm", duration_seconds=10.0)
    total = get_session_bytes_since_chunk(sid, -1)
    # Estimate is len(b64)*3//4 ≈ raw bytes; allow ±2 bytes per chunk for padding
    assert 3 * 1024 - 6 <= total <= 3 * 1024 + 6
    clear_session(sid)


def test_bytes_since_chunk_excludes_chunks_at_or_below_boundary():
    sid = "test-byte-since"
    clear_session(sid)
    for idx in range(5):
        store_chunk(sid, idx, _b64(1024), "audio/webm", duration_seconds=10.0)
    bytes_after_1 = get_session_bytes_since_chunk(sid, 1)
    assert 3 * 1024 - 6 <= bytes_after_1 <= 3 * 1024 + 6
    assert get_session_bytes_since_chunk(sid, 4) == 0
    clear_session(sid)


def test_bytes_since_chunk_realistic_high_bitrate_triggers_around_57_chunks():
    """Ranjan-style high-bitrate chunks (215 KB each, 10s).
    With 12 MB budget, the trigger should fire around chunk 56–58 ≈ 9.5 min."""
    sid = "test-budget-high"
    clear_session(sid)
    chunk_raw = 215 * 1024
    triggered_at = None
    for idx in range(80):
        store_chunk(sid, idx, _b64(chunk_raw), "audio/webm", duration_seconds=10.0)
        if get_session_bytes_since_chunk(sid, -1) >= SEGMENT_BYTE_BUDGET:
            triggered_at = idx
            break
    assert triggered_at is not None, "Budget should have been crossed"
    assert 55 <= triggered_at <= 60, f"Triggered too early/late: chunk {triggered_at}"
    clear_session(sid)


def test_bytes_since_chunk_low_bitrate_needs_duration_ceiling():
    """Low-bitrate (109 KB / 10s ≈ 87 kbps): byte budget alone wouldn't fire
    until ~19 min — past MAX_SEGMENT_SECONDS (15 min). This proves why the
    duration ceiling is needed as a safety net."""
    sid = "test-budget-low"
    clear_session(sid)
    chunk_raw = 109 * 1024
    triggered_at = None
    for idx in range(140):
        store_chunk(sid, idx, _b64(chunk_raw), "audio/webm", duration_seconds=10.0)
        if get_session_bytes_since_chunk(sid, -1) >= SEGMENT_BYTE_BUDGET:
            triggered_at = idx
            break
    assert triggered_at is not None
    assert 110 <= triggered_at <= 120
    duration_at_trigger = (triggered_at + 1) * 10
    assert duration_at_trigger > MAX_SEGMENT_SECONDS, (
        f"Low-bitrate budget trigger at {duration_at_trigger}s exceeds {MAX_SEGMENT_SECONDS}s — "
        f"this is exactly the case where the MAX_SEGMENT_SECONDS ceiling fires first."
    )
    clear_session(sid)


def test_bytes_since_chunk_segment_2_only_counts_post_boundary_chunks():
    """When the second segment is being checked, only chunks past the prior
    boundary should count toward the budget."""
    sid = "test-budget-seg2"
    clear_session(sid)
    chunk_raw = 215 * 1024
    # Pretend prior segment consumed chunks 0..56 (i.e. boundary is 56)
    for idx in range(120):
        store_chunk(sid, idx, _b64(chunk_raw), "audio/webm", duration_seconds=10.0)
    bytes_post_boundary = get_session_bytes_since_chunk(sid, 56)
    # Chunks 57..119 = 63 chunks × 215 KB ≈ 13.2 MB
    expected_min = 63 * 215 * 1024 - 200
    expected_max = 63 * 215 * 1024 + 200
    assert expected_min <= bytes_post_boundary <= expected_max
    # Should be over budget (12 MB)
    assert bytes_post_boundary >= SEGMENT_BYTE_BUDGET
    clear_session(sid)

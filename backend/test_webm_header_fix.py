"""
Unit tests for the WebM init-header relocation fix.

Covers the MediaRecorder defect where the EBML init segment lands in chunk 1/2
instead of chunk 0, which a naive index-order concat would place mid-stream and
a decoder would reject. See Docs/webm-header-fix.md.

Run from the backend/ directory:  pytest test_webm_header_fix.py -v
"""

import base64

from services.audio_splitter import (
    _EBML_MAGIC,
    _WEBM_CLUSTER_ID,
    _extract_webm_init_segment,
    normalize_webm_header_order,
    stitch_and_get_bytes_for_chunk_range,
)
from services.audio_stitcher import stitch_audio_chunks


# --- synthetic WebM-like byte builders -------------------------------------
# init segment = EBML magic + (Segment/Info/Tracks stand-in, no Cluster id)
_INIT = _EBML_MAGIC + b"\x11SEGMENT_INFO_TRACKS_CODEC_CONFIG\x22"


def _cluster(tag: bytes) -> bytes:
    """A raw Cluster: Cluster element id + distinctive payload (no EBML magic)."""
    return _WEBM_CLUSTER_ID + b"::" + tag


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def _chunk(index: int, raw: bytes, mime: str = "audio/webm") -> dict:
    return {"chunk_index": index, "audio_data": _b64(raw), "mime_type": mime}


# Cluster payloads for chunks 0..3 (distinctive, contain no magic bytes)
C0, C1, C2, C3 = (_cluster(b"AAA"), _cluster(b"BBB"), _cluster(b"CCC"), _cluster(b"DDD"))


# --- _extract_webm_init_segment --------------------------------------------

def test_extract_init_none_for_headerless_chunk():
    assert _extract_webm_init_segment(C0) is None          # raw cluster, no header
    assert _extract_webm_init_segment(b"") is None


def test_extract_init_returns_prefix_for_carrier():
    carrier = _INIT + C0
    assert _extract_webm_init_segment(carrier) == _INIT


# --- normalize_webm_header_order -------------------------------------------

def test_normalize_is_noop_when_chunk0_has_header():
    healthy = [_INIT + C0, C1, C2]
    out = normalize_webm_header_order(healthy)
    assert out == healthy                                   # fast path, unchanged


def test_normalize_relocates_header_from_chunk1():
    # header landed in chunk 1
    broken = [C0, _INIT + C1, C2]
    out = normalize_webm_header_order(broken)
    assert b"".join(out) == _INIT + C0 + C1 + C2            # single header at front
    assert b"".join(out).count(_EBML_MAGIC) == 1
    # order preserved: cluster sequence identical to a healthy recording
    assert b"".join(out)[len(_INIT):] == C0 + C1 + C2


def test_normalize_relocates_header_from_chunk2():
    broken = [C0, C1, _INIT + C2]
    out = normalize_webm_header_order(broken)
    assert b"".join(out) == _INIT + C0 + C1 + C2
    assert b"".join(out).count(_EBML_MAGIC) == 1


def test_normalize_no_header_anywhere_passes_through():
    headerless = [C0, C1, C2]
    out = normalize_webm_header_order(headerless)           # must not raise
    assert b"".join(out) == C0 + C1 + C2
    assert b"".join(out).count(_EBML_MAGIC) == 0


# --- full stitch (stitch_audio_chunks) -------------------------------------

def test_full_stitch_header_in_chunk1():
    chunks = [_chunk(0, C0), _chunk(1, _INIT + C1), _chunk(2, C2)]
    b64, mime = stitch_audio_chunks(chunks)
    out = base64.b64decode(b64)
    assert out.startswith(_EBML_MAGIC)
    assert out.count(_EBML_MAGIC) == 1
    assert out == _INIT + C0 + C1 + C2


def test_full_stitch_healthy_unchanged():
    chunks = [_chunk(0, _INIT + C0), _chunk(1, C1), _chunk(2, C2)]
    out = base64.b64decode(stitch_audio_chunks(chunks)[0])
    assert out == _INIT + C0 + C1 + C2
    assert out.count(_EBML_MAGIC) == 1


# --- segment-range stitch (stitch_and_get_bytes_for_chunk_range) -----------

def test_range_includes_chunk0_with_header_in_chunk1():
    chunks = [_chunk(0, C0), _chunk(1, _INIT + C1), _chunk(2, C2), _chunk(3, C3)]
    combined, mime = stitch_and_get_bytes_for_chunk_range(chunks, 0, 2)
    assert combined.startswith(_EBML_MAGIC)
    assert combined.count(_EBML_MAGIC) == 1
    assert combined == _INIT + C0 + C1 + C2


def test_range_midrecording_finds_header_in_chunk1():
    # header is in chunk 1; slice 2..3 has no header of its own
    chunks = [_chunk(0, C0), _chunk(1, _INIT + C1), _chunk(2, C2), _chunk(3, C3)]
    combined, mime = stitch_and_get_bytes_for_chunk_range(chunks, 2, 3)
    assert combined.startswith(_EBML_MAGIC)
    assert combined.count(_EBML_MAGIC) == 1
    assert combined == _INIT + C2 + C3                      # init prepended once, slice order kept


def test_range_midrecording_header_in_chunk0():
    chunks = [_chunk(0, _INIT + C0), _chunk(1, C1), _chunk(2, C2), _chunk(3, C3)]
    combined, mime = stitch_and_get_bytes_for_chunk_range(chunks, 2, 3)
    assert combined.startswith(_EBML_MAGIC)
    assert combined.count(_EBML_MAGIC) == 1
    assert combined == _INIT + C2 + C3

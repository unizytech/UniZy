"""
Audio Splitter Service

Provides chunk-range stitching for segment-based parallel transcription.
Used by both live recording path and reprocess path to stitch a range
of audio chunks into a single audio buffer for transcription.
"""

import base64
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# WebM Cluster element ID (Matroska/EBML) — marks the start of audio packets.
# Everything before the first occurrence in chunk 0 is the init segment:
# EBML Header + Segment header + Info + Tracks (codec config).
_WEBM_CLUSTER_ID = b"\x1f\x43\xb6\x75"

# EBML magic at offset 0 of any well-formed WebM/Matroska file. We use this
# to validate that the bytes we *think* are chunk 0 actually carry a header,
# defending against out-of-order chunk arrival or any state where the chunk
# tagged `chunk_index=0` doesn't actually contain the recording's start.
_EBML_MAGIC = b"\x1a\x45\xdf\xa3"

# Mime types that follow the WebM/Matroska container layout where only the
# first chunk carries the EBML+Segment+Tracks init header.
_WEBM_MIME_TYPES = (
    "audio/webm",
    "video/webm",
    "audio/x-matroska",
    "video/x-matroska",
)


def _extract_webm_init_segment(chunk_0_bytes: bytes) -> Optional[bytes]:
    """
    Extract the init segment (EBML+Segment+Tracks) from chunk 0 bytes.

    For MediaRecorder-produced WebM, only chunk 0 carries the container
    header. The init segment is everything before the first Cluster element
    — it contains the codec config Gemini needs to decode subsequent chunks.

    Returns None when the bytes don't look like a real WebM header chunk
    (missing EBML magic, no Cluster found, or Cluster at offset 0). In all
    such cases the caller falls back to plain byte-concatenation. The EBML
    magic check guards against a misidentified chunk 0 — chunks can arrive
    out of order over the network, and we must not splice arbitrary bytes
    onto the front of a downstream segment.
    """
    if not chunk_0_bytes or not chunk_0_bytes.startswith(_EBML_MAGIC):
        return None
    idx = chunk_0_bytes.find(_WEBM_CLUSTER_ID)
    # idx <= 0 covers both "not found" (-1) and "Cluster at offset 0"
    # (which would mean chunk 0 itself has no header — defensive guard).
    if idx <= 0:
        return None
    return chunk_0_bytes[:idx]


def is_webm_mime_type(mime_type: Optional[str]) -> bool:
    """True if the mime type uses the WebM/Matroska container layout (init header
    carried only by the first chunk), so header-order normalization applies."""
    return (mime_type or "").lower().split(";", 1)[0].strip() in _WEBM_MIME_TYPES


def _scan_for_webm_init(
    decoded_chunks: List[bytes], max_scan: int = 3
) -> Optional[Tuple[int, bytes]]:
    """Scan the first `max_scan` decoded chunks for the one carrying the WebM init
    segment. Returns (carrier_index, init_bytes), or None if none carry it."""
    for i in range(min(max_scan, len(decoded_chunks))):
        init = _extract_webm_init_segment(decoded_chunks[i])
        if init:
            return i, init
    return None


def normalize_webm_header_order(
    decoded_chunks: List[bytes], max_scan: int = 3
) -> List[bytes]:
    """Ensure the WebM init segment leads the stream, preserving chunk order.

    MediaRecorder intermittently emits the first Blob without the init segment, so
    the EBML header (``1A 45 DF A3``) lands in chunk 1 (or 2). A naive index-order
    concat then places the header mid-stream, producing an invalid container that
    decoders reject (e.g. 400 INVALID_ARGUMENT).

    Strategy — relocate the header only, never reorder audio:
      * empty list → unchanged
      * chunk 0 already starts with the EBML magic → unchanged (fast path)
      * otherwise find the carrier among the first ``max_scan`` chunks, strip its
        init segment off the carrier, and prepend the init once
      * if no chunk in the first ``max_scan`` carries a header → unchanged + warn
    """
    if not decoded_chunks:
        return decoded_chunks
    if decoded_chunks[0].startswith(_EBML_MAGIC):
        return decoded_chunks  # fast path — already well-formed
    found = _scan_for_webm_init(decoded_chunks, max_scan)
    if found is None:
        logger.warning(
            "[AUDIO_SPLITTER] No EBML header in first %d chunks; passing through "
            "header-less (decoder may reject).",
            min(max_scan, len(decoded_chunks)),
        )
        return decoded_chunks
    carrier_index, init = found
    result = list(decoded_chunks)
    result[carrier_index] = result[carrier_index][len(init):]  # strip header off carrier
    return [init] + result  # prepend the single header once, order preserved


def _find_init_in_first_chunks(
    chunks: List[dict], max_scan: int = 3
) -> Optional[bytes]:
    """Find the WebM init segment among the recording's first `max_scan` chunks.

    The header normally leads chunk 0, but MediaRecorder sometimes emits it in
    chunk 1 or 2. Decodes chunk_index 0..max_scan-1 in order and returns the first
    valid init segment found, or None. Used by mid-recording segment slices, which
    have no header of their own.
    """
    by_index = {}
    for c in chunks:
        ci = c.get("chunk_index", -1)
        if 0 <= ci < max_scan and ci not in by_index:
            by_index[ci] = c
    for ci in range(max_scan):
        c = by_index.get(ci)
        if c is None:
            continue
        try:
            init = _extract_webm_init_segment(base64.b64decode(c.get("audio_data", "")))
        except Exception as e:
            logger.warning(f"[AUDIO_SPLITTER] init scan: decode failed for chunk {ci}: {e}")
            continue
        if init:
            return init
    return None


def stitch_and_get_bytes_for_chunk_range(
    chunks: List[dict],
    start_index: int,
    end_index: int,
) -> Tuple[bytes, str]:
    """
    Stitch a range of chunks and return raw bytes.

    Args:
        chunks: All chunks sorted by chunk_index. MUST include chunk_index 0
            for WebM ranges that start mid-recording — its EBML header is
            extracted and prepended to the output so Gemini can decode the
            slice as a valid WebM container.
        start_index: Start chunk index (inclusive)
        end_index: End chunk index (inclusive)

    Returns:
        Tuple of (audio_bytes, mime_type)

    Raises:
        ValueError: If no chunks found in range
    """
    range_chunks = [
        c for c in chunks
        if start_index <= c.get("chunk_index", -1) <= end_index
    ]

    if not range_chunks:
        raise ValueError(f"No chunks found in range {start_index}-{end_index}")

    range_chunks.sort(key=lambda x: x.get("chunk_index", 0))
    mime_type = range_chunks[0].get("mime_type", "audio/webm")

    decoded = [base64.b64decode(c.get("audio_data", "")) for c in range_chunks]

    min_chunk_index = range_chunks[0].get("chunk_index", start_index)
    is_webm = is_webm_mime_type(mime_type)

    if is_webm and min_chunk_index == 0:
        # Slice starts at the recording's beginning. The init header normally leads
        # chunk 0, but MediaRecorder sometimes emits it in chunk 1/2 (defect). Relocate
        # it to the front in-order so the slice is a valid streaming WebM.
        decoded = normalize_webm_header_order(decoded)
        combined = b"".join(decoded)
    elif is_webm and min_chunk_index > 0:
        # Mid-recording slice: the combined bytes begin with raw Cluster data (no
        # EBML/Segment/Tracks header). Decoders reject such buffers (400
        # INVALID_ARGUMENT). Find the init among the full recording's first 3 chunks
        # (it may be in 0, 1, or 2) and prepend it ONCE.
        combined = b"".join(decoded)
        init_bytes = _find_init_in_first_chunks(chunks, max_scan=3)
        if init_bytes:
            logger.debug(
                f"[AUDIO_SPLITTER] Prepending {len(init_bytes)}B WebM init "
                f"to range {start_index}-{end_index} ({len(combined)}B combined)"
            )
            combined = init_bytes + combined
        else:
            logger.warning(
                f"[AUDIO_SPLITTER] Range {start_index}-{end_index} starts mid-recording "
                f"but no WebM init found in first 3 chunks; falling back to header-less "
                f"concat (decoder may reject)."
            )
    else:
        combined = b"".join(decoded)

    return combined, mime_type

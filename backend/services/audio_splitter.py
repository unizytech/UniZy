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

    combined = b""
    for chunk in range_chunks:
        audio_b64 = chunk.get("audio_data", "")
        combined += base64.b64decode(audio_b64)

    # If this slice doesn't start at chunk 0, the combined bytes begin with
    # raw Cluster data (no EBML/Segment/Tracks header). Gemini rejects such
    # buffers with 400 INVALID_ARGUMENT. Prepend the header from chunk 0
    # ONCE to make the output a valid streaming WebM.
    min_chunk_index = range_chunks[0].get("chunk_index", start_index)
    is_webm = (mime_type or "").lower().split(";", 1)[0].strip() in _WEBM_MIME_TYPES

    if min_chunk_index > 0 and is_webm:
        chunk_0 = next(
            (c for c in chunks if c.get("chunk_index") == 0),
            None,
        )
        if chunk_0 is None:
            logger.warning(
                f"[AUDIO_SPLITTER] Range {start_index}-{end_index} starts at "
                f"chunk_index={min_chunk_index} but chunk 0 not in chunks list; "
                f"falling back to header-less byte concat (Gemini may reject)."
            )
        else:
            try:
                chunk_0_bytes = base64.b64decode(chunk_0.get("audio_data", ""))
                init_bytes = _extract_webm_init_segment(chunk_0_bytes)
                if init_bytes:
                    logger.debug(
                        f"[AUDIO_SPLITTER] Prepending {len(init_bytes)}B WebM init "
                        f"to range {start_index}-{end_index} ({len(combined)}B combined)"
                    )
                    combined = init_bytes + combined
                else:
                    logger.warning(
                        f"[AUDIO_SPLITTER] Could not extract WebM init from chunk 0 "
                        f"({len(chunk_0_bytes)}B); falling back to header-less concat."
                    )
            except Exception as e:
                logger.warning(
                    f"[AUDIO_SPLITTER] WebM init extraction failed: {e}; "
                    f"falling back to header-less concat."
                )

    return combined, mime_type

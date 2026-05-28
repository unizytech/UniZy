"""
Audio Silence Remover Service

Removes silence from audio files before transcription to:
1. Reduce Gemini API costs (less audio data)
2. Speed up transcription (shorter audio = faster response)
3. Improve transcription accuracy (no long silence gaps)

Uses pydub's silence detection (backed by ffmpeg).
"""

import io
import base64
import time
import logging
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    from pydub import AudioSegment
    from pydub.silence import detect_nonsilent
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logger.warning("pydub not available - silence removal disabled")


# MIME type to pydub format mapping
_MIME_FORMAT_MAP = {
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/mp3": "mp3",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/flac": "flac",
    "audio/m4a": "m4a",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/3gpp": "3gp",
}

# pydub format to export format mapping (some formats need different export names)
_EXPORT_FORMAT_MAP = {
    "webm": "webm",
    "mp3": "mp3",
    "wav": "wav",
    "ogg": "ogg",
    "flac": "flac",
    "m4a": "ipod",  # pydub uses 'ipod' for m4a export
    "aac": "adts",
    "3gp": "3gp",
}

# Minimum audio duration to trigger silence removal (15 minutes)
# Short recordings don't benefit enough to justify the processing overhead
MIN_DURATION_FOR_SILENCE_REMOVAL_MS = 1200000  # 20 minutes

# Minimum file size (bytes) to consider for silence removal.
# Uses conservative 4 KB/s (32kbps) estimate so we don't falsely skip
# high-bitrate files. Callers should use this for an early-exit check
# BEFORE calling remove_silence_from_audio / remove_silence_from_base64.
MIN_SIZE_FOR_SILENCE_REMOVAL_BYTES = (MIN_DURATION_FOR_SILENCE_REMOVAL_MS // 1000) * 4 * 1024  # ~3.5 MB


def remove_silence_from_audio(
    audio_bytes: bytes,
    mime_type: str,
    silence_thresh_dbfs: int = -60,
    min_silence_len_ms: int = 5000,
    padding_ms: int = 200,
) -> Tuple[bytes, str, Dict[str, Any]]:
    """
    Remove silence from audio bytes.

    Args:
        audio_bytes: Raw audio bytes
        mime_type: MIME type of the audio
        silence_thresh_dbfs: Volume threshold below which is considered silence (dBFS).
                            More negative = more aggressive (removes quieter sounds).
                            Typical values: -30 (strict), -40 (moderate), -57 (lenient)
        min_silence_len_ms: Minimum continuous silence duration (ms) to remove.
                           Shorter silences (pauses between words) are kept.
                           500ms is good for natural speech pauses.
        padding_ms: Padding to keep around each speech segment (ms).
                   Prevents cutting off speech edges.

    Returns:
        Tuple of (processed_bytes, mime_type, stats_dict)
        stats_dict contains: original_duration_ms, new_duration_ms, removed_ms,
                           silence_removed_pct, speech_segments_count
    """
    if not PYDUB_AVAILABLE:
        logger.warning("[SILENCE_REMOVER] pydub not available, returning original audio")
        return audio_bytes, mime_type, {"removed": False, "reason": "pydub not available"}

    start_time = time.time()

    # Determine input format
    mime_clean = mime_type.split(";")[0].strip().lower()
    input_format = _MIME_FORMAT_MAP.get(mime_clean)

    if not input_format:
        logger.warning(f"[SILENCE_REMOVER] Unknown MIME type: {mime_type}, skipping silence removal")
        return audio_bytes, mime_type, {"removed": False, "reason": f"unknown mime type: {mime_type}"}

    try:
        # Load audio with pydub
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=input_format)
        original_duration_ms = len(audio)

        if original_duration_ms < 3000:  # Don't process audio shorter than 3 seconds
            logger.info(f"[SILENCE_REMOVER] Audio too short ({original_duration_ms}ms), skipping")
            return audio_bytes, mime_type, {
                "removed": False,
                "reason": "audio too short",
                "original_duration_ms": original_duration_ms,
            }

        # Detect non-silent segments
        nonsilent_ranges = detect_nonsilent(
            audio,
            min_silence_len=min_silence_len_ms,
            silence_thresh=silence_thresh_dbfs,
        )

        if not nonsilent_ranges:
            logger.warning("[SILENCE_REMOVER] No speech detected, returning original audio")
            return audio_bytes, mime_type, {
                "removed": False,
                "reason": "no speech detected",
                "all_silent": True,
                "original_duration_ms": original_duration_ms,
            }

        # If silence ratio is low (<20%), not worth processing
        total_speech_ms = sum(end - start for start, end in nonsilent_ranges)
        silence_ratio = 1.0 - (total_speech_ms / original_duration_ms)

        if silence_ratio < 0.20:
            elapsed = time.time() - start_time
            logger.info(
                f"[SILENCE_REMOVER] Low silence ratio ({silence_ratio:.1%}), "
                f"skipping removal (analysis took {elapsed:.2f}s)"
            )
            return audio_bytes, mime_type, {
                "removed": False,
                "reason": f"low silence ratio ({silence_ratio:.1%})",
                "original_duration_ms": original_duration_ms,
                "silence_ratio": round(silence_ratio, 3),
            }

        # Build output by concatenating non-silent segments with padding
        output = AudioSegment.empty()
        for i, (start, end) in enumerate(nonsilent_ranges):
            # Add padding around each segment
            padded_start = max(0, start - padding_ms)
            padded_end = min(original_duration_ms, end + padding_ms)
            output += audio[padded_start:padded_end]

        new_duration_ms = len(output)
        removed_ms = original_duration_ms - new_duration_ms

        # Check minimum useful duration after silence removal (10 seconds)
        MIN_USEFUL_DURATION_MS = 10000  # 10 seconds

        if new_duration_ms < MIN_USEFUL_DURATION_MS:
            logger.warning(
                f"[SILENCE_REMOVER] Post-removal audio too short "
                f"({new_duration_ms}ms < {MIN_USEFUL_DURATION_MS}ms), returning original"
            )
            return audio_bytes, mime_type, {
                "removed": False,
                "reason": f"post-removal audio too short ({new_duration_ms}ms)",
                "too_short_after_removal": True,
                "original_duration_ms": original_duration_ms,
                "would_be_duration_ms": new_duration_ms,
                "silence_removed_pct": round(removed_ms / original_duration_ms * 100, 1),
            }

        # Export back to original format
        export_format = _EXPORT_FORMAT_MAP.get(input_format, input_format)
        buffer = io.BytesIO()

        # Set export parameters for good quality
        export_params = {}
        if export_format in ("webm",):
            export_params = {"codec": "libopus", "parameters": ["-b:a", "64k"]}
        elif export_format in ("mp3",):
            export_params = {"bitrate": "128k"}
        elif export_format in ("ipod",):  # m4a
            export_params = {"codec": "aac", "bitrate": "128k"}

        output.export(buffer, format=export_format, **export_params)
        processed_bytes = buffer.getvalue()

        elapsed = time.time() - start_time

        stats = {
            "removed": True,
            "original_duration_ms": original_duration_ms,
            "new_duration_ms": new_duration_ms,
            "removed_ms": removed_ms,
            "silence_removed_pct": round(removed_ms / original_duration_ms * 100, 1),
            "speech_segments_count": len(nonsilent_ranges),
            "original_size_bytes": len(audio_bytes),
            "new_size_bytes": len(processed_bytes),
            "processing_time_s": round(elapsed, 3),
            "silence_thresh_dbfs": silence_thresh_dbfs,
            "min_silence_len_ms": min_silence_len_ms,
        }

        logger.info(
            f"[SILENCE_REMOVER] Removed {removed_ms}ms silence "
            f"({stats['silence_removed_pct']}%) from {original_duration_ms}ms audio. "
            f"{len(nonsilent_ranges)} speech segments. "
            f"Size: {len(audio_bytes)//1024}KB -> {len(processed_bytes)//1024}KB. "
            f"Took {elapsed:.2f}s"
        )

        return processed_bytes, mime_type, stats

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[SILENCE_REMOVER] Failed after {elapsed:.2f}s: {e}")
        # Return original audio on failure - never block the pipeline
        return audio_bytes, mime_type, {
            "removed": False,
            "reason": f"error: {str(e)}",
        }


def remove_silence_from_base64(
    audio_b64: str,
    mime_type: str,
    silence_thresh_dbfs: int = -60,
    min_silence_len_ms: int = 5000,
    padding_ms: int = 200,
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Convenience wrapper that accepts/returns base64-encoded audio.

    Same args as remove_silence_from_audio but with base64 I/O.

    Returns:
        Tuple of (processed_b64, mime_type, stats_dict)
    """
    audio_bytes = base64.b64decode(audio_b64)
    processed_bytes, out_mime, stats = remove_silence_from_audio(
        audio_bytes, mime_type,
        silence_thresh_dbfs=silence_thresh_dbfs,
        min_silence_len_ms=min_silence_len_ms,
        padding_ms=padding_ms,
    )
    processed_b64 = base64.b64encode(processed_bytes).decode("utf-8")
    return processed_b64, out_mime, stats

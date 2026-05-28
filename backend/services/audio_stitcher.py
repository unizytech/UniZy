"""
Audio Stitching Service for Live Recording Feature

This service handles combining multiple audio chunks into a single audio file.
Supports WebM, WAV, and other audio formats.

For WebM chunks from MediaRecorder, simple concatenation works because
MediaRecorder creates self-contained chunks that can be joined directly.
"""

import base64
import io
import wave
import subprocess
import logging
import shutil
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
import tempfile
import os

logger = logging.getLogger(__name__)


# ============================================================================
# Audio Stitching Functions
# ============================================================================

def stitch_audio_chunks(
    chunks: List[Dict[str, Any]],
    output_mime_type: str = "audio/webm"
) -> Tuple[str, str]:
    """
    Stitch multiple audio chunks into a single audio file.

    Args:
        chunks: List of chunk dicts with 'audio_data' (base64) and 'mime_type'
        output_mime_type: MIME type for output (default: 'audio/webm')

    Returns:
        Tuple of (base64_audio, mime_type)

    Raises:
        ValueError: If chunks list is empty or mime types are inconsistent
    """
    if not chunks:
        raise ValueError("Cannot stitch empty chunks list")

    # Sort chunks by chunk_index to ensure correct order
    sorted_chunks = sorted(chunks, key=lambda x: x.get("chunk_index", 0))

    # Get mime type from first chunk if not all chunks have same type
    first_mime_type = sorted_chunks[0].get("mime_type", "audio/webm")

    # For raw PCM audio (from Gemini Live sessions)
    # PCM is headerless - simple byte concatenation
    if first_mime_type.startswith("audio/pcm"):
        return _stitch_pcm_chunks(sorted_chunks, first_mime_type)

    # For WebM/MP4/M4A formats, simple concatenation works
    if first_mime_type in ["audio/webm", "audio/mp4", "audio/m4a", "audio/mpeg"]:
        return _stitch_webm_chunks(sorted_chunks, first_mime_type)

    # For WAV files, use proper WAV stitching
    elif first_mime_type == "audio/wav":
        return _stitch_wav_chunks(sorted_chunks)

    # Fallback: try simple concatenation
    else:
        return _stitch_webm_chunks(sorted_chunks, first_mime_type)


def _stitch_webm_chunks(chunks: List[Dict[str, Any]], mime_type: str) -> Tuple[str, str]:
    """
    Stitch WebM/MP4/M4A chunks using simple concatenation.

    MediaRecorder creates self-contained chunks that can be concatenated directly.
    Each chunk has its own header, and concatenating them creates a valid file.

    Args:
        chunks: List of sorted chunk dicts
        mime_type: MIME type of the chunks

    Returns:
        Tuple of (base64_audio, mime_type)

    Raises:
        ValueError: If base64 decoding fails
    """
    combined_bytes = b""

    for i, chunk in enumerate(chunks):
        audio_data_b64 = chunk.get("audio_data", "")

        # 🔧 VALIDATION: Check for common dataURI prefix issues
        if audio_data_b64.startswith("data:"):
            raise ValueError(
                f"Chunk {i} contains dataURI prefix 'data:' - expected pure base64 string. "
                f"Please strip the dataURI prefix (e.g., 'data:audio/wav;base64,') before uploading. "
                f"First 50 chars: {audio_data_b64[:50]}"
            )

        # 🔧 VALIDATION: Check for invalid base64 characters
        invalid_chars = set(audio_data_b64) - set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
        if invalid_chars:
            raise ValueError(
                f"Chunk {i} contains invalid base64 characters: {invalid_chars}. "
                f"This usually means the dataURI prefix wasn't stripped properly. "
                f"First 50 chars: {audio_data_b64[:50]}"
            )

        # Decode base64 to bytes
        try:
            audio_bytes = base64.b64decode(audio_data_b64)
        except Exception as e:
            raise ValueError(
                f"Chunk {i} base64 decoding failed: {str(e)}. "
                f"Base64 length: {len(audio_data_b64)} (valid length must be multiple of 4). "
                f"Length % 4 = {len(audio_data_b64) % 4}. "
                f"First 50 chars: {audio_data_b64[:50]}"
            ) from e

        combined_bytes += audio_bytes

    # Encode back to base64
    combined_b64 = base64.b64encode(combined_bytes).decode("utf-8")

    return combined_b64, mime_type


def _stitch_pcm_chunks(chunks: List[Dict[str, Any]], mime_type: str) -> Tuple[str, str]:
    """
    Stitch raw PCM audio chunks using simple byte concatenation.

    PCM (Pulse Code Modulation) is raw audio without headers, so chunks can
    be directly concatenated. Used for Gemini Live API sessions which stream
    16kHz 16-bit PCM audio.

    Args:
        chunks: List of sorted chunk dicts with base64-encoded PCM data
        mime_type: MIME type (e.g., 'audio/pcm;rate=16000')

    Returns:
        Tuple of (base64_audio, mime_type)

    Raises:
        ValueError: If base64 decoding fails
    """
    combined_bytes = b""

    for i, chunk in enumerate(chunks):
        audio_data_b64 = chunk.get("audio_data", "")

        # Validation: Check for dataURI prefix
        if audio_data_b64.startswith("data:"):
            raise ValueError(
                f"PCM Chunk {i} contains dataURI prefix 'data:' - expected pure base64 string. "
                f"First 50 chars: {audio_data_b64[:50]}"
            )

        # Decode base64 to bytes
        try:
            audio_bytes = base64.b64decode(audio_data_b64)
        except Exception as e:
            raise ValueError(
                f"PCM Chunk {i} base64 decoding failed: {str(e)}. "
                f"Base64 length: {len(audio_data_b64)}. "
                f"First 50 chars: {audio_data_b64[:50]}"
            ) from e

        combined_bytes += audio_bytes

    # Encode back to base64
    combined_b64 = base64.b64encode(combined_bytes).decode("utf-8")

    return combined_b64, mime_type


def _stitch_wav_chunks(chunks: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Stitch WAV chunks using proper WAV file handling.

    Combines WAV chunks by reading their audio data and creating a new WAV file
    with the combined samples.

    Args:
        chunks: List of sorted chunk dicts

    Returns:
        Tuple of (base64_audio, 'audio/wav')

    Raises:
        ValueError: If base64 decoding fails
    """
    # Decode all chunks
    wav_files = []
    for i, chunk in enumerate(chunks):
        audio_data_b64 = chunk.get("audio_data", "")

        # 🔧 VALIDATION: Check for common dataURI prefix issues
        if audio_data_b64.startswith("data:"):
            raise ValueError(
                f"Chunk {i} contains dataURI prefix 'data:' - expected pure base64 string. "
                f"Please strip the dataURI prefix (e.g., 'data:audio/wav;base64,') before uploading. "
                f"First 50 chars: {audio_data_b64[:50]}"
            )

        # 🔧 VALIDATION: Check for invalid base64 characters
        invalid_chars = set(audio_data_b64) - set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
        if invalid_chars:
            raise ValueError(
                f"WAV Chunk {i} contains invalid base64 characters: {invalid_chars}. "
                f"This usually means the dataURI prefix wasn't stripped properly. "
                f"First 50 chars: {audio_data_b64[:50]}"
            )

        # Decode base64 to bytes
        try:
            audio_bytes = base64.b64decode(audio_data_b64)
        except Exception as e:
            raise ValueError(
                f"WAV Chunk {i} base64 decoding failed: {str(e)}. "
                f"Base64 length: {len(audio_data_b64)} (valid length must be multiple of 4). "
                f"Length % 4 = {len(audio_data_b64) % 4}. "
                f"First 50 chars: {audio_data_b64[:50]}"
            ) from e

        wav_files.append(io.BytesIO(audio_bytes))

    # Get parameters from first WAV file
    with wave.open(wav_files[0], "rb") as first_wav:
        params = first_wav.getparams()

    # Create output buffer
    output_buffer = io.BytesIO()

    # Write combined WAV
    with wave.open(output_buffer, "wb") as output_wav:
        output_wav.setparams(params)

        # Write frames from all chunks
        for wav_buffer in wav_files:
            wav_buffer.seek(0)  # Reset to beginning
            with wave.open(wav_buffer, "rb") as wav_file:
                frames = wav_file.readframes(wav_file.getnframes())
                output_wav.writeframes(frames)

    # Get combined audio bytes
    output_buffer.seek(0)
    combined_bytes = output_buffer.read()

    # Encode to base64
    combined_b64 = base64.b64encode(combined_bytes).decode("utf-8")

    return combined_b64, "audio/wav"


# ============================================================================
# FFmpeg-based Stitching (for proper format handling)
# ============================================================================

def is_ffmpeg_available() -> bool:
    """Check if FFmpeg is available on the system."""
    return shutil.which("ffmpeg") is not None


def stitch_audio_chunks_ffmpeg(
    chunks: List[Dict[str, Any]],
    output_mime_type: str = "audio/webm"
) -> Tuple[str, str]:
    """
    Stitch audio chunks using FFmpeg for proper format handling.

    This creates valid output files by properly demuxing and remuxing,
    which produces better quality output than simple byte concatenation.

    FFmpeg concat demuxer is used with stream copy (no re-encoding) for
    maximum speed while still fixing container format issues.

    Args:
        chunks: List of chunk dicts with 'audio_data' (base64) and 'mime_type'
        output_mime_type: MIME type for output (default: 'audio/webm')

    Returns:
        Tuple of (base64_audio, mime_type)

    Raises:
        ValueError: If chunks list is empty
    """
    if not chunks:
        raise ValueError("Cannot stitch empty chunks list")

    # Check FFmpeg availability
    if not is_ffmpeg_available():
        logger.warning("[FFMPEG_STITCH] FFmpeg not available, falling back to simple concatenation")
        return stitch_audio_chunks(chunks, output_mime_type)

    sorted_chunks = sorted(chunks, key=lambda x: x.get("chunk_index", 0))

    # Determine output extension from MIME type
    mime_ext_map = {
        "audio/webm": "webm",
        "audio/mp4": "m4a",
        "audio/m4a": "m4a",
        "audio/wav": "wav",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/ogg": "ogg",
        "audio/flac": "flac",
        "audio/aac": "aac",
    }
    first_mime = sorted_chunks[0].get("mime_type", output_mime_type).split(";")[0]
    output_ext = mime_ext_map.get(first_mime, "webm")

    try:
        # Create temp directory for chunk files
        with tempfile.TemporaryDirectory() as temp_dir:
            chunk_files = []

            # Write each chunk to a temp file
            for i, chunk in enumerate(sorted_chunks):
                audio_bytes = base64.b64decode(chunk["audio_data"])
                chunk_path = os.path.join(temp_dir, f"chunk_{i:04d}.{output_ext}")
                with open(chunk_path, "wb") as f:
                    f.write(audio_bytes)
                chunk_files.append(chunk_path)

            logger.info(f"[FFMPEG_STITCH] Written {len(chunk_files)} chunks to temp files")

            # Create concat file for FFmpeg
            concat_file = os.path.join(temp_dir, "concat.txt")
            with open(concat_file, "w") as f:
                for chunk_path in chunk_files:
                    # FFmpeg concat requires escaped paths
                    escaped_path = chunk_path.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            # Output file
            output_path = os.path.join(temp_dir, f"output.{output_ext}")

            # Run FFmpeg concat
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",  # Stream copy, no re-encoding
                output_path
            ]

            logger.info(f"[FFMPEG_STITCH] Running FFmpeg: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=120  # 2 minute timeout for large files
            )

            if result.returncode != 0:
                stderr = result.stderr.decode() if result.stderr else "Unknown error"
                logger.error(f"[FFMPEG_STITCH] FFmpeg failed (return code {result.returncode}): {stderr}")
                # Fallback to simple concatenation
                logger.warning("[FFMPEG_STITCH] Falling back to simple concatenation")
                return stitch_audio_chunks(chunks, output_mime_type)

            # Read output and encode to base64
            with open(output_path, "rb") as f:
                output_bytes = f.read()

            output_size_mb = len(output_bytes) / (1024 * 1024)
            logger.info(f"[FFMPEG_STITCH] Successfully stitched {len(chunks)} chunks ({output_size_mb:.2f} MB)")

            return base64.b64encode(output_bytes).decode("utf-8"), first_mime

    except subprocess.TimeoutExpired:
        logger.error("[FFMPEG_STITCH] FFmpeg timed out after 120 seconds")
        logger.warning("[FFMPEG_STITCH] Falling back to simple concatenation")
        return stitch_audio_chunks(chunks, output_mime_type)

    except Exception as e:
        logger.error(f"[FFMPEG_STITCH] Error during FFmpeg stitching: {e}")
        logger.warning("[FFMPEG_STITCH] Falling back to simple concatenation")
        return stitch_audio_chunks(chunks, output_mime_type)


# ============================================================================
# File-based Stitching (for large files)
# ============================================================================

def stitch_audio_chunks_to_file(
    chunks: List[Dict[str, Any]],
    output_path: str,
    mime_type: str = "audio/webm"
) -> str:
    """
    Stitch audio chunks and save directly to a file (for large audio).

    Args:
        chunks: List of chunk dicts
        output_path: Path to save the stitched audio file
        mime_type: MIME type of the chunks

    Returns:
        Path to the saved file

    Raises:
        ValueError: If chunks list is empty
    """
    if not chunks:
        raise ValueError("Cannot stitch empty chunks list")

    # Sort chunks by index
    sorted_chunks = sorted(chunks, key=lambda x: x.get("chunk_index", 0))

    # Create output directory if it doesn't exist
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Write chunks to file
    with open(output_path, "wb") as output_file:
        for chunk in sorted_chunks:
            audio_data_b64 = chunk.get("audio_data", "")
            audio_bytes = base64.b64decode(audio_data_b64)
            output_file.write(audio_bytes)

    return output_path


def create_temp_stitched_file(
    chunks: List[Dict[str, Any]],
    suffix: str = ".webm"
) -> str:
    """
    Stitch chunks to a temporary file.

    Args:
        chunks: List of chunk dicts
        suffix: File extension (e.g., '.webm', '.wav')

    Returns:
        Path to temporary file

    Note:
        Caller is responsible for deleting the temp file when done
    """
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_path = temp_file.name
    temp_file.close()

    stitch_audio_chunks_to_file(chunks, temp_path)

    return temp_path


# ============================================================================
# Utility Functions
# ============================================================================

def get_audio_duration_estimate(chunks: List[Dict[str, Any]]) -> float:
    """
    Estimate total audio duration from chunk metadata.

    Args:
        chunks: List of chunk dicts with 'duration_seconds'

    Returns:
        Estimated total duration in seconds
    """
    total_duration = 0.0

    for chunk in chunks:
        duration = chunk.get("duration_seconds")
        if duration is not None:
            total_duration += float(duration)

    return total_duration


def get_total_audio_size(chunks: List[Dict[str, Any]]) -> int:
    """
    Calculate total size of all audio chunks in bytes.

    Args:
        chunks: List of chunk dicts with 'audio_data' (base64)

    Returns:
        Total size in bytes
    """
    total_size = 0

    for chunk in chunks:
        audio_data_b64 = chunk.get("audio_data", "")
        # Base64 encoded size is ~4/3 of actual size
        # But we can get exact size by decoding
        audio_bytes = base64.b64decode(audio_data_b64)
        total_size += len(audio_bytes)

    return total_size


def validate_chunks(chunks: List[Dict[str, Any]], auto_reindex: bool = True) -> Dict[str, Any]:
    """
    Validate chunk data before stitching.

    IMPORTANT: Trust client-assigned chunk_index when valid.
    The client knows the correct audio sequence. Server arrival time (created_at)
    is affected by network conditions and is NOT reliable for audio ordering.

    Reindexing strategy:
    1. If chunk indices are valid (0, 1, 2, ... N-1 with no gaps/duplicates):
       - Trust chunk_index - just sort by it (this is the correct audio order)
    2. If chunk indices are invalid (gaps or duplicates):
       - Fall back to timestamp-based ordering (created_at, then chunk_timestamp)
       - This handles edge cases like retry uploads or client bugs

    Args:
        chunks: List of chunk dicts (modified in-place if reindexing)
        auto_reindex: If True, fix non-sequential indices by sorting by timestamp

    Returns:
        Dict with validation results:
        {
            "valid": bool,
            "errors": List[str],
            "warnings": List[str],
            "chunk_count": int,
            "total_size_bytes": int,
            "estimated_duration_seconds": float,
            "reindexed": bool
        }
    """
    errors = []
    warnings = []
    reindexed = False

    if not chunks:
        errors.append("No chunks provided")
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "chunk_count": 0,
            "total_size_bytes": 0,
            "estimated_duration_seconds": 0.0,
            "reindexed": False,
        }

    # Check if client-assigned indices are valid (no gaps, no duplicates)
    actual_indices = [c.get("chunk_index", -1) for c in chunks]
    expected_indices = list(range(len(chunks)))
    indices_valid = sorted(actual_indices) == expected_indices

    if indices_valid:
        # ✅ CORRECT PATH: Client indices are valid - trust them
        # Just sort by chunk_index (this IS the correct audio order)
        chunks.sort(key=lambda x: x.get("chunk_index", 0))
        logger.debug(
            f"[VALIDATE_CHUNKS] Client indices valid ({actual_indices}), "
            f"sorted by chunk_index (correct audio order)"
        )
    else:
        # ⚠️ FALLBACK PATH: Invalid indices - use timestamp fallback
        if auto_reindex:
            # Sort by timestamp to get temporal order
            # This handles edge cases like duplicate chunk uploads or client bugs
            original_indices = actual_indices.copy()
            chunks.sort(key=lambda x: (
                x.get("created_at", ""),
                x.get("chunk_timestamp", ""),
                x.get("chunk_index", 0)
            ))

            # Reassign sequential indices in-place
            for i, chunk in enumerate(chunks):
                chunk["chunk_index"] = i

            reindexed = True
            warnings.append(
                f"Chunk indices invalid (got {original_indices}, expected {expected_indices}). "
                f"Auto-reindexed {len(chunks)} chunks by timestamp order (fallback)."
            )
            logger.warning(
                f"[VALIDATE_CHUNKS] ⚠️ Invalid chunk indices: {original_indices}. "
                f"Using timestamp-based fallback reindexing."
            )
        else:
            # If not auto-reindexing, treat as error (old behavior)
            sorted_by_index = sorted(chunks, key=lambda x: x.get("chunk_index", -1))
            got_indices = [c.get("chunk_index", -1) for c in sorted_by_index]
            errors.append(f"Missing or duplicate chunk indices. Expected {expected_indices}, got {got_indices}")

    # Check for missing audio data
    for i, chunk in enumerate(chunks):
        if not chunk.get("audio_data"):
            errors.append(f"Chunk {i} is missing audio_data")

    # Check mime type consistency
    mime_types = set(c.get("mime_type", "unknown") for c in chunks)
    if len(mime_types) > 1:
        warnings.append(f"Inconsistent MIME types: {mime_types}")

    # Calculate stats (proceed even with warnings, only skip on actual errors)
    has_data_errors = any("missing audio_data" in e for e in errors)
    total_size = get_total_audio_size(chunks) if not has_data_errors else 0
    estimated_duration = get_audio_duration_estimate(chunks) if not has_data_errors else 0.0

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "chunk_count": len(chunks),
        "total_size_bytes": total_size,
        "estimated_duration_seconds": estimated_duration,
        "reindexed": reindexed,
    }


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Example: Stitch sample chunks
    sample_chunks = [
        {
            "chunk_index": 0,
            "audio_data": "base64encodeddata1...",
            "mime_type": "audio/webm",
            "duration_seconds": 10.0,
        },
        {
            "chunk_index": 1,
            "audio_data": "base64encodeddata2...",
            "mime_type": "audio/webm",
            "duration_seconds": 10.0,
        },
    ]

    # Validate before stitching
    validation = validate_chunks(sample_chunks)
    print(f"Validation: {validation}")

    if validation["valid"]:
        # Stitch chunks
        stitched_audio, mime_type = stitch_audio_chunks(sample_chunks)
        print(f"Stitched {len(sample_chunks)} chunks into {mime_type}")
        print(f"Output size: {len(stitched_audio)} characters (base64)")

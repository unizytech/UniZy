"""
Audio Validation Service

Provides non-blocking audio validation for chunk uploads:
- MIME type validation against Gemini API supported formats
- Audio format detection from magic bytes
- Persistent warning logging to database for debugging

All validation is async and non-blocking - chunks continue to upload
even if validation warnings are generated.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# All Gemini API supported audio MIME types
# Reference: https://ai.google.dev/gemini-api/docs/audio
SUPPORTED_MIME_TYPES = [
    "audio/wav",
    "audio/mp3",
    "audio/mpeg",
    "audio/aiff",
    "audio/aac",
    "audio/ogg",
    "audio/flac",
    "audio/webm",
    "audio/mp4",
    "audio/m4a",
    "audio/pcm",  # Raw PCM for Gemini Live API
    # Vendor-specific variants (browsers/OS may report these)
    "audio/x-m4a",   # macOS/iOS reports M4A as this
    "audio/x-wav",   # Some systems report WAV as this
    "audio/x-aiff",  # Some systems report AIFF as this
    # Video containers that may contain audio-only content
    # (browsers sometimes report these for audio-only recordings)
    "video/webm",    # Normalized to audio/webm in pipeline
    "video/mp4",     # Normalized to audio/mp4 in pipeline
]


def detect_audio_format(header_bytes: bytes) -> Optional[str]:
    """
    Detect audio format from magic bytes (file signature).

    Args:
        header_bytes: First 12+ bytes of the audio file

    Returns:
        Detected format string or None if unrecognized
    """
    if len(header_bytes) < 12:
        return None

    # WebM/MKV (EBML header)
    if header_bytes[:4] == b'\x1a\x45\xdf\xa3':
        return "webm"

    # WAV (RIFF header)
    elif header_bytes[:4] == b'RIFF' and header_bytes[8:12] == b'WAVE':
        return "wav"

    # AIFF
    elif header_bytes[:4] == b'FORM' and header_bytes[8:12] == b'AIFF':
        return "aiff"

    # MP3 (ID3 tag or sync bytes)
    elif header_bytes[:3] == b'ID3' or header_bytes[:2] == b'\xff\xfb' or header_bytes[:2] == b'\xff\xfa':
        return "mp3"

    # MP4/M4A/AAC container (ftyp box)
    elif header_bytes[4:8] == b'ftyp':
        return "mp4"

    # OGG (FLAC in OGG container or Vorbis)
    elif header_bytes[:4] == b'OggS':
        return "ogg"

    # FLAC (native)
    elif header_bytes[:4] == b'fLaC':
        return "flac"

    # AAC raw (ADTS header)
    elif header_bytes[:2] == b'\xff\xf1' or header_bytes[:2] == b'\xff\xf9':
        return "aac"

    return None


def mime_matches_format(mime_type: str, detected_format: str) -> bool:
    """
    Check if declared MIME type matches the detected audio format.

    Args:
        mime_type: Declared MIME type (may include codec info)
        detected_format: Format detected from magic bytes

    Returns:
        True if formats are compatible, False otherwise
    """
    # Strip codec info from MIME type (e.g., "audio/webm;codecs=opus" -> "audio/webm")
    base_mime = mime_type.split(';')[0].strip()

    mime_format_map = {
        "audio/webm": ["webm"],
        "audio/mp4": ["mp4"],
        "audio/m4a": ["mp4"],
        "audio/x-m4a": ["mp4"],  # Vendor-specific variant
        "audio/mpeg": ["mp3"],
        "audio/mp3": ["mp3"],
        "audio/wav": ["wav"],
        "audio/x-wav": ["wav"],  # Vendor-specific variant
        "audio/ogg": ["ogg"],
        "audio/flac": ["flac", "ogg"],  # FLAC can be in OGG container
        "audio/aiff": ["aiff"],
        "audio/x-aiff": ["aiff"],  # Vendor-specific variant
        "audio/aac": ["aac", "mp4"],  # AAC often in MP4 container
    }
    expected_formats = mime_format_map.get(base_mime, [])
    return detected_format in expected_formats


def is_supported_mime_type(mime_type: str) -> bool:
    """
    Check if MIME type is supported by Gemini API.

    Args:
        mime_type: MIME type to check (may include codec info)

    Returns:
        True if supported, False otherwise
    """
    base_mime = mime_type.split(';')[0].strip()
    return base_mime in SUPPORTED_MIME_TYPES


async def log_validation_warning(
    session_id: str,
    chunk_index: int,
    warning_type: str,
    declared_mime_type: str,
    detected_format: Optional[str],
    message: str
) -> None:
    """
    Persist validation warning to database for later analysis.

    This is async and fire-and-forget - failures are logged but don't
    block the upload process.

    Args:
        session_id: Recording session UUID
        chunk_index: Index of the chunk with the warning
        warning_type: Type of warning ('mime_unsupported', 'mime_mismatch', 'format_detection_failed')
        declared_mime_type: MIME type declared by the client
        detected_format: Format detected from magic bytes (or None)
        message: Human-readable warning message
    """
    from services.supabase_service import supabase

    try:
        supabase.table("audio_validation_warnings").insert({
            "session_id": session_id,
            "chunk_index": chunk_index,
            "warning_type": warning_type,
            "declared_mime_type": declared_mime_type,
            "detected_format": detected_format,
            "message": message
        }).execute()
        logger.debug(f"[VALIDATION] Logged warning to DB: {warning_type} for session {session_id}")
    except Exception as e:
        # Log error but don't fail - validation is non-blocking
        logger.error(f"[VALIDATION] Failed to log warning to DB: {e}")


def get_format_description(detected_format: Optional[str]) -> str:
    """Get human-readable description of detected format."""
    format_names = {
        "webm": "WebM (Matroska)",
        "wav": "WAV (RIFF)",
        "aiff": "AIFF",
        "mp3": "MP3",
        "mp4": "MP4/M4A",
        "ogg": "OGG Vorbis/FLAC",
        "flac": "FLAC",
        "aac": "AAC (ADTS)",
    }
    return format_names.get(detected_format, detected_format or "Unknown")


# ============================================================================
# Chunk Size Validation
# ============================================================================

# Expected chunk sizes (based on typical recording patterns)
MIN_CHUNK_SIZE_BYTES = 1000  # 1KB - smaller is likely empty/error
MAX_CHUNK_SIZE_BYTES = 50 * 1024 * 1024  # 50MB - larger is unusual
TYPICAL_CHUNK_SIZE_MIN = 10 * 1024  # 10KB
TYPICAL_CHUNK_SIZE_MAX = 20 * 1024 * 1024  # 20MB


def validate_chunk_size(audio_bytes: bytes, chunk_index: int) -> Optional[dict]:
    """
    Validate chunk size for anomalies.

    Args:
        audio_bytes: Decoded audio bytes
        chunk_index: Index of the chunk

    Returns:
        Dict with warning info if anomaly detected, None otherwise
    """
    size = len(audio_bytes)

    if size < MIN_CHUNK_SIZE_BYTES:
        return {
            "warning_type": "chunk_size_anomaly",
            "message": f"Chunk is very small ({size} bytes) - may be empty or corrupted",
            "details": {"size_bytes": size, "min_expected": MIN_CHUNK_SIZE_BYTES}
        }

    if size > MAX_CHUNK_SIZE_BYTES:
        return {
            "warning_type": "chunk_size_anomaly",
            "message": f"Chunk is unusually large ({size / (1024*1024):.1f}MB) - may cause processing issues",
            "details": {"size_bytes": size, "max_expected": MAX_CHUNK_SIZE_BYTES}
        }

    return None


# ============================================================================
# Empty Audio Detection
# ============================================================================

def detect_empty_audio(audio_bytes: bytes, mime_type: str) -> Optional[dict]:
    """
    Detect if audio chunk contains silence or near-empty data.

    Args:
        audio_bytes: Decoded audio bytes
        mime_type: MIME type of the audio

    Returns:
        Dict with warning info if empty/silent, None otherwise
    """
    if len(audio_bytes) < 100:
        return {
            "warning_type": "empty_audio",
            "message": f"Audio chunk has minimal data ({len(audio_bytes)} bytes)",
            "details": {"size_bytes": len(audio_bytes)}
        }

    # For PCM audio, check if all bytes are near-zero (silence)
    if "pcm" in mime_type.lower():
        # Sample a portion of the audio
        sample_size = min(len(audio_bytes), 10000)
        sample = audio_bytes[:sample_size]

        # Count bytes that are near-zero (silence threshold)
        silent_bytes = sum(1 for b in sample if b < 5 or b > 250)  # Near 0 or 255 for signed/unsigned
        silence_ratio = silent_bytes / sample_size

        if silence_ratio > 0.95:  # 95% silence
            return {
                "warning_type": "empty_audio",
                "message": f"Audio appears to be mostly silence ({silence_ratio*100:.1f}% silent bytes)",
                "details": {"silence_ratio": silence_ratio}
            }

    return None


# ============================================================================
# Codec Detection and Validation
# ============================================================================

# Gemini-supported codecs by container
SUPPORTED_CODECS = {
    "webm": ["opus", "vorbis"],  # WebM typically uses Opus or Vorbis
    "mp4": ["aac", "mp4a", "alac"],  # MP4/M4A uses AAC or ALAC
    "ogg": ["vorbis", "opus", "flac"],  # OGG can contain various codecs
}

# Unsupported codecs that we know cause issues
UNSUPPORTED_CODECS = ["vp8", "vp9", "av1", "h264", "h265", "hevc"]  # Video codecs in audio containers


def detect_codec_from_webm(audio_bytes: bytes) -> Optional[str]:
    """
    Attempt to detect codec from WebM container.

    Args:
        audio_bytes: Full audio bytes

    Returns:
        Detected codec name or None
    """
    try:
        # Look for codec ID in EBML structure
        # Opus: 0x41_4F_70_75_73 ("A_OPUS")
        # Vorbis: 0x41_56_6F_72_62_69_73 ("A_VORBIS")
        if b'A_OPUS' in audio_bytes[:1000] or b'opus' in audio_bytes[:1000].lower():
            return "opus"
        if b'A_VORBIS' in audio_bytes[:1000] or b'vorbis' in audio_bytes[:1000].lower():
            return "vorbis"
        if b'V_VP8' in audio_bytes[:1000] or b'V_VP9' in audio_bytes[:1000]:
            return "vp8/vp9"  # Video codec - problematic
    except:
        pass
    return None


def detect_codec_from_mp4(audio_bytes: bytes) -> Optional[str]:
    """
    Attempt to detect codec from MP4/M4A container.

    Args:
        audio_bytes: Full audio bytes

    Returns:
        Detected codec name or None
    """
    try:
        # Look for codec indicators in MP4 structure
        if b'mp4a' in audio_bytes[:2000]:
            return "aac"
        if b'alac' in audio_bytes[:2000]:
            return "alac"
        if b'avc1' in audio_bytes[:2000] or b'hvc1' in audio_bytes[:2000]:
            return "h264/h265"  # Video codec - problematic
    except:
        pass
    return None


def validate_codec(audio_bytes: bytes, detected_format: Optional[str], mime_type: str) -> Optional[dict]:
    """
    Validate that the codec is supported by Gemini API.

    Args:
        audio_bytes: Full audio bytes
        detected_format: Format detected from magic bytes
        mime_type: Declared MIME type

    Returns:
        Dict with warning info if codec issues, None otherwise
    """
    if not detected_format:
        return None

    codec = None

    # Detect codec based on container
    if detected_format == "webm":
        codec = detect_codec_from_webm(audio_bytes)
    elif detected_format == "mp4":
        codec = detect_codec_from_mp4(audio_bytes)

    if not codec:
        return None

    # Check for known unsupported codecs
    codec_lower = codec.lower()
    for unsupported in UNSUPPORTED_CODECS:
        if unsupported in codec_lower:
            return {
                "warning_type": "codec_unsupported",
                "message": f"Detected video codec '{codec}' in audio container - may cause transcription issues",
                "details": {"codec": codec, "container": detected_format}
            }

    # Check if codec is in supported list for this container
    supported = SUPPORTED_CODECS.get(detected_format, [])
    if supported and codec_lower not in [c.lower() for c in supported]:
        return {
            "warning_type": "codec_unsupported",
            "message": f"Codec '{codec}' may not be optimally supported in {detected_format} container",
            "details": {"codec": codec, "container": detected_format, "supported_codecs": supported}
        }

    return None

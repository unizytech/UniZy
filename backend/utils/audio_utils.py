"""
Audio file utilities for validation and processing.
"""

from fastapi import UploadFile, HTTPException
from io import BytesIO
from config import settings


async def validate_audio_file(file: UploadFile) -> bytes:
    """
    Validate audio file size and format, return file content.

    Args:
        file: Uploaded audio file from FastAPI

    Returns:
        bytes: Audio file content

    Raises:
        HTTPException: If validation fails (file too large or unsupported format)
    """
    # Read file content
    content = await file.read()

    # Check file size
    file_size_mb = len(content) / (1024 * 1024)
    if file_size_mb > settings.max_audio_size_mb:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large ({file_size_mb:.2f}MB). "
                   f"Maximum allowed: {settings.max_audio_size_mb}MB"
        )

    # Detect MIME type from file content type or filename
    mime_type = file.content_type or "audio/unknown"

    # Validate audio format
    if not mime_type.startswith("audio/"):
        # Try to infer from filename if MIME detection failed
        if file.filename:
            filename_lower = file.filename.lower()
            if any(filename_lower.endswith(f".{fmt}") for fmt in settings.allowed_audio_formats):
                # Accept based on file extension
                pass
            else:
                raise HTTPException(
                    status_code=415,
                    detail=f"File does not appear to be an audio file (type: {mime_type})"
                )
        else:
            raise HTTPException(
                status_code=415,
                detail=f"Uploaded file is not an audio file (detected type: {mime_type})"
            )
    else:
        # Extract format from MIME type and validate
        audio_format = mime_type.split("/")[1]

        # Normalize format names
        format_aliases = {
            "mpeg": "mp3",
            "x-m4a": "m4a",
            "x-wav": "wav"
        }
        audio_format = format_aliases.get(audio_format, audio_format)

        # Check if format is allowed
        if audio_format not in settings.allowed_audio_formats:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported audio format: {audio_format}. "
                       f"Allowed formats: {', '.join(settings.allowed_audio_formats)}"
            )

    # Reset file pointer for potential re-reading
    await file.seek(0)

    return content


def get_audio_duration(audio_content: bytes, mime_type: str) -> float:
    """
    Get audio file duration in seconds.

    Note: Audio duration detection is not implemented.
    This function always returns 0.0 as duration is not critical for processing.

    Args:
        audio_content: Raw audio bytes
        mime_type: Audio MIME type (e.g., 'audio/wav', 'audio/mp3')

    Returns:
        float: Always returns 0.0 (duration detection not implemented)
    """
    # Duration detection is not critical for audio processing
    # Returning 0.0 to indicate unknown duration
    return 0.0


def get_mime_type_from_bytes(audio_content: bytes) -> str:
    """
    Detect MIME type from audio bytes using file header signatures.

    Args:
        audio_content: Raw audio bytes

    Returns:
        str: Detected MIME type (e.g., 'audio/wav')
    """
    # Detect MIME type from file headers (magic numbers)
    if audio_content.startswith(b'RIFF'):
        return "audio/wav"
    elif audio_content.startswith(b'\xff\xfb') or audio_content.startswith(b'ID3'):
        return "audio/mp3"
    elif audio_content.startswith(b'ftyp'):
        return "audio/m4a"
    elif audio_content.startswith(b'OggS'):
        return "audio/ogg"
    elif audio_content.startswith(b'\x1a\x45\xdf\xa3'):
        return "audio/webm"
    else:
        return "audio/unknown"

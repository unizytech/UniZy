"""
Temporary Audio Storage Service

Stores decoded audio files in Supabase Storage for 24 hours to enable:
- Debugging audio issues
- Re-processing with different settings
- Audio quality verification

Files are automatically cleaned up by a pg_cron job after 24 hours.
All operations are designed to be non-blocking (async fire-and-forget).
"""

import asyncio
import base64
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from services.supabase_service import supabase

logger = logging.getLogger(__name__)

BUCKET_NAME = "temp-audio"
DEFAULT_EXPIRY_HOURS = 24


def _get_extension_for_mime(mime_type: str) -> str:
    """
    Get file extension for MIME type.

    Args:
        mime_type: Audio MIME type (may include codec info)

    Returns:
        Appropriate file extension
    """
    mime_ext_map = {
        "audio/webm": "webm",
        "audio/wav": "wav",
        "audio/mp3": "mp3",
        "audio/mpeg": "mp3",
        "audio/aiff": "aiff",
        "audio/aac": "aac",
        "audio/ogg": "ogg",
        "audio/flac": "flac",
        "audio/mp4": "m4a",
        "audio/m4a": "m4a",
        "audio/x-m4a": "m4a",
        "audio/pcm": "pcm",
        "video/webm": "webm",  # Browser may report video/webm for audio-only
        "video/mp4": "m4a",    # Browser may report video/mp4 for audio-only
    }
    base_mime = mime_type.split(';')[0].strip()
    return mime_ext_map.get(base_mime, "webm")


def normalize_audio_mime_type(mime_type: str) -> str:
    """
    Normalize MIME type to a standard format accepted by APIs (Gemini, Supabase Storage).

    Some browsers/systems send non-standard MIME types like 'audio/x-m4a'.
    This normalizes them to standard types that APIs accept.

    Args:
        mime_type: Original MIME type (may include codec info)

    Returns:
        Normalized MIME type (preserves codec info if present)
    """
    base_mime = mime_type.split(';')[0].strip()
    codec_info = mime_type[len(base_mime):] if len(mime_type) > len(base_mime) else ""

    # Map non-standard MIME types to standard ones
    # Note: video/webm is sometimes sent by browsers for audio-only WebM recordings
    mime_normalization = {
        "audio/x-m4a": "audio/m4a",
        "audio/x-wav": "audio/wav",
        "audio/x-aiff": "audio/aiff",
        "audio/x-flac": "audio/flac",
        "audio/x-mp3": "audio/mp3",
        "video/webm": "audio/webm",  # Browser sometimes reports video/webm for audio-only
        "video/mp4": "audio/mp4",    # Same issue with MP4 containers
    }

    normalized_base = mime_normalization.get(base_mime, base_mime)
    return normalized_base + codec_info


def store_temp_audio(
    audio_data_b64: str,
    session_id: str,
    mime_type: str = "audio/webm",
    expiry_hours: int = DEFAULT_EXPIRY_HOURS,
    update_session_url: bool = True
) -> Optional[str]:
    """
    Store decoded audio in Supabase Storage for temporary access.

    Args:
        audio_data_b64: Base64 encoded audio data
        session_id: Recording session ID
        mime_type: MIME type of the audio
        expiry_hours: Hours until auto-deletion (default 24)
        update_session_url: If True, also update recording_sessions.full_audio_url

    Returns:
        Storage path if successful, None on failure
    """
    try:
        # Decode audio
        audio_bytes = base64.b64decode(audio_data_b64)
        audio_size_bytes = len(audio_bytes)
        audio_size_mb = audio_size_bytes / (1024 * 1024)

        # Generate unique filename
        file_ext = _get_extension_for_mime(mime_type)
        file_id = str(uuid.uuid4())[:8]
        storage_path = f"{session_id}/{file_id}.{file_ext}"

        # Normalize MIME type for storage bucket compatibility
        normalized_mime = normalize_audio_mime_type(mime_type)
        if normalized_mime != mime_type:
            logger.info(f"[AUDIO_STORAGE] Normalized MIME type: {mime_type} -> {normalized_mime}")

        logger.info(f"[AUDIO_STORAGE] Uploading {audio_size_mb:.2f}MB to {storage_path}")

        # Upload to storage
        result = supabase.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=audio_bytes,
            file_options={"content-type": normalized_mime}
        )

        # Check for errors
        if hasattr(result, 'error') and result.error:
            logger.error(f"[AUDIO_STORAGE] Upload failed: {result.error}")
            return None

        # Track for cleanup
        expires_at = datetime.utcnow() + timedelta(hours=expiry_hours)
        supabase.table("temp_audio_files").insert({
            "storage_path": storage_path,
            "session_id": session_id,
            "expires_at": expires_at.isoformat()
        }).execute()

        # Update recording_sessions with full_audio_url for reprocessing support
        if update_session_url:
            try:
                # Build public URL for the stored audio
                # Format: https://<project>.supabase.co/storage/v1/object/public/<bucket>/<path>
                import os
                supabase_url = os.environ.get("SUPABASE_URL", "")
                if supabase_url:
                    full_audio_url = f"{supabase_url}/storage/v1/object/public/{BUCKET_NAME}/{storage_path}"
                    supabase.table("recording_sessions").update({
                        "full_audio_url": full_audio_url,
                        "full_audio_mime_type": normalized_mime,
                        "full_audio_size_bytes": audio_size_bytes
                    }).eq("id", session_id).execute()
                    logger.info(f"[AUDIO_STORAGE] Updated session {session_id} with full_audio_url")
            except Exception as url_err:
                # Non-fatal - storage succeeded, URL update failed
                logger.warning(f"[AUDIO_STORAGE] Failed to update session full_audio_url: {url_err}")

        logger.info(f"[AUDIO_STORAGE] Stored audio: {storage_path} (expires {expires_at.isoformat()})")
        return storage_path

    except Exception as e:
        logger.error(f"[AUDIO_STORAGE] Failed to store audio: {e}", exc_info=True)
        return None


async def store_temp_audio_async(
    audio_data_b64: str,
    session_id: str,
    mime_type: str = "audio/webm",
    expiry_hours: int = DEFAULT_EXPIRY_HOURS,
    update_session_url: bool = True
) -> Optional[str]:
    """
    Async version - Store decoded audio in Supabase Storage.
    Designed for fire-and-forget usage during extraction pipeline.

    This runs in background and doesn't block the extraction process.
    Also updates recording_sessions.full_audio_url for reprocessing support.

    Args:
        audio_data_b64: Base64 encoded audio data
        session_id: Recording session ID
        mime_type: MIME type of the audio
        expiry_hours: Hours until auto-deletion (default 24)
        update_session_url: If True, also update recording_sessions.full_audio_url

    Returns:
        Storage path if successful, None on failure
    """
    # Run the sync function in a thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: store_temp_audio(audio_data_b64, session_id, mime_type, expiry_hours, update_session_url)
    )


def get_temp_audio_url(storage_path: str, expires_in: int = 3600) -> Optional[str]:
    """
    Get a signed URL for temporary audio access.

    Args:
        storage_path: Path in storage bucket
        expires_in: URL validity in seconds (default 1 hour)

    Returns:
        Signed URL if successful, None on failure
    """
    try:
        result = supabase.storage.from_(BUCKET_NAME).create_signed_url(
            path=storage_path,
            expires_in=expires_in
        )
        return result.get("signedURL")
    except Exception as e:
        logger.error(f"[AUDIO_STORAGE] Failed to get signed URL: {e}")
        return None


def delete_temp_audio(storage_path: str) -> bool:
    """
    Manually delete a temporary audio file.

    Args:
        storage_path: Path in storage bucket

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        supabase.storage.from_(BUCKET_NAME).remove([storage_path])
        supabase.table("temp_audio_files").delete().eq("storage_path", storage_path).execute()
        logger.info(f"[AUDIO_STORAGE] Deleted: {storage_path}")
        return True
    except Exception as e:
        logger.error(f"[AUDIO_STORAGE] Failed to delete: {e}")
        return False


def cleanup_expired_files() -> int:
    """
    Clean up expired temporary audio files.
    This is typically called by a pg_cron job but can be called manually.

    Returns:
        Number of files cleaned up
    """
    try:
        # Get all expired files
        result = supabase.table("temp_audio_files").select(
            "id, storage_path"
        ).lt("expires_at", datetime.utcnow().isoformat()).execute()

        if not result.data:
            logger.debug("[AUDIO_STORAGE] No expired files to clean up")
            return 0

        cleaned = 0
        for record in result.data:
            try:
                # Delete from storage
                supabase.storage.from_(BUCKET_NAME).remove([record["storage_path"]])
                # Delete tracking record
                supabase.table("temp_audio_files").delete().eq("id", record["id"]).execute()
                cleaned += 1
                logger.debug(f"[AUDIO_STORAGE] Cleaned up: {record['storage_path']}")
            except Exception as e:
                logger.warning(f"[AUDIO_STORAGE] Failed to clean up {record['storage_path']}: {e}")

        logger.info(f"[AUDIO_STORAGE] Cleaned up {cleaned} expired files")
        return cleaned

    except Exception as e:
        logger.error(f"[AUDIO_STORAGE] Cleanup failed: {e}")
        return 0


def list_temp_files_for_session(session_id: str) -> list:
    """
    List all temporary audio files for a session.

    Args:
        session_id: Recording session ID

    Returns:
        List of temp file records with storage paths and expiry times
    """
    try:
        result = supabase.table("temp_audio_files").select(
            "id, storage_path, created_at, expires_at"
        ).eq("session_id", session_id).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"[AUDIO_STORAGE] Failed to list files for session: {e}")
        return []


def fetch_audio_from_url(audio_url: str) -> Optional[tuple]:
    """
    Fetch audio content from a storage URL or path.

    Supports both:
    - Full URLs (uses HTTP client)
    - Storage paths (uses Supabase storage client with service key)

    Args:
        audio_url: Full URL or storage path (e.g., "session_id/file.webm")

    Returns:
        Tuple of (base64_audio_data, mime_type) or None on failure
    """
    try:
        # Check if it's a storage path (not a full URL)
        # Storage paths look like: "session_id/filename.webm"
        # Full URLs start with "http"
        if not audio_url.startswith("http"):
            # It's a storage path - use Supabase client
            logger.info(f"[AUDIO_STORAGE] Fetching from storage path: {audio_url}")
            result = supabase.storage.from_(BUCKET_NAME).download(audio_url)
            if result:
                audio_b64 = base64.b64encode(result).decode("utf-8")
                # Determine mime type from extension
                ext = audio_url.split(".")[-1].lower()
                mime_map = {"webm": "audio/webm", "wav": "audio/wav", "mp3": "audio/mp3", "m4a": "audio/m4a"}
                mime_type = mime_map.get(ext, "audio/webm")
                logger.info(f"[AUDIO_STORAGE] Fetched {len(result)} bytes from storage path")
                return (audio_b64, mime_type)
            return None

        # Extract storage path from full URL if it's a Supabase storage URL
        # Format: https://<project>.supabase.co/storage/v1/object/public/<bucket>/<path>
        if "/storage/v1/object/" in audio_url and BUCKET_NAME in audio_url:
            # Extract the path after bucket name
            bucket_marker = f"/{BUCKET_NAME}/"
            if bucket_marker in audio_url:
                storage_path = audio_url.split(bucket_marker)[1]
                logger.info(f"[AUDIO_STORAGE] Extracted storage path from URL: {storage_path}")
                result = supabase.storage.from_(BUCKET_NAME).download(storage_path)
                if result:
                    audio_b64 = base64.b64encode(result).decode("utf-8")
                    ext = storage_path.split(".")[-1].lower()
                    mime_map = {"webm": "audio/webm", "wav": "audio/wav", "mp3": "audio/mp3", "m4a": "audio/m4a"}
                    mime_type = mime_map.get(ext, "audio/webm")
                    logger.info(f"[AUDIO_STORAGE] Fetched {len(result)} bytes from storage")
                    return (audio_b64, mime_type)
                return None

        # Fallback to HTTP client for other URLs
        import httpx
        logger.info(f"[AUDIO_STORAGE] Fetching audio via HTTP: {audio_url}")

        with httpx.Client(timeout=60.0) as client:
            response = client.get(audio_url)
            response.raise_for_status()

            audio_bytes = response.content
            content_type = response.headers.get("content-type", "audio/webm")

            # Encode to base64
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

            logger.info(f"[AUDIO_STORAGE] Fetched {len(audio_bytes)} bytes from URL")
            return (audio_b64, content_type)

    except Exception as e:
        logger.error(f"[AUDIO_STORAGE] Failed to fetch audio from URL/path: {e}")
        return None


async def fetch_audio_from_url_async(audio_url: str) -> Optional[tuple]:
    """
    Async version - Fetch audio content from a storage URL.

    Args:
        audio_url: Full URL to the audio file in storage

    Returns:
        Tuple of (base64_audio_data, mime_type) or None on failure
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: fetch_audio_from_url(audio_url)
    )

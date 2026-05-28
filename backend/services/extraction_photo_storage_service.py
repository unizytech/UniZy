"""
Extraction Photo Storage Service

Stores user-uploaded photos attached to medical_extractions rows in the
Supabase Storage 'extraction-photos' bucket. Photos are permanent; deletion
is explicit (per-photo or via cascade when the parent extraction is deleted).
"""

import logging
from typing import Optional

from services.supabase_service import supabase

logger = logging.getLogger(__name__)

BUCKET_NAME = "extraction-photos"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_MIME = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}

_MIME_EXT_MAP = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
}


class PhotoStorageError(Exception):
    """Base for photo storage errors."""


class PhotoTooLargeError(PhotoStorageError):
    """Raised when an upload exceeds MAX_BYTES."""


class PhotoUnsupportedMimeError(PhotoStorageError):
    """Raised when MIME type is not in ALLOWED_MIME."""


class PhotoStorageQuotaError(PhotoStorageError):
    """Raised when the bucket/project storage is full or quota exceeded."""


class PhotoStorageUploadError(PhotoStorageError):
    """Raised on any other upload failure."""


def _extension_for_mime(mime_type: str) -> str:
    base = (mime_type or "").split(";")[0].strip().lower()
    return _MIME_EXT_MAP.get(base, "bin")


def _is_quota_error(message: str) -> bool:
    """Best-effort detection of storage quota / out-of-space errors."""
    if not message:
        return False
    m = message.lower()
    quota_markers = (
        "quota",
        "exceeded",
        "storage limit",
        "no space",
        "insufficient storage",
        "payload too large",
        "disk full",
        "bucket is full",
    )
    return any(marker in m for marker in quota_markers)


def validate_photo(file_bytes: bytes, mime_type: str) -> None:
    """
    Validate photo bytes + MIME type before upload.

    Raises:
        PhotoTooLargeError: if file exceeds MAX_BYTES
        PhotoUnsupportedMimeError: if MIME type is not allowed
    """
    if len(file_bytes) > MAX_BYTES:
        raise PhotoTooLargeError(
            f"Photo size {len(file_bytes)} bytes exceeds limit of {MAX_BYTES} bytes (10MB)"
        )

    base_mime = (mime_type or "").split(";")[0].strip().lower()
    if base_mime not in ALLOWED_MIME:
        raise PhotoUnsupportedMimeError(
            f"Unsupported image type: {mime_type!r}. Allowed: {sorted(ALLOWED_MIME)}"
        )


def upload_photo(
    extraction_id: str,
    photo_id: str,
    file_bytes: bytes,
    mime_type: str,
) -> str:
    """
    Upload a photo to the extraction-photos bucket.

    Returns:
        storage_path on success.

    Raises:
        PhotoTooLargeError, PhotoUnsupportedMimeError,
        PhotoStorageQuotaError, PhotoStorageUploadError
    """
    validate_photo(file_bytes, mime_type)

    ext = _extension_for_mime(mime_type)
    storage_path = f"{extraction_id}/{photo_id}.{ext}"
    base_mime = mime_type.split(";")[0].strip().lower()

    logger.info(
        f"[PHOTO_STORAGE] Uploading {len(file_bytes)} bytes to {storage_path}"
    )

    try:
        result = supabase.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": base_mime},
        )
    except Exception as e:
        msg = str(e)
        logger.error(f"[PHOTO_STORAGE] Upload exception: {msg}")
        if _is_quota_error(msg):
            raise PhotoStorageQuotaError(
                "Photo storage is full. Please contact support."
            ) from e
        raise PhotoStorageUploadError(
            "Failed to upload photo. Please try again."
        ) from e

    if hasattr(result, "error") and result.error:
        err_msg = str(result.error)
        logger.error(f"[PHOTO_STORAGE] Upload returned error: {err_msg}")
        if _is_quota_error(err_msg):
            raise PhotoStorageQuotaError(
                "Photo storage is full. Please contact support."
            )
        raise PhotoStorageUploadError(
            "Failed to upload photo. Please try again."
        )

    return storage_path


def get_photo_signed_url(storage_path: str, expires_in: int = 3600) -> Optional[str]:
    """Get a signed URL for the photo. Returns None on failure."""
    try:
        result = supabase.storage.from_(BUCKET_NAME).create_signed_url(
            path=storage_path,
            expires_in=expires_in,
        )
        return result.get("signedURL") or result.get("signed_url")
    except Exception as e:
        logger.error(f"[PHOTO_STORAGE] Signed URL failed for {storage_path}: {e}")
        return None


def delete_photo(storage_path: str) -> bool:
    """Delete a photo from storage. Returns True on success."""
    try:
        supabase.storage.from_(BUCKET_NAME).remove([storage_path])
        logger.info(f"[PHOTO_STORAGE] Deleted: {storage_path}")
        return True
    except Exception as e:
        logger.error(f"[PHOTO_STORAGE] Delete failed for {storage_path}: {e}")
        return False

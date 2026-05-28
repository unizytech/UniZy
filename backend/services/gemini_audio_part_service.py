"""Audio-part construction for inference.

Single abstraction for turning audio bytes into a ``types.Part`` suitable
for ``generate_content`` regardless of whether the runtime is on the
consumer API (key auth) or Vertex AI (service-account auth):

- inline (≤ threshold)         → ``Part.from_bytes``
- consumer API + large payload → SDK files upload  → ``Part.from_uri("files/…")``
- Vertex AI + large payload    → GCS object upload → ``Part.from_uri("gs://…")``

The consumer API does not accept GCS URIs and Vertex AI does not expose
the SDK files endpoint, so the routing decision is centralised here.
"""

import asyncio
import logging
import os
import time
import uuid
from io import BytesIO
from typing import Optional, Tuple

from google.genai import types

from .gemini_client_factory import get_gemini_client, is_vertex_ai_mode

logger = logging.getLogger(__name__)


LARGE_FILE_THRESHOLD = 15 * 1024 * 1024


class AudioPartConfigError(RuntimeError):
    """Raised when GCS-mode is required but the bucket is not configured."""


def _gcs_bucket() -> str:
    bucket = os.getenv("GCP_FILES_BUCKET", "").strip()
    if not bucket:
        raise AudioPartConfigError(
            "GCP_FILES_BUCKET is not set. Required when use_vertex_ai=true "
            f"and audio exceeds {LARGE_FILE_THRESHOLD // (1024 * 1024)}MB."
        )
    return bucket


def _gcs_object_key(mime_type: str) -> str:
    ext = (mime_type or "").rsplit("/", 1)[-1].lower() or "bin"
    if ext == "mpeg":
        ext = "mp3"
    return f"inference-audio/{uuid.uuid4()}.{ext}"


async def _upload_to_gcs(audio_bytes: bytes, mime_type: str) -> str:
    from google.cloud import storage

    bucket = _gcs_bucket()
    key = _gcs_object_key(mime_type)

    def _sync_upload() -> str:
        gcs = storage.Client()
        blob = gcs.bucket(bucket).blob(key)
        blob.upload_from_string(audio_bytes, content_type=mime_type)
        return f"gs://{bucket}/{key}"

    return await asyncio.to_thread(_sync_upload)


async def _delete_from_gcs(uri: str) -> None:
    from google.cloud import storage

    if not uri.startswith("gs://"):
        return
    _, _, rest = uri.partition("gs://")
    bucket_name, _, key = rest.partition("/")
    if not bucket_name or not key:
        return

    def _sync_delete() -> None:
        gcs = storage.Client()
        gcs.bucket(bucket_name).blob(key).delete()

    await asyncio.to_thread(_sync_delete)


async def build_audio_part(
    audio_bytes: bytes,
    mime_type: str,
    *,
    threshold_bytes: int = LARGE_FILE_THRESHOLD,
) -> Tuple[types.Part, Optional[str]]:
    """Build a ``types.Part`` for the given audio.

    Returns ``(part, cleanup_handle)`` where ``cleanup_handle`` is either
    ``"files/<name>"`` (consumer API), ``"gs://<bucket>/<key>"`` (Vertex AI),
    or ``None`` (inline). Pass it to ``cleanup_audio_part(...)``, typically
    fire-and-forget, after the inference call.
    """
    size = len(audio_bytes)

    if size <= threshold_bytes:
        return (
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            None,
        )

    if is_vertex_ai_mode():
        upload_start = time.time()
        gs_uri = await _upload_to_gcs(audio_bytes, mime_type)
        logger.info(
            f"[AUDIO_PART] Remote upload complete in "
            f"{time.time() - upload_start:.2f}s "
            f"({size / 1024 / 1024:.1f}MB, scheme=gcs)"
        )
        return (
            types.Part.from_uri(file_uri=gs_uri, mime_type=mime_type),
            gs_uri,
        )

    client = get_gemini_client()
    upload_start = time.time()
    file_io = BytesIO(audio_bytes)
    uploaded = await client.aio.files.upload(
        file=file_io,
        config=types.UploadFileConfig(mime_type=mime_type),
    )
    logger.info(
        f"[AUDIO_PART] Remote upload complete in "
        f"{time.time() - upload_start:.2f}s "
        f"({size / 1024 / 1024:.1f}MB, scheme=files)"
    )
    return (
        types.Part.from_uri(file_uri=uploaded.uri, mime_type=mime_type),
        uploaded.name,
    )


async def cleanup_audio_part(handle: Optional[str]) -> None:
    """Delete the uploaded artifact behind ``handle``. Never raises."""
    if not handle:
        return
    try:
        if handle.startswith("gs://"):
            await _delete_from_gcs(handle)
            logger.debug(f"[AUDIO_PART] Remote object deleted: {handle}")
        else:
            client = get_gemini_client()
            await client.aio.files.delete(name=handle)
            logger.debug(f"[AUDIO_PART] Remote object deleted: {handle}")
    except Exception as e:
        logger.debug(f"[AUDIO_PART] Cleanup failed (non-fatal): {e}")

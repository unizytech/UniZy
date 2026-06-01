"""
Extraction Photos API Router

Endpoints to attach, list, and delete photos linked to a extractions row.

Auth: admin / web_app / EHR (EHR clients are scoped to their school via the
existing EHRExtractionAccessChecker).

Storage: 'extraction-photos' Supabase Storage bucket. See
backend/services/extraction_photo_storage_service.py.
"""

import os
import uuid
import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from services.audit_service import audit_service
from services.supabase_service import supabase
from services.extraction_photo_storage_service import (
    ALLOWED_MIME,
    MAX_BYTES,
    PhotoStorageError,
    PhotoStorageQuotaError,
    PhotoStorageUploadError,
    PhotoTooLargeError,
    PhotoUnsupportedMimeError,
    delete_photo,
    get_photo_signed_url,
    upload_photo,
)

logger = logging.getLogger(__name__)

# Conditional EHR auth (mirrors backend/routers/extractions.py)
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import EHRExtractionAccessChecker, get_current_client

    _extraction_checker = EHRExtractionAccessChecker()

    async def verify_extraction_access(request: Request, extraction_id: str = None):  # type: ignore[misc]
        extraction_uuid = uuid.UUID(extraction_id) if extraction_id else None
        client = get_current_client(request)
        return await _extraction_checker(request, extraction_uuid, client)
else:
    async def verify_extraction_access(request: Request, extraction_id: str = None):  # type: ignore[misc]
        return None


router = APIRouter(
    prefix="/api/v1/extractions",
    tags=["Extraction Photos"],
)


# ----------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------

class ExtractionPhotoResponse(BaseModel):
    id: str
    extraction_id: str
    label: str
    original_filename: Optional[str]
    mime_type: str
    file_size_bytes: int
    signed_url: Optional[str]
    created_at: str


class ExtractionPhotoListResponse(BaseModel):
    photos: List[ExtractionPhotoResponse]
    total: int


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _get_extraction_or_404(extraction_id: str) -> dict:
    try:
        result = supabase.table("extractions").select(
            "id, student_id, counsellor_id"
        ).eq("id", extraction_id).limit(1).execute()
    except Exception as e:
        logger.error(f"[PHOTOS] Failed to load extraction {extraction_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify extraction")

    if not result.data:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return result.data[0]


def _row_to_response(row: dict) -> ExtractionPhotoResponse:
    signed = get_photo_signed_url(row["storage_path"])
    return ExtractionPhotoResponse(
        id=row["id"],
        extraction_id=row["extraction_id"],
        label=row["label"],
        original_filename=row.get("original_filename"),
        mime_type=row["mime_type"],
        file_size_bytes=row["file_size_bytes"],
        signed_url=signed,
        created_at=row["created_at"],
    )


def _client_info(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Return (client_id, client_type) from request.state.client if present."""
    client = getattr(request.state, "client", None)
    if not client:
        return None, None
    client_id = getattr(client, "client_id", None) or getattr(client, "id", None)
    client_type = getattr(client, "client_type", None)
    return (str(client_id) if client_id else None, client_type)


def _audit(
    request: Request,
    *,
    action: str,
    resource_id: str,
    student_id: Optional[str],
    status: int,
) -> None:
    """Fire-and-forget PHI audit log."""
    client_ctx = getattr(request.state, "client", None)
    if not client_ctx:
        return
    try:
        asyncio.create_task(
            audit_service.log_phi_access(
                client_context=client_ctx,
                request=request,
                response_status=status,
                response_time_ms=0,
                resource_type="extraction_photo",
                resource_id=resource_id,
                action=action,
                student_id=student_id,
            )
        )
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------

@router.post(
    "/{extraction_id}/photos",
    response_model=ExtractionPhotoResponse,
    status_code=201,
)
async def upload_extraction_photo(
    request: Request,
    extraction_id: str,
    file: UploadFile = File(...),
    label: str = Form(...),
    _auth=Depends(verify_extraction_access),
):
    """Attach a photo to an extraction."""
    try:
        uuid.UUID(extraction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction_id")

    label = (label or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="Label is required")
    if len(label) > 200:
        raise HTTPException(status_code=400, detail="Label must be 200 characters or fewer")

    extraction = _get_extraction_or_404(extraction_id)

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    mime_type = (file.content_type or "").split(";")[0].strip().lower()
    if mime_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type. Allowed: {', '.join(sorted(ALLOWED_MIME))}",
        )
    if len(file_bytes) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image is larger than the 10 MB limit. Please upload a smaller file.",
        )

    photo_id = str(uuid.uuid4())
    try:
        storage_path = upload_photo(
            extraction_id=extraction_id,
            photo_id=photo_id,
            file_bytes=file_bytes,
            mime_type=mime_type,
        )
    except PhotoTooLargeError:
        raise HTTPException(
            status_code=413,
            detail="Image is larger than the 10 MB limit. Please upload a smaller file.",
        )
    except PhotoUnsupportedMimeError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type. Allowed: {', '.join(sorted(ALLOWED_MIME))}",
        )
    except PhotoStorageQuotaError:
        # 507 Insufficient Storage — clean message, no provider names
        raise HTTPException(
            status_code=507,
            detail="Photo storage is full. Please try again later or contact support.",
        )
    except (PhotoStorageUploadError, PhotoStorageError):
        raise HTTPException(
            status_code=502,
            detail="Failed to upload photo. Please try again.",
        )

    client_id, client_type = _client_info(request)

    insert_payload = {
        "id": photo_id,
        "extraction_id": extraction_id,
        "label": label,
        "original_filename": file.filename,
        "storage_path": storage_path,
        "mime_type": mime_type,
        "file_size_bytes": len(file_bytes),
        "uploaded_by": client_id,
        "uploaded_by_type": client_type,
    }

    try:
        result = supabase.table("extraction_photos").insert(insert_payload).execute()
    except Exception as e:
        # Roll back the storage object so we don't leak orphans
        logger.error(f"[PHOTOS] DB insert failed; deleting storage object: {e}")
        delete_photo(storage_path)
        raise HTTPException(status_code=500, detail="Failed to record photo metadata")

    if not result.data:
        delete_photo(storage_path)
        raise HTTPException(status_code=500, detail="Failed to record photo metadata")

    row = result.data[0]
    _audit(
        request,
        action="create",
        resource_id=photo_id,
        student_id=extraction.get("student_id"),
        status=201,
    )
    return _row_to_response(row)


@router.get(
    "/{extraction_id}/photos",
    response_model=ExtractionPhotoListResponse,
)
async def list_extraction_photos(
    request: Request,
    extraction_id: str,
    _auth=Depends(verify_extraction_access),
):
    """List photos attached to an extraction."""
    try:
        uuid.UUID(extraction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction_id")

    extraction = _get_extraction_or_404(extraction_id)

    try:
        result = supabase.table("extraction_photos").select(
            "id, extraction_id, label, original_filename, storage_path, mime_type, file_size_bytes, created_at"
        ).eq("extraction_id", extraction_id).order("created_at", desc=False).execute()
    except Exception as e:
        logger.error(f"[PHOTOS] Failed to list photos for {extraction_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list photos")

    rows = result.data or []
    photos = [_row_to_response(r) for r in rows]

    _audit(
        request,
        action="read",
        resource_id=extraction_id,
        student_id=extraction.get("student_id"),
        status=200,
    )
    return ExtractionPhotoListResponse(photos=photos, total=len(photos))


@router.delete(
    "/{extraction_id}/photos/{photo_id}",
    status_code=204,
)
async def delete_extraction_photo(
    request: Request,
    extraction_id: str,
    photo_id: str,
    _auth=Depends(verify_extraction_access),
):
    """Delete a photo from an extraction (DB row + storage object)."""
    try:
        uuid.UUID(extraction_id)
        uuid.UUID(photo_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid id")

    extraction = _get_extraction_or_404(extraction_id)

    try:
        existing = supabase.table("extraction_photos").select(
            "id, extraction_id, storage_path"
        ).eq("id", photo_id).limit(1).execute()
    except Exception as e:
        logger.error(f"[PHOTOS] Lookup failed for photo {photo_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load photo")

    if not existing.data:
        raise HTTPException(status_code=404, detail="Photo not found")

    photo_row = existing.data[0]
    if photo_row["extraction_id"] != extraction_id:
        raise HTTPException(status_code=404, detail="Photo not found")

    delete_photo(photo_row["storage_path"])  # storage error logged but not fatal

    try:
        supabase.table("extraction_photos").delete().eq("id", photo_id).execute()
    except Exception as e:
        logger.error(f"[PHOTOS] Failed to delete photo row {photo_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete photo")

    _audit(
        request,
        action="delete",
        resource_id=photo_id,
        student_id=extraction.get("student_id"),
        status=204,
    )
    return None

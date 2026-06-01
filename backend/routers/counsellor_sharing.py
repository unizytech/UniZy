"""
Counsellor Sharing Router

CRUD endpoints for managing counsellor-to-counsellor student sharing links.
Uses the counsellor_counsellor_students table with bidirectional storage.

Auth: Admin only (all endpoints).
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, Path, Query
from pydantic import BaseModel, Field
from models.auth_models import ClientContext
from dependencies.auth import require_admin
from services.supabase_service import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/counsellor-sharing", tags=["Counsellor Sharing"])


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateSharingLinkRequest(BaseModel):
    counsellor_id: str = Field(..., description="First counsellor UUID")
    linked_counsellor_id: str = Field(..., description="Second counsellor UUID")
    student_ids: Optional[List[str]] = Field(
        None,
        description="List of student UUIDs to share. NULL = share all students."
    )


class UpdateSharingLinkRequest(BaseModel):
    student_ids: Optional[List[str]] = Field(
        None,
        description="New student IDs list. NULL = share all students. Empty array = no specific students (use NULL for all)."
    )


class AddStudentsRequest(BaseModel):
    student_ids: List[str] = Field(..., description="Student UUIDs to add to existing sharing link")


class RemoveStudentsRequest(BaseModel):
    student_ids: List[str] = Field(..., description="Student UUIDs to remove from existing sharing link")


# ============================================================================
# Endpoints
# ============================================================================

@router.get("")
async def list_sharing_links(
    school_id: Optional[str] = Query(None, description="Filter by school ID"),
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    List all active counsellor sharing links, optionally filtered by school.

    Returns grouped pairs (A↔B shown once, not twice).
    """
    try:
        query = supabase.table("counsellor_counsellor_students")\
            .select("id, counsellor_id, linked_counsellor_id, student_ids, is_active, created_at, updated_at")\
            .eq("is_active", True)\
            .order("created_at", desc=True)

        result = query.execute()
        all_links = result.data or []

        # Group bidirectional pairs: only show each pair once
        seen_pairs = set()
        grouped_links = []

        for link in all_links:
            pair_key = tuple(sorted([link["counsellor_id"], link["linked_counsellor_id"]]))
            if pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                grouped_links.append(link)

        # If school_id filter, fetch counsellor school_ids and filter
        if school_id:
            counsellor_ids = set()
            for link in grouped_links:
                counsellor_ids.add(link["counsellor_id"])
                counsellor_ids.add(link["linked_counsellor_id"])

            if counsellor_ids:
                counsellors_result = supabase.table("counsellors")\
                    .select("id, school_id")\
                    .in_("id", list(counsellor_ids))\
                    .execute()
                counsellor_schools = {d["id"]: d.get("school_id") for d in (counsellors_result.data or [])}

                # Keep only links where at least one counsellor is in the school
                grouped_links = [
                    link for link in grouped_links
                    if counsellor_schools.get(link["counsellor_id"]) == school_id
                    or counsellor_schools.get(link["linked_counsellor_id"]) == school_id
                ]

        # Enrich with counsellor names
        counsellor_ids = set()
        for link in grouped_links:
            counsellor_ids.add(link["counsellor_id"])
            counsellor_ids.add(link["linked_counsellor_id"])

        counsellor_names = {}
        if counsellor_ids:
            counsellors_result = supabase.table("counsellors")\
                .select("id, full_name, email, school_id")\
                .in_("id", list(counsellor_ids))\
                .execute()
            for doc in (counsellors_result.data or []):
                counsellor_names[doc["id"]] = {
                    "full_name": doc.get("full_name", doc.get("email", "Unknown")),
                    "email": doc.get("email"),
                    "school_id": doc.get("school_id"),
                }

        # Build response
        enriched_links = []
        for link in grouped_links:
            doc_a = counsellor_names.get(link["counsellor_id"], {})
            doc_b = counsellor_names.get(link["linked_counsellor_id"], {})
            student_ids = link.get("student_ids")

            enriched_links.append({
                "id": link["id"],
                "counsellor_id": link["counsellor_id"],
                "counsellor_name": doc_a.get("full_name", "Unknown"),
                "counsellor_email": doc_a.get("email"),
                "linked_counsellor_id": link["linked_counsellor_id"],
                "linked_counsellor_name": doc_b.get("full_name", "Unknown"),
                "linked_counsellor_email": doc_b.get("email"),
                "sharing_mode": "all_patients" if student_ids is None else "specific_patients",
                "student_ids": student_ids,
                "student_count": len(student_ids) if student_ids else None,
                "is_active": link["is_active"],
                "created_at": link["created_at"],
                "updated_at": link.get("updated_at"),
            })

        return {
            "success": True,
            "sharing_links": enriched_links,
            "count": len(enriched_links),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DOCTOR_SHARING] Error listing sharing links: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list sharing links: {str(e)}")


@router.post("")
async def create_sharing_link(
    request: CreateSharingLinkRequest,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Create a bidirectional counsellor sharing link.

    Inserts two rows (A→B and B→A) for query simplicity.
    """
    if request.counsellor_id == request.linked_counsellor_id:
        raise HTTPException(status_code=400, detail="Cannot link a counsellor to themselves")

    try:
        # Check if link already exists (either direction)
        existing = supabase.table("counsellor_counsellor_students")\
            .select("id, is_active")\
            .eq("counsellor_id", request.counsellor_id)\
            .eq("linked_counsellor_id", request.linked_counsellor_id)\
            .execute()

        if existing.data:
            row = existing.data[0]
            if row["is_active"]:
                raise HTTPException(status_code=409, detail="Sharing link already exists between these counsellors")
            else:
                # Reactivate existing link (both directions)
                _reactivate_link(request.counsellor_id, request.linked_counsellor_id, request.student_ids)
                return {
                    "success": True,
                    "message": "Sharing link reactivated",
                    "link_id": row["id"],
                }

        # Insert both directions
        row_a = {
            "counsellor_id": request.counsellor_id,
            "linked_counsellor_id": request.linked_counsellor_id,
            "student_ids": request.student_ids,
        }
        row_b = {
            "counsellor_id": request.linked_counsellor_id,
            "linked_counsellor_id": request.counsellor_id,
            "student_ids": request.student_ids,
        }

        result_a = supabase.table("counsellor_counsellor_students").insert(row_a).execute()
        supabase.table("counsellor_counsellor_students").insert(row_b).execute()

        if not result_a.data:
            raise HTTPException(status_code=500, detail="Failed to create sharing link")

        link_id = result_a.data[0]["id"]

        mode = "all_patients" if request.student_ids is None else f"{len(request.student_ids)} specific student(s)"
        logger.info(
            f"[DOCTOR_SHARING] Created sharing link: {request.counsellor_id[:8]}... ↔ {request.linked_counsellor_id[:8]}... ({mode})"
        )

        return {
            "success": True,
            "message": f"Sharing link created ({mode})",
            "link_id": link_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DOCTOR_SHARING] Error creating sharing link: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create sharing link: {str(e)}")


@router.put("/{counsellor_id}/{linked_counsellor_id}")
async def update_sharing_link(
    counsellor_id: str = Path(..., description="First counsellor UUID"),
    linked_counsellor_id: str = Path(..., description="Second counsellor UUID"),
    request: UpdateSharingLinkRequest = ...,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Update sharing link between two counsellors (both directions updated).

    Set student_ids to null for "share all", or provide array for selective sharing.
    """
    try:
        update_data = {
            "student_ids": request.student_ids,
            "updated_at": "now()",
        }

        # Update both directions
        result = supabase.table("counsellor_counsellor_students")\
            .update(update_data)\
            .eq("counsellor_id", counsellor_id)\
            .eq("linked_counsellor_id", linked_counsellor_id)\
            .execute()

        supabase.table("counsellor_counsellor_students")\
            .update(update_data)\
            .eq("counsellor_id", linked_counsellor_id)\
            .eq("linked_counsellor_id", counsellor_id)\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Sharing link not found")

        mode = "all_patients" if request.student_ids is None else f"{len(request.student_ids)} specific student(s)"
        logger.info(f"[DOCTOR_SHARING] Updated sharing link: {counsellor_id[:8]}... ↔ {linked_counsellor_id[:8]}... → {mode}")

        return {
            "success": True,
            "message": f"Sharing link updated ({mode})",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DOCTOR_SHARING] Error updating sharing link: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update sharing link: {str(e)}")


@router.post("/{counsellor_id}/{linked_counsellor_id}/students")
async def add_students_to_link(
    counsellor_id: str = Path(...),
    linked_counsellor_id: str = Path(...),
    request: AddStudentsRequest = ...,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Add students to an existing selective sharing link.

    If the link is currently "share all" (student_ids=NULL), this converts it
    to selective sharing with only these students.
    """
    try:
        # Fetch current state
        existing = supabase.table("counsellor_counsellor_students")\
            .select("id, student_ids")\
            .eq("counsellor_id", counsellor_id)\
            .eq("linked_counsellor_id", linked_counsellor_id)\
            .eq("is_active", True)\
            .execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Sharing link not found")

        current_ids = existing.data[0].get("student_ids") or []
        # Merge: add new IDs without duplicates
        merged = list(set(current_ids + request.student_ids))

        update_data = {"student_ids": merged, "updated_at": "now()"}

        supabase.table("counsellor_counsellor_students")\
            .update(update_data)\
            .eq("counsellor_id", counsellor_id)\
            .eq("linked_counsellor_id", linked_counsellor_id)\
            .execute()

        supabase.table("counsellor_counsellor_students")\
            .update(update_data)\
            .eq("counsellor_id", linked_counsellor_id)\
            .eq("linked_counsellor_id", counsellor_id)\
            .execute()

        return {
            "success": True,
            "message": f"Added {len(request.student_ids)} student(s), total now {len(merged)}",
            "student_ids": merged,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DOCTOR_SHARING] Error adding students: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to add students: {str(e)}")


@router.post("/{counsellor_id}/{linked_counsellor_id}/remove-students")
async def remove_students_from_link(
    counsellor_id: str = Path(...),
    linked_counsellor_id: str = Path(...),
    request: RemoveStudentsRequest = ...,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Remove students from an existing selective sharing link.

    If all students are removed, the link remains active but with an empty array.
    """
    try:
        existing = supabase.table("counsellor_counsellor_students")\
            .select("id, student_ids")\
            .eq("counsellor_id", counsellor_id)\
            .eq("linked_counsellor_id", linked_counsellor_id)\
            .eq("is_active", True)\
            .execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Sharing link not found")

        current_ids = existing.data[0].get("student_ids") or []
        remaining = [pid for pid in current_ids if pid not in request.student_ids]

        update_data = {"student_ids": remaining if remaining else [], "updated_at": "now()"}

        supabase.table("counsellor_counsellor_students")\
            .update(update_data)\
            .eq("counsellor_id", counsellor_id)\
            .eq("linked_counsellor_id", linked_counsellor_id)\
            .execute()

        supabase.table("counsellor_counsellor_students")\
            .update(update_data)\
            .eq("counsellor_id", linked_counsellor_id)\
            .eq("linked_counsellor_id", counsellor_id)\
            .execute()

        return {
            "success": True,
            "message": f"Removed {len(request.student_ids)} student(s), {len(remaining)} remaining",
            "student_ids": remaining,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DOCTOR_SHARING] Error removing students: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to remove students: {str(e)}")


@router.delete("/{counsellor_id}/{linked_counsellor_id}")
async def deactivate_sharing_link(
    counsellor_id: str = Path(...),
    linked_counsellor_id: str = Path(...),
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Soft-delete (deactivate) a sharing link. Deactivates both directions.
    """
    try:
        deactivate_data = {"is_active": False, "updated_at": "now()"}

        result = supabase.table("counsellor_counsellor_students")\
            .update(deactivate_data)\
            .eq("counsellor_id", counsellor_id)\
            .eq("linked_counsellor_id", linked_counsellor_id)\
            .execute()

        supabase.table("counsellor_counsellor_students")\
            .update(deactivate_data)\
            .eq("counsellor_id", linked_counsellor_id)\
            .eq("linked_counsellor_id", counsellor_id)\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Sharing link not found")

        logger.info(f"[DOCTOR_SHARING] Deactivated sharing link: {counsellor_id[:8]}... ↔ {linked_counsellor_id[:8]}...")

        return {
            "success": True,
            "message": "Sharing link deactivated",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DOCTOR_SHARING] Error deactivating sharing link: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to deactivate sharing link: {str(e)}")


# ============================================================================
# Helpers
# ============================================================================

def _reactivate_link(counsellor_id: str, linked_counsellor_id: str, student_ids: Optional[List[str]]) -> None:
    """Reactivate a previously deactivated sharing link (both directions)."""
    reactivate_data = {
        "is_active": True,
        "student_ids": student_ids,
        "updated_at": "now()",
    }

    supabase.table("counsellor_counsellor_students")\
        .update(reactivate_data)\
        .eq("counsellor_id", counsellor_id)\
        .eq("linked_counsellor_id", linked_counsellor_id)\
        .execute()

    supabase.table("counsellor_counsellor_students")\
        .update(reactivate_data)\
        .eq("counsellor_id", linked_counsellor_id)\
        .eq("linked_counsellor_id", counsellor_id)\
        .execute()

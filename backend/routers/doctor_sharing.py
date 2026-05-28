"""
Doctor Sharing Router

CRUD endpoints for managing doctor-to-doctor patient sharing links.
Uses the doctor_doctor_patients table with bidirectional storage.

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

router = APIRouter(prefix="/api/v1/doctor-sharing", tags=["Doctor Sharing"])


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateSharingLinkRequest(BaseModel):
    doctor_id: str = Field(..., description="First doctor UUID")
    linked_doctor_id: str = Field(..., description="Second doctor UUID")
    patient_ids: Optional[List[str]] = Field(
        None,
        description="List of patient UUIDs to share. NULL = share all patients."
    )


class UpdateSharingLinkRequest(BaseModel):
    patient_ids: Optional[List[str]] = Field(
        None,
        description="New patient IDs list. NULL = share all patients. Empty array = no specific patients (use NULL for all)."
    )


class AddPatientsRequest(BaseModel):
    patient_ids: List[str] = Field(..., description="Patient UUIDs to add to existing sharing link")


class RemovePatientsRequest(BaseModel):
    patient_ids: List[str] = Field(..., description="Patient UUIDs to remove from existing sharing link")


# ============================================================================
# Endpoints
# ============================================================================

@router.get("")
async def list_sharing_links(
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    List all active doctor sharing links, optionally filtered by hospital.

    Returns grouped pairs (A↔B shown once, not twice).
    """
    try:
        query = supabase.table("doctor_doctor_patients")\
            .select("id, doctor_id, linked_doctor_id, patient_ids, is_active, created_at, updated_at")\
            .eq("is_active", True)\
            .order("created_at", desc=True)

        result = query.execute()
        all_links = result.data or []

        # Group bidirectional pairs: only show each pair once
        seen_pairs = set()
        grouped_links = []

        for link in all_links:
            pair_key = tuple(sorted([link["doctor_id"], link["linked_doctor_id"]]))
            if pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                grouped_links.append(link)

        # If hospital_id filter, fetch doctor hospital_ids and filter
        if hospital_id:
            doctor_ids = set()
            for link in grouped_links:
                doctor_ids.add(link["doctor_id"])
                doctor_ids.add(link["linked_doctor_id"])

            if doctor_ids:
                doctors_result = supabase.table("doctors")\
                    .select("id, hospital_id")\
                    .in_("id", list(doctor_ids))\
                    .execute()
                doctor_hospitals = {d["id"]: d.get("hospital_id") for d in (doctors_result.data or [])}

                # Keep only links where at least one doctor is in the hospital
                grouped_links = [
                    link for link in grouped_links
                    if doctor_hospitals.get(link["doctor_id"]) == hospital_id
                    or doctor_hospitals.get(link["linked_doctor_id"]) == hospital_id
                ]

        # Enrich with doctor names
        doctor_ids = set()
        for link in grouped_links:
            doctor_ids.add(link["doctor_id"])
            doctor_ids.add(link["linked_doctor_id"])

        doctor_names = {}
        if doctor_ids:
            doctors_result = supabase.table("doctors")\
                .select("id, full_name, email, hospital_id")\
                .in_("id", list(doctor_ids))\
                .execute()
            for doc in (doctors_result.data or []):
                doctor_names[doc["id"]] = {
                    "full_name": doc.get("full_name", doc.get("email", "Unknown")),
                    "email": doc.get("email"),
                    "hospital_id": doc.get("hospital_id"),
                }

        # Build response
        enriched_links = []
        for link in grouped_links:
            doc_a = doctor_names.get(link["doctor_id"], {})
            doc_b = doctor_names.get(link["linked_doctor_id"], {})
            patient_ids = link.get("patient_ids")

            enriched_links.append({
                "id": link["id"],
                "doctor_id": link["doctor_id"],
                "doctor_name": doc_a.get("full_name", "Unknown"),
                "doctor_email": doc_a.get("email"),
                "linked_doctor_id": link["linked_doctor_id"],
                "linked_doctor_name": doc_b.get("full_name", "Unknown"),
                "linked_doctor_email": doc_b.get("email"),
                "sharing_mode": "all_patients" if patient_ids is None else "specific_patients",
                "patient_ids": patient_ids,
                "patient_count": len(patient_ids) if patient_ids else None,
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
    Create a bidirectional doctor sharing link.

    Inserts two rows (A→B and B→A) for query simplicity.
    """
    if request.doctor_id == request.linked_doctor_id:
        raise HTTPException(status_code=400, detail="Cannot link a doctor to themselves")

    try:
        # Check if link already exists (either direction)
        existing = supabase.table("doctor_doctor_patients")\
            .select("id, is_active")\
            .eq("doctor_id", request.doctor_id)\
            .eq("linked_doctor_id", request.linked_doctor_id)\
            .execute()

        if existing.data:
            row = existing.data[0]
            if row["is_active"]:
                raise HTTPException(status_code=409, detail="Sharing link already exists between these doctors")
            else:
                # Reactivate existing link (both directions)
                _reactivate_link(request.doctor_id, request.linked_doctor_id, request.patient_ids)
                return {
                    "success": True,
                    "message": "Sharing link reactivated",
                    "link_id": row["id"],
                }

        # Insert both directions
        row_a = {
            "doctor_id": request.doctor_id,
            "linked_doctor_id": request.linked_doctor_id,
            "patient_ids": request.patient_ids,
        }
        row_b = {
            "doctor_id": request.linked_doctor_id,
            "linked_doctor_id": request.doctor_id,
            "patient_ids": request.patient_ids,
        }

        result_a = supabase.table("doctor_doctor_patients").insert(row_a).execute()
        supabase.table("doctor_doctor_patients").insert(row_b).execute()

        if not result_a.data:
            raise HTTPException(status_code=500, detail="Failed to create sharing link")

        link_id = result_a.data[0]["id"]

        mode = "all_patients" if request.patient_ids is None else f"{len(request.patient_ids)} specific patient(s)"
        logger.info(
            f"[DOCTOR_SHARING] Created sharing link: {request.doctor_id[:8]}... ↔ {request.linked_doctor_id[:8]}... ({mode})"
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


@router.put("/{doctor_id}/{linked_doctor_id}")
async def update_sharing_link(
    doctor_id: str = Path(..., description="First doctor UUID"),
    linked_doctor_id: str = Path(..., description="Second doctor UUID"),
    request: UpdateSharingLinkRequest = ...,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Update sharing link between two doctors (both directions updated).

    Set patient_ids to null for "share all", or provide array for selective sharing.
    """
    try:
        update_data = {
            "patient_ids": request.patient_ids,
            "updated_at": "now()",
        }

        # Update both directions
        result = supabase.table("doctor_doctor_patients")\
            .update(update_data)\
            .eq("doctor_id", doctor_id)\
            .eq("linked_doctor_id", linked_doctor_id)\
            .execute()

        supabase.table("doctor_doctor_patients")\
            .update(update_data)\
            .eq("doctor_id", linked_doctor_id)\
            .eq("linked_doctor_id", doctor_id)\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Sharing link not found")

        mode = "all_patients" if request.patient_ids is None else f"{len(request.patient_ids)} specific patient(s)"
        logger.info(f"[DOCTOR_SHARING] Updated sharing link: {doctor_id[:8]}... ↔ {linked_doctor_id[:8]}... → {mode}")

        return {
            "success": True,
            "message": f"Sharing link updated ({mode})",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DOCTOR_SHARING] Error updating sharing link: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update sharing link: {str(e)}")


@router.post("/{doctor_id}/{linked_doctor_id}/patients")
async def add_patients_to_link(
    doctor_id: str = Path(...),
    linked_doctor_id: str = Path(...),
    request: AddPatientsRequest = ...,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Add patients to an existing selective sharing link.

    If the link is currently "share all" (patient_ids=NULL), this converts it
    to selective sharing with only these patients.
    """
    try:
        # Fetch current state
        existing = supabase.table("doctor_doctor_patients")\
            .select("id, patient_ids")\
            .eq("doctor_id", doctor_id)\
            .eq("linked_doctor_id", linked_doctor_id)\
            .eq("is_active", True)\
            .execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Sharing link not found")

        current_ids = existing.data[0].get("patient_ids") or []
        # Merge: add new IDs without duplicates
        merged = list(set(current_ids + request.patient_ids))

        update_data = {"patient_ids": merged, "updated_at": "now()"}

        supabase.table("doctor_doctor_patients")\
            .update(update_data)\
            .eq("doctor_id", doctor_id)\
            .eq("linked_doctor_id", linked_doctor_id)\
            .execute()

        supabase.table("doctor_doctor_patients")\
            .update(update_data)\
            .eq("doctor_id", linked_doctor_id)\
            .eq("linked_doctor_id", doctor_id)\
            .execute()

        return {
            "success": True,
            "message": f"Added {len(request.patient_ids)} patient(s), total now {len(merged)}",
            "patient_ids": merged,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DOCTOR_SHARING] Error adding patients: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to add patients: {str(e)}")


@router.post("/{doctor_id}/{linked_doctor_id}/remove-patients")
async def remove_patients_from_link(
    doctor_id: str = Path(...),
    linked_doctor_id: str = Path(...),
    request: RemovePatientsRequest = ...,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Remove patients from an existing selective sharing link.

    If all patients are removed, the link remains active but with an empty array.
    """
    try:
        existing = supabase.table("doctor_doctor_patients")\
            .select("id, patient_ids")\
            .eq("doctor_id", doctor_id)\
            .eq("linked_doctor_id", linked_doctor_id)\
            .eq("is_active", True)\
            .execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Sharing link not found")

        current_ids = existing.data[0].get("patient_ids") or []
        remaining = [pid for pid in current_ids if pid not in request.patient_ids]

        update_data = {"patient_ids": remaining if remaining else [], "updated_at": "now()"}

        supabase.table("doctor_doctor_patients")\
            .update(update_data)\
            .eq("doctor_id", doctor_id)\
            .eq("linked_doctor_id", linked_doctor_id)\
            .execute()

        supabase.table("doctor_doctor_patients")\
            .update(update_data)\
            .eq("doctor_id", linked_doctor_id)\
            .eq("linked_doctor_id", doctor_id)\
            .execute()

        return {
            "success": True,
            "message": f"Removed {len(request.patient_ids)} patient(s), {len(remaining)} remaining",
            "patient_ids": remaining,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DOCTOR_SHARING] Error removing patients: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to remove patients: {str(e)}")


@router.delete("/{doctor_id}/{linked_doctor_id}")
async def deactivate_sharing_link(
    doctor_id: str = Path(...),
    linked_doctor_id: str = Path(...),
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Soft-delete (deactivate) a sharing link. Deactivates both directions.
    """
    try:
        deactivate_data = {"is_active": False, "updated_at": "now()"}

        result = supabase.table("doctor_doctor_patients")\
            .update(deactivate_data)\
            .eq("doctor_id", doctor_id)\
            .eq("linked_doctor_id", linked_doctor_id)\
            .execute()

        supabase.table("doctor_doctor_patients")\
            .update(deactivate_data)\
            .eq("doctor_id", linked_doctor_id)\
            .eq("linked_doctor_id", doctor_id)\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Sharing link not found")

        logger.info(f"[DOCTOR_SHARING] Deactivated sharing link: {doctor_id[:8]}... ↔ {linked_doctor_id[:8]}...")

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

def _reactivate_link(doctor_id: str, linked_doctor_id: str, patient_ids: Optional[List[str]]) -> None:
    """Reactivate a previously deactivated sharing link (both directions)."""
    reactivate_data = {
        "is_active": True,
        "patient_ids": patient_ids,
        "updated_at": "now()",
    }

    supabase.table("doctor_doctor_patients")\
        .update(reactivate_data)\
        .eq("doctor_id", doctor_id)\
        .eq("linked_doctor_id", linked_doctor_id)\
        .execute()

    supabase.table("doctor_doctor_patients")\
        .update(reactivate_data)\
        .eq("doctor_id", linked_doctor_id)\
        .eq("linked_doctor_id", doctor_id)\
        .execute()

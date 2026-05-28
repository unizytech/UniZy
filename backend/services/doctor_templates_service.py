"""
Doctor Templates Service - Template sharing and activation management
Manages the doctor_templates junction table for template access control and activation.
"""

import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from services.supabase_service import supabase
import logging

logger = logging.getLogger(__name__)

# Columns to fetch for template listings (excludes large internal fields)
TEMPLATE_LIST_COLUMNS = "id, template_code, template_name, description, consultation_type_id, is_active, is_default, use_case, specialization, hospital_id, doctor_id, estimated_extraction_time_seconds, created_at, updated_at"


def assign_template_ownership(
    template_id: uuid.UUID,
    new_owner_id: uuid.UUID,
) -> Dict[str, Any]:
    """
    Assign ownership of a global template to a specific doctor.

    This converts a global template (doctor_id=NULL) to a doctor-owned template,
    and creates a doctor_templates entry for the new owner.

    Args:
        template_id: Template UUID to assign ownership
        new_owner_id: Doctor UUID to become the new owner

    Returns:
        Dict with template_updated and owner_share_created flags

    Raises:
        ValueError: If template not found, not global, or inactive
    """
    # Verify template exists and is global (doctor_id = NULL)
    template_response = (
        supabase.table("templates")
        .select("id, doctor_id, template_name, is_active")
        .eq("id", str(template_id))
        .limit(1)
        .execute()
    )

    if not template_response.data:
        raise ValueError(f"Template {template_id} not found")

    template = template_response.data[0]

    if not template.get("is_active", True):
        raise ValueError(f"Cannot assign ownership of inactive template {template_id}")

    if template.get("doctor_id") is not None:
        raise ValueError(f"Template {template_id} already has an owner. Cannot reassign ownership.")

    # Verify new owner exists
    doctor_response = (
        supabase.table("doctors")
        .select("id, full_name")
        .eq("id", str(new_owner_id))
        .limit(1)
        .execute()
    )

    if not doctor_response.data:
        raise ValueError(f"Doctor {new_owner_id} not found")

    doctor_name = doctor_response.data[0].get("full_name", "Unknown")

    # Update template's doctor_id
    update_response = (
        supabase.table("templates")
        .update({"doctor_id": str(new_owner_id), "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", str(template_id))
        .execute()
    )

    logger.info(f"[ASSIGN_OWNERSHIP] Template {template_id} assigned to doctor {new_owner_id} ({doctor_name})")

    # Create doctor_templates entry for the owner
    owner_share = {
        "doctor_id": str(new_owner_id),
        "template_id": str(template_id),
        "access_level": "use",
        "is_active": True,
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    # Check if entry already exists
    existing = (
        supabase.table("doctor_templates")
        .select("id")
        .eq("doctor_id", str(new_owner_id))
        .eq("template_id", str(template_id))
        .limit(1)
        .execute()
    )

    if existing.data:
        # Update existing entry
        supabase.table("doctor_templates").update({
            "access_level": "use",
            "is_active": True,
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("doctor_id", str(new_owner_id)).eq("template_id", str(template_id)).execute()
        logger.info(f"[ASSIGN_OWNERSHIP] Updated existing doctor_templates entry for owner")
    else:
        # Create new entry
        supabase.table("doctor_templates").insert(owner_share).execute()
        logger.info(f"[ASSIGN_OWNERSHIP] Created doctor_templates entry for owner")

    return {
        "template_updated": True,
        "owner_share_created": True,
        "new_owner_id": str(new_owner_id),
        "new_owner_name": doctor_name
    }


def share_template_with_doctor(
    template_id: uuid.UUID,
    doctor_id: uuid.UUID,
    shared_by_admin_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Share a template with a specific doctor.

    Args:
        template_id: Template UUID to share
        doctor_id: Doctor UUID to share with
        shared_by_admin_id: Admin UUID who is sharing (optional, for audit trail)

    Returns:
        Created doctor_templates record

    Raises:
        ValueError: If template not found or already shared
        ValueError: If trying to share doctor-owned template with another doctor
    """
    # Verify template exists and is active
    template = (
        supabase.table("templates")
        .select("id, doctor_id, template_name, is_active, consultation_type_id")
        .eq("id", str(template_id))
        .limit(1)
        .execute()
    )

    if not template.data:
        raise ValueError(f"Template {template_id} not found")

    # CRITICAL: Prevent sharing soft-deleted templates
    if not template.data[0].get("is_active", True):
        raise ValueError(
            f"Cannot share template {template_id} - template has been deactivated by admin. "
            "Reactivate the template first before sharing."
        )

    template_owner = template.data[0].get("doctor_id")

    # Prevent sharing if doctor already owns this template
    if template_owner == str(doctor_id):
        raise ValueError(f"Doctor {doctor_id} already owns this template")

    # Check if already shared
    existing = (
        supabase.table("doctor_templates")
        .select("id, is_active")
        .eq("doctor_id", str(doctor_id))
        .eq("template_id", str(template_id))
        .limit(1)
        .execute()
    )

    if existing.data:
        existing_record = existing.data[0]
        if existing_record.get("is_active"):
            # Already shared and active - no-op
            logger.info(f"Template {template_id} already shared with doctor {doctor_id} and active - no changes")
            return existing_record

        # Reactivate soft-deleted share
        result = (
            supabase.table("doctor_templates")
            .update({
                "access_level": "use",
                "is_active": True,
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            .eq("id", existing_record["id"])
            .execute()
        )
        logger.info(f"Reactivated template {template_id} share for doctor {doctor_id}")
        return result.data[0] if result.data else existing_record

    # Create doctor_templates record
    share_data = {
        "doctor_id": str(doctor_id),
        "template_id": str(template_id),
        "access_level": "use",
        "is_active": True,
        "activated_at": datetime.now(timezone.utc).isoformat(),
    }

    result = supabase.table("doctor_templates").insert(share_data).execute()

    logger.info(f"Shared template {template_id} with doctor {doctor_id} (access_level: use, is_active: True)")

    return result.data[0] if result.data else {}


def bulk_share_template(
    template_id: uuid.UUID,
    doctor_ids: List[uuid.UUID],
) -> Dict[str, Any]:
    """
    Share a template with multiple doctors at once.

    OPTIMIZED: Uses batch queries instead of N+1 individual queries.
    - Before: 4-6 queries per doctor (400-600 queries for 100 doctors)
    - After: 4-5 queries total regardless of doctor count

    Args:
        template_id: Template UUID to share
        doctor_ids: List of doctor UUIDs to share with

    Returns:
        Summary with success and failed operations
    """
    if not doctor_ids:
        return {
            "template_id": str(template_id),
            "total_requested": 0,
            "successful": 0,
            "failed": 0,
            "success": [],
            "failed_records": []
        }

    # 1. Verify template exists (1 query)
    template = (
        supabase.table("templates")
        .select("id, is_active, consultation_type_id, doctor_id")
        .eq("id", str(template_id))
        .limit(1)
        .execute()
    )

    if not template.data or not template.data[0].get("is_active"):
        raise ValueError(f"Template {template_id} not found or inactive")

    template_data = template.data[0]
    template_owner = template_data.get("doctor_id")
    consultation_type_id = template_data.get("consultation_type_id")

    # Filter out doctors who own the template
    doctor_ids_str = [str(d) for d in doctor_ids if str(d) != template_owner]

    if not doctor_ids_str:
        return {
            "template_id": str(template_id),
            "total_requested": len(doctor_ids),
            "successful": 0,
            "failed": len(doctor_ids),
            "success": [],
            "failed_records": [{"doctor_id": str(d), "error": "Doctor owns this template"} for d in doctor_ids]
        }

    # 2. Get existing shares for ALL doctors in ONE query
    existing = (
        supabase.table("doctor_templates")
        .select("id, doctor_id, is_active")
        .eq("template_id", str(template_id))
        .in_("doctor_id", doctor_ids_str)
        .execute()
    )

    existing_by_doctor = {e["doctor_id"]: e for e in (existing.data or [])}

    # 3. Separate into: new inserts, reactivations needed, already active
    to_insert = []
    to_reactivate = []
    already_active = []

    for doctor_id_str in doctor_ids_str:
        if doctor_id_str in existing_by_doctor:
            existing_record = existing_by_doctor[doctor_id_str]
            if existing_record.get("is_active"):
                already_active.append(doctor_id_str)
            else:
                # Soft-deleted, reactivate
                to_reactivate.append(existing_record["id"])
        else:
            to_insert.append({
                "doctor_id": doctor_id_str,
                "template_id": str(template_id),
                "access_level": "use",
                "is_active": True,
            })

    success = []
    failed = []

    # 4. Batch INSERT new shares (1 query)
    if to_insert:
        try:
            insert_result = supabase.table("doctor_templates").insert(to_insert).execute()
            for record in (insert_result.data or []):
                success.append({"doctor_id": record["doctor_id"], "action": "created"})
        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            for item in to_insert:
                failed.append({"doctor_id": item["doctor_id"], "error": str(e)})

    # 5. Batch reactivate soft-deleted shares (1 query)
    if to_reactivate:
        try:
            update_result = (
                supabase.table("doctor_templates")
                .update({
                    "access_level": "use",
                    "is_active": True,
                    "activated_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                })
                .in_("id", to_reactivate)
                .execute()
            )
            for record in (update_result.data or []):
                success.append({"doctor_id": record["doctor_id"], "action": "reactivated"})
        except Exception as e:
            logger.error(f"Batch reactivate failed: {e}")
            for record_id in to_reactivate:
                failed.append({"doctor_id": "unknown", "error": str(e)})

    # 6. Count already active as success
    for doctor_id_str in already_active:
        success.append({"doctor_id": doctor_id_str, "action": "already_shared"})

    logger.info(f"Bulk shared template {template_id}: {len(success)} success, {len(failed)} failed")

    return {
        "template_id": str(template_id),
        "total_requested": len(doctor_ids),
        "successful": len(success),
        "failed": len(failed),
        "success": success,
        "failed_records": failed
    }


def share_template_with_hospital(
    template_id: uuid.UUID,
    hospital_id: uuid.UUID,
) -> Dict[str, Any]:
    """
    Share a template with all doctors in a specific hospital.

    Args:
        template_id: Template UUID to share
        hospital_id: Hospital UUID

    Returns:
        Summary with success and failed operations
    """
    # Get all doctors in this hospital
    doctors = (
        supabase.table("doctors")
        .select("id")
        .eq("hospital_id", str(hospital_id))
        .eq("is_active", True)
        .execute()
    )

    if not doctors.data:
        return {
            "template_id": str(template_id),
            "hospital_id": str(hospital_id),
            "total_doctors": 0,
            "message": "No active doctors found in this hospital"
        }

    doctor_ids = [uuid.UUID(d["id"]) for d in doctors.data]

    return bulk_share_template(template_id, doctor_ids)


def share_template_with_specialization(
    template_id: uuid.UUID,
    specialization: str,
) -> Dict[str, Any]:
    """
    Share a template with all doctors of a specific specialization.

    Args:
        template_id: Template UUID to share
        specialization: Specialization name (e.g., "Cardiology", "Psychiatry")

    Returns:
        Summary with success and failed operations
    """
    # Get all doctors with this specialization
    doctors = (
        supabase.table("doctors")
        .select("id")
        .eq("specialization", specialization)
        .eq("is_active", True)
        .execute()
    )

    if not doctors.data:
        return {
            "template_id": str(template_id),
            "specialization": specialization,
            "total_doctors": 0,
            "message": f"No active doctors found with specialization '{specialization}'"
        }

    doctor_ids = [uuid.UUID(d["id"]) for d in doctors.data]

    return bulk_share_template(template_id, doctor_ids)


def activate_template_for_doctor(
    doctor_id: uuid.UUID,
    template_id: uuid.UUID,
    consultation_type_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Ensure a doctor_templates entry exists with is_active=True for this doctor+template.

    This simply links the template to the doctor. No "one active per consultation type"
    constraint — doctors can have multiple active templates.

    Args:
        doctor_id: Doctor UUID
        template_id: Template UUID to link
        consultation_type_id: Optional - not used for gating, kept for API compatibility

    Returns:
        Updated or created doctor_templates record

    Raises:
        ValueError: If template not found or soft-deleted
    """
    # Verify template exists and is active
    template = (
        supabase.table("templates")
        .select("id, doctor_id, is_active")
        .eq("id", str(template_id))
        .limit(1)
        .execute()
    )

    if not template.data:
        raise ValueError(f"Template {template_id} not found")

    # CRITICAL: Prevent linking soft-deleted templates
    if not template.data[0].get("is_active", True):
        raise ValueError(
            f"Cannot activate template {template_id} - template has been deactivated by admin. "
            "Contact admin to reactivate the template."
        )

    # Check if record exists
    existing = (
        supabase.table("doctor_templates")
        .select("id, is_active")
        .eq("doctor_id", str(doctor_id))
        .eq("template_id", str(template_id))
        .limit(1)
        .execute()
    )

    if existing.data:
        if existing.data[0].get("is_active"):
            # Already active, no-op
            return existing.data[0]
        # Reactivate
        result = (
            supabase.table("doctor_templates")
            .update({
                "is_active": True,
                "access_level": "use",
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            .eq("doctor_id", str(doctor_id))
            .eq("template_id", str(template_id))
            .execute()
        )
    else:
        # Create new record
        result = supabase.table("doctor_templates").insert({
            "doctor_id": str(doctor_id),
            "template_id": str(template_id),
            "access_level": "use",
            "is_active": True,
            "activated_at": datetime.now(timezone.utc).isoformat()
        }).execute()

    logger.info(f"Activated template {template_id} for doctor {doctor_id}")

    return result.data[0] if result.data else {}


def deactivate_template_for_doctor(
    doctor_id: uuid.UUID,
    template_id: uuid.UUID
) -> None:
    """
    Soft-delete a doctor-template link by setting is_active=False.

    This removes the template from the doctor's visible list without
    deleting the junction row.

    Args:
        doctor_id: Doctor UUID
        template_id: Template UUID to remove
    """
    supabase.table("doctor_templates")\
        .update({
            "is_active": False,
            "updated_at": datetime.now(timezone.utc).isoformat()
        })\
        .eq("doctor_id", str(doctor_id))\
        .eq("template_id", str(template_id))\
        .execute()

    logger.info(f"Soft-deleted template {template_id} for doctor {doctor_id}")


def get_doctor_accessible_templates(
    doctor_id: uuid.UUID,
    consultation_type_id: Optional[uuid.UUID] = None,
    include_common: bool = True
) -> List[Dict[str, Any]]:
    """
    Get all templates accessible to a doctor.

    Returns templates that:
    1. Doctor owns (templates.doctor_id = doctor_id)
    2. Are shared with doctor (doctor_templates junction table)
    3. Are common (templates.doctor_id = NULL) if include_common=True

    Args:
        doctor_id: Doctor UUID
        consultation_type_id: Optional - filter by consultation type
        include_common: Include common templates (doctor_id=NULL)

    Returns:
        List of accessible templates with access info
    """
    # Use explicit columns to exclude large internal fields (assembled_full_prompt, assembled_schema_json)

    # Get owned templates
    owned_query = supabase.table("templates")\
        .select(f"{TEMPLATE_LIST_COLUMNS}, consultation_types(type_code, type_name)")\
        .eq("doctor_id", str(doctor_id))\
        .eq("is_active", True)

    if consultation_type_id:
        owned_query = owned_query.eq("consultation_type_id", str(consultation_type_id))

    owned_templates = owned_query.execute()

    # Get shared templates
    shared_query = supabase.table("doctor_templates")\
        .select(f"*, templates({TEMPLATE_LIST_COLUMNS}, consultation_types(type_code, type_name))")\
        .eq("doctor_id", str(doctor_id))

    shared_templates = shared_query.execute()

    # Get common templates
    common_templates_data = []
    if include_common:
        common_query = supabase.table("templates")\
            .select(f"{TEMPLATE_LIST_COLUMNS}, consultation_types(type_code, type_name)")\
            .is_("doctor_id", "null")\
            .eq("is_active", True)

        if consultation_type_id:
            common_query = common_query.eq("consultation_type_id", str(consultation_type_id))

        common_templates = common_query.execute()
        common_templates_data = common_templates.data if common_templates.data else []

    # Combine results - build explicit fields to avoid leaking internal data
    results = []

    # Helper to build template result with explicit fields
    def build_template_result(template: Dict, access_type: str, is_active: bool) -> Dict[str, Any]:
        consultation_type = template.get("consultation_types", {}) or {}
        return {
            "id": template.get("id"),
            "template_code": template.get("template_code"),
            "template_name": template.get("template_name"),
            "description": template.get("description"),
            "consultation_type_id": template.get("consultation_type_id"),
            "consultation_type_code": consultation_type.get("type_code"),
            "consultation_type_name": consultation_type.get("type_name"),
            "is_default": template.get("is_default"),
            "use_case": template.get("use_case"),
            "specialization": template.get("specialization"),
            "hospital_id": template.get("hospital_id"),
            "doctor_id": template.get("doctor_id"),
            "estimated_extraction_time_seconds": template.get("estimated_extraction_time_seconds"),
            "created_at": template.get("created_at"),
            "updated_at": template.get("updated_at"),
            "access_type": access_type,
            "access_level": "use",
            "is_active": is_active
        }

    # Add owned templates
    for template in (owned_templates.data or []):
        results.append(build_template_result(
            template,
            access_type="owner",
            is_active=True
        ))

    # Add shared templates
    for record in (shared_templates.data or []):
        template = record.get("templates", {})
        # Skip if parent template is soft-deleted
        if not template or not template.get("is_active", True):
            continue
        # Only include active (not soft-deleted) doctor_templates entries
        if not record.get("is_active", False):
            continue
        results.append(build_template_result(
            template,
            access_type="shared",
            is_active=True
        ))

    # Add common templates
    for template in common_templates_data:
        results.append(build_template_result(
            template,
            access_type="common",
            is_active=True
        ))

    return results


def get_doctor_default_template(doctor_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get the default template for a doctor.

    Priority order:
    1. Doctor's own default_template_id (if set)
    2. Doctor's hospital's default_template_id (if doctor belongs to hospital and hospital has default)
    3. None

    Args:
        doctor_id: Doctor UUID

    Returns:
        Dict with id and template_code if default found, None otherwise
    """
    # Get doctor with their default_template_id and hospital_id
    doctor_result = (
        supabase.table("doctors")
        .select("id, default_template_id, hospital_id")
        .eq("id", str(doctor_id))
        .limit(1)
        .execute()
    )

    if not doctor_result.data:
        return None

    doctor = doctor_result.data[0]
    default_template_id = doctor.get("default_template_id")

    # Priority 1: Doctor's own default
    if default_template_id:
        template_result = (
            supabase.table("templates")
            .select("id, template_code")
            .eq("id", default_template_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if template_result.data:
            return {
                "id": template_result.data[0]["id"],
                "template_code": template_result.data[0]["template_code"]
            }

    # Priority 2: Hospital's default
    hospital_id = doctor.get("hospital_id")
    if hospital_id:
        hospital_result = (
            supabase.table("hospitals")
            .select("default_template_id")
            .eq("id", hospital_id)
            .limit(1)
            .execute()
        )

        if hospital_result.data:
            hospital_default_id = hospital_result.data[0].get("default_template_id")
            if hospital_default_id:
                template_result = (
                    supabase.table("templates")
                    .select("id, template_code")
                    .eq("id", hospital_default_id)
                    .eq("is_active", True)
                    .limit(1)
                    .execute()
                )
                if template_result.data:
                    return {
                        "id": template_result.data[0]["id"],
                        "template_code": template_result.data[0]["template_code"]
                    }

    return None


def revoke_template_access(
    doctor_id: uuid.UUID,
    template_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Revoke a doctor's access to a shared template.

    This ONLY removes junction table entries (explicitly granted access).
    Cannot revoke access to templates owned by the doctor.

    Args:
        doctor_id: Doctor UUID
        template_id: Template UUID

    Returns:
        Dict with revoked status and count

    Raises:
        ValueError: If trying to revoke access to owned template
    """
    # Verify template exists and check ownership
    template = (
        supabase.table("templates")
        .select("doctor_id")
        .eq("id", str(template_id))
        .limit(1)
        .execute()
    )

    if not template.data:
        raise ValueError(f"Template {template_id} not found")

    template_owner = template.data[0].get("doctor_id")

    # Prevent revoking access to templates the doctor owns
    if template_owner == str(doctor_id):
        raise ValueError("Cannot revoke access to owned template. Delete the template instead.")

    # Check if entry exists before attempting delete
    existing = (
        supabase.table("doctor_templates")
        .select("id, is_active")
        .eq("doctor_id", str(doctor_id))
        .eq("template_id", str(template_id))
        .limit(1)
        .execute()
    )

    if not existing.data:
        logger.warning(f"[REVOKE] No doctor_templates entry found for doctor {doctor_id} and template {template_id}")
        return {"revoked": False, "reason": "no_entry_found"}

    entry_id = existing.data[0]["id"]
    was_active = existing.data[0].get("is_active", False)

    # Delete from doctor_templates junction table
    # This removes explicitly granted access (via share)
    # Common templates can have junction entries when explicitly shared
    delete_result = (
        supabase.table("doctor_templates")
        .delete()
        .eq("id", entry_id)
        .execute()
    )

    # Verify deletion succeeded
    deleted_count = len(delete_result.data) if delete_result.data else 0

    if deleted_count > 0:
        logger.info(f"[REVOKE] Successfully deleted doctor_templates entry (id={entry_id}) for doctor {doctor_id} and template {template_id}. was_active={was_active}")
        return {"revoked": True, "deleted_count": deleted_count, "was_active": was_active}
    else:
        logger.error(f"[REVOKE] DELETE returned no data for entry (id={entry_id}). doctor={doctor_id}, template={template_id}")
        # As a fallback, verify the entry is truly gone
        verify = (
            supabase.table("doctor_templates")
            .select("id")
            .eq("id", entry_id)
            .limit(1)
            .execute()
        )
        if not verify.data:
            logger.info(f"[REVOKE] Verified entry (id={entry_id}) is deleted despite empty response")
            return {"revoked": True, "deleted_count": 1, "was_active": was_active, "verified": True}
        else:
            logger.error(f"[REVOKE] Entry (id={entry_id}) still exists after DELETE!")
            return {"revoked": False, "reason": "delete_failed"}


def check_consultation_type_visibility(
    doctor_id: uuid.UUID,
    consultation_type_id: uuid.UUID
) -> bool:
    """
    Check if a doctor has visibility to a specific consultation type.

    Visibility rules:
    - If ALL visibility arrays (visible_to_hospitals, visible_to_doctors, visible_to_specializations) are NULL/empty → Everyone can see
    - If ANY array has values → Only those specific entities can see it

    Args:
        doctor_id: Doctor UUID
        consultation_type_id: Consultation type UUID

    Returns:
        True if doctor has visibility, False otherwise
    """
    # Get consultation type with visibility settings
    consult_type = (
        supabase.table("consultation_types")
        .select("visible_to_hospitals, visible_to_doctors, visible_to_specializations")
        .eq("id", str(consultation_type_id))
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    if not consult_type.data:
        return False

    visibility = consult_type.data[0]
    visible_hospitals = visibility.get("visible_to_hospitals") or []
    visible_doctors = visibility.get("visible_to_doctors") or []
    visible_specializations = visibility.get("visible_to_specializations") or []

    # If all visibility arrays are empty → Everyone can see
    if not visible_hospitals and not visible_doctors and not visible_specializations:
        return True

    # Get doctor details
    doctor = (
        supabase.table("doctors")
        .select("id, hospital_id, specialization")
        .eq("id", str(doctor_id))
        .limit(1)
        .execute()
    )

    if not doctor.data:
        return False

    doctor_data = doctor.data[0]
    doctor_hospital = doctor_data.get("hospital_id")
    doctor_specialization = doctor_data.get("specialization")

    # Check visibility conditions (OR logic - any match grants access)
    if visible_doctors and str(doctor_id) in visible_doctors:
        return True

    if visible_hospitals and doctor_hospital and str(doctor_hospital) in visible_hospitals:
        return True

    if visible_specializations and doctor_specialization in visible_specializations:
        return True

    return False


def activate_from_consultation_type(
    doctor_id: uuid.UUID,
    consultation_type_id: uuid.UUID,
    template_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create and activate a new doctor-owned template from a consultation type.

    Workflow:
    1. Check doctor has visibility to this consultation type
    2. Create new template owned by doctor
    3. Clone all segments from consultation_type_segments junction
    4. Auto-activate for doctor

    Args:
        doctor_id: Doctor UUID
        consultation_type_id: Consultation type UUID to clone from
        template_name: Optional custom template name

    Returns:
        Created template record with activation status

    Raises:
        PermissionError: If doctor doesn't have visibility to consultation type
        ValueError: If consultation type not found
    """
    # Check visibility
    if not check_consultation_type_visibility(doctor_id, consultation_type_id):
        raise PermissionError(
            f"Doctor {doctor_id} does not have visibility to consultation type {consultation_type_id}. "
            "Contact admin to enable visibility."
        )

    # Get consultation type details
    consult_type = (
        supabase.table("consultation_types")
        .select("type_code, type_name")
        .eq("id", str(consultation_type_id))
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    if not consult_type.data:
        raise ValueError(f"Consultation type {consultation_type_id} not found")

    type_code = consult_type.data[0]["type_code"]
    type_name = consult_type.data[0]["type_name"]

    # Get doctor details for naming
    doctor = (
        supabase.table("doctors")
        .select("full_name")
        .eq("id", str(doctor_id))
        .limit(1)
        .execute()
    )

    if not doctor.data:
        raise ValueError(f"Doctor {doctor_id} not found")

    doctor_name_part = doctor.data[0]["full_name"].replace(" ", "").upper()[:8]

    # Generate unique template_code (max 50 chars)
    # Include microseconds to prevent collisions when called rapidly
    timestamp = datetime.now(timezone.utc).strftime("%m%d%H%M%S%f")
    template_code = f"{type_code}_{doctor_name_part}_{timestamp}"

    # Create template
    template_data = {
        "template_code": template_code,
        "template_name": template_name or f"{type_name} - {doctor_name_part}",
        "consultation_type_id": str(consultation_type_id),
        "doctor_id": str(doctor_id),  # Doctor owns this template
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    new_template = supabase.table("templates").insert(template_data).execute()

    if not new_template.data:
        raise ValueError("Failed to create template")

    template_id = new_template.data[0]["id"]

    # Clone segments from consultation_type_segments
    consult_segments = (
        supabase.table("consultation_type_segments")
        .select("segment_id, segment_code, default_category, default_display_order, default_brevity_level, default_terminology_style")
        .eq("consultation_type_id", str(consultation_type_id))
        .execute()
    )

    if consult_segments.data:
        template_segments = []
        actual_template_name = template_data["template_name"]
        for segment in consult_segments.data:
            template_segments.append({
                "template_id": template_id,
                "template_name": actual_template_name,  # Include template name in junction
                "segment_id": segment["segment_id"],
                "segment_code": segment["segment_code"],
                "category": segment.get("default_category", "additional"),
                "display_order": segment.get("default_display_order", 999),
                "brevity_level": segment.get("default_brevity_level", "balanced"),
                "terminology_style": segment.get("default_terminology_style", "medical_terms")
            })

        supabase.table("template_segments").insert(template_segments).execute()

    # Auto-activate for doctor
    activate_template_for_doctor(doctor_id, uuid.UUID(template_id), consultation_type_id)

    logger.info(f"Created and activated template {template_id} from consultation type {type_code} for doctor {doctor_id}")

    return {
        **new_template.data[0],
        "segment_count": len(consult_segments.data) if consult_segments.data else 0,
        "is_activated": True
    }


def clone_template(
    doctor_id: uuid.UUID,
    source_template_id: uuid.UUID,
    template_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Clone a template to create a doctor-owned copy.

    Doctor can clone:
    - Shared templates
    - Global templates (doctor_id = NULL)
    - Their own templates (for versioning)

    Workflow:
    1. Verify doctor has access to source template
    2. Create new template owned by doctor
    3. Copy all segments from template_segments junction
    4. Auto-activate for doctor

    Args:
        doctor_id: Doctor UUID
        source_template_id: Template UUID to clone
        template_name: Optional custom name for cloned template

    Returns:
        Created template record with activation status

    Raises:
        ValueError: If source template not found or not accessible
    """
    # Verify source template exists
    source_template = (
        supabase.table("templates")
        .select("*, consultation_types(type_code, type_name)")
        .eq("id", str(source_template_id))
        .limit(1)
        .execute()
    )

    if not source_template.data:
        raise ValueError(f"Source template {source_template_id} not found")

    source = source_template.data[0]

    # Check if source template is soft-deleted
    if not source.get("is_active", True):
        raise ValueError(f"Cannot clone deactivated template {source_template_id}")

    source_owner = source.get("doctor_id")
    consultation_type_id = source.get("consultation_type_id")
    consultation_type = source.get("consultation_types", {})
    type_code = consultation_type.get("type_code", "TEMPLATE")

    # Check access
    can_clone = False

    if source_owner == str(doctor_id):
        # Doctor owns the source
        can_clone = True
    elif source_owner is None:
        # Common/global template
        can_clone = True
    else:
        # Check if shared
        shared = (
            supabase.table("doctor_templates")
            .select("id")
            .eq("doctor_id", str(doctor_id))
            .eq("template_id", str(source_template_id))
            .limit(1)
            .execute()
        )
        can_clone = bool(shared.data)

    if not can_clone:
        raise ValueError(
            f"Doctor {doctor_id} does not have access to template {source_template_id}. "
            "Cannot clone inaccessible template."
        )

    # Get doctor details for naming
    doctor = (
        supabase.table("doctors")
        .select("full_name")
        .eq("id", str(doctor_id))
        .limit(1)
        .execute()
    )

    if not doctor.data:
        raise ValueError(f"Doctor {doctor_id} not found")

    doctor_name_part = doctor.data[0]["full_name"].replace(" ", "").upper()[:8]

    # Generate unique template_code (max 50 chars)
    # Include microseconds to prevent collisions when called rapidly
    timestamp = datetime.now(timezone.utc).strftime("%m%d%H%M%S%f")
    template_code = f"CLN_{type_code}_{doctor_name_part}_{timestamp}"

    # Create cloned template
    template_data = {
        "template_code": template_code,
        "template_name": template_name or f"Clone of {source.get('template_name', 'Template')}",
        "consultation_type_id": consultation_type_id,
        "doctor_id": str(doctor_id),  # Doctor owns the clone
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    new_template = supabase.table("templates").insert(template_data).execute()

    if not new_template.data:
        raise ValueError("Failed to create cloned template")

    template_id = new_template.data[0]["id"]

    # Clone segments from source template_segments
    source_segments = (
        supabase.table("template_segments")
        .select("segment_id, segment_code, category, display_order, brevity_level, terminology_style")
        .eq("template_id", str(source_template_id))
        .execute()
    )

    if source_segments.data:
        template_segments = []
        actual_template_name = template_data["template_name"]
        for segment in source_segments.data:
            template_segments.append({
                "template_id": template_id,
                "template_name": actual_template_name,  # Include template name in junction
                "segment_id": segment["segment_id"],
                "segment_code": segment["segment_code"],
                "category": segment.get("category", "ADDITIONAL"),
                "display_order": segment.get("display_order", 999),
                "brevity_level": segment.get("brevity_level", "balanced"),
                "terminology_style": segment.get("terminology_style", "medical_terms")
            })

        supabase.table("template_segments").insert(template_segments).execute()

    # Auto-activate for doctor
    if consultation_type_id:
        activate_template_for_doctor(doctor_id, uuid.UUID(template_id), uuid.UUID(consultation_type_id))

    logger.info(f"Cloned template {source_template_id} → {template_id} for doctor {doctor_id}")

    return {
        **new_template.data[0],
        "source_template_id": str(source_template_id),
        "segment_count": len(source_segments.data) if source_segments.data else 0,
        "is_activated": True if consultation_type_id else False
    }


def get_doctor_dashboard_data(
    doctor_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Get comprehensive dashboard data for a doctor.

    Returns:
    1. Visible consultation types (based on visibility settings)
    2. Accessible templates (owned, shared, global) grouped by access type

    Args:
        doctor_id: Doctor UUID

    Returns:
        Dictionary with consultation_types and templates lists
    """
    # Get all active consultation types
    all_consult_types = (
        supabase.table("consultation_types")
        .select("id, type_code, type_name, description, icon_name, color_code, visible_to_hospitals, visible_to_doctors, visible_to_specializations")
        .eq("is_active", True)
        .execute()
    )

    # Get doctor details
    doctor = (
        supabase.table("doctors")
        .select("id, hospital_id, specialization")
        .eq("id", str(doctor_id))
        .limit(1)
        .execute()
    )

    if not doctor.data:
        raise ValueError(f"Doctor {doctor_id} not found")

    doctor_data = doctor.data[0]
    doctor_hospital = doctor_data.get("hospital_id")
    doctor_specialization = doctor_data.get("specialization")

    # Filter visible consultation types
    visible_consultation_types = []

    for ct in (all_consult_types.data or []):
        visible_hospitals = ct.get("visible_to_hospitals") or []
        visible_doctors = ct.get("visible_to_doctors") or []
        visible_specializations = ct.get("visible_to_specializations") or []

        # If all empty → everyone can see
        if not visible_hospitals and not visible_doctors and not visible_specializations:
            visible_consultation_types.append({
                "id": ct["id"],
                "type_code": ct["type_code"],
                "type_name": ct["type_name"],
                "description": ct.get("description"),
                "icon_name": ct.get("icon_name"),
                "color_code": ct.get("color_code"),
                "access_type": "create_template",  # Can activate from consultation type
                "badge": "Activate"
            })
            continue

        # Check specific visibility (OR logic)
        has_visibility = False

        if visible_doctors and str(doctor_id) in visible_doctors:
            has_visibility = True
        elif visible_hospitals and doctor_hospital and str(doctor_hospital) in visible_hospitals:
            has_visibility = True
        elif visible_specializations and doctor_specialization in visible_specializations:
            has_visibility = True

        if has_visibility:
            visible_consultation_types.append({
                "id": ct["id"],
                "type_code": ct["type_code"],
                "type_name": ct["type_name"],
                "description": ct.get("description"),
                "icon_name": ct.get("icon_name"),
                "color_code": ct.get("color_code"),
                "access_type": "create_template",
                "badge": "Activate"
            })

    # Get accessible templates
    accessible_templates = get_doctor_accessible_templates(doctor_id, include_common=True)

    # Enrich templates with action badges
    for template in accessible_templates:
        if template.get("access_type") == "owner":
            template["badge"] = "Owned"
        elif template.get("access_type") == "common":
            template["badge"] = "Global"
        else:
            template["badge"] = "Shared"

    return {
        "consultation_types": visible_consultation_types,
        "templates": accessible_templates,
        "consultation_types_count": len(visible_consultation_types),
        "templates_count": len(accessible_templates)
    }


def get_template_shares(template_id: uuid.UUID) -> Dict[str, Any]:
    """
    Get all shares for a template.

    Returns individual doctor shares, and ONLY hospitals/specializations where
    ALL doctors have the template.

    Args:
        template_id: Template UUID

    Returns:
        Dictionary with:
        - doctors: List of individual doctor shares with is_active status
        - hospital_ids: List of hospital IDs where ALL doctors have this template
        - specializations: List of specializations where ALL doctors have this template

    Note:
        is_active=true means the share is active, is_active=false means soft-deleted.
    """
    # Get ALL individual doctor shares from doctor_templates junction table
    doctor_shares = (
        supabase.table("doctor_templates")
        .select("id, doctor_id, is_active, activated_at, doctors(id, full_name, email, specialization, hospital_id)")
        .eq("template_id", str(template_id))
        .execute()
    )

    # Format doctor shares
    doctors = []
    doctors_with_template_by_hospital = {}  # hospital_id -> set of doctor_ids with template
    doctors_with_template_by_spec = {}  # specialization -> set of doctor_ids with template

    for share in doctor_shares.data:
        doctor_info = share.get("doctors", {})
        doctor_id = share["doctor_id"]
        hospital_id = doctor_info.get("hospital_id")
        specialization = doctor_info.get("specialization")

        doctors.append({
            "id": share["id"],
            "doctor_id": doctor_id,
            "doctor_name": doctor_info.get("full_name", "Unknown"),
            "email": doctor_info.get("email"),
            "specialization": specialization,
            "hospital_id": hospital_id,
            "is_active": share.get("is_active", False),
            "activated_at": share.get("activated_at")
        })

        # Track which doctors have template by hospital and specialization
        if hospital_id:
            if hospital_id not in doctors_with_template_by_hospital:
                doctors_with_template_by_hospital[hospital_id] = set()
            doctors_with_template_by_hospital[hospital_id].add(doctor_id)

        if specialization:
            if specialization not in doctors_with_template_by_spec:
                doctors_with_template_by_spec[specialization] = set()
            doctors_with_template_by_spec[specialization].add(doctor_id)

    # OPTIMIZED: Get ALL doctor counts in 1 query instead of N queries per hospital/specialization
    # Before: 1 query per hospital + 1 query per specialization (N+1 problem)
    # After: 1 query total for all active doctors grouped by hospital and specialization

    fully_shared_hospitals = []
    fully_shared_specializations = []

    if doctors_with_template_by_hospital or doctors_with_template_by_spec:
        # Get all active doctors with their hospital_id and specialization (1 query)
        all_active_doctors = (
            supabase.table("doctors")
            .select("id, hospital_id, specialization")
            .eq("is_active", True)
            .execute()
        )

        # Build counts in-memory (O(n) where n = total doctors)
        hospital_doctor_counts = {}  # hospital_id -> total active doctors
        spec_doctor_counts = {}  # specialization -> total active doctors

        for doc in (all_active_doctors.data or []):
            h_id = doc.get("hospital_id")
            spec = doc.get("specialization")

            if h_id:
                hospital_doctor_counts[h_id] = hospital_doctor_counts.get(h_id, 0) + 1
            if spec:
                spec_doctor_counts[spec] = spec_doctor_counts.get(spec, 0) + 1

        # Compare with template shares (in-memory, no more queries)
        for hospital_id, doctors_with_access in doctors_with_template_by_hospital.items():
            total_in_hospital = hospital_doctor_counts.get(hospital_id, 0)
            if total_in_hospital > 0 and total_in_hospital == len(doctors_with_access):
                fully_shared_hospitals.append(hospital_id)

        for spec, doctors_with_access in doctors_with_template_by_spec.items():
            total_with_spec = spec_doctor_counts.get(spec, 0)
            if total_with_spec > 0 and total_with_spec == len(doctors_with_access):
                fully_shared_specializations.append(spec)

    return {
        "doctors": doctors,
        "hospital_ids": fully_shared_hospitals,
        "specializations": fully_shared_specializations,
        "total_shares": len(doctors)
    }

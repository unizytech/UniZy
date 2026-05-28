"""
Nurse Templates Service - Template sharing and activation management for nurses

Manages the nurse_templates junction table for template access control and activation.
Unlike doctors, nurses cannot own templates - they can only use templates shared with them.
"""

import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from services.supabase_service import supabase
import logging

logger = logging.getLogger(__name__)

# Columns to fetch for template listings (excludes large internal fields)
TEMPLATE_LIST_COLUMNS = "id, template_code, template_name, description, consultation_type_id, is_active, is_default, use_case, specialization, hospital_id, doctor_id, estimated_extraction_time_seconds, created_at, updated_at"


def share_template_with_nurse(
    template_id: uuid.UUID,
    template_code: str,
    nurse_id: uuid.UUID,
) -> Dict[str, Any]:
    """
    Share a template with a specific nurse.

    Args:
        template_id: Template UUID to share
        template_code: Template code (denormalized for readability)
        nurse_id: Nurse UUID to share with

    Returns:
        Created or reactivated nurse_templates record

    Raises:
        ValueError: If template not found or nurse not found
    """
    # Verify template exists and is active
    template = (
        supabase.table("templates")
        .select("id, template_code, template_name, is_active")
        .eq("id", str(template_id))
        .limit(1)
        .execute()
    )

    if not template.data:
        raise ValueError(f"Template {template_id} not found")

    if not template.data[0].get("is_active", True):
        raise ValueError(
            f"Cannot share template {template_id} - template has been deactivated. "
            "Reactivate the template first before sharing."
        )

    # Verify nurse exists
    nurse = (
        supabase.table("nurses")
        .select("id, full_name")
        .eq("id", str(nurse_id))
        .limit(1)
        .execute()
    )

    if not nurse.data:
        raise ValueError(f"Nurse {nurse_id} not found")

    # Check if already shared
    existing = (
        supabase.table("nurse_templates")
        .select("id, is_active")
        .eq("nurse_id", str(nurse_id))
        .eq("template_id", str(template_id))
        .limit(1)
        .execute()
    )

    if existing.data:
        existing_record = existing.data[0]
        if existing_record.get("is_active"):
            logger.info(f"Template {template_id} already shared with nurse {nurse_id}")
            return existing_record

        # Reactivate soft-deleted entry
        result = (
            supabase.table("nurse_templates")
            .update({
                "is_active": True,
                "access_level": "use",
                "activated_at": datetime.now(timezone.utc).isoformat()
            })
            .eq("id", existing_record["id"])
            .execute()
        )
        logger.info(f"Reactivated template {template_id} for nurse {nurse_id}")
        return result.data[0] if result.data else existing_record

    # Create nurse_templates record
    share_data = {
        "nurse_id": str(nurse_id),
        "template_id": str(template_id),
        "template_code": template_code,
        "access_level": "use",
        "is_active": True,
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    result = supabase.table("nurse_templates").insert(share_data).execute()

    logger.info(f"Shared template {template_id} with nurse {nurse_id}")

    return result.data[0] if result.data else {}


def bulk_share_template_with_nurses(
    template_id: uuid.UUID,
    template_code: str,
    nurse_ids: List[uuid.UUID],
) -> Dict[str, Any]:
    """
    Share a template with multiple nurses at once.

    Args:
        template_id: Template UUID to share
        template_code: Template code (denormalized for readability)
        nurse_ids: List of nurse UUIDs to share with

    Returns:
        Summary with success and failed operations
    """
    if not nurse_ids:
        return {
            "template_id": str(template_id),
            "total_requested": 0,
            "successful": 0,
            "failed": 0,
            "success": [],
            "failed_records": []
        }

    # Verify template exists
    template = (
        supabase.table("templates")
        .select("id, is_active")
        .eq("id", str(template_id))
        .limit(1)
        .execute()
    )

    if not template.data or not template.data[0].get("is_active"):
        raise ValueError(f"Template {template_id} not found or inactive")

    nurse_ids_str = [str(n) for n in nurse_ids]

    # Get existing shares for ALL nurses in ONE query
    existing = (
        supabase.table("nurse_templates")
        .select("id, nurse_id, is_active")
        .eq("template_id", str(template_id))
        .in_("nurse_id", nurse_ids_str)
        .execute()
    )

    existing_by_nurse = {e["nurse_id"]: e for e in (existing.data or [])}

    # Separate into: new inserts, reactivate (soft-deleted), already active
    to_insert = []
    to_reactivate = []
    already_active = []

    for nurse_id_str in nurse_ids_str:
        if nurse_id_str in existing_by_nurse:
            existing_record = existing_by_nurse[nurse_id_str]
            if existing_record.get("is_active"):
                already_active.append(nurse_id_str)
            else:
                to_reactivate.append(existing_record["id"])
        else:
            to_insert.append({
                "nurse_id": nurse_id_str,
                "template_id": str(template_id),
                "template_code": template_code,
                "access_level": "use",
                "is_active": True,
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat()
            })

    success = []
    failed = []

    # Batch INSERT new shares
    if to_insert:
        try:
            insert_result = supabase.table("nurse_templates").insert(to_insert).execute()
            for record in (insert_result.data or []):
                success.append({"nurse_id": record["nurse_id"], "action": "created"})
        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            for item in to_insert:
                failed.append({"nurse_id": item["nurse_id"], "error": str(e)})

    # Batch REACTIVATE soft-deleted shares
    if to_reactivate:
        try:
            update_result = (
                supabase.table("nurse_templates")
                .update({
                    "access_level": "use",
                    "is_active": True,
                    "activated_at": datetime.now(timezone.utc).isoformat()
                })
                .in_("id", to_reactivate)
                .execute()
            )
            for record in (update_result.data or []):
                success.append({"nurse_id": record["nurse_id"], "action": "reactivated"})
        except Exception as e:
            logger.error(f"Batch reactivate failed: {e}")
            for record_id in to_reactivate:
                failed.append({"nurse_id": "unknown", "error": str(e)})

    # Count already active as success
    for nurse_id_str in already_active:
        success.append({"nurse_id": nurse_id_str, "action": "already_shared"})

    logger.info(f"Bulk shared template {template_id}: {len(success)} success, {len(failed)} failed")

    return {
        "template_id": str(template_id),
        "total_requested": len(nurse_ids),
        "successful": len(success),
        "failed": len(failed),
        "success": success,
        "failed_records": failed
    }


def activate_template_for_nurse(
    nurse_id: uuid.UUID,
    template_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Activate (link) a template for a specific nurse.

    Sets is_active=True on the nurse_templates entry. Multiple templates
    can be active simultaneously.

    Args:
        nurse_id: Nurse UUID
        template_id: Template UUID to activate

    Returns:
        Updated activation record

    Raises:
        ValueError: If template not accessible by nurse
    """
    # Verify nurse has access to this template
    access = (
        supabase.table("nurse_templates")
        .select("id")
        .eq("nurse_id", str(nurse_id))
        .eq("template_id", str(template_id))
        .limit(1)
        .execute()
    )

    if not access.data:
        raise ValueError(f"Nurse {nurse_id} does not have access to template {template_id}")

    # Activate the selected template (no "deactivate all others" — multiple can be active)
    result = (
        supabase.table("nurse_templates")
        .update({
            "is_active": True,
            "activated_at": datetime.now(timezone.utc).isoformat()
        })
        .eq("nurse_id", str(nurse_id))
        .eq("template_id", str(template_id))
        .execute()
    )

    logger.info(f"Activated template {template_id} for nurse {nurse_id}")

    return result.data[0] if result.data else {}


def deactivate_template_for_nurse(
    nurse_id: uuid.UUID,
    template_id: uuid.UUID
) -> None:
    """
    Soft-delete a template for a specific nurse (set is_active=False).

    Args:
        nurse_id: Nurse UUID
        template_id: Template UUID to remove
    """
    supabase.table("nurse_templates")\
        .update({"is_active": False})\
        .eq("nurse_id", str(nurse_id))\
        .eq("template_id", str(template_id))\
        .execute()

    logger.info(f"Deactivated template {template_id} for nurse {nurse_id}")


def get_nurse_accessible_templates(
    nurse_id: uuid.UUID
) -> List[Dict[str, Any]]:
    """
    Get all templates accessible to a nurse.

    Args:
        nurse_id: Nurse UUID

    Returns:
        List of accessible templates with access info
    """
    # Get shared templates via nurse_templates junction
    # Use explicit columns to exclude large internal fields (assembled_full_prompt, assembled_schema_json)
    shared = supabase.table("nurse_templates")\
        .select(f"*, templates({TEMPLATE_LIST_COLUMNS}, consultation_types(type_code, type_name))")\
        .eq("nurse_id", str(nurse_id))\
        .execute()

    results = []

    for record in (shared.data or []):
        template = record.get("templates", {})
        # Only return entries where both nurse_templates.is_active AND templates.is_active are True
        if template and template.get("is_active", True) and record.get("is_active", False):
            consultation_type = template.get("consultation_types", {}) or {}
            results.append({
                "id": record.get("id"),  # nurse_templates junction ID
                "nurse_id": record.get("nurse_id"),
                "template_id": template.get("id"),  # The actual template ID
                "template_code": record.get("template_code") or template.get("template_code"),
                "template_name": template.get("template_name"),
                "description": template.get("description"),
                "consultation_type_code": consultation_type.get("type_code"),
                "consultation_type_name": consultation_type.get("type_name"),
                "access_type": "shared",
                "is_active": record.get("is_active", False),
                "activated_at": record.get("activated_at"),
                "created_at": record.get("created_at")
            })

    return results


def get_nurse_active_template(
    nurse_id: uuid.UUID
) -> Optional[Dict[str, Any]]:
    """
    Get an active template for a nurse (returns first active template found).

    Multiple templates can be active simultaneously. This returns the first one,
    used as a fallback in the default template resolution chain.

    Args:
        nurse_id: Nurse UUID

    Returns:
        Active template record or None if no template is active
    """
    # Use explicit columns to exclude large internal fields (assembled_full_prompt, assembled_schema_json)
    active = (
        supabase.table("nurse_templates")
        .select(f"*, templates({TEMPLATE_LIST_COLUMNS}, consultation_types(type_code, type_name))")
        .eq("nurse_id", str(nurse_id))
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    if not active.data:
        return None

    record = active.data[0]
    template = record.get("templates", {})
    consultation_type = template.get("consultation_types", {}) or {}

    # Return explicit fields only (no **template spread to avoid leaking internal fields)
    return {
        "id": template.get("id"),
        "template_code": record.get("template_code") or template.get("template_code"),
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
        "access_type": "shared",
        "is_active": True
    }


def revoke_nurse_template_access(
    nurse_id: uuid.UUID,
    template_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Revoke a nurse's access to a template.

    This DELETES the junction table entry (hard delete).

    Args:
        nurse_id: Nurse UUID
        template_id: Template UUID

    Returns:
        Dict with revoked status
    """
    # Check if entry exists
    existing = (
        supabase.table("nurse_templates")
        .select("id, is_active")
        .eq("nurse_id", str(nurse_id))
        .eq("template_id", str(template_id))
        .limit(1)
        .execute()
    )

    if not existing.data:
        logger.warning(f"[REVOKE] No nurse_templates entry found for nurse {nurse_id} and template {template_id}")
        return {"revoked": False, "reason": "no_entry_found"}

    entry_id = existing.data[0]["id"]
    was_active = existing.data[0].get("is_active", False)

    # Delete from nurse_templates
    delete_result = (
        supabase.table("nurse_templates")
        .delete()
        .eq("id", entry_id)
        .execute()
    )

    deleted_count = len(delete_result.data) if delete_result.data else 0

    if deleted_count > 0:
        logger.info(f"[REVOKE] Successfully deleted nurse_templates entry for nurse {nurse_id} and template {template_id}")
        return {"revoked": True, "deleted_count": deleted_count, "was_active": was_active}
    else:
        # Verify the entry is gone
        verify = (
            supabase.table("nurse_templates")
            .select("id")
            .eq("id", entry_id)
            .limit(1)
            .execute()
        )
        if not verify.data:
            logger.info(f"[REVOKE] Verified entry is deleted despite empty response")
            return {"revoked": True, "deleted_count": 1, "was_active": was_active, "verified": True}
        else:
            logger.error(f"[REVOKE] Entry still exists after DELETE!")
            return {"revoked": False, "reason": "delete_failed"}


def validate_nurse_template_access(
    nurse_id: str,
    template_id: str
) -> bool:
    """
    Check if a nurse has access to a specific template.

    Args:
        nurse_id: Nurse UUID as string
        template_id: Template UUID as string

    Returns:
        True if nurse has an active link to this template, False otherwise
    """
    response = supabase.table("nurse_templates")\
        .select("id, is_active")\
        .eq("nurse_id", nurse_id)\
        .eq("template_id", template_id)\
        .limit(1)\
        .execute()

    if not response.data:
        return False

    return response.data[0].get("is_active", False)


def get_nurse_default_template(
    nurse_id: uuid.UUID,
    doctor_id: Optional[uuid.UUID] = None
) -> Optional[Dict[str, Any]]:
    """
    Get the default template for a nurse through a fallback chain.

    Priority order:
    1. Nurse's default_template_id (from nurses table)
    2. Linked doctor's default (via nurse_doctors -> doctors.default_template_id)
    3. Hospital default (via nurses.hospital_id -> hospitals.default_template_id)
    4. OP_CORE fallback (universal template)

    Args:
        nurse_id: Nurse UUID
        doctor_id: Optional doctor UUID (passed for linked doctor fallback)

    Returns:
        Dict with id and template_code if default found, None otherwise
    """
    # Fetch nurse record
    nurse_result = (
        supabase.table("nurses")
        .select("id, default_template_id, hospital_id")
        .eq("id", str(nurse_id))
        .limit(1)
        .execute()
    )

    if not nurse_result.data:
        return None

    nurse = nurse_result.data[0]

    # Priority 1: Nurse's own default_template_id
    default_template_id = nurse.get("default_template_id")
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
            logger.info(f"[NURSE_DEFAULT] Resolved via nurse default_template_id for nurse {nurse_id}")
            return {
                "id": template_result.data[0]["id"],
                "template_code": template_result.data[0]["template_code"]
            }

    # Priority 2: Linked doctor's default
    try:
        from services.nurse_service import get_nurse_doctors
        nurse_doctors = get_nurse_doctors(str(nurse_id))
        for assoc in nurse_doctors:
            doctor_info = assoc.get("doctors", {})
            if not doctor_info:
                continue
            linked_doctor_id = doctor_info.get("id")
            if linked_doctor_id:
                doctor_record = (
                    supabase.table("doctors")
                    .select("default_template_id")
                    .eq("id", linked_doctor_id)
                    .limit(1)
                    .execute()
                )
                if doctor_record.data:
                    doc_default_id = doctor_record.data[0].get("default_template_id")
                    if doc_default_id:
                        template_result = (
                            supabase.table("templates")
                            .select("id, template_code")
                            .eq("id", doc_default_id)
                            .eq("is_active", True)
                            .limit(1)
                            .execute()
                        )
                        if template_result.data:
                            logger.info(f"[NURSE_DEFAULT] Resolved via linked doctor {linked_doctor_id} default for nurse {nurse_id}")
                            return {
                                "id": template_result.data[0]["id"],
                                "template_code": template_result.data[0]["template_code"]
                            }
    except Exception as e:
        logger.warning(f"[NURSE_DEFAULT] Error checking linked doctors: {e}")

    # Priority 3: Hospital default
    hospital_id = nurse.get("hospital_id")
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
                    logger.info(f"[NURSE_DEFAULT] Resolved via hospital default for nurse {nurse_id}")
                    return {
                        "id": template_result.data[0]["id"],
                        "template_code": template_result.data[0]["template_code"]
                    }

    # Priority 4: OP_CORE fallback (universal template)
    try:
        op_core_result = (
            supabase.table("templates")
            .select("id, template_code")
            .eq("template_code", "OP_CORE")
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if op_core_result.data:
            logger.info(f"[NURSE_DEFAULT] Resolved via OP_CORE fallback for nurse {nurse_id}")
            return {
                "id": op_core_result.data[0]["id"],
                "template_code": op_core_result.data[0]["template_code"]
            }
    except Exception as e:
        logger.warning(f"[NURSE_DEFAULT] Error fetching OP_CORE fallback: {e}")

    return None


def get_template_nurse_shares(template_id: uuid.UUID) -> Dict[str, Any]:
    """
    Get all nurses who have access to a template.

    Args:
        template_id: Template UUID

    Returns:
        Dictionary with nurses list and count
    """
    nurse_shares = (
        supabase.table("nurse_templates")
        .select("id, nurse_id, template_code, is_active, activated_at, nurses(id, full_name, email, qualification, hospital_id)")
        .eq("template_id", str(template_id))
        .execute()
    )

    nurses = []
    for share in (nurse_shares.data or []):
        nurse_info = share.get("nurses", {})
        nurses.append({
            "id": share["id"],
            "nurse_id": share["nurse_id"],
            "nurse_name": nurse_info.get("full_name", "Unknown"),
            "email": nurse_info.get("email"),
            "qualification": nurse_info.get("qualification"),
            "hospital_id": nurse_info.get("hospital_id"),
            "template_code": share.get("template_code"),
            "is_active": share.get("is_active", False),
            "activated_at": share.get("activated_at")
        })

    return {
        "nurses": nurses,
        "total_shares": len(nurses)
    }

"""
Assistant Templates Service - Template sharing and activation management for assistants

Manages the assistant_templates junction table for template access control and activation.
Unlike counsellors, assistants cannot own templates - they can only use templates shared with them.
"""

import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from services.supabase_service import supabase
import logging

logger = logging.getLogger(__name__)

# Columns to fetch for template listings (excludes large internal fields)
TEMPLATE_LIST_COLUMNS = "id, template_code, template_name, description, consultation_type_id, is_active, is_default, use_case, specialization, school_id, counsellor_id, estimated_extraction_time_seconds, created_at, updated_at"


def share_template_with_assistant(
    template_id: uuid.UUID,
    template_code: str,
    assistant_id: uuid.UUID,
) -> Dict[str, Any]:
    """
    Share a template with a specific assistant.

    Args:
        template_id: Template UUID to share
        template_code: Template code (denormalized for readability)
        assistant_id: Assistant UUID to share with

    Returns:
        Created or reactivated assistant_templates record

    Raises:
        ValueError: If template not found or assistant not found
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

    # Verify assistant exists
    nurse = (
        supabase.table("assistants")
        .select("id, full_name")
        .eq("id", str(assistant_id))
        .limit(1)
        .execute()
    )

    if not nurse.data:
        raise ValueError(f"Assistant {assistant_id} not found")

    # Check if already shared
    existing = (
        supabase.table("assistant_templates")
        .select("id, is_active")
        .eq("assistant_id", str(assistant_id))
        .eq("template_id", str(template_id))
        .limit(1)
        .execute()
    )

    if existing.data:
        existing_record = existing.data[0]
        if existing_record.get("is_active"):
            logger.info(f"Template {template_id} already shared with assistant {assistant_id}")
            return existing_record

        # Reactivate soft-deleted entry
        result = (
            supabase.table("assistant_templates")
            .update({
                "is_active": True,
                "access_level": "use",
                "activated_at": datetime.now(timezone.utc).isoformat()
            })
            .eq("id", existing_record["id"])
            .execute()
        )
        logger.info(f"Reactivated template {template_id} for assistant {assistant_id}")
        return result.data[0] if result.data else existing_record

    # Create assistant_templates record
    share_data = {
        "assistant_id": str(assistant_id),
        "template_id": str(template_id),
        "template_code": template_code,
        "access_level": "use",
        "is_active": True,
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    result = supabase.table("assistant_templates").insert(share_data).execute()

    logger.info(f"Shared template {template_id} with assistant {assistant_id}")

    return result.data[0] if result.data else {}


def bulk_share_template_with_assistants(
    template_id: uuid.UUID,
    template_code: str,
    assistant_ids: List[uuid.UUID],
) -> Dict[str, Any]:
    """
    Share a template with multiple assistants at once.

    Args:
        template_id: Template UUID to share
        template_code: Template code (denormalized for readability)
        assistant_ids: List of assistant UUIDs to share with

    Returns:
        Summary with success and failed operations
    """
    if not assistant_ids:
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

    assistant_ids_str = [str(n) for n in assistant_ids]

    # Get existing shares for ALL assistants in ONE query
    existing = (
        supabase.table("assistant_templates")
        .select("id, assistant_id, is_active")
        .eq("template_id", str(template_id))
        .in_("assistant_id", assistant_ids_str)
        .execute()
    )

    existing_by_assistant = {e["assistant_id"]: e for e in (existing.data or [])}

    # Separate into: new inserts, reactivate (soft-deleted), already active
    to_insert = []
    to_reactivate = []
    already_active = []

    for assistant_id_str in assistant_ids_str:
        if assistant_id_str in existing_by_assistant:
            existing_record = existing_by_assistant[assistant_id_str]
            if existing_record.get("is_active"):
                already_active.append(assistant_id_str)
            else:
                to_reactivate.append(existing_record["id"])
        else:
            to_insert.append({
                "assistant_id": assistant_id_str,
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
            insert_result = supabase.table("assistant_templates").insert(to_insert).execute()
            for record in (insert_result.data or []):
                success.append({"assistant_id": record["assistant_id"], "action": "created"})
        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            for item in to_insert:
                failed.append({"assistant_id": item["assistant_id"], "error": str(e)})

    # Batch REACTIVATE soft-deleted shares
    if to_reactivate:
        try:
            update_result = (
                supabase.table("assistant_templates")
                .update({
                    "access_level": "use",
                    "is_active": True,
                    "activated_at": datetime.now(timezone.utc).isoformat()
                })
                .in_("id", to_reactivate)
                .execute()
            )
            for record in (update_result.data or []):
                success.append({"assistant_id": record["assistant_id"], "action": "reactivated"})
        except Exception as e:
            logger.error(f"Batch reactivate failed: {e}")
            for record_id in to_reactivate:
                failed.append({"assistant_id": "unknown", "error": str(e)})

    # Count already active as success
    for assistant_id_str in already_active:
        success.append({"assistant_id": assistant_id_str, "action": "already_shared"})

    logger.info(f"Bulk shared template {template_id}: {len(success)} success, {len(failed)} failed")

    return {
        "template_id": str(template_id),
        "total_requested": len(assistant_ids),
        "successful": len(success),
        "failed": len(failed),
        "success": success,
        "failed_records": failed
    }


def activate_template_for_assistant(
    assistant_id: uuid.UUID,
    template_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Activate (link) a template for a specific assistant.

    Sets is_active=True on the assistant_templates entry. Multiple templates
    can be active simultaneously.

    Args:
        assistant_id: Assistant UUID
        template_id: Template UUID to activate

    Returns:
        Updated activation record

    Raises:
        ValueError: If template not accessible by assistant
    """
    # Verify assistant has access to this template
    access = (
        supabase.table("assistant_templates")
        .select("id")
        .eq("assistant_id", str(assistant_id))
        .eq("template_id", str(template_id))
        .limit(1)
        .execute()
    )

    if not access.data:
        raise ValueError(f"Assistant {assistant_id} does not have access to template {template_id}")

    # Activate the selected template (no "deactivate all others" — multiple can be active)
    result = (
        supabase.table("assistant_templates")
        .update({
            "is_active": True,
            "activated_at": datetime.now(timezone.utc).isoformat()
        })
        .eq("assistant_id", str(assistant_id))
        .eq("template_id", str(template_id))
        .execute()
    )

    logger.info(f"Activated template {template_id} for assistant {assistant_id}")

    return result.data[0] if result.data else {}


def deactivate_template_for_assistant(
    assistant_id: uuid.UUID,
    template_id: uuid.UUID
) -> None:
    """
    Soft-delete a template for a specific assistant (set is_active=False).

    Args:
        assistant_id: Assistant UUID
        template_id: Template UUID to remove
    """
    supabase.table("assistant_templates")\
        .update({"is_active": False})\
        .eq("assistant_id", str(assistant_id))\
        .eq("template_id", str(template_id))\
        .execute()

    logger.info(f"Deactivated template {template_id} for assistant {assistant_id}")


def get_assistant_accessible_templates(
    assistant_id: uuid.UUID
) -> List[Dict[str, Any]]:
    """
    Get all templates accessible to an assistant.

    Args:
        assistant_id: Assistant UUID

    Returns:
        List of accessible templates with access info
    """
    # Get shared templates via assistant_templates junction
    # Use explicit columns to exclude large internal fields (assembled_full_prompt, assembled_schema_json)
    shared = supabase.table("assistant_templates")\
        .select(f"*, templates({TEMPLATE_LIST_COLUMNS}, consultation_types(type_code, type_name))")\
        .eq("assistant_id", str(assistant_id))\
        .execute()

    results = []

    for record in (shared.data or []):
        template = record.get("templates", {})
        # Only return entries where both assistant_templates.is_active AND templates.is_active are True
        if template and template.get("is_active", True) and record.get("is_active", False):
            consultation_type = template.get("consultation_types", {}) or {}
            results.append({
                "id": record.get("id"),  # assistant_templates junction ID
                "assistant_id": record.get("assistant_id"),
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


def get_assistant_active_template(
    assistant_id: uuid.UUID
) -> Optional[Dict[str, Any]]:
    """
    Get an active template for an assistant (returns first active template found).

    Multiple templates can be active simultaneously. This returns the first one,
    used as a fallback in the default template resolution chain.

    Args:
        assistant_id: Assistant UUID

    Returns:
        Active template record or None if no template is active
    """
    # Use explicit columns to exclude large internal fields (assembled_full_prompt, assembled_schema_json)
    active = (
        supabase.table("assistant_templates")
        .select(f"*, templates({TEMPLATE_LIST_COLUMNS}, consultation_types(type_code, type_name))")
        .eq("assistant_id", str(assistant_id))
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
        "school_id": template.get("school_id"),
        "counsellor_id": template.get("counsellor_id"),
        "estimated_extraction_time_seconds": template.get("estimated_extraction_time_seconds"),
        "access_type": "shared",
        "is_active": True
    }


def revoke_assistant_template_access(
    assistant_id: uuid.UUID,
    template_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Revoke an assistant's access to a template.

    This DELETES the junction table entry (hard delete).

    Args:
        assistant_id: Assistant UUID
        template_id: Template UUID

    Returns:
        Dict with revoked status
    """
    # Check if entry exists
    existing = (
        supabase.table("assistant_templates")
        .select("id, is_active")
        .eq("assistant_id", str(assistant_id))
        .eq("template_id", str(template_id))
        .limit(1)
        .execute()
    )

    if not existing.data:
        logger.warning(f"[REVOKE] No assistant_templates entry found for assistant {assistant_id} and template {template_id}")
        return {"revoked": False, "reason": "no_entry_found"}

    entry_id = existing.data[0]["id"]
    was_active = existing.data[0].get("is_active", False)

    # Delete from assistant_templates
    delete_result = (
        supabase.table("assistant_templates")
        .delete()
        .eq("id", entry_id)
        .execute()
    )

    deleted_count = len(delete_result.data) if delete_result.data else 0

    if deleted_count > 0:
        logger.info(f"[REVOKE] Successfully deleted assistant_templates entry for assistant {assistant_id} and template {template_id}")
        return {"revoked": True, "deleted_count": deleted_count, "was_active": was_active}
    else:
        # Verify the entry is gone
        verify = (
            supabase.table("assistant_templates")
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


def validate_assistant_template_access(
    assistant_id: str,
    template_id: str
) -> bool:
    """
    Check if an assistant has access to a specific template.

    Args:
        assistant_id: Assistant UUID as string
        template_id: Template UUID as string

    Returns:
        True if assistant has an active link to this template, False otherwise
    """
    response = supabase.table("assistant_templates")\
        .select("id, is_active")\
        .eq("assistant_id", assistant_id)\
        .eq("template_id", template_id)\
        .limit(1)\
        .execute()

    if not response.data:
        return False

    return response.data[0].get("is_active", False)


def get_assistant_default_template(
    assistant_id: uuid.UUID,
    counsellor_id: Optional[uuid.UUID] = None
) -> Optional[Dict[str, Any]]:
    """
    Get the default template for an assistant through a fallback chain.

    Priority order:
    1. Assistant's default_template_id (from assistants table)
    2. Linked counsellor's default (via assistant_counsellors -> counsellors.default_template_id)
    3. School default (via assistants.school_id -> schools.default_template_id)
    4. OP_CORE fallback (universal template)

    Args:
        assistant_id: Assistant UUID
        counsellor_id: Optional counsellor UUID (passed for linked counsellor fallback)

    Returns:
        Dict with id and template_code if default found, None otherwise
    """
    # Fetch assistant record
    assistant_result = (
        supabase.table("assistants")
        .select("id, default_template_id, school_id")
        .eq("id", str(assistant_id))
        .limit(1)
        .execute()
    )

    if not assistant_result.data:
        return None

    nurse = assistant_result.data[0]

    # Priority 1: Assistant's own default_template_id
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
            logger.info(f"[NURSE_DEFAULT] Resolved via assistant default_template_id for assistant {assistant_id}")
            return {
                "id": template_result.data[0]["id"],
                "template_code": template_result.data[0]["template_code"]
            }

    # Priority 2: Linked counsellor's default
    try:
        from services.assistant_service import get_assistant_counsellors
        assistant_counsellors = get_assistant_counsellors(str(assistant_id))
        for assoc in assistant_counsellors:
            counsellor_info = assoc.get("counsellors", {})
            if not counsellor_info:
                continue
            linked_counsellor_id = counsellor_info.get("id")
            if linked_counsellor_id:
                counsellor_record = (
                    supabase.table("counsellors")
                    .select("default_template_id")
                    .eq("id", linked_counsellor_id)
                    .limit(1)
                    .execute()
                )
                if counsellor_record.data:
                    doc_default_id = counsellor_record.data[0].get("default_template_id")
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
                            logger.info(f"[NURSE_DEFAULT] Resolved via linked counsellor {linked_counsellor_id} default for assistant {assistant_id}")
                            return {
                                "id": template_result.data[0]["id"],
                                "template_code": template_result.data[0]["template_code"]
                            }
    except Exception as e:
        logger.warning(f"[NURSE_DEFAULT] Error checking linked counsellors: {e}")

    # Priority 3: School default
    school_id = nurse.get("school_id")
    if school_id:
        school_result = (
            supabase.table("schools")
            .select("default_template_id")
            .eq("id", school_id)
            .limit(1)
            .execute()
        )
        if school_result.data:
            school_default_id = school_result.data[0].get("default_template_id")
            if school_default_id:
                template_result = (
                    supabase.table("templates")
                    .select("id, template_code")
                    .eq("id", school_default_id)
                    .eq("is_active", True)
                    .limit(1)
                    .execute()
                )
                if template_result.data:
                    logger.info(f"[NURSE_DEFAULT] Resolved via school default for assistant {assistant_id}")
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
            logger.info(f"[NURSE_DEFAULT] Resolved via OP_CORE fallback for assistant {assistant_id}")
            return {
                "id": op_core_result.data[0]["id"],
                "template_code": op_core_result.data[0]["template_code"]
            }
    except Exception as e:
        logger.warning(f"[NURSE_DEFAULT] Error fetching OP_CORE fallback: {e}")

    return None


def get_template_assistant_shares(template_id: uuid.UUID) -> Dict[str, Any]:
    """
    Get all assistants who have access to a template.

    Args:
        template_id: Template UUID

    Returns:
        Dictionary with assistants list and count
    """
    assistant_shares = (
        supabase.table("assistant_templates")
        .select("id, assistant_id, template_code, is_active, activated_at, assistants(id, full_name, email, qualification, school_id)")
        .eq("template_id", str(template_id))
        .execute()
    )

    nurses = []
    for share in (assistant_shares.data or []):
        assistant_info = share.get("assistants", {})
        nurses.append({
            "id": share["id"],
            "assistant_id": share["assistant_id"],
            "assistant_name": assistant_info.get("full_name", "Unknown"),
            "email": assistant_info.get("email"),
            "qualification": assistant_info.get("qualification"),
            "school_id": assistant_info.get("school_id"),
            "template_code": share.get("template_code"),
            "is_active": share.get("is_active", False),
            "activated_at": share.get("activated_at")
        })

    return {
        "assistants": nurses,
        "total_shares": len(nurses)
    }

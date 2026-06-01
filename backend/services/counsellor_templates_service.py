"""
Counsellor Templates Service - Template sharing and activation management
Manages the counsellor_templates junction table for template access control and activation.
"""

import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from services.supabase_service import supabase
import logging

logger = logging.getLogger(__name__)

# Columns to fetch for template listings (excludes large internal fields)
TEMPLATE_LIST_COLUMNS = "id, template_code, template_name, description, consultation_type_id, is_active, is_default, use_case, specialization, school_id, counsellor_id, estimated_extraction_time_seconds, created_at, updated_at"


def assign_template_ownership(
    template_id: uuid.UUID,
    new_owner_id: uuid.UUID,
) -> Dict[str, Any]:
    """
    Assign ownership of a global template to a specific counsellor.

    This converts a global template (counsellor_id=NULL) to a counsellor-owned template,
    and creates a counsellor_templates entry for the new owner.

    Args:
        template_id: Template UUID to assign ownership
        new_owner_id: Counsellor UUID to become the new owner

    Returns:
        Dict with template_updated and owner_share_created flags

    Raises:
        ValueError: If template not found, not global, or inactive
    """
    # Verify template exists and is global (counsellor_id = NULL)
    template_response = (
        supabase.table("templates")
        .select("id, counsellor_id, template_name, is_active")
        .eq("id", str(template_id))
        .limit(1)
        .execute()
    )

    if not template_response.data:
        raise ValueError(f"Template {template_id} not found")

    template = template_response.data[0]

    if not template.get("is_active", True):
        raise ValueError(f"Cannot assign ownership of inactive template {template_id}")

    if template.get("counsellor_id") is not None:
        raise ValueError(f"Template {template_id} already has an owner. Cannot reassign ownership.")

    # Verify new owner exists
    counsellor_response = (
        supabase.table("counsellors")
        .select("id, full_name")
        .eq("id", str(new_owner_id))
        .limit(1)
        .execute()
    )

    if not counsellor_response.data:
        raise ValueError(f"Counsellor {new_owner_id} not found")

    counsellor_name = counsellor_response.data[0].get("full_name", "Unknown")

    # Update template's counsellor_id
    update_response = (
        supabase.table("templates")
        .update({"counsellor_id": str(new_owner_id), "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", str(template_id))
        .execute()
    )

    logger.info(f"[ASSIGN_OWNERSHIP] Template {template_id} assigned to counsellor {new_owner_id} ({counsellor_name})")

    # Create counsellor_templates entry for the owner
    owner_share = {
        "counsellor_id": str(new_owner_id),
        "template_id": str(template_id),
        "access_level": "use",
        "is_active": True,
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    # Check if entry already exists
    existing = (
        supabase.table("counsellor_templates")
        .select("id")
        .eq("counsellor_id", str(new_owner_id))
        .eq("template_id", str(template_id))
        .limit(1)
        .execute()
    )

    if existing.data:
        # Update existing entry
        supabase.table("counsellor_templates").update({
            "access_level": "use",
            "is_active": True,
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("counsellor_id", str(new_owner_id)).eq("template_id", str(template_id)).execute()
        logger.info(f"[ASSIGN_OWNERSHIP] Updated existing counsellor_templates entry for owner")
    else:
        # Create new entry
        supabase.table("counsellor_templates").insert(owner_share).execute()
        logger.info(f"[ASSIGN_OWNERSHIP] Created counsellor_templates entry for owner")

    return {
        "template_updated": True,
        "owner_share_created": True,
        "new_owner_id": str(new_owner_id),
        "new_owner_name": counsellor_name
    }


def share_template_with_counsellor(
    template_id: uuid.UUID,
    counsellor_id: uuid.UUID,
    shared_by_admin_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Share a template with a specific counsellor.

    Args:
        template_id: Template UUID to share
        counsellor_id: Counsellor UUID to share with
        shared_by_admin_id: Admin UUID who is sharing (optional, for audit trail)

    Returns:
        Created counsellor_templates record

    Raises:
        ValueError: If template not found or already shared
        ValueError: If trying to share counsellor-owned template with another counsellor
    """
    # Verify template exists and is active
    template = (
        supabase.table("templates")
        .select("id, counsellor_id, template_name, is_active, consultation_type_id")
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

    template_owner = template.data[0].get("counsellor_id")

    # Prevent sharing if counsellor already owns this template
    if template_owner == str(counsellor_id):
        raise ValueError(f"Counsellor {counsellor_id} already owns this template")

    # Check if already shared
    existing = (
        supabase.table("counsellor_templates")
        .select("id, is_active")
        .eq("counsellor_id", str(counsellor_id))
        .eq("template_id", str(template_id))
        .limit(1)
        .execute()
    )

    if existing.data:
        existing_record = existing.data[0]
        if existing_record.get("is_active"):
            # Already shared and active - no-op
            logger.info(f"Template {template_id} already shared with counsellor {counsellor_id} and active - no changes")
            return existing_record

        # Reactivate soft-deleted share
        result = (
            supabase.table("counsellor_templates")
            .update({
                "access_level": "use",
                "is_active": True,
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            .eq("id", existing_record["id"])
            .execute()
        )
        logger.info(f"Reactivated template {template_id} share for counsellor {counsellor_id}")
        return result.data[0] if result.data else existing_record

    # Create counsellor_templates record
    share_data = {
        "counsellor_id": str(counsellor_id),
        "template_id": str(template_id),
        "access_level": "use",
        "is_active": True,
        "activated_at": datetime.now(timezone.utc).isoformat(),
    }

    result = supabase.table("counsellor_templates").insert(share_data).execute()

    logger.info(f"Shared template {template_id} with counsellor {counsellor_id} (access_level: use, is_active: True)")

    return result.data[0] if result.data else {}


def bulk_share_template(
    template_id: uuid.UUID,
    counsellor_ids: List[uuid.UUID],
) -> Dict[str, Any]:
    """
    Share a template with multiple counsellors at once.

    OPTIMIZED: Uses batch queries instead of N+1 individual queries.
    - Before: 4-6 queries per counsellor (400-600 queries for 100 counsellors)
    - After: 4-5 queries total regardless of counsellor count

    Args:
        template_id: Template UUID to share
        counsellor_ids: List of counsellor UUIDs to share with

    Returns:
        Summary with success and failed operations
    """
    if not counsellor_ids:
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
        .select("id, is_active, consultation_type_id, counsellor_id")
        .eq("id", str(template_id))
        .limit(1)
        .execute()
    )

    if not template.data or not template.data[0].get("is_active"):
        raise ValueError(f"Template {template_id} not found or inactive")

    template_data = template.data[0]
    template_owner = template_data.get("counsellor_id")
    consultation_type_id = template_data.get("consultation_type_id")

    # Filter out counsellors who own the template
    counsellor_ids_str = [str(d) for d in counsellor_ids if str(d) != template_owner]

    if not counsellor_ids_str:
        return {
            "template_id": str(template_id),
            "total_requested": len(counsellor_ids),
            "successful": 0,
            "failed": len(counsellor_ids),
            "success": [],
            "failed_records": [{"counsellor_id": str(d), "error": "Counsellor owns this template"} for d in counsellor_ids]
        }

    # 2. Get existing shares for ALL counsellors in ONE query
    existing = (
        supabase.table("counsellor_templates")
        .select("id, counsellor_id, is_active")
        .eq("template_id", str(template_id))
        .in_("counsellor_id", counsellor_ids_str)
        .execute()
    )

    existing_by_counsellor = {e["counsellor_id"]: e for e in (existing.data or [])}

    # 3. Separate into: new inserts, reactivations needed, already active
    to_insert = []
    to_reactivate = []
    already_active = []

    for counsellor_id_str in counsellor_ids_str:
        if counsellor_id_str in existing_by_counsellor:
            existing_record = existing_by_counsellor[counsellor_id_str]
            if existing_record.get("is_active"):
                already_active.append(counsellor_id_str)
            else:
                # Soft-deleted, reactivate
                to_reactivate.append(existing_record["id"])
        else:
            to_insert.append({
                "counsellor_id": counsellor_id_str,
                "template_id": str(template_id),
                "access_level": "use",
                "is_active": True,
            })

    success = []
    failed = []

    # 4. Batch INSERT new shares (1 query)
    if to_insert:
        try:
            insert_result = supabase.table("counsellor_templates").insert(to_insert).execute()
            for record in (insert_result.data or []):
                success.append({"counsellor_id": record["counsellor_id"], "action": "created"})
        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            for item in to_insert:
                failed.append({"counsellor_id": item["counsellor_id"], "error": str(e)})

    # 5. Batch reactivate soft-deleted shares (1 query)
    if to_reactivate:
        try:
            update_result = (
                supabase.table("counsellor_templates")
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
                success.append({"counsellor_id": record["counsellor_id"], "action": "reactivated"})
        except Exception as e:
            logger.error(f"Batch reactivate failed: {e}")
            for record_id in to_reactivate:
                failed.append({"counsellor_id": "unknown", "error": str(e)})

    # 6. Count already active as success
    for counsellor_id_str in already_active:
        success.append({"counsellor_id": counsellor_id_str, "action": "already_shared"})

    logger.info(f"Bulk shared template {template_id}: {len(success)} success, {len(failed)} failed")

    return {
        "template_id": str(template_id),
        "total_requested": len(counsellor_ids),
        "successful": len(success),
        "failed": len(failed),
        "success": success,
        "failed_records": failed
    }


def share_template_with_school(
    template_id: uuid.UUID,
    school_id: uuid.UUID,
) -> Dict[str, Any]:
    """
    Share a template with all counsellors in a specific school.

    Args:
        template_id: Template UUID to share
        school_id: School UUID

    Returns:
        Summary with success and failed operations
    """
    # Get all counsellors in this school
    doctors = (
        supabase.table("counsellors")
        .select("id")
        .eq("school_id", str(school_id))
        .eq("is_active", True)
        .execute()
    )

    if not doctors.data:
        return {
            "template_id": str(template_id),
            "school_id": str(school_id),
            "total_counsellors": 0,
            "message": "No active counsellors found in this school"
        }

    counsellor_ids = [uuid.UUID(d["id"]) for d in doctors.data]

    return bulk_share_template(template_id, counsellor_ids)


def share_template_with_specialization(
    template_id: uuid.UUID,
    specialization: str,
) -> Dict[str, Any]:
    """
    Share a template with all counsellors of a specific specialization.

    Args:
        template_id: Template UUID to share
        specialization: Specialization name (e.g., "Cardiology", "Psychiatry")

    Returns:
        Summary with success and failed operations
    """
    # Get all counsellors with this specialization
    doctors = (
        supabase.table("counsellors")
        .select("id")
        .eq("specialization", specialization)
        .eq("is_active", True)
        .execute()
    )

    if not doctors.data:
        return {
            "template_id": str(template_id),
            "specialization": specialization,
            "total_counsellors": 0,
            "message": f"No active counsellors found with specialization '{specialization}'"
        }

    counsellor_ids = [uuid.UUID(d["id"]) for d in doctors.data]

    return bulk_share_template(template_id, counsellor_ids)


def activate_template_for_counsellor(
    counsellor_id: uuid.UUID,
    template_id: uuid.UUID,
    consultation_type_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Ensure a counsellor_templates entry exists with is_active=True for this counsellor+template.

    This simply links the template to the counsellor. No "one active per consultation type"
    constraint — counsellors can have multiple active templates.

    Args:
        counsellor_id: Counsellor UUID
        template_id: Template UUID to link
        consultation_type_id: Optional - not used for gating, kept for API compatibility

    Returns:
        Updated or created counsellor_templates record

    Raises:
        ValueError: If template not found or soft-deleted
    """
    # Verify template exists and is active
    template = (
        supabase.table("templates")
        .select("id, counsellor_id, is_active")
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
        supabase.table("counsellor_templates")
        .select("id, is_active")
        .eq("counsellor_id", str(counsellor_id))
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
            supabase.table("counsellor_templates")
            .update({
                "is_active": True,
                "access_level": "use",
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            .eq("counsellor_id", str(counsellor_id))
            .eq("template_id", str(template_id))
            .execute()
        )
    else:
        # Create new record
        result = supabase.table("counsellor_templates").insert({
            "counsellor_id": str(counsellor_id),
            "template_id": str(template_id),
            "access_level": "use",
            "is_active": True,
            "activated_at": datetime.now(timezone.utc).isoformat()
        }).execute()

    logger.info(f"Activated template {template_id} for counsellor {counsellor_id}")

    return result.data[0] if result.data else {}


def deactivate_template_for_counsellor(
    counsellor_id: uuid.UUID,
    template_id: uuid.UUID
) -> None:
    """
    Soft-delete a counsellor-template link by setting is_active=False.

    This removes the template from the counsellor's visible list without
    deleting the junction row.

    Args:
        counsellor_id: Counsellor UUID
        template_id: Template UUID to remove
    """
    supabase.table("counsellor_templates")\
        .update({
            "is_active": False,
            "updated_at": datetime.now(timezone.utc).isoformat()
        })\
        .eq("counsellor_id", str(counsellor_id))\
        .eq("template_id", str(template_id))\
        .execute()

    logger.info(f"Soft-deleted template {template_id} for counsellor {counsellor_id}")


def get_counsellor_accessible_templates(
    counsellor_id: uuid.UUID,
    consultation_type_id: Optional[uuid.UUID] = None,
    include_common: bool = True
) -> List[Dict[str, Any]]:
    """
    Get all templates accessible to a counsellor.

    Returns templates that:
    1. Counsellor owns (templates.counsellor_id = counsellor_id)
    2. Are shared with counsellor (counsellor_templates junction table)
    3. Are common (templates.counsellor_id = NULL) if include_common=True

    Args:
        counsellor_id: Counsellor UUID
        consultation_type_id: Optional - filter by consultation type
        include_common: Include common templates (counsellor_id=NULL)

    Returns:
        List of accessible templates with access info
    """
    # Use explicit columns to exclude large internal fields (assembled_full_prompt, assembled_schema_json)

    # Get owned templates
    owned_query = supabase.table("templates")\
        .select(f"{TEMPLATE_LIST_COLUMNS}, consultation_types(type_code, type_name)")\
        .eq("counsellor_id", str(counsellor_id))\
        .eq("is_active", True)

    if consultation_type_id:
        owned_query = owned_query.eq("consultation_type_id", str(consultation_type_id))

    owned_templates = owned_query.execute()

    # Get shared templates
    shared_query = supabase.table("counsellor_templates")\
        .select(f"*, templates({TEMPLATE_LIST_COLUMNS}, consultation_types(type_code, type_name))")\
        .eq("counsellor_id", str(counsellor_id))

    shared_templates = shared_query.execute()

    # Get common templates
    common_templates_data = []
    if include_common:
        common_query = supabase.table("templates")\
            .select(f"{TEMPLATE_LIST_COLUMNS}, consultation_types(type_code, type_name)")\
            .is_("counsellor_id", "null")\
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
            "school_id": template.get("school_id"),
            "counsellor_id": template.get("counsellor_id"),
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
        # Only include active (not soft-deleted) counsellor_templates entries
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


def get_counsellor_default_template(counsellor_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get the default template for a counsellor.

    Priority order:
    1. Counsellor's own default_template_id (if set)
    2. Counsellor's school's default_template_id (if counsellor belongs to school and school has default)
    3. None

    Args:
        counsellor_id: Counsellor UUID

    Returns:
        Dict with id and template_code if default found, None otherwise
    """
    # Get counsellor with their default_template_id and school_id
    counsellor_result = (
        supabase.table("counsellors")
        .select("id, default_template_id, school_id")
        .eq("id", str(counsellor_id))
        .limit(1)
        .execute()
    )

    if not counsellor_result.data:
        return None

    doctor = counsellor_result.data[0]
    default_template_id = doctor.get("default_template_id")

    # Priority 1: Counsellor's own default
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

    # Priority 2: School's default
    school_id = doctor.get("school_id")
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
                    return {
                        "id": template_result.data[0]["id"],
                        "template_code": template_result.data[0]["template_code"]
                    }

    return None


def revoke_template_access(
    counsellor_id: uuid.UUID,
    template_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Revoke a counsellor's access to a shared template.

    This ONLY removes junction table entries (explicitly granted access).
    Cannot revoke access to templates owned by the counsellor.

    Args:
        counsellor_id: Counsellor UUID
        template_id: Template UUID

    Returns:
        Dict with revoked status and count

    Raises:
        ValueError: If trying to revoke access to owned template
    """
    # Verify template exists and check ownership
    template = (
        supabase.table("templates")
        .select("counsellor_id")
        .eq("id", str(template_id))
        .limit(1)
        .execute()
    )

    if not template.data:
        raise ValueError(f"Template {template_id} not found")

    template_owner = template.data[0].get("counsellor_id")

    # Prevent revoking access to templates the counsellor owns
    if template_owner == str(counsellor_id):
        raise ValueError("Cannot revoke access to owned template. Delete the template instead.")

    # Check if entry exists before attempting delete
    existing = (
        supabase.table("counsellor_templates")
        .select("id, is_active")
        .eq("counsellor_id", str(counsellor_id))
        .eq("template_id", str(template_id))
        .limit(1)
        .execute()
    )

    if not existing.data:
        logger.warning(f"[REVOKE] No counsellor_templates entry found for counsellor {counsellor_id} and template {template_id}")
        return {"revoked": False, "reason": "no_entry_found"}

    entry_id = existing.data[0]["id"]
    was_active = existing.data[0].get("is_active", False)

    # Delete from counsellor_templates junction table
    # This removes explicitly granted access (via share)
    # Common templates can have junction entries when explicitly shared
    delete_result = (
        supabase.table("counsellor_templates")
        .delete()
        .eq("id", entry_id)
        .execute()
    )

    # Verify deletion succeeded
    deleted_count = len(delete_result.data) if delete_result.data else 0

    if deleted_count > 0:
        logger.info(f"[REVOKE] Successfully deleted counsellor_templates entry (id={entry_id}) for counsellor {counsellor_id} and template {template_id}. was_active={was_active}")
        return {"revoked": True, "deleted_count": deleted_count, "was_active": was_active}
    else:
        logger.error(f"[REVOKE] DELETE returned no data for entry (id={entry_id}). counsellor={counsellor_id}, template={template_id}")
        # As a fallback, verify the entry is truly gone
        verify = (
            supabase.table("counsellor_templates")
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
    counsellor_id: uuid.UUID,
    consultation_type_id: uuid.UUID
) -> bool:
    """
    Check if a counsellor has visibility to a specific consultation type.

    Visibility rules:
    - If ALL visibility arrays (visible_to_schools, visible_to_counsellors, visible_to_specializations) are NULL/empty → Everyone can see
    - If ANY array has values → Only those specific entities can see it

    Args:
        counsellor_id: Counsellor UUID
        consultation_type_id: Consultation type UUID

    Returns:
        True if counsellor has visibility, False otherwise
    """
    # Get consultation type with visibility settings
    consult_type = (
        supabase.table("consultation_types")
        .select("visible_to_schools, visible_to_counsellors, visible_to_specializations")
        .eq("id", str(consultation_type_id))
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    if not consult_type.data:
        return False

    visibility = consult_type.data[0]
    visible_schools = visibility.get("visible_to_schools") or []
    visible_counsellors = visibility.get("visible_to_counsellors") or []
    visible_specializations = visibility.get("visible_to_specializations") or []

    # If all visibility arrays are empty → Everyone can see
    if not visible_schools and not visible_counsellors and not visible_specializations:
        return True

    # Get counsellor details
    doctor = (
        supabase.table("counsellors")
        .select("id, school_id, specialization")
        .eq("id", str(counsellor_id))
        .limit(1)
        .execute()
    )

    if not doctor.data:
        return False

    counsellor_data = doctor.data[0]
    counsellor_school = counsellor_data.get("school_id")
    counsellor_specialization = counsellor_data.get("specialization")

    # Check visibility conditions (OR logic - any match grants access)
    if visible_counsellors and str(counsellor_id) in visible_counsellors:
        return True

    if visible_schools and counsellor_school and str(counsellor_school) in visible_schools:
        return True

    if visible_specializations and counsellor_specialization in visible_specializations:
        return True

    return False


def activate_from_consultation_type(
    counsellor_id: uuid.UUID,
    consultation_type_id: uuid.UUID,
    template_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create and activate a new counsellor-owned template from a consultation type.

    Workflow:
    1. Check counsellor has visibility to this consultation type
    2. Create new template owned by counsellor
    3. Clone all segments from consultation_type_segments junction
    4. Auto-activate for counsellor

    Args:
        counsellor_id: Counsellor UUID
        consultation_type_id: Consultation type UUID to clone from
        template_name: Optional custom template name

    Returns:
        Created template record with activation status

    Raises:
        PermissionError: If counsellor doesn't have visibility to consultation type
        ValueError: If consultation type not found
    """
    # Check visibility
    if not check_consultation_type_visibility(counsellor_id, consultation_type_id):
        raise PermissionError(
            f"Counsellor {counsellor_id} does not have visibility to consultation type {consultation_type_id}. "
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

    # Get counsellor details for naming
    doctor = (
        supabase.table("counsellors")
        .select("full_name")
        .eq("id", str(counsellor_id))
        .limit(1)
        .execute()
    )

    if not doctor.data:
        raise ValueError(f"Counsellor {counsellor_id} not found")

    counsellor_name_part = doctor.data[0]["full_name"].replace(" ", "").upper()[:8]

    # Generate unique template_code (max 50 chars)
    # Include microseconds to prevent collisions when called rapidly
    timestamp = datetime.now(timezone.utc).strftime("%m%d%H%M%S%f")
    template_code = f"{type_code}_{counsellor_name_part}_{timestamp}"

    # Create template
    template_data = {
        "template_code": template_code,
        "template_name": template_name or f"{type_name} - {counsellor_name_part}",
        "consultation_type_id": str(consultation_type_id),
        "counsellor_id": str(counsellor_id),  # Counsellor owns this template
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

    # Auto-activate for counsellor
    activate_template_for_counsellor(counsellor_id, uuid.UUID(template_id), consultation_type_id)

    logger.info(f"Created and activated template {template_id} from consultation type {type_code} for counsellor {counsellor_id}")

    return {
        **new_template.data[0],
        "segment_count": len(consult_segments.data) if consult_segments.data else 0,
        "is_activated": True
    }


def clone_template(
    counsellor_id: uuid.UUID,
    source_template_id: uuid.UUID,
    template_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Clone a template to create a counsellor-owned copy.

    Counsellor can clone:
    - Shared templates
    - Global templates (counsellor_id = NULL)
    - Their own templates (for versioning)

    Workflow:
    1. Verify counsellor has access to source template
    2. Create new template owned by counsellor
    3. Copy all segments from template_segments junction
    4. Auto-activate for counsellor

    Args:
        counsellor_id: Counsellor UUID
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

    source_owner = source.get("counsellor_id")
    consultation_type_id = source.get("consultation_type_id")
    consultation_type = source.get("consultation_types", {})
    type_code = consultation_type.get("type_code", "TEMPLATE")

    # Check access
    can_clone = False

    if source_owner == str(counsellor_id):
        # Counsellor owns the source
        can_clone = True
    elif source_owner is None:
        # Common/global template
        can_clone = True
    else:
        # Check if shared
        shared = (
            supabase.table("counsellor_templates")
            .select("id")
            .eq("counsellor_id", str(counsellor_id))
            .eq("template_id", str(source_template_id))
            .limit(1)
            .execute()
        )
        can_clone = bool(shared.data)

    if not can_clone:
        raise ValueError(
            f"Counsellor {counsellor_id} does not have access to template {source_template_id}. "
            "Cannot clone inaccessible template."
        )

    # Get counsellor details for naming
    doctor = (
        supabase.table("counsellors")
        .select("full_name")
        .eq("id", str(counsellor_id))
        .limit(1)
        .execute()
    )

    if not doctor.data:
        raise ValueError(f"Counsellor {counsellor_id} not found")

    counsellor_name_part = doctor.data[0]["full_name"].replace(" ", "").upper()[:8]

    # Generate unique template_code (max 50 chars)
    # Include microseconds to prevent collisions when called rapidly
    timestamp = datetime.now(timezone.utc).strftime("%m%d%H%M%S%f")
    template_code = f"CLN_{type_code}_{counsellor_name_part}_{timestamp}"

    # Create cloned template
    template_data = {
        "template_code": template_code,
        "template_name": template_name or f"Clone of {source.get('template_name', 'Template')}",
        "consultation_type_id": consultation_type_id,
        "counsellor_id": str(counsellor_id),  # Counsellor owns the clone
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

    # Auto-activate for counsellor
    if consultation_type_id:
        activate_template_for_counsellor(counsellor_id, uuid.UUID(template_id), uuid.UUID(consultation_type_id))

    logger.info(f"Cloned template {source_template_id} → {template_id} for counsellor {counsellor_id}")

    return {
        **new_template.data[0],
        "source_template_id": str(source_template_id),
        "segment_count": len(source_segments.data) if source_segments.data else 0,
        "is_activated": True if consultation_type_id else False
    }


def get_counsellor_dashboard_data(
    counsellor_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Get comprehensive dashboard data for a counsellor.

    Returns:
    1. Visible consultation types (based on visibility settings)
    2. Accessible templates (owned, shared, global) grouped by access type

    Args:
        counsellor_id: Counsellor UUID

    Returns:
        Dictionary with consultation_types and templates lists
    """
    # Get all active consultation types
    all_consult_types = (
        supabase.table("consultation_types")
        .select("id, type_code, type_name, description, icon_name, color_code, visible_to_schools, visible_to_counsellors, visible_to_specializations")
        .eq("is_active", True)
        .execute()
    )

    # Get counsellor details
    doctor = (
        supabase.table("counsellors")
        .select("id, school_id, specialization")
        .eq("id", str(counsellor_id))
        .limit(1)
        .execute()
    )

    if not doctor.data:
        raise ValueError(f"Counsellor {counsellor_id} not found")

    counsellor_data = doctor.data[0]
    counsellor_school = counsellor_data.get("school_id")
    counsellor_specialization = counsellor_data.get("specialization")

    # Filter visible consultation types
    visible_consultation_types = []

    for ct in (all_consult_types.data or []):
        visible_schools = ct.get("visible_to_schools") or []
        visible_counsellors = ct.get("visible_to_counsellors") or []
        visible_specializations = ct.get("visible_to_specializations") or []

        # If all empty → everyone can see
        if not visible_schools and not visible_counsellors and not visible_specializations:
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

        if visible_counsellors and str(counsellor_id) in visible_counsellors:
            has_visibility = True
        elif visible_schools and counsellor_school and str(counsellor_school) in visible_schools:
            has_visibility = True
        elif visible_specializations and counsellor_specialization in visible_specializations:
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
    accessible_templates = get_counsellor_accessible_templates(counsellor_id, include_common=True)

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

    Returns individual counsellor shares, and ONLY schools/specializations where
    ALL counsellors have the template.

    Args:
        template_id: Template UUID

    Returns:
        Dictionary with:
        - counsellors: List of individual counsellor shares with is_active status
        - school_ids: List of school IDs where ALL counsellors have this template
        - specializations: List of specializations where ALL counsellors have this template

    Note:
        is_active=true means the share is active, is_active=false means soft-deleted.
    """
    # Get ALL individual counsellor shares from counsellor_templates junction table
    counsellor_shares = (
        supabase.table("counsellor_templates")
        .select("id, counsellor_id, is_active, activated_at, counsellors(id, full_name, email, specialization, school_id)")
        .eq("template_id", str(template_id))
        .execute()
    )

    # Format counsellor shares
    doctors = []
    counsellors_with_template_by_school = {}  # school_id -> set of counsellor_ids with template
    counsellors_with_template_by_spec = {}  # specialization -> set of counsellor_ids with template

    for share in counsellor_shares.data:
        counsellor_info = share.get("counsellors", {})
        counsellor_id = share["counsellor_id"]
        school_id = counsellor_info.get("school_id")
        specialization = counsellor_info.get("specialization")

        doctors.append({
            "id": share["id"],
            "counsellor_id": counsellor_id,
            "counsellor_name": counsellor_info.get("full_name", "Unknown"),
            "email": counsellor_info.get("email"),
            "specialization": specialization,
            "school_id": school_id,
            "is_active": share.get("is_active", False),
            "activated_at": share.get("activated_at")
        })

        # Track which counsellors have template by school and specialization
        if school_id:
            if school_id not in counsellors_with_template_by_school:
                counsellors_with_template_by_school[school_id] = set()
            counsellors_with_template_by_school[school_id].add(counsellor_id)

        if specialization:
            if specialization not in counsellors_with_template_by_spec:
                counsellors_with_template_by_spec[specialization] = set()
            counsellors_with_template_by_spec[specialization].add(counsellor_id)

    # OPTIMIZED: Get ALL counsellor counts in 1 query instead of N queries per school/specialization
    # Before: 1 query per school + 1 query per specialization (N+1 problem)
    # After: 1 query total for all active counsellors grouped by school and specialization

    fully_shared_schools = []
    fully_shared_specializations = []

    if counsellors_with_template_by_school or counsellors_with_template_by_spec:
        # Get all active counsellors with their school_id and specialization (1 query)
        all_active_counsellors = (
            supabase.table("counsellors")
            .select("id, school_id, specialization")
            .eq("is_active", True)
            .execute()
        )

        # Build counts in-memory (O(n) where n = total counsellors)
        school_counsellor_counts = {}  # school_id -> total active counsellors
        spec_counsellor_counts = {}  # specialization -> total active counsellors

        for doc in (all_active_counsellors.data or []):
            h_id = doc.get("school_id")
            spec = doc.get("specialization")

            if h_id:
                school_counsellor_counts[h_id] = school_counsellor_counts.get(h_id, 0) + 1
            if spec:
                spec_counsellor_counts[spec] = spec_counsellor_counts.get(spec, 0) + 1

        # Compare with template shares (in-memory, no more queries)
        for school_id, counsellors_with_access in counsellors_with_template_by_school.items():
            total_in_school = school_counsellor_counts.get(school_id, 0)
            if total_in_school > 0 and total_in_school == len(counsellors_with_access):
                fully_shared_schools.append(school_id)

        for spec, counsellors_with_access in counsellors_with_template_by_spec.items():
            total_with_spec = spec_counsellor_counts.get(spec, 0)
            if total_with_spec > 0 and total_with_spec == len(counsellors_with_access):
                fully_shared_specializations.append(spec)

    return {
        "counsellors": doctors,
        "school_ids": fully_shared_schools,
        "specializations": fully_shared_specializations,
        "total_shares": len(doctors)
    }

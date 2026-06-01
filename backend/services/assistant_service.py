"""
Assistant Management Service

Provides CRUD operations for assistant management without Supabase auth integration.
Uses random UUID generation for assistant IDs.
"""

import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from .supabase_service import supabase


def get_all_assistants(
    is_active: Optional[bool] = True,
    school_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all assistants, optionally filtered by active status and school.

    Args:
        is_active: Filter by active status (default: True)
        school_id: Filter by school UUID (optional)

    Returns:
        List of assistant records
    """
    query = supabase.table("assistants").select("*, schools(id, school_name)")

    if is_active is not None:
        query = query.eq("is_active", is_active)

    if school_id:
        query = query.eq("school_id", school_id)

    query = query.order("full_name")
    response = query.execute()

    return response.data if response.data else []


def search_assistants(query: str) -> List[Dict[str, Any]]:
    """
    Search assistants by name or email.

    Args:
        query: Search term (case-insensitive)

    Returns:
        List of matching assistant records
    """
    response = supabase.table("assistants")\
        .select("*, schools(id, school_name)")\
        .or_(f"full_name.ilike.%{query}%,email.ilike.%{query}%")\
        .eq("is_active", True)\
        .order("full_name")\
        .execute()

    return response.data if response.data else []


def get_assistant(assistant_id: str) -> Optional[Dict[str, Any]]:
    """
    Get assistant by ID.

    Args:
        assistant_id: Assistant UUID

    Returns:
        Assistant record or None if not found
    """
    response = supabase.table("assistants")\
        .select("*, schools(id, school_name)")\
        .eq("id", assistant_id)\
        .execute()

    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


def create_assistant(
    email: str,
    full_name: str,
    qualification: Optional[str] = None,
    school_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create new assistant with random UUID (no auth integration).

    Args:
        email: Assistant's email address
        full_name: Assistant's full name
        qualification: Nursing qualification (RN, LPN, BSN, etc.)
        school_id: School UUID (optional)

    Returns:
        Created assistant record

    Raises:
        ValueError: If email already exists
    """
    # Check if email already exists
    existing = supabase.table("assistants")\
        .select("id")\
        .eq("email", email)\
        .execute()

    if existing.data and len(existing.data) > 0:
        raise ValueError(f"Assistant with email '{email}' already exists")

    # Generate random UUID
    assistant_id = str(uuid.uuid4())

    assistant_data = {
        "id": assistant_id,
        "email": email,
        "full_name": full_name,
        "qualification": qualification,
        "school_id": school_id,
        "is_active": True,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

    response = supabase.table("assistants").insert(assistant_data).execute()

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to create assistant")

    return response.data[0]


def update_assistant(
    assistant_id: str,
    email: Optional[str] = None,
    full_name: Optional[str] = None,
    qualification: Optional[str] = None,
    school_id: Optional[str] = None,
    is_active: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Update assistant information.

    Args:
        assistant_id: Assistant UUID
        email: New email (optional)
        full_name: New full name (optional)
        qualification: New qualification (optional)
        school_id: New school ID (optional)
        is_active: New active status (optional)

    Returns:
        Updated assistant record

    Raises:
        ValueError: If assistant not found or email conflict
    """
    # Check if assistant exists
    existing = get_assistant(assistant_id)
    if not existing:
        raise ValueError(f"Assistant with ID '{assistant_id}' not found")

    # Check email uniqueness if updating email
    if email and email != existing["email"]:
        email_check = supabase.table("assistants")\
            .select("id")\
            .eq("email", email)\
            .neq("id", assistant_id)\
            .execute()

        if email_check.data and len(email_check.data) > 0:
            raise ValueError(f"Email '{email}' is already in use by another assistant")

    # Build update data
    update_data = {"updated_at": datetime.utcnow().isoformat()}

    if email is not None:
        update_data["email"] = email
    if full_name is not None:
        update_data["full_name"] = full_name
    if qualification is not None:
        update_data["qualification"] = qualification
    if school_id is not None:
        update_data["school_id"] = school_id
    if is_active is not None:
        update_data["is_active"] = is_active

    response = supabase.table("assistants")\
        .update(update_data)\
        .eq("id", assistant_id)\
        .execute()

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to update assistant")

    return response.data[0]


def deactivate_assistant(assistant_id: str) -> Dict[str, Any]:
    """
    Soft delete assistant by setting is_active to False.

    Args:
        assistant_id: Assistant UUID

    Returns:
        Updated assistant record

    Raises:
        ValueError: If assistant not found
    """
    return update_assistant(assistant_id, is_active=False)


# ============================================================================
# Assistant-Counsellor Association Functions
# ============================================================================

def get_assistant_counsellors(assistant_id: str) -> List[Dict[str, Any]]:
    """
    Get all counsellors associated with an assistant.

    Args:
        assistant_id: Assistant UUID

    Returns:
        List of counsellor records with association info
    """
    response = supabase.table("assistant_counsellors")\
        .select("*, counsellors(id, full_name, email, specialization, school_id)")\
        .eq("assistant_id", assistant_id)\
        .eq("is_active", True)\
        .execute()

    return response.data if response.data else []


def link_assistant_to_counsellor(assistant_id: str, counsellor_id: str) -> Dict[str, Any]:
    """
    Link an assistant to a supervising counsellor.

    Args:
        assistant_id: Assistant UUID
        counsellor_id: Counsellor UUID

    Returns:
        Created/updated association record

    Raises:
        ValueError: If assistant or counsellor not found
    """
    # Verify assistant exists
    nurse = get_assistant(assistant_id)
    if not nurse:
        raise ValueError(f"Assistant with ID '{assistant_id}' not found")

    # Verify counsellor exists
    doctor = supabase.table("counsellors").select("id").eq("id", counsellor_id).execute()
    if not doctor.data:
        raise ValueError(f"Counsellor with ID '{counsellor_id}' not found")

    # Check if association already exists
    existing = supabase.table("assistant_counsellors")\
        .select("id, is_active")\
        .eq("assistant_id", assistant_id)\
        .eq("counsellor_id", counsellor_id)\
        .execute()

    if existing.data and len(existing.data) > 0:
        # Reactivate if inactive
        if not existing.data[0].get("is_active"):
            response = supabase.table("assistant_counsellors")\
                .update({"is_active": True})\
                .eq("id", existing.data[0]["id"])\
                .execute()
            return response.data[0] if response.data else existing.data[0]
        return existing.data[0]

    # Create new association
    association_data = {
        "assistant_id": assistant_id,
        "counsellor_id": counsellor_id,
        "is_active": True,
        "created_at": datetime.utcnow().isoformat()
    }

    response = supabase.table("assistant_counsellors").insert(association_data).execute()

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to link assistant to counsellor")

    return response.data[0]


def unlink_assistant_from_counsellor(assistant_id: str, counsellor_id: str) -> Dict[str, Any]:
    """
    Unlink an assistant from a counsellor (soft delete).

    Args:
        assistant_id: Assistant UUID
        counsellor_id: Counsellor UUID

    Returns:
        Updated association record

    Raises:
        ValueError: If association not found
    """
    # Find existing association
    existing = supabase.table("assistant_counsellors")\
        .select("id")\
        .eq("assistant_id", assistant_id)\
        .eq("counsellor_id", counsellor_id)\
        .execute()

    if not existing.data or len(existing.data) == 0:
        raise ValueError(f"No association found between assistant '{assistant_id}' and counsellor '{counsellor_id}'")

    # Soft delete by setting is_active to False
    response = supabase.table("assistant_counsellors")\
        .update({"is_active": False})\
        .eq("id", existing.data[0]["id"])\
        .execute()

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to unlink assistant from counsellor")

    return response.data[0]


def get_counsellors_for_assistant(assistant_id: str) -> List[Dict[str, Any]]:
    """
    Get list of counsellors that this assistant can work with.

    Args:
        assistant_id: Assistant UUID

    Returns:
        List of counsellor records
    """
    associations = get_assistant_counsellors(assistant_id)
    return [assoc.get("counsellors", {}) for assoc in associations if assoc.get("counsellors")]


def validate_assistant_counsellor_access(assistant_id: str, counsellor_id: str) -> bool:
    """
    Check if an assistant is authorized to work with a specific counsellor.

    Args:
        assistant_id: Assistant UUID
        counsellor_id: Counsellor UUID

    Returns:
        True if assistant can work with this counsellor, False otherwise
    """
    response = supabase.table("assistant_counsellors")\
        .select("id")\
        .eq("assistant_id", assistant_id)\
        .eq("counsellor_id", counsellor_id)\
        .eq("is_active", True)\
        .execute()

    return bool(response.data and len(response.data) > 0)

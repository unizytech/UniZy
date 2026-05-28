"""
Nurse Management Service

Provides CRUD operations for nurse management without Supabase auth integration.
Uses random UUID generation for nurse IDs.
"""

import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from .supabase_service import supabase


def get_all_nurses(
    is_active: Optional[bool] = True,
    hospital_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all nurses, optionally filtered by active status and hospital.

    Args:
        is_active: Filter by active status (default: True)
        hospital_id: Filter by hospital UUID (optional)

    Returns:
        List of nurse records
    """
    query = supabase.table("nurses").select("*, hospitals(id, hospital_name)")

    if is_active is not None:
        query = query.eq("is_active", is_active)

    if hospital_id:
        query = query.eq("hospital_id", hospital_id)

    query = query.order("full_name")
    response = query.execute()

    return response.data if response.data else []


def search_nurses(query: str) -> List[Dict[str, Any]]:
    """
    Search nurses by name or email.

    Args:
        query: Search term (case-insensitive)

    Returns:
        List of matching nurse records
    """
    response = supabase.table("nurses")\
        .select("*, hospitals(id, hospital_name)")\
        .or_(f"full_name.ilike.%{query}%,email.ilike.%{query}%")\
        .eq("is_active", True)\
        .order("full_name")\
        .execute()

    return response.data if response.data else []


def get_nurse(nurse_id: str) -> Optional[Dict[str, Any]]:
    """
    Get nurse by ID.

    Args:
        nurse_id: Nurse UUID

    Returns:
        Nurse record or None if not found
    """
    response = supabase.table("nurses")\
        .select("*, hospitals(id, hospital_name)")\
        .eq("id", nurse_id)\
        .execute()

    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


def create_nurse(
    email: str,
    full_name: str,
    qualification: Optional[str] = None,
    hospital_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create new nurse with random UUID (no auth integration).

    Args:
        email: Nurse's email address
        full_name: Nurse's full name
        qualification: Nursing qualification (RN, LPN, BSN, etc.)
        hospital_id: Hospital UUID (optional)

    Returns:
        Created nurse record

    Raises:
        ValueError: If email already exists
    """
    # Check if email already exists
    existing = supabase.table("nurses")\
        .select("id")\
        .eq("email", email)\
        .execute()

    if existing.data and len(existing.data) > 0:
        raise ValueError(f"Nurse with email '{email}' already exists")

    # Generate random UUID
    nurse_id = str(uuid.uuid4())

    nurse_data = {
        "id": nurse_id,
        "email": email,
        "full_name": full_name,
        "qualification": qualification,
        "hospital_id": hospital_id,
        "is_active": True,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

    response = supabase.table("nurses").insert(nurse_data).execute()

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to create nurse")

    return response.data[0]


def update_nurse(
    nurse_id: str,
    email: Optional[str] = None,
    full_name: Optional[str] = None,
    qualification: Optional[str] = None,
    hospital_id: Optional[str] = None,
    is_active: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Update nurse information.

    Args:
        nurse_id: Nurse UUID
        email: New email (optional)
        full_name: New full name (optional)
        qualification: New qualification (optional)
        hospital_id: New hospital ID (optional)
        is_active: New active status (optional)

    Returns:
        Updated nurse record

    Raises:
        ValueError: If nurse not found or email conflict
    """
    # Check if nurse exists
    existing = get_nurse(nurse_id)
    if not existing:
        raise ValueError(f"Nurse with ID '{nurse_id}' not found")

    # Check email uniqueness if updating email
    if email and email != existing["email"]:
        email_check = supabase.table("nurses")\
            .select("id")\
            .eq("email", email)\
            .neq("id", nurse_id)\
            .execute()

        if email_check.data and len(email_check.data) > 0:
            raise ValueError(f"Email '{email}' is already in use by another nurse")

    # Build update data
    update_data = {"updated_at": datetime.utcnow().isoformat()}

    if email is not None:
        update_data["email"] = email
    if full_name is not None:
        update_data["full_name"] = full_name
    if qualification is not None:
        update_data["qualification"] = qualification
    if hospital_id is not None:
        update_data["hospital_id"] = hospital_id
    if is_active is not None:
        update_data["is_active"] = is_active

    response = supabase.table("nurses")\
        .update(update_data)\
        .eq("id", nurse_id)\
        .execute()

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to update nurse")

    return response.data[0]


def deactivate_nurse(nurse_id: str) -> Dict[str, Any]:
    """
    Soft delete nurse by setting is_active to False.

    Args:
        nurse_id: Nurse UUID

    Returns:
        Updated nurse record

    Raises:
        ValueError: If nurse not found
    """
    return update_nurse(nurse_id, is_active=False)


# ============================================================================
# Nurse-Doctor Association Functions
# ============================================================================

def get_nurse_doctors(nurse_id: str) -> List[Dict[str, Any]]:
    """
    Get all doctors associated with a nurse.

    Args:
        nurse_id: Nurse UUID

    Returns:
        List of doctor records with association info
    """
    response = supabase.table("nurse_doctors")\
        .select("*, doctors(id, full_name, email, specialization, hospital_id)")\
        .eq("nurse_id", nurse_id)\
        .eq("is_active", True)\
        .execute()

    return response.data if response.data else []


def link_nurse_to_doctor(nurse_id: str, doctor_id: str) -> Dict[str, Any]:
    """
    Link a nurse to a supervising doctor.

    Args:
        nurse_id: Nurse UUID
        doctor_id: Doctor UUID

    Returns:
        Created/updated association record

    Raises:
        ValueError: If nurse or doctor not found
    """
    # Verify nurse exists
    nurse = get_nurse(nurse_id)
    if not nurse:
        raise ValueError(f"Nurse with ID '{nurse_id}' not found")

    # Verify doctor exists
    doctor = supabase.table("doctors").select("id").eq("id", doctor_id).execute()
    if not doctor.data:
        raise ValueError(f"Doctor with ID '{doctor_id}' not found")

    # Check if association already exists
    existing = supabase.table("nurse_doctors")\
        .select("id, is_active")\
        .eq("nurse_id", nurse_id)\
        .eq("doctor_id", doctor_id)\
        .execute()

    if existing.data and len(existing.data) > 0:
        # Reactivate if inactive
        if not existing.data[0].get("is_active"):
            response = supabase.table("nurse_doctors")\
                .update({"is_active": True})\
                .eq("id", existing.data[0]["id"])\
                .execute()
            return response.data[0] if response.data else existing.data[0]
        return existing.data[0]

    # Create new association
    association_data = {
        "nurse_id": nurse_id,
        "doctor_id": doctor_id,
        "is_active": True,
        "created_at": datetime.utcnow().isoformat()
    }

    response = supabase.table("nurse_doctors").insert(association_data).execute()

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to link nurse to doctor")

    return response.data[0]


def unlink_nurse_from_doctor(nurse_id: str, doctor_id: str) -> Dict[str, Any]:
    """
    Unlink a nurse from a doctor (soft delete).

    Args:
        nurse_id: Nurse UUID
        doctor_id: Doctor UUID

    Returns:
        Updated association record

    Raises:
        ValueError: If association not found
    """
    # Find existing association
    existing = supabase.table("nurse_doctors")\
        .select("id")\
        .eq("nurse_id", nurse_id)\
        .eq("doctor_id", doctor_id)\
        .execute()

    if not existing.data or len(existing.data) == 0:
        raise ValueError(f"No association found between nurse '{nurse_id}' and doctor '{doctor_id}'")

    # Soft delete by setting is_active to False
    response = supabase.table("nurse_doctors")\
        .update({"is_active": False})\
        .eq("id", existing.data[0]["id"])\
        .execute()

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to unlink nurse from doctor")

    return response.data[0]


def get_doctors_for_nurse(nurse_id: str) -> List[Dict[str, Any]]:
    """
    Get list of doctors that this nurse can work with.

    Args:
        nurse_id: Nurse UUID

    Returns:
        List of doctor records
    """
    associations = get_nurse_doctors(nurse_id)
    return [assoc.get("doctors", {}) for assoc in associations if assoc.get("doctors")]


def validate_nurse_doctor_access(nurse_id: str, doctor_id: str) -> bool:
    """
    Check if a nurse is authorized to work with a specific doctor.

    Args:
        nurse_id: Nurse UUID
        doctor_id: Doctor UUID

    Returns:
        True if nurse can work with this doctor, False otherwise
    """
    response = supabase.table("nurse_doctors")\
        .select("id")\
        .eq("nurse_id", nurse_id)\
        .eq("doctor_id", doctor_id)\
        .eq("is_active", True)\
        .execute()

    return bool(response.data and len(response.data) > 0)

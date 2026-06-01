"""
Counsellor Management Service

Provides CRUD operations for counsellor management without Supabase auth integration.
Uses random UUID generation for counsellor IDs.
"""

import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from .supabase_service import supabase


def get_all_counsellors(is_active: bool = True) -> List[Dict[str, Any]]:
    """
    Get all counsellors, optionally filtered by active status.

    Args:
        is_active: Filter by active status (default: True)

    Returns:
        List of counsellor records
    """
    query = supabase.table("counsellors").select("*")

    if is_active is not None:
        query = query.eq("is_active", is_active)

    query = query.order("full_name")
    response = query.execute()

    return response.data if response.data else []


def search_counsellors(query: str) -> List[Dict[str, Any]]:
    """
    Search counsellors by name or email.

    Args:
        query: Search term (case-insensitive)

    Returns:
        List of matching counsellor records
    """
    response = supabase.table("counsellors")\
        .select("*")\
        .or_(f"full_name.ilike.%{query}%,email.ilike.%{query}%")\
        .eq("is_active", True)\
        .order("full_name")\
        .execute()

    return response.data if response.data else []


def get_counsellor(counsellor_id: str) -> Optional[Dict[str, Any]]:
    """
    Get counsellor by ID.

    Args:
        counsellor_id: Counsellor UUID

    Returns:
        Counsellor record or None if not found
    """
    response = supabase.table("counsellors")\
        .select("*")\
        .eq("id", counsellor_id)\
        .execute()

    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


def create_counsellor(
    email: str,
    full_name: str,
    specialization: Optional[str] = None,
    default_template: Optional[str] = None,
    default_transcription_engine: str = "gemini",
    default_transcription_model: str = "gemini-2.5-flash"
) -> Dict[str, Any]:
    """
    Create new counsellor with random UUID (no auth integration).

    Args:
        email: Counsellor's email address
        full_name: Counsellor's full name
        specialization: Medical specialization (e.g., "Psychiatry", "Cardiology")
        default_template: Default template code
        default_transcription_engine: Default transcription engine
        default_transcription_model: Default transcription model

    Returns:
        Created counsellor record

    Raises:
        ValueError: If email already exists
    """
    # Check if email already exists
    existing = supabase.table("counsellors")\
        .select("id")\
        .eq("email", email)\
        .execute()

    if existing.data and len(existing.data) > 0:
        raise ValueError(f"Counsellor with email '{email}' already exists")

    # Generate random UUID
    counsellor_id = str(uuid.uuid4())

    counsellor_data = {
        "id": counsellor_id,
        "email": email,
        "full_name": full_name,
        "specialization": specialization,
        "auth_user_id": None,  # Skip auth integration per user requirement
        "default_template": default_template,
        "default_transcription_engine": default_transcription_engine,
        "default_transcription_model": default_transcription_model,
        "is_active": True,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

    response = supabase.table("counsellors").insert(counsellor_data).execute()

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to create counsellor")

    return response.data[0]


def update_counsellor(
    counsellor_id: str,
    email: Optional[str] = None,
    full_name: Optional[str] = None,
    specialization: Optional[str] = None,
    default_template: Optional[str] = None,
    default_transcription_engine: Optional[str] = None,
    default_transcription_model: Optional[str] = None,
    is_active: Optional[bool] = None,
    op_consultation_fee: Optional[float] = None,
    ip_primary_consultation_fee: Optional[float] = None,
    ip_secondary_consultation_fee: Optional[float] = None,
    translation_language: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update counsellor information.

    Args:
        counsellor_id: Counsellor UUID
        email: New email (optional)
        full_name: New full name (optional)
        specialization: New specialization (optional)
        default_template: New default template (optional)
        default_transcription_engine: New default engine (optional)
        default_transcription_model: New default model (optional)
        is_active: New active status (optional)

    Returns:
        Updated counsellor record

    Raises:
        ValueError: If counsellor not found or email conflict
    """
    # Check if counsellor exists
    existing = get_counsellor(counsellor_id)
    if not existing:
        raise ValueError(f"Counsellor with ID '{counsellor_id}' not found")

    # Check email uniqueness if updating email
    if email and email != existing["email"]:
        email_check = supabase.table("counsellors")\
            .select("id")\
            .eq("email", email)\
            .neq("id", counsellor_id)\
            .execute()

        if email_check.data and len(email_check.data) > 0:
            raise ValueError(f"Email '{email}' is already in use by another counsellor")

    # Build update data
    update_data = {"updated_at": datetime.utcnow().isoformat()}

    if email is not None:
        update_data["email"] = email
    if full_name is not None:
        update_data["full_name"] = full_name
    if specialization is not None:
        update_data["specialization"] = specialization
    if default_template is not None:
        update_data["default_template"] = default_template
    if default_transcription_engine is not None:
        update_data["default_transcription_engine"] = default_transcription_engine
    if default_transcription_model is not None:
        update_data["default_transcription_model"] = default_transcription_model
    if is_active is not None:
        update_data["is_active"] = is_active
    if op_consultation_fee is not None:
        update_data["op_consultation_fee"] = op_consultation_fee
    if ip_primary_consultation_fee is not None:
        update_data["ip_primary_consultation_fee"] = ip_primary_consultation_fee
    if ip_secondary_consultation_fee is not None:
        update_data["ip_secondary_consultation_fee"] = ip_secondary_consultation_fee
    if translation_language is not None:
        # Allow empty string to clear the setting
        update_data["translation_language"] = translation_language if translation_language else None

    response = supabase.table("counsellors")\
        .update(update_data)\
        .eq("id", counsellor_id)\
        .execute()

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to update counsellor")

    return response.data[0]


def deactivate_counsellor(counsellor_id: str) -> Dict[str, Any]:
    """
    Soft delete counsellor by setting is_active to False.

    Args:
        counsellor_id: Counsellor UUID

    Returns:
        Updated counsellor record

    Raises:
        ValueError: If counsellor not found
    """
    return update_counsellor(counsellor_id, is_active=False)


def get_counsellor_all_configurations(counsellor_id: str) -> Dict[str, Any]:
    """
    Get all segment configurations for a counsellor across all consultation types.

    Args:
        counsellor_id: Counsellor UUID

    Returns:
        Dictionary with global and consultation-specific configurations:
        {
            "doctor": {...},
            "global_config": [...],  # consultation_type_id = NULL
            "consultation_configs": {
                "OP": [...],
                "DISCHARGE": [...],
                "RESPIRATORY": [...]
            }
        }
    """
    # Get counsellor info
    doctor = get_counsellor(counsellor_id)
    if not doctor:
        raise ValueError(f"Counsellor with ID '{counsellor_id}' not found")

    # Get all configurations for this counsellor
    response = supabase.table("doctor_segment_configurations")\
        .select("*, segment_definitions(*), consultation_types(type_code, type_name)")\
        .eq("counsellor_id", counsellor_id)\
        .execute()

    configs = response.data if response.data else []

    # Separate global vs consultation-specific
    global_config = []
    consultation_configs = {}

    for config in configs:
        if config.get("consultation_type_id") is None:
            # Global configuration (applies across all types)
            global_config.append(config)
        else:
            # Consultation-specific configuration
            consultation_type = config.get("consultation_types")
            if consultation_type:
                type_code = consultation_type["type_code"]
                if type_code not in consultation_configs:
                    consultation_configs[type_code] = []
                consultation_configs[type_code].append(config)

    return {
        "doctor": doctor,
        "global_config": global_config,
        "consultation_configs": consultation_configs
    }

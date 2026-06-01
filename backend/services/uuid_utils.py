"""
Counsellor ID UUID Normalization Utilities

Provides functions to convert string counsellor IDs to valid UUIDs for database operations.
Supports multiple strategies:
1. Valid UUID strings → Parse and return UUID
2. Invalid strings → Generate deterministic UUID using namespace
3. None → Generate random anonymous UUID
"""

import uuid
from typing import Optional


# Namespace UUID for deterministic counsellor ID generation
# Using DNS namespace as a base for counsellor-related UUIDs
DOCTOR_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, 'ai-live-recorder.counsellor-ids')


def normalize_counsellor_id(counsellor_id: Optional[str]) -> uuid.UUID:
    """
    Convert a string counsellor_id to a valid UUID.

    Strategies:
    1. If counsellor_id is None → Generate random anonymous UUID
    2. If counsellor_id is valid UUID string → Parse and return UUID object
    3. If counsellor_id is invalid UUID → Generate deterministic UUID from string

    Args:
        counsellor_id: Counsellor identifier (string or None)

    Returns:
        uuid.UUID: Valid UUID object

    Examples:
        >>> normalize_counsellor_id(None)
        UUID('random-uuid-here')

        >>> normalize_counsellor_id('550e8400-e29b-41d4-a716-446655440000')
        UUID('550e8400-e29b-41d4-a716-446655440000')

        >>> normalize_counsellor_id('test-counsellor-123')
        UUID('deterministic-uuid-for-test-counsellor-123')
    """
    # Case 1: None → Generate random anonymous UUID
    if counsellor_id is None:
        return uuid.uuid4()

    # Case 2: Valid UUID string → Parse and return
    try:
        return uuid.UUID(counsellor_id)
    except (ValueError, AttributeError):
        pass

    # Case 3: Invalid UUID string → Generate deterministic UUID
    # Using uuid5 ensures same string always generates same UUID
    return uuid.uuid5(DOCTOR_NAMESPACE, counsellor_id)


def is_valid_uuid(value: str) -> bool:
    """
    Check if a string is a valid UUID.

    Args:
        value: String to validate

    Returns:
        bool: True if valid UUID, False otherwise

    Examples:
        >>> is_valid_uuid('550e8400-e29b-41d4-a716-446655440000')
        True

        >>> is_valid_uuid('test-user-123')
        False
    """
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def counsellor_id_to_string(counsellor_uuid: uuid.UUID) -> str:
    """
    Convert UUID back to string representation.

    Args:
        counsellor_uuid: UUID object

    Returns:
        str: UUID as string

    Examples:
        >>> counsellor_id_to_string(UUID('550e8400-e29b-41d4-a716-446655440000'))
        '550e8400-e29b-41d4-a716-446655440000'
    """
    return str(counsellor_uuid)


def generate_anonymous_counsellor_id() -> uuid.UUID:
    """
    Generate a random UUID for anonymous counsellors.

    Returns:
        uuid.UUID: Random UUID

    Examples:
        >>> generate_anonymous_counsellor_id()
        UUID('random-uuid-here')
    """
    return uuid.uuid4()


def generate_deterministic_counsellor_id(identifier: str) -> uuid.UUID:
    """
    Generate a deterministic UUID from a string identifier.
    Same identifier always produces the same UUID.

    Args:
        identifier: String to convert to UUID

    Returns:
        uuid.UUID: Deterministic UUID

    Examples:
        >>> generate_deterministic_counsellor_id('user@example.com')
        UUID('deterministic-uuid-for-user@example.com')

        >>> generate_deterministic_counsellor_id('user@example.com')
        UUID('same-deterministic-uuid')  # Always same result
    """
    return uuid.uuid5(DOCTOR_NAMESPACE, identifier)


# Convenience function for common use case
def ensure_uuid(value: Optional[str | uuid.UUID]) -> uuid.UUID:
    """
    Ensure the value is a UUID, converting if necessary.

    Args:
        value: String, UUID, or None

    Returns:
        uuid.UUID: Valid UUID object

    Examples:
        >>> ensure_uuid(None)
        UUID('random-uuid')

        >>> ensure_uuid('test-user')
        UUID('deterministic-uuid')

        >>> ensure_uuid(UUID('existing-uuid'))
        UUID('existing-uuid')
    """
    if isinstance(value, uuid.UUID):
        return value

    if isinstance(value, str):
        return normalize_counsellor_id(value)

    # None or other types
    return normalize_counsellor_id(None)

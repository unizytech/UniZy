"""
Dependencies package for FastAPI backend.

Contains dependency injection functions for authentication, authorization, and common operations.
"""

from dependencies.auth import (
    get_current_client,
    get_optional_client,
    require_scope,
    require_hospital_access,
    require_doctor_access,
    require_admin,
)

__all__ = [
    "get_current_client",
    "get_optional_client",
    "require_scope",
    "require_hospital_access",
    "require_doctor_access",
    "require_admin",
]

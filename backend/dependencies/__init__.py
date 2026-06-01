"""
Dependencies package for FastAPI backend.

Contains dependency injection functions for authentication, authorization, and common operations.
"""

from dependencies.auth import (
    get_current_client,
    get_optional_client,
    require_scope,
    require_school_access,
    require_counsellor_access,
    require_admin,
)

__all__ = [
    "get_current_client",
    "get_optional_client",
    "require_scope",
    "require_school_access",
    "require_counsellor_access",
    "require_admin",
]

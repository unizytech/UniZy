"""
Middleware package for FastAPI backend.

Contains authentication, rate limiting, and audit logging middleware.
"""

from middleware.auth_middleware import AuthMiddleware

__all__ = ["AuthMiddleware"]

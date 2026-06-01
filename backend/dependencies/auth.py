"""
Authentication Dependencies for FastAPI

Provides dependency injection functions for:
- Getting the current authenticated client
- Requiring specific scopes
- Requiring school/counsellor access
- Admin-only endpoints

Usage in routers:
    from dependencies.auth import get_current_client, require_scope

    @router.get("/extractions")
    async def list_extractions(
        client: ClientContext = Depends(get_current_client)
    ):
        # client is guaranteed to be authenticated
        pass

    @router.post("/extractions")
    async def create_extraction(
        client: ClientContext = Depends(require_scope("write:extractions"))
    ):
        # client has "write:extractions" scope
        pass
"""

from typing import Optional, Callable
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Query

from models.auth_models import ClientContext
from services.auth_service import (
    validate_school_access,
    validate_counsellor_access,
    validate_counsellor_exists,
    ensure_student_exists,
    validate_ehr_counsellor_access,
    validate_ehr_student_access,
    validate_ehr_extraction_access,
    validate_ehr_submission_access,
    validate_ehr_session_access,
    validate_ehr_correlation_access,
)


# ============================================================================
# Core Dependencies
# ============================================================================

def get_current_client(request: Request) -> ClientContext:
    """
    Get the authenticated client from request state.

    This is the base dependency for all authenticated endpoints.
    Returns the ClientContext attached by AuthMiddleware.

    Raises:
        HTTPException 401: If not authenticated
    """
    if not hasattr(request.state, "client") or request.state.client is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return request.state.client


def get_optional_client(request: Request) -> Optional[ClientContext]:
    """
    Get the client from request state, or None if not authenticated.

    Use this for endpoints that work both with and without auth.
    """
    if hasattr(request.state, "client"):
        return request.state.client
    return None


# ============================================================================
# Scope-Based Authorization
# ============================================================================

def require_scope(scope: str) -> Callable[[ClientContext], ClientContext]:
    """
    Dependency factory that requires a specific scope.

    Usage:
        @router.get("/resource")
        async def get_resource(client: ClientContext = Depends(require_scope("read:resource"))):
            pass

    Args:
        scope: The required scope (e.g., "read:extractions", "write:students")

    Returns:
        Dependency function that validates the scope
    """
    def check_scope(client: ClientContext = Depends(get_current_client)) -> ClientContext:
        if not client.has_scope(scope):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: missing required scope '{scope}'",
            )
        return client

    return check_scope


def require_any_scope(*scopes: str) -> Callable[[ClientContext], ClientContext]:
    """
    Dependency factory that requires any one of the specified scopes.

    Usage:
        @router.get("/resource")
        async def get_resource(
            client: ClientContext = Depends(require_any_scope("read:resource", "admin:all"))
        ):
            pass
    """
    def check_scopes(client: ClientContext = Depends(get_current_client)) -> ClientContext:
        for scope in scopes:
            if client.has_scope(scope):
                return client

        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: requires one of scopes {list(scopes)}",
        )

    return check_scopes


def require_all_scopes(*scopes: str) -> Callable[[ClientContext], ClientContext]:
    """
    Dependency factory that requires all specified scopes.

    Usage:
        @router.delete("/resource/{id}")
        async def delete_resource(
            client: ClientContext = Depends(require_all_scopes("write:resource", "admin:delete"))
        ):
            pass
    """
    def check_scopes(client: ClientContext = Depends(get_current_client)) -> ClientContext:
        missing = [s for s in scopes if not client.has_scope(s)]
        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: missing scopes {missing}",
            )
        return client

    return check_scopes


# ============================================================================
# Resource Access Authorization
# ============================================================================

def require_school_access(
    school_id: UUID = Query(..., description="School ID to access"),
    client: ClientContext = Depends(get_current_client),
) -> ClientContext:
    """
    Dependency that validates school access.

    Use this when an endpoint accesses school-specific data.
    Mobile/Web apps with school_id=NULL have global access.
    EHR clients can only access their assigned school.

    Usage:
        @router.get("/school/{school_id}/data")
        async def get_school_data(
            school_id: UUID,
            client: ClientContext = Depends(require_school_access)
        ):
            pass
    """
    if not client.can_access_school(school_id):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: client restricted to school {client.school_id}",
        )
    return client


def require_counsellor_access(
    counsellor_id: UUID = Query(..., description="Counsellor ID to access"),
    client: ClientContext = Depends(get_current_client),
) -> ClientContext:
    """
    Dependency that validates counsellor access.

    Use this when an endpoint accesses counsellor-specific data.

    Usage:
        @router.get("/counsellor/{counsellor_id}/extractions")
        async def get_counsellor_extractions(
            counsellor_id: UUID,
            client: ClientContext = Depends(require_counsellor_access)
        ):
            pass
    """
    if not client.can_access_counsellor(counsellor_id):
        raise HTTPException(
            status_code=403,
            detail="Access denied: client does not have access to this counsellor's data",
        )
    return client


class CounsellorAccessChecker:
    """
    Callable class for checking counsellor access from path parameters.

    Usage:
        @router.get("/counsellors/{counsellor_id}/students")
        async def get_students(
            counsellor_id: UUID,
            client: ClientContext = Depends(CounsellorAccessChecker())
        ):
            pass
    """

    async def __call__(
        self,
        request: Request,
        counsellor_id: Optional[UUID] = None,
        client: ClientContext = Depends(get_current_client),
    ) -> ClientContext:
        # Try to get counsellor_id from path if not provided
        if counsellor_id is None:
            counsellor_id_str = request.path_params.get("counsellor_id")
            if counsellor_id_str:
                try:
                    counsellor_id = UUID(counsellor_id_str)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid counsellor_id format")

        if counsellor_id and not client.can_access_counsellor(counsellor_id):
            raise HTTPException(
                status_code=403,
                detail="Access denied: client does not have access to this counsellor's data",
            )

        return client


class StudentAccessChecker:
    """
    Callable class for checking student access and auto-creation.

    For EHR clients, automatically creates students if they don't exist.

    Usage:
        @router.get("/students/{student_id}/history")
        async def get_history(
            student_id: str,
            client: ClientContext = Depends(StudentAccessChecker())
        ):
            pass
    """

    def __init__(self, auto_create: bool = True):
        """
        Args:
            auto_create: Whether to auto-create students for EHR clients
        """
        self.auto_create = auto_create

    async def __call__(
        self,
        request: Request,
        student_id: Optional[str] = None,
        client: ClientContext = Depends(get_current_client),
    ) -> ClientContext:
        # Try to get student_id from path if not provided
        if student_id is None:
            student_id = request.path_params.get("student_id")

        if student_id and self.auto_create and client.client_type == "ehr":
            # Auto-create student for EHR clients
            await ensure_student_exists(student_id, client)

        return client


# ============================================================================
# EHR School-Scoped Access Checkers
# ============================================================================
# These checkers validate that EHR clients can only access resources
# belonging to counsellors within their assigned school.
# Admin/Mobile/Web clients pass through (admin has full access, mobile/web trusted).

class EHRCounsellorAccessChecker:
    """
    Checker for endpoints with counsellor_id parameter.

    Validates that EHR clients can only access counsellors in their school.
    Admin users have full access. Mobile/Web apps are trusted.

    Usage:
        @router.get("/counsellors/{counsellor_id}/extractions")
        async def get_counsellor_extractions(
            counsellor_id: UUID,
            client: ClientContext = Depends(EHRCounsellorAccessChecker())
        ):
            pass
    """

    async def __call__(
        self,
        request: Request,
        counsellor_id: Optional[UUID] = None,
        client: ClientContext = Depends(get_current_client),
    ) -> ClientContext:
        # Try to get counsellor_id from path if not provided
        if counsellor_id is None:
            counsellor_id_str = request.path_params.get("counsellor_id")
            if counsellor_id_str:
                try:
                    counsellor_id = UUID(counsellor_id_str)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid counsellor_id format")

        if counsellor_id and client.client_type == "ehr":
            if not await validate_ehr_counsellor_access(client, counsellor_id):
                raise HTTPException(
                    status_code=403,
                    detail=f"EHR client restricted to school {client.school_id}"
                )

        return client


class EHRStudentAccessChecker:
    """
    Checker for endpoints with student_id parameter.

    Validates that EHR clients can only access students with records
    from counsellors in their school. Admin users have full access.
    Mobile/Web apps are trusted.

    Usage:
        @router.get("/students/{student_id}/history")
        async def get_student_history(
            student_id: str,
            client: ClientContext = Depends(EHRStudentAccessChecker())
        ):
            pass
    """

    async def __call__(
        self,
        request: Request,
        student_id: Optional[str] = None,
        client: ClientContext = Depends(get_current_client),
    ) -> ClientContext:
        # Try to get student_id from path if not provided
        if student_id is None:
            student_id = request.path_params.get("student_id")

        if student_id and client.client_type == "ehr":
            if not await validate_ehr_student_access(client, student_id):
                raise HTTPException(
                    status_code=403,
                    detail=f"Student not accessible to school {client.school_id}"
                )

        return client


class EHRExtractionAccessChecker:
    """
    Checker for endpoints with extraction_id (no counsellor_id/student_id in path).

    Validates that EHR clients can only access extractions belonging to
    counsellors in their school. Admin users have full access.
    Mobile/Web apps are trusted.

    Usage:
        @router.get("/extractions/{extraction_id}")
        async def get_extraction(
            extraction_id: UUID,
            client: ClientContext = Depends(EHRExtractionAccessChecker())
        ):
            pass
    """

    async def __call__(
        self,
        request: Request,
        extraction_id: Optional[UUID] = None,
        client: ClientContext = Depends(get_current_client),
    ) -> ClientContext:
        # Try to get extraction_id from path if not provided
        if extraction_id is None:
            extraction_id_str = request.path_params.get("extraction_id")
            if extraction_id_str:
                try:
                    extraction_id = UUID(extraction_id_str)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid extraction_id format")

        if extraction_id and client.client_type == "ehr":
            if not await validate_ehr_extraction_access(client, extraction_id):
                raise HTTPException(
                    status_code=403,
                    detail=f"Extraction not accessible to school {client.school_id}"
                )

        return client


class EHRSubmissionAccessChecker:
    """
    Checker for endpoints with submission_id (no counsellor_id/student_id in path).

    Validates that EHR clients can only access submissions belonging to
    counsellors in their school. Admin users have full access.
    Mobile/Web apps are trusted.

    Usage:
        @router.get("/recording/status/{submission_id}")
        async def get_status(
            submission_id: UUID,
            client: ClientContext = Depends(EHRSubmissionAccessChecker())
        ):
            pass
    """

    async def __call__(
        self,
        request: Request,
        submission_id: Optional[UUID] = None,
        client: ClientContext = Depends(get_current_client),
    ) -> ClientContext:
        # Try to get submission_id from path if not provided
        if submission_id is None:
            submission_id_str = request.path_params.get("submission_id")
            if submission_id_str:
                try:
                    submission_id = UUID(submission_id_str)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid submission_id format")

        if submission_id and client.client_type == "ehr":
            if not await validate_ehr_submission_access(client, submission_id):
                raise HTTPException(
                    status_code=403,
                    detail=f"Submission not accessible to school {client.school_id}"
                )

        return client


class EHRSessionAccessChecker:
    """
    Checker for endpoints with session_id (no counsellor_id/student_id in path).

    Validates that EHR clients can only access sessions belonging to
    counsellors in their school. Admin users have full access.
    Mobile/Web apps are trusted.

    Usage:
        @router.get("/extractions/session/{session_id}")
        async def get_by_session(
            session_id: UUID,
            client: ClientContext = Depends(EHRSessionAccessChecker())
        ):
            pass
    """

    async def __call__(
        self,
        request: Request,
        session_id: Optional[UUID] = None,
        client: ClientContext = Depends(get_current_client),
    ) -> ClientContext:
        # Try to get session_id from path if not provided
        if session_id is None:
            session_id_str = request.path_params.get("session_id")
            if session_id_str:
                try:
                    session_id = UUID(session_id_str)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid session_id format")

        if session_id and client.client_type == "ehr":
            if not await validate_ehr_session_access(client, session_id):
                raise HTTPException(
                    status_code=403,
                    detail=f"Session not accessible to school {client.school_id}"
                )

        return client


class EHRCorrelationAccessChecker:
    """
    Checker for endpoints with correlation_id (chunk upload, cancel recording).

    Validates that EHR clients can only access recordings belonging to
    counsellors in their school. Admin users have full access.
    Mobile/Web apps are trusted.

    Note: correlation_id typically comes from request body, not path.
    This checker should be used after parsing the body.

    Usage:
        @router.post("/recording/chunk")
        async def upload_chunk(
            request: ChunkRequest,
            client: ClientContext = Depends(EHRCorrelationAccessChecker())
        ):
            # Additional validation needed for correlation_id from body
            pass
    """

    async def __call__(
        self,
        request: Request,
        correlation_id: Optional[str] = None,
        client: ClientContext = Depends(get_current_client),
    ) -> ClientContext:
        # correlation_id typically comes from request body, not path
        # This checker validates if correlation_id is provided
        if correlation_id and client.client_type == "ehr":
            if not await validate_ehr_correlation_access(client, correlation_id):
                raise HTTPException(
                    status_code=403,
                    detail=f"Recording not accessible to school {client.school_id}"
                )

        return client


# ============================================================================
# Admin-Only Access
# ============================================================================

def require_admin(client: ClientContext = Depends(get_current_client)) -> ClientContext:
    """
    Dependency that requires admin access.

    Only allows requests from:
    - Supabase authenticated admin users
    - Clients with admin:* scopes

    Usage:
        @router.post("/admin/clients")
        async def create_client(
            client: ClientContext = Depends(require_admin)
        ):
            pass
    """
    if client.client_type == "admin":
        return client

    # Check for admin scopes
    admin_scopes = [s for s in client.scopes if s.startswith("admin:")]
    if admin_scopes:
        return client

    raise HTTPException(
        status_code=403,
        detail="Admin access required",
    )


def require_super_admin(client: ClientContext = Depends(get_current_client)) -> ClientContext:
    """
    Dependency that requires super admin access.

    Only allows super_admin role from Supabase auth.
    """
    if client.client_type != "admin" or client.user_role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Super admin access required",
        )
    return client


# ============================================================================
# Composite Dependencies
# ============================================================================

def require_write_access(
    client: ClientContext = Depends(get_current_client),
) -> ClientContext:
    """
    Requires write access (for create/update/delete operations).

    Checks for any write scope.
    """
    write_scopes = [s for s in client.scopes if s.startswith("write:")]
    if not write_scopes and client.client_type != "admin":
        raise HTTPException(
            status_code=403,
            detail="Write access required",
        )
    return client


def require_extraction_access(
    client: ClientContext = Depends(get_current_client),
) -> ClientContext:
    """
    Requires extraction access (read or write).
    """
    if not (
        client.has_scope("read:extractions")
        or client.has_scope("write:extractions")
        or client.client_type == "admin"
    ):
        raise HTTPException(
            status_code=403,
            detail="Extraction access required",
        )
    return client


def require_student_access(
    client: ClientContext = Depends(get_current_client),
) -> ClientContext:
    """
    Requires student data access.
    """
    if not (
        client.has_scope("read:students")
        or client.has_scope("write:students")
        or client.client_type == "admin"
    ):
        raise HTTPException(
            status_code=403,
            detail="Student access required",
        )
    return client


# ============================================================================
# Utility Dependencies
# ============================================================================

async def validate_counsellor_id(
    counsellor_id: UUID = Query(..., description="Counsellor ID"),
    client: ClientContext = Depends(get_current_client),
) -> UUID:
    """
    Validate that a counsellor_id exists and client has access.

    Returns the validated counsellor_id.
    """
    # Check access
    if not client.can_access_counsellor(counsellor_id):
        raise HTTPException(
            status_code=403,
            detail="Access denied to this counsellor's data",
        )

    # Validate exists
    await validate_counsellor_exists(counsellor_id)

    return counsellor_id


async def validate_optional_counsellor_id(
    counsellor_id: Optional[UUID] = Query(None, description="Counsellor ID (optional)"),
    client: ClientContext = Depends(get_current_client),
) -> Optional[UUID]:
    """
    Validate an optional counsellor_id if provided.

    Returns the validated counsellor_id or None.
    """
    if counsellor_id is None:
        return None

    if not client.can_access_counsellor(counsellor_id):
        raise HTTPException(
            status_code=403,
            detail="Access denied to this counsellor's data",
        )

    await validate_counsellor_exists(counsellor_id)

    return counsellor_id

"""
Authentication Dependencies for FastAPI

Provides dependency injection functions for:
- Getting the current authenticated client
- Requiring specific scopes
- Requiring hospital/doctor access
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
    validate_hospital_access,
    validate_doctor_access,
    validate_doctor_exists,
    ensure_patient_exists,
    validate_ehr_doctor_access,
    validate_ehr_patient_access,
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
        scope: The required scope (e.g., "read:extractions", "write:patients")

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

def require_hospital_access(
    hospital_id: UUID = Query(..., description="Hospital ID to access"),
    client: ClientContext = Depends(get_current_client),
) -> ClientContext:
    """
    Dependency that validates hospital access.

    Use this when an endpoint accesses hospital-specific data.
    Mobile/Web apps with hospital_id=NULL have global access.
    EHR clients can only access their assigned hospital.

    Usage:
        @router.get("/hospital/{hospital_id}/data")
        async def get_hospital_data(
            hospital_id: UUID,
            client: ClientContext = Depends(require_hospital_access)
        ):
            pass
    """
    if not client.can_access_hospital(hospital_id):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: client restricted to hospital {client.hospital_id}",
        )
    return client


def require_doctor_access(
    doctor_id: UUID = Query(..., description="Doctor ID to access"),
    client: ClientContext = Depends(get_current_client),
) -> ClientContext:
    """
    Dependency that validates doctor access.

    Use this when an endpoint accesses doctor-specific data.

    Usage:
        @router.get("/doctor/{doctor_id}/extractions")
        async def get_doctor_extractions(
            doctor_id: UUID,
            client: ClientContext = Depends(require_doctor_access)
        ):
            pass
    """
    if not client.can_access_doctor(doctor_id):
        raise HTTPException(
            status_code=403,
            detail="Access denied: client does not have access to this doctor's data",
        )
    return client


class DoctorAccessChecker:
    """
    Callable class for checking doctor access from path parameters.

    Usage:
        @router.get("/doctors/{doctor_id}/patients")
        async def get_patients(
            doctor_id: UUID,
            client: ClientContext = Depends(DoctorAccessChecker())
        ):
            pass
    """

    async def __call__(
        self,
        request: Request,
        doctor_id: Optional[UUID] = None,
        client: ClientContext = Depends(get_current_client),
    ) -> ClientContext:
        # Try to get doctor_id from path if not provided
        if doctor_id is None:
            doctor_id_str = request.path_params.get("doctor_id")
            if doctor_id_str:
                try:
                    doctor_id = UUID(doctor_id_str)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid doctor_id format")

        if doctor_id and not client.can_access_doctor(doctor_id):
            raise HTTPException(
                status_code=403,
                detail="Access denied: client does not have access to this doctor's data",
            )

        return client


class PatientAccessChecker:
    """
    Callable class for checking patient access and auto-creation.

    For EHR clients, automatically creates patients if they don't exist.

    Usage:
        @router.get("/patients/{patient_id}/history")
        async def get_history(
            patient_id: str,
            client: ClientContext = Depends(PatientAccessChecker())
        ):
            pass
    """

    def __init__(self, auto_create: bool = True):
        """
        Args:
            auto_create: Whether to auto-create patients for EHR clients
        """
        self.auto_create = auto_create

    async def __call__(
        self,
        request: Request,
        patient_id: Optional[str] = None,
        client: ClientContext = Depends(get_current_client),
    ) -> ClientContext:
        # Try to get patient_id from path if not provided
        if patient_id is None:
            patient_id = request.path_params.get("patient_id")

        if patient_id and self.auto_create and client.client_type == "ehr":
            # Auto-create patient for EHR clients
            await ensure_patient_exists(patient_id, client)

        return client


# ============================================================================
# EHR Hospital-Scoped Access Checkers
# ============================================================================
# These checkers validate that EHR clients can only access resources
# belonging to doctors within their assigned hospital.
# Admin/Mobile/Web clients pass through (admin has full access, mobile/web trusted).

class EHRDoctorAccessChecker:
    """
    Checker for endpoints with doctor_id parameter.

    Validates that EHR clients can only access doctors in their hospital.
    Admin users have full access. Mobile/Web apps are trusted.

    Usage:
        @router.get("/doctors/{doctor_id}/extractions")
        async def get_doctor_extractions(
            doctor_id: UUID,
            client: ClientContext = Depends(EHRDoctorAccessChecker())
        ):
            pass
    """

    async def __call__(
        self,
        request: Request,
        doctor_id: Optional[UUID] = None,
        client: ClientContext = Depends(get_current_client),
    ) -> ClientContext:
        # Try to get doctor_id from path if not provided
        if doctor_id is None:
            doctor_id_str = request.path_params.get("doctor_id")
            if doctor_id_str:
                try:
                    doctor_id = UUID(doctor_id_str)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid doctor_id format")

        if doctor_id and client.client_type == "ehr":
            if not await validate_ehr_doctor_access(client, doctor_id):
                raise HTTPException(
                    status_code=403,
                    detail=f"EHR client restricted to hospital {client.hospital_id}"
                )

        return client


class EHRPatientAccessChecker:
    """
    Checker for endpoints with patient_id parameter.

    Validates that EHR clients can only access patients with records
    from doctors in their hospital. Admin users have full access.
    Mobile/Web apps are trusted.

    Usage:
        @router.get("/patients/{patient_id}/history")
        async def get_patient_history(
            patient_id: str,
            client: ClientContext = Depends(EHRPatientAccessChecker())
        ):
            pass
    """

    async def __call__(
        self,
        request: Request,
        patient_id: Optional[str] = None,
        client: ClientContext = Depends(get_current_client),
    ) -> ClientContext:
        # Try to get patient_id from path if not provided
        if patient_id is None:
            patient_id = request.path_params.get("patient_id")

        if patient_id and client.client_type == "ehr":
            if not await validate_ehr_patient_access(client, patient_id):
                raise HTTPException(
                    status_code=403,
                    detail=f"Patient not accessible to hospital {client.hospital_id}"
                )

        return client


class EHRExtractionAccessChecker:
    """
    Checker for endpoints with extraction_id (no doctor_id/patient_id in path).

    Validates that EHR clients can only access extractions belonging to
    doctors in their hospital. Admin users have full access.
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
                    detail=f"Extraction not accessible to hospital {client.hospital_id}"
                )

        return client


class EHRSubmissionAccessChecker:
    """
    Checker for endpoints with submission_id (no doctor_id/patient_id in path).

    Validates that EHR clients can only access submissions belonging to
    doctors in their hospital. Admin users have full access.
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
                    detail=f"Submission not accessible to hospital {client.hospital_id}"
                )

        return client


class EHRSessionAccessChecker:
    """
    Checker for endpoints with session_id (no doctor_id/patient_id in path).

    Validates that EHR clients can only access sessions belonging to
    doctors in their hospital. Admin users have full access.
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
                    detail=f"Session not accessible to hospital {client.hospital_id}"
                )

        return client


class EHRCorrelationAccessChecker:
    """
    Checker for endpoints with correlation_id (chunk upload, cancel recording).

    Validates that EHR clients can only access recordings belonging to
    doctors in their hospital. Admin users have full access.
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
                    detail=f"Recording not accessible to hospital {client.hospital_id}"
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


def require_patient_access(
    client: ClientContext = Depends(get_current_client),
) -> ClientContext:
    """
    Requires patient data access.
    """
    if not (
        client.has_scope("read:patients")
        or client.has_scope("write:patients")
        or client.client_type == "admin"
    ):
        raise HTTPException(
            status_code=403,
            detail="Patient access required",
        )
    return client


# ============================================================================
# Utility Dependencies
# ============================================================================

async def validate_doctor_id(
    doctor_id: UUID = Query(..., description="Doctor ID"),
    client: ClientContext = Depends(get_current_client),
) -> UUID:
    """
    Validate that a doctor_id exists and client has access.

    Returns the validated doctor_id.
    """
    # Check access
    if not client.can_access_doctor(doctor_id):
        raise HTTPException(
            status_code=403,
            detail="Access denied to this doctor's data",
        )

    # Validate exists
    await validate_doctor_exists(doctor_id)

    return doctor_id


async def validate_optional_doctor_id(
    doctor_id: Optional[UUID] = Query(None, description="Doctor ID (optional)"),
    client: ClientContext = Depends(get_current_client),
) -> Optional[UUID]:
    """
    Validate an optional doctor_id if provided.

    Returns the validated doctor_id or None.
    """
    if doctor_id is None:
        return None

    if not client.can_access_doctor(doctor_id):
        raise HTTPException(
            status_code=403,
            detail="Access denied to this doctor's data",
        )

    await validate_doctor_exists(doctor_id)

    return doctor_id

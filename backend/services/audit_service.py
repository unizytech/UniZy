"""
HIPAA Audit Service

Provides HIPAA-compliant audit logging for all PHI (Protected Health Information) access.

HIPAA Requirements:
- Log WHO accessed data (client/user identification)
- Log WHAT was accessed (resource type, action)
- Log WHOSE data was accessed (student, counsellor identifiers)
- Log WHEN access occurred (timestamp)
- Log HOW access occurred (endpoint, method, IP)
- Retain logs for minimum 6 years
- Logs cannot be deleted (enforced by database trigger)

Usage:
    from services.audit_service import audit_service

    # Log PHI access
    await audit_service.log_phi_access(
        client_context=client,
        request=request,
        response_status=200,
        response_time_ms=150,
        student_id="P123",
        action="read",
        resource_type="extraction",
    )
"""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import Request

from services.log_sanitizer import truncate_id

from models.auth_models import ClientContext
from services.supabase_service import supabase, retry_on_network_error

logger = logging.getLogger(__name__)


class AuditService:
    """
    HIPAA-compliant audit logging service for PHI access.

    All methods are async to avoid blocking the main request flow.
    Audit logging failures are logged but don't fail the main request.
    """

    # Endpoints that access PHI (Protected Health Information)
    PHI_ENDPOINTS = [
        "/api/v1/students/",
        "/api/v1/extractions/",
        "/api/v1/summary/extract",
        "/api/v1/option1/recording/",
        "/api/v1/merge/",
    ]

    # PHI field categories for detailed logging
    PHI_FIELD_CATEGORIES = {
        "patient_demographics": ["name", "dob", "address", "phone", "email", "student_id"],
        "medical_history": ["diagnosis", "medications", "allergies", "conditions"],
        "treatment": ["prescription", "treatment_plan", "procedures"],
        "clinical_notes": ["chief_complaint", "hpi", "physical_exam", "assessment"],
        "lab_results": ["investigations", "test_results", "imaging"],
    }

    def is_phi_endpoint(self, path: str) -> bool:
        """
        Check if an endpoint accesses PHI data.

        Args:
            path: The request URL path

        Returns:
            True if the endpoint accesses PHI
        """
        return any(path.startswith(ep) for ep in self.PHI_ENDPOINTS)

    def _infer_resource_type(self, path: str) -> str:
        """
        Infer resource type from endpoint path.

        Args:
            path: The request URL path

        Returns:
            Resource type string (e.g., 'patient', 'extraction')
        """
        if "/students/" in path:
            return "patient"
        elif "/extractions/" in path:
            return "extraction"
        elif "/summary/extract" in path:
            return "extraction"
        elif "/recording/" in path:
            return "recording"
        elif "/merge/" in path:
            return "merge"
        elif "/counsellors/" in path:
            return "doctor"
        else:
            return "unknown"

    def _infer_action(self, method: str, path: str) -> str:
        """
        Infer action from HTTP method and path.

        Args:
            method: HTTP method
            path: Request path

        Returns:
            Action string (read, create, update, delete, export)
        """
        method = method.upper()

        # Check for export endpoints
        if "export" in path.lower() or "download" in path.lower():
            return "export"

        # Standard REST action mapping
        if method == "GET":
            return "read"
        elif method == "POST":
            return "create"
        elif method in ("PUT", "PATCH"):
            return "update"
        elif method == "DELETE":
            return "delete"
        else:
            return "access"

    async def log_phi_access(
        self,
        client_context: ClientContext,
        request: Request,
        response_status: int,
        response_time_ms: int,
        student_id: Optional[str] = None,
        counsellor_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: Optional[str] = None,
        phi_fields: Optional[List[str]] = None,
        error_message: Optional[str] = None,
        access_reason: Optional[str] = None,
        data_exported: bool = False,
    ):
        """
        Log PHI access to the audit table.

        This method is fire-and-forget - errors are logged but don't fail the request.

        Args:
            client_context: Authenticated client context
            request: FastAPI request object
            response_status: HTTP response status code
            response_time_ms: Response time in milliseconds
            student_id: Student identifier (external or internal)
            counsellor_id: Counsellor who owns/created the data
            resource_type: Type of resource accessed (student, extraction, etc.)
            resource_id: Specific resource identifier
            action: Action performed (read, create, update, delete, export)
            phi_fields: List of PHI field names accessed
            error_message: Error message if request failed
            access_reason: Optional reason for access
            data_exported: Whether data was exported/downloaded
        """
        try:
            # Get request correlation ID if available
            request_id = getattr(request.state, "request_id", None)
            if not request_id:
                request_id = str(uuid.uuid4())

            # Infer action and resource type if not provided
            if action is None:
                action = self._infer_action(request.method, str(request.url.path))

            if resource_type is None:
                resource_type = self._infer_resource_type(str(request.url.path))

            # Get client IP address
            ip_address = None
            if request.client:
                ip_address = request.client.host

            # Check for forwarded IP (behind proxy)
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                # Get the first IP in the chain (original client)
                ip_address = forwarded_for.split(",")[0].strip()

            # Build audit log entry
            audit_entry = {
                # WHO
                "client_id": str(client_context.client_id),
                "client_type": client_context.client_type,
                "client_name": client_context.client_name,
                "user_id": str(client_context.user_id) if client_context.user_id else None,
                "user_email": client_context.user_email,

                # WHAT
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,

                # WHOSE
                "student_id": student_id,
                "counsellor_id": str(counsellor_id) if counsellor_id else None,
                "school_id": str(client_context.school_id) if client_context.school_id else None,

                # HOW
                "endpoint": str(request.url.path),
                "method": request.method,
                "ip_address": ip_address,
                "user_agent": request.headers.get("user-agent"),

                # Request/Response
                "request_id": request_id,
                "status_code": response_status,
                "response_time_ms": response_time_ms,
                "error_message": error_message,

                # Additional context
                "phi_fields_accessed": phi_fields,
                "data_exported": data_exported,
                "access_reason": access_reason,
            }

            # Insert audit log in a thread to avoid blocking the event loop
            await asyncio.to_thread(
                retry_on_network_error,
                lambda: supabase.table("phi_audit_log").insert(audit_entry).execute()
            )

            logger.debug(
                f"PHI audit: {action} {resource_type} by {client_context.client_name} "
                f"(student={truncate_id(student_id)}, status={response_status})"
            )

        except Exception as e:
            # Log error but don't fail the main request
            logger.error(f"Failed to write PHI audit log: {type(e).__name__}")

    # Compiled patterns for resource_id extraction (UUID / ALL_CAPS code / numeric)
    _UUID_RE = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    _CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
    _NUMERIC_RE = re.compile(r"^\d+$")
    # Path prefixes to ignore when scanning for ID-like segments
    _SKIP_SEGMENTS = frozenset({"api", "v1", "v2", "admin"})

    def _looks_like_id(self, segment: str) -> bool:
        """True if a path segment looks like a resource id (UUID, code, or numeric)."""
        if not segment:
            return False
        if self._UUID_RE.match(segment):
            return True
        if self._CODE_RE.match(segment):
            return True
        if self._NUMERIC_RE.match(segment):
            return True
        return False

    def _extract_resource_id(self, path: str) -> Optional[str]:
        """
        Extract a resource id from an admin URL path.

        Scans path segments right-to-left and returns the first segment that
        looks like a UUID, ALL_CAPS code, or numeric id. Skips boilerplate
        prefix segments (api, v1, admin). Returns None if no id-like segment
        is present (e.g. collection-level POST endpoints).
        """
        parts = [p for p in path.split("/") if p and p not in self._SKIP_SEGMENTS]
        for seg in reversed(parts):
            if self._looks_like_id(seg):
                return seg
        return None

    def _infer_admin_resource_type(self, path: str) -> str:
        """
        Infer the resource type for an admin-config endpoint path.

        Distinct from `_infer_resource_type` (PHI-focused). Returns the
        logical config table the endpoint mutates so audit queries like
        "who edited templates this week" are easy.
        """
        # Order matters: more specific paths first
        if "/system-prompts/components" in path or "/prompt-components" in path:
            return "system_prompt_component"
        if "/system-prompts/configurations" in path or "/prompt-configurations" in path:
            return "system_prompt_configuration"
        if "/system-prompts/config-components" in path:
            return "system_prompt_config_component"
        if "/system-prompts/consultation-types" in path:
            return "consultation_type_system_prompt"
        if "/system-prompts" in path:
            return "system_prompt"
        if "/template-segments" in path:
            return "template_segment"
        if "/template-standard-texts" in path:
            return "template_standard_text"
        if "/templates" in path:
            return "template"
        if "/segment-definitions" in path or "/segments/" in path or path.endswith("/segments"):
            return "segment_definition"
        if "/consultation-type-segments" in path:
            return "consultation_type_segment"
        if "/consultation-types" in path:
            return "consultation_type"
        if "/counsellor-templates" in path:
            return "doctor_template"
        if "/counsellor-medicines" in path or ("/medicines" in path and "/school" not in path):
            return "doctor_medicine"
        if "/school-medicines" in path or "/medicine-list" in path:
            return "hospital_medicine_list"
        if "/counsellor-investigations" in path or ("/investigations" in path and "/school" not in path):
            return "doctor_investigation"
        if "/school-investigations" in path or "/investigation-list" in path:
            return "hospital_investigation_list"
        if "/assistants" in path:
            return "nurse"
        if "/counsellors" in path:
            return "doctor"
        if "/admin/clients" in path or "/api-clients" in path:
            return "api_client"
        if "/processing-modes" in path:
            return "processing_mode"
        if "/triage" in path:
            return "triage_config"
        if "/radiology-plan" in path:
            return "radiology_plan_library"
        if "/radiology-toxicity" in path:
            return "radiology_toxicity_library"
        if "/app-settings" in path:
            return "app_setting"
        if "/admin/" in path:
            return "admin"
        return "unknown"

    async def log_admin_action(
        self,
        client_context: ClientContext,
        request: Request,
        response_status: int,
        response_time_ms: int,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        before_value: Optional[dict] = None,
        after_value: Optional[dict] = None,
        request_body: Optional[dict] = None,
        error_message: Optional[str] = None,
    ):
        """
        Log an admin-initiated config mutation.

        Fire-and-forget: failures are logged but never propagate. Called
        automatically by AuthMiddleware for every non-PHI admin write
        (POST/PUT/PATCH/DELETE). Endpoints may also call directly to record
        before/after diffs and a known resource_id.

        Args:
            client_context: Authenticated admin client (must be client_type='admin')
            request: FastAPI request object
            response_status: HTTP response status code
            response_time_ms: Response time in milliseconds
            resource_type: Logical resource (template, system_prompt_component, ...).
                Inferred from path if not supplied.
            resource_id: PK of the affected row (when known)
            before_value: Snapshot before mutation (optional)
            after_value: Snapshot after mutation (optional)
            request_body: Redacted request payload (optional)
            error_message: Error message if request failed
        """
        try:
            # Only log admin-type clients; defensive guard since middleware checks too
            if client_context.client_type != "admin":
                return

            request_id = getattr(request.state, "request_id", None)
            if not request_id:
                request_id = str(uuid.uuid4())

            action = self._infer_action(request.method, str(request.url.path))
            # Reads slip through if a caller invokes this directly; skip them.
            if action == "read":
                return

            if resource_type is None:
                resource_type = self._infer_admin_resource_type(str(request.url.path))

            if resource_id is None:
                resource_id = self._extract_resource_id(str(request.url.path))

            # IP extraction (mirror log_phi_access logic)
            ip_address = None
            if request.client:
                host = request.client.host
                if host and host not in ("testclient",):
                    if host == "localhost":
                        ip_address = "127.0.0.1"
                    else:
                        ipv4 = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
                        ipv6 = r'^[0-9a-fA-F:]+$'
                        if re.match(ipv4, host) or re.match(ipv6, host):
                            ip_address = host
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                ip_address = forwarded_for.split(",")[0].strip()

            audit_entry = {
                # WHO
                "admin_id": str(client_context.client_id) if client_context.client_id else None,
                "admin_email": client_context.user_email or client_context.client_name or "unknown",
                "admin_role": client_context.user_role,

                # WHAT
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,

                # HOW
                "endpoint": str(request.url.path),
                "method": request.method,
                "ip_address": ip_address,
                "user_agent": request.headers.get("user-agent"),

                # Request/Response metadata
                "request_id": request_id,
                "status_code": response_status,
                "response_time_ms": response_time_ms,
                "error_message": error_message,

                # Diff context
                "before_value": before_value,
                "after_value": after_value,
                "request_body": request_body,
            }

            await asyncio.to_thread(
                retry_on_network_error,
                lambda: supabase.table("admin_action_log").insert(audit_entry).execute()
            )

            logger.debug(
                f"[ADMIN_AUDIT] {action} {resource_type} by {audit_entry['admin_email']} "
                f"(status={response_status})"
            )

        except Exception as e:
            logger.error(f"Failed to write admin action log: {type(e).__name__}")

    async def log_failed_auth(
        self,
        request: Request,
        error_message: str,
        attempted_client_type: Optional[str] = None,
    ):
        """
        Log a failed authentication attempt.

        Args:
            request: FastAPI request object
            error_message: Reason for auth failure
            attempted_client_type: Type of auth that was attempted
        """
        try:
            # Get client IP
            ip_address = None
            if request.client:
                host = request.client.host
                # Validate IP address format (skip TestClient pseudo-IP "testclient")
                if host and host not in ("testclient", "localhost"):
                    # Check if it looks like a valid IP (IPv4 or IPv6)
                    import re
                    ipv4_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
                    ipv6_pattern = r'^[0-9a-fA-F:]+$'
                    if re.match(ipv4_pattern, host) or re.match(ipv6_pattern, host):
                        ip_address = host
                elif host == "localhost":
                    ip_address = "127.0.0.1"

            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                ip_address = forwarded_for.split(",")[0].strip()

            audit_entry = {
                "client_id": None,
                "client_type": attempted_client_type or "unknown",
                "client_name": "unauthenticated",
                "action": "auth_failed",
                "resource_type": "authentication",
                "endpoint": str(request.url.path),
                "method": request.method,
                "ip_address": ip_address,
                "user_agent": request.headers.get("user-agent"),
                "request_id": str(uuid.uuid4()),
                "status_code": 401,
                "error_message": error_message,
            }

            await asyncio.to_thread(
                retry_on_network_error,
                lambda: supabase.table("phi_audit_log").insert(audit_entry).execute()
            )

            logger.warning(f"Failed auth attempt from {ip_address}: {error_message}")

        except Exception as e:
            logger.error(f"Failed to log auth failure: {type(e).__name__}")

    async def get_student_access_history(
        self,
        student_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """
        Get access history for a specific student.

        Args:
            student_id: Student identifier to query
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            List of audit log entries for the student
        """
        try:
            result = retry_on_network_error(
                lambda: supabase.table("phi_audit_log")
                .select("*")
                .eq("student_id", student_id)
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting student access history: {e}")
            return []

    async def get_client_access_history(
        self,
        client_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """
        Get access history for a specific API client.

        Args:
            client_id: Client ID to query
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            List of audit log entries for the client
        """
        try:
            result = retry_on_network_error(
                lambda: supabase.table("phi_audit_log")
                .select("*")
                .eq("client_id", str(client_id))
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting client access history: {e}")
            return []

    async def get_access_report(
        self,
        start_date: datetime,
        end_date: datetime,
        student_id: Optional[str] = None,
        client_id: Optional[UUID] = None,
        action: Optional[str] = None,
        limit: int = 1000,
    ) -> List[dict]:
        """
        Generate an access report for a time period.

        Args:
            start_date: Start of reporting period
            end_date: End of reporting period
            student_id: Filter by student (optional)
            client_id: Filter by client (optional)
            action: Filter by action type (optional)
            limit: Maximum records to return

        Returns:
            List of audit log entries matching criteria
        """
        try:
            query = (
                supabase.table("phi_audit_log")
                .select("*")
                .gte("created_at", start_date.isoformat())
                .lte("created_at", end_date.isoformat())
            )

            if student_id:
                query = query.eq("student_id", student_id)
            if client_id:
                query = query.eq("client_id", str(client_id))
            if action:
                query = query.eq("action", action)

            result = retry_on_network_error(
                lambda: query.order("created_at", desc=True).limit(limit).execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Error generating access report: {e}")
            return []

    async def get_audit_summary(
        self,
        client_id: Optional[UUID] = None,
        hours: int = 24,
    ) -> dict:
        """
        Get a summary of audit activity.

        Args:
            client_id: Filter by client (optional)
            hours: Number of hours to look back

        Returns:
            Summary statistics
        """
        try:
            # Get recent activity
            from datetime import timedelta
            start_time = datetime.now(timezone.utc) - timedelta(hours=hours)

            query = (
                supabase.table("phi_audit_log")
                .select("action, resource_type, status_code")
                .gte("created_at", start_time.isoformat())
            )

            if client_id:
                query = query.eq("client_id", str(client_id))

            result = retry_on_network_error(
                lambda: query.execute()
            )

            if not result.data:
                return {
                    "total_requests": 0,
                    "by_action": {},
                    "by_resource": {},
                    "success_rate": 0,
                }

            data = result.data

            # Calculate summary
            total = len(data)
            by_action = {}
            by_resource = {}
            success_count = 0

            for entry in data:
                action = entry.get("action", "unknown")
                resource = entry.get("resource_type", "unknown")
                status = entry.get("status_code", 0)

                by_action[action] = by_action.get(action, 0) + 1
                by_resource[resource] = by_resource.get(resource, 0) + 1

                if 200 <= status < 300:
                    success_count += 1

            return {
                "total_requests": total,
                "by_action": by_action,
                "by_resource": by_resource,
                "success_rate": (success_count / total * 100) if total > 0 else 0,
                "time_period_hours": hours,
            }

        except Exception as e:
            logger.error(f"Error generating audit summary: {e}")
            return {"error": str(e)}


# Global audit service instance
audit_service = AuditService()

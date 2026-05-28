"""
Admin API Router

Handles administrative operations including:
- API Client Management (create, list, update, delete, rotate keys)
- HIPAA Audit Log viewing
- Segment request approval
- Pending segment review
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from pydantic import BaseModel
import uuid

from models.auth_models import (
    APIClientCreate,
    APIClientUpdate,
    APIClientResponse,
    APIKeyCreateResponse,
    APIKeyRotateResponse,
    ServiceJWTCreate,
    ServiceJWTResponse,
    APIUsageStats,
    ClientContext,
)
from services.auth_service import (
    create_api_client,
    rotate_api_key,
    refresh_service_jwt,
    revoke_all_refresh_tokens,
    switch_auth_mode,
)
from services.audit_service import audit_service
from services.supabase_service import supabase, retry_on_network_error
from services.gemini_client_factory import reset_client, is_vertex_ai_mode
from dependencies.auth import require_admin


router = APIRouter(prefix="/api/v1/admin", tags=["Admin Operations"])


def normalize_admin_id(admin_id: str) -> uuid.UUID:
    """Normalize admin ID string to UUID"""
    try:
        return uuid.UUID(admin_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid admin ID format")


# =============================================================================
# Segment Approval Workflow
# =============================================================================

@router.get("/segments/pending")
async def get_pending_segment_requests(
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get all pending segment requests awaiting admin approval.

    Returns segments with status='pending_approval' that need schema completion.

    **Returns:**
    - segments: List of pending segment records with doctor and consultation type info
    - count: Total number of pending requests
    """
    try:
        from services.supabase_service import get_pending_segments

        segments = get_pending_segments()

        return {
            "success": True,
            "segments": segments,
            "count": len(segments)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch pending segments")


@router.put("/segments/{segment_id}/approve")
async def approve_segment_request(
    segment_id: str,
    admin_id: str = Query(..., description="Admin ID approving the request"),
    schema_definition_json: Dict[str, Any] = Body(..., description="JSON schema for segment structure"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Approve a pending segment request by adding the JSON schema.

    **Path Parameters:**
    - segment_id: UUID of the pending segment (unique identifier)

    **Query Parameters:**
    - admin_id: Admin UUID approving the request

    **Request Body:**
    - schema_definition_json: Complete JSON schema definition for extraction

    **Actions:**
    1. Validates the segment is in pending_approval status
    2. Adds the JSON schema to the segment
    3. Changes status from 'pending_approval' to 'active'
    4. Records admin_id and approval timestamp
    5. **If segment has template_id**: Automatically adds segment to template_segments junction table
    6. Returns approved segment details

    **Template Junction Table Insertion:**
    - When a doctor requests a segment from within a template, the segment.template_id is set
    - Upon approval, the segment is automatically added to that template's segment list
    - The unique combination (template_id, segment_id) ensures no duplicates
    - Default configuration is inherited from the segment request
    """
    try:
        from services.supabase_service import (
            approve_segment_request,
            add_segment_to_template
        )

        admin_uuid = normalize_admin_id(admin_id)

        # Approve the segment (sets is_active=true, adds schema, updates status)
        segment = approve_segment_request(
            segment_id=segment_id,
            schema_definition_json=schema_definition_json,
            approved_by_admin_id=admin_uuid
        )

        # If segment was requested from within a template, add it to that template
        template_id = segment.get("template_id")
        segment_code = segment.get("segment_code", segment_id)

        if template_id:
            try:
                add_segment_to_template(
                    template_id=uuid.UUID(template_id),
                    segment_id=uuid.UUID(segment["id"]),
                    segment_code=segment_code,
                    category=segment.get("default_category", "additional"),
                    display_order=segment.get("display_order", 999),
                    brevity_level=segment.get("default_brevity_level", "balanced"),
                    terminology_style=segment.get("default_terminology_style", "medical_terms")
                )

                return {
                    "success": True,
                    "message": f"Segment '{segment_code}' approved and added to template",
                    "segment": segment,
                    "added_to_template": True,
                    "template_id": template_id
                }
            except Exception as template_error:
                # Segment is approved but failed to add to template - log warning
                return {
                    "success": True,
                    "message": f"Segment '{segment_code}' approved but failed to add to template",
                    "segment": segment,
                    "added_to_template": False,
                    "template_error": str(template_error)
                }
        else:
            # Segment approved but not associated with any template
            return {
                "success": True,
                "message": f"Segment '{segment_code}' approved and activated",
                "segment": segment,
                "added_to_template": False
            }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to approve segment")


# =============================================================================
# API Client Management
# =============================================================================

@router.post("/clients", response_model=APIKeyCreateResponse)
async def create_client(
    data: APIClientCreate,
    client: ClientContext = Depends(require_admin),
) -> APIKeyCreateResponse:
    """
    Create a new API client.

    **Client Types:**
    - `ehr`: EHR integration (server-to-server) - uses API Key authentication
      - REQUIRES hospital_id (one API key per hospital)
    - `mobile_app`: Mobile application - uses Service JWT authentication
      - hospital_id=NULL means global access to all hospitals
    - `web_app`: External web application (white-label) - uses Service JWT authentication
      - hospital_id=NULL means global access to all hospitals

    **IMPORTANT:** The API key or JWT token is only shown ONCE in the response.
    Store it securely - it cannot be retrieved later.

    **Returns:**
    - client_id: UUID of the new client
    - client_name: Human-readable name
    - api_key: The API key (for EHR) or JWT token (for mobile/web)
    - api_key_prefix: First 8 characters for identification
    """
    return await create_api_client(data)


@router.get("/clients")
async def list_clients(
    client_type: Optional[str] = Query(None, description="Filter by client type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    List all API clients.

    **Query Parameters:**
    - client_type: Filter by 'ehr', 'mobile_app', or 'web_app'
    - is_active: Filter by active/inactive status
    - hospital_id: Filter by hospital (NULL shows global clients)

    **Returns:**
    - clients: List of API client records (without sensitive credentials)
    - count: Total number of clients matching filters
    """
    try:
        query = supabase.table("api_clients").select(
            "id, client_name, client_type, auth_mode, hospital_id, allowed_doctor_ids, "
            "scopes, is_active, rate_limit_per_hour, token_expiry_minutes, contact_email, description, "
            "api_key_prefix, created_at, updated_at, last_used_at"
        )

        if client_type:
            query = query.eq("client_type", client_type)
        if is_active is not None:
            query = query.eq("is_active", is_active)
        if hospital_id:
            query = query.eq("hospital_id", hospital_id)

        result = retry_on_network_error(
            lambda: query.order("created_at", desc=True).execute()
        )

        return {
            "success": True,
            "clients": result.data or [],
            "count": len(result.data or []),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to list clients")


@router.get("/clients/{client_id}")
async def get_client(
    client_id: str,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Get details for a specific API client.

    **Path Parameters:**
    - client_id: UUID of the client

    **Returns:**
    - client: Client details (without sensitive credentials)
    """
    try:
        result = retry_on_network_error(
            lambda: supabase.table("api_clients")
            .select(
                "id, client_name, client_type, auth_mode, hospital_id, allowed_doctor_ids, "
                "scopes, is_active, rate_limit_per_hour, token_expiry_minutes, contact_email, description, "
                "api_key_prefix, created_at, updated_at, last_used_at"
            )
            .eq("id", client_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Client not found")

        return {
            "success": True,
            "client": result.data[0],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get client")


@router.put("/clients/{client_id}")
async def update_client(
    client_id: str,
    data: APIClientUpdate,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Update an API client.

    **Path Parameters:**
    - client_id: UUID of the client

    **Request Body:**
    - client_name: New name (optional)
    - allowed_doctor_ids: New doctor restrictions (optional)
    - scopes: New scopes (optional)
    - rate_limit_per_hour: New rate limit (optional)
    - is_active: Enable/disable client (optional)
    """
    try:
        update_data = data.model_dump(exclude_unset=True)

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Convert UUIDs to strings
        if "allowed_doctor_ids" in update_data and update_data["allowed_doctor_ids"]:
            update_data["allowed_doctor_ids"] = [
                str(d) for d in update_data["allowed_doctor_ids"]
            ]

        result = retry_on_network_error(
            lambda: supabase.table("api_clients")
            .update(update_data)
            .eq("id", client_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Client not found")

        return {
            "success": True,
            "message": "Client updated successfully",
            "client": result.data[0],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update client")


@router.delete("/clients/{client_id}")
async def delete_client(
    client_id: str,
    hard_delete: bool = Query(False, description="Permanently delete (vs soft delete)"),
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Delete (deactivate) an API client.

    **Path Parameters:**
    - client_id: UUID of the client

    **Query Parameters:**
    - hard_delete: If true, permanently removes the client. Default: soft delete (set is_active=false)

    **Note:** Soft delete is recommended to preserve audit trail.
    """
    try:
        if hard_delete:
            # CASCADE will delete refresh_tokens automatically
            result = retry_on_network_error(
                lambda: supabase.table("api_clients")
                .delete()
                .eq("id", client_id)
                .execute()
            )
        else:
            result = retry_on_network_error(
                lambda: supabase.table("api_clients")
                .update({"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()})
                .eq("id", client_id)
                .execute()
            )

        if not result.data:
            raise HTTPException(status_code=404, detail="Client not found")

        # Revoke all refresh tokens on deactivation (fire-and-forget)
        if not hard_delete:
            try:
                import asyncio
                asyncio.create_task(revoke_all_refresh_tokens(uuid.UUID(client_id)))
            except Exception:
                pass

        return {
            "success": True,
            "message": "Client deleted" if hard_delete else "Client deactivated",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete client")


@router.post("/clients/{client_id}/rotate-key", response_model=APIKeyRotateResponse)
async def rotate_client_key(
    client_id: str,
    client: ClientContext = Depends(require_admin),
) -> APIKeyRotateResponse:
    """
    Rotate the API key for an EHR client.

    **Path Parameters:**
    - client_id: UUID of the EHR client

    **Note:** This only works for EHR clients (API key auth).
    For mobile/web apps, use /clients/{client_id}/refresh-token instead.

    **IMPORTANT:** The new API key is only shown ONCE in the response.
    The old key is immediately invalidated.
    """
    return await rotate_api_key(uuid.UUID(client_id))


@router.post("/clients/{client_id}/switch-auth-mode")
async def switch_client_auth_mode(
    client_id: str,
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Switch an EHR client between API Key and Token-based auth.

    Generates new credentials for the target mode and invalidates old ones.
    The new credentials are returned once — store them securely.
    """
    return await switch_auth_mode(uuid.UUID(client_id))


@router.post("/clients/{client_id}/refresh-token", response_model=ServiceJWTResponse)
async def refresh_client_token(
    client_id: str,
    expires_in_hours: int = Query(24, ge=1, le=720, description="Token validity in hours"),
    client: ClientContext = Depends(require_admin),
) -> ServiceJWTResponse:
    """
    Generate a new JWT token for a mobile/web app client.

    **Path Parameters:**
    - client_id: UUID of the mobile_app or web_app client

    **Query Parameters:**
    - expires_in_hours: Token validity (1-720 hours, default: 24)

    **Note:** This only works for mobile_app and web_app clients.
    For EHR clients, use /clients/{client_id}/rotate-key instead.
    """
    return await refresh_service_jwt(uuid.UUID(client_id), expires_in_hours)


@router.get("/clients/{client_id}/usage")
async def get_client_usage(
    client_id: str,
    hours: int = Query(24, ge=1, le=720, description="Hours to look back"),
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Get API usage statistics for a client.

    **Path Parameters:**
    - client_id: UUID of the client

    **Query Parameters:**
    - hours: Number of hours to look back (default: 24)

    **Returns:**
    - total_requests: Total API calls in the period
    - requests_by_endpoint: Breakdown by endpoint
    - requests_by_status: Breakdown by HTTP status code
    - avg_response_time_ms: Average response time
    """
    try:
        from datetime import timedelta

        start_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = retry_on_network_error(
            lambda: supabase.table("api_client_usage")
            .select("endpoint, method, status_code, response_time_ms")
            .eq("client_id", client_id)
            .gte("created_at", start_time.isoformat())
            .execute()
        )

        data = result.data or []
        total = len(data)

        if total == 0:
            return {
                "success": True,
                "client_id": client_id,
                "period_hours": hours,
                "total_requests": 0,
                "requests_by_endpoint": {},
                "requests_by_status": {},
                "avg_response_time_ms": 0,
            }

        # Calculate statistics
        by_endpoint = {}
        by_status = {}
        total_response_time = 0

        for entry in data:
            endpoint = entry.get("endpoint", "unknown")
            status = entry.get("status_code", 0)
            response_time = entry.get("response_time_ms", 0)

            by_endpoint[endpoint] = by_endpoint.get(endpoint, 0) + 1
            by_status[str(status)] = by_status.get(str(status), 0) + 1
            total_response_time += response_time or 0

        return {
            "success": True,
            "client_id": client_id,
            "period_hours": hours,
            "total_requests": total,
            "requests_by_endpoint": by_endpoint,
            "requests_by_status": by_status,
            "avg_response_time_ms": total_response_time / total if total > 0 else 0,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get usage stats")


# =============================================================================
# HIPAA Audit Log Viewer
# =============================================================================

@router.get("/audit/patient/{patient_id}")
async def get_patient_audit_log(
    patient_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Get audit log entries for a specific patient.

    **Path Parameters:**
    - patient_id: Patient identifier

    **Query Parameters:**
    - limit: Maximum records to return (default: 100, max: 1000)
    - offset: Number of records to skip for pagination

    **Returns:**
    - entries: List of audit log entries
    - count: Number of entries returned
    """
    entries = await audit_service.get_patient_access_history(
        patient_id=patient_id,
        limit=limit,
        offset=offset,
    )

    return {
        "success": True,
        "patient_id": patient_id,
        "entries": entries,
        "count": len(entries),
    }


@router.get("/audit/client/{client_id}")
async def get_client_audit_log(
    client_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Get audit log entries for a specific API client.

    **Path Parameters:**
    - client_id: API client UUID

    **Query Parameters:**
    - limit: Maximum records to return (default: 100, max: 1000)
    - offset: Number of records to skip for pagination

    **Returns:**
    - entries: List of audit log entries
    - count: Number of entries returned
    """
    entries = await audit_service.get_client_access_history(
        client_id=uuid.UUID(client_id),
        limit=limit,
        offset=offset,
    )

    return {
        "success": True,
        "client_id": client_id,
        "entries": entries,
        "count": len(entries),
    }


@router.get("/audit/report")
async def get_audit_report(
    start_date: str = Query(..., description="Start date (ISO format)"),
    end_date: str = Query(..., description="End date (ISO format)"),
    patient_id: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None, description="Filter by action (read, create, update, delete)"),
    limit: int = Query(1000, ge=1, le=10000),
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Generate an audit report for a time period.

    **Query Parameters:**
    - start_date: Start of reporting period (ISO format)
    - end_date: End of reporting period (ISO format)
    - patient_id: Filter by patient (optional)
    - client_id: Filter by API client (optional)
    - action: Filter by action type (optional)
    - limit: Maximum records to return (default: 1000)

    **Returns:**
    - entries: List of audit log entries matching criteria
    - count: Number of entries returned
    - period: Reporting period info
    """
    try:
        start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid date format")

    entries = await audit_service.get_access_report(
        start_date=start,
        end_date=end,
        patient_id=patient_id,
        client_id=uuid.UUID(client_id) if client_id else None,
        action=action,
        limit=limit,
    )

    return {
        "success": True,
        "period": {
            "start": start_date,
            "end": end_date,
        },
        "filters": {
            "patient_id": patient_id,
            "client_id": client_id,
            "action": action,
        },
        "entries": entries,
        "count": len(entries),
    }


@router.get("/audit/summary")
async def get_audit_summary(
    client_id: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=720),
    client: ClientContext = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Get a summary of audit activity.

    **Query Parameters:**
    - client_id: Filter by API client (optional)
    - hours: Number of hours to look back (default: 24)

    **Returns:**
    - total_requests: Total API calls
    - by_action: Breakdown by action type
    - by_resource: Breakdown by resource type
    - success_rate: Percentage of successful requests
    """
    summary = await audit_service.get_audit_summary(
        client_id=uuid.UUID(client_id) if client_id else None,
        hours=hours,
    )

    return {
        "success": True,
        **summary,
    }


# =============================================================================
# App Settings
# =============================================================================


class AppSettingUpdate(BaseModel):
    value: bool


@router.get("/settings", dependencies=[Depends(require_admin)])
async def get_app_settings():
    """Get all app settings."""
    result = supabase.table("app_settings").select("key, value, description, updated_at").execute()

    settings = {}
    for row in result.data:
        settings[row["key"]] = {
            "value": row["value"],
            "description": row.get("description"),
            "updated_at": row.get("updated_at"),
        }

    return {"success": True, "settings": settings}


@router.put("/settings/use-vertex-ai", dependencies=[Depends(require_admin)])
async def update_use_vertex_ai(body: AppSettingUpdate):
    """
    Toggle use_vertex_ai setting and reset the Gemini client.

    The next pipeline call will create a new client using the updated setting.
    """
    new_value = str(body.value).lower()

    # Update DB
    result = supabase.table("app_settings").update({
        "value": new_value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("key", "use_vertex_ai").execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="use_vertex_ai setting not found in app_settings table")

    # Reset the singleton client so next call picks up new setting
    reset_client()

    return {
        "success": True,
        "use_vertex_ai": body.value,
        "message": f"Switched to {'Vertex AI' if body.value else 'Gemini API'}. Next API call will use the new client.",
    }

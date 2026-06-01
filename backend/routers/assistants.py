"""
Assistant Management Router

REST API endpoints for assistant CRUD operations.
"""

import os
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import uuid

from models.auth_models import ClientContext
from dependencies.auth import require_admin, get_current_client

from services.assistant_service import (
    get_all_assistants,
    search_assistants,
    get_assistant,
    create_assistant,
    update_assistant,
    deactivate_assistant,
    get_assistant_counsellors,
    link_assistant_to_counsellor,
    unlink_assistant_from_counsellor
)
from services.assistant_templates_service import share_template_with_assistant
from services.supabase_service import supabase

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/assistants", tags=["Assistant Management"])


# ============================================================================
# Helper Functions
# ============================================================================

def _assign_default_template_to_assistant(assistant_id: str, assistant_name: str, school_id: Optional[str] = None) -> None:
    """
    Assign a default template to a newly created assistant.

    Resolution chain:
    1. Linked counsellor's default (first active from assistant_counsellors)
    2. School default (schools.default_template_id)
    3. OP_CORE fallback (universal template)

    The template is shared via assistant_templates and set as assistants.default_template_id.
    Failures are logged but don't block assistant creation.

    Args:
        assistant_id: UUID of the newly created assistant
        assistant_name: Name of the assistant (for logging)
        school_id: Optional school UUID for school default lookup
    """
    try:
        template_id = None
        template_code = None
        source = None

        # 1. Try linked counsellor's default
        try:
            from services.assistant_service import get_assistant_counsellors
            assistant_counsellors = get_assistant_counsellors(assistant_id)
            for assoc in assistant_counsellors:
                counsellor_info = assoc.get("counsellors", {})
                if not counsellor_info:
                    continue
                linked_counsellor_id = counsellor_info.get("id")
                if linked_counsellor_id:
                    counsellor_record = (
                        supabase.table("counsellors")
                        .select("default_template_id")
                        .eq("id", linked_counsellor_id)
                        .limit(1)
                        .execute()
                    )
                    if counsellor_record.data:
                        doc_default_id = counsellor_record.data[0].get("default_template_id")
                        if doc_default_id:
                            template_result = (
                                supabase.table("templates")
                                .select("id, template_code, is_active")
                                .eq("id", doc_default_id)
                                .eq("is_active", True)
                                .limit(1)
                                .execute()
                            )
                            if template_result.data:
                                template_id = template_result.data[0]["id"]
                                template_code = template_result.data[0]["template_code"]
                                source = f"linked counsellor {linked_counsellor_id}"
                                break
        except Exception as e:
            logger.warning(f"[NURSE_CREATE] Error checking linked counsellors for default: {e}")

        # 2. Try school default
        if not template_id and school_id:
            try:
                school_result = (
                    supabase.table("schools")
                    .select("default_template_id")
                    .eq("id", school_id)
                    .limit(1)
                    .execute()
                )
                if school_result.data:
                    hosp_default_id = school_result.data[0].get("default_template_id")
                    if hosp_default_id:
                        template_result = (
                            supabase.table("templates")
                            .select("id, template_code, is_active")
                            .eq("id", hosp_default_id)
                            .eq("is_active", True)
                            .limit(1)
                            .execute()
                        )
                        if template_result.data:
                            template_id = template_result.data[0]["id"]
                            template_code = template_result.data[0]["template_code"]
                            source = "school default"
            except Exception as e:
                logger.warning(f"[NURSE_CREATE] Error checking school default: {e}")

        # 3. OP_CORE fallback
        if not template_id:
            try:
                op_core_result = (
                    supabase.table("templates")
                    .select("id, template_code, is_active")
                    .eq("template_code", "OP_CORE")
                    .eq("is_active", True)
                    .limit(1)
                    .execute()
                )
                if op_core_result.data:
                    template_id = op_core_result.data[0]["id"]
                    template_code = op_core_result.data[0]["template_code"]
                    source = "OP_CORE fallback"
            except Exception as e:
                logger.warning(f"[NURSE_CREATE] Error fetching OP_CORE fallback: {e}")

        if not template_id:
            logger.warning(
                f"[NURSE_CREATE] No default template found for assistant '{assistant_name}' (ID: {assistant_id})"
            )
            return

        # Share and set as default
        share_template_with_assistant(
            template_id=uuid.UUID(template_id),
            template_code=template_code,
            assistant_id=uuid.UUID(assistant_id),
        )

        try:
            supabase.table("assistants")\
                .update({"default_template_id": str(template_id)})\
                .eq("id", assistant_id)\
                .execute()
        except Exception as set_default_err:
            logger.warning(f"[NURSE_CREATE] Failed to set default template: {set_default_err}")

        logger.info(
            f"[NURSE_CREATE] Assigned {template_code} (from {source}) as default for assistant '{assistant_name}' (ID: {assistant_id})"
        )

    except Exception as e:
        logger.error(
            f"[NURSE_CREATE] Failed to assign default template for assistant '{assistant_name}': {e}"
        )


# ============================================================================
# Request/Response Models
# ============================================================================

class AssistantCreateRequest(BaseModel):
    """Request model for creating an assistant"""
    email: str = Field(..., description="Nurse's email address")
    full_name: str = Field(..., min_length=2, max_length=255, description="Nurse's full name")
    qualification: Optional[str] = Field(None, max_length=100, description="Nursing qualification (RN, LPN, BSN)")
    school_id: Optional[str] = Field(None, description="School UUID")


class AssistantCreateWithSchoolRequest(BaseModel):
    """Request model for creating an assistant with school code lookup"""
    id: str = Field(..., description="Assistant UUID (provided by caller)")
    school_code: str = Field(..., min_length=1, max_length=50, description="School code to lookup school_id")
    full_name: str = Field(..., min_length=2, max_length=255, description="Nurse's full name")
    email: str = Field(..., description="Nurse's email address")
    qualification: Optional[str] = Field(None, max_length=100, description="Nursing qualification (RN, LPN, BSN)")


class AssistantCreateEHRRequest(BaseModel):
    """Request model for EHR integration - auto-generates UUID"""
    school_code: str = Field(..., min_length=1, max_length=50, description="School code to lookup school_id")
    full_name: str = Field(..., min_length=2, max_length=255, description="Nurse's full name")
    email: str = Field(..., description="Nurse's email address")
    qualification: Optional[str] = Field(None, max_length=100, description="Nursing qualification (RN, LPN, BSN)")


class AssistantUpdateRequest(BaseModel):
    """Request model for updating an assistant"""
    email: Optional[str] = Field(None, description="New email address")
    full_name: Optional[str] = Field(None, min_length=2, max_length=255, description="New full name")
    qualification: Optional[str] = Field(None, max_length=100, description="New qualification")
    school_id: Optional[str] = Field(None, description="New school UUID")
    is_active: Optional[bool] = Field(None, description="Active status")
    default_template_id: Optional[str] = Field(None, description="Default template UUID (null to clear)")


class SetAssistantDefaultTemplateRequest(BaseModel):
    """Request model for setting assistant's default template"""
    template_id: Optional[str] = Field(None, description="Template UUID to set as default (null to clear)")


# ============================================================================
# Assistant CRUD Endpoints
# ============================================================================

@router.get("")
async def list_assistants(
    active_only: bool = Query(True, description="Filter by active status"),
    school_id: Optional[str] = Query(None, description="Filter by school"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get all assistants.

    **Query Parameters:**
    - `active_only`: Filter to show only active assistants (default: true)
    - `school_id`: Filter by school UUID (optional)

    **Returns:**
    - List of assistant records with metadata
    """
    try:
        nurses = get_all_assistants(is_active=active_only, school_id=school_id)

        return {
            "success": True,
            "assistants": nurses,
            "count": len(nurses)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch assistants")


@router.get("/search")
async def search_assistants_endpoint(
    q: str = Query(..., min_length=2, description="Search query (name or email)"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Search assistants by name or email.

    **Query Parameters:**
    - `q`: Search term (case-insensitive, minimum 2 characters)

    **Returns:**
    - List of matching assistant records
    """
    try:
        results = search_assistants(q)

        return {
            "success": True,
            "query": q,
            "assistants": results,
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Search failed")


@router.get("/list-all")
async def list_all_assistants_for_sharing(
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get list of all active assistants for sharing templates.

    Returns simplified assistant list with id, name, email, and qualification.
    Used by UI to display assistant checkboxes.

    **Response:**
    ```json
    {
        "success": true,
        "assistants": [
            {
                "id": "uuid",
                "full_name": "Jane Doe",
                "email": "jane@example.com",
                "qualification": "RN"
            }
        ],
        "count": 10
    }
    ```
    """
    try:
        from services.supabase_service import supabase

        response = (
            supabase.table("assistants")
            .select("id, full_name, email, qualification, school_id")
            .eq("is_active", True)
            .order("full_name")
            .execute()
        )

        return {
            "success": True,
            "assistants": response.data or [],
            "count": len(response.data or [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch assistants")


@router.get("/{assistant_id}")
async def get_assistant_endpoint(
    assistant_id: str,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Get assistant by ID.

    **Path Parameters:**
    - `assistant_id`: Assistant UUID

    **Returns:**
    - Assistant record with full details
    """
    try:
        nurse = get_assistant(assistant_id)

        if not nurse:
            raise HTTPException(status_code=404, detail="Assistant not found")

        return {
            "success": True,
            "nurse": nurse
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch assistant")


@router.post("")
async def create_assistant_endpoint(
    request: AssistantCreateRequest,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Create new assistant with random UUID.

    **Request Body:**
    ```json
    {
        "email": "assistant@school.com",
        "full_name": "Jane Smith",
        "qualification": "RN",
        "school_id": "school-uuid"
    }
    ```

    **Returns:**
    - Created assistant record with generated UUID

    **Notes:**
    - No Supabase auth integration (uses random UUID)
    - Email must be unique
    """
    try:
        nurse = create_assistant(
            email=request.email,
            full_name=request.full_name,
            qualification=request.qualification,
            school_id=request.school_id
        )

        # Assign default template to newly created assistant
        _assign_default_template_to_assistant(nurse["id"], request.full_name, request.school_id)

        return {
            "success": True,
            "message": f"Assistant '{request.full_name}' created successfully",
            "nurse": nurse
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create assistant")


@router.post("/with-school")
async def create_assistant_with_school(
    request: AssistantCreateWithSchoolRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Create new assistant with provided UUID and school code lookup.

    **Auth:** Admin, Web, and EHR (EHR restricted to own school)

    **Request Body:**
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "school_code": "HOSP001",
        "full_name": "Jane Smith",
        "email": "assistant@school.com",
        "qualification": "RN"
    }
    ```

    **Returns:**
    - success: True if assistant created
    - message: Success message
    - assistant_id: UUID of created assistant

    **Notes:**
    - UUID is provided by caller (not auto-generated)
    - school_id is looked up from schools table using school_code
    - Email must be unique
    """
    try:
        from services.supabase_service import supabase
        from datetime import datetime

        # Validate UUID format
        try:
            assistant_uuid = uuid.UUID(request.id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID format")

        # Lookup school_id from school_code
        school_response = (
            supabase.table("schools")
            .select("id")
            .eq("school_code", request.school_code)
            .eq("is_active", True)
            .execute()
        )

        if not school_response.data or len(school_response.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="School not found or inactive"
            )

        school_id = school_response.data[0]["id"]

        # EHR clients can only create assistants in their own school
        if client.client_type == "ehr":
            if client.school_id is None or str(client.school_id) != school_id:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )

        # Check if assistant ID already exists
        existing_id = (
            supabase.table("assistants")
            .select("id")
            .eq("id", str(assistant_uuid))
            .execute()
        )

        if existing_id.data and len(existing_id.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Assistant with this ID already exists"
            )

        # Check if email already exists
        existing_email = (
            supabase.table("assistants")
            .select("id")
            .eq("email", request.email)
            .execute()
        )

        if existing_email.data and len(existing_email.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Assistant with this email already exists"
            )

        # Create assistant with provided UUID and school_id
        assistant_data = {
            "id": str(assistant_uuid),
            "school_id": school_id,
            "full_name": request.full_name,
            "email": request.email,
            "qualification": request.qualification,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        response = supabase.table("assistants").insert(assistant_data).execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to create assistant")

        # Assign default template to newly created assistant
        _assign_default_template_to_assistant(str(assistant_uuid), request.full_name, school_id)

        return {
            "success": True,
            "message": f"Assistant '{request.full_name}' created successfully",
            "assistant_id": str(assistant_uuid)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create assistant")


@router.post("/ehr")
async def create_assistant_ehr(
    request: AssistantCreateEHRRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Create new assistant for EHR integration with auto-generated UUID.

    **Auth:** Admin, Web, and EHR (EHR restricted to own school)

    **Request Body:**
    ```json
    {
        "school_code": "HOSP001",
        "full_name": "Jane Smith",
        "email": "assistant@school.com",
        "qualification": "RN"
    }
    ```

    **Returns:**
    - success: True if assistant created
    - message: Success message
    - assistant_id: Auto-generated UUID of created assistant

    **Notes:**
    - UUID is auto-generated (not provided by caller)
    - school_id is looked up from schools table using school_code
    - Email must be unique
    - Returns 409 if email already exists
    - Returns 404 if school_code not found
    """
    try:
        from datetime import datetime

        # Generate new UUID
        assistant_uuid = uuid.uuid4()

        # Lookup school_id from school_code
        school_response = (
            supabase.table("schools")
            .select("id")
            .eq("school_code", request.school_code)
            .eq("is_active", True)
            .execute()
        )

        if not school_response.data or len(school_response.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="School not found or inactive"
            )

        school_id = school_response.data[0]["id"]

        # EHR clients can only create assistants in their own school
        if client.client_type == "ehr":
            if client.school_id is None or str(client.school_id) != school_id:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )

        # Check if email already exists
        existing_email = (
            supabase.table("assistants")
            .select("id")
            .eq("email", request.email)
            .execute()
        )

        if existing_email.data and len(existing_email.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Assistant with this email already exists"
            )

        # Create assistant with auto-generated UUID and school_id
        assistant_data = {
            "id": str(assistant_uuid),
            "school_id": school_id,
            "full_name": request.full_name,
            "email": request.email,
            "qualification": request.qualification,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        response = supabase.table("assistants").insert(assistant_data).execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to create assistant")

        # Assign default template to newly created assistant
        _assign_default_template_to_assistant(str(assistant_uuid), request.full_name, school_id)

        return {
            "success": True,
            "message": f"Assistant '{request.full_name}' created successfully",
            "assistant_id": str(assistant_uuid)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create assistant")


@router.put("/{assistant_id}")
async def update_assistant_endpoint(
    assistant_id: str,
    request: AssistantUpdateRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Update assistant information.

    **Auth:** Admin, Web, and EHR (EHR restricted to assistants in own school)

    **Path Parameters:**
    - `assistant_id`: Assistant UUID

    **Request Body:**
    - Any fields to update (all optional)

    **Returns:**
    - Updated assistant record
    """
    try:
        from services.supabase_service import supabase

        # EHR clients can only update assistants in their own school
        if client.client_type == "ehr":
            assistant_result = (
                supabase.table("assistants")
                .select("school_id")
                .eq("id", assistant_id)
                .execute()
            )
            if not assistant_result.data:
                raise HTTPException(status_code=404, detail="Assistant not found")

            assistant_school_id = assistant_result.data[0].get("school_id")
            if client.school_id is None or str(client.school_id) != assistant_school_id:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )

        # Handle default_template_id separately (not in assistant_service.update_assistant)
        if request.default_template_id is not None:
            supabase.table("assistants")\
                .update({"default_template_id": request.default_template_id if request.default_template_id else None})\
                .eq("id", assistant_id)\
                .execute()

        nurse = update_assistant(
            assistant_id=assistant_id,
            email=request.email,
            full_name=request.full_name,
            qualification=request.qualification,
            school_id=request.school_id,
            is_active=request.is_active
        )

        return {
            "success": True,
            "message": "Assistant updated successfully",
            "nurse": nurse
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update assistant")


@router.delete("/{assistant_id}")
async def deactivate_assistant_endpoint(
    assistant_id: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Soft delete assistant (set is_active to false).

    **Path Parameters:**
    - `assistant_id`: Assistant UUID

    **Returns:**
    - Updated assistant record with is_active=false

    **Notes:**
    - This is a soft delete - assistant record is preserved
    - Assistant will not appear in active assistant lists
    """
    try:
        nurse = deactivate_assistant(assistant_id)

        return {
            "success": True,
            "message": f"Assistant '{nurse['full_name']}' deactivated successfully",
            "nurse": nurse
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to deactivate assistant")


# ============================================================================
# Assistant-Counsellor Association Endpoints
# ============================================================================

@router.get("/{assistant_id}/counsellors")
async def list_assistant_counsellors(
    assistant_id: str,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Get all counsellors associated with an assistant.

    **Path Parameters:**
    - `assistant_id`: Assistant UUID

    **Returns:**
    - List of counsellor records with association info
    """
    try:
        # Verify assistant exists
        nurse = get_assistant(assistant_id)
        if not nurse:
            raise HTTPException(status_code=404, detail="Assistant not found")

        associations = get_assistant_counsellors(assistant_id)

        # Extract counsellor info from associations
        doctors = []
        for assoc in associations:
            counsellor_info = assoc.get("counsellors", {})
            if counsellor_info:
                doctors.append({
                    "association_id": assoc.get("id"),
                    "counsellor_id": assoc.get("counsellor_id"),
                    "counsellor_name": counsellor_info.get("full_name"),  # Frontend expects counsellor_name
                    "email": counsellor_info.get("email"),
                    "specialization": counsellor_info.get("specialization"),
                    "school_id": counsellor_info.get("school_id"),
                    "is_active": assoc.get("is_active", True),
                    "created_at": assoc.get("created_at")
                })

        return {
            "success": True,
            "assistant_id": assistant_id,
            "counsellors": doctors,
            "count": len(doctors)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch assistant counsellors")


@router.post("/{assistant_id}/counsellors/{counsellor_id}")
async def link_assistant_to_counsellor_endpoint(
    assistant_id: str,
    counsellor_id: str,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Link an assistant to a supervising counsellor.

    **Auth:** Admin + Web + EHR (EHR restricted to assistants in own school)

    **Path Parameters:**
    - `assistant_id`: Assistant UUID
    - `counsellor_id`: Counsellor UUID

    **Returns:**
    - Created/updated association record

    **Notes:**
    - If association exists but is inactive, it will be reactivated
    - Idempotent - calling multiple times has same result
    """
    try:
        # EHR clients can only link assistants in their own school
        if client.client_type == "ehr":
            assistant_result = (
                supabase.table("assistants")
                .select("school_id")
                .eq("id", assistant_id)
                .execute()
            )
            if not assistant_result.data:
                raise HTTPException(status_code=404, detail="Assistant not found")
            assistant_school_id = assistant_result.data[0].get("school_id")
            if client.school_id is None or str(client.school_id) != assistant_school_id:
                raise HTTPException(status_code=403, detail="Access denied")

        association = link_assistant_to_counsellor(assistant_id, counsellor_id)

        # Assign counsellor's default template to assistant if assistant has no default
        # or currently has a PRESCREEN template
        try:
            assistant_record = supabase.table("assistants")\
                .select("id, default_template_id, school_id")\
                .eq("id", assistant_id).limit(1).execute()
            if assistant_record.data:
                nurse = assistant_record.data[0]
                should_reassign = False

                if not nurse.get("default_template_id"):
                    should_reassign = True
                else:
                    # Check if current default is a PRESCREEN template
                    current_tmpl = supabase.table("templates")\
                        .select("template_code")\
                        .eq("id", nurse["default_template_id"]).limit(1).execute()
                    if current_tmpl.data and "PRESCREEN" in (current_tmpl.data[0].get("template_code") or "").upper():
                        should_reassign = True

                if should_reassign:
                    _assign_default_template_to_assistant(
                        assistant_id, "", nurse.get("school_id")
                    )
                    logger.info(f"[NURSE_LINK] Reassigned default template for assistant {assistant_id} after linking counsellor {counsellor_id}")
        except Exception as e:
            logger.warning(f"[NURSE_LINK] Template reassignment after counsellor link failed: {e}")

        return {
            "success": True,
            "message": f"Assistant linked to counsellor successfully",
            "association": association
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to link assistant to counsellor")


@router.delete("/{assistant_id}/counsellors/{counsellor_id}")
async def unlink_assistant_from_counsellor_endpoint(
    assistant_id: str,
    counsellor_id: str,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Unlink an assistant from a counsellor (soft delete).

    **Auth:** Admin + Web + EHR (EHR restricted to assistants in own school)

    **Path Parameters:**
    - `assistant_id`: Assistant UUID
    - `counsellor_id`: Counsellor UUID

    **Returns:**
    - Updated association record with is_active=false

    **Notes:**
    - This is a soft delete - association record is preserved
    - Can be relinked later
    """
    try:
        # EHR clients can only unlink assistants in their own school
        if client.client_type == "ehr":
            assistant_result = (
                supabase.table("assistants")
                .select("school_id")
                .eq("id", assistant_id)
                .execute()
            )
            if not assistant_result.data:
                raise HTTPException(status_code=404, detail="Assistant not found")
            assistant_school_id = assistant_result.data[0].get("school_id")
            if client.school_id is None or str(client.school_id) != assistant_school_id:
                raise HTTPException(status_code=403, detail="Access denied")

        association = unlink_assistant_from_counsellor(assistant_id, counsellor_id)

        return {
            "success": True,
            "message": "Assistant unlinked from counsellor successfully",
            "association": association
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to unlink assistant from counsellor")


# ============================================================================
# Assistant Default Template Endpoints
# ============================================================================

@router.put("/{assistant_id}/default-template")
async def set_assistant_default_template(
    assistant_id: str,
    body: SetAssistantDefaultTemplateRequest = None,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Set or clear the default template for an assistant.

    **Path Parameters:**
    - assistant_id: Assistant UUID

    **Request Body:**
    ```json
    {
        "template_id": "uuid-of-template"  // or null to clear
    }
    ```

    **Returns:**
    - success: True if updated
    - message: Success message
    - default_template_id: The set template ID (or null if cleared)

    **Notes:**
    - Assistant default takes highest priority in assistant fallback chain
    - The template must be accessible to the assistant (is_active=True)
    """
    from services.assistant_templates_service import validate_assistant_template_access

    try:
        assistant_uuid = uuid.UUID(assistant_id)

        # Validate assistant exists
        assistant_result = (
            supabase.table("assistants")
            .select("id, full_name, school_id")
            .eq("id", assistant_id)
            .execute()
        )

        if not assistant_result.data or len(assistant_result.data) == 0:
            raise HTTPException(status_code=404, detail="Assistant not found")

        nurse = assistant_result.data[0]
        template_id = body.template_id if body else None

        # EHR clients can only update assistants in their own school
        if client.client_type == "ehr":
            assistant_school_id = nurse.get("school_id")
            if client.school_id is None or str(client.school_id) != assistant_school_id:
                raise HTTPException(status_code=403, detail="Access denied")

        # If template_id provided, validate assistant has 'use' access
        if template_id:
            has_access = validate_assistant_template_access(assistant_id, template_id)
            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail="Assistant does not have 'use' access to this template"
                )

            # Verify template is active
            template_result = (
                supabase.table("templates")
                .select("id, template_code, is_active")
                .eq("id", template_id)
                .execute()
            )

            if not template_result.data or len(template_result.data) == 0:
                raise HTTPException(status_code=404, detail="Template not found")

            template = template_result.data[0]
            if not template.get("is_active"):
                raise HTTPException(status_code=400, detail="Cannot set inactive template as default")

        # Update assistant's default_template_id
        update_result = (
            supabase.table("assistants")
            .update({"default_template_id": template_id})
            .eq("id", assistant_id)
            .execute()
        )

        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to update assistant default template")

        if template_id:
            return {
                "success": True,
                "message": f"Default template set for assistant '{nurse['full_name']}'",
                "default_template_id": template_id
            }
        else:
            return {
                "success": True,
                "message": f"Default template cleared for assistant '{nurse['full_name']}'",
                "default_template_id": None
            }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to set assistant default template")

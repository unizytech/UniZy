"""
Nurse Management Router

REST API endpoints for nurse CRUD operations.
"""

import os
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import uuid

from models.auth_models import ClientContext
from dependencies.auth import require_admin, get_current_client

from services.nurse_service import (
    get_all_nurses,
    search_nurses,
    get_nurse,
    create_nurse,
    update_nurse,
    deactivate_nurse,
    get_nurse_doctors,
    link_nurse_to_doctor,
    unlink_nurse_from_doctor
)
from services.nurse_templates_service import share_template_with_nurse
from services.supabase_service import supabase

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/nurses", tags=["Nurse Management"])


# ============================================================================
# Helper Functions
# ============================================================================

def _assign_default_template_to_nurse(nurse_id: str, nurse_name: str, hospital_id: Optional[str] = None) -> None:
    """
    Assign a default template to a newly created nurse.

    Resolution chain:
    1. Linked doctor's default (first active from nurse_doctors)
    2. Hospital default (hospitals.default_template_id)
    3. OP_CORE fallback (universal template)

    The template is shared via nurse_templates and set as nurses.default_template_id.
    Failures are logged but don't block nurse creation.

    Args:
        nurse_id: UUID of the newly created nurse
        nurse_name: Name of the nurse (for logging)
        hospital_id: Optional hospital UUID for hospital default lookup
    """
    try:
        template_id = None
        template_code = None
        source = None

        # 1. Try linked doctor's default
        try:
            from services.nurse_service import get_nurse_doctors
            nurse_doctors = get_nurse_doctors(nurse_id)
            for assoc in nurse_doctors:
                doctor_info = assoc.get("doctors", {})
                if not doctor_info:
                    continue
                linked_doctor_id = doctor_info.get("id")
                if linked_doctor_id:
                    doctor_record = (
                        supabase.table("doctors")
                        .select("default_template_id")
                        .eq("id", linked_doctor_id)
                        .limit(1)
                        .execute()
                    )
                    if doctor_record.data:
                        doc_default_id = doctor_record.data[0].get("default_template_id")
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
                                source = f"linked doctor {linked_doctor_id}"
                                break
        except Exception as e:
            logger.warning(f"[NURSE_CREATE] Error checking linked doctors for default: {e}")

        # 2. Try hospital default
        if not template_id and hospital_id:
            try:
                hospital_result = (
                    supabase.table("hospitals")
                    .select("default_template_id")
                    .eq("id", hospital_id)
                    .limit(1)
                    .execute()
                )
                if hospital_result.data:
                    hosp_default_id = hospital_result.data[0].get("default_template_id")
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
                            source = "hospital default"
            except Exception as e:
                logger.warning(f"[NURSE_CREATE] Error checking hospital default: {e}")

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
                f"[NURSE_CREATE] No default template found for nurse '{nurse_name}' (ID: {nurse_id})"
            )
            return

        # Share and set as default
        share_template_with_nurse(
            template_id=uuid.UUID(template_id),
            template_code=template_code,
            nurse_id=uuid.UUID(nurse_id),
        )

        try:
            supabase.table("nurses")\
                .update({"default_template_id": str(template_id)})\
                .eq("id", nurse_id)\
                .execute()
        except Exception as set_default_err:
            logger.warning(f"[NURSE_CREATE] Failed to set default template: {set_default_err}")

        logger.info(
            f"[NURSE_CREATE] Assigned {template_code} (from {source}) as default for nurse '{nurse_name}' (ID: {nurse_id})"
        )

    except Exception as e:
        logger.error(
            f"[NURSE_CREATE] Failed to assign default template for nurse '{nurse_name}': {e}"
        )


# ============================================================================
# Request/Response Models
# ============================================================================

class NurseCreateRequest(BaseModel):
    """Request model for creating a nurse"""
    email: str = Field(..., description="Nurse's email address")
    full_name: str = Field(..., min_length=2, max_length=255, description="Nurse's full name")
    qualification: Optional[str] = Field(None, max_length=100, description="Nursing qualification (RN, LPN, BSN)")
    hospital_id: Optional[str] = Field(None, description="Hospital UUID")


class NurseCreateWithHospitalRequest(BaseModel):
    """Request model for creating a nurse with hospital code lookup"""
    id: str = Field(..., description="Nurse UUID (provided by caller)")
    hospital_code: str = Field(..., min_length=1, max_length=50, description="Hospital code to lookup hospital_id")
    full_name: str = Field(..., min_length=2, max_length=255, description="Nurse's full name")
    email: str = Field(..., description="Nurse's email address")
    qualification: Optional[str] = Field(None, max_length=100, description="Nursing qualification (RN, LPN, BSN)")


class NurseCreateEHRRequest(BaseModel):
    """Request model for EHR integration - auto-generates UUID"""
    hospital_code: str = Field(..., min_length=1, max_length=50, description="Hospital code to lookup hospital_id")
    full_name: str = Field(..., min_length=2, max_length=255, description="Nurse's full name")
    email: str = Field(..., description="Nurse's email address")
    qualification: Optional[str] = Field(None, max_length=100, description="Nursing qualification (RN, LPN, BSN)")


class NurseUpdateRequest(BaseModel):
    """Request model for updating a nurse"""
    email: Optional[str] = Field(None, description="New email address")
    full_name: Optional[str] = Field(None, min_length=2, max_length=255, description="New full name")
    qualification: Optional[str] = Field(None, max_length=100, description="New qualification")
    hospital_id: Optional[str] = Field(None, description="New hospital UUID")
    is_active: Optional[bool] = Field(None, description="Active status")
    default_template_id: Optional[str] = Field(None, description="Default template UUID (null to clear)")


class SetNurseDefaultTemplateRequest(BaseModel):
    """Request model for setting nurse's default template"""
    template_id: Optional[str] = Field(None, description="Template UUID to set as default (null to clear)")


# ============================================================================
# Nurse CRUD Endpoints
# ============================================================================

@router.get("")
async def list_nurses(
    active_only: bool = Query(True, description="Filter by active status"),
    hospital_id: Optional[str] = Query(None, description="Filter by hospital"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get all nurses.

    **Query Parameters:**
    - `active_only`: Filter to show only active nurses (default: true)
    - `hospital_id`: Filter by hospital UUID (optional)

    **Returns:**
    - List of nurse records with metadata
    """
    try:
        nurses = get_all_nurses(is_active=active_only, hospital_id=hospital_id)

        return {
            "success": True,
            "nurses": nurses,
            "count": len(nurses)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch nurses")


@router.get("/search")
async def search_nurses_endpoint(
    q: str = Query(..., min_length=2, description="Search query (name or email)"),
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Search nurses by name or email.

    **Query Parameters:**
    - `q`: Search term (case-insensitive, minimum 2 characters)

    **Returns:**
    - List of matching nurse records
    """
    try:
        results = search_nurses(q)

        return {
            "success": True,
            "query": q,
            "nurses": results,
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Search failed")


@router.get("/list-all")
async def list_all_nurses_for_sharing(
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get list of all active nurses for sharing templates.

    Returns simplified nurse list with id, name, email, and qualification.
    Used by UI to display nurse checkboxes.

    **Response:**
    ```json
    {
        "success": true,
        "nurses": [
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
            supabase.table("nurses")
            .select("id, full_name, email, qualification, hospital_id")
            .eq("is_active", True)
            .order("full_name")
            .execute()
        )

        return {
            "success": True,
            "nurses": response.data or [],
            "count": len(response.data or [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch nurses")


@router.get("/{nurse_id}")
async def get_nurse_endpoint(
    nurse_id: str,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Get nurse by ID.

    **Path Parameters:**
    - `nurse_id`: Nurse UUID

    **Returns:**
    - Nurse record with full details
    """
    try:
        nurse = get_nurse(nurse_id)

        if not nurse:
            raise HTTPException(status_code=404, detail="Nurse not found")

        return {
            "success": True,
            "nurse": nurse
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch nurse")


@router.post("")
async def create_nurse_endpoint(
    request: NurseCreateRequest,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Create new nurse with random UUID.

    **Request Body:**
    ```json
    {
        "email": "nurse@hospital.com",
        "full_name": "Jane Smith",
        "qualification": "RN",
        "hospital_id": "hospital-uuid"
    }
    ```

    **Returns:**
    - Created nurse record with generated UUID

    **Notes:**
    - No Supabase auth integration (uses random UUID)
    - Email must be unique
    """
    try:
        nurse = create_nurse(
            email=request.email,
            full_name=request.full_name,
            qualification=request.qualification,
            hospital_id=request.hospital_id
        )

        # Assign default template to newly created nurse
        _assign_default_template_to_nurse(nurse["id"], request.full_name, request.hospital_id)

        return {
            "success": True,
            "message": f"Nurse '{request.full_name}' created successfully",
            "nurse": nurse
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create nurse")


@router.post("/with-hospital")
async def create_nurse_with_hospital(
    request: NurseCreateWithHospitalRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Create new nurse with provided UUID and hospital code lookup.

    **Auth:** Admin, Web, and EHR (EHR restricted to own hospital)

    **Request Body:**
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "hospital_code": "HOSP001",
        "full_name": "Jane Smith",
        "email": "nurse@hospital.com",
        "qualification": "RN"
    }
    ```

    **Returns:**
    - success: True if nurse created
    - message: Success message
    - nurse_id: UUID of created nurse

    **Notes:**
    - UUID is provided by caller (not auto-generated)
    - hospital_id is looked up from hospitals table using hospital_code
    - Email must be unique
    """
    try:
        from services.supabase_service import supabase
        from datetime import datetime

        # Validate UUID format
        try:
            nurse_uuid = uuid.UUID(request.id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID format")

        # Lookup hospital_id from hospital_code
        hospital_response = (
            supabase.table("hospitals")
            .select("id")
            .eq("hospital_code", request.hospital_code)
            .eq("is_active", True)
            .execute()
        )

        if not hospital_response.data or len(hospital_response.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="Hospital not found or inactive"
            )

        hospital_id = hospital_response.data[0]["id"]

        # EHR clients can only create nurses in their own hospital
        if client.client_type == "ehr":
            if client.hospital_id is None or str(client.hospital_id) != hospital_id:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )

        # Check if nurse ID already exists
        existing_id = (
            supabase.table("nurses")
            .select("id")
            .eq("id", str(nurse_uuid))
            .execute()
        )

        if existing_id.data and len(existing_id.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Nurse with this ID already exists"
            )

        # Check if email already exists
        existing_email = (
            supabase.table("nurses")
            .select("id")
            .eq("email", request.email)
            .execute()
        )

        if existing_email.data and len(existing_email.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Nurse with this email already exists"
            )

        # Create nurse with provided UUID and hospital_id
        nurse_data = {
            "id": str(nurse_uuid),
            "hospital_id": hospital_id,
            "full_name": request.full_name,
            "email": request.email,
            "qualification": request.qualification,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        response = supabase.table("nurses").insert(nurse_data).execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to create nurse")

        # Assign default template to newly created nurse
        _assign_default_template_to_nurse(str(nurse_uuid), request.full_name, hospital_id)

        return {
            "success": True,
            "message": f"Nurse '{request.full_name}' created successfully",
            "nurse_id": str(nurse_uuid)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create nurse")


@router.post("/ehr")
async def create_nurse_ehr(
    request: NurseCreateEHRRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Create new nurse for EHR integration with auto-generated UUID.

    **Auth:** Admin, Web, and EHR (EHR restricted to own hospital)

    **Request Body:**
    ```json
    {
        "hospital_code": "HOSP001",
        "full_name": "Jane Smith",
        "email": "nurse@hospital.com",
        "qualification": "RN"
    }
    ```

    **Returns:**
    - success: True if nurse created
    - message: Success message
    - nurse_id: Auto-generated UUID of created nurse

    **Notes:**
    - UUID is auto-generated (not provided by caller)
    - hospital_id is looked up from hospitals table using hospital_code
    - Email must be unique
    - Returns 409 if email already exists
    - Returns 404 if hospital_code not found
    """
    try:
        from datetime import datetime

        # Generate new UUID
        nurse_uuid = uuid.uuid4()

        # Lookup hospital_id from hospital_code
        hospital_response = (
            supabase.table("hospitals")
            .select("id")
            .eq("hospital_code", request.hospital_code)
            .eq("is_active", True)
            .execute()
        )

        if not hospital_response.data or len(hospital_response.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="Hospital not found or inactive"
            )

        hospital_id = hospital_response.data[0]["id"]

        # EHR clients can only create nurses in their own hospital
        if client.client_type == "ehr":
            if client.hospital_id is None or str(client.hospital_id) != hospital_id:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )

        # Check if email already exists
        existing_email = (
            supabase.table("nurses")
            .select("id")
            .eq("email", request.email)
            .execute()
        )

        if existing_email.data and len(existing_email.data) > 0:
            raise HTTPException(
                status_code=409,
                detail="Nurse with this email already exists"
            )

        # Create nurse with auto-generated UUID and hospital_id
        nurse_data = {
            "id": str(nurse_uuid),
            "hospital_id": hospital_id,
            "full_name": request.full_name,
            "email": request.email,
            "qualification": request.qualification,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        response = supabase.table("nurses").insert(nurse_data).execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to create nurse")

        # Assign default template to newly created nurse
        _assign_default_template_to_nurse(str(nurse_uuid), request.full_name, hospital_id)

        return {
            "success": True,
            "message": f"Nurse '{request.full_name}' created successfully",
            "nurse_id": str(nurse_uuid)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create nurse")


@router.put("/{nurse_id}")
async def update_nurse_endpoint(
    nurse_id: str,
    request: NurseUpdateRequest,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Update nurse information.

    **Auth:** Admin, Web, and EHR (EHR restricted to nurses in own hospital)

    **Path Parameters:**
    - `nurse_id`: Nurse UUID

    **Request Body:**
    - Any fields to update (all optional)

    **Returns:**
    - Updated nurse record
    """
    try:
        from services.supabase_service import supabase

        # EHR clients can only update nurses in their own hospital
        if client.client_type == "ehr":
            nurse_result = (
                supabase.table("nurses")
                .select("hospital_id")
                .eq("id", nurse_id)
                .execute()
            )
            if not nurse_result.data:
                raise HTTPException(status_code=404, detail="Nurse not found")

            nurse_hospital_id = nurse_result.data[0].get("hospital_id")
            if client.hospital_id is None or str(client.hospital_id) != nurse_hospital_id:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )

        # Handle default_template_id separately (not in nurse_service.update_nurse)
        if request.default_template_id is not None:
            supabase.table("nurses")\
                .update({"default_template_id": request.default_template_id if request.default_template_id else None})\
                .eq("id", nurse_id)\
                .execute()

        nurse = update_nurse(
            nurse_id=nurse_id,
            email=request.email,
            full_name=request.full_name,
            qualification=request.qualification,
            hospital_id=request.hospital_id,
            is_active=request.is_active
        )

        return {
            "success": True,
            "message": "Nurse updated successfully",
            "nurse": nurse
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update nurse")


@router.delete("/{nurse_id}")
async def deactivate_nurse_endpoint(
    nurse_id: str,
    client: ClientContext = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Soft delete nurse (set is_active to false).

    **Path Parameters:**
    - `nurse_id`: Nurse UUID

    **Returns:**
    - Updated nurse record with is_active=false

    **Notes:**
    - This is a soft delete - nurse record is preserved
    - Nurse will not appear in active nurse lists
    """
    try:
        nurse = deactivate_nurse(nurse_id)

        return {
            "success": True,
            "message": f"Nurse '{nurse['full_name']}' deactivated successfully",
            "nurse": nurse
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to deactivate nurse")


# ============================================================================
# Nurse-Doctor Association Endpoints
# ============================================================================

@router.get("/{nurse_id}/doctors")
async def list_nurse_doctors(
    nurse_id: str,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Get all doctors associated with a nurse.

    **Path Parameters:**
    - `nurse_id`: Nurse UUID

    **Returns:**
    - List of doctor records with association info
    """
    try:
        # Verify nurse exists
        nurse = get_nurse(nurse_id)
        if not nurse:
            raise HTTPException(status_code=404, detail="Nurse not found")

        associations = get_nurse_doctors(nurse_id)

        # Extract doctor info from associations
        doctors = []
        for assoc in associations:
            doctor_info = assoc.get("doctors", {})
            if doctor_info:
                doctors.append({
                    "association_id": assoc.get("id"),
                    "doctor_id": assoc.get("doctor_id"),
                    "doctor_name": doctor_info.get("full_name"),  # Frontend expects doctor_name
                    "email": doctor_info.get("email"),
                    "specialization": doctor_info.get("specialization"),
                    "hospital_id": doctor_info.get("hospital_id"),
                    "is_active": assoc.get("is_active", True),
                    "created_at": assoc.get("created_at")
                })

        return {
            "success": True,
            "nurse_id": nurse_id,
            "doctors": doctors,
            "count": len(doctors)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch nurse doctors")


@router.post("/{nurse_id}/doctors/{doctor_id}")
async def link_nurse_to_doctor_endpoint(
    nurse_id: str,
    doctor_id: str,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Link a nurse to a supervising doctor.

    **Auth:** Admin + Web + EHR (EHR restricted to nurses in own hospital)

    **Path Parameters:**
    - `nurse_id`: Nurse UUID
    - `doctor_id`: Doctor UUID

    **Returns:**
    - Created/updated association record

    **Notes:**
    - If association exists but is inactive, it will be reactivated
    - Idempotent - calling multiple times has same result
    """
    try:
        # EHR clients can only link nurses in their own hospital
        if client.client_type == "ehr":
            nurse_result = (
                supabase.table("nurses")
                .select("hospital_id")
                .eq("id", nurse_id)
                .execute()
            )
            if not nurse_result.data:
                raise HTTPException(status_code=404, detail="Nurse not found")
            nurse_hospital_id = nurse_result.data[0].get("hospital_id")
            if client.hospital_id is None or str(client.hospital_id) != nurse_hospital_id:
                raise HTTPException(status_code=403, detail="Access denied")

        association = link_nurse_to_doctor(nurse_id, doctor_id)

        # Assign doctor's default template to nurse if nurse has no default
        # or currently has a PRESCREEN template
        try:
            nurse_record = supabase.table("nurses")\
                .select("id, default_template_id, hospital_id")\
                .eq("id", nurse_id).limit(1).execute()
            if nurse_record.data:
                nurse = nurse_record.data[0]
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
                    _assign_default_template_to_nurse(
                        nurse_id, "", nurse.get("hospital_id")
                    )
                    logger.info(f"[NURSE_LINK] Reassigned default template for nurse {nurse_id} after linking doctor {doctor_id}")
        except Exception as e:
            logger.warning(f"[NURSE_LINK] Template reassignment after doctor link failed: {e}")

        return {
            "success": True,
            "message": f"Nurse linked to doctor successfully",
            "association": association
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to link nurse to doctor")


@router.delete("/{nurse_id}/doctors/{doctor_id}")
async def unlink_nurse_from_doctor_endpoint(
    nurse_id: str,
    doctor_id: str,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Unlink a nurse from a doctor (soft delete).

    **Auth:** Admin + Web + EHR (EHR restricted to nurses in own hospital)

    **Path Parameters:**
    - `nurse_id`: Nurse UUID
    - `doctor_id`: Doctor UUID

    **Returns:**
    - Updated association record with is_active=false

    **Notes:**
    - This is a soft delete - association record is preserved
    - Can be relinked later
    """
    try:
        # EHR clients can only unlink nurses in their own hospital
        if client.client_type == "ehr":
            nurse_result = (
                supabase.table("nurses")
                .select("hospital_id")
                .eq("id", nurse_id)
                .execute()
            )
            if not nurse_result.data:
                raise HTTPException(status_code=404, detail="Nurse not found")
            nurse_hospital_id = nurse_result.data[0].get("hospital_id")
            if client.hospital_id is None or str(client.hospital_id) != nurse_hospital_id:
                raise HTTPException(status_code=403, detail="Access denied")

        association = unlink_nurse_from_doctor(nurse_id, doctor_id)

        return {
            "success": True,
            "message": "Nurse unlinked from doctor successfully",
            "association": association
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to unlink nurse from doctor")


# ============================================================================
# Nurse Default Template Endpoints
# ============================================================================

@router.put("/{nurse_id}/default-template")
async def set_nurse_default_template(
    nurse_id: str,
    body: SetNurseDefaultTemplateRequest = None,
    client: ClientContext = Depends(get_current_client)
) -> Dict[str, Any]:
    """
    Set or clear the default template for a nurse.

    **Path Parameters:**
    - nurse_id: Nurse UUID

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
    - Nurse default takes highest priority in nurse fallback chain
    - The template must be accessible to the nurse (is_active=True)
    """
    from services.nurse_templates_service import validate_nurse_template_access

    try:
        nurse_uuid = uuid.UUID(nurse_id)

        # Validate nurse exists
        nurse_result = (
            supabase.table("nurses")
            .select("id, full_name, hospital_id")
            .eq("id", nurse_id)
            .execute()
        )

        if not nurse_result.data or len(nurse_result.data) == 0:
            raise HTTPException(status_code=404, detail="Nurse not found")

        nurse = nurse_result.data[0]
        template_id = body.template_id if body else None

        # EHR clients can only update nurses in their own hospital
        if client.client_type == "ehr":
            nurse_hospital_id = nurse.get("hospital_id")
            if client.hospital_id is None or str(client.hospital_id) != nurse_hospital_id:
                raise HTTPException(status_code=403, detail="Access denied")

        # If template_id provided, validate nurse has 'use' access
        if template_id:
            has_access = validate_nurse_template_access(nurse_id, template_id)
            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail="Nurse does not have 'use' access to this template"
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

        # Update nurse's default_template_id
        update_result = (
            supabase.table("nurses")
            .update({"default_template_id": template_id})
            .eq("id", nurse_id)
            .execute()
        )

        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to update nurse default template")

        if template_id:
            return {
                "success": True,
                "message": f"Default template set for nurse '{nurse['full_name']}'",
                "default_template_id": template_id
            }
        else:
            return {
                "success": True,
                "message": f"Default template cleared for nurse '{nurse['full_name']}'",
                "default_template_id": None
            }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to set nurse default template")

"""
Billing Router - Bill Generation and Management API

REST API endpoints for automated bill generation from extraction data,
bill CRUD operations, and bill confirmation workflow.
"""

import os
import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends, Path, Query, Request
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime

from services.supabase_service import supabase, get_doctor_hospital_id_cached
from services.billing_service import generate_bill, generate_merged_bill

logger = logging.getLogger(__name__)

# ============================================================================
# Auth Setup (conditional, same pattern as merge.py)
# ============================================================================
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"

if AUTH_ENABLED:
    from dependencies.auth import get_current_client
    from models.auth_models import ClientContext

    async def verify_billing_access(request: Request):
        """Verify the client has billing access (Admin + Web + EHR)."""
        client = get_current_client(request)
        if client.client_type not in ("admin", "web_app", "ehr"):
            raise HTTPException(status_code=403, detail="Access denied")
        return client
else:
    async def verify_billing_access(request: Request = None):
        return None

router = APIRouter(prefix="/api/v1/billing", tags=["Billing"])


# ============================================================================
# Request/Response Models
# ============================================================================

class LineItemUpdateRequest(BaseModel):
    """Request model for updating a bill line item"""
    unit_price: Optional[float] = Field(None, description="Updated unit price")
    quantity: Optional[float] = Field(None, description="Updated quantity")
    billing_action: Optional[str] = Field(None, description="Updated billing action: auto_billed, pending_review, flagged_manual")
    notes: Optional[str] = Field(None, description="Updated notes")


VALID_CATEGORIES = {
    "registration", "consultation", "pharmacy", "lab", "radiology",
    "procedure", "room", "admission", "miscellaneous",
}


class LineItemCreateRequest(BaseModel):
    """Request model for adding a line item to a draft bill"""
    category: str = Field(..., description="Item category: registration, consultation, pharmacy, lab, radiology, procedure, room, admission, miscellaneous")
    description: str = Field(..., description="Item description")
    quantity: float = Field(1, description="Quantity (default 1)")
    unit_price: Optional[float] = Field(None, description="Price per unit")
    billing_action: str = Field("pending_review", description="Billing action: auto_billed, pending_review, flagged_manual")
    item_code: Optional[str] = Field(None, description="CPT code or item code")
    notes: Optional[str] = Field(None, description="Optional notes")


class BillGenerateRequest(BaseModel):
    """Optional fields for bill generation"""
    visit_id: Optional[str] = Field(None, description="EHR visit ID")
    visit_date: Optional[str] = Field(None, description="Visit date (ISO format)")
    billed_by: Optional[str] = Field(None, description="User who created/billed")


class BillUpdateRequest(BaseModel):
    """Request model for updating bill-level fields"""
    visit_id: Optional[str] = Field(None, description="EHR visit ID")
    visit_date: Optional[str] = Field(None, description="Visit date (ISO format)")
    billed_by: Optional[str] = Field(None, description="User who created/billed")


class StandaloneBillCreateRequest(BaseModel):
    """Request model for creating a standalone bill (no extraction)"""
    hospital_code: str = Field(..., description="Hospital code")
    patient_id: Optional[str] = Field(None, description="Patient external ID (UHID)")
    doctor_id: Optional[str] = Field(None, description="Doctor UUID")
    bill_type: str = Field("OP", description="Bill type: OP or IP")
    consultation_type_code: Optional[str] = Field(None, description="Consultation type code")
    visit_id: str = Field(..., description="EHR visit ID")
    visit_date: str = Field(..., description="Visit date (ISO format)")
    billed_by: str = Field(..., description="User who created the bill")
    line_items: Optional[List[LineItemCreateRequest]] = Field(None, description="Initial line items")


# ============================================================================
# Bill Generation Endpoints
# ============================================================================

@router.post("/generate/{extraction_id}")
async def generate_bill_endpoint(
    request: Request,
    extraction_id: str = Path(..., description="Extraction UUID"),
    body: Optional[BillGenerateRequest] = None,
    _auth=Depends(verify_billing_access),
) -> Dict[str, Any]:
    """
    Generate a bill from an extraction.

    **Auth:** Admin + Web + EHR

    Reads the extraction data, resolves hospital/doctor/patient,
    and generates an itemized bill with line items.

    Returns the created bill with all line items.
    """
    try:
        # Check if bill already exists for this extraction
        existing = (
            supabase.table("bills")
            .select("id, bill_status")
            .eq("extraction_id", extraction_id)
            .neq("bill_status", "superseded")
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=409,
                detail=f"Bill already exists for this extraction (id: {existing.data[0]['id']}, status: {existing.data[0]['bill_status']}). Use /regenerate to create a new one."
            )

        # Fetch extraction
        extraction = _get_extraction(extraction_id)

        # Resolve IDs
        doctor_id = extraction.get("doctor_id")
        patient_id = extraction.get("patient_id")
        hospital_id = _resolve_hospital_id(doctor_id, extraction)

        if not hospital_id:
            raise HTTPException(status_code=400, detail="Cannot determine hospital_id for this extraction")

        # Get consultation type code
        consultation_type_code = _get_consultation_type_code(extraction)

        # Get extraction data
        extraction_data = extraction.get("original_extraction_json") or extraction.get("edited_extraction_json") or {}

        bill = generate_bill(
            extraction_id=extraction_id,
            hospital_id=hospital_id,
            doctor_id=doctor_id,
            patient_id=patient_id,
            extraction_data=extraction_data,
            consultation_type_code=consultation_type_code,
            is_merged=extraction.get("is_merged", False),
            visit_id=body.visit_id if body else None,
            visit_date=body.visit_date if body else None,
            billed_by=body.billed_by if body else None,
        )

        return {
            "success": True,
            "message": "Bill generated successfully",
            "bill": bill,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Billing] Failed to generate bill for extraction {extraction_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate bill: {str(e)}")


@router.post("/generate-merged/{extraction_id}")
async def generate_merged_bill_endpoint(
    request: Request,
    extraction_id: str = Path(..., description="Merged extraction UUID"),
    body: Optional[BillGenerateRequest] = None,
    _auth=Depends(verify_billing_access),
) -> Dict[str, Any]:
    """
    Generate a bill from a merged extraction and supersede source bills.

    **Auth:** Admin + Web + EHR

    Validates the extraction is merged, finds source extractions,
    generates a cumulative bill, and marks source bills as superseded.
    """
    try:
        # Check if bill already exists
        existing = (
            supabase.table("bills")
            .select("id, bill_status")
            .eq("extraction_id", extraction_id)
            .neq("bill_status", "superseded")
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=409,
                detail=f"Bill already exists for this extraction (id: {existing.data[0]['id']}). Use /regenerate to create a new one."
            )

        # Fetch extraction and validate it's merged
        extraction = _get_extraction(extraction_id)

        if not extraction.get("is_merged"):
            raise HTTPException(
                status_code=400,
                detail="This extraction is not a merged extraction. Use /generate/{extraction_id} instead."
            )

        # Get source extraction IDs from merge_metadata
        merge_metadata = extraction.get("merge_metadata") or {}
        source_extraction_ids = merge_metadata.get("source_extraction_ids", [])

        if not source_extraction_ids:
            # Try extraction_relationships table
            try:
                rel_result = (
                    supabase.table("extraction_relationships")
                    .select("source_extraction_id")
                    .eq("merged_extraction_id", extraction_id)
                    .execute()
                )
                if rel_result.data:
                    source_extraction_ids = [r["source_extraction_id"] for r in rel_result.data]
            except Exception:
                pass

        # Resolve IDs
        doctor_id = extraction.get("doctor_id")
        patient_id = extraction.get("patient_id")
        hospital_id = _resolve_hospital_id(doctor_id, extraction)

        if not hospital_id:
            raise HTTPException(status_code=400, detail="Cannot determine hospital_id for this extraction")

        consultation_type_code = _get_consultation_type_code(extraction)
        extraction_data = extraction.get("original_extraction_json") or extraction.get("edited_extraction_json") or {}

        bill = generate_merged_bill(
            extraction_id=extraction_id,
            source_extraction_ids=source_extraction_ids,
            hospital_id=hospital_id,
            doctor_id=doctor_id,
            patient_id=patient_id,
            extraction_data=extraction_data,
            consultation_type_code=consultation_type_code,
            visit_id=body.visit_id if body else None,
            visit_date=body.visit_date if body else None,
            billed_by=body.billed_by if body else None,
        )

        return {
            "success": True,
            "message": "Merged bill generated successfully",
            "bill": bill,
            "superseded_count": len(source_extraction_ids),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Billing] Failed to generate merged bill for {extraction_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate merged bill: {str(e)}")


@router.post("/regenerate/{extraction_id}")
async def regenerate_bill_endpoint(
    request: Request,
    extraction_id: str = Path(..., description="Extraction UUID"),
    body: Optional[BillGenerateRequest] = None,
    _auth=Depends(verify_billing_access),
) -> Dict[str, Any]:
    """
    Delete existing draft bill and regenerate.

    **Auth:** Admin + Web + EHR

    Only deletes draft bills. Confirmed bills cannot be regenerated.
    """
    try:
        # Check for existing bill
        existing = (
            supabase.table("bills")
            .select("id, bill_status")
            .eq("extraction_id", extraction_id)
            .neq("bill_status", "superseded")
            .execute()
        )

        if existing.data:
            bill = existing.data[0]
            if bill["bill_status"] == "confirmed":
                raise HTTPException(
                    status_code=400,
                    detail="Cannot regenerate a confirmed bill. Create a new bill instead."
                )

            # Delete the draft bill (cascade deletes line items)
            supabase.table("bills").delete().eq("id", bill["id"]).execute()
            logger.info(f"[Billing] Deleted draft bill {bill['id']} for regeneration")

        # Fetch extraction
        extraction = _get_extraction(extraction_id)
        doctor_id = extraction.get("doctor_id")
        patient_id = extraction.get("patient_id")
        hospital_id = _resolve_hospital_id(doctor_id, extraction)

        if not hospital_id:
            raise HTTPException(status_code=400, detail="Cannot determine hospital_id for this extraction")

        consultation_type_code = _get_consultation_type_code(extraction)
        extraction_data = extraction.get("original_extraction_json") or extraction.get("edited_extraction_json") or {}

        bill = generate_bill(
            extraction_id=extraction_id,
            hospital_id=hospital_id,
            doctor_id=doctor_id,
            patient_id=patient_id,
            extraction_data=extraction_data,
            consultation_type_code=consultation_type_code,
            is_merged=extraction.get("is_merged", False),
            visit_id=body.visit_id if body else None,
            visit_date=body.visit_date if body else None,
            billed_by=body.billed_by if body else None,
        )

        return {
            "success": True,
            "message": "Bill regenerated successfully",
            "bill": bill,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Billing] Failed to regenerate bill for {extraction_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to regenerate bill: {str(e)}")


# ============================================================================
# Standalone Bill Creation
# ============================================================================

@router.post("/create")
async def create_standalone_bill(
    request: Request,
    body: StandaloneBillCreateRequest,
    _auth=Depends(verify_billing_access),
) -> Dict[str, Any]:
    """
    Create a standalone bill with no extraction (e.g., registration-only bills).

    **Auth:** Admin + Web + EHR

    Creates a bill record with extraction_id = NULL and optional line items.
    """
    try:
        # Resolve hospital_code to hospital_id
        hospital_check = (
            supabase.table("hospitals")
            .select("id")
            .eq("hospital_code", body.hospital_code)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if not hospital_check.data:
            raise HTTPException(status_code=404, detail=f"Hospital not found or inactive: {body.hospital_code}")

        hospital_id = hospital_check.data[0]["id"]

        # Resolve patient UHID to internal UUID if provided
        patient_uuid = None
        if body.patient_id:
            patient_query = (
                supabase.table("patients")
                .select("id")
                .eq("patient_id", body.patient_id)
                .eq("hospital_id", hospital_id)
                .limit(1)
                .execute()
            )
            if not patient_query.data:
                raise HTTPException(status_code=404, detail=f"No patient found with UHID: {body.patient_id}")
            patient_uuid = patient_query.data[0]["id"]

        # Validate bill_type
        if body.bill_type not in ("OP", "IP"):
            raise HTTPException(status_code=400, detail="bill_type must be 'OP' or 'IP'")

        # Validate line items if provided
        line_item_rows = []
        if body.line_items:
            for item in body.line_items:
                if item.category not in VALID_CATEGORIES:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid category '{item.category}'. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}",
                    )
                if item.billing_action not in ("auto_billed", "pending_review", "flagged_manual"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid billing_action '{item.billing_action}'",
                    )

                unit_price = item.unit_price or 0
                total_price = round(float(unit_price) * float(item.quantity), 2)

                line_item_rows.append({
                    "id": str(uuid.uuid4()),
                    "category": item.category,
                    "description": item.description,
                    "item_code": item.item_code,
                    "quantity": item.quantity,
                    "unit_price": unit_price,
                    "total_price": total_price,
                    "confidence": "high",
                    "source_segment": "manual",
                    "billing_action": item.billing_action,
                    "notes": item.notes,
                })

        # Calculate totals from line items
        total_amount = 0.0
        auto_billed_amount = 0.0
        pending_review_amount = 0.0
        flagged_amount = 0.0

        for item in line_item_rows:
            item_total = float(item.get("total_price") or 0)
            total_amount += item_total
            action = item.get("billing_action", "pending_review")
            if action == "auto_billed":
                auto_billed_amount += item_total
            elif action == "pending_review":
                pending_review_amount += item_total
            elif action == "flagged_manual":
                flagged_amount += item_total

        # Create bill record
        bill_data = {
            "extraction_id": None,
            "hospital_id": hospital_id,
            "patient_id": patient_uuid,
            "doctor_id": body.doctor_id,
            "bill_type": body.bill_type,
            "bill_status": "draft",
            "consultation_type_code": body.consultation_type_code,
            "is_merged_bill": False,
            "total_amount": round(total_amount, 2),
            "auto_billed_amount": round(auto_billed_amount, 2),
            "pending_review_amount": round(pending_review_amount, 2),
            "flagged_amount": round(flagged_amount, 2),
            "generation_metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "line_item_count": len(line_item_rows),
                "standalone": True,
            },
        }

        bill_data["visit_id"] = body.visit_id
        bill_data["visit_date"] = body.visit_date
        bill_data["billed_by"] = body.billed_by

        bill_result = supabase.table("bills").insert(bill_data).execute()
        if not bill_result.data:
            raise HTTPException(status_code=500, detail="Failed to create bill record")

        bill = bill_result.data[0]
        bill_id = bill["id"]

        # Insert line items
        if line_item_rows:
            for item in line_item_rows:
                item["bill_id"] = bill_id
            supabase.table("bill_line_items").insert(line_item_rows).execute()

        # Re-fetch with line items
        items_result = (
            supabase.table("bill_line_items")
            .select("*")
            .eq("bill_id", bill_id)
            .order("created_at")
            .execute()
        )
        bill["line_items"] = items_result.data or []

        logger.info(f"[Billing] Created standalone {body.bill_type} bill {bill_id} for hospital {body.hospital_code}: {len(line_item_rows)} items")

        return {
            "success": True,
            "message": "Standalone bill created successfully",
            "bill": bill,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Billing] Failed to create standalone bill: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create standalone bill: {str(e)}")


# ============================================================================
# Bill Read Endpoints
# ============================================================================

@router.get("/extraction/{extraction_id}")
async def get_bill_by_extraction(
    request: Request,
    extraction_id: str = Path(..., description="Extraction UUID"),
    _auth=Depends(verify_billing_access),
) -> Dict[str, Any]:
    """
    Get bill for an extraction.

    **Auth:** Admin + Web + EHR
    """
    try:
        result = (
            supabase.table("bills")
            .select("*")
            .eq("extraction_id", extraction_id)
            .neq("bill_status", "superseded")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="No bill found for this extraction")

        bill = result.data[0]

        # Fetch line items
        items = (
            supabase.table("bill_line_items")
            .select("*")
            .eq("bill_id", bill["id"])
            .order("created_at")
            .execute()
        )

        bill["line_items"] = items.data or []

        return {
            "success": True,
            "bill": bill,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch bill")


@router.get("/visit/{visit_id}")
async def get_bills_by_visit(
    request: Request,
    visit_id: str = Path(..., description="EHR visit ID"),
    include_superseded: bool = Query(False, description="Include superseded bills"),
    _auth=Depends(verify_billing_access),
) -> Dict[str, Any]:
    """
    Get all bills for a visit ID.

    **Auth:** Admin + Web + EHR
    """
    try:
        query = (
            supabase.table("bills")
            .select("*")
            .eq("visit_id", visit_id)
            .order("created_at", desc=True)
        )

        if not include_superseded:
            query = query.neq("bill_status", "superseded")

        result = query.execute()

        if not result.data:
            raise HTTPException(status_code=404, detail=f"No bills found for visit_id: {visit_id}")

        # Fetch line items for each bill
        for bill in result.data:
            items = (
                supabase.table("bill_line_items")
                .select("*")
                .eq("bill_id", bill["id"])
                .order("created_at")
                .execute()
            )
            bill["line_items"] = items.data or []

        return {
            "success": True,
            "bills": result.data,
            "count": len(result.data),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Billing] Failed to fetch bills for visit_id {visit_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch visit bills")


@router.get("/patient/{patient_id}")
async def get_bills_by_patient(
    request: Request,
    patient_id: str = Path(..., description="Patient external ID (UHID)"),
    hospital_code: Optional[str] = Query(None, description="Hospital code to scope patient lookup"),
    visit_id: Optional[str] = Query(None, description="Filter by EHR visit ID"),
    visit_date: Optional[str] = Query(None, description="Filter by visit date (ISO format)"),
    billed_by: Optional[str] = Query(None, description="Filter by billed_by user"),
    include_superseded: bool = Query(False, description="Include superseded bills"),
    _auth=Depends(verify_billing_access),
) -> Dict[str, Any]:
    """
    List all bills for a patient by UHID (external patient ID).

    **Auth:** Admin + Web + EHR
    """
    try:
        # Resolve hospital_code to hospital_id if provided
        hospital_id = None
        if hospital_code:
            hospital_result = (
                supabase.table("hospitals")
                .select("id")
                .eq("hospital_code", hospital_code)
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            if not hospital_result.data:
                raise HTTPException(status_code=404, detail=f"Hospital not found or inactive: {hospital_code}")
            hospital_id = hospital_result.data[0]["id"]

        # Resolve UHID to internal patient UUID(s)
        patient_query = (
            supabase.table("patients")
            .select("id")
            .eq("patient_id", patient_id)
        )
        if hospital_id:
            patient_query = patient_query.eq("hospital_id", hospital_id)

        patient_result = patient_query.execute()

        if not patient_result.data:
            raise HTTPException(status_code=404, detail=f"No patient found with UHID: {patient_id}")

        patient_uuids = [p["id"] for p in patient_result.data]

        query = (
            supabase.table("bills")
            .select("*")
            .in_("patient_id", patient_uuids)
            .order("created_at", desc=True)
        )

        if visit_id:
            query = query.eq("visit_id", visit_id)
        if visit_date:
            query = query.eq("visit_date", visit_date)
        if billed_by:
            query = query.eq("billed_by", billed_by)

        if not include_superseded:
            query = query.neq("bill_status", "superseded")

        result = query.execute()

        return {
            "success": True,
            "bills": result.data or [],
            "count": len(result.data or []),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Billing] Failed to fetch bills for patient UHID {patient_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch patient bills")


@router.get("/{bill_id}")
async def get_bill(
    request: Request,
    bill_id: str = Path(..., description="Bill UUID"),
    _auth=Depends(verify_billing_access),
) -> Dict[str, Any]:
    """
    Get a bill with all line items.

    **Auth:** Admin + Web + EHR
    """
    try:
        result = (
            supabase.table("bills")
            .select("*")
            .eq("id", bill_id)
            .limit(1)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Bill not found")

        bill = result.data[0]

        # Fetch line items
        items = (
            supabase.table("bill_line_items")
            .select("*")
            .eq("bill_id", bill_id)
            .order("created_at")
            .execute()
        )

        bill["line_items"] = items.data or []

        return {
            "success": True,
            "bill": bill,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch bill")


# ============================================================================
# Bill Update Endpoints
# ============================================================================

@router.patch("/{bill_id}")
async def update_bill(
    request: Request,
    bill_id: str = Path(..., description="Bill UUID"),
    body: BillUpdateRequest = ...,
    _auth=Depends(verify_billing_access),
) -> Dict[str, Any]:
    """
    Update bill-level fields (visit_id, visit_date, billed_by).

    **Auth:** Admin + Web + EHR
    """
    try:
        # Verify bill exists and is draft
        bill_check = (
            supabase.table("bills")
            .select("id, bill_status")
            .eq("id", bill_id)
            .limit(1)
            .execute()
        )

        if not bill_check.data:
            raise HTTPException(status_code=404, detail="Bill not found")

        status = bill_check.data[0]["bill_status"]
        if status == "confirmed":
            raise HTTPException(status_code=400, detail="Cannot modify a confirmed bill")
        if status == "superseded":
            raise HTTPException(status_code=400, detail="Cannot modify a superseded bill")

        update_data = {}
        if body.visit_id is not None:
            update_data["visit_id"] = body.visit_id
        if body.visit_date is not None:
            update_data["visit_date"] = body.visit_date
        if body.billed_by is not None:
            update_data["billed_by"] = body.billed_by

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        update_data["updated_at"] = datetime.utcnow().isoformat()

        result = (
            supabase.table("bills")
            .update(update_data)
            .eq("id", bill_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update bill")

        return {
            "success": True,
            "message": "Bill updated",
            "bill": result.data[0],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Billing] Failed to update bill {bill_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update bill")


@router.put("/{bill_id}/line-items/{line_item_id}")
async def update_line_item(
    request: Request,
    bill_id: str = Path(..., description="Bill UUID"),
    line_item_id: str = Path(..., description="Line item UUID"),
    update: LineItemUpdateRequest = ...,
    _auth=Depends(verify_billing_access),
) -> Dict[str, Any]:
    """
    Update a bill line item (price, quantity, action).

    **Auth:** Admin + Web + EHR
    """
    try:
        # Verify bill exists and is draft
        bill_check = (
            supabase.table("bills")
            .select("id, bill_status")
            .eq("id", bill_id)
            .limit(1)
            .execute()
        )

        if not bill_check.data:
            raise HTTPException(status_code=404, detail="Bill not found")

        if bill_check.data[0]["bill_status"] == "confirmed":
            raise HTTPException(status_code=400, detail="Cannot modify a confirmed bill")

        # Verify line item belongs to this bill
        item_check = (
            supabase.table("bill_line_items")
            .select("id, bill_id, unit_price, quantity")
            .eq("id", line_item_id)
            .eq("bill_id", bill_id)
            .limit(1)
            .execute()
        )

        if not item_check.data:
            raise HTTPException(status_code=404, detail="Line item not found in this bill")

        # Build update data
        update_data = {}
        current = item_check.data[0]

        if update.unit_price is not None:
            update_data["unit_price"] = update.unit_price
        if update.quantity is not None:
            update_data["quantity"] = update.quantity
        if update.billing_action is not None:
            if update.billing_action not in ("auto_billed", "pending_review", "flagged_manual"):
                raise HTTPException(status_code=400, detail="Invalid billing_action")
            update_data["billing_action"] = update.billing_action
        if update.notes is not None:
            update_data["notes"] = update.notes

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Recalculate total_price if price or quantity changed
        new_price = update_data.get("unit_price", current.get("unit_price"))
        new_qty = update_data.get("quantity", current.get("quantity"))
        if new_price is not None and new_qty is not None:
            update_data["total_price"] = round(float(new_price) * float(new_qty), 2)

        result = (
            supabase.table("bill_line_items")
            .update(update_data)
            .eq("id", line_item_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update line item")

        # Recalculate bill totals
        _recalculate_bill_totals(bill_id)

        return {
            "success": True,
            "message": "Line item updated",
            "line_item": result.data[0],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update line item")


@router.delete("/{bill_id}/line-items/{line_item_id}")
async def delete_line_item(
    request: Request,
    bill_id: str = Path(..., description="Bill UUID"),
    line_item_id: str = Path(..., description="Line item UUID"),
    _auth=Depends(verify_billing_access),
) -> Dict[str, Any]:
    """
    Delete a line item from a draft bill.

    **Auth:** Admin + Web + EHR
    """
    try:
        # Verify bill exists and is draft
        bill_check = (
            supabase.table("bills")
            .select("id, bill_status")
            .eq("id", bill_id)
            .limit(1)
            .execute()
        )

        if not bill_check.data:
            raise HTTPException(status_code=404, detail="Bill not found")

        status = bill_check.data[0]["bill_status"]
        if status == "confirmed":
            raise HTTPException(status_code=400, detail="Cannot modify a confirmed bill")
        if status == "superseded":
            raise HTTPException(status_code=400, detail="Cannot modify a superseded bill")

        # Verify line item belongs to this bill
        item_check = (
            supabase.table("bill_line_items")
            .select("id, bill_id")
            .eq("id", line_item_id)
            .eq("bill_id", bill_id)
            .limit(1)
            .execute()
        )

        if not item_check.data:
            raise HTTPException(status_code=404, detail="Line item not found in this bill")

        # Delete the line item
        supabase.table("bill_line_items").delete().eq("id", line_item_id).execute()

        # Recalculate bill totals
        _recalculate_bill_totals(bill_id)

        return {
            "success": True,
            "message": "Line item deleted",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Billing] Failed to delete line item {line_item_id} from bill {bill_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete line item")


@router.post("/{bill_id}/line-items")
async def add_line_items(
    request: Request,
    bill_id: str = Path(..., description="Bill UUID"),
    items: List[LineItemCreateRequest] = ...,
    _auth=Depends(verify_billing_access),
) -> Dict[str, Any]:
    """
    Add one or more line items to a draft bill.

    **Auth:** Admin + Web + EHR

    Allows manually adding extra charges (miscellaneous fees, supplies, etc.)
    to an existing draft bill.
    """
    try:
        if not items:
            raise HTTPException(status_code=400, detail="At least one line item is required")

        # Verify bill exists and is draft
        bill_check = (
            supabase.table("bills")
            .select("id, bill_status")
            .eq("id", bill_id)
            .limit(1)
            .execute()
        )

        if not bill_check.data:
            raise HTTPException(status_code=404, detail="Bill not found")

        status = bill_check.data[0]["bill_status"]
        if status == "confirmed":
            raise HTTPException(status_code=400, detail="Cannot modify a confirmed bill")
        if status == "superseded":
            raise HTTPException(status_code=400, detail="Cannot modify a superseded bill")

        # Validate and build insert rows
        rows = []
        for item in items:
            if item.category not in VALID_CATEGORIES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid category '{item.category}'. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}",
                )
            if item.billing_action not in ("auto_billed", "pending_review", "flagged_manual"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid billing_action '{item.billing_action}'",
                )

            unit_price = item.unit_price or 0
            total_price = round(float(unit_price) * float(item.quantity), 2)

            rows.append({
                "id": str(uuid.uuid4()),
                "bill_id": bill_id,
                "category": item.category,
                "description": item.description,
                "item_code": item.item_code,
                "quantity": item.quantity,
                "unit_price": unit_price,
                "total_price": total_price,
                "confidence": "high",
                "source_segment": "manual",
                "billing_action": item.billing_action,
                "notes": item.notes,
            })

        # Batch insert
        result = supabase.table("bill_line_items").insert(rows).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to insert line items")

        # Recalculate bill totals
        _recalculate_bill_totals(bill_id)

        return {
            "success": True,
            "message": f"{len(result.data)} line item(s) added",
            "line_items": result.data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Billing] Failed to add line items to bill {bill_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to add line items")


@router.put("/{bill_id}/confirm")
async def confirm_bill(
    request: Request,
    bill_id: str = Path(..., description="Bill UUID"),
    _auth=Depends(verify_billing_access),
) -> Dict[str, Any]:
    """
    Confirm a bill (draft → confirmed).

    **Auth:** Admin + Web + EHR
    """
    try:
        # Verify bill exists and is draft
        bill_check = (
            supabase.table("bills")
            .select("id, bill_status")
            .eq("id", bill_id)
            .limit(1)
            .execute()
        )

        if not bill_check.data:
            raise HTTPException(status_code=404, detail="Bill not found")

        current_status = bill_check.data[0]["bill_status"]
        if current_status == "confirmed":
            raise HTTPException(status_code=400, detail="Bill is already confirmed")
        if current_status == "superseded":
            raise HTTPException(status_code=400, detail="Cannot confirm a superseded bill")

        # Update status
        result = (
            supabase.table("bills")
            .update({
                "bill_status": "confirmed",
                "updated_at": datetime.utcnow().isoformat(),
            })
            .eq("id", bill_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to confirm bill")

        # Fetch full bill with line items
        bill = result.data[0]
        items = (
            supabase.table("bill_line_items")
            .select("*")
            .eq("bill_id", bill_id)
            .order("created_at")
            .execute()
        )
        bill["line_items"] = items.data or []

        return {
            "success": True,
            "message": "Bill confirmed",
            "bill": bill,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to confirm bill")


# ============================================================================
# Helper Functions
# ============================================================================

def _get_extraction(extraction_id: str) -> Dict[str, Any]:
    """Fetch extraction record."""
    result = (
        supabase.table("medical_extractions")
        .select("id, doctor_id, patient_id, consultation_type_id, original_extraction_json, edited_extraction_json, is_merged, merge_metadata")
        .eq("id", extraction_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Extraction not found")

    return result.data[0]


def _resolve_hospital_id(doctor_id: Optional[str], extraction: Dict[str, Any]) -> Optional[str]:
    """Resolve hospital_id from doctor or extraction metadata."""
    if doctor_id:
        hospital_id = get_doctor_hospital_id_cached(uuid.UUID(doctor_id))
        if hospital_id:
            return hospital_id

    # Fallback: check merge_metadata
    merge_metadata = extraction.get("merge_metadata") or {}
    return merge_metadata.get("hospital_id")


def _get_consultation_type_code(extraction: Dict[str, Any]) -> Optional[str]:
    """Get consultation type code from extraction."""
    ct_id = extraction.get("consultation_type_id")
    if not ct_id:
        return None

    try:
        result = (
            supabase.table("consultation_types")
            .select("type_code")
            .eq("id", ct_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0].get("type_code")
    except Exception:
        pass

    return None


def _recalculate_bill_totals(bill_id: str):
    """Recalculate bill totals from line items."""
    try:
        items = (
            supabase.table("bill_line_items")
            .select("total_price, billing_action")
            .eq("bill_id", bill_id)
            .execute()
        )

        total = 0.0
        auto = 0.0
        pending = 0.0
        flagged = 0.0

        for item in (items.data or []):
            item_total = float(item.get("total_price") or 0)
            total += item_total
            action = item.get("billing_action", "pending_review")
            if action == "auto_billed":
                auto += item_total
            elif action == "pending_review":
                pending += item_total
            elif action == "flagged_manual":
                flagged += item_total

        supabase.table("bills").update({
            "total_amount": round(total, 2),
            "auto_billed_amount": round(auto, 2),
            "pending_review_amount": round(pending, 2),
            "flagged_amount": round(flagged, 2),
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", bill_id).execute()

    except Exception as e:
        logger.warning(f"[Billing] Failed to recalculate bill totals for {bill_id}: {e}")

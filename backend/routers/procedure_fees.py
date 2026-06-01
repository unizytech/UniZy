"""
Procedure Fee Router - Procedure Fee Master CRUD

REST API endpoints for managing procedure fee master data per school.
Includes individual CRUD and CSV bulk upload.
"""

import os
import csv
import io
import logging
from fastapi import APIRouter, HTTPException, Depends, Path, Query, Request, UploadFile, File
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime

from services.supabase_service import supabase

logger = logging.getLogger(__name__)

# ============================================================================
# Auth Setup
# ============================================================================
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"

if AUTH_ENABLED:
    from dependencies.auth import get_current_client
    from models.auth_models import ClientContext

    async def verify_procedure_fee_access(request: Request):
        """Verify the client has procedure fee access (Admin + Web + EHR)."""
        client = get_current_client(request)
        if client.client_type not in ("admin", "web_app", "ehr"):
            raise HTTPException(status_code=403, detail="Access denied")
        return client
else:
    async def verify_procedure_fee_access(request: Request = None):
        return None

router = APIRouter(prefix="/api/v1/schools", tags=["Procedure Fees"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ProcedureFeeCreateRequest(BaseModel):
    """Request model for creating a procedure fee"""
    procedure_name: str = Field(..., min_length=1, max_length=255, description="Procedure name")
    cpt_code: Optional[str] = Field(None, max_length=20, description="CPT code")
    icd_pcs_code: Optional[str] = Field(None, max_length=20, description="ICD PCS code")
    fee: float = Field(..., gt=0, description="Procedure fee amount")
    category: Optional[str] = Field("minor", description="Category: minor, surgery, emergency")


class ProcedureFeeUpdateRequest(BaseModel):
    """Request model for updating a procedure fee"""
    procedure_name: Optional[str] = Field(None, min_length=1, max_length=255)
    cpt_code: Optional[str] = Field(None, max_length=20)
    icd_pcs_code: Optional[str] = Field(None, max_length=20)
    fee: Optional[float] = Field(None, gt=0)
    category: Optional[str] = Field(None)
    is_active: Optional[bool] = Field(None)


# ============================================================================
# Procedure Fee CRUD Endpoints
# ============================================================================

@router.get("/{school_id}/procedure-fees")
async def list_procedure_fees(
    request: Request,
    school_id: str = Path(..., description="School UUID"),
    category: Optional[str] = Query(None, description="Filter by category"),
    include_inactive: bool = Query(False, description="Include inactive fees"),
    _auth=Depends(verify_procedure_fee_access),
) -> Dict[str, Any]:
    """
    List procedure fees for a school.

    **Auth:** Admin + Web + EHR
    """
    try:
        query = (
            supabase.table("procedure_fee_master")
            .select("*")
            .eq("school_id", school_id)
            .order("procedure_name")
        )

        if not include_inactive:
            query = query.eq("is_active", True)

        if category:
            query = query.eq("category", category)

        result = query.execute()

        return {
            "success": True,
            "procedure_fees": result.data or [],
            "count": len(result.data or []),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to list procedure fees")


@router.post("/{school_id}/procedure-fees")
async def create_procedure_fee(
    request: Request,
    school_id: str = Path(..., description="School UUID"),
    fee_request: ProcedureFeeCreateRequest = ...,
    _auth=Depends(verify_procedure_fee_access),
) -> Dict[str, Any]:
    """
    Create a procedure fee entry.

    **Auth:** Admin + Web + EHR
    """
    try:
        # Check uniqueness
        existing = (
            supabase.table("procedure_fee_master")
            .select("id")
            .eq("school_id", school_id)
            .eq("procedure_name", fee_request.procedure_name)
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=409,
                detail=f"Procedure '{fee_request.procedure_name}' already exists for this school"
            )

        insert_data = {
            "school_id": school_id,
            "procedure_name": fee_request.procedure_name,
            "cpt_code": fee_request.cpt_code,
            "icd_pcs_code": fee_request.icd_pcs_code,
            "fee": fee_request.fee,
            "category": fee_request.category or "minor",
            "is_active": True,
        }

        result = supabase.table("procedure_fee_master").insert(insert_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create procedure fee")

        return {
            "success": True,
            "message": f"Procedure fee for '{fee_request.procedure_name}' created",
            "procedure_fee": result.data[0],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create procedure fee")


@router.put("/{school_id}/procedure-fees/{fee_id}")
async def update_procedure_fee(
    request: Request,
    school_id: str = Path(..., description="School UUID"),
    fee_id: str = Path(..., description="Procedure fee UUID"),
    fee_request: ProcedureFeeUpdateRequest = ...,
    _auth=Depends(verify_procedure_fee_access),
) -> Dict[str, Any]:
    """
    Update a procedure fee entry.

    **Auth:** Admin + Web + EHR
    """
    try:
        # Verify exists
        existing = (
            supabase.table("procedure_fee_master")
            .select("id")
            .eq("id", fee_id)
            .eq("school_id", school_id)
            .limit(1)
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Procedure fee not found")

        # Build update data
        update_data = {"updated_at": datetime.utcnow().isoformat()}

        if fee_request.procedure_name is not None:
            # Check uniqueness for new name
            name_check = (
                supabase.table("procedure_fee_master")
                .select("id")
                .eq("school_id", school_id)
                .eq("procedure_name", fee_request.procedure_name)
                .neq("id", fee_id)
                .execute()
            )
            if name_check.data:
                raise HTTPException(status_code=409, detail="Procedure with this name already exists")
            update_data["procedure_name"] = fee_request.procedure_name

        if fee_request.cpt_code is not None:
            update_data["cpt_code"] = fee_request.cpt_code or None
        if fee_request.icd_pcs_code is not None:
            update_data["icd_pcs_code"] = fee_request.icd_pcs_code or None
        if fee_request.fee is not None:
            update_data["fee"] = fee_request.fee
        if fee_request.category is not None:
            update_data["category"] = fee_request.category
        if fee_request.is_active is not None:
            update_data["is_active"] = fee_request.is_active

        result = (
            supabase.table("procedure_fee_master")
            .update(update_data)
            .eq("id", fee_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update procedure fee")

        return {
            "success": True,
            "message": "Procedure fee updated",
            "procedure_fee": result.data[0],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update procedure fee")


@router.delete("/{school_id}/procedure-fees/{fee_id}")
async def delete_procedure_fee(
    request: Request,
    school_id: str = Path(..., description="School UUID"),
    fee_id: str = Path(..., description="Procedure fee UUID"),
    _auth=Depends(verify_procedure_fee_access),
) -> Dict[str, Any]:
    """
    Soft-delete a procedure fee (set is_active=false).

    **Auth:** Admin + Web + EHR
    """
    try:
        existing = (
            supabase.table("procedure_fee_master")
            .select("id, procedure_name, is_active")
            .eq("id", fee_id)
            .eq("school_id", school_id)
            .limit(1)
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Procedure fee not found")

        if not existing.data[0].get("is_active"):
            raise HTTPException(status_code=400, detail="Procedure fee is already inactive")

        supabase.table("procedure_fee_master").update({
            "is_active": False,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", fee_id).execute()

        return {
            "success": True,
            "message": f"Procedure fee '{existing.data[0]['procedure_name']}' deactivated",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete procedure fee")


@router.post("/{school_id}/procedure-fees/upload")
async def upload_procedure_fees(
    request: Request,
    school_id: str = Path(..., description="School UUID"),
    file: UploadFile = File(...),
    replace_existing: bool = Query(False, description="Replace all existing fees"),
    _auth=Depends(verify_procedure_fee_access),
) -> Dict[str, Any]:
    """
    CSV upload of procedure fees.

    **Auth:** Admin + Web + EHR

    Expected CSV columns: procedure_name, cpt_code, icd_pcs_code, fee, category
    Required: procedure_name, fee
    """
    try:
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="Only CSV files are supported")

        content = await file.read()
        csv_content = content.decode('utf-8-sig')

        # Parse CSV
        reader = csv.DictReader(io.StringIO(csv_content))
        if reader.fieldnames:
            reader.fieldnames = [f.lower().strip().lstrip('\ufeff') for f in reader.fieldnames]

        procedures = []
        errors = []

        for row_num, row in enumerate(reader, start=2):
            try:
                name = row.get('procedure_name', '').strip()
                if not name:
                    errors.append({"row": row_num, "error": "Missing procedure_name"})
                    continue

                fee_str = row.get('fee', '').strip()
                if not fee_str:
                    errors.append({"row": row_num, "error": "Missing fee", "data": name})
                    continue

                try:
                    fee = float(fee_str)
                except ValueError:
                    errors.append({"row": row_num, "error": f"Invalid fee value: {fee_str}", "data": name})
                    continue

                procedures.append({
                    "school_id": school_id,
                    "procedure_name": name,
                    "cpt_code": row.get('cpt_code', '').strip() or None,
                    "icd_pcs_code": row.get('icd_pcs_code', '').strip() or None,
                    "fee": fee,
                    "category": row.get('category', '').strip() or "minor",
                    "is_active": True,
                })

            except Exception as e:
                errors.append({"row": row_num, "error": str(e)})

        if not procedures:
            raise HTTPException(status_code=400, detail="No valid procedures found in CSV")

        # Deactivate existing if requested
        if replace_existing:
            supabase.table("procedure_fee_master").update({
                "is_active": False,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("school_id", school_id).execute()

        # Deduplicate by procedure_name (last wins)
        seen = {}
        for proc in procedures:
            seen[proc["procedure_name"].lower()] = proc
        procedures = list(seen.values())

        # Batch upsert
        successful = 0
        BATCH_SIZE = 500

        for i in range(0, len(procedures), BATCH_SIZE):
            batch = procedures[i:i + BATCH_SIZE]
            try:
                supabase.table("procedure_fee_master").upsert(
                    batch,
                    on_conflict="school_id,procedure_name"
                ).execute()
                successful += len(batch)
            except Exception as e:
                logger.warning(f"[ProcedureFee] Batch upsert failed, falling back: {e}")
                for proc in batch:
                    try:
                        supabase.table("procedure_fee_master").upsert(
                            proc,
                            on_conflict="school_id,procedure_name"
                        ).execute()
                        successful += 1
                    except Exception as inner_e:
                        errors.append({"row": "N/A", "error": str(inner_e), "data": proc.get("procedure_name")})

        return {
            "success": True,
            "message": f"Uploaded {successful} procedure fees",
            "total_rows": len(procedures) + len(errors),
            "successful": successful,
            "failed": len(errors),
            "errors": errors[:10] if errors else [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ProcedureFee] Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload procedure fees: {str(e)}")

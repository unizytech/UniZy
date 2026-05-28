"""
Radiology Config Router

CRUD APIs for radiology template configuration:
- /api/v1/radiology/templates/{template_id}/plan-library
- /api/v1/radiology/templates/{template_id}/toxicity-library
- /api/v1/radiology/templates/{template_id}/standard-texts
- /api/v1/radiology/templates/{template_id}/examination-segment (GET only)

All endpoints accept admin, web_app, and ehr clients.
"""

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from dependencies.auth import get_current_client
from models.auth_models import ClientContext
from services import radiology_library_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/radiology", tags=["Radiology Config"])


# ----------------------------------------------------------------------------
# Auth helper — admin, web_app, and ehr all permitted
# ----------------------------------------------------------------------------

def require_admin_ehr_web(
    client: ClientContext = Depends(get_current_client),
) -> ClientContext:
    if client.client_type not in ("admin", "web_app", "ehr"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return client


def _parse_uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {label} UUID")


# ----------------------------------------------------------------------------
# Request models
# ----------------------------------------------------------------------------

class PlanItemCreate(BaseModel):
    plan_code: str = Field(..., max_length=64)
    plan_name: str = Field(..., max_length=255)
    rt_intent: Optional[str] = None
    rt_indication: Optional[str] = None
    rt_dose_gy: Optional[str] = None
    rt_fractions: Optional[str] = None
    rt_dose_per_fraction_gy: Optional[str] = None
    rt_weeks: Optional[str] = None
    rt_technique: Optional[str] = None
    concurrent_systemic_therapy: Optional[str] = None
    display_order: Optional[int] = 0


class PlanItemUpdate(BaseModel):
    plan_code: Optional[str] = None
    plan_name: Optional[str] = None
    rt_intent: Optional[str] = None
    rt_indication: Optional[str] = None
    rt_dose_gy: Optional[str] = None
    rt_fractions: Optional[str] = None
    rt_dose_per_fraction_gy: Optional[str] = None
    rt_weeks: Optional[str] = None
    rt_technique: Optional[str] = None
    concurrent_systemic_therapy: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class ToxicityItemCreate(BaseModel):
    toxicity_code: str = Field(..., max_length=64)
    phase: str = Field(..., pattern="^(early|late)$")
    text: str
    conditional_trigger: Optional[str] = Field(default=None, max_length=64)
    display_order: Optional[int] = 0


class ToxicityItemUpdate(BaseModel):
    toxicity_code: Optional[str] = None
    phase: Optional[str] = Field(default=None, pattern="^(early|late)$")
    text: Optional[str] = None
    conditional_trigger: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class StandardTextCreate(BaseModel):
    key: str = Field(..., max_length=64)
    label: Optional[str] = Field(default=None, max_length=255)
    text: str
    display_order: Optional[int] = 0


class StandardTextUpdate(BaseModel):
    key: Optional[str] = None
    label: Optional[str] = None
    text: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


# ----------------------------------------------------------------------------
# Plan library
# ----------------------------------------------------------------------------

@router.get("/templates/{template_id}/plan-library")
async def get_plan_library(
    template_id: str,
    include_inactive: bool = Query(False),
    _client: ClientContext = Depends(require_admin_ehr_web),
):
    tid = _parse_uuid(template_id, "template_id")
    items = svc.list_plan_library(tid, include_inactive=include_inactive)
    return {"items": items, "count": len(items)}


@router.post("/templates/{template_id}/plan-library")
async def create_plan_library_item(
    template_id: str,
    payload: PlanItemCreate,
    _client: ClientContext = Depends(require_admin_ehr_web),
):
    tid = _parse_uuid(template_id, "template_id")
    try:
        item = svc.create_plan_item(tid, payload.model_dump(exclude_none=True))
    except Exception as e:
        logger.exception("[RADIOLOGY_CFG] create_plan_item failed")
        raise HTTPException(status_code=400, detail=str(e))
    return {"item": item}


@router.put("/templates/{template_id}/plan-library/{item_id}")
async def update_plan_library_item(
    template_id: str,
    item_id: str,
    payload: PlanItemUpdate,
    _client: ClientContext = Depends(require_admin_ehr_web),
):
    _parse_uuid(template_id, "template_id")
    iid = _parse_uuid(item_id, "item_id")
    try:
        item = svc.update_plan_item(iid, payload.model_dump(exclude_none=True))
    except Exception as e:
        logger.exception("[RADIOLOGY_CFG] update_plan_item failed")
        raise HTTPException(status_code=400, detail=str(e))
    return {"item": item}


@router.delete("/templates/{template_id}/plan-library/{item_id}")
async def delete_plan_library_item(
    template_id: str,
    item_id: str,
    _client: ClientContext = Depends(require_admin_ehr_web),
):
    _parse_uuid(template_id, "template_id")
    iid = _parse_uuid(item_id, "item_id")
    try:
        item = svc.delete_plan_item(iid)
    except Exception as e:
        logger.exception("[RADIOLOGY_CFG] delete_plan_item failed")
        raise HTTPException(status_code=400, detail=str(e))
    return {"item": item}


# ----------------------------------------------------------------------------
# Toxicity library
# ----------------------------------------------------------------------------

@router.get("/templates/{template_id}/toxicity-library")
async def get_toxicity_library(
    template_id: str,
    phase: Optional[str] = Query(None, pattern="^(early|late)$"),
    include_inactive: bool = Query(False),
    _client: ClientContext = Depends(require_admin_ehr_web),
):
    tid = _parse_uuid(template_id, "template_id")
    items = svc.list_toxicity_library(tid, phase=phase, include_inactive=include_inactive)
    return {"items": items, "count": len(items)}


@router.post("/templates/{template_id}/toxicity-library")
async def create_toxicity_library_item(
    template_id: str,
    payload: ToxicityItemCreate,
    _client: ClientContext = Depends(require_admin_ehr_web),
):
    tid = _parse_uuid(template_id, "template_id")
    try:
        item = svc.create_toxicity_item(tid, payload.model_dump(exclude_none=True))
    except Exception as e:
        logger.exception("[RADIOLOGY_CFG] create_toxicity_item failed")
        raise HTTPException(status_code=400, detail=str(e))
    return {"item": item}


@router.put("/templates/{template_id}/toxicity-library/{item_id}")
async def update_toxicity_library_item(
    template_id: str,
    item_id: str,
    payload: ToxicityItemUpdate,
    _client: ClientContext = Depends(require_admin_ehr_web),
):
    _parse_uuid(template_id, "template_id")
    iid = _parse_uuid(item_id, "item_id")
    try:
        item = svc.update_toxicity_item(iid, payload.model_dump(exclude_none=True))
    except Exception as e:
        logger.exception("[RADIOLOGY_CFG] update_toxicity_item failed")
        raise HTTPException(status_code=400, detail=str(e))
    return {"item": item}


@router.delete("/templates/{template_id}/toxicity-library/{item_id}")
async def delete_toxicity_library_item(
    template_id: str,
    item_id: str,
    _client: ClientContext = Depends(require_admin_ehr_web),
):
    _parse_uuid(template_id, "template_id")
    iid = _parse_uuid(item_id, "item_id")
    try:
        item = svc.delete_toxicity_item(iid)
    except Exception as e:
        logger.exception("[RADIOLOGY_CFG] delete_toxicity_item failed")
        raise HTTPException(status_code=400, detail=str(e))
    return {"item": item}


# ----------------------------------------------------------------------------
# Standard texts
# ----------------------------------------------------------------------------

@router.get("/templates/{template_id}/standard-texts")
async def get_standard_texts(
    template_id: str,
    include_inactive: bool = Query(False),
    _client: ClientContext = Depends(require_admin_ehr_web),
):
    tid = _parse_uuid(template_id, "template_id")
    items = svc.list_standard_texts(tid, include_inactive=include_inactive)
    return {"items": items, "count": len(items)}


@router.post("/templates/{template_id}/standard-texts")
async def create_standard_text_item(
    template_id: str,
    payload: StandardTextCreate,
    _client: ClientContext = Depends(require_admin_ehr_web),
):
    tid = _parse_uuid(template_id, "template_id")
    try:
        item = svc.create_standard_text(tid, payload.model_dump(exclude_none=True))
    except Exception as e:
        logger.exception("[RADIOLOGY_CFG] create_standard_text failed")
        raise HTTPException(status_code=400, detail=str(e))
    return {"item": item}


@router.put("/templates/{template_id}/standard-texts/{item_id}")
async def update_standard_text_item(
    template_id: str,
    item_id: str,
    payload: StandardTextUpdate,
    _client: ClientContext = Depends(require_admin_ehr_web),
):
    _parse_uuid(template_id, "template_id")
    iid = _parse_uuid(item_id, "item_id")
    try:
        item = svc.update_standard_text(iid, payload.model_dump(exclude_none=True))
    except Exception as e:
        logger.exception("[RADIOLOGY_CFG] update_standard_text failed")
        raise HTTPException(status_code=400, detail=str(e))
    return {"item": item}


@router.delete("/templates/{template_id}/standard-texts/{item_id}")
async def delete_standard_text_item(
    template_id: str,
    item_id: str,
    _client: ClientContext = Depends(require_admin_ehr_web),
):
    _parse_uuid(template_id, "template_id")
    iid = _parse_uuid(item_id, "item_id")
    try:
        item = svc.delete_standard_text(iid)
    except Exception as e:
        logger.exception("[RADIOLOGY_CFG] delete_standard_text failed")
        raise HTTPException(status_code=400, detail=str(e))
    return {"item": item}


# ----------------------------------------------------------------------------
# Examination viewer (read-only)
# ----------------------------------------------------------------------------

@router.get("/templates/{template_id}/examination-segment")
async def get_examination_segment(
    template_id: str,
    _client: ClientContext = Depends(require_admin_ehr_web),
):
    tid = _parse_uuid(template_id, "template_id")
    seg = svc.get_examination_segment_for_template(tid)
    if not seg:
        raise HTTPException(status_code=404, detail="No EXAMINATION_* segment for this template")
    return seg

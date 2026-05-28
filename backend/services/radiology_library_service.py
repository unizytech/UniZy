"""
Radiology Library Service

CRUD + library renderers for:
- radiology_plan_library: items substituted into PLAN segment {{LIBRARY_PLAN}}
- radiology_toxicity_library: items substituted into TOXICITY segment {{LIBRARY_TOXICITY}}
- template_standard_texts: named text blocks merged into extraction JSON before EHR dispatch

After every mutation we fire-and-forget a per-template re-assembly so the
cached templates.assembled_full_prompt picks up the new library content.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from .supabase_service import supabase

logger = logging.getLogger(__name__)


# ============================================================================
# Re-assembly trigger (fire-and-forget; pipeline-latency-safe per CLAUDE.md)
# ============================================================================

def _trigger_reassembly(template_id: uuid.UUID, source: str) -> None:
    try:
        from .template_assembly_service import trigger_reassembly_async
        asyncio.create_task(
            trigger_reassembly_async(
                [template_id],
                trigger_source=source,
                include_audio=False,
            )
        )
    except RuntimeError:
        logger.debug("[RADIOLOGY_LIB] No running event loop; skipping reassembly trigger")
    except Exception as e:
        logger.warning(f"[RADIOLOGY_LIB] Failed to schedule reassembly: {e}")


# ============================================================================
# Plan library CRUD
# ============================================================================

PLAN_FIELDS = (
    "id, template_id, plan_code, plan_name, rt_intent, rt_indication, "
    "rt_dose_gy, rt_fractions, rt_dose_per_fraction_gy, rt_weeks, rt_technique, "
    "concurrent_systemic_therapy, display_order, is_active, created_at, updated_at"
)


def list_plan_library(template_id: uuid.UUID, include_inactive: bool = False) -> List[Dict[str, Any]]:
    q = supabase.table("radiology_plan_library").select(PLAN_FIELDS).eq("template_id", str(template_id))
    if not include_inactive:
        q = q.eq("is_active", True)
    result = q.order("display_order").order("plan_code").execute()
    return result.data or []


def create_plan_item(template_id: uuid.UUID, payload: Dict[str, Any]) -> Dict[str, Any]:
    row = {**payload, "template_id": str(template_id)}
    result = supabase.table("radiology_plan_library").insert(row).execute()
    if not result.data:
        raise RuntimeError("Failed to create plan library item")
    _trigger_reassembly(template_id, "plan_library_create")
    return result.data[0]


def update_plan_item(item_id: uuid.UUID, payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = {k: v for k, v in payload.items() if v is not None}
    payload["updated_at"] = "now()"
    result = supabase.table("radiology_plan_library").update(payload).eq("id", str(item_id)).execute()
    if not result.data:
        raise RuntimeError("Plan library item not found")
    template_id = uuid.UUID(result.data[0]["template_id"])
    _trigger_reassembly(template_id, "plan_library_update")
    return result.data[0]


def delete_plan_item(item_id: uuid.UUID) -> Dict[str, Any]:
    result = supabase.table("radiology_plan_library").update(
        {"is_active": False, "updated_at": "now()"}
    ).eq("id", str(item_id)).execute()
    if not result.data:
        raise RuntimeError("Plan library item not found")
    template_id = uuid.UUID(result.data[0]["template_id"])
    _trigger_reassembly(template_id, "plan_library_delete")
    return result.data[0]


# ============================================================================
# Toxicity library CRUD
# ============================================================================

TOXICITY_FIELDS = (
    "id, template_id, toxicity_code, phase, text, conditional_trigger, "
    "display_order, is_active, created_at, updated_at"
)


def list_toxicity_library(
    template_id: uuid.UUID,
    phase: Optional[str] = None,
    include_inactive: bool = False,
) -> List[Dict[str, Any]]:
    q = supabase.table("radiology_toxicity_library").select(TOXICITY_FIELDS).eq("template_id", str(template_id))
    if phase:
        q = q.eq("phase", phase)
    if not include_inactive:
        q = q.eq("is_active", True)
    result = q.order("phase").order("display_order").order("toxicity_code").execute()
    return result.data or []


def create_toxicity_item(template_id: uuid.UUID, payload: Dict[str, Any]) -> Dict[str, Any]:
    row = {**payload, "template_id": str(template_id)}
    result = supabase.table("radiology_toxicity_library").insert(row).execute()
    if not result.data:
        raise RuntimeError("Failed to create toxicity library item")
    _trigger_reassembly(template_id, "toxicity_library_create")
    return result.data[0]


def update_toxicity_item(item_id: uuid.UUID, payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = {k: v for k, v in payload.items() if v is not None}
    payload["updated_at"] = "now()"
    result = supabase.table("radiology_toxicity_library").update(payload).eq("id", str(item_id)).execute()
    if not result.data:
        raise RuntimeError("Toxicity library item not found")
    template_id = uuid.UUID(result.data[0]["template_id"])
    _trigger_reassembly(template_id, "toxicity_library_update")
    return result.data[0]


def delete_toxicity_item(item_id: uuid.UUID) -> Dict[str, Any]:
    result = supabase.table("radiology_toxicity_library").update(
        {"is_active": False, "updated_at": "now()"}
    ).eq("id", str(item_id)).execute()
    if not result.data:
        raise RuntimeError("Toxicity library item not found")
    template_id = uuid.UUID(result.data[0]["template_id"])
    _trigger_reassembly(template_id, "toxicity_library_delete")
    return result.data[0]


# ============================================================================
# Standard texts CRUD
# ============================================================================

STANDARD_TEXT_FIELDS = (
    "id, template_id, key, label, text, display_order, is_active, created_at, updated_at"
)


def list_standard_texts(template_id: uuid.UUID, include_inactive: bool = False) -> List[Dict[str, Any]]:
    q = supabase.table("template_standard_texts").select(STANDARD_TEXT_FIELDS).eq("template_id", str(template_id))
    if not include_inactive:
        q = q.eq("is_active", True)
    result = q.order("display_order").order("key").execute()
    return result.data or []


def create_standard_text(template_id: uuid.UUID, payload: Dict[str, Any]) -> Dict[str, Any]:
    row = {**payload, "template_id": str(template_id)}
    result = supabase.table("template_standard_texts").insert(row).execute()
    if not result.data:
        raise RuntimeError("Failed to create standard text")
    return result.data[0]


def update_standard_text(item_id: uuid.UUID, payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = {k: v for k, v in payload.items() if v is not None}
    payload["updated_at"] = "now()"
    result = supabase.table("template_standard_texts").update(payload).eq("id", str(item_id)).execute()
    if not result.data:
        raise RuntimeError("Standard text not found")
    return result.data[0]


def delete_standard_text(item_id: uuid.UUID) -> Dict[str, Any]:
    result = supabase.table("template_standard_texts").update(
        {"is_active": False, "updated_at": "now()"}
    ).eq("id", str(item_id)).execute()
    if not result.data:
        raise RuntimeError("Standard text not found")
    return result.data[0]


# ============================================================================
# Library renderers — used by template_assembly_service to substitute
# {{LIBRARY_PLAN}} and {{LIBRARY_TOXICITY}} placeholders in segment prompts
# ============================================================================

_PLAN_OUTPUT_KEYS = (
    "id", "name",
    "rt_intent", "rt_indication", "rt_dose_gy", "rt_fractions",
    "rt_dose_per_fraction_gy", "rt_weeks", "rt_technique",
    "concurrent_systemic_therapy",
)


def _plan_row_to_library_entry(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("plan_code") or "",
        "name": row.get("plan_name") or "",
        "rt_intent": row.get("rt_intent") or "",
        "rt_indication": row.get("rt_indication") or "",
        "rt_dose_gy": row.get("rt_dose_gy") or "",
        "rt_fractions": row.get("rt_fractions") or "",
        "rt_dose_per_fraction_gy": row.get("rt_dose_per_fraction_gy") or "",
        "rt_weeks": row.get("rt_weeks") or "",
        "rt_technique": row.get("rt_technique") or "",
        "concurrent_systemic_therapy": row.get("concurrent_systemic_therapy") or "",
    }


def render_plan_library_block(template_id: uuid.UUID) -> str:
    """JSON array of plan templates inserted at {{LIBRARY_PLAN}}.

    Returns "[]" when no active items exist so the LLM still sees valid JSON.
    """
    rows = list_plan_library(template_id)
    library = [_plan_row_to_library_entry(r) for r in rows]
    return json.dumps(library, ensure_ascii=False, indent=2)


def render_toxicity_library_block(template_id: uuid.UUID) -> str:
    """JSON object {early_toxicity_library:[...], late_toxicity_library:[...]}
    inserted at {{LIBRARY_TOXICITY}}. Each entry carries its toxicity_code as
    `id` and, when set, a `conditional_trigger` (BRACHYTHERAPY / SCF /
    LEFT_HEART) so the LLM can apply trigger-based inclusion without relying
    on id-prefix matching."""
    rows = list_toxicity_library(template_id)
    early: List[Dict[str, str]] = []
    late: List[Dict[str, str]] = []
    for r in rows:
        entry: Dict[str, str] = {
            "id": r.get("toxicity_code") or "",
            "text": r.get("text") or "",
        }
        trigger = r.get("conditional_trigger")
        if trigger:
            entry["conditional_trigger"] = trigger
        if r.get("phase") == "early":
            early.append(entry)
        elif r.get("phase") == "late":
            late.append(entry)
    return json.dumps(
        {"early_toxicity_library": early, "late_toxicity_library": late},
        ensure_ascii=False,
        indent=2,
    )


# ============================================================================
# Examination viewer
# ============================================================================

def get_examination_segment_for_template(template_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Return the EXAMINATION_* segment definition for a template, or None.

    Joins template_segments → segment_definitions, filters by segment_code
    starting with 'EXAMINATION_'. Each radiology template has exactly one.
    """
    result = supabase.table("template_segments").select(
        "segment_code, segment_definitions!inner(segment_code, segment_name, prompt_section_text, schema_definition_json)"
    ).eq("template_id", str(template_id)).execute()

    for row in result.data or []:
        seg = row.get("segment_definitions") or {}
        code = seg.get("segment_code") or row.get("segment_code") or ""
        if code.startswith("EXAMINATION_"):
            return {
                "segment_code": code,
                "segment_name": seg.get("segment_name"),
                "prompt_section_text": seg.get("prompt_section_text"),
                "schema_definition_json": seg.get("schema_definition_json"),
            }
    return None

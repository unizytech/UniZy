"""
Schema drift logger for counsellor edits to extractions.

Counsellor-edit iframes occasionally send fields with a different shape than
the AI-extraction schema (the canonical example: `diagnosis` arrives as
{primary_diagnosis: "..."} instead of [{name, code}, ...]). When this
happens, downstream EHR formatters that assume the canonical shape may
silently drop the field.

This module walks an incoming edit against the template's stored schema
and emits a single `[SCHEMA_DRIFT]` log line per edit summarising any
mismatches. Logging is intentionally non-blocking — the merge and EHR
sync still proceed. Operators use the warnings to prioritise which
formatter helpers need defensive type handling.

Wired into `update_extraction_edits` (services/supabase_service.py) as
fire-and-forget after the merge.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Map JSON-Schema "type" tokens (and the bare-string types used by our
# segment_definitions.schema_definition_json) to Python isinstance probes.
_TYPE_MATCHERS = {
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    # bool is a subclass of int — exclude it for "number"
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "null": lambda v: v is None,
}


def _shape_of(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _walk(
    data: Any,
    schema: Any,
    path: str,
    drifts: List[Tuple[str, str, str]],
    max_drifts: int = 50,
) -> None:
    """Recursively compare data against schema; append drift tuples."""
    if len(drifts) >= max_drifts:
        return
    if schema is None:
        return

    # JSON-Schema-style wrapper: {"type": "object", "properties": {...}}
    if isinstance(schema, dict) and "properties" in schema:
        if not isinstance(data, dict):
            drifts.append((path or "<root>", "object", _shape_of(data)))
            return
        properties = schema.get("properties") or {}
        if isinstance(properties, dict):
            for key, sub_schema in properties.items():
                if key in data:
                    _walk(data[key], sub_schema, f"{path}.{key}" if path else key, drifts, max_drifts)
        return

    # Bare type token: "string", "boolean", "number", ...
    if isinstance(schema, str):
        matcher = _TYPE_MATCHERS.get(schema)
        if matcher is not None and not matcher(data):
            # Allow empty string for any leaf (common formatter convention)
            if not (data == "" and schema in ("string", "number", "boolean")):
                drifts.append((path or "<root>", schema, _shape_of(data)))
        return

    # Array shorthand: ["string"] or [{...}]
    if isinstance(schema, list):
        if not isinstance(data, list):
            drifts.append((path or "<root>", "array", _shape_of(data)))
            return
        if len(schema) >= 1:
            item_schema = schema[0]
            for i, item in enumerate(data):
                _walk(item, item_schema, f"{path}[{i}]", drifts, max_drifts)
        return

    # Plain dict schema (key -> sub-schema for each)
    if isinstance(schema, dict):
        if not isinstance(data, dict):
            drifts.append((path or "<root>", "object", _shape_of(data)))
            return
        for key, sub_schema in schema.items():
            if key in data:
                _walk(data[key], sub_schema, f"{path}.{key}" if path else key, drifts, max_drifts)
        return


def collect_drifts(
    data: Any,
    schema: Any,
    max_drifts: int = 50,
) -> List[Tuple[str, str, str]]:
    """Return list of (json_path, expected_shape, actual_shape)."""
    drifts: List[Tuple[str, str, str]] = []
    if schema is None or data is None:
        return drifts
    _walk(data, schema, "", drifts, max_drifts)
    return drifts


def _fetch_template_schema_for_extraction(
    extraction_id: str,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Look up the template (id, assembled_schema_json) tied to an extraction.

    Path: extractions.session_id → recording_sessions.template_id
        → templates.assembled_schema_json

    Returns (template_id, schema) — either may be None if the extraction
    does not have a template association (rare).
    """
    # Local import keeps this module decoupled at module-load time.
    from services.supabase_service import supabase

    sess_resp = (
        supabase.table("extractions")
        .select("recording_sessions(template_id)")
        .eq("id", str(extraction_id))
        .limit(1)
        .execute()
    )
    if not sess_resp.data:
        return None, None
    session_info = sess_resp.data[0].get("recording_sessions") or {}
    template_id = session_info.get("template_id")
    if not template_id:
        return None, None
    tpl_resp = (
        supabase.table("templates")
        .select("assembled_schema_json")
        .eq("id", str(template_id))
        .limit(1)
        .execute()
    )
    if not tpl_resp.data:
        return template_id, None
    return template_id, tpl_resp.data[0].get("assembled_schema_json")


def log_schema_drift_sync(
    extraction_id: str,
    edited_data: Dict[str, Any],
) -> None:
    """
    Synchronous core: fetch the schema for `extraction_id` and log any drift.
    Diagnostic-only; never raises.
    """
    try:
        if not isinstance(edited_data, dict) or not edited_data:
            return
        template_id, schema = _fetch_template_schema_for_extraction(extraction_id)
        if not schema:
            return
        drifts = collect_drifts(edited_data, schema)
        if not drifts:
            return
        # Compact one-line summary suitable for grep
        summary = "; ".join(
            f"{path}: expected {expected}, got {actual}"
            for path, expected, actual in drifts[:20]
        )
        more = f" (+{len(drifts) - 20} more)" if len(drifts) > 20 else ""
        logger.warning(
            f"[SCHEMA_DRIFT] extraction={extraction_id} "
            f"template={template_id} drift_count={len(drifts)} :: {summary}{more}"
        )
    except Exception as e:
        logger.debug(f"[SCHEMA_DRIFT] check failed for {extraction_id}: {type(e).__name__}: {e}")


def schedule_schema_drift_log(
    extraction_id: str,
    edited_data: Dict[str, Any],
) -> None:
    """
    Fire-and-forget wrapper. Offloads DB lookups + walk to a thread so
    nothing on the edit critical path blocks. Safe from any context —
    sync, async, or no event loop.
    """
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Not inside an event loop — run inline; cheap.
            log_schema_drift_sync(extraction_id, edited_data)
            return
        loop.create_task(asyncio.to_thread(
            log_schema_drift_sync,
            extraction_id,
            edited_data,
        ))
    except Exception as e:
        logger.debug(f"[SCHEMA_DRIFT] scheduling failed: {type(e).__name__}: {e}")

"""Conform an extraction dict to a template's assembled JSON schema (the reference field format).

Runs synchronously at extraction finalisation (extraction_service). The template's
assembled_schema_json mirrors references/updated_meeting_response_structure.json (camelCase
per-segment keys), so conforming to it makes the stored output match that reference format
field-for-field.

Behaviour (priority = match the reference field format):
  * MISSING keys           -> added with an empty, type-appropriate default (recursively).
  * MATCHING content       -> preserved exactly (never overwritten).
  * TYPE/SHAPE MISMATCH    -> reset to the reference's empty default for that field
                              (e.g. an object where the reference wants a string).
  * EXTRA keys not in ref  -> dropped, so the output carries exactly the reference's field set.
Arrays of objects: each element is conformed to the item schema (missing item-fields filled,
mismatched reset, extra item-keys dropped). Pure Python, no I/O.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _schema_type(schema: Dict[str, Any]) -> Optional[str]:
    t = schema.get("type")
    if isinstance(t, list):
        return next((x for x in t if x != "null"), (t[0] if t else None))
    return t


def _empty_default(schema: Dict[str, Any]) -> Any:
    """Build an empty value matching a schema (object skeletons built recursively)."""
    if not isinstance(schema, dict):
        return None
    t = _schema_type(schema)
    if t == "object":
        return {
            k: _empty_default(sub if isinstance(sub, dict) else {})
            for k, sub in (schema.get("properties") or {}).items()
        }
    if t == "array":
        return []
    if t == "string":
        return ""
    # number/integer/boolean/unknown -> null: key exists without inventing a value
    return None


def _conform(data: Any, schema: Dict[str, Any], path: str, changes: List[str]) -> Any:
    """Return `data` conformed to `schema`. Adds missing, preserves matching, resets/drops mismatch."""
    if not isinstance(schema, dict):
        return data
    t = _schema_type(schema)

    if t == "object":
        props = schema.get("properties") or {}
        src = data if isinstance(data, dict) else {}
        if not isinstance(data, dict) and data not in (None, ""):
            changes.append(f"reset {path or '<root>'} (expected object)")
        result: Dict[str, Any] = {}
        for key, sub in props.items():
            child = f"{path}.{key}" if path else key
            sub = sub if isinstance(sub, dict) else {}
            if key in src and src[key] is not None:
                result[key] = _conform(src[key], sub, child, changes)
            else:
                result[key] = _empty_default(sub)
                if key not in src:
                    changes.append(f"added {child}")
        # drop any extra keys not in the reference field set
        for key in src:
            if key not in props:
                changes.append(f"dropped {path}.{key}" if path else f"dropped {key}")
        return result

    if t == "array":
        items = schema.get("items")
        if not isinstance(data, list):
            if data not in (None, ""):
                changes.append(f"reset {path} (expected array)")
            return []
        if isinstance(items, dict) and _schema_type(items) == "object":
            return [_conform(el, items, f"{path}[{i}]", changes) for i, el in enumerate(data)]
        return data  # primitive array preserved as-is

    if t == "string":
        if isinstance(data, str):
            return data
        if data is None:
            return ""
        changes.append(f"reset {path} (expected string, got {type(data).__name__})")
        return ""

    if t in ("number", "integer"):
        if isinstance(data, (int, float)) and not isinstance(data, bool):
            return data
        if data is None:
            return None
        changes.append(f"reset {path} (expected {t})")
        return None

    if t == "boolean":
        if isinstance(data, bool) or data is None:
            return data
        changes.append(f"reset {path} (expected boolean)")
        return None

    # unknown schema type: preserve as-is
    return data


def complete_to_schema(data: Dict[str, Any], assembled_schema_json: Any) -> Tuple[Dict[str, Any], List[str]]:
    """Conform `data` to a template's assembled JSON schema (reference field format).

    Returns (conformed_data, changes). `changes` entries are prefixed 'added' / 'reset' / 'dropped'.
    Returns the input unchanged if the schema is unusable.
    """
    schema = assembled_schema_json
    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except Exception:
            return data, []
    if (
        not isinstance(schema, dict)
        or _schema_type(schema) != "object"
        or not schema.get("properties")
        or not isinstance(data, dict)
    ):
        return data, []
    changes: List[str] = []
    conformed = _conform(data, schema, "", changes)
    return conformed, changes

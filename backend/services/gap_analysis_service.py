"""
Template-aware gap analysis for the /api/v1/ehr/extraction-gaps endpoint.

Walks segment_definitions.schema_definition_json dynamically to determine the
expected fields per segment, cross-references admin config stored in
template_segments.gap_analysis_fields_json, then compares against the
extraction data to produce a per-segment missing/captured/partial breakdown.

Output shape is byte-compatible with the legacy hardcoded analyzer
(_check_flat_segment and _check_comorbidities in routers/ehr_integration.py)
so external consumers of the public EHR API see identical responses for the
four legacy segments (vitals, nutritionalScreening, allergy, comorbidities)
after seeding.
"""
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from services.supabase_service import supabase

logger = logging.getLogger(__name__)


# Matches the canonical snake_case -> camelCase used by template_assembly_service
def _to_camel_case(snake_str: str) -> str:
    components = re.split(r"[_\s]+", snake_str.lower())
    components = [c for c in components if c]
    if not components:
        return snake_str.lower()
    return components[0] + "".join(x.title() for x in components[1:])


def _is_empty(value: Any) -> bool:
    """Mirrors ehr_integration._is_empty so output matches legacy byte-for-byte."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def walk_schema_leaves(schema: Dict[str, Any], prefix: str = "") -> List[str]:
    """
    Produce dot-paths for every scalar leaf under an object schema.

    Does NOT descend into arrays — arrays are opaque to the gap analyzer by
    default. If an admin wants to gap-track an array, they can include the
    array's root path explicitly.
    """
    if not isinstance(schema, dict):
        return []

    stype = schema.get("type", "string")
    if stype == "object":
        props = schema.get("properties") or {}
        leaves: List[str] = []
        for key, sub in props.items():
            sub_path = f"{prefix}.{key}" if prefix else key
            sub_type = (sub or {}).get("type", "string") if isinstance(sub, dict) else "string"
            if sub_type == "object":
                leaves.extend(walk_schema_leaves(sub, sub_path))
            else:
                leaves.append(sub_path)
        return leaves
    # At the top-level, a scalar schema has no leaves of interest
    return [prefix] if prefix else []


def classify_segment_shape(schema: Dict[str, Any]) -> str:
    """
    Heuristic classification used to drive both UI rendering and default-leaf
    derivation.

    Returns one of: "flat", "nested_presence", "comorbidity", "array", "unknown".
    """
    if not isinstance(schema, dict):
        return "unknown"

    stype = schema.get("type")
    if stype == "array":
        return "array"
    if stype != "object":
        return "unknown"

    props = schema.get("properties") or {}
    if not props:
        return "unknown"

    # Count object-typed children and their sub-property shapes
    all_object_children = True
    has_status = 0
    has_present = 0
    total = 0
    for _, sub in props.items():
        total += 1
        if not isinstance(sub, dict) or sub.get("type") != "object":
            all_object_children = False
            break
        sub_props = sub.get("properties") or {}
        if "status" in sub_props:
            has_status += 1
        if "present" in sub_props:
            has_present += 1

    if all_object_children and total > 0:
        # Dominant signal: comorbidity entries use .status; presence segments use .present
        if has_status >= total / 2 and has_present == 0:
            return "comorbidity"
        if has_present >= total / 2:
            return "nested_presence"

    return "flat"


def default_leaves_for_shape(shape: str, schema: Dict[str, Any]) -> List[str]:
    """
    Leaves used when gap_analysis_fields_json is NULL (admin hasn't configured).

    Recognized shapes get their conventional leaf set. Arrays default to an
    empty list (not tracked) — admin must opt in.
    """
    if not isinstance(schema, dict):
        return []

    if shape == "flat":
        props = schema.get("properties") or {}
        return list(props.keys())

    if shape == "nested_presence":
        props = schema.get("properties") or {}
        return [f"{key}.present" for key in props.keys()]

    if shape == "comorbidity":
        props = schema.get("properties") or {}
        leaves: List[str] = []
        for key, sub in props.items():
            sub_props = (sub or {}).get("properties") or {}
            if "status" in sub_props:
                leaves.append(f"{key}.status")
            if "since" in sub_props:
                leaves.append(f"{key}.since")
        return leaves

    return []


def _get_nested(data: Any, path: str) -> Any:
    """Walk a dot-path into a nested dict. Returns None if any step is missing."""
    if data is None:
        return None
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


def _analyse_flat(
    segment_data: Dict[str, Any],
    included_leaves: List[str],
) -> Dict[str, Any]:
    """
    For flat segments, missing/captured field names are the leaf paths themselves
    (which for flat segments are single-level keys like "spo2", "pulse").
    Matches _check_flat_segment output byte-for-byte when included_leaves matches
    the legacy field list.
    """
    missing: List[str] = []
    captured: List[str] = []
    for path in included_leaves:
        value = _get_nested(segment_data, path)
        if _is_empty(value):
            missing.append(path)
        else:
            captured.append(path)
    return {
        "total_fields": len(included_leaves),
        "missing_count": len(missing),
        "missing_fields": missing,
        "captured_fields": captured,
    }


def _analyse_comorbidity(
    segment_data: Dict[str, Any],
    included_leaves: List[str],
) -> Dict[str, Any]:
    """
    For comorbidity shapes, aggregate by parent key:
      - parent is missing if its .status leaf is empty (when included)
      - parent is partial if .status=="Yes" and its .since leaf is included+empty

    Matches _check_comorbidities output when included_leaves contains all
    12 parents' .status plus the 4 WITH_SINCE parents' .since leaves.
    """
    status_keys: List[str] = []
    since_keys = set()
    for path in included_leaves:
        if path.endswith(".status"):
            status_keys.append(path.rsplit(".", 1)[0])
        elif path.endswith(".since"):
            since_keys.add(path.rsplit(".", 1)[0])
        else:
            # Unrecognized leaf for comorbidity shape — treat as a flat-style leaf
            status_keys.append(path)

    missing: List[str] = []
    captured: List[str] = []
    partial: List[str] = []

    for parent in status_keys:
        entry = segment_data.get(parent, {}) if isinstance(segment_data, dict) else {}
        entry = entry or {}
        status = entry.get("status", "")
        if _is_empty(status):
            missing.append(parent)
        else:
            captured.append(parent)
            if parent in since_keys and status == "Yes" and _is_empty(entry.get("since")):
                partial.append(parent)

    return {
        "total_fields": len(status_keys),
        "missing_count": len(missing),
        "missing_fields": missing,
        "captured_fields": captured,
        "partial_fields": partial,
    }


def _analyse_nested_presence(
    segment_data: Dict[str, Any],
    included_leaves: List[str],
) -> Dict[str, Any]:
    """
    For nested_presence shapes (e.g. chief_complaints.pnd.present):
      - parent is missing if .present is empty
      - parent is partial if .present == "Yes" and any additionally-tracked
        leaf (e.g. .description) is empty
    """
    presence_parents: List[str] = []
    extra_by_parent: Dict[str, List[str]] = {}
    for path in included_leaves:
        if "." not in path:
            presence_parents.append(path)
            continue
        parent, _, leaf = path.partition(".")
        if leaf == "present":
            if parent not in presence_parents:
                presence_parents.append(parent)
        else:
            extra_by_parent.setdefault(parent, []).append(leaf)

    missing: List[str] = []
    captured: List[str] = []
    partial: List[str] = []

    for parent in presence_parents:
        entry = segment_data.get(parent, {}) if isinstance(segment_data, dict) else {}
        entry = entry or {}
        present = entry.get("present", "")
        if _is_empty(present):
            missing.append(parent)
        else:
            captured.append(parent)
            if present == "Yes":
                for leaf in extra_by_parent.get(parent, []):
                    if _is_empty(entry.get(leaf)):
                        if parent not in partial:
                            partial.append(parent)
                        break

    return {
        "total_fields": len(presence_parents),
        "missing_count": len(missing),
        "missing_fields": missing,
        "captured_fields": captured,
        "partial_fields": partial,
    }


def _analyse_array(
    segment_data: Any,
    included_leaves: List[str],
) -> Dict[str, Any]:
    """
    Arrays are not gap-tracked by default. If the admin explicitly included the
    root leaf (any path), empty or absent array counts as missing.
    """
    if not included_leaves:
        return {
            "total_fields": 0,
            "missing_count": 0,
            "missing_fields": [],
            "captured_fields": [],
        }
    leaf = included_leaves[0]
    is_empty_array = segment_data is None or (isinstance(segment_data, list) and len(segment_data) == 0)
    if is_empty_array:
        return {
            "total_fields": 1,
            "missing_count": 1,
            "missing_fields": [leaf],
            "captured_fields": [],
        }
    return {
        "total_fields": 1,
        "missing_count": 0,
        "missing_fields": [],
        "captured_fields": [leaf],
    }


def analyse_segment(
    shape: str,
    segment_data: Any,
    included_leaves: List[str],
) -> Dict[str, Any]:
    """Dispatch to the shape-specific analyzer."""
    data = segment_data if isinstance(segment_data, dict) else {}
    if shape == "flat":
        return _analyse_flat(data, included_leaves)
    if shape == "comorbidity":
        return _analyse_comorbidity(data, included_leaves)
    if shape == "nested_presence":
        return _analyse_nested_presence(data, included_leaves)
    if shape == "array":
        return _analyse_array(segment_data, included_leaves)
    # unknown — treat as flat if we have any leaves, else empty
    return _analyse_flat(data, included_leaves)


def _load_template_segments(template_id: str) -> List[Dict[str, Any]]:
    """
    Load active template_segments joined with segment_definitions for a given
    template, sorted by display_order. Returns one dict per segment with the
    fields needed for gap analysis and admin-config rendering.
    """
    result = supabase.table("template_segments").select(
        "id, category, display_order, gap_analysis_fields_json, include_in_empty_payload, "
        "segment_definitions!inner(id, segment_code, segment_name, schema_definition_json, is_active)"
    ).eq("template_id", template_id).execute()

    rows: List[Dict[str, Any]] = []
    for row in (result.data or []):
        seg_def = row.get("segment_definitions") or {}
        if not seg_def.get("is_active", True):
            continue
        if row.get("category") == "excluded":
            continue
        schema = seg_def.get("schema_definition_json") or {}
        if isinstance(schema, str):
            import json
            try:
                schema = json.loads(schema)
            except Exception:
                schema = {}
        rows.append({
            "template_segment_id": row.get("id"),
            "segment_definition_id": seg_def.get("id"),
            "segment_code": seg_def.get("segment_code", ""),
            "segment_name": seg_def.get("segment_name", ""),
            "segment_key": _to_camel_case(seg_def.get("segment_code", "")),
            "category": row.get("category", "additional"),
            "display_order": row.get("display_order", 999),
            "schema": schema,
            "gap_analysis_fields_json": row.get("gap_analysis_fields_json"),
            "include_in_empty_payload": row.get("include_in_empty_payload"),
        })
    rows.sort(key=lambda r: r["display_order"])
    return rows


# Legacy camelCase keys that must appear first in the response when present, to
# preserve JSON-key insertion order for external consumers.
_LEGACY_KEY_ORDER = ["vitals", "comorbidities", "allergy", "nutritionalScreening"]


def compute_extraction_gaps(
    extraction_id: str,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, int], Optional[str]]:
    """
    Load the extraction + its template's segments, compute gaps per segment.

    Returns (gaps_dict, summary_dict, template_code). Shape of gaps_dict matches
    ExtractionGapsResponse.gaps; summary_dict matches ExtractionGapsSummary.
    """
    try:
        uuid.UUID(extraction_id)
    except (ValueError, TypeError):
        raise ValueError("Invalid extraction_id format")

    result = supabase.table("medical_extractions").select(
        "id, original_extraction_json, edited_extraction_json, "
        "recording_sessions(template_code)"
    ).eq("id", extraction_id).limit(1).execute()

    if not result.data:
        raise LookupError("Extraction not found")

    row = result.data[0]
    extraction_data = row.get("edited_extraction_json") or row.get("original_extraction_json") or {}
    session = row.get("recording_sessions") or {}
    template_code = session.get("template_code")

    # Resolve template_id from template_code. Not all extractions have a template
    # (legacy rows) — fall back to the legacy hardcoded analysis in that case.
    gaps: Dict[str, Dict[str, Any]] = {}

    if not template_code:
        return gaps, _summarize(gaps), None

    template_result = supabase.table("templates").select("id, template_code").eq(
        "template_code", template_code
    ).limit(1).execute()

    if not template_result.data:
        return gaps, _summarize(gaps), template_code

    template_id = template_result.data[0]["id"]
    segments = _load_template_segments(template_id)

    for seg in segments:
        segment_key = seg["segment_key"]
        schema = seg["schema"]
        shape = classify_segment_shape(schema)
        configured = seg["gap_analysis_fields_json"]

        if configured is None:
            included_leaves = default_leaves_for_shape(shape, schema)
        else:
            # Explicitly configured (including [] = excluded)
            included_leaves = list(configured)

        if not included_leaves:
            # Segment excluded from gap analysis
            continue

        segment_data = extraction_data.get(segment_key) if isinstance(extraction_data, dict) else None
        gaps[segment_key] = analyse_segment(shape, segment_data, included_leaves)

    # Preserve insertion order: legacy keys first (when present), then the rest
    # in display_order. External webapp consumers that iterate may depend on
    # seeing vitals/comorbidities/allergy/nutritionalScreening first.
    ordered: Dict[str, Dict[str, Any]] = {}
    for legacy in _LEGACY_KEY_ORDER:
        if legacy in gaps:
            ordered[legacy] = gaps.pop(legacy)
    for key, value in gaps.items():
        ordered[key] = value

    return ordered, _summarize(ordered), template_code


def _summarize(gaps: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    total_fields = sum(g.get("total_fields", 0) for g in gaps.values())
    total_missing = sum(g.get("missing_count", 0) for g in gaps.values())
    pct = round((total_fields - total_missing) / total_fields * 100) if total_fields > 0 else 100
    return {
        "total_fields": total_fields,
        "total_missing": total_missing,
        "completeness_percentage": pct,
    }

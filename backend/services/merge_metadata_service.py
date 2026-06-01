"""
Merge Metadata Service — schema-driven merge configuration.

Derives, from a template's assembled schema (the camelCase output-key → JSON-schema map
stored on `templates.assembled_schema_json`), the metadata the continuation/merge engines
need to merge extraction segments WITHOUT hardcoding domain-specific segment names:

- which segments are lists (and how to identify items within them),
- which object segments contain nested string-arrays (to union, not overwrite),
- which object segments are scalar (latest-wins),
- which segments are free strings.

This keeps the merge machinery domain-agnostic: it adapts to whatever segments a given
database's templates define (medical on `main`, counselling on `dev`).

Latency: `derive_merge_metadata()` is a pure function over an already-loaded schema.
`get_merge_metadata(template_id)` caches results (TTLCache, 8h) so the continuation hot
path pays at most one schema read per template per TTL window.
"""

import logging
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Scalar JSON-schema types. Anything else ("object", "array") is structural.
_SCALAR_TYPES = {"string", "number", "integer", "boolean", "null"}

# Priority order for choosing the identity field of array-of-object items.
# `task_name` covers counselling TASKS; the generic fallbacks cover other shapes.
_IDENTITY_FIELD_PRIORITY = ("task_name", "name", "title", "label", "item_name", "id")

# Mirror the existing template-cache TTL (8h) used across supabase_service.
_CACHE_TTL_SECONDS = 8 * 60 * 60
_merge_meta_cache: TTLCache = TTLCache(maxsize=100, ttl=_CACHE_TTL_SECONDS)


@dataclass
class MergeMeta:
    """Per-segment (camelCase output key) merge metadata derived from its JSON schema."""
    camel_key: str
    is_list: bool = False
    # array-of-object: the field used to dedupe/match items. None => array-of-scalar
    # (identity is the value itself, e.g. keyFacts strings).
    item_identity_field: Optional[str] = None
    item_is_scalar: bool = False
    # For object segments: dot-paths (as key tuples) to every nested array-of-scalars node.
    nested_array_paths: List[Tuple[str, ...]] = field(default_factory=list)
    is_scalar_object: bool = False   # object with no nested arrays (all leaves scalar -> latest-wins)
    is_object: bool = False
    is_free_string: bool = False


def _pick_identity_field(item_props: Any) -> Optional[str]:
    """Choose the identity field for array-of-object items by priority, case-insensitively."""
    if not isinstance(item_props, dict) or not item_props:
        return None
    lower_map = {k.lower(): k for k in item_props}
    for cand in _IDENTITY_FIELD_PRIORITY:
        if cand in item_props:
            return cand
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def _collect_nested_array_paths(properties: Any) -> List[Tuple[str, ...]]:
    """
    Walk an object schema's `properties`, returning the key-tuple path to every nested
    array-of-scalars node (e.g. ("Planned Activities", "Activities")). Recurses into
    nested objects. Array-of-object nodes are NOT collected (out of scope for string union).
    """
    paths: List[Tuple[str, ...]] = []

    def walk(props: Any, prefix: Tuple[str, ...]) -> None:
        if not isinstance(props, dict):
            return
        for key, node in props.items():
            if not isinstance(node, dict):
                continue
            ntype = node.get("type")
            path = prefix + (key,)
            if ntype == "array":
                items = node.get("items", {})
                item_type = items.get("type") if isinstance(items, dict) else None
                # Treat array-of-scalar (or untyped items) as a unionable string-array.
                if item_type is None or item_type in _SCALAR_TYPES:
                    paths.append(path)
            elif ntype == "object":
                walk(node.get("properties", {}), path)

    walk(properties, ())
    return paths


def derive_merge_metadata(assembled_schema_json: Any) -> Dict[str, MergeMeta]:
    """
    Pure function: derive {camelKey: MergeMeta} from an assembled schema dict of shape
    {"type": "object", "properties": {camelKey: <segment schema>}, ...}.

    Returns {} for malformed/empty input.
    """
    meta: Dict[str, MergeMeta] = {}
    if not isinstance(assembled_schema_json, dict):
        return meta
    properties = assembled_schema_json.get("properties")
    if not isinstance(properties, dict):
        return meta

    for camel_key, node in properties.items():
        if not isinstance(node, dict):
            continue
        m = MergeMeta(camel_key=camel_key)
        ntype = node.get("type")

        if ntype == "array":
            m.is_list = True
            items = node.get("items", {})
            item_type = items.get("type") if isinstance(items, dict) else None
            if item_type == "object":
                m.item_identity_field = _pick_identity_field(items.get("properties", {}))
                m.item_is_scalar = False
            else:
                # array-of-scalar: identity is the value itself
                m.item_identity_field = None
                m.item_is_scalar = True
        elif ntype == "object":
            m.is_object = True
            m.nested_array_paths = _collect_nested_array_paths(node.get("properties", {}))
            # No nested arrays => every leaf is a scalar (or scalar sub-object) => latest-wins.
            m.is_scalar_object = not m.nested_array_paths
        elif ntype == "string":
            m.is_free_string = True
        # other top-level scalar types fall through with all flags False (treated latest-wins)

        meta[camel_key] = m

    return meta


def get_merge_metadata(
    template_id: Any,
    assembled_schema_json: Optional[dict] = None,
) -> Dict[str, MergeMeta]:
    """
    Cached accessor. If `assembled_schema_json` is supplied (slow-path lookups carry it),
    it is used directly with no DB call. Otherwise the schema is loaded once per template
    per TTL window via template_assembly_service.get_template_by_id.

    Returns {} if no schema could be resolved (caller should treat as "no merge metadata"
    and fall back to whole-segment carry-forward).
    """
    key = str(template_id) if template_id else None
    if key and key in _merge_meta_cache:
        return _merge_meta_cache[key]

    schema = assembled_schema_json
    if schema is None and template_id:
        try:
            from services.template_assembly_service import get_template_by_id
            tpl = get_template_by_id(_uuid.UUID(str(template_id)))
            schema = (tpl or {}).get("assembled_schema_json")
        except Exception as e:
            logger.warning(f"[MERGE_META] Could not load assembled schema for template {template_id}: {e}")
            schema = None

    meta = derive_merge_metadata(schema) if schema else {}
    if key and meta:
        _merge_meta_cache[key] = meta
        logger.debug(f"[MERGE_META] Derived metadata for template {key}: {len(meta)} segments")
    return meta


def clear(template_id: Any = None) -> None:
    """Invalidate cached merge metadata. Clears all entries when template_id is None."""
    if template_id is None:
        _merge_meta_cache.clear()
    else:
        _merge_meta_cache.pop(str(template_id), None)

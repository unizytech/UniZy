"""Filter excluded-category segments from extraction JSON at read time.

The extraction pipeline deliberately keeps `category='excluded'` segments in
the assembled prompt and stores them in `original_extraction_json` /
`edited_extraction_json` (so toggling a category on/off doesn't require a
prompt re-assembly). The webhook delivery path strips them before sending
(see `webhook_service.send_insights_to_webhook`). This module provides the
symmetric strip for GET endpoints that read the JSON straight from the DB
and return it to UI / EHR clients — without it, those endpoints leak the
excluded segments that webhook consumers never see.

Internal backend consumers (kg_service, billing, raster_api_service, etc.)
are intentionally NOT filtered — they may still need access to all extracted
fields. This helper is for response surfaces only.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional, Set

from services.supabase_service import supabase

logger = logging.getLogger(__name__)


def _to_camel(snake_code: str) -> str:
    """UPPER_SNAKE_CASE → camelCase. Mirrors webhook_service's conversion."""
    parts = snake_code.lower().split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _excluded_camel_keys(excluded_codes: Iterable[str]) -> Set[str]:
    return {_to_camel(c) for c in excluded_codes if c}


def get_template_excluded_codes(template_code: Optional[str]) -> Set[str]:
    """Return the set of UPPER_SNAKE_CASE segment codes marked
    ``category='excluded'`` for the given template. Returns empty set on any
    error or missing template — the caller should treat empty as "no filtering"."""
    if not template_code:
        return set()
    try:
        tres = (
            supabase.table("templates")
            .select("id")
            .eq("template_code", template_code)
            .limit(1)
            .execute()
        )
        if not tres.data:
            return set()
        template_id = tres.data[0]["id"]

        sres = (
            supabase.table("template_segments")
            .select("category, segment_definitions!inner(segment_code)")
            .eq("template_id", template_id)
            .eq("category", "excluded")
            .execute()
        )
        return {
            (row.get("segment_definitions") or {}).get("segment_code")
            for row in (sres.data or [])
            if (row.get("segment_definitions") or {}).get("segment_code")
        }
    except Exception as e:
        logger.warning(f"[EXCL_FILTER] Failed to load excluded codes for template {template_code}: {e}")
        return set()


def filter_excluded_segments(
    extraction_data: Optional[Dict[str, Any]],
    template_code: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Strip excluded-category segment keys from an extraction JSON dict.

    No-op when:
      * extraction_data is not a dict (None, or some unexpected type)
      * template_code is missing
      * the template has no excluded segments

    Returns a NEW dict — never mutates the caller's object.
    """
    if not isinstance(extraction_data, dict):
        return extraction_data

    excluded_camel = _excluded_camel_keys(get_template_excluded_codes(template_code))
    if not excluded_camel:
        return extraction_data

    stripped_keys = [k for k in extraction_data.keys() if k in excluded_camel]
    if not stripped_keys:
        return extraction_data

    logger.debug(
        f"[EXCL_FILTER] Stripping {len(stripped_keys)} excluded segment(s) "
        f"from response for template {template_code}: {stripped_keys}"
    )
    return {k: v for k, v in extraction_data.items() if k not in excluded_camel}

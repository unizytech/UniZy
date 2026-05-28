"""
Iframe edit-payload normalizer.

The KG hospital edit iframe loads our extraction (which the AI emits in the
"KG Cardio" prescription schema: dose / intake / intake_period / duration /
duration_unit / instructions), renders it in the iframe's own form using
M-N-E-N quantities (morning_qty / noon_qty / evening_qty / night_qty /
durationDays / remarks / timeToTake), and then PUTs the edits back to
``/api/v1/ehr/iframe/edit/{submission_id}`` in the iframe's schema.

If we persist the iframe's payload as-is, ``edited_extraction_json`` ends up
in a different shape than ``original_extraction_json`` and every prescription
edit looks like a massive WER edit (every key is "different" — even when the
underlying drug/dose is identical).

This module converts iframe-shaped prescription items back to the AI's
original schema *before* persistence, but only when a schema mismatch is
actually detected. For templates that natively use M-N-E-N (PSG, OP/Discharge),
no conversion happens.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_INTAKE_PERIOD_ENUMS = {"Regular", "SOS", "STAT", "PRN", "Alternate Days"}

_TIME_TO_TAKE_TO_INTAKE = {
    "before meals": "Before Food",
    "before food": "Before Food",
    "after meals": "After Food",
    "after food": "After Food",
    "empty stomach": "Empty Stomach",
    "anytime": "Anytime",
}


def _norm_qty(v: Any) -> str:
    """Normalize a quantity field. Strips trailing ".0" / whitespace; "" or None → "0"."""
    if v is None:
        return "0"
    s = str(v).strip()
    if not s:
        return "0"
    try:
        f = float(s)
        return str(int(f)) if f == int(f) else s
    except (ValueError, TypeError):
        return s


def _is_kg_cardio_schema(item: Dict[str, Any]) -> bool:
    """Heuristic: KG Cardio prescription items have ``dose`` or ``intake_period`` keys."""
    return "dose" in item or "intake_period" in item or "duration_unit" in item


def _is_iframe_mnenshape(item: Dict[str, Any]) -> bool:
    """Heuristic: iframe-shaped items have ``morning_qty`` or ``durationDays``."""
    return "morning_qty" in item or "durationDays" in item


def _iframe_item_to_kg_cardio(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert one prescription dict from iframe M-N-E-N schema to KG Cardio schema."""
    out: Dict[str, Any] = {}

    # Preserve identity + post-processor matcher fields verbatim
    for k in ("name", "_external_id", "_form", "_formulary_name", "_common_names"):
        if k in item:
            out[k] = item[k]

    # M-A-E-N quantities → "M-A-E-N" dose string
    m = _norm_qty(item.get("morning_qty"))
    n = _norm_qty(item.get("noon_qty"))
    e = _norm_qty(item.get("evening_qty"))
    nt = _norm_qty(item.get("night_qty"))

    if any(q != "0" for q in (m, n, e, nt)):
        out["dose"] = f"{m}-{n}-{e}-{nt}"
    else:
        # Doctor cleared all quantities — preserve any pre-existing dose if iframe
        # left it in (rare), else empty.
        out["dose"] = str(item.get("dose", "") or "")

    # durationDays → duration + duration_unit, with the special case where
    # the iframe stuffs an intake_period enum ("Regular", "SOS", …) into the
    # durationDays field. Recover it into intake_period in that case.
    dd_raw = item.get("durationDays", "")
    dd = str(dd_raw).strip() if dd_raw is not None else ""

    intake_period_from_dd: Optional[str] = None
    if dd in _INTAKE_PERIOD_ENUMS:
        intake_period_from_dd = dd
        out["duration"] = ""
        out["duration_unit"] = ""
    elif dd:
        try:
            days = int(float(dd))
            out["duration"] = str(days)
            out["duration_unit"] = "Day"
        except (ValueError, TypeError):
            out["duration"] = dd
            out["duration_unit"] = ""
    else:
        out["duration"] = ""
        out["duration_unit"] = ""

    # remarks → instructions
    out["instructions"] = item.get("remarks") or item.get("instructions") or ""

    # timeToTake → intake (with mapping). Fall through to whatever the iframe
    # sent if it doesn't match the known phrases.
    ttt = item.get("timeToTake", "")
    ttt_lower = str(ttt).strip().lower() if ttt is not None else ""
    out["intake"] = _TIME_TO_TAKE_TO_INTAKE.get(
        ttt_lower, ttt or item.get("intake", "") or ""
    )

    # route — preserve, default to "Oral"
    out["route"] = item.get("route") or "Oral"

    # intake_period — prefer the value recovered from durationDays, else iframe's
    # explicit intake_period, else "".
    out["intake_period"] = intake_period_from_dd or item.get("intake_period") or ""

    return out


def _normalize_prescription(
    edited_pres: List[Any],
    original_pres: List[Any],
) -> List[Any]:
    """If ``original_pres`` is in KG Cardio schema and ``edited_pres`` is in
    iframe M-N-E-N schema, convert the edited items. Else return as-is."""
    first_orig = next((x for x in original_pres if isinstance(x, dict)), None)
    if not first_orig or not _is_kg_cardio_schema(first_orig):
        return edited_pres

    # Only convert items that actually look iframe-shaped — leave anything else
    # alone (defensive: covers mixed payloads, deletions, etc.).
    converted: List[Any] = []
    any_converted = False
    for item in edited_pres:
        if isinstance(item, dict) and _is_iframe_mnenshape(item):
            converted.append(_iframe_item_to_kg_cardio(item))
            any_converted = True
        else:
            converted.append(item)

    if any_converted:
        logger.info(
            "[IFRAME_NORMALIZE] Converted prescription items from M-N-E-N "
            "iframe schema back to KG Cardio dose schema "
            f"({sum(1 for x in edited_pres if isinstance(x, dict) and _is_iframe_mnenshape(x))} item(s))"
        )
    return converted


def normalize_iframe_edit_payload(
    edited_data: Dict[str, Any],
    original_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Top-level entry point. Returns a new dict — input is not mutated.

    Currently normalizes the ``prescription`` segment. Other segments where
    schema drift may happen (e.g. ``treatmentPlan`` object→array) are
    candidates for follow-up; this function is structured to add them one
    segment at a time without changing callers.
    """
    if not isinstance(edited_data, dict) or not isinstance(original_data, dict):
        return edited_data

    edit_pres = edited_data.get("prescription")
    orig_pres = original_data.get("prescription")
    if not isinstance(edit_pres, list) or not isinstance(orig_pres, list):
        return edited_data
    if not orig_pres or not edit_pres:
        return edited_data

    new_pres = _normalize_prescription(edit_pres, orig_pres)
    if new_pres is edit_pres:
        return edited_data

    return {**edited_data, "prescription": new_pres}

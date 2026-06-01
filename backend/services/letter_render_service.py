"""Letter Render Service

At extraction tail, after the LLM-derived `insights` dict is finalized but
before persist + EHR dispatch, this module:

1. Loads the template's standard text fragments (`template_standard_texts`).
2. Builds a flat context dict from extraction segments + student record + helpers.
3. Resolves `{{ var }}` placeholders inside each fragment.
4. Renders the full Jinja2 layout (`templates.letter_template_jinja`) to a
   single `consult_letter` string.
5. Mutates the `insights` dict in place to add two top-level keys:
   - `standard_texts`: flat dict of resolved fragments.
   - `consult_letter`: the assembled letter (or empty string on failure).

Triggered for any template whose `letter_template_jinja IS NOT NULL` — not
specific to radiology.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime
from typing import Any, Dict, Optional

from jinja2 import Environment, BaseLoader, StrictUndefined, ChainableUndefined, select_autoescape  # noqa: F401

from .supabase_service import supabase

logger = logging.getLogger(__name__)


# ============================================================================
# Jinja2 environment (sandboxed, autoescape disabled — output is plain text)
# ============================================================================

_jinja_env = Environment(
    loader=BaseLoader(),
    autoescape=False,
    # trim_blocks/lstrip_blocks would collapse newlines BETWEEN adjacent {% if %}
    # blocks (e.g. RT_INTENT_LINE next to RT_DOSE_LINE), so we leave them off
    # and rely on the post-render whitespace cleanup below.
    trim_blocks=False,
    lstrip_blocks=False,
    keep_trailing_newline=False,
    # ChainableUndefined: missing vars render as "" and don't blow up on access
    undefined=ChainableUndefined,
)


# ============================================================================
# Helpers
# ============================================================================

def _derive_honorific(sex: Optional[str]) -> str:
    if not sex:
        return ""
    s = sex.strip().lower()
    if s in ("male", "m"):
        return "Mr."
    if s in ("female", "f"):
        return "Mrs."
    return ""


def _compute_age(dob: Any) -> str:
    if not dob:
        return ""
    try:
        if isinstance(dob, str):
            d = datetime.strptime(dob[:10], "%Y-%m-%d").date()
        elif isinstance(dob, datetime):
            d = dob.date()
        elif isinstance(dob, date):
            d = dob
        else:
            return ""
        today = date.today()
        years = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
        return str(years) if years >= 0 else ""
    except Exception:
        return ""


_BLOOD_KEYS = (
    "hb_g_dl", "platelets_lakhs_mm3", "wbc_cells_mm3", "anc_cells_mm3",
    "neutrophils_pct", "creatinine_mg_dl", "albumin_mg_dl", "sodium_meq_l",
    "potassium_meq_l", "calcium_mg_dl",
)


_CAMEL_BOUNDARY_1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_BOUNDARY_2 = re.compile(r"([a-z0-9])([A-Z])")


def _camel_to_snake(name: str) -> str:
    """presentingComplaints → presenting_complaints; PRESENTING_COMPLAINTS → presenting_complaints."""
    s1 = _CAMEL_BOUNDARY_1.sub(r"\1_\2", name)
    return _CAMEL_BOUNDARY_2.sub(r"\1_\2", s1).lower()


def _flatten_insights(insights: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten segment-keyed insights into a single dict.

    Each segment's sub-fields land at top level (e.g. PLAN.rt_dose_gy →
    rt_dose_gy). Last segment wins on key collision (rare in practice).
    String / list / dict scalar values that aren't sub-dicts are also kept
    under their segment_code (uppercase).

    The LLM emits top-level keys in camelCase (e.g. `presentingComplaints`)
    while layouts reference snake_case (`{{ presenting_complaints }}`). Single-
    field segments collapse to a direct scalar (no inner dict to spread), so
    we additionally expose every top-level key under its snake_case alias.
    """
    out: Dict[str, Any] = {}
    if not isinstance(insights, dict):
        return out
    for segment_code, value in insights.items():
        out[segment_code] = value
        snake = _camel_to_snake(segment_code)
        if snake != segment_code and snake not in out:
            out[snake] = value
        if isinstance(value, dict):
            for k, v in value.items():
                out[k] = v
    return out


def _primary_diagnosis(insights: Dict[str, Any]) -> str:
    """Pull primary diagnosis name from common DIAGNOSIS shapes."""
    diag = insights.get("DIAGNOSIS")
    if isinstance(diag, list):
        for d in diag:
            if isinstance(d, dict) and (d.get("type") or "").lower().startswith("primary"):
                return d.get("name") or ""
        if diag and isinstance(diag[0], dict):
            return diag[0].get("name") or ""
    elif isinstance(diag, dict):
        return diag.get("primary") or diag.get("name") or ""
    elif isinstance(diag, str):
        return diag
    return ""


def _referring_counsellor(insights: Dict[str, Any]) -> str:
    # LLM emits camelCase per assembled schema (`referralDetails`).
    # Fall back to UPPER_SNAKE for any legacy / hand-edited extraction JSON.
    ref = insights.get("referralDetails") or insights.get("REFERRAL_DETAILS")
    if isinstance(ref, dict):
        return ref.get("referred_by") or ""
    return ""


# ============================================================================
# Student record fetch
# ============================================================================

def _fetch_student(student_id: Any) -> Dict[str, Any]:
    if not student_id:
        return {}
    try:
        result = supabase.table("students").select(
            "full_name, gender, date_of_birth, add_info"
        ).eq("id", str(student_id)).execute()
        if result.data:
            return result.data[0] or {}
    except Exception as e:
        logger.warning(f"[LETTER_RENDER] Student fetch failed for {student_id}: {e}")
    return {}


# ============================================================================
# Context build
# ============================================================================

def build_letter_context(
    insights: Dict[str, Any],
    student_record: Dict[str, Any],
    session_record: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Flatten insights + add student + helpers into a single Jinja context."""
    ctx = _flatten_insights(insights or {})

    # Student PHI — resolved server-side, never via LLM
    name = (student_record or {}).get("full_name") or ""
    sex = (student_record or {}).get("gender") or ""
    dob = (student_record or {}).get("date_of_birth")
    ctx["patient_name"] = name
    ctx["patient_sex"] = sex
    ctx["patient_age"] = _compute_age(dob)
    ctx["honorific"] = _derive_honorific(sex)

    # Pulled from extraction
    if "primary_diagnosis" not in ctx or not ctx.get("primary_diagnosis"):
        ctx["primary_diagnosis"] = _primary_diagnosis(insights or {})
    if "referring_doctor" not in ctx or not ctx.get("referring_doctor"):
        ctx["referring_doctor"] = _referring_counsellor(insights or {})

    # Computed helpers
    ctx["has_any_blood_value"] = any(ctx.get(k) for k in _BLOOD_KEYS)

    # Derived display helper: MRN parenthetical for the greeting line.
    # Resolves to " (MRN 442187)" when present, "" when absent — keeps the
    # standard_text simple ({{ mrn_paren }}) since the placeholder resolver
    # doesn't run Jinja conditionals.
    mrn_val = str(ctx.get("mrn") or "").strip()
    ctx["mrn_paren"] = f" (MRN {mrn_val})" if mrn_val else ""

    # Hand-fill placeholders for empty PHI fields (printed-form workflow):
    # when student name / age / diagnosis aren't available at extraction
    # time, render an underscore line in the greeting so the counsellor can
    # write the value on the printed letter.
    ctx["patient_name_display"] = str(ctx.get("patient_name") or "").strip() or ("_" * 30)
    ctx["patient_age_display"] = str(ctx.get("patient_age") or "").strip() or "___"
    ctx["primary_diagnosis_display"] = str(ctx.get("primary_diagnosis") or "").strip() or ("_" * 40)

    return ctx


# ============================================================================
# Standard texts: load + resolve placeholders
# ============================================================================

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def _resolve_one(text: str, context: Dict[str, Any]) -> str:
    if not text:
        return ""

    def repl(m: "re.Match[str]") -> str:
        key = m.group(1)
        val = context.get(key, "")
        return "" if val is None else str(val)

    return _PLACEHOLDER_RE.sub(repl, text)


def resolve_standard_texts(
    template_id: uuid.UUID,
    context: Dict[str, Any],
) -> Dict[str, str]:
    """Load active standard texts for `template_id` and resolve placeholders."""
    try:
        result = supabase.table("template_standard_texts").select(
            "key, text, display_order"
        ).eq("template_id", str(template_id)).eq("is_active", True).order("display_order").execute()
    except Exception as e:
        logger.warning(f"[LETTER_RENDER] Failed to load standard texts for {template_id}: {e}")
        return {}

    out: Dict[str, str] = {}
    for row in result.data or []:
        key = row.get("key") or ""
        if not key:
            continue
        out[key] = _resolve_one(row.get("text") or "", context)
    return out


# ============================================================================
# Letter render
# ============================================================================

def _fetch_letter_template(template_id: uuid.UUID) -> Optional[str]:
    try:
        result = supabase.table("templates").select("letter_template_jinja").eq("id", str(template_id)).execute()
        if result.data and result.data[0].get("letter_template_jinja"):
            return result.data[0]["letter_template_jinja"]
    except Exception as e:
        logger.warning(f"[LETTER_RENDER] Failed to load layout for {template_id}: {e}")
    return None


def render_full_letter(
    template_id: uuid.UUID,
    context: Dict[str, Any],
) -> Optional[str]:
    """Render the per-template Jinja layout. Returns None when no layout set."""
    layout = _fetch_letter_template(template_id)
    if not layout:
        return None
    try:
        tmpl = _jinja_env.from_string(layout)
        rendered = tmpl.render(**context)
        # Collapse 3+ blank lines to 2 (paragraph spacing) for readability.
        rendered = re.sub(r"\n{3,}", "\n\n", rendered).strip() + "\n"
        return rendered
    except Exception as e:
        logger.warning(f"[LETTER_RENDER] Jinja render failed for {template_id}: {e}")
        return None


# ============================================================================
# Top-level entrypoint
# ============================================================================

def attach_letter_artifacts(
    insights: Dict[str, Any],
    template_id: Any,
    student_id: Any,
    session_record: Optional[Dict[str, Any]] = None,
) -> None:
    """Mutate `insights` to add `standard_texts` and `consult_letter`.

    Safe to call when `template_id` lacks a layout (fast no-op via empty layout
    check). Always wrapped in try/except by callers; failures here are logged
    but never raised.
    """
    if not template_id:
        return
    try:
        tid = template_id if isinstance(template_id, uuid.UUID) else uuid.UUID(str(template_id))
    except Exception:
        logger.warning(f"[LETTER_RENDER] Invalid template_id: {template_id}")
        return

    layout = _fetch_letter_template(tid)
    if not layout:
        # No rendering for this template; nothing to attach.
        return

    student_record = _fetch_student(student_id)
    context = build_letter_context(insights, student_record, session_record)

    # Resolve fragments first; merge them into context so the layout can reference
    # {{ GREETING_SALUTATION }} etc. directly.
    standard_texts = resolve_standard_texts(tid, context)
    context.update(standard_texts)

    try:
        tmpl = _jinja_env.from_string(layout)
        consult_letter = tmpl.render(**context)
        consult_letter = re.sub(r"\n{3,}", "\n\n", consult_letter).strip() + "\n"
    except Exception as e:
        logger.warning(f"[LETTER_RENDER] Layout render failed for {tid}: {e}")
        consult_letter = ""

    # Mutate insights — these flow into original_extraction_json + ehr_payload_json
    insights["standard_texts"] = standard_texts
    insights["consult_letter"] = consult_letter

    logger.info(
        f"[LETTER_RENDER] Attached {len(standard_texts)} standard texts + "
        f"{len(consult_letter)} char letter for template {tid}"
    )

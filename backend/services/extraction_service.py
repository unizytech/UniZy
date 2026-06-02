"""
Complete template-based extraction workflow.

This service provides the full extraction pipeline used by both:
1. Live recording flow (RecordingProcessor)
2. TRANSCRIPT_ONLY → /extract API flow

Ensures both flows have identical behavior:
- Update session.consultation_type_id
- Save to extractions table
- Schedule emotion extraction (if enabled)
"""

import asyncio
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Schema-derived merge metadata for the CURRENT continuation merge (set at the call site).
# A ContextVar keeps it async-safe across concurrent extractions without threading the
# metadata through every helper signature. Empty dict => fall back to the static medical
# constants below (keeps the medical `main` path working even if a schema can't be loaded).
_merge_meta_ctx: "ContextVar[dict]" = ContextVar("_merge_meta_ctx", default={})


def _merge_meta_for(key: str):
    """Return the MergeMeta for an output key from the current context, or None."""
    meta = _merge_meta_ctx.get()
    return meta.get(key) if meta else None


def _is_merge_list_key(key: str) -> bool:
    """A segment is a merge-able list if the schema says so OR it's a known medical list key."""
    m = _merge_meta_for(key)
    if m is not None and m.is_list:
        return True
    return key in _LIST_SEGMENT_KEYS

# ============================================================================
# LIST AVAILABILITY CACHE (with TTL and invalidation)
# ============================================================================

_list_availability_cache: Dict[str, Dict[str, Any]] = {}
_LIST_CACHE_TTL_SECONDS = 31536000  # 1 year (effectively infinite - invalidated on list updates, cleared on server restart)

def _get_cache_key(counsellor_id: uuid.UUID) -> str:
    return f"list_avail_{counsellor_id}"

def get_cached_list_availability(counsellor_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get cached list availability if not expired."""
    cache_key = _get_cache_key(counsellor_id)
    if cache_key in _list_availability_cache:
        entry = _list_availability_cache[cache_key]
        if datetime.now() < entry["expires_at"]:
            logger.debug(f"[LIST_CACHE] ♻️ Cache HIT for counsellor {str(counsellor_id)[:8]}...")
            return entry["data"]
        else:
            # Expired, remove it
            del _list_availability_cache[cache_key]
    return None

def set_cached_list_availability(counsellor_id: uuid.UUID, data: Dict[str, Any]) -> None:
    """Cache list availability with TTL."""
    cache_key = _get_cache_key(counsellor_id)
    _list_availability_cache[cache_key] = {
        "data": data,
        "expires_at": datetime.now() + timedelta(seconds=_LIST_CACHE_TTL_SECONDS),
        "cached_at": datetime.now()
    }
    logger.debug(f"[LIST_CACHE] 💾 Cached for counsellor {str(counsellor_id)[:8]}... (TTL: ∞, invalidated on update)")

def invalidate_list_cache(counsellor_id: uuid.UUID) -> bool:
    """Invalidate cache for a specific counsellor. Call this when lists are updated."""
    cache_key = _get_cache_key(counsellor_id)
    if cache_key in _list_availability_cache:
        del _list_availability_cache[cache_key]
        logger.debug(f"[LIST_CACHE] 🗑️ Invalidated cache for counsellor {str(counsellor_id)[:8]}...")
        return True
    return False

def invalidate_list_cache_by_school(school_id: uuid.UUID) -> int:
    """Invalidate cache for all counsellors in a school. Call when school lists are updated."""
    # For school-level changes, we invalidate all caches since we don't track counsellor→school mapping here
    # This is a simple approach; a more sophisticated one would track the mapping
    count = len(_list_availability_cache)
    _list_availability_cache.clear()
    logger.debug(f"[LIST_CACHE] 🗑️ Invalidated ALL caches ({count} entries) due to school list update")
    return count

async def check_list_availability_parallel(counsellor_id: uuid.UUID) -> Dict[str, Any]:
    """
    Check medicine and investigation list availability in PARALLEL with caching.

    This replaces the sequential calls to has_medicine_lists() and has_investigation_lists().
    Reduces latency from ~1.2s to ~0.3s (4 sequential calls → 4 parallel calls).

    Args:
        counsellor_id: Counsellor UUID to check

    Returns:
        Dict with keys: has_medicine_list, has_investigation_list, medicine_status, investigation_status
    """
    # Check cache first
    cached = get_cached_list_availability(counsellor_id)
    if cached:
        return cached

    check_start = time.time()

    from services.medicine_service import has_medicine_lists
    from services.investigation_service import has_investigation_lists

    # Run both checks in parallel using asyncio
    medicine_task = asyncio.to_thread(has_medicine_lists, counsellor_id)
    investigation_task = asyncio.to_thread(has_investigation_lists, counsellor_id)

    medicine_status, investigation_status = await asyncio.gather(
        medicine_task, investigation_task
    )

    result = {
        "has_medicine_list": medicine_status["has_any_list"],
        "has_investigation_list": investigation_status["has_any_list"],
        "medicine_status": medicine_status,
        "investigation_status": investigation_status,
    }

    check_duration = time.time() - check_start
    logger.info(
        f"[TIMING_LIST_CHECK] Parallel check: {check_duration:.3f}s "
        f"(medicine={result['has_medicine_list']}, investigation={result['has_investigation_list']})"
    )

    # Cache the result
    set_cached_list_availability(counsellor_id, result)

    return result


# ============================================================================
# CONTINUATION MERGE HELPERS
# ============================================================================

def _is_segment_empty(value: Any) -> bool:
    """Check if a segment value is empty/N/A (all fields are N/A or empty)."""
    if value is None or value == "" or value == "N/A" or value == "Not mentioned" or value == "None":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    if isinstance(value, dict):
        # A dict is "empty" if ALL its values are empty/N/A
        if not value:
            return True
        return all(_is_segment_empty(v) for v in value.values())
    return False


_MERGE_SKIP_KEYS = {"reportMetadata"}

# Keys known to contain list data — safety net union merge applies to these
_LIST_SEGMENT_KEYS = {
    "prescription", "medications", "prescriptionOp", "prescriptionDischarge",
    "medicationChart", "prescriptionItems", "continuingMedications", "antibiotics_list",
    "diagnosis", "diagnosisOp", "diagnosisDischarge",
    "chiefComplaints", "chiefComplaintsOp", "chiefComplaintsDischarge", "complaints",
    "investigations", "investigationsOp", "investigationsDischarge",
    "orderedLabs", "orderedRadiology", "labResults",
    "treatmentPlan", "treatmentPlanAdviceOp", "treatmentPlanAdviceDischarge",
}

# Dict-shaped segments (radiology) that should be merged FIELD-BY-FIELD on
# continuation rather than treated as opaque blobs. When both parent and
# current are non-empty dicts, current wins on per-field conflict and parent
# fills missing fields. Verified unique to RS_* templates as of 2026-04-28
# (no overlap with OP/discharge/PSG segment_codes).
_DICT_FIELD_MERGE_KEYS = {
    "PLAN",
    "EXAMINATION_BREAST", "EXAMINATION_GYN", "EXAMINATION_HN",
    "EXAMINATION_PROSTATE", "EXAMINATION_RECTUM",
    "RT_CONSIDERATIONS",
}

# TOXICITY (radiology) is special — a dict whose two arrays are unioned by
# library_id. Validator-driven removals from these arrays are honored.
_TOXICITY_KEY = "TOXICITY"
_TOXICITY_ARRAY_KEYS = ("early_toxicities", "late_toxicities")

# Radiology site detection: each RS_* template emits exactly one EXAMINATION_<SITE>
# segment. We use the prefix of that key as the canonical "site" signal so the
# merge can detect cross-site continuations (e.g. parent RS_BREAST → current
# RS_PROSTATE) without any DB lookup.
_RADIOLOGY_SITE_PREFIX = "EXAMINATION_"

# Cross-template key equivalence groups.
# When parent has key X and current template uses key Y for the same concept,
# skip copying parent's X if current already has a non-empty Y.
# Each tuple is a group of equivalent keys — order doesn't matter.
_KEY_EQUIVALENCE_GROUPS = [
    # Examination variants
    ("examination", "physicalExamination", "physicalExaminationOp", "physicalExaminationDischarge",
     "generalExamination", "systemicExamination", "surgicalExamination", "mentalStatusExamination"),
    # History variants
    ("history", "historyOp", "historyDischarge", "pastHistory",
     "generalHistory", "surgicalHistory", "hospitalCourse", "psgCourseInHospital"),
    # HPI variants
    ("historyOfPresentIllness", "hpi", "historyOfPresentIllnessOp"),
    # Treatment plan variants
    ("treatmentPlan", "treatmentPlanAdviceOp", "treatmentPlanAdviceDischarge",
     "treatmentPlanAdvice", "treatmentSummary", "treatmentDetails", "carePlanAndAdvice"),
    # Follow-up variants
    ("followUp", "followUpOp", "followUpDischarge", "followUpAndInstructions"),
    # Investigations variants
    ("investigations", "investigationsOp", "investigationsDischarge",
     "orderedLabs", "orderedRadiology", "labResults",
     "psgHospitalInvestigation", "psgInvestigationsProcedure"),
    # Prescription variants
    ("prescription", "prescriptionOp", "prescriptionDischarge", "medications",
     "psgHospitalMedications", "medicationChart", "prescriptionItems",
     "continuingMedications", "antibiotics_list"),
    # Chief complaints variants
    ("chiefComplaints", "chiefComplaintsOp", "chiefComplaintsDischarge", "complaints"),
    # Diagnosis variants
    ("diagnosis", "diagnosisOp", "diagnosisDischarge"),
    # Vitals
    ("vitals",),
    # Allergy variants
    ("allergy", "allergies"),
    # Referral variants
    ("referralDetails", "referralInformation"),
    # Emergency contact variants
    ("emergencyContact", "emergency"),
    # Student info variants
    ("patientInformation", "patientDetails", "patientDemographics"),
]

# Build reverse lookup: key → set of equivalent keys (excluding self)
_KEY_EQUIVALENTS: dict[str, set[str]] = {}
for _group in _KEY_EQUIVALENCE_GROUPS:
    _group_set = set(_group)
    for _k in _group:
        _KEY_EQUIVALENTS[_k] = _group_set - {_k}


def _current_has_equivalent(key: str, insights: dict) -> bool:
    """Check if current output has a non-empty equivalent key for the given parent key."""
    equivalents = _KEY_EQUIVALENTS.get(key)
    if not equivalents:
        return False
    return any(not _is_segment_empty(insights.get(eq)) for eq in equivalents)


# ============================================================================
# Radiology-specific merge helpers (dict-shaped segments + toxicity arrays)
# ============================================================================

def _merge_dict_fields(parent_dict: Any, current_dict: Any) -> dict:
    """Field-by-field merge for dict-shaped segments.

    Current wins on per-field conflict; parent fills fields that are empty in
    current. Non-dict inputs degrade to whichever side is a dict (or empty).
    """
    if not isinstance(current_dict, dict):
        return parent_dict if isinstance(parent_dict, dict) else {}
    if not isinstance(parent_dict, dict):
        return current_dict
    merged: dict = dict(current_dict)
    for k, parent_v in parent_dict.items():
        if _is_segment_empty(merged.get(k)) and not _is_segment_empty(parent_v):
            merged[k] = parent_v
    return merged


def _toxicity_item_id(item: Any) -> str:
    """Stable identifier for a toxicity item (library_id preferred, text fallback)."""
    if not isinstance(item, dict):
        return str(item)
    lib_id = (item.get("library_id") or "").strip()
    if lib_id:
        return f"id:{lib_id}"
    text = (item.get("text") or "").strip().lower()
    return f"text:{text}"


def _union_toxicity_array(
    parent_arr: Any,
    current_arr: Any,
    removed_ids: Optional[set] = None,
) -> list:
    """Dedupe two toxicity arrays by library_id (current wins on conflict).

    Items whose library_id is in `removed_ids` are dropped from the union —
    used to honor validator confirm_removed decisions.
    """
    removed = removed_ids or set()
    out: list = []
    seen: set = set()

    def _push(item: Any) -> None:
        if not isinstance(item, dict):
            return
        lib_id = (item.get("library_id") or "").strip()
        if lib_id and lib_id in removed:
            return
        key = _toxicity_item_id(item)
        if key in seen:
            return
        seen.add(key)
        out.append(item)

    # Current first so it wins on duplicate library_id
    if isinstance(current_arr, list):
        for it in current_arr:
            _push(it)
    if isinstance(parent_arr, list):
        for it in parent_arr:
            _push(it)
    return out


def _merge_toxicity_segment(
    parent_tox: Any,
    current_tox: Any,
    removed_ids_by_array: Optional[dict] = None,
) -> dict:
    """Union early/late toxicity arrays by library_id; current wins on conflict."""
    removed_map = removed_ids_by_array or {}
    if not isinstance(current_tox, dict):
        current_tox = {}
    if not isinstance(parent_tox, dict):
        parent_tox = {}
    merged: dict = dict(current_tox)
    for arr_key in _TOXICITY_ARRAY_KEYS:
        merged[arr_key] = _union_toxicity_array(
            parent_tox.get(arr_key, []),
            current_tox.get(arr_key, []),
            removed_ids=removed_map.get(arr_key),
        )
    return merged


def _lift_toxicity_arrays(data: dict, target: dict) -> None:
    """Surface TOXICITY.early_toxicities / .late_toxicities as top-level keys
    so the validator can review them under its existing list-segment logic.
    """
    tox = data.get(_TOXICITY_KEY)
    if not isinstance(tox, dict):
        return
    for arr_key in _TOXICITY_ARRAY_KEYS:
        arr = tox.get(arr_key)
        if isinstance(arr, list) and arr:
            target[arr_key] = arr


def _radiology_site_from_insights(data: Any) -> Optional[str]:
    """Return the radiology site marker (BREAST/GYN/HN/PROSTATE/RECTUM) embedded
    in an extraction dict, or None if no marker is present. Uses the
    EXAMINATION_<SITE> segment_code as the canonical signal — guaranteed
    unique per RS_* template (see migration audit 2026-04-28)."""
    if not isinstance(data, dict):
        return None
    for k in data:
        if isinstance(k, str) and k.startswith(_RADIOLOGY_SITE_PREFIX):
            return k[len(_RADIOLOGY_SITE_PREFIX):]
    return None


def _smart_merge_continuation(
    insights: dict,
    parent_data: dict,
    current_template_keys: Optional[set] = None,
    validator_result: Optional[Dict[str, Any]] = None,
) -> dict:
    """
    Template-gated safety net for continuation extractions.

    Strategy:
    1. Template-gated empty segment carry-forward (always runs)
    2. If validator ran: apply carry_forward items + cross_segment_patches
    3. If validator did NOT run: no list union (triggers determined it wasn't needed)
    4. NO blind list union — validator is the sole authority for list merges when triggered
    """
    merged_empty = 0
    merged_validator = 0
    removed_count = 0
    enriched_count = 0
    skipped_template = []

    # Cross-site continuation guard — if the parent and current extractions
    # come from different radiology cancer sites (e.g. RS_BREAST → RS_PROSTATE),
    # treat this as a NEW visit rather than a continuation. Visit detection
    # upstream does NOT gate on template/consultation_type, so this can happen
    # for multi-site cancer students seen by the same counsellor in the same window.
    # Wholesale-skip the merge to avoid TOXICITY library_ids and other site-
    # specific data bleeding across.
    parent_site = _radiology_site_from_insights(parent_data)
    current_site = _radiology_site_from_insights(insights)
    if parent_site and current_site and parent_site != current_site:
        logger.warning(
            f"[CONTINUATION_MERGE] Cross-site continuation detected: "
            f"parent={parent_site} → current={current_site}; skipping merge entirely "
            f"to avoid TOXICITY / PLAN contamination across cancer sites."
        )
        return insights

    logger.info(
        f"[CONTINUATION_MERGE] Starting: parent_keys={list(parent_data.keys())} | "
        f"current_keys={list(current_template_keys) if current_template_keys else 'None (permissive)'} | "
        f"validator={'YES' if validator_result else 'NO'}"
    )

    for key, parent_value in parent_data.items():
        if key in _MERGE_SKIP_KEYS or _is_segment_empty(parent_value):
            continue

        # Phase 1: Template gating — skip parent keys not in current template
        if current_template_keys is not None:
            in_template = key in current_template_keys
            if not in_template:
                equivalents = _KEY_EQUIVALENTS.get(key, set())
                in_template = bool(equivalents & current_template_keys)
            if not in_template:
                skipped_template.append(key)
                continue

        current_value = insights.get(key)

        if _is_segment_empty(current_value):
            # Check if current template uses a different key for the same concept
            if _current_has_equivalent(key, insights):
                logger.debug(
                    f"[CONTINUATION_MERGE] Skipped parent '{key}' — current has equivalent key with data"
                )
                continue
            # When validator ran, skip list segments — validator's carry_forward is the authority
            if validator_result and _is_merge_list_key(key) and isinstance(parent_value, list):
                logger.debug(
                    f"[CONTINUATION_MERGE] Skipped list '{key}' — validator will handle via carry_forward"
                )
                continue
            # Wholly empty → copy parent wholesale
            insights[key] = parent_value
            merged_empty += 1
            logger.debug(f"[CONTINUATION_MERGE] Carried forward empty '{key}' from parent")
        else:
            # Phase 1.5: Field-by-field merge for radiology-shaped dict segments.
            # Without this, a counsellor refining ONE field on PLAN/EXAMINATION_<SITE>/
            # RT_CONSIDERATIONS would silently drop all the other parent fields.
            if key in _DICT_FIELD_MERGE_KEYS and isinstance(parent_value, dict) and isinstance(current_value, dict):
                # Plan swap detection: when plan_template_id changes, treat current
                # PLAN as a deliberate replacement and skip field-merge so the prior
                # plan's dose/fractions/technique don't bleed into the new plan.
                if key == "PLAN":
                    p_pid = (parent_value.get("plan_template_id") or "").strip()
                    c_pid = (current_value.get("plan_template_id") or "").strip()
                    if p_pid and c_pid and p_pid != c_pid:
                        logger.info(
                            f"[CONTINUATION_MERGE] PLAN swap detected: {p_pid} → {c_pid}; "
                            f"keeping current PLAN intact (no field-merge to avoid contamination)."
                        )
                        continue

                merged_dict = _merge_dict_fields(parent_value, current_value)
                if merged_dict != current_value:
                    insights[key] = merged_dict
                    merged_empty += 1
                    logger.debug(
                        f"[CONTINUATION_MERGE] Field-merge for '{key}': "
                        f"{len([k for k,v in parent_value.items() if _is_segment_empty(current_value.get(k)) and not _is_segment_empty(v)])} parent fields filled gaps"
                    )
            # Phase 1.6: TOXICITY arrays union by library_id. Current wins per-id;
            # validator's confirm_removed (collected later in Phase 2) is honored
            # by the explicit handler block below.
            elif key == _TOXICITY_KEY and isinstance(parent_value, dict) and isinstance(current_value, dict):
                merged_tox = _merge_toxicity_segment(parent_value, current_value)
                if merged_tox != current_value:
                    insights[key] = merged_tox
                    merged_empty += 1
                    logger.debug(
                        f"[CONTINUATION_MERGE] TOXICITY union: "
                        f"early={len(merged_tox.get('early_toxicities', []))} "
                        f"late={len(merged_tox.get('late_toxicities', []))}"
                    )
            # Phase 1.7: Generic DEEP-merge for any other object segment (counselling
            # studentContext/futureGoals/nextSteps/assessmentMeters/..., or any cross-template
            # object). Without this, a follow-up that touches one nested field would drop the
            # rest of the parent's object. Union nested scalar-arrays; latest-wins on scalars.
            elif isinstance(parent_value, dict) and isinstance(current_value, dict):
                _m = _merge_meta_for(key)
                _nap = set(_m.nested_array_paths) if _m else set()
                merged_obj = _deep_merge_object(parent_value, current_value, _nap)
                if merged_obj != current_value:
                    insights[key] = merged_obj
                    merged_empty += 1
                    logger.debug(f"[CONTINUATION_MERGE] Deep-merged object segment '{key}'")

    # Phase 2: Apply validator results (carry_forward + cross_segment_patches)
    if validator_result:
        # Apply carry_forward items — use validator for WHICH items, but copy FULL object from parent
        for cf_item in validator_result.get("carry_forward", []):
            segment = cf_item.get("segment")
            validator_item = cf_item.get("item")
            if not segment or not validator_item:
                continue

            # Radiology TOXICITY: validator may emit segment="early_toxicities" /
            # "late_toxicities" — route the carry_forward into the TOXICITY dict.
            if segment in _TOXICITY_ARRAY_KEYS:
                tox = insights.setdefault(_TOXICITY_KEY, {})
                if not isinstance(tox, dict):
                    tox = {}
                    insights[_TOXICITY_KEY] = tox
                arr = tox.setdefault(segment, [])
                if not isinstance(arr, list):
                    arr = []
                    tox[segment] = arr
                # Dedupe by library_id (or text fallback)
                cf_id = _toxicity_item_id(validator_item)
                if any(_toxicity_item_id(it) == cf_id for it in arr):
                    continue
                # Look up the FULL parent item if available
                parent_tox = parent_data.get(_TOXICITY_KEY) or {}
                parent_arr = parent_tox.get(segment, []) if isinstance(parent_tox, dict) else []
                full_item = next(
                    (p for p in parent_arr if _toxicity_item_id(p) == cf_id),
                    None,
                ) if isinstance(parent_arr, list) else None
                arr.append(full_item if full_item else validator_item)
                merged_validator += 1
                logger.debug(
                    f"[CONTINUATION_MERGE] Validator carry-forward (toxicity): "
                    f"added {cf_id} to TOXICITY.{segment} — {cf_item.get('reason', 'N/A')}"
                )
                continue

            # Find the correct key in insights (may use equivalent name)
            target_key = _find_equivalent_list_key(segment, insights)
            if not target_key:
                if current_template_keys is None or segment in current_template_keys:
                    target_key = segment
                else:
                    continue

            if target_key not in insights:
                insights[target_key] = []
            if isinstance(insights[target_key], list):
                # Get item name from validator's response
                item_name = _get_item_name(validator_item, target_key)
                if not item_name:
                    continue

                # Dedup check
                existing_names = {
                    (_get_item_name(existing, target_key) or "").lower().strip()
                    for existing in insights[target_key]
                }
                if item_name.lower().strip() in existing_names:
                    continue

                # Look up FULL object from parent_data (validator may return incomplete items)
                parent_segment = parent_data.get(target_key) or parent_data.get(segment) or []
                full_item = None
                if isinstance(parent_segment, list):
                    item_lower = item_name.lower().strip()
                    for p_item in parent_segment:
                        p_name = (_get_item_name(p_item, target_key) or "").lower().strip()
                        if p_name == item_lower or item_lower in p_name or p_name in item_lower:
                            full_item = p_item
                            break

                # Use parent's full object if found, otherwise validator's (partial) object
                item_to_add = full_item if full_item else validator_item
                insights[target_key].append(item_to_add)
                merged_validator += 1
                source = "parent" if full_item else "validator"
                logger.debug(
                    f"[CONTINUATION_MERGE] Validator carry-forward: "
                    f"added '{item_name}' to '{target_key}' (source={source}) — {cf_item.get('reason', 'N/A')}"
                )

        # Apply confirm_removed — remove items from current insights that the validator
        # confirmed should be removed (e.g., investigations with results discussed,
        # vague complaints replaced by specific parent versions)
        for cr_item in validator_result.get("confirm_removed", []):
            segment = cr_item.get("segment")
            cr_name = cr_item.get("item_name", "")
            if not segment or not cr_name:
                continue

            # Radiology TOXICITY: validator may emit segment="early_toxicities" /
            # "late_toxicities" with item_name=library_id. Route the removal into
            # the TOXICITY dict array so the union from Phase 1.6 is trimmed.
            if segment in _TOXICITY_ARRAY_KEYS:
                tox = insights.get(_TOXICITY_KEY)
                if not isinstance(tox, dict):
                    continue
                arr = tox.get(segment)
                if not isinstance(arr, list):
                    continue
                cr_norm = cr_name.strip().lower()
                original_len = len(arr)
                tox[segment] = [
                    it for it in arr
                    if (it.get("library_id") or "").strip().lower() != cr_norm
                    and (it.get("text") or "").strip().lower()[:80] != cr_norm
                ]
                if len(tox[segment]) < original_len:
                    removed_count += 1
                    logger.info(
                        f"[CONTINUATION_MERGE] Validator confirm_removed (toxicity): "
                        f"removed '{cr_name}' from TOXICITY.{segment} — {cr_item.get('reason', 'N/A')}"
                    )
                continue

            target_key = _find_equivalent_list_key(segment, insights)
            if not target_key or not isinstance(insights.get(target_key), list):
                continue
            original_len = len(insights[target_key])
            insights[target_key] = [
                item for item in insights[target_key]
                if (_get_item_name(item, target_key) or "").lower().strip() != cr_name.lower().strip()
            ]
            if len(insights[target_key]) < original_len:
                removed_count += 1
                logger.info(
                    f"[CONTINUATION_MERGE] Validator confirm_removed: removed '{cr_name}' "
                    f"from '{target_key}' — {cr_item.get('reason', 'N/A')}"
                )

        # Apply cross_segment_patches (allergy conflicts, state transitions, investigation results)
        patches_applied = 0
        for patch in validator_result.get("cross_segment_patches", []):
            action = patch.get("action")
            segment = patch.get("segment")
            item_name = patch.get("item_name")

            if action == "add_to_examination":
                # Investigation results → add to examination segment so data isn't lost
                # Find examination key — check all equivalence variants including dict types.
                # For radiology, prefer the EXAMINATION_<SITE> key matching the current
                # extraction's site so the patch lands in the right site-specific dict.
                exam_search_keys = (
                    "examination", "physicalExamination", "physicalExaminationOp",
                    "physicalExaminationDischarge", "generalExamination",
                    "systemicExamination", "surgicalExamination",
                )
                _current_site = _radiology_site_from_insights(insights)
                if _current_site:
                    exam_search_keys = (f"{_RADIOLOGY_SITE_PREFIX}{_current_site}",) + exam_search_keys
                exam_key = next((k for k in exam_search_keys if k in insights), None)
                patch_item = patch.get("item", {})
                inv_name = patch_item.get("name", item_name or "Unknown")
                inv_value = patch_item.get("value", "Results discussed")
                result_text = f"{inv_name}: {inv_value}"

                if exam_key and isinstance(insights.get(exam_key), list):
                    # Standard templates — examination is a list of {name, value}
                    insights[exam_key].append({"name": inv_name, "value": inv_value})
                    patches_applied += 1
                elif exam_key and isinstance(insights.get(exam_key), dict):
                    # Cardio/OG templates — examination is a nested dict
                    # Try known nested paths, then fall back to top-level
                    exam_dict = insights[exam_key]
                    added = False
                    # Try appending to nested sub-dicts that are strings (systemic, general, etc.)
                    for sub_key in ("investigation_results", "findings", "general", "systemic"):
                        if sub_key in exam_dict:
                            val = exam_dict[sub_key]
                            if isinstance(val, str):
                                exam_dict[sub_key] = f"{val}; {result_text}" if val and val != "N/A" else result_text
                                added = True
                                break
                            elif isinstance(val, list):
                                val.append(result_text)
                                added = True
                                break
                            elif isinstance(val, dict):
                                # Nested dict (e.g., systemic.cardiac_examination) — add as new key
                                val["investigation_results"] = val.get("investigation_results", "")
                                val["investigation_results"] = f"{val['investigation_results']}; {result_text}" if val["investigation_results"] else result_text
                                added = True
                                break
                    if not added:
                        # Last resort — add as top-level key in examination dict
                        exam_dict["investigation_results"] = exam_dict.get("investigation_results", "")
                        exam_dict["investigation_results"] = f"{exam_dict['investigation_results']}; {result_text}" if exam_dict["investigation_results"] else result_text
                    patches_applied += 1
                else:
                    # No examination segment (e.g., Neonatal) — log but don't fail
                    logger.warning(
                        f"[CONTINUATION_MERGE] No examination segment found to capture investigation result: "
                        f"'{inv_name}' = '{inv_value}' (template may not support this)"
                    )
                    continue

                logger.info(
                    f"[CONTINUATION_MERGE] Investigation result → {exam_key}: "
                    f"'{inv_name}' = '{inv_value}' — {patch.get('reason', 'N/A')}"
                )
                continue

            if not action or not segment or not item_name:
                continue

            target_key = _find_equivalent_list_key(segment, insights)
            if not target_key or not isinstance(insights.get(target_key), list):
                continue

            if action == "remove":
                original_len = len(insights[target_key])
                insights[target_key] = [
                    item for item in insights[target_key]
                    if (_get_item_name(item, target_key) or "").lower().strip() != item_name.lower().strip()
                ]
                if len(insights[target_key]) < original_len:
                    patches_applied += 1
                    logger.info(
                        f"[CONTINUATION_MERGE] Cross-segment patch: removed '{item_name}' "
                        f"from '{target_key}' — {patch.get('reason', 'N/A')}"
                    )
            elif action == "flag":
                # Log-only: flag for awareness but don't modify data (counsellor decision needed)
                logger.warning(
                    f"[CONTINUATION_MERGE] Cross-segment flag: '{item_name}' in '{target_key}' — "
                    f"{patch.get('type', 'unknown')}: {patch.get('reason', 'N/A')}"
                )

        if patches_applied > 0:
            logger.info(f"[CONTINUATION_MERGE] Applied {patches_applied} cross-segment patches")

    # Phase 3: Field enrichment — restore detail lost by Gemini's "continue as usual" summaries.
    # For list-of-object segments where items match by identity (medical: medicine name;
    # counselling: task_name), copy empty fields from the matching parent item. List-of-string
    # segments (e.g. keyFacts) are skipped naturally — their items aren't dicts.
    _meta = _merge_meta_ctx.get()
    _enrich_keys = set(_LIST_SEGMENT_KEYS) | {k for k, m in _meta.items() if m.is_list}
    for key in _enrich_keys:
        current_list = insights.get(key)
        parent_list = parent_data.get(key)
        if not isinstance(current_list, list) or not isinstance(parent_list, list):
            continue

        # Build parent lookup by normalized name
        parent_lookup = {}
        for p_item in parent_list:
            if not isinstance(p_item, dict):
                continue
            p_name = (_get_item_name(p_item, key) or "").lower().strip()
            if p_name:
                parent_lookup[p_name] = p_item

        if not parent_lookup:
            continue

        for c_item in current_list:
            if not isinstance(c_item, dict):
                continue
            c_name = (_get_item_name(c_item, key) or "").lower().strip()
            if not c_name:
                continue

            # Exact match first, then fuzzy substring match
            # "tablet sepcar" matches "tablet sepcar 800 mg" (strength may change)
            p_item = parent_lookup.get(c_name)
            if not p_item:
                for p_name, p_candidate in parent_lookup.items():
                    if c_name in p_name or p_name in c_name:
                        p_item = p_candidate
                        break
            if not p_item:
                continue
            fields_enriched = []
            for field, p_val in p_item.items():
                if field.startswith("_"):
                    continue  # Skip metadata fields
                c_val = c_item.get(field)
                # Only enrich if current field is empty/missing and parent has a value
                # Note: "0" is a valid dosage value (e.g., noon_qty="0"), so don't treat it as empty
                if (c_val is None or c_val == "") and p_val is not None and p_val != "":
                    c_item[field] = p_val
                    fields_enriched.append(field)

            if fields_enriched:
                enriched_count += 1
                logger.info(
                    f"[CONTINUATION_MERGE] Enriched '{c_name}' in '{key}': "
                    f"restored {fields_enriched} from parent"
                )

    if skipped_template:
        logger.info(f"[CONTINUATION_MERGE] Template-gated: skipped {skipped_template}")

    total = merged_empty + merged_validator + removed_count
    logger.info(
        f"[CONTINUATION_MERGE] Done: "
        f"{merged_empty} empty carried forward, {merged_validator} validator items applied, "
        f"{removed_count} validator items removed, {enriched_count} items enriched from parent, "
        f"{len(skipped_template)} template-gated skips (total actions={total})"
    )

    return insights


def _union_lists(parent_list: list, current_list: list, key: str) -> list:
    """Union two lists, dedup by normalized name. Current wins on conflicts."""
    if not parent_list:
        return current_list
    if not current_list:
        return parent_list

    # Build lookup of current items by normalized name
    current_names = set()
    for item in current_list:
        name = _get_item_name(item, key)
        if name:
            current_names.add(name.lower().strip())

    # Add parent items not in current
    merged = list(current_list)  # Start with current
    for item in parent_list:
        name = _get_item_name(item, key)
        if name and name.lower().strip() not in current_names:
            merged.append(item)
        elif not name:
            # No identifiable name — check for exact duplicates
            if item not in current_list:
                merged.append(item)

    return merged


def _union_string_list(parent_list: list, current_list: list) -> list:
    """Union two arrays preserving current order first, then parent extras.

    Strings dedupe case-insensitively on the FULL trimmed value (status-prefixed items like
    'Ongoing: X' vs 'Completed: X' are intentionally kept distinct). Non-string items dedupe
    by equality. Used for nested string-arrays inside object segments.
    """
    if not isinstance(parent_list, list):
        return current_list
    if not isinstance(current_list, list):
        return parent_list
    merged = list(current_list)
    seen = {v.strip().lower() for v in current_list if isinstance(v, str)}
    for v in parent_list:
        if isinstance(v, str):
            if v.strip().lower() not in seen:
                merged.append(v)
                seen.add(v.strip().lower())
        elif v not in merged:
            merged.append(v)
    return merged


def _is_scalar_list(value: Any) -> bool:
    """True if value is a (possibly empty) list containing only scalar items (str/num/bool)."""
    return isinstance(value, list) and all(
        isinstance(v, (str, int, float, bool)) for v in value
    )


def _deep_merge_object(parent: Any, current: Any, nested_array_paths: Optional[set] = None, path: tuple = ()) -> Any:
    """Recursively DEEP-merge an object segment — never a shallow overwrite or blind append.

    Philosophy (must hold across templates):
    - dict + dict: recurse key-by-key, preserving keys present in only one side.
    - list + list of scalars: UNION (no data loss). Detected structurally so it works even
      when parent/current came from different templates; `nested_array_paths` (from the
      current template's schema, if available) is an additional hint.
    - list + list of objects: current wins (item-level identity merge is handled by the
      validator/Phase-3 for top-level lists; we don't guess identity for nested object-lists).
    - scalar: current wins when non-empty, else inherit parent (latest-wins with carry-forward).
    Empty current values always inherit the parent's value.
    """
    nested_array_paths = nested_array_paths or set()
    if not isinstance(parent, dict) or not isinstance(current, dict):
        return current if not _is_segment_empty(current) else parent

    result = dict(current)
    for k, p_val in parent.items():
        cur_path = path + (k,)
        c_val = current.get(k)
        if k not in current or _is_segment_empty(c_val):
            if not _is_segment_empty(p_val):
                result[k] = p_val
            continue
        if isinstance(p_val, dict) and isinstance(c_val, dict):
            result[k] = _deep_merge_object(p_val, c_val, nested_array_paths, cur_path)
        elif isinstance(p_val, list) and isinstance(c_val, list):
            # Union scalar arrays (structural detection OR schema hint); object-lists: current wins.
            if cur_path in nested_array_paths or (_is_scalar_list(p_val) and _is_scalar_list(c_val)):
                result[k] = _union_string_list(p_val, c_val)
            else:
                result[k] = c_val
        else:
            result[k] = c_val  # scalar latest-wins (current already non-empty)
    return result


def _get_item_name(item: Any, segment_key: str) -> Optional[str]:
    """Extract the name/identifier from a list item based on segment type.

    Schema-driven first: if the current merge metadata names an identity field for this
    segment (e.g. tasks -> task_name), use it. Falls back to the medical heuristics below
    so the legacy/medical path keeps working when no metadata is present.
    """
    if isinstance(item, str):
        return item

    if not isinstance(item, dict):
        return None

    m = _merge_meta_for(segment_key)
    if m is not None and m.item_identity_field:
        val = item.get(m.item_identity_field)
        if val:
            return val
        # fall through to heuristics if the identity field is empty/missing

    key_lower = segment_key.lower()

    if "prescription" in key_lower or "medication" in key_lower or "antibiotic" in key_lower:
        return (item.get("name") or item.get("medicine_name") or item.get("drug_name")
                or item.get("generic_name") or item.get("medicationName") or item.get("drugName"))
    elif "diagnosis" in key_lower:
        return item.get("name") or item.get("diagnosis")
    elif "complaint" in key_lower or "chief" in key_lower:
        return item.get("complaint") or item.get("name")
    elif "investigation" in key_lower or "lab" in key_lower or "radiology" in key_lower:
        return (item.get("name") or item.get("test_name") or item.get("investigation")
                or item.get("study_name") or item.get("investigation_name"))
    elif key_lower in ("early_toxicities", "late_toxicities"):
        # Radiology toxicity items: identify by library_id; fall back to text snippet.
        lib_id = (item.get("library_id") or "").strip()
        if lib_id:
            return lib_id
        text = (item.get("text") or "").strip()
        return text[:80] if text else None
    else:
        return item.get("name") or item.get("title")


# ============================================================================
# CONTINUATION VALIDATOR: Conditional Trigger + Helpers
# ============================================================================

# Keywords indicating an item should be stopped/changed/removed/completed.
# Medical (stop/discontinue medication) + counselling lifecycle (a task is done/dropped).
_STOP_KEYWORDS = [
    # medical
    "stop", "discontinue", "remove", "cancel", "no need", "not required",
    "don't take", "avoid", "only take", "change to", "switch to", "replace",
    "no longer", "withdraw", "off the", "taper off",
    # counselling task lifecycle
    "done", "completed", "complete", "finished", "dropped", "drop that",
    "cancelled", "abandoned", "withdrew", "skip", "no longer needed",
]

# Keywords indicating investigation results are being discussed
_RESULT_KEYWORDS = [
    "results", "report shows", "came back", "values are", "test shows",
    "levels are", "found to be", "reports are", "investigation shows",
    "saw your", "seen your", "looked at", "x-ray shows", "scan shows",
    "is normal", "are normal", "is clear", "it is normal",
]


def _find_equivalent_list_key(key: str, target_dict: dict) -> Optional[str]:
    """Find the equivalent key in target dict using key equivalence groups."""
    if key in target_dict:
        return key
    equivalents = _KEY_EQUIVALENTS.get(key, set())
    for eq in equivalents:
        if eq in target_dict:
            return eq
    return None


def _extract_list_segments(data: dict) -> dict:
    """Extract only list-type segments for validator input (schema-driven, medical fallback)."""
    return {k: v for k, v in data.items() if isinstance(v, list) and v and _is_merge_list_key(k)}


# Non-list segments the validator reasons over for cross-segment checks. Counselling keys
# (futureGoals/academics/...) sit alongside the legacy medical keys; only the keys actually
# present in `data` are surfaced, so this is a harmless union across domains.
_CROSS_SEGMENT_CONTEXT_KEYS = [
    # counselling
    'futureGoals', 'academics', 'directionalChanges', 'assessmentMeters', 'nextSteps',
    # medical (legacy / main)
    'allergy', 'allergies', 'vitals', 'historyOfPresentIllness', 'hpi',
]


def _extract_context_segments(data: dict) -> dict:
    """Extract the non-list context segments used for cross-segment validation."""
    context = {}
    for key in _CROSS_SEGMENT_CONTEXT_KEYS:
        if key in data and not _is_segment_empty(data[key]):
            context[key] = data[key]
    return context


def _should_run_validator(
    parent_lists: dict,
    current_lists: dict,
    insights: dict,
    transcript: str,
) -> tuple:
    """
    Determine if micro-validator should run. Returns (should_run, reasons).
    Pure string operations, ~1-2ms.
    """
    reasons = []
    transcript_lower = transcript.lower()

    logger.info(
        f"[CONTINUATION_VALIDATOR] Trigger check inputs: "
        f"parent_list_keys={list(parent_lists.keys())} "
        f"current_list_keys={list(current_lists.keys())} "
        f"transcript_len={len(transcript)}"
    )

    # Trigger 1: Parent list items missing from current
    for key in parent_lists:
        # Check current_lists first, then fall back to insights keys for the equivalent
        equiv_key = _find_equivalent_list_key(key, current_lists)
        if not equiv_key:
            # Current lists may be empty but segment exists in insights (as empty list)
            equiv_key = _find_equivalent_list_key(key, insights) or key
        parent_names = {(_get_item_name(item, key) or "").lower().strip() for item in parent_lists[key]}
        current_names = {(_get_item_name(item, equiv_key) or "").lower().strip() for item in current_lists.get(equiv_key, [])}
        parent_names.discard("")
        current_names.discard("")
        missing = parent_names - current_names
        if missing:
            reasons.append(f"missing_items:{key}:{len(missing)}")

    # Trigger 2: Parent has list segments + stop/change keywords in transcript
    # Check against insights keys (not just current_lists) because Gemini may have
    # produced empty lists for segments it intends to clear
    if not reasons:
        has_parent_lists = bool(parent_lists)
        has_stop_intent = any(kw in transcript_lower for kw in _STOP_KEYWORDS)
        matched_keywords = [kw for kw in _STOP_KEYWORDS if kw in transcript_lower]
        logger.info(
            f"[CONTINUATION_VALIDATOR] Trigger 2 check: "
            f"has_parent_lists={has_parent_lists} has_stop_intent={has_stop_intent} "
            f"matched_keywords={matched_keywords}"
        )
        if has_parent_lists and has_stop_intent:
            reasons.append("stop_intent_with_parent_lists")

    # Trigger 3: Allergy + prescription both non-empty (student safety)
    allergy_data = next((insights.get(k) for k in ['allergy', 'allergies'] if insights.get(k)), None)
    rx_data = next((insights.get(k) for k in ['prescription', 'prescriptionOp', 'prescriptionDischarge', 'medications'] if insights.get(k)), None)
    if not _is_segment_empty(allergy_data) and not _is_segment_empty(rx_data):
        reasons.append("allergy_prescription_present")

    # Trigger 4: Parent had investigations + transcript mentions results
    parent_has_inv = any(k for k in parent_lists if "investigation" in k.lower() or "lab" in k.lower() or "radiology" in k.lower())
    if parent_has_inv and any(kw in transcript_lower for kw in _RESULT_KEYWORDS):
        reasons.append("investigation_results_mentioned")

    return (len(reasons) > 0, reasons)


# ============================================================================
# ALLERGY-PRESCRIPTION SAFETY CHECK (Phase 4 — pure code, no LLM)
# ============================================================================

def _normalize_drug_name(name: str) -> str:
    """Normalize drug/allergy name for fuzzy matching."""
    return name.lower().strip().rstrip(".,;:")


def _fuzzy_drug_match(drug_name: str, allergy_name: str) -> bool:
    """Check if a drug name matches an allergy name (substring + normalized)."""
    d = _normalize_drug_name(drug_name)
    a = _normalize_drug_name(allergy_name)
    if not d or not a:
        return False
    return d == a or d in a or a in d


def _get_allergy_items(insights: dict) -> list:
    """Extract normalized allergy names from insights."""
    items = []
    for key in ['allergy', 'allergies']:
        val = insights.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.strip():
                    items.append(item.strip())
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("allergen") or item.get("allergy") or ""
                    if name.strip():
                        items.append(name.strip())
        elif isinstance(val, dict):
            # Some templates use dict format for allergies
            for sub_key in ['drug_allergies', 'food_allergies', 'allergies', 'known_allergies']:
                sub_val = val.get(sub_key)
                if isinstance(sub_val, list):
                    for item in sub_val:
                        if isinstance(item, str) and item.strip():
                            items.append(item.strip())
                        elif isinstance(item, dict):
                            name = item.get("name") or item.get("allergen") or ""
                            if name.strip():
                                items.append(name.strip())
                elif isinstance(sub_val, str) and sub_val.strip() and sub_val.strip().lower() not in ("n/a", "none", "not mentioned", "nil"):
                    items.append(sub_val.strip())
    return items


def _get_prescription_items(insights: dict) -> list:
    """Extract drug names from prescription segments."""
    items = []
    for key in ['prescription', 'prescriptionOp', 'prescriptionDischarge', 'medications']:
        val = insights.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.strip():
                    items.append(item.strip())
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("medicine_name") or item.get("drug_name") or ""
                    if name.strip():
                        items.append(name.strip())
    return items


async def _check_allergy_prescription_conflict(extraction_id: str, insights: dict):
    """Pure string-matching check for allergy-prescription conflicts — no LLM call."""
    try:
        allergy_items = _get_allergy_items(insights)
        prescription_items = _get_prescription_items(insights)

        if not allergy_items or not prescription_items:
            return

        conflicts = []
        for drug in prescription_items:
            for allergy in allergy_items:
                if _fuzzy_drug_match(drug, allergy):
                    conflicts.append({"drug": drug, "allergy": allergy})

        if conflicts:
            logger.error(
                f"[SAFETY_ALERT] Allergy-prescription conflict in {extraction_id}: {conflicts}"
            )
    except Exception as e:
        logger.warning(f"[SAFETY_CHECK] Allergy check failed (non-fatal): {e}")


def _find_complaints_key(insights: Dict[str, Any]) -> Optional[str]:
    """Find the chief complaints key in the extraction JSON."""
    for key in ['chiefComplaints', 'chiefComplaintsOp', 'chiefComplaintsDischarge', 'complaints', 'chief_complaints']:
        if key in insights:
            return key
    # Case-insensitive fallback
    for key in insights:
        if 'complaint' in key.lower() or 'chief' in key.lower():
            return key
    return None


def _find_diagnosis_key(insights: Dict[str, Any]) -> Optional[str]:
    """Find the diagnosis key in the extraction JSON."""
    for key in ['diagnosis', 'diagnosisOp', 'diagnosisDischarge']:
        if key in insights:
            return key
    # Case-insensitive fallback
    for key in insights:
        if 'diagnos' in key.lower():
            return key
    return None


# ============================================================================
# BACKGROUND TASK: DB Save Only (Fire-and-Forget)
# ============================================================================

async def _save_extraction_async(
    session_id: uuid.UUID,
    consultation_type_id: uuid.UUID,
    counsellor_id: Optional[uuid.UUID],
    student_id: Optional[uuid.UUID],
    extraction_mode: str,
    model_used: str,
    segments: list,
    full_extraction: Dict[str, Any],
    submission_id: Optional[uuid.UUID],
    transcript_text: str,
    stitching_time_seconds: Optional[float],
    transcription_time_seconds: Optional[float],
    extraction_time_seconds: Optional[float],
    total_processing_time_seconds: Optional[float],
    extraction_id: uuid.UUID,
    recording_metadata_json: Optional[Dict[str, Any]],
    ehr_payload_json: Optional[Dict[str, Any]] = None,
    is_continuation: bool = False,
    parent_extraction_ids: Optional[list] = None,
) -> None:
    """
    Background task for DB save only.

    This runs in fire-and-forget mode to reduce perceived latency.
    Post-processing (medicine/investigation matching) has already completed
    in the main flow before this task is scheduled.

    Args:
        All parameters needed for save_medical_extraction
    """
    import time as time_module
    from services.supabase_service import save_medical_extraction

    try:
        logger.debug(f"[EXTRACTION_ASYNC] Starting DB save for extraction {extraction_id}")
        save_start = time_module.time()

        await asyncio.to_thread(
            save_medical_extraction,
            session_id=session_id,
            consultation_type_id=consultation_type_id,
            counsellor_id=counsellor_id,
            student_id=student_id,
            extraction_mode=extraction_mode,
            model_used=model_used,
            segments=segments,
            full_extraction=full_extraction,
            submission_id=submission_id,
            transcript_text=transcript_text,
            stitching_time_seconds=stitching_time_seconds,
            transcription_time_seconds=transcription_time_seconds,
            extraction_time_seconds=extraction_time_seconds,
            total_processing_time_seconds=total_processing_time_seconds,
            extraction_id=extraction_id,
            recording_metadata_json=recording_metadata_json,
            ehr_payload_json=ehr_payload_json,
            is_continuation=is_continuation,
            parent_extraction_ids=parent_extraction_ids,
        )

        save_duration = time_module.time() - save_start
        logger.info(f"[TIMING_EXTRACTION_ASYNC] DB save completed: {save_duration:.3f}s for extraction {extraction_id}")

        # Seed accuracy metrics for this extraction so unedited records contribute
        # to the WER denominator (otherwise the aggregate is computed only over
        # edited records and biased upward by outliers). Comparing the original
        # against itself yields 0 errors and the AI word count for the
        # denominator — when the counsellor later edits, the row is upserted with
        # real WER values.
        if isinstance(full_extraction, dict) and counsellor_id:
            try:
                from services.accuracy_metrics_service import compute_and_save_accuracy_metrics
                asyncio.create_task(compute_and_save_accuracy_metrics(
                    extraction_id=extraction_id,
                    original_json=full_extraction,
                    edited_json=full_extraction,
                    counsellor_id=str(counsellor_id),
                    transcript_text=transcript_text,
                ))
            except Exception as acc_err:
                logger.warning(f"[EXTRACTION_ASYNC] Failed to seed accuracy metrics: {acc_err}")

    except Exception as e:
        logger.error(f"[EXTRACTION_ASYNC] DB save failed for extraction {extraction_id}: {e}")
        # Don't re-raise - this is fire-and-forget


async def perform_template_extraction(
    transcript: str,
    session_id: uuid.UUID,
    extraction_model: str = "gemini-2.5-flash",
    submission_id: Optional[uuid.UUID] = None,
    cached_artifacts: Optional[Dict[str, Any]] = None,
    # NEW PARAMETERS for timing metrics (passed from recording_processor.py)
    stitching_time_seconds: Optional[float] = None,
    transcription_time_seconds: Optional[float] = None,
    extraction_time_seconds: Optional[float] = None,
    total_processing_time_seconds: Optional[float] = None,
    # Audio data for after_transcription emotion mode
    audio_content: Optional[bytes] = None,
    audio_mime_type: Optional[str] = None,
    # OPTIMIZATION: Pass session dict to avoid re-querying
    session_data: Optional[Dict[str, Any]] = None,
    # Pre-generated extraction_id for parallel emotion analysis
    extraction_id: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    """
    Complete template-based extraction workflow with database updates.

    This function:
    1. Loads session from database
    2. Looks up activated template
    3. Derives consultation_type_id from template
    4. Updates session.consultation_type_id in database
    5. Performs extraction using extract_summary_dynamic()
    6. Saves extraction to extractions table
    7. Schedules triage/consultation insights (fire-and-forget)
    8. Returns extraction results

    NOTE: Emotion analysis is now scheduled in recording_processor.py
    in parallel with extraction for reduced latency.

    Args:
        transcript: Transcribed audio text
        session_id: Recording session UUID
        extraction_model: Gemini model for extraction (default: gemini-2.5-flash)
        submission_id: Optional processing job UUID (for webhook context)
        cached_artifacts: Optional pre-generated artifacts from parallel processing
                         If provided, skips prompt generation step (uses cached prompts/schema)
        stitching_time_seconds: Time to stitch audio chunks (NULL for RecordTab)
        transcription_time_seconds: Time for AI transcription
        extraction_time_seconds: Time for medical insights extraction
        total_processing_time_seconds: Total processing time
        audio_content: Optional audio bytes for after_transcription emotion mode
        audio_mime_type: Optional MIME type of audio (e.g., 'audio/webm')
        extraction_id: Pre-generated UUID for parallel emotion analysis (optional)
                      If provided, the database record will use this ID

    Returns:
        Dict containing:
        - data: Extracted insights
        - metadata: Extraction metadata
        - consultation_type_id: For caller's use
        - session_info: For webhook context

    Raises:
        ValueError: If session not found, template not found, or required data missing
    """
    import time as time_module
    function_start = time_module.time()

    try:
        from services.supabase_service import (
            supabase,
            get_active_template_by_code,
            save_medical_extraction,
        )
        from services.gemini_service import extract_summary_dynamic

        # Step 1: Load session from database (or use passed session_data)
        step1_start = time_module.time()
        if session_data:
            logger.debug(f"[EXTRACTION_SERVICE] ✅ OPTIMIZATION: Using passed session_data (no DB query)")
            session = session_data
        else:
            logger.debug(f"[EXTRACTION_SERVICE] Loading session from database: {session_id}")
            session_response = supabase.table("recording_sessions")\
                .select("*")\
                .eq("id", str(session_id))\
                .limit(1)\
                .execute()

            if not session_response.data:
                logger.error(f"[EXTRACTION_SERVICE] Session not found: {session_id}")
                raise ValueError(f"Session not found: {session_id}")

            session = session_response.data[0]
        template_code = session.get('template_code')
        template_name = session.get('template_name')  # Display name for readability
        extraction_mode = session.get('extraction_mode')
        counsellor_id_str = session.get('counsellor_id')
        student_id_str = session.get('student_id')

        step1_duration = time_module.time() - step1_start
        logger.info(f"[TIMING_EXTRACTION] Step 1 (session load): {step1_duration:.3f}s")
        logger.debug(
            f"[EXTRACTION_SERVICE] Session loaded - template_code={template_code}, "
            f"mode={extraction_mode}, counsellor={counsellor_id_str}"
        )

        # Step 1.5: Check for pre-generated prompts from /live/chunk (parallel prompt generation)
        # For RecordTab sessions, prompts may have been pre-generated when first chunk arrived
        live_cached_prompts = None
        if session.get('transcription_model') == 'gemini-live-api':
            correlation_id = session.get('correlation_id')
            if correlation_id:
                # ⚡ LOG LIVE API USAGE (client-side WebSocket transcription)
                # This logs estimated usage for the Gemini Live API call that happened client-side
                try:
                    from services.chunk_memory_store import get_session_audio_duration
                    from services.llm_usage_service import create_live_api_usage, log_llm_usage

                    live_audio_duration = get_session_audio_duration(correlation_id)
                    if live_audio_duration and live_audio_duration > 0:
                        live_usage = create_live_api_usage(
                            model='gemini-2.5-flash-native-audio-preview-12-2025',
                            session_duration_seconds=live_audio_duration,
                            audio_duration_seconds=live_audio_duration,
                            session_id=session_id,
                            counsellor_id=uuid.UUID(counsellor_id_str) if counsellor_id_str else None,
                            consultation_type_code=template_code,
                            template_code=template_code,
                        )
                        await log_llm_usage(live_usage)
                        logger.info(
                            f"[EXTRACTION_SERVICE] ✅ Logged Live API usage: {live_audio_duration:.1f}s audio, "
                            f"estimated cost=${live_usage.total_cost_usd:.4f}"
                        )
                    else:
                        logger.warning(f"[EXTRACTION_SERVICE] Could not determine audio duration for Live API usage logging")
                except Exception as e:
                    logger.warning(f"[EXTRACTION_SERVICE] Failed to log Live API usage: {e}")
                from routers.recording_session import get_cached_live_prompts
                live_cached_prompts = get_cached_live_prompts(correlation_id)
                if live_cached_prompts:
                    logger.debug(f"[EXTRACTION_SERVICE] ✅ Using pre-generated prompts from /live/chunk (parallel optimization)")
                    # Use cached artifacts - skip list check and artifact generation
                    cached_artifacts = live_cached_prompts.get("artifacts")

                    # CRITICAL: Inject transcript into user_prompt_template
                    # Cached artifacts have user_prompt_template with {transcript} placeholder
                    # We need to create user_prompt with actual transcript for Gemini call
                    if cached_artifacts and cached_artifacts.get("user_prompt_template"):
                        # Use .replace() instead of .format() to avoid JSON curly braces issues
                        user_prompt_with_transcript = cached_artifacts["user_prompt_template"].replace("{transcript}", transcript)
                        logger.debug(f"[EXTRACTION_SERVICE] ✅ Transcript injected into cached user_prompt ({len(transcript)} chars)")

                        # FRESH STUDENT CONTEXT INJECTION
                        # Student context was NOT cached (to ensure we get latest prescriptions/summaries)
                        # Fetch and inject it now
                        cached_student_id = live_cached_prompts.get("student_id")
                        if cached_student_id:
                            try:
                                from services.student_context_service import (
                                    get_student_context_for_extraction,
                                    format_student_context_for_prompt
                                )
                                patient_context = get_student_context_for_extraction(
                                    student_id=cached_student_id,
                                    counsellor_id=counsellor_id_str,
                                    num_past_consultations=3
                                )
                                if patient_context.get("has_context"):
                                    student_context_text = format_student_context_for_prompt(patient_context)
                                    # Inject before "Return ONLY the JSON object" line
                                    if "Return ONLY the JSON object" in user_prompt_with_transcript:
                                        user_prompt_with_transcript = user_prompt_with_transcript.replace(
                                            "Return ONLY the JSON object",
                                            f"{student_context_text}\nReturn ONLY the JSON object"
                                        )
                                    else:
                                        # Fallback: append at end
                                        user_prompt_with_transcript += f"\n{student_context_text}"
                                    logger.debug(
                                        f"[EXTRACTION_SERVICE] ✅ Fresh student context injected for {cached_student_id[:8]}... "
                                        f"(prescriptions={len(patient_context.get('past_prescriptions', []))}, "
                                        f"summaries={len(patient_context.get('past_summaries', []))})"
                                    )
                                else:
                                    logger.debug(f"[EXTRACTION_SERVICE] No student context found for {cached_student_id[:8]}...")
                            except Exception as e:
                                logger.warning(f"[EXTRACTION_SERVICE] Failed to fetch student context: {e}")

                        cached_artifacts = {
                            **cached_artifacts,
                            "user_prompt": user_prompt_with_transcript
                        }

                    # Also skip list check since it was done during prompt generation
                    # Set list_availability from cache to avoid redundant check

        # Step 2: Handle TRANSCRIPT_ONLY mode
        if not extraction_mode or template_code == "TRANSCRIPT_ONLY":
            logger.info("[EXTRACTION_SERVICE] TRANSCRIPT_ONLY mode - skipping extraction")
            return None

        # Step 3: Validate counsellor_id
        counsellor_uuid = uuid.UUID(counsellor_id_str) if counsellor_id_str else None
        if not counsellor_uuid:
            logger.error("[EXTRACTION_SERVICE] No counsellor_id in session")
            raise ValueError("counsellor_id required for template-based extraction")

        # Step 3.5: Check medicine/investigation list availability (PARALLEL + CACHED)
        # This determines whether to inject lists into prompts and run post-processing
        # Optimized: runs both checks in parallel and caches result for 5 minutes
        # SKIP if we have live_cached_prompts (already done during parallel prompt generation)
        step3_start = time_module.time()
        list_check_start = time.time()
        if live_cached_prompts and live_cached_prompts.get("list_availability"):
            # Use cached list availability from parallel prompt generation
            list_availability = live_cached_prompts.get("list_availability")
            logger.info(f"[TIMING_LIST_CHECK] ⚡ SKIPPED - using cached from /live/chunk")
        else:
            list_availability = await check_list_availability_parallel(counsellor_uuid)
            list_check_duration = time.time() - list_check_start
            logger.info(f"[TIMING_LIST_CHECK] Total list availability check: {list_check_duration:.3f}s")

        # Step 4: Look up activated template (OPTIMIZED with session context)
        # Check if session_context_json has template_id - if so, skip redundant lookup
        session_context = session.get('session_context_json', {}) or {}
        active_template = None

        if session_context.get('template_id') and session_context.get('consultation_type_id'):
            # FAST PATH: Use template_id from session context (saved during /start)
            # This eliminates the template lookup query entirely
            logger.debug(
                f"[EXTRACTION_SERVICE] ✅ OPTIMIZATION: Using template_id from session_context "
                f"(template_id={session_context['template_id'][:8]}..., "
                f"has_preassembled={session_context.get('has_preassembled', False)})"
            )
            active_template = {
                "id": session_context['template_id'],
                "template_id": session_context['template_id'],
                "consultation_type_id": session_context['consultation_type_id'],
                "template_code": session_context.get('template_code', template_code),
                "template_name": template_name,
                "is_default": False,
                "is_active": True,
                "source": session_context.get('source', 'session_context'),
                # Include hash values for cache validation
                "prompt_assembly_hash": session_context.get('prompt_assembly_hash'),
                "schema_assembly_hash": session_context.get('schema_assembly_hash'),
            }
        else:
            # SLOW PATH: Session context not available, do full lookup (cached)
            logger.debug(f"[EXTRACTION_SERVICE] Looking up template by code: {template_code} (no session_context)")
            template_lookup_start = time_module.time()
            from services.supabase_service import get_active_template_by_code_cached
            active_template = get_active_template_by_code_cached(counsellor_uuid, template_code)
            template_lookup_duration = time_module.time() - template_lookup_start
            logger.info(f"[TIMING_EXTRACTION] Template lookup (slow path): {template_lookup_duration:.3f}s")

        if not active_template:
            logger.warning(
                f"[EXTRACTION_SERVICE] Template with code '{template_code}' not found, "
                f"attempting default template"
            )

            # Priority 0: Assistant fallback (when session has assistant_id)
            assistant_id_str = session.get('assistant_id')
            if assistant_id_str:
                from services.assistant_templates_service import get_assistant_default_template
                nurse_default = get_assistant_default_template(
                    uuid.UUID(assistant_id_str), counsellor_uuid
                )
                if nurse_default:
                    active_template = get_active_template_by_code_cached(
                        counsellor_uuid, nurse_default["template_code"]
                    )
                    if active_template:
                        logger.info(f"[EXTRACTION_SERVICE] Resolved via assistant fallback: {nurse_default['template_code']}")

            # Priority 1: Counsellor default -> School default
            if not active_template:
                from services.counsellor_templates_service import get_counsellor_default_template
                default_template = get_counsellor_default_template(counsellor_uuid)

                if default_template:
                    active_template = get_active_template_by_code_cached(
                        counsellor_uuid, default_template["template_code"]
                    )
                    if active_template:
                        logger.info(
                            f"[EXTRACTION_SERVICE] Resolved to counsellor/school default: "
                            f"{default_template['template_code']}"
                        )

            # Priority 2: OP_CORE via cached lookup
            if not active_template:
                active_template = get_active_template_by_code_cached(counsellor_uuid, "OP_CORE")
                if active_template:
                    logger.info(f"[EXTRACTION_SERVICE] Resolved to OP_CORE fallback")

            # Priority 3: Error — no template available
            if not active_template:
                raise ValueError(
                    f"No template found for code '{template_code}' and no default template available "
                    f"for counsellor {counsellor_uuid}"
                )

        # Step 5: Get consultation_type_id from template
        consultation_type_id = uuid.UUID(active_template['consultation_type_id'])
        consultation_type_code = active_template.get('template_code')

        step4_duration = time_module.time() - step3_start
        logger.info(f"[TIMING_EXTRACTION] Step 3-4 (list check + template resolve): {step4_duration:.3f}s")
        logger.debug(
            f"[EXTRACTION_SERVICE] Template resolved - consultation_type_id={consultation_type_id}, "
            f"code={consultation_type_code}"
        )

        # Step 6: Update session.consultation_type_id in database (FALLBACK ONLY)
        # This is a fallback for:
        # 1. RecordTab workflow (doesn't go through recording_session.py start_recording())
        # 2. Cases where template_name was changed after session creation
        # If consultation_type_id was already set during session creation, skip this update
        existing_consultation_type_id = session.get('consultation_type_id')
        if not existing_consultation_type_id:
            logger.debug(
                f"[EXTRACTION_SERVICE] ⚠️ consultation_type_id not set during session creation, "
                f"updating now (fallback path)"
            )
            supabase.table('recording_sessions')\
                .update({'consultation_type_id': str(consultation_type_id)})\
                .eq('id', str(session_id))\
                .execute()
        else:
            logger.debug(
                f"[EXTRACTION_SERVICE] ✅ consultation_type_id already set: {existing_consultation_type_id} "
                f"(parallel prompt generation optimization active)"
            )

        # Step 7: Perform extraction using dynamic system
        step7_start = time_module.time()
        # Read continuation context from session_context_json (set during /start background validation)
        is_continuation = session_context.get('is_continuation', False)
        parent_extraction_ids = session_context.get('parent_extraction_ids', [])

        logger.debug(
            f"[EXTRACTION_SERVICE] Starting extraction - "
            f"template_code={template_code}, mode={extraction_mode}, model={extraction_model}, "
            f"cached_artifacts={'present' if cached_artifacts else 'absent'}, "
            f"is_continuation={is_continuation}, parent_extraction_ids_count={len(parent_extraction_ids)}"
        )

        # Voice-aware extraction: for consultation types whose prompts depend on
        # voice cues (e.g. psychology screenings with voice-override-applied logic),
        # attach the audio bytes alongside the transcript so Gemini can reason over both.
        # Default false on every consultation type — opt-in per type.
        attach_audio_to_extraction = False
        try:
            ct_lookup = supabase.table('consultation_types')\
                .select('extraction_includes_audio')\
                .eq('id', str(consultation_type_id))\
                .limit(1)\
                .execute()
            if ct_lookup.data:
                attach_audio_to_extraction = bool(ct_lookup.data[0].get('extraction_includes_audio'))
        except Exception as flag_err:
            logger.warning(
                f"[EXTRACTION_SERVICE] Could not resolve extraction_includes_audio flag (defaulting to false): {flag_err}"
            )

        extraction_audio_content = audio_content if (attach_audio_to_extraction and audio_content) else None
        extraction_audio_mime_type = audio_mime_type if (attach_audio_to_extraction and audio_content) else None
        if attach_audio_to_extraction and not audio_content:
            logger.warning(
                f"[EXTRACTION_SERVICE] consultation type {consultation_type_code} has extraction_includes_audio=true "
                f"but no audio bytes were passed through — falling back to text-only extraction"
            )
        elif attach_audio_to_extraction:
            logger.info(
                f"[EXTRACTION_SERVICE] Voice-aware extraction enabled for {consultation_type_code} "
                f"({len(audio_content) / 1024 / 1024:.1f}MB audio attached)"
            )

        result = await extract_summary_dynamic(
            transcript=transcript,
            consultation_type_id=str(consultation_type_id),
            counsellor_id=str(counsellor_uuid),
            template_code=template_code,
            mode=extraction_mode,
            model=extraction_model,
            cached_artifacts=cached_artifacts,
            session_id=str(session_id),  # Pass for LLM usage tracking
            student_id=student_id_str,  # Pass for history context injection (prescriptions, summaries, caution)
            has_medicine_list=list_availability.get("has_medicine_list", True),
            has_investigation_list=list_availability.get("has_investigation_list", True),
            is_continuation=is_continuation,
            parent_extraction_ids=parent_extraction_ids,
            audio_content=extraction_audio_content,
            audio_mime_type=extraction_audio_mime_type,
            recording_metadata=session.get("recording_metadata_json") if session else None,
        )

        step7_duration = time_module.time() - step7_start
        logger.info(f"[TIMING_EXTRACTION] Step 7 (Gemini extraction call): {step7_duration:.3f}s")
        logger.info(f"[EXTRACTION_SERVICE] Extraction completed successfully")

        # Extract insights from result
        insights = result.get('data', result)

        # Step 8: Build segments list for DB save
        logger.debug(f"[EXTRACTION_SERVICE] Preparing extraction for database save")
        segments = []

        if isinstance(insights, dict):
            for segment_code, segment_value in insights.items():
                if segment_value not in [None, "", "N/A", "Not mentioned", "None"]:
                    segments.append({
                        "segment_code": segment_code,
                        "segment_value": segment_value
                    })

        # Debug: Log timing metrics
        logger.debug(f"[EXTRACTION_SERVICE] Timing metrics:")
        logger.debug(f"[EXTRACTION_SERVICE] - stitching_time_seconds: {stitching_time_seconds}")
        logger.debug(f"[EXTRACTION_SERVICE] - transcription_time_seconds: {transcription_time_seconds}")
        logger.debug(f"[EXTRACTION_SERVICE] - extraction_time_seconds: {extraction_time_seconds}")
        logger.debug(f"[EXTRACTION_SERVICE] - total_processing_time_seconds: {total_processing_time_seconds}")

        # extraction_id is already pre-generated (passed in as parameter)
        logger.debug(f"[EXTRACTION_SERVICE] Using pre-generated extraction_id: {extraction_id}")

        # ============================================================================
        # Step 8.5: POST-PROCESSING (BLOCKING - must complete before return)
        # This corrects medicine/investigation names from counsellor's preferred lists
        # ============================================================================

        # Medicine post-processing (only if counsellor has medicine lists)
        if counsellor_uuid and isinstance(insights, dict) and list_availability.get("has_medicine_list"):
            try:
                import time as time_module
                medicine_postprocess_start = time_module.time()

                from services.medicine_service import postprocess_prescription_extraction

                # Get diagnosis for context (if available)
                diagnosis = ""
                if 'diagnosis' in insights:
                    diag_val = insights['diagnosis']
                    if isinstance(diag_val, dict):
                        diagnosis = diag_val.get('data', str(diag_val))
                    else:
                        diagnosis = str(diag_val) if diag_val else ""

                logger.debug(f"[EXTRACTION_SERVICE] Running medicine post-processing for counsellor {counsellor_uuid}")

                # Post-process prescription - corrects medicine names to match counsellor's list
                insights = await postprocess_prescription_extraction(
                    extraction_data=insights,
                    counsellor_id=counsellor_uuid,
                    extraction_id=extraction_id,
                    submission_id=str(submission_id) if submission_id else str(session_id),
                    diagnosis=diagnosis,
                    template_id=None,
                    log_matches=True
                )

                medicine_postprocess_time = time_module.time() - medicine_postprocess_start
                logger.info(f"[TIMING_POSTPROCESS] Medicine post-processing: {medicine_postprocess_time:.3f}s")

            except Exception as e:
                logger.warning(f"[EXTRACTION_SERVICE] Medicine post-processing failed (non-fatal): {e}")
        elif counsellor_uuid and not list_availability.get("has_medicine_list"):
            logger.debug(f"[EXTRACTION_SERVICE] Skipping medicine post-processing - no lists for counsellor {counsellor_uuid}")

        # Investigation post-processing (only if counsellor has investigation lists)
        if counsellor_uuid and isinstance(insights, dict) and list_availability.get("has_investigation_list"):
            try:
                import time as time_module
                investigation_postprocess_start = time_module.time()

                from services.investigation_service import postprocess_investigations_extraction

                logger.debug(f"[EXTRACTION_SERVICE] Running investigation post-processing for counsellor {counsellor_uuid}")

                # Post-process investigations - corrects investigation names to match counsellor's list
                insights = await postprocess_investigations_extraction(
                    extraction_data=insights,
                    counsellor_id=counsellor_uuid,
                    extraction_id=extraction_id,
                    submission_id=str(submission_id) if submission_id else str(session_id),
                    template_id=None,
                    log_matches=True
                )

                investigation_postprocess_time = time_module.time() - investigation_postprocess_start
                logger.info(f"[TIMING_POSTPROCESS] Investigation post-processing: {investigation_postprocess_time:.3f}s")

            except Exception as e:
                logger.warning(f"[EXTRACTION_SERVICE] Investigation post-processing failed (non-fatal): {e}")
        elif counsellor_uuid and not list_availability.get("has_investigation_list"):
            logger.debug(f"[EXTRACTION_SERVICE] Skipping investigation post-processing - no lists for counsellor {counsellor_uuid}")

        # ============================================================================
        # Step 8.6: CONTINUATION MERGE — Template-Gated Safety Net + Micro-Validator
        # Gemini is the primary merge engine (via continuation prompt with 12 merge
        # principles). This step provides:
        # 1. Template-gated empty segment carry-forward (always)
        # 2. Conditional micro-validator for list merges (only when triggered)
        # 3. Allergy-prescription safety check (fire-and-forget, pure code)
        # Only runs for continuations.
        # ============================================================================
        if is_continuation and isinstance(insights, dict) and student_id_str and parent_extraction_ids:
            try:
                import time as time_module
                from services.supabase_service import supabase as _sb
                from services.history_extraction_utils import get_extraction_data

                # Fetch the most recent parent extraction (transitive — latest has cumulative context)
                parent_result = _sb.table("extractions")\
                    .select("id, original_extraction_json, edited_extraction_json")\
                    .in_("id", parent_extraction_ids)\
                    .order("created_at", desc=True)\
                    .limit(1)\
                    .execute()

                parent_data = get_extraction_data(parent_result.data[0]) if parent_result.data else {}

                # Schema-driven merge metadata for the CURRENT template. Set on a ContextVar
                # that the merge helpers read; always reset in `finally`. (Cross-template
                # continuations still deep-merge correctly via the structural _deep_merge_object
                # path; extractions has no template_id column to look the parent up by.)
                _merge_ctx_token = None
                try:
                    from services.merge_metadata_service import get_merge_metadata
                    _tpl_id = (active_template or {}).get('id') or (active_template or {}).get('template_id')
                    _merge_meta = get_merge_metadata(_tpl_id, (active_template or {}).get('assembled_schema_json'))
                    _merge_ctx_token = _merge_meta_ctx.set(_merge_meta)
                    logger.debug(f"[CONTINUATION_MERGE] Loaded merge metadata: {len(_merge_meta)} segments")
                except Exception as e:
                    logger.warning(f"[CONTINUATION_MERGE] Merge metadata load failed (using medical fallback): {e}")

                if parent_data:
                    # Prepare inputs
                    current_lists = _extract_list_segments(insights)
                    parent_lists = _extract_list_segments(parent_data)
                    # Radiology: surface TOXICITY.early/late arrays so the validator
                    # can review them under its existing list-segment logic.
                    _lift_toxicity_arrays(insights, current_lists)
                    _lift_toxicity_arrays(parent_data, parent_lists)
                    current_template_keys = set(insights.keys())

                    # Conditional validator trigger (~1ms check)
                    should_validate, trigger_reasons = _should_run_validator(
                        parent_lists, current_lists, insights, transcript
                    )

                    validator_result = None
                    if should_validate:
                        logger.info(f"[CONTINUATION_VALIDATOR] Triggered: {trigger_reasons}")
                        try:
                            from services.continuation_validator_service import validate_continuation_merge
                            from services.supabase_service import get_validator_model_by_mode

                            # Fetch configurable model from processing_modes
                            _mode_code = session.get('processing_mode', 'default') or 'default'
                            _validator_model = get_validator_model_by_mode(_mode_code)

                            validator_start = time_module.time()
                            current_context = _extract_context_segments(insights)
                            validator_result = await validate_continuation_merge(
                                current_lists=current_lists,
                                parent_lists=parent_lists,
                                current_non_lists=current_context,
                                transcript=transcript,
                                model=_validator_model,
                            )
                            validator_duration = time_module.time() - validator_start
                            logger.info(f"[TIMING_CONTINUATION_VALIDATOR] {validator_duration:.3f}s")
                        except Exception as e:
                            logger.warning(f"[CONTINUATION_VALIDATOR] Failed (non-fatal): {e}")
                    else:
                        logger.debug("[CONTINUATION_VALIDATOR] Skipped — no triggers matched")

                    # Apply template-gated merge with validator results
                    insights = _smart_merge_continuation(
                        insights, parent_data,
                        current_template_keys=current_template_keys,
                        validator_result=validator_result,
                    )

                    # Phase 4: Fire-and-forget allergy-prescription safety check.
                    # Inert for counselling (no allergy/prescription segments → no-op).
                    try:
                        asyncio.create_task(_check_allergy_prescription_conflict(
                            str(extraction_id), insights
                        ))
                    except Exception as e:
                        logger.warning(f"[SAFETY_CHECK] Failed to schedule allergy check: {e}")

            except Exception as e:
                logger.warning(f"[CONTINUATION_MERGE] Smart merge failed (non-fatal): {e}")
            finally:
                # Always clear the merge-metadata ContextVar for this request.
                _tok = locals().get('_merge_ctx_token')
                if _tok is not None:
                    try:
                        _merge_meta_ctx.reset(_tok)
                    except Exception:
                        pass

        # ============================================================================
        # OUTPUT NORMALISATION: conform the extraction to the template's assembled schema (which
        # mirrors references/updated_meeting_response_structure.json) so the stored output matches
        # that reference field format — missing keys filled with empty defaults, matching content
        # preserved, type-mismatched fields reset, extra keys dropped. Runs BEFORE letter render so
        # rendered artifacts (added below) survive. Synchronous, non-fatal.
        # ============================================================================
        try:
            from services.extraction_output_formatter import complete_to_schema
            _norm_schema = (active_template or {}).get('assembled_schema_json')
            if _norm_schema and isinstance(insights, dict):
                insights, _norm_changes = complete_to_schema(insights, _norm_schema)
                if _norm_changes:
                    logger.info(
                        f"[OUTPUT_FORMATTER] Conformed extraction to reference schema: "
                        f"{len(_norm_changes)} change(s) (e.g. {', '.join(_norm_changes[:5])})"
                    )
        except Exception as e:
            logger.warning(f"[OUTPUT_FORMATTER] Non-fatal normalisation failure: {e}")

        # ============================================================================
        # LETTER RENDER: For templates with a Jinja layout (currently radiology),
        # resolve standard text fragments + render the full consult letter and
        # attach to `insights`. Synchronous (sub-30 ms) so the rendered output
        # ships in both original_extraction_json and the EHR payload below.
        # Failure is non-fatal — logged and skipped.
        # ============================================================================
        try:
            from services.letter_render_service import attach_letter_artifacts
            _letter_template_id = (active_template or {}).get('id') or (active_template or {}).get('template_id')
            if _letter_template_id:
                attach_letter_artifacts(
                    insights,
                    _letter_template_id,
                    student_id_str,
                    session_record=session,
                )
        except Exception as e:
            logger.warning(f"[LETTER_RENDER] Non-fatal render failure: {e}")

        # ============================================================================
        # EHR PAYLOAD: Compute formatted payload for ehr_payload_json
        # (Template-specific lookup formatting removed with the NEO subsystem.)
        # ============================================================================
        ehr_payload = None

        # Rebuild segments from RAW insights (not formatted)
        segments = []
        if isinstance(insights, dict):
            for segment_code, segment_value in insights.items():
                if segment_value not in [None, "", "N/A", "Not mentioned", "None"]:
                    segments.append({
                        "segment_code": segment_code,
                        "segment_value": segment_value
                    })

        # ============================================================================
        # OPTIMIZATION: Fire-and-forget DB save ONLY
        # Post-processing is complete, now save to DB in background
        # This reduces perceived latency by ~0.6s
        # ============================================================================

        # Calculate extraction_time here (includes Gemini call + post-processing)
        # This is more accurate than the passed extraction_time_seconds which was None
        calculated_extraction_time = time_module.time() - function_start

        # Launch background task for DB save only
        asyncio.create_task(
            _save_extraction_async(
                session_id=session_id,
                consultation_type_id=consultation_type_id,
                counsellor_id=counsellor_uuid,
                student_id=uuid.UUID(student_id_str) if student_id_str else None,
                extraction_mode=extraction_mode,
                model_used=extraction_model,
                segments=segments,
                full_extraction=insights,             # RAW -> original_extraction_json
                submission_id=submission_id,
                transcript_text=transcript,
                stitching_time_seconds=stitching_time_seconds,
                transcription_time_seconds=transcription_time_seconds,
                extraction_time_seconds=calculated_extraction_time,  # Use calculated value
                total_processing_time_seconds=total_processing_time_seconds,
                extraction_id=extraction_id,
                recording_metadata_json=session.get('recording_metadata_json'),
                ehr_payload_json=ehr_payload,          # FORMATTED -> ehr_payload_json
                is_continuation=is_continuation,
                parent_extraction_ids=parent_extraction_ids,
            )
        )

        logger.debug(f"[EXTRACTION_SERVICE] DB save scheduled (fire-and-forget) for extraction {extraction_id}")

        # Q&A Engine: Schedule embedding generation (fire-and-forget, no latency impact)
        # This enables semantic search over extractions
        try:
            from services.qa.embedding_job_service import schedule_extraction_embedding
            asyncio.create_task(schedule_extraction_embedding(extraction_id))
            logger.debug(f"[EXTRACTION_SERVICE] Embedding generation scheduled (fire-and-forget) for extraction {extraction_id}")
        except ImportError:
            # Q&A Engine not installed - skip silently
            pass
        except Exception as e:
            # Non-critical: log warning but don't fail extraction
            logger.warning(f"[EXTRACTION_SERVICE] Failed to schedule embedding generation: {e}")

        # Nudge API: Send medical_records (fire-and-forget, zero latency impact)
        try:
            from services.nudge_api_service import send_nudge_medical_records
            send_nudge_medical_records(
                extraction_id=str(extraction_id),
                full_extraction=insights,
                student_id=student_id_str,
                counsellor_id=str(counsellor_uuid) if counsellor_uuid else None,
                template_code=consultation_type_code,
                submission_id=str(submission_id) if submission_id else None,
            )
        except Exception as e:
            logger.warning(f"[EXTRACTION_SERVICE] Failed to schedule Nudge medical_records: {e}")

        # Translation: Schedule Indic language translation (fire-and-forget, zero latency impact)
        try:
            from services.translation_service import schedule_translation
            asyncio.create_task(schedule_translation(
                extraction_id=extraction_id,
                extraction_data=insights,
                counsellor_id=str(counsellor_uuid) if counsellor_uuid else None,
                processing_mode_code=session.get('processing_mode', 'default') or 'default',
            ))
        except Exception as e:
            logger.warning(f"[EXTRACTION_SERVICE] Failed to schedule translation: {e}")

        # NOTE: Emotion analysis scheduling has been moved to recording_processor.py
        # It now runs in parallel with extraction (fire-and-forget) for reduced latency
        # See: recording_processor.py -> process() -> "PARALLEL EMOTION ANALYSIS" section

        # Step 9: Get consultation type for triage/insights toggles
        # Triage/insights scheduling uses _wait_for_extraction_to_exist to handle race condition
        # (extraction record may not exist yet since DB save is fire-and-forget)
        from services.supabase_service import get_consultation_type_by_id_cached
        consultation_type = get_consultation_type_by_id_cached(consultation_type_id)

        # Step 9a.5: Generate triage suggestions + consultation insights (fire-and-forget)
        # Chain: triage → consultation_insights → severity → clinical_needs → allied_health → dropoff → care_quality
        # Runs triage engine to detect red flags, missing investigations, etc.
        # Then schedules care quality risk assessment after triage completes
        enable_triage = consultation_type.get('enable_triage_analysis', True) if consultation_type else True
        enable_emotion = consultation_type.get('enable_emotion_analysis', True) if consultation_type else True

        # For RecordTab (live sessions): derive insights from emotion AND triage (ignore DB setting)
        # For normal VHR flow: read from DB as usual
        is_live_session = session.get('transcription_model') == 'gemini-live-api'
        if is_live_session:
            # RecordTab: insights enabled only when BOTH emotion and triage are enabled
            enable_insights = enable_emotion and enable_triage
            logger.debug(f"[EXTRACTION_SERVICE] Live session - Triage: {enable_triage}, Emotion: {enable_emotion}, Insights (derived): {enable_insights}")
        else:
            # Normal VHR flow: read from DB
            enable_insights = consultation_type.get('enable_consultation_insights', True) if consultation_type else True
            logger.debug(f"[EXTRACTION_SERVICE] VHR session - Triage: {enable_triage}, Insights (from DB): {enable_insights}")

        if not enable_triage and not enable_insights:
            # Both disabled - skip entirely
            logger.debug(f"[EXTRACTION_SERVICE] Triage and consultation insights disabled for this consultation type - skipping")
        elif enable_triage:
            # Triage enabled - schedule triage (may or may not chain to insights based on flag)
            try:
                from services.background_tasks import schedule_triage_generation

                await schedule_triage_generation(
                    extraction_id=extraction_id,
                    transcript=transcript,  # Pass transcript for consultation insights extraction
                    extraction_data=insights,  # Pass extraction data for downstream services
                    counsellor_id=str(counsellor_uuid) if counsellor_uuid else None,
                    student_id=student_id_str,
                    consultation_type_code=consultation_type_code,
                    include_gemini=True,  # Use Gemini AI for richer triage insights
                    enable_consultation_insights=enable_insights,  # Pass insights toggle
                )
                logger.debug(f"[EXTRACTION_SERVICE] Scheduled triage generation for extraction {extraction_id}")
            except Exception as e:
                logger.warning(f"[EXTRACTION_SERVICE] Failed to schedule triage generation: {e}")
        else:
            # Triage disabled, but insights enabled - schedule insights directly (skip triage)
            try:
                from services.background_tasks import schedule_consultation_insights_extraction

                await schedule_consultation_insights_extraction(
                    extraction_id=extraction_id,
                    transcript=transcript,
                    extraction_data=insights,
                    counsellor_id=str(counsellor_uuid) if counsellor_uuid else None,
                    student_id=student_id_str,
                )
                logger.debug(f"[EXTRACTION_SERVICE] Scheduled consultation insights directly (triage disabled) for extraction {extraction_id}")
            except Exception as e:
                logger.warning(f"[EXTRACTION_SERVICE] Failed to schedule consultation insights: {e}")

        # Step 9b: Unified EHR Routing (fire-and-forget)
        # Routes to EHR based on counsellor's ehr_type_id (not template)
        # - Counsellor's ehr_type_id determines which EHR to send to
        # - School's config provides the URL for that EHR type
        # - Template code is used for Neopead URL suffix lookup
        if counsellor_uuid:
            try:
                from services.ehr_routing_service import schedule_ehr_sync

                # Build patient_info dict with all fields needed by various EHRs
                patient_info = {}

                # UHID: Prefer student_identifier from session (passed by EHR in recording API call)
                # Falls back to students table lookup if session value not available
                session_uhid = session.get("student_identifier", "") if session else ""

                # Fetch student data for EHR routing (add_info for Raster/Neopead)
                if student_id_str:
                    try:
                        student_result = supabase.table("students").select(
                            "student_id, add_info"
                        ).eq("id", student_id_str).execute()

                        if student_result.data:
                            student_record = student_result.data[0]
                            patient_info["student_id"] = session_uhid or student_record.get("student_id", "")  # UHID
                            student_add_info = student_record.get("add_info") or {}

                            # Neopead fields from add_info (Raster fields now come from recording_metadata)
                            patient_info["neopead_add_info"] = student_add_info

                            logger.debug(f"[EXTRACTION_SERVICE] Built patient_info for EHR routing: uhid={patient_info.get('student_id')} (from={'session' if session_uhid else 'db'})")
                    except Exception as e:
                        logger.warning(f"[EXTRACTION_SERVICE] Failed to fetch student data for EHR: {e}")

                # If student DB lookup failed but we have session UHID, still set it
                if not patient_info.get("student_id") and session_uhid:
                    patient_info["student_id"] = session_uhid

                # Fetch school_code for Aosta
                if counsellor_uuid:
                    try:
                        counsellor_result = supabase.table("counsellors").select(
                            "school_id, schools(school_code)"
                        ).eq("id", str(counsellor_uuid)).execute()

                        if counsellor_result.data:
                            school_data = counsellor_result.data[0].get("schools") or {}
                            patient_info["school_code"] = school_data.get("school_code", "")
                            patient_info["counsellor_id"] = str(counsellor_uuid)
                    except Exception as e:
                        logger.warning(f"[EXTRACTION_SERVICE] Failed to fetch school code for EHR: {e}")

                # KG formatter reads patient_info["patient_uuid"] (the extractions.student_id
                # UUID, distinct from the UHID string stored at patient_info["student_id"]).
                if student_id_str:
                    patient_info["patient_uuid"] = student_id_str

                # Get recording metadata for EHR routing fields
                if session:
                    recording_metadata = session.get("recording_metadata_json") or {}
                    # Aosta fields
                    patient_info["ip_id"] = recording_metadata.get("ip_id")
                    patient_info["op_id"] = recording_metadata.get("op_id")
                    # KG fields
                    patient_info["visit_id"] = recording_metadata.get("visit_id", "")
                    patient_info["role"] = recording_metadata.get("role", "")
                    # Raster fields (directly from recording_metadata, same pattern as Aosta)
                    patient_info["visit_number"] = recording_metadata.get("visit_number", "")
                    patient_info["consultant_id"] = recording_metadata.get("consultant_id", 0)
                    _rm_cuid = recording_metadata.get("created_user_id") or recording_metadata.get("modified_user_id", 0)
                    patient_info["created_user_id"] = _rm_cuid
                    patient_info["modified_user_id"] = _rm_cuid
                    patient_info["sex"] = recording_metadata.get("sex")
                    # Raster New OP field — iframe clients send "template_id";
                    # legacy key "template_id_raster" kept for back-compat.
                    from services.raster_api_service import extract_raster_template_id
                    patient_info["template_id_raster"] = extract_raster_template_id(recording_metadata)
                    # GEM_CASE_SHEET / GCC_REVIEW fields (sent to Aosta URL with Template_id/Template_Name)
                    patient_info["template_id_aosta"] = recording_metadata.get("template_id") or recording_metadata.get("Template_id") or ""
                    patient_info["template_name_aosta"] = recording_metadata.get("template_name") or recording_metadata.get("Template_Name") or ""

                extraction_data = insights.copy()

                # NEW: Publish to realtime table (fire-and-forget, zero latency impact)
                try:
                    from services.realtime_publisher_service import publish_extraction_response_fire_and_forget

                    # Get school_id from counsellor lookup (already done above)
                    school_id_for_realtime = None
                    if counsellor_result and counsellor_result.data:
                        school_id_for_realtime = counsellor_result.data[0].get("school_id")

                    if school_id_for_realtime and submission_id:
                        asyncio.create_task(publish_extraction_response_fire_and_forget(
                            submission_id=str(submission_id),
                            school_id=school_id_for_realtime,
                            counsellor_id=str(counsellor_uuid) if counsellor_uuid else None,
                            extraction_id=str(extraction_id),
                            insights=insights,
                            school_code=patient_info.get("school_code"),
                            recording_metadata=recording_metadata if session else None,
                            uhid=patient_info.get("student_id", ""),
                        ))
                except Exception as e:
                    logger.warning(f"[EXTRACTION_SERVICE] Failed to schedule realtime publish: {e}")

                # Schedule EHR sync (fire-and-forget based on counsellor's ehr_type_id)
                schedule_ehr_sync(
                    counsellor_id=str(counsellor_uuid),
                    extraction_data=extraction_data,
                    patient_info=patient_info,
                    template_code=consultation_type_code,
                    is_edit=False,
                    extraction_id=str(extraction_id),
                )

            except Exception as e:
                logger.warning(f"[EXTRACTION_SERVICE] Failed to schedule EHR sync: {e}")

        # Step 10: Prepare return data
        session_info = {
            'correlation_id': session.get('correlation_id'),
            'submission_id': str(submission_id) if submission_id else None,
            'extraction_id': str(extraction_id),  # Always include for webhook tracking
            'session_id': str(session_id),
            'counsellor_id': str(counsellor_uuid),
            'student_id': student_id_str,
            'template_code': template_code,  # Unique identifier for DB lookups
            'template_name': template_name,  # Display name for readability
            'extraction_mode': extraction_mode,
            'processing_mode': session.get('processing_mode'),
            'consultation_type_code': consultation_type_code,
        }

        # 🔍 DETAILED LOGGING: Log data being returned to frontend
        logger.debug(f"[EXTRACTION_RETURN] ========== DATA RETURNING TO FRONTEND ==========")
        logger.debug(f"[EXTRACTION_RETURN] Consultation Type: {consultation_type_code}")
        logger.debug(f"[EXTRACTION_RETURN] Template Name: {template_name}")
        logger.debug(f"[EXTRACTION_RETURN] Extraction Mode: {extraction_mode}")
        logger.debug(f"[EXTRACTION_RETURN] Extraction ID: {extraction_id}")

        if insights:
            logger.debug(f"[EXTRACTION_RETURN] Insights Type: {type(insights).__name__}")
            logger.debug(f"[EXTRACTION_RETURN] Insights Keys: {list(insights.keys())}")
            logger.debug(f"[EXTRACTION_RETURN] Total Fields: {len(insights)}")

            # Check if segmented or flat
            if insights and isinstance(list(insights.values())[0] if insights else None, dict):
                logger.debug(f"[EXTRACTION_RETURN] Segmented Data - Segment Names: {list(insights.keys())}")
            else:
                logger.debug(f"[EXTRACTION_RETURN] Flat Data Structure")
        else:
            logger.warning(f"[EXTRACTION_RETURN] ⚠️  No insights data!")

        logger.debug(f"[EXTRACTION_RETURN] Metadata: {result.get('metadata', {})}")
        logger.debug(f"[EXTRACTION_RETURN] =============================================")

        # Log total function time
        function_duration = time_module.time() - function_start
        logger.info(f"[TIMING_EXTRACTION] ✅ perform_template_extraction TOTAL: {function_duration:.3f}s")

        return {
            'data': insights,
            'metadata': result.get('metadata', {}),
            'consultation_type_id': str(consultation_type_id),
            'extraction_id': str(extraction_id),
            'session_info': session_info,
            'excluded_segment_codes': result.get('excluded_segment_codes', set()),  # For response filtering
        }

    except Exception as e:
        logger.error(f"[EXTRACTION_SERVICE] Extraction failed: {e}", exc_info=True)
        raise

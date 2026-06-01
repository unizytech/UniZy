"""
Student Context Service for Prompt Injection

This service fetches relevant student history data to inject into extraction prompts:
1. Past prescriptions - for medicine continuity when counsellor says "continue previous medicines"
2. Past SUMMARY segments - for enriching history when relevant to current symptoms
3. CAUTION segment - for safety alerts about allergies and limitations

The context is formatted for injection into the user prompt to give Gemini
relevant student history for more accurate extraction.
"""

import json
import uuid
import logging
import time
from typing import Dict, Any, Optional, List

from services.history_extraction_utils import (
    extract_and_normalize_prescription,
    get_extraction_data,
    get_segment_from_extraction,
    get_segments_batch,
    extract_chief_complaints,
    find_segment_value,
    extract_complaints_list,
    extract_diagnosis_list,
)

logger = logging.getLogger(__name__)

_EMPTY_SENTINELS = {"", "n/a", "not mentioned", "none", "null"}


def _is_value_empty(value: Any) -> bool:
    """Domain-agnostic emptiness check for a segment value."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _EMPTY_SENTINELS
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def get_student_context_for_extraction(
    student_id: str,
    counsellor_id: Optional[str] = None,
    num_past_consultations: int = 2,
    is_continuation: bool = False,
    parent_extraction_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Fetch relevant student history for prompt injection.

    Both modes use only the MOST RECENT extraction (transitive — latest already
    contains prior context via the enrichment chain).

    Two modes:
    - Continuation mode (is_continuation=True): Fetch prescription, SUMMARY, and
      CAUTION from the most recent parent extraction. Full enrichment with
      conflict resolution (current transcript always wins).
    - New consultation mode (is_continuation=False, default): Fetch latest 1
      extraction. Prescriptions + cautions from all (current + linked counsellors),
      summaries only from current counsellor.

    Args:
        student_id: Student UUID string
        counsellor_id: Optional counsellor UUID string to filter consultations
        num_past_consultations: Number of past consultations to consider (unused, kept for API compat)
        is_continuation: Whether this is a continuation of a prior visit (default: False)
        parent_extraction_ids: List of parent extraction IDs for continuation mode (default: None)

    Returns:
        Dict with:
            - past_prescriptions: List of past prescription data
            - past_summaries: List of past SUMMARY segment data
            - caution_aggregated: Aggregated CAUTION data
            - has_context: Boolean indicating if any context was found
            - context_mode: "continuation" or "new_consultation"
            - parent_extraction_ids: List of parent extraction IDs (if continuation)
    """
    from services.supabase_service import supabase

    result = {
        "past_prescriptions": [],
        "past_summaries": [],
        "caution_aggregated": None,  # Changed: Now aggregates from multiple extractions
        "parent_chief_complaints": [],
        "parent_diagnosis": [],
        "parent_hpi": None,
        "parent_vitals": None,
        "parent_examination": None,
        "parent_treatment_plan": None,
        "parent_follow_up": None,
        "parent_investigations": None,
        "parent_history": None,
        "parent_referral": None,
        "parent_emergency_contact": None,
        "parent_patient_info": None,
        "parent_report_metadata": None,
        "parent_comorbidities": None,
        "parent_allergy": None,
        "parent_nutritional_screening": None,
        # Domain-agnostic: the FULL prior extraction record. Used to deep-merge continuations
        # for ANY template (counselling and others) without hardcoding per-segment keys.
        "parent_full_record": None,
        "has_context": False,
        "context_mode": "continuation" if is_continuation else "new_consultation",
        "parent_extraction_ids": parent_extraction_ids or [],
    }

    try:
        patient_uuid = uuid.UUID(student_id)
    except (ValueError, TypeError):
        logger.warning(f"[PATIENT_CONTEXT] Invalid student_id: {student_id}")
        return result

    try:
        timing_start = time.time()

        # =========================================================================
        # CONTINUATION MODE: Fetch only from specific parent extraction IDs
        # Uses ONLY the most recent parent (transitive — it already contains
        # cumulative context from the entire visit chain)
        # Fetches prescription, SUMMARY, AND CAUTION from that parent
        # =========================================================================
        if is_continuation and parent_extraction_ids:
            logger.info(
                f"[PATIENT_CONTEXT] CONTINUATION MODE: fetching from {len(parent_extraction_ids)} parent extraction(s)"
            )

            parent_result = supabase.table("extractions")\
                .select("id, created_at, original_extraction_json, edited_extraction_json, session_id")\
                .in_("id", parent_extraction_ids)\
                .order("created_at", desc=True)\
                .execute()

            extractions = parent_result.data or []
            query_time = time.time() - timing_start
            logger.info(f"[PATIENT_CONTEXT_TIMING] Continuation extractions query: {query_time:.3f}s ({len(extractions)} results)")

            if not extractions:
                logger.debug(f"[PATIENT_CONTEXT] No parent extractions found for IDs: {parent_extraction_ids}")
                return result

            # Use ONLY the most recent parent (transitive chain — latest already
            # contains merged context from all prior recordings in the visit)
            most_recent = extractions[0]
            extraction_id = most_recent["id"]
            ext_data = get_extraction_data(most_recent)
            created_at = most_recent.get("created_at", "")

            logger.info(
                f"[PATIENT_CONTEXT] Using most recent parent only: {extraction_id} "
                f"(from {created_at[:10] if created_at else 'Unknown'}), "
                f"skipping {len(extractions) - 1} older parent(s) (transitive)"
            )

            # Fetch CAUTION + SUMMARY segments for most recent parent
            segments_batch = get_segments_batch([extraction_id], ["CAUTION", "SUMMARY"], supabase)
            ext_segments = segments_batch.get(extraction_id, {})

            # Prescription from most recent parent
            prescription = extract_and_normalize_prescription(ext_data, include_raw_text=True)
            if prescription:
                result["past_prescriptions"].append({
                    "extraction_id": extraction_id,
                    "date": created_at[:10] if created_at else "Unknown",
                    "prescription": prescription
                })

            # Summary from most recent parent (enables full context enrichment)
            summary_segment = ext_segments.get("SUMMARY")
            if summary_segment:
                result["past_summaries"].append({
                    "extraction_id": extraction_id,
                    "date": created_at[:10] if created_at else "Unknown",
                    "summary": summary_segment
                })

            # Caution from most recent parent (safety checks)
            caution_segment = ext_segments.get("CAUTION")
            if caution_segment:
                result["caution_aggregated"] = _aggregate_caution_data([{
                    "extraction_id": extraction_id,
                    "date": created_at[:10] if created_at else "Unknown",
                    "caution": caution_segment
                }])

            # Chief complaints from most recent parent (for auto-merge carry forward)
            parent_complaints_raw = extract_chief_complaints(ext_data)
            if parent_complaints_raw:
                result["parent_chief_complaints"] = extract_complaints_list(parent_complaints_raw)
                logger.info(
                    f"[PATIENT_CONTEXT] Extracted {len(result['parent_chief_complaints'])} chief complaints from parent {extraction_id}"
                )

            # Diagnosis from most recent parent (for auto-merge carry forward)
            parent_diagnosis_raw = find_segment_value(ext_data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge')
            if parent_diagnosis_raw:
                result["parent_diagnosis"] = extract_diagnosis_list(parent_diagnosis_raw)
                logger.info(
                    f"[PATIENT_CONTEXT] Extracted {len(result['parent_diagnosis'])} diagnoses from parent {extraction_id}"
                )

            # HPI from most recent parent (for auto-merge carry forward)
            parent_hpi = find_segment_value(ext_data, 'historyOfPresentIllness', 'hpi', 'historyOfPresentIllnessOp')
            if parent_hpi:
                result["parent_hpi"] = parent_hpi
                logger.info(f"[PATIENT_CONTEXT] Extracted HPI from parent {extraction_id}")

            # Additional segments from most recent parent (for smart field-level merge)
            parent_vitals = find_segment_value(ext_data, 'vitals')
            if parent_vitals:
                result["parent_vitals"] = parent_vitals
                logger.info(f"[PATIENT_CONTEXT] Extracted vitals from parent {extraction_id}")

            parent_examination = find_segment_value(ext_data, 'examination', 'physicalExaminationOp', 'physicalExaminationDischarge', 'physicalExamination', 'generalExamination', 'systemicExamination', 'surgicalExamination', 'mentalStatusExamination')
            if parent_examination:
                result["parent_examination"] = parent_examination
                logger.info(f"[PATIENT_CONTEXT] Extracted examination from parent {extraction_id}")

            parent_treatment_plan = find_segment_value(ext_data, 'treatmentPlan', 'treatmentPlanAdviceOp', 'treatmentPlanAdviceDischarge', 'treatmentPlanAdvice', 'treatmentSummary', 'treatmentDetails')
            if parent_treatment_plan:
                result["parent_treatment_plan"] = parent_treatment_plan
                logger.info(f"[PATIENT_CONTEXT] Extracted treatment plan from parent {extraction_id}")

            parent_follow_up = find_segment_value(ext_data, 'followUp', 'followUpOp', 'followUpDischarge')
            if parent_follow_up:
                result["parent_follow_up"] = parent_follow_up
                logger.info(f"[PATIENT_CONTEXT] Extracted follow-up from parent {extraction_id}")

            parent_investigations = find_segment_value(ext_data, 'investigations', 'investigationsOp', 'investigationsDischarge', 'orderedLabs', 'orderedRadiology', 'labResults', 'psgHospitalInvestigation', 'psgInvestigationsProcedure')
            if parent_investigations:
                result["parent_investigations"] = parent_investigations
                logger.info(f"[PATIENT_CONTEXT] Extracted investigations from parent {extraction_id}")

            parent_history = find_segment_value(ext_data, 'history', 'historyOp', 'historyDischarge', 'pastHistory', 'generalHistory', 'surgicalHistory', 'hospitalCourse', 'psgCourseInHospital')
            if parent_history:
                result["parent_history"] = parent_history
                logger.info(f"[PATIENT_CONTEXT] Extracted history from parent {extraction_id}")

            # Referral, Emergency Contact, Student Info, Report Metadata from most recent parent
            parent_referral = find_segment_value(ext_data, 'referralDetails', 'referralInformation')
            if parent_referral:
                result["parent_referral"] = parent_referral
                logger.info(f"[PATIENT_CONTEXT] Extracted referral details from parent {extraction_id}")

            parent_emergency = find_segment_value(ext_data, 'emergencyContact', 'emergency')
            if parent_emergency:
                result["parent_emergency_contact"] = parent_emergency
                logger.info(f"[PATIENT_CONTEXT] Extracted emergency contact from parent {extraction_id}")

            parent_patient_info = find_segment_value(ext_data, 'patientInformation', 'patientDetails', 'patientDemographics')
            if parent_patient_info:
                result["parent_patient_info"] = parent_patient_info
                logger.info(f"[PATIENT_CONTEXT] Extracted student information from parent {extraction_id}")

            parent_report_metadata = find_segment_value(ext_data, 'reportMetadata')
            if parent_report_metadata:
                result["parent_report_metadata"] = parent_report_metadata
                logger.info(f"[PATIENT_CONTEXT] Extracted report metadata from parent {extraction_id}")

            # Comorbidities, allergy, nutritional screening from parent (for KG cardio continuations)
            parent_comorbidities = find_segment_value(ext_data, 'comorbidities')
            if parent_comorbidities:
                result["parent_comorbidities"] = parent_comorbidities
                logger.info(f"[PATIENT_CONTEXT] Extracted comorbidities from parent {extraction_id}")

            parent_allergy = find_segment_value(ext_data, 'allergy', 'drugAllergy', 'drug_allergy')
            if parent_allergy:
                result["parent_allergy"] = parent_allergy
                logger.info(f"[PATIENT_CONTEXT] Extracted allergy from parent {extraction_id}")

            parent_nutritional = find_segment_value(ext_data, 'nutritionalScreening', 'nutritional_screening')
            if parent_nutritional:
                result["parent_nutritional_screening"] = parent_nutritional
                logger.info(f"[PATIENT_CONTEXT] Extracted nutritional screening from parent {extraction_id}")

            # Domain-agnostic full prior record (drop only noisy metadata). Drives the generic
            # deep-merge continuation block for templates without medical per-segment handling.
            if isinstance(ext_data, dict) and ext_data:
                result["parent_full_record"] = {
                    k: v for k, v in ext_data.items()
                    if k not in ("reportMetadata",) and not _is_value_empty(v)
                }

            result["has_context"] = bool(
                result["past_prescriptions"] or
                result["past_summaries"] or
                result["caution_aggregated"] or
                result["parent_chief_complaints"] or
                result["parent_diagnosis"] or
                result["parent_hpi"] or
                result["parent_vitals"] or
                result["parent_examination"] or
                result["parent_treatment_plan"] or
                result["parent_follow_up"] or
                result["parent_investigations"] or
                result["parent_history"] or
                result["parent_referral"] or
                result["parent_emergency_contact"] or
                result["parent_patient_info"] or
                result["parent_report_metadata"] or
                result.get("parent_comorbidities") or
                result.get("parent_allergy") or
                result.get("parent_nutritional_screening") or
                result.get("parent_full_record")
            )

            total_time = time.time() - timing_start
            logger.info(
                f"[PATIENT_CONTEXT_TIMING] CONTINUATION TOTAL: {total_time:.3f}s - "
                f"prescriptions={len(result['past_prescriptions'])}, "
                f"summaries={len(result['past_summaries'])}, "
                f"caution_aggregated={'Yes' if result['caution_aggregated'] else 'No'}"
            )
            return result

        # =========================================================================
        # NEW CONSULTATION MODE (default): Use only the latest 1 extraction
        # (transitive — latest already has prior context via enrichment chain)
        # =========================================================================

        # Only need the latest 1 extraction (transitive — it already has prior context)
        fetch_limit = 1

        query = supabase.table("extractions")\
            .select("id, counsellor_id, created_at, original_extraction_json, edited_extraction_json, session_id")\
            .eq("student_id", str(patient_uuid))\
            .order("created_at", desc=True)\
            .limit(fetch_limit)

        if counsellor_id:
            # Expand to include linked counsellors (via counsellor_counsellor_students)
            from services.visit_detection_service import _get_linked_counsellor_ids
            linked_ids = _get_linked_counsellor_ids(counsellor_id, student_id=student_id)
            if linked_ids:
                all_counsellor_ids = [counsellor_id] + linked_ids
                query = query.in_("counsellor_id", all_counsellor_ids)
            else:
                query = query.eq("counsellor_id", counsellor_id)

        extractions_result = query.execute()
        all_extractions = extractions_result.data or []

        query_time = time.time() - timing_start
        logger.info(f"[PATIENT_CONTEXT_TIMING] Initial extractions query: {query_time:.3f}s ({len(all_extractions)} results)")

        if not all_extractions:
            logger.debug(f"[PATIENT_CONTEXT] No past extractions found for student {student_id}")
            return result

        # Use only the latest 1 extraction (transitive — latest already has prior context)
        extractions = all_extractions[:1]

        logger.info(
            f"[PATIENT_CONTEXT] Using latest 1 extraction for student {student_id} "
            f"(from {len(all_extractions)} total)"
        )

        # Collect all CAUTION segments for aggregation
        all_cautions = []

        # ⚡ OPTIMIZATION: Batch fetch all SUMMARY and CAUTION segments in ONE query
        # Instead of 2 queries per extraction (up to 24 queries for 4 extractions with retries)
        # we now do just 1 query total
        segment_loop_start = time.time()

        extraction_ids = [ext["id"] for ext in extractions]
        segments_batch = get_segments_batch(extraction_ids, ["SUMMARY", "CAUTION"], supabase)

        batch_query_time = time.time() - segment_loop_start
        logger.info(
            f"[PATIENT_CONTEXT_TIMING] ⚡ Batch segment query: {batch_query_time:.3f}s "
            f"(1 query for {len(extractions)} extractions, fetched {sum(len(v) for v in segments_batch.values())} segments)"
        )

        # Process each extraction (most recent first) - now using cached batch results
        for ext in extractions:
            extraction_id = ext["id"]
            ext_counsellor_id = ext.get("counsellor_id")
            # Use shared utility to get edited or original extraction data
            ext_data = get_extraction_data(ext)
            created_at = ext.get("created_at", "")

            # Prescription: from ALL (current + linked counsellors)
            prescription = extract_and_normalize_prescription(ext_data, include_raw_text=True)
            if prescription:
                result["past_prescriptions"].append({
                    "extraction_id": extraction_id,
                    "date": created_at[:10] if created_at else "Unknown",
                    "prescription": prescription
                })

            ext_segments = segments_batch.get(extraction_id, {})

            # Summary: ONLY from current counsellor's extractions (not linked counsellors)
            # Prevents cross-counsellor diagnosis leaking into new consultation context
            if ext_counsellor_id == counsellor_id:
                summary_segment = ext_segments.get("SUMMARY")
                if summary_segment:
                    result["past_summaries"].append({
                        "extraction_id": extraction_id,
                        "date": created_at[:10] if created_at else "Unknown",
                        "summary": summary_segment
                    })

            # Caution: from ALL (current + linked counsellors) — safety first
            caution_segment = ext_segments.get("CAUTION")
            if caution_segment:
                all_cautions.append({
                    "extraction_id": extraction_id,
                    "date": created_at[:10] if created_at else "Unknown",
                    "caution": caution_segment
                })

        # Aggregate CAUTION data from all collected extractions
        if all_cautions:
            result["caution_aggregated"] = _aggregate_caution_data(all_cautions)
            logger.info(
                f"[PATIENT_CONTEXT] Aggregated CAUTION from {len(all_cautions)} extractions for student {student_id}"
            )

        # Check if we found any context
        result["has_context"] = bool(
            result["past_prescriptions"] or
            result["past_summaries"] or
            result["caution_aggregated"]
        )

        total_time = time.time() - timing_start
        logger.info(
            f"[PATIENT_CONTEXT_TIMING] ✅ TOTAL TIME: {total_time:.3f}s - "
            f"prescriptions={len(result['past_prescriptions'])}, "
            f"summaries={len(result['past_summaries'])}, "
            f"caution_aggregated={'Yes' if result['caution_aggregated'] else 'No'}"
        )

        return result

    except Exception as e:
        logger.error(f"[PATIENT_CONTEXT] Error fetching student context: {e}", exc_info=True)
        return result


def _aggregate_caution_data(caution_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate CAUTION data from multiple extractions to find common/consistent allergies.

    The aggregation logic:
    1. Collect all unique allergies mentioned across extractions
    2. Track frequency of each allergy (how many times mentioned)
    3. Prioritize allergies mentioned in multiple consultations (more reliable)
    4. Include all unique contraindications and conditions

    Args:
        caution_list: List of caution dicts with 'extraction_id', 'date', 'caution' keys

    Returns:
        Dict with:
            - allergies: List of unique allergies with frequency
            - contraindications: List of unique contraindications
            - conditions: List of unique medical conditions
            - special_notes: List of special considerations
            - source_count: Number of extractions aggregated
            - sources: List of source extraction dates
    """
    # Track allergies with their frequency
    allergy_counts: Dict[str, int] = {}
    contraindications: set = set()
    conditions: set = set()
    special_notes: set = set()
    sources: List[str] = []

    for item in caution_list:
        caution_data = item.get("caution")
        date = item.get("date", "Unknown")
        sources.append(date)

        if not caution_data:
            continue

        # Handle string type CAUTION (current schema)
        if isinstance(caution_data, str):
            # Parse the string to extract allergies
            # Common patterns: "Allergic to X", "Allergy: X", just "X" if standalone
            caution_lower = caution_data.lower()
            if "allerg" in caution_lower or "sensitive" in caution_lower:
                # This is likely an allergy mention
                _add_to_count(allergy_counts, caution_data.strip())
            elif "contraindic" in caution_lower:
                contraindications.add(caution_data.strip())
            elif "condition" in caution_lower or "disease" in caution_lower:
                conditions.add(caution_data.strip())
            else:
                # Could be allergy or general caution - add to allergies
                _add_to_count(allergy_counts, caution_data.strip())

        # Handle dict type CAUTION (legacy format)
        elif isinstance(caution_data, dict):
            # Extract allergies
            allergies = caution_data.get("allergies") or caution_data.get("drug_allergies") or []
            if isinstance(allergies, str):
                allergies = [allergies]
            for allergy in allergies:
                if allergy:
                    _add_to_count(allergy_counts, str(allergy).strip())

            # Extract contraindications
            contras = caution_data.get("contraindications") or caution_data.get("drug_contraindications") or []
            if isinstance(contras, str):
                contras = [contras]
            for contra in contras:
                if contra:
                    contraindications.add(str(contra).strip())

            # Extract conditions
            conds = caution_data.get("medical_conditions") or caution_data.get("conditions_affecting_treatment") or []
            if isinstance(conds, str):
                conds = [conds]
            for cond in conds:
                if cond:
                    conditions.add(str(cond).strip())

            # Extract special notes
            special = caution_data.get("special_considerations") or caution_data.get("notes") or caution_data.get("other")
            if special:
                special_notes.add(str(special).strip())

    # Build aggregated result with frequency info
    aggregated_allergies = []
    for allergy, count in sorted(allergy_counts.items(), key=lambda x: (-x[1], x[0])):
        aggregated_allergies.append({
            "allergy": allergy,
            "mentioned_in": count,
            "confidence": "HIGH" if count >= 2 else "MEDIUM" if count == 1 else "LOW"
        })

    return {
        "allergies": aggregated_allergies,
        "contraindications": list(contraindications),
        "conditions": list(conditions),
        "special_notes": list(special_notes),
        "source_count": len(caution_list),
        "sources": sources
    }


def _add_to_count(counts: Dict[str, int], item: str) -> None:
    """Helper to add/increment item in counts dict, normalizing case."""
    if not item:
        return
    # Normalize to title case for consistent matching
    normalized = item.strip()
    # Check if similar item exists (case-insensitive)
    for existing in counts:
        if existing.lower() == normalized.lower():
            counts[existing] += 1
            return
    counts[normalized] = 1


def format_student_context_for_prompt(context: Dict[str, Any], is_continuation: bool = False) -> str:
    """
    Format student context data into a string for prompt injection.

    Two modes:
    - Continuation mode: Full enrichment — prior context enriches extraction,
      current transcript always wins on conflicts.
    - New consultation mode: Standard guardrails with strengthened instructions.

    Args:
        context: Student context dict from get_student_context_for_extraction()
        is_continuation: Whether this is a continuation of a prior visit (default: False)

    Returns:
        Formatted string to inject into user prompt
    """
    if not context.get("has_context"):
        return ""

    # Auto-detect from context if not passed explicitly
    if not is_continuation:
        is_continuation = context.get("context_mode") == "continuation"

    sections = []

    if is_continuation:
        # CONTINUATION MODE header — the model is the PRIMARY (deep) merge engine.
        # These principles are DOMAIN-NEUTRAL on purpose: the same deep-merge philosophy
        # applies to a counselling follow-up session and to any other follow-up record.
        # Domain-specific guidance (e.g. medicine names, safety warnings) is provided by the
        # dedicated sections below, only when that data is present.
        sections.append("""
==============================================================================
PRIOR SESSION RECORD (CONTINUATION MODE — YOU ARE THE PRIMARY MERGE ENGINE)
==============================================================================
The data below is from the MOST RECENT prior record in this SAME ongoing case/visit.
It already contains cumulative context from earlier records in the chain.

YOU ARE THE PRIMARY MERGE ENGINE. A lightweight validation check runs after you, but YOUR
output is the foundation. Produce the most accurate, COMPLETE merged record as if the prior
record and the current transcript were a single session. Do NOT drop data just because the
speaker did not repeat it in the current recording.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEEP-MERGE PRINCIPLES (CRITICAL — this is a DEEP merge, never a shallow overwrite
and never a blind append):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. CARRY FORWARD BY DEFAULT:
   - Every item/field present in the prior record MUST appear in your output unless the
     current transcript explicitly changes or removes it.
   - "Not mentioned again" NEVER means "delete it" — carry it forward unchanged.

2. DEEP-MERGE NESTED STRUCTURES (do not overwrite a whole object/section):
   - When both prior and current have the same nested object (a section with sub-fields),
     merge them field-by-field: keep every prior sub-field, update only the ones the current
     transcript changes, and add new sub-fields. Never replace an entire section just because
     one field changed.

3. UNION LISTS (never blind-append, never drop):
   - For list/array fields (and nested lists), produce the UNION of prior and current items.
   - Keep all prior items, add new ones, and NEVER produce duplicates of the same item.
   - Only drop a list item if the transcript explicitly removes/completes/cancels it.

4. ITEM LIFECYCLE (explicit removal only):
   - If the speaker explicitly STOPS / COMPLETES / CANCELS / DROPS an item → remove that
     specific item from the output.
   - PARTIAL CHANGES: only the explicitly named items change; all others carry forward.
   - If an item's details change (e.g. a date, status, or value is updated) → output the item
     ONCE with the UPDATED details (never both the old and new versions).

5. LATEST-WINS FOR CURRENT STATE (scalars / single-value fields):
   - If the current transcript provides a value → it REPLACES the prior value.
   - If the current transcript is silent → carry the prior value forward unchanged.
   - Produce clean unified values — NO "|" separators, NO concatenation of old and new.

6. APPEND / SYNTHESISE HISTORY & NARRATIVE FIELDS:
   - For history and free-text/narrative fields, combine prior + current into ONE coherent
     narrative showing progression ("Initially X, now also Y"). Never concatenate with "|".

7. CONFLICT RESOLUTION:
   - The CURRENT transcript is ALWAYS the source of truth when prior and current conflict.
   - Prior context provides CONTINUITY only for what the current transcript does not mention.

8. REFINEMENT, NOT DUPLICATION:
   - When an item is refined/clarified (same thing, better wording), output ONLY the refined
     version — do not keep both the vague and the refined forms.

9. CROSS-FIELD CONSISTENCY:
   - Before finalising, ensure the merged record is internally consistent: a change in one
     section (e.g. a changed goal, direction, or status) should be reflected wherever else it
     is referenced; do not leave stale values that contradict an explicit update.
==============================================================================""")

        # Generic prior-record dump for templates without dedicated per-segment handling
        # (e.g. counselling). Skipped when the medical per-segment sections below will render,
        # to avoid duplicating the same data on the medical path.
        _has_medical_sections = bool(
            context.get("caution_aggregated") or context.get("past_prescriptions") or
            context.get("parent_chief_complaints") or context.get("parent_diagnosis") or
            context.get("parent_hpi") or context.get("parent_investigations") or
            context.get("parent_treatment_plan") or context.get("parent_examination") or
            context.get("parent_vitals") or context.get("parent_history")
        )
        parent_full = context.get("parent_full_record")
        if parent_full and not _has_medical_sections:
            try:
                _record_text = json.dumps(parent_full, indent=2, ensure_ascii=False, default=str)
            except Exception:
                _record_text = str(parent_full)
            sections.append(f"""
**PRIOR SESSION RECORD (merge this forward using the DEEP-MERGE PRINCIPLES above):**
{_record_text}

INSTRUCTIONS:
- Treat every field above as the baseline. Carry it ALL forward, then apply the current
  transcript on top: update changed values, add new items, UNION lists (keep prior + new),
  and remove ONLY what the transcript explicitly stops / completes / cancels.
- Deep-merge nested sections field-by-field — do not overwrite a whole section because one
  field changed.
- Your merged output MUST be at least as complete as this prior record, except for items the
  transcript explicitly removes.
""")
    else:
        # NEW CONSULTATION MODE header (original)
        sections.append("""
==============================================================================
PAST STUDENT RECORDS (FOR REFERENCE TO GENERATE CAUTION & WARNINGS)
==============================================================================
The following are the student's PAST prescriptions and consultation summaries.
Use this historical context ONLY to:
1. Generate appropriate CAUTION and WARNINGS for the 'warnings' segment
2. Resolve "continue previous medicines" to actual medicine names
3. Provide relevant history context ONLY when the counsellor explicitly references it
   in the current transcript

⚠️ CRITICAL — DO NOT FABRICATE FROM PRIOR CONTEXT:
- Do NOT generate followUp, treatmentPlan, emergencyContact, history, or any other
  segment content from prior records. These segments must ONLY reflect what was
  actually discussed in the CURRENT transcript.
- If the current transcript does not discuss follow-up plans, leave followUp empty/N/A.
- If the current transcript does not discuss treatment plans, leave treatmentPlan empty/N/A.
- The ONLY exception is the 'warnings' segment, which MUST use prior context for
  allergy/contraindication safety checks.
==============================================================================""")

    # Format AGGREGATED CAUTION section (most important - safety first)
    if context.get("caution_aggregated"):
        caution_aggregated = context["caution_aggregated"]
        caution_text = _format_aggregated_caution_for_prompt(caution_aggregated)
        if caution_text:
            source_info = f"(Aggregated from {caution_aggregated.get('source_count', 0)} past consultations)"
            sections.append(f"""
**STUDENT SAFETY ALERTS - AGGREGATED FROM PAST CONSULTATIONS (CRITICAL):**
{source_info}

{caution_text}

⚠️ MANDATORY SAFETY CHECK - OUTPUT TO 'warnings' SEGMENT:
You MUST perform the following checks and record results in the 'warnings' segment:

1. **ALLERGY CHECK**: For EACH medicine in the prescription:
   - Compare against ALL allergies listed above
   - If potential match or similar drug class: FLAG as "ALLERGY_ALERT"
   - If no match found: Record as "CLEARED"

2. **CONTRAINDICATION CHECK**: For EACH medicine:
   - Check against contraindications and medical conditions above
   - If contraindicated: FLAG as "CONTRAINDICATION_ALERT"
   - If caution needed: FLAG as "CAUTION_REQUIRED"

3. **WARNINGS SEGMENT OUTPUT FORMAT**:
   The 'warnings' segment must contain exactly 3 string fields:
   {{
     "allergy_checks": "Medicine1:CLEARED; Medicine2:ALLERGY_ALERT(matched: Penicillin, note: cross-reactivity)",
     "contraindication_checks": "Medicine1:CLEARED; Medicine2:CAUTION_REQUIRED(reason: renal impairment)",
     "safety_summary": "Status:ALERTS_PRESENT | Critical:[Penicillin allergy detected, Renal dose adjustment needed]"
   }}

   FORMAT RULES:
   - allergy_checks: Semicolon-separated list of "MedicineName:STATUS" or "MedicineName:STATUS(matched: X, note: Y)"
   - contraindication_checks: Semicolon-separated list of "MedicineName:STATUS" or "MedicineName:STATUS(reason: X)"
   - safety_summary: "Status:SAFE|ALERTS_PRESENT|REVIEW_REQUIRED|NO_HISTORY_AVAILABLE | Critical:[comma-separated alerts or 'None']"

4. If NO allergies/contraindications are known, set safety_summary to "Status:NO_HISTORY_AVAILABLE | Critical:[None]"
""")

    # Format past prescriptions section
    if context.get("past_prescriptions"):
        prescriptions_text = _format_prescriptions_for_prompt(context["past_prescriptions"])
        if prescriptions_text:
            sections.append(f"""
**STUDENT'S PREVIOUS PRESCRIPTIONS:**
{prescriptions_text}

📋 MANDATORY PRESCRIPTION EXTRACTION RULES:

⚠️ CRITICAL - NEVER OUTPUT VAGUE PHRASES unless the STUDENT's Past prescription doesn't have actual medicine names:
You MUST NOT output phrases like:
- "Continue previous medication"
- "Same medicines as before"
- "Continue previous prescription"
- "Repeat prescription"

You MUST ALWAYS use actual medicine names if present in past prescriptions.

✅ REQUIRED ACTIONS:
1. **When counsellor says "continue previous medicines", "same medicines", "continue the same", etc.**:
   - You MUST copy the ACTUAL medicine names, dosages, and instructions from the prescriptions listed above
   - List each medicine individually with its complete details
   - Example: If past prescription has "Paracetamol 500mg", output the full medicine entry, NOT "continue previous"

2. **When counsellor mentions a specific medicine from past prescription**:
   - Use the EXACT name and dosage from the past prescriptions above
   - Match case and spelling exactly

3. **When counsellor modifies a previous medicine** (e.g., "increase Paracetamol dosage"):
   - Copy the medicine name from above and apply the modification mentioned

4. **For completely NEW medicines** not in past prescriptions:
   - Extract as usual from transcript

5. **If past prescriptions are NOT relevant** to current consultation:
   - Do NOT copy any medicines from above

6. **If past prescriptions are vague or incomplete**:
   - Do NOT guess or fabricate details - in this case, say "continue past prescriptions"

7. **FUZZY MEDICINE NAME MATCHING** (for stop/change/continue):
   - Match by brand name, generic name, OR common abbreviation.
   - "stop dolo" matches "Dolo 650mg" or "Tab. Dolo 650"
   - "increase metformin" matches "Metformin 500mg" or "Tab. Metformin HCl 500mg"
   - "paracetamol" matches "Dolo 650mg" (generic ↔ brand match)
   - When in doubt, match the most likely medicine from the prior prescription list.

🔴 VALIDATION CHECK:
Before finalizing the prescription segment, verify:
- NO medicine entry contains words like "continue", "previous", "same", "repeat", "as before" unless past prescriptions are also vague
- EVERY medicine has an actual drug name (e.g., "Paracetamol", "Amoxicillin", not "previous medicine")
""")

    # Format past summaries section
    if context.get("past_summaries"):
        summaries_text = _format_summaries_for_prompt(context["past_summaries"])
        if summaries_text:
            if is_continuation:
                # Continuation mode: summaries are for auto-merge enrichment
                sections.append(f"""
**PRIOR VISIT SUMMARY (CONTINUATION — NARRATIVE SYNTHESIS):**
{summaries_text}

INSTRUCTIONS FOR USING PRIOR SUMMARY IN CONTINUATION:
1. Carry forward this summary as baseline and UPDATE with new information from the current transcript.
2. If the CURRENT transcript contradicts this summary, the CURRENT transcript wins.
3. The merged result should be a complete summary covering both recordings.
4. Produce a coherent synthesized narrative — NO "|" separators. Show progression naturally.
""")
            else:
                # New consultation mode: summaries are for reference only
                sections.append(f"""
**STUDENT'S PAST CONSULTATION SUMMARIES:**
{summaries_text}

INSTRUCTIONS FOR USING PAST SUMMARIES:
1. Past summaries are for REFERENCE ONLY — primarily for generating warnings/caution
2. ONLY include past summary info in History IF the current transcript explicitly
   discusses or references those past conditions
3. Do NOT auto-populate ANY segments from past summaries — this includes chief complaints,
   diagnosis, examination, treatmentPlan, followUp, emergencyContact, history, and all others
4. If past conditions are not mentioned in the current transcript, do not include them
5. The ONLY segment that should use prior context is 'warnings' (for safety checks)
""")

    # Format prior chief complaints section (continuation auto-merge only)
    if is_continuation and context.get("parent_chief_complaints"):
        complaints_list = context["parent_chief_complaints"]
        complaints_formatted = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(complaints_list))
        sections.append(f"""
**PRIOR CHIEF COMPLAINTS (MUST CARRY FORWARD):**
{complaints_formatted}

INSTRUCTIONS:
- You MUST include ALL the above chief complaints in your output.
- Add any NEW complaints mentioned in the current transcript.
- Only REMOVE a complaint if the counsellor explicitly says it is resolved in the current recording.
- Do NOT drop complaints just because they are not mentioned in the current transcript.
""")

    # Format prior diagnosis section (continuation auto-merge only)
    if is_continuation and context.get("parent_diagnosis"):
        diagnosis_list = context["parent_diagnosis"]
        diag_lines = []
        for i, dx in enumerate(diagnosis_list):
            name = dx.get('name', str(dx)) if isinstance(dx, dict) else str(dx)
            code = dx.get('code') if isinstance(dx, dict) else None
            code_str = f" (ICD: {code})" if code else ""
            diag_lines.append(f"  {i+1}. {name}{code_str}")
        diagnosis_formatted = "\n".join(diag_lines)
        sections.append(f"""
**PRIOR DIAGNOSIS (MUST CARRY FORWARD):**
{diagnosis_formatted}

INSTRUCTIONS:
- You MUST include ALL the above diagnoses in your output, preserving ICD codes.
- Add any NEW diagnoses from the current transcript.
- Only REMOVE a diagnosis if the counsellor explicitly contradicts or resolves it in the current recording.
- Do NOT drop diagnoses just because they are not mentioned in the current transcript.
""")

    # Format prior HPI section (continuation auto-merge only)
    if is_continuation and context.get("parent_hpi"):
        hpi_data = context["parent_hpi"]
        if isinstance(hpi_data, dict):
            hpi_text = json.dumps(hpi_data, indent=2, ensure_ascii=False)
        elif isinstance(hpi_data, list):
            hpi_text = json.dumps(hpi_data, indent=2, ensure_ascii=False)
        else:
            hpi_text = str(hpi_data)
        # Truncate if very long
        if len(hpi_text) > 2000:
            hpi_text = hpi_text[:2000] + "..."
        sections.append(f"""
**PRIOR HPI (CARRY FORWARD — NARRATIVE SYNTHESIS):**
{hpi_text}

INSTRUCTIONS:
- Use this as the BASELINE for historyOfPresentIllness in your output.
- APPEND or UPDATE with any new information from the current transcript.
- Do NOT replace the entire HPI — extend it with new details.
- If the current transcript contradicts specific HPI details, use the current version for those details.
- Produce a coherent merged narrative showing progression — NO "|" separators.
""")

    # Format prior vitals section (continuation auto-merge only)
    if is_continuation and context.get("parent_vitals"):
        vitals_data = context["parent_vitals"]
        if isinstance(vitals_data, (dict, list)):
            vitals_text = json.dumps(vitals_data, indent=2, ensure_ascii=False)
        else:
            vitals_text = str(vitals_data)
        if len(vitals_text) > 2000:
            vitals_text = vitals_text[:2000] + "..."
        sections.append(f"""
**PRIOR VITALS (CARRY FORWARD — LATEST-WINS):**
{vitals_text}

INSTRUCTIONS:
- If current transcript has data for a vital sign, use the CURRENT value (replaces prior).
- Otherwise carry forward the prior value unchanged.
- Do NOT drop vitals just because the current transcript doesn't mention them.
- Produce clean, unified values — NO "|" separators between old and new values.
""")

    # Format prior examination section (continuation auto-merge only)
    if is_continuation and context.get("parent_examination"):
        exam_data = context["parent_examination"]
        if isinstance(exam_data, (dict, list)):
            exam_text = json.dumps(exam_data, indent=2, ensure_ascii=False)
        else:
            exam_text = str(exam_data)
        if len(exam_text) > 2000:
            exam_text = exam_text[:2000] + "..."
        sections.append(f"""
**PRIOR EXAMINATION (CARRY FORWARD — LATEST-WINS):**
{exam_text}

INSTRUCTIONS:
- If current transcript has examination findings for a field, use the CURRENT findings (replaces prior).
- Otherwise carry forward the prior examination data for that field.
- Do NOT drop examination findings just because they are not re-examined in the current transcript.
- Produce clean, unified values — NO "|" separators between old and new findings.
""")

    # Format prior treatment plan section (continuation auto-merge only)
    if is_continuation and context.get("parent_treatment_plan"):
        tp_data = context["parent_treatment_plan"]
        if isinstance(tp_data, (dict, list)):
            tp_text = json.dumps(tp_data, indent=2, ensure_ascii=False)
        else:
            tp_text = str(tp_data)
        if len(tp_text) > 2000:
            tp_text = tp_text[:2000] + "..."
        sections.append(f"""
**PRIOR TREATMENT PLAN (CARRY FORWARD — NARRATIVE SYNTHESIS):**
{tp_text}

INSTRUCTIONS:
- Carry forward the prior treatment plan as baseline.
- Add any NEW treatment instructions from the current transcript.
- If current transcript changes specific treatment items, use the CURRENT version for those.
- Do NOT drop treatment plan items just because they are not re-mentioned.
- Produce a coherent merged narrative — NO "|" separators. Synthesize into natural text.
""")

    # Format prior follow-up section (continuation auto-merge only)
    if is_continuation and context.get("parent_follow_up"):
        fu_data = context["parent_follow_up"]
        if isinstance(fu_data, (dict, list)):
            fu_text = json.dumps(fu_data, indent=2, ensure_ascii=False)
        else:
            fu_text = str(fu_data)
        if len(fu_text) > 2000:
            fu_text = fu_text[:2000] + "..."
        sections.append(f"""
**PRIOR FOLLOW UP (CARRY FORWARD — LATEST-WINS):**
{fu_text}

INSTRUCTIONS:
- Carry forward the prior follow-up instructions as baseline.
- Add any NEW follow-up instructions from the current transcript.
- If current transcript changes the follow-up plan, use the CURRENT version.
- Produce clean, unified text — NO "|" separators.
""")

    # Format prior investigations section (continuation auto-merge only)
    if is_continuation and context.get("parent_investigations"):
        inv_data = context["parent_investigations"]
        if isinstance(inv_data, (dict, list)):
            inv_text = json.dumps(inv_data, indent=2, ensure_ascii=False)
        else:
            inv_text = str(inv_data)
        if len(inv_text) > 2000:
            inv_text = inv_text[:2000] + "..."
        sections.append(f"""
**PRIOR INVESTIGATIONS (CARRY FORWARD — CONFIRMED ORDERS ONLY):**
{inv_text}

INSTRUCTIONS:
- Only carry forward investigations that were CONFIRMED/ORDERED by the counsellor.
- Do NOT carry forward CONDITIONAL investigations (e.g., "if fever persists, do blood culture",
  "consider MRI if pain continues"). Conditional investigations belong in the follow-up or
  treatment plan contingency section, not here.
- Add any NEW confirmed investigations ordered in the current transcript.
- If counsellor CANCELS an investigation (e.g., "cancel the MRI", "no need for X-ray") → REMOVE it.
- Deduplicate by test name — if same investigation appears in both, use the current version.
- Do not include Investigation RESULTS discussed by the counsellor (e.g., "blood sugar came back 180")
  here. They belong in the EXAMINATION segment (clinical_assessment).
""")

    # Format prior history section (continuation auto-merge only)
    if is_continuation and context.get("parent_history"):
        hist_data = context["parent_history"]
        if isinstance(hist_data, (dict, list)):
            hist_text = json.dumps(hist_data, indent=2, ensure_ascii=False)
        else:
            hist_text = str(hist_data)
        if len(hist_text) > 2000:
            hist_text = hist_text[:2000] + "..."
        sections.append(f"""
**PRIOR HISTORY (CARRY FORWARD — NARRATIVE SYNTHESIS):**
{hist_text}

INSTRUCTIONS:
- Combine prior and current history information chronologically.
- Show disease progression: what was known before + what's new now.
- If current transcript updates or corrects specific history details, use the CURRENT version.
- Produce a coherent narrative — NOT "prior text | current text".
- Do NOT drop history just because it is not re-mentioned in the current transcript.
""")

    # Format prior referral details section (continuation auto-merge only)
    if is_continuation and context.get("parent_referral"):
        ref_data = context["parent_referral"]
        if isinstance(ref_data, (dict, list)):
            ref_text = json.dumps(ref_data, indent=2, ensure_ascii=False)
        else:
            ref_text = str(ref_data)
        if len(ref_text) > 2000:
            ref_text = ref_text[:2000] + "..."
        sections.append(f"""
**PRIOR REFERRAL DETAILS (CARRY FORWARD — LATEST-WINS):**
{ref_text}

INSTRUCTIONS:
- If current transcript has referral info → use current (replaces prior).
- Otherwise carry forward prior referral unchanged.
""")

    # Format prior emergency contact section (continuation auto-merge only)
    if is_continuation and context.get("parent_emergency_contact"):
        ec_data = context["parent_emergency_contact"]
        if isinstance(ec_data, (dict, list)):
            ec_text = json.dumps(ec_data, indent=2, ensure_ascii=False)
        else:
            ec_text = str(ec_data)
        if len(ec_text) > 2000:
            ec_text = ec_text[:2000] + "..."
        sections.append(f"""
**PRIOR EMERGENCY CONTACT (CARRY FORWARD — LATEST-WINS):**
{ec_text}

INSTRUCTIONS:
- If current transcript has emergency contact info → use current.
- Otherwise carry forward prior emergency contact unchanged.
""")

    # Format prior student information section (continuation auto-merge only)
    if is_continuation and context.get("parent_patient_info"):
        pi_data = context["parent_patient_info"]
        if isinstance(pi_data, (dict, list)):
            pi_text = json.dumps(pi_data, indent=2, ensure_ascii=False)
        else:
            pi_text = str(pi_data)
        if len(pi_text) > 2000:
            pi_text = pi_text[:2000] + "..."
        sections.append(f"""
**PRIOR STUDENT INFORMATION (CARRY FORWARD — LATEST-WINS):**
{pi_text}

INSTRUCTIONS:
- If current transcript has student info (age, gender, ward, bed) → use current.
- Otherwise carry forward prior values.
""")

    # Format prior report metadata section (continuation auto-merge only)
    if is_continuation and context.get("parent_report_metadata"):
        rm_data = context["parent_report_metadata"]
        if isinstance(rm_data, (dict, list)):
            rm_text = json.dumps(rm_data, indent=2, ensure_ascii=False)
        else:
            rm_text = str(rm_data)
        if len(rm_text) > 2000:
            rm_text = rm_text[:2000] + "..."
        sections.append(f"""
**PRIOR REPORT METADATA (CARRY FORWARD — LATEST-WINS):**
{rm_text}

INSTRUCTIONS:
- If current transcript has metadata (counsellor name, location, specialty) → use current.
- Otherwise carry forward prior values.
""")

    # Format prior comorbidities section (continuation auto-merge only)
    if is_continuation and context.get("parent_comorbidities"):
        como_data = context["parent_comorbidities"]
        if isinstance(como_data, (dict, list)):
            como_text = json.dumps(como_data, indent=2, ensure_ascii=False)
        else:
            como_text = str(como_data)
        if len(como_text) > 2000:
            como_text = como_text[:2000] + "..."
        sections.append(f"""
**PRIOR COMORBIDITIES (CARRY FORWARD — UPDATE ON NEW INFO):**
{como_text}

INSTRUCTIONS:
- Carry forward ALL prior comorbidity statuses unchanged.
- If current transcript reveals a NEW condition (e.g., "student now reports diabetes"), update that specific entry to "Yes" with duration.
- If current transcript explicitly DENIES a condition that was previously "Yes", update to "No".
- If current transcript does not mention a comorbidity, keep the prior value as-is.
- Do NOT reset unmentioned comorbidities to empty — preserve the prior assessment.
""")

    # Format prior allergy section (continuation auto-merge only)
    if is_continuation and context.get("parent_allergy"):
        allergy_data = context["parent_allergy"]
        if isinstance(allergy_data, (dict, list)):
            allergy_text = json.dumps(allergy_data, indent=2, ensure_ascii=False)
        else:
            allergy_text = str(allergy_data)
        if len(allergy_text) > 2000:
            allergy_text = allergy_text[:2000] + "..."
        sections.append(f"""
**PRIOR ALLERGY (CARRY FORWARD — SAFETY CRITICAL):**
{allergy_text}

INSTRUCTIONS:
- ALWAYS carry forward prior allergy data — allergies are NEVER dropped.
- If current transcript reveals a NEW allergy, ADD it to details.
- If prior has_allergy was "Yes", keep it "Yes" even if current transcript does not re-mention it.
- Only change has_allergy from "Yes" to "No Known Allergy" if counsellor explicitly corrects it.
""")

    # Format prior nutritional screening section (continuation auto-merge only)
    if is_continuation and context.get("parent_nutritional_screening"):
        nutr_data = context["parent_nutritional_screening"]
        if isinstance(nutr_data, (dict, list)):
            nutr_text = json.dumps(nutr_data, indent=2, ensure_ascii=False)
        else:
            nutr_text = str(nutr_data)
        if len(nutr_text) > 2000:
            nutr_text = nutr_text[:2000] + "..."
        sections.append(f"""
**PRIOR NUTRITIONAL SCREENING (CARRY FORWARD — LATEST-WINS):**
{nutr_text}

INSTRUCTIONS:
- If current transcript provides height/weight/BMI, use the CURRENT values (replaces prior).
- Otherwise carry forward prior values unchanged.
- Do NOT drop measurements just because they are not re-mentioned.
""")

    if sections:
        return "\n" + "\n".join(sections)

    return ""


def _format_aggregated_caution_for_prompt(caution_aggregated: Dict[str, Any]) -> str:
    """
    Format aggregated CAUTION data for prompt injection.

    Shows allergies with confidence levels based on how many times they were mentioned
    across past consultations.

    Args:
        caution_aggregated: Aggregated caution dict from _aggregate_caution_data()

    Returns:
        Formatted string for prompt
    """
    if not caution_aggregated:
        return ""

    lines = []

    # Format allergies with confidence levels
    allergies = caution_aggregated.get("allergies", [])
    if allergies:
        lines.append("🚨 KNOWN ALLERGIES:")
        for allergy_info in allergies:
            allergy = allergy_info.get("allergy", "")
            confidence = allergy_info.get("confidence", "MEDIUM")
            mentioned = allergy_info.get("mentioned_in", 1)

            # Add visual indicator based on confidence
            if confidence == "HIGH":
                indicator = "⚠️ [CONFIRMED - mentioned in multiple consultations]"
            elif confidence == "MEDIUM":
                indicator = "[Single mention]"
            else:
                indicator = "[Low confidence]"

            lines.append(f"   • {allergy} {indicator} (x{mentioned})")
        lines.append("")

    # Format contraindications
    contraindications = caution_aggregated.get("contraindications", [])
    if contraindications:
        lines.append("⛔ CONTRAINDICATIONS:")
        for contra in contraindications:
            lines.append(f"   • {contra}")
        lines.append("")

    # Format medical conditions
    conditions = caution_aggregated.get("conditions", [])
    if conditions:
        lines.append("🏥 MEDICAL CONDITIONS AFFECTING TREATMENT:")
        for condition in conditions:
            lines.append(f"   • {condition}")
        lines.append("")

    # Format special notes
    special_notes = caution_aggregated.get("special_notes", [])
    if special_notes:
        lines.append("📝 SPECIAL CONSIDERATIONS:")
        for note in special_notes:
            lines.append(f"   • {note}")
        lines.append("")

    return "\n".join(lines) if lines else ""


def _format_caution_for_prompt(caution_data: Any) -> str:
    """Format CAUTION segment data for prompt.

    Primary schema is string type. Dict is legacy fallback.
    """
    if not caution_data:
        return ""

    lines = []

    # Primary: string type (current schema)
    if isinstance(caution_data, str):
        lines.append(f"• {caution_data}")

    # Fallback: dict type (legacy format)
    elif isinstance(caution_data, dict):
        # Allergies
        allergies = caution_data.get("allergies") or caution_data.get("drug_allergies") or []
        if allergies:
            if isinstance(allergies, list):
                lines.append(f"• ALLERGIES: {', '.join(str(a) for a in allergies)}")
            else:
                lines.append(f"• ALLERGIES: {allergies}")

        # Contraindications
        contraindications = caution_data.get("contraindications") or caution_data.get("drug_contraindications") or []
        if contraindications:
            if isinstance(contraindications, list):
                lines.append(f"• CONTRAINDICATIONS: {', '.join(str(c) for c in contraindications)}")
            else:
                lines.append(f"• CONTRAINDICATIONS: {contraindications}")

        # Medical conditions that affect treatment
        conditions = caution_data.get("medical_conditions") or caution_data.get("conditions_affecting_treatment") or []
        if conditions:
            if isinstance(conditions, list):
                lines.append(f"• CONDITIONS: {', '.join(str(c) for c in conditions)}")
            else:
                lines.append(f"• CONDITIONS: {conditions}")

        # Special considerations
        special = caution_data.get("special_considerations") or caution_data.get("notes") or caution_data.get("other")
        if special:
            lines.append(f"• SPECIAL NOTES: {special}")

    return "\n".join(lines) if lines else ""


def _format_prescriptions_for_prompt(prescriptions: List[Dict[str, Any]]) -> str:
    """Format past prescriptions for prompt.

    Handles the PRESCRIPTION segment schema:
    - Array of objects with: name, morning_qty, noon_qty, evening_qty, night_qty,
      timeToTake, durationDays, remarks
    """
    if not prescriptions:
        return ""

    lines = []

    for presc in prescriptions[:3]:  # Limit to 3 most recent
        date = presc.get("date", "Unknown date")
        medicines = presc.get("prescription", [])

        if not medicines:
            continue

        lines.append(f"--- Prescription from {date} ---")

        for med in medicines[:10]:  # Limit to 10 medicines per prescription
            if isinstance(med, dict):
                # Primary field: name
                name = med.get("name") or med.get("medicine_name") or med.get("drug_name") or "Unknown"

                # Build dosage string from qty fields (morning_qty, noon_qty, evening_qty, night_qty)
                qty_parts = []
                morning = med.get("morning_qty") or med.get("morning")
                noon = med.get("noon_qty") or med.get("noon") or med.get("afternoon_qty")
                evening = med.get("evening_qty") or med.get("evening")
                night = med.get("night_qty") or med.get("night")

                if morning or noon or evening or night:
                    # Format as "M-N-E-N" style (e.g., "1-0-1-0")
                    qty_parts = [
                        morning or "0",
                        noon or "0",
                        evening or "0",
                        night or "0"
                    ]
                    dosage = "-".join(qty_parts)
                else:
                    # Fallback to legacy fields
                    dosage = med.get("dosage") or med.get("dose") or ""

                # Timing (when to take)
                time_to_take = med.get("timeToTake") or med.get("timing") or med.get("frequency") or ""

                # Duration
                duration = med.get("durationDays") or med.get("duration") or ""

                # Remarks
                remarks = med.get("remarks") or ""

                # Build the medicine line
                med_line = f"  • {name}"
                if dosage:
                    med_line += f" - {dosage}"
                if time_to_take:
                    med_line += f" ({time_to_take})"
                if duration:
                    med_line += f" for {duration} days" if duration.isdigit() else f" for {duration}"
                if remarks:
                    med_line += f" [{remarks}]"
                lines.append(med_line)
            elif isinstance(med, str):
                lines.append(f"  • {med}")

        lines.append("")  # Empty line between prescriptions

    return "\n".join(lines) if lines else ""


def _format_summaries_for_prompt(summaries: List[Dict[str, Any]]) -> str:
    """Format past summaries for prompt.

    Primary schema is string type. Dict is legacy fallback.
    """
    if not summaries:
        return ""

    lines = []

    for summ in summaries[:2]:  # Limit to 2 most recent summaries
        date = summ.get("date", "Unknown date")
        summary_data = summ.get("summary", {})

        if not summary_data:
            continue

        lines.append(f"--- Summary from {date} ---")

        # Primary: string type (current schema)
        if isinstance(summary_data, str):
            # Truncate long summaries
            if len(summary_data) > 1000:
                summary_data = summary_data[:1000] + "..."
            lines.append(f"  {summary_data}")

        # Fallback: dict type (legacy format)
        elif isinstance(summary_data, dict):
            # Key diagnoses
            diagnosis = summary_data.get("primary_diagnosis") or summary_data.get("diagnosis")
            if diagnosis:
                lines.append(f"  Diagnosis: {diagnosis}")

            # Chief complaints
            complaints = summary_data.get("chief_complaints") or summary_data.get("presenting_complaints")
            if complaints:
                if isinstance(complaints, list):
                    lines.append(f"  Complaints: {', '.join(str(c) for c in complaints[:3])}")
                else:
                    lines.append(f"  Complaints: {complaints}")

            # Key findings
            findings = summary_data.get("key_findings") or summary_data.get("significant_findings")
            if findings:
                lines.append(f"  Key Findings: {findings}")

            # Summary text
            summary_text = summary_data.get("summary") or summary_data.get("clinical_summary") or summary_data.get("brief_summary")
            if summary_text:
                # Truncate long summaries
                if len(str(summary_text)) > 1000:
                    summary_text = str(summary_text)[:1000] + "..."
                lines.append(f"  Summary: {summary_text}")

        lines.append("")  # Empty line between summaries

    return "\n".join(lines) if lines else ""

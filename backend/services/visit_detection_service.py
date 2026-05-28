"""
Visit Detection Service

Detects whether a new recording is a continuation of an existing visit
by finding prior extractions from the same patient using boundary-based detection.

Detection logic (boundary-based, no time window):
1. Fetch recent extractions for patient (capped at max_lookback rows)
2. Filter by matching criteria:
   a. Same doctor
   b. Nurse→Doctor: prior session had nurse linked to current doctor
   c. Doctor→Nurse: current session has nurse, prior was linked doctor
   d. Linked doctor: prior doctor is linked via doctor_doctor_patients
3. Find boundary: most recent matched extraction with is_continuation=false
4. All matched extractions from boundary onwards → parent chain
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


def detect_continuation_extractions(
    patient_id: str,
    doctor_id: str,
    nurse_id: Optional[str] = None,
    max_lookback: int = 50,
) -> Optional[Dict[str, Any]]:
    """
    Find prior extractions from the same visit for this patient.

    Uses boundary-based detection: finds the most recent extraction with
    is_continuation=false as the visit boundary, then includes all matched
    extractions from that boundary onwards.

    Args:
        patient_id: Patient UUID string
        doctor_id: Doctor UUID string
        nurse_id: Optional nurse UUID string (if current session is nurse-initiated)
        max_lookback: Max rows to scan (default: 50, no time filter)

    Returns:
        {
            "parent_extraction_ids": ["<ext_uuid_1>", ...],
            "detection_reason": "same_doctor" | "nurse_to_doctor" | "doctor_to_nurse" | "linked_doctor"
        }
        or None if no same-visit extractions found.
    """
    from services.supabase_service import supabase

    try:
        # 1. Fetch recent extractions (no time filter, capped at max_lookback)
        result = supabase.table("medical_extractions")\
            .select("id, doctor_id, created_at, is_continuation, parent_extraction_ids, recording_sessions(nurse_id, doctor_id)")\
            .eq("patient_id", patient_id)\
            .order("created_at", desc=True)\
            .limit(max_lookback)\
            .execute()

        all_extractions = result.data or []

        if not all_extractions:
            logger.debug(f"[VISIT_DETECT] No recent extractions for patient {patient_id}")
            return None

        # 2. Get linked doctor IDs for cross-doctor matching
        linked_doctor_ids = _get_linked_doctor_ids(doctor_id, patient_id=patient_id)

        # 3. Pre-parse session info and batch-fetch nurse-doctor links (avoids N+1 queries)
        parsed_extractions = []
        nurse_ids_to_check = set()
        doctor_ids_to_check = set()

        for ext in all_extractions:
            ext_doctor_id = ext.get("doctor_id")
            rs = ext.get("recording_sessions")
            session_nurse_id = None
            if rs:
                if isinstance(rs, dict):
                    session_nurse_id = rs.get("nurse_id")
                elif isinstance(rs, list) and rs:
                    session_nurse_id = rs[0].get("nurse_id")

            parsed_extractions.append((ext, ext_doctor_id, session_nurse_id))

            # Collect IDs needed for Rule 2 (prior nurse → current doctor)
            if session_nurse_id and not nurse_id:
                nurse_ids_to_check.add(session_nurse_id)
                doctor_ids_to_check.add(doctor_id)
            # Collect IDs needed for Rule 3 (current nurse → prior doctor)
            if nurse_id and not session_nurse_id and ext_doctor_id:
                nurse_ids_to_check.add(nurse_id)
                doctor_ids_to_check.add(ext_doctor_id)

        # Single batch query for all nurse-doctor links (replaces N individual queries)
        nurse_doctor_links = set()
        if nurse_ids_to_check:
            nurse_doctor_links = _batch_get_nurse_doctor_links(
                list(nurse_ids_to_check), list(doctor_ids_to_check)
            )

        # 4. Filter by matching criteria (4 rules) — all in-memory, zero DB calls
        matched = []
        detection_reason = None

        for ext, ext_doctor_id, session_nurse_id in parsed_extractions:
            reason = None

            # Rule 1: Same doctor
            if ext_doctor_id == doctor_id:
                reason = "same_doctor"

            # Rule 2: Nurse→Doctor (prior was by a nurse linked to current doctor)
            elif session_nurse_id and not nurse_id:
                if (session_nurse_id, doctor_id) in nurse_doctor_links:
                    reason = "nurse_to_doctor"

            # Rule 3: Doctor→Nurse (current session has nurse, prior was by linked doctor)
            elif nurse_id and not session_nurse_id:
                if ext_doctor_id and (nurse_id, ext_doctor_id) in nurse_doctor_links:
                    reason = "doctor_to_nurse"

            # Rule 4: Linked doctor (via doctor_doctor_patients)
            elif ext_doctor_id and ext_doctor_id in linked_doctor_ids:
                reason = "linked_doctor"

            if reason:
                matched.append(ext)
                if not detection_reason:
                    detection_reason = reason

        if not matched:
            logger.debug(f"[VISIT_DETECT] No matching extractions for patient {patient_id}, doctor {doctor_id[:8]}...")
            return None

        # 4. Find boundary: most recent matched extraction with is_continuation=false
        boundary_created_at = None
        for ext in matched:  # already ordered desc by created_at
            if not ext.get("is_continuation", False):
                boundary_created_at = ext["created_at"]
                break

        if boundary_created_at is None:
            # All matched extractions are continuations with no "new consultation" boundary.
            # This shouldn't happen normally (legacy data defaults is_continuation=false),
            # but handle gracefully by returning None.
            logger.warning(f"[VISIT_DETECT] No boundary (is_continuation=false) found among {len(matched)} matched extractions")
            return None

        # 5. Collect all matched extractions from boundary onwards (>= boundary time)
        parent_ids = set()
        for ext in matched:
            if ext["created_at"] >= boundary_created_at:
                parent_ids.add(ext["id"])
                # Include transitive parent_extraction_ids
                for pid in (ext.get("parent_extraction_ids") or []):
                    parent_ids.add(str(pid))

        if not parent_ids:
            return None

        parent_ids_list = list(parent_ids)

        logger.info(
            f"[VISIT_DETECT] Found {len(parent_ids_list)} parent extraction(s) for patient {patient_id}, "
            f"doctor {doctor_id[:8]}..., reason={detection_reason}, boundary={boundary_created_at}"
        )

        return {
            "parent_extraction_ids": parent_ids_list,
            "detection_reason": detection_reason,
        }

    except Exception as e:
        logger.error(f"[VISIT_DETECT] Error detecting continuation: {e}", exc_info=True)
        return None


def _get_linked_doctor_ids(doctor_id: str, patient_id: Optional[str] = None) -> List[str]:
    """
    Get all doctors linked to this doctor via doctor_doctor_patients.

    Single DB query with filtering pushed to PostgREST:
    - patient_ids IS NULL rows → share ALL patients (always match)
    - patient_id in patient_ids → share that specific patient (cs = contains)

    Args:
        doctor_id: Current doctor UUID string
        patient_id: Optional patient UUID string for selective matching

    Returns:
        List of linked doctor ID strings
    """
    from services.supabase_service import supabase

    try:
        query = supabase.table("doctor_doctor_patients")\
            .select("linked_doctor_id")\
            .eq("doctor_id", doctor_id)\
            .eq("is_active", True)

        if patient_id:
            # DB-level filter: match "share all" (NULL) OR array contains this patient
            query = query.or_(f"patient_ids.is.null,patient_ids.cs.{{{patient_id}}}")
        else:
            # No patient context — only match "share all" links
            query = query.is_("patient_ids", "null")

        result = query.execute()
        return list(set(row["linked_doctor_id"] for row in (result.data or [])))

    except Exception as e:
        logger.warning(f"[VISIT_DETECT] Error fetching linked doctors: {e}")
        return []


def _batch_get_nurse_doctor_links(
    nurse_ids: List[str], doctor_ids: List[str]
) -> set:
    """
    Batch-fetch all nurse-doctor links for the given IDs.
    Returns a set of (nurse_id, doctor_id) tuples for O(1) lookup.

    Single DB query replaces N individual _is_nurse_linked_to_doctor calls.
    """
    from services.supabase_service import supabase

    try:
        result = supabase.table("nurse_doctors")\
            .select("nurse_id, doctor_id")\
            .in_("nurse_id", nurse_ids)\
            .in_("doctor_id", doctor_ids)\
            .execute()
        return {(row["nurse_id"], row["doctor_id"]) for row in (result.data or [])}
    except Exception as e:
        logger.warning(f"[VISIT_DETECT] Error batch-fetching nurse-doctor links: {e}")
        return set()

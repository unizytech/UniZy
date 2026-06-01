"""
Visit Detection Service

Detects whether a new recording is a continuation of an existing visit
by finding prior extractions from the same student using boundary-based detection.

Detection logic (boundary-based, no time window):
1. Fetch recent extractions for student (capped at max_lookback rows)
2. Filter by matching criteria:
   a. Same counsellor
   b. Assistant→Counsellor: prior session had assistant linked to current counsellor
   c. Counsellor→Assistant: current session has assistant, prior was linked counsellor
   d. Linked counsellor: prior counsellor is linked via counsellor_counsellor_students
3. Find boundary: most recent matched extraction with is_continuation=false
4. All matched extractions from boundary onwards → parent chain
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


def detect_continuation_extractions(
    student_id: str,
    counsellor_id: str,
    assistant_id: Optional[str] = None,
    max_lookback: int = 50,
) -> Optional[Dict[str, Any]]:
    """
    Find prior extractions from the same visit for this student.

    Uses boundary-based detection: finds the most recent extraction with
    is_continuation=false as the visit boundary, then includes all matched
    extractions from that boundary onwards.

    Args:
        student_id: Student UUID string
        counsellor_id: Counsellor UUID string
        assistant_id: Optional assistant UUID string (if current session is assistant-initiated)
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
        result = supabase.table("extractions")\
            .select("id, counsellor_id, created_at, is_continuation, parent_extraction_ids, recording_sessions(assistant_id, counsellor_id)")\
            .eq("student_id", student_id)\
            .order("created_at", desc=True)\
            .limit(max_lookback)\
            .execute()

        all_extractions = result.data or []

        if not all_extractions:
            logger.debug(f"[VISIT_DETECT] No recent extractions for student {student_id}")
            return None

        # 2. Get linked counsellor IDs for cross-counsellor matching
        linked_counsellor_ids = _get_linked_counsellor_ids(counsellor_id, student_id=student_id)

        # 3. Pre-parse session info and batch-fetch assistant-counsellor links (avoids N+1 queries)
        parsed_extractions = []
        assistant_ids_to_check = set()
        counsellor_ids_to_check = set()

        for ext in all_extractions:
            ext_counsellor_id = ext.get("counsellor_id")
            rs = ext.get("recording_sessions")
            session_assistant_id = None
            if rs:
                if isinstance(rs, dict):
                    session_assistant_id = rs.get("assistant_id")
                elif isinstance(rs, list) and rs:
                    session_assistant_id = rs[0].get("assistant_id")

            parsed_extractions.append((ext, ext_counsellor_id, session_assistant_id))

            # Collect IDs needed for Rule 2 (prior assistant → current counsellor)
            if session_assistant_id and not assistant_id:
                assistant_ids_to_check.add(session_assistant_id)
                counsellor_ids_to_check.add(counsellor_id)
            # Collect IDs needed for Rule 3 (current assistant → prior counsellor)
            if assistant_id and not session_assistant_id and ext_counsellor_id:
                assistant_ids_to_check.add(assistant_id)
                counsellor_ids_to_check.add(ext_counsellor_id)

        # Single batch query for all assistant-counsellor links (replaces N individual queries)
        assistant_counsellor_links = set()
        if assistant_ids_to_check:
            assistant_counsellor_links = _batch_get_assistant_counsellor_links(
                list(assistant_ids_to_check), list(counsellor_ids_to_check)
            )

        # 4. Filter by matching criteria (4 rules) — all in-memory, zero DB calls
        matched = []
        detection_reason = None

        for ext, ext_counsellor_id, session_assistant_id in parsed_extractions:
            reason = None

            # Rule 1: Same counsellor
            if ext_counsellor_id == counsellor_id:
                reason = "same_doctor"

            # Rule 2: Assistant→Counsellor (prior was by an assistant linked to current counsellor)
            elif session_assistant_id and not assistant_id:
                if (session_assistant_id, counsellor_id) in assistant_counsellor_links:
                    reason = "nurse_to_doctor"

            # Rule 3: Counsellor→Assistant (current session has assistant, prior was by linked counsellor)
            elif assistant_id and not session_assistant_id:
                if ext_counsellor_id and (assistant_id, ext_counsellor_id) in assistant_counsellor_links:
                    reason = "doctor_to_nurse"

            # Rule 4: Linked counsellor (via counsellor_counsellor_students)
            elif ext_counsellor_id and ext_counsellor_id in linked_counsellor_ids:
                reason = "linked_doctor"

            if reason:
                matched.append(ext)
                if not detection_reason:
                    detection_reason = reason

        if not matched:
            logger.debug(f"[VISIT_DETECT] No matching extractions for student {student_id}, counsellor {counsellor_id[:8]}...")
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
            f"[VISIT_DETECT] Found {len(parent_ids_list)} parent extraction(s) for student {student_id}, "
            f"counsellor {counsellor_id[:8]}..., reason={detection_reason}, boundary={boundary_created_at}"
        )

        return {
            "parent_extraction_ids": parent_ids_list,
            "detection_reason": detection_reason,
        }

    except Exception as e:
        logger.error(f"[VISIT_DETECT] Error detecting continuation: {e}", exc_info=True)
        return None


def _get_linked_counsellor_ids(counsellor_id: str, student_id: Optional[str] = None) -> List[str]:
    """
    Get all counsellors linked to this counsellor via counsellor_counsellor_students.

    Single DB query with filtering pushed to PostgREST:
    - student_ids IS NULL rows → share ALL students (always match)
    - student_id in student_ids → share that specific student (cs = contains)

    Args:
        counsellor_id: Current counsellor UUID string
        student_id: Optional student UUID string for selective matching

    Returns:
        List of linked counsellor ID strings
    """
    from services.supabase_service import supabase

    try:
        query = supabase.table("counsellor_counsellor_students")\
            .select("linked_counsellor_id")\
            .eq("counsellor_id", counsellor_id)\
            .eq("is_active", True)

        if student_id:
            # DB-level filter: match "share all" (NULL) OR array contains this student
            query = query.or_(f"student_ids.is.null,student_ids.cs.{{{student_id}}}")
        else:
            # No student context — only match "share all" links
            query = query.is_("student_ids", "null")

        result = query.execute()
        return list(set(row["linked_counsellor_id"] for row in (result.data or [])))

    except Exception as e:
        logger.warning(f"[VISIT_DETECT] Error fetching linked counsellors: {e}")
        return []


def _batch_get_assistant_counsellor_links(
    assistant_ids: List[str], counsellor_ids: List[str]
) -> set:
    """
    Batch-fetch all assistant-counsellor links for the given IDs.
    Returns a set of (assistant_id, counsellor_id) tuples for O(1) lookup.

    Single DB query replaces N individual _is_nurse_linked_to_doctor calls.
    """
    from services.supabase_service import supabase

    try:
        result = supabase.table("assistant_counsellors")\
            .select("assistant_id, counsellor_id")\
            .in_("assistant_id", assistant_ids)\
            .in_("counsellor_id", counsellor_ids)\
            .execute()
        return {(row["assistant_id"], row["counsellor_id"]) for row in (result.data or [])}
    except Exception as e:
        logger.warning(f"[VISIT_DETECT] Error batch-fetching assistant-counsellor links: {e}")
        return set()

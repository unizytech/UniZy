"""
Continuation Merge Micro-Validator Service

Validates the AI's merge decisions for continuation (follow-up session) extractions by reviewing:
1. Parent list items that are missing from current output (accidental drops vs deliberate removals)
2. Cross-segment consistency (task lifecycle/date sanity, next-meeting date, goal-direction
   consistency, assessment-meter latest-wins)

This is a focused, single-purpose AI call (~2-3s) that only runs when triggered by specific
conditions (missing items, lifecycle/stop intent). On failure, the caller falls back to
empty-segment-only carry-forward. The return contract
{carry_forward, confirm_removed, cross_segment_patches} is consumed by the merge engine in
extraction_service._smart_merge_continuation.
"""

import json
import logging
import asyncio
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

_VALIDATOR_TIMEOUT_SECONDS = 45

_DEFAULT_VALIDATOR_MODEL = "gemini-2.5-flash"


async def validate_continuation_merge(
    current_lists: Dict[str, list],
    parent_lists: Dict[str, list],
    current_non_lists: Dict[str, Any],
    transcript: str,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Micro-validator: reviews Gemini's merge decisions for list segments.

    Returns dict with:
    - carry_forward: parent items Gemini accidentally dropped (should be added back)
    - confirm_removed: parent items Gemini deliberately removed (validated)
    - cross_segment_patches: consistency fixes (allergy conflicts, state transitions)

    Returns None on failure (caller should fall back to empty-segment-only carry-forward).
    """
    from services.gemini_client_factory import get_gemini_client
    from google.genai import types

    client = get_gemini_client()
    validator_model = model or _DEFAULT_VALIDATOR_MODEL

    # Build context for non-list segments (truncate HPI to keep token count low)
    context_summary = {}
    for key, value in current_non_lists.items():
        if isinstance(value, str) and len(value) > 500:
            context_summary[key] = value[:500] + "..."
        else:
            context_summary[key] = value

    prompt = f"""You are a school/university-counselling session merge validator. A counsellor
recorded a follow-up session that continues a prior session with the same student. The AI
extracted data from the new recording and was supposed to MERGE it with the prior session's
record (a deep merge: carry everything forward, update what changed, add what's new).

Your job: validate the merge decisions for LIST segments only (e.g. `tasks`, `keyFacts`).

PARENT LIST ITEMS (from the prior session):
{json.dumps(parent_lists, indent=2, default=str)}

CURRENT LIST ITEMS (AI's merged output):
{json.dumps(current_lists, indent=2, default=str)}

CURRENT NON-LIST CONTEXT (goals, academics, assessment meters, next steps, etc.):
{json.dumps(context_summary, indent=2, default=str)}

TRANSCRIPT OF CURRENT SESSION:
{transcript}

ITEM IDENTITY:
- `tasks`: each item is an object identified by its `task_name`.
- `keyFacts`: each item is a single sentence string; the string itself is its identity.

TASK 1 — MISSING ITEM VALIDATION:
For each parent item NOT present in the current output, decide which applies:
1. DELIBERATELY REMOVED — the counsellor explicitly completed / cancelled / dropped it in the
   transcript (e.g. "you've finished the Common App essay", "let's drop the chess club idea").
2. ACCIDENTALLY DROPPED — not mentioned in the transcript at all → should be carried forward.
3. REFINED — same item, reworded/clarified (e.g. "Draft essay" → "Draft Common App personal essay").

IMPORTANT — KEY-FACT SPECIFICITY:
- If the parent has a SPECIFIC fact (e.g. "Targeting Computer Science at top-10 US universities")
  and the current output has a VAGUE version (e.g. "Interested in university"), carry forward the
  PARENT's specific version and mark the vague current version for removal. Counselling records
  need specificity — keep the more detailed wording for the same fact.

IMPORTANT — PARTIAL CHANGES:
- The counsellor may complete/cancel ONLY SOME tasks (e.g. "finish A and B" but C, D continue).
  Evaluate EACH missing item independently against the transcript.
- Resolve ONLY SOME facts/goals while others persist. Check each one.

TASK 2 — TASK LIFECYCLE & DATE SANITY:
Check ALL `tasks` items in BOTH parent AND current lists:
- If the transcript says a task is DONE / COMPLETED / FINISHED / DROPPED / CANCELLED → REMOVE it
  from `tasks` (confirm_removed). Phrases: "you've completed", "that's done", "we can drop", "skip
  that one", "no longer needed".
- DATE SANITY: flag any task whose `end_date` is before its `start_date`, or whose dates are
  clearly stale/implausible relative to the session — emit a `flag` patch (do NOT auto-delete).
- Tasks NOT discussed in the transcript must remain in their current state.

TASK 3 — CROSS-SEGMENT CONSISTENCY CHECKS:
a) NEXT MEETING DATE: if `nextSteps` has a next-meeting Date, it should be parseable and not in
   the past relative to the session → otherwise `flag`.
b) DIRECTION ↔ GOALS: if `directionalChanges` indicates the student changed direction (e.g. switched
   target course/career), ensure `futureGoals`/`academics` reflect the NEW direction; if a stale
   goal still lingers that contradicts the change, `flag` it (counsellor decision needed).
c) ASSESSMENT METERS (latest-wins): post-session values (e.g. Post-Session Anxiety) should come
   from the CURRENT session, not the parent. If a current value is present, it wins.

Return JSON with exactly this structure:
{{
  "carry_forward": [
    {{"segment": "tasks", "item": {{}}, "reason": "not mentioned in transcript, should continue"}}
  ],
  "confirm_removed": [
    {{"segment": "tasks", "item_name": "Draft Common App essay", "reason": "counsellor said it's completed"}},
    {{"segment": "keyFacts", "item_name": "Interested in university", "reason": "replaced by more specific parent fact"}}
  ],
  "cross_segment_patches": [
    {{"type": "task_date", "segment": "tasks", "item_name": "Visit campus", "action": "flag", "reason": "end_date is before start_date"}},
    {{"type": "next_meeting_date", "segment": "nextSteps", "item_name": "Next meeting", "action": "flag", "reason": "scheduled date is in the past"}},
    {{"type": "goal_inconsistency", "segment": "futureGoals", "item_name": "Medicine", "action": "flag", "reason": "student switched target to Computer Science"}}
  ]
}}

Rules:
- carry_forward.item must be the FULL item object copied from the parent data.
- If ALL parent items are present in current with no issues, return empty arrays.
- Be conservative: when in doubt, carry forward (preserving the student's record > tidiness).
- Do NOT invent items that weren't in parent or current data.
- Evaluate EACH item independently — partial completions/removals are common.
- Use `action: "remove"` only inside confirm_removed; cross_segment_patches should generally use
  `action: "flag"` (log-only) unless an item clearly must be removed.
- For key facts: PREFER the parent's specific wording over the current's vague version of the same fact."""

    try:
        # Log inputs for observability
        parent_item_counts = {k: len(v) for k, v in parent_lists.items()}
        current_item_counts = {k: len(v) for k, v in current_lists.items()}
        logger.info(
            f"[CONTINUATION_VALIDATOR] Calling model={validator_model} | "
            f"parent_lists={parent_item_counts} | current_lists={current_item_counts} | "
            f"context_keys={list(context_summary.keys())} | transcript_len={len(transcript)}"
        )
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=validator_model,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            ),
            timeout=_VALIDATOR_TIMEOUT_SECONDS,
        )

        if not response or not response.text:
            logger.warning("[CONTINUATION_VALIDATOR] Empty response from Gemini")
            return None

        result = json.loads(response.text)

        # Validate structure
        if not isinstance(result, dict):
            logger.warning(f"[CONTINUATION_VALIDATOR] Unexpected response type: {type(result)}")
            return None

        # Ensure required keys exist with defaults
        validated = {
            "carry_forward": result.get("carry_forward", []),
            "confirm_removed": result.get("confirm_removed", []),
            "cross_segment_patches": result.get("cross_segment_patches", []),
        }

        cf_count = len(validated["carry_forward"])
        cr_count = len(validated["confirm_removed"])
        patch_count = len(validated["cross_segment_patches"])
        logger.info(
            f"[CONTINUATION_VALIDATOR] Result: "
            f"{cf_count} carry_forward, {cr_count} confirm_removed, {patch_count} patches"
        )

        # Log details of each decision
        for cf in validated["carry_forward"]:
            item_name = cf.get("item", {}).get("name", "") if isinstance(cf.get("item"), dict) else str(cf.get("item", ""))
            logger.info(
                f"[CONTINUATION_VALIDATOR] CARRY_FORWARD: segment={cf.get('segment')} "
                f"item={item_name} reason={cf.get('reason', '')}"
            )
        for cr in validated["confirm_removed"]:
            logger.info(
                f"[CONTINUATION_VALIDATOR] CONFIRM_REMOVED: segment={cr.get('segment')} "
                f"item={cr.get('item_name', '')} reason={cr.get('reason', '')}"
            )
        for patch in validated["cross_segment_patches"]:
            logger.info(
                f"[CONTINUATION_VALIDATOR] PATCH: type={patch.get('type')} "
                f"segment={patch.get('segment')} item={patch.get('item_name', '')} "
                f"action={patch.get('action', '')} reason={patch.get('reason', '')}"
            )

        return validated

    except asyncio.TimeoutError:
        logger.warning(f"[CONTINUATION_VALIDATOR] Timed out after {_VALIDATOR_TIMEOUT_SECONDS}s")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"[CONTINUATION_VALIDATOR] Failed to parse response JSON: {e}")
        return None
    except Exception as e:
        logger.warning(f"[CONTINUATION_VALIDATOR] Failed (non-fatal): {e}")
        return None

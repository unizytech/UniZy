"""
Continuation Merge Micro-Validator Service

Validates Gemini's merge decisions for continuation extractions by reviewing:
1. Parent list items that are missing from current output (accidental drops vs deliberate removals)
2. Cross-segment consistency (allergy-prescription conflicts, investigation state, vitals contradictions)

This is a focused, single-purpose Gemini call (~2-3s) that only runs when triggered
by specific conditions (missing items, stop intent, allergy+Rx, investigation results).
On failure, the caller falls back to empty-segment-only carry-forward.
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

    prompt = f"""You are a medical record merge validator. A doctor recorded a continuation
of a prior visit. The AI extracted data from the new recording and was supposed to merge
it with the prior recording's data.

Your job: validate the merge decisions for LIST segments only.

PARENT LIST ITEMS (from prior recording):
{json.dumps(parent_lists, indent=2, default=str)}

CURRENT LIST ITEMS (AI's merged output):
{json.dumps(current_lists, indent=2, default=str)}

CURRENT NON-LIST CONTEXT:
{json.dumps(context_summary, indent=2, default=str)}

TRANSCRIPT OF CURRENT RECORDING:
{transcript}

TASK 1 — MISSING ITEM VALIDATION:
For each parent item NOT present in the current output, determine:
1. Was it DELIBERATELY REMOVED? (doctor explicitly stopped/cancelled/resolved it in transcript)
2. Was it ACCIDENTALLY DROPPED? (not mentioned in transcript, should be carried forward)
3. Was it REFINED? (same concept, different name — e.g., "Suspected Pneumonia" → "Bacterial Pneumonia")

IMPORTANT — CHIEF COMPLAINTS SPECIFICITY:
- If the parent has a SPECIFIC complaint (e.g., "Right wrist and finger pain for 1 week") and the
  current output has a VAGUE version (e.g., "Pain"), carry forward the PARENT's specific version
  and mark the vague current version for removal. Medical records need specificity — site, duration,
  and context must be preserved. The parent's wording is preferred over the current's if the parent
  is more detailed about the same complaint.

IMPORTANT — PARTIAL CHANGES:
- Doctor may stop ONLY SOME medications (e.g., "stop A and B" but C, D should continue).
  Evaluate EACH missing item independently against the transcript.
- Doctor may review results for ONLY SOME investigations. Others stay as "ordered."
  Do NOT assume all investigations got results just because some did.
- Doctor may resolve ONLY SOME complaints while others persist. Check each one.

TASK 2 — INVESTIGATION RESULTS REVIEW:
Check ALL investigation items in BOTH parent AND current lists (not just missing items).
If the transcript discusses results for ANY investigation — whether the investigation is missing
from current OR still present in current — it means the test has been PERFORMED:
- REMOVE it from investigations (confirm_removed) — it is no longer pending
- ADD the result to examination via cross_segment_patch (add_to_examination)
- This applies whether the investigation is only in parent, or in BOTH parent and current
- Common phrases indicating results were reviewed: "saw your X-ray", "X-ray shows", "report is normal",
  "results came back", "test shows", "looked at your scan", "your blood work is fine"
- Investigations NOT discussed in transcript must remain in their current state

Example: Doctor says "when we saw your X-ray, your bone is quite weak" →
  1. confirm_removed: segment=investigations, item_name="X-Ray Hand", reason="results discussed - bone weakness noted"
  2. cross_segment_patch: type="investigation_result", segment="examination", action="add_to_examination",
     item={{"name": "X-Ray Hand", "value": "Bone weakness noted"}}, reason="X-ray results reviewed in transcript"

TASK 3 — CROSS-SEGMENT CONSISTENCY CHECKS:
Check these cross-segment relationships:

a) ALLERGY ↔ PRESCRIPTION: Any prescribed drug that conflicts with an allergy?
   → Action: remove the conflicting drug from prescription

b) VITALS ↔ TRANSCRIPT: Vitals showing abnormal values but transcript says condition resolved?
   → Action: flag for review (e.g., "fever resolved" but temperature still shows 102°F)

Return JSON with exactly this structure:
{{
  "carry_forward": [
    {{"segment": "prescription", "item": {{}}, "reason": "not mentioned in transcript, should continue"}}
  ],
  "confirm_removed": [
    {{"segment": "prescription", "item_name": "Paracetamol", "reason": "doctor explicitly said stop"}},
    {{"segment": "investigations", "item_name": "X-Ray Hand", "reason": "results discussed - bone weakness noted"}}
  ],
  "cross_segment_patches": [
    {{"type": "allergy_conflict", "segment": "prescription", "item_name": "Amoxicillin", "action": "remove", "reason": "conflicts with Amoxicillin allergy"}},
    {{"type": "investigation_result", "segment": "examination", "action": "add_to_examination", "item": {{"name": "X-Ray Hand", "value": "Bone weakness noted"}}, "reason": "X-ray results reviewed in transcript"}},
    {{"type": "complaint_specificity", "segment": "chiefComplaints", "item_name": "Pain", "action": "remove", "reason": "replaced by more specific parent complaint"}}
  ]
}}

Rules:
- carry_forward.item must be the FULL item object copied from the parent data
- If ALL parent items are present in current with no issues, return empty arrays
- Only flag allergy conflicts when there's a clear drug-allergy match
- Be conservative: when in doubt, carry forward (patient safety > data cleanliness)
- Do NOT invent items that weren't in parent or current data
- Evaluate EACH item independently — partial stops/results/resolutions are common
- For investigation results: ALWAYS pair a confirm_removed with an add_to_examination patch so data is not lost
- For chief complaints: PREFER the parent's specific wording over the current's vague version of the same complaint"""

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

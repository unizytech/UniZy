"""
Translation Service for Extractions

Translates student-facing fields of extraction results into Indic languages.
Runs as fire-and-forget post-extraction, zero pipeline latency impact.
"""

import asyncio
import copy
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Translatable fields per segment code ───────────────────────────────────
# Maps segment_code -> list of field names that should be translated.
# Fields NOT listed here are kept in English (drug names, ICD codes, dates, etc.)

TRANSLATABLE_FIELDS: Dict[str, List[str]] = {
    # HIGH priority — student-facing instructions
    "PRESCRIPTION": ["remarks", "timeToTake"],
    "TREATMENT_PLAN": [],  # Multi-schema: array/object/string — handled dynamically when fields=[]
    "FOLLOW_UP": ["special_instructions", "other_instructions"],
    "WARNINGS": ["safety_summary"],
    "EMERGENCY_CONTACT": [],  # String — translate directly
    "CAUTION": [],  # String — student-facing treatment limitations

    # MEDIUM priority — clinical narrative
    "CHIEF_COMPLAINTS": [],  # Array of strings — translate all items directly
    "DIAGNOSIS": ["notes"],
    "HISTORY_OF_PRESENT_ILLNESS": ["impact_on_daily_life", "aggravating_factors", "alleviating_factors",
                                    "progression", "characterization",
                                    "negative_findings"],
    "HISTORY": ["family_history", "social_history", "past_medical_history"],
    "REFERRAL_DETAILS": ["reason_for_referral"],

    # Additional segments from various templates
    "CLINICAL_NOTES": [
        "instructions", "follow_up", "treatment", "chief_complaints",
        "clinical_assessment", "examination_findings", "past_medical_history",
        "history_of_present_illness", "family_history", "social_history",
    ],
    "CONSUMABLES": ["instructions"],
    "HOSPITAL_COURSE": ["summary", "daily_progress", "complications"],
    "DISCHARGE_CONDITION": ["condition_at_discharge", "functional_status"],
    "TREATMENT_SUMMARY": ["treatment_summary", "patient_response"],
    "TREATMENT_DETAILS": ["operation_notes", "intraoperative_findings"],
    "PROCEDURE_NOTES": ["notes", "post_procedure_instructions", "findings"],
    "PSG_COURSE_IN_HOSPITAL": ["course_in_hospital"],
    "PSG_CONDITION_ON_DISCHARGE": ["condition_on_discharge"],
    "PSG_ADMISSION_DETAILS": ["admission_details"],
    "PSG_MORBIDITY_ASSESSMENT": ["details", "reason_prolonged_stay"],
    "GENERAL_HISTORY": [
        "detailed_medical_history", "known_medical_problems", "personal_history",
        "sleep_details", "occupation_info", "other_relevant_history", "addiction_details",
    ],
    "GENERAL_EXAMINATION": ["general_findings", "other_relevant_finding"],
    "SURGICAL_HISTORY": ["aggravating_factors", "progress"],
    "MENTAL_STATUS_EXAMINATION": [
        "mood_and_affect", "thought_process_and_content", "cognition",
        "perception", "insight_and_judgment",
    ],
    "VISIT_SUMMARY": ["visit_summary"],
    "TB_SCREENING": ["remarks"],
    "ALLERGIES": ["details"],
    "ALLERGY": ["details"],
    "SYSTEMIC_EXAMINATION": ["examination"],
}


def _normalize_key(key: str) -> str:
    """Normalize a key for case-insensitive matching.
    Converts UPPER_SNAKE_CASE and camelCase to lowercase without separators.
    e.g. FOLLOW_UP -> followup, followUp -> followup, clinicalNotes -> clinicalnotes
    """
    return key.replace("_", "").lower()


def _build_key_map(extraction_json: Dict[str, Any]) -> Dict[str, str]:
    """Build a normalized-key -> actual-key mapping for extraction JSON.
    Allows TRANSLATABLE_FIELDS (UPPER_SNAKE) to match camelCase extraction keys.
    """
    return {_normalize_key(k): k for k in extraction_json}


# Supported languages
SUPPORTED_LANGUAGES = {
    "tamil": "Tamil (தமிழ்)",
    "hindi": "Hindi (हिन्दी)",
    "telugu": "Telugu (తెలుగు)",
    "kannada": "Kannada (ಕನ್ನಡ)",
    "malayalam": "Malayalam (മലയാളം)",
    "bengali": "Bengali (বাংলা)",
    "marathi": "Marathi (मराठी)",
    "gujarati": "Gujarati (ગુજરાતી)",
}


def _extract_translatable_fields(extraction_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract only translatable fields from extraction JSON into a sparse structure.
    This minimizes token cost by sending only what needs translation to Gemini.

    Uses case-insensitive matching so TRANSLATABLE_FIELDS keys (UPPER_SNAKE_CASE)
    match extraction JSON keys (camelCase, snake_case, etc.).

    The sparse dict keys use the ACTUAL extraction JSON key (preserving case),
    so merge can map them back directly.

    Returns a dict like:
    {
        "prescription": {"data": [{"remarks": "Take after food", "timeToTake": "Morning"}]},
        "clinicalNotes": {"data": {"instructions": "...", "treatment": "..."}}
    }
    """
    sparse = {}
    key_map = _build_key_map(extraction_json)

    for segment_code, fields in TRANSLATABLE_FIELDS.items():
        # Case-insensitive lookup: FOLLOW_UP matches followUp, CLINICAL_NOTES matches clinicalNotes
        normalized = _normalize_key(segment_code)
        actual_key = key_map.get(normalized)
        if not actual_key:
            continue

        segment_data = extraction_json[actual_key]

        # Handle both dict-with-data and direct-value formats
        if isinstance(segment_data, dict):
            data_value = segment_data.get("data", segment_data)
        else:
            data_value = segment_data

        if data_value is None:
            continue

        # Handle list of items (e.g., prescription has array of medicines)
        if isinstance(data_value, list):
            if not fields:
                # No specific fields — translate all string items directly (e.g., treatment_plan array)
                string_items = [item for item in data_value if isinstance(item, str) and item.strip()]
                if string_items:
                    sparse[actual_key] = {"data": string_items}
            else:
                # Array of objects with specific translatable fields (e.g., prescription)
                sparse_items = []
                for item in data_value:
                    if not isinstance(item, dict):
                        continue
                    sparse_item = {}
                    for field in fields:
                        if field in item and item[field]:
                            val = item[field]
                            # Only translate non-empty strings or lists of strings
                            if isinstance(val, str) and val.strip():
                                sparse_item[field] = val
                            elif isinstance(val, list) and val:
                                sparse_item[field] = val
                    if sparse_item:
                        sparse_items.append(sparse_item)
                if sparse_items:
                    sparse[actual_key] = {"data": sparse_items}

        elif isinstance(data_value, dict):
            if not fields:
                # No specific fields — translate all non-empty string values in the dict
                sparse_item = {}
                for k, v in data_value.items():
                    if isinstance(v, str) and v.strip():
                        sparse_item[k] = v
                if sparse_item:
                    sparse[actual_key] = {"data": sparse_item}
            else:
                sparse_item = {}
                for field in fields:
                    if field in data_value and data_value[field]:
                        val = data_value[field]
                        if isinstance(val, str) and val.strip():
                            sparse_item[field] = val
                        elif isinstance(val, list) and val:
                            sparse_item[field] = val
                if sparse_item:
                    sparse[actual_key] = {"data": sparse_item}

        elif isinstance(data_value, str) and data_value.strip():
            # Direct string value for the segment
            if not fields or len(fields) == 1:
                sparse[actual_key] = {"data": data_value}
            else:
                for field in fields:
                    if field == segment_code.lower():
                        sparse[actual_key] = {"data": data_value}
                        break

    return sparse


def _merge_translations_into_copy(
    full_copy: Dict[str, Any],
    translated_sparse: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge translated fields back into the full extraction copy,
    replacing only the translatable fields while keeping everything else in English.

    Uses case-insensitive matching to handle key format differences between
    the translated sparse dict and the full extraction copy.
    """
    key_map = _build_key_map(full_copy)

    for sparse_key, translated_segment in translated_sparse.items():
        # Case-insensitive lookup to find matching key in full_copy
        normalized = _normalize_key(sparse_key)
        actual_key = key_map.get(normalized)
        if not actual_key:
            continue

        translated_data = translated_segment.get("data") if isinstance(translated_segment, dict) else translated_segment
        if translated_data is None:
            continue

        original_segment = full_copy[actual_key]

        if isinstance(original_segment, dict) and "data" in original_segment:
            original_data = original_segment["data"]
        else:
            original_data = original_segment

        # Handle list of items
        if isinstance(original_data, list) and isinstance(translated_data, list):
            for i, translated_item in enumerate(translated_data):
                if i >= len(original_data):
                    break
                if isinstance(translated_item, dict) and isinstance(original_data[i], dict):
                    for field, value in translated_item.items():
                        if field in original_data[i]:
                            original_data[i][field] = value

        # Handle dict
        elif isinstance(original_data, dict) and isinstance(translated_data, dict):
            for field, value in translated_data.items():
                if field in original_data:
                    original_data[field] = value

        # Handle direct string value
        elif isinstance(original_data, str) and isinstance(translated_data, str):
            if isinstance(original_segment, dict) and "data" in original_segment:
                original_segment["data"] = translated_data
            else:
                full_copy[actual_key] = translated_data

    return full_copy


def _build_translation_prompt(sparse_json: Dict[str, Any], target_language: str) -> str:
    """Build the Gemini prompt for translating extraction fields."""
    lang_display = SUPPORTED_LANGUAGES.get(target_language, target_language.title())

    return f"""You are a medical document translator specializing in {lang_display} translation.

TASK: Translate the following extraction fields from English to {lang_display}.

CRITICAL RULES:
1. Translate ONLY the text values. Keep all JSON keys exactly as they are.
2. NEVER translate: drug names, medicine names, ICD codes, medical procedure names, numbers, dates, dosages, units.
3. For well-known medical terms that have a common local equivalent, use the local term followed by the English term in parentheses. Example: "சர்க்கரை நோய் (Diabetes)"
4. Use natural, colloquial {lang_display} that students can easily understand. Avoid overly formal or Sanskritized language.
5. If a value is already a number, date, code, or untranslatable term, return it as-is.
6. Preserve the exact JSON structure. Return valid JSON only.
7. For lists of strings, translate each string in the list individually.

INPUT JSON:
```json
{json.dumps(sparse_json, indent=2, ensure_ascii=False)}
```

Return ONLY the translated JSON with the same structure. No explanation, no markdown fences."""


async def translate_extraction(
    extraction_json: Dict[str, Any],
    target_language: str,
    model_name: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    """
    Translate an extraction's student-facing fields into the target language.

    Returns a full copy of the extraction JSON with translatable fields in target language
    and non-translatable fields kept in English.
    """
    # Step 1: Extract only translatable fields (sparse structure)
    sparse = _extract_translatable_fields(extraction_json)

    if not sparse:
        logger.info(f"[TRANSLATION] No translatable fields found in extraction")
        return copy.deepcopy(extraction_json)

    logger.debug(f"[TRANSLATION] Extracted {len(sparse)} segments with translatable fields")

    # Step 2: Build prompt and call Gemini
    prompt = _build_translation_prompt(sparse, target_language)

    from google.genai import types
    from services.gemini_client_factory import get_gemini_client

    client = get_gemini_client()

    response = await client.aio.models.generate_content(
        model=model_name,
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    # Step 3: Parse translated JSON
    response_text = response.text.strip()

    # Clean markdown fences if present
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        response_text = "\n".join(lines)

    translated_sparse = json.loads(response_text)

    # Step 4: Deep copy original and merge translations
    full_copy = copy.deepcopy(extraction_json)
    result = _merge_translations_into_copy(full_copy, translated_sparse)

    logger.debug(f"[TRANSLATION] Successfully merged translations for {len(translated_sparse)} segments")
    return result


async def schedule_translation(
    extraction_id: uuid.UUID,
    extraction_data: Dict[str, Any],
    counsellor_id: str,
    processing_mode_code: str = "default",
) -> None:
    """
    Public fire-and-forget entry point for translation.
    Checks if counsellor has translation_language configured and schedules translation.
    """
    try:
        from services.supabase_service import get_counsellor_translation_language

        target_language = get_counsellor_translation_language(uuid.UUID(counsellor_id) if isinstance(counsellor_id, str) else counsellor_id)

        if not target_language:
            logger.debug(f"[TRANSLATION] No translation language configured for counsellor {counsellor_id} - skipping")
            return

        if target_language.lower() not in SUPPORTED_LANGUAGES:
            logger.warning(f"[TRANSLATION] Unsupported language '{target_language}' for counsellor {counsellor_id} - skipping")
            return

        logger.debug(f"[TRANSLATION] Scheduling translation to '{target_language}' for extraction {extraction_id}")

        asyncio.create_task(
            _run_translation(
                extraction_id=extraction_id,
                extraction_data=extraction_data,
                target_language=target_language.lower(),
                processing_mode_code=processing_mode_code,
            )
        )

        logger.debug(f"[TRANSLATION] Translation scheduled (fire-and-forget) for extraction {extraction_id}")

    except Exception as e:
        logger.warning(f"[TRANSLATION] Failed to schedule translation: {e}")


async def _run_translation(
    extraction_id: uuid.UUID,
    extraction_data: Dict[str, Any],
    target_language: str,
    processing_mode_code: str = "default",
) -> None:
    """
    Internal async worker that performs the actual translation.
    Waits for extraction to exist in DB, translates, and saves.
    """
    from services.supabase_service import (
        get_translation_model_by_mode,
        save_extraction_translation,
        update_extraction_translation_status,
    )

    start_time = time.time()

    try:
        # Wait for extraction to exist in DB (handles race condition with fire-and-forget DB save)
        from services.background_tasks import _wait_for_extraction_to_exist

        extraction_exists = await _wait_for_extraction_to_exist(extraction_id, max_wait_seconds=30)
        if not extraction_exists:
            logger.warning(f"[TRANSLATION] Extraction {extraction_id} not found after waiting - skipping")
            return

        # Create initial record to mark translation as started
        save_extraction_translation(
            extraction_id=extraction_id,
            target_language=target_language,
            translated_json={},  # Placeholder
            model_used="",
            translation_time_seconds=0,
            started=True,
            completed=False,
        )

        # Get model from processing_modes
        model_name = get_translation_model_by_mode(processing_mode_code)
        logger.info(f"[TRANSLATION] Using model '{model_name}' for {target_language} translation of extraction {extraction_id}")

        # Perform translation (with retry for transient network errors)
        max_retries = 2
        translated_json = None
        for attempt in range(1, max_retries + 1):
            try:
                translated_json = await translate_extraction(
                    extraction_json=extraction_data,
                    target_language=target_language,
                    model_name=model_name,
                )
                break
            except Exception as retry_err:
                if attempt < max_retries and "ConnectError" in type(retry_err).__name__ or "ConnectError" in str(retry_err):
                    logger.warning(f"[TRANSLATION] Attempt {attempt} failed (network), retrying in 3s: {retry_err}")
                    await asyncio.sleep(3)
                else:
                    raise

        elapsed = time.time() - start_time

        # Save completed translation
        update_extraction_translation_status(
            extraction_id=extraction_id,
            target_language=target_language,
            translated_json=translated_json,
            model_used=model_name,
            translation_time_seconds=round(elapsed, 2),
            completed=True,
            failed=False,
        )

        logger.info(
            f"[TRANSLATION] ✅ Completed {target_language} translation for extraction {extraction_id} "
            f"in {elapsed:.2f}s using {model_name}"
        )

    except json.JSONDecodeError as e:
        elapsed = time.time() - start_time
        error_msg = f"Failed to parse Gemini translation response: {e}"
        logger.error(f"[TRANSLATION] {error_msg}")
        try:
            update_extraction_translation_status(
                extraction_id=extraction_id,
                target_language=target_language,
                completed=False,
                failed=True,
                error=error_msg,
                translation_time_seconds=round(elapsed, 2),
            )
        except Exception:
            pass

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"Translation failed: {str(e)}"
        logger.error(f"[TRANSLATION] {error_msg}", exc_info=True)
        try:
            update_extraction_translation_status(
                extraction_id=extraction_id,
                target_language=target_language,
                completed=False,
                failed=True,
                error=error_msg,
                translation_time_seconds=round(elapsed, 2),
            )
        except Exception:
            pass

"""
Gemini AI Service for medical transcription and insight extraction.
Ported from TypeScript lib/gemini.ts
"""

import os
import json
import logging
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
import re
import httpx  # For catching connection errors gracefully

from .error_utils import sanitize_error_message as _sanitize_error_message
from .log_sanitizer import truncate_id
from .gemini_audio_part_service import build_audio_part, cleanup_audio_part

from .neonatal_prompts import (
    NEO_DAILY_PROMPT_SYSTEM,
    NEO_DAILY_PROMPT_USER,
    NEO_PROFORMA_PROMPT_SYSTEM,
    NEO_PROFORMA_PROMPT_USER,
    NEO_DAILY_PARAMETERS_SCHEMA,
    NEO_OP_PROMPT_SYSTEM,
    NEO_OP_PROMPT_USER,
    NEO_DISCHARGE_SYSTEM_PROMPT,
    NEO_DISCHARGE_USER_PROMPT,
    NEO_ADMISSION_SYSTEM_PROMPT,
    NEO_ADMISSION_USER_PROMPT,
)

from .neo_proforma_prompts_split import NEO_PROFORMA_PART1_SCHEMA, NEO_PROFORMA_PART2_SCHEMA
from .neo_proforma_formatter import format_neo_proforma_from_parts

from .neo_op_prompts_split import NEO_OP_PART1_SCHEMA, NEO_OP_PART2_SCHEMA
from .neo_op_formatter import format_neo_op_from_parts

from .neo_discharge_prompts_split import NEO_DISCHARGE_PART1_SCHEMA, NEO_DISCHARGE_PART2_SCHEMA
from .neo_discharge_formatter import format_neo_discharge_from_parts

from .neo_admission_prompts_split import NEO_ADMISSION_PART1_SCHEMA, NEO_ADMISSION_PART2_SCHEMA
from .neo_admission_formatter import format_neo_admission_from_parts

from .neo_daily_prompts_split import (
    NEO_DAILY_PART1_SCHEMA,
    NEO_DAILY_PART2_SCHEMA,
    NEO_DAILY_SPLIT_SYSTEM_PROMPT,
    NEO_DAILY_PART1_USER_PROMPT,
    NEO_DAILY_PART2_USER_PROMPT,
)
from .neo_daily_formatter import format_neo_daily_from_parts

# NEO_DAILY_FREE: Simplified neonatal daily progress (17 flat free-text fields)
from .neo_daily_free_prompts import (
    NEO_DAILY_FREE_SCHEMA,
    NEO_DAILY_FREE_SYSTEM_PROMPT,
    NEO_DAILY_FREE_USER_PROMPT,
)

# NEO_PROFORMA_FREE: Neonatal proforma free-text (21 fields)
from .neo_proforma_free_prompts import (
    NEO_PROFORMA_FREE_SCHEMA,
    NEO_PROFORMA_FREE_SYSTEM_PROMPT,
    NEO_PROFORMA_FREE_USER_PROMPT,
)

# NEO_DISCHARGE_FREE: NICU discharge free-text (21 fields)
from .neo_discharge_free_prompts import (
    NEO_DISCHARGE_FREE_SCHEMA,
    NEO_DISCHARGE_FREE_SYSTEM_PROMPT,
    NEO_DISCHARGE_FREE_USER_PROMPT,
)

# NEO_POSTNATAL_DAY_FREE: Postnatal daycare free-text (9 fields)
from .neo_postnatal_day_free_prompts import (
    NEO_POSTNATAL_DAY_FREE_SCHEMA,
    NEO_POSTNATAL_DAY_FREE_SYSTEM_PROMPT,
    NEO_POSTNATAL_DAY_FREE_USER_PROMPT,
)

# NEO_POSTNATAL_DISCHARGE_FREE: Postnatal discharge free-text (15 fields)
from .neo_postnatal_discharge_free_prompts import (
    NEO_POSTNATAL_DISCHARGE_FREE_SCHEMA,
    NEO_POSTNATAL_DISCHARGE_FREE_SYSTEM_PROMPT,
    NEO_POSTNATAL_DISCHARGE_FREE_USER_PROMPT,
)

# Context caching service for optimized API performance
from .gemini_cache_service import (
    get_or_create_cache,
    CACHE_KEY_NEO_DAILY,
    CACHE_KEY_NEO_PROFORMA,
    CACHE_KEY_NEO_OP,
    CACHE_KEY_OPHTHAL_DISCHARGE,
    CACHE_KEY_OPHTHALMOLOGY,
    CACHE_KEY_OPHTHAL_FULL,
    CACHE_KEY_OPHTHAL_POSTOP_RX,
    CACHE_KEY_OPHTHAL_PRESCRIPTION,
    get_template_cache_key,
)

# Ophthalmology Discharge imports
from .ophthal_discharge_prompt import (
    OPHTHAL_DISCHARGE_SYSTEM_PROMPT,
    OPHTHAL_DISCHARGE_USER_PROMPT,
)
from .ophthal_discharge_prompt_split import (
    OPHTHAL_DISCHARGE_PART1_SCHEMA,
    OPHTHAL_DISCHARGE_PART2_SCHEMA,
)
from .ophthal_discharge_formatter import format_ophthal_discharge_from_parts

# Ophthalmology Basic imports
from .ophthal_prompt import (
    OPHTHAL_SYSTEM_PROMPT,
    OPHTHAL_USER_PROMPT,
)
from .ophthal_prompt_split import (
    OPHTHAL_PART1_SCHEMA,
    OPHTHAL_PART2_SCHEMA,
)
from .ophthal_formatter import format_ophthalmology_from_parts

# Ophthalmology Full Consultation imports
from .ophthal_consult_prompt import (
    OPHTHAL_FULL_SYSTEM_PROMPT,
    OPHTHAL_FULL_USER_PROMPT,
)
from .ophthal_consult_prompt_split import (
    OPHTHAL_FULL_PART1_SCHEMA,
    OPHTHAL_FULL_PART2_SCHEMA,
)
from .ophthal_consult_formatter import format_ophthal_full_consult_from_parts

# Ophthalmology Post-Operative Prescription imports
from .ophthal_postop_rx_prompt import (
    OPHTHAL_POSTOP_RX_SYSTEM_PROMPT,
    OPHTHAL_POSTOP_RX_USER_PROMPT,
    OPHTHAL_POSTOP_RX_SCHEMA,
)

# Ophthalmology General Prescription imports
from .ophthal_prescription_prompt import (
    OPHTHAL_PRESCRIPTION_SYSTEM_PROMPT,
    OPHTHAL_PRESCRIPTION_USER_PROMPT,
    OPHTHAL_PRESCRIPTION_SCHEMA,
)

# Import for early split type detection and model lookup
from .supabase_service import get_patient_by_id, get_extraction_model_by_mode

# Load environment variables from .env file
load_dotenv()

# ============================================================================
# Split Extraction Types
# These consultation types use two-part extraction due to schema complexity
# Detection happens BEFORE artifact generation to avoid unnecessary computation
# ============================================================================
SPLIT_EXTRACTION_TYPES = {
    "OPHTHAL_CONSULT_BRIEF", "OPHTHA_DISCHARGE", "OPHTHAL_FULL_CONSULT",
    "NEO_OP", "NEO_PROFORMA", "NEO_DISCHARGE",
    "NEO_ADMISSION", "NEO_DAILY", "NEO_DAILY_FREE",
    # New free-text templates:
    "NEO_PROFORMA_FREE", "NEO_DISCHARGE_FREE",
    "NEO_POSTNATAL_DAY_FREE", "NEO_POSTNATAL_DISCHARGE_FREE",
}

# Neonatal consultation types that need patient data overrides
NEONATAL_OVERRIDE_TYPES = {
    "NEO_OP", "NEO_PROFORMA", "NEO_DISCHARGE",
    "NEO_ADMISSION", "NEO_DAILY", "NEO_DAILY_FREE",
    "NEO_PROFORMA_FREE", "NEO_DISCHARGE_FREE",
    "NEO_POSTNATAL_DAY_FREE", "NEO_POSTNATAL_DISCHARGE_FREE",
}


def _calculate_age_components(birth_date_str: str, reference_date=None) -> Dict[str, int]:
    """
    Calculate age components (years, months, days, weeks, weeksDays) from birth date.

    Args:
        birth_date_str: Date of birth in YYYY-MM-DD format
        reference_date: Reference date for calculation (default: today)

    Returns:
        Dict with years, months, days, weeks, weeksDays
    """
    from datetime import datetime, date
    from dateutil.relativedelta import relativedelta

    try:
        # Parse birth date
        if isinstance(birth_date_str, str):
            birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
        elif isinstance(birth_date_str, date):
            birth_date = birth_date_str
        else:
            return {}

        ref_date = reference_date or date.today()

        # Calculate using relativedelta for accurate year/month/day
        delta = relativedelta(ref_date, birth_date)

        # Also calculate total days for weeks calculation
        total_days = (ref_date - birth_date).days
        weeks = total_days // 7
        weeks_days = total_days % 7

        return {
            "years": delta.years,
            "months": delta.months,
            "days": delta.days,
            "weeks": weeks,
            "weeksDays": weeks_days
        }
    except Exception:
        return {}


def _calculate_corrected_age(birth_date_str: str, gestation_weeks: int, gestation_days: int = 0, reference_date=None) -> Dict[str, int]:
    """
    Calculate corrected age for premature babies.

    Corrected age = Chronological age - (40 weeks - gestational age at birth)

    Args:
        birth_date_str: Date of birth in YYYY-MM-DD format
        gestation_weeks: Gestational age at birth (weeks)
        gestation_days: Gestational age at birth (days)
        reference_date: Reference date for calculation (default: today)

    Returns:
        Dict with years, months, days, weeks, weeksDays for corrected age
    """
    from datetime import datetime, date, timedelta
    from dateutil.relativedelta import relativedelta

    try:
        # Parse birth date
        if isinstance(birth_date_str, str):
            birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
        elif isinstance(birth_date_str, date):
            birth_date = birth_date_str
        else:
            return {}

        ref_date = reference_date or date.today()

        # Calculate prematurity adjustment (40 weeks = full term)
        total_gestation_days = (gestation_weeks * 7) + gestation_days
        full_term_days = 40 * 7  # 280 days
        prematurity_days = full_term_days - total_gestation_days

        # Corrected birth date = actual birth date + prematurity adjustment
        corrected_birth_date = birth_date + timedelta(days=prematurity_days)

        # If corrected birth date is in the future, corrected age is 0
        if corrected_birth_date > ref_date:
            return {
                "years": 0,
                "months": 0,
                "days": 0,
                "weeks": 0,
                "weeksDays": 0
            }

        # Calculate corrected age
        delta = relativedelta(ref_date, corrected_birth_date)
        total_days = (ref_date - corrected_birth_date).days
        weeks = total_days // 7
        weeks_days = total_days % 7

        return {
            "years": delta.years,
            "months": delta.months,
            "days": delta.days,
            "weeks": weeks,
            "weeksDays": weeks_days
        }
    except Exception:
        return {}


def _calculate_eligibility_flags(birth_weight_grams: Optional[int], gestation_weeks: Optional[int]) -> Dict[str, bool]:
    """
    Calculate eligibility flags based on birth weight and gestation.

    Args:
        birth_weight_grams: Birth weight in grams
        gestation_weeks: Gestational age in weeks

    Returns:
        Dict with eligibility flags
    """
    result = {}

    if birth_weight_grams is not None or gestation_weeks is not None:
        # Lesser: Birth weight <1500g OR gestation <32 weeks
        is_lesser = False
        if birth_weight_grams is not None and birth_weight_grams < 1500:
            is_lesser = True
        if gestation_weeks is not None and gestation_weeks < 32:
            is_lesser = True
        result["birthWeightGestationIsLesser"] = is_lesser

        # Greater: Birth weight >1500g OR gestation >32 weeks
        is_greater = False
        if birth_weight_grams is not None and birth_weight_grams > 1500:
            is_greater = True
        if gestation_weeks is not None and gestation_weeks > 32:
            is_greater = True
        result["birthWeightGestationIsGreater"] = is_greater

    return result


def apply_neonatal_patient_overrides(
    extraction_data: Dict[str, Any],
    patient_id: Optional[str],
    consultation_type_code: str,
    recording_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Apply patient data overrides and auto-calculations to neonatal extraction results.

    For neonatal templates:
    1. Personal details (UHID, name, DOB, etc.) come from patient database
    2. Ages (chronological, corrected) are auto-calculated from DOB/gestation
    3. Eligibility flags are auto-calculated from birth weight/gestation
    4. Hospital name and consultation date are auto-filled

    Args:
        extraction_data: The formatted extraction result from Gemini
        patient_id: Patient UUID to look up in database
        consultation_type_code: The consultation type (e.g., NEONATAL_ADMISSION)

    Returns:
        Extraction data with patient fields overridden and ages calculated
    """
    import logging
    from datetime import datetime
    logger = logging.getLogger(__name__)

    # Only process neonatal types
    if consultation_type_code not in NEONATAL_OVERRIDE_TYPES:
        return extraction_data

    # Deep copy to avoid modifying original
    result = extraction_data.copy()

    # ========== AUTO-FILL: Consultation DateTime ==========
    current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")

    # For NEO_OP flattened structure
    if "opDateTime" in result and (not result["opDateTime"] or result["opDateTime"] == ""):
        result["opDateTime"] = current_datetime
        logger.debug(f"[NEONATAL_OVERRIDE] Auto-filled opDateTime: {current_datetime}")

    # For NEO_PROFORMA flat structure
    if "dateTime" in result and (not result["dateTime"] or result["dateTime"] == ""):
        result["dateTime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.debug(f"[NEONATAL_OVERRIDE] Auto-filled dateTime: {result['dateTime']}")

    # For NEO_DAILY_FREE flat structure
    if "entryDate" in result and (not result["entryDate"] or result["entryDate"] == ""):
        result["entryDate"] = datetime.now().strftime("%Y-%m-%d")
        logger.debug(f"[NEONATAL_OVERRIDE] Auto-filled entryDate: {result['entryDate']}")

    # For NEO_ADMISSION nested structure
    if "admission" in result and isinstance(result["admission"], dict):
        admission = result["admission"]
        if not admission.get("admissionDate") or admission.get("admissionDate") == "":
            admission["admissionDate"] = current_datetime
            result["admission"] = admission
            logger.debug(f"[NEONATAL_OVERRIDE] Auto-filled admission.admissionDate: {current_datetime}")

    # ========== AUTO-CALCULATE: APGAR Totals for NEO_PROFORMA ==========
    if "apgar" in result and isinstance(result["apgar"], dict):
        apgar = result["apgar"]
        apgar_modified = False
        for minute in ["minute1", "minute5", "minute10", "minute15", "minute20"]:
            if minute in apgar and isinstance(apgar[minute], dict):
                minute_data = apgar[minute]
                # Check if we have component scores but no total
                components = ["color", "heartRate", "reflex", "tone", "respiration"]
                component_values = [minute_data.get(c) for c in components]
                # Only calculate if all components are present and total is missing/null
                if all(v is not None for v in component_values) and minute_data.get("total") is None:
                    try:
                        total = sum(int(v) for v in component_values)
                        minute_data["total"] = total
                        apgar_modified = True
                        logger.debug(f"[NEONATAL_OVERRIDE] Auto-calculated APGAR {minute} total: {total}")
                    except (ValueError, TypeError):
                        pass  # Keep as-is if values can't be summed
        if apgar_modified:
            result["apgar"] = apgar

    # ========== AUTO-FILL: Hospital Name ==========
    # TODO: Get from hospital settings when available
    # For now, use a default or leave as extracted

    if not patient_id:
        logger.debug("[NEONATAL_OVERRIDE] No patient_id provided, skipping patient-specific overrides")
        return result

    try:
        import uuid
        patient_uuid = uuid.UUID(patient_id) if isinstance(patient_id, str) else patient_id
        patient = get_patient_by_id(patient_uuid)

        if not patient:
            logger.warning(f"[NEONATAL_OVERRIDE] Patient {truncate_id(patient_id)} not found")
            return result

        uhid = patient.get("patient_id")  # This is the UHID
        add_info = patient.get("add_info") or {}

        logger.debug(f"[NEONATAL_OVERRIDE] Applying overrides from patient {truncate_id(uhid)} (add_info_keys: {len(add_info) if add_info else 0})")

        # Extract key values for calculations
        birth_date = add_info.get("birthDate")
        gestation_str = add_info.get("gestation")
        birth_weight_str = add_info.get("birthWeight")

        # Parse gestation
        gestation_weeks = None
        gestation_days = 0
        if gestation_str and isinstance(gestation_str, str) and "+" in gestation_str:
            try:
                parts = gestation_str.split("+")
                gestation_weeks = int(parts[0].strip())
                gestation_days = int(parts[1].strip()) if len(parts) > 1 else 0
            except (ValueError, IndexError):
                pass

        # Parse birth weight (could be string like "2500" or "2.5 kg")
        birth_weight_grams = None
        if birth_weight_str:
            try:
                # Try to extract numeric value
                import re
                match = re.search(r'(\d+(?:\.\d+)?)', str(birth_weight_str))
                if match:
                    weight_val = float(match.group(1))
                    # If value is small, assume it's in kg
                    if weight_val < 10:
                        birth_weight_grams = int(weight_val * 1000)
                    else:
                        birth_weight_grams = int(weight_val)
            except (ValueError, TypeError):
                pass

        # ========== CALCULATE CHRONOLOGICAL AGE ==========
        # Note: Corrected age is NOT auto-calculated - it's extracted from the recording
        chronological_age = {}

        if birth_date:
            chronological_age = _calculate_age_components(birth_date)
            logger.debug(f"[NEONATAL_OVERRIDE] Calculated chronological age: {bool(chronological_age)}")

        # ========== CALCULATE ELIGIBILITY FLAGS ==========
        eligibility_flags = _calculate_eligibility_flags(birth_weight_grams, gestation_weeks)
        if eligibility_flags:
            logger.debug(f"[NEONATAL_OVERRIDE] Calculated eligibility flags: {len(eligibility_flags)} flags")

        # ========== APPLY TO NEO_PROFORMA FLAT STRUCTURE ==========
        # NEO_PROFORMA uses flat fields: babyName, dob, sex, gestationWeeks, gestationDays (no prefix)
        is_proforma = "babyName" in result or "gestationWeeks" in result

        if is_proforma:
            # Override basic fields
            if uhid:
                result["uhid"] = uhid
            if add_info.get("babyName"):
                result["babyName"] = add_info["babyName"]
            if birth_date:
                result["dob"] = birth_date
            if add_info.get("gender"):
                result["sex"] = add_info["gender"]
            if gestation_weeks is not None:
                result["gestationWeeks"] = str(gestation_weeks)
                result["gestationDays"] = str(gestation_days)
            if add_info.get("visitNumber"):
                # For NEO_PROFORMA, visitNumber might not be in schema but good to track
                pass  # Skip if not in schema
            logger.debug(f"[NEONATAL_OVERRIDE] Applied NEO_PROFORMA overrides: uhid={truncate_id(uhid)}, babyName=[REDACTED]")

        # ========== APPLY TO NEO_OP FLATTENED STRUCTURE ==========
        # Check if this is a flattened NEO_OP structure (uses baby_ prefix)
        elif "baby_name" in result or "baby_dob" in result:
            # Override basic fields
            if uhid:
                result["uhid"] = uhid
            if add_info.get("babyName"):
                result["baby_name"] = add_info["babyName"]
            if birth_date:
                result["baby_dob"] = birth_date
            if add_info.get("gender"):
                result["baby_sex"] = add_info["gender"]
            if gestation_weeks is not None:
                result["baby_gestation_weeks"] = gestation_weeks
                result["baby_gestation_days"] = gestation_days

            # Apply chronological age
            if chronological_age:
                result["baby_chronologicalAge_years"] = chronological_age.get("years")
                result["baby_chronologicalAge_months"] = chronological_age.get("months")
                result["baby_chronologicalAge_days"] = chronological_age.get("days")
                result["baby_chronologicalAge_weeks"] = chronological_age.get("weeks")
                result["baby_chronologicalAge_weeksDays"] = chronological_age.get("weeksDays")

            # Note: Corrected age is extracted from recording, NOT auto-calculated

            # Apply eligibility flags
            if eligibility_flags:
                result["eligibility_birthWeightGestationIsLesser"] = eligibility_flags.get("birthWeightGestationIsLesser", False)
                result["eligibility_birthWeightGestationIsGreater"] = eligibility_flags.get("birthWeightGestationIsGreater", False)

        # ========== APPLY TO NESTED STRUCTURE (other neonatal types) ==========
        else:
            # ========== BABY SECTION ==========
            if "baby" in result and isinstance(result["baby"], dict):
                baby = result["baby"].copy()

                # Override UHID (both in baby object AND at root level)
                if uhid:
                    baby["uhid"] = uhid
                    result["uhid"] = uhid  # Set root-level uhid here to ensure both are populated

                # Override name from add_info
                if add_info.get("babyName"):
                    baby["name"] = add_info["babyName"]

                # Override DOB from add_info
                if birth_date:
                    baby["dob"] = birth_date

                # Override sex/gender from add_info
                if add_info.get("gender"):
                    baby["sex"] = add_info["gender"]

                # Override gestation
                if gestation_weeks is not None:
                    baby["gestation"] = {"weeks": gestation_weeks, "days": gestation_days}

                # Apply chronological age
                if chronological_age:
                    baby["chronologicalAge"] = chronological_age

                # Note: Corrected age is extracted from recording, NOT auto-calculated

                result["baby"] = baby

            # ========== ELIGIBILITY SECTION ==========
            if "eligibility" in result and isinstance(result["eligibility"], dict) and eligibility_flags:
                eligibility = result["eligibility"].copy()
                eligibility.update(eligibility_flags)
                result["eligibility"] = eligibility

            # ========== ADMISSION SECTION ==========
            if "admission" in result and isinstance(result["admission"], dict):
                admission = result["admission"].copy()

                # Override visit number
                if add_info.get("visitNumber"):
                    admission["visitNumber"] = add_info["visitNumber"]

                # Room/bed come strictly from recording_metadata (passed at /start by iframe)
                if recording_metadata is not None:
                    if recording_metadata.get("roomId") is not None:
                        admission["roomId"] = recording_metadata["roomId"]
                    if recording_metadata.get("bedId") is not None:
                        admission["bedId"] = recording_metadata["bedId"]

                result["admission"] = admission

            # ========== TOP-LEVEL FIELDS (for NEO_DAILY, NEO_DISCHARGE, etc.) ==========
            # Always set uhid if available - don't require it to already exist in result
            # (filter_na_values may have removed empty uhid from formatter output)
            if uhid:
                result["uhid"] = uhid

            if add_info.get("visitNumber") and "visitNumber" in result:
                result["visitNumber"] = add_info["visitNumber"]

            # Root-level room/bed come strictly from recording_metadata
            if recording_metadata is not None:
                if recording_metadata.get("roomId") is not None and "roomId" in result:
                    result["roomId"] = recording_metadata["roomId"]
                if recording_metadata.get("bedId") is not None and "bedId" in result:
                    result["bedId"] = recording_metadata["bedId"]

        logger.debug(f"[NEONATAL_OVERRIDE] Successfully applied patient overrides and auto-calculations")
        return result

    except Exception as e:
        logger.error(f"[NEONATAL_OVERRIDE] Error applying overrides: {type(e).__name__}", exc_info=True)
        # Return original data on error - don't fail extraction
        return extraction_data


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Debug logging for Google SDK - track API calls and retries
logging.getLogger("google.api_core.retry").setLevel(logging.DEBUG)  # Log retries
logging.getLogger("httpx").setLevel(logging.DEBUG)  # Log all HTTP requests (shows each Gemini API call)
logging.getLogger("google_genai").setLevel(logging.DEBUG)  # Log google-genai SDK internals

# Initialize Gemini client using factory (supports both Gemini API and Vertex AI)
from services.gemini_client_factory import get_gemini_client

client = get_gemini_client()


# ============================================================================
# JSON Cleaning Helper
# ============================================================================

def clean_and_parse_json(response_text: str, context: str = "response") -> Dict[str, Any]:
    """
    Robustly clean and parse JSON from Gemini API responses.

    Handles common formatting issues:
    - Leading/trailing whitespace and newlines
    - Markdown code blocks (```json ... ```)
    - Missing opening/closing braces
    - Extra whitespace before first character

    Args:
        response_text: Raw text from Gemini API
        context: Description for logging (e.g., "Part 1", "Part 2", "main response")

    Returns:
        Parsed JSON as dictionary

    Raises:
        json.JSONDecodeError: If JSON cannot be parsed after cleaning
    """
    import time
    parse_start = time.time()

    # Step 1: Strip whitespace
    cleaned = response_text.strip()

    # Step 2: Remove markdown code blocks
    if cleaned.startswith('```json'):
        cleaned = cleaned[7:].strip()
    elif cleaned.startswith('```'):
        cleaned = cleaned[3:].strip()

    if cleaned.endswith('```'):
        cleaned = cleaned[:-3].strip()

    # Step 3: Handle missing opening brace (common Gemini issue)
    # If JSON starts with a quote (like '\n "patientDemographics"'), add opening brace
    if cleaned and not cleaned.startswith('{') and cleaned.startswith('"'):
        logger.warning(f"[JSON_CLEAN] {context} missing opening brace - adding {{")
        cleaned = '{' + cleaned

    # Step 4: Handle missing closing brace
    if cleaned and not cleaned.endswith('}') and '{' in cleaned:
        logger.warning(f"[JSON_CLEAN] {context} missing closing brace - adding }}")
        cleaned = cleaned + '}'

    # Step 5: Parse JSON
    try:
        result = json.loads(cleaned)
        parse_duration = time.time() - parse_start
        logger.info(f"[TIMING_JSON] {context} parsed: {parse_duration:.3f}s ({len(response_text)} chars)")
        return result
    except json.JSONDecodeError:
        parse_duration = time.time() - parse_start
        logger.error(f"[TIMING_JSON] {context} FAILED: {parse_duration:.3f}s")
        logger.error(f"[JSON_CLEAN] {context} parsing failed after cleaning")
        logger.error(f"[JSON_CLEAN] Original length: {len(response_text)}")
        logger.error(f"[JSON_CLEAN] Cleaned length: {len(cleaned)}")
        logger.error(f"[JSON_CLEAN] First 200 chars of cleaned: {cleaned[:200]}")
        logger.error(f"[JSON_CLEAN] Last 200 chars of cleaned: {cleaned[-200:]}")
        raise


async def extract_neo_daily_parameters(
    transcript: str,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract neo natal daily parameters using NEO DAILY prompt with system instructions and Gemini 2.5 Pro.

    Uses split prompt architecture:
    - System instruction: Guidelines and extraction rules (reduced latency)
    - User prompt: Task, transcript, and JSON schema

    Args:
        transcript: Clinical note transcript (transcribed medical dictation)
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)

    Returns:
        Extracted respiratory parameters as JSON

    Raises:
        Exception: If extraction fails
    """
    import time
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting neo natal daily parameters (NEO DAILY prompt with system instructions)')

    try:
        # Format user prompt with transcript
        user_prompt = NEO_DAILY_PROMPT_USER.format(transcript=transcript)

        logger.debug("[GeminiService] Starting Gemini API call...")
        api_start_time = time.time()

        # Try to get or create cache for system prompt
        model = get_extraction_model_by_mode('default')  # Use model from processing_modes table
        cache_name = get_or_create_cache(
            prompt_type=CACHE_KEY_NEO_DAILY,
            system_instruction=NEO_DAILY_PROMPT_SYSTEM,
            model=model,
            ttl_seconds=3600  # 1 hour
        )

        try:
            # Add timeout wrapper
            import asyncio

            # Build config with or without cache
            if cache_name:
                logger.debug("[GeminiService] Using cached system prompt for NEO_DAILY")
                config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=NEO_DAILY_PARAMETERS_SCHEMA,
                    temperature=0.0,  # Zero temp for strict extraction
                )
            else:
                logger.debug("[GeminiService] Fallback: Using non-cached system prompt")
                config = types.GenerateContentConfig(
                    system_instruction=NEO_DAILY_PROMPT_SYSTEM,
                    response_mime_type="application/json",
                    response_schema=NEO_DAILY_PARAMETERS_SCHEMA,
                    temperature=0.0,  # Zero temp for strict extraction
                )

            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model,
                    contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                    config=config
                ),
                timeout=120.0  # 2 minute timeout
            )
            api_end_time = time.time()
            api_duration = api_end_time - api_start_time
            logger.info(f"[TIMING_GEMINI_API] Gemini API call: {api_duration:.2f}s")

            # Log usage to database (fire-and-forget)
            usage_data = log_extraction_usage(
                response=response,
                model=model,
                api_duration_seconds=api_duration,
                call_subtype="neo_daily",
                consultation_type_code="NEONATAL_DAILY",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(NEO_DAILY_PROMPT_SYSTEM) // 4,  # Rough estimate
                user_prompt_tokens=len(user_prompt) // 4,  # Rough estimate
            )
            await log_llm_usage(usage_data)

        except asyncio.TimeoutError:
            logger.error("[GeminiService] Gemini API call timed out after 120 seconds")
            # Log timeout error
            error_usage = create_error_usage(
                call_type="extraction",
                model=model,
                api_duration_seconds=120.0,
                error_message="Timeout after 120s",
                call_subtype="neo_daily",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(error_usage)
            raise Exception("AI service call timed out after 120 seconds")
        except Exception as e:
            api_end_time = time.time()
            api_duration = api_end_time - api_start_time
            logger.error(f"[GeminiService] Gemini API call failed after {api_duration:.2f}s: {type(e).__name__}: {str(e)}")
            raise Exception(_sanitize_error_message(str(e)))

        logger.debug("[GeminiService] Extracting response text...")
        json_text = response.text
        if not json_text:
            raise Exception('No text response received from model')
        logger.debug(f"[GeminiService] Response text received (length: {len(json_text)} chars)")

        # Clean JSON response
        logger.debug("[GeminiService] Cleaning JSON response...")
        cleaned_json_text = json_text.strip()
        if cleaned_json_text.startswith('```json'):
            cleaned_json_text = cleaned_json_text[7:].strip()
        if cleaned_json_text.endswith('```'):
            cleaned_json_text = cleaned_json_text[:-3].strip()

        logger.debug("[GeminiService] Parsing JSON...")
        result = json.loads(cleaned_json_text)
        logger.debug('[GeminiService] Respiratory parameter extraction successful.')

        # 🔍 DETAILED LOGGING: Log NEO_DAILY extraction results
        logger.debug("[GEMINI_NEO_DAILY] ========== NEO_DAILY EXTRACTION RESULT ==========")
        logger.debug(f"[GEMINI_NEO_DAILY] Result Type: {type(result).__name__}")
        logger.debug(f"[GEMINI_NEO_DAILY] Total Fields Extracted: {len(result) if isinstance(result, dict) else 'N/A'}")
        if isinstance(result, dict):
            logger.debug(f"[GEMINI_NEO_DAILY] Field Names: {list(result.keys())}")

            # Check critical fields
            critical_fields = ["uhid", "invasiveVentilation", "respiratoryIndication", "respiratoryRate", "spo2"]
            present = [f for f in critical_fields if f in result]
            missing = [f for f in critical_fields if f not in result]
            logger.debug(f"[GEMINI_NEO_DAILY] Critical Fields Present: {present}")
            if missing:
                logger.warning(f"[GEMINI_NEO_DAILY] Critical Fields Missing: {missing}")

            # Sample values (first 5 fields, type only for privacy)
            sample = {k: type(v).__name__ for k, v in list(result.items())[:5]}
            logger.debug(f"[GEMINI_NEO_DAILY] Sample Field Types: {sample}")
        logger.debug("[GEMINI_NEO_DAILY] ===============================================")

        return result

    except Exception as e:
        logger.error(f"Error extracting respiratory parameters: {e}")
        return {
            "error": "Failed to parse respiratory parameters. The model may have returned an invalid format or the request failed."
        }

async def extract_neo_proforma_parameters_split(
    transcript: str,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    medicine_list_text: str = "",
    investigation_list_text: str = "",
) -> Dict[str, Any]:
    """
    Extract neonatal admission/birth proforma using TWO-PART extraction to avoid schema complexity limits.

    Even the flattened schema (185 properties) exceeds Gemini's constraint limits.
    This function splits the extraction into TWO separate API calls:

    PART 1 (82 fields): BABY VITALS & IMMEDIATE CARE
    - Baby demographics, APGAR scores, birth vitals
    - Resuscitation details, delivery room procedures
    - Medical problems, initial examination

    PART 2 (103 fields): MATERNAL HISTORY & PREGNANCY
    - Maternal demographics, previous births
    - Pregnancy complications, antenatal scans
    - Labour and delivery details, maternal health

    Both results are merged and reconstructed into the final nested structure.

    Args:
        transcript: Clinical note transcript (birth/admission documentation, transcribed medical dictation)
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)

    Returns:
        Extracted neonatal proforma data as JSON with 100+ fields (same output as single-call version)

    Raises:
        Exception: If extraction fails
    """
    import time
    import asyncio
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting neonatal proforma using TWO-PART approach (Part 1: Baby + Part 2: Maternal)')

    try:
        # Use the SAME comprehensive prompt for both API calls
        # The response_schema parameter will constrain which fields get extracted
        # Build medicine list section for injection (proforma has maternalAntibioticsArray)
        medicine_list_section = ""
        if medicine_list_text:
            medicine_list_section = (
                "\n\n**MEDICINE MATCHING (CRITICAL):**\n"
                "When extracting maternal antibiotics, match drug names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for pronunciation variations and abbreviations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{medicine_list_text}"
            )
        investigation_list_section = ""
        if investigation_list_text:
            investigation_list_section = (
                "\n\n**INVESTIGATION MATCHING (CRITICAL):**\n"
                "When extracting investigations, match names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for abbreviations and spoken variations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{investigation_list_text}"
            )
        user_prompt = NEO_PROFORMA_PROMPT_USER.format(
            transcript=transcript,
            medicine_list_section=medicine_list_section,
            investigation_list_section=investigation_list_section
        )
        system_prompt = NEO_PROFORMA_PROMPT_SYSTEM
        model = get_extraction_model_by_mode('default')  # Use model from processing_modes table

        # Check provider for routing
        from services.llm_client_factory import get_provider, generate_structured_output_parallel
        from services.schema_adapter import gemini_schema_to_json_schema
        provider = get_provider(model)

        if provider != "gemini":
            # === NON-GEMINI PATH (Claude/OpenAI) ===
            logger.debug(f"[LLM_ROUTING] Using {provider} provider with model: {model}")
            parallel_start_time = time.time()

            # Convert Gemini schemas to JSON Schema
            part1_json = gemini_schema_to_json_schema(NEO_PROFORMA_PART1_SCHEMA)
            part2_json = gemini_schema_to_json_schema(NEO_PROFORMA_PART2_SCHEMA)

            # Run parallel extraction via LLM factory
            part1_resp, part2_resp = await generate_structured_output_parallel(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema_part1=part1_json,
                json_schema_part2=part2_json,
                model=model,
                temperature=0.0,
            )

            parallel_duration = time.time() - parallel_start_time
            logger.info(f"[TIMING_LLM_API] ✅ PARALLEL extraction ({provider}): {parallel_duration:.2f}s (both parts)")

            # Data is already parsed in LLMResponse.data
            part1_data = part1_resp.data
            part2_data = part2_resp.data
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields, Part 2 extracted {len(part2_data)} fields")

            # Log usage for both parts using raw_response
            usage_data_p1 = log_extraction_usage(
                response=part1_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration,
                call_subtype="neo_proforma_part1",
                consultation_type_code="NEONATAL_PROFORMA",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p1)

            usage_data_p2 = log_extraction_usage(
                response=part2_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration,
                call_subtype="neo_proforma_part2",
                consultation_type_code="NEONATAL_PROFORMA",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p2)

        else:
            # === GEMINI PATH (existing code) ===
            # Get or create cache for system prompt (used by BOTH Part 1 and Part 2)
            cache_name = get_or_create_cache(
                prompt_type=CACHE_KEY_NEO_PROFORMA,
                system_instruction=system_prompt,
                model=model,
                ttl_seconds=3600  # 1 hour
            )

            logger.debug(
                f"[GeminiService] Using comprehensive NEO_PROFORMA prompt for both parts. "
                f"Schema constraints will guide field extraction. "
                f"Cache: {'enabled' if cache_name else 'disabled'}"
            )

            # Build configs for both parts
            if cache_name:
                part1_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=NEO_PROFORMA_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=NEO_PROFORMA_PART2_SCHEMA,
                    temperature=0.0,
                )
            else:
                part1_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=NEO_PROFORMA_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=NEO_PROFORMA_PART2_SCHEMA,
                    temperature=0.0,
                )

            # ========== RUN BOTH PARTS IN PARALLEL ==========
            logger.debug("[GeminiService] Starting PARALLEL extraction: Part 1 (82 fields) + Part 2 (103 fields)...")
            parallel_start_time = time.time()

            async def extract_part1():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part1_config
                    ),
                    timeout=120.0
                )

            async def extract_part2():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part2_config
                    ),
                    timeout=120.0
                )

            try:
                # Run both extractions concurrently
                part1_response, part2_response = await asyncio.gather(
                    extract_part1(),
                    extract_part2()
                )
                parallel_end_time = time.time()
                parallel_duration = parallel_end_time - parallel_start_time
                logger.info(f"[TIMING_GEMINI_API] ✅ PARALLEL extraction: {parallel_duration:.2f}s (both parts)")

                # Log usage for both parts
                usage_data_p1 = log_extraction_usage(
                    response=part1_response,
                    model=model,
                    api_duration_seconds=parallel_duration,
                    call_subtype="neo_proforma_part1",
                    consultation_type_code="NEONATAL_PROFORMA",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p1)

                usage_data_p2 = log_extraction_usage(
                    response=part2_response,
                    model=model,
                    api_duration_seconds=parallel_duration,
                    call_subtype="neo_proforma_part2",
                    consultation_type_code="NEONATAL_PROFORMA",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p2)

            except asyncio.TimeoutError:
                logger.error("[GeminiService] Parallel extraction timed out after 120 seconds")
                error_usage = create_error_usage(
                    call_type="extraction", model=model, api_duration_seconds=120.0,
                    error_message="Timeout after 120s", call_subtype="neo_proforma_parallel",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                )
                await log_llm_usage(error_usage)
                raise Exception("Parallel extraction timed out")
            except Exception as e:
                logger.error(f"[GeminiService] Parallel extraction failed: {type(e).__name__}: {str(e)}")
                raise Exception(_sanitize_error_message(str(e)))

            # Parse both responses with robust cleaning
            logger.debug("[GeminiService] Parsing Part 1 response...")
            part1_data = clean_and_parse_json(part1_response.text, context="NEO_PROFORMA Part 1")
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields")

            logger.debug("[GeminiService] Parsing Part 2 response...")
            part2_data = clean_and_parse_json(part2_response.text, context="NEO_PROFORMA Part 2")
            logger.debug(f"[GeminiService] Part 2 extracted {len(part2_data)} fields")

        # Merge and reconstruct nested structure
        logger.debug("[GeminiService] Merging Part 1 and Part 2 results...")
        formatted_result = format_neo_proforma_from_parts(part1_data, part2_data)
        logger.debug("[GeminiService] Two-part extraction successful!")

        # Filter out N/A values
        filtered_result = filter_na_values(formatted_result)
        logger.debug("[GeminiService] Filtered N/A values from formatted result")

        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting neonatal proforma (two-part): {e}")
        return {
            "error": f"Failed to parse neonatal proforma using two-part extraction: {_sanitize_error_message(str(e))}"
        }


async def extract_neo_op_parameters_split(
    transcript: str,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    medicine_list_text: str = "",
    investigation_list_text: str = "",
) -> Dict[str, Any]:
    """
    Extract neonatal outpatient follow-up parameters using TWO-PART extraction.

    The NEO_OP schema (~125 properties when flattened) exceeds Gemini's constraint limits.
    This function splits the extraction into TWO separate API calls:

    PART 1 (~65 fields): BABY, ELIGIBILITY & MEDICAL HISTORY
    - Patient identification (uhid, opDateTime, hospitalName)
    - Baby details including ages
    - Eligibility criteria
    - Medical history

    PART 2 (~60 fields): FAMILY, FOLLOW-UP & PRESCRIPTIONS
    - Mother details
    - Partner details
    - Follow-up details
    - Medications array
    - Immunization details

    Both results are merged and reconstructed into the final nested structure.

    Args:
        transcript: Clinical note transcript (outpatient follow-up dictation)
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)

    Returns:
        Extracted outpatient parameters as nested JSON

    Raises:
        Exception: If extraction fails
    """
    import time
    import uuid as uuid_module
    import asyncio

    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    try:
        # Use the SAME comprehensive prompt for both API calls
        # The response_schema parameter will constrain which fields get extracted
        # Build medicine list section for injection (NEO_OP has medication_drugIds)
        medicine_list_section = ""
        if medicine_list_text:
            medicine_list_section = (
                "\n\n**MEDICINE MATCHING (CRITICAL):**\n"
                "When extracting medications, match drug names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for pronunciation variations and abbreviations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{medicine_list_text}"
            )
        investigation_list_section = ""
        if investigation_list_text:
            investigation_list_section = (
                "\n\n**INVESTIGATION MATCHING (CRITICAL):**\n"
                "When extracting investigations, match names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for abbreviations and spoken variations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{investigation_list_text}"
            )
        user_prompt = NEO_OP_PROMPT_USER.format(
            transcript=transcript,
            medicine_list_section=medicine_list_section,
            investigation_list_section=investigation_list_section
        )
        system_prompt = NEO_OP_PROMPT_SYSTEM
        model = get_extraction_model_by_mode('default')  # Use model from processing_modes table

        # Check provider for routing
        from services.llm_client_factory import get_provider, generate_structured_output_parallel
        from services.schema_adapter import gemini_schema_to_json_schema
        provider = get_provider(model)

        if provider != "gemini":
            # === NON-GEMINI PATH (Claude/OpenAI) ===
            logger.debug(f"[LLM_ROUTING] Using {provider} provider with model: {model}")
            parallel_start_time = time.time()

            # Convert Gemini schemas to JSON Schema
            part1_json = gemini_schema_to_json_schema(NEO_OP_PART1_SCHEMA)
            part2_json = gemini_schema_to_json_schema(NEO_OP_PART2_SCHEMA)

            # Run parallel extraction via LLM factory
            part1_resp, part2_resp = await generate_structured_output_parallel(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema_part1=part1_json,
                json_schema_part2=part2_json,
                model=model,
                temperature=0.0,
            )

            parallel_duration = time.time() - parallel_start_time
            logger.info(f"[TIMING_LLM_API] ✅ PARALLEL extraction ({provider}): {parallel_duration:.2f}s (both parts)")

            # Data is already parsed in LLMResponse.data
            part1_data = part1_resp.data
            part2_data = part2_resp.data
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields, Part 2 extracted {len(part2_data)} fields")

            # Log usage for both parts using raw_response
            usage_data_p1 = log_extraction_usage(
                response=part1_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration,
                call_subtype="neo_op_part1",
                consultation_type_code="NEO_OP",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p1)

            usage_data_p2 = log_extraction_usage(
                response=part2_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration,
                call_subtype="neo_op_part2",
                consultation_type_code="NEO_OP",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p2)

        else:
            # === GEMINI PATH (existing code) ===
            # Get or create cache for system prompt (used by BOTH Part 1 and Part 2)
            cache_name = get_or_create_cache(
                prompt_type=CACHE_KEY_NEO_OP,
                system_instruction=system_prompt,
                model=model,
                ttl_seconds=3600  # 1 hour
            )

            logger.debug(
                f"[GeminiService] Using comprehensive NEO_OP prompt for both parts. "
                f"Schema constraints will guide field extraction. "
                f"Cache: {'enabled' if cache_name else 'disabled'}"
            )

            # Build Part 1 config with or without cache
            if cache_name:
                part1_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=NEO_OP_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=NEO_OP_PART2_SCHEMA,
                    temperature=0.0,
                )
            else:
                part1_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=NEO_OP_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=NEO_OP_PART2_SCHEMA,
                    temperature=0.0,
                )

            # ========== RUN BOTH PARTS IN PARALLEL ==========
            logger.debug("[GeminiService] Starting PARALLEL extraction: Part 1 (~65 fields) + Part 2 (~60 fields)...")
            parallel_start_time = time.time()

            async def extract_part1():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part1_config
                    ),
                    timeout=120.0
                )

            async def extract_part2():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part2_config
                    ),
                    timeout=120.0
                )

            try:
                # Run both extractions concurrently
                part1_response, part2_response = await asyncio.gather(
                    extract_part1(),
                    extract_part2()
                )
                parallel_end_time = time.time()
                parallel_duration = parallel_end_time - parallel_start_time
                logger.info(f"[TIMING_GEMINI_API] ✅ PARALLEL extraction: {parallel_duration:.2f}s (both parts)")

                # Log usage for both parts
                usage_data_p1 = log_extraction_usage(
                    response=part1_response,
                    model=model,
                    api_duration_seconds=parallel_duration,
                    call_subtype="neo_op_part1",
                    consultation_type_code="NEO_OP",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p1)

                usage_data_p2 = log_extraction_usage(
                    response=part2_response,
                    model=model,
                    api_duration_seconds=parallel_duration,
                    call_subtype="neo_op_part2",
                    consultation_type_code="NEO_OP",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p2)

            except asyncio.TimeoutError:
                logger.error("[GeminiService] Parallel extraction timed out after 120 seconds")
                error_usage = create_error_usage(
                    call_type="extraction", model=model, api_duration_seconds=120.0,
                    error_message="Timeout after 120s", call_subtype="neo_op_parallel",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                )
                await log_llm_usage(error_usage)
                raise Exception("Parallel extraction timed out")

            # Parse both responses with robust cleaning
            logger.debug("[GeminiService] Parsing Part 1 response...")
            part1_data = clean_and_parse_json(part1_response.text, context="NEO_OP Part 1")
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields")

            logger.debug("[GeminiService] Parsing Part 2 response...")
            part2_data = clean_and_parse_json(part2_response.text, context="NEO_OP Part 2")
            logger.debug(f"[GeminiService] Part 2 extracted {len(part2_data)} fields")

        # Merge and reconstruct nested structure
        logger.debug("[GeminiService] Merging Part 1 and Part 2 results...")
        formatted_result = format_neo_op_from_parts(part1_data, part2_data)
        logger.debug("[GeminiService] Two-part extraction successful!")

        # Filter out N/A values
        filtered_result = filter_na_values(formatted_result)
        logger.debug("[GeminiService] Filtered N/A values from formatted result")

        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting NEO_OP (two-part): {e}")
        return {
            "error": f"Failed to parse NEO_OP using two-part extraction: {_sanitize_error_message(str(e))}"
        }


async def extract_neo_discharge_parameters_split(
    transcript: str,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    medicine_list_text: str = "",
    investigation_list_text: str = "",
) -> Dict[str, Any]:
    """
    Extract neonatal discharge summary using TWO-PART extraction to avoid schema complexity limits.

    PART 1 (~45 fields): CORE DISCHARGE INFO
    - Patient identification (uhid, visitNumber, room/bed)
    - Discharge basics (status, date, weight, measurements)
    - Immunization details
    - Physical exam findings
    - Next appointment
    - Medications array

    PART 2 (~40 fields): CHECKLIST & SCREENINGS
    - Blood test results
    - Cranial ultrasound & echocardiography
    - Hearing screening (OAE, ABR)
    - ROP screening & treatment
    - Procedures, infections, advice

    Both results are merged and reconstructed into the final nested structure.

    Args:
        transcript: Clinical discharge summary transcript
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)
        medicine_list_text: Formatted medicine list for prompt injection (optional)

    Returns:
        Extracted neonatal discharge data as JSON with nested structure

    Raises:
        Exception: If extraction fails
    """
    import time
    import asyncio
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting neonatal discharge using TWO-PART approach')

    try:
        # Build medicine list section for injection (discharge has medications arrays)
        medicine_list_section = ""
        if medicine_list_text:
            medicine_list_section = (
                "\n\n**MEDICINE MATCHING (CRITICAL):**\n"
                "When extracting medications, match drug names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for pronunciation variations and abbreviations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{medicine_list_text}"
            )
        investigation_list_section = ""
        if investigation_list_text:
            investigation_list_section = (
                "\n\n**INVESTIGATION MATCHING (CRITICAL):**\n"
                "When extracting investigations, match names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for abbreviations and spoken variations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{investigation_list_text}"
            )
        user_prompt = NEO_DISCHARGE_USER_PROMPT.format(
            transcript=transcript,
            medicine_list_section=medicine_list_section,
            investigation_list_section=investigation_list_section
        )
        system_prompt = NEO_DISCHARGE_SYSTEM_PROMPT
        model = get_extraction_model_by_mode('default')  # Use model from processing_modes table

        # Check provider for routing
        from services.llm_client_factory import get_provider, generate_structured_output_parallel
        from services.schema_adapter import gemini_schema_to_json_schema
        provider = get_provider(model)

        if provider != "gemini":
            # === NON-GEMINI PATH (Claude/OpenAI) ===
            logger.debug(f"[LLM_ROUTING] Using {provider} provider with model: {model}")
            parallel_start_time = time.time()

            # Convert Gemini schemas to JSON Schema
            part1_json = gemini_schema_to_json_schema(NEO_DISCHARGE_PART1_SCHEMA)
            part2_json = gemini_schema_to_json_schema(NEO_DISCHARGE_PART2_SCHEMA)

            # Run parallel extraction via LLM factory
            part1_resp, part2_resp = await generate_structured_output_parallel(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema_part1=part1_json,
                json_schema_part2=part2_json,
                model=model,
                temperature=0.0,
            )

            parallel_duration = time.time() - parallel_start_time
            logger.info(f"[TIMING_LLM_API] ✅ PARALLEL extraction ({provider}): {parallel_duration:.2f}s (both parts)")

            # Data is already parsed in LLMResponse.data
            part1_data = part1_resp.data
            part2_data = part2_resp.data
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields, Part 2 extracted {len(part2_data)} fields")

            # Log usage for both parts using raw_response
            usage_data_p1 = log_extraction_usage(
                response=part1_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration,
                call_subtype="neo_discharge_part1",
                consultation_type_code="NEONATAL_DISCHARGE",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p1)

            usage_data_p2 = log_extraction_usage(
                response=part2_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration,
                call_subtype="neo_discharge_part2",
                consultation_type_code="NEONATAL_DISCHARGE",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p2)

        else:
            # === GEMINI PATH (existing code) ===
            # Get or create cache for system prompt
            cache_name = get_or_create_cache(
                prompt_type="NEO_DISCHARGE",
                system_instruction=system_prompt,
                model=model,
                ttl_seconds=3600
            )

            logger.debug(f"[GeminiService] Cache: {'enabled' if cache_name else 'disabled'}")

            # Build configs for both parts
            if cache_name:
                part1_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=NEO_DISCHARGE_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=NEO_DISCHARGE_PART2_SCHEMA,
                    temperature=0.0,
                )
            else:
                part1_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=NEO_DISCHARGE_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=NEO_DISCHARGE_PART2_SCHEMA,
                    temperature=0.0,
                )

            # ========== RUN BOTH PARTS IN PARALLEL ==========
            logger.debug("[GeminiService] Starting PARALLEL extraction: Part 1 (~45 fields) + Part 2 (~40 fields)...")
            parallel_start_time = time.time()

            async def extract_part1():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part1_config
                    ),
                    timeout=120.0
                )

            async def extract_part2():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part2_config
                    ),
                    timeout=120.0
                )

            try:
                part1_response, part2_response = await asyncio.gather(
                    extract_part1(),
                    extract_part2()
                )
                parallel_end_time = time.time()
                parallel_duration = parallel_end_time - parallel_start_time
                logger.info(f"[TIMING_GEMINI_API] ✅ PARALLEL extraction: {parallel_duration:.2f}s (both parts)")

                # Log usage for both parts
                usage_data_p1 = log_extraction_usage(
                    response=part1_response,
                    model=model,
                    api_duration_seconds=parallel_duration,
                    call_subtype="neo_discharge_part1",
                    consultation_type_code="NEONATAL_DISCHARGE",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p1)

                usage_data_p2 = log_extraction_usage(
                    response=part2_response,
                    model=model,
                    api_duration_seconds=parallel_duration,
                    call_subtype="neo_discharge_part2",
                    consultation_type_code="NEONATAL_DISCHARGE",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p2)

            except asyncio.TimeoutError:
                logger.error("[GeminiService] Parallel extraction timed out after 120 seconds")
                error_usage = create_error_usage(
                    call_type="extraction", model=model, api_duration_seconds=120.0,
                    error_message="Timeout after 120s", call_subtype="neo_discharge_parallel",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                )
                await log_llm_usage(error_usage)
                raise Exception("Parallel extraction timed out")

            # Parse both responses
            logger.debug("[GeminiService] Parsing Part 1 response...")
            part1_data = clean_and_parse_json(part1_response.text, context="NEO_DISCHARGE Part 1")
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields")

            logger.debug("[GeminiService] Parsing Part 2 response...")
            part2_data = clean_and_parse_json(part2_response.text, context="NEO_DISCHARGE Part 2")
            logger.debug(f"[GeminiService] Part 2 extracted {len(part2_data)} fields")

        # Merge and reconstruct nested structure
        logger.debug("[GeminiService] Merging Part 1 and Part 2 results...")
        formatted_result = format_neo_discharge_from_parts(part1_data, part2_data)
        logger.debug("[GeminiService] Two-part extraction successful!")

        # Filter out N/A values
        filtered_result = filter_na_values(formatted_result)
        logger.debug("[GeminiService] Filtered N/A values from formatted result")

        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting NEONATAL_DISCHARGE (two-part): {e}")
        return {
            "error": f"Failed to parse NEONATAL_DISCHARGE using two-part extraction: {_sanitize_error_message(str(e))}"
        }


async def extract_neo_admission_parameters_split(
    transcript: str,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    medicine_list_text: str = "",
    investigation_list_text: str = "",
) -> Dict[str, Any]:
    """
    Extract neonatal admission using TWO-PART extraction to avoid schema complexity limits.

    PART 1 (~60 fields): BABY, ADMISSION & PREGNANCY
    - Baby demographics (name, uhid, dob, birth details)
    - Admission info (date, type, room/bed, seen by)
    - Medical history (problems, smoking, alcohol, tobacco)
    - Pregnancy details (complications, scans)
    - Baby resuscitation details

    PART 2 (~70 fields): CLINICAL ASSESSMENT & SCORES
    - Admission details (42 fields - vitals, examination, neuro)
    - Procedures (lines, investigations, antibiotics)
    - CRIB-2 score components
    - SNAPPE-2 score components
    - Diagnosis and parent discussion

    Both results are merged and reconstructed into the final nested structure.

    Args:
        transcript: Clinical admission transcript
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)
        medicine_list_text: Formatted medicine list for prompt injection (optional)

    Returns:
        Extracted neonatal admission data as JSON with nested structure

    Raises:
        Exception: If extraction fails
    """
    import time
    import asyncio
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting neonatal admission using TWO-PART approach')

    try:
        # Build medicine list section for injection (admission has procedures_ivAntibioticIds)
        medicine_list_section = ""
        if medicine_list_text:
            medicine_list_section = (
                "\n\n**MEDICINE MATCHING (CRITICAL):**\n"
                "When extracting antibiotics/medications, match drug names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for pronunciation variations and abbreviations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{medicine_list_text}"
            )
        investigation_list_section = ""
        if investigation_list_text:
            investigation_list_section = (
                "\n\n**INVESTIGATION MATCHING (CRITICAL):**\n"
                "When extracting investigations, match names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for abbreviations and spoken variations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{investigation_list_text}"
            )
        user_prompt = NEO_ADMISSION_USER_PROMPT.format(
            transcript=transcript,
            medicine_list_section=medicine_list_section,
            investigation_list_section=investigation_list_section
        )
        system_prompt = NEO_ADMISSION_SYSTEM_PROMPT
        model = get_extraction_model_by_mode('default')  # Use model from processing_modes table

        # Check provider for routing
        from services.llm_client_factory import get_provider, generate_structured_output_parallel
        from services.schema_adapter import gemini_schema_to_json_schema
        provider = get_provider(model)

        if provider != "gemini":
            # === NON-GEMINI PATH (Claude/OpenAI) ===
            logger.debug(f"[LLM_ROUTING] Using {provider} provider with model: {model}")
            parallel_start_time = time.time()

            # Convert Gemini schemas to JSON Schema
            part1_json = gemini_schema_to_json_schema(NEO_ADMISSION_PART1_SCHEMA)
            part2_json = gemini_schema_to_json_schema(NEO_ADMISSION_PART2_SCHEMA)

            # Run parallel extraction via LLM factory
            part1_resp, part2_resp = await generate_structured_output_parallel(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema_part1=part1_json,
                json_schema_part2=part2_json,
                model=model,
                temperature=0.0,
            )

            parallel_duration = time.time() - parallel_start_time
            logger.info(f"[TIMING_LLM_API] ✅ PARALLEL extraction ({provider}): {parallel_duration:.2f}s (both parts)")

            # Data is already parsed in LLMResponse.data
            part1_data = part1_resp.data
            part2_data = part2_resp.data
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields, Part 2 extracted {len(part2_data)} fields")

            # Log usage for both parts using raw_response
            usage_data_p1 = log_extraction_usage(
                response=part1_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration,
                call_subtype="neo_admission_part1",
                consultation_type_code="NEONATAL_ADMISSION",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p1)

            usage_data_p2 = log_extraction_usage(
                response=part2_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration,
                call_subtype="neo_admission_part2",
                consultation_type_code="NEONATAL_ADMISSION",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p2)

        else:
            # === GEMINI PATH (existing code) ===
            # Get or create cache for system prompt
            cache_name = get_or_create_cache(
                prompt_type="NEO_ADMISSION",
                system_instruction=system_prompt,
                model=model,
                ttl_seconds=3600
            )

            logger.debug(f"[GeminiService] Cache: {'enabled' if cache_name else 'disabled'}")

            # Build configs for both parts
            if cache_name:
                part1_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=NEO_ADMISSION_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=NEO_ADMISSION_PART2_SCHEMA,
                    temperature=0.0,
                )
            else:
                part1_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=NEO_ADMISSION_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=NEO_ADMISSION_PART2_SCHEMA,
                    temperature=0.0,
                )

            # ========== RUN BOTH PARTS IN PARALLEL ==========
            logger.debug("[GeminiService] Starting PARALLEL extraction: Part 1 (~60 fields) + Part 2 (~70 fields)...")
            parallel_start_time = time.time()

            async def extract_part1():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part1_config
                    ),
                    timeout=120.0
                )

            async def extract_part2():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part2_config
                    ),
                    timeout=120.0
                )

            try:
                part1_response, part2_response = await asyncio.gather(
                    extract_part1(),
                    extract_part2()
                )
                parallel_end_time = time.time()
                parallel_duration = parallel_end_time - parallel_start_time
                logger.info(f"[TIMING_GEMINI_API] ✅ PARALLEL extraction: {parallel_duration:.2f}s (both parts)")

                # Log usage for both parts
                usage_data_p1 = log_extraction_usage(
                    response=part1_response,
                    model=model,
                    api_duration_seconds=parallel_duration,
                    call_subtype="neo_admission_part1",
                    consultation_type_code="NEONATAL_ADMISSION",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p1)

                usage_data_p2 = log_extraction_usage(
                    response=part2_response,
                    model=model,
                    api_duration_seconds=parallel_duration,
                    call_subtype="neo_admission_part2",
                    consultation_type_code="NEONATAL_ADMISSION",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p2)

            except asyncio.TimeoutError:
                logger.error("[GeminiService] Parallel extraction timed out after 120 seconds")
                error_usage = create_error_usage(
                    call_type="extraction", model=model, api_duration_seconds=120.0,
                    error_message="Timeout after 120s", call_subtype="neo_admission_parallel",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                )
                await log_llm_usage(error_usage)
                raise Exception("Parallel extraction timed out")

            # Parse both responses
            logger.debug("[GeminiService] Parsing Part 1 response...")
            part1_data = clean_and_parse_json(part1_response.text, context="NEO_ADMISSION Part 1")
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields")

            logger.debug("[GeminiService] Parsing Part 2 response...")
            part2_data = clean_and_parse_json(part2_response.text, context="NEO_ADMISSION Part 2")
            logger.debug(f"[GeminiService] Part 2 extracted {len(part2_data)} fields")

        # Merge and reconstruct nested structure
        logger.debug("[GeminiService] Merging Part 1 and Part 2 results...")
        formatted_result = format_neo_admission_from_parts(part1_data, part2_data)
        logger.debug("[GeminiService] Two-part extraction successful!")

        # Filter out N/A values
        filtered_result = filter_na_values(formatted_result)
        logger.debug("[GeminiService] Filtered N/A values from formatted result")

        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting NEONATAL_ADMISSION (two-part): {e}")
        return {
            "error": f"Failed to parse NEONATAL_ADMISSION using two-part extraction: {_sanitize_error_message(str(e))}"
        }


async def extract_neo_daily_parameters_split(
    transcript: str,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    medicine_list_text: str = "",
    investigation_list_text: str = "",
) -> Dict[str, Any]:
    """
    Extract neonatal daily progress notes using TWO-PART extraction to avoid schema complexity limits.

    The expanded NEO_DAILY schema (~125 fields) exceeds Gemini's constraint limits.
    This function splits the extraction into TWO separate API calls:

    PART 1 (~58 fields): PATIENT + VITALS + RESPIRATORY + CARDIOVASCULAR
    - Patient identification (uhid, admissionId)
    - General info (dateTime, seenBy, problems, background)
    - Respiratory system (ventilation settings, gas exchange, examination)
    - Cardiovascular system (hemodynamics, perfusion)
    - Plan and notes

    PART 2 (~67 fields): SYSTEM EXAMINATIONS & SUPPORT
    - Gastrointestinal (feeding, bowel, abdomen)
    - CNS (neuro status)
    - Renal/Fluid Balance (urine output, electrolytes)
    - Sepsis (cultures, antibiotics)
    - Invasive Lines (UAC/UVC/PICC/IV)
    - Skin (condition, rash)
    - ROP (screening status)

    Both results are merged and reconstructed into the final nested dailyLog structure.

    Args:
        transcript: Clinical daily progress note transcript
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)
        medicine_list_text: Formatted medicine list for prompt injection (optional)

    Returns:
        Extracted neonatal daily data as JSON with nested dailyLog structure

    Raises:
        Exception: If extraction fails
    """
    import time
    import asyncio
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting neonatal daily progress using TWO-PART approach')

    try:
        # Part 1 gets its own user prompt (focuses on vitals, respiratory, cardiovascular)
        part1_user_prompt = NEO_DAILY_PART1_USER_PROMPT.format(transcript=transcript)
        # Part 2 gets its own user prompt (focuses on systems examination + antibiotics)
        # Build medicine list section for injection into Part 2 (which has antibiotics_list)
        medicine_list_section = ""
        if medicine_list_text:
            medicine_list_section = (
                "\n\n**MEDICINE MATCHING (CRITICAL):**\n"
                "When extracting antibiotics/medications, match drug names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for pronunciation variations and abbreviations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{medicine_list_text}"
            )
        investigation_list_section = ""
        if investigation_list_text:
            investigation_list_section = (
                "\n\n**INVESTIGATION MATCHING (CRITICAL):**\n"
                "When extracting investigations, match names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for abbreviations and spoken variations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{investigation_list_text}"
            )
        part2_user_prompt = NEO_DAILY_PART2_USER_PROMPT.format(
            transcript=transcript,
            medicine_list_section=medicine_list_section,
            investigation_list_section=investigation_list_section
        )
        system_prompt = NEO_DAILY_SPLIT_SYSTEM_PROMPT
        model = get_extraction_model_by_mode('default')  # Use model from processing_modes table

        # Check provider for routing
        from services.llm_client_factory import get_provider, generate_structured_output
        from services.schema_adapter import gemini_schema_to_json_schema
        provider = get_provider(model)

        if provider != "gemini":
            # === NON-GEMINI PATH (Claude/OpenAI) ===
            # NEO_DAILY uses DIFFERENT user prompts for each part, so we can't use generate_structured_output_parallel()
            logger.debug(f"[LLM_ROUTING] Using {provider} provider with model: {model}")
            parallel_start_time = time.time()

            # Convert Gemini schemas to JSON Schema
            part1_json = gemini_schema_to_json_schema(NEO_DAILY_PART1_SCHEMA)
            part2_json = gemini_schema_to_json_schema(NEO_DAILY_PART2_SCHEMA)

            # Run parallel extraction with separate user prompts
            part1_task = generate_structured_output(
                system_prompt=system_prompt,
                user_prompt=part1_user_prompt,
                json_schema=part1_json,
                model=model,
                temperature=0.0,
            )
            part2_task = generate_structured_output(
                system_prompt=system_prompt,
                user_prompt=part2_user_prompt,
                json_schema=part2_json,
                model=model,
                temperature=0.0,
            )
            part1_resp, part2_resp = await asyncio.gather(part1_task, part2_task)

            parallel_duration = time.time() - parallel_start_time
            logger.info(f"[TIMING_LLM_API] ✅ PARALLEL extraction ({provider}): {parallel_duration:.2f}s (both parts)")

            # Data is already parsed in LLMResponse.data
            part1_data = part1_resp.data
            part2_data = part2_resp.data
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields, Part 2 extracted {len(part2_data)} fields")

            # Log usage for both parts using raw_response
            usage_data_p1 = log_extraction_usage(
                response=part1_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration,
                call_subtype="neo_daily_part1",
                consultation_type_code="NEONATAL_DAILY",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(part1_user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p1)

            usage_data_p2 = log_extraction_usage(
                response=part2_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration,
                call_subtype="neo_daily_part2",
                consultation_type_code="NEONATAL_DAILY",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(part2_user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p2)

        else:
            # === GEMINI PATH (existing code) ===
            # Get or create cache for system prompt (shared by both parts)
            cache_name = get_or_create_cache(
                prompt_type=CACHE_KEY_NEO_DAILY,
                system_instruction=system_prompt,
                model=model,
                ttl_seconds=3600  # 1 hour
            )

            logger.debug(
                f"[GeminiService] Using NEO_DAILY split prompts. "
                f"Cache: {'enabled' if cache_name else 'disabled'}"
            )

            # Build configs for both parts
            if cache_name:
                part1_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=NEO_DAILY_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=NEO_DAILY_PART2_SCHEMA,
                    temperature=0.0,
                )
            else:
                part1_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=NEO_DAILY_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=NEO_DAILY_PART2_SCHEMA,
                    temperature=0.0,
                )

            # ========== RUN BOTH PARTS IN PARALLEL ==========
            logger.debug("[GeminiService] Starting PARALLEL extraction: Part 1 (~58 fields) + Part 2 (~67 fields)...")
            parallel_start_time = time.time()

            async def extract_part1():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": part1_user_prompt}]}],
                        config=part1_config
                    ),
                    timeout=120.0
                )

            async def extract_part2():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": part2_user_prompt}]}],
                        config=part2_config
                    ),
                    timeout=120.0
                )

            try:
                part1_response, part2_response = await asyncio.gather(
                    extract_part1(),
                    extract_part2()
                )
                parallel_end_time = time.time()
                parallel_duration = parallel_end_time - parallel_start_time
                logger.info(f"[TIMING_GEMINI_API] PARALLEL extraction: {parallel_duration:.2f}s (both parts)")

                # Log usage for both parts
                usage_data_p1 = log_extraction_usage(
                    response=part1_response,
                    model=model,
                    api_duration_seconds=parallel_duration,
                    call_subtype="neo_daily_part1",
                    consultation_type_code="NEONATAL_DAILY",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(part1_user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p1)

                usage_data_p2 = log_extraction_usage(
                    response=part2_response,
                    model=model,
                    api_duration_seconds=parallel_duration,
                    call_subtype="neo_daily_part2",
                    consultation_type_code="NEONATAL_DAILY",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(part2_user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p2)

            except asyncio.TimeoutError:
                logger.error("[GeminiService] Parallel extraction timed out after 120 seconds")
                error_usage = create_error_usage(
                    call_type="extraction", model=model, api_duration_seconds=120.0,
                    error_message="Timeout after 120s", call_subtype="neo_daily_parallel",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                )
                await log_llm_usage(error_usage)
                raise Exception("Parallel extraction timed out")

            # Parse both responses
            logger.debug("[GeminiService] Parsing Part 1 response...")
            part1_data = clean_and_parse_json(part1_response.text, context="NEO_DAILY Part 1")
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields")

            logger.debug("[GeminiService] Parsing Part 2 response...")
            part2_data = clean_and_parse_json(part2_response.text, context="NEO_DAILY Part 2")
            logger.debug(f"[GeminiService] Part 2 extracted {len(part2_data)} fields")

        # Merge and reconstruct nested dailyLog structure
        logger.debug("[GeminiService] Merging Part 1 and Part 2 results...")
        formatted_result = format_neo_daily_from_parts(part1_data, part2_data)
        logger.debug("[GeminiService] Two-part extraction successful!")

        # Filter out empty/null values
        filtered_result = filter_na_values(formatted_result)
        logger.debug("[GeminiService] Filtered empty values from formatted result")

        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting NEONATAL_DAILY (two-part): {e}")
        return {
            "error": f"Failed to parse NEONATAL_DAILY using two-part extraction: {_sanitize_error_message(str(e))}"
        }


async def extract_neo_daily_free_parameters(
    transcript: str,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    medicine_list_text: str = "",
    investigation_list_text: str = "",
) -> Dict[str, Any]:
    """
    Extract neonatal daily progress notes in simplified FREE-TEXT format.

    Unlike NEO_DAILY (~125 structured fields, two-part split), this uses a single
    Gemini call with 17 flat fields. Clinical details are captured as free text
    within system-specific fields (respiratorySystem, cardiovascularSystem, etc.).

    Args:
        transcript: Clinical daily progress note transcript
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)

    Returns:
        Extracted neonatal daily data as flat JSON with 17 fields

    Raises:
        Exception: If extraction fails
    """
    import time
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting neonatal daily progress using FREE-TEXT format (17 fields)')

    try:
        # Build medicine list section for injection (free text sepsis field has antibiotic names)
        medicine_list_section = ""
        if medicine_list_text:
            medicine_list_section = (
                "\n\n**MEDICINE MATCHING (CRITICAL):**\n"
                "When extracting antibiotics/medications in the sepsis field, match drug names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for pronunciation variations and abbreviations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{medicine_list_text}"
            )
        investigation_list_section = ""
        if investigation_list_text:
            investigation_list_section = (
                "\n\n**INVESTIGATION MATCHING (CRITICAL):**\n"
                "When extracting investigations, match names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for abbreviations and spoken variations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{investigation_list_text}"
            )
        user_prompt = NEO_DAILY_FREE_USER_PROMPT.format(
            transcript=transcript,
            medicine_list_section=medicine_list_section,
            investigation_list_section=investigation_list_section
        )
        system_prompt = NEO_DAILY_FREE_SYSTEM_PROMPT
        model = get_extraction_model_by_mode('default')

        # Check provider for routing
        from services.llm_client_factory import get_provider, generate_structured_output
        from services.schema_adapter import gemini_schema_to_json_schema
        provider = get_provider(model)

        start_time = time.time()

        if provider != "gemini":
            # === NON-GEMINI PATH (Claude/OpenAI) ===
            logger.debug(f"[LLM_ROUTING] NEO_DAILY_FREE using {provider} provider with model: {model}")

            json_schema = gemini_schema_to_json_schema(NEO_DAILY_FREE_SCHEMA)
            response = await generate_structured_output(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema=json_schema,
                model=model,
                temperature=0.0,
            )

            api_duration = time.time() - start_time
            logger.info(f"[TIMING_LLM_API] NEO_DAILY_FREE extraction ({provider}): {api_duration:.2f}s")

            result_data = response.data
            logger.debug(f"[GeminiService] NEO_DAILY_FREE extracted {len(result_data)} fields")

            # Log usage
            usage_data = log_extraction_usage(
                response=response.raw_response,
                model=model,
                api_duration_seconds=api_duration,
                call_subtype="neo_daily_free",
                consultation_type_code="NEONATAL_DAILY_FREE",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data)

        else:
            # === GEMINI PATH ===
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=NEO_DAILY_FREE_SCHEMA,
                temperature=0.0,
            )

            logger.debug("[GeminiService] Starting NEO_DAILY_FREE extraction (17 fields)...")
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=config,
                    ),
                    timeout=120.0,
                )

                api_duration = time.time() - start_time
                logger.info(f"[TIMING_GEMINI_API] NEO_DAILY_FREE extraction: {api_duration:.2f}s")

                # Log usage
                usage_data = log_extraction_usage(
                    response=response,
                    model=model,
                    api_duration_seconds=api_duration,
                    call_subtype="neo_daily_free",
                    consultation_type_code="NEONATAL_DAILY_FREE",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data)

            except asyncio.TimeoutError:
                logger.error("[GeminiService] NEO_DAILY_FREE extraction timed out after 120 seconds")
                error_usage = create_error_usage(
                    call_type="extraction", model=model, api_duration_seconds=120.0,
                    error_message="Timeout after 120s", call_subtype="neo_daily_free",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                )
                await log_llm_usage(error_usage)
                raise Exception("NEO_DAILY_FREE extraction timed out")

            # Parse response
            result_data = clean_and_parse_json(response.text, context="NEO_DAILY_FREE")
            logger.debug(f"[GeminiService] NEO_DAILY_FREE extracted {len(result_data)} fields")

        # ========== POST-PROCESSING ==========
        # Resolve seenBy names/IDs via doctor lookup, default to [7] if empty
        from services.doctor_lookups import resolve_seen_by_ids
        seen_by_raw = result_data.get("seenBy")
        if isinstance(seen_by_raw, list) and seen_by_raw:
            result_data["seenBy"] = resolve_seen_by_ids(seen_by_raw)
        else:
            result_data["seenBy"] = [7]
            logger.debug("[GeminiService] NEO_DAILY_FREE: Defaulted seenBy to [7]")

        # Filter out empty/null values
        filtered_result = filter_na_values(result_data)
        logger.debug("[GeminiService] NEO_DAILY_FREE extraction successful!")

        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting NEONATAL_DAILY_FREE: {e}")
        return {
            "error": f"Failed to parse NEONATAL_DAILY_FREE: {_sanitize_error_message(str(e))}"
        }


async def extract_neo_proforma_free_parameters(
    transcript: str,
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    medicine_list_text: str = "",
    investigation_list_text: str = "",
) -> Dict[str, Any]:
    """
    Extract neonatal proforma data in simplified FREE-TEXT format (21 fields).
    Single Gemini call. Maps to /store-neonatal-proforma-free-text.
    """
    import time
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting neonatal proforma using FREE-TEXT format (21 fields)')

    try:
        medicine_list_section = ""
        if medicine_list_text:
            medicine_list_section = (
                "\n\n**MEDICINE MATCHING (CRITICAL):**\n"
                "When extracting medications, match drug names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for pronunciation variations and abbreviations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{medicine_list_text}"
            )
        investigation_list_section = ""
        if investigation_list_text:
            investigation_list_section = (
                "\n\n**INVESTIGATION MATCHING (CRITICAL):**\n"
                "When extracting investigations, match names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for abbreviations and spoken variations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{investigation_list_text}"
            )
        user_prompt = NEO_PROFORMA_FREE_USER_PROMPT.format(
            transcript=transcript,
            medicine_list_section=medicine_list_section,
            investigation_list_section=investigation_list_section
        )
        system_prompt = NEO_PROFORMA_FREE_SYSTEM_PROMPT
        model = get_extraction_model_by_mode('default')

        from services.llm_client_factory import get_provider, generate_structured_output
        from services.schema_adapter import gemini_schema_to_json_schema
        provider = get_provider(model)

        start_time = time.time()

        if provider != "gemini":
            logger.debug(f"[LLM_ROUTING] NEO_PROFORMA_FREE using {provider} provider with model: {model}")
            json_schema = gemini_schema_to_json_schema(NEO_PROFORMA_FREE_SCHEMA)
            response = await generate_structured_output(
                system_prompt=system_prompt, user_prompt=user_prompt,
                json_schema=json_schema, model=model, temperature=0.0,
            )
            api_duration = time.time() - start_time
            logger.info(f"[TIMING_LLM_API] NEO_PROFORMA_FREE extraction ({provider}): {api_duration:.2f}s")
            result_data = response.data
            usage_data = log_extraction_usage(
                response=response.raw_response, model=model,
                api_duration_seconds=api_duration, call_subtype="neo_proforma_free",
                consultation_type_code="NEO_PROFORMA_FREE",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data)
        else:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=NEO_PROFORMA_FREE_SCHEMA,
                temperature=0.0,
            )
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=config,
                    ),
                    timeout=120.0,
                )
                api_duration = time.time() - start_time
                logger.info(f"[TIMING_GEMINI_API] NEO_PROFORMA_FREE extraction: {api_duration:.2f}s")
                usage_data = log_extraction_usage(
                    response=response, model=model,
                    api_duration_seconds=api_duration, call_subtype="neo_proforma_free",
                    consultation_type_code="NEO_PROFORMA_FREE",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data)
            except asyncio.TimeoutError:
                logger.error("[GeminiService] NEO_PROFORMA_FREE extraction timed out after 120 seconds")
                error_usage = create_error_usage(
                    call_type="extraction", model=model, api_duration_seconds=120.0,
                    error_message="Timeout after 120s", call_subtype="neo_proforma_free",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                )
                await log_llm_usage(error_usage)
                raise Exception("NEO_PROFORMA_FREE extraction timed out")
            result_data = clean_and_parse_json(response.text, context="NEO_PROFORMA_FREE")

        # Post-processing: resolve seenBy
        from services.doctor_lookups import resolve_seen_by_ids
        seen_by_raw = result_data.get("seenBy")
        if isinstance(seen_by_raw, list) and seen_by_raw:
            result_data["seenBy"] = resolve_seen_by_ids(seen_by_raw)
        else:
            result_data["seenBy"] = [7]

        filtered_result = filter_na_values(result_data)
        logger.debug("[GeminiService] NEO_PROFORMA_FREE extraction successful!")
        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting NEO_PROFORMA_FREE: {e}")
        return {"error": f"Failed to parse NEO_PROFORMA_FREE: {_sanitize_error_message(str(e))}"}


async def extract_neo_discharge_free_parameters(
    transcript: str,
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    medicine_list_text: str = "",
    investigation_list_text: str = "",
) -> Dict[str, Any]:
    """
    Extract NICU discharge data in simplified FREE-TEXT format (21 fields).
    Single Gemini call. Maps to /store-nicu-discharge-free-text.
    """
    import time
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting NICU discharge using FREE-TEXT format (21 fields)')

    try:
        medicine_list_section = ""
        if medicine_list_text:
            medicine_list_section = (
                "\n\n**MEDICINE MATCHING (CRITICAL):**\n"
                "When extracting medications in the medications array, match drug names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for pronunciation variations and abbreviations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{medicine_list_text}"
            )
        investigation_list_section = ""
        if investigation_list_text:
            investigation_list_section = (
                "\n\n**INVESTIGATION MATCHING (CRITICAL):**\n"
                "When extracting investigations, match names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for abbreviations and spoken variations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{investigation_list_text}"
            )
        user_prompt = NEO_DISCHARGE_FREE_USER_PROMPT.format(
            transcript=transcript,
            medicine_list_section=medicine_list_section,
            investigation_list_section=investigation_list_section
        )
        system_prompt = NEO_DISCHARGE_FREE_SYSTEM_PROMPT
        model = get_extraction_model_by_mode('default')

        from services.llm_client_factory import get_provider, generate_structured_output
        from services.schema_adapter import gemini_schema_to_json_schema
        provider = get_provider(model)

        start_time = time.time()

        if provider != "gemini":
            logger.debug(f"[LLM_ROUTING] NEO_DISCHARGE_FREE using {provider} provider with model: {model}")
            json_schema = gemini_schema_to_json_schema(NEO_DISCHARGE_FREE_SCHEMA)
            response = await generate_structured_output(
                system_prompt=system_prompt, user_prompt=user_prompt,
                json_schema=json_schema, model=model, temperature=0.0,
            )
            api_duration = time.time() - start_time
            logger.info(f"[TIMING_LLM_API] NEO_DISCHARGE_FREE extraction ({provider}): {api_duration:.2f}s")
            result_data = response.data
            usage_data = log_extraction_usage(
                response=response.raw_response, model=model,
                api_duration_seconds=api_duration, call_subtype="neo_discharge_free",
                consultation_type_code="NEO_DISCHARGE_FREE",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data)
        else:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=NEO_DISCHARGE_FREE_SCHEMA,
                temperature=0.0,
            )
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=config,
                    ),
                    timeout=120.0,
                )
                api_duration = time.time() - start_time
                logger.info(f"[TIMING_GEMINI_API] NEO_DISCHARGE_FREE extraction: {api_duration:.2f}s")
                usage_data = log_extraction_usage(
                    response=response, model=model,
                    api_duration_seconds=api_duration, call_subtype="neo_discharge_free",
                    consultation_type_code="NEO_DISCHARGE_FREE",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data)
            except asyncio.TimeoutError:
                logger.error("[GeminiService] NEO_DISCHARGE_FREE extraction timed out after 120 seconds")
                error_usage = create_error_usage(
                    call_type="extraction", model=model, api_duration_seconds=120.0,
                    error_message="Timeout after 120s", call_subtype="neo_discharge_free",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                )
                await log_llm_usage(error_usage)
                raise Exception("NEO_DISCHARGE_FREE extraction timed out")
            result_data = clean_and_parse_json(response.text, context="NEO_DISCHARGE_FREE")

        # Post-processing: resolve seenBy
        from services.doctor_lookups import resolve_seen_by_ids
        seen_by_raw = result_data.get("seenBy")
        if isinstance(seen_by_raw, list) and seen_by_raw:
            result_data["seenBy"] = resolve_seen_by_ids(seen_by_raw)
        else:
            result_data["seenBy"] = [7]

        filtered_result = filter_na_values(result_data)
        logger.debug("[GeminiService] NEO_DISCHARGE_FREE extraction successful!")
        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting NEO_DISCHARGE_FREE: {e}")
        return {"error": f"Failed to parse NEO_DISCHARGE_FREE: {_sanitize_error_message(str(e))}"}


async def extract_neo_postnatal_day_free_parameters(
    transcript: str,
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    medicine_list_text: str = "",
    investigation_list_text: str = "",
) -> Dict[str, Any]:
    """
    Extract postnatal daycare data in simplified FREE-TEXT format (9 fields).
    Single Gemini call. Maps to /store-postnatal-daycare-free-text.
    """
    import time
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting postnatal daycare using FREE-TEXT format (9 fields)')

    try:
        medicine_list_section = ""
        if medicine_list_text:
            medicine_list_section = (
                "\n\n**MEDICINE MATCHING (CRITICAL):**\n"
                "When extracting medications, match drug names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for pronunciation variations and abbreviations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{medicine_list_text}"
            )
        investigation_list_section = ""
        if investigation_list_text:
            investigation_list_section = (
                "\n\n**INVESTIGATION MATCHING (CRITICAL):**\n"
                "When extracting investigations, match names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for abbreviations and spoken variations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{investigation_list_text}"
            )
        user_prompt = NEO_POSTNATAL_DAY_FREE_USER_PROMPT.format(
            transcript=transcript,
            medicine_list_section=medicine_list_section,
            investigation_list_section=investigation_list_section
        )
        system_prompt = NEO_POSTNATAL_DAY_FREE_SYSTEM_PROMPT
        model = get_extraction_model_by_mode('default')

        from services.llm_client_factory import get_provider, generate_structured_output
        from services.schema_adapter import gemini_schema_to_json_schema
        provider = get_provider(model)

        start_time = time.time()

        if provider != "gemini":
            logger.debug(f"[LLM_ROUTING] NEO_POSTNATAL_DAY_FREE using {provider} provider with model: {model}")
            json_schema = gemini_schema_to_json_schema(NEO_POSTNATAL_DAY_FREE_SCHEMA)
            response = await generate_structured_output(
                system_prompt=system_prompt, user_prompt=user_prompt,
                json_schema=json_schema, model=model, temperature=0.0,
            )
            api_duration = time.time() - start_time
            logger.info(f"[TIMING_LLM_API] NEO_POSTNATAL_DAY_FREE extraction ({provider}): {api_duration:.2f}s")
            result_data = response.data
            usage_data = log_extraction_usage(
                response=response.raw_response, model=model,
                api_duration_seconds=api_duration, call_subtype="neo_postnatal_day_free",
                consultation_type_code="NEO_POSTNATAL_DAY_FREE",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data)
        else:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=NEO_POSTNATAL_DAY_FREE_SCHEMA,
                temperature=0.0,
            )
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=config,
                    ),
                    timeout=120.0,
                )
                api_duration = time.time() - start_time
                logger.info(f"[TIMING_GEMINI_API] NEO_POSTNATAL_DAY_FREE extraction: {api_duration:.2f}s")
                usage_data = log_extraction_usage(
                    response=response, model=model,
                    api_duration_seconds=api_duration, call_subtype="neo_postnatal_day_free",
                    consultation_type_code="NEO_POSTNATAL_DAY_FREE",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data)
            except asyncio.TimeoutError:
                logger.error("[GeminiService] NEO_POSTNATAL_DAY_FREE extraction timed out after 120 seconds")
                error_usage = create_error_usage(
                    call_type="extraction", model=model, api_duration_seconds=120.0,
                    error_message="Timeout after 120s", call_subtype="neo_postnatal_day_free",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                )
                await log_llm_usage(error_usage)
                raise Exception("NEO_POSTNATAL_DAY_FREE extraction timed out")
            result_data = clean_and_parse_json(response.text, context="NEO_POSTNATAL_DAY_FREE")

        # Post-processing: resolve seenBy
        from services.doctor_lookups import resolve_seen_by_ids
        seen_by_raw = result_data.get("seenBy")
        if isinstance(seen_by_raw, list) and seen_by_raw:
            result_data["seenBy"] = resolve_seen_by_ids(seen_by_raw)
        else:
            result_data["seenBy"] = [7]

        filtered_result = filter_na_values(result_data)
        logger.debug("[GeminiService] NEO_POSTNATAL_DAY_FREE extraction successful!")
        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting NEO_POSTNATAL_DAY_FREE: {e}")
        return {"error": f"Failed to parse NEO_POSTNATAL_DAY_FREE: {_sanitize_error_message(str(e))}"}


async def extract_neo_postnatal_discharge_free_parameters(
    transcript: str,
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    medicine_list_text: str = "",
    investigation_list_text: str = "",
) -> Dict[str, Any]:
    """
    Extract postnatal discharge data in simplified FREE-TEXT format (15 fields).
    Single Gemini call. Maps to /store-postnatal-discharge-free-text.
    """
    import time
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting postnatal discharge using FREE-TEXT format (15 fields)')

    try:
        medicine_list_section = ""
        if medicine_list_text:
            medicine_list_section = (
                "\n\n**MEDICINE MATCHING (CRITICAL):**\n"
                "When extracting medications in the medications array, match drug names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for pronunciation variations and abbreviations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{medicine_list_text}"
            )
        investigation_list_section = ""
        if investigation_list_text:
            investigation_list_section = (
                "\n\n**INVESTIGATION MATCHING (CRITICAL):**\n"
                "When extracting investigations, match names from this list:\n"
                "- Use the EXACT name from the list when a match is found\n"
                "- Account for abbreviations and spoken variations\n"
                "- If no match exists, use the spoken name verbatim\n\n"
                f"{investigation_list_text}"
            )
        user_prompt = NEO_POSTNATAL_DISCHARGE_FREE_USER_PROMPT.format(
            transcript=transcript,
            medicine_list_section=medicine_list_section,
            investigation_list_section=investigation_list_section
        )
        system_prompt = NEO_POSTNATAL_DISCHARGE_FREE_SYSTEM_PROMPT
        model = get_extraction_model_by_mode('default')

        from services.llm_client_factory import get_provider, generate_structured_output
        from services.schema_adapter import gemini_schema_to_json_schema
        provider = get_provider(model)

        start_time = time.time()

        if provider != "gemini":
            logger.debug(f"[LLM_ROUTING] NEO_POSTNATAL_DISCHARGE_FREE using {provider} provider with model: {model}")
            json_schema = gemini_schema_to_json_schema(NEO_POSTNATAL_DISCHARGE_FREE_SCHEMA)
            response = await generate_structured_output(
                system_prompt=system_prompt, user_prompt=user_prompt,
                json_schema=json_schema, model=model, temperature=0.0,
            )
            api_duration = time.time() - start_time
            logger.info(f"[TIMING_LLM_API] NEO_POSTNATAL_DISCHARGE_FREE extraction ({provider}): {api_duration:.2f}s")
            result_data = response.data
            usage_data = log_extraction_usage(
                response=response.raw_response, model=model,
                api_duration_seconds=api_duration, call_subtype="neo_postnatal_discharge_free",
                consultation_type_code="NEO_POSTNATAL_DISCHARGE_FREE",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data)
        else:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=NEO_POSTNATAL_DISCHARGE_FREE_SCHEMA,
                temperature=0.0,
            )
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=config,
                    ),
                    timeout=120.0,
                )
                api_duration = time.time() - start_time
                logger.info(f"[TIMING_GEMINI_API] NEO_POSTNATAL_DISCHARGE_FREE extraction: {api_duration:.2f}s")
                usage_data = log_extraction_usage(
                    response=response, model=model,
                    api_duration_seconds=api_duration, call_subtype="neo_postnatal_discharge_free",
                    consultation_type_code="NEO_POSTNATAL_DISCHARGE_FREE",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data)
            except asyncio.TimeoutError:
                logger.error("[GeminiService] NEO_POSTNATAL_DISCHARGE_FREE extraction timed out after 120 seconds")
                error_usage = create_error_usage(
                    call_type="extraction", model=model, api_duration_seconds=120.0,
                    error_message="Timeout after 120s", call_subtype="neo_postnatal_discharge_free",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                )
                await log_llm_usage(error_usage)
                raise Exception("NEO_POSTNATAL_DISCHARGE_FREE extraction timed out")
            result_data = clean_and_parse_json(response.text, context="NEO_POSTNATAL_DISCHARGE_FREE")

        # Post-processing: resolve seenBy
        from services.doctor_lookups import resolve_seen_by_ids
        seen_by_raw = result_data.get("seenBy")
        if isinstance(seen_by_raw, list) and seen_by_raw:
            result_data["seenBy"] = resolve_seen_by_ids(seen_by_raw)
        else:
            result_data["seenBy"] = [7]

        filtered_result = filter_na_values(result_data)
        logger.debug("[GeminiService] NEO_POSTNATAL_DISCHARGE_FREE extraction successful!")
        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting NEO_POSTNATAL_DISCHARGE_FREE: {e}")
        return {"error": f"Failed to parse NEO_POSTNATAL_DISCHARGE_FREE: {_sanitize_error_message(str(e))}"}


async def extract_ophthal_discharge_parameters_split(
    transcript: str,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract ophthalmology discharge summary using TWO-PART extraction to avoid schema complexity limits.

    The flattened schema (42 properties) may approach Gemini's constraint limits.
    This function splits the extraction into TWO separate API calls:

    PART 1 (23 fields): PATIENT DATA & TREATMENT
    - Patient demographics, admission details
    - Medical team, diagnosis
    - Treatment given, discharge status
    - Provider information

    PART 2 (19 fields): MEDICATIONS & DISCHARGE INSTRUCTIONS
    - Discharge medication (8 parallel arrays)
    - Discharge advice, emergency contact

    Both results are merged and reconstructed into the final nested structure.

    Args:
        transcript: Clinical discharge summary transcript
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)

    Returns:
        Extracted ophthalmology discharge data as JSON with nested structure

    Raises:
        Exception: If extraction fails
    """
    import time
    import asyncio
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting ophthalmology discharge using TWO-PART approach')

    try:
        user_prompt = OPHTHAL_DISCHARGE_USER_PROMPT.format(transcript=transcript)
        system_prompt = OPHTHAL_DISCHARGE_SYSTEM_PROMPT
        model = get_extraction_model_by_mode('default')  # Use model from processing_modes table

        # Check provider for routing
        from services.llm_client_factory import get_provider, generate_structured_output_parallel
        from services.schema_adapter import gemini_schema_to_json_schema
        provider = get_provider(model)

        if provider != "gemini":
            # === NON-GEMINI PATH (Claude/OpenAI) ===
            logger.debug(f"[LLM_ROUTING] Using {provider} provider with model: {model}")
            parallel_start_time = time.time()

            # Convert Gemini schemas to JSON Schema
            part1_json = gemini_schema_to_json_schema(OPHTHAL_DISCHARGE_PART1_SCHEMA)
            part2_json = gemini_schema_to_json_schema(OPHTHAL_DISCHARGE_PART2_SCHEMA)

            # Run parallel extraction via LLM factory
            part1_resp, part2_resp = await generate_structured_output_parallel(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema_part1=part1_json,
                json_schema_part2=part2_json,
                model=model,
                temperature=0.0,
            )

            parallel_duration = time.time() - parallel_start_time
            logger.info(f"[TIMING_LLM_API] ✅ PARALLEL extraction ({provider}): {parallel_duration:.2f}s (both parts)")

            # Data is already parsed in LLMResponse.data
            part1_data = part1_resp.data
            part2_data = part2_resp.data
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields, Part 2 extracted {len(part2_data)} fields")

            # Log usage for both parts using raw_response
            usage_data_p1 = log_extraction_usage(
                response=part1_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration,
                call_subtype="ophthal_discharge_part1",
                consultation_type_code="OPHTHAL_DISCHARGE",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p1)

            usage_data_p2 = log_extraction_usage(
                response=part2_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration,
                call_subtype="ophthal_discharge_part2",
                consultation_type_code="OPHTHAL_DISCHARGE",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4,
                user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p2)

        else:
            # === GEMINI PATH (existing code) ===
            # Get or create cache for system prompt (used by BOTH Part 1 and Part 2)
            cache_name = get_or_create_cache(
                prompt_type=CACHE_KEY_OPHTHAL_DISCHARGE,
                system_instruction=system_prompt,
                model=model,
                ttl_seconds=3600  # 1 hour
            )

            logger.debug(f"[GeminiService] Cache: {'enabled' if cache_name else 'disabled'}")

            # Build configs for both parts
            if cache_name:
                part1_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=OPHTHAL_DISCHARGE_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=OPHTHAL_DISCHARGE_PART2_SCHEMA,
                    temperature=0.0,
                )
            else:
                part1_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=OPHTHAL_DISCHARGE_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=OPHTHAL_DISCHARGE_PART2_SCHEMA,
                    temperature=0.0,
                )

            # ========== RUN BOTH PARTS IN PARALLEL ==========
            logger.debug("[GeminiService] Starting PARALLEL extraction: Part 1 (23 fields) + Part 2 (19 fields)...")
            parallel_start_time = time.time()

            async def extract_part1():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part1_config
                    ),
                    timeout=120.0
                )

            async def extract_part2():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part2_config
                    ),
                    timeout=120.0
                )

            try:
                part1_response, part2_response = await asyncio.gather(
                    extract_part1(),
                    extract_part2()
                )
                parallel_end_time = time.time()
                parallel_duration = parallel_end_time - parallel_start_time
                logger.info(f"[TIMING_GEMINI_API] ✅ PARALLEL extraction: {parallel_duration:.2f}s (both parts)")

                # Log usage for both parts
                usage_data_p1 = log_extraction_usage(
                    response=part1_response,
                    model=model,
                    api_duration_seconds=parallel_duration,
                    call_subtype="ophthal_discharge_part1",
                    consultation_type_code="OPHTHAL_DISCHARGE",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p1)

                usage_data_p2 = log_extraction_usage(
                    response=part2_response,
                    model=model,
                    api_duration_seconds=parallel_duration,
                    call_subtype="ophthal_discharge_part2",
                    consultation_type_code="OPHTHAL_DISCHARGE",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4,
                    user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p2)

            except asyncio.TimeoutError:
                logger.error("[GeminiService] Parallel extraction timed out after 120 seconds")
                error_usage = create_error_usage(
                    call_type="extraction", model=model, api_duration_seconds=120.0,
                    error_message="Timeout after 120s", call_subtype="ophthal_discharge_parallel",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                )
                await log_llm_usage(error_usage)
                raise Exception("Parallel extraction timed out")
            except Exception as e:
                logger.error(f"[GeminiService] Parallel extraction failed: {type(e).__name__}: {str(e)}")
                raise Exception(_sanitize_error_message(str(e)))

            # Parse both responses with robust cleaning
            logger.debug("[GeminiService] Parsing Part 1 response...")
            part1_data = clean_and_parse_json(part1_response.text, context="OPHTHAL_DISCHARGE Part 1")
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields")

            logger.debug("[GeminiService] Parsing Part 2 response...")
            part2_data = clean_and_parse_json(part2_response.text, context="OPHTHAL_DISCHARGE Part 2")
            logger.debug(f"[GeminiService] Part 2 extracted {len(part2_data)} fields")

        # Merge and reconstruct nested structure
        logger.debug("[GeminiService] Merging Part 1 and Part 2 results...")
        formatted_result = format_ophthal_discharge_from_parts(part1_data, part2_data)
        logger.debug("[GeminiService] Two-part extraction successful!")

        # Filter out N/A values
        filtered_result = filter_na_values(formatted_result)
        logger.debug("[GeminiService] Filtered N/A values from formatted result")

        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting ophthalmology discharge (two-part): {e}")
        return {
            "error": f"Failed to parse ophthalmology discharge using two-part extraction: {_sanitize_error_message(str(e))}"
        }


async def extract_ophthalmology_parameters_split(
    transcript: str,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract basic ophthalmology consultation using TWO-PART extraction to avoid schema complexity limits.

    The flattened schema (71 properties) may exceed Gemini's constraint limits,
    especially with the deeply nested fundusExamination section.
    This function splits the extraction into TWO separate API calls:

    PART 1 (33 fields): PATIENT DATA & ANTERIOR EXAMINATION
    - Patient demographics, clinical history
    - Visual acuity, refraction
    - Muscle balance, intraocular pressure
    - Gonioscopy, provider information

    PART 2 (38 fields): SLIT LAMP & FUNDUS EXAMINATION
    - Slit lamp examination (bilateral)
    - Fundus examination (26 fields, 4 levels deep)
    - Diagnosis, advice and follow-up

    Both results are merged and reconstructed into the final nested structure.

    Args:
        transcript: Clinical consultation transcript
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)

    Returns:
        Extracted ophthalmology consultation data as JSON with nested structure

    Raises:
        Exception: If extraction fails
    """
    import time
    import asyncio
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting basic ophthalmology consultation using TWO-PART approach')

    try:
        user_prompt = OPHTHAL_USER_PROMPT.format(transcript=transcript)
        system_prompt = OPHTHAL_SYSTEM_PROMPT
        model = get_extraction_model_by_mode('default')  # Use model from processing_modes table

        # Check provider for routing
        from services.llm_client_factory import get_provider, generate_structured_output_parallel
        from services.schema_adapter import gemini_schema_to_json_schema
        provider = get_provider(model)

        if provider != "gemini":
            # === NON-GEMINI PATH (Claude/OpenAI) ===
            logger.debug(f"[LLM_ROUTING] Using {provider} provider with model: {model}")
            parallel_start_time = time.time()

            # Convert Gemini schemas to JSON Schema
            part1_json = gemini_schema_to_json_schema(OPHTHAL_PART1_SCHEMA)
            part2_json = gemini_schema_to_json_schema(OPHTHAL_PART2_SCHEMA)

            # Run parallel extraction via LLM factory
            part1_resp, part2_resp = await generate_structured_output_parallel(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema_part1=part1_json,
                json_schema_part2=part2_json,
                model=model,
                temperature=0.0,
            )

            parallel_duration = time.time() - parallel_start_time
            logger.info(f"[TIMING_LLM_API] ✅ PARALLEL extraction ({provider}): {parallel_duration:.2f}s (both parts)")

            # Data is already parsed in LLMResponse.data
            part1_data = part1_resp.data
            part2_data = part2_resp.data
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields, Part 2 extracted {len(part2_data)} fields")

            # Log usage for both parts using raw_response
            usage_data_p1 = log_extraction_usage(
                response=part1_resp.raw_response, model=model, api_duration_seconds=parallel_duration,
                call_subtype="ophthalmology_part1", consultation_type_code="OPHTHALMOLOGY",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4, user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p1)

            usage_data_p2 = log_extraction_usage(
                response=part2_resp.raw_response, model=model, api_duration_seconds=parallel_duration,
                call_subtype="ophthalmology_part2", consultation_type_code="OPHTHALMOLOGY",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4, user_prompt_tokens=len(user_prompt) // 4,
            )
            await log_llm_usage(usage_data_p2)

        else:
            # === GEMINI PATH (existing code) ===
            # Get or create cache for system prompt (used by BOTH Part 1 and Part 2)
            cache_name = get_or_create_cache(
                prompt_type=CACHE_KEY_OPHTHALMOLOGY,
                system_instruction=system_prompt,
                model=model,
                ttl_seconds=3600  # 1 hour
            )

            logger.debug(f"[GeminiService] Cache: {'enabled' if cache_name else 'disabled'}")

            # Build configs for both parts
            if cache_name:
                part1_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=OPHTHAL_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=OPHTHAL_PART2_SCHEMA,
                    temperature=0.0,
                )
            else:
                part1_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=OPHTHAL_PART1_SCHEMA,
                    temperature=0.0,
                )
                part2_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=OPHTHAL_PART2_SCHEMA,
                    temperature=0.0,
                )

            # ========== RUN BOTH PARTS IN PARALLEL ==========
            logger.debug("[GeminiService] Starting PARALLEL extraction: Part 1 (33 fields) + Part 2 (38 fields)...")
            parallel_start_time = time.time()

            async def extract_part1():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part1_config
                    ),
                    timeout=120.0
                )

            async def extract_part2():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part2_config
                    ),
                    timeout=120.0
                )

            try:
                part1_response, part2_response = await asyncio.gather(
                    extract_part1(),
                    extract_part2()
                )
                parallel_end_time = time.time()
                parallel_duration = parallel_end_time - parallel_start_time
                logger.info(f"[TIMING_GEMINI_API] ✅ PARALLEL extraction: {parallel_duration:.2f}s (both parts)")

                # Log usage for both parts
                usage_data_p1 = log_extraction_usage(
                    response=part1_response, model=model, api_duration_seconds=parallel_duration,
                    call_subtype="ophthalmology_part1", consultation_type_code="OPHTHALMOLOGY",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4, user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p1)

                usage_data_p2 = log_extraction_usage(
                    response=part2_response, model=model, api_duration_seconds=parallel_duration,
                    call_subtype="ophthalmology_part2", consultation_type_code="OPHTHALMOLOGY",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4, user_prompt_tokens=len(user_prompt) // 4,
                )
                await log_llm_usage(usage_data_p2)

            except asyncio.TimeoutError:
                logger.error("[GeminiService] Parallel extraction timed out after 120 seconds")
                error_usage = create_error_usage(
                    call_type="extraction", model=model, api_duration_seconds=120.0,
                    error_message="Timeout after 120s", call_subtype="ophthalmology_parallel",
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                )
                await log_llm_usage(error_usage)
                raise Exception("Parallel extraction timed out")
            except Exception as e:
                logger.error(f"[GeminiService] Parallel extraction failed: {type(e).__name__}: {str(e)}")
                raise Exception(_sanitize_error_message(str(e)))

            # Parse both responses with robust cleaning
            logger.debug("[GeminiService] Parsing Part 1 response...")
            part1_data = clean_and_parse_json(part1_response.text, context="OPHTHALMOLOGY Part 1")
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields")

            logger.debug("[GeminiService] Parsing Part 2 response...")
            part2_data = clean_and_parse_json(part2_response.text, context="OPHTHALMOLOGY Part 2")
            logger.debug(f"[GeminiService] Part 2 extracted {len(part2_data)} fields")

        # Merge and reconstruct nested structure
        logger.debug("[GeminiService] Merging Part 1 and Part 2 results...")
        formatted_result = format_ophthalmology_from_parts(part1_data, part2_data)
        logger.debug("[GeminiService] Two-part extraction successful!")

        # Filter out N/A values
        filtered_result = filter_na_values(formatted_result)
        logger.debug("[GeminiService] Filtered N/A values from formatted result")

        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting ophthalmology consultation (two-part): {e}")
        return {
            "error": f"Failed to parse ophthalmology consultation using two-part extraction: {_sanitize_error_message(str(e))}"
        }


async def extract_ophthal_full_consult_parameters_split(
    transcript: str,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract comprehensive ophthalmology consultation using TWO-PART extraction to avoid schema complexity limits.

    The flattened schema (118 properties) exceeds Gemini's constraint limits.
    This function splits the extraction into TWO separate API calls:

    PART 1 (65 fields): PATIENT DATA & PRIMARY EXAMINATION
    - Patient demographics, clinical history
    - Visual acuity and refraction (bilateral)
    - Keratometry (bilateral)
    - Cover tests (with/without glass)
    - Binocular vision tests
    - Macular function tests, PBCT charts, diplopia charting

    PART 2 (53 fields): ADVANCED EXAMINATION & MANAGEMENT
    - Dry eye assessment (11 fields)
    - Slit lamp examination (bilateral - 15 fields)
    - Intraocular pressure (8 fields + 4 pachymetry)
    - Gonioscopy, fundus examination (7 fields)
    - Diurnal IOP variation (4 parallel arrays)
    - Visual field analysis (8 fields)
    - Diagnosis, procedures, recommendations, notes

    Both results are merged and reconstructed into the final nested structure.

    Args:
        transcript: Comprehensive clinical consultation transcript
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)

    Returns:
        Extracted full ophthalmology consultation data as JSON with nested structure

    Raises:
        Exception: If extraction fails
    """
    import time
    import asyncio
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting full ophthalmology consultation using TWO-PART approach')

    try:
        user_prompt = OPHTHAL_FULL_USER_PROMPT.format(transcript=transcript)
        system_prompt = OPHTHAL_FULL_SYSTEM_PROMPT
        model = get_extraction_model_by_mode('default')  # Use model from processing_modes table

        # Check provider for routing
        from services.llm_client_factory import get_provider, generate_structured_output_parallel
        from services.schema_adapter import gemini_schema_to_json_schema
        provider = get_provider(model)

        if provider != "gemini":
            # === NON-GEMINI PATH (Claude/OpenAI) ===
            logger.debug(f"[LLM_ROUTING] Using {provider} provider with model: {model}")
            parallel_start_time = time.time()

            # Convert Gemini schemas to JSON Schema
            part1_json = gemini_schema_to_json_schema(OPHTHAL_FULL_PART1_SCHEMA)
            part2_json = gemini_schema_to_json_schema(OPHTHAL_FULL_PART2_SCHEMA)

            # Run parallel extraction via LLM factory
            part1_resp, part2_resp = await generate_structured_output_parallel(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema_part1=part1_json,
                json_schema_part2=part2_json,
                model=model,
                temperature=0.0,
            )

            parallel_duration = time.time() - parallel_start_time
            logger.info(f"[TIMING_LLM_API] ✅ PARALLEL extraction ({provider}): {parallel_duration:.2f}s (both parts)")

            # Data is already parsed in LLMResponse.data
            part1_data = part1_resp.data
            part2_data = part2_resp.data
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields, Part 2 extracted {len(part2_data)} fields")

            # Log usage for both parts using raw_response
            usage_data_p1 = log_extraction_usage(
                response=part1_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration / 2,
                call_subtype="ophthal_full_part1",
                consultation_type_code="OPHTHAL_FULL",
                template_code=None,
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4 if system_prompt else None,
                user_prompt_tokens=len(user_prompt) // 4 if user_prompt else None,
            )
            await log_llm_usage(usage_data_p1)

            usage_data_p2 = log_extraction_usage(
                response=part2_resp.raw_response,
                model=model,
                api_duration_seconds=parallel_duration / 2,
                call_subtype="ophthal_full_part2",
                consultation_type_code="OPHTHAL_FULL",
                template_code=None,
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4 if system_prompt else None,
                user_prompt_tokens=len(user_prompt) // 4 if user_prompt else None,
            )
            await log_llm_usage(usage_data_p2)

        else:
            # === GEMINI PATH (existing code) ===
            # Get or create cache for system prompt (used by BOTH Part 1 and Part 2)
            cache_name = get_or_create_cache(
                prompt_type=CACHE_KEY_OPHTHAL_FULL,
                system_instruction=system_prompt,
                model=model,
                ttl_seconds=3600  # 1 hour
            )

            logger.debug(f"[GeminiService] Cache: {'enabled' if cache_name else 'disabled'}")

            # Build Part 1 config with or without cache
            if cache_name:
                part1_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=OPHTHAL_FULL_PART1_SCHEMA,
                    temperature=0.0,
                )
            else:
                part1_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=OPHTHAL_FULL_PART1_SCHEMA,
                    temperature=0.0,
                )

            # Build Part 2 config with or without cache (SAME cache as Part 1!)
            if cache_name:
                part2_config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=OPHTHAL_FULL_PART2_SCHEMA,
                    temperature=0.0,
                )
            else:
                part2_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=OPHTHAL_FULL_PART2_SCHEMA,
                    temperature=0.0,
                )

            # ========== RUN BOTH PARTS IN PARALLEL ==========
            logger.debug("[GeminiService] Starting PARALLEL extraction: Part 1 (65 fields) + Part 2 (53 fields)...")
            parallel_start_time = time.time()

            async def extract_part1():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part1_config
                    ),
                    timeout=120.0
                )

            async def extract_part2():
                return await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                        config=part2_config
                    ),
                    timeout=120.0
                )

            try:
                part1_response, part2_response = await asyncio.gather(
                    extract_part1(),
                    extract_part2()
                )
                parallel_end_time = time.time()
                parallel_duration = parallel_end_time - parallel_start_time
                logger.info(f"[TIMING_GEMINI_API] ✅ PARALLEL extraction: {parallel_duration:.2f}s (both parts)")

                # Log usage for Part 1
                usage_data_p1 = log_extraction_usage(
                    response=part1_response,
                    model=model,
                    api_duration_seconds=parallel_duration / 2,  # Approximate per-part duration
                    call_subtype="ophthal_full_part1",
                    consultation_type_code="OPHTHAL_FULL",
                    template_code=None,
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4 if system_prompt else None,
                    user_prompt_tokens=len(user_prompt) // 4 if user_prompt else None,
                )
                await log_llm_usage(usage_data_p1)

                # Log usage for Part 2
                usage_data_p2 = log_extraction_usage(
                    response=part2_response,
                    model=model,
                    api_duration_seconds=parallel_duration / 2,  # Approximate per-part duration
                    call_subtype="ophthal_full_part2",
                    consultation_type_code="OPHTHAL_FULL",
                    template_code=None,
                    session_id=uuid_module.UUID(session_id) if session_id else None,
                    extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                    doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    system_prompt_tokens=len(system_prompt) // 4 if system_prompt else None,
                    user_prompt_tokens=len(user_prompt) // 4 if user_prompt else None,
                )
                await log_llm_usage(usage_data_p2)

            except asyncio.TimeoutError:
                logger.error("[GeminiService] PARALLEL extraction timed out after 120 seconds")
                # Log timeout error for both parts
                for subtype in ["ophthal_full_part1", "ophthal_full_part2"]:
                    error_usage = create_error_usage(
                        call_type="extraction",
                        call_subtype=subtype,
                        model=model,
                        error_message="Parallel extraction timed out after 120 seconds",
                        session_id=uuid_module.UUID(session_id) if session_id else None,
                        extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                        doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    )
                    await log_llm_usage(error_usage)
                raise Exception("PARALLEL extraction timed out")
            except Exception as e:
                logger.error(f"[GeminiService] PARALLEL extraction failed: {type(e).__name__}: {str(e)}")
                # Log error for both parts
                for subtype in ["ophthal_full_part1", "ophthal_full_part2"]:
                    error_usage = create_error_usage(
                        call_type="extraction",
                        call_subtype=subtype,
                        model=model,
                        error_message=str(e),
                        session_id=uuid_module.UUID(session_id) if session_id else None,
                        extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                        doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                    )
                    await log_llm_usage(error_usage)
                raise Exception(_sanitize_error_message(str(e)))

            logger.info(f"[TIMING_GEMINI_API] Both API calls: {parallel_duration:.2f}s total (PARALLEL)")

            # Parse both responses with robust cleaning
            logger.debug("[GeminiService] Parsing Part 1 response...")
            part1_data = clean_and_parse_json(part1_response.text, context="OPHTHAL_FULL Part 1")
            logger.debug(f"[GeminiService] Part 1 extracted {len(part1_data)} fields")

            logger.debug("[GeminiService] Parsing Part 2 response...")
            part2_data = clean_and_parse_json(part2_response.text, context="OPHTHAL_FULL Part 2")
            logger.debug(f"[GeminiService] Part 2 extracted {len(part2_data)} fields")

        # Merge and reconstruct nested structure
        logger.debug("[GeminiService] Merging Part 1 and Part 2 results...")
        formatted_result = format_ophthal_full_consult_from_parts(part1_data, part2_data)
        logger.debug("[GeminiService] Two-part extraction successful!")

        # Filter out N/A values
        filtered_result = filter_na_values(formatted_result)
        logger.debug("[GeminiService] Filtered N/A values from formatted result")

        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting full ophthalmology consultation (two-part): {e}")
        return {
            "error": f"Failed to parse full ophthalmology consultation using two-part extraction: {_sanitize_error_message(str(e))}"
        }


async def extract_ophthal_postop_rx(
    transcript: str,
    consultation_date: str = None,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract ophthalmology post-operative prescription schedule from voice transcript.

    This function extracts structured medication schedules including:
    - Frequency interpretation (e.g., "4 times a day" → specific times)
    - Duration to date conversion (e.g., "2 weeks" → exact date ranges)
    - Tapering schedules (creates separate rows for different phases)
    - Eye specification (Left Eye, Right Eye, Both Eyes)

    Args:
        transcript: Voice transcript text containing prescription instructions
        consultation_date: Surgery/consultation date in dd/mm/yy format (defaults to today)
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)

    Returns:
        Dict containing:
        - patientDetails: Patient identification
        - surgeryDetails: Surgery procedure information
        - medications: Array of medication rows with timings
        - generalInstructions: Post-op care instructions
        - followUp: Follow-up appointment details

    Raises:
        Exception: If extraction fails
    """
    import time
    import asyncio
    from datetime import datetime
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting ophthalmology post-operative prescription')

    # Default to today's date if not provided
    if not consultation_date:
        consultation_date = datetime.now().strftime("%d/%m/%y")

    try:
        user_prompt = OPHTHAL_POSTOP_RX_USER_PROMPT.format(
            transcript=transcript,
            consultation_date=consultation_date
        )
        system_prompt = OPHTHAL_POSTOP_RX_SYSTEM_PROMPT
        model = get_extraction_model_by_mode('default')  # Use model from processing_modes table

        # Get or create cache for system prompt
        cache_name = get_or_create_cache(
            prompt_type=CACHE_KEY_OPHTHAL_POSTOP_RX,
            system_instruction=system_prompt,
            model=model,
            ttl_seconds=3600  # 1 hour
        )

        logger.debug(f"[GeminiService] Cache: {'enabled' if cache_name else 'disabled'}")

        start_time = time.time()

        # Build config with or without cache
        if cache_name:
            config = types.GenerateContentConfig(
                cached_content=cache_name,
                response_mime_type="application/json",
                response_schema=OPHTHAL_POSTOP_RX_SCHEMA,
                temperature=0.0,
            )
        else:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=OPHTHAL_POSTOP_RX_SCHEMA,
                temperature=0.0,
            )

        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model,
                    contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                    config=config,
                ),
                timeout=120.0  # 2 minute timeout
            )
            end_time = time.time()
            api_duration = end_time - start_time
            logger.info(f"[TIMING_GEMINI_API] API call: {api_duration:.2f}s")

            # Log usage
            usage_data = log_extraction_usage(
                response=response,
                model=model,
                api_duration_seconds=api_duration,
                call_subtype="ophthal_postop_rx",
                consultation_type_code="OPHTHAL_POSTOP_RX",
                template_code=None,
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4 if system_prompt else None,
                user_prompt_tokens=len(user_prompt) // 4 if user_prompt else None,
            )
            await log_llm_usage(usage_data)

        except asyncio.TimeoutError:
            logger.error("[GeminiService] API call timed out after 120s")
            # Log timeout error
            error_usage = create_error_usage(
                call_type="extraction",
                call_subtype="ophthal_postop_rx",
                model=model,
                error_message="API call timed out after 120 seconds",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(error_usage)
            raise
        except Exception as e:
            logger.error(f"[GeminiService] API call failed: {type(e).__name__}: {str(e)}")
            # Log error
            error_usage = create_error_usage(
                call_type="extraction",
                call_subtype="ophthal_postop_rx",
                model=model,
                error_message=str(e),
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(error_usage)
            raise Exception(_sanitize_error_message(str(e)))

        # Parse response
        logger.debug("[GeminiService] Parsing response...")
        result = clean_and_parse_json(response.text, context="OPHTHAL_POSTOP_RX")

        # Count medications
        med_count = len(result.get('medications', []))
        logger.debug(f"[GeminiService] Extracted {med_count} medication rows")

        # Filter out N/A values
        filtered_result = filter_na_values(result)
        logger.debug("[GeminiService] Filtered N/A values from result")

        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting post-operative prescription: {e}")
        return {
            "error": f"Failed to parse post-operative prescription: {_sanitize_error_message(str(e))}"
        }


async def extract_ophthal_prescription(
    transcript: str,
    consultation_date: str = None,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract ophthalmology general prescription from voice transcript.

    This function extracts structured prescription data including:
    - Oral medications (capsules, tablets, syrups)
    - Topical medications (eye drops, ointments, gels)
    - Frequency and duration
    - Continuing medications from previous prescriptions
    - Special instructions

    Args:
        transcript: Voice transcript text containing prescription instructions
        consultation_date: Consultation date (defaults to today)
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)

    Returns:
        Dict containing:
        - patientDetails: Patient identification
        - prescriptionItems: Array of medication items
        - continuingMedications: Medications to continue from previous
        - additionalNotes: Extra instructions
        - doctorDetails: Doctor information
        - followUp: Follow-up details
        - pharmacyNote: Note for pharmacy

    Raises:
        Exception: If extraction fails
    """
    import time
    import asyncio
    from datetime import datetime
    import uuid as uuid_module
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug('[GeminiService] Extracting ophthalmology prescription')

    # Default to today's date if not provided
    if not consultation_date:
        consultation_date = datetime.now().strftime("%d/%m/%y")

    try:
        user_prompt = OPHTHAL_PRESCRIPTION_USER_PROMPT.format(
            transcript=transcript,
            consultation_date=consultation_date
        )
        system_prompt = OPHTHAL_PRESCRIPTION_SYSTEM_PROMPT
        model = get_extraction_model_by_mode('default')  # Use model from processing_modes table

        # Get or create cache for system prompt
        cache_name = get_or_create_cache(
            prompt_type=CACHE_KEY_OPHTHAL_PRESCRIPTION,
            system_instruction=system_prompt,
            model=model,
            ttl_seconds=3600  # 1 hour
        )

        logger.debug(f"[GeminiService] Cache: {'enabled' if cache_name else 'disabled'}")

        start_time = time.time()

        # Build config with or without cache
        if cache_name:
            config = types.GenerateContentConfig(
                cached_content=cache_name,
                response_mime_type="application/json",
                response_schema=OPHTHAL_PRESCRIPTION_SCHEMA,
                temperature=0.0,
            )
        else:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=OPHTHAL_PRESCRIPTION_SCHEMA,
                temperature=0.0,
            )

        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model,
                    contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
                    config=config,
                ),
                timeout=120.0  # 2 minute timeout
            )
            end_time = time.time()
            api_duration = end_time - start_time
            logger.info(f"[TIMING_GEMINI_API] API call: {api_duration:.2f}s")

            # Log usage
            usage_data = log_extraction_usage(
                response=response,
                model=model,
                api_duration_seconds=api_duration,
                call_subtype="ophthal_prescription",
                consultation_type_code="OPHTHAL_PRESCRIPTION",
                template_code=None,
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4 if system_prompt else None,
                user_prompt_tokens=len(user_prompt) // 4 if user_prompt else None,
            )
            await log_llm_usage(usage_data)

        except asyncio.TimeoutError:
            logger.error("[GeminiService] API call timed out after 120s")
            # Log timeout error
            error_usage = create_error_usage(
                call_type="extraction",
                call_subtype="ophthal_prescription",
                model=model,
                error_message="API call timed out after 120 seconds",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(error_usage)
            raise
        except Exception as e:
            logger.error(f"[GeminiService] API call failed: {type(e).__name__}: {str(e)}")
            # Log error
            error_usage = create_error_usage(
                call_type="extraction",
                call_subtype="ophthal_prescription",
                model=model,
                error_message=str(e),
                session_id=uuid_module.UUID(session_id) if session_id else None,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(error_usage)
            raise Exception(_sanitize_error_message(str(e)))

        # Parse response
        logger.debug("[GeminiService] Parsing response...")
        result = clean_and_parse_json(response.text, context="OPHTHAL_PRESCRIPTION")

        # Count prescription items
        item_count = len(result.get('prescriptionItems', []))
        continuing_count = len(result.get('continuingMedications', []))
        logger.debug(f"[GeminiService] Extracted {item_count} prescription items, {continuing_count} continuing medications")

        # Filter out N/A values
        filtered_result = filter_na_values(result)
        logger.debug("[GeminiService] Filtered N/A values from result")

        return filtered_result

    except Exception as e:
        logger.error(f"Error extracting prescription: {e}")
        return {
            "error": f"Failed to parse prescription: {_sanitize_error_message(str(e))}"
        }


# ============================================================================
# Transcription Methods (Home Tab - Live Recording & File Upload)
# ============================================================================

def _parse_language_tag(text: str) -> tuple:
    """Extract [DETECTED_LANG:LanguageName] tag from the first line of transcription.

    Returns:
        (cleaned_text, detected_language) — language is None if tag not found.
    """
    match = re.match(r'^\[DETECTED_LANG:([^\]]+)\]', text)
    if match:
        language = match.group(1).strip()
        cleaned = text[match.end():].lstrip('\n')
        return cleaned, language
    return text, None


async def detect_language_from_audio(
    audio_content: bytes,
    mime_type: str,
    model: str = 'gemini-2.5-flash',
    timeout_seconds: float = 30.0,
    session_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
) -> Optional[str]:
    """Detect the dominant spoken language from a short audio preview.

    Fast, minimal Gemini call intended for fire-and-forget use alongside
    transcription. Does NOT produce a transcript — only the language name.
    Runs out-of-band so it cannot destabilize the transcription prompt.

    Args:
        audio_content: Raw audio bytes (ideally a short preview — 20s or less)
        mime_type: Audio MIME type
        model: Gemini model to use
        timeout_seconds: Max wall time for the call
        session_id / doctor_id: Optional usage-tracking context

    Returns:
        Language name string (e.g., "Tamil", "Hindi", "English") or None
        on any failure. Never raises — always safe to call fire-and-forget.
    """
    import asyncio as _asyncio
    from services.llm_usage_service import log_llm_usage, LLMUsageData, create_error_usage
    import uuid as _uuid

    user_prompt = (
        "Identify the dominant spoken language in this audio clip. "
        "Focus on the PATIENT if multiple speakers are present. "
        'Respond with ONLY a JSON object: {"language": "LanguageName"} '
        "where LanguageName is one of: Tamil, Hindi, English, Telugu, "
        "Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Urdu, "
        "or another commonly spoken language. No commentary, no tags."
    )

    try:
        audio_part = types.Part.from_bytes(data=audio_content, mime_type=mime_type)
        api_start = time.time()
        response = await _asyncio.wait_for(
            client.aio.models.generate_content(
                model=model,
                contents=[{"role": "user", "parts": [{"text": user_prompt}, audio_part]}],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            ),
            timeout=timeout_seconds,
        )
        api_duration = time.time() - api_start

        # Log usage (non-blocking)
        try:
            usage = LLMUsageData(
                call_type="language_detection",
                call_subtype="audio_preview",
                model=model,
                api_duration_seconds=api_duration,
                audio_size_bytes=len(audio_content),
                prompt_token_count=getattr(response.usage_metadata, 'prompt_token_count', 0) if response.usage_metadata else 0,
                candidates_token_count=getattr(response.usage_metadata, 'candidates_token_count', 0) if response.usage_metadata else 0,
                session_id=_uuid.UUID(session_id) if session_id else None,
                doctor_id=_uuid.UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(usage)
        except Exception as log_e:
            logger.debug(f"[LANG_DETECT] Usage log failed (non-fatal): {log_e}")

        raw = (response.text or "").strip()
        if not raw:
            return None
        parsed = json.loads(raw)
        language = (parsed.get("language") or "").strip()
        if not language:
            return None
        logger.info(f"[LANG_DETECT] Detected language: {language} ({api_duration:.2f}s)")
        return language

    except _asyncio.TimeoutError:
        logger.warning(f"[LANG_DETECT] Detection timed out after {timeout_seconds}s")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"[LANG_DETECT] Non-JSON response: {e}")
        return None
    except Exception as e:
        logger.warning(f"[LANG_DETECT] Detection failed: {_sanitize_error_message(str(e))}")
        return None


async def transcribe_audio(
    audio_content: bytes,
    mime_type: str,
    model: str = 'gemini-2.5-flash',
    target_language: Optional[str] = None,
    timeout_seconds: float = 300.0,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    audio_duration_seconds: Optional[float] = None,
) -> tuple:
    """
    Transcribe audio using Gemini multimodal capabilities.

    For large audio files (>15MB), automatically uploads via Gemini Files API
    instead of sending inline, to avoid the 20MB inline request limit.
    Timeout is dynamically scaled based on audio duration.

    Args:
        audio_content: Raw audio bytes
        mime_type: Audio MIME type (e.g., 'audio/wav', 'audio/mp3')
        model: Gemini model to use
        target_language: Target language for transcription (None = original language, "English" = English)
        timeout_seconds: Timeout for the API call in seconds (default: 300s, auto-scaled for long audio)
        session_id: Recording session ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)
        audio_duration_seconds: Audio duration for cost calculation (optional, estimated from size if not provided)

    Returns:
        Tuple of (transcribed_text, detected_language). detected_language is None if not detected.

    Raises:
        Exception: If transcription fails or times out
    """
    import asyncio
    import time
    import uuid as uuid_module
    from io import BytesIO
    from services.llm_usage_service import log_transcription_usage, log_llm_usage, create_error_usage
    from services.supabase_service import get_transcription_prompt_with_fallback
    from services.audio_emotion_prompts import generate_transcription_user_prompt

    # Calculate audio size
    audio_size_bytes = len(audio_content)
    # Practical inline-data ceiling for Gemini transcription is far below the
    # documented 100 MB — base64 encoding inflates payloads by ~33% and the
    # gRPC request-size cap kicks in well before then. At 90 MB we observed
    # 400 INVALID_ARGUMENT for ~40 MB stitched recordings (and even ~25 MB
    # per-segment slices from the segment pipeline). 15 MB matches the
    # threshold already used in the skip-transcription path below (line ~4614)
    # and routes any non-trivial audio through the Files API which handles
    # arbitrarily large payloads cleanly.
    LARGE_FILE_THRESHOLD = 15 * 1024 * 1024  # 15MB

    # Estimate audio duration if not provided (rough estimate: ~16KB per second for WebM)
    if audio_duration_seconds is None:
        audio_duration_seconds = audio_size_bytes / 16000  # ~16KB/s for WebM audio

    # Dynamic timeout: scale with audio duration for long recordings
    # Base: 300s for ≤10 min, then +30s per extra minute, capped at 1800s (30 min)
    if audio_duration_seconds > 600:  # > 10 minutes
        extra_minutes = (audio_duration_seconds - 600) / 60
        timeout_seconds = max(timeout_seconds, min(300 + extra_minutes * 30, 1800))

    use_file_api = audio_size_bytes > LARGE_FILE_THRESHOLD
    logger.info(
        f'[GeminiService] Starting audio transcription '
        f'(size: {audio_size_bytes / 1024 / 1024:.1f}MB, '
        f'duration: {audio_duration_seconds:.0f}s, '
        f'timeout: {timeout_seconds:.0f}s, '
        f'method: {"Files API" if use_file_api else "inline"})'
    )

    audio_cleanup_handle = None  # Track for cleanup (files/<name> or gs://...)

    try:
        # Get system prompt from database
        try:
            prompt_data = get_transcription_prompt_with_fallback()
            system_prompt = prompt_data["system_prompt"]
            prompt_source = prompt_data["source"]
            logger.debug(f"[GeminiService] Using {prompt_source} transcription system prompt")
        except ValueError as e:
            logger.error(f"[GeminiService] Failed to get transcription prompt from database: {e}")
            raise Exception(f"Transcription prompt not configured: {e}")

        # Generate user prompt with target language
        user_prompt = generate_transcription_user_prompt(target_language)

        async def _do_call(force_files_api: bool):
            """Build the audio part and invoke generate_content. Returns (response, cleanup_handle).
            On exception, schedules cleanup of any uploaded artifact before re-raising."""
            # threshold_bytes=0 forces the Files-API/GCS path even for small payloads
            part_local, cleanup_local = await build_audio_part(
                audio_content,
                mime_type,
                threshold_bytes=0 if force_files_api else LARGE_FILE_THRESHOLD,
            )
            try:
                resp = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}, part_local]}],
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=0.1,
                        )
                    ),
                    timeout=timeout_seconds
                )
                return resp, cleanup_local
            except Exception:
                # Drop the uploaded artifact before propagating; retry will re-upload.
                if cleanup_local:
                    try:
                        asyncio.create_task(cleanup_audio_part(cleanup_local))
                    except Exception:
                        pass
                raise

        api_start_time = time.time()
        try:
            try:
                response, audio_cleanup_handle = await _do_call(force_files_api=False)
            except Exception as first_err:
                # Auto-retry inline INVALID_ARGUMENT via Files API. Catches:
                #  (a) gRPC payload-size edge for ~13–15MB inline (base64 inflates to ~20MB)
                #  (b) ephemeral Gemini-side rejections that don't repeat on a fresh upload
                # Only fires if the first call went inline AND we got INVALID_ARGUMENT —
                # genuine container-corruption is already gated upstream by the ffprobe check.
                msg = str(first_err)
                is_inline_call = not use_file_api
                is_invalid_arg = "INVALID_ARGUMENT" in msg or " 400 " in msg
                if is_inline_call and is_invalid_arg:
                    logger.warning(
                        f"[GeminiService] Inline transcription returned INVALID_ARGUMENT "
                        f"({audio_size_bytes / 1024 / 1024:.1f}MB). "
                        f"Auto-retrying via Files API."
                    )
                    response, audio_cleanup_handle = await _do_call(force_files_api=True)
                else:
                    raise
            api_duration = time.time() - api_start_time
            logger.info(f'[TIMING_TRANSCRIPTION] Gemini transcription: {api_duration:.2f}s (source: {prompt_source}, method: {"Files API" if use_file_api else "inline"})')

            # Log usage (fire-and-forget)
            usage_data = log_transcription_usage(
                response=response,
                model=model,
                api_duration_seconds=api_duration,
                audio_duration_seconds=audio_duration_seconds,
                audio_size_bytes=audio_size_bytes,
                session_id=uuid_module.UUID(session_id) if session_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(usage_data)

        except asyncio.TimeoutError:
            api_duration = time.time() - api_start_time
            logger.error(f'[GeminiService] Transcription API timed out after {api_duration:.2f}s (limit: {timeout_seconds}s)')

            # Log error usage
            error_usage = create_error_usage(
                call_type="transcription",
                model=model,
                api_duration_seconds=api_duration,
                error_message=f"Timeout after {timeout_seconds}s",
                call_subtype="audio_to_text",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(error_usage)

            raise Exception(f"Transcription timed out after {timeout_seconds} seconds. The audio may be too long or the API is overloaded. Please try again.")

        if not response.text:
            raise Exception('Failed to transcribe audio - no text returned.')

        # Hallucination guards. Two independent signals:
        #   (a) Absolute cap (>=60K tokens): Gemini's hard 65,536-token output ceiling
        #       almost always means a repetition loop filled the entire buffer.
        #   (b) Tokens-per-second ratio (>50): normal speech produces ~3-10 tok/sec of
        #       audio (empirical range across Indian-language + English consultations).
        #       A ratio >50 catches loops that produced huge output WITHOUT reaching
        #       the hard cap — e.g. 25K tokens for 30s audio is still garbage.
        out_tokens = (
            getattr(response.usage_metadata, 'candidates_token_count', 0) or 0
            if response.usage_metadata else 0
        )

        hit_cap = out_tokens >= 60000
        hit_ratio = False
        if audio_duration_seconds and audio_duration_seconds > 5 and out_tokens > 0:
            tok_per_sec = out_tokens / audio_duration_seconds
            if tok_per_sec > 50:
                hit_ratio = True
                logger.error(
                    f'[TRANSCRIPTION] Hallucination by ratio: {out_tokens} tokens '
                    f'for {audio_duration_seconds:.1f}s audio ({tok_per_sec:.1f} tok/sec; '
                    f'normal is 3-10). Rejecting.'
                )

        if hit_cap or hit_ratio:
            if hit_cap and not hit_ratio:
                logger.error(
                    f'[TRANSCRIPTION] Output-cap hallucination detected: '
                    f'{out_tokens} tokens (audio_duration={audio_duration_seconds}s). '
                    f'Transcript is almost certainly a repetition loop; rejecting.'
                )
            raise ValueError(
                'The audio may be unclear. Please re-record or reprocess.'
            )

        raw_text = response.text.strip()
        transcript, detected_language = _parse_language_tag(raw_text)
        if detected_language:
            logger.info(f'[GeminiService] Audio transcription successful. Detected language: {detected_language}')
        else:
            logger.info('[GeminiService] Audio transcription successful. No language tag detected.')
        return transcript, detected_language

    except asyncio.TimeoutError:
        raise  # Re-raise timeout errors
    except ValueError:
        # Transcription validation failures already have user-friendly messages
        # (e.g. from the output-cap hallucination guard). Don't wrap them.
        raise
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}")
        raise Exception(f"Failed to transcribe audio: {_sanitize_error_message(str(e))}")
    finally:
        # Clean up uploaded artifact (fire-and-forget, non-blocking)
        if audio_cleanup_handle:
            try:
                asyncio.create_task(cleanup_audio_part(audio_cleanup_handle))
            except Exception:
                pass  # Cleanup failure is non-fatal


def build_audio_extraction_user_prompt(
    doctor_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    has_medicine_list: bool = True,
    has_investigation_list: bool = True,
) -> str:
    """
    Build dynamic user prompt for direct audio extraction with all 5 injections:
    1. Medicine list (doctor-specific)
    2. Investigation list (doctor-specific)
    3. Caution/Warnings aggregation (patient history)
    4. Past prescriptions (patient history)
    5. Past summaries (patient history)

    Args:
        doctor_id: Doctor UUID string for medicine/investigation lists
        patient_id: Patient UUID string for historical context
        has_medicine_list: Whether doctor has medicine list configured
        has_investigation_list: Whether doctor has investigation list configured

    Returns:
        Dynamic user prompt string with all applicable injections
    """
    import uuid

    prompt_parts = [
        "Extract medical insights from this audio consultation in English.",
        "Return the extracted information as structured JSON according to the schema provided.",
        "Listen carefully to the entire audio and extract all relevant medical information.",
    ]

    # Injection 1: Medicine list (if doctor has one)
    if doctor_id and has_medicine_list:
        try:
            from services.medicine_service import get_medicine_list_for_prompt
            doctor_uuid = uuid.UUID(doctor_id) if isinstance(doctor_id, str) else doctor_id
            medicine_list = get_medicine_list_for_prompt(doctor_uuid)
            if medicine_list:
                prompt_parts.append(f"""
**MEDICINE MATCHING (CRITICAL):**
When extracting medicines for the prescription segment, follow these rules:

1. **MATCH FROM LIST FIRST**: For each medicine mentioned, find the closest match from the doctor's medicine list below. Account for:
   - Pronunciation variations (e.g., "amlo" → "AMLODIPINE", "glycomet" → "METFORMIN")
   - Abbreviated names (e.g., "telmi 40" → "TELMISARTAN 40MG")
   - Brand vs generic names (listed as "also:" alternatives)
   - Phonetic similarities (e.g., "azithro" → "AZITHROMYCIN")

2. **MATCH BOTH BRAND NAME AND FORM**: Each medicine entry has a `[Form]` tag (e.g., `[Tablet]`, `[Syrup]`, `[Capsule]`) indicating its dosage form. You MUST match based on BOTH the brand name AND the form mentioned by the doctor. Use the `[Form]` tag to disambiguate entries with the same brand. For example:
   - Doctor says "Dolo 650 tablet" → pick "DOLO 650 [Tablet]", NOT "DOLO 100 ML SYRUP [Syrup]"
   - Doctor says "Crocin syrup" → if no entry has a matching `[Syrup]` form for Crocin, output the spoken name "Crocin Syrup" verbatim. Do NOT pick "CROCIN 500 MG TABLETS [Tablet]" when the doctor clearly said syrup.
   - The form spoken by the doctor MUST match the `[Form]` tag of the selected entry. NEVER substitute a tablet for a syrup or vice versa.

3. **USE EXACT NAME FROM LIST**: If a close match is found, copy the COMPLETE medicine name exactly as it appears in the list — include everything before the `[Form]` tag and "(also:" part. Do NOT include the `[Form]` tag in the output. Do NOT truncate or remove any suffixes like "Kg TABLET" or "ML LIQUID". For example, if the list shows "T - CALPOL 650MG TAB  Kg TABLET [Tablet] (also: CALPOL, ...)", output exactly: "T - CALPOL 650MG TAB  Kg TABLET"

4. **NEW MEDICINES ONLY IF NO MATCH**: Only use the spoken medicine name verbatim if there is NO reasonable match in the list below. This includes cases where the brand exists but the form does not match (e.g., doctor says "syrup" but only a `[Tablet]` entry exists).

5. **FORM SELF-CHECK (MANDATORY)**: After selecting a medicine from the list, verify the `[Form]` tag matches what the doctor said:
   - Doctor said "syrup" but you picked a `[Tablet]` entry? WRONG — output the spoken name verbatim instead.
   - Doctor said "tablet" but you picked a `[Syrup]` entry? WRONG — output the spoken name verbatim instead.
   - If the form doesn't match ANY entry for that brand, output the spoken name verbatim.
   Also set the `dosage_form` field to what the doctor ACTUALLY SAID (e.g., "Syrup"), regardless of which list entry you matched.

{medicine_list}

**FORM REMINDER: A syrup is NEVER a tablet. A tablet is NEVER a syrup. The [Form] tag MUST match the form the doctor said. If in doubt, output the spoken name verbatim.**
""")
                logger.debug(f"[SKIP_TRANSCRIPTION] Injected medicine list ({len(medicine_list)} chars)")
        except Exception as e:
            logger.warning(f"[SKIP_TRANSCRIPTION] Failed to inject medicine list: {e}")

    # Injection 2: Investigation list (if doctor has one)
    if doctor_id and has_investigation_list:
        try:
            from services.investigation_service import get_investigation_list_for_prompt
            doctor_uuid = uuid.UUID(doctor_id) if isinstance(doctor_id, str) else doctor_id
            investigation_list = get_investigation_list_for_prompt(doctor_uuid)
            if investigation_list:
                prompt_parts.append(f"""
**INVESTIGATION MATCHING (CRITICAL):**
When extracting investigations, follow these rules:

1. **MATCH FROM LIST FIRST**: For each investigation mentioned, find the closest match from the doctor's investigation list below. Account for:
   - Abbreviations (e.g., "CBC" → "Complete Blood Count", "LFT" → "Liver Function Test")
   - Common names (e.g., "blood count" → "Complete Blood Count", "chest x-ray" → "X-Ray Chest PA View")
   - Phonetic similarities (e.g., "hemogram" → "Complete Blood Count")

2. **USE EXACT NAME FROM LIST**: If a close match is found, copy the COMPLETE investigation name exactly as it appears in the list - include everything before the "(also:" part. Do NOT truncate or modify the name. For example, if the list shows "Complete Blood Count (also: CBC, ...)", output exactly: "Complete Blood Count"

3. **NEW INVESTIGATIONS ONLY IF NO MATCH**: Only use the spoken investigation name verbatim if there is NO reasonable match in the list below.

{investigation_list}
""")
                logger.debug(f"[SKIP_TRANSCRIPTION] Injected investigation list ({len(investigation_list)} chars)")
        except Exception as e:
            logger.warning(f"[SKIP_TRANSCRIPTION] Failed to inject investigation list: {e}")

    # Injections 3-5: Patient context (cautions, past prescriptions, past summaries)
    if patient_id:
        try:
            from services.patient_context_service import (
                get_patient_context_for_extraction,
                format_patient_context_for_prompt
            )
            doctor_id_str = str(doctor_id) if doctor_id else None
            patient_context = get_patient_context_for_extraction(
                patient_id=patient_id,
                doctor_id=doctor_id_str,
                num_past_consultations=3  # Same as normal pipeline
            )
            if patient_context.get("has_context"):
                # This includes:
                # - Caution/Warnings aggregation (allergies with frequency)
                # - Past Prescriptions (last 3 consultations)
                # - Past Summaries (last 2 consultations)
                context_text = format_patient_context_for_prompt(patient_context)
                if context_text:
                    prompt_parts.append(context_text)
                    logger.debug(f"[SKIP_TRANSCRIPTION] Injected patient context ({len(context_text)} chars)")
        except Exception as e:
            logger.warning(f"[SKIP_TRANSCRIPTION] Failed to inject patient context: {e}")

    return "\n\n".join(prompt_parts)


async def extract_insights_from_audio_direct(
    audio_content: bytes,
    mime_type: str,
    system_prompt: str,
    response_schema: Dict[str, Any],
    model: str = "gemini-2.0-flash",
    timeout_seconds: float = 180.0,
    session_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    has_medicine_list: bool = False,
    has_investigation_list: bool = False,
    audio_duration_seconds: Optional[float] = None,
    template_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract medical insights directly from audio without transcription.

    Uses Gemini multimodal: audio + prompt + schema → structured JSON.
    This bypasses the transcription step for consultation types with skip_transcription enabled.

    Now includes all 5 prompt injections (same as normal pipeline):
    1. Medicine list (doctor-specific)
    2. Investigation list (doctor-specific)
    3. Caution/Warnings aggregation (patient history)
    4. Past prescriptions (patient history)
    5. Past summaries (patient history)

    Args:
        audio_content: Raw audio bytes
        mime_type: Audio MIME type (e.g., 'audio/wav', 'audio/webm')
        system_prompt: Pre-assembled system prompt from template
        response_schema: JSON schema dict for structured output
        model: Gemini model to use
        timeout_seconds: Timeout for the API call
        session_id: Recording session ID for usage tracking
        doctor_id: Doctor ID for list injection and usage tracking
        patient_id: Patient ID for historical context injection
        has_medicine_list: Whether doctor has medicine list configured
        has_investigation_list: Whether doctor has investigation list configured
        audio_duration_seconds: Audio duration for cost calculation
        template_code: Template code for logging

    Returns:
        Dict with extracted insights data

    Raises:
        Exception: If extraction fails or times out
    """
    import asyncio
    import time
    import json
    import uuid as uuid_module
    from services.llm_usage_service import log_llm_usage, create_error_usage, LLMUsageData

    from io import BytesIO

    # Calculate audio size
    audio_size_bytes = len(audio_content)
    LARGE_FILE_THRESHOLD = 15 * 1024 * 1024  # 15MB

    # Estimate audio duration if not provided
    if audio_duration_seconds is None:
        audio_duration_seconds = audio_size_bytes / 16000  # ~16KB/s for WebM audio

    # Dynamic timeout: scale with audio duration for long recordings
    if audio_duration_seconds > 600:
        extra_minutes = (audio_duration_seconds - 600) / 60
        timeout_seconds = max(timeout_seconds, min(300 + extra_minutes * 30, 1800))

    use_file_api = audio_size_bytes > LARGE_FILE_THRESHOLD
    logger.info(
        f'[TIMING_SKIP_TRANSCRIPTION] Starting direct audio extraction '
        f'(model: {model}, size: {audio_size_bytes / 1024 / 1024:.1f}MB, '
        f'timeout: {timeout_seconds:.0f}s, method: {"Files API" if use_file_api else "inline"})'
    )

    audio_cleanup_handle = None  # Track for cleanup (files/<name> or gs://...)

    try:
        audio_part, audio_cleanup_handle = await build_audio_part(
            audio_content,
            mime_type,
            threshold_bytes=LARGE_FILE_THRESHOLD,
        )

        # Build dynamic user prompt with all 5 injections
        user_prompt = build_audio_extraction_user_prompt(
            doctor_id=doctor_id,
            patient_id=patient_id,
            has_medicine_list=has_medicine_list,
            has_investigation_list=has_investigation_list,
        )

        # Convert schema dict to Gemini Schema if needed
        if isinstance(response_schema, dict):
            # Import the conversion function from segment_registry
            from services.segment_registry import _json_schema_to_gemini_schema
            gemini_schema = _json_schema_to_gemini_schema(response_schema)
        else:
            gemini_schema = response_schema

        api_start_time = time.time()
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model,
                    contents=[{"role": "user", "parts": [{"text": user_prompt}, audio_part]}],
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        response_schema=gemini_schema,
                        temperature=0.1,
                    )
                ),
                timeout=timeout_seconds
            )
            api_duration = time.time() - api_start_time
            logger.info(f'[TIMING_SKIP_TRANSCRIPTION] Direct extraction completed: {api_duration:.2f}s')

            # Log usage (fire-and-forget)
            usage_data = LLMUsageData(
                call_type="extraction",
                call_subtype="direct_audio_extraction",
                model=model,
                api_duration_seconds=api_duration,
                audio_duration_seconds=audio_duration_seconds,
                audio_size_bytes=audio_size_bytes,
                prompt_token_count=getattr(response.usage_metadata, 'prompt_token_count', 0) if response.usage_metadata else 0,
                candidates_token_count=getattr(response.usage_metadata, 'candidates_token_count', 0) if response.usage_metadata else 0,
                session_id=uuid_module.UUID(session_id) if session_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                template_code=template_code,
            )
            await log_llm_usage(usage_data)

        except asyncio.TimeoutError:
            api_duration = time.time() - api_start_time
            logger.error(f'[TIMING_SKIP_TRANSCRIPTION] Direct extraction timed out after {api_duration:.2f}s')

            # Log error usage
            error_usage = create_error_usage(
                call_type="extraction",
                model=model,
                api_duration_seconds=api_duration,
                error_message=f"Timeout after {timeout_seconds}s",
                call_subtype="direct_audio_extraction",
                session_id=uuid_module.UUID(session_id) if session_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(error_usage)

            raise Exception(f"Direct audio extraction timed out after {timeout_seconds} seconds.")

        if not response.text:
            raise Exception('Direct audio extraction failed - no response returned.')

        # Parse JSON response
        result = json.loads(response.text)

        logger.info(f'[TIMING_SKIP_TRANSCRIPTION] Direct extraction successful, got {len(result)} segments')
        return {"data": result, "model_used": model, "api_duration": api_duration}

    except asyncio.TimeoutError:
        raise
    except json.JSONDecodeError as e:
        logger.error(f"[TIMING_SKIP_TRANSCRIPTION] Error parsing JSON response: {e}")
        raise Exception(f"Failed to parse direct extraction results: {_sanitize_error_message(str(e))}")
    except Exception as e:
        logger.error(f"[TIMING_SKIP_TRANSCRIPTION] Error in direct audio extraction: {e}")
        raise Exception(f"Failed to extract insights from audio: {_sanitize_error_message(str(e))}")
    finally:
        if audio_cleanup_handle:
            try:
                asyncio.create_task(cleanup_audio_part(audio_cleanup_handle))
            except Exception:
                pass


async def extract_audio_only_emotions(
    audio_content: bytes,
    audio_mime_type: str,
    template_id: str,
    model: str = 'gemini-2.5-flash-preview',
    timeout_seconds: float = 120.0,
    session_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract emotions from audio ONLY (no transcript required).
    Used for skip_transcription mode where we bypass transcription.

    Uses pre-assembled AUDIO_* segment prompts from templates table.
    Outputs to unified emotion schema format for consistency with combined emotions.

    Args:
        audio_content: Raw audio bytes
        audio_mime_type: Audio MIME type (e.g., 'audio/mp3', 'audio/wav')
        template_id: Template UUID for prompt lookup
        model: Gemini model to use
        timeout_seconds: Timeout for the API call
        session_id: Recording session ID for usage tracking
        doctor_id: Doctor ID for usage tracking
        extraction_id: Medical extraction ID to link results to

    Returns:
        Dict with unified emotion segments:
        {
            "success": True,
            "unified_segments": {
                "ANXIETY_POST_CONSULTATION": {..., "source": "audio_only"},
                "FINANCIAL_CONCERNS": {..., "source": "audio_only"},
                ...
            },
            "metadata": {...}
        }
    """
    import asyncio
    import time
    import json
    import uuid as uuid_module
    from services.llm_usage_service import log_llm_usage, create_error_usage
    from services.supabase_service import get_audio_emotion_prompt_with_fallback

    logger.debug(f'[EMOTION:AUDIO_ONLY] Starting audio-only emotion extraction (timeout: {timeout_seconds}s)...')
    logger.debug(f'[EMOTION:AUDIO_ONLY] Audio size: {len(audio_content)} bytes, MIME: {audio_mime_type}')

    try:
        # Get audio-only emotion prompt and schema from database
        template_uuid = uuid_module.UUID(template_id) if isinstance(template_id, str) else template_id
        prompt_data = get_audio_emotion_prompt_with_fallback(template_uuid)

        if prompt_data is None:
            logger.warning(
                f"[EMOTION:AUDIO_ONLY] Audio emotion prompts not configured for template {template_id}. "
                f"Ensure AUDIO_* segments are activated."
            )
            return {
                "success": False,
                "error": "Audio emotion prompts not configured",
                "unified_segments": {},
                "metadata": {
                    "extraction_id": extraction_id,
                    "template_id": template_id,
                    "status": "skipped",
                    "reason": "prompts_not_configured"
                }
            }

        system_prompt = prompt_data["system_prompt"]
        response_schema = prompt_data.get("schema")
        prompt_source = prompt_data.get("source", "unknown")
        logger.debug(f"[EMOTION:AUDIO_ONLY] Using {prompt_source} prompt for template {template_id}")

        # Build user prompt for audio-only analysis
        user_prompt = """Analyze this medical consultation audio recording.

## Your Task:
Focus on VOCAL characteristics only - tone, pace, hesitations, tremors, and emotional indicators.

1. Listen for anxiety indicators: trembling voice, rapid speech, hesitations
2. Listen for financial stress: deflection when costs are mentioned, sighing, defensive tone
3. Listen for compliance indicators: enthusiasm vs reluctance, certainty vs doubt
4. Analyze doctor communication style: empathy, clarity, pacing

Note: Since there is no transcript for this analysis, only assess audio-level indicators.
Set text_level fields to null and mismatch fields to null (no text comparison possible)."""

        # Create audio part
        audio_part = types.Part.from_bytes(
            data=audio_content,
            mime_type=audio_mime_type
        )

        # Make API call
        api_start = time.time()
        try:
            if response_schema:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}, audio_part]}],
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            response_mime_type="application/json",
                            response_schema=response_schema,
                            temperature=0.1,
                        )
                    ),
                    timeout=timeout_seconds
                )
            else:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[{"role": "user", "parts": [{"text": user_prompt}, audio_part]}],
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            response_mime_type="application/json",
                            temperature=0.1,
                        )
                    ),
                    timeout=timeout_seconds
                )

            api_duration = time.time() - api_start
            logger.info(f'[EMOTION:AUDIO_ONLY] API call completed in {api_duration:.2f}s')

        except asyncio.TimeoutError:
            api_duration = time.time() - api_start
            logger.error(f'[EMOTION:AUDIO_ONLY] Timed out after {api_duration:.2f}s')
            return {
                "success": False,
                "error": f"Timeout after {timeout_seconds}s",
                "unified_segments": {},
                "metadata": {"extraction_id": extraction_id, "status": "timeout"}
            }

        if not response.text:
            logger.error('[EMOTION:AUDIO_ONLY] No response text returned')
            return {
                "success": False,
                "error": "No response text",
                "unified_segments": {},
                "metadata": {"extraction_id": extraction_id, "status": "empty_response"}
            }

        # Parse response
        try:
            segments = json.loads(response.text)
        except json.JSONDecodeError as e:
            logger.error(f'[EMOTION:AUDIO_ONLY] Failed to parse JSON response: {e}')
            return {
                "success": False,
                "error": f"JSON parse error: {str(e)}",
                "unified_segments": {},
                "metadata": {"extraction_id": extraction_id, "status": "parse_error"}
            }

        # Transform AUDIO_* segments to unified format for consistent UI/webhook display
        # Gemini returns: AUDIO_PATIENT_ANXIETY, AUDIO_FINANCIAL_CONCERNS, etc.
        # UI expects: ANXIETY_POST_CONSULTATION, FINANCIAL_CONCERNS, etc.
        from services.emotion_transformer import transform_audio_to_unified
        unified_segments = transform_audio_to_unified(segments)

        logger.debug(
            f'[EMOTION:AUDIO_ONLY] Successfully extracted {len(segments)} raw AUDIO_* segments, '
            f'transformed to {len(unified_segments)} unified segments'
        )

        return {
            "success": True,
            "unified_segments": unified_segments,
            "metadata": {
                "extraction_id": extraction_id,
                "template_id": template_id,
                "model": model,
                "api_duration_seconds": api_duration,
                "source": "audio_only",
                "prompt_source": prompt_source,
                "raw_segment_count": len(segments)
            }
        }

    except Exception as e:
        logger.error(f'[EMOTION:AUDIO_ONLY] Error in audio-only emotion extraction: {e}')
        return {
            "success": False,
            "error": _sanitize_error_message(str(e)),
            "unified_segments": {},
            "metadata": {"extraction_id": extraction_id, "status": "error"}
        }


async def generate_content_with_gemini(
    prompt: str,
    model: str = 'gemini-2.5-flash',
    temperature: float = 0.1
) -> str:
    """
    Generate content using Gemini with a text prompt.

    Args:
        prompt: The text prompt to send to Gemini
        model: Gemini model to use
        temperature: Temperature for generation (0.0-1.0)

    Returns:
        Generated text response

    Raises:
        Exception: If generation fails
    """
    logger.debug('[GeminiService] Generating content...')

    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            config=types.GenerateContentConfig(
                temperature=temperature,
            )
        )

        if not response.text:
            raise Exception('Failed to generate content - no text returned.')

        logger.debug('[GeminiService] Content generation successful.')
        return response.text.strip()

    except Exception as e:
        logger.error(f"Error generating content: {e}")
        raise Exception(f"Failed to generate content: {_sanitize_error_message(str(e))}")


async def generate_content(
    system_prompt: str,
    user_prompt: str,
    response_schema: types.Schema,
    model: str = 'gemini-2.5-flash',
    temperature: float = 0.1
) -> Dict[str, Any]:
    """
    Generate structured JSON content using Gemini with system instruction and response schema.

    This function is used for dynamic extraction with pre-generated prompts from the database.

    Args:
        system_prompt: System instruction for Gemini (segment extraction guidelines)
        user_prompt: User prompt with transcript
        response_schema: Gemini Schema object for structured output
        model: Gemini model to use (default: gemini-2.0-flash-exp)
        temperature: Temperature for generation (0.0-1.0)

    Returns:
        Parsed JSON dict with extracted medical data

    Raises:
        Exception: If generation or parsing fails
    """
    import json

    logger.debug(f'[GeminiService] Generating content with dynamic prompts using {model}...')

    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=temperature,
            )
        )

        if not response.text:
            raise Exception('Failed to generate content - no text returned.')

        # Parse JSON response
        result = json.loads(response.text)

        logger.debug('[GeminiService] Dynamic extraction successful.')
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON response: {e}")
        raise Exception(f"Failed to parse extraction results: {_sanitize_error_message(str(e))}")
    except Exception as e:
        logger.error(f"Error generating content with dynamic prompts: {e}")
        raise Exception(f"Failed to generate content: {_sanitize_error_message(str(e))}")


# ============================================================================
# Dynamic OP Summary Extraction (Database-Driven Segment Configuration)
# ============================================================================

def filter_na_values(data: Any) -> Any:
    """
    Recursively filter out N/A values from extracted data.

    Removes fields with the following values:
    - String "N/A" (case insensitive)
    - String "n/a"
    - None
    - Empty strings

    Args:
        data: Extracted data (dict, list, or primitive)

    Returns:
        Filtered data with N/A values removed
    """
    if isinstance(data, dict):
        filtered = {}
        for key, value in data.items():
            # Recursively filter the value
            filtered_value = filter_na_values(value)

            # Skip if value is N/A or None
            if filtered_value is None:
                continue
            if isinstance(filtered_value, str):
                if filtered_value.lower() in ["n/a", "na", "not available", ""]:
                    continue

            # Keep non-N/A values
            filtered[key] = filtered_value
        return filtered
    elif isinstance(data, list):
        # Filter each item in the list
        filtered_list = []
        for item in data:
            filtered_item = filter_na_values(item)
            # Skip None and N/A items
            if filtered_item is None:
                continue
            if isinstance(filtered_item, str):
                if filtered_item.lower() in ["n/a", "na", "not available", ""]:
                    continue
            filtered_list.append(filtered_item)
        return filtered_list
    else:
        # Return primitive values as-is
        return data


def _to_camel_case(snake_str: str) -> str:
    """Convert snake_case or space-separated string to camelCase"""
    import re
    components = re.split(r'[_\s]+', snake_str.lower())
    components = [c for c in components if c]
    if not components:
        return snake_str.lower()
    return components[0] + ''.join(x.title() for x in components[1:])


def reorder_by_display_order(extracted_data: Dict[str, Any], segments: list) -> Dict[str, Any]:
    """
    Reorder extracted data dict to match segment display_order.

    Args:
        extracted_data: Dict from Gemini with keys as camelCase segment codes
        segments: List of segment dicts with segment_code and display_order

    Returns:
        OrderedDict with keys sorted by display_order
    """
    if not segments or not extracted_data:
        return extracted_data

    # Build mapping: camelCase key -> display_order
    key_order = {}
    for seg in segments:
        segment_code = seg.get("segment_code", "")
        display_order = seg.get("display_order", 999)
        camel_key = _to_camel_case(segment_code)
        key_order[camel_key] = display_order

    # Sort extracted_data keys by display_order
    sorted_keys = sorted(
        extracted_data.keys(),
        key=lambda k: key_order.get(k, 999)
    )

    # Build ordered dict
    ordered_data = {}
    for key in sorted_keys:
        ordered_data[key] = extracted_data[key]

    return ordered_data


def _empty_value_for_schema(prop_schema: Any) -> Any:
    """Build an empty value matching a JSON Schema property's declared type.

    Why: When a required field is still absent after retry, persisting the wrong
    shape (e.g. ``""`` where downstream code expects a list) would crash callers.
    Type-aware empties keep the contract: arrays → [], objects → {sub: empty},
    primitives → "" / 0 / false, unknown → "".
    """
    if not isinstance(prop_schema, dict):
        return ""
    t = prop_schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), t[0] if t else None)
    if t == "array":
        return []
    if t == "object":
        sub_props = prop_schema.get("properties") or {}
        return {k: _empty_value_for_schema(v) for k, v in sub_props.items()}
    if t in ("number", "integer"):
        return 0
    if t == "boolean":
        return False
    return ""


async def _retry_missing_required_keys(
    json_schema: Dict[str, Any],
    extracted_data: Any,
    system_prompt: str,
    user_prompt: str,
    model: str,
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    template_code: Optional[str] = None,
) -> Any:
    """Re-prompt once for any required schema keys the LLM dropped, then merge.

    Why: Anthropic tool-use does not strictly enforce JSON Schema `required`,
    so models can occasionally omit fields entirely (observed: DIAGNOSIS missing
    on OP_CORE extractions). This guarantees the persisted output is the union
    of the first response and a single focused retry — one stitched extraction.
    How to apply: Called only when one or more required keys are absent from the
    parsed response. Bounded to a single retry; on failure, original is returned.
    """
    import time
    from services.llm_client_factory import generate_structured_output
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, get_thinking_budget

    if not isinstance(extracted_data, dict):
        return extracted_data

    required = json_schema.get("required") or []
    missing = [k for k in required if k not in extracted_data]
    if not missing:
        return extracted_data

    properties = json_schema.get("properties") or {}
    sub_properties = {k: properties[k] for k in missing if k in properties}
    if not sub_properties:
        logger.warning(
            f"[EXTRACTION] Required keys missing but no schema properties found for: {missing}. "
            f"Backfilling empty strings."
        )
        merged = dict(extracted_data)
        for k in missing:
            merged[k] = ""
        return merged

    sub_schema = {
        "type": "object",
        "properties": sub_properties,
        "required": list(sub_properties.keys()),
    }

    retry_user_prompt = (
        f"{user_prompt}\n\n"
        f"---\n"
        f"IMPORTANT: A previous extraction attempt did not return the following required fields: "
        f"{', '.join(missing)}. Re-extract ONLY these fields from the same transcript above. "
        f"For any field where no information is present in the transcript, return an empty value "
        f"(empty array [], empty string \"\", or an object with empty string fields). "
        f"Return ONLY a JSON object with these keys: {', '.join(sub_properties.keys())}."
    )

    logger.warning(
        f"[EXTRACTION] Required keys missing from LLM output: {missing}. Triggering single retry."
    )

    api_start = time.time()
    retry_data: Dict[str, Any] = {}
    retry_raw_response = None
    retry_succeeded = False
    try:
        retry_response = await generate_structured_output(
            system_prompt=system_prompt,
            user_prompt=retry_user_prompt,
            json_schema=sub_schema,
            model=model,
            temperature=0.2,
            thinking_budget=get_thinking_budget(model, "extraction"),
        )
        retry_raw_response = retry_response.raw_response
        if isinstance(retry_response.data, dict):
            retry_data = retry_response.data
            retry_succeeded = True
        else:
            logger.error(
                f"[EXTRACTION] Retry returned non-dict response; will backfill empties."
            )
    except Exception as e:
        logger.error(f"[EXTRACTION] Required-key retry call failed: {e}. Will backfill empties.")

    api_duration = time.time() - api_start

    if retry_raw_response is not None:
        try:
            usage_data = log_extraction_usage(
                response=retry_raw_response,
                model=model,
                api_duration_seconds=api_duration,
                call_subtype="dynamic_required_retry",
                template_code=template_code,
                session_id=uuid.UUID(session_id) if session_id else None,
                extraction_id=uuid.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid.UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(usage_data)
        except Exception as e:
            logger.warning(f"[EXTRACTION] Failed to log retry usage: {e}")

    merged = dict(extracted_data)
    for k, v in retry_data.items():
        if k in missing:
            merged[k] = v

    still_missing = [k for k in missing if k not in merged]
    backfilled: list = []
    for k in still_missing:
        merged[k] = _empty_value_for_schema(properties.get(k, {}))
        backfilled.append(k)

    filled_by_retry = [k for k in missing if k not in still_missing]
    if backfilled:
        logger.warning(
            f"[EXTRACTION] Backfilled empty values for required keys after retry "
            f"({'retry succeeded' if retry_succeeded else 'retry failed'}): {backfilled}. "
            f"Filled by retry: {filled_by_retry}. (retry took {api_duration:.2f}s)"
        )
    else:
        logger.info(
            f"[EXTRACTION] Retry filled missing required keys: {filled_by_retry} "
            f"(retry took {api_duration:.2f}s)"
        )
    return merged


async def extract_summary_dynamic(
    transcript: str,
    consultation_type_id: str,
    doctor_id: Optional[str] = None,
    template_code: Optional[str] = None,
    mode: str = "full",
    model: str = "gemini-2.5-flash",
    cached_artifacts: Optional[Dict[str, Any]] = None,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    # Patient context for history injection (optional)
    patient_id: Optional[str] = None,
    # List availability flags (skip injection if doctor/hospital has no lists)
    has_medicine_list: bool = True,
    has_investigation_list: bool = True,
    # Continuation support (optional, non-breaking)
    is_continuation: bool = False,
    parent_extraction_ids: Optional[list] = None,
    # Audio attachment for templates whose prompts depend on voice cues
    # (e.g. psychology screenings using voice-override-applied logic).
    # When provided AND provider == "gemini", the audio is attached to the
    # extraction call alongside the transcript-substituted user prompt.
    audio_content: Optional[bytes] = None,
    audio_mime_type: Optional[str] = None,
    # Recording metadata from /start (used for neonatal overrides like roomId/bedId)
    recording_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Extract medical consultation summary using database-driven segment configuration.

    This function dynamically generates prompts and schemas based on:
    - Consultation type (OP, DISCHARGE, RESPIRATORY, etc.)
    - User's segment configuration (CORE/ADDITIONAL/FULL)
    - Brevity level preferences (concise/balanced/detailed)
    - Terminology style preferences (medical_terms/simple_terms/as_spoken)
    - Patient history context (prescriptions, summaries, cautions)

    Args:
        transcript: Consultation transcript text
        consultation_type_id: Consultation type UUID (OP, DISCHARGE, RESPIRATORY, etc.)
        doctor_id: Doctor ID for personalized configuration (None = default config)
        template_code: Template code for template-specific configuration (optional, unique identifier)
        mode: 'core' | 'additional' | 'full'
        model: Gemini model to use (default: gemini-2.5-flash)
        cached_artifacts: Optional pre-generated artifacts from parallel processing
                         If provided, skips prompt generation step (fast path)
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        patient_id: Patient ID for injecting history context (prescriptions, summaries, caution)
        has_medicine_list: Whether doctor/hospital has medicine lists (skip injection if False)
        has_investigation_list: Whether doctor/hospital has investigation lists (skip injection if False)

    Returns:
        Dict with extracted insights and metadata (N/A values filtered)

    Raises:
        Exception: If extraction fails
    """
    from .segment_registry import generate_extraction_artifacts
    import uuid
    import time
    from services.llm_usage_service import log_extraction_usage, log_llm_usage, create_error_usage

    logger.debug(
        f'[GeminiService] Starting dynamic extraction '
        f'(consultation_type_id: {consultation_type_id}, mode: {mode}, '
        f'doctor_id: {doctor_id}, template_code: {template_code}, '
        f'cached_artifacts: {"present" if cached_artifacts else "absent"})'
    )

    try:
        # Convert consultation_type_id to UUID for lookups
        consultation_type_uuid = uuid.UUID(consultation_type_id) if isinstance(consultation_type_id, str) else consultation_type_id

        # =====================================================================
        # EARLY SPLIT TYPE DETECTION
        # Check template_code BEFORE generating artifacts to avoid waste
        # Split extraction types have complex schemas requiring two-part calls
        # =====================================================================

        if template_code in SPLIT_EXTRACTION_TYPES:
            logger.debug(f"[GeminiService] Split extraction type: {template_code} - bypassing artifact generation")

            # Fetch medicine list text for NEO templates that have medication fields
            medicine_list_text = ""
            if doctor_id and has_medicine_list:
                try:
                    from services.medicine_service import get_medicine_list_for_prompt
                    import uuid as _uuid_mod
                    _doc_uuid = _uuid_mod.UUID(doctor_id) if isinstance(doctor_id, str) else doctor_id
                    medicine_list_text = get_medicine_list_for_prompt(_doc_uuid) or ""
                    if medicine_list_text:
                        logger.debug(f"[GeminiService] Fetched medicine list for NEO prompt injection ({len(medicine_list_text)} chars)")
                except Exception as e:
                    logger.warning(f"[GeminiService] Failed to fetch medicine list for NEO injection: {e}")

            # Fetch investigation list text for NEO templates that have investigation fields
            investigation_list_text = ""
            if doctor_id and has_investigation_list:
                try:
                    from services.investigation_service import get_investigation_list_for_prompt
                    import uuid as _uuid_mod2
                    _doc_uuid2 = _uuid_mod2.UUID(doctor_id) if isinstance(doctor_id, str) else doctor_id
                    investigation_list_text = get_investigation_list_for_prompt(_doc_uuid2) or ""
                    if investigation_list_text:
                        logger.debug(f"[GeminiService] Fetched investigation list for NEO prompt injection ({len(investigation_list_text)} chars)")
                except Exception as e:
                    logger.warning(f"[GeminiService] Failed to fetch investigation list for NEO injection: {e}")

            if template_code == "NEO_PROFORMA":
                result = await extract_neo_proforma_parameters_split(transcript, medicine_list_text=medicine_list_text, investigation_list_text=investigation_list_text)
                result = apply_neonatal_patient_overrides(result, patient_id, template_code, recording_metadata=recording_metadata)
                return {
                    "data": result,
                    "metadata": {
                        "mode": mode,
                        "segment_count": 185,
                        "model": model,
                        "doctor_id": doctor_id,
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},
                        "extraction_method": "two-part"
                    }
                }

            elif template_code == "NEO_OP":
                result = await extract_neo_op_parameters_split(transcript, medicine_list_text=medicine_list_text, investigation_list_text=investigation_list_text)
                result = apply_neonatal_patient_overrides(result, patient_id, template_code, recording_metadata=recording_metadata)
                return {
                    "data": result,
                    "metadata": {
                        "mode": mode,
                        "segment_count": 125,
                        "model": model,
                        "doctor_id": doctor_id,
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},
                        "extraction_method": "two-part"
                    }
                }

            elif template_code == "OPHTHA_DISCHARGE":
                result = await extract_ophthal_discharge_parameters_split(transcript)
                return {
                    "data": result,
                    "metadata": {
                        "mode": mode,
                        "segment_count": 42,
                        "model": model,
                        "doctor_id": doctor_id,
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},
                        "extraction_method": "two-part"
                    }
                }

            elif template_code == "OPHTHAL_CONSULT_BRIEF":
                result = await extract_ophthalmology_parameters_split(transcript)
                return {
                    "data": result,
                    "metadata": {
                        "mode": mode,
                        "segment_count": 71,
                        "model": model,
                        "doctor_id": doctor_id,
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},
                        "extraction_method": "two-part"
                    }
                }

            elif template_code == "OPHTHAL_FULL_CONSULT":
                result = await extract_ophthal_full_consult_parameters_split(transcript)
                return {
                    "data": result,
                    "metadata": {
                        "mode": mode,
                        "segment_count": 118,
                        "model": model,
                        "doctor_id": doctor_id,
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},
                        "extraction_method": "two-part"
                    }
                }

            elif template_code == "NEO_DISCHARGE":
                result = await extract_neo_discharge_parameters_split(transcript, medicine_list_text=medicine_list_text, investigation_list_text=investigation_list_text)
                result = apply_neonatal_patient_overrides(result, patient_id, template_code, recording_metadata=recording_metadata)
                return {
                    "data": result,
                    "metadata": {
                        "mode": mode,
                        "segment_count": 85,
                        "model": model,
                        "doctor_id": doctor_id,
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},
                        "extraction_method": "two-part"
                    }
                }

            elif template_code == "NEO_ADMISSION":
                result = await extract_neo_admission_parameters_split(transcript, medicine_list_text=medicine_list_text, investigation_list_text=investigation_list_text)
                result = apply_neonatal_patient_overrides(result, patient_id, template_code, recording_metadata=recording_metadata)
                return {
                    "data": result,
                    "metadata": {
                        "mode": mode,
                        "segment_count": 130,
                        "model": model,
                        "doctor_id": doctor_id,
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},
                        "extraction_method": "two-part"
                    }
                }

            elif template_code == "NEO_DAILY":
                result = await extract_neo_daily_parameters_split(transcript, medicine_list_text=medicine_list_text, investigation_list_text=investigation_list_text)
                result = apply_neonatal_patient_overrides(result, patient_id, template_code, recording_metadata=recording_metadata)
                return {
                    "data": result,
                    "metadata": {
                        "mode": mode,
                        "segment_count": 125,
                        "model": model,
                        "doctor_id": doctor_id,
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},
                        "extraction_method": "two-part"
                    }
                }

            elif template_code == "NEO_DAILY_FREE":
                result = await extract_neo_daily_free_parameters(transcript, medicine_list_text=medicine_list_text, investigation_list_text=investigation_list_text)
                result = apply_neonatal_patient_overrides(result, patient_id, template_code, recording_metadata=recording_metadata)
                return {
                    "data": result,
                    "metadata": {
                        "mode": mode,
                        "segment_count": 17,
                        "model": model,
                        "doctor_id": doctor_id,
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},
                        "extraction_method": "single-call"
                    }
                }

            elif template_code == "NEO_PROFORMA_FREE":
                result = await extract_neo_proforma_free_parameters(transcript, medicine_list_text=medicine_list_text, investigation_list_text=investigation_list_text)
                result = apply_neonatal_patient_overrides(result, patient_id, template_code, recording_metadata=recording_metadata)
                return {
                    "data": result,
                    "metadata": {
                        "mode": mode,
                        "segment_count": 21,
                        "model": model,
                        "doctor_id": doctor_id,
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},
                        "extraction_method": "single-call"
                    }
                }

            elif template_code == "NEO_DISCHARGE_FREE":
                result = await extract_neo_discharge_free_parameters(transcript, medicine_list_text=medicine_list_text, investigation_list_text=investigation_list_text)
                result = apply_neonatal_patient_overrides(result, patient_id, template_code, recording_metadata=recording_metadata)
                return {
                    "data": result,
                    "metadata": {
                        "mode": mode,
                        "segment_count": 21,
                        "model": model,
                        "doctor_id": doctor_id,
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},
                        "extraction_method": "single-call"
                    }
                }

            elif template_code == "NEO_POSTNATAL_DAY_FREE":
                result = await extract_neo_postnatal_day_free_parameters(transcript, medicine_list_text=medicine_list_text, investigation_list_text=investigation_list_text)
                result = apply_neonatal_patient_overrides(result, patient_id, template_code, recording_metadata=recording_metadata)
                return {
                    "data": result,
                    "metadata": {
                        "mode": mode,
                        "segment_count": 9,
                        "model": model,
                        "doctor_id": doctor_id,
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},
                        "extraction_method": "single-call"
                    }
                }

            elif template_code == "NEO_POSTNATAL_DISCHARGE_FREE":
                result = await extract_neo_postnatal_discharge_free_parameters(transcript, medicine_list_text=medicine_list_text, investigation_list_text=investigation_list_text)
                result = apply_neonatal_patient_overrides(result, patient_id, template_code, recording_metadata=recording_metadata)
                return {
                    "data": result,
                    "metadata": {
                        "mode": mode,
                        "segment_count": 15,
                        "model": model,
                        "doctor_id": doctor_id,
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},
                        "extraction_method": "single-call"
                    }
                }

        # =====================================================================
        # NON-SPLIT TYPES: Generate artifacts for dynamic extraction
        # =====================================================================
        if cached_artifacts:
            logger.debug('[GeminiService] Using cached artifacts from parallel processing')
            artifacts = cached_artifacts
        else:
            doctor_uuid = uuid.UUID(doctor_id) if doctor_id else None

            # Generate dynamic prompts and schema
            # Include patient_id for history context injection (prescriptions, summaries, caution)
            # Include list availability flags to skip injection if doctor/hospital has no lists
            artifacts = generate_extraction_artifacts(
                consultation_type_id=consultation_type_uuid,
                doctor_id=doctor_uuid,
                template_code=template_code,
                mode=mode,
                transcript=transcript,
                patient_id=patient_id,
                has_medicine_list=has_medicine_list,
                has_investigation_list=has_investigation_list,
                is_continuation=is_continuation,
                parent_extraction_ids=parent_extraction_ids,
            )

        system_prompt = artifacts["system_prompt"]
        user_prompt = artifacts["user_prompt"]
        schema = artifacts["schema"]
        segment_count = artifacts["segment_count"]

        # Handle empty segments case (e.g., 'additional' mode with no segments)
        if segment_count == 0:
            logger.debug(f'[GeminiService] No segments found for mode={mode}, returning empty result')
            return {
                "data": {},
                "metadata": {
                    "mode": mode,
                    "segment_count": 0,
                    "model": model,
                    "doctor_id": doctor_id,
                    "validation": artifacts["validation"],
                    "message": "No segments configured for this mode"
                }
            }

        logger.debug(f'[GeminiService] Generated artifacts for {segment_count} segments')

        # Log schema details for debugging
        import json as json_module
        schema_str = str(schema)
        schema_size = len(schema_str)
        logger.debug(f'[GeminiService] Schema size: {schema_size} characters')
        logger.debug(f'[GeminiService] Schema properties count: {len(schema.properties) if hasattr(schema, "properties") else "N/A"}')

        # Log full schema for debugging (only in debug mode or for troubleshooting)
        try:
            # Convert Gemini Schema to dict for logging
            if hasattr(schema, 'to_dict'):
                schema_dict = schema.to_dict()
            else:
                schema_dict = {"type": str(schema.type), "properties_count": len(schema.properties) if hasattr(schema, "properties") else 0}
            logger.debug(f'[GeminiService] Full schema structure: {json_module.dumps(schema_dict, indent=2)}')
        except Exception as e:
            logger.warning(f'[GeminiService] Could not serialize schema for logging: {e}')

        # =====================================================================
        # MULTI-LLM ROUTING: Route to appropriate provider based on model name
        # =====================================================================
        from services.llm_client_factory import get_provider, generate_structured_output

        provider = get_provider(model)
        api_start_time = time.time()

        if provider != "gemini":
            # ===== NON-GEMINI PATH (Claude / OpenAI) =====
            logger.debug(f"[LLM_ROUTING] Using {provider} provider with model: {model}")

            # Get raw JSON schema from artifacts (added by segment_registry)
            json_schema = artifacts.get("json_schema")
            if not json_schema:
                raise Exception("No json_schema available in artifacts. Ensure template has assembled_schema_json.")

            # Call unified LLM factory
            from services.llm_usage_service import get_thinking_budget
            llm_response = await generate_structured_output(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema=json_schema,
                model=model,
                temperature=0.2,
                thinking_budget=get_thinking_budget(model, "extraction"),
            )
            api_duration = time.time() - api_start_time
            logger.info(f"[TIMING_LLM_API] extract_summary_dynamic: {api_duration:.2f}s (provider={provider}, model={model}, segments={segment_count})")

            # Log usage
            logger.debug(f"[USAGE] Token Usage ({provider}):")
            logger.debug(f"[USAGE]   Input tokens: {llm_response.input_tokens}")
            logger.debug(f"[USAGE]   Output tokens: {llm_response.output_tokens}")
            logger.debug(f"[USAGE]   Cached tokens: {llm_response.cached_tokens}")

            # Log usage to database
            consultation_type_code = artifacts.get("template_code") or template_code
            usage_data = log_extraction_usage(
                response=llm_response.raw_response,
                model=model,
                api_duration_seconds=api_duration,
                call_subtype=f"dynamic_{mode}",
                consultation_type_code=consultation_type_code,
                template_code=template_code,
                session_id=uuid.UUID(session_id) if session_id else None,
                extraction_id=uuid.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4 if system_prompt else None,
                user_prompt_tokens=len(user_prompt) // 4 if user_prompt else None,
            )
            await log_llm_usage(usage_data)

            # Data is already parsed by the factory
            extracted_data = llm_response.data

            extracted_data = await _retry_missing_required_keys(
                json_schema=json_schema,
                extracted_data=extracted_data,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                session_id=session_id,
                extraction_id=extraction_id,
                doctor_id=doctor_id,
                template_code=template_code,
            )

        else:
            # ===== GEMINI PATH (existing logic) =====
            # Build audio part if audio_content was provided. Used for templates
            # whose prompts depend on voice cues (psychology screenings etc.).
            # Falls back to text-only on any failure — extraction must not break.
            audio_part = None
            audio_cleanup_handle = None
            if audio_content and audio_mime_type:
                try:
                    audio_size_bytes = len(audio_content)
                    audio_part, audio_cleanup_handle = await build_audio_part(
                        audio_content,
                        audio_mime_type,
                    )
                    logger.info(
                        f"[EXTRACTION] Audio attached to extraction call "
                        f"({audio_size_bytes / 1024 / 1024:.1f}MB, mime={audio_mime_type}, "
                        f"method={'remote' if audio_cleanup_handle else 'inline'})"
                    )
                except Exception as audio_err:
                    logger.warning(
                        f"[EXTRACTION] Failed to attach audio (text-only fallback): {audio_err}"
                    )
                    audio_part = None
                    audio_cleanup_handle = None

            # contents is multimodal when audio_part was built; text-only otherwise
            if audio_part is not None:
                extraction_contents = [{"role": "user", "parts": [{"text": user_prompt}, audio_part]}]
            else:
                extraction_contents = user_prompt

            # Try to cache system prompt by template_code or consultation_type_code
            cache_key = get_template_cache_key(template_code) if template_code else f"CONSULT_{consultation_type_code}_{mode}"
            cache_name = get_or_create_cache(
                prompt_type=cache_key,
                system_instruction=system_prompt,
                model=model,
                ttl_seconds=3600  # 1 hour
            )

            # Get thinking budget from DB config
            from services.llm_usage_service import get_thinking_budget
            ext_budget = get_thinking_budget(model, "extraction")
            # Only set thinking_config when budget > 0 (capping). 0 or None = use Gemini default
            ext_thinking = types.ThinkingConfig(thinking_budget=ext_budget) if ext_budget and ext_budget > 0 else None

            # Build config with or without cache
            # max_output_tokens raised from Gemini default (8192) to 16384 to
            # accommodate long extractions where the per-segment string-encoded
            # JSON outputs can otherwise hit the cap and truncate mid-stream
            # (observed on Script 5.3 / 4573-char transcripts).
            if cache_name:
                logger.debug(f"[GeminiService] Using cached system prompt for '{cache_key}'")
                config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_schema=schema,
                    thinking_config=ext_thinking,
                    max_output_tokens=16384,
                )
            else:
                logger.debug("[GeminiService] Fallback: Using non-cached system prompt")
                config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_schema=schema,
                    thinking_config=ext_thinking,
                    max_output_tokens=16384,
                )

            # Call Gemini with dynamic configuration (150s timeout, retry on transient failures)
            max_retries = 2
            for attempt in range(1, max_retries + 1):
                try:
                    api_start_time = time.time()
                    response = await asyncio.wait_for(
                        client.aio.models.generate_content(
                            model=model,
                            contents=extraction_contents,
                            config=config
                        ),
                        timeout=150.0
                    )
                    break  # Success — exit retry loop
                except (asyncio.TimeoutError, httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout, genai_errors.APIError) as retry_err:
                    api_duration = time.time() - api_start_time
                    # Classify: 429/RESOURCE_EXHAUSTED is retryable with longer backoff;
                    # other APIError subtypes (auth, invalid request, 5xx other than transient) are not.
                    is_rate_limit = False
                    if isinstance(retry_err, genai_errors.APIError):
                        err_str = str(retry_err)
                        if getattr(retry_err, "code", None) == 429 or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                            is_rate_limit = True
                            err_label = "Rate limit"
                        else:
                            raise
                    elif isinstance(retry_err, asyncio.TimeoutError):
                        err_label = "Timeout"
                    else:
                        err_label = "Connection issue"
                    if attempt < max_retries:
                        # Rate-limit quotas typically reset within ~60s — back off longer than for connection blips
                        backoff = attempt * 10 if is_rate_limit else attempt * 3  # 10s/20s vs 3s/6s
                        logger.warning(
                            f"[EXTRACTION_RETRY] Attempt {attempt}/{max_retries} failed "
                            f"({err_label}, {api_duration:.1f}s). Retrying in {backoff}s..."
                        )
                        # Log retry attempt to usage log
                        error_usage = create_error_usage(
                            call_type="extraction",
                            call_subtype=f"dynamic_{mode}_retry{attempt}",
                            model=model,
                            error_message=f"AI service {err_label.lower()} after {api_duration:.1f}s (attempt {attempt}, will retry)",
                            api_duration_seconds=api_duration,
                            session_id=uuid.UUID(session_id) if session_id else None,
                            extraction_id=uuid.UUID(extraction_id) if extraction_id else None,
                            doctor_id=uuid.UUID(doctor_id) if doctor_id else None,
                        )
                        await log_llm_usage(error_usage)
                        await asyncio.sleep(backoff)
                    else:
                        logger.error(
                            f"[EXTRACTION_RETRY] All {max_retries} attempts failed "
                            f"({err_label}, {api_duration:.1f}s). Giving up."
                        )
                        raise  # Re-raise to outer handler

            api_duration = time.time() - api_start_time
            logger.info(f"[TIMING_GEMINI_API] extract_summary_dynamic: {api_duration:.2f}s (model={model}, segments={segment_count})")

            # Cleanup uploaded audio (fire-and-forget) — only when remote upload was used
            if audio_cleanup_handle:
                try:
                    asyncio.create_task(cleanup_audio_part(audio_cleanup_handle))
                except Exception:
                    pass

            # Log usage metadata for token tracking (cached vs non-cached)
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                logger.debug(f"[USAGE] Token Usage for '{cache_key}':")
                logger.debug(f"[USAGE]   Prompt tokens: {getattr(usage, 'prompt_token_count', 'N/A')}")
                logger.debug(f"[USAGE]   Cached tokens: {getattr(usage, 'cached_content_token_count', 0)}")
                logger.debug(f"[USAGE]   Output tokens: {getattr(usage, 'candidates_token_count', 'N/A')}")
                logger.debug(f"[USAGE]   Total tokens: {getattr(usage, 'total_token_count', 'N/A')}")

                # Calculate cache hit ratio
                prompt_tokens = getattr(usage, 'prompt_token_count', 0) or 0
                cached_tokens = getattr(usage, 'cached_content_token_count', 0) or 0
                if prompt_tokens > 0:
                    cache_ratio = (cached_tokens / prompt_tokens) * 100
                    logger.debug(f"[USAGE]   Cache hit ratio: {cache_ratio:.1f}%")

            # Log usage to database (fire-and-forget)
            consultation_type_code = artifacts.get("template_code") or template_code
            usage_data = log_extraction_usage(
                response=response,
                model=model,
                api_duration_seconds=api_duration,
                call_subtype=f"dynamic_{mode}",
                consultation_type_code=consultation_type_code,
                template_code=template_code,
                session_id=uuid.UUID(session_id) if session_id else None,
                extraction_id=uuid.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid.UUID(doctor_id) if doctor_id else None,
                system_prompt_tokens=len(system_prompt) // 4 if system_prompt else None,
                user_prompt_tokens=len(user_prompt) // 4 if user_prompt else None,
            )
            await log_llm_usage(usage_data)

            if not response.text:
                raise Exception('No response text from AI service')

            # Detect MAX_TOKENS truncation so callers can investigate /
            # bump the cap. The outer JSON often parses (clean_and_parse_json
            # auto-closes braces) but inner per-segment string values can be
            # cut mid-stream, leaving them as malformed JSON downstream.
            try:
                if response.candidates:
                    finish = response.candidates[0].finish_reason
                    finish_name = getattr(finish, 'name', str(finish)) if finish is not None else ''
                    if finish_name == 'MAX_TOKENS':
                        logger.warning(
                            f"[TRUNCATION] Extraction hit MAX_TOKENS for "
                            f"template={template_code} mode={mode} "
                            f"(transcript={len(transcript)} chars, response={len(response.text)} chars). "
                            f"Some segment values may be truncated; consider raising max_output_tokens "
                            f"or splitting the segment schema."
                        )
            except Exception:
                pass

            # Parse JSON response with robust cleaning
            extracted_data = clean_and_parse_json(response.text, context="extract_summary_dynamic")

        # NOTE: reorder_by_display_order commented out for performance optimization.
        # JSON key order is cosmetic; frontend can reorder if needed.
        # This eliminates dependency on loading full segment definitions.
        #
        # segments = artifacts.get("segments", [])
        # if segments:
        #     extracted_data = reorder_by_display_order(extracted_data, segments)
        #     logger.info(f'[GeminiService] Reordered {len(extracted_data)} segments by display_order')

        # Derive segment_count from extracted data (not from loaded segments)
        actual_segment_count = len(extracted_data) if isinstance(extracted_data, dict) else 0

        # Apply patient data overrides for neonatal types
        artifact_template_code = artifacts.get("template_code") or template_code
        if artifact_template_code in NEONATAL_OVERRIDE_TYPES:
            extracted_data = apply_neonatal_patient_overrides(extracted_data, patient_id, artifact_template_code, recording_metadata=recording_metadata)

        return {
            "data": extracted_data,
            "metadata": {
                "mode": mode,
                "segment_count": actual_segment_count,
                "model": model,
                "doctor_id": doctor_id,
                "validation": artifacts["validation"]
            },
            "excluded_segment_codes": artifacts.get("excluded_segment_codes", set())  # For response filtering
        }

    except asyncio.TimeoutError:
        logger.error(f"[EXTRACTION] AI service timed out after 150s (dynamic extraction, segments={segment_count}) — all retries exhausted")
        # Log final timeout to usage log for observability
        try:
            error_usage = create_error_usage(
                call_type="extraction",
                call_subtype=f"dynamic_{mode}",
                model=model,
                error_message=f"AI service timeout after 150s (all retries exhausted, segments={segment_count})",
                api_duration_seconds=150.0,
                session_id=uuid.UUID(session_id) if session_id else None,
                extraction_id=uuid.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid.UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(error_usage)
        except Exception:
            pass  # Usage logging failure is non-fatal
        raise Exception("AI service timed out after 150 seconds - please retry")
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        raise Exception(f"Failed to parse AI response as JSON: {str(e)}")
    except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
        # Transient network errors — already retried above, log final failure
        logger.warning(f"[EXTRACTION] AI service connection issue (all retries exhausted)")
        try:
            error_usage = create_error_usage(
                call_type="extraction",
                call_subtype=f"dynamic_{mode}",
                model=model,
                error_message="AI service connection issue (all retries exhausted)",
                session_id=uuid.UUID(session_id) if session_id else None,
                extraction_id=uuid.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid.UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(error_usage)
        except Exception:
            pass
        raise Exception("AI service temporarily unavailable - please retry")
    except Exception as e:
        # Check if it's a wrapped httpx error
        error_msg = str(e)
        if "Server disconnected" in error_msg or "RemoteProtocolError" in error_msg:
            logger.warning(f"[EXTRACTION] ⚠️ Gemini API connection issue (transient): {error_msg}")
            raise Exception("AI service temporarily unavailable - please retry")
        logger.error(f"Error in dynamic summary extraction: {e}")
        raise Exception(f"Failed to extract summary: {_sanitize_error_message(str(e))}")


# =============================================================================
# COMBINED EMOTION EXTRACTION (Single Multimodal Call)
# =============================================================================

# =============================================================================
# COMBINED EMOTION EXTRACTION (Multimodal Text + Audio)
# =============================================================================
# NOTE: Combined emotion prompts and schemas are stored in the database:
# - Base prompt: system_prompt_components.COMBINED_EMOTION_BASE_PROMPT
# - Segment prompts/schemas: segment_definitions.COMBINED_*
# - Pre-assembled: templates.assembled_combined_emotion_*
#
# NO hardcoded fallback - if database retrieval fails, emotion analysis is skipped.
# =============================================================================


async def extract_combined_emotions(
    audio_content: bytes,
    audio_mime_type: str,
    transcript: str,
    template_id: str,
    model: str = 'gemini-2.5-flash-preview',
    timeout_seconds: float = 120.0,
    session_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Single multimodal Gemini call for combined text + audio emotion analysis.

    This replaces the previous 2-3 step process (text extraction + audio extraction + congruence)
    with a single API call that analyzes both inputs simultaneously.

    Args:
        audio_content: Raw audio bytes
        audio_mime_type: Audio MIME type (e.g., 'audio/mp3', 'audio/wav')
        transcript: Full consultation transcript text
        template_id: Template UUID (used for future prompt customization)
        model: Gemini model to use (default: gemini-2.5-flash-preview for multimodal)
        timeout_seconds: Timeout for the API call
        session_id: Recording session ID for usage tracking
        doctor_id: Doctor ID for usage tracking
        extraction_id: Medical extraction ID to link results to

    Returns:
        Dict with unified emotion segments directly:
        {
            "success": True,
            "unified_segments": {
                "ANXIETY_POST_CONSULTATION": {...},
                "FINANCIAL_CONCERNS": {...},
                "OTHER_EMOTIONS_DETECTED": {...},
                "TREATMENT_COMPLIANCE_LIKELIHOOD": {...},
                "DOCTOR_COMMUNICATION_STYLE": {...}
            },
            "metadata": {...}
        }

    Note:
        Output format matches the unified segment schema used by downstream consumers
        (intervention_orchestrator, retention_interventions_service, webhooks).
        All segments include text_level, audio_level, and mismatch fields.
    """
    import asyncio
    import time
    import json
    import uuid as uuid_module
    from services.llm_usage_service import log_llm_usage, create_error_usage
    from services.supabase_service import get_combined_emotion_prompt

    logger.debug(f'[EMOTION:COMBINED] Starting combined emotion extraction (timeout: {timeout_seconds}s)...')
    logger.debug(f'[EMOTION:COMBINED] Audio size: {len(audio_content)} bytes, MIME: {audio_mime_type}')
    logger.debug(f'[EMOTION:COMBINED] Transcript length: {len(transcript)} chars')

    try:
        # Get prompt and schema from database (NO fallback - will skip if not available)
        template_uuid = uuid_module.UUID(template_id) if isinstance(template_id, str) else template_id
        prompt_data = get_combined_emotion_prompt(template_uuid)

        if prompt_data is None:
            # No prompt available in database - skip emotion analysis gracefully
            logger.warning(
                f"[EMOTION:COMBINED] Emotion analysis skipped - combined emotion prompts not configured in database. "
                f"Run the 20260110160000_combined_emotion_prompts.sql migration to set up prompts."
            )
            return {
                "success": False,
                "error": "Combined emotion prompts not configured in database",
                "unified_segments": {},
                "metadata": {
                    "extraction_id": extraction_id,
                    "template_id": template_id,
                    "status": "skipped",
                    "reason": "prompts_not_configured"
                }
            }

        system_prompt = prompt_data["system_prompt"]
        response_schema = prompt_data["schema"]
        prompt_source = prompt_data["source"]
        logger.debug(f"[EMOTION:COMBINED] Using {prompt_source} prompt for template {template_id}")

        # Build user prompt with transcript context
        user_prompt = f"""Analyze this medical consultation using BOTH the transcript text AND the audio recording.

## Transcript:
{transcript}

## Your Task:
1. Analyze the TEXT content for what was explicitly said
2. Analyze the AUDIO for how it was said (voice characteristics)
3. Detect mismatches between text and audio assessments
4. Provide combined assessments for each category

Remember: Mismatches are clinically significant - they may reveal hidden anxiety, financial stress, or compliance concerns."""

        # Create audio part
        audio_part = types.Part.from_bytes(
            data=audio_content,
            mime_type=audio_mime_type
        )

        api_start_time = time.time()

        # Try to cache the emotion system prompt (saves ~90% on input tokens)
        cache_name = None
        try:
            from services.gemini_cache_service import get_or_create_cache
            cache_name = get_or_create_cache(
                prompt_type=f"EMOTION_COMBINED_{template_id}",
                system_instruction=system_prompt,
                model=model,
                ttl_seconds=3600
            )
        except Exception as cache_err:
            logger.debug(f"[EMOTION:COMBINED] Cache setup skipped: {cache_err}")

        try:
            if cache_name:
                config = types.GenerateContentConfig(
                    cached_content=cache_name,
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                )
            else:
                config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                )

            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model,
                    contents=[{"role": "user", "parts": [{"text": user_prompt}, audio_part]}],
                    config=config,
                ),
                timeout=timeout_seconds
            )
            api_duration = time.time() - api_start_time
            logger.info(f'[TIMING_EMOTION] Combined emotion extraction: {api_duration:.2f}s (source: {prompt_source}, cached={cache_name is not None})')

        except asyncio.TimeoutError:
            api_duration = time.time() - api_start_time
            logger.error(f'[EMOTION:COMBINED] Extraction timed out after {api_duration:.2f}s')
            raise Exception(f"Combined emotion extraction timed out after {timeout_seconds} seconds.")

        if not response.text:
            raise Exception('Failed to extract combined emotions - no response returned.')

        # Log LLM usage for emotion extraction (with audio cost estimation)
        audio_size = len(audio_content)
        estimated_audio_duration = audio_size / 16000  # ~16KB/s for WebM audio
        try:
            from services.llm_usage_service import log_emotion_usage
            usage_data = log_emotion_usage(
                response=response,
                model=model,
                api_duration_seconds=api_duration,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                session_id=uuid_module.UUID(session_id) if session_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
                audio_duration_seconds=estimated_audio_duration,
                audio_size_bytes=audio_size,
            )
            await log_llm_usage(usage_data)
            logger.debug(f"[EMOTION:COMBINED] Logged LLM usage: {usage_data.total_token_count} tokens, ${usage_data.total_cost_usd:.4f}")
        except Exception as e:
            logger.warning(f"[EMOTION:COMBINED] Failed to log LLM usage: {e}")

        # Parse JSON response
        try:
            result = json.loads(response.text)
        except json.JSONDecodeError as e:
            logger.warning(f'[EMOTION:COMBINED] Failed to parse response: {e}. Returning empty segments.')
            return {
                "success": True,
                "unified_segments": _get_empty_unified_segments(),
                "metadata": {
                    "extraction_id": extraction_id,
                    "template_id": template_id,
                    "model": model,
                    "api_duration_seconds": api_duration,
                    "status": "completed_with_fallback",
                    "fallback_reason": f"JSON parse error: {str(e)[:100]}"
                }
            }

        # Add source field and calculate combined scores
        unified_segments = _enrich_combined_segments(result)

        logger.debug(f'[EMOTION:COMBINED] Extraction successful: {len(unified_segments)} segments')

        # Log any mismatches detected
        mismatch_count = sum(1 for seg in unified_segments.values()
                           if isinstance(seg, dict) and seg.get("mismatch", False))
        if mismatch_count > 0:
            logger.debug(f'[EMOTION:COMBINED] Detected {mismatch_count} text-audio mismatches')

        return {
            "success": True,
            "unified_segments": unified_segments,
            "metadata": {
                "extraction_id": extraction_id,
                "template_id": template_id,
                "model": model,
                "api_duration_seconds": api_duration,
                "mismatch_count": mismatch_count,
                "status": "completed"
            }
        }

    except asyncio.TimeoutError:
        raise
    except Exception as e:
        error_detail = str(e) or f"{type(e).__name__} (no message)"
        logger.error(f"[EMOTION:COMBINED] Combined emotion extraction failed: {error_detail}", exc_info=True)
        raise Exception(f"Combined emotion extraction failed: {_sanitize_error_message(error_detail)}")


def _get_empty_unified_segments() -> Dict[str, Any]:
    """Return empty unified segments structure for fallback cases."""
    return {
        "ANXIETY_POST_CONSULTATION": {
            "pre_consultation": {"level": "None", "text_level": "None", "audio_level": "None", "mismatch": False},
            "post_consultation": {"level": "None", "text_level": "None", "audio_level": "None", "mismatch": False},
            "trajectory": {"trajectory": "Stable"},
            "source": "combined",
            "mismatch": False
        },
        "FINANCIAL_CONCERNS": {
            "concerns_present": False,
            "severity": "None",
            "text_severity": "None",
            "audio_severity": "None",
            "mismatch": False,
            "source": "combined"
        },
        "OTHER_EMOTIONS_DETECTED": {
            "emotions_detected": [],
            "dominant_emotion": "None",
            "mismatch": False,
            "source": "combined"
        },
        "TREATMENT_COMPLIANCE_LIKELIHOOD": {
            "likelihood": "Moderate",
            "text_likelihood": "Moderate",
            "audio_likelihood": "Moderate",
            "mismatch": False,
            "source": "combined"
        },
        "DOCTOR_COMMUNICATION_STYLE": {
            "primary_style": "Clinical",
            "mismatch": False,
            "source": "combined"
        }
    }


def _enrich_combined_segments(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich combined segments with source field and calculate combined scores.

    Adds:
    - source: "combined" to all segments
    - combined_score: Numeric score for severity/level fields
    - Ensures mismatch field exists
    """
    severity_score_map = {
        "none": 0.0, "mild": 0.33, "moderate": 0.66, "severe": 1.0
    }
    likelihood_score_map = {
        "very low": 0.1, "low": 0.3, "moderate": 0.6, "high": 0.9
    }

    def get_score(level: Optional[str], score_map: Dict[str, float]) -> float:
        if not level:
            return 0.5
        return score_map.get(level.lower().strip(), 0.5)

    enriched = {}

    # COMBINED_ANXIETY (maps to ANXIETY_POST_CONSULTATION for downstream compatibility)
    anxiety_key = "COMBINED_ANXIETY" if "COMBINED_ANXIETY" in result else "ANXIETY_POST_CONSULTATION"
    if anxiety_key in result:
        anxiety = result[anxiety_key]
        # Calculate overall mismatch
        pre_mismatch = anxiety.get("pre_consultation", {}).get("mismatch", False)
        post_mismatch = anxiety.get("post_consultation", {}).get("mismatch", False)

        # Add combined_score to nested objects
        if "pre_consultation" in anxiety:
            pre = anxiety["pre_consultation"]
            pre["combined_score"] = get_score(pre.get("level"), severity_score_map)
            pre.setdefault("mismatch", False)
        if "post_consultation" in anxiety:
            post = anxiety["post_consultation"]
            post["combined_score"] = get_score(post.get("level"), severity_score_map)
            post.setdefault("mismatch", False)

        anxiety["source"] = "combined"
        anxiety["mismatch"] = pre_mismatch or post_mismatch
        enriched["ANXIETY_POST_CONSULTATION"] = anxiety

    # COMBINED_FINANCIAL_CONCERNS (maps to FINANCIAL_CONCERNS)
    financial_key = "COMBINED_FINANCIAL_CONCERNS" if "COMBINED_FINANCIAL_CONCERNS" in result else "FINANCIAL_CONCERNS"
    if financial_key in result:
        financial = result[financial_key]
        financial["source"] = "combined"
        financial["combined_score"] = get_score(financial.get("severity"), severity_score_map)
        financial.setdefault("mismatch", False)
        enriched["FINANCIAL_CONCERNS"] = financial

    # COMBINED_OTHER_EMOTIONS (maps to OTHER_EMOTIONS_DETECTED)
    emotions_key = "COMBINED_OTHER_EMOTIONS" if "COMBINED_OTHER_EMOTIONS" in result else "OTHER_EMOTIONS_DETECTED"
    if emotions_key in result:
        emotions = result[emotions_key]
        emotions["source"] = "combined"
        emotions.setdefault("mismatch", False)
        emotions.setdefault("emotions_detected", [])
        # Populate text_emotions from emotions_detected for compatibility
        emotions["text_emotions"] = emotions.get("emotions_detected", [])
        enriched["OTHER_EMOTIONS_DETECTED"] = emotions

    # COMBINED_COMPLIANCE (maps to TREATMENT_COMPLIANCE_LIKELIHOOD)
    compliance_key = "COMBINED_COMPLIANCE" if "COMBINED_COMPLIANCE" in result else "TREATMENT_COMPLIANCE_LIKELIHOOD"
    if compliance_key in result:
        compliance = result[compliance_key]
        compliance["source"] = "combined"
        compliance["combined_score"] = get_score(compliance.get("likelihood"), likelihood_score_map)
        compliance.setdefault("mismatch", False)
        compliance.setdefault("positive_factors", [])
        compliance.setdefault("negative_factors", [])
        compliance.setdefault("key_barriers", [])
        enriched["TREATMENT_COMPLIANCE_LIKELIHOOD"] = compliance

    # COMBINED_DOCTOR_STYLE (maps to DOCTOR_COMMUNICATION_STYLE)
    doctor_key = "COMBINED_DOCTOR_STYLE" if "COMBINED_DOCTOR_STYLE" in result else "DOCTOR_COMMUNICATION_STYLE"
    if doctor_key in result:
        doctor = result[doctor_key]
        doctor["source"] = "combined"
        doctor.setdefault("mismatch", False)
        doctor.setdefault("empathy_indicators", [])
        enriched["DOCTOR_COMMUNICATION_STYLE"] = doctor

    # COMBINED_INTERACTION_DYNAMICS (new segment, maps to INTERACTION_DYNAMICS)
    if "COMBINED_INTERACTION_DYNAMICS" in result:
        dynamics = result["COMBINED_INTERACTION_DYNAMICS"]
        dynamics["source"] = "combined"
        dynamics.setdefault("mismatch", False)
        enriched["INTERACTION_DYNAMICS"] = dynamics

    # COMBINED_CONGRUENCE_SUMMARY (new segment, maps to CONGRUENCE_SUMMARY)
    if "COMBINED_CONGRUENCE_SUMMARY" in result:
        congruence = result["COMBINED_CONGRUENCE_SUMMARY"]
        congruence["source"] = "combined"
        enriched["CONGRUENCE_SUMMARY"] = congruence

    return enriched


# =============================================================================
# CONSULTATION INSIGHTS EXTRACTION
# =============================================================================

async def extract_consultation_insights(
    transcript: str,
    extraction_data: Dict[str, Any],
    model: str = 'gemini-2.5-flash',
    temperature: float = 0.1,
    extraction_id: Optional[uuid.UUID] = None,
    session_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    """
    Extract 14 clinical signal groups from consultation using Gemini AI.

    Uses ICD code cross-validation for accuracy by passing previously extracted
    DIAGNOSIS segment as context.

    Args:
        transcript: Full consultation transcript
        extraction_data: Dict with extracted segments (DIAGNOSIS, PRESCRIPTION, etc.)
        model: Gemini model to use (default: gemini-2.5-flash)
        temperature: Temperature for generation (default: 0.1 for consistency)

    Returns:
        Dict with 14 signal groups:
        - patient_signals
        - clinical_severity_signals
        - diagnostic_needs
        - medication_signals
        - nutritional_signals
        - physiotherapy_signals
        - homecare_signals
        - sleep_signals
        - rehabilitation_signals
        - wellness_signals
        - mental_health_signals
        - education_signals
        - competitor_signals
        - access_logistics_signals

    Raises:
        Exception: If extraction fails
    """
    import json
    import time
    from services.consultation_insights_prompts import (
        CONSULTATION_INSIGHTS_SYSTEM_PROMPT,
        CONSULTATION_INSIGHTS_SCHEMA,
        generate_consultation_insights_prompt,
    )
    from services.gemini_cache_service import CACHE_KEY_CONSULTATION_INSIGHTS

    logger.debug(f'[ConsultationInsights] Starting extraction with {model}...')
    start_time = time.time()

    try:
        # Generate user prompt with extracted segment context for ICD cross-validation
        # Extraction data uses camelCase keys; try both camelCase and UPPER_SNAKE fallback
        def _find_segment(*keys):
            for k in keys:
                val = extraction_data.get(k)
                if val:
                    return val
            return None

        user_prompt = generate_consultation_insights_prompt(
            transcript=transcript,
            diagnosis_segment=_find_segment("diagnosis", "diagnosisOp", "diagnosisDischarge", "DIAGNOSIS"),
            prescription_segment=_find_segment("prescription", "prescriptionOp", "prescriptionDischarge", "PRESCRIPTION"),
            investigations_segment=_find_segment("investigations", "investigationsOp", "investigationsDischarge", "INVESTIGATIONS"),
            follow_up_segment=_find_segment("followUp", "follow_up", "followUpOp", "FOLLOW_UP"),
            treatment_plan_segment=_find_segment("treatmentPlan", "treatmentPlanAdviceOp", "treatmentPlanAdviceDischarge", "TREATMENT_PLAN"),
        )

        # Route through LLM factory (supports Gemini/Claude/OpenAI)
        from services.llm_client_factory import generate_structured_output
        from services.schema_adapter import gemini_schema_to_json_schema

        json_schema = gemini_schema_to_json_schema(CONSULTATION_INSIGHTS_SCHEMA)

        from services.llm_usage_service import get_thinking_budget
        llm_result = await generate_structured_output(
            system_prompt=CONSULTATION_INSIGHTS_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_schema=json_schema,
            model=model,
            temperature=temperature,
            cache_key=CACHE_KEY_CONSULTATION_INSIGHTS,
            thinking_budget=get_thinking_budget(model, "consultation_insights"),
        )

        # Log LLM usage (fire-and-forget)
        api_duration = time.time() - start_time
        try:
            from services.llm_usage_service import extract_usage_from_response, log_llm_usage
            usage_data = extract_usage_from_response(
                response=llm_result.raw_response,
                call_type="consultation_insights",
                model=model,
                api_duration_seconds=api_duration,
                extraction_id=extraction_id,
                session_id=session_id,
                doctor_id=doctor_id,
            )
            asyncio.create_task(log_llm_usage(usage_data))
        except Exception as usage_err:
            logger.warning(f"[ConsultationInsights] Failed to log usage: {usage_err}")

        # Data is already parsed by the factory
        result = llm_result.data

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f'[ConsultationInsights] Extraction successful in {duration_ms}ms. '
            f'chronic={result.get("clinical_severity_signals", {}).get("is_chronic")}, '
            f'surgical={result.get("clinical_severity_signals", {}).get("is_surgical")}'
        )

        # Add metadata
        result["_metadata"] = {
            "model_used": model,
            "extraction_duration_ms": duration_ms,
            "extraction_version": "1.0.0"
        }

        return result

    except json.JSONDecodeError as e:
        logger.error(f"[ConsultationInsights] Error parsing JSON response: {e}")
        raise Exception(f"Failed to parse consultation insights: {_sanitize_error_message(str(e))}")
    except Exception as e:
        logger.error(f"[ConsultationInsights] Extraction error: {e}")
        raise Exception(f"Failed to extract consultation insights: {_sanitize_error_message(str(e))}")
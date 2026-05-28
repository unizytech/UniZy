"""
Raster API integration service for neonatal care system.

This service handles all Raster API integrations:
- Fetching NICU inpatient list (get-nicu-inpatient-list)
- Fetching OP baby list (today-op-baby-list)
- Posting NEO_DAILY extraction results (store-daycare-transcribed-data)
- Posting NEO_PROFORMA extraction results (store-neonatal-proforma-transcribed-data)
- Posting NEO_OP extraction results (store-op-neonatal-transcribed-data)
- Posting NEO_DISCHARGE extraction results (store-nicu-discharge-transcribed-data)
- Posting NEO_ADMISSION extraction results (store-nicu-admission-transcribed-data)
"""

import os
import csv
import re
import json
import logging
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union
from pathlib import Path

from services.raster_lookups import (
    apply_raster_lookups_to_neo_daily,
    apply_raster_lookups_to_neo_op,
    normalize_medication_route,
)
from services.drug_lookups import lookup_drug_id_fuzzy, lookup_drug_id_with_fallback

logger = logging.getLogger(__name__)


# ============================================================================
# Raster MedicineType enum mapping
# Maps internal form names to Raster API's MedicineType Java enum values
# ============================================================================

_RASTER_MEDICINE_TYPE_MAP = {
    "tablet": "TABLET",
    "capsule": "CAPSULE",
    "injection": "INJECTION",
    "ointment": "OINMENT",      # Raster enum has typo: OINMENT (not OINTMENT)
    "needle": "NEEDLE",
    "soap": "SOAP",
    "bandage": "BANDAGE",
    "paste": "PASTE",
    "drops": "DROPS",
    "enema": "ENEMA",
    "granules": "GRANULES",
    "spray": "SPRAY",
    "jelly": "JELLY",
    "suction_catheter": "SUCTION_CATHETER",
    "lotion": "LOTION",
    "syrup": "SYRUP",
    "dyna_product": "DYNA_PRODUCT",
    "powder": "POWDER",
    "udyna_product": "UDYNA_PRODUCT",
    "surgical": "SURGICAL",
}


def _map_to_raster_medicine_type(dosage_form: str) -> str:
    """Map a dosage form string to a valid Raster MedicineType enum value.
    Falls back to TABLET if no form is provided or no match found."""
    if not dosage_form:
        return "TABLET"
    return _RASTER_MEDICINE_TYPE_MAP.get(dosage_form.strip().lower(), "TABLET")


# ============================================================================
# Department ID Lookup from Raster_Department_id_to_Material_type.csv
# Maps material external_id → department_id
# ============================================================================

_RASTER_DEPT_LOOKUP: Dict[str, int] = {}


def _load_raster_dept_lookup() -> Dict[str, int]:
    """Load material_id → department_id mapping from CSV (cached in-memory)."""
    global _RASTER_DEPT_LOOKUP
    if _RASTER_DEPT_LOOKUP:
        return _RASTER_DEPT_LOOKUP

    csv_path = Path(__file__).resolve().parent.parent.parent / "test_data" / "Raster_Department_id_to_Material_type.csv"
    if not csv_path.exists():
        logger.warning(f"[RASTER_EMR] Department lookup CSV not found: {csv_path}")
        return _RASTER_DEPT_LOOKUP

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header: id,name,department_id,name,type
            for row in reader:
                if len(row) >= 3:
                    material_id = row[0].strip()
                    dept_id = row[2].strip()
                    if material_id and dept_id:
                        try:
                            _RASTER_DEPT_LOOKUP[material_id] = int(dept_id)
                        except ValueError:
                            pass
        logger.info(f"[RASTER_EMR] Loaded {len(_RASTER_DEPT_LOOKUP)} material→department mappings")
    except Exception as e:
        logger.error(f"[RASTER_EMR] Failed to load department lookup CSV: {e}")

    return _RASTER_DEPT_LOOKUP


def _get_department_id_for_material(external_id: Any) -> Optional[int]:
    """Look up department_id for a material external_id."""
    lookup = _load_raster_dept_lookup()
    return lookup.get(str(external_id)) if external_id else None


# ============================================================================
# Prescription Helper Functions
# ============================================================================

def _parse_frequency_count(frequency: str) -> int:
    """
    Parse frequency string to get doses-per-day count.

    Examples:
        "1-0-1" → 2, "1-1-1" → 3, "0-0-1" → 1
        "Once daily" → 1, "Twice daily" → 2, "SOS" → 1
    """
    if not frequency:
        return 1

    freq = frequency.strip()

    # Pattern: "1-0-1", "1-1-1-1", etc.
    dash_pattern = re.match(r'^[\d]+([-][\d]+)+$', freq)
    if dash_pattern:
        parts = freq.split('-')
        return sum(1 for p in parts if p.strip() != '0')

    freq_lower = freq.lower()
    if "thrice" in freq_lower or "three times" in freq_lower or "tid" in freq_lower or "tds" in freq_lower:
        return 3
    if "twice" in freq_lower or "two times" in freq_lower or "bid" in freq_lower or "bd" in freq_lower:
        return 2
    if "four" in freq_lower or "qid" in freq_lower or "qds" in freq_lower:
        return 4
    # Default: once
    return 1


def _parse_duration_number(duration: str) -> int:
    """Extract numeric value from duration string. E.g., '5 days' → 5, '2 weeks' → 2."""
    if not duration:
        return 1
    match = re.search(r'(\d+)', str(duration))
    return int(match.group(1)) if match else 1


def _derive_duration_type(duration: str) -> int:
    """
    Derive duration_type from duration text.
    1=Days, 2=Weeks, 3=Months, 4=Years, 5=Nos
    """
    if not duration:
        return 1  # default to Days

    dur_lower = str(duration).lower()
    if "year" in dur_lower:
        return 4
    if "month" in dur_lower:
        return 3
    if "week" in dur_lower:
        return 2
    if "day" in dur_lower:
        return 1
    # If just a number with no unit, assume days
    if re.match(r'^\s*\d+\s*$', str(duration)):
        return 1
    return 5  # Nos (unrecognized)

# Load Raster API base URL from environment
RASTER_API_URL = os.getenv("RASTER_API_URL", "").rstrip("/")

# Raster General EMR API URL (for RASTER_OP template)
RASTER_GENERAL_EMR_URL = os.getenv("RASTER_GENERAL_EMR_URL", "").rstrip("/")

# Temporary hardcoded UHID for NEO_PROFORMA when audio doesn't contain it
# TODO: Remove this workaround once proper uhid handling is implemented
TEMP_UHID_FALLBACK = os.getenv("RASTER_TEMP_UHID", "TEMP_UHID_000000")


# ============================================================================
# SLASH SANITIZATION - Strip escaped forward slashes before sending to Raster
# ============================================================================

def _sanitize_escaped_slashes(obj: Any) -> Any:
    """
    Recursively strip escaped forward slashes (\\/) from all string values.

    PHP's json_encode() escapes '/' as '\\/' by default. While Python's json.dumps
    does NOT escape slashes, this provides a defensive layer to ensure no escaped
    slashes reach the Raster API from any source (e.g., LLM responses, DB values).
    """
    if isinstance(obj, str):
        return obj.replace("\\/", "/")
    elif isinstance(obj, dict):
        return {k: _sanitize_escaped_slashes(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_escaped_slashes(item) for item in obj]
    else:
        return obj


# ============================================================================
# PRE-PROCESSING VALIDATION FOR RASTER API PAYLOADS
# ============================================================================

def _validate_and_fix_neo_daily_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and fix NEO_DAILY payload before sending to Raster API.

    Fixes common issues:
    - Ensures antibiotics/transfusions/fluids have correct structure
    - Converts empty objects {} to None to prevent "Array to string conversion"
    - Ensures all required fields have default values

    Args:
        payload: The extraction payload to validate

    Returns:
        Fixed payload ready for Raster API
    """
    fixed = payload.copy()
    issues_found = []

    # Fix antibiotics array
    if "antibiotics" in fixed:
        antibiotics = fixed.get("antibiotics", [])
        if isinstance(antibiotics, list):
            fixed_antibiotics = []
            for idx, ab in enumerate(antibiotics):
                if isinstance(ab, dict):
                    fixed_ab = {
                        "drugId": ab.get("drugId") or idx + 1,
                        "drugName": ab.get("drugName", ""),
                        "dose": ab.get("dose", ""),
                        "frequency": ab.get("frequency", ""),
                        "route": ab.get("route", "IV"),
                    }
                    fixed_antibiotics.append(fixed_ab)
                    if not ab.get("dose"):
                        issues_found.append(f"antibiotics[{idx}].dose missing")
            fixed["antibiotics"] = fixed_antibiotics

    # Fix transfusions array
    if "transfusions" in fixed:
        transfusions = fixed.get("transfusions", [])
        if isinstance(transfusions, list):
            fixed_transfusions = []
            for idx, tr in enumerate(transfusions):
                if isinstance(tr, dict):
                    fixed_tr = {
                        "product": tr.get("product", ""),
                        "volume": tr.get("volume"),
                    }
                    fixed_transfusions.append(fixed_tr)
            fixed["transfusions"] = fixed_transfusions

    # Fix fluids array
    if "fluids" in fixed:
        fluids = fixed.get("fluids", [])
        if isinstance(fluids, list):
            fixed_fluids = []
            for idx, fl in enumerate(fluids):
                if isinstance(fl, dict):
                    fixed_fl = {
                        "fluidId": fl.get("fluidId") or idx + 1,
                        "fluidName": fl.get("fluidName", ""),
                        "rate": fl.get("rate", ""),
                        "duration": fl.get("duration", ""),
                    }
                    fixed_fluids.append(fixed_fl)
            fixed["fluids"] = fixed_fluids

    # Fix empty nested objects in dailyLog
    if "dailyLog" in fixed and isinstance(fixed["dailyLog"], dict):
        fixed["dailyLog"] = _fix_empty_objects_recursive(fixed["dailyLog"])

    if issues_found:
        logger.warning(f"[RASTER_API] Payload validation issues: {issues_found}")

    return fixed


def _fix_empty_objects_recursive(obj: Any) -> Any:
    """
    Recursively fix empty objects {} by converting to None.

    Empty objects can cause "Array to string conversion" errors in Laravel.
    """
    if isinstance(obj, dict):
        if not obj:  # Empty dict
            return None
        return {k: _fix_empty_objects_recursive(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_fix_empty_objects_recursive(item) for item in obj]
    else:
        return obj


def _validate_and_fix_neo_proforma_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and fix NEO_PROFORMA payload before sending to Raster API.

    Fixes common issues:
    - Ensures all required top-level fields have default values
    - Ensures liveBirthBabyDetails has all required fields (birthYear, place, etc.)
    - Ensures pregnancyComplicationsDetails has all required fields
    - Ensures scan details have all required fields
    - Converts empty objects {} to objects with empty string values

    Args:
        payload: The extraction payload to validate

    Returns:
        Fixed payload ready for Raster API
    """
    fixed = payload.copy()
    issues_found = []

    # All required top-level string fields per Raster schema
    required_string_fields = [
        "uhid", "dateTime", "babyName", "dob", "tob", "sex", "birthStatus",
        "birthWeight", "birthLength", "birthHeadCircunference", "birthOrder",
        "babyBloodGroup", "gestationWeeks", "gestationDays", "transferStatus",
        "consanguinity", "gravida", "para", "liveBirth", "abortion", "conception",
        "lmp", "EDDByUSG", "EDDByDate", "motherBloodGroup", "HIV", "HepatitisB",
        "VDRL", "booked", "bookedPlace", "pleaceOfBooking", "supervised",
        "pleaceOfSupervision", "multiplePregnancy", "pregnancyComplications",
        "antenatalSteroids", "typeOfSteriods", "steroidCourse", "timeOfLastDose",
        "lastDoseDeliveryInterval", "antenatalMgSO4ForNeuroprotection",
        "labour", "natureofLabour", "commentOnLiquor", "riskFactorsForSepsisInMothers",
        "maternalPyrexia", "maternalPyrexiaTemperatureFahrenheit", "PROM",
        "durationOfPROM", "maternalAntibiotics", "modeOfDelivery", "presentation",
        "fetalDistress", "CTG", "CTGDetails", "cordBloodGas", "cordPH", "cordBE",
        "cordHCO3", "typeofAnesthesia", "delayedCordClamping",
        "delayedCordClampingduration", "reasonForNoDCC", "umbilicalCordMilking",
        "cutCordMilking", "resuscitation", "initialSteps", "facialOxygen",
        "durationOfFacialOxygen", "bagMaskVentilation", "bagMaskVentilationDuration",
        "bagMaskVentilationDurationMin", "maximumFio2Rquired", "deliveryRoomCPAP",
        "intubation", "ETTSizeInMM", "depthOfInsertion", "depthOfInsertionLengthInCM",
        "PPV", "durationOfPTV", "durationOfPTVMinutes", "CPR", "durationOfCPR",
        "durationOfCPRMinutes", "drugs", "timeOf1stGasp", "timeOf1stGaspInMinutes",
        "regularRespiration", "regularRespirationMinutes", "gastricAspirate",
        "vitaminK", "vitaminKDose", "vitaminKRoute", "DCT", "ICT",
        "initialExaminationSummary", "malformation", "backgroundDetails", "plan",
        "adjustedRiskForTrisomiesAvailable", "adjustedRiskForTrisomy21",
        "adjustedRiskForTrisomy18", "adjustedRiskForTrisomy13", "otherInvestigations"
    ]

    # Ensure all required string fields have at least empty string
    for field in required_string_fields:
        if field not in fixed or fixed[field] is None:
            fixed[field] = ""
            issues_found.append(f"Added missing field: {field}")

    # Ensure required array fields exist
    required_array_fields = [
        "medicalProblem", "riskFactors", "indication",
        "maternalAntibioticsDetails", "drugDetails"
    ]
    for field in required_array_fields:
        if field not in fixed or not isinstance(fixed[field], list):
            fixed[field] = []
            issues_found.append(f"Fixed array field: {field}")

    # Fix medicalProblem array - ensure each item has problemsId and medications fields
    # Note: These are MATERNAL medical problems per Raster schema
    if "medicalProblem" in fixed and isinstance(fixed["medicalProblem"], list):
        fixed_problems = []
        for idx, problem in enumerate(fixed["medicalProblem"]):
            if isinstance(problem, dict):
                # Support both old (problem/medication) and new (problemsId/medications) field names
                fixed_problem = {
                    "problemsId": problem.get("problemsId", problem.get("problem", "")),
                    "medications": problem.get("medications", problem.get("medication", ""))
                }
                fixed_problems.append(fixed_problem)
            elif isinstance(problem, (str, int)):
                # If it's just a string/int, convert to proper structure
                fixed_problems.append({"problemsId": problem, "medications": ""})
            else:
                fixed_problems.append({"problemsId": "", "medications": ""})
        fixed["medicalProblem"] = fixed_problems

    # Template for liveBirthBabyDetails - all required fields per Raster schema
    live_birth_template = {
        "place": "",
        "gender": "",
        "health": "",
        "details": "",
        "birthYear": "",
        "gestation": "",
        "birthWeight": "",
        "complications": "",
        "typeOfDelivery": ""
    }

    # Fix liveBirthBabyDetails array
    if "liveBirthBabyDetails" in fixed:
        live_births = fixed.get("liveBirthBabyDetails", [])
        if isinstance(live_births, list):
            fixed_births = []
            for idx, birth in enumerate(live_births):
                if isinstance(birth, dict):
                    # Merge with template to ensure all fields present
                    fixed_birth = {**live_birth_template}
                    for key in live_birth_template:
                        if key in birth and birth[key]:
                            fixed_birth[key] = birth[key]
                    fixed_births.append(fixed_birth)
                    # Check for completely empty births
                    if not any(birth.get(k) for k in live_birth_template):
                        issues_found.append(f"liveBirthBabyDetails[{idx}] empty")
                else:
                    # Not a dict, add template
                    fixed_births.append({**live_birth_template})
                    issues_found.append(f"liveBirthBabyDetails[{idx}] was not dict")
            fixed["liveBirthBabyDetails"] = fixed_births
        else:
            # Not a list, create default
            fixed["liveBirthBabyDetails"] = [{**live_birth_template}, {**live_birth_template}]
            issues_found.append("liveBirthBabyDetails was not a list")

    # Template for pregnancyComplicationsDetails
    # Note: Field is "complicationId" (integer) per reference file
    complication_template = {
        "duration": "",
        "treatment": "",
        "complicationId": "",
        "durationType": ""
    }

    # Fix pregnancyComplicationsDetails array
    if "pregnancyComplicationsDetails" in fixed:
        complications = fixed.get("pregnancyComplicationsDetails", [])
        if isinstance(complications, list):
            fixed_complications = []
            for idx, comp in enumerate(complications):
                if isinstance(comp, dict):
                    fixed_comp = {**complication_template}
                    for key in complication_template:
                        if key in comp and comp[key]:
                            fixed_comp[key] = comp[key]
                    # Support old field name "complication" -> "complicationId"
                    if "complication" in comp and comp["complication"] and not fixed_comp["complicationId"]:
                        fixed_comp["complicationId"] = comp["complication"]
                    fixed_complications.append(fixed_comp)
                else:
                    fixed_complications.append({**complication_template})
            fixed["pregnancyComplicationsDetails"] = fixed_complications

    # Template for scan details (dating, anomaly, other, doppler)
    scan_template = {
        "date": "",
        "findings": "",
        "gestation": ""
    }

    # Fix datingScanDetails
    if "datingScanDetails" in fixed:
        scan = fixed.get("datingScanDetails", {})
        if isinstance(scan, dict):
            fixed_scan = {**scan_template}
            for key in scan_template:
                if key in scan and scan[key]:
                    fixed_scan[key] = scan[key]
            fixed["datingScanDetails"] = fixed_scan
        else:
            fixed["datingScanDetails"] = {**scan_template}

    # Fix anomalyScanDetails
    if "anomalyScanDetails" in fixed:
        scan = fixed.get("anomalyScanDetails", {})
        if isinstance(scan, dict):
            fixed_scan = {**scan_template}
            for key in scan_template:
                if key in scan and scan[key]:
                    fixed_scan[key] = scan[key]
            fixed["anomalyScanDetails"] = fixed_scan
        else:
            fixed["anomalyScanDetails"] = {**scan_template}

    # Fix otherScanDetails array
    if "otherScanDetails" in fixed:
        scans = fixed.get("otherScanDetails", [])
        if isinstance(scans, list):
            fixed_scans = []
            for scan in scans:
                if isinstance(scan, dict):
                    fixed_scan = {**scan_template}
                    for key in scan_template:
                        if key in scan and scan[key]:
                            fixed_scan[key] = scan[key]
                    fixed_scans.append(fixed_scan)
                else:
                    fixed_scans.append({**scan_template})
            fixed["otherScanDetails"] = fixed_scans

    # Fix dopplerScanDetails array
    if "dopplerScanDetails" in fixed:
        scans = fixed.get("dopplerScanDetails", [])
        if isinstance(scans, list):
            fixed_scans = []
            for scan in scans:
                if isinstance(scan, dict):
                    fixed_scan = {**scan_template}
                    for key in scan_template:
                        if key in scan and scan[key]:
                            fixed_scan[key] = scan[key]
                    fixed_scans.append(fixed_scan)
                else:
                    fixed_scans.append({**scan_template})
            fixed["dopplerScanDetails"] = fixed_scans

    # Fix maternalAntibioticsDetails array if present
    if "maternalAntibioticsDetails" in fixed:
        antibiotics = fixed.get("maternalAntibioticsDetails", [])
        if not isinstance(antibiotics, list):
            fixed["maternalAntibioticsDetails"] = []

    # Fix drugDetails array if present
    if "drugDetails" in fixed:
        drugs = fixed.get("drugDetails", [])
        if not isinstance(drugs, list):
            fixed["drugDetails"] = []

    # Fix apgar nested object - ensure all minute structures exist
    apgar_minute_template = {
        "tone": None,
        "color": None,
        "total": None,
        "reflex": None,
        "heartRate": None,
        "respiration": None
    }

    if "apgar" not in fixed or not isinstance(fixed.get("apgar"), dict):
        fixed["apgar"] = {
            "status": "unknown",
            "minute1": {**apgar_minute_template},
            "minute5": {**apgar_minute_template},
            "minute10": {**apgar_minute_template},
            "minute15": {**apgar_minute_template},
            "minute20": {**apgar_minute_template}
        }
        issues_found.append("Added missing apgar object")
    else:
        apgar = fixed["apgar"]
        if "status" not in apgar:
            apgar["status"] = "unknown"
        for minute in ["minute1", "minute5", "minute10", "minute15", "minute20"]:
            if minute not in apgar or not isinstance(apgar.get(minute), dict):
                apgar[minute] = {**apgar_minute_template}
            else:
                # Ensure all fields in minute object exist
                for field in apgar_minute_template:
                    if field not in apgar[minute]:
                        apgar[minute][field] = None

    if issues_found:
        logger.warning(f"[RASTER_API] NEO_PROFORMA payload validation issues: {issues_found[:10]}...")

    return fixed


def _clean_medication_metadata(med: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove lookup metadata fields from a medication object.

    Strips underscore-prefixed metadata fields (e.g., _external_id)
    that are added by post-processing but should not be sent to Raster API.

    Args:
        med: Medication dict that may contain metadata fields

    Returns:
        Cleaned medication dict with only API-expected fields
    """
    # Fields to keep (per Raster API schema)
    allowed_fields = {"drugId", "route", "dosage", "additionalInstruction"}

    cleaned = {}
    for key, value in med.items():
        # Skip all underscore-prefixed metadata fields
        if key.startswith("_"):
            continue
        # Keep only allowed fields
        if key in allowed_fields:
            cleaned[key] = value

    return cleaned


def _validate_and_fix_neo_discharge_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and fix NEO_DISCHARGE payload before sending to Raster API.

    Fixes common issues:
    - Cleans medications array (removes lookup metadata, ensures drugId is numeric)
    - Ensures required nested structures exist

    Args:
        payload: The extraction payload to validate

    Returns:
        Fixed payload ready for Raster API
    """
    fixed = payload.copy()
    issues_found = []

    # Fix medications inside discharge object
    discharge = fixed.get("discharge")
    if isinstance(discharge, dict) and "medications" in discharge:
        medications = discharge.get("medications", [])
        if isinstance(medications, list):
            fixed_medications = []
            for idx, med in enumerate(medications):
                if isinstance(med, dict):
                    drug_id = med.get("drugId", "")

                    # Check if drugId is a valid numeric ID
                    if isinstance(drug_id, str) and drug_id.isdigit():
                        drug_id_str = drug_id
                    elif isinstance(drug_id, int):
                        drug_id_str = str(drug_id)
                    elif isinstance(drug_id, str) and drug_id and not drug_id.isdigit():
                        # It's a drug NAME - try to look up
                        drug_name = drug_id
                        looked_up_id = lookup_drug_id_fuzzy(drug_name)
                        if looked_up_id is not None:
                            drug_id_str = str(looked_up_id)
                            logger.debug(f"[RASTER_API] NEO_DISCHARGE medication {idx}: drugName='{drug_name}' -> drugId={drug_id_str}")
                        else:
                            # Fallback to sequential ID if not found (like NEO_OP)
                            drug_id_str = str(idx + 1)
                            issues_found.append(f"medications[{idx}].drugId '{drug_name}' not found in drug DB, using fallback ID {drug_id_str}")
                            logger.warning(f"[RASTER_API] NEO_DISCHARGE medication {idx}: drugName='{drug_name}' NOT FOUND, using fallback ID {drug_id_str}")
                    else:
                        drug_id_str = str(idx + 1)

                    # Clean dosage array (handle both array and single dict)
                    dosage_data = med.get("dosage", [])
                    fixed_dosage = []
                    if isinstance(dosage_data, list):
                        for d in dosage_data:
                            if isinstance(d, dict):
                                fixed_dosage.append({
                                    "dose": d.get("dose", ""),
                                    "frequency": d.get("frequency", ""),
                                    "duration": d.get("duration", ""),
                                    "additionalInstruction": d.get("additionalInstruction", "")
                                })
                    elif isinstance(dosage_data, dict):
                        # Single dosage object - wrap in array
                        fixed_dosage.append({
                            "dose": dosage_data.get("dose", ""),
                            "frequency": dosage_data.get("frequency", ""),
                            "duration": dosage_data.get("duration", ""),
                            "additionalInstruction": dosage_data.get("additionalInstruction", "")
                        })

                    if not fixed_dosage:
                        fixed_dosage = [{"dose": "", "frequency": "", "duration": "", "additionalInstruction": ""}]

                    # Build clean medication object (no metadata fields)
                    fixed_med = {
                        "drugId": drug_id_str,
                        "route": normalize_medication_route(med.get("route")),
                        "dosage": fixed_dosage
                    }

                    fixed_medications.append(fixed_med)

            discharge["medications"] = fixed_medications

    if issues_found:
        logger.warning(f"[RASTER_API] NEO_DISCHARGE payload validation issues: {issues_found[:10]}...")

    return fixed


def _validate_and_fix_neo_op_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and fix NEO_OP payload before sending to Raster API.

    Fixes common issues:
    - Restructures baby.chronologicalAge and baby.correctedAge to Raster's expected nested format
    - Ensures medications have integer drugId (not drug names)
    - Ensures immunization vaccineIds are integers
    - Ensures required fields have default values

    Args:
        payload: The extraction payload to validate

    Returns:
        Fixed payload ready for Raster API
    """
    fixed = payload.copy()
    issues_found = []

    # ========== FIX BABY AGE STRUCTURES ==========
    # Raster expects nested structure: {yearMonthDays: {...}, weeksDays: {...}}
    # But our extraction returns flat structure: {years, months, days, weeks, weeksDays}
    def _restructure_age(flat_age: Dict[str, Any]) -> Dict[str, Any]:
        """Convert flat age dict to Raster's nested format."""
        if not flat_age or not isinstance(flat_age, dict):
            return {
                "yearMonthDays": {"years": 0, "months": 0, "days": 0},
                "weeksDays": {"weeks": 0, "days": 0}
            }
        # Check if already in correct nested format
        if "yearMonthDays" in flat_age and "weeksDays" in flat_age:
            return flat_age
        # Convert from flat format
        return {
            "yearMonthDays": {
                "years": flat_age.get("years", 0) or 0,
                "months": flat_age.get("months", 0) or 0,
                "days": flat_age.get("days", 0) or 0
            },
            "weeksDays": {
                "weeks": flat_age.get("weeks", 0) or 0,
                "days": flat_age.get("weeksDays", 0) or 0
            }
        }

    if "baby" in fixed and isinstance(fixed["baby"], dict):
        baby = fixed["baby"]

        # Fix chronologicalAge structure
        if "chronologicalAge" in baby:
            original_chrono = baby["chronologicalAge"]
            baby["chronologicalAge"] = _restructure_age(original_chrono)
            if original_chrono != baby["chronologicalAge"]:
                issues_found.append("Restructured baby.chronologicalAge to nested format")
                logger.debug(f"[RASTER_API] Fixed chronologicalAge: {original_chrono} -> {baby['chronologicalAge']}")

        # Fix correctedAge structure
        if "correctedAge" in baby:
            original_corrected = baby["correctedAge"]
            baby["correctedAge"] = _restructure_age(original_corrected)
            if original_corrected != baby["correctedAge"]:
                issues_found.append("Restructured baby.correctedAge to nested format")
                logger.debug(f"[RASTER_API] Fixed correctedAge: {original_corrected} -> {baby['correctedAge']}")

    # Fix medications array - drugId must be numeric string referencing mas_drugivfluid.id
    # Uses drug_lookups.py to convert drug names to actual Raster database IDs
    if "medications" in fixed and isinstance(fixed["medications"], list):
        fixed_medications = []
        for idx, med in enumerate(fixed["medications"]):
            if isinstance(med, dict):
                drug_id = med.get("drugId", "")
                drug_name = ""

                # Check if drugId is a valid numeric ID
                if isinstance(drug_id, str) and drug_id.isdigit():
                    # Valid numeric ID - use as-is (as string per Raster schema)
                    drug_id_str = drug_id
                elif isinstance(drug_id, int):
                    drug_id_str = str(drug_id)
                elif isinstance(drug_id, str) and drug_id and not drug_id.isdigit():
                    # It's a drug NAME - look up in Raster drug database
                    drug_name = drug_id
                    looked_up_id = lookup_drug_id_fuzzy(drug_name)
                    if looked_up_id is not None:
                        drug_id_str = str(looked_up_id)
                        logger.debug(f"[RASTER_API] Medication {idx}: drugName='{drug_name}' -> drugId={drug_id_str} (from drug lookup)")
                    else:
                        # Fallback to sequential ID if not found in database
                        drug_id_str = str(idx + 1)
                        issues_found.append(f"medications[{idx}].drugId '{drug_name}' not found in drug DB, using fallback ID {drug_id_str}")
                        logger.warning(f"[RASTER_API] Medication {idx}: drugName='{drug_name}' NOT FOUND in drug DB, using fallback ID {drug_id_str}")
                else:
                    drug_id_str = str(idx + 1)  # Use sequential IDs for empty values

                # Raster expects dosage as array of {dose, frequency, duration} objects
                dosage_data = med.get("dosage", [])

                # Ensure dosage is a properly formatted array
                fixed_dosage = []
                if isinstance(dosage_data, list):
                    for d in dosage_data:
                        if isinstance(d, dict):
                            fixed_dosage.append({
                                "dose": d.get("dose", ""),
                                "frequency": d.get("frequency", ""),
                                "duration": d.get("duration", "")
                            })
                elif isinstance(dosage_data, dict):
                    # Single dosage object - wrap in array
                    fixed_dosage.append({
                        "dose": dosage_data.get("dose", ""),
                        "frequency": dosage_data.get("frequency", ""),
                        "duration": dosage_data.get("duration", "")
                    })

                # If no dosage data, add empty dosage entry to prevent "Undefined index: dose" error
                if not fixed_dosage:
                    fixed_dosage = [{"dose": "", "frequency": "", "duration": ""}]

                fixed_med = {
                    "drugId": drug_id_str,
                    "route": normalize_medication_route(med.get("route")),  # Convert route text to ID
                    "dosage": fixed_dosage
                }

                fixed_medications.append(fixed_med)
        fixed["medications"] = fixed_medications

    # Fix immunization - vaccineIds must be integers referencing Raster's vaccine table
    # TODO: Implement Raster DB vaccine lookup to convert vaccine names to actual IDs
    if "immunization" in fixed and isinstance(fixed["immunization"], dict):
        immunization = fixed["immunization"]
        # Check both "vaccineList" (Raster schema) and "vaccines" (possible extraction key)
        vaccine_key = "vaccineList" if "vaccineList" in immunization else "vaccines"
        if vaccine_key in immunization and isinstance(immunization[vaccine_key], list):
            fixed_vaccines = []
            for idx, vac in enumerate(immunization[vaccine_key]):
                if isinstance(vac, dict):
                    vaccine_id = vac.get("vaccineId", "")
                    if isinstance(vaccine_id, str) and vaccine_id.isdigit():
                        vaccine_id = int(vaccine_id)
                    elif isinstance(vaccine_id, int):
                        pass  # Already an int
                    elif isinstance(vaccine_id, str) and vaccine_id and not vaccine_id.isdigit():
                        # Vaccine NAME, not ID - use placeholder
                        # TODO: Replace with Raster DB lookup for vaccine ID
                        issues_found.append(f"immunization.{vaccine_key}[{idx}].vaccineId '{vaccine_id}' is name, using placeholder")
                        logger.debug(f"[RASTER_API] Vaccine {idx}: name='{vaccine_id}' -> placeholder ID (TODO: implement Raster DB lookup)")
                        vaccine_id = idx + 1  # Use sequential IDs (1, 2, 3...) that exist in Raster DB
                    else:
                        vaccine_id = idx + 1  # Use sequential IDs for empty values
                    fixed_vaccines.append({"vaccineId": vaccine_id})
            immunization["vaccineList"] = fixed_vaccines  # Always use Raster's expected key

    # Ensure required string fields exist
    required_fields = ["uhid", "opDateTime"]
    for field in required_fields:
        if field not in fixed or fixed[field] is None:
            fixed[field] = ""
            issues_found.append(f"Added missing field: {field}")

    if issues_found:
        logger.warning(f"[RASTER_API] NEO_OP payload validation issues: {issues_found[:10]}...")

    return fixed


# ============================================================================
# Raster General EMR Integration (RASTER_OP template)
# ============================================================================

def format_for_raster(
    extraction_insights: Dict[str, Any],
    uhid: str,
    visit_number: str,
    consultant_id: int,
    modified_user_id: int,
    created_user_id: Optional[int] = None,
    sex: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Format RASTER_OP extraction insights to Raster General EMR API schema.

    Maps extraction fields to the EMR format:
    - vitals → vitals object
    - chiefComplaints → chief_complaint
    - historyOfPresentIllness → duration_of_illness, history_of_present_illness
    - history → past_history
    - examination → clinical_findings
    - diagnosis → provisional_diagnosis
    - investigations → investigations string in visit_record
    - prescription → prescription block with pharmacy_prescription_item[]
    - investigations → request block with request_item[]
    - treatmentPlan + followUp → doctor_advice
    - followUp.review_date → next_followup_date

    Args:
        extraction_insights: The extraction insights dict from RASTER_OP template
        uhid: Patient UHID (e.g., "HRD35553")
        visit_number: Visit number (e.g., "OP/25000973")
        consultant_id: Consultant/Doctor ID in Raster system (from patient add_info)
        modified_user_id: User ID for audit trail (from patient add_info)
        created_user_id: User ID who created the record (from add_info, defaults to modified_user_id)
        sex: Patient sex (from add_info, e.g., "Male", "Female")

    Returns:
        Dict formatted for Raster General EMR API
    """
    # Default created_user_id to modified_user_id if not provided
    if created_user_id is None:
        created_user_id = modified_user_id
    # Build vitals from extraction
    vitals_data = extraction_insights.get("vitals") or {}
    vitals = {
        "height": vitals_data.get("height"),
        "weight": vitals_data.get("weight"),
        "bmi": vitals_data.get("bmi"),
        "bps": vitals_data.get("systolic_bp"),
        "bpd": vitals_data.get("diastolic_bp"),
        "temp": vitals_data.get("temperature"),
        "spo2": vitals_data.get("spo2"),
        "resp": vitals_data.get("respiratory_rate"),
        "pulse": vitals_data.get("pulse")
    }
    # Remove None values from vitals
    vitals = {k: v for k, v in vitals.items() if v is not None}

    # Chief complaints - join array to string
    chief_complaints = extraction_insights.get("chiefComplaints", [])
    if isinstance(chief_complaints, list):
        chief_complaint = ", ".join(chief_complaints) if chief_complaints else ""
    else:
        chief_complaint = str(chief_complaints) if chief_complaints else ""

    # History of Present Illness - extract duration and combine other fields
    hpi = extraction_insights.get("historyOfPresentIllness", {})
    if isinstance(hpi, dict):
        duration_of_illness = hpi.get("duration", "")
        # Combine HPI fields for history_of_present_illness
        hpi_parts = []
        if hpi.get("onset"):
            hpi_parts.append(f"Onset: {hpi.get('onset')}")
        if hpi.get("characterization"):
            hpi_parts.append(hpi.get("characterization"))
        if hpi.get("severity"):
            hpi_parts.append(f"Severity: {hpi.get('severity')}")
        if hpi.get("progression"):
            hpi_parts.append(f"Progression: {hpi.get('progression')}")
        if hpi.get("aggravating_factors"):
            hpi_parts.append(f"Aggravating: {hpi.get('aggravating_factors')}")
        if hpi.get("alleviating_factors"):
            hpi_parts.append(f"Alleviating: {hpi.get('alleviating_factors')}")
        if hpi.get("negative_findings"):
            hpi_parts.append(f"Negative findings: {hpi.get('negative_findings')}")
        history_of_present_illness = ". ".join(hpi_parts) if hpi_parts else ""
    else:
        duration_of_illness = ""
        history_of_present_illness = str(hpi) if hpi else ""

    # Past history - combine past_medical_history and past_surgical_history
    history = extraction_insights.get("history", {})
    if isinstance(history, dict):
        past_parts = []
        if history.get("past_medical_history"):
            past_parts.append(f"Medical: {history.get('past_medical_history')}")
        if history.get("past_surgical_history"):
            past_parts.append(f"Surgical: {history.get('past_surgical_history')}")
        if history.get("family_history"):
            past_parts.append(f"Family: {history.get('family_history')}")
        if history.get("social_history"):
            past_parts.append(f"Social: {history.get('social_history')}")
        if history.get("drug_allergies"):
            past_parts.append(f"Allergies: {history.get('drug_allergies')}")
        past_history = ". ".join(past_parts) if past_parts else "None"
    else:
        past_history = str(history) if history else "None"

    # Build visit_notes from HPI + current_medications + past_investigations
    visit_notes_parts = []
    if duration_of_illness:
        visit_notes_parts.append(f"Duration of Illness: {duration_of_illness}")
    if history_of_present_illness:
        visit_notes_parts.append(history_of_present_illness)
    # Current medications from history segment
    if isinstance(history, dict):
        current_meds = history.get("current_medications", [])
        if isinstance(current_meds, list) and current_meds:
            med_strs = []
            for med in current_meds:
                if isinstance(med, dict):
                    name = med.get("medication_name", "")
                    dosage = med.get("dosage", "")
                    freq = med.get("frequency", "")
                    parts = [p for p in [name, dosage, freq] if p]
                    if parts:
                        med_strs.append(" ".join(parts))
            if med_strs:
                visit_notes_parts.append(f"Current Medications: {', '.join(med_strs)}")
        # Past investigations from history segment
        past_inv = history.get("past_investigations", [])
        if isinstance(past_inv, list) and past_inv:
            inv_strs = []
            for inv in past_inv:
                if isinstance(inv, dict):
                    test = inv.get("name", "") or inv.get("test_name", "")
                    result = inv.get("result", "")
                    date = inv.get("date", "")
                    parts = [test]
                    if result:
                        parts.append(f"- {result}")
                    if date and date != "N/A":
                        parts.append(f"({date})")
                    inv_strs.append(" ".join(parts))
            if inv_strs:
                visit_notes_parts.append(f"Past Investigations: {', '.join(inv_strs)}")
    visit_notes = ". ".join(visit_notes_parts) if visit_notes_parts else "None"

    # Clinical findings from examination
    examination = extraction_insights.get("examination", {})
    if isinstance(examination, dict):
        clinical_findings = examination.get("clinical_assessment", "")
        # If no clinical_assessment, try to build from other exam fields
        if not clinical_findings:
            exam_parts = []
            for key in ["cardiovascular_system", "respiratory_system", "central_nervous_system", "musculoskeletal", "other_systems"]:
                if examination.get(key):
                    exam_parts.append(examination.get(key))
            clinical_findings = ". ".join(exam_parts) if exam_parts else ""
    else:
        clinical_findings = str(examination) if examination else ""

    # Provisional diagnosis - join diagnosis names
    diagnosis_list = extraction_insights.get("diagnosis", [])
    if isinstance(diagnosis_list, list):
        diagnosis_names = []
        for d in diagnosis_list:
            if isinstance(d, dict):
                name = d.get("name", "")
                dtype = d.get("type", "")
                if name:
                    diagnosis_names.append(f"{name} ({dtype})" if dtype else name)
            else:
                diagnosis_names.append(str(d))
        provisional_diagnosis = ", ".join(diagnosis_names) if diagnosis_names else ""
    else:
        provisional_diagnosis = str(diagnosis_list) if diagnosis_list else ""

    # Investigations - join test names from all categories
    investigations_data = extraction_insights.get("investigations", {})
    investigation_names = []
    all_inv_tests = _collect_investigation_tests(extraction_insights)
    for test in all_inv_tests:
        if isinstance(test, dict):
            name = test.get("name") or test.get("test_name") or test.get("study_name") or test.get("Test_Name") or ""
            if name:
                investigation_names.append(name)
        elif isinstance(test, str):
            investigation_names.append(test)
    investigations = ", ".join(investigation_names) if investigation_names else ""

    # Doctor advice - combine treatment_plan and follow_up
    treatment_plan = extraction_insights.get("treatmentPlan", {})
    follow_up = extraction_insights.get("followUp", {})
    advice_parts = []

    if isinstance(treatment_plan, list):
        advice_parts.extend([str(item) for item in treatment_plan if item])
    elif isinstance(treatment_plan, dict):
        # Legacy format backward compat
        for key in ("diet_instructions", "activity_instructions", "monitoring_instructions", "medication_adherence"):
            val = treatment_plan.get(key)
            if val:
                advice_parts.append(str(val))
    elif treatment_plan:
        advice_parts.append(str(treatment_plan))

    if isinstance(follow_up, dict):
        if follow_up.get("special_instructions"):
            advice_parts.append(follow_up.get("special_instructions"))
        if follow_up.get("other_instructions"):
            advice_parts.append(follow_up.get("other_instructions"))
    elif follow_up:
        advice_parts.append(str(follow_up))

    doctor_advice = ". ".join(advice_parts) if advice_parts else ""

    # Extract next_followup_date from followUp (skip N/A values)
    next_followup_date = None
    if isinstance(follow_up, dict):
        raw_date = follow_up.get("review_date") or None
        if raw_date and str(raw_date).strip().upper() != "N/A":
            next_followup_date = raw_date

    # Extract referred doctor from referralDetails segment
    referral_details = extraction_insights.get("referralDetails", {})
    if isinstance(referral_details, dict):
        referred_doctor = referral_details.get("referred_to") or "None"
    else:
        referred_doctor = "None"

    # ===== Build prescription block from extraction medicines =====
    prescription_items = []
    prescription_fields = ['prescription', 'medications', 'drugs', 'prescribedMedicines']
    prescription_data = None
    for key in prescription_fields:
        if key in extraction_insights:
            prescription_data = extraction_insights[key]
            break

    if prescription_data:
        # Extract medication list from various structures
        meds_list = []
        if isinstance(prescription_data, list):
            meds_list = prescription_data
        elif isinstance(prescription_data, dict):
            for nested_key in ['prescription', 'medications', 'drugs', 'items']:
                if nested_key in prescription_data and isinstance(prescription_data[nested_key], list):
                    meds_list = prescription_data[nested_key]
                    break
            if not meds_list:
                meds_list = [prescription_data]

        for med in meds_list:
            if not isinstance(med, dict):
                continue

            # Get medicine name from various field names
            med_name = ""
            for nk in ['name', 'medicine_name', 'drugName', 'medication']:
                if nk in med and med[nk]:
                    med_name = med[nk]
                    break
            if not med_name:
                continue

            # Handle multiple field name conventions across templates
            frequency = med.get("frequency") or med.get("timeToTake", "")
            duration_raw = med.get("duration") or med.get("durationDays", "")
            direction = med.get("route") or med.get("direction", "")
            remarks = med.get("remarks", "")
            dosage_form = med.get("dosage_form") or med.get("_form") or med.get("form") or med.get("drug_type", "")
            formulary_name = med.get("_formulary_name", "")
            external_id = med.get("_external_id")

            # Map dosage_form to Raster MedicineType enum; default to TABLET
            medicine_type = _map_to_raster_medicine_type(dosage_form)

            # Build frequency from morning/noon/evening/night qty if no standard frequency
            if not frequency:
                qty_parts = []
                for slot in ["morning_qty", "noon_qty", "evening_qty", "night_qty"]:
                    qty_parts.append(str(med.get(slot, "0")))
                if any(p != "0" for p in qty_parts):
                    frequency = "-".join(qty_parts)

            # Compute order_qty = frequency_count × duration_number
            freq_count = _parse_frequency_count(str(frequency))
            dur_number = _parse_duration_number(str(duration_raw))
            order_qty = freq_count * dur_number

            # Derive duration_type from duration text
            duration_type = _derive_duration_type(str(duration_raw))

            # Parse duration to just the numeric string
            dur_match = re.search(r'(\d+)', str(duration_raw))
            duration_str = dur_match.group(1) if dur_match else str(duration_raw)

            prescription_items.append({
                "medicine_name": med_name,
                "frequency": str(frequency),
                "direction": str(direction),
                "remarks": str(remarks),
                "pharmacy_medicine_id": external_id if external_id else 0,
                "order_qty": order_qty,
                "duration": duration_str,
                "duration_type": duration_type,
                "material_ingredients": str(formulary_name),
                "intake_schedule": str(frequency),
                "medicine_type": medicine_type,
                "third_party": "One_Health"
            })

    prescription_block = {
        "created_user_id": created_user_id,
        "patient_visit_number": visit_number,
        "patient_number": uhid,
        "doctor_id": consultant_id,
        "third_party": "One_Health",
        "pharmacy_prescription_item": prescription_items
    }

    # ===== Build request block from extraction investigations =====
    request_items = []
    all_tests = _collect_investigation_tests(extraction_insights)

    first_dept_id = None
    for test in all_tests:
        if not isinstance(test, dict):
            continue

        test_name = ""
        for nk in ['name', 'test_name', 'Test_Name', 'study_name']:
            if nk in test and test[nk]:
                test_name = test[nk]
                break
        if not test_name:
            continue

        external_id = test.get("_external_id")
        dept_id = _get_department_id_for_material(external_id)
        # Default to LAB (21) if department lookup fails (unmatched or unknown)
        if dept_id is None:
            dept_id = 21
        if first_dept_id is None:
            first_dept_id = dept_id

        request_items.append({
            "material_id": external_id if external_id else 0,
            "qty": 1,
            "unit": "QTY",
            "price": 0,
            "item_value": 0,
            "modified_user_id": created_user_id,
            "doctor_id": consultant_id,
            "department_id": dept_id,
            "alied_name": test_name,
            "material_type": 5,
            "remarks": ""
        })

    request_value = sum(item["item_value"] for item in request_items)

    request_block = {
        "created_user_id": created_user_id,
        "request_value": request_value,
        "patient_name": None,
        "mrn": uhid,
        "visit_number": visit_number,
        "sex": sex,
        "consultant_doctor_id": consultant_id,
        "department_id": first_dept_id if first_dept_id is not None else 21,
        "third_party_name": "One_Health",
        "request_item": request_items
    }

    # Build final payload
    payload = {
        "uhid": uhid,
        "visit_number": visit_number,
        "consultant_id": consultant_id,
        "modified_user_id": created_user_id,
        "next_followup_date": next_followup_date,
        "vitals": vitals,
        "visit_record": {
            "chief_complaint": chief_complaint,
            "duration_of_illness": duration_of_illness,
            "history_of_present_illness": history_of_present_illness,
            "past_history": past_history,
            "clinical_findings": clinical_findings,
            "provisional_diagnosis": provisional_diagnosis,
            "investigations": investigations,
            "doctor_advice": doctor_advice,
            "visit_notes": visit_notes,
            "emr_referred_doctor": referred_doctor
        },
        "prescription": prescription_block,
        "request": request_block
    }

    logger.debug(f"[RASTER_EMR] Formatted payload for uhid={uhid}, visit={visit_number}, "
                 f"medicines={len(prescription_items)}, investigations={len(request_items)}")
    return payload


# ============================================================================
# Raster New OP Integration (RASTER_NEW_OP template)
# ============================================================================


def _compute_gcs(data: Dict[str, Any]) -> Optional[int]:
    """Compute Glasgow Coma Scale total from component scores."""
    scores = [data.get("eyeScore"), data.get("verbalScore"), data.get("motorScore")]
    return sum(scores) if all(s is not None for s in scores) else None


def _convert_date_format(date_str: str) -> Optional[str]:
    """Convert a follow-up date to YYYY-MM-DD (what the Raster API expects).

    The extraction pipeline emits dates in DD-MM-YYYY format (set by
    generate_user_prompt in segment_registry.py). This helper converts
    DD-MM-YYYY (or DD/MM/YYYY) to YYYY-MM-DD for the Raster payload, and
    also accepts YYYY-MM-DD as a tolerance in case extraction ever emits
    that form. Returns None for empty, N/A, or unparseable values so the
    Raster payload never carries raw text in nextFollowUpDate.
    """
    if not date_str or str(date_str).strip().upper() in ("N/A", ""):
        return None
    s = str(date_str).strip()

    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

    m = re.match(r'^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$', s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

    logger.warning(f"[RASTER_NEW_OP] Unexpected follow-up date format '{date_str}' — sending None")
    return None


def extract_raster_template_id(meta: Optional[Dict[str, Any]]) -> Optional[int]:
    """Read the Raster templateId from recording metadata.

    Accepts either the canonical key ``template_id_raster`` or the key
    ``template_id`` as actually sent by Raster iframe clients. Coerces to
    int; returns None if unset or unparseable. Keeps the read behavior in
    one place so every call site agrees on the key-fallback rule.
    """
    if not meta:
        return None
    val = meta.get("template_id_raster")
    if val in (None, ""):
        val = meta.get("template_id")
    if val in (None, ""):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def format_for_raster_new_op(
    extraction_insights: Dict[str, Any],
    uhid: str,
    visit_number: str,
    consultant_id: int = 0,
    modified_user_id: int = 0,
    sex: Optional[str] = None,
    template_id_raster: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Format RASTER_NEW_OP extraction insights to the new Raster API payload schema.

    This is a granular, section-per-key format (unlike the older format_for_raster
    which uses a flat visit_record).

    Args:
        extraction_insights: The extraction insights dict from RASTER_NEW_OP template
        uhid: Patient UHID
        visit_number: Visit number (e.g., "OP/25148074")
        consultant_id: Consultant ID in Raster system
        modified_user_id: User ID for audit trail
        sex: Patient sex
        template_id_raster: Template ID in Raster system (for patientDetail)

    Returns:
        Dict formatted for the new Raster API
    """

    # === patientDetail ===
    follow_up = extraction_insights.get("followUp", {}) or {}
    if not isinstance(follow_up, dict):
        follow_up = {}
    raw_review_date = follow_up.get("review_date") or None
    next_followup_date = _convert_date_format(raw_review_date) if raw_review_date else None

    # Coerce to int in case caller passed a string (iframe clients send "11")
    _tid = None
    if template_id_raster is not None:
        try:
            _tid = int(template_id_raster)
        except (ValueError, TypeError):
            _tid = None

    patient_detail = {
        "uhid": uhid,
        "visitNumber": visit_number,
        "templateId": _tid if _tid is not None else 53,
        "visitStatus": "CHECKED_IN",
        "nextFollowUpDate": next_followup_date,
    }

    # === vitals ===
    vitals_data = extraction_insights.get("vitals") or {}
    systolic = vitals_data.get("systolic_bp")
    diastolic = vitals_data.get("diastolic_bp")
    bp_str = None
    if systolic is not None and diastolic is not None:
        bp_str = f"{systolic}/{diastolic}"

    vitals = {
        "temperature": vitals_data.get("temperature"),
        "pulse": vitals_data.get("pulse"),
        "respiratory": vitals_data.get("respiratory_rate"),
        "spO2": vitals_data.get("spo2"),
        "height": vitals_data.get("height"),
        "weight": vitals_data.get("weight"),
        "bmi": vitals_data.get("bmi"),
        "grbs": vitals_data.get("grbs"),
        "painScore": vitals_data.get("pain_score"),
        "bps": str(systolic) if systolic is not None else None,
        "bpd": str(diastolic) if diastolic is not None else None,
        "bp": bp_str,
    }

    # === clinicalHistory (from HISTORY_OF_PRESENT_ILLNESS segment) ===
    clinical_history = extraction_insights.get("historyOfPresentIllness", [])
    if not isinstance(clinical_history, list):
        clinical_history = []

    # === familyHistory + habit (from HISTORY segment) ===
    history_data = extraction_insights.get("history") or {}
    if not isinstance(history_data, dict):
        history_data = {}
    family_history = history_data.get("familyHistory", [])
    if not isinstance(family_history, list):
        family_history = []
    habits = history_data.get("habits", [])
    if not isinstance(habits, list):
        habits = []

    # === presentingComplaints (from CHIEF_COMPLAINTS segment) ===
    presenting_complaints = extraction_insights.get("chiefComplaints", [])
    if not isinstance(presenting_complaints, list):
        presenting_complaints = []

    # === generalWellness ===
    general_wellness = extraction_insights.get("generalWellness") or {}
    if not isinstance(general_wellness, dict):
        general_wellness = {}
    if general_wellness.get("sleepDuration") is None:
        general_wellness["sleepDuration"] = 0

    # === generalExamination ===
    general_examination = extraction_insights.get("generalExamination", [])
    if not isinstance(general_examination, list):
        general_examination = []

    # === systemicExamination (from EXAMINATION / Neuro segment) ===
    neuro_data = extraction_insights.get("examination") or {}
    if not isinstance(neuro_data, dict):
        neuro_data = {}

    gcs_total = _compute_gcs(neuro_data)

    # Convert pupil type arrays to comma-separated strings
    right_type = neuro_data.get("pupilsRightType", [])
    left_type = neuro_data.get("pupilsLeftType", [])
    if isinstance(right_type, list):
        right_type = ",".join(right_type)
    if isinstance(left_type, list):
        left_type = ",".join(left_type)

    systemic_examination = {
        "upperLimbRight": neuro_data.get("upperLimbRight", ""),
        "upperLimbLeft": neuro_data.get("upperLimbLeft", ""),
        "lowerLimbRight": neuro_data.get("lowerLimbRight", ""),
        "lowerLimpLeft": neuro_data.get("lowerLimbLeft", ""),  # Raster API expects "Limp" (typo in their spec)
        "glasgowComaScale": gcs_total,
        "eyeScore": neuro_data.get("eyeScore"),
        "verbalScore": neuro_data.get("verbalScore"),
        "motorScore": neuro_data.get("motorScore"),
        "pupilsRightSize": neuro_data.get("pupilsRightSize"),
        "pupilsRightType": right_type,
        "pupilsLeftSize": neuro_data.get("pupilsLeftSize"),
        "pupilsLeftType": left_type,
    }

    # === organ system examinations (from SYSTEMIC_EXAMINATION segment) ===
    organ_exam = extraction_insights.get("systemicExamination") or {}
    if not isinstance(organ_exam, dict):
        organ_exam = {}

    cardiovascular = organ_exam.get("cardiovascular", [])
    respiratory = organ_exam.get("respiratory", [])
    abdomen = organ_exam.get("abdomen", [])
    cns = organ_exam.get("cns", [])
    ent = organ_exam.get("ent", [])

    # === advice (from TREATMENT_PLAN segment) ===
    treatment_plan = extraction_insights.get("treatmentPlan", [])
    advice = []
    if isinstance(treatment_plan, list):
        for item in treatment_plan:
            if isinstance(item, str) and item.strip():
                advice.append({"name": item.strip()})
            elif isinstance(item, dict) and item.get("name"):
                advice.append(item)

    # === diagnosis (map type to "Provisional" for Raster API) ===
    raw_diagnosis = extraction_insights.get("diagnosis", [])
    if not isinstance(raw_diagnosis, list):
        raw_diagnosis = []
    diagnosis_list = []
    for d in raw_diagnosis:
        if isinstance(d, dict):
            diagnosis_list.append({
                "name": d.get("name", ""),
                "code": d.get("code", ""),
                "type": "Provisional",
            })
        else:
            diagnosis_list.append(d)

    # === investigationValues + investigationFollowupValues ===
    all_tests = _collect_investigation_tests(extraction_insights)
    investigation_values = []
    investigation_followup_values = []

    for test in all_tests:
        if not isinstance(test, dict):
            continue
        test_name = ""
        for nk in ['name', 'test_name', 'Test_Name', 'study_name']:
            if nk in test and test[nk]:
                test_name = test[nk]
                break
        if not test_name:
            continue

        external_id = test.get("_external_id")
        dept_id = _get_department_id_for_material(external_id)
        # Default to LAB (21) if department lookup fails
        if dept_id is None:
            dept_id = 21

        # Map extraction type to itemType
        test_type = (test.get("type", "") or "").lower()
        if test_type == "laboratory":
            item_type = "INVESTIGATION"
        else:
            item_type = "SERVICE"

        inv_item = {
            "department": test.get("_category", ""),
            "startDuration": None,
            "endDuration": None,
            "unit": "1 qty",
            "unitValue": None,
            "serviceItemId": int(external_id) if external_id else 0,
            "investigationName": test_name,
            "itemType": item_type,
            "itemStatus": None,
            "hisItemId": None,
            "favourite": False,
        }

        # All investigations go to investigationValues (no follow-up split
        # since _is_followup is not populated by the matching pipeline)
        investigation_values.append(inv_item)

    # === medications (from PRESCRIPTION segment) ===
    medications = []
    prescription_fields = ['prescription', 'medications', 'drugs', 'prescribedMedicines']
    prescription_data = None
    for key in prescription_fields:
        if key in extraction_insights:
            prescription_data = extraction_insights[key]
            break

    if prescription_data:
        meds_list = []
        if isinstance(prescription_data, list):
            meds_list = prescription_data
        elif isinstance(prescription_data, dict):
            for nested_key in ['prescription', 'medications', 'drugs', 'items']:
                if nested_key in prescription_data and isinstance(prescription_data[nested_key], list):
                    meds_list = prescription_data[nested_key]
                    break
            if not meds_list:
                meds_list = [prescription_data]

        for med in meds_list:
            if not isinstance(med, dict):
                continue

            med_name = ""
            for nk in ['name', 'medicine_name', 'drugName', 'medication']:
                if nk in med and med[nk]:
                    med_name = med[nk]
                    break
            if not med_name:
                continue

            # Parse quantities
            m_qty = med.get("morning_qty", "")
            a_qty = med.get("noon_qty", "")
            n_qty = med.get("evening_qty", "")
            e_qty = med.get("night_qty", "")

            def _parse_qty(v):
                if not v or str(v).strip() == "":
                    return ""
                try:
                    return float(v)
                except (ValueError, TypeError):
                    return v

            m_val = _parse_qty(m_qty)
            a_val = _parse_qty(a_qty)
            n_val = _parse_qty(n_qty)
            e_val = _parse_qty(e_qty)

            # Build frequency string
            freq_parts = [str(m_val) if m_val != "" else "0",
                          str(a_val) if a_val != "" else "0",
                          str(n_val) if n_val != "" else "0"]
            frequency = " - ".join(freq_parts)

            # Duration
            duration_raw = med.get("durationDays") or med.get("duration", "")
            dur_match = re.search(r'(\d+)', str(duration_raw))
            duration_number = int(dur_match.group(1)) if dur_match else 1
            duration_str = f"{duration_number} days" if dur_match else str(duration_raw) if duration_raw else ""

            # Total quantity
            freq_count = _parse_frequency_count(str(frequency))
            total_qty = freq_count * duration_number

            # Medicine type
            dosage_form = med.get("dosage_form") or med.get("_form") or med.get("form") or med.get("drug_type", "")
            medicine_type = _map_to_raster_medicine_type(dosage_form)

            # External IDs from medicine matching (_external_id, _formulary_name, _form, _product_code are enriched)
            external_id = med.get("_external_id")
            formulary_name = med.get("_formulary_name", "")
            product_code = med.get("_product_code", "")

            medications.append({
                "productId": str(external_id) if external_id else "",
                "productCode": product_code,
                "productName": med_name,
                "productGenericName": formulary_name,
                "medicineType": medicine_type,
                "type": "Daily",
                "frequency": frequency,
                "consumableQuantity": "",
                "unit": "",
                "duration": duration_str,
                "when": med.get("timeToTake", ""),
                "where": "",
                "route": med.get("route", ""),
                "details": "",
                "notes": med.get("remarks", ""),
                "startFrom": "",
                "time": "",
                "medicationUse": [],
                "M": m_val,
                "A": a_val,
                "N": n_val,
                "E": e_val,
                "totalQuantity": total_qty,
                "moleculeName": formulary_name,
                "unitId": None,
                "status": None,
                "prescriptionNumber": None,
                "prescriptionItemId": None,
            })

    # === visitNote ===
    visit_note_parts = []
    if follow_up.get("special_instructions"):
        visit_note_parts.append(follow_up["special_instructions"])
    if follow_up.get("other_instructions"):
        visit_note_parts.append(follow_up["other_instructions"])
    visit_note = {"note": ". ".join(visit_note_parts) if visit_note_parts else ""}

    # === Build final payload ===
    payload = {
        "patientDetail": patient_detail,
        "vitals": vitals,
        "clinicalHistory": clinical_history,
        "familyHistory": family_history,
        "presentingComplaints": presenting_complaints,
        "generalWellness": general_wellness,
        "generalExamination": general_examination,
        "systemicExamination": systemic_examination,
        "cardiovascular": cardiovascular if isinstance(cardiovascular, list) else [],
        "respiratory": respiratory if isinstance(respiratory, list) else [],
        "abdomen": abdomen if isinstance(abdomen, list) else [],
        "cns": cns if isinstance(cns, list) else [],
        "ent": ent if isinstance(ent, list) else [],
        "advice": advice,
        "habit": habits,
        "investigationValues": investigation_values,
        "investigationFollowupValues": investigation_followup_values,
        "diagnosis": diagnosis_list,
        "medications": medications,
        "assessmentStatus": "CHECKED_IN",
        "visitNote": visit_note,
        "user": "emr",
    }

    logger.debug(
        f"[RASTER_NEW_OP] Formatted payload for uhid={uhid}, visit={visit_number}, "
        f"medicines={len(medications)}, investigations={len(investigation_values)}, "
        f"followup_inv={len(investigation_followup_values)}"
    )
    return payload


def _collect_investigation_tests(extraction_insights: Dict[str, Any]) -> List[Dict]:
    """Collect all investigation test dicts from extraction insights (handles both dict and list formats)."""
    investigations_data = extraction_insights.get("investigations", {})
    tests = []

    if isinstance(investigations_data, dict):
        for category in ["laboratory_tests", "imaging_studies", "other_tests"]:
            cat_tests = investigations_data.get(category, [])
            if isinstance(cat_tests, list):
                tests.extend(cat_tests)
    elif isinstance(investigations_data, list):
        tests.extend(investigations_data)

    return tests


async def send_to_raster_emr(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send formatted data to Raster General EMR API.

    Args:
        payload: The formatted payload from format_for_raster()

    Returns:
        Dict with status_code, success flag, and response body
    """
    if not RASTER_GENERAL_EMR_URL:
        logger.warning("[RASTER_EMR] RASTER_GENERAL_EMR_URL not configured - skipping")
        return {
            "success": False,
            "skipped": True,
            "reason": "RASTER_GENERAL_EMR_URL not configured"
        }

    # Sanitize escaped slashes before sending
    payload = _sanitize_escaped_slashes(payload)

    logger.info(f"[RASTER_EMR] Sending to {RASTER_GENERAL_EMR_URL}")
    logger.debug(f"[RASTER_EMR] Payload summary: uhid={payload.get('uhid')}, visit={payload.get('visit_number')}, consultant_id={payload.get('consultant_id')}, modified_user_id={payload.get('modified_user_id')}")
    logger.debug(f"[RASTER_EMR] Full payload: {json.dumps(payload, indent=2, default=str)}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                RASTER_GENERAL_EMR_URL,
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            logger.info(f"[RASTER_EMR] Response status: {response.status_code}")

            # Try to parse response as JSON
            try:
                body = response.json()
            except Exception:
                body = {"raw": response.text}

            success = 200 <= response.status_code < 300

            if success:
                logger.info(f"[RASTER_EMR] ✅ Successfully posted to Raster General EMR")
            else:
                logger.error(f"[RASTER_EMR] ❌ Failed: {body}")

            return {
                "status_code": response.status_code,
                "body": body,
                "success": success
            }

    except httpx.TimeoutException:
        logger.error("[RASTER_EMR] Request timed out after 30 seconds")
        return {
            "status_code": 408,
            "body": {"error": "Request timeout"},
            "success": False
        }
    except httpx.RequestError as e:
        logger.error(f"[RASTER_EMR] Request failed: {e}")
        return {
            "status_code": 500,
            "body": {"error": str(e)},
            "success": False
        }


# ============================================================================
# NICU Inpatient List - Fetch patients from Raster/Neopaed system
# ============================================================================

async def fetch_nicu_inpatient_list() -> Dict[str, Any]:
    """
    Fetch NICU inpatient list from Raster/Neopaed hospital API and sync to database.

    Calls the NICU inpatient list API and syncs patients to the database:
    - uhid -> patient_id
    - All other fields stored in add_info JSONB column
    - If patient exists (by uhid), only updates add_info
    - If patient doesn't exist, creates new patient record

    Returns:
        Dict with success status, counts of created/updated patients, and any errors
    """
    # Import here to avoid circular dependency
    from services.supabase_service import supabase, retry_on_network_error

    # Validate environment configuration
    if not RASTER_API_URL:
        error_msg = "RASTER_API_URL environment variable is not set"
        logger.error(f"[RASTER_API:NICU] {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "created": 0,
            "updated": 0
        }

    nicu_api_url = f"{RASTER_API_URL}/get-nicu-inpatient-list"
    logger.info(f"[RASTER_API:NICU] Fetching inpatient list from {nicu_api_url}")

    created_count = 0
    updated_count = 0
    errors: List[Dict[str, Any]] = []

    try:
        # Fetch data from external hospital API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(nicu_api_url)
            response.raise_for_status()
            patients_data = response.json()

        logger.info(f"[RASTER_API:NICU] Fetched {len(patients_data)} patients from Neopaed API")

        for patient in patients_data:
            try:
                uhid = patient.get("uhid")
                if not uhid:
                    errors.append({"error": "Missing uhid", "data": patient})
                    continue

                # Extract fields for add_info (everything except uhid)
                add_info = {
                    "visitNumber": patient.get("visitNumber"),
                    "babyName": patient.get("babyName"),
                    "gender": patient.get("gender"),
                    "birthDate": patient.get("birthDate"),
                    "roomNo": patient.get("roomNo"),
                    "bedNo": patient.get("bedNo"),
                    "gestation": patient.get("gestation"),
                    "source": "neopaed_api",
                    "synced_at": datetime.now(timezone.utc).isoformat()
                }

                # Check if patient exists by uhid (patient_id)
                def _check_patient():
                    return supabase.table("patients").select("id, patient_id").eq("patient_id", uhid).execute()

                existing = retry_on_network_error(_check_patient)

                if existing.data:
                    # Patient exists - update add_info only
                    patient_uuid = existing.data[0]["id"]

                    def _update_patient():
                        return supabase.table("patients").update({
                            "add_info": add_info,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", patient_uuid).execute()

                    retry_on_network_error(_update_patient)
                    updated_count += 1
                    logger.debug(f"[RASTER_API:NICU] Updated patient {uhid}")
                else:
                    # Patient doesn't exist - create new record
                    new_patient = {
                        "patient_id": uhid,
                        "full_name": patient.get("babyName"),
                        "gender": patient.get("gender"),
                        "date_of_birth": patient.get("birthDate"),
                        "add_info": add_info,
                        "is_anonymized": False
                    }

                    def _create_patient():
                        return supabase.table("patients").insert(new_patient).execute()

                    retry_on_network_error(_create_patient)
                    created_count += 1
                    logger.debug(f"[RASTER_API:NICU] Created patient {uhid}")

            except Exception as e:
                error_msg = f"Failed to process patient {patient.get('uhid', 'unknown')}: {str(e)}"
                logger.error(f"[RASTER_API:NICU] {error_msg}")
                errors.append({"uhid": patient.get("uhid"), "error": str(e)})

        logger.info(f"[RASTER_API:NICU] Completed: {created_count} created, {updated_count} updated, {len(errors)} errors")

        return {
            "success": True,
            "created": created_count,
            "updated": updated_count,
            "total_processed": created_count + updated_count,
            "errors": errors if errors else None,
            "source_url": nicu_api_url
        }

    except httpx.HTTPError as e:
        error_msg = f"Failed to fetch from Neopaed API: {str(e)}"
        logger.error(f"[RASTER_API:NICU] {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "created": created_count,
            "updated": updated_count
        }
    except Exception as e:
        error_msg = f"Unexpected error during NICU patient fetch: {str(e)}"
        logger.error(f"[RASTER_API:NICU] {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "created": created_count,
            "updated": updated_count
        }


# ============================================================================
# OP Baby List - Fetch outpatient babies from Raster/Neopaed system
# ============================================================================

async def fetch_op_baby_list() -> Dict[str, Any]:
    """
    Fetch today's OP (outpatient) baby list from Raster/Neopaed hospital API and sync to database.

    Calls the OP baby list API and syncs patients to the database:
    - uhid -> patient_id
    - All other fields stored in add_info JSONB column
    - If patient exists (by uhid), only updates add_info
    - If patient doesn't exist, creates new patient record

    Returns:
        Dict with success status, counts of created/updated patients, and any errors
    """
    # Import here to avoid circular dependency
    from services.supabase_service import supabase, retry_on_network_error

    # Validate environment configuration
    if not RASTER_API_URL:
        error_msg = "RASTER_API_URL environment variable is not set"
        logger.error(f"[RASTER_API:OP] {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "created": 0,
            "updated": 0
        }

    op_api_url = f"{RASTER_API_URL}/today-op-baby-list"
    logger.info(f"[RASTER_API:OP] Fetching OP baby list from {op_api_url}")

    created_count = 0
    updated_count = 0
    errors: List[Dict[str, Any]] = []

    try:
        # Fetch data from external hospital API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(op_api_url)
            response.raise_for_status()
            patients_data = response.json()

        logger.info(f"[RASTER_API:OP] Fetched {len(patients_data)} patients from Neopaed OP API")

        for patient in patients_data:
            try:
                uhid = patient.get("uhid")
                if not uhid:
                    errors.append({"error": "Missing uhid", "data": patient})
                    continue

                # Extract fields for add_info (everything except uhid)
                # Note: OP uses visitId instead of visitNumber, no roomNo/bedNo
                add_info = {
                    "visitId": patient.get("visitId"),
                    "babyName": patient.get("babyName"),
                    "gender": patient.get("gender"),
                    "birthDate": patient.get("birthDate"),
                    "gestation": patient.get("gestation"),
                    "source": "neopaed_op_api",
                    "synced_at": datetime.now(timezone.utc).isoformat()
                }

                # Check if patient exists by uhid (patient_id)
                def _check_patient():
                    return supabase.table("patients").select("id, patient_id").eq("patient_id", uhid).execute()

                existing = retry_on_network_error(_check_patient)

                if existing.data:
                    # Patient exists - update add_info only
                    patient_uuid = existing.data[0]["id"]

                    def _update_patient():
                        return supabase.table("patients").update({
                            "add_info": add_info,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", patient_uuid).execute()

                    retry_on_network_error(_update_patient)
                    updated_count += 1
                    logger.debug(f"[RASTER_API:OP] Updated patient {uhid}")
                else:
                    # Patient doesn't exist - create new record
                    new_patient = {
                        "patient_id": uhid,
                        "full_name": patient.get("babyName"),
                        "gender": patient.get("gender"),
                        "date_of_birth": patient.get("birthDate"),
                        "add_info": add_info,
                        "is_anonymized": False
                    }

                    def _create_patient():
                        return supabase.table("patients").insert(new_patient).execute()

                    retry_on_network_error(_create_patient)
                    created_count += 1
                    logger.debug(f"[RASTER_API:OP] Created patient {uhid}")

            except Exception as e:
                error_msg = f"Failed to process patient {patient.get('uhid', 'unknown')}: {str(e)}"
                logger.error(f"[RASTER_API:OP] {error_msg}")
                errors.append({"uhid": patient.get("uhid"), "error": str(e)})

        logger.info(f"[RASTER_API:OP] Completed: {created_count} created, {updated_count} updated, {len(errors)} errors")

        return {
            "success": True,
            "created": created_count,
            "updated": updated_count,
            "total_processed": created_count + updated_count,
            "errors": errors if errors else None,
            "source_url": op_api_url
        }

    except httpx.HTTPError as e:
        error_msg = f"Failed to fetch from Neopaed OP API: {str(e)}"
        logger.error(f"[RASTER_API:OP] {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "created": created_count,
            "updated": updated_count
        }
    except Exception as e:
        error_msg = f"Unexpected error during OP baby fetch: {str(e)}"
        logger.error(f"[RASTER_API:OP] {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "created": created_count,
            "updated": updated_count
        }


# ============================================================================
# Combined Neopaed Patient Sync - Fetches both NICU and OP patients
# ============================================================================

async def fetch_all_neopaed_patients() -> Dict[str, Any]:
    """
    Fetch all patients from Neopaed system (both NICU inpatients and OP babies).

    Calls both APIs and aggregates results:
    - NICU inpatient list (get-nicu-inpatient-list)
    - OP baby list (today-op-baby-list)

    Returns:
        Dict with combined success status, counts, and breakdown by source
    """
    logger.info("[RASTER_API:ALL] Starting combined Neopaed patient sync")

    # Fetch from both sources
    nicu_result = await fetch_nicu_inpatient_list()
    op_result = await fetch_op_baby_list()

    # Aggregate results
    total_created = nicu_result.get("created", 0) + op_result.get("created", 0)
    total_updated = nicu_result.get("updated", 0) + op_result.get("updated", 0)

    # Combine errors
    all_errors = []
    if nicu_result.get("errors"):
        all_errors.extend([{**e, "source": "nicu"} for e in nicu_result["errors"]])
    if op_result.get("errors"):
        all_errors.extend([{**e, "source": "op"} for e in op_result["errors"]])

    # Overall success if at least one succeeded
    overall_success = nicu_result.get("success", False) or op_result.get("success", False)

    logger.info(
        f"[RASTER_API:ALL] Combined sync completed - "
        f"NICU: {nicu_result.get('created', 0)}+{nicu_result.get('updated', 0)}, "
        f"OP: {op_result.get('created', 0)}+{op_result.get('updated', 0)}"
    )

    return {
        "success": overall_success,
        "created": total_created,
        "updated": total_updated,
        "total_processed": total_created + total_updated,
        "nicu": {
            "success": nicu_result.get("success", False),
            "created": nicu_result.get("created", 0),
            "updated": nicu_result.get("updated", 0),
            "error": nicu_result.get("error")
        },
        "op": {
            "success": op_result.get("success", False),
            "created": op_result.get("created", 0),
            "updated": op_result.get("updated", 0),
            "error": op_result.get("error")
        },
        "errors": all_errors if all_errors else None
    }


# Alias for backward compatibility
initialize_patients_neopaed = fetch_nicu_inpatient_list

"""
NEO_ADMISSION Raster API Lookup Tables

Field-level value normalization for NEO_ADMISSION payloads before sending
to the Neopaed API. Reuses shared normalizers from neo_proforma_lookups.py
and navigates the nested admission payload structure.

Reference: references/Neopaed - One Hat integration values reference sheet.md
"""

import logging
import re
from typing import Dict, Any

from services.neo_proforma_lookups import (
    normalize_birth_status,
    normalize_blood_group,
    normalize_sex,
    normalize_yes_no,
    normalize_na_yes_no,
    normalize_cord_blood_gas,
    strip_gestation_suffix,
    convert_complication_to_id,
    convert_comma_separated_to_int_array,
    convert_comma_separated_to_string_array,
    _normalize_field,
    _capitalize_fields,
    _lookup,
)

logger = logging.getLogger(__name__)


# ============================================================================
# ADMISSION DETAILS — ENUM MAPS
# ============================================================================

CFT_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not applicable": "N/A",
    "not assessed": "N/A",
    "< 3 seconds": "< 3 Seconds",
    "<3 seconds": "< 3 Seconds",
    "less than 3 seconds": "< 3 Seconds",
    "less than 3": "< 3 Seconds",
    "normal": "< 3 Seconds",
    "3-5 seconds": "3-5 Seconds",
    "3 to 5 seconds": "3-5 Seconds",
    ">5 seconds": ">5 Seconds",
    "> 5 seconds": ">5 Seconds",
    "more than 5 seconds": ">5 Seconds",
    "more than 5": ">5 Seconds",
    "prolonged": "Prolonged",
}

CRY_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "normal consolable": "Normal consolable",
    "normal": "Normal consolable",
    "consolable": "Normal consolable",
    "good cry": "Normal consolable",
    "lusty cry": "Normal consolable",
    "abnormal inconsolable": "Abnormal Inconsolable",
    "abnormal": "Abnormal Inconsolable",
    "inconsolable": "Abnormal Inconsolable",
    "high pitched cry": "High pitched cry",
    "high pitched": "High pitched cry",
    "shrill": "High pitched cry",
    "weak cry": "Weak Cry",
    "weak": "Weak Cry",
    "feeble cry": "Weak Cry",
    "feeble": "Weak Cry",
    "sedated/paralysed": "Sedated/Paralysed",
    "sedated": "Sedated/Paralysed",
    "paralysed": "Sedated/Paralysed",
    "paralyzed": "Sedated/Paralysed",
}

HERNIA_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "no hernia": "No hernia",
    "none": "No hernia",
    "no": "No hernia",
    "absent": "No hernia",
    "nil": "No hernia",
    "right inguinal hernia": "Right Inguinal hernia",
    "right inguinal": "Right Inguinal hernia",
    "right hernia": "Right Inguinal hernia",
    "left inguinal hernia": "Left Inguinal hernia",
    "left inguinal": "Left Inguinal hernia",
    "left hernia": "Left Inguinal hernia",
    "umbilical/para umbilical hernia": "Umbilical/para umbilical hernia",
    "umbilical hernia": "Umbilical/para umbilical hernia",
    "para umbilical hernia": "Umbilical/para umbilical hernia",
    "paraumbilical hernia": "Umbilical/para umbilical hernia",
    "obstructed/strangulated": "Obstructed/strangulated",
    "obstructed": "Obstructed/strangulated",
    "strangulated": "Obstructed/strangulated",
}

ABDOMEN_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "normal": "Normal",
    "soft": "Normal",
    "soft and non-tender": "Normal",
    "scaphoid": "Scaphoid",
    "distended": "Distended",
    "distention": "Distended",
    "abdominal distension": "Distended",
}

TONE_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "normal": "Normal",
    "good": "Normal",
    "hypotonia": "Hypotonia",
    "hypotonic": "Hypotonia",
    "low tone": "Hypotonia",
    "floppy": "Hypotonia",
    "hypertonia": "Hypertonia",
    "hypertonic": "Hypertonia",
    "increased tone": "Hypertonia",
    "sedated/paralysed": "Sedated/Paralysed",
    "sedated": "Sedated/Paralysed",
    "paralysed": "Sedated/Paralysed",
    "paralyzed": "Sedated/Paralysed",
}

ACTIVITY_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "normal": "Normal",
    "active": "Normal",
    "alert": "Normal",
    "comatosed": "Comatosed",
    "comatose": "Comatosed",
    "decreased": "Decreased",
    "lethargic": "Decreased",
    "reduced": "Decreased",
    "increased": "Increased",
    "hyperactive": "Increased",
    "irritable": "Irritable",
    "sedated/paralysed": "Sedated/Paralysed",
    "sedated": "Sedated/Paralysed",
    "paralysed": "Sedated/Paralysed",
    "paralyzed": "Sedated/Paralysed",
}

AIR_ENTRY_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "equal": "Equal",
    "bilateral equal": "Equal",
    "good": "Equal",
    "adequate": "Equal",
    "normal": "Equal",
    "reduced bilateral": "Reduced Bilateral",
    "reduced bilaterally": "Reduced Bilateral",
    "bilateral reduced": "Reduced Bilateral",
    "reduced both sides": "Reduced Bilateral",
    "reduced right": "Reduced Right",
    "right reduced": "Reduced Right",
    "reduced on right": "Reduced Right",
    "reduced left": "Reduced Left",
    "left reduced": "Reduced Left",
    "reduced on left": "Reduced Left",
}

UMBILICUS_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "healthy": "Healthy",
    "clean": "Healthy",
    "dry": "Healthy",
    "normal": "Healthy",
    "possible infection": "Possible infection",
    "omphalitis": "Omphalitis",
    "infected": "Omphalitis",
    "omphalocele": "Omphalocele",
    "gastroschisis": "Gastroschisis",
    "hernia": "Hernia",
    "umbilical hernia": "Hernia",
    "meconium stained": "Meconium Stained",
    "meconium": "Meconium Stained",
    "large": "Large",
    "shrivelled": "Shrivelled",
    "shriveled": "Shrivelled",
}

RETRACTIONS_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "no": "No",
    "none": "No",
    "absent": "No",
    "nil": "No",
    "mild": "Mild",
    "minimal": "Mild",
    "moderate": "Moderate",
    "severe": "Severe",
    "significant": "Severe",
}

CHEST_MOVEMENT_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "symmetrical": "Symmetrical",
    "symmetric": "Symmetrical",
    "equal": "Symmetrical",
    "normal": "Symmetrical",
    "asymmetrical": "Asymmetrical",
    "asymmetric": "Asymmetrical",
    "unequal": "Asymmetrical",
}

S1S2_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "normal": "Normal",
    "heard": "Normal",
    "abnormal": "Abnormal",
}

MURMUR_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "absent": "Absent",
    "no": "Absent",
    "no murmur": "Absent",
    "none": "Absent",
    "nil": "Absent",
    "present": "Present",
    "yes": "Present",
    "heard": "Present",
}

COLOR_MAP: Dict[str, str] = {
    "pink": "Pink",
    "well perfused": "Pink",
    "yellow": "Yellow",
    "jaundiced": "Yellow",
    "icteric": "Yellow",
    "pale": "Pale",
    "pallor": "Pale",
    "acral cyanosis": "Acral Cyanosis",
    "peripheral cyanosis": "Acral Cyanosis",
    "acrocyanosis": "Acral Cyanosis",
    "central cyanosis": "Central Cyanosis",
    "cyanosed": "Central Cyanosis",
    "cyanotic": "Central Cyanosis",
}

BOWEL_SOUNDS_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "normal": "Normal",
    "present": "Normal",
    "heard": "Normal",
    "increased": "Increased",
    "hyperactive": "Increased",
    "decreased": "Decreased",
    "sluggish": "Decreased",
    "hypoactive": "Decreased",
    "absent": "Absent",
    "none": "Absent",
    "nil": "Absent",
}

PUPILS_MAP: Dict[str, str] = {
    "not examined": "Not Examined",
    "not assessed": "Not Examined",
    "n/a": "Not Examined",
    "na": "Not Examined",
    "equal and reacting to light": "Equal and reacting to light",
    "equal and reactive": "Equal and reacting to light",
    "brisk": "Equal and reacting to light",
    "reactive": "Equal and reacting to light",
    "normal": "Equal and reacting to light",
    "bilaterally reactive": "Equal and reacting to light",
    "abnormal": "Abnormal",
    "unequal": "Abnormal",
    "fixed": "Abnormal",
    "dilated": "Abnormal",
    "non-reactive": "Abnormal",
    "non reactive": "Abnormal",
}

ANTERIOR_FONTANELLE_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "normal": "Normal",
    "normotensive": "Normal",
    "flat": "Normal",
    "open": "Normal",
    "depressed": "Depressed",
    "sunken": "Depressed",
    "bulging": "Bulging",
    "tense": "Bulging",
    "full": "Bulging",
}

NEONATAL_REFLEXES_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "normal": "Normal",
    "present": "Normal",
    "suppressed": "Suppressed",
    "depressed": "Suppressed",
    "absent": "Absent",
    "exaggerated": "Exaggerated",
    "brisk": "Exaggerated",
    "sedated/paralysed": "Sedated/Paralysed",
    "sedated": "Sedated/Paralysed",
    "paralysed": "Sedated/Paralysed",
    "paralyzed": "Sedated/Paralysed",
}

GENITALIA_MAP: Dict[str, str] = {
    "normal": "Normal",
    "abnormal": "Abnormal",
    "ambiguous": "Abnormal",
}

PULSES_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "normal": "Normal",
    "palpable": "Normal",
    "good": "Normal",
    "well felt": "Normal",
    "bounding": "Bounding",
    "feeble/weak": "Feeble/Weak",
    "feeble": "Feeble/Weak",
    "weak": "Feeble/Weak",
    "thready": "Feeble/Weak",
    "absent": "Absent",
    "not palpable": "Absent",
    "not felt": "Absent",
}

NA_YES_NO_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "not assessed": "N/A",
    "none": "N/A",
    "yes": "Yes",
    "true": "Yes",
    "present": "Yes",
    "no": "No",
    "false": "No",
    "absent": "No",
    "nil": "No",
}

ADMITTED_FROM_MAP: Dict[str, str] = {
    "labour ward": "Labour ward",
    "labor ward": "Labour ward",
    "labour room": "Labour ward",
    "labor room": "Labour ward",
    "delivery room": "Labour ward",
    "postnatal ward": "Postnatal ward",
    "postnatal": "Postnatal ward",
    "post natal ward": "Postnatal ward",
    "op": "OP",
    "outpatient": "OP",
    "out patient": "OP",
    "opd": "OP",
    "outside hospital": "Outside Hospital",
    "outside": "Outside Hospital",
    "referred": "Outside Hospital",
    "external": "Outside Hospital",
    "obstetric theatres": "Obstetric theatres",
    "obstetric theatre": "Obstetric theatres",
    "ot": "Obstetric theatres",
    "operation theatre": "Obstetric theatres",
    "operation theater": "Obstetric theatres",
}


# ============================================================================
# PROCEDURES — ENUM MAPS
# ============================================================================

INITIAL_XRAY_MAP: Dict[str, str] = {
    "not done": "Not done",
    "no": "Not done",
    "none": "Not done",
    "not indicated": "Not indicated",
    "performed": "Performed",
    "done": "Performed",
    "yes": "Performed",
}

SEPSIS_SCREEN_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "yes": "Yes",
    "done": "Yes",
    "sent": "Yes",
    "no": "No",
    "not done": "No",
    "none": "No",
}

ENTERAL_FEEDING_MAP: Dict[str, str] = {
    "n/a": "N/A",
    "na": "N/A",
    "yes": "Yes",
    "started": "Yes",
    "initiated": "Yes",
    "no": "No",
    "nil": "No",
    "none": "No",
    "not started": "No",
    "npo": "No",
}


# ============================================================================
# NORMALIZER FUNCTIONS (admission-specific)
# ============================================================================

def _normalize_admission_enum(obj: Dict[str, Any], field: str, lookup_map: Dict[str, str]) -> None:
    """Normalize a field in-place using a lookup map, only if the field exists."""
    if field in obj:
        obj[field] = _lookup(obj[field], lookup_map)


def apply_raster_lookups_to_neo_admission(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply all Raster lookup transformations to a NEO_ADMISSION payload.

    Navigates the nested admission structure and normalizes enum fields,
    Yes/No fields, gestation suffixes, and complication IDs.
    """

    # 1. Baby section — resuscitation Yes/No fields + capitalize
    baby = payload.get("baby")
    if isinstance(baby, dict):
        for field in ["ventilationRequired", "deliveryCpap"]:
            if field in baby:
                baby[field] = normalize_yes_no(baby[field])
        if "surfactantGiven" in baby:
            baby["surfactantGiven"] = normalize_na_yes_no(baby["surfactantGiven"])
        _capitalize_fields(baby, ["descriptionOfResuscitation"])

    # 2. Admission section — seenBy resolution + enum normalization
    admission = payload.get("admission")
    if isinstance(admission, dict):
        # Resolve seenBy names to IDs (flat integer array)
        seen_by = admission.get("seenBy")
        if isinstance(seen_by, list):
            from services.doctor_lookups import resolve_seen_by_ids, DEFAULT_SEEN_BY_ID
            resolved = []
            for item in seen_by:
                if isinstance(item, (int, float)):
                    resolved.append(int(item))
                elif isinstance(item, str) and item.strip():
                    if item.strip().isdigit():
                        resolved.append(int(item.strip()))
                    else:
                        from services.doctor_lookups import lookup_doctor_id
                        doc_id = lookup_doctor_id(item.strip())
                        if doc_id is not None:
                            resolved.append(doc_id)
                elif isinstance(item, dict) and "id" in item:
                    # Backward compat: handle {"id": ...} format
                    val = item["id"]
                    if isinstance(val, int) and val > 0:
                        resolved.append(val)
                    elif isinstance(val, str) and val.strip().isdigit():
                        resolved.append(int(val.strip()))
            admission["seenBy"] = resolved or [DEFAULT_SEEN_BY_ID]

        # Yes/No fields in admission
        if "ventilation" in admission:
            admission["ventilation"] = normalize_yes_no(admission["ventilation"])
        _normalize_field(admission, "initialBloodGas", normalize_cord_blood_gas)

        # Enum fields (physical exam — now inside admission)
        _normalize_admission_enum(admission, "cft", CFT_MAP)
        _normalize_admission_enum(admission, "cry", CRY_MAP)
        _normalize_admission_enum(admission, "herina", HERNIA_MAP)
        _normalize_admission_enum(admission, "abdomen", ABDOMEN_MAP)
        _normalize_admission_enum(admission, "tone", TONE_MAP)
        _normalize_admission_enum(admission, "activity", ACTIVITY_MAP)
        _normalize_admission_enum(admission, "airEntry", AIR_ENTRY_MAP)
        _normalize_admission_enum(admission, "umbilicus", UMBILICUS_MAP)
        _normalize_admission_enum(admission, "retractions", RETRACTIONS_MAP)
        _normalize_admission_enum(admission, "chestMovement", CHEST_MOVEMENT_MAP)
        _normalize_admission_enum(admission, "s1s2", S1S2_MAP)
        _normalize_admission_enum(admission, "murmur", MURMUR_MAP)
        _normalize_admission_enum(admission, "color", COLOR_MAP)
        _normalize_admission_enum(admission, "bowelSounds", BOWEL_SOUNDS_MAP)
        _normalize_admission_enum(admission, "pupils", PUPILS_MAP)
        _normalize_admission_enum(admission, "anteriorFontanelle", ANTERIOR_FONTANELLE_MAP)
        _normalize_admission_enum(admission, "neonatalReflexes", NEONATAL_REFLEXES_MAP)
        _normalize_admission_enum(admission, "genitalia", GENITALIA_MAP)
        _normalize_admission_enum(admission, "centralPulses", PULSES_MAP)
        _normalize_admission_enum(admission, "peripheralPulses", PULSES_MAP)
        _normalize_admission_enum(admission, "femoralPulses", PULSES_MAP)
        _normalize_admission_enum(admission, "admittedFrom", ADMITTED_FROM_MAP)

        # N/A / Yes / No fields
        for field in ["hepatomegaly", "splenomegaly", "seizures"]:
            if field in admission:
                admission[field] = _lookup(admission[field], NA_YES_NO_MAP, default="N/A")

        # Capitalize free-text fields in admission
        _capitalize_fields(admission, ["referralReason", "majorComplaints", "abnormalities"])

    # 3. Medical History — Yes/No fields + problem ID validation
    med_history = payload.get("medicalHistory")
    if isinstance(med_history, dict):
        for field in ["smoking", "alcohol", "tobacco"]:
            if field in med_history:
                med_history[field] = normalize_yes_no(med_history[field])

        # Validate medicalProblems[].problemsId range (1-90)
        problems = med_history.get("medicalProblems")
        if isinstance(problems, list):
            for prob in problems:
                if isinstance(prob, dict) and "problemsId" in prob:
                    pid = prob["problemsId"]
                    if isinstance(pid, str) and pid.isdigit():
                        prob["problemsId"] = int(pid)

    # 4. Pregnancy — complication IDs + scan gestation cleanup
    pregnancy = payload.get("pregnancy")
    if isinstance(pregnancy, dict):
        # Complication IDs (text → integer conversion)
        complications = pregnancy.get("complication")
        if isinstance(complications, list):
            for comp in complications:
                if isinstance(comp, dict) and "complicationId" in comp:
                    comp["complicationId"] = convert_complication_to_id(comp["complicationId"])

        # Scan gestation cleanup — strip "weeks" suffix
        for scan_key in ["datingScanDetails", "anomalyScanDetails"]:
            scan = pregnancy.get(scan_key)
            if isinstance(scan, dict) and "gestation" in scan:
                scan["gestation"] = strip_gestation_suffix(scan["gestation"])

        for scan_key in ["otherScanDetails", "dopplerScanDetails"]:
            scans = pregnancy.get(scan_key)
            if isinstance(scans, list):
                for scan in scans:
                    if isinstance(scan, dict) and "gestation" in scan:
                        scan["gestation"] = strip_gestation_suffix(scan["gestation"])

    # 5. Procedures — uac/uvc status + enum fields + drug lookups
    procedures = payload.get("procedures")
    if isinstance(procedures, dict):
        for line_key in ["uac", "uvc"]:
            line = procedures.get(line_key)
            if isinstance(line, dict) and "status" in line:
                line["status"] = normalize_yes_no(line["status"])

        # Enum fields
        _normalize_admission_enum(procedures, "initialxray", INITIAL_XRAY_MAP)
        _normalize_admission_enum(procedures, "sepsisScreen", SEPSIS_SCREEN_MAP)
        _normalize_admission_enum(procedures, "enteralFeeding", ENTERAL_FEEDING_MAP)

        # IV Antibiotic — resolve string names to Raster drug IDs
        _resolve_iv_antibiotics(procedures)

    # 6. Diagnosis — parentsSpokenTo + timeOfDiscussion (12-hour format)
    diagnosis = payload.get("diagnosis")
    if isinstance(diagnosis, dict):
        if "parentsSpokenTo" in diagnosis:
            diagnosis["parentsSpokenTo"] = normalize_yes_no(diagnosis["parentsSpokenTo"])
        if "timeOfDiscussion" in diagnosis:
            diagnosis["timeOfDiscussion"] = _convert_to_12hr(diagnosis["timeOfDiscussion"])
        _capitalize_fields(diagnosis, [
            "plan", "mattersDiscussed", "indicationOfAdmissionOther",
        ])

        # Convert indicationOfAdmission from comma-separated string to array of integers
        _convert_indication_of_admission_to_array(diagnosis)

    # 7. Sentence capitalization — free-text narrative fields only
    # Pregnancy — complication treatments + scan findings
    if isinstance(pregnancy, dict):
        complications = pregnancy.get("complication")
        if isinstance(complications, list):
            for comp in complications:
                if isinstance(comp, dict):
                    _capitalize_fields(comp, ["treatment"])
        for scan_key in ["datingScanDetails", "anomalyScanDetails"]:
            scan = pregnancy.get(scan_key)
            if isinstance(scan, dict):
                _capitalize_fields(scan, ["findings"])
        for scan_key in ["otherScanDetails", "dopplerScanDetails"]:
            scans = pregnancy.get(scan_key)
            if isinstance(scans, list):
                for scan in scans:
                    if isinstance(scan, dict):
                        _capitalize_fields(scan, ["findings"])

    # Procedures — only true free-text fields (enum fields handled above)
    if isinstance(procedures, dict):
        _capitalize_fields(procedures, ["indications", "fluids"])

    return payload


def _resolve_iv_antibiotics(procedures: Dict[str, Any]) -> None:
    """Resolve string antibiotic names to Raster drug IDs using fuzzy lookup."""
    iv_antibiotics = procedures.get("ivAntibiotic")
    if not isinstance(iv_antibiotics, list):
        return

    from services.drug_lookups import lookup_drug_id_fuzzy

    for item in iv_antibiotics:
        if not isinstance(item, dict) or "antibiotic" not in item:
            continue
        ab = item["antibiotic"]
        if isinstance(ab, str) and ab.strip() and not ab.strip().isdigit():
            resolved = lookup_drug_id_fuzzy(ab.strip())
            if resolved is not None:
                logger.info(f"[EXTRACTION_LOOKUPS] ivAntibiotic resolved: '{ab}' -> {resolved}")
                item["antibiotic"] = resolved


def _convert_indication_of_admission_to_array(diagnosis: Dict[str, Any]) -> None:
    """
    Convert indicationOfAdmission from comma-separated string to array of integers.
    Uses the generic utility function.
    """
    diagnosis["indicationOfAdmission"] = convert_comma_separated_to_int_array(
        diagnosis.get("indicationOfAdmission")
    )


def _convert_to_12hr(value) -> str:
    """Convert 24-hour time (e.g. '17:00') to 12-hour format (e.g. '05:00 PM')."""
    if value is None:
        return ""
    val_str = str(value).strip()
    if not val_str:
        return val_str

    # Already in 12-hour format (contains AM/PM)
    if re.search(r'[AaPp][Mm]', val_str):
        # Normalize spacing/case: "5:00pm" → "05:00 PM"
        m = re.match(r'^(\d{1,2}):(\d{2})\s*([AaPp][Mm])$', val_str)
        if m:
            hour, minute, period = m.group(1), m.group(2), m.group(3).upper()
            return f"{int(hour):02d}:{minute} {period}"
        return val_str

    # 24-hour format: "17:00" or "09:30"
    m = re.match(r'^(\d{1,2}):(\d{2})$', val_str)
    if m:
        hour = int(m.group(1))
        minute = m.group(2)
        if hour == 0:
            return f"12:{minute} AM"
        elif hour < 12:
            return f"{hour:02d}:{minute} AM"
        elif hour == 12:
            return f"12:{minute} PM"
        else:
            return f"{(hour - 12):02d}:{minute} PM"

    return val_str

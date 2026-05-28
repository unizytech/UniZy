"""
KG Hospital EHR Integration Service

Transforms CARDIO_INITIAL and CARDIO_REASSESS extraction output into
KG Hospital Cardiology payload formats.

CARDIO_INITIAL segment mapping (15-section KG form):
- VITALS -> vitals (temp, pulse, rr, bp, spo2, date_time) + nutritional_screening
- GENERAL_HISTORY -> comorbidities (9 medical checkboxes) + past_medical_history
- HISTORY -> comorbidities (smoking, tobacco, alcohol) + family_history
- ALLERGY -> drug_allergy
- CHIEF_COMPLAINTS -> present_complaints
- HISTORY_OF_PRESENT_ILLNESS -> history_of_presenting_illness + drug_history
- GENERAL_EXAMINATION -> general_examination (face, eyes, neck, legs, others)
- SYSTEMIC_EXAMINATION -> systemic_examination (cvs, rs, abdomen_gi, cns, local)
- DIAGNOSIS -> diagnosis
- INVESTIGATIONS -> suggested_investigations (8 checkboxes) + investigations_list
- CLINICAL_NOTES + FOLLOW_UP -> consultants_referral, treatment_and_future_plan
- PRESCRIPTION -> prescription
- FOLLOW_UP -> review_on, other_instructions

CARDIO_REASSESS segment mapping (same as INITIAL minus ALLERGY, GENERAL_HISTORY):
- VITALS -> vitals (temp, pulse, rr, bp, spo2, date_time) + nutritional_screening
- CHIEF_COMPLAINTS -> present_complaints
- CLINICAL_NOTES.has_patient_improved -> has_patient_improved
- HISTORY_OF_PRESENT_ILLNESS -> history_of_presenting_illness + drug_history
- HISTORY -> family_history
- GENERAL_EXAMINATION -> general_examination (face, eyes, neck, legs, others)
- SYSTEMIC_EXAMINATION -> systemic_examination (cvs, rs, abdomen_gi, cns, local)
- DIAGNOSIS -> diagnosis
- INVESTIGATIONS -> suggested_investigations (8 checkboxes) + investigations_list
- CLINICAL_NOTES + FOLLOW_UP -> consultants_referral, treatment_and_future_plan
- PRESCRIPTION -> prescription
- FOLLOW_UP -> review_on, other_instructions
"""

import asyncio
import json
import logging
import re
import httpx
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# ── Medical History: 12 cardiology checkboxes ──────────────────────────
# Each key maps to keyword patterns matched against
# GENERAL_HISTORY.known_medical_problems[].condition
MEDICAL_HISTORY_KEYWORDS: Dict[str, List[str]] = {
    "dm": ["diabetes", "dm", "diabetic", "type 2 diabetes", "type 1 diabetes",
           "t2dm", "t1dm", "iddm", "niddm", "diabetes mellitus"],
    "ht": ["hypertension", "ht", "htn", "high blood pressure", "elevated bp",
           "essential hypertension", "systemic hypertension"],
    "dlp": ["dyslipidemia", "dlp", "hyperlipidemia", "hypercholesterolemia",
            "high cholesterol", "lipid disorder"],
    "previous_mi": ["myocardial infarction", "mi", "heart attack", "stemi",
                    "nstemi", "acute coronary syndrome", "acs", "previous mi"],
    "previous_stent": ["stent", "pci", "angioplasty", "ptca",
                       "coronary stenting", "previous stent"],
    "valvular_stent": ["valvular", "valve replacement", "valve repair",
                       "prosthetic valve", "valvular stent", "mvr", "avr"],
    "anticoagulant": ["anticoagulant", "warfarin", "acenocoumarol", "heparin",
                      "enoxaparin", "rivaroxaban", "apixaban", "dabigatran",
                      "on anticoagulation", "blood thinner"],
    "history_of_cva": ["cva", "stroke", "cerebrovascular accident", "tia",
                       "transient ischemic", "cerebral infarct", "hemiplegia",
                       "history of cva"],
    "history_of_copd": ["copd", "chronic obstructive", "emphysema",
                        "chronic bronchitis", "history of copd"],
    "previous_cabg": ["cabg", "coronary artery bypass", "bypass surgery",
                      "bypass graft", "previous cabg"],
    "crf": ["crf", "chronic renal failure", "ckd", "chronic kidney disease",
            "renal failure", "end stage renal", "esrd", "dialysis"],
    "pvod": ["pvod", "peripheral vascular", "pad", "peripheral arterial",
             "claudication", "pvd", "peripheral vascular occlusive"],
}

# ── Investigation checkboxes ───────────────────────────────────────────
# Matched against INVESTIGATIONS[].name
INVESTIGATION_KEYWORDS: Dict[str, List[str]] = {
    "ecg": ["ecg", "electrocardiogram", "ekg", "12 lead"],
    "ct": ["ct", "ct scan", "computed tomography", "ct angiography",
           "ct coronary", "ctpa", "hrct", "cect"],
    "echo": ["echo", "echocardiogram", "2d echo", "echocardiography",
             "doppler echo", "transthoracic", "tte", "tee"],
    "mri": ["mri", "magnetic resonance", "cardiac mri", "cmr"],
    "usg": ["usg", "ultrasound", "ultrasonography", "sonography"],
    "bmd": ["bmd", "bone mineral density", "dexa", "dxa"],
    "xray": ["xray", "x-ray", "x ray", "chest x-ray", "cxr",
             "radiograph", "chest radiograph"],
    "mammogram": ["mammogram", "mammography"],
}


# ── Comorbidity checkboxes (KG form Section 3) ───────────────────────
# 9 medical conditions matched from GENERAL_HISTORY.known_medical_problems
COMORBIDITY_KEYWORDS: Dict[str, List[str]] = {
    "dm": ["diabetes", "dm", "diabetic", "type 2 diabetes", "type 1 diabetes",
           "t2dm", "t1dm", "iddm", "niddm", "diabetes mellitus"],
    "ht": ["hypertension", "ht", "htn", "high blood pressure", "elevated bp",
           "essential hypertension", "systemic hypertension"],
    "dlp": ["dyslipidemia", "dlp", "hyperlipidemia", "hypercholesterolemia",
            "high cholesterol", "lipid disorder"],
    "history_of_copd": ["copd", "chronic obstructive", "emphysema",
                        "chronic bronchitis", "history of copd"],
    "previous_mi": ["myocardial infarction", "mi", "heart attack", "stemi",
                    "nstemi", "acute coronary syndrome", "acs", "previous mi"],
    "previous_stent": ["stent", "pci", "angioplasty", "ptca",
                       "coronary stenting", "previous stent"],
    "renal_failure": ["crf", "chronic renal failure", "ckd", "chronic kidney disease",
                      "renal failure", "end stage renal", "esrd", "dialysis",
                      "acute kidney", "kidney failure"],
    "history_of_cva": ["cva", "stroke", "cerebrovascular accident", "tia",
                       "transient ischemic", "cerebral infarct", "hemiplegia",
                       "history of cva"],
    "peripheral_vascular_disease": ["pvod", "peripheral vascular", "pad",
                                    "peripheral arterial", "claudication", "pvd",
                                    "peripheral vascular occlusive",
                                    "peripheral vascular disease"],
}

# Only these 4 comorbidities get a "since" field on the KG form
COMORBIDITIES_WITH_SINCE = {"dm", "ht", "dlp", "history_of_copd"}

# 3 habit-based checkboxes matched from HISTORY.habits[].habitName
HABIT_CHECKBOX_MAP: Dict[str, List[str]] = {
    "smoking": ["smoking", "cigarette", "bidi", "beedi", "smoke"],
    "tobacco_chewing": ["tobacco chewing", "tobacco", "gutka", "pan masala",
                        "chewing tobacco"],
    "alcohol_intake": ["alcohol", "drinking", "liquor", "beer", "wine",
                       "spirits", "alcohol intake"],
}


# ── Helper functions ───────────────────────────────────────────────────

def _to_str(value: Any) -> str:
    """
    Convert a numeric or string value to string, stripping units.

    Schema-drift guard: if a leaf slot receives an unexpected complex
    type (dict or list — possible from doctor-edit iframes), return ""
    rather than the Python repr. Keeps EHR payloads clean of junk like
    "{'value': '70', 'unit': 'kg'}".
    """
    if value is None or isinstance(value, (dict, list)):
        return ""
    s = str(value).strip()
    # Remove common unit suffixes
    s = re.sub(r'\s*(bpm|mmhg|cm|kg|kg/m2|%|f|°f|°c)\s*$', '', s, flags=re.IGNORECASE)
    return s


def _compute_bmi_flag(bmi_val: Any) -> str:
    """Compute BMI classification flag."""
    if bmi_val is None:
        return ""
    try:
        bmi = float(bmi_val)
    except (ValueError, TypeError):
        return ""

    if bmi < 18.5:
        return "below_18_5"
    elif bmi <= 24.5:
        return "normal"
    else:
        return "above_24_5"


def _match_keywords(text: str, keyword_list: List[str]) -> bool:
    """Check if any keyword appears in the text (case-insensitive)."""
    text_lower = text.lower().strip()
    for kw in keyword_list:
        if kw in text_lower:
            return True
    return False


def _format_since(since_value: Any, since_unit: Any) -> str:
    """Format since_value + since_unit into readable string."""
    val = since_value
    unit = since_unit or ""

    if val is None or val == "" or val == 0:
        return ""

    return f"{val} {unit}".strip()


def _parse_medical_history(general_history: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """
    Parse GENERAL_HISTORY into 12 cardiology checkbox statuses.

    Matches known_medical_problems[].condition against keyword dictionaries.
    Also checks detailed_medical_history free text as fallback.
    """
    result = {}
    for key in MEDICAL_HISTORY_KEYWORDS:
        result[key] = {"status": "No", "since": ""}

    known_problems = general_history.get("known_medical_problems", [])
    if not isinstance(known_problems, list):
        known_problems = []

    # Match structured problems
    for problem in known_problems:
        if not isinstance(problem, dict):
            continue
        condition = problem.get("condition", "")
        if not condition:
            continue

        for checkbox_key, keywords in MEDICAL_HISTORY_KEYWORDS.items():
            if result[checkbox_key]["status"] == "Yes":
                continue  # Already matched
            if _match_keywords(condition, keywords):
                result[checkbox_key]["status"] = "Yes"
                result[checkbox_key]["since"] = _format_since(
                    problem.get("since_value"),
                    problem.get("since_unit")
                )

    # Fallback: check detailed_medical_history free text
    detailed = general_history.get("detailed_medical_history", "")
    if detailed and isinstance(detailed, str):
        for checkbox_key, keywords in MEDICAL_HISTORY_KEYWORDS.items():
            if result[checkbox_key]["status"] == "Yes":
                continue
            if _match_keywords(detailed, keywords):
                result[checkbox_key]["status"] = "Yes"

    return result


def _parse_investigation_checkboxes(
    investigations: Any,
) -> Dict[str, Any]:
    """
    Parse investigations into investigation checkboxes.

    Accepts top-level investigations list (flat array of {name, type, date}).

    Returns dict with:
    - blood_investigations: comma-separated lab test names
    - ecg, ct, echo, mri, usg, bmd, xray, mammogram: booleans
    """
    result: Dict[str, Any] = {
        "blood_investigations": "",
        "ecg": False,
        "ct": False,
        "echo": False,
        "mri": False,
        "usg": False,
        "bmd": False,
        "xray": False,
        "mammogram": False,
    }

    if not isinstance(investigations, list):
        return result

    lab_names = []

    for inv in investigations:
        if not isinstance(inv, dict):
            continue
        inv_name = inv.get("name", "")
        inv_type = (inv.get("type", "") or "").lower()
        if not inv_name:
            continue

        # Check against checkbox keywords
        matched_checkbox = False
        for checkbox_key, keywords in INVESTIGATION_KEYWORDS.items():
            if _match_keywords(inv_name, keywords):
                result[checkbox_key] = True
                matched_checkbox = True
                break

        # Lab investigations go into blood_investigations text
        if inv_type in ("lab", "laboratory") or (not matched_checkbox and inv_type not in ("imaging",)):
            if inv_type in ("lab", "laboratory"):
                lab_names.append(inv_name)

    result["blood_investigations"] = ", ".join(lab_names)
    return result


def _build_investigations_list(investigations: Any) -> List[Dict[str, str]]:
    """
    Build investigations_list with service_id and service_name from investigations.

    Tolerates schema drift introduced by doctor edits:
      - List form (canonical): [{name, _external_id}, ...]
      - Dict form sometimes sent by iframe edits:
        {done: [...], next_visit: [...], pending: [...], investigations: [...]}
        — values that are lists are concatenated.
      - String form: treated as a single-name investigation.
      - Anything else: empty list.
    """
    if isinstance(investigations, dict):
        flat = []
        for v in investigations.values():
            if isinstance(v, list):
                flat.extend(v)
        investigations = flat
    elif isinstance(investigations, str) and investigations.strip():
        investigations = [{"name": investigations.strip()}]
    elif not isinstance(investigations, list):
        return []

    result = []
    for inv in investigations:
        if isinstance(inv, str) and inv.strip():
            result.append({"service_id": "", "service_name": inv.strip()})
            continue
        if not isinstance(inv, dict):
            continue
        name = inv.get("name", "")
        if not name:
            continue
        result.append({
            "service_id": inv.get("_external_id", ""),
            "service_name": name,
        })
    return result


def _format_complaints(chief_complaints: Any) -> str:
    """
    Format CHIEF_COMPLAINTS into readable text.

    Handles both:
    - Array of strings: ["Chest pain for 3 days", "Breathlessness"]
    - Array of objects: [{complaint_name, since_value, since_unit, severity, notes}]
    """
    if not chief_complaints or not isinstance(chief_complaints, list):
        return ""

    parts = []
    for item in chief_complaints:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            name = item.get("complaint_name", "")
            if not name:
                continue
            since = _format_since(item.get("since_value"), item.get("since_unit"))
            severity = item.get("severity", "")
            text = name
            if since:
                text += f" for {since}"
            if severity and severity.lower() not in ("none", "n/a", ""):
                text += f" ({severity})"
            parts.append(text)

    return ", ".join(parts)


def _format_diagnosis(diagnosis: Any) -> str:
    """
    Format DIAGNOSIS into a readable string for EHR payloads.

    Supports two schemas:
      - List form (legacy AI output): [{name, code, type}, ...]
        → "Name (Code), Name2 (Code2)"
      - Object form (doctor edit / new schema):
        {primary_diagnosis: "...", interim_diagnosis: [...],
         secondary_diagnoses: [...], differential_diagnoses: [...]}
        → primary text first, then any named diagnoses, joined by newlines.
    """
    if not diagnosis:
        return ""

    # List form (legacy)
    if isinstance(diagnosis, list):
        parts = []
        for d in diagnosis:
            if isinstance(d, dict):
                name = d.get("name", "")
                code = d.get("code", "")
                if name:
                    parts.append(f"{name} ({code})" if code else name)
            elif isinstance(d, str) and d:
                parts.append(d)
        return ", ".join(parts)

    # Object form (new)
    if isinstance(diagnosis, dict):
        parts = []
        primary = diagnosis.get("primary_diagnosis", "")
        if isinstance(primary, str) and primary.strip():
            parts.append(primary.strip())
        for arr_key in ("interim_diagnosis", "secondary_diagnoses", "differential_diagnoses"):
            arr = diagnosis.get(arr_key)
            if isinstance(arr, list):
                for d in arr:
                    if isinstance(d, dict):
                        name = d.get("name", "")
                        code = d.get("code", "")
                        if name:
                            parts.append(f"{name} ({code})" if code else name)
                    elif isinstance(d, str) and d.strip():
                        parts.append(d.strip())
        return "\n".join(p for p in parts if p)

    return ""


def _combine_findings(
    general_exam: Dict[str, Any],
    systemic_exam: Any,
) -> Dict[str, str]:
    """
    Combine GENERAL_EXAMINATION + SYSTEMIC_EXAMINATION into findings.

    Returns dict with positive and negative finding strings.
    """
    positive_parts = []
    negative_parts = []

    # General examination findings
    general_findings = general_exam.get("general_findings", "")
    if general_findings:
        # Try to split positive/negative
        _split_findings(general_findings, positive_parts, negative_parts)

    # Other general exam fields
    for field in ("general_appearance", "general_systemic_examination",
                  "other_relevant_finding"):
        val = general_exam.get(field, "")
        if val and isinstance(val, str) and val.lower() not in ("normal", "n/a", ""):
            positive_parts.append(val)

    jvp = general_exam.get("jugular_vein_pressure", "")
    if jvp and isinstance(jvp, str) and jvp.lower() not in ("normal", "n/a", ""):
        positive_parts.append(f"JVP: {jvp}")

    # Systemic examination
    if isinstance(systemic_exam, list):
        for exam in systemic_exam:
            if isinstance(exam, dict):
                system = exam.get("system_type", "")
                finding = exam.get("examination", "")
                if finding:
                    label = f"{system}: {finding}" if system else finding
                    positive_parts.append(label)

    return {
        "positive": ", ".join(positive_parts) if positive_parts else "",
        "negative": ", ".join(negative_parts) if negative_parts else "",
    }


def _split_findings(text: str, positive: list, negative: list):
    """Split findings text into positive and negative lists."""
    # Common negative prefixes
    neg_patterns = [
        r"no\s+\w+",
        r"not\s+\w+",
        r"nil\s+\w+",
        r"absent\s+\w+",
    ]
    neg_keywords = ["no pallor", "no icterus", "no cyanosis", "no clubbing",
                    "no lymphadenopathy", "no pedal edema", "no edema",
                    "no jaundice", "no rash"]

    # Split on commas or semicolons
    items = re.split(r'[,;]+', text)
    for item in items:
        item = item.strip()
        if not item:
            continue
        item_lower = item.lower()
        is_negative = any(nk in item_lower for nk in neg_keywords)
        if not is_negative:
            is_negative = any(re.match(p, item_lower) for p in neg_patterns)

        if is_negative:
            negative.append(item)
        else:
            positive.append(item)


def _extract_referral_text(text: str) -> Optional[str]:
    """Extract referral text from a string, handling 'Dr.' honorific."""
    if not text or not isinstance(text, str):
        return None
    # Match "refer/referral/referred to ..." up to sentence end
    # Use a pattern that doesn't stop at "Dr." or "Mr." etc.
    match = re.search(
        r'refer(?:ral|red)?\s+(?:to\s+)?(.+?)(?:(?<!\b[A-Z]r)\.(?:\s|$)|$)',
        text, re.IGNORECASE
    )
    if not match:
        return None
    # Get the full match and clean up trailing punctuation
    result = match.group(0).strip().rstrip(".")
    return result if result else None


def _parse_referral(
    clinical_notes: Dict[str, Any],
    follow_up: Dict[str, Any],
) -> str:
    """Extract referral information from CLINICAL_NOTES and FOLLOW_UP."""
    referral_parts = []

    # Check CLINICAL_NOTES fields (flat structure)
    for field in ("instructions", "follow_up"):
        ref = _extract_referral_text(clinical_notes.get(field, ""))
        if ref and ref not in referral_parts:
            referral_parts.append(ref)

    # Check FOLLOW_UP fields
    for field in ("other_instructions", "special_instructions"):
        ref = _extract_referral_text(follow_up.get(field, ""))
        if ref and ref not in referral_parts:
            referral_parts.append(ref)

    return ". ".join(referral_parts) if referral_parts else ""


def _parse_treatment_plan(
    prescription: Any,
    follow_up: Dict[str, Any],
    clinical_notes: Dict[str, Any],
) -> Dict[str, str]:
    """Build treatment_and_future_plan from PRESCRIPTION, FOLLOW_UP, CLINICAL_NOTES."""
    has_prescription = isinstance(prescription, list) and len(prescription) > 0

    # Check for admission mentions
    admission = "No"
    reason = ""
    admission_type = ""

    instructions = clinical_notes.get("instructions", "") or ""
    treatment = clinical_notes.get("treatment", "") or ""
    combined = f"{instructions} {treatment}".lower()

    if "admit" in combined or "admission" in combined:
        admission = "Yes"
        # Try to extract reason
        match = re.search(
            r'admit(?:ted)?\s+(?:for|due to|in view of)\s+(.+?)(?:\.|$)',
            combined, re.IGNORECASE
        )
        if match:
            reason = match.group(1).strip()

        # Check admission type
        if "icu" in combined or "intensive care" in combined:
            admission_type = "ICU"
        elif "observation" in combined:
            admission_type = "Observation"
        elif "ward" in combined:
            admission_type = "Ward"

    # Also check follow_up for admission mentions
    for field in ("other_instructions", "special_instructions"):
        val = (follow_up.get(field, "") or "").lower()
        if "admit" in val or "admission" in val:
            admission = "Yes"
            if "icu" in val:
                admission_type = "ICU"
            elif "observation" in val:
                admission_type = "Observation"

    return {
        "drugs_as_per_prescription": "Yes" if has_prescription else "No",
        "admission": admission,
        "reason_for_admission": reason,
        "type_of_admission": admission_type,
    }


def _parse_frequency(dose: str) -> Dict[str, bool]:
    """Parse M-A-E-N dose string into frequency dict.

    "1-0-0-1" → {"M": True, "A": False, "E": False, "N": True}
    "SOS"     → {"M": False, "A": False, "E": False, "N": False}
    """
    freq = {"M": False, "A": False, "E": False, "N": False}
    if not dose or not isinstance(dose, str):
        return freq
    dose = dose.strip()
    if dose.upper() in ("SOS", "STAT", "PRN"):
        return freq
    parts = dose.split("-")
    if len(parts) == 4:
        keys = ["M", "A", "E", "N"]
        for i, part in enumerate(parts):
            try:
                freq[keys[i]] = int(part) > 0
            except (ValueError, TypeError):
                freq[keys[i]] = False
    return freq


def _parse_duration(duration_days: str):
    """Parse duration string into (number, unit).

    "5 days"   → (5, "Day")
    "2 weeks"  → (2, "Week")
    "1 month"  → (1, "Month")
    Returns ("", "") if unparseable.
    """
    if not duration_days or not isinstance(duration_days, str):
        return ("", "")
    d = duration_days.strip().lower()
    if d in ("n/a", "na", "null", "none", "sos", ""):
        return ("", "")
    # Try to extract number and unit
    match = re.match(r'(\d+)\s*(day|days|week|weeks|month|months|year|years)?', d)
    if not match:
        # Try just a number (assume days)
        try:
            return (int(d), "Day")
        except ValueError:
            return ("", "")
    num = int(match.group(1))
    unit_raw = (match.group(2) or "day").lower()
    unit_map = {
        "day": "Day", "days": "Day",
        "week": "Week", "weeks": "Week",
        "month": "Month", "months": "Month",
        "year": "Year", "years": "Year",
    }
    return (num, unit_map.get(unit_raw, "Day"))


def _map_intake(time_to_take: str) -> str:
    """Map timeToTake to KG intake dropdown value."""
    if not time_to_take or not isinstance(time_to_take, str):
        return ""
    t = time_to_take.strip().lower()
    if t in ("n/a", "na", "null", "none", ""):
        return ""
    after = ["after meals", "after food", "after eating", "post meal", "post food"]
    before = ["before meals", "before food", "before eating", "empty stomach",
              "on empty stomach", "pre meal", "pre food"]
    with_food = ["with food", "with meals", "during meals", "during food"]
    if_needed = ["sos", "if needed", "as needed", "when needed", "prn", "as required"]

    if any(k in t for k in after):
        return "After Food"
    if any(k in t for k in before):
        return "Before Food"
    if any(k in t for k in with_food):
        return "With Food"
    if any(k in t for k in if_needed):
        return "If Needed"
    # Return cleaned-up original if no match
    return time_to_take.strip()


def _map_route(route: str) -> str:
    """Map route to KG dropdown value. Default 'Oral'."""
    if not route or not isinstance(route, str):
        return "Oral"
    r = route.strip().lower()
    if r in ("n/a", "na", "null", "none", ""):
        return "Oral"
    route_map = {
        "oral": "Oral",
        "intravenous": "Intravenous", "iv": "Intravenous",
        "intramuscular": "Intramuscular", "im": "Intramuscular",
        "subcutaneous": "Subcutaneous", "sc": "Subcutaneous", "s/c": "Subcutaneous",
        "inhaled": "Inhaled", "inhalation": "Inhaled",
        "sublingual": "Sublingual", "sl": "Sublingual",
        "topical": "Topical",
        "rectal": "Rectal",
        "nasal": "Nasal",
        "eye drops": "Eye Drops", "ophthalmic": "Eye Drops",
        "ear drops": "Ear Drops", "otic": "Ear Drops",
        "transdermal": "Transdermal",
    }
    for key, val in route_map.items():
        if key in r:
            return val
    return route.strip()


def _map_intake_period(intake_period: str) -> str:
    """Map intakePeriod to KG dropdown value. Default empty."""
    if not intake_period or not isinstance(intake_period, str):
        return ""
    p = intake_period.strip().lower()
    if p in ("n/a", "na", "null", "none", ""):
        return ""
    period_map = {
        "sos": "SOS", "stat": "STAT", "prn": "PRN",
        "alternate days": "Alternate days", "alternate day": "Alternate days",
        "weekly once": "Weekly once", "once a week": "Weekly once",
        "weekly twice": "Weekly twice", "twice a week": "Weekly twice",
        "monthly once": "Monthly once", "once a month": "Monthly once",
        "fortnightly": "Fortnightly", "every 2 weeks": "Fortnightly",
    }
    for key, val in period_map.items():
        if key in p:
            return val
    return intake_period.strip()


def _compute_quantity(dose: str, duration, duration_unit: str) -> str:
    """Compute total quantity: sum of dose digits × duration in days.

    "1-0-0-1" with 5 days → "10"
    SOS → ""
    """
    if not dose or not isinstance(dose, str):
        return ""
    dose = dose.strip()
    if dose.upper() in ("SOS", "STAT", "PRN"):
        return ""
    if not duration or duration == "":
        return ""
    # Sum dose digits
    parts = dose.split("-")
    if len(parts) != 4:
        return ""
    try:
        per_day = sum(int(p) for p in parts)
    except (ValueError, TypeError):
        return ""
    if per_day <= 0:
        return ""
    # Convert duration to days
    try:
        dur_num = int(duration)
    except (ValueError, TypeError):
        return ""
    unit = (duration_unit or "").lower()
    if "week" in unit:
        dur_days = dur_num * 7
    elif "month" in unit:
        dur_days = dur_num * 30
    elif "year" in unit:
        dur_days = dur_num * 365
    else:
        dur_days = dur_num
    return str(per_day * dur_days)


def _format_prescription(prescription_array: Any, follow_up_date: str = "") -> List[Dict]:
    """
    Format PRESCRIPTION array into KG 13-field prescription format.

    Tolerates dict-form payloads from doctor-edit iframes by flattening
    list-typed values (e.g. {medications: [...], otc: [...]} → combined list).
    """
    if isinstance(prescription_array, dict):
        flat = []
        for v in prescription_array.values():
            if isinstance(v, list):
                flat.extend(v)
        prescription_array = flat
    if not prescription_array or not isinstance(prescription_array, list):
        return []

    result = []
    for med in prescription_array:
        if not isinstance(med, dict):
            continue
        name = med.get("name", "")
        if not name:
            continue

        dose = med.get("dose", "") or ""
        duration_raw = med.get("durationDays", "") or ""
        time_to_take = med.get("timeToTake", "") or ""
        route = med.get("route", "") or ""
        intake_period = med.get("intakePeriod", "") or ""
        remarks = med.get("remarks", "") or ""

        # Clean n/a values
        na_values = ("n/a", "na", "null", "none")
        if isinstance(dose, str) and dose.strip().lower() in na_values:
            dose = ""
        if isinstance(duration_raw, str) and duration_raw.strip().lower() in na_values:
            duration_raw = ""
        if isinstance(remarks, str) and remarks.strip().lower() in na_values:
            remarks = ""

        frequency = _parse_frequency(dose)
        duration_num, duration_unit = _parse_duration(duration_raw)
        quantity = _compute_quantity(dose, duration_num, duration_unit)

        result.append({
            "drug_id": med.get("_external_id", ""),
            "drug_name": name,
            "frequency": frequency,
            "duration": duration_num,
            "duration_unit": duration_unit,
            "quantity": quantity,
            "intake": _map_intake(time_to_take),
            "route": _map_route(route),
            "intake_period": _map_intake_period(intake_period),
            "quantity_uom": "",
            "instructions": remarks,
            "investigation": "",
            "next_review_date": follow_up_date,
            "prescription_valid_upto": "",
        })

    return result


def _combine_instructions(
    follow_up: Dict[str, Any],
    clinical_notes: Dict[str, Any],
) -> str:
    """Combine other instructions from FOLLOW_UP and CLINICAL_NOTES."""
    parts = []

    # FOLLOW_UP.other_instructions
    other = follow_up.get("other_instructions", "")
    if other and isinstance(other, str) and other.lower() not in ("n/a", "na", "none", ""):
        parts.append(other)

    # FOLLOW_UP.special_instructions
    special = follow_up.get("special_instructions", "")
    if special and isinstance(special, str) and special.lower() not in ("n/a", "na", "none", ""):
        parts.append(special)

    # CLINICAL_NOTES.instructions (flat structure)
    instructions = clinical_notes.get("instructions", "")
    if instructions and isinstance(instructions, str) and instructions.lower() not in ("n/a", "na", "none", ""):
        parts.append(instructions)

    return ". ".join(parts) if parts else ""


# ── Comorbidity parser (replaces _parse_medical_history for INITIAL) ──

def _parse_comorbidities(
    general_history: Dict[str, Any],
    history: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Parse comorbidities from GENERAL_HISTORY (medical conditions) and HISTORY (habits).

    Returns 12 checkbox entries matching the KG form:
    - DM, HT, DLP, COPD: {status, since}
    - Previous MI, Previous Stent, Renal Failure, History of CVA,
      Peripheral Vascular Disease, Smoking, Tobacco Chewing, Alcohol Intake: {status}
    """
    result: Dict[str, Any] = {}

    # Initialize medical condition checkboxes
    for key in COMORBIDITY_KEYWORDS:
        if key in COMORBIDITIES_WITH_SINCE:
            result[key] = {"status": "No", "since": ""}
        else:
            result[key] = {"status": "No"}

    # Initialize habit checkboxes
    for key in HABIT_CHECKBOX_MAP:
        result[key] = {"status": "No"}

    # Match medical conditions from GENERAL_HISTORY.known_medical_problems
    known_problems = general_history.get("known_medical_problems", [])
    if not isinstance(known_problems, list):
        known_problems = []

    for problem in known_problems:
        if not isinstance(problem, dict):
            continue
        condition = problem.get("condition", "")
        if not condition:
            continue

        for checkbox_key, keywords in COMORBIDITY_KEYWORDS.items():
            if result[checkbox_key]["status"] == "Yes":
                continue
            if _match_keywords(condition, keywords):
                result[checkbox_key]["status"] = "Yes"
                if checkbox_key in COMORBIDITIES_WITH_SINCE:
                    result[checkbox_key]["since"] = _format_since(
                        problem.get("since_value"),
                        problem.get("since_unit")
                    )

    # Fallback: check detailed_medical_history free text
    detailed = general_history.get("detailed_medical_history", "")
    if detailed and isinstance(detailed, str):
        for checkbox_key, keywords in COMORBIDITY_KEYWORDS.items():
            if result[checkbox_key]["status"] == "Yes":
                continue
            if _match_keywords(detailed, keywords):
                result[checkbox_key]["status"] = "Yes"

    # Match habits from HISTORY.habits[]
    habits = history.get("habits", [])
    if not isinstance(habits, list):
        habits = []

    for habit in habits:
        if not isinstance(habit, dict):
            continue
        habit_name = habit.get("habitName", "")
        if not habit_name:
            continue

        for checkbox_key, keywords in HABIT_CHECKBOX_MAP.items():
            if result[checkbox_key]["status"] == "Yes":
                continue
            if _match_keywords(habit_name, keywords):
                pattern = (habit.get("habitPattern", "") or "").lower()
                habit_hist = (habit.get("habitHistory", "") or "").lower()
                if "never" in pattern or "never" in habit_hist:
                    continue
                result[checkbox_key]["status"] = "Yes"

    return result


# ── New section formatters (KG form sections 6-11) ───────────────────

def _format_hpi(hpi: Dict[str, Any]) -> str:
    """Format HISTORY_OF_PRESENT_ILLNESS into narrative text."""
    if not hpi or not isinstance(hpi, dict):
        return ""

    parts = []
    for field, label in [
        ("current_complaints", ""),
        ("last_visit", "Last visit"),
        ("recent_labs", "Recent labs"),
        ("activity_status", "Activity"),
        ("adl_status", "ADL"),
        ("negative_symptoms", "Denies"),
    ]:
        val = hpi.get(field, "")
        if val and isinstance(val, str) and val.lower() not in ("n/a", "na", "none", ""):
            parts.append(f"{label}: {val}" if label else val)

    return ". ".join(parts)


def _format_family_history(history: Dict[str, Any]) -> str:
    """Format HISTORY.familyHistory[] into readable text."""
    if not history or not isinstance(history, dict):
        return ""

    family = history.get("familyHistory", [])
    if not isinstance(family, list) or not family:
        return ""

    parts = []
    for entry in family:
        if not isinstance(entry, dict):
            continue
        disease = entry.get("diseaseName", "")
        if not disease:
            continue
        relationship = entry.get("relationship", "")
        remarks = entry.get("remarks", "")

        text = f"{relationship}: {disease}" if relationship else disease
        duration_parts = []
        years = entry.get("years", "")
        months = entry.get("months", "")
        if years:
            duration_parts.append(f"{years} years")
        if months:
            duration_parts.append(f"{months} months")
        if duration_parts:
            text += f" ({', '.join(duration_parts)})"
        if remarks:
            text += f" - {remarks}"
        parts.append(text)

    return ", ".join(parts)


def _format_drug_history(hpi: Dict[str, Any]) -> str:
    """Format current medications from HISTORY_OF_PRESENT_ILLNESS into text."""
    if not hpi or not isinstance(hpi, dict):
        return ""

    parts = []
    medications = hpi.get("current_medications", [])
    if isinstance(medications, list):
        for med in medications:
            if not isinstance(med, dict):
                continue
            name = med.get("name", "")
            schedule = med.get("schedule", "")
            if name:
                parts.append(f"{name} {schedule}".strip() if schedule else name)

    other_meds = hpi.get("other_specialty_medications", "")
    if other_meds and isinstance(other_meds, str) and other_meds.lower() not in ("n/a", "na", "none", ""):
        parts.append(other_meds)

    return ", ".join(parts)


def _format_general_exam_structured(general_exam: Dict[str, Any]) -> Dict[str, str]:
    """
    Map GENERAL_EXAMINATION fields to KG form's 5 body-area fields.

    Classification:
    - face: pallor, icterus, cyanosis mentions
    - eyes: scleral, conjunctival mentions
    - neck: JVP, lymphadenopathy, thyroid mentions
    - legs: pedal edema, clubbing mentions
    - others: general_appearance + remaining findings
    """
    face_kw = ["pallor", "cyanosis", "facial", "face"]
    eye_kw = ["icterus", "scleral", "conjunctival", "jaundice", "eye", "pupil"]
    neck_kw = ["jvp", "jugular", "lymphadenopathy", "thyroid", "neck", "cervical"]
    leg_kw = ["pedal edema", "edema", "clubbing", "leg", "lower limb", "ankle",
              "peripheral edema"]

    face_parts: list = []
    eye_parts: list = []
    neck_parts: list = []
    leg_parts: list = []
    other_parts: list = []

    # Classify general_findings items by body area
    general_findings = general_exam.get("general_findings", "")
    if general_findings and isinstance(general_findings, str):
        items = re.split(r'[,;]+', general_findings)
        for item in items:
            item = item.strip()
            if not item:
                continue
            item_lower = item.lower()

            classified = False
            if any(k in item_lower for k in eye_kw):
                eye_parts.append(item)
                classified = True
            elif any(k in item_lower for k in face_kw):
                face_parts.append(item)
                classified = True
            if any(k in item_lower for k in neck_kw):
                neck_parts.append(item)
                classified = True
            if any(k in item_lower for k in leg_kw):
                leg_parts.append(item)
                classified = True
            if not classified:
                other_parts.append(item)

    # JVP → neck
    jvp = general_exam.get("jugular_vein_pressure", "")
    if jvp and isinstance(jvp, str) and jvp.lower() not in ("n/a", "na", "none", ""):
        neck_parts.append(f"JVP: {jvp}")

    # general_appearance → others
    appearance = general_exam.get("general_appearance", "")
    if appearance and isinstance(appearance, str):
        other_parts.insert(0, appearance)

    # other_relevant_finding → others
    other_finding = general_exam.get("other_relevant_finding", "")
    if other_finding and isinstance(other_finding, str) and other_finding.lower() not in ("n/a", "na", "none", ""):
        other_parts.append(other_finding)

    # general_systemic_examination → others
    systemic = general_exam.get("general_systemic_examination", "")
    if systemic and isinstance(systemic, str) and systemic.lower() not in ("n/a", "na", "none", ""):
        other_parts.append(systemic)

    return {
        "face": ", ".join(face_parts),
        "eyes": ", ".join(eye_parts),
        "neck": ", ".join(neck_parts),
        "legs": ", ".join(leg_parts),
        "others": ", ".join(other_parts),
    }


def _format_systemic_exam_structured(systemic_exam: Any) -> Dict[str, str]:
    """
    Map SYSTEMIC_EXAMINATION array to KG form's 5 system-specific fields.

    system_type mapping:
    - Cardio Vascular / CVS → cvs
    - Respiratory / RS → rs
    - Abdomen / GI → abdomen_gi
    - Central Nervous / CNS → cns
    - everything else → local_examination
    """
    result = {
        "cvs": "",
        "rs": "",
        "abdomen_gi": "",
        "cns": "",
        "local_examination": "",
    }

    if not isinstance(systemic_exam, list):
        return result

    local_parts = []

    for exam in systemic_exam:
        if not isinstance(exam, dict):
            continue
        system = (exam.get("system_type", "") or "").lower()
        finding = exam.get("examination", "") or ""
        if not finding:
            continue

        if "cardio" in system or "cvs" in system or "cardiovascular" in system:
            result["cvs"] = (result["cvs"] + ", " + finding) if result["cvs"] else finding
        elif "respiratory" in system or " rs" in system or system == "rs":
            result["rs"] = (result["rs"] + ", " + finding) if result["rs"] else finding
        elif "abdomen" in system or "gi" in system or "gastro" in system:
            result["abdomen_gi"] = (result["abdomen_gi"] + ", " + finding) if result["abdomen_gi"] else finding
        elif "central nervous" in system or "cns" in system or "neuro" in system:
            result["cns"] = (result["cns"] + ", " + finding) if result["cns"] else finding
        else:
            local_parts.append(finding)

    result["local_examination"] = ", ".join(local_parts)
    return result


def _format_treatment_plan_text(
    prescription: Any,
    clinical_notes: Dict[str, Any],
    follow_up: Dict[str, Any],
) -> str:
    """
    Build treatment_and_future_plan as a simple text string.

    Combines: CLINICAL_NOTES.treatment, CLINICAL_NOTES.instructions,
    FOLLOW_UP.other_instructions, FOLLOW_UP.special_instructions,
    and a brief prescription mention if present.
    """
    na_values = ("n/a", "na", "null", "none", "")
    parts = []

    # Treatment from clinical notes
    treatment = clinical_notes.get("treatment", "")
    if treatment and isinstance(treatment, str) and treatment.strip().lower() not in na_values:
        parts.append(treatment.strip())

    # Instructions from clinical notes
    instructions = clinical_notes.get("instructions", "")
    if instructions and isinstance(instructions, str) and instructions.strip().lower() not in na_values:
        parts.append(instructions.strip())

    # Follow-up other instructions
    other = follow_up.get("other_instructions", "")
    if other and isinstance(other, str) and other.strip().lower() not in na_values:
        parts.append(other.strip())

    # Follow-up special instructions
    special = follow_up.get("special_instructions", "")
    if special and isinstance(special, str) and special.strip().lower() not in na_values:
        parts.append(special.strip())

    # Mention prescription if present
    if isinstance(prescription, list) and len(prescription) > 0:
        parts.append("Drugs as per prescription")

    return ". ".join(parts) if parts else ""


# ── Main formatter ─────────────────────────────────────────────────────

def _format_prescription_kg(prescription_arr: Any, review_date: str = "") -> List[Dict]:
    """
    Map new CARDIO_INITIAL prescription schema to KG format.

    New extraction provides: name, dose (M-A-E-N string), duration (numeric),
    duration_unit (Day/Week/Month), intake, route, intake_period, instructions.
    Formatter adds: frequency booleans, quantity, drug_id, next_review_date.

    Tolerates schema drift: doctor-edit iframes occasionally send the field
    as a dict (e.g. {medications: [...]}), a string ("None"), or null.
    Anything that doesn't reduce to a list of drug-dicts → empty list.
    """
    if isinstance(prescription_arr, dict):
        flat = []
        for v in prescription_arr.values():
            if isinstance(v, list):
                flat.extend(v)
        prescription_arr = flat
    if not prescription_arr or not isinstance(prescription_arr, list):
        return []

    result = []
    for drug in prescription_arr:
        if not isinstance(drug, dict):
            continue
        name = drug.get("name", "")
        if not name:
            continue

        dose = drug.get("dose", "") or ""
        duration = drug.get("duration", "") or ""
        duration_unit = drug.get("duration_unit", "Day") or "Day"

        frequency = _parse_frequency(dose)
        quantity = _compute_quantity(dose, duration, duration_unit)

        result.append({
            "drug_id": drug.get("_external_id", ""),
            "drug_name": name,
            "frequency": frequency,
            "duration": duration,
            "duration_unit": duration_unit,
            "quantity": quantity,
            "intake": drug.get("intake", "") or "",
            "route": drug.get("route", "Oral") or "Oral",
            "intake_period": drug.get("intake_period", "") or "",
            "quantity_uom": "",
            "instructions": drug.get("instructions", "") or "",
            "investigation": "",
            "next_review_date": review_date,
            "prescription_valid_upto": "",
        })

    return result


def format_for_kg(
    extraction_data: Dict[str, Any],
    patient_id: str = "",
    doctor_id: str = "",
    extraction_id: str = "",
    doctor_name: str = "",
    uhid: str = "",
    visit_id: str = "",
    role: str = "",
) -> Dict[str, Any]:
    """
    Format CARDIO_INITIAL extraction data into KG Hospital Cardiology payload.

    Restructured segments now produce most KG fields directly. This formatter
    handles: metadata injection, key renames (camelCase → snake_case), flattening
    nested segments to top-level, and transforming retained segments (diagnosis
    array → string, investigations → service_id list, prescription → frequency
    booleans + quantity).

    Args:
        extraction_data: Dict with camelCase segment keys from assembled schema
        patient_id: Patient UUID
        doctor_id: Doctor UUID
        extraction_id: Extraction UUID
        doctor_name: Doctor display name
        uhid: Patient UHID (external ID)
        visit_id: Visit ID from recording metadata

    Returns:
        Dict formatted for KG Hospital Cardiology Initial Assessment API
    """
    # Extract segments (camelCase keys from assembled schema)
    vitals = extraction_data.get("vitals", {}) or {}
    nutritional = extraction_data.get("nutritionalScreening", {}) or {}
    comorbidities = extraction_data.get("comorbidities", {}) or {}
    allergy = extraction_data.get("allergy", {}) or {}
    chief_complaints = extraction_data.get("chiefComplaints", "")
    hpi = extraction_data.get("historyOfPresentIllness", {}) or {}
    general_history = extraction_data.get("generalHistory", {}) or {}
    family = extraction_data.get("history", {}) or {}
    gen_exam = extraction_data.get("generalExamination", {}) or {}
    sys_exam = extraction_data.get("systemicExamination", {}) or {}
    diagnosis_arr = extraction_data.get("diagnosis", []) or []
    investigations_arr = extraction_data.get("investigations", []) or []
    prescription_arr = extraction_data.get("prescription", []) or []
    treatment = extraction_data.get("treatmentPlan", {}) or {}

    if not isinstance(vitals, dict):
        vitals = {}
    if not isinstance(nutritional, dict):
        nutritional = {}
    if not isinstance(comorbidities, dict):
        comorbidities = {}
    if not isinstance(allergy, dict):
        allergy = {}
    if isinstance(chief_complaints, list):
        # Backward compat: old format was array, new is string
        chief_complaints = _format_complaints(chief_complaints)
    if not isinstance(hpi, dict):
        hpi = {}
    if not isinstance(general_history, dict):
        general_history = {}
    if not isinstance(family, dict):
        family = {}
    if not isinstance(gen_exam, dict):
        gen_exam = {}
    if not isinstance(sys_exam, dict):
        sys_exam = {}
    if not isinstance(treatment, dict):
        treatment = {}

    now = datetime.utcnow()
    review_date = treatment.get("review_on", "") or ""

    # ── Build payload ──────────────────────────────────────────────

    payload: Dict[str, Any] = {
        # Metadata
        "patient_id": patient_id,
        "uhid": uhid,
        "visit_id": visit_id,
        "doctor_id": doctor_id,
        "extraction_id": extraction_id,
        "role": role,
        "form_type": "CARDIOLOGY_INITIAL_ASSESSMENT",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),

        # 1. Vitals — pass through + inject date_time
        "vitals": {
            "temperature": _to_str(vitals.get("temperature")),
            "pulse": _to_str(vitals.get("pulse")),
            "respiratory_rate": _to_str(vitals.get("respiratory_rate")),
            "blood_pressure": _to_str(vitals.get("blood_pressure")),
            "spo2": _to_str(vitals.get("spo2")),
            "date_time": now.strftime("%Y-%m-%d %H:%M"),
        },

        # 2. Nutritional screening — pass through
        "nutritional_screening": {
            "height": _to_str(nutritional.get("height")),
            "weight": _to_str(nutritional.get("weight")),
            "bmi": _to_str(nutritional.get("bmi")),
            "bmi_flag": nutritional.get("bmi_flag", "") or "",
        },
        "nutritional_assessment_needed": "No",

        # 3. Comorbidities — pass through (Gemini produces 12 checkboxes directly)
        "comorbidities": comorbidities,

        # 4. Drug allergy — rename allergy → drug_allergy
        "drug_allergy": {
            "has_allergy": allergy.get("has_allergy", "No"),
            "details": allergy.get("details", ""),
        },

        # 5. Present complaints — pass through (Gemini produces string directly)
        "present_complaints": chief_complaints if isinstance(chief_complaints, str) else "",

        # 6. History of presenting illness — flatten from HPI segment
        "history_of_presenting_illness": hpi.get("history_of_presenting_illness", "") or "",

        # 7. Past medical history — flatten from GENERAL_HISTORY
        "past_medical_history": general_history.get("past_medical_history", "") or "",

        # 8. Family history — flatten from HISTORY
        "family_history": family.get("family_history", "") or "",

        # 9. Drug history — flatten from HPI segment
        "drug_history": hpi.get("drug_history", "") or "",

        # 10. General examination — pass through (Gemini produces 5 body-area fields)
        "general_examination": gen_exam,

        # 11. Systemic examination — pass through (Gemini produces 5 system fields)
        "systemic_examination": sys_exam,

        # 12. Diagnosis — retained as array, concatenate to string
        "diagnosis": _format_diagnosis(diagnosis_arr),

        # 13. Investigations — retained as array, map to service_id list
        "investigations_list": _build_investigations_list(investigations_arr),

        # 14. Treatment and future plan — flatten from TREATMENT_PLAN segment
        "treatment_and_future_plan": treatment.get("treatment_and_future_plan", "") or "",

        # 15. Prescription — parse dose → frequency booleans + compute quantity
        "prescription": _format_prescription_kg(prescription_arr, review_date),

        # 16. Consultants referral — flatten from TREATMENT_PLAN segment
        "consultants_referral": treatment.get("consultants_referral", "") or "",

        # Doctor name + time
        "doctor_name": doctor_name,
        "time": now.strftime("%H:%M"),

        # Review on
        "review_on": review_date,
    }

    logger.info(
        f"[KG_EHR] Formatted payload: extraction={extraction_id}, "
        f"vitals={bool(payload['vitals'].get('blood_pressure'))}, comorbidity_hits="
        f"{sum(1 for v in comorbidities.values() if isinstance(v, dict) and v.get('status') == 'Yes')}/12, "
        f"complaints={bool(payload['present_complaints'])}, "
        f"diagnosis={bool(payload['diagnosis'])}, "
        f"prescription_count={len(payload['prescription'])}, "
        f"hpi={bool(payload['history_of_presenting_illness'])}, "
        f"family_history={bool(payload['family_history'])}, "
        f"drug_history={bool(payload['drug_history'])}"
    )

    return payload


# ── CARDIO_REASSESS formatter ──────────────────────────────────────────

_REASSESS_COMPLAINT_KEYS = (
    "pain_over_surgical_site",
    "chest_pain",
    "breathlessness",
    "palpitations",
    "pedal_edema",
    "giddiness",
    "fatigue",
    "pnd",
    "orthopnea",
    "shoulder_pain",
    "body_pain",
    "normal_bowel_habits",
    "normal_bladder_habits",
    "loss_of_appetite",
    "decreased_sleep",
    "sweating",
    "ambulation",
)

_REASSESS_GEN_EXAM_KEYS = (
    "pallor",
    "icterus",
    "clubbing",
    "jvp_raised",
    "pedal_edema",
    "cyanosis",
    "varicose_veins",
    "peripheral_pulses_intact",
)


def _yes_no(value: Any) -> str:
    """Normalize to 'Yes' or 'No'. Anything empty/falsy/unrecognized → 'No'."""
    if value is None:
        return "No"
    s = str(value).strip().lower()
    if s in ("yes", "y", "true", "1", "present", "positive"):
        return "Yes"
    return "No"


def _build_reassess_complaints(chief_complaints: Any) -> Dict[str, Dict[str, str]]:
    """Build the 17-symptom payload object with consistent defaults."""
    if not isinstance(chief_complaints, dict):
        chief_complaints = {}
    result: Dict[str, Dict[str, str]] = {}
    for key in _REASSESS_COMPLAINT_KEYS:
        item = chief_complaints.get(key, {})
        if not isinstance(item, dict):
            item = {}
        result[key] = {
            "present": _yes_no(item.get("present")),
            "duration": _to_str(item.get("duration")),
            "description": _to_str(item.get("description")),
        }
    return result


def format_for_kg_reassess(
    extraction_data: Dict[str, Any],
    patient_id: str = "",
    doctor_id: str = "",
    extraction_id: str = "",
    doctor_name: str = "",
    uhid: str = "",
    visit_id: str = "",
    role: str = "",
) -> Dict[str, Any]:
    """
    Format CARDIO_REASSESS extraction data into KG Hospital Cardiology
    Re-Assessment payload.

    Reads the 10 segments linked to the CARDIO_REASSESS template:
    - vitals (weight, spo2, pulse, blood_pressure)
    - chiefComplaints (17 symptom checkboxes with duration + description)
    - generalExamination (8 yes/no checkboxes)
    - systemicExamination (cvs, rs, pa, cns)
    - woundExamination (healing_status, discharge)
    - diagnosis (shared from CARDIO_INITIAL — array of {name, code, type})
    - investigations (shared — represents NEXT VISIT investigations per prompt)
    - investigationsDone (already-performed investigations)
    - prescription (shared from CARDIO_INITIAL — new schema)
    - treatmentPlan (advice, treatment_and_future_plan, consultants_referral, review_on)
    """
    vitals = extraction_data.get("vitals", {}) or {}
    chief_complaints = extraction_data.get("chiefComplaints", {}) or {}
    gen_exam = extraction_data.get("generalExamination", {}) or {}
    sys_exam = extraction_data.get("systemicExamination", {}) or {}
    wound = extraction_data.get("woundExamination", {}) or {}
    diagnosis_arr = extraction_data.get("diagnosis", []) or []
    investigations_next = extraction_data.get("investigations", []) or []
    investigations_done = extraction_data.get("investigationsDone", []) or []
    prescription_arr = extraction_data.get("prescription", []) or []
    treatment = extraction_data.get("treatmentPlan", {}) or {}

    if not isinstance(vitals, dict):
        vitals = {}
    if not isinstance(chief_complaints, dict):
        chief_complaints = {}
    if not isinstance(gen_exam, dict):
        gen_exam = {}
    if not isinstance(sys_exam, dict):
        sys_exam = {}
    if not isinstance(wound, dict):
        wound = {}
    if not isinstance(treatment, dict):
        treatment = {}

    now = datetime.utcnow()
    review_date = treatment.get("review_on", "") or ""

    payload: Dict[str, Any] = {
        "patient_id": patient_id,
        "uhid": uhid,
        "visit_id": visit_id,
        "doctor_id": doctor_id,
        "extraction_id": extraction_id,
        "role": role,
        "form_type": "CARDIOLOGY_REASSESSMENT",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),

        # 1. Vitals
        "vitals": {
            "weight": _to_str(vitals.get("weight")),
            "spo2": _to_str(vitals.get("spo2")),
            "pulse": _to_str(vitals.get("pulse")),
            "blood_pressure": _to_str(vitals.get("blood_pressure")),
            "date_time": now.strftime("%Y-%m-%d %H:%M"),
        },

        # 2. Present complaints — 17 structured symptoms
        "present_complaints": _build_reassess_complaints(chief_complaints),

        # 3. General examination — 8 yes/no checkboxes
        "general_examination": {
            key: _yes_no(gen_exam.get(key)) for key in _REASSESS_GEN_EXAM_KEYS
        },

        # 4. Systemic examination — 4 systems
        "systemic_examination": {
            "cvs": _to_str(sys_exam.get("cvs")),
            "rs": _to_str(sys_exam.get("rs")),
            "pa": _to_str(sys_exam.get("pa")),
            "cns": _to_str(sys_exam.get("cns")),
        },

        # 5. Wound examination
        "wound_examination": {
            "healing_status": _to_str(wound.get("healing_status")),
            "discharge": _to_str(wound.get("discharge")),
        },

        # 6. Diagnosis
        "diagnosis": _format_diagnosis(diagnosis_arr),

        # 7. Investigations done — already performed
        "investigations_done": _build_investigations_list(investigations_done),

        # 8. Investigations next visit — shared INVESTIGATIONS segment, "ordered" per prompt
        "investigations_next_visit": _build_investigations_list(investigations_next),

        # 9. Prescription
        "prescription": _format_prescription_kg(prescription_arr, review_date),

        # 10. Treatment plan
        "treatment_and_future_plan": treatment.get("treatment_and_future_plan", "") or "",
        "advice": treatment.get("advice", "") or "",
        "consultants_referral": treatment.get("consultants_referral", "") or "",

        "doctor_name": doctor_name,
        "time": now.strftime("%H:%M"),
        "review_on": review_date,
    }

    complaints_yes = sum(
        1 for v in payload["present_complaints"].values()
        if isinstance(v, dict) and v.get("present") == "Yes"
    )
    gen_exam_yes = sum(1 for v in payload["general_examination"].values() if v == "Yes")

    logger.info(
        f"[KG_EHR] Formatted REASSESS payload: extraction={extraction_id}, "
        f"bp={bool(payload['vitals']['blood_pressure'])}, "
        f"weight={bool(payload['vitals']['weight'])}, "
        f"complaints_yes={complaints_yes}/17, "
        f"gen_exam_yes={gen_exam_yes}/8, "
        f"diagnosis={bool(payload['diagnosis'])}, "
        f"prescription_count={len(payload['prescription'])}, "
        f"investigations_done={len(payload['investigations_done'])}, "
        f"investigations_next={len(payload['investigations_next_visit'])}, "
        f"wound_status={bool(payload['wound_examination']['healing_status'])}, "
        f"systemic_cvs={bool(payload['systemic_examination']['cvs'])}, "
        f"advice={bool(payload['advice'])}, "
        f"review_on={bool(review_date)}"
    )

    return payload


# ── Diagnostic curl ────────────────────────────────────────────────────

async def _curl_diagnostic(api_url: str, api_key: Optional[str], payload: Dict[str, Any]) -> None:
    """
    Run layered network diagnostic before httpx POST.

    Tests each layer independently:
    1. DNS resolution (nslookup)
    2. TCP connectivity (curl connect-only)
    3. Full HTTP POST (curl with payload)
    """
    import socket
    from urllib.parse import urlparse
    hostname = urlparse(api_url).hostname or ""

    # ── Layer 0: Server's own outbound IP ──
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl", "-s", "--max-time", "5", "https://ifconfig.me",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
        outbound_ip = stdout.decode().strip() if stdout else "UNKNOWN"
        logger.info(f"[KG_EHR:DIAG] 0/3 SERVER OUTBOUND IP: {outbound_ip}  ← KG must whitelist this")
    except Exception as e:
        logger.warning(f"[KG_EHR:DIAG] 0/3 OUTBOUND IP: could not determine — {e}")

    # ── Layer 1: DNS resolution (Python socket — no nslookup needed) ──
    try:
        resolved_ip = await asyncio.get_event_loop().run_in_executor(
            None, lambda: socket.gethostbyname(hostname)
        )
        logger.info(f"[KG_EHR:DIAG] 1/3 DNS: {hostname} -> {resolved_ip}")
    except socket.gaierror as e:
        logger.warning(f"[KG_EHR:DIAG] 1/3 DNS FAILED: {hostname} — {e}")
        return
    except Exception as e:
        logger.warning(f"[KG_EHR:DIAG] 1/3 DNS ERROR: {e}")
        return

    # ── Layer 1b: Outbound port 443 test (raw TCP socket — bypasses curl) ──
    try:
        def _tcp_connect():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            try:
                s.connect((resolved_ip, 443))
                return True
            except (socket.timeout, ConnectionRefusedError, OSError) as e:
                return str(e)
            finally:
                s.close()

        tcp_result = await asyncio.get_event_loop().run_in_executor(None, _tcp_connect)
        if tcp_result is True:
            logger.info(f"[KG_EHR:DIAG] 1b/3 RAW TCP to {resolved_ip}:443 — CONNECTED OK")
        else:
            logger.warning(f"[KG_EHR:DIAG] 1b/3 RAW TCP to {resolved_ip}:443 — FAILED: {tcp_result}")
            logger.warning(f"[KG_EHR:DIAG] VERDICT: Cloud server CANNOT reach KG on port 443. Either cloud egress is blocked OR KG firewall is blocking server IP.")
            return
    except Exception as e:
        logger.warning(f"[KG_EHR:DIAG] 1b/3 RAW TCP ERROR: {e}")

    # ── Layer 2: TCP + TLS connectivity (no payload) ──
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl", "-s", "-o", "/dev/null",
            "-w", "tcp_connect:%{time_connect}s ssl:%{time_appconnect}s status:%{http_code}",
            "--connect-timeout", "10",
            "-X", "HEAD", api_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        output = stdout.decode().strip() if stdout else ""
        logger.info(f"[KG_EHR:DIAG] 2/3 TCP+TLS: {output} (rc={proc.returncode})")
        if proc.returncode != 0:
            err = stderr.decode().strip() if stderr else ""
            logger.warning(f"[KG_EHR:DIAG] TCP+TLS FAILED — curl error: {err}")
            # curl exit codes: 6=DNS fail, 7=connect refused, 28=timeout, 35=SSL error, 60=SSL cert
            code_map = {6: "DNS_FAIL", 7: "CONN_REFUSED/FIREWALL", 28: "TIMEOUT/FIREWALL", 35: "SSL_HANDSHAKE_FAIL", 60: "SSL_CERT_INVALID"}
            hint = code_map.get(proc.returncode, f"CURL_EXIT_{proc.returncode}")
            logger.warning(f"[KG_EHR:DIAG] LIKELY CAUSE: {hint}")
            return
    except asyncio.TimeoutError:
        logger.warning("[KG_EHR:DIAG] 2/3 TCP+TLS: TIMEOUT after 15s — likely FIREWALL blocking port 443")
        return
    except Exception as e:
        logger.warning(f"[KG_EHR:DIAG] 2/3 TCP+TLS: ERROR — {e}")

    # ── Layer 3: Full HTTP POST with payload ──
    try:
        payload_json = json.dumps(payload)
        cmd = [
            "curl", "-s",
            "-o", "/dev/null",
            "-w", "http_status:%{http_code} time_dns:%{time_namelookup}s time_connect:%{time_connect}s time_ssl:%{time_appconnect}s time_total:%{time_total}s size_upload:%{size_upload}B",
            "-X", "POST", api_url,
            "-H", "Content-Type: application/json",
            "-m", "30",
        ]
        if api_key:
            cmd.extend(["-H", f"Authorization: Bearer {api_key}"])
        cmd.extend(["-d", payload_json])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=35)
        output = stdout.decode().strip() if stdout else ""
        err = stderr.decode().strip() if stderr else ""

        logger.info(f"[KG_EHR:DIAG] 3/3 HTTP POST: {output} (rc={proc.returncode})")
        if err:
            logger.warning(f"[KG_EHR:DIAG] HTTP POST stderr: {err}")
    except asyncio.TimeoutError:
        logger.warning("[KG_EHR:DIAG] 3/3 HTTP POST: curl TIMEOUT after 35s")
    except Exception as e:
        logger.warning(f"[KG_EHR:DIAG] 3/3 HTTP POST: ERROR — {e}")


# ── HTTP sender ────────────────────────────────────────────────────────

async def send_to_kg(
    payload: Dict[str, Any],
    api_url: str,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send formatted payload to KG Hospital API endpoint.

    Args:
        payload: The formatted payload from format_for_kg()
        api_url: KG Hospital API URL
        api_key: Optional API key for authentication

    Returns:
        Dict with status_code, body, and success flag
    """
    logger.info(f"[KG_EHR] Sending to {api_url}")
    logger.info(f"[KG_EHR] Payload extraction_id: {payload.get('extraction_id')}, payload_size: {len(json.dumps(payload))} bytes")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        logger.info("[KG_EHR] No API key provided, sending without auth")

    try:
        logger.info("[KG_EHR] Starting httpx POST...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                api_url,
                json=payload,
                headers=headers,
            )

            logger.info(f"[KG_EHR] httpx response status: {response.status_code}")

            try:
                body = response.json()
            except Exception:
                body = {"raw": response.text}

            if response.status_code >= 400:
                logger.warning(f"[KG_EHR] Error response: {response.status_code} - {body}")

            return {
                "status_code": response.status_code,
                "body": body,
                "success": 200 <= response.status_code < 300,
            }

    except httpx.TimeoutException as te:
        logger.warning(f"[KG_EHR] httpx TIMEOUT after 30s — type: {type(te).__name__}")
        return {
            "status_code": 408,
            "body": {"error": f"Request timeout: {type(te).__name__}"},
            "success": False,
        }
    except httpx.RequestError as e:
        logger.warning(f"[KG_EHR] httpx REQUEST ERROR: {type(e).__name__}: {e}")
        return {
            "status_code": 500,
            "body": {"error": str(e)},
            "success": False,
        }

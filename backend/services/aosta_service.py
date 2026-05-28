"""
Aosta EHR Integration Service

Provides functions to format extraction insights for Aosta API
and send data to Aosta's backend endpoint.

Now uses hospital_ehr table for configuration instead of environment variables.
"""

import logging
import httpx
import re
from math import gcd
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger(__name__)


# Keywords for detecting drug type from medicine name
_SYRUP_KEYWORDS = {"SYRUP", "SYR", "LIQUID", "SUSPENSION", "ELIXIR", "ORAL SOLUTION"}
_DROPS_KEYWORDS = {"DROPS", "DROP"}
_CAPSULE_KEYWORDS = {"CAPSULE", "CAP"}
_TABLET_KEYWORDS = {"TABLET", "TAB"}

# Form values from DB that map to liquid types
_LIQUID_FORMS = {"syrup", "liquid", "suspension", "elixir", "oral solution", "drops"}


def _detect_drug_type(med: dict) -> str:
    """
    Detect drug type using multiple signals (priority order):
    1. _form field from medicine matcher DB record (most reliable)
    2. form field from Gemini extraction (if DB form not available)
    3. Medicine name keywords (SYRUP, TABLET, etc.)
    4. Quantity values - check if any qty contains "ml" suffix
    Fallback: "tablet"
    """
    # Signal 1: _form from DB (most reliable)
    form = (med.get("_form") or "").strip().lower()
    # Signal 2: form from Gemini extraction (if DB form not available)
    if not form:
        form = (med.get("form") or "").strip().lower()
    if form:
        if form in _LIQUID_FORMS:
            return "syrup"
        if form in ("capsule", "cap"):
            return "capsule"
        if form in ("tablet", "tab"):
            return "tablet"
        if form in ("drops", "drop"):
            return "drops"
        # Recognized form but not in our map — still use it if reasonable
        if form:
            logger.debug(f"[AOSTA] Unrecognized form '{form}', falling through to name check")

    # Signal 3: Medicine name keywords
    name_upper = (med.get("name") or "").upper()
    if name_upper:
        for kw in _SYRUP_KEYWORDS:
            if kw in name_upper:
                return "syrup"
        for kw in _DROPS_KEYWORDS:
            if kw in name_upper:
                return "drops"
        for kw in _CAPSULE_KEYWORDS:
            if kw in name_upper:
                return "capsule"
        for kw in _TABLET_KEYWORDS:
            if kw in name_upper:
                return "tablet"

    # Signal 4: Quantity values containing "ml"
    for qty_key in ("morning_qty", "noon_qty", "evening_qty", "night_qty"):
        qty_str = str(med.get(qty_key, ""))
        if re.search(r'\d+\s*ml', qty_str, re.IGNORECASE):
            return "syrup"

    return "tablet"


def _parse_qty(raw: Any) -> float:
    """Parse a quantity value to float, stripping 'ml' suffix if present."""
    s = str(raw or "0").strip().lower()
    s = re.sub(r'\s*ml\s*$', '', s)
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _float_gcd(values: List[float]) -> float:
    """Compute GCD of a list of floats by converting to integer multiples."""
    # Multiply by 100 to handle up to 2 decimal places
    int_values = [int(round(v * 100)) for v in values if v > 0]
    if not int_values:
        return 0.0
    result = int_values[0]
    for v in int_values[1:]:
        result = gcd(result, v)
    return result / 100.0


def _compute_dosage_and_frequencies(
    med: dict, drug_type: str
) -> Tuple[str, str, str, str, str]:
    """
    Compute dosage_value and adjusted frequencies based on drug type.

    For tablets/capsules: dosage_value=1, frequencies = raw qty values
    For syrups/drops/liquid: dosage_value = GCD of non-zero qty values,
                             frequencies = qty / dosage_value

    Returns: (dosage_value, freq_morning, freq_afternoon, freq_evening, freq_night)
    """
    raw_m = _parse_qty(med.get("morning_qty", "0"))
    raw_a = _parse_qty(med.get("noon_qty", "0"))
    raw_e = _parse_qty(med.get("evening_qty", "0"))
    raw_n = _parse_qty(med.get("night_qty", "0"))

    if drug_type in ("syrup", "drops", "liquid", "oral solution", "suspension", "elixir"):
        non_zero = [v for v in [raw_m, raw_a, raw_e, raw_n] if v > 0]
        if not non_zero:
            return ("null", "0", "0", "0", "0")

        dosage = _float_gcd(non_zero)
        if dosage <= 0:
            dosage = non_zero[0]  # fallback to first non-zero value

        def _freq(val: float) -> str:
            if val == 0:
                return "0"
            f = val / dosage
            return f"{f:.2f}" if f != int(f) else str(int(f))

        dosage_str = f"{dosage:.2f}" if dosage != int(dosage) else f"{int(dosage)}.00"
        return (dosage_str, _freq(raw_m), _freq(raw_a), _freq(raw_e), _freq(raw_n))
    else:
        # Tablets/capsules: dosage_value=1, frequencies are raw quantities
        def _fmt(val: float) -> str:
            if val == 0:
                return "0"
            return f"{val:.2f}" if val != int(val) else str(int(val))

        return ("1", _fmt(raw_m), _fmt(raw_a), _fmt(raw_e), _fmt(raw_n))


def _build_aosta_medicines(prescription: Any) -> List[Dict[str, Any]]:
    """Build the Aosta-shape Medicines array from extraction's prescription field."""
    medicines: List[Dict[str, Any]] = []
    if not isinstance(prescription, list):
        return medicines
    for med in prescription:
        if not isinstance(med, dict):
            continue
        med_name = med.get("name", "")
        drug_type = _detect_drug_type(med)
        is_liquid = drug_type in ("syrup", "liquid", "oral solution", "suspension", "elixir", "drops")
        drug_type_label = "syrup" if is_liquid else ("capsule" if drug_type == "capsule" else "tablet")

        dosage_val, freq_m, freq_a, freq_e, freq_n = _compute_dosage_and_frequencies(med, drug_type_label)

        raw_days = med.get("durationDays", "")
        try:
            days_val = str(int(float(str(raw_days)))) if raw_days and str(raw_days).strip().lower() not in ("n/a", "na", "null", "none", "") else "1"
        except (ValueError, TypeError):
            days_val = "1"

        medicines.append({
            "brand_id": med.get("_external_id") or "null",
            "brand_name": med_name,
            "generic_name": med.get("_formulary_name") or "null",
            "strength": "null",
            "uom": "null",
            "frequency_morning": freq_m,
            "frequency_afternoon": freq_a,
            "frequency_evening": freq_e,
            "frequency_night": freq_n,
            "days": days_val,
            "dosage_value": dosage_val,
            "prn": "",
            "route": "Oral",
            "drug_type": drug_type_label,
            "medication_name": f"({med_name.upper()})" if med_name else "",
            "medicine_type": "existing",
            "instructions": med.get("remarks", "") or med.get("timeToTake", "")
        })
    return medicines


def _build_aosta_investigations(investigations: Any, hospital_code: str) -> List[Dict[str, Any]]:
    """Build the Aosta-shape Investigations array from extraction's investigations field."""
    formatted: List[Dict[str, Any]] = []
    if not isinstance(investigations, list):
        return formatted
    for inv in investigations:
        if isinstance(inv, dict):
            test_name = inv.get("Test_Name") or inv.get("name") or ""
            test_id = inv.get("Test_id")
            external_id = test_id if (test_id and test_id != "null") else inv.get("_external_id")
        else:
            test_name = str(inv) if inv else ""
            external_id = None

        if not test_name:
            continue

        common_names = inv.get("_common_names") or [] if isinstance(inv, dict) else []
        short_name = common_names[0] if common_names else (test_name[:20] if len(test_name) > 20 else test_name)

        formatted.append({
            "Test_ShortName": short_name,
            "Test_Name": test_name,
            "Test_id": external_id or "null",
            "Test_type": (inv.get("_investigation_type") if isinstance(inv, dict) else None) or "Laboratory",
            "hospital_id": hospital_code or "",
        })
    return formatted


def _build_followup_text(follow_up: Any) -> str:
    """Compose a single-string follow-up instruction from extraction's followUp field."""
    if isinstance(follow_up, dict):
        parts = []
        if follow_up.get("special_instructions"):
            parts.append(follow_up.get("special_instructions"))
        if follow_up.get("other_instructions"):
            parts.append(follow_up.get("other_instructions"))
        if follow_up.get("review_date"):
            parts.append(f"Review date: {follow_up.get('review_date')}")
        return ". ".join(parts)
    return str(follow_up) if follow_up else ""


def _stringify_treatment_plan(treatment_plan: Any) -> str:
    """Coerce a treatmentPlan value (string | list | other) into a single string."""
    if isinstance(treatment_plan, list):
        return ". ".join(str(item) for item in treatment_plan if item)
    if isinstance(treatment_plan, str):
        return treatment_plan
    return str(treatment_plan) if treatment_plan else ""


def _stringify_examination(extraction_insights: Dict[str, Any]) -> str:
    """Read the examination segment (list / dict / string) and return a flat string.

    Tries the canonical key 'examination' first, then 'physicalExamination' / 'physicalExaminationOp'
    (see _KEY_EQUIVALENCE_GROUPS in extraction_service.py).
    """
    for key in ("examination", "physicalExamination", "physicalExaminationOp"):
        val = extraction_insights.get(key)
        if not val:
            continue
        if isinstance(val, str):
            return val
        if isinstance(val, list):
            parts = []
            for item in val:
                if isinstance(item, dict):
                    name = item.get("name", "")
                    value = item.get("value", "")
                    if name and value:
                        parts.append(f"{name}: {value}")
                    elif value:
                        parts.append(str(value))
                elif item:
                    parts.append(str(item))
            return ", ".join(parts)
        if isinstance(val, dict):
            return ", ".join(f"{k}: {v}" for k, v in val.items() if v)
    return ""


_DRUG_TYPE_PREFIX = {"tablet": "Tab", "capsule": "Cap", "syrup": "Syr", "drops": "Drops"}
_NAME_PREFIX_TOKENS = {"tab", "tablet", "cap", "capsule", "syr", "syrup", "drops", "drop"}


def _stringify_prescription(prescription: Any) -> str:
    """Render the prescription array as a single flat string.

    Format per med: '<Tab|Cap|Syr|Drops> <name> <m-n-e-ni> x <days>d (<remarks>)'.
    Prefix is omitted when the name already starts with a form token.
    """
    if not isinstance(prescription, list):
        return ""
    segments: List[str] = []
    for med in prescription:
        if not isinstance(med, dict):
            continue
        name = (med.get("name") or "").strip()
        if not name:
            continue
        first_token = name.split(None, 1)[0].rstrip(".").lower()
        prefix = "" if first_token in _NAME_PREFIX_TOKENS else _DRUG_TYPE_PREFIX.get(_detect_drug_type(med), "Tab")
        m = str(med.get("morning_qty") or "0").strip() or "0"
        n = str(med.get("noon_qty") or "0").strip() or "0"
        e = str(med.get("evening_qty") or "0").strip() or "0"
        ni = str(med.get("night_qty") or "0").strip() or "0"
        head = f"{prefix} {name}".strip()
        seg = f"{head} {m}-{n}-{e}-{ni}"
        days_raw = str(med.get("durationDays") or "").strip()
        if days_raw and days_raw.lower() not in ("n/a", "na", "null", "none", "0"):
            seg += f" x {days_raw}d"
        instr = (med.get("remarks") or "").strip()
        if instr:
            seg += f" ({instr})"
        segments.append(seg)
    return "; ".join(segments)


def _split_prior_imaging(items: Any) -> Tuple[str, str, str, str]:
    """Return (composite, first_date, first_modality, first_findings) from priorImaging array."""
    if not isinstance(items, list) or not items:
        return ("", "", "", "")
    composite_parts: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        date = (item.get("date") or "").strip()
        mod = (item.get("modality") or "").strip()
        find = (item.get("findings") or "").strip()
        head = " ".join(p for p in [date, mod] if p)
        if head and find:
            composite_parts.append(f"{head}: {find}")
        elif head:
            composite_parts.append(head)
        elif find:
            composite_parts.append(find)
    first = items[0] if isinstance(items[0], dict) else {}
    return (
        "; ".join(composite_parts),
        (first.get("date") or "").strip(),
        (first.get("modality") or "").strip(),
        (first.get("findings") or "").strip(),
    )


def _join_labeled(data: Dict[str, Any], pairs: List[Tuple[str, str]]) -> str:
    """Build 'Label: value. Label: value' skipping empty values."""
    if not isinstance(data, dict):
        return ""
    parts: List[str] = []
    for key, label in pairs:
        val = (data.get(key) or "").strip() if isinstance(data.get(key), str) else str(data.get(key) or "").strip()
        if val:
            parts.append(f"{label}: {val}")
    return ". ".join(parts)


def format_for_aosta(
    extraction_insights: Dict[str, Any],
    patient_id: str,
    doctor_id: str,
    hospital_code: str,
    ip_id: Optional[str] = None,
    op_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Format AOSTA_OP extraction insights to Aosta API schema.

    Transforms our extraction format to match Aosta's expected payload structure.

    Args:
        extraction_insights: The extraction insights dict (from original_extraction_json or edited_extraction_json)
        patient_id: Patient ID from patients.patient_id (VARCHAR) - maps to RegNumber
        doctor_id: Doctor UUID as string - maps to PractitionerId
        hospital_code: Hospital code from hospitals.hospital_code - maps to HospitalId
        ip_id: Inpatient visit ID from recording_metadata - maps to Ipid
        op_id: Outpatient visit ID from recording_metadata - maps to Opid

    Returns:
        Dict formatted for Aosta API
    """
    payload = {
        # Metadata fields
        "RegNumber": patient_id or "",
        "Ipid": ip_id or "0",
        "Opid": op_id or "0",
        "PractitionerId": doctor_id or "",
        "HospitalId": hospital_code or "",
    }

    # Flatten history object - extract each history field
    history = extraction_insights.get("history", {})

    # Combine PastMedicalHistory with Summary and CurrentMedications
    past_medical = history.get("PastMedicalHistory", "")
    summary = extraction_insights.get("summary", "")

    # Handle current_medications - can be at root level (string) or in history (array of objects)
    current_meds_history = extraction_insights.get("currentMedicationsHistory", "")

    # AOSTA format: history.current_medications is array of {medication_name, dosage, frequency}
    current_medications = history.get("current_medications", [])
    if isinstance(current_medications, list) and current_medications:
        med_names = []
        for med in current_medications:
            if isinstance(med, dict):
                name = med.get("medication_name", "")
                if name and name != "N/A":
                    dosage = med.get("dosage", "")
                    if dosage and dosage != "N/A":
                        med_names.append(f"{name} ({dosage})")
                    else:
                        med_names.append(name)
        if med_names:
            current_meds_history = f"Current medications: {', '.join(med_names)}"

    # Combine non-empty values into PastMedicalHistory
    past_medical_parts = [p for p in [past_medical, summary, current_meds_history] if p and p != "N/A"]
    payload["PastMedicalHistory"] = ", ".join(past_medical_parts)

    payload["PresentMedicalHistory"] = history.get("PresentMedicalHistory", "")
    payload["SurgicalHistory"] = history.get("SurgicalHistory", "")
    payload["SocialHistory"] = history.get("SocialHistory", "")
    payload["FamilyHistory"] = history.get("FamilyHistory", "")

    # Map chiefComplaints (array of strings) to ChiefComplaints (comma-separated string)
    # Handle both list format and dict format (e.g., {'0': 'complaint1', '1': 'complaint2'})
    chief_complaints = extraction_insights.get("chiefComplaints", [])
    if isinstance(chief_complaints, list):
        payload["ChiefComplaints"] = ", ".join(str(c) for c in chief_complaints if c) if chief_complaints else ""
    elif isinstance(chief_complaints, dict):
        # Handle dict with numeric keys - extract values in order
        values = [str(chief_complaints[k]) for k in sorted(chief_complaints.keys(), key=lambda x: int(x) if str(x).isdigit() else x) if chief_complaints.get(k)]
        payload["ChiefComplaints"] = ", ".join(values) if values else ""
    else:
        payload["ChiefComplaints"] = str(chief_complaints) if chief_complaints else ""

    # Map allergies (string)
    payload["Allergies"] = extraction_insights.get("allergies", "")

    # Map diagnosis (array of {code, name, type}) to comma-separated string of "name-code-type"
    diagnosis_list = extraction_insights.get("diagnosis", [])
    if isinstance(diagnosis_list, list):
        diagnosis_parts = []
        for d in diagnosis_list:
            if isinstance(d, dict) and d.get("name"):
                name = d.get("name", "")
                code = d.get("code", "")
                dtype = d.get("type", "")
                # Format: "name-code-type" (skip empty parts)
                parts = [p for p in [name, code, dtype] if p]
                diagnosis_parts.append("-".join(parts))
        payload["Diagnosis"] = ", ".join(diagnosis_parts) if diagnosis_parts else ""
    else:
        payload["Diagnosis"] = str(diagnosis_list) if diagnosis_list else ""

    payload["TreatmentPlan"] = _stringify_treatment_plan(extraction_insights.get("treatmentPlan", ""))

    payload["Medicines"] = _build_aosta_medicines(extraction_insights.get("prescription", []))
    payload["Investigations"] = _build_aosta_investigations(extraction_insights.get("investigations", []), hospital_code)
    payload["DoctorInstruction"] = _build_followup_text(extraction_insights.get("followUp", {}))

    logger.info(f"[AOSTA] Formatted payload with {len(payload)} fields")
    return payload


def format_for_gem_case_sheet(
    extraction_insights: Dict[str, Any],
    patient_id: str,
    doctor_id: str,
    hospital_code: str,
    template_id: str,
    template_name: str,
    ip_id: Optional[str] = None,
    op_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Format extraction for the GEM_CASE_SHEET payload (sent to Aosta API URL).

    Differs from Aosta: single combined 'History' string, 'Examination' field,
    Template_id/Template_Name from recording_metadata. No Allergies/DoctorInstruction.
    """
    payload: Dict[str, Any] = {
        "RegNumber": patient_id or "",
        "Ipid": ip_id or "0",
        "Opid": op_id or "0",
        "PractitionerId": doctor_id or "",
        "Template_id": str(template_id) if template_id is not None else "",
        "Template_Name": template_name or "",
        "HospitalId": hospital_code or "",
    }

    history = extraction_insights.get("history", {}) or {}
    history_parts = [
        history.get("PastMedicalHistory", ""),
        history.get("PresentMedicalHistory", ""),
        history.get("SurgicalHistory", ""),
        history.get("SocialHistory", ""),
        history.get("FamilyHistory", ""),
    ]
    payload["History"] = ", ".join(p for p in history_parts if p and p != "N/A")

    chief_complaints = extraction_insights.get("chiefComplaints", [])
    if isinstance(chief_complaints, list):
        payload["ChiefComplaints"] = ", ".join(str(c) for c in chief_complaints if c) if chief_complaints else ""
    elif isinstance(chief_complaints, dict):
        values = [str(chief_complaints[k]) for k in sorted(chief_complaints.keys(), key=lambda x: int(x) if str(x).isdigit() else x) if chief_complaints.get(k)]
        payload["ChiefComplaints"] = ", ".join(values) if values else ""
    else:
        payload["ChiefComplaints"] = str(chief_complaints) if chief_complaints else ""

    diagnosis_list = extraction_insights.get("diagnosis", [])
    if isinstance(diagnosis_list, list):
        diagnosis_parts = []
        for d in diagnosis_list:
            if isinstance(d, dict) and d.get("name"):
                parts = [p for p in [d.get("name", ""), d.get("code", ""), d.get("type", "")] if p]
                diagnosis_parts.append("-".join(parts))
        payload["Diagnosis"] = ", ".join(diagnosis_parts) if diagnosis_parts else ""
    else:
        payload["Diagnosis"] = str(diagnosis_list) if diagnosis_list else ""

    payload["TreatmentPlan"] = _stringify_treatment_plan(extraction_insights.get("treatmentPlan", ""))
    payload["Examination"] = _stringify_examination(extraction_insights)

    payload["Medicines"] = _build_aosta_medicines(extraction_insights.get("prescription", []))
    payload["Investigations"] = _build_aosta_investigations(extraction_insights.get("investigations", []), hospital_code)

    logger.info(f"[GEM_CASE_SHEET] Formatted payload with {len(payload)} fields (template={template_name})")
    return payload


def format_for_gcc_review(
    extraction_insights: Dict[str, Any],
    patient_id: str,
    doctor_id: str,
    hospital_code: str,
    template_id: str,
    template_name: str,
    ip_id: Optional[str] = None,
    op_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Format extraction for the GCC_REVIEW payload (sent to Aosta API URL).

    Only carries identifiers, FollowupCaseSheet (treatmentPlan + followUp combined),
    Medicines, and Investigations.
    """
    payload: Dict[str, Any] = {
        "RegNumber": patient_id or "",
        "Ipid": ip_id or "0",
        "Opid": op_id or "0",
        "PractitionerId": doctor_id or "",
        "Template_id": str(template_id) if template_id is not None else "",
        "Template_Name": template_name or "",
        "HospitalId": hospital_code or "",
    }

    followup_parts = [
        _stringify_treatment_plan(extraction_insights.get("treatmentPlan", "")),
        _build_followup_text(extraction_insights.get("followUp", {})),
    ]
    payload["FollowupCaseSheet"] = ". ".join(p for p in followup_parts if p)

    payload["Medicines"] = _build_aosta_medicines(extraction_insights.get("prescription", []))
    payload["Investigations"] = _build_aosta_investigations(extraction_insights.get("investigations", []), hospital_code)

    logger.info(f"[GCC_REVIEW] Formatted payload with {len(payload)} fields (template={template_name})")
    return payload


def format_for_aosta_gem_breast_centre(
    extraction_insights: Dict[str, Any],
    patient_id: str,
    doctor_id: str,
    hospital_code: str,
    template_id: str,
    template_name: str,
    ip_id: Optional[str] = None,
    op_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Format extraction for the GEM_BREAST_CENTRE payload (sent to Aosta API URL).

    44 flat-string fields. Breast-centre-specific segments (patientHistory,
    menstrualHistory, obstetricHistory, breastHistory, examinationBreast,
    imaging, priorImaging, recommendationAdvise) feed individual Aosta fields;
    PersonalHistory/MenstrualHistory/ObstetricHistory composites are built
    from the granular pieces. DiagnosisNotes has no source — emitted empty.
    Requires Template_id/Template_Name from recording_metadata.
    """
    patient_history = extraction_insights.get("patientHistory") or {}
    menstrual_history = extraction_insights.get("menstrualHistory") or {}
    obstetric_history = extraction_insights.get("obstetricHistory") or {}
    breast_history = extraction_insights.get("breastHistory") or {}
    examination_breast = extraction_insights.get("examinationBreast") or {}
    imaging = extraction_insights.get("imaging") or {}
    recommendation_advise = extraction_insights.get("recommendationAdvise") or {}
    prior_imaging_items = extraction_insights.get("priorImaging") or []

    prior_imaging_str, imaging_date, modality, findings = _split_prior_imaging(prior_imaging_items)

    chief_complaints = extraction_insights.get("chiefComplaints", [])
    if isinstance(chief_complaints, list):
        chief_complaints_str = ", ".join(str(c) for c in chief_complaints if c)
    elif isinstance(chief_complaints, dict):
        values = [
            str(chief_complaints[k])
            for k in sorted(chief_complaints.keys(), key=lambda x: int(x) if str(x).isdigit() else x)
            if chief_complaints.get(k)
        ]
        chief_complaints_str = ", ".join(values)
    else:
        chief_complaints_str = str(chief_complaints) if chief_complaints else ""

    diagnosis_list = extraction_insights.get("diagnosis", [])
    if isinstance(diagnosis_list, list):
        diagnosis_parts = []
        for d in diagnosis_list:
            if isinstance(d, dict) and d.get("name"):
                parts = [p for p in [d.get("name", ""), d.get("code", ""), d.get("type", "")] if p]
                diagnosis_parts.append("-".join(parts))
        diagnosis_str = ", ".join(diagnosis_parts)
    else:
        diagnosis_str = str(diagnosis_list) if diagnosis_list else ""

    def _s(d: Any, key: str) -> str:
        if not isinstance(d, dict):
            return ""
        v = d.get(key)
        if v is None:
            return ""
        return v.strip() if isinstance(v, str) else str(v).strip()

    payload: Dict[str, Any] = {
        "RegNumber": patient_id or "",
        "Ipid": ip_id or "0",
        "Opid": op_id or "0",
        "PractitionerId": doctor_id or "",
        "Template_id": str(template_id) if template_id is not None else "",
        "Template_Name": template_name or "",
        "HospitalId": hospital_code or "",

        "DiagnosisNotes": "",
        "ChiefComplaints": chief_complaints_str,
        "PastHistory": _s(patient_history, "past_history"),
        "PriorImaging": prior_imaging_str,
        "ImagingDate": imaging_date,
        "Modality": modality,
        "Findings": findings,
        "BreastBiopsiesHistory": _s(breast_history, "breast_biopsies_history"),
        "BreastSurgeryHistory": _s(breast_history, "breast_surgery_history"),
        "SurgeryMedicalIllnessHistory": _s(patient_history, "surgical_medical_illness_history"),
        "PersonalHistory": _join_labeled(patient_history, [("smoking", "Smoking"), ("alcohol", "Alcohol")]),
        "Smoking": _s(patient_history, "smoking"),
        "Alcohol": _s(patient_history, "alcohol"),
        "MenstrualHistory": _join_labeled(menstrual_history, [
            ("age_at_menarche", "Menarche"),
            ("age_at_menopause", "Menopause"),
            ("menopausal_status", "Status"),
            ("lmp", "LMP"),
            ("cycles", "Cycles"),
            ("marital_status", "Marital"),
        ]),
        "MenopausalStatus": _s(menstrual_history, "menopausal_status"),
        "AgeAtMenarche": _s(menstrual_history, "age_at_menarche"),
        "AgeAtMenopause": _s(menstrual_history, "age_at_menopause"),
        "LMP": _s(menstrual_history, "lmp"),
        "Cycles": _s(menstrual_history, "cycles"),
        "MaritalStatus": _s(menstrual_history, "marital_status"),
        "ObstetricHistory": _join_labeled(obstetric_history, [
            ("age_at_first_childbirth", "Age at first childbirth"),
            ("number_of_children", "Children"),
            ("total_months_of_breastfeeding", "Breastfeeding (months)"),
            ("family_history_of_cancer", "Family Hx of cancer"),
        ]),
        "AgeAtFirstChildBirth": _s(obstetric_history, "age_at_first_childbirth"),
        "NumberOfChildren": _s(obstetric_history, "number_of_children"),
        "TotalMonthsOfBreastFeeding": _s(obstetric_history, "total_months_of_breastfeeding"),
        "FamilyHistoryOfCancer": _s(obstetric_history, "family_history_of_cancer"),
        "AllergyHistory": _s(patient_history, "allergy_history"),
        "Medicines": _stringify_prescription(extraction_insights.get("prescription", [])),
        "Following": _s(patient_history, "following"),
        "Examination": _s(examination_breast, "examination"),
        "Diagnosis": diagnosis_str,
        "Imaging": _s(imaging, "imaging"),
        "UltrasoundHistory": _s(imaging, "ultrasound"),
        "BIRADSCategory": _s(imaging, "birads_category"),
        "Recommendation": _s(recommendation_advise, "recommendation"),
        "Management": _s(recommendation_advise, "management"),
        "Advise": _s(recommendation_advise, "advise"),
        "ReviewRemarks": _s(recommendation_advise, "review_remarks"),
    }

    logger.info(f"[GEM_BREAST_CENTRE] Formatted payload with {len(payload)} fields (template={template_name})")
    return payload


async def send_to_aosta(
    payload: Dict[str, Any],
    api_url: str,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send formatted data to Aosta backend.

    Args:
        payload: The formatted payload from format_for_aosta()
        api_url: Required - the hospital's configured Aosta URL
        api_key: Optional - if not provided, sends without Authorization header

    Returns:
        Dict with status_code, body, and success flag
    """
    logger.info(f"[AOSTA] Sending to {api_url}")
    logger.info(f"[AOSTA] Payload RegNumber: {payload.get('RegNumber')}, PractitionerId: {payload.get('PractitionerId')}")
    logger.debug(f"[AOSTA] Full payload: {payload}")

    # Build headers - include Authorization only if API key is provided
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        logger.info("[AOSTA] No API key provided, sending without auth")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                api_url,
                json=payload,
                headers=headers
            )

            logger.info(f"[AOSTA] Response status: {response.status_code}")

            # Try to parse response as JSON, fallback to text
            try:
                body = response.json()
            except Exception:
                body = {"raw": response.text}

            # Log warning (not error) for non-success - don't block pipeline
            if response.status_code >= 400:
                logger.warning(f"[AOSTA] Error response: {response.status_code} - {body}")

            return {
                "status_code": response.status_code,
                "body": body,
                "success": 200 <= response.status_code < 300
            }

    except httpx.TimeoutException:
        logger.warning("[AOSTA] Request timed out after 30 seconds")
        return {
            "status_code": 408,
            "body": {"error": "Request timeout"},
            "success": False
        }
    except httpx.RequestError as e:
        logger.warning(f"[AOSTA] Request failed: {e}")
        return {
            "status_code": 500,
            "body": {"error": str(e)},
            "success": False
        }


async def get_hospital_ehr_config(hospital_id: str, ehr_type: str) -> Optional[Dict[str, Any]]:
    """
    Get EHR configuration for a hospital.

    Args:
        hospital_id: Hospital UUID as string
        ehr_type: EHR integration type (e.g., 'aosta', 'raster', 'epic')

    Returns:
        Dict with {api_url, api_key, is_enabled} or None if not configured
    """
    from services.supabase_service import supabase

    try:
        result = (
            supabase.table("hospital_ehr")
            .select("api_url, api_key, is_enabled")
            .eq("hospital_id", hospital_id)
            .eq("ehr_integration_type", ehr_type.lower())
            .eq("is_enabled", True)
            .limit(1)
            .execute()
        )

        if result.data and len(result.data) > 0:
            config = result.data[0]
            logger.info(f"[EHR] Found {ehr_type} config for hospital {hospital_id}: url={bool(config.get('api_url'))}")
            return {
                "api_url": config.get("api_url"),
                "api_key": config.get("api_key"),
                "is_enabled": config.get("is_enabled", True)
            }

        logger.debug(f"[EHR] No {ehr_type} config found for hospital {hospital_id}")
        return None

    except Exception as e:
        logger.warning(f"[EHR] Failed to get {ehr_type} config for hospital {hospital_id}: {e}")
        return None


def get_hospital_code(hospital_id: str) -> Optional[str]:
    """
    Get hospital_code from hospital_id.

    Args:
        hospital_id: Hospital UUID as string

    Returns:
        Hospital code string or None if not found
    """
    from services.supabase_service import supabase

    try:
        response = (
            supabase.table("hospitals")
            .select("hospital_code")
            .eq("id", hospital_id)
            .limit(1)
            .execute()
        )

        if response.data and len(response.data) > 0:
            return response.data[0].get("hospital_code")
        return None

    except Exception as e:
        logger.error(f"[AOSTA] Failed to get hospital_code for {hospital_id}: {e}")
        return None


def get_patient_external_id(patient_uuid: str) -> Optional[str]:
    """
    Get patient_id (external VARCHAR ID) from patient UUID.

    Args:
        patient_uuid: Patient table UUID as string

    Returns:
        Patient ID string (e.g., "PAT001") or None if not found
    """
    from services.supabase_service import supabase

    try:
        response = (
            supabase.table("patients")
            .select("patient_id")
            .eq("id", patient_uuid)
            .limit(1)
            .execute()
        )

        if response.data and len(response.data) > 0:
            return response.data[0].get("patient_id")
        return None

    except Exception as e:
        logger.error(f"[AOSTA] Failed to get patient_id for {patient_uuid}: {e}")
        return None

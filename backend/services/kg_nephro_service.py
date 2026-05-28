"""
KG Hospital Nephrology EHR Integration Service

Transforms NEPHRO_INITIAL extraction output into KG Hospital Nephrology
Initial Assessment payload and POSTs it to the configured KG endpoint.

NEPHRO_INITIAL segment mapping (mirrors CARDIO_INITIAL where possible):
- VITALS -> vitals (temp, pulse, rr, bp, spo2, date_time)
- NUTRITIONAL_SCREENING -> nutritional_screening
- COMORBIDITIES_NEPHRO -> comorbidities (16-item nephro checklist)
- ALLERGY -> drug_allergy
- CHIEF_COMPLAINTS -> present_complaints
- HISTORY_OF_PRESENT_ILLNESS -> history_of_presenting_illness + drug_history
- GENERAL_HISTORY -> past_medical_history
- HISTORY -> family_history
- GENERAL_EXAMINATION -> general_examination
- SYSTEMIC_EXAMINATION -> systemic_examination
- DIAGNOSIS -> diagnosis (string)
- INVESTIGATIONS -> investigations_list + suggested_packages (nephro packages)
- BLOOD_GROUP -> blood_profile (blood group, Rh, transfusion history)
- TREATMENT_PLAN -> treatment_and_future_plan, consultants_referral, review_on
- PRESCRIPTION -> prescription

Reuses kg_service.send_to_kg() for the HTTP POST since the KG endpoint is
shared between cardio and nephro forms (differs only in payload form_type).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# The 16 fixed nephro checklist keys on the KG form (matches COMORBIDITIES_NEPHRO schema)
NEPHRO_COMORBIDITY_KEYS = (
    "dm", "bp", "smoking",
    "hematuria", "stones", "frequency", "nocturia", "straining",
    "dyspnoea", "edema", "cough", "fever",
    "skin_rash", "pruritus", "nausea", "vomiting",
)

# Keys that carry a `since` field on the form (all except the habit)
NEPHRO_COMORBIDITIES_WITH_SINCE = set(NEPHRO_COMORBIDITY_KEYS) - {"smoking"}


# Nephro investigation package checkboxes. Matched against INVESTIGATIONS[].name
# (case-insensitive substring). Used to produce `suggested_packages` booleans
# alongside the raw investigations_list.
NEPHRO_PACKAGE_KEYWORDS: Dict[str, List[str]] = {
    "nephro_op_package": ["nephro op package", "nephro package"],
    "virus_package": ["virus package"],
    "transplant_package": ["transplant package"],
    "haemodialysis_package": ["haemodialysis package", "hemodialysis package"],
    "capd_package": ["capd package", "capd"],
    "usg_post_void_residual": ["usg with post void", "post void residual",
                               "post-void residual", "pvr"],
}


# ── Helpers ────────────────────────────────────────────────────────────

def _to_str(v: Any) -> str:
    """Coerce a leaf value to string; drift-guard returns '' for dict/list."""
    if v is None or isinstance(v, (dict, list)):
        return ""
    return str(v).strip()


def _yes_no(v: Any) -> str:
    if v is None:
        return "No"
    s = str(v).strip().lower()
    if s in ("yes", "y", "true", "1", "present", "positive"):
        return "Yes"
    return "No"


def _normalize_comorbidities(comorbidities: Any) -> Dict[str, Dict[str, str]]:
    """Ensure all 16 nephro checkbox keys are present with consistent defaults.

    Each key resolves to {"status": "No"|"Yes"|"", "since": "<text>"} where
    keys without a `since` field on the form (smoking) omit it.
    """
    if not isinstance(comorbidities, dict):
        comorbidities = {}
    out: Dict[str, Dict[str, str]] = {}
    for key in NEPHRO_COMORBIDITY_KEYS:
        entry = comorbidities.get(key, {})
        if not isinstance(entry, dict):
            entry = {}
        status = entry.get("status") or ""
        if key in NEPHRO_COMORBIDITIES_WITH_SINCE:
            out[key] = {"status": status, "since": entry.get("since") or ""}
        else:
            out[key] = {"status": status}
    return out


def _suggested_packages(investigations: Any) -> Dict[str, bool]:
    """Scan investigations[].name for nephro-package keyword hits."""
    result = {k: False for k in NEPHRO_PACKAGE_KEYWORDS}
    result["others"] = ""
    if not isinstance(investigations, list):
        return result

    others_parts: List[str] = []
    for item in investigations:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").lower().strip()
        if not name:
            continue
        matched = False
        for pkg, keywords in NEPHRO_PACKAGE_KEYWORDS.items():
            if any(kw in name for kw in keywords):
                result[pkg] = True
                matched = True
                break
        if not matched:
            # Preserve non-package investigations as free-text "others"
            others_parts.append(str(item.get("name", "")))
    result["others"] = ", ".join(others_parts) if others_parts else ""
    return result


def _format_diagnosis(diagnosis: Any) -> str:
    """
    Format DIAGNOSIS into a readable string for the KG nephro EHR payload.

    Tolerates two schemas:
      - List form (legacy AI output): [{name, code, type}, ...]
      - Object form (doctor-edit iframes / new schema):
        {primary_diagnosis: "...", interim_diagnosis: [...],
         secondary_diagnoses: [...], differential_diagnoses: [...]}
        → primary text first, then any named diagnoses, joined by "; ".
    """
    if not diagnosis:
        return ""

    # List form (legacy)
    if isinstance(diagnosis, list):
        parts: List[str] = []
        for d in diagnosis:
            if isinstance(d, dict):
                name = (d.get("name") or "").strip()
                code = (d.get("code") or "").strip()
                dtype = (d.get("type") or "").strip()
                if name:
                    bits = [name]
                    if code:
                        bits.append(f"({code})")
                    if dtype:
                        bits.append(f"[{dtype}]")
                    parts.append(" ".join(bits))
            elif isinstance(d, str) and d.strip():
                parts.append(d.strip())
        return "; ".join(parts)

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
                        name = (d.get("name") or "").strip()
                        code = (d.get("code") or "").strip()
                        if name:
                            parts.append(f"{name} ({code})" if code else name)
                    elif isinstance(d, str) and d.strip():
                        parts.append(d.strip())
        return "; ".join(p for p in parts if p)

    return ""


def _build_investigations_list(investigations: Any) -> List[Dict[str, str]]:
    """
    Tolerates schema drift: list (canonical), dict (concatenates list values),
    string (single item), or anything else (empty list).
    """
    if isinstance(investigations, dict):
        flat: List[Any] = []
        for v in investigations.values():
            if isinstance(v, list):
                flat.extend(v)
        investigations = flat
    elif isinstance(investigations, str) and investigations.strip():
        investigations = [{"name": investigations.strip()}]
    elif not isinstance(investigations, list):
        return []
    out: List[Dict[str, str]] = []
    for item in investigations:
        if isinstance(item, dict):
            out.append({
                "name": _to_str(item.get("name")),
                "type": _to_str(item.get("type")),
                "date": _to_str(item.get("date")),
            })
        elif isinstance(item, str):
            out.append({"name": item.strip(), "type": "", "date": ""})
    return out


def _format_blood_profile(blood: Any) -> Dict[str, str]:
    """Flatten BLOOD_GROUP segment to KG payload shape."""
    if not isinstance(blood, dict):
        blood = {}
    txn = blood.get("transfusion_history") or {}
    if not isinstance(txn, dict):
        txn = {}
    return {
        "blood_group": _to_str(blood.get("blood_group")),
        "rh": _to_str(blood.get("rh")),
        "transfusion_received": _to_str(txn.get("received")),
        "transfusion_details": _to_str(txn.get("details")),
    }


# ── Main formatter ─────────────────────────────────────────────────────

def format_for_kg_nephro(
    extraction_data: Dict[str, Any],
    patient_id: str = "",
    doctor_id: str = "",
    extraction_id: str = "",
    doctor_name: str = "",
    uhid: str = "",
    visit_id: str = "",
    role: str = "",
) -> Dict[str, Any]:
    """Format NEPHRO_INITIAL extraction into KG Hospital Nephrology payload.

    Mirrors the cardio payload layout so downstream KG consumers can share
    infra — differences are in `form_type`, the nephro comorbidity checklist,
    the nephro investigation packages, and the new `blood_profile` block.
    """
    if not isinstance(extraction_data, dict):
        extraction_data = {}

    vitals = extraction_data.get("vitals") or {}
    nutritional = extraction_data.get("nutritionalScreening") or {}
    # Primary nephro comorbidity segment; fall back to generic in case the
    # template is reconfigured later.
    comorbidities = (
        extraction_data.get("comorbiditiesNephro")
        or extraction_data.get("comorbidities")
        or {}
    )
    allergy = extraction_data.get("allergy") or {}
    chief_complaints = extraction_data.get("chiefComplaints") or ""
    hpi = extraction_data.get("historyOfPresentIllness") or {}
    general_history = extraction_data.get("generalHistory") or {}
    family = extraction_data.get("history") or {}
    gen_exam = extraction_data.get("generalExamination") or {}
    sys_exam = extraction_data.get("systemicExamination") or {}
    diagnosis_arr = extraction_data.get("diagnosis") or []
    investigations_arr = extraction_data.get("investigations") or []
    prescription_arr = extraction_data.get("prescription") or []
    treatment = extraction_data.get("treatmentPlan") or {}
    blood_group_seg = extraction_data.get("bloodGroup") or {}

    # Defensive dict coercions
    for var_name in ("vitals", "nutritional", "allergy", "hpi", "general_history",
                     "family", "gen_exam", "sys_exam", "treatment", "blood_group_seg"):
        if not isinstance(locals()[var_name], dict):
            locals()[var_name] = {}
    if isinstance(chief_complaints, list):
        chief_complaints = ", ".join(str(c) for c in chief_complaints if c)

    now = datetime.utcnow()
    review_date = treatment.get("review_on", "") or ""

    payload: Dict[str, Any] = {
        # Metadata
        "patient_id": patient_id,
        "uhid": uhid,
        "visit_id": visit_id,
        "doctor_id": doctor_id,
        "extraction_id": extraction_id,
        "role": role,
        "form_type": "NEPHROLOGY_INITIAL_ASSESSMENT",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),

        # 1. Vitals
        "vitals": {
            "temperature": _to_str(vitals.get("temperature")),
            "pulse": _to_str(vitals.get("pulse")),
            "respiratory_rate": _to_str(vitals.get("respiratory_rate")),
            "blood_pressure": _to_str(vitals.get("blood_pressure")),
            "spo2": _to_str(vitals.get("spo2")),
            "date_time": now.strftime("%Y-%m-%d %H:%M"),
        },

        # 2. Nutritional screening
        "nutritional_screening": {
            "height": _to_str(nutritional.get("height")),
            "weight": _to_str(nutritional.get("weight")),
            "bmi": _to_str(nutritional.get("bmi")),
            "bmi_flag": nutritional.get("bmi_flag", "") or "",
        },

        # 3. Nephro comorbidities / complaints checklist (16 items)
        "comorbidities": _normalize_comorbidities(comorbidities),

        # 4. Drug allergy
        "drug_allergy": {
            "has_allergy": allergy.get("has_allergy", "No") or "No",
            "details": _to_str(allergy.get("details")),
        },

        # 5. Present complaints (narrative)
        "present_complaints": chief_complaints if isinstance(chief_complaints, str) else "",

        # 6. History of presenting illness
        "history_of_presenting_illness": _to_str(hpi.get("history_of_presenting_illness")),

        # 7. Past medical history
        "past_medical_history": _to_str(general_history.get("past_medical_history")),

        # 8. Family history
        "family_history": _to_str(family.get("family_history")),

        # 9. Drug history
        "drug_history": _to_str(hpi.get("drug_history")),

        # 10. General examination (5 body-area keys)
        "general_examination": gen_exam,

        # 11. Systemic examination (5 system keys)
        "systemic_examination": sys_exam,

        # 12. Diagnosis — string joined from array
        "diagnosis": _format_diagnosis(diagnosis_arr),

        # 13a. Investigations raw list (preserved for reference)
        "investigations_list": _build_investigations_list(investigations_arr),

        # 13b. Nephro-specific package checkboxes
        "suggested_packages": _suggested_packages(investigations_arr),

        # 14. Blood profile (group, Rh, transfusion history)
        "blood_profile": _format_blood_profile(blood_group_seg),

        # 15. Treatment and future plan
        "treatment_and_future_plan": _to_str(treatment.get("treatment_and_future_plan")),

        # 16. Consultants referral
        "consultants_referral": _to_str(treatment.get("consultants_referral")),

        # 17. Prescription — pass through the normalized list
        "prescription": prescription_arr if isinstance(prescription_arr, list) else [],

        # Trailing metadata
        "doctor_name": doctor_name,
        "time": now.strftime("%H:%M"),
        "review_on": review_date,
    }

    comorbidity_hits = sum(
        1 for v in payload["comorbidities"].values()
        if isinstance(v, dict) and v.get("status") == "Yes"
    )
    logger.info(
        f"[KG_NEPHRO] Formatted payload: extraction={extraction_id}, "
        f"vitals={bool(payload['vitals'].get('blood_pressure'))}, "
        f"comorbidity_hits={comorbidity_hits}/16, "
        f"complaints={bool(payload['present_complaints'])}, "
        f"diagnosis={bool(payload['diagnosis'])}, "
        f"prescription_count={len(payload['prescription'])}, "
        f"blood_group={payload['blood_profile'].get('blood_group') or '-'}"
    )
    return payload


# ── Reassess formatter ─────────────────────────────────────────────────

def format_for_kg_nephro_reassess(
    extraction_data: Dict[str, Any],
    patient_id: str = "",
    doctor_id: str = "",
    extraction_id: str = "",
    doctor_name: str = "",
    uhid: str = "",
    visit_id: str = "",
    role: str = "",
) -> Dict[str, Any]:
    """Format NEPHRO_REASSESS extraction into KG Hospital Nephrology
    Re-Assessment payload.

    The reassess template is intentionally narrow — only 4 segments wired
    on the template (DIAGNOSIS, TREATMENT_PLAN, INVESTIGATIONS, and the
    catch-all SIGNS_AND_SYMPTOMS narrative). Mirrors the nephro_initial
    payload shape where keys overlap so downstream KG consumers can share
    parsing — the differences are: `form_type`, no comorbidity checklist /
    no blood_profile / no per-section vitals/exam blocks (those collapse
    into the `present_complaints` narrative), and no prescription block.
    """
    if not isinstance(extraction_data, dict):
        extraction_data = {}

    # SIGNS_AND_SYMPTOMS replaces CHIEF_COMPLAINTS as the catch-all narrative.
    # Fall back to chiefComplaints for back-compat with prior NEPHRO_REASSESS
    # extractions that used the old segment.
    signs_and_symptoms = (
        extraction_data.get("signsAndSymptoms")
        or extraction_data.get("chiefComplaints")
        or ""
    )
    if isinstance(signs_and_symptoms, list):
        signs_and_symptoms = ", ".join(str(s) for s in signs_and_symptoms if s)
    elif not isinstance(signs_and_symptoms, str):
        signs_and_symptoms = ""

    diagnosis_arr = extraction_data.get("diagnosis") or []
    investigations_arr = extraction_data.get("investigations") or []
    treatment = extraction_data.get("treatmentPlan") or {}
    if not isinstance(treatment, dict):
        treatment = {}

    now = datetime.utcnow()
    review_date = treatment.get("review_on", "") or ""

    payload: Dict[str, Any] = {
        # Metadata — mirrors nephro_initial
        "patient_id": patient_id,
        "uhid": uhid,
        "visit_id": visit_id,
        "doctor_id": doctor_id,
        "extraction_id": extraction_id,
        "role": role,
        "form_type": "NEPHROLOGY_REASSESSMENT",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),

        # 1. Present condition / signs and symptoms — single narrative covering
        # symptoms + vitals + exam + history + comorbidities + allergies +
        # drug history + recent labs (catch-all on the reassess template).
        "present_complaints": signs_and_symptoms,

        # 2. Diagnosis — string joined from array (same shape as initial)
        "diagnosis": _format_diagnosis(diagnosis_arr),

        # 3a. Investigations raw list (preserved for reference)
        "investigations_list": _build_investigations_list(investigations_arr),

        # 3b. Nephro-specific package checkboxes
        "suggested_packages": _suggested_packages(investigations_arr),

        # 4. Treatment / plan
        "treatment_and_future_plan": _to_str(treatment.get("treatment_and_future_plan")),
        "consultants_referral": _to_str(treatment.get("consultants_referral")),

        # Trailing metadata — mirrors nephro_initial
        "doctor_name": doctor_name,
        "time": now.strftime("%H:%M"),
        "review_on": review_date,
    }

    logger.info(
        f"[KG_NEPHRO_REASSESS] Formatted payload: extraction={extraction_id}, "
        f"signs_and_symptoms={bool(payload['present_complaints'])}, "
        f"diagnosis={bool(payload['diagnosis'])}, "
        f"investigations_count={len(payload['investigations_list'])}, "
        f"treatment={bool(payload['treatment_and_future_plan'])}, "
        f"review_on={bool(review_date)}, role={role!r}"
    )
    return payload


# ── HTTP sender ────────────────────────────────────────────────────────

async def send_to_kg_nephro(
    payload: Dict[str, Any],
    api_url: str,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Thin wrapper over kg_service.send_to_kg — KG endpoint is shared across
    forms; only the payload.form_type differs."""
    from services.kg_service import send_to_kg
    return await send_to_kg(payload=payload, api_url=api_url, api_key=api_key)

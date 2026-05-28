"""
Raster API Lookup Tables

This file contains all the lookup mappings required by Raster API for neonatal templates.
These mappings convert extracted text values to the integer IDs or specific string values
expected by the Raster database.

Used by: NEO_DAILY, NEO_OP, NEO_PROFORMA, NEO_DISCHARGE, NEO_ADMISSION templates
"""

from typing import Dict, List, Optional, Any, Union


# ============================================================================
# RESPIRATORY INDICATION MAPPINGS (array of integers)
# Used in: NEO_DAILY dailyLog.respiratory.indication
# ============================================================================

RESPIRATORY_INDICATION_MAP: Dict[str, int] = {
    # Exact matches (case-insensitive matching should be used)
    "others": 1,
    "other": 1,
    "pneumonia": 2,
    "mas": 3,
    "meconium aspiration syndrome": 3,
    "meconium aspiration": 3,
    "pphn": 4,
    "persistent pulmonary hypertension": 4,
    "pulmonary hypertension": 4,
    "apnea": 5,
    "apnoea": 5,
    "hie": 6,
    "hypoxic ischemic encephalopathy": 6,
    "hypoxic-ischemic encephalopathy": 6,
    "cdh": 7,
    "congenital diaphragmatic hernia": 7,
    "diaphragmatic hernia": 7,
    "cardiac": 8,
    "heart": 8,
    "post operative": 9,
    "post-operative": 9,
    "postoperative": 9,
    "post op": 9,
    "airleak": 10,
    "air leak": 10,
    "pneumothorax": 10,
    "pleural effusion": 11,
    "test": 12,
    "chylothorax": 13,
    "ttn": 14,
    "transient tachypnea": 14,
    "transient tachypnea of newborn": 14,
    "preterm rds": 15,
    "rds": 15,
    "respiratory distress syndrome": 15,
    "seizures": 16,
    "seizure": 16,
    "convulsions": 16,
    "term rds": 17,
    "sepsis": 18,
    "infection": 18,
    "pooling of oral secretions": 19,
    "delayed promoter clearance": 19,
    "oral secretions": 19,
    "head injury": 20,
    "bronchiolitis": 21,
    "acute pulmonary haemorrhage": 22,
    "acute pulmonary hemorrhage": 22,
    "pulmonary haemorrhage": 22,
    "pulmonary hemorrhage": 22,
    "acute surgical abdomen": 23,
    "surgical abdomen": 23,
    "nec": 24,
    "necrotizing enterocolitis": 24,
    "necrotising enterocolitis": 24,
}

# Reverse mapping for ID to name (for logging/debugging)
RESPIRATORY_INDICATION_NAMES: Dict[int, str] = {
    1: "Others",
    2: "Pneumonia",
    3: "MAS",
    4: "PPHN",
    5: "Apnea",
    6: "HIE",
    7: "CDH",
    8: "Cardiac",
    9: "Post Operative",
    10: "Airleak",
    11: "Pleural Effusion",
    12: "test",
    13: "Chylothorax",
    14: "TTN",
    15: "Preterm RDS",
    16: "Seizures",
    17: "Term RDS",
    18: "Sepsis",
    19: "Pooling of oral secretions/delayed promoter clearance",
    20: "Head Injury",
    21: "Bronchiolitis",
    22: "Acute Pulmonary Haemorrhage",
    23: "Acute Surgical abdomen",
    24: "NEC",
}


# ============================================================================
# INVASIVE VENTILATION (String enum)
# Used in: NEO_DAILY dailyLog.respiratory.invasiveVentilation
# ============================================================================

INVASIVE_VENTILATION_VALUES = ["Yes", "No", "N/A"]

def normalize_invasive_ventilation(value: Any) -> str:
    """Normalize invasive ventilation value to Raster expected format."""
    if value is None:
        return "N/A"
    val_str = str(value).strip().lower()
    if val_str in ["yes", "true", "1", "y"]:
        return "Yes"
    elif val_str in ["no", "false", "0", "n"]:
        return "No"
    return "N/A"


# ============================================================================
# VENTILATION TYPE (String enum)
# Used in: NEO_DAILY dailyLog.respiratory.ventilationType
# ============================================================================

VENTILATION_TYPE_MAP: Dict[str, str] = {
    "non-invasive": "NonInvasiveVentilation",
    "non invasive": "NonInvasiveVentilation",
    "noninvasive": "NonInvasiveVentilation",
    "niv": "NonInvasiveVentilation",
    "other respiratory support": "OtherRespiratorySupport",
    "other respiratory": "OtherRespiratorySupport",
    "other": "OtherRespiratorySupport",
    "spontaneous": "SpontaneouslyVentilating",
    "spontaneously ventilating": "SpontaneouslyVentilating",
    "room air": "SpontaneouslyVentilating",
    "self": "SpontaneouslyVentilating",
}

VENTILATION_TYPE_VALUES = ["NonInvasiveVentilation", "OtherRespiratorySupport", "SpontaneouslyVentilating", "N/A"]

def normalize_ventilation_type(value: Any) -> str:
    """Normalize ventilation type to Raster expected format."""
    if value is None:
        return "N/A"
    val_str = str(value).strip().lower()
    # Check direct mapping
    if val_str in VENTILATION_TYPE_MAP:
        return VENTILATION_TYPE_MAP[val_str]
    # Check if already a valid value
    for valid in VENTILATION_TYPE_VALUES:
        if val_str == valid.lower():
            return valid
    return "N/A"


# ============================================================================
# NON-INVASIVE VENTILATION MODE (String enum)
# Used in: NEO_DAILY dailyLog.respiratory.nonInvasiveVentilationMode
# ============================================================================

NON_INVASIVE_VENTILATION_MODE_MAP: Dict[str, str] = {
    "cpap": "CPAP",
    "continuous positive airway pressure": "CPAP",
    "nimv": "NIMV",
    "nasal intermittent mandatory ventilation": "NIMV",
    "hhhfnc": "HHHFNC",
    "high humidity high flow nasal cannula": "HHHFNC",
    "high flow": "HHHFNC",
    "hfnc": "HHHFNC",
    "nhfov": "nHFOV",
    "nasal high frequency oscillatory ventilation": "nHFOV",
    "high frequency": "nHFOV",
}

NON_INVASIVE_VENTILATION_MODE_VALUES = ["CPAP", "NIMV", "HHHFNC", "nHFOV", "N/A"]

def normalize_niv_mode(value: Any) -> str:
    """Normalize non-invasive ventilation mode to Raster expected format."""
    if value is None:
        return "N/A"
    val_str = str(value).strip().lower()
    if val_str in NON_INVASIVE_VENTILATION_MODE_MAP:
        return NON_INVASIVE_VENTILATION_MODE_MAP[val_str]
    for valid in NON_INVASIVE_VENTILATION_MODE_VALUES:
        if val_str == valid.lower():
            return valid
    return "N/A"


# ============================================================================
# OTHER RESPIRATORY SUPPORT (String enum)
# Used in: NEO_DAILY dailyLog.respiratory.otherRespiratorySupport
# ============================================================================

OTHER_RESPIRATORY_SUPPORT_MAP: Dict[str, str] = {
    "npo2": "NPO2",
    "nasal prong o2": "NPO2",
    "nasal prong": "NPO2",
    "nasal oxygen": "NPO2",
    "hbo2": "HBO2",
    "hood box o2": "HBO2",
    "hood box": "HBO2",
    "hood oxygen": "HBO2",
    "face": "Face",
    "face mask": "Face",
    "facemask": "Face",
    "oxygen mask": "Face",
}

OTHER_RESPIRATORY_SUPPORT_VALUES = ["NPO2", "HBO2", "Face", "N/A"]

def normalize_other_respiratory_support(value: Any) -> str:
    """Normalize other respiratory support to Raster expected format."""
    if value is None:
        return "N/A"
    val_str = str(value).strip().lower()
    if val_str in OTHER_RESPIRATORY_SUPPORT_MAP:
        return OTHER_RESPIRATORY_SUPPORT_MAP[val_str]
    for valid in OTHER_RESPIRATORY_SUPPORT_VALUES:
        if val_str == valid.lower():
            return valid
    return "N/A"


# ============================================================================
# SURFACTANT THERAPY (String enum)
# Used in: NEO_DAILY dailyLog.respiratory.surfactantTherapy
# ============================================================================

SURFACTANT_THERAPY_VALUES = ["Yes", "No", "N/A"]

def normalize_surfactant_therapy(value: Any) -> str:
    """Normalize surfactant therapy value to Raster expected format."""
    if value is None:
        return "N/A"
    val_str = str(value).strip().lower()
    if val_str in ["yes", "true", "1", "y", "given"]:
        return "Yes"
    elif val_str in ["no", "false", "0", "n", "not given"]:
        return "No"
    return "N/A"


# ============================================================================
# RETRACTIONS (String enum)
# Used in: NEO_DAILY dailyLog.respiratory.retractions
# ============================================================================

RETRACTIONS_MAP: Dict[str, str] = {
    "no": "No",
    "none": "No",
    "absent": "No",
    "mild": "Mild",
    "slight": "Mild",
    "minimal": "Mild",
    "moderate": "Moderate",
    "significant": "Moderate",
    "severe": "Severe",
    "marked": "Severe",
    "prominent": "Severe",
}

RETRACTIONS_VALUES = ["No", "Mild", "Moderate", "Severe"]

def normalize_retractions(value: Any) -> str:
    """Normalize retractions value to Raster expected format."""
    if value is None:
        return "No"
    val_str = str(value).strip().lower()
    if val_str in RETRACTIONS_MAP:
        return RETRACTIONS_MAP[val_str]
    for valid in RETRACTIONS_VALUES:
        if val_str == valid.lower():
            return valid
    return "No"


# ============================================================================
# AIR ENTRY (String enum)
# Used in: NEO_DAILY dailyLog.respiratory.airEntry
# ============================================================================

AIR_ENTRY_MAP: Dict[str, str] = {
    "equal": "Equal",
    "normal": "Equal",
    "bilateral equal": "Equal",
    "good": "Equal",
    "reduced bilateral": "Reduced Bilateral",
    "bilateral reduced": "Reduced Bilateral",
    "reduced both sides": "Reduced Bilateral",
    "reduced rt": "Reduced Rt",
    "reduced right": "Reduced Rt",
    "right reduced": "Reduced Rt",
    "reduced lt": "Reduced Lt",
    "reduced left": "Reduced Lt",
    "left reduced": "Reduced Lt",
}

AIR_ENTRY_VALUES = ["Equal", "Reduced Bilateral", "Reduced Rt", "Reduced Lt"]

def normalize_air_entry(value: Any) -> str:
    """Normalize air entry value to Raster expected format."""
    if value is None:
        return "Equal"
    val_str = str(value).strip().lower()
    if val_str in AIR_ENTRY_MAP:
        return AIR_ENTRY_MAP[val_str]
    for valid in AIR_ENTRY_VALUES:
        if val_str == valid.lower():
            return valid
    return "Equal"


# ============================================================================
# CHEST MOVEMENTS (String enum)
# Used in: NEO_DAILY dailyLog.respiratory.chestMovements
# ============================================================================

CHEST_MOVEMENTS_MAP: Dict[str, str] = {
    "symmetrical": "Symmetrical",
    "symmetric": "Symmetrical",
    "equal": "Symmetrical",
    "normal": "Symmetrical",
    "asymmetrical": "Asymmetrical",
    "asymmetric": "Asymmetrical",
    "unequal": "Asymmetrical",
}

CHEST_MOVEMENTS_VALUES = ["Symmetrical", "Asymmetrical", "N/A"]

def normalize_chest_movements(value: Any) -> str:
    """Normalize chest movements value to Raster expected format."""
    if value is None:
        return "N/A"
    val_str = str(value).strip().lower()
    if val_str in CHEST_MOVEMENTS_MAP:
        return CHEST_MOVEMENTS_MAP[val_str]
    for valid in CHEST_MOVEMENTS_VALUES:
        if val_str == valid.lower():
            return valid
    return "N/A"


# ============================================================================
# ADDED SOUNDS (String enum)
# Used in: NEO_DAILY dailyLog.respiratory.addedSounds
# ============================================================================

ADDED_SOUNDS_MAP: Dict[str, str] = {
    "present": "Present",
    "yes": "Present",
    "heard": "Present",
    "crepitations": "Present",
    "wheeze": "Present",
    "rhonchi": "Present",
    "absent": "Absent",
    "no": "Absent",
    "none": "Absent",
    "clear": "Absent",
}

ADDED_SOUNDS_VALUES = ["Present", "Absent"]

def normalize_added_sounds(value: Any) -> str:
    """Normalize added sounds value to Raster expected format."""
    if value is None:
        return "Absent"
    val_str = str(value).strip().lower()
    if val_str in ADDED_SOUNDS_MAP:
        return ADDED_SOUNDS_MAP[val_str]
    for valid in ADDED_SOUNDS_VALUES:
        if val_str == valid.lower():
            return valid
    return "Absent"


# ============================================================================
# BLOOD GAS TYPE (String enum)
# Used in: NEO_DAILY dailyLog.respiratory.bloodGas.bloodGasType
# ============================================================================

BLOOD_GAS_TYPE_MAP: Dict[str, str] = {
    "not done": "Not done",
    "none": "Not done",
    "no": "Not done",
    "arterial": "Arterial",
    "abg": "Arterial",
    "venous": "Venous",
    "vbg": "Venous",
    "capillary": "Capillary",
    "cbg": "Capillary",
    "not indicated": "Not indicated",
}

BLOOD_GAS_TYPE_VALUES = ["Not done", "Arterial", "Venous", "Capillary", "Not indicated", "N/A"]

def normalize_blood_gas_type(value: Any) -> str:
    """Normalize blood gas type to Raster expected format."""
    if value is None:
        return "N/A"
    val_str = str(value).strip().lower()
    if val_str in BLOOD_GAS_TYPE_MAP:
        return BLOOD_GAS_TYPE_MAP[val_str]
    for valid in BLOOD_GAS_TYPE_VALUES:
        if val_str == valid.lower():
            return valid
    return "N/A"


# ============================================================================
# ET TUBE (String enum)
# Used in: NEO_DAILY dailyLog.respiratory.etTube
# ============================================================================

ET_TUBE_VALUES = ["Yes", "No", "N/A"]

def normalize_et_tube(value: Any) -> str:
    """Normalize ET tube value to Raster expected format."""
    if value is None:
        return "N/A"
    val_str = str(value).strip().lower()
    if val_str in ["yes", "true", "1", "y", "in situ", "present"]:
        return "Yes"
    elif val_str in ["no", "false", "0", "n", "removed", "absent"]:
        return "No"
    return "N/A"


# ============================================================================
# SPONTANEOUSLY VENTILATING (String enum)
# Used in: NEO_DAILY
# ============================================================================

SPONTANEOUSLY_VENTILATING_VALUES = ["Yes", "No", "N/A"]

def normalize_spontaneously_ventilating(value: Any) -> str:
    """Normalize spontaneously ventilating value to Raster expected format."""
    if value is None:
        return "N/A"
    val_str = str(value).strip().lower()
    if val_str in ["yes", "true", "1", "y"]:
        return "Yes"
    elif val_str in ["no", "false", "0", "n"]:
        return "No"
    return "N/A"


# ============================================================================
# BOOLEAN FIELDS WITH DEFAULT FALSE
# Used in: volume_targeting, calco, chronicLungDisease, etc.
# ============================================================================

def normalize_boolean_default_false(value: Any) -> bool:
    """Normalize boolean value with default false."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    val_str = str(value).strip().lower()
    return val_str in ["yes", "true", "1", "y"]


# ============================================================================
# HELPER FUNCTIONS FOR RESPIRATORY INDICATION CONVERSION
# ============================================================================

def convert_respiratory_indications_to_ids(indications: Union[List[str], str, None]) -> List[int]:
    """
    Convert respiratory indication text values to Raster integer IDs.

    Args:
        indications: List of indication strings, single string, or None

    Returns:
        List of integer IDs for Raster API
    """
    if indications is None:
        return []

    # Convert single string to list
    if isinstance(indications, str):
        # Split by comma if multiple values
        indications = [ind.strip() for ind in indications.split(",") if ind.strip()]

    ids = []
    for indication in indications:
        if isinstance(indication, int):
            # Already an ID
            if 1 <= indication <= 24:
                ids.append(indication)
        elif isinstance(indication, str):
            indication_lower = indication.strip().lower()
            if indication_lower in RESPIRATORY_INDICATION_MAP:
                ids.append(RESPIRATORY_INDICATION_MAP[indication_lower])
            elif indication_lower.isdigit():
                # It's a string number
                id_val = int(indication_lower)
                if 1 <= id_val <= 24:
                    ids.append(id_val)

    return ids


def get_respiratory_indication_name(indication_id: int) -> str:
    """Get the name for a respiratory indication ID."""
    return RESPIRATORY_INDICATION_NAMES.get(indication_id, f"Unknown ({indication_id})")


# ============================================================================
# NEO_OP SPECIFIC LOOKUPS
# ============================================================================

# Follow-up outcome values
# Reference: Sent Home, Admitted, Discharge Against Medical Advice, Awaiting results
FOLLOWUP_OUTCOME_MAP: Dict[str, str] = {
    "sent home": "Sent Home",
    "home": "Sent Home",
    "discharged": "Sent Home",
    "admitted": "Admitted",
    "admission": "Admitted",
    "discharge against medical advice": "Discharge Against Medical Advice",
    "dama": "Discharge Against Medical Advice",
    "lama": "Discharge Against Medical Advice",
    "left against medical advice": "Discharge Against Medical Advice",
    "awaiting results": "Awaiting results",
    "waiting": "Awaiting results",
    "pending results": "Awaiting results",
    "referred": "Referred",
    "referral": "Referred",
    "transfer": "Referred",
    "death": "Death",
    "died": "Death",
    "expired": "Death",
}

def normalize_followup_outcome(value: Any) -> str:
    """Normalize follow-up outcome to Raster expected format."""
    if value is None:
        return "Sent Home"
    val_str = str(value).strip().lower()
    if val_str in FOLLOWUP_OUTCOME_MAP:
        return FOLLOWUP_OUTCOME_MAP[val_str]
    return "Sent Home"


# Immunization status values
# Reference: Due, Given, Complete
IMMUNIZATION_STATUS_MAP: Dict[str, str] = {
    "due": "Due",
    "pending": "Due",
    "scheduled": "Due",
    "not given": "Due",
    "no": "Due",
    "given": "Given",
    "yes": "Given",
    "done": "Given",
    "complete": "Complete",
    "completed": "Complete",
    "all done": "Complete",
}

def normalize_immunization_status(value: Any) -> str:
    """Normalize immunization status to Raster expected format."""
    if value is None:
        return "Due"
    val_str = str(value).strip().lower()
    if val_str in IMMUNIZATION_STATUS_MAP:
        return IMMUNIZATION_STATUS_MAP[val_str]
    return "Due"


# ============================================================================
# MEDICATION ROUTE MAPPINGS
# Used in: NEO_OP medications[].route
# ============================================================================

MEDICATION_ROUTE_MAP: Dict[str, str] = {
    "oral": "1",
    "po": "1",
    "by mouth": "1",
    "inhalation": "2",
    "inhaled": "2",
    "nebulizer": "2",
    "nebulized": "2",
    "iv": "3",
    "intravenous": "3",
    "im": "4",
    "intramuscular": "4",
    "sc": "5",
    "subcutaneous": "5",
    "topical": "6",
    "rectal": "7",
    "pr": "7",
    "sublingual": "8",
    "sl": "8",
    "nasal": "9",
    "intranasal": "9",
}

def normalize_medication_route(value: Any) -> str:
    """Normalize medication route to Raster expected format (string ID)."""
    if value is None:
        return "1"  # Default to oral
    val_str = str(value).strip().lower()
    if val_str in MEDICATION_ROUTE_MAP:
        return MEDICATION_ROUTE_MAP[val_str]
    # Check if already a valid numeric string
    if val_str.isdigit() and 1 <= int(val_str) <= 10:
        return val_str
    return "1"  # Default to oral


# ============================================================================
# NEO_OP DEMOGRAPHIC & APPOINTMENT LOOKUPS (from reference doc)
# ============================================================================

TITLE_MAP: Dict[str, str] = {
    "ms.": "Ms.",
    "ms": "Ms.",
    "mrs.": "Mrs.",
    "mrs": "Mrs.",
    "miss.": "Miss.",
    "miss": "Miss.",
    "mr.": "Mr.",
    "mr": "Mr.",
    "dr.": "Dr.",
    "dr": "Dr.",
    "doctor": "Dr.",
}

def normalize_title(value: Any) -> str:
    """Normalize title to Raster expected format."""
    if value is None:
        return ""
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in TITLE_MAP:
        return TITLE_MAP[val_lower]
    return val_str

EDUCATION_MAP: Dict[str, str] = {
    "uneducated": "Uneducated",
    "none": "Uneducated",
    "primary school": "Primary School",
    "primary": "Primary School",
    "secondary school": "Secondary school",
    "secondary": "Secondary school",
    "high school": "Secondary school",
    "graduate": "Graduate",
    "degree": "Graduate",
    "postgraduate": "Postgraduate",
    "post graduate": "Postgraduate",
    "pg": "Postgraduate",
    "masters": "Postgraduate",
}

def normalize_education(value: Any) -> str:
    """Normalize education to Raster expected format."""
    if value is None:
        return ""
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in EDUCATION_MAP:
        return EDUCATION_MAP[val_lower]
    return val_str

OCCUPATION_STATUS_MAP: Dict[str, str] = {
    "currently employed": "Currently employed",
    "employed": "Currently employed",
    "working": "Currently employed",
    "previously employed but currently not employed": "Previously employed but currently not employed",
    "previously employed": "Previously employed but currently not employed",
    "unemployed": "Previously employed but currently not employed",
    "never employed": "Never employed",
    "homemaker": "Never employed",
    "housewife": "Never employed",
}

def normalize_occupation_status(value: Any) -> str:
    """Normalize occupation status to Raster expected format."""
    if value is None:
        return ""
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in OCCUPATION_STATUS_MAP:
        return OCCUPATION_STATUS_MAP[val_lower]
    return val_str

APPOINTMENT_TYPE_MAP: Dict[str, str] = {
    "new appointment": "New Appointment",
    "new": "New Appointment",
    "first visit": "New Appointment",
    "review appointment": "Review Appointment",
    "review": "Review Appointment",
    "follow up": "Review Appointment",
    "follow-up": "Review Appointment",
    "followup": "Review Appointment",
    "emergency appointment": "Emergency Appointment",
    "emergency": "Emergency Appointment",
    "out of appointment": "Out of Appointment",
    "unscheduled": "Out of Appointment",
    "walk-in": "Out of Appointment",
    "walk in": "Out of Appointment",
    "immunization": "Immunization",
    "vaccination": "Immunization",
    "vaccine": "Immunization",
    "weaning appointment": "Weaning Appointment",
    "weaning": "Weaning Appointment",
    "neurodevelopmental screening": "Neurodevelopmental Screening",
    "neuro screening": "Neurodevelopmental Screening",
    "neurodevelopmental assessment": "Neurodevelopmental Assessment",
    "neuro assessment": "Neurodevelopmental Assessment",
    "cardiac appointment": "Cardiac Appointment",
    "cardiac": "Cardiac Appointment",
    "antenatal counseling": "Antenatal Counseling",
    "antenatal": "Antenatal Counseling",
    "bereavement appointment": "Bereavement Appointment",
    "bereavement": "Bereavement Appointment",
    "video consultation": "Video Consultation",
    "video": "Video Consultation",
    "teleconsultation": "Video Consultation",
}

def normalize_appointment_type(value: Any) -> str:
    """Normalize appointment type to Raster expected format."""
    if value is None:
        return "New Appointment"
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in APPOINTMENT_TYPE_MAP:
        return APPOINTMENT_TYPE_MAP[val_lower]
    # Check if already a valid value
    valid_values = {v.lower(): v for v in set(APPOINTMENT_TYPE_MAP.values())}
    if val_lower in valid_values:
        return valid_values[val_lower]
    return val_str

# Neurosonogram / echocardiogram: 2 = performed, 1 = Not performed
NEURO_ECHO_MAP: Dict[str, int] = {
    "performed": 2,
    "done": 2,
    "yes": 2,
    "completed": 2,
    "not performed": 1,
    "not done": 1,
    "no": 1,
    "pending": 1,
}

def normalize_neuro_echo(value: Any) -> Union[int, Any]:
    """Normalize neurosonogram/echocardiogram to integer (2=performed, 1=Not performed)."""
    if value is None:
        return 1
    if isinstance(value, int):
        return value if value in (1, 2) else 1
    val_str = str(value).strip().lower()
    if val_str in NEURO_ECHO_MAP:
        return NEURO_ECHO_MAP[val_str]
    if val_str.isdigit():
        val_int = int(val_str)
        return val_int if val_int in (1, 2) else 1
    return 1


# ============================================================================
# MASTER FUNCTION TO APPLY ALL LOOKUPS TO PAYLOAD
# ============================================================================

def apply_raster_lookups_to_neo_daily(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply all Raster lookup transformations to a NEO_DAILY payload.

    This function normalizes all enum fields to their expected Raster values.
    """
    if "dailyLog" not in payload or not isinstance(payload["dailyLog"], dict):
        return payload

    daily_log = payload["dailyLog"]

    # Resolve seenBy names/IDs via doctor lookup (array for NEO_DAILY)
    if "seenBy" in daily_log:
        from services.doctor_lookups import resolve_seen_by_ids
        seen_by_raw = daily_log.get("seenBy")
        if isinstance(seen_by_raw, list):
            daily_log["seenBy"] = resolve_seen_by_ids(seen_by_raw)

    # Process respiratory section
    if "respiratory" in daily_log and isinstance(daily_log["respiratory"], dict):
        resp = daily_log["respiratory"]

        # Normalize enum fields
        if "invasiveVentilation" in resp:
            resp["invasiveVentilation"] = normalize_invasive_ventilation(resp["invasiveVentilation"])

        if "ventilationType" in resp:
            resp["ventilationType"] = normalize_ventilation_type(resp["ventilationType"])

        if "nonInvasiveVentilationMode" in resp:
            resp["nonInvasiveVentilationMode"] = normalize_niv_mode(resp["nonInvasiveVentilationMode"])

        if "otherRespiratorySupport" in resp:
            resp["otherRespiratorySupport"] = normalize_other_respiratory_support(resp["otherRespiratorySupport"])

        if "spontaneouslyVentilating" in resp:
            resp["spontaneouslyVentilating"] = normalize_spontaneously_ventilating(resp["spontaneouslyVentilating"])

        if "surfactantTherapy" in resp:
            resp["surfactantTherapy"] = normalize_surfactant_therapy(resp["surfactantTherapy"])

        if "retractions" in resp:
            resp["retractions"] = normalize_retractions(resp["retractions"])

        if "airEntry" in resp:
            resp["airEntry"] = normalize_air_entry(resp["airEntry"])

        if "chestMovements" in resp:
            resp["chestMovements"] = normalize_chest_movements(resp["chestMovements"])

        if "addedSounds" in resp:
            resp["addedSounds"] = normalize_added_sounds(resp["addedSounds"])

        if "etTube" in resp:
            resp["etTube"] = normalize_et_tube(resp["etTube"])

        # Convert respiratory indications to IDs
        if "indication" in resp:
            resp["indication"] = convert_respiratory_indications_to_ids(resp["indication"])

        # Normalize boolean fields
        if "volume_targeting" in resp:
            resp["volume_targeting"] = normalize_boolean_default_false(resp["volume_targeting"])

        if "calco" in resp:
            resp["calco"] = normalize_boolean_default_false(resp["calco"])

        if "chronicLungDisease" in resp:
            resp["chronicLungDisease"] = normalize_boolean_default_false(resp["chronicLungDisease"])

        # Process bloodGas nested object
        if "bloodGas" in resp and isinstance(resp["bloodGas"], dict):
            blood_gas = resp["bloodGas"]
            if "bloodGasType" in blood_gas:
                blood_gas["bloodGasType"] = normalize_blood_gas_type(blood_gas["bloodGasType"])

    # Sentence capitalization — free-text narrative fields
    from services.neo_proforma_lookups import _capitalize_fields as _cap_fields

    # Respiratory free-text (fields NOT handled by enum lookups above)
    if "respiratory" in daily_log and isinstance(daily_log["respiratory"], dict):
        _cap_fields(daily_log["respiratory"], ["findings"])

    _cap_fields(daily_log, ["background"])

    # CVS free-text
    if "cvs" in daily_log and isinstance(daily_log["cvs"], dict):
        cvs = daily_log["cvs"]
        _cap_fields(cvs, [
            "centralPulses", "peripheralPulses", "femoralPulses",
            "precordialActivity", "s1s2", "murmur", "murmurCharacter",
            "color", "findings", "pda", "pdaTreatment", "pah", "pahTreatment",
        ])
        echo = cvs.get("echo")
        if isinstance(echo, dict):
            _cap_fields(echo, ["report"])

    # GI free-text
    if "gi" in daily_log and isinstance(daily_log["gi"], dict):
        gi = daily_log["gi"]
        _cap_fields(gi, [
            "abdomen", "bowelSounds", "stoolNature", "aspirateNature",
            "findings", "nec", "necTreatment", "umbilicus", "hernia",
            "genitalia", "immunoglobulins",
        ])
        nutrition = gi.get("nutrition")
        if isinstance(nutrition, dict):
            _cap_fields(nutrition, [
                "feeds", "fullEnteralFeeds", "ivFluids", "tpn", "otherDrugs",
            ])
        nnj = gi.get("nnj")
        if isinstance(nnj, dict):
            _cap_fields(nnj, ["treatment"])

    # CNS free-text
    if "cns" in daily_log and isinstance(daily_log["cns"], dict):
        cns = daily_log["cns"]
        _cap_fields(cns, [
            "anteriorFontanelle", "activity", "tone", "cry", "seizures",
            "typeOfSeizures", "reflexes", "pupils", "findings",
            "therapeuticHypothermia", "sedationParalysis", "neuroSonogram",
            "ultrasoundSpine", "mriCtBrain",
        ])
        eeg = cns.get("eegCfm")
        if isinstance(eeg, dict):
            _cap_fields(eeg, ["report"])

    # Sepsis free-text
    if "sepsis" in daily_log and isinstance(daily_log["sepsis"], dict):
        _cap_fields(daily_log["sepsis"], ["lumbarPuncture", "viralMeningitis"])

    # Invasive lines free-text
    if "invasiveLines" in daily_log and isinstance(daily_log["invasiveLines"], dict):
        for line_key in ["pvc", "picc", "uvc", "uac", "pac"]:
            line = daily_log["invasiveLines"].get(line_key)
            if isinstance(line, dict):
                _cap_fields(line, ["site", "position", "complication"])

    # Skin + ROP free-text
    if "skin" in daily_log and isinstance(daily_log["skin"], dict):
        _cap_fields(daily_log["skin"], ["findings"])
    if "rop" in daily_log and isinstance(daily_log["rop"], dict):
        _cap_fields(daily_log["rop"], ["findings"])

    return payload


def apply_raster_lookups_to_neo_op(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply all Raster lookup transformations to a NEO_OP payload.
    """
    from services.neo_proforma_lookups import (
        normalize_birth_status,
        normalize_sex,
        normalize_birth_order,
        normalize_blood_group,
    )

    # Baby demographics
    if "baby" in payload and isinstance(payload["baby"], dict):
        baby = payload["baby"]
        if "birthStatus" in baby:
            baby["birthStatus"] = normalize_birth_status(baby["birthStatus"])
        if "sex" in baby:
            baby["sex"] = normalize_sex(baby["sex"])
        if "birthOrder" in baby:
            baby["birthOrder"] = normalize_birth_order(baby["birthOrder"])
        if "bloodGroup" in baby:
            baby["bloodGroup"] = normalize_blood_group(baby["bloodGroup"])

    # Mother demographics
    if "mother" in payload and isinstance(payload["mother"], dict):
        mother = payload["mother"]
        if "title" in mother:
            mother["title"] = normalize_title(mother["title"])
        if "education" in mother:
            mother["education"] = normalize_education(mother["education"])
        if "bloodGroup" in mother:
            mother["bloodGroup"] = normalize_blood_group(mother["bloodGroup"])
        occ = mother.get("occupation")
        if isinstance(occ, dict) and "status" in occ:
            occ["status"] = normalize_occupation_status(occ["status"])

    # Partner demographics
    if "partner" in payload and isinstance(payload["partner"], dict):
        partner = payload["partner"]
        if "title" in partner:
            partner["title"] = normalize_title(partner["title"])
        if "education" in partner:
            partner["education"] = normalize_education(partner["education"])
        occ = partner.get("occupation")
        if isinstance(occ, dict) and "status" in occ:
            occ["status"] = normalize_occupation_status(occ["status"])

    # Follow-up — outcome and appointmentType
    if "followUp" in payload and isinstance(payload["followUp"], dict):
        if "outcome" in payload["followUp"]:
            payload["followUp"]["outcome"] = normalize_followup_outcome(payload["followUp"]["outcome"])
        if "appointmentType" in payload["followUp"]:
            payload["followUp"]["appointmentType"] = normalize_appointment_type(payload["followUp"]["appointmentType"])

    # Medical history — neurosonogram and echocardiogram
    if "medicalHistory" in payload and isinstance(payload["medicalHistory"], dict):
        mh = payload["medicalHistory"]
        if "neurosonogram" in mh:
            mh["neurosonogram"] = normalize_neuro_echo(mh["neurosonogram"])
        if "echocardiogram" in mh:
            mh["echocardiogram"] = normalize_neuro_echo(mh["echocardiogram"])

    # Normalize immunization status
    if "immunization" in payload and isinstance(payload["immunization"], dict):
        if "status" in payload["immunization"]:
            payload["immunization"]["status"] = normalize_immunization_status(payload["immunization"]["status"])

    # Normalize medication routes
    if "medications" in payload and isinstance(payload["medications"], list):
        for med in payload["medications"]:
            if isinstance(med, dict) and "route" in med:
                med["route"] = normalize_medication_route(med["route"])

    # Sentence capitalization — free-text narrative fields
    from services.neo_proforma_lookups import _capitalize_fields

    if "medicalHistory" in payload and isinstance(payload["medicalHistory"], dict):
        _capitalize_fields(payload["medicalHistory"], [
            "babyBackground", "confidentialDetails", "complaints", "hpi",
            "allergy", "familyHistory", "treatmentHistory", "development",
            "examination", "diagnosis", "advice", "investigations",
        ])

    if "followUp" in payload and isinstance(payload["followUp"], dict):
        _capitalize_fields(payload["followUp"], ["nextReviewIndication"])
        fee = payload["followUp"].get("fee")
        if isinstance(fee, dict):
            _capitalize_fields(fee, ["reason"])

        # Resolve seenBy name/ID via doctor lookup (single value for NEO_OP)
        from services.doctor_lookups import resolve_seen_by_single
        if "seenBy" in payload["followUp"]:
            payload["followUp"]["seenBy"] = resolve_seen_by_single(payload["followUp"]["seenBy"])

    if "eligibility" in payload and isinstance(payload["eligibility"], dict):
        _capitalize_fields(payload["eligibility"], ["otherSpecify"])

    return payload

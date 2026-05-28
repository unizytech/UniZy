"""
NEO_DISCHARGE Raster API Lookup Tables

Field-level value normalization for NEO_DISCHARGE payloads before sending
to the Neopaed API. Includes discharge-specific maps (immunization status,
neurosonogram/echocardiogram) plus shared normalizers.

Reference: references/Neopaed - One Hat integration values reference sheet.md
"""

import logging
from typing import Dict, Any, Union

from services.neo_proforma_lookups import (
    normalize_yes_no,
    _normalize_field,
    _capitalize_fields,
)

logger = logging.getLogger(__name__)


# ============================================================================
# DISCHARGE-SPECIFIC MAPS
# ============================================================================

IMMUNIZATION_STATUS_MAP: Dict[str, str] = {
    "due": "Due",
    "pending": "Due",
    "not given": "Due",
    "given": "Given",
    "yes": "Given",
    "done": "Given",
    "complete": "Complete",
    "completed": "Complete",
    "all done": "Complete",
}

IMMUNIZATION_SCHEDULE_MAP: Dict[str, str] = {
    "at birth": "At birth",
    "birth": "At birth",
    "6 wks": "6 wks",
    "6 weeks": "6 wks",
    "10 wks": "10 wks",
    "10 weeks": "10 wks",
    "14 wks": "14 wks",
    "14 weeks": "14 wks",
    "6 mths": "6 mths",
    "6 months": "6 mths",
    "9 mths": "9 mths",
    "9 months": "9 mths",
    "1 year": "1 year",
    "12 months": "1 year",
    "15 mths": "15 mths",
    "15 months": "15 mths",
    "16-18 mths": "16-18 mths",
    "18 mths": "18 mths",
    "18 months": "18 mths",
    "2 years": "2 years",
    "24 months": "2 years",
    "5 years": "5 years",
    "10 years": "10 years",
    "optional": "Optional",
    "catch up": "Catch Up",
    "catchup": "Catch Up",
}

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

# Eyes examination findings
EYES_MAP: Dict[str, str] = {
    "": "N/A",
    "n/a": "N/A",
    "na": "N/A",
    "normal": "Normal with Red reflex",
    "normal with red reflex": "Normal with Red reflex",
    "red reflex present": "Normal with Red reflex",
    "red reflex normal": "Normal with Red reflex",
    "subconjunctival hemorrhage": "Subconjunctival Hemorrhage",
    "subconjunctival haemorrhage": "Subconjunctival Hemorrhage",
    "conjunctival hemorrhage": "Subconjunctival Hemorrhage",
    "cataract": "Cataract",
    "congenital cataract": "Cataract",
    "microophthalmos": "Microophthalmos",
    "microphthalmos": "Microophthalmos",
    "microphthalmia": "Microophthalmos",
}

# Discharge status
DISCHARGE_STATUS_MAP: Dict[str, str] = {
    "inpatient": "Inpatient",
    "discharged": "Discharged",
    "discharge": "Discharged",
    "discharge at request": "Discharge at Request",
    "dar": "Discharge at Request",
    "leaving against medical advice": "Leaving against medical advice",
    "lama": "Leaving against medical advice",
    "ama": "Leaving against medical advice",
    "transferred": "Transferred",
    "transfer": "Transferred",
    "died": "Died",
    "expired": "Died",
    "death": "Died",
    "died (ocnr)": "Died (OCNR)",
    "ocnr": "Died (OCNR)",
    "died (pcnr)": "Died (PCNR)",
    "pcnr": "Died (PCNR)",
}

# Cardiac murmur findings
CARDIAC_MURMUR_MAP: Dict[str, str] = {
    "": "N/A",
    "n/a": "N/A",
    "na": "N/A",
    "absent": "Absent",
    "no": "Absent",
    "no murmur": "Absent",
    "none": "Absent",
    "present": "Present",
    "yes": "Present",
    "murmur present": "Present",
    "heard": "Present",
}

# Pulses (femoral, central, peripheral)
PULSES_MAP: Dict[str, str] = {
    "": "N/A",
    "n/a": "N/A",
    "na": "N/A",
    "normal": "Normal",
    "good": "Normal",
    "well felt": "Normal",
    "bounding": "Bounding",
    "feeble": "Feeble/Weak",
    "weak": "Feeble/Weak",
    "feeble/weak": "Feeble/Weak",
    "low volume": "Feeble/Weak",
    "absent": "Absent",
    "not felt": "Absent",
    "not palpable": "Absent",
}

# Hips examination findings
HIPS_MAP: Dict[str, str] = {
    "": "N/A",
    "n/a": "N/A",
    "na": "N/A",
    "normal": "Normal",
    "ddh rt": "DDH Rt",
    "ddh right": "DDH Rt",
    "right ddh": "DDH Rt",
    "ddh lt": "DDH Lt",
    "ddh left": "DDH Lt",
    "left ddh": "DDH Lt",
    "ddh bilateral": "DDH Bilateral",
    "bilateral ddh": "DDH Bilateral",
    "ddh both": "DDH Bilateral",
}

# Genitalia examination
GENITALIA_MAP: Dict[str, str] = {
    "normal": "Normal",
    "normal male": "Normal",
    "normal female": "Normal",
    "abnormal": "Abnormal",
    "ambiguous": "Abnormal",
}

# Neurological status at discharge
NEUROLOGICAL_STATUS_MAP: Dict[str, str] = {
    "": "N/A",
    "n/a": "N/A",
    "na": "N/A",
    "normal": "Normal",
    "suspect": "Suspect",
    "suspicious": "Suspect",
    "abnormal": "Abnormal",
}

# Newborn screening status
NEWBORN_SCREEN_MAP: Dict[str, str] = {
    "": "N/A",
    "n/a": "N/A",
    "na": "N/A",
    "sent": "Sent",
    "done": "Sent",
    "collected": "Sent",
    "not sent": "Not Sent",
    "not done": "Not Sent",
    "pending": "Not Sent",
    "normal": "Normal",
    "abnormal": "Abnormal",
}

# Hearing/ROP screening status
SCREENING_STATUS_MAP: Dict[str, str] = {
    "": "N/A",
    "n/a": "N/A",
    "na": "N/A",
    "performed": "Performed",
    "done": "Performed",
    "completed": "Performed",
    "to be performed as outpatient": "To be performed as outpatient",
    "outpatient": "To be performed as outpatient",
    "pending": "To be performed as outpatient",
    "not indicated": "Not Indicated",
    "not required": "Not Indicated",
}

# Cranial ultrasound / Echocardiography status
IMAGING_STATUS_MAP: Dict[str, str] = {
    "": "N/A",
    "n/a": "N/A",
    "na": "N/A",
    "normal": "Normal",
    "abnormal": "Abnormal",
    "not indicated": "Not Indicated",
    "not done": "Not Done",
    "not required": "Not Indicated",
}

# ROP treatment type
ROP_TREATMENT_MAP: Dict[str, str] = {
    "": "N/A",
    "n/a": "N/A",
    "na": "N/A",
    "laser": "Laser",
    "cryotherapy": "Cryotherapy",
    "cryo": "Cryotherapy",
    "surgical": "Surgical",
    "surgery": "Surgical",
}

# Feeding method at discharge
FEEDING_MAP: Dict[str, str] = {
    "": "N/A",
    "n/a": "N/A",
    "na": "N/A",
    "not applicable": "Not applicable",
    # Direct breastfeeding
    "directly breast fed": "Directly Breast Fed",
    "direct breastfeed": "Directly Breast Fed",
    "direct breastfeeding": "Directly Breast Fed",
    "breastfed": "Directly Breast Fed",
    "breastfeeding": "Directly Breast Fed",
    "dbf": "Directly Breast Fed",
    "exclusive breastfeeding": "Directly Breast Fed",
    "ebf": "Directly Breast Fed",
    # DBF + top ups
    "fed dbf + ebm top up": "Fed DBF + EBM Top up",
    "dbf + ebm top up": "Fed DBF + EBM Top up",
    "dbf with ebm top up": "Fed DBF + EBM Top up",
    "breastfed with ebm top up": "Fed DBF + EBM Top up",
    "fed dbf + formula top up": "Fed DBF + Formula Top up",
    "dbf + formula top up": "Fed DBF + Formula Top up",
    "dbf with formula top up": "Fed DBF + Formula Top up",
    "breastfed with formula top up": "Fed DBF + Formula Top up",
    "fed dbf + ebm/formula top up": "Fed DBF + EBM/Formula Top up",
    "dbf + ebm/formula top up": "Fed DBF + EBM/Formula Top up",
    "mixed feeding": "Fed DBF + EBM/Formula Top up",
    # Spoon feeding
    "spoon fed with ebm": "Spoon Fed with EBM",
    "spoon fed ebm": "Spoon Fed with EBM",
    "spoon feeding with ebm": "Spoon Fed with EBM",
    "spoon fed with formula": "Spoon Fed with Formula",
    "spoon fed formula": "Spoon Fed with Formula",
    "spoon feeding with formula": "Spoon Fed with Formula",
    # Paladai feeding
    "paladai fed with ebm": "Paladai Fed with EBM",
    "paladai fed ebm": "Paladai Fed with EBM",
    "paladai feeding with ebm": "Paladai Fed with EBM",
    "paladai with ebm": "Paladai Fed with EBM",
    "paladai fed with formula": "Paladai Fed with Formula",
    "paladai fed formula": "Paladai Fed with Formula",
    "paladai feeding with formula": "Paladai Fed with Formula",
    "paladai with formula": "Paladai Fed with Formula",
    # Bottle feeding
    "bottle fed": "Bottle Fed",
    "bottle feeding": "Bottle Fed",
    "formula fed": "Bottle Fed",
    "formula feeding": "Bottle Fed",
}


# ============================================================================
# NORMALIZER FUNCTIONS
# ============================================================================

def normalize_immunization_status(value: Any) -> str:
    """Normalize immunization status to reference values: Due, Given, Complete."""
    if value is None:
        return "Due"
    val_str = str(value).strip().lower()
    if val_str in IMMUNIZATION_STATUS_MAP:
        return IMMUNIZATION_STATUS_MAP[val_str]
    # Check if already a valid value
    for valid in set(IMMUNIZATION_STATUS_MAP.values()):
        if val_str == valid.lower():
            return valid
    return "Due"


def normalize_immunization_schedule(value: Any) -> str:
    """Normalize immunization schedule to reference values."""
    if value is None:
        return ""
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in IMMUNIZATION_SCHEDULE_MAP:
        return IMMUNIZATION_SCHEDULE_MAP[val_lower]
    # Check if already a valid value
    for valid in set(IMMUNIZATION_SCHEDULE_MAP.values()):
        if val_lower == valid.lower():
            return valid
    return val_str  # passthrough if unrecognized


def normalize_neuro_echo(value: Any) -> Union[int, str]:
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


def normalize_eyes(value: Any) -> str:
    """Normalize eyes examination findings to reference values."""
    if value is None or value == "":
        return "N/A"
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in EYES_MAP:
        return EYES_MAP[val_lower]
    # Check if already a valid value (case-insensitive)
    valid_values = {v.lower(): v for v in set(EYES_MAP.values())}
    if val_lower in valid_values:
        return valid_values[val_lower]
    # Passthrough with warning
    logger.warning(f"Unrecognized eyes value: '{val_str}', passing through")
    return val_str


def normalize_feeding(value: Any) -> str:
    """Normalize feeding method to reference values."""
    if value is None or value == "":
        return "N/A"
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in FEEDING_MAP:
        return FEEDING_MAP[val_lower]
    # Check if already a valid value (case-insensitive)
    valid_values = {v.lower(): v for v in set(FEEDING_MAP.values())}
    if val_lower in valid_values:
        return valid_values[val_lower]
    # Passthrough with warning
    logger.warning(f"Unrecognized feeding value: '{val_str}', passing through")
    return val_str


def normalize_discharge_status(value: Any) -> str:
    """Normalize discharge status to reference values."""
    if value is None or value == "":
        return ""
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in DISCHARGE_STATUS_MAP:
        return DISCHARGE_STATUS_MAP[val_lower]
    # Check if already a valid value
    valid_values = {v.lower(): v for v in set(DISCHARGE_STATUS_MAP.values())}
    if val_lower in valid_values:
        return valid_values[val_lower]
    logger.warning(f"Unrecognized discharge status: '{val_str}', passing through")
    return val_str


def normalize_cardiac_murmur(value: Any) -> str:
    """Normalize cardiac murmur findings to reference values."""
    if value is None or value == "":
        return "N/A"
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in CARDIAC_MURMUR_MAP:
        return CARDIAC_MURMUR_MAP[val_lower]
    valid_values = {v.lower(): v for v in set(CARDIAC_MURMUR_MAP.values())}
    if val_lower in valid_values:
        return valid_values[val_lower]
    logger.warning(f"Unrecognized cardiac murmur value: '{val_str}', passing through")
    return val_str


def normalize_pulses(value: Any) -> str:
    """Normalize pulse findings (femoral, central, peripheral) to reference values."""
    if value is None or value == "":
        return "N/A"
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in PULSES_MAP:
        return PULSES_MAP[val_lower]
    valid_values = {v.lower(): v for v in set(PULSES_MAP.values())}
    if val_lower in valid_values:
        return valid_values[val_lower]
    logger.warning(f"Unrecognized pulses value: '{val_str}', passing through")
    return val_str


def normalize_hips(value: Any) -> str:
    """Normalize hips examination findings to reference values."""
    if value is None or value == "":
        return "N/A"
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in HIPS_MAP:
        return HIPS_MAP[val_lower]
    valid_values = {v.lower(): v for v in set(HIPS_MAP.values())}
    if val_lower in valid_values:
        return valid_values[val_lower]
    logger.warning(f"Unrecognized hips value: '{val_str}', passing through")
    return val_str


def normalize_genitalia(value: Any) -> str:
    """Normalize genitalia examination findings to reference values."""
    if value is None or value == "":
        return ""
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in GENITALIA_MAP:
        return GENITALIA_MAP[val_lower]
    valid_values = {v.lower(): v for v in set(GENITALIA_MAP.values())}
    if val_lower in valid_values:
        return valid_values[val_lower]
    logger.warning(f"Unrecognized genitalia value: '{val_str}', passing through")
    return val_str


def normalize_neurological_status(value: Any) -> str:
    """Normalize neurological status at discharge to reference values."""
    if value is None or value == "":
        return "N/A"
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in NEUROLOGICAL_STATUS_MAP:
        return NEUROLOGICAL_STATUS_MAP[val_lower]
    valid_values = {v.lower(): v for v in set(NEUROLOGICAL_STATUS_MAP.values())}
    if val_lower in valid_values:
        return valid_values[val_lower]
    logger.warning(f"Unrecognized neurological status: '{val_str}', passing through")
    return val_str


def normalize_newborn_screen(value: Any) -> str:
    """Normalize newborn screening status to reference values."""
    if value is None or value == "":
        return "N/A"
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in NEWBORN_SCREEN_MAP:
        return NEWBORN_SCREEN_MAP[val_lower]
    valid_values = {v.lower(): v for v in set(NEWBORN_SCREEN_MAP.values())}
    if val_lower in valid_values:
        return valid_values[val_lower]
    logger.warning(f"Unrecognized newborn screen status: '{val_str}', passing through")
    return val_str


def normalize_screening_status(value: Any) -> str:
    """Normalize hearing/ROP screening status to reference values."""
    if value is None or value == "":
        return "N/A"
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in SCREENING_STATUS_MAP:
        return SCREENING_STATUS_MAP[val_lower]
    valid_values = {v.lower(): v for v in set(SCREENING_STATUS_MAP.values())}
    if val_lower in valid_values:
        return valid_values[val_lower]
    logger.warning(f"Unrecognized screening status: '{val_str}', passing through")
    return val_str


def normalize_imaging_status(value: Any) -> str:
    """Normalize cranial ultrasound/echocardiography status to reference values."""
    if value is None or value == "":
        return "N/A"
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in IMAGING_STATUS_MAP:
        return IMAGING_STATUS_MAP[val_lower]
    valid_values = {v.lower(): v for v in set(IMAGING_STATUS_MAP.values())}
    if val_lower in valid_values:
        return valid_values[val_lower]
    logger.warning(f"Unrecognized imaging status: '{val_str}', passing through")
    return val_str


def normalize_rop_treatment(value: Any) -> str:
    """Normalize ROP treatment type to reference values."""
    if value is None or value == "":
        return "N/A"
    val_str = str(value).strip()
    val_lower = val_str.lower()
    if val_lower in ROP_TREATMENT_MAP:
        return ROP_TREATMENT_MAP[val_lower]
    valid_values = {v.lower(): v for v in set(ROP_TREATMENT_MAP.values())}
    if val_lower in valid_values:
        return valid_values[val_lower]
    logger.warning(f"Unrecognized ROP treatment type: '{val_str}', passing through")
    return val_str


# ============================================================================
# MASTER FUNCTION
# ============================================================================

def apply_raster_lookups_to_neo_discharge(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply all Raster lookup transformations to a NEO_DISCHARGE payload.

    Navigates the nested discharge structure and normalizes immunization,
    Yes/No fields, physical exam findings, screening statuses, and more.
    """

    discharge = payload.get("discharge")
    if not isinstance(discharge, dict):
        return payload

    # 1. Immunization — status and schedule
    immunization = discharge.get("immunization")
    if isinstance(immunization, dict):
        _normalize_field(immunization, "status", normalize_immunization_status)
        _normalize_field(immunization, "schedule", normalize_immunization_schedule)

    # 2. Discharge status
    _normalize_field(discharge, "dischargeStatus", normalize_discharge_status)

    # 3. Physical findings — malformation Yes/No
    if "malformation" in discharge:
        discharge["malformation"] = normalize_yes_no(discharge["malformation"])

    # 4. Physical exam findings — categorical lookups
    _normalize_field(discharge, "eyes", normalize_eyes)
    _normalize_field(discharge, "cardiacMurmur", normalize_cardiac_murmur)
    _normalize_field(discharge, "femoralPulses", normalize_pulses)
    _normalize_field(discharge, "centralPulses", normalize_pulses)
    _normalize_field(discharge, "peripheralPulses", normalize_pulses)
    _normalize_field(discharge, "hips", normalize_hips)
    _normalize_field(discharge, "genitalia", normalize_genitalia)
    _normalize_field(discharge, "neurologicalStatus", normalize_neurological_status)
    _normalize_field(discharge, "feeding", normalize_feeding)

    # 5. Screening statuses — newborn, hearing, ROP
    _normalize_field(discharge, "newBornScreen", normalize_newborn_screen)

    hearing_screening = discharge.get("hearingScreening")
    if isinstance(hearing_screening, dict):
        _normalize_field(hearing_screening, "status", normalize_screening_status)

    rop_screening = discharge.get("ropScreening")
    if isinstance(rop_screening, dict):
        _normalize_field(rop_screening, "status", normalize_screening_status)

    # 6. Checklist section
    checklist = discharge.get("checklist")
    if isinstance(checklist, dict):
        # Yes/No fields
        for field in [
            "hospitalAcquiredInfection",
            "ventilatorAssociatedPneumonia",
            "bloodStreamInfections",
        ]:
            if field in checklist:
                checklist[field] = normalize_yes_no(checklist[field])

        # ROP treatment — status (Yes/No) and type (Laser/Cryotherapy/Surgical)
        rop_treatment = checklist.get("ropTreatment")
        if isinstance(rop_treatment, dict):
            if "status" in rop_treatment:
                rop_treatment["status"] = normalize_yes_no(rop_treatment["status"])
            _normalize_field(rop_treatment, "type", normalize_rop_treatment)

        # Blood test section — cranial ultrasound / echocardiography
        blood_test = checklist.get("bloodTest")
        if isinstance(blood_test, dict):
            for scan_key in ["cranialUltrasound", "echoCardiography"]:
                scan = blood_test.get(scan_key)
                if isinstance(scan, dict):
                    # Status: Normal/Abnormal/Not Indicated/Not Done
                    _normalize_field(scan, "status", normalize_imaging_status)
                    _capitalize_fields(scan, ["condition"])

        # Checklist free-text
        _capitalize_fields(checklist, ["advice", "planFollowUp"])

    # 7. Sentence capitalization — free-text fields only
    _capitalize_fields(discharge, [
        "additionalInformation", "genitaliaFindings", "malformationDetails",
    ])

    return payload

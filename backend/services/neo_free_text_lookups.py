"""
NEO Free-Text Lookup Functions

Shared lookup/normalization functions for the 4 free-text neonatal templates:
  - NEO_PROFORMA_FREE
  - NEO_DISCHARGE_FREE
  - NEO_POSTNATAL_DAY_FREE
  - NEO_POSTNATAL_DISCHARGE_FREE

These are simpler than the structured NEO_* lookups because most fields are
free text. Only enum fields and medications need normalization.

Reuses _capitalize_fields() and capitalize_sentences() from neo_proforma_lookups.py.
"""

import logging
from typing import Dict, Any

from services.neo_proforma_lookups import (
    _capitalize_fields,
    capitalize_sentences,
    TRANSFER_STATUS_MAP,
    _lookup,
)

logger = logging.getLogger(__name__)


# ============================================================================
# ENUM MAPS (specific to free-text templates)
# ============================================================================

NICU_DISCHARGE_STATUS_MAP: Dict[str, str] = {
    "discharged": "Discharged",
    "absconded": "Absconded",
    "lama": "LAMA",
    "transferred": "Transferred",
    "expired": "Expired",
}

POSTNATAL_DISCHARGE_STATUS_MAP: Dict[str, str] = {
    "discharged": "Discharged",
    "lama": "LAMA",
    "referred": "Referred",
}

DISCHARGE_TIME_SESSION_MAP: Dict[str, str] = {
    "am": "AM",
    "pm": "PM",
}


# ============================================================================
# MEDICATION CAPITALIZATION
# ============================================================================

def _capitalize_medications(medications):
    """Apply sentence capitalization to medication text fields."""
    if not isinstance(medications, list):
        return
    for med in medications:
        if not isinstance(med, dict):
            continue
        _capitalize_fields(med, [
            "drugName", "genericName", "formulation",
            "dose", "frequency", "duration", "additionalInstruction"
        ])


# ============================================================================
# NEO_PROFORMA_FREE LOOKUPS
# ============================================================================

def apply_lookups_neo_proforma_free(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply lookups for NEO_PROFORMA_FREE payloads.

    - transferStatus: normalize to NICU/HDU/SCBU/Postnatal Ward/Nursery
    - Text fields: sentence capitalization
    """
    # Transfer status enum
    if "transferStatus" in payload:
        payload["transferStatus"] = _lookup(
            payload["transferStatus"], TRANSFER_STATUS_MAP
        )

    # Capitalize free-text fields
    _capitalize_fields(payload, [
        "obstetricHistory", "pregnancy", "pregnancyContd",
        "labour", "delivery", "apgar", "resuscitationDetails",
        "essentialDetails", "postResuscitationCare", "admissionDetails",
        "procedures", "diagnosis", "summaryOfExamination",
    ])

    return payload


# ============================================================================
# NEO_DISCHARGE_FREE LOOKUPS
# ============================================================================

def apply_lookups_neo_discharge_free(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply lookups for NEO_DISCHARGE_FREE payloads.

    - status: normalize to Discharged/Absconded/LAMA/Transferred/Expired
    - dischargeTimeSession: normalize to AM/PM
    - Text fields + medication text: sentence capitalization
    """
    # Discharge status enum
    if "status" in payload:
        payload["status"] = _lookup(
            payload["status"], NICU_DISCHARGE_STATUS_MAP
        )

    # Time session enum
    if "dischargeTimeSession" in payload:
        payload["dischargeTimeSession"] = _lookup(
            payload["dischargeTimeSession"], DISCHARGE_TIME_SESSION_MAP
        )

    # Capitalize free-text fields
    _capitalize_fields(payload, [
        "immunization", "dischargeExamination", "dischargeBloodInvestigations",
        "additionalInformation", "advice", "planForFollowup", "nextFollowupDetails",
    ])

    # Capitalize medication text fields
    _capitalize_medications(payload.get("medications"))

    return payload


# ============================================================================
# NEO_POSTNATAL_DAY_FREE LOOKUPS
# ============================================================================

def apply_lookups_neo_postnatal_day_free(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply lookups for NEO_POSTNATAL_DAY_FREE payloads.

    - Text fields only: sentence capitalization
    """
    _capitalize_fields(payload, [
        "background", "diagnosis", "notes", "plan",
    ])

    return payload


# ============================================================================
# NEO_POSTNATAL_DISCHARGE_FREE LOOKUPS
# ============================================================================

def apply_lookups_neo_postnatal_discharge_free(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply lookups for NEO_POSTNATAL_DISCHARGE_FREE payloads.

    - status: normalize to Discharged/LAMA/Referred
    - Text fields + medication text: sentence capitalization
    """
    # Discharge status enum
    if "status" in payload:
        payload["status"] = _lookup(
            payload["status"], POSTNATAL_DISCHARGE_STATUS_MAP
        )

    # Capitalize free-text fields
    _capitalize_fields(payload, [
        "immunization", "diagnosis", "dischargeExamination", "postnatalCourse",
    ])

    # Capitalize medication text fields
    _capitalize_medications(payload.get("medications"))

    return payload

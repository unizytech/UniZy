"""
Clinical Severity Assessment Service

Extracts clinical signals from extraction data and delegates severity calculation
to map_insights_to_clinical_severity() in consultation_insights_prompts.py.

This module handles:
- Keyword-based signal extraction from extraction segments (DIAGNOSIS, PRESCRIPTION, etc.)
- Building ClinicalInput data structure for downstream processing
- Database persistence via calculate_and_save_severity()

Severity calculation (ICD scoring, specialty scoring, thresholds) is centralized in:
consultation_insights_prompts.py → map_insights_to_clinical_severity()

Severity Levels:
- LOW: Score 0-2 (routine care, low stakes)
- MEDIUM: Score 3-6 (moderate stakes, needs attention)
- HIGH: Score 7+ OR critical override (high stakes, requires intervention)

Author: Unizy Health
Version: 2.0.0
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class SeverityLevel(Enum):
    """Clinical severity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ClinicalInput:
    """
    Clinical signals extracted from consultation.

    Attributes:
        specialty: Medical specialty (e.g., "cardiology", "orthopedics")
        diagnosis_text: Free-text diagnosis from consultation
        icd_codes: List of ICD-10 codes for the diagnosis
        medications: List of prescribed medications
        follow_up_urgency: "routine", "soon", or "urgent"
        is_surgical: Whether treatment involves surgery
        is_chronic: Whether condition is chronic
        treatment_duration_days: Expected treatment duration in days
        is_second_opinion: Whether doctor recommends consulting another specialist
        is_alternate_procedure: Whether doctor suggests alternate treatment if first fails
    """
    specialty: str
    diagnosis_text: str
    icd_codes: List[str] = field(default_factory=list)
    medications: List[str] = field(default_factory=list)
    follow_up_urgency: Optional[str] = None
    is_surgical: bool = False
    is_chronic: bool = False
    treatment_duration_days: Optional[int] = None
    is_second_opinion: bool = False
    is_alternate_procedure: bool = False


@dataclass
class ClinicalSeverityResult:
    """
    Result of clinical severity assessment.

    Attributes:
        severity_level: LOW, MEDIUM, or HIGH
        total_score: Numeric score used to determine level
        was_overridden: True if critical condition triggered auto-HIGH
        override_reason: Reason for override (e.g., "Critical ICD code: C34.9")
        score_breakdown: Dict with individual score components
        contributing_factors: Human-readable list of factors
    """
    severity_level: SeverityLevel
    total_score: int
    was_overridden: bool
    override_reason: Optional[str]
    score_breakdown: Dict[str, Any]
    contributing_factors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "severity_level": self.severity_level.value,
            "total_score": self.total_score,
            "was_overridden": self.was_overridden,
            "override_reason": self.override_reason,
            "score_breakdown": self.score_breakdown,
            "contributing_factors": self.contributing_factors
        }


# =============================================================================
# KEYWORD CONFIGURATION (used by build_clinical_input_from_extraction)
# =============================================================================
# Note: ICD/Specialty scoring configs moved to consultation_insights_prompts.py
# This module now uses map_insights_to_clinical_severity() for centralized scoring

# Keywords indicating surgical context
SURGICAL_KEYWORDS = [
    "surgery", "surgical", "operation", "procedure", "post-op",
    "post-operative", "postoperative", "pre-op", "pre-operative",
    "preoperative", "arthroplasty", "replacement", "resection",
    "excision", "implant", "graft", "bypass", "angioplasty",
    "laparoscopy", "laparoscopic", "arthroscopy", "arthroscopic",
    "amputation", "reconstruction", "fusion", "fixation"
]

# Keywords indicating chronic condition
CHRONIC_KEYWORDS = [
    "chronic", "long-term", "long term", "ongoing", "management",
    "controlled", "uncontrolled", "maintenance", "lifetime",
    "permanent", "progressive", "degenerative", "persistent"
]

# Keywords indicating second opinion or specialist referral (+2 severity)
SECOND_OPINION_KEYWORDS = [
    # Second opinion
    "second opinion", "another opinion", "get opinion", "seek opinion",
    "opinion from", "specialist opinion",
    # Specialist referral
    "specialist referral", "referred to", "referring to", "refer to",
    "referral to", "referral for", "specialist review",
    "specialist consultation", "consult with",
    # Recommendations to see specialist
    "need to see", "should see", "recommend seeing", "advise seeing",
    "please see", "must see", "visit the",
    # Specific specialty consults
    "consult cardiology", "consult neurology", "consult oncology",
    "consult gastro", "consult pulmo", "consult nephro",
    "consult ortho", "consult ent", "consult ophtha",
    "cardiology referral", "neurology referral", "oncology referral",
    "surgical referral", "surgery referral",
    # Multi-disciplinary
    "multi-disciplinary", "multidisciplinary", "mdt review",
    "tumor board", "joint consultation", "team review"
]

# Keywords indicating alternate procedure/treatment (+1 severity)
ALTERNATE_PROCEDURE_KEYWORDS = [
    "if not improved", "if no improvement", "if not better",
    "if no response", "if doesn't respond", "if fails",
    "alternative would be", "alternate treatment", "alternative treatment",
    "try this first", "try for", "trial of",
    "fallback", "fall back", "backup plan",
    "escalate to", "escalation", "step up",
    "next step would be", "next option", "other option",
    "if this doesn't work", "otherwise", "failing which",
    "plan b", "second line", "second-line"
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _infer_surgical_flag(diagnosis_text: str, explicit_flag: bool) -> bool:
    """Infer surgical context if not explicitly set."""
    if explicit_flag:
        return True

    diagnosis_lower = diagnosis_text.lower()
    return any(kw in diagnosis_lower for kw in SURGICAL_KEYWORDS)


def _infer_chronic_flag(
    diagnosis_text: str,
    explicit_flag: bool,
    treatment_duration_days: Optional[int]
) -> bool:
    """Infer chronic condition if not explicitly set."""
    if explicit_flag:
        return True

    if treatment_duration_days and treatment_duration_days > 90:
        return True

    diagnosis_lower = diagnosis_text.lower()
    return any(kw in diagnosis_lower for kw in CHRONIC_KEYWORDS)


# =============================================================================
# EXTRACTION DATA HELPERS
# =============================================================================

def _extract_icd_codes_from_diagnosis(diagnosis_data: Any) -> Tuple[List[str], str]:
    """
    Extract ICD-10 codes and diagnosis text from DIAGNOSIS segment.

    DIAGNOSIS segment schema: Array of {code, name, type}
    - code: ICD-10 code (e.g., 'I50.9')
    - name: Diagnosis name with comments
    - type: Primary or Secondary

    Returns:
        Tuple of (icd_codes, diagnosis_text)
    """
    icd_codes = []
    diagnosis_names = []

    if isinstance(diagnosis_data, list):
        for item in diagnosis_data:
            if isinstance(item, dict):
                # Extract ICD code from 'code' field
                code = item.get("code", "")
                if code and isinstance(code, str) and code.strip():
                    icd_codes.append(code.strip())

                # Collect diagnosis names
                name = item.get("name", "")
                if name and isinstance(name, str):
                    diagnosis_names.append(name.strip())
    elif isinstance(diagnosis_data, dict):
        # Legacy format: {primary: "", secondary: ""}
        primary = diagnosis_data.get("primary", "")
        if primary:
            diagnosis_names.append(primary)
        secondary = diagnosis_data.get("secondary", "")
        if secondary:
            diagnosis_names.append(secondary)
    elif isinstance(diagnosis_data, str):
        diagnosis_names.append(diagnosis_data)

    diagnosis_text = " ".join(diagnosis_names)
    return icd_codes, diagnosis_text


def _extract_medications_and_duration(prescription_data: Any) -> Tuple[List[str], Optional[int]]:
    """
    Extract medications and max treatment duration from PRESCRIPTION segment.

    PRESCRIPTION segment schema: Array of {name, durationDays, morning_qty, noon_qty, night_qty, ...}

    Returns:
        Tuple of (medication_names, max_duration_days)
    """
    medications = []
    max_duration = None

    if isinstance(prescription_data, list):
        for item in prescription_data:
            if isinstance(item, dict):
                # Extract medication name
                name = item.get("name", "")
                if name and isinstance(name, str):
                    medications.append(name.strip())

                # Extract duration (durationDays field) — convert to days
                duration_str = item.get("durationDays", "")
                if duration_str:
                    try:
                        if isinstance(duration_str, (int, float)):
                            duration = int(duration_str)
                        else:
                            import re
                            d = str(duration_str).strip().lower()
                            match = re.match(r'(\d+)\s*(day|days|week|weeks|month|months|year|years)?', d)
                            if match:
                                num = int(match.group(1))
                                unit = (match.group(2) or "day").lower()
                                if unit.startswith("week"):
                                    duration = num * 7
                                elif unit.startswith("month"):
                                    duration = num * 30
                                elif unit.startswith("year"):
                                    duration = num * 365
                                else:
                                    duration = num
                            else:
                                numbers = re.findall(r'\d+', d)
                                duration = int(numbers[0]) if numbers else None

                        if duration and (max_duration is None or duration > max_duration):
                            max_duration = duration
                    except (ValueError, IndexError):
                        pass
            elif isinstance(item, str):
                medications.append(item)

    return medications, max_duration


def _extract_follow_up_info(follow_up_data: Any) -> Tuple[Optional[str], bool]:
    """
    Extract follow-up urgency and surgical hints from FOLLOW_UP segment.

    FOLLOW_UP segment schema: {review_date, special_instructions, other_instructions}

    Returns:
        Tuple of (urgency, is_surgical_hint)
    """
    urgency = None
    is_surgical_hint = False

    if not isinstance(follow_up_data, dict):
        return urgency, is_surgical_hint

    # Check review_date and other_instructions for urgency signals
    review = follow_up_data.get("review_date", "") or ""
    other = follow_up_data.get("other_instructions", "") or ""
    special = follow_up_data.get("special_instructions", "") or ""
    combined_lower = f"{review} {other} {special}".lower()

    # Infer urgency from follow-up text
    if any(term in combined_lower for term in ["immediate", "emergency", "urgent", "asap", "today", "tomorrow"]):
        urgency = "urgent"
    elif any(term in combined_lower for term in ["soon", "early", "within 3", "within 5", "priority", "1 week", "2 week"]):
        urgency = "soon"
    elif any(term in combined_lower for term in ["routine", "regular", "monthly", "3 month", "6 month"]):
        urgency = "routine"

    # Check for surgical keywords in all fields
    if any(kw in combined_lower for kw in SURGICAL_KEYWORDS):
        is_surgical_hint = True

    return urgency, is_surgical_hint


def _extract_treatment_plan_info(treatment_plan_data: Any) -> Tuple[bool, bool]:
    """
    Extract chronic and surgical hints from TREATMENT_PLAN segment.

    TREATMENT_PLAN may have various schemas depending on template.
    Common fields: follow_up, medication_changes, other_advice

    Returns:
        Tuple of (is_chronic_hint, is_surgical_hint)
    """
    is_chronic_hint = False
    is_surgical_hint = False

    if isinstance(treatment_plan_data, dict):
        # Collect all text from treatment plan
        all_values = []
        for key, value in treatment_plan_data.items():
            if isinstance(value, str):
                all_values.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        all_values.extend(str(v) for v in item.values() if v)
                    elif isinstance(item, str):
                        all_values.append(item)
            elif isinstance(value, dict):
                all_values.extend(str(v) for v in value.values() if v)

        all_text = " ".join(all_values).lower()

        # Check for chronic keywords
        if any(kw in all_text for kw in CHRONIC_KEYWORDS):
            is_chronic_hint = True

        # Check for surgical keywords
        if any(kw in all_text for kw in SURGICAL_KEYWORDS):
            is_surgical_hint = True

        # Check medication_changes for ongoing management (chronic hint)
        med_changes = treatment_plan_data.get("medication_changes", [])
        if isinstance(med_changes, list) and len(med_changes) >= 3:
            # Multiple medication adjustments suggest chronic condition
            is_chronic_hint = True

    elif isinstance(treatment_plan_data, list):
        all_text = " ".join([str(item) for item in treatment_plan_data if item]).lower()
        if any(kw in all_text for kw in CHRONIC_KEYWORDS):
            is_chronic_hint = True
        if any(kw in all_text for kw in SURGICAL_KEYWORDS):
            is_surgical_hint = True

    elif isinstance(treatment_plan_data, str):
        text_lower = treatment_plan_data.lower()
        if any(kw in text_lower for kw in CHRONIC_KEYWORDS):
            is_chronic_hint = True
        if any(kw in text_lower for kw in SURGICAL_KEYWORDS):
            is_surgical_hint = True

    return is_chronic_hint, is_surgical_hint


def _extract_chronic_from_history(history_data: Any) -> bool:
    """
    Check HISTORY segment for chronic condition indicators.

    HISTORY segment may have: past_medical_history, current_medications,
    allergies, family_history, etc.

    Returns:
        True if chronic condition indicators found
    """
    if isinstance(history_data, dict):
        # Check all text fields for chronic keywords
        all_text_parts = []
        for key, value in history_data.items():
            if isinstance(value, str):
                all_text_parts.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        all_text_parts.append(item)
                    elif isinstance(item, dict):
                        all_text_parts.extend(str(v) for v in item.values() if isinstance(v, str))

        all_text = " ".join(all_text_parts).lower()

        # Check for chronic keywords
        if any(kw in all_text for kw in CHRONIC_KEYWORDS):
            return True

        # Check for known chronic conditions in past medical history
        pmh = history_data.get("past_medical_history", "") or ""
        if isinstance(pmh, str):
            pmh_lower = pmh.lower()
            chronic_conditions = [
                "diabetes", "hypertension", "copd", "asthma", "heart failure",
                "ckd", "kidney disease", "liver disease", "epilepsy", "thyroid",
                "arthritis", "cancer", "hiv", "hepatitis"
            ]
            if any(cond in pmh_lower for cond in chronic_conditions):
                return True

    elif isinstance(history_data, str):
        if any(kw in history_data.lower() for kw in CHRONIC_KEYWORDS):
            return True

    return False


def _extract_treatment_summary_hints(treatment_summary_data: Any) -> Tuple[bool, bool]:
    """
    Extract surgical and chronic hints from TREATMENT_SUMMARY segment.

    TREATMENT_SUMMARY contains summary of prior consultations and may have
    references to surgical history or chronic conditions.

    Returns:
        Tuple of (is_chronic_hint, is_surgical_hint)
    """
    is_chronic_hint = False
    is_surgical_hint = False

    if isinstance(treatment_summary_data, dict):
        # Collect all text from treatment summary
        all_values = []
        for key, value in treatment_summary_data.items():
            if isinstance(value, str):
                all_values.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        all_values.append(item)
                    elif isinstance(item, dict):
                        all_values.extend(str(v) for v in item.values() if v)

        all_text = " ".join(all_values).lower()

        if any(kw in all_text for kw in CHRONIC_KEYWORDS):
            is_chronic_hint = True
        if any(kw in all_text for kw in SURGICAL_KEYWORDS):
            is_surgical_hint = True

    elif isinstance(treatment_summary_data, str):
        text_lower = treatment_summary_data.lower()
        if any(kw in text_lower for kw in CHRONIC_KEYWORDS):
            is_chronic_hint = True
        if any(kw in text_lower for kw in SURGICAL_KEYWORDS):
            is_surgical_hint = True

    return is_chronic_hint, is_surgical_hint


def _detect_second_opinion_and_alternate(
    extraction_data: Dict[str, Any]
) -> Tuple[bool, bool]:
    """
    Detect if doctor recommends second opinion or alternate treatment.

    Scans DIAGNOSIS, TREATMENT_PLAN, FOLLOW_UP, and EXAMINATION segments
    for keywords indicating:
    - Second opinion: "consult with", "refer to", "specialist opinion"
    - Alternate procedure: "if not improved", "try this first", "fallback"

    Returns:
        Tuple of (is_second_opinion, is_alternate_procedure)
    """
    is_second_opinion = False
    is_alternate_procedure = False

    # Segments to check for these keywords
    segments_to_check = [
        "DIAGNOSIS", "diagnosis",
        "TREATMENT_PLAN", "treatment_plan",
        "FOLLOW_UP", "follow_up",
        "EXAMINATION", "examination",
        "TREATMENT_SUMMARY", "treatment_summary",
        "CAUTION", "caution"
    ]

    all_text_parts = []

    for segment_key in segments_to_check:
        segment_data = extraction_data.get(segment_key)
        if not segment_data:
            continue

        if isinstance(segment_data, str):
            all_text_parts.append(segment_data)
        elif isinstance(segment_data, dict):
            # Collect all string values from dict
            for value in segment_data.values():
                if isinstance(value, str):
                    all_text_parts.append(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            all_text_parts.append(item)
                        elif isinstance(item, dict):
                            all_text_parts.extend(
                                str(v) for v in item.values() if isinstance(v, str)
                            )
        elif isinstance(segment_data, list):
            for item in segment_data:
                if isinstance(item, str):
                    all_text_parts.append(item)
                elif isinstance(item, dict):
                    # For DIAGNOSIS array: collect all 'name' fields
                    name = item.get("name", "")
                    if name:
                        all_text_parts.append(name)
                    # Also check other fields
                    for key, value in item.items():
                        if isinstance(value, str) and key != "name":
                            all_text_parts.append(value)

    # Combine all text and check for keywords
    all_text = " ".join(all_text_parts).lower()

    # Check for second opinion keywords
    for keyword in SECOND_OPINION_KEYWORDS:
        if keyword in all_text:
            is_second_opinion = True
            logger.debug(f"[SEVERITY] Second opinion detected: '{keyword}'")
            break

    # Check for alternate procedure keywords
    for keyword in ALTERNATE_PROCEDURE_KEYWORDS:
        if keyword in all_text:
            is_alternate_procedure = True
            logger.debug(f"[SEVERITY] Alternate procedure detected: '{keyword}'")
            break

    return is_second_opinion, is_alternate_procedure


def _parse_warnings_for_severity(warnings_data: Any) -> Tuple[List[str], bool]:
    """
    Parse WARNINGS segment for drug interactions and critical alerts.

    WARNINGS schema: {allergy_checks, contraindication_checks, safety_summary}
    These are JSON strings that need parsing.

    Returns:
        Tuple of (alert_messages, has_critical_alerts)
    """
    alerts = []
    has_critical = False

    if not isinstance(warnings_data, dict):
        return alerts, has_critical

    # Parse safety_summary for critical alerts
    safety_summary_str = warnings_data.get("safety_summary", "")
    if safety_summary_str:
        try:
            if isinstance(safety_summary_str, str):
                safety_summary = json.loads(safety_summary_str)
            else:
                safety_summary = safety_summary_str

            if isinstance(safety_summary, dict):
                status = safety_summary.get("overall_safety_status", "")
                if status in ("ALERTS_PRESENT", "REVIEW_REQUIRED"):
                    has_critical = True

                critical_alerts = safety_summary.get("critical_alerts", [])
                if isinstance(critical_alerts, list):
                    alerts.extend(critical_alerts)
        except (json.JSONDecodeError, TypeError):
            pass

    # Parse contraindication_checks
    contra_str = warnings_data.get("contraindication_checks", "")
    if contra_str:
        try:
            if isinstance(contra_str, str):
                contra_checks = json.loads(contra_str)
            else:
                contra_checks = contra_str

            if isinstance(contra_checks, list):
                for check in contra_checks:
                    if isinstance(check, dict):
                        status = check.get("status", "")
                        if status in ("CONTRAINDICATION_ALERT", "CAUTION_REQUIRED"):
                            reason = check.get("reason", "Drug interaction")
                            medicine = check.get("medicine", "Unknown")
                            alerts.append(f"{medicine}: {reason}")
                            if status == "CONTRAINDICATION_ALERT":
                                has_critical = True
        except (json.JSONDecodeError, TypeError):
            pass

    # Parse allergy_checks
    allergy_str = warnings_data.get("allergy_checks", "")
    if allergy_str:
        try:
            if isinstance(allergy_str, str):
                allergy_checks = json.loads(allergy_str)
            else:
                allergy_checks = allergy_str

            if isinstance(allergy_checks, list):
                for check in allergy_checks:
                    if isinstance(check, dict):
                        status = check.get("status", "")
                        if status == "ALLERGY_ALERT":
                            medicine = check.get("medicine", "Unknown")
                            matched = check.get("matched_allergy", "")
                            alerts.append(f"Allergy alert: {medicine} - {matched}")
                            has_critical = True
        except (json.JSONDecodeError, TypeError):
            pass

    return alerts, has_critical


def build_clinical_input_from_extraction(
    extraction_data: Dict[str, Any],
    doctor_specialty: Optional[str] = None
) -> ClinicalInput:
    """
    Build ClinicalInput from extraction data.

    Extracts clinical signals from the actual segment JSON structures used in
    OP_CORE and DISCHARGE_CORE templates.

    Segment schemas:
    - DIAGNOSIS: Array of {code (ICD-10), name, type}
    - PRESCRIPTION: Array of {name, durationDays, morning_qty, ...}
    - FOLLOW_UP: {review_date, special_instructions, other_instructions}
    - TREATMENT_PLAN: Various schemas with follow_up, medication_changes, etc.
    - WARNINGS: {allergy_checks, contraindication_checks, safety_summary} (JSON strings)
    - CAUTION: String with treatment limitations

    Args:
        extraction_data: Original extraction JSON from Gemini
        doctor_specialty: Optional specialty override (from doctor profile)

    Returns:
        ClinicalInput populated from extraction data
    """
    # Initialize flags
    is_surgical = False
    is_chronic = False
    treatment_duration_days = None
    follow_up_urgency = None

    # -------------------------------------------------------------------------
    # 1. DIAGNOSIS segment → ICD codes + diagnosis text
    # -------------------------------------------------------------------------
    icd_codes = []
    diagnosis_text = ""

    diagnosis_data = extraction_data.get("DIAGNOSIS") or extraction_data.get("diagnosis")
    if diagnosis_data:
        icd_codes, diagnosis_text = _extract_icd_codes_from_diagnosis(diagnosis_data)

    # -------------------------------------------------------------------------
    # 2. PRESCRIPTION segment → medications + treatment duration
    # -------------------------------------------------------------------------
    medications = []

    prescription_data = extraction_data.get("PRESCRIPTION") or extraction_data.get("prescription")
    if prescription_data:
        medications, treatment_duration_days = _extract_medications_and_duration(prescription_data)

    # Infer chronic from long treatment duration
    if treatment_duration_days and treatment_duration_days > 90:
        is_chronic = True

    # -------------------------------------------------------------------------
    # 3. FOLLOW_UP segment → urgency + surgical hints
    # -------------------------------------------------------------------------
    follow_up_data = extraction_data.get("FOLLOW_UP") or extraction_data.get("follow_up")
    if follow_up_data:
        follow_up_urgency, surgical_from_followup = _extract_follow_up_info(follow_up_data)
        if surgical_from_followup:
            is_surgical = True

    # -------------------------------------------------------------------------
    # 4. TREATMENT_PLAN segment → chronic + surgical hints
    # -------------------------------------------------------------------------
    treatment_plan_data = extraction_data.get("TREATMENT_PLAN") or extraction_data.get("treatment_plan")
    if treatment_plan_data:
        chronic_from_tp, surgical_from_tp = _extract_treatment_plan_info(treatment_plan_data)
        if chronic_from_tp:
            is_chronic = True
        if surgical_from_tp:
            is_surgical = True

    # -------------------------------------------------------------------------
    # 5. HISTORY segment → chronic condition indicators
    # -------------------------------------------------------------------------
    history_data = extraction_data.get("HISTORY") or extraction_data.get("history")
    if history_data:
        if _extract_chronic_from_history(history_data):
            is_chronic = True

    # -------------------------------------------------------------------------
    # 6. WARNINGS segment → critical drug interactions (may trigger override)
    # -------------------------------------------------------------------------
    warnings_data = extraction_data.get("WARNINGS") or extraction_data.get("warnings")
    if warnings_data:
        alert_messages, has_critical_alerts = _parse_warnings_for_severity(warnings_data)
        # Critical drug interactions add to diagnosis text for keyword matching
        if has_critical_alerts and alert_messages:
            diagnosis_text += " " + " ".join(alert_messages)

    # -------------------------------------------------------------------------
    # 7. CAUTION segment → may contain surgical/chronic hints
    # -------------------------------------------------------------------------
    caution_data = extraction_data.get("CAUTION") or extraction_data.get("caution")
    if caution_data and isinstance(caution_data, str):
        caution_lower = caution_data.lower()
        if any(kw in caution_lower for kw in SURGICAL_KEYWORDS):
            is_surgical = True
        if any(kw in caution_lower for kw in CHRONIC_KEYWORDS):
            is_chronic = True

    # -------------------------------------------------------------------------
    # 8. TREATMENT_SUMMARY segment → surgical/chronic from prior consultations
    # -------------------------------------------------------------------------
    treatment_summary_data = (
        extraction_data.get("TREATMENT_SUMMARY") or
        extraction_data.get("treatment_summary")
    )
    if treatment_summary_data:
        chronic_from_ts, surgical_from_ts = _extract_treatment_summary_hints(treatment_summary_data)
        if chronic_from_ts:
            is_chronic = True
        if surgical_from_ts:
            is_surgical = True

    # -------------------------------------------------------------------------
    # 9. Check diagnosis text for surgical/chronic keywords
    # -------------------------------------------------------------------------
    if diagnosis_text:
        diagnosis_lower = diagnosis_text.lower()
        if not is_surgical and any(kw in diagnosis_lower for kw in SURGICAL_KEYWORDS):
            is_surgical = True
        if not is_chronic and any(kw in diagnosis_lower for kw in CHRONIC_KEYWORDS):
            is_chronic = True

    # -------------------------------------------------------------------------
    # 10. Detect second opinion and alternate procedure recommendations
    # -------------------------------------------------------------------------
    is_second_opinion, is_alternate_procedure = _detect_second_opinion_and_alternate(
        extraction_data
    )

    # Use specialty from doctor profile or default
    specialty = doctor_specialty or "general_medicine"

    return ClinicalInput(
        specialty=specialty,
        diagnosis_text=diagnosis_text,
        icd_codes=icd_codes,
        medications=medications,
        follow_up_urgency=follow_up_urgency,
        is_surgical=is_surgical,
        is_chronic=is_chronic,
        treatment_duration_days=treatment_duration_days,
        is_second_opinion=is_second_opinion,
        is_alternate_procedure=is_alternate_procedure
    )


# =============================================================================
# DATABASE INTEGRATION
# =============================================================================

async def calculate_and_save_severity(
    extraction_id: uuid.UUID,
    extraction_data: Dict[str, Any],
    doctor_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None,
    doctor_specialty: Optional[str] = None,
    consultation_insights: Optional[Dict[str, Any]] = None,
    consultation_insights_id: Optional[uuid.UUID] = None
) -> Optional[uuid.UUID]:
    """
    Calculate clinical severity and save to database.

    Main entry point for background task integration.
    Uses map_insights_to_clinical_severity() for centralized scoring logic.

    Args:
        extraction_id: UUID of the medical extraction
        extraction_data: Original extraction JSON (used to extract ICD codes and signals)
        doctor_id: Optional doctor UUID
        patient_id: Optional patient UUID
        doctor_specialty: Optional specialty from doctor profile
        consultation_insights: Optional pre-extracted consultation insights (if available)

    Returns:
        UUID of saved assessment, or None on error
    """
    from services.supabase_service import save_clinical_severity_assessment
    from services.consultation_insights_prompts import map_insights_to_clinical_severity

    try:
        # Build clinical input from extraction (keyword-based signal extraction)
        clinical_input = build_clinical_input_from_extraction(
            extraction_data,
            doctor_specialty
        )

        # If pre-extracted consultation insights provided, use them
        # Otherwise, construct insights from keyword-extracted ClinicalInput
        if consultation_insights:
            insights = consultation_insights
        else:
            # Convert ClinicalInput to insights format for map_insights_to_clinical_severity()
            insights = {
                "clinical_severity_signals": {
                    "is_chronic": clinical_input.is_chronic,
                    "is_surgical": clinical_input.is_surgical,
                    "follow_up_urgency": clinical_input.follow_up_urgency or "routine",
                    "is_second_opinion_recommended": clinical_input.is_second_opinion,
                    "is_alternate_treatment_discussed": clinical_input.is_alternate_procedure,
                    "critical_condition_detected": False,  # Will be detected by ICD check
                },
                "medication_signals": {
                    "total_medications_prescribed": len(clinical_input.medications),
                    "max_duration_days": clinical_input.treatment_duration_days,
                }
            }

        # Calculate severity using centralized map function
        result = map_insights_to_clinical_severity(
            insights=insights,
            icd_codes=clinical_input.icd_codes,
            specialty=clinical_input.specialty
        )

        # Prepare data for database
        # Note: Raw AI signals are stored in consultation_insights table (no input_data column)
        assessment_data = {
            "extraction_id": str(extraction_id),
            "patient_id": str(patient_id) if patient_id else None,
            "doctor_id": str(doctor_id) if doctor_id else None,
            "consultation_insights_id": str(consultation_insights_id) if consultation_insights_id else None,
            "severity_level": result["severity_level"],
            "total_score": result["total_score"],
            "was_overridden": result.get("critical_condition", False),
            "override_reason": f"Critical ICD code: {result.get('critical_code')}" if result.get("critical_code") else None,
            "score_breakdown": {
                "icd_score": result["icd_score"],
                "specialty_score": result["specialty_score"],
                "base_score": result["base_score"],
                "surgical_boost": result["surgical_boost"],
                "modifier_score": result["modifier_score"],
            },
            "contributing_factors": result["severity_reasons"],
            # Flag columns (stored directly, no longer in input_data)
            "is_surgical": clinical_input.is_surgical,
            "is_chronic": clinical_input.is_chronic,
            "is_second_opinion": clinical_input.is_second_opinion,
            "is_alternate_procedure": clinical_input.is_alternate_procedure,
            "calculation_version": "2.0.0"  # Version bump for new formula
        }

        # Save to database
        assessment_id = save_clinical_severity_assessment(assessment_data)

        logger.info(
            f"[SEVERITY] Saved assessment {assessment_id} for extraction {extraction_id}: "
            f"{result['severity_level']} (score={result['total_score']})"
        )

        return assessment_id

    except Exception as e:
        logger.error(
            f"[SEVERITY] Failed to calculate/save for extraction {extraction_id}: {e}",
            exc_info=True
        )
        return None


# =============================================================================
# MODULE INFO
# =============================================================================

__version__ = "2.0.0"  # Updated to use centralized scoring via map_insights_to_clinical_severity()
__author__ = "Unizy Health"
__all__ = [
    # Enums
    "SeverityLevel",

    # Data classes
    "ClinicalInput",
    "ClinicalSeverityResult",

    # Main functions
    "build_clinical_input_from_extraction",
    "calculate_and_save_severity",
]

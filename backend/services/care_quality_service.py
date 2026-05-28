"""
Care Quality Risk Score Service (AI-Enhanced)

Calculates care quality risk score (0-100%) based on 4 indicators:
- Q1: Medication Issue (allergy/contraindication alerts from WARNINGS segment)
- Q2: Missed Red Flag (red flags not addressed in treatment - from triage engine)
- Q3: Incomplete Treatment Plan (missing investigations, diagnosis without treatment)
- Q4: Follow-up Gap Risk (serious diagnosis with vague follow-up)

The service queries:
1. triage_suggestion_log for red flags and missing investigations
2. extraction_segments for WARNINGS, DIAGNOSIS, PRESCRIPTION, TREATMENT_PLAN, FOLLOW_UP
3. clinical_severity_assessments for ICD severity context
4. consultation_insights for enhanced clinical severity signals (AI-extracted)

Version: 2.0.0 (AI-Enhanced - Uses consultation_insights for severity context)
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class RiskLevel(Enum):
    """Care quality risk levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Indicator weights (must sum to 100)
INDICATOR_WEIGHTS = {
    "medication_issue": 25,      # Q1
    "missed_red_flag": 25,       # Q2
    "incomplete_treatment": 25,  # Q3
    "followup_gap": 25           # Q4
}

# Severity modifiers
SEVERITY_MODIFIERS = {
    "HIGH": 1.3,    # +30%
    "MEDIUM": 1.15, # +15%
    "LOW": 1.0      # No change
}

# Vague follow-up patterns
VAGUE_FOLLOWUP_PATTERNS = [
    "as needed", "if needed", "prn", "if symptoms", "when required",
    "if worsens", "if no improvement", "as necessary", "sos",
    "come back if", "return if", "if any issues", "if problems",
    "when necessary", "if required"
]

# Critical red flag keywords (for severity determination)
CRITICAL_RED_FLAG_KEYWORDS = [
    "hypotension", "hypoxia", "shock", "bleeding", "suicidal",
    "cardiac arrest", "respiratory failure", "seizure", "altered sensorium"
]

# High-severity ICD prefixes (require definite follow-up)
HIGH_SEVERITY_ICD_PREFIXES = [
    "I21", "I22",  # MI
    "I60", "I61", "I62", "I63", "I64",  # Stroke
    "C",  # Malignancy (all)
    "N17", "N18",  # Kidney disease
    "A41",  # Sepsis
    "J96",  # Respiratory failure
    "K72",  # Hepatic failure
]


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class CareQualityResult:
    """Result of care quality risk assessment."""
    care_quality_score: float
    risk_level: RiskLevel

    # Indicators
    is_medication_issue: bool
    is_missed_red_flag: bool
    is_incomplete_treatment: bool
    is_followup_gap: bool

    # Reasons per indicator
    medication_issue_reasons: List[str]
    missed_red_flag_reasons: List[str]
    incomplete_treatment_reasons: List[str]
    followup_gap_reasons: List[str]

    # Severities per indicator
    medication_issue_severity: str
    missed_red_flag_severity: str
    incomplete_treatment_severity: str
    followup_gap_severity: str

    # Consolidated
    reasons: List[str]

    # Score breakdown
    base_score: float
    indicator_count: int
    primary_risk_driver: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "care_quality_score": round(self.care_quality_score, 2),
            "risk_level": self.risk_level.value,
            "is_medication_issue": self.is_medication_issue,
            "is_missed_red_flag": self.is_missed_red_flag,
            "is_incomplete_treatment": self.is_incomplete_treatment,
            "is_followup_gap": self.is_followup_gap,
            "medication_issue_reasons": self.medication_issue_reasons,
            "missed_red_flag_reasons": self.missed_red_flag_reasons,
            "incomplete_treatment_reasons": self.incomplete_treatment_reasons,
            "followup_gap_reasons": self.followup_gap_reasons,
            "medication_issue_severity": self.medication_issue_severity,
            "missed_red_flag_severity": self.missed_red_flag_severity,
            "incomplete_treatment_severity": self.incomplete_treatment_severity,
            "followup_gap_severity": self.followup_gap_severity,
            "reasons": self.reasons,
            "base_score": round(self.base_score, 2),
            "indicator_count": self.indicator_count,
            "primary_risk_driver": self.primary_risk_driver,
        }


# =============================================================================
# Q1: MEDICATION ISSUE
# =============================================================================

def check_medication_issue(warnings_segment: Optional[Dict]) -> Tuple[bool, List[str], str]:
    """
    Check for medication issues from WARNINGS segment.

    WARNINGS schema:
    - allergy_checks: JSON string array [{medicine, status, matched_allergy, notes}]
    - contraindication_checks: JSON string array [{medicine, status, reason}]
    - safety_summary: JSON {overall_safety_status, critical_alerts}

    Returns: (is_triggered, reasons, severity)
    """
    reasons = []
    severity = "LOW"

    if not warnings_segment:
        return False, [], "LOW"

    # Parse allergy_checks
    allergy_checks_str = warnings_segment.get("allergy_checks", "[]")
    try:
        if isinstance(allergy_checks_str, str):
            allergy_checks = json.loads(allergy_checks_str)
        else:
            allergy_checks = allergy_checks_str or []

        for check in allergy_checks:
            if isinstance(check, dict) and check.get("status") == "ALLERGY_ALERT":
                medicine = check.get("medicine", "Unknown")
                matched = check.get("matched_allergy", "")
                reasons.append(f"Allergy alert: {medicine} conflicts with known allergy to {matched}")
                severity = "HIGH"
    except (json.JSONDecodeError, TypeError):
        pass

    # Parse contraindication_checks
    contra_checks_str = warnings_segment.get("contraindication_checks", "[]")
    try:
        if isinstance(contra_checks_str, str):
            contra_checks = json.loads(contra_checks_str)
        else:
            contra_checks = contra_checks_str or []

        for check in contra_checks:
            if isinstance(check, dict):
                status = check.get("status", "")
                if status == "CONTRAINDICATION_ALERT":
                    medicine = check.get("medicine", "Unknown")
                    reason = check.get("reason", "Contraindication")
                    reasons.append(f"Contraindication: {medicine} - {reason}")
                    severity = "HIGH"
                elif status == "CAUTION_REQUIRED":
                    medicine = check.get("medicine", "Unknown")
                    reason = check.get("reason", "Caution")
                    reasons.append(f"Caution required: {medicine} - {reason}")
                    if severity != "HIGH":
                        severity = "MEDIUM"
    except (json.JSONDecodeError, TypeError):
        pass

    # Parse safety_summary
    safety_str = warnings_segment.get("safety_summary", "{}")
    try:
        if isinstance(safety_str, str):
            safety = json.loads(safety_str)
        else:
            safety = safety_str or {}

        if isinstance(safety, dict):
            status = safety.get("overall_safety_status", "")
            if status == "REVIEW_REQUIRED" and severity == "LOW":
                severity = "MEDIUM"
    except (json.JSONDecodeError, TypeError):
        pass

    return len(reasons) > 0, reasons, severity


# =============================================================================
# Q2: MISSED RED FLAG
# =============================================================================

def check_missed_red_flag(
    triage_suggestions: List[Dict],
    diagnosis_segment: Optional[List[Dict]],
    treatment_plan_segment: Optional[Dict],
    prescription_segment: Optional[List[Dict]]
) -> Tuple[bool, List[str], str]:
    """
    Check if identified red flags were addressed in treatment.

    Uses triage_suggestion_log entries with suggestion_type='red_flag'.
    Cross-references with diagnosis/treatment/prescription to see if addressed.

    Returns: (is_triggered, reasons, severity)
    """
    reasons = []
    severity = "LOW"

    # Filter for red_flag suggestions
    red_flag_suggestions = [
        s for s in triage_suggestions
        if s.get("suggestion_type") == "red_flag"
    ]

    if not red_flag_suggestions:
        return False, [], "LOW"

    # Build text of what was addressed
    addressed_parts = []

    if diagnosis_segment:
        for d in diagnosis_segment:
            if isinstance(d, dict):
                addressed_parts.append(d.get("name", ""))
                addressed_parts.append(d.get("code", ""))

    if treatment_plan_segment:
        if isinstance(treatment_plan_segment, list):
            addressed_parts.extend([str(item) for item in treatment_plan_segment if item])
        elif isinstance(treatment_plan_segment, dict):
            addressed_parts.extend(str(v) for v in treatment_plan_segment.values() if v)
        elif isinstance(treatment_plan_segment, str) and treatment_plan_segment:
            addressed_parts.append(treatment_plan_segment)

    if prescription_segment:
        for p in prescription_segment:
            if isinstance(p, dict):
                addressed_parts.append(p.get("name", ""))
                addressed_parts.append(p.get("remarks", ""))

    addressed_text = " ".join(addressed_parts).lower()

    # Check each red flag
    for suggestion in red_flag_suggestions:
        suggestion_text = suggestion.get("suggestion_text", "")
        if not suggestion_text:
            continue

        # Extract key terms from red flag
        key_terms = _extract_key_terms(suggestion_text)

        # Check if addressed
        addressed = any(term in addressed_text for term in key_terms)

        if not addressed:
            reasons.append(f"Red flag not addressed: {suggestion_text}")

            # Determine severity based on critical keywords
            if any(kw in suggestion_text.lower() for kw in CRITICAL_RED_FLAG_KEYWORDS):
                severity = "HIGH"
            elif severity != "HIGH":
                severity = "MEDIUM"

    return len(reasons) > 0, reasons, severity


def _extract_key_terms(text: str) -> List[str]:
    """Extract key medical terms from text for matching."""
    # Simple extraction: words > 3 chars, lowercase, no stopwords
    stopwords = {"the", "and", "for", "with", "from", "that", "this", "patient", "consider"}
    words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
    return [w for w in words if w not in stopwords]


# =============================================================================
# Q3: INCOMPLETE TREATMENT PLAN
# =============================================================================

def check_incomplete_treatment(
    triage_suggestions: List[Dict],
    diagnosis_segment: Optional[List[Dict]],
    prescription_segment: Optional[List[Dict]],
    treatment_plan_segment: Optional[Dict]
) -> Tuple[bool, List[str], str]:
    """
    Check for incomplete treatment plan:
    1. Diagnosis without prescription/treatment
    2. Critical missing investigations from triage
    3. Many important missing investigations

    Returns: (is_triggered, reasons, severity)
    """
    reasons = []
    severity = "LOW"

    # Check 1: Diagnosis without prescription
    diagnosis_count = len(diagnosis_segment) if diagnosis_segment else 0
    prescription_count = len(prescription_segment) if prescription_segment else 0

    has_treatment = False
    if treatment_plan_segment:
        if isinstance(treatment_plan_segment, list):
            has_treatment = len(treatment_plan_segment) > 0
        elif isinstance(treatment_plan_segment, dict):
            has_treatment = any(v for v in treatment_plan_segment.values() if v)
        elif isinstance(treatment_plan_segment, str):
            has_treatment = bool(treatment_plan_segment.strip())

    if diagnosis_count > 0 and prescription_count == 0 and not has_treatment:
        diagnoses = []
        for d in (diagnosis_segment or [])[:3]:
            if isinstance(d, dict):
                diagnoses.append(d.get("name", "Unknown"))
        if diagnoses:
            reasons.append(f"Diagnosis present ({', '.join(diagnoses)}) but no prescription or treatment documented")
            severity = "HIGH"

    # Check 2: Critical missing investigations from triage
    critical_investigations = [
        s for s in triage_suggestions
        if s.get("suggestion_type") == "investigation" and
        s.get("source_layer") in ("critical", "critical_actions")
    ]

    if critical_investigations:
        for suggestion in critical_investigations[:3]:
            suggestion_text = suggestion.get("suggestion_text", "Missing investigation")
            reasons.append(f"Critical investigation not ordered: {suggestion_text}")
        severity = "HIGH"

    # Check 3: Many important missing investigations (3+)
    important_investigations = [
        s for s in triage_suggestions
        if s.get("suggestion_type") == "investigation" and
        s.get("source_layer") in ("important", "important_considerations")
    ]

    if len(important_investigations) >= 3:
        reasons.append(f"{len(important_investigations)} recommended investigations not ordered")
        if severity == "LOW":
            severity = "MEDIUM"

    return len(reasons) > 0, reasons, severity


# =============================================================================
# Q4: FOLLOW-UP GAP RISK
# =============================================================================

def _has_specific_timeline(text: str) -> bool:
    """
    Check if text contains a SPECIFIC timeline (e.g., "5 days", "1 week", "2 months").

    A timeline is specific if it contains a number followed by a time unit.
    Examples of SPECIFIC timelines:
    - "After 5 days" -> True
    - "In 1 week" -> True
    - "2-3 weeks" -> True
    - "Within 48 hours" -> True
    - "After 5 days, if symptoms persist" -> True (has specific time)

    Examples of VAGUE timelines (no specific time):
    - "As needed" -> False
    - "If symptoms worsen" -> False
    - "Come back if problems" -> False
    """
    if not text:
        return False

    text_lower = text.lower()

    # Patterns that indicate a SPECIFIC timeline
    # Look for numbers followed by time units
    import re
    specific_patterns = [
        r'\d+\s*days?',           # 5 days, 1 day
        r'\d+\s*weeks?',          # 2 weeks, 1 week
        r'\d+\s*months?',         # 3 months, 1 month
        r'\d+\s*hours?',          # 48 hours, 24 hour
        r'\d+\s*-\s*\d+\s*days?', # 5-7 days
        r'\d+\s*-\s*\d+\s*weeks?',# 2-3 weeks
        r'\d+\s*to\s*\d+\s*days?',# 5 to 7 days
        r'tomorrow',              # tomorrow
        r'next\s+week',           # next week
        r'next\s+month',          # next month
        r'after\s+\d+',           # after 5...
        r'in\s+\d+',              # in 5...
        r'within\s+\d+',          # within 48...
    ]

    for pattern in specific_patterns:
        if re.search(pattern, text_lower):
            return True

    return False


def check_followup_gap(
    follow_up_segment: Optional[Dict],
    diagnosis_segment: Optional[List[Dict]],
    clinical_severity: Optional[Dict],
    consultation_insights: Optional[Dict] = None,
    treatment_plan_segment: Optional[Dict] = None
) -> Tuple[bool, List[str], str]:
    """
    Check for follow-up gap with serious diagnosis:
    1. Vague/empty follow-up timeline (NO specific time period mentioned)
    2. Serious diagnosis (high-severity ICD codes or HIGH clinical severity)

    Now also uses AI-extracted clinical_severity_signals from consultation_insights
    for enhanced severity detection.

    IMPORTANT: A timeline like "After 5 days, if symptoms persist" is NOT vague
    because it contains a specific time period (5 days). Only timelines with
    NO specific time period are considered vague.

    Also checks treatment_plan_segment for follow-up information if follow_up_segment
    doesn't have a timeline.

    Returns: (is_triggered, reasons, severity)
    """
    reasons = []
    severity = "LOW"

    # Get follow-up timeline from follow_up_segment
    timeline = ""
    if follow_up_segment and isinstance(follow_up_segment, dict):
        timeline = follow_up_segment.get("review_date", "") or follow_up_segment.get("other_instructions", "") or ""

    # Also check treatment_plan_segment for follow-up info if follow_up timeline is empty
    if not timeline.strip() and treatment_plan_segment:
        if isinstance(treatment_plan_segment, list):
            # Array format — scan items for follow-up/review keywords
            combined = " ".join([str(item) for item in treatment_plan_segment if item])
            if combined.strip():
                timeline = combined
        elif isinstance(treatment_plan_segment, dict):
            treatment_followup = treatment_plan_segment.get("follow_up", "") or ""
            treatment_review = treatment_plan_segment.get("review_date", "") or ""
            if treatment_followup:
                timeline = treatment_followup
            elif treatment_review:
                timeline = treatment_review
        elif isinstance(treatment_plan_segment, str) and treatment_plan_segment.strip():
            timeline = treatment_plan_segment

    timeline_lower = timeline.lower().strip()

    # Check 1: Determine if follow-up is vague
    # A timeline is vague ONLY if it has NO specific time period
    # "After 5 days, if symptoms persist" -> NOT vague (has "5 days")
    # "Come back if symptoms worsen" -> vague (no specific time)
    has_specific_time = _has_specific_timeline(timeline_lower)

    is_vague = (
        not timeline_lower or
        timeline_lower in ["", "n/a", "none", "not specified", "-"] or
        (not has_specific_time and any(pattern in timeline_lower for pattern in VAGUE_FOLLOWUP_PATTERNS))
    )

    # Check 2: Diagnosis severity
    has_serious_diagnosis = False
    serious_diagnoses = []

    for diagnosis in (diagnosis_segment or []):
        if isinstance(diagnosis, dict):
            icd_code = diagnosis.get("code", "") or ""
            diagnosis_name = diagnosis.get("name", "")

            # Check if ICD code indicates serious condition
            if any(icd_code.upper().startswith(prefix) for prefix in HIGH_SEVERITY_ICD_PREFIXES):
                has_serious_diagnosis = True
                serious_diagnoses.append(diagnosis_name or icd_code)

    # Also use clinical_severity if available
    if clinical_severity:
        severity_level = clinical_severity.get("severity_level", "")
        if severity_level in ["HIGH", "CRITICAL"]:
            has_serious_diagnosis = True

    # Also check AI-extracted clinical_severity_signals from consultation_insights
    if consultation_insights:
        severity_signals = consultation_insights.get("clinical_severity_signals", {})
        if severity_signals:
            # Check for high-severity indicators from AI extraction
            if severity_signals.get("is_surgical_intervention", False):
                has_serious_diagnosis = True
            if severity_signals.get("is_multi_system", False):
                has_serious_diagnosis = True
            # Check ICD codes from AI extraction
            ai_icd_codes = severity_signals.get("icd_codes_detected", [])
            for icd_code in ai_icd_codes:
                if any(str(icd_code).upper().startswith(prefix) for prefix in HIGH_SEVERITY_ICD_PREFIXES):
                    has_serious_diagnosis = True
                    if icd_code not in serious_diagnoses:
                        serious_diagnoses.append(str(icd_code))

    # Determine trigger
    if is_vague and has_serious_diagnosis:
        if serious_diagnoses:
            reasons.append(f"Serious diagnosis ({', '.join(serious_diagnoses[:2])}) with vague/empty follow-up")
        else:
            reasons.append("High clinical severity with vague/empty follow-up")
        severity = "HIGH"
    elif is_vague and diagnosis_segment:
        reasons.append(f"Follow-up timeline is vague or empty: '{timeline}'")
        severity = "MEDIUM"

    return len(reasons) > 0, reasons, severity


# =============================================================================
# SCORE CALCULATION
# =============================================================================

def calculate_risk_score(
    indicators: Dict[str, bool],
    severities: Dict[str, str]
) -> Tuple[float, float, RiskLevel, Optional[str]]:
    """
    Calculate final risk score from indicators and severities.

    Returns: (final_score, base_score, risk_level, primary_driver)
    """
    # Calculate base score from triggered indicators
    base_score = sum(
        INDICATOR_WEIGHTS[ind]
        for ind, triggered in indicators.items()
        if triggered
    )

    # Find max severity for modifier
    severity_order = ["LOW", "MEDIUM", "HIGH"]
    max_severity = "LOW"
    for sev in severities.values():
        if severity_order.index(sev) > severity_order.index(max_severity):
            max_severity = sev

    # Apply modifier
    raw_score = base_score * SEVERITY_MODIFIERS[max_severity]
    final_score = min(95, max(5, raw_score))  # Clamp 5-95%

    # Determine risk level
    if final_score >= 70:
        risk_level = RiskLevel.CRITICAL
    elif final_score >= 50:
        risk_level = RiskLevel.HIGH
    elif final_score >= 30:
        risk_level = RiskLevel.MEDIUM
    else:
        risk_level = RiskLevel.LOW

    # Find primary driver (highest weight triggered indicator)
    primary_driver = None
    max_weight = 0
    for ind, triggered in indicators.items():
        if triggered and INDICATOR_WEIGHTS[ind] > max_weight:
            max_weight = INDICATOR_WEIGHTS[ind]
            primary_driver = ind

    return final_score, base_score, risk_level, primary_driver


# =============================================================================
# MAIN CALCULATION
# =============================================================================

def calculate_care_quality_risk(
    warnings_segment: Optional[Dict],
    triage_suggestions: List[Dict],
    diagnosis_segment: Optional[List[Dict]],
    prescription_segment: Optional[List[Dict]],
    treatment_plan_segment: Optional[Dict],
    follow_up_segment: Optional[Dict],
    clinical_severity: Optional[Dict],
    consultation_insights: Optional[Dict] = None
) -> CareQualityResult:
    """
    Calculate care quality risk score from all inputs.

    Args:
        warnings_segment: WARNINGS segment data (medication safety)
        triage_suggestions: List of triage suggestions from triage_suggestion_log
        diagnosis_segment: DIAGNOSIS segment data
        prescription_segment: PRESCRIPTION segment data
        treatment_plan_segment: TREATMENT_PLAN segment data
        follow_up_segment: FOLLOW_UP segment data
        clinical_severity: clinical_severity_assessments record
        consultation_insights: AI-extracted consultation insights (optional)

    Returns:
        CareQualityResult with score, level, indicators, and reasons
    """
    # Check each indicator
    q1_triggered, q1_reasons, q1_severity = check_medication_issue(warnings_segment)
    q2_triggered, q2_reasons, q2_severity = check_missed_red_flag(
        triage_suggestions, diagnosis_segment, treatment_plan_segment, prescription_segment
    )
    q3_triggered, q3_reasons, q3_severity = check_incomplete_treatment(
        triage_suggestions, diagnosis_segment, prescription_segment, treatment_plan_segment
    )
    q4_triggered, q4_reasons, q4_severity = check_followup_gap(
        follow_up_segment, diagnosis_segment, clinical_severity, consultation_insights,
        treatment_plan_segment
    )

    # Build indicator dicts
    indicators = {
        "medication_issue": q1_triggered,
        "missed_red_flag": q2_triggered,
        "incomplete_treatment": q3_triggered,
        "followup_gap": q4_triggered
    }
    severities = {
        "medication_issue": q1_severity,
        "missed_red_flag": q2_severity,
        "incomplete_treatment": q3_severity,
        "followup_gap": q4_severity
    }

    # Calculate score
    final_score, base_score, risk_level, primary_driver = calculate_risk_score(
        indicators, severities
    )

    # Count triggered indicators
    indicator_count = sum(1 for v in indicators.values() if v)

    # Consolidate all reasons
    all_reasons = q1_reasons + q2_reasons + q3_reasons + q4_reasons

    return CareQualityResult(
        care_quality_score=final_score,
        risk_level=risk_level,
        is_medication_issue=q1_triggered,
        is_missed_red_flag=q2_triggered,
        is_incomplete_treatment=q3_triggered,
        is_followup_gap=q4_triggered,
        medication_issue_reasons=q1_reasons,
        missed_red_flag_reasons=q2_reasons,
        incomplete_treatment_reasons=q3_reasons,
        followup_gap_reasons=q4_reasons,
        medication_issue_severity=q1_severity,
        missed_red_flag_severity=q2_severity,
        incomplete_treatment_severity=q3_severity,
        followup_gap_severity=q4_severity,
        reasons=all_reasons,
        base_score=base_score,
        indicator_count=indicator_count,
        primary_risk_driver=primary_driver
    )


# =============================================================================
# HELPER: EXTRACT SPECIFIC WARNINGS FOR INTERVENTIONS
# =============================================================================

def _extract_specific_warnings(
    warnings_segment: Optional[Dict],
    triage_suggestions: List[Dict],
    consultation_insights: Optional[Dict],
    diagnosis_segment: Optional[List[Dict]],
    prescription_segment: Optional[List[Dict]]
) -> Dict[str, Any]:
    """
    Extract specific warnings from source data for intervention generation.

    These warnings are used by quality_interventions_service to generate
    specific, actionable intervention messages (e.g., "X-ray not ordered"
    instead of generic "recommended investigations not ordered").

    Returns:
        Dict containing specific warnings and metadata
    """
    input_data = {
        "triage_suggestion_count": len(triage_suggestions),
        "has_warnings": warnings_segment is not None,
        "has_consultation_insights": consultation_insights is not None,
        "diagnosis_count": len(diagnosis_segment) if diagnosis_segment else 0,
        "prescription_count": len(prescription_segment) if prescription_segment else 0,
        "clinical_severity_signals": consultation_insights.get("clinical_severity_signals", {}) if consultation_insights else {},
        "extraction_source": "ai_insights",
        # Specific warnings for intervention generation
        "contraindication_warnings": [],
        "drug_interaction_warnings": [],
        "allergy_warnings": [],
        "dosage_warnings": [],
        "workup_warnings": [],
        "red_flag_warnings": [],
        "diagnosis_warnings": [],
        "protocol_warnings": [],
        "followup_warnings": [],
        "total_medications": 0,
    }

    # Extract medication warnings from WARNINGS segment
    if warnings_segment:
        # Parse allergy checks
        allergy_checks_str = warnings_segment.get("allergy_checks", "[]")
        try:
            if isinstance(allergy_checks_str, str):
                allergy_checks = json.loads(allergy_checks_str)
            else:
                allergy_checks = allergy_checks_str or []

            for check in allergy_checks:
                if isinstance(check, dict) and check.get("status") == "ALLERGY_ALERT":
                    medicine = check.get("medicine", "Unknown medication")
                    matched = check.get("matched_allergy", "known allergen")
                    input_data["allergy_warnings"].append({
                        "medicine": medicine,
                        "matched_allergy": matched,
                        "details": f"{medicine} conflicts with known allergy to {matched}"
                    })
        except (json.JSONDecodeError, TypeError):
            pass

        # Parse contraindication checks
        contra_checks_str = warnings_segment.get("contraindication_checks", "[]")
        try:
            if isinstance(contra_checks_str, str):
                contra_checks = json.loads(contra_checks_str)
            else:
                contra_checks = contra_checks_str or []

            for check in contra_checks:
                if isinstance(check, dict):
                    status = check.get("status", "")
                    if status in ("CONTRAINDICATION_ALERT", "CAUTION_REQUIRED"):
                        medicine = check.get("medicine", "Unknown medication")
                        reason = check.get("reason", "potential contraindication")
                        input_data["contraindication_warnings"].append({
                            "medicine": medicine,
                            "reason": reason,
                            "status": status,
                            "details": f"{medicine} - {reason}"
                        })
        except (json.JSONDecodeError, TypeError):
            pass

    # Extract workup warnings from triage suggestions
    for suggestion in triage_suggestions:
        suggestion_type = suggestion.get("suggestion_type", "")
        suggestion_text = suggestion.get("suggestion_text", "")
        source_layer = suggestion.get("source_layer", "")
        category = suggestion.get("category", "")

        # Missing investigations
        if suggestion_type == "investigation" or category == "investigation":
            # Clean up the suggestion text to get just the investigation name
            investigation_name = suggestion_text
            # Remove common prefixes
            for prefix in ["Consider ", "Order ", "Recommend ", "Urgent: ", "Critical: "]:
                if investigation_name.startswith(prefix):
                    investigation_name = investigation_name[len(prefix):]

            input_data["workup_warnings"].append({
                "investigation": investigation_name,
                "priority": source_layer,
                "full_text": suggestion_text,
                "rationale": suggestion.get("rationale", "")
            })

        # Red flags
        if suggestion_type == "red_flag" or category == "red_flag":
            input_data["red_flag_warnings"].append({
                "flag": suggestion_text,
                "priority": source_layer,
                "rationale": suggestion.get("rationale", "")
            })

    # Count total medications from prescription segment
    if prescription_segment and isinstance(prescription_segment, list):
        input_data["total_medications"] = len(prescription_segment)

    return input_data


# =============================================================================
# DATABASE INTEGRATION
# =============================================================================

async def calculate_and_save_care_quality(
    extraction_id: uuid.UUID,
    consultation_insights: Dict[str, Any],
    doctor_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None
) -> Optional[uuid.UUID]:
    """
    Calculate care quality risk using AI insights and save to database.

    Main entry point for background task integration.
    Uses AI-extracted consultation insights for enhanced severity detection.

    Args:
        extraction_id: UUID of the medical extraction
        consultation_insights: AI-extracted consultation insights (REQUIRED)
        doctor_id: Optional doctor UUID
        patient_id: Optional patient UUID

    Returns:
        UUID of saved assessment, or None on error
    """
    from services.supabase_service import (
        get_extraction_segments,
        get_triage_suggestions_by_extraction,
        get_clinical_severity_by_extraction,
        save_care_quality_risk,
    )

    try:
        start_time = datetime.utcnow()

        # Fetch extraction segments (returns list of segment records)
        segment_list = get_extraction_segments(extraction_id)
        if not segment_list:
            logger.warning(
                f"[CARE_QUALITY] No segments found for extraction_id={extraction_id}. "
                f"Skipping care quality assessment."
            )
            return None

        # Convert list to dict keyed by segment_code
        segments = {}
        for seg in segment_list:
            code = seg.get("segment_code")
            if code:
                segments[code] = seg.get("segment_value")

        # Extract relevant segments
        warnings_segment = segments.get("WARNINGS") or segments.get("warnings")
        diagnosis_segment = segments.get("DIAGNOSIS") or segments.get("diagnosis")
        prescription_segment = segments.get("PRESCRIPTION") or segments.get("prescription")
        treatment_plan_segment = segments.get("TREATMENT_PLAN") or segments.get("treatmentPlan")
        follow_up_segment = segments.get("FOLLOW_UP") or segments.get("followUp")

        # Fetch triage suggestions
        triage_suggestions = get_triage_suggestions_by_extraction(extraction_id)

        # Fetch clinical severity (if exists)
        clinical_severity = get_clinical_severity_by_extraction(extraction_id)

        # Calculate care quality risk with AI-enhanced severity detection
        result = calculate_care_quality_risk(
            warnings_segment=warnings_segment,
            triage_suggestions=triage_suggestions,
            diagnosis_segment=diagnosis_segment,
            prescription_segment=prescription_segment,
            treatment_plan_segment=treatment_plan_segment,
            follow_up_segment=follow_up_segment,
            clinical_severity=clinical_severity,
            consultation_insights=consultation_insights
        )

        # Prepare data for database
        assessment_data = {
            "extraction_id": str(extraction_id),
            "patient_id": str(patient_id) if patient_id else None,
            "doctor_id": str(doctor_id) if doctor_id else None,
            "care_quality_score": result.care_quality_score,
            "risk_level": result.risk_level.value,
            "is_medication_issue": result.is_medication_issue,
            "is_missed_red_flag": result.is_missed_red_flag,
            "is_incomplete_treatment": result.is_incomplete_treatment,
            "is_followup_gap": result.is_followup_gap,
            "medication_issue_reasons": result.medication_issue_reasons,
            "missed_red_flag_reasons": result.missed_red_flag_reasons,
            "incomplete_treatment_reasons": result.incomplete_treatment_reasons,
            "followup_gap_reasons": result.followup_gap_reasons,
            "medication_issue_severity": result.medication_issue_severity,
            "missed_red_flag_severity": result.missed_red_flag_severity,
            "incomplete_treatment_severity": result.incomplete_treatment_severity,
            "followup_gap_severity": result.followup_gap_severity,
            "reasons": result.reasons,
            "base_score": result.base_score,
            "indicator_count": result.indicator_count,
            "primary_risk_driver": result.primary_risk_driver,
            "input_data": _extract_specific_warnings(
                warnings_segment=warnings_segment,
                triage_suggestions=triage_suggestions,
                consultation_insights=consultation_insights,
                diagnosis_segment=diagnosis_segment,
                prescription_segment=prescription_segment
            ),
            "calculation_version": "2.0.0"  # AI-enhanced version
        }

        # Save to database
        assessment_id = save_care_quality_risk(assessment_data)

        elapsed = (datetime.utcnow() - start_time).total_seconds()

        logger.info(
            f"[CARE_QUALITY] ✓ Saved assessment {assessment_id} for extraction {extraction_id}: "
            f"{result.risk_level.value} (score={result.care_quality_score:.1f}%, "
            f"indicators={result.indicator_count}) in {elapsed:.2f}s"
        )

        return assessment_id

    except Exception as e:
        logger.error(
            f"[CARE_QUALITY] ✗ Failed to calculate/save for extraction {extraction_id}: {e}",
            exc_info=True
        )
        return None


# =============================================================================
# MODULE INFO
# =============================================================================

__version__ = "2.0.0"
__all__ = [
    # Enums
    "RiskLevel",

    # Data classes
    "CareQualityResult",

    # Checker functions
    "check_medication_issue",
    "check_missed_red_flag",
    "check_incomplete_treatment",
    "check_followup_gap",

    # Main functions
    "calculate_care_quality_risk",
    "calculate_and_save_care_quality",
]

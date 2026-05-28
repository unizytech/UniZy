"""
Revenue Interventions Service

Generates revenue-related interventions based on assessment scores.

NEW 7-CATEGORY SYSTEM:
- OP_TO_IP: SURGICAL_CONSULTATION (potential OP to IP conversion)
- FOLLOWUP_DUE: SECOND_OPINION_CONSULT, ALTERNATIVE_TREATMENT_CONSULT, SPECIALIST_REFERRAL_NEEDED
- RX_REFILL: PRESCRIPTION_REFILL_REMINDER
- DIAGNOSTICS_DUE: HOME_DIAGNOSTIC_COLLECTION, RECURRING_TEST_SCHEDULE
- ALLIED_HEALTH: 9 allied health referrals + CHRONIC_CARE_PROGRAM

Assessment Sources:
- Allied Health Services (10 types) - from allied_health_needs + CHRONIC_CARE_PROGRAM
- Clinical Upsell (4 types) - from clinical_severity
- Diagnostics & Rx (3 types) - from other_clinical_needs
- Specialist Referral (1 type) - from care_quality_risk

Priority Adjustments:
- Financial Concerns: If patient has HIGH or MEDIUM financial concerns (from emotion analysis),
  allied health intervention priorities are downgraded:
  - HIGH → MEDIUM
  - MEDIUM → LOW
  - LOW → LOW (unchanged)
  Rationale: Patients struggling with main treatment costs are unlikely to purchase
  additional allied health services.

Author: Unizy Health
Version: 2.0.0
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


def _clean_reason_text(reason: str) -> str:
    """
    Clean up reason text by removing technical markers.

    Removes:
    - [POTENTIAL] prefix
    - "- may benefit from..." suffix
    - Excessive whitespace
    """
    if not reason:
        return reason

    cleaned = reason

    # Remove [POTENTIAL] prefix
    cleaned = re.sub(r'^\[POTENTIAL\]\s*', '', cleaned)

    # Remove "- may benefit from..." suffix
    cleaned = re.sub(r'\s*-\s*may benefit from.*$', '', cleaned, flags=re.IGNORECASE)

    # Clean up whitespace
    cleaned = cleaned.strip()

    return cleaned if cleaned else reason


# =============================================================================
# INTERVENTION DEFINITIONS
# =============================================================================

@dataclass
class InterventionDefinition:
    """Definition for a revenue intervention type."""
    intervention_type: str
    sub_type: str  # allied_health, clinical_upsell, diagnostics_rx
    priority: str  # CRITICAL, HIGH, MEDIUM, LOW
    reason_template: str
    action_template: str


# Allied Health Services (9 types) - triggered by allied_health_needs assessment
ALLIED_HEALTH_INTERVENTIONS: Dict[str, InterventionDefinition] = {
    "NUTRITIONAL_REFERRAL": InterventionDefinition(
        intervention_type="NUTRITIONAL_REFERRAL",
        sub_type="allied_health",
        priority="HIGH",
        reason_template="Patient has {condition} requiring dietary guidance",
        action_template="Schedule nutritional counseling appointment"
    ),
    "PHYSIOTHERAPY_REFERRAL": InterventionDefinition(
        intervention_type="PHYSIOTHERAPY_REFERRAL",
        sub_type="allied_health",
        priority="HIGH",
        reason_template="Patient has {condition}",
        action_template="Schedule physiotherapy evaluation"
    ),
    "MENTAL_HEALTH_REFERRAL": InterventionDefinition(
        intervention_type="MENTAL_HEALTH_REFERRAL",
        sub_type="allied_health",
        priority="HIGH",
        reason_template="Patient shows signs of {indicator}",
        action_template="Refer to mental health specialist"
    ),
    "SLEEP_CLINIC_REFERRAL": InterventionDefinition(
        intervention_type="SLEEP_CLINIC_REFERRAL",
        sub_type="allied_health",
        priority="MEDIUM",
        reason_template="Patient reports {symptoms} suggesting sleep disorder",
        action_template="Schedule sleep study consultation"
    ),
    "CARDIAC_REHAB_REFERRAL": InterventionDefinition(
        intervention_type="CARDIAC_REHAB_REFERRAL",
        sub_type="allied_health",
        priority="HIGH",
        reason_template="Patient had {event} and would benefit from cardiac rehabilitation",
        action_template="Enroll in cardiac rehabilitation program"
    ),
    "GENERAL_REHAB_REFERRAL": InterventionDefinition(
        intervention_type="GENERAL_REHAB_REFERRAL",
        sub_type="allied_health",
        priority="MEDIUM",
        reason_template="Patient requires rehabilitation following {condition}",
        action_template="Schedule rehabilitation assessment"
    ),
    "HOMECARE_SERVICES": InterventionDefinition(
        intervention_type="HOMECARE_SERVICES",
        sub_type="allied_health",
        priority="MEDIUM",
        reason_template="Patient (age {age}) with {condition} needs home-based care support",
        action_template="Arrange home healthcare services"
    ),
    "WELLNESS_PROGRAM": InterventionDefinition(
        intervention_type="WELLNESS_PROGRAM",
        sub_type="allied_health",
        priority="LOW",
        reason_template="Patient has lifestyle risk factors for {conditions}",
        action_template="Enroll in wellness and prevention program"
    ),
    "TREATMENT_EDUCATION_PROGRAM": InterventionDefinition(
        intervention_type="TREATMENT_EDUCATION_PROGRAM",
        sub_type="allied_health",
        priority="LOW",
        reason_template="Patient shows difficulty understanding {aspect}",
        action_template="Schedule patient education session"
    ),
}

# Clinical Upsell (4 types) - triggered by clinical_severity assessment
CLINICAL_UPSELL_INTERVENTIONS: Dict[str, InterventionDefinition] = {
    "SURGICAL_CONSULTATION": InterventionDefinition(
        intervention_type="SURGICAL_CONSULTATION",
        sub_type="clinical_upsell",
        priority="HIGH",
        reason_template="Patient's {condition} may require surgical intervention",
        action_template="Schedule surgical consultation"
    ),
    "SECOND_OPINION_CONSULT": InterventionDefinition(
        intervention_type="SECOND_OPINION_CONSULT",
        sub_type="clinical_upsell",
        priority="HIGH",
        reason_template="Complex diagnosis warrants second opinion for {condition}",
        action_template="Facilitate second opinion consultation"
    ),
    "ALTERNATIVE_TREATMENT_CONSULT": InterventionDefinition(
        intervention_type="ALTERNATIVE_TREATMENT_CONSULT",
        sub_type="clinical_upsell",
        priority="MEDIUM",
        reason_template="Alternative treatment options available for {condition}",
        action_template="Discuss alternative treatment approaches"
    ),
    "CHRONIC_CARE_PROGRAM": InterventionDefinition(
        intervention_type="CHRONIC_CARE_PROGRAM",
        sub_type="clinical_upsell",
        priority="MEDIUM",
        reason_template="Patient has {condition} requiring ongoing management",
        action_template="Enroll in chronic care management program"
    ),
}

# Diagnostics & Rx (3 types) - triggered by other_clinical_needs assessment
DIAGNOSTICS_RX_INTERVENTIONS: Dict[str, InterventionDefinition] = {
    "HOME_DIAGNOSTIC_COLLECTION": InterventionDefinition(
        intervention_type="HOME_DIAGNOSTIC_COLLECTION",
        sub_type="diagnostics_rx",
        priority="MEDIUM",
        reason_template="Patient requires {tests} - home collection available",
        action_template="Arrange home sample collection"
    ),
    "PRESCRIPTION_REFILL_REMINDER": InterventionDefinition(
        intervention_type="PRESCRIPTION_REFILL_REMINDER",
        sub_type="diagnostics_rx",
        priority="LOW",
        reason_template="Patient on {count} medications needs refill coordination",
        action_template="Set up prescription refill reminders"
    ),
    "RECURRING_TEST_SCHEDULE": InterventionDefinition(
        intervention_type="RECURRING_TEST_SCHEDULE",
        sub_type="diagnostics_rx",
        priority="LOW",
        reason_template="Patient needs periodic {test_type} monitoring for {condition}",
        action_template="Schedule recurring diagnostic tests"
    ),
}

# Specialist Referral (1 type) - triggered by care_quality_risk assessment (moved from QUALITY)
SPECIALIST_REFERRAL_INTERVENTIONS: Dict[str, InterventionDefinition] = {
    "SPECIALIST_REFERRAL_NEEDED": InterventionDefinition(
        intervention_type="SPECIALIST_REFERRAL_NEEDED",
        sub_type="specialist_referral",
        priority="MEDIUM",
        reason_template="Patient condition warrants specialist referral for {specialty}",
        action_template="Initiate specialist referral process"
    ),
}

# Priority score mapping
PRIORITY_SCORES = {
    "CRITICAL": 95,
    "HIGH": 80,
    "MEDIUM": 60,
    "LOW": 40
}


# =============================================================================
# INTERVENTION GENERATION
# =============================================================================

def _extract_evidence_from_insights(
    consultation_insights: Optional[Dict[str, Any]],
    signal_group: str,
    evidence_fields: List[str] = None
) -> List[Dict[str, str]]:
    """
    Extract evidence/quotes from consultation_insights for compelling rationale.

    The consultation_insights schema has 14 signal groups, each with specific evidence fields:
    - clinical_severity_signals: chronic_evidence, surgical_evidence, urgency_evidence
    - mental_health_signals: mental_health_evidence, anxiety_indicators
    - nutritional_signals: metabolic_conditions, diet_instruction_summary
    - physiotherapy_signals: physiotherapy_evidence
    - rehabilitation_signals: rehab_evidence
    - education_signals: education_evidence, understanding_barrier_evidence
    - etc.

    Args:
        consultation_insights: Raw consultation insights dict
        signal_group: Name of signal group (e.g., "clinical_severity_signals", "mental_health_signals")
        evidence_fields: List of field names to try within the signal group

    Returns:
        List of evidence dicts with 'source' and 'content' keys
    """
    if not consultation_insights:
        return []

    evidence_list = []
    signal_data = consultation_insights.get(signal_group, {})

    if not signal_data:
        return []

    # Default evidence fields to try
    if evidence_fields is None:
        evidence_fields = ["evidence", "chronic_evidence", "mental_health_evidence",
                          "physiotherapy_evidence", "rehab_evidence", "education_evidence",
                          "understanding_barrier_evidence", "anxiety_indicators"]

    # Try each evidence field
    for evidence_field in evidence_fields:
        evidence = signal_data.get(evidence_field)
        if not evidence:
            continue

        # Handle both list and string evidence
        if isinstance(evidence, list):
            for item in evidence:
                if item and str(item).strip():
                    evidence_list.append({
                        "source": f"{signal_group}.{evidence_field}",
                        "content": str(item).strip()
                    })
        elif isinstance(evidence, str) and evidence.strip():
            evidence_list.append({
                "source": f"{signal_group}.{evidence_field}",
                "content": evidence.strip()
            })

    return evidence_list


def _get_evidence_for_intervention_type(
    consultation_insights: Optional[Dict[str, Any]],
    intervention_type: str
) -> List[Dict[str, str]]:
    """
    Get relevant evidence from consultation_insights based on intervention type.

    Maps intervention types to the correct signal groups and evidence fields.
    """
    if not consultation_insights:
        return []

    # Map intervention types to signal groups and evidence fields
    INTERVENTION_EVIDENCE_MAP = {
        # Clinical upsell interventions -> clinical_severity_signals
        "CHRONIC_CARE_PROGRAM": ("clinical_severity_signals", ["chronic_evidence"]),
        "SURGICAL_CONSULTATION": ("clinical_severity_signals", ["surgical_evidence"]),
        "SECOND_OPINION_CONSULT": ("clinical_severity_signals", ["second_opinion_evidence", "icd_validation"]),
        "ALTERNATIVE_TREATMENT_CONSULT": ("clinical_severity_signals", ["alternate_treatment_evidence"]),

        # Allied health interventions -> specific signal groups
        "MENTAL_HEALTH_REFERRAL": ("mental_health_signals", ["mental_health_evidence", "anxiety_indicators"]),
        "NUTRITIONAL_REFERRAL": ("nutritional_signals", ["metabolic_conditions", "diet_instruction_summary", "icd_validation"]),
        "PHYSIOTHERAPY_REFERRAL": ("physiotherapy_signals", ["physiotherapy_evidence", "icd_validation"]),
        "HOMECARE_SERVICES": ("homecare_signals", ["mobility_evidence"]),
        "SLEEP_CLINIC_REFERRAL": ("sleep_signals", ["sleep_evidence", "sleep_symptoms"]),
        "CARDIAC_REHAB_REFERRAL": ("rehabilitation_signals", ["rehab_evidence", "cardiac_event_type"]),
        "GENERAL_REHAB_REFERRAL": ("rehabilitation_signals", ["rehab_evidence"]),
        "WELLNESS_PROGRAM": ("wellness_signals", ["wellness_evidence", "lifestyle_diseases"]),
        "TREATMENT_EDUCATION_PROGRAM": ("education_signals", ["education_evidence", "understanding_barrier_evidence"]),

        # Diagnostics interventions -> diagnostic_needs
        "HOME_DIAGNOSTIC_COLLECTION": ("diagnostic_needs", ["ordered_tests", "recurring_monitoring_evidence"]),
        "PRESCRIPTION_REFILL_REMINDER": ("medication_signals", ["refill_evidence", "long_term_medication_names"]),
        "RECURRING_TEST_SCHEDULE": ("diagnostic_needs", ["recurring_monitoring_type", "recurring_monitoring_evidence"]),

        # Specialist referral
        "SPECIALIST_REFERRAL_NEEDED": ("clinical_severity_signals", ["second_opinion_evidence", "icd_validation"]),
    }

    if intervention_type not in INTERVENTION_EVIDENCE_MAP:
        return []

    signal_group, evidence_fields = INTERVENTION_EVIDENCE_MAP[intervention_type]
    return _extract_evidence_from_insights(consultation_insights, signal_group, evidence_fields)


def _format_evidence_for_rationale(evidence_list: List[Dict[str, str]]) -> str:
    """Format evidence list into human-readable string with quotes.

    Note: No truncation applied - full evidence text is preserved for
    complete context in trigger_reason field.
    """
    if not evidence_list:
        return ""

    quotes = []
    for ev in evidence_list[:3]:  # Limit to 3 quotes
        content = ev.get("content", "")
        if content:
            # No truncation - preserve full text for complete context
            quotes.append(f'"{content}"')

    return " | ".join(quotes)


def _evidence_to_string_list(evidence_list: List[Dict[str, str]]) -> List[str]:
    """Convert evidence objects to list of strings for storage.

    Converts [{"content": "...", "source": "..."}] to ["quote text", "quote text"]
    for proper display in frontend.
    """
    if not evidence_list:
        return []

    strings = []
    for ev in evidence_list:
        content = ev.get("content", "")
        if content:
            # No truncation - preserve full text for complete context
            strings.append(content)

    return strings


def generate_revenue_interventions(
    allied_health_needs: Optional[Dict[str, Any]],
    clinical_severity: Optional[Dict[str, Any]],
    other_clinical_needs: Optional[Dict[str, Any]],
    hospital_pricing: Dict[str, Dict[str, Any]],
    consultation_insights_id: Optional[uuid.UUID] = None,
    care_quality_risk: Optional[Dict[str, Any]] = None,
    financial_concerns_level: Optional[str] = None,
    consultation_insights: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Generate revenue interventions based on assessment scores.

    Args:
        allied_health_needs: Allied health needs assessment record
        clinical_severity: Clinical severity assessment record
        other_clinical_needs: Other clinical needs assessment record
        hospital_pricing: Dict mapping intervention_type -> {revenue_estimate, service_name}
        consultation_insights_id: Optional FK to consultation_insights
        care_quality_risk: Care quality risk assessment (for specialist referral)
        financial_concerns_level: "high" or "medium" if financial concerns detected.
            When present, allied health priorities are downgraded since patients
            with financial concerns for main treatment are unlikely to purchase
            additional allied health services.
        consultation_insights: Raw consultation_insights dict for extracting
            evidence/quotes to include in intervention rationale.

    Returns:
        List of intervention dicts ready for save_categorized_intervention()
    """
    interventions = []

    # Extract severity level for priority adjustments
    severity_level = None
    if clinical_severity:
        severity_level = clinical_severity.get("severity_level", "MILD")

    # 1. Allied Health Services (from allied_health_needs)
    # Priority downgraded if patient has financial concerns
    if allied_health_needs:
        interventions.extend(
            _generate_allied_health_interventions(
                allied_health_needs,
                hospital_pricing,
                consultation_insights_id,
                financial_concerns_level,
                consultation_insights
            )
        )

    # 2. Clinical Upsell (from clinical_severity)
    if clinical_severity:
        interventions.extend(
            _generate_clinical_upsell_interventions(
                clinical_severity,
                hospital_pricing,
                consultation_insights_id,
                consultation_insights
            )
        )

    # 3. Diagnostics & Rx (from other_clinical_needs)
    if other_clinical_needs:
        interventions.extend(
            _generate_diagnostics_rx_interventions(
                other_clinical_needs,
                hospital_pricing,
                consultation_insights_id,
                consultation_insights
            )
        )

    # 4. Specialist Referral (from care_quality_risk, moved from QUALITY)
    if care_quality_risk:
        interventions.extend(
            _generate_specialist_referral_interventions(
                care_quality_risk,
                hospital_pricing,
                consultation_insights_id,
                severity_level,
                consultation_insights
            )
        )

    logger.info(f"[REVENUE] Generated {len(interventions)} revenue interventions")
    return interventions


def _generate_allied_health_interventions(
    assessment: Dict[str, Any],
    pricing: Dict[str, Dict[str, Any]],
    insights_id: Optional[uuid.UUID],
    financial_concerns_level: Optional[str] = None,
    consultation_insights: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Generate allied health service interventions.

    Priority Adjustment for Financial Concerns:
    - If financial_concerns_level is "high" or "medium", priorities are downgraded
    - Rationale: Patients with financial concerns for main treatment are unlikely
      to purchase additional allied health services
    - HIGH → MEDIUM, MEDIUM → LOW, LOW → LOW (unchanged)

    Evidence from consultation_insights (allied_health_signals) is included
    in the rationale for compelling intervention reasons.
    """
    interventions = []
    assessment_id = assessment.get("id")

    # Only generate if priority is HIGH or MEDIUM
    priority_level = assessment.get("priority_level", "NONE")
    if priority_level not in ("HIGH", "MEDIUM"):
        return []

    # Determine if we should downgrade priorities due to financial concerns
    downgrade_for_financial = financial_concerns_level in ("high", "medium")
    if downgrade_for_financial:
        logger.info(
            f"[ALLIED_HEALTH] Financial concerns detected ({financial_concerns_level}) - "
            f"downgrading allied health priorities"
        )

    # Map assessment flags to intervention types
    flag_mappings = [
        ("is_nutritional_health", "NUTRITIONAL_REFERRAL", "nutritional_health_reasons", "metabolic condition"),
        ("is_physiotherapy", "PHYSIOTHERAPY_REFERRAL", "physiotherapy_reasons", "musculoskeletal condition"),
        ("is_mental_health", "MENTAL_HEALTH_REFERRAL", "mental_health_reasons", "mental health indicators"),
        ("is_sleep_therapy", "SLEEP_CLINIC_REFERRAL", "sleep_therapy_reasons", "sleep symptoms"),
        ("is_rehab_cardiac", "CARDIAC_REHAB_REFERRAL", "rehab_cardiac_reasons", "cardiac event"),
        ("is_rehab_common", "GENERAL_REHAB_REFERRAL", "rehab_common_reasons", "rehabilitation needs"),
        ("is_homecare", "HOMECARE_SERVICES", "homecare_reasons", "homecare needs"),
        ("is_wellness", "WELLNESS_PROGRAM", "wellness_reasons", "lifestyle risk factors"),
        ("is_treatment_education", "TREATMENT_EDUCATION_PROGRAM", "treatment_education_reasons", "treatment understanding"),
    ]

    for flag_name, intervention_type, reasons_field, default_condition in flag_mappings:
        if assessment.get(flag_name, False):
            definition = ALLIED_HEALTH_INTERVENTIONS[intervention_type]
            reasons = assessment.get(reasons_field, [])

            # Build reason from assessment data - clean up [POTENTIAL] markers
            raw_condition = reasons[0] if reasons else default_condition
            condition = _clean_reason_text(raw_condition)
            base_reason = definition.reason_template.format(
                condition=condition,
                indicator=condition,
                symptoms=condition,
                event=condition,
                age=assessment.get("patient_age", "elderly"),
                conditions=condition,
                aspect=condition
            )

            # Extract evidence from consultation_insights for compelling rationale
            # Use intervention-specific signal group mapping
            evidence = _get_evidence_for_intervention_type(consultation_insights, intervention_type)
            evidence_text = _format_evidence_for_rationale(evidence)

            # Append evidence to reason if available
            trigger_reason = base_reason
            if evidence_text:
                trigger_reason += f" - Evidence: {evidence_text}"

            # Get pricing
            price_info = pricing.get(intervention_type, {})

            # Apply priority downgrade if financial concerns detected
            # HIGH → MEDIUM, MEDIUM → LOW, LOW → LOW
            priority = definition.priority
            priority_downgraded = False
            if downgrade_for_financial:
                if priority == "HIGH":
                    priority = "MEDIUM"
                    priority_downgraded = True
                elif priority == "MEDIUM":
                    priority = "LOW"
                    priority_downgraded = True
                # LOW stays LOW, CRITICAL stays CRITICAL (safety-related)

            priority_score = PRIORITY_SCORES.get(priority, 50)

            # Build rationale sources - clean reasons for consistency
            cleaned_reasons = [_clean_reason_text(r) for r in reasons] if reasons else []
            rationale = {"reasons": cleaned_reasons, "flag": flag_name, "evidence_quotes": _evidence_to_string_list(evidence)}
            if priority_downgraded:
                rationale["priority_downgraded"] = True
                rationale["original_priority"] = definition.priority
                rationale["downgrade_reason"] = f"financial_concerns_{financial_concerns_level}"

            interventions.append({
                "intervention_code": intervention_type,
                "intervention_category": "ALLIED_HEALTH",  # New 7-category system
                "intervention_sub_type": definition.sub_type,
                "priority_level": priority,
                "priority_score": priority_score,
                "trigger_reason": trigger_reason,
                "action": definition.action_template,
                "revenue_estimate": price_info.get("revenue_estimate"),
                "consultation_insights_id": insights_id,
                "linked_assessment_type": "allied_health_needs",
                "linked_assessment_id": assessment_id,
                "rationale_sources": rationale
            })

    return interventions


# Category mapping for clinical upsell interventions
CLINICAL_UPSELL_CATEGORY_MAP = {
    "SURGICAL_CONSULTATION": "OP_TO_IP",           # Potential OP to IP conversion
    "SECOND_OPINION_CONSULT": "FOLLOWUP_DUE",      # Needs follow-up consultation
    "ALTERNATIVE_TREATMENT_CONSULT": "FOLLOWUP_DUE",  # Needs follow-up consultation
    "CHRONIC_CARE_PROGRAM": "ALLIED_HEALTH",       # Allied health program enrollment
}


def _generate_clinical_upsell_interventions(
    assessment: Dict[str, Any],
    pricing: Dict[str, Dict[str, Any]],
    insights_id: Optional[uuid.UUID],
    consultation_insights: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Generate clinical upsell interventions with evidence from consultation_insights."""
    interventions = []
    assessment_id = assessment.get("id")

    # Get severity info
    severity_level = assessment.get("severity_level", "MILD")
    severity_score = assessment.get("severity_score", 0)

    # Only generate for MODERATE or higher severity, or specific flags
    if severity_level in ("MILD", "NONE") and severity_score < 4:
        # Still check for specific flags
        pass

    # Map assessment flags to intervention types
    flag_mappings = [
        ("is_surgical", "SURGICAL_CONSULTATION", "surgical condition"),
        ("is_second_opinion", "SECOND_OPINION_CONSULT", "complex diagnosis"),
        ("is_alternate_procedure", "ALTERNATIVE_TREATMENT_CONSULT", "current treatment"),
        ("is_chronic", "CHRONIC_CARE_PROGRAM", "chronic condition"),
    ]

    for flag_name, intervention_type, default_condition in flag_mappings:
        if assessment.get(flag_name, False):
            definition = CLINICAL_UPSELL_INTERVENTIONS[intervention_type]

            # Get condition from assessment
            input_data = assessment.get("input_data", {}) or {}
            primary_diagnosis = input_data.get("primary_diagnosis", default_condition)

            base_reason = definition.reason_template.format(condition=primary_diagnosis)

            # Extract evidence from consultation_insights using intervention-specific mapping
            evidence = _get_evidence_for_intervention_type(consultation_insights, intervention_type)
            evidence_text = _format_evidence_for_rationale(evidence)

            # Append evidence to reason if available
            trigger_reason = base_reason
            if evidence_text:
                trigger_reason += f" - Evidence: {evidence_text}"

            # Get pricing
            price_info = pricing.get(intervention_type, {})

            # Get category from mapping (OP_TO_IP, FOLLOWUP_DUE, or ALLIED_HEALTH)
            category = CLINICAL_UPSELL_CATEGORY_MAP.get(intervention_type, "FOLLOWUP_DUE")

            interventions.append({
                "intervention_code": intervention_type,
                "intervention_category": category,  # New 7-category system
                "intervention_sub_type": definition.sub_type,
                "priority_level": definition.priority,
                "priority_score": PRIORITY_SCORES.get(definition.priority, 50),
                "trigger_reason": trigger_reason,
                "action": definition.action_template,
                "revenue_estimate": price_info.get("revenue_estimate"),
                "consultation_insights_id": insights_id,
                "linked_assessment_type": "clinical_severity",
                "linked_assessment_id": assessment_id,
                "rationale_sources": {
                    "severity_level": severity_level,
                    "flag": flag_name,
                    "evidence_quotes": _evidence_to_string_list(evidence)
                }
            })

    return interventions


def _generate_diagnostics_rx_interventions(
    assessment: Dict[str, Any],
    pricing: Dict[str, Dict[str, Any]],
    insights_id: Optional[uuid.UUID],
    consultation_insights: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Generate diagnostics and prescription interventions with evidence."""
    interventions = []
    assessment_id = assessment.get("id")

    # Only generate if priority is HIGH or MEDIUM
    priority_level = assessment.get("priority_level", "NONE")
    if priority_level not in ("HIGH", "MEDIUM"):
        return []

    # Evidence will be extracted per intervention type below

    # Home diagnostic collection
    if assessment.get("is_followup_diagnostics") or assessment.get("is_recurring_diagnostics"):
        definition = DIAGNOSTICS_RX_INTERVENTIONS["HOME_DIAGNOSTIC_COLLECTION"]
        tests = assessment.get("followup_diagnostics_reasons", [])
        test_names = ", ".join(tests[:3]) if tests else "follow-up tests"

        base_reason = definition.reason_template.format(tests=test_names)
        evidence = _get_evidence_for_intervention_type(consultation_insights, "HOME_DIAGNOSTIC_COLLECTION")
        evidence_text = _format_evidence_for_rationale(evidence)
        trigger_reason = base_reason
        if evidence_text:
            trigger_reason += f" - Evidence: {evidence_text}"

        price_info = pricing.get("HOME_DIAGNOSTIC_COLLECTION", {})

        interventions.append({
            "intervention_code": "HOME_DIAGNOSTIC_COLLECTION",
            "intervention_category": "DIAGNOSTICS_DUE",  # New 7-category system
            "intervention_sub_type": definition.sub_type,
            "priority_level": definition.priority,
            "priority_score": PRIORITY_SCORES.get(definition.priority, 50),
            "trigger_reason": trigger_reason,
            "action": definition.action_template,
            "revenue_estimate": price_info.get("revenue_estimate"),
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "other_clinical_needs",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {"tests": tests, "evidence_quotes": _evidence_to_string_list(evidence)}
        })

    # Prescription refill reminder (for chronic/complex medication regimens)
    if assessment.get("is_rx_refill"):
        # Check if medication count is significant
        input_data = assessment.get("input_data", {}) or {}
        med_count = input_data.get("medication_count", 0)

        if med_count >= 3:  # Only for patients on 3+ medications
            definition = DIAGNOSTICS_RX_INTERVENTIONS["PRESCRIPTION_REFILL_REMINDER"]
            base_reason = definition.reason_template.format(count=med_count)
            evidence = _get_evidence_for_intervention_type(consultation_insights, "PRESCRIPTION_REFILL_REMINDER")
            evidence_text = _format_evidence_for_rationale(evidence)
            trigger_reason = base_reason
            if evidence_text:
                trigger_reason += f" - Evidence: {evidence_text}"

            price_info = pricing.get("PRESCRIPTION_REFILL_REMINDER", {})

            interventions.append({
                "intervention_code": "PRESCRIPTION_REFILL_REMINDER",
                "intervention_category": "RX_REFILL",  # New 7-category system
                "intervention_sub_type": definition.sub_type,
                "priority_level": definition.priority,
                "priority_score": PRIORITY_SCORES.get(definition.priority, 50),
                "trigger_reason": trigger_reason,
                "action": definition.action_template,
                "revenue_estimate": price_info.get("revenue_estimate"),
                "consultation_insights_id": insights_id,
                "linked_assessment_type": "other_clinical_needs",
                "linked_assessment_id": assessment_id,
                "rationale_sources": {"medication_count": med_count, "evidence_quotes": _evidence_to_string_list(evidence)}
            })

    # Recurring test schedule
    if assessment.get("is_recurring_diagnostics"):
        definition = DIAGNOSTICS_RX_INTERVENTIONS["RECURRING_TEST_SCHEDULE"]
        tests = assessment.get("recurring_diagnostics_reasons", [])
        test_type = tests[0] if tests else "routine monitoring"

        # Get condition from chronic status
        input_data = assessment.get("input_data", {}) or {}
        condition = input_data.get("chronic_condition", "ongoing condition")

        base_reason = definition.reason_template.format(test_type=test_type, condition=condition)
        evidence = _get_evidence_for_intervention_type(consultation_insights, "RECURRING_TEST_SCHEDULE")
        evidence_text = _format_evidence_for_rationale(evidence)
        trigger_reason = base_reason
        if evidence_text:
            trigger_reason += f" - Evidence: {evidence_text}"

        price_info = pricing.get("RECURRING_TEST_SCHEDULE", {})

        interventions.append({
            "intervention_code": "RECURRING_TEST_SCHEDULE",
            "intervention_category": "DIAGNOSTICS_DUE",  # New 7-category system
            "intervention_sub_type": definition.sub_type,
            "priority_level": definition.priority,
            "priority_score": PRIORITY_SCORES.get(definition.priority, 50),
            "trigger_reason": trigger_reason,
            "action": definition.action_template,
            "revenue_estimate": price_info.get("revenue_estimate"),
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "other_clinical_needs",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {"recurring_tests": tests, "evidence_quotes": _evidence_to_string_list(evidence)}
        })

    return interventions


def _generate_specialist_referral_interventions(
    care_quality_risk: Dict[str, Any],
    pricing: Dict[str, Dict[str, Any]],
    insights_id: Optional[uuid.UUID],
    severity_level: Optional[str] = None,
    consultation_insights: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Generate specialist referral intervention.
    Moved from QUALITY category to REVENUE.

    SEVERITY BOOST: Priority boosted to HIGH if severity is SEVERE/CRITICAL

    Args:
        care_quality_risk: Care quality risk assessment record
        pricing: Hospital pricing dictionary
        insights_id: FK to consultation_insights
        severity_level: Clinical severity level for priority adjustments
        consultation_insights: Raw consultation_insights for evidence extraction

    Returns:
        List of intervention dicts
    """
    interventions = []
    assessment_id = care_quality_risk.get("id")
    input_data = care_quality_risk.get("input_data", {}) or {}

    is_high_severity = severity_level in ("SEVERE", "CRITICAL")

    # SPECIALIST_REFERRAL_NEEDED
    if care_quality_risk.get("is_referral_risk"):
        definition = SPECIALIST_REFERRAL_INTERVENTIONS["SPECIALIST_REFERRAL_NEEDED"]
        warnings = input_data.get("referral_warnings", [])
        specialty = warnings[0] if warnings else "specialist"

        # Boost priority to HIGH if high severity
        priority = "HIGH" if is_high_severity else definition.priority
        priority_score = PRIORITY_SCORES[priority]

        base_reason = definition.reason_template.format(specialty=specialty)

        # Extract evidence using intervention-specific mapping
        evidence = _get_evidence_for_intervention_type(consultation_insights, "SPECIALIST_REFERRAL_NEEDED")
        evidence_text = _format_evidence_for_rationale(evidence)

        trigger_reason = base_reason
        if evidence_text:
            trigger_reason += f" - Evidence: {evidence_text}"

        # Get pricing
        price_info = pricing.get("SPECIALIST_REFERRAL_NEEDED", {})

        interventions.append({
            "intervention_code": "SPECIALIST_REFERRAL_NEEDED",
            "intervention_category": "FOLLOWUP_DUE",  # New 7-category system
            "intervention_sub_type": definition.sub_type,
            "priority_level": priority,
            "priority_score": priority_score,
            "trigger_reason": trigger_reason,
            "action": definition.action_template,
            "revenue_estimate": price_info.get("revenue_estimate"),
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "care_quality_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {
                "referral_warnings": warnings,
                "severity_level": severity_level,
                "priority_boosted": is_high_severity,
                "evidence_quotes": _evidence_to_string_list(evidence)
            }
        })

    return interventions


# =============================================================================
# MODULE INFO
# =============================================================================

__version__ = "2.0.0"
__author__ = "Unizy Health"
__all__ = [
    "generate_revenue_interventions",
    "ALLIED_HEALTH_INTERVENTIONS",
    "CLINICAL_UPSELL_INTERVENTIONS",
    "DIAGNOSTICS_RX_INTERVENTIONS",
    "SPECIALIST_REFERRAL_INTERVENTIONS",
]

"""
Quality Interventions Service

Generates QUALITY_RISK category interventions to close care gaps.

NEW 7-CATEGORY SYSTEM:
- All quality interventions now use QUALITY_RISK category

Assessment Sources:
- Based on care_quality_risk assessment
- Based on triage warnings from input_data

7 Quality Intervention Types:

Medication Safety (4):
1. CONTRAINDICATION_ALERT - Potential contraindication detected
2. DRUG_INTERACTION_REVIEW - Drug interaction risk
3. POLYPHARMACY_REVIEW - 5+ medications
4. DOSAGE_VERIFICATION - Dosage concerns

Documentation & Protocol (3):
5. MISSING_DIAGNOSIS_ALERT - Treatment without diagnosis
6. PROTOCOL_DEVIATION_REVIEW - Non-standard treatment
7. INCOMPLETE_WORKUP_ALERT - Missing investigations

NOTE: The following interventions were moved to other categories:
- URGENT_FOLLOWUP_NEEDED -> FOLLOWUP_DUE (retention_interventions_service.py)
- PATIENT_EDUCATION_GAP -> RETENTION_RISK (retention_interventions_service.py)
- SPECIALIST_REFERRAL_NEEDED -> FOLLOWUP_DUE (revenue_interventions_service.py)

Author: Unizy Health
Version: 2.0.0
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# =============================================================================
# INTERVENTION DEFINITIONS
# =============================================================================

@dataclass
class QualityInterventionDefinition:
    """Definition for a quality intervention type."""
    intervention_type: str
    sub_type: str  # medication_safety, documentation, followup
    priority: str
    reason_template: str
    action_template: str


QUALITY_INTERVENTIONS: Dict[str, QualityInterventionDefinition] = {
    # Medication Safety (4)
    "CONTRAINDICATION_ALERT": QualityInterventionDefinition(
        intervention_type="CONTRAINDICATION_ALERT",
        sub_type="medication_safety",
        priority="CRITICAL",
        reason_template="Potential contraindication detected: {details}",
        action_template="Urgent pharmacist review required before dispensing"
    ),
    "DRUG_INTERACTION_REVIEW": QualityInterventionDefinition(
        intervention_type="DRUG_INTERACTION_REVIEW",
        sub_type="medication_safety",
        priority="HIGH",
        reason_template="Potential drug interaction between {drug1} and {drug2}",
        action_template="Review prescription with pharmacist"
    ),
    "POLYPHARMACY_REVIEW": QualityInterventionDefinition(
        intervention_type="POLYPHARMACY_REVIEW",
        sub_type="medication_safety",
        priority="MEDIUM",
        reason_template="Patient on {count} medications - polypharmacy risk",
        action_template="Schedule medication reconciliation review"
    ),
    "DOSAGE_VERIFICATION": QualityInterventionDefinition(
        intervention_type="DOSAGE_VERIFICATION",
        sub_type="medication_safety",
        priority="HIGH",
        reason_template="Dosage concern for {medication}: {details}",
        action_template="Verify dosage with prescribing physician"
    ),

    # Documentation & Protocol (3)
    "MISSING_DIAGNOSIS_ALERT": QualityInterventionDefinition(
        intervention_type="MISSING_DIAGNOSIS_ALERT",
        sub_type="documentation",
        priority="HIGH",
        reason_template="Treatment prescribed without documented diagnosis for {treatment}",
        action_template="Request diagnosis documentation from physician"
    ),
    "PROTOCOL_DEVIATION_REVIEW": QualityInterventionDefinition(
        intervention_type="PROTOCOL_DEVIATION_REVIEW",
        sub_type="documentation",
        priority="MEDIUM",
        reason_template="Treatment deviates from standard protocol for {condition}",
        action_template="Flag for clinical review and documentation"
    ),
    "INCOMPLETE_WORKUP_ALERT": QualityInterventionDefinition(
        intervention_type="INCOMPLETE_WORKUP_ALERT",
        sub_type="documentation",
        priority="HIGH",
        reason_template="Recommended investigations not ordered: {missing_tests}",
        action_template="Follow up on pending diagnostic workup"
    ),

    # NOTE: Follow-up interventions moved to other categories:
    # - URGENT_FOLLOWUP_NEEDED -> RETENTION
    # - PATIENT_EDUCATION_GAP -> RETENTION
    # - SPECIALIST_REFERRAL_NEEDED -> REVENUE
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

def generate_quality_interventions(
    care_quality_risk: Optional[Dict[str, Any]],
    consultation_insights_id: Optional[uuid.UUID] = None
) -> List[Dict[str, Any]]:
    """
    Generate quality interventions based on care quality risk assessment.

    The care_quality_risk assessment contains:
    - 18 triage risk flags (is_*_risk fields)
    - Aggregated risk scores
    - input_data with detailed triage warnings

    Args:
        care_quality_risk: Care quality risk assessment record
        consultation_insights_id: Optional FK to consultation_insights

    Returns:
        List of intervention dicts ready for save_categorized_intervention()
    """
    if not care_quality_risk:
        return []

    interventions = []
    assessment_id = care_quality_risk.get("id")
    input_data = care_quality_risk.get("input_data", {}) or {}

    # 1. Medication Safety Interventions
    interventions.extend(
        _generate_medication_safety_interventions(
            care_quality_risk,
            input_data,
            assessment_id,
            consultation_insights_id
        )
    )

    # 2. Documentation & Protocol Interventions
    interventions.extend(
        _generate_documentation_interventions(
            care_quality_risk,
            input_data,
            assessment_id,
            consultation_insights_id
        )
    )

    # NOTE: Follow-up interventions (URGENT_FOLLOWUP_NEEDED, PATIENT_EDUCATION_GAP,
    # SPECIALIST_REFERRAL_NEEDED) have been moved to RETENTION and REVENUE categories

    logger.info(f"[QUALITY] Generated {len(interventions)} quality interventions")
    return interventions


def _generate_medication_safety_interventions(
    assessment: Dict[str, Any],
    input_data: Dict[str, Any],
    assessment_id: Optional[str],
    insights_id: Optional[uuid.UUID]
) -> List[Dict[str, Any]]:
    """
    Generate medication safety interventions.

    Uses broad database field `is_medication_issue` combined with
    specific warnings from `input_data` to determine which interventions to trigger.
    """
    interventions = []
    is_medication_issue = assessment.get("is_medication_issue", False)

    # 1. CONTRAINDICATION_ALERT - triggered by contraindication_warnings or allergy_warnings
    warnings = input_data.get("contraindication_warnings", [])
    allergy_warnings = input_data.get("allergy_warnings", [])
    if warnings or allergy_warnings:
        definition = QUALITY_INTERVENTIONS["CONTRAINDICATION_ALERT"]

        # Extract specific details from structured warnings
        if warnings and isinstance(warnings[0], dict):
            details = warnings[0].get("details", "potential contraindication detected")
        elif allergy_warnings and isinstance(allergy_warnings[0], dict):
            details = allergy_warnings[0].get("details", "allergy alert detected")
        elif warnings:
            details = str(warnings[0])
        else:
            details = "potential contraindication detected"

        interventions.append({
            "intervention_code": "CONTRAINDICATION_ALERT",
            "intervention_category": "QUALITY_RISK",
            "intervention_sub_type": definition.sub_type,
            "priority_level": definition.priority,
            "priority_score": PRIORITY_SCORES[definition.priority],
            "trigger_reason": definition.reason_template.format(details=details),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "care_quality_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {"contraindication_warnings": warnings, "allergy_warnings": allergy_warnings}
        })

    # 2. DRUG_INTERACTION_REVIEW - triggered by drug_interaction_warnings in input_data
    interactions = input_data.get("drug_interaction_warnings", [])
    if interactions:
        definition = QUALITY_INTERVENTIONS["DRUG_INTERACTION_REVIEW"]

        # Parse interaction details
        drug1, drug2 = "prescribed medication", "existing medication"
        if interactions and isinstance(interactions[0], dict):
            drug1 = interactions[0].get("drug1", drug1)
            drug2 = interactions[0].get("drug2", drug2)
        elif interactions:
            # Try to extract from string
            drug1 = str(interactions[0])

        interventions.append({
            "intervention_code": "DRUG_INTERACTION_REVIEW",
            "intervention_category": "QUALITY_RISK",
            "intervention_sub_type": definition.sub_type,
            "priority_level": definition.priority,
            "priority_score": PRIORITY_SCORES[definition.priority],
            "trigger_reason": definition.reason_template.format(drug1=drug1, drug2=drug2),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "care_quality_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {"drug_interaction_warnings": interactions}
        })

    # 3. POLYPHARMACY_REVIEW - triggered when total_medications >= 5
    med_count = input_data.get("total_medications", 0)
    if med_count >= 5:
        definition = QUALITY_INTERVENTIONS["POLYPHARMACY_REVIEW"]

        interventions.append({
            "intervention_code": "POLYPHARMACY_REVIEW",
            "intervention_category": "QUALITY_RISK",
            "intervention_sub_type": definition.sub_type,
            "priority_level": definition.priority,
            "priority_score": PRIORITY_SCORES[definition.priority],
            "trigger_reason": definition.reason_template.format(count=med_count),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "care_quality_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {"medication_count": med_count}
        })

    # 4. DOSAGE_VERIFICATION - triggered by dosage_warnings in input_data
    dosage_warnings = input_data.get("dosage_warnings", [])
    if dosage_warnings:
        definition = QUALITY_INTERVENTIONS["DOSAGE_VERIFICATION"]

        medication = "medication"
        details = "dosage may be outside normal range"
        if dosage_warnings and isinstance(dosage_warnings[0], dict):
            medication = dosage_warnings[0].get("medicine", dosage_warnings[0].get("medication", medication))
            details = dosage_warnings[0].get("details", dosage_warnings[0].get("concern", details))
        elif dosage_warnings:
            details = str(dosage_warnings[0])

        interventions.append({
            "intervention_code": "DOSAGE_VERIFICATION",
            "intervention_category": "QUALITY_RISK",
            "intervention_sub_type": definition.sub_type,
            "priority_level": definition.priority,
            "priority_score": PRIORITY_SCORES[definition.priority],
            "trigger_reason": definition.reason_template.format(medication=medication, details=details),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "care_quality_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {"dosage_warnings": dosage_warnings}
        })

    return interventions


def _generate_documentation_interventions(
    assessment: Dict[str, Any],
    input_data: Dict[str, Any],
    assessment_id: Optional[str],
    insights_id: Optional[uuid.UUID]
) -> List[Dict[str, Any]]:
    """
    Generate documentation and protocol interventions.

    Uses database fields `is_incomplete_treatment` and `is_missed_red_flag`
    combined with specific warnings from `input_data` to determine interventions.
    """
    interventions = []
    is_incomplete_treatment = assessment.get("is_incomplete_treatment", False)
    is_missed_red_flag = assessment.get("is_missed_red_flag", False)
    incomplete_reasons = assessment.get("incomplete_treatment_reasons", [])

    # 5. MISSING_DIAGNOSIS_ALERT - triggered when diagnosis present but no treatment
    # Check incomplete_treatment_reasons for diagnosis-related issues
    diagnosis_warnings = input_data.get("diagnosis_warnings", [])
    has_diagnosis_issue = any("diagnosis" in str(r).lower() for r in incomplete_reasons) if incomplete_reasons else False

    if is_incomplete_treatment and (diagnosis_warnings or has_diagnosis_issue):
        definition = QUALITY_INTERVENTIONS["MISSING_DIAGNOSIS_ALERT"]
        # Extract treatment name from reasons
        treatment = "prescribed treatment"
        if incomplete_reasons:
            for reason in incomplete_reasons:
                if "diagnosis" in str(reason).lower():
                    treatment = str(reason)
                    break
        elif diagnosis_warnings:
            treatment = diagnosis_warnings[0] if isinstance(diagnosis_warnings[0], str) else str(diagnosis_warnings[0])

        interventions.append({
            "intervention_code": "MISSING_DIAGNOSIS_ALERT",
            "intervention_category": "QUALITY_RISK",
            "intervention_sub_type": definition.sub_type,
            "priority_level": definition.priority,
            "priority_score": PRIORITY_SCORES[definition.priority],
            "trigger_reason": definition.reason_template.format(treatment=treatment),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "care_quality_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {"diagnosis_warnings": diagnosis_warnings, "incomplete_reasons": incomplete_reasons}
        })

    # 6. PROTOCOL_DEVIATION_REVIEW - triggered by protocol_warnings in input_data
    protocol_warnings = input_data.get("protocol_warnings", [])
    if protocol_warnings:
        definition = QUALITY_INTERVENTIONS["PROTOCOL_DEVIATION_REVIEW"]
        condition = protocol_warnings[0] if isinstance(protocol_warnings[0], str) else str(protocol_warnings[0])

        interventions.append({
            "intervention_code": "PROTOCOL_DEVIATION_REVIEW",
            "intervention_category": "QUALITY_RISK",
            "intervention_sub_type": definition.sub_type,
            "priority_level": definition.priority,
            "priority_score": PRIORITY_SCORES[definition.priority],
            "trigger_reason": definition.reason_template.format(condition=condition),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "care_quality_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {"protocol_warnings": protocol_warnings}
        })

    # 7. INCOMPLETE_WORKUP_ALERT - triggered by workup_warnings in input_data
    # This covers missing investigations identified by triage
    workup_warnings = input_data.get("workup_warnings", [])
    if workup_warnings:
        definition = QUALITY_INTERVENTIONS["INCOMPLETE_WORKUP_ALERT"]

        # Extract specific investigation names from structured warnings
        investigation_names = []
        for w in workup_warnings[:3]:  # Limit to 3 for display
            if isinstance(w, dict):
                investigation_names.append(w.get("investigation", w.get("full_text", "investigation")))
            else:
                investigation_names.append(str(w))
        missing_tests = ", ".join(investigation_names) if investigation_names else "recommended investigations"

        interventions.append({
            "intervention_code": "INCOMPLETE_WORKUP_ALERT",
            "intervention_category": "QUALITY_RISK",
            "intervention_sub_type": definition.sub_type,
            "priority_level": definition.priority,
            "priority_score": PRIORITY_SCORES[definition.priority],
            "trigger_reason": definition.reason_template.format(missing_tests=missing_tests),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "care_quality_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {"workup_warnings": workup_warnings}
        })

    return interventions


# NOTE: _generate_followup_interventions function removed
# URGENT_FOLLOWUP_NEEDED, PATIENT_EDUCATION_GAP moved to retention_interventions_service.py
# SPECIALIST_REFERRAL_NEEDED moved to revenue_interventions_service.py


# =============================================================================
# MODULE INFO
# =============================================================================

__version__ = "1.1.0"
__author__ = "Unizy Health"
__all__ = [
    "generate_quality_interventions",
    "QUALITY_INTERVENTIONS",
]

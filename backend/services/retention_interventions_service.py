"""
Retention Interventions Service

Generates retention-related interventions to prevent student dropoff.

NEW 7-CATEGORY SYSTEM:
- RETENTION_RISK: COMPETITOR_COUNTEROFFER, ACCESS_BARRIER_RESOLUTION, FINANCIAL_ASSISTANCE,
                  COMPLIANCE_SUPPORT, SATISFACTION_RECOVERY, EMOTIONAL_SUPPORT,
                  PATIENT_EDUCATION_GAP, SEVERITY_AWARENESS_GAP
- FOLLOWUP_DUE: FOLLOW_UP_REMINDER, URGENT_FOLLOWUP_NEEDED

Assessment Sources:
- Based on student_dropoff_risk assessment
- Based on emotional segment analysis (EMOTIONAL_SUPPORT)
- Based on clinical_severity for priority adjustments

10 Retention Intervention Types:
1. COMPETITOR_COUNTEROFFER - Student considering other providers
2. ACCESS_BARRIER_RESOLUTION - Logistics/access issues
3. FINANCIAL_ASSISTANCE - Financial concerns with high dropoff risk (skipped if severity MILD/NONE)
4. COMPLIANCE_SUPPORT - Low treatment adherence (HIGH priority if severity SEVERE/CRITICAL)
5. FOLLOW_UP_REMINDER - Vague follow-up scheduling (MEDIUM priority if severity MODERATE+)
6. SATISFACTION_RECOVERY - Dissatisfaction detected
7. EMOTIONAL_SUPPORT - Anxiety elevated/worsened (HIGH priority if severity SEVERE/CRITICAL)
8. URGENT_FOLLOWUP_NEEDED - Urgent follow-up required (CRITICAL if severity SEVERE/CRITICAL)
9. PATIENT_EDUCATION_GAP - Understanding barrier for treatment plan
10. SEVERITY_AWARENESS_GAP - Student doesn't understand severity

Author: Unizy Health
Version: 2.0.0
"""

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# =============================================================================
# EVIDENCE EXTRACTION HELPERS
# =============================================================================

def _extract_evidence_from_insights(
    consultation_insights: Optional[Dict[str, Any]],
    signal_group: str,
    evidence_field: str = "evidence"
) -> List[Dict[str, str]]:
    """
    Extract evidence/quotes from consultation_insights for compelling rationale.

    Args:
        consultation_insights: Raw consultation insights dict
        signal_group: Name of signal group (e.g., "competitor_signals", "access_logistics_signals")
        evidence_field: Name of evidence field within the signal group

    Returns:
        List of evidence dicts with 'source' and 'content' keys
    """
    if not consultation_insights:
        return []

    evidence_list = []
    signal_data = consultation_insights.get(signal_group, {})

    if not signal_data:
        return []

    # Try to get the evidence field
    evidence = signal_data.get(evidence_field) or signal_data.get(f"{evidence_field}s") or []

    # Handle both list and string evidence
    if isinstance(evidence, list):
        for item in evidence:
            if item and str(item).strip():
                evidence_list.append({
                    "source": signal_group,
                    "content": str(item).strip()
                })
    elif evidence and str(evidence).strip():
        evidence_list.append({
            "source": signal_group,
            "content": str(evidence).strip()
        })

    return evidence_list


def _format_evidence_for_rationale(evidence_list: List[Dict[str, str]]) -> str:
    """
    Format evidence list into a human-readable string for trigger_reason.

    Args:
        evidence_list: List of evidence dicts

    Returns:
        Formatted string with quotes
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


# =============================================================================
# INTERVENTION DEFINITIONS
# =============================================================================

@dataclass
class RetentionInterventionDefinition:
    """Definition for a retention intervention type."""
    intervention_type: str
    sub_type: str  # retention, emotional
    priority: str
    reason_template: str
    action_template: str


RETENTION_INTERVENTIONS: Dict[str, RetentionInterventionDefinition] = {
    "COMPETITOR_COUNTEROFFER": RetentionInterventionDefinition(
        intervention_type="COMPETITOR_COUNTEROFFER",
        sub_type="retention",
        priority="CRITICAL",
        reason_template="Student mentioned considering other healthcare providers: {details}",
        action_template="Proactive outreach with value proposition and loyalty benefits"
    ),
    "ACCESS_BARRIER_RESOLUTION": RetentionInterventionDefinition(
        intervention_type="ACCESS_BARRIER_RESOLUTION",
        sub_type="retention",
        priority="HIGH",
        reason_template="Student faces {barrier_type} barriers to accessing care",
        action_template="Arrange alternative access solutions to remove barriers"
    ),
    "FINANCIAL_ASSISTANCE": RetentionInterventionDefinition(
        intervention_type="FINANCIAL_ASSISTANCE",
        sub_type="retention",
        priority="HIGH",
        reason_template="Student expressed financial concerns with {probability}% dropoff risk",
        action_template="Connect with financial counselor to discuss payment options"
    ),
    "COMPLIANCE_SUPPORT": RetentionInterventionDefinition(
        intervention_type="COMPLIANCE_SUPPORT",
        sub_type="retention",
        priority="MEDIUM",
        reason_template="Student shows low treatment adherence likelihood with {med_count} medications",
        action_template="Enroll in medication adherence program with reminders"
    ),
    "FOLLOW_UP_REMINDER": RetentionInterventionDefinition(
        intervention_type="FOLLOW_UP_REMINDER",
        sub_type="retention",
        priority="LOW",
        reason_template="No specific follow-up scheduled with {risk_level} retention risk",
        action_template="Schedule automated follow-up reminder call"
    ),
    "SATISFACTION_RECOVERY": RetentionInterventionDefinition(
        intervention_type="SATISFACTION_RECOVERY",
        sub_type="retention",
        priority="HIGH",
        reason_template="Student anxiety worsened with weak counsellor rapport: {details}",
        action_template="Manager callback for service recovery within 24 hours"
    ),
    "EMOTIONAL_SUPPORT": RetentionInterventionDefinition(
        intervention_type="EMOTIONAL_SUPPORT",
        sub_type="emotional",
        priority="MEDIUM",
        reason_template="Student showed {emotion_state} requiring emotional support",
        action_template="Connect with student support team for emotional follow-up"
    ),
    # Moved from QUALITY category
    "URGENT_FOLLOWUP_NEEDED": RetentionInterventionDefinition(
        intervention_type="URGENT_FOLLOWUP_NEEDED",
        sub_type="followup",
        priority="HIGH",
        reason_template="Urgent follow-up needed for {condition} within {timeframe}",
        action_template="Schedule priority follow-up appointment"
    ),
    "PATIENT_EDUCATION_GAP": RetentionInterventionDefinition(
        intervention_type="PATIENT_EDUCATION_GAP",
        sub_type="education",
        priority="LOW",
        reason_template="Student lacks understanding of {topic}",
        action_template="Provide student education materials"
    ),
    # New: Severity awareness mismatch
    "SEVERITY_AWARENESS_GAP": RetentionInterventionDefinition(
        intervention_type="SEVERITY_AWARENESS_GAP",
        sub_type="education",
        priority="HIGH",
        reason_template="Student may not understand gravity of condition: {details}",
        action_template="Schedule dedicated counseling session to explain condition severity and importance of treatment adherence"
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

def generate_retention_interventions(
    dropoff_risk: Optional[Dict[str, Any]],
    emotional_segments: Optional[Dict[str, Any]] = None,
    consultation_insights: Optional[Dict[str, Any]] = None,
    consultation_insights_id: Optional[uuid.UUID] = None,
    clinical_severity: Optional[Dict[str, Any]] = None,
    care_quality_risk: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Generate retention interventions based on dropoff risk and emotional analysis.

    Args:
        dropoff_risk: Student dropoff risk assessment record
        emotional_segments: Emotional segment data (ANXIETY_POST_CONSULTATION, etc.)
        consultation_insights: Raw consultation insights (for competitor/access signals)
        consultation_insights_id: Optional FK to consultation_insights
        clinical_severity: Clinical severity assessment (for priority adjustments)
        care_quality_risk: Care quality risk assessment (for followup/education interventions)

    Returns:
        List of intervention dicts ready for save_categorized_intervention()
    """
    interventions = []

    # Extract severity level for priority adjustments
    severity_level = None
    if clinical_severity:
        severity_level = clinical_severity.get("severity_level", "MILD")

    # 1. Dropoff risk-based interventions
    if dropoff_risk:
        interventions.extend(
            _generate_dropoff_interventions(
                dropoff_risk,
                consultation_insights,
                consultation_insights_id,
                severity_level
            )
        )

    # 2. Emotional support intervention (from emotional segments or dropoff risk)
    emotional_intervention = _generate_emotional_support_intervention(
        dropoff_risk,
        emotional_segments,
        consultation_insights_id,
        severity_level
    )
    if emotional_intervention:
        interventions.append(emotional_intervention)

    # 3. Followup and education interventions (moved from QUALITY)
    if care_quality_risk:
        interventions.extend(
            _generate_followup_education_interventions(
                care_quality_risk,
                consultation_insights_id,
                severity_level
            )
        )

    # 4. Severity awareness gap intervention
    # Triggers when clinical severity is HIGH but student shows low emotional response
    severity_awareness = _generate_severity_awareness_intervention(
        dropoff_risk=dropoff_risk,
        severity_level=severity_level,
        consultation_insights_id=consultation_insights_id
    )
    if severity_awareness:
        interventions.append(severity_awareness)

    logger.info(f"[RETENTION] Generated {len(interventions)} retention interventions")
    return interventions


def _generate_dropoff_interventions(
    dropoff_risk: Dict[str, Any],
    consultation_insights: Optional[Dict[str, Any]],
    insights_id: Optional[uuid.UUID],
    severity_level: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Generate interventions based on dropoff risk assessment.

    Severity-based adjustments:
    - FINANCIAL_ASSISTANCE: Skipped if severity is MILD or NONE
    - COMPLIANCE_SUPPORT: Priority boosted to HIGH if severity is SEVERE/CRITICAL
    - FOLLOW_UP_REMINDER: Priority boosted to MEDIUM if severity is MODERATE+
    """
    interventions = []
    assessment_id = dropoff_risk.get("id")

    risk_level = dropoff_risk.get("risk_level", "LOW")
    dropoff_probability = dropoff_risk.get("dropoff_probability", 0)

    # Severity-based priority adjustments
    is_high_severity = severity_level in ("SEVERE", "CRITICAL")
    is_moderate_or_higher = severity_level in ("MODERATE", "SEVERE", "CRITICAL")
    is_low_severity = severity_level in ("MILD", "NONE", None)

    # 1. COMPETITOR_COUNTEROFFER - if competitor risk detected
    if dropoff_risk.get("is_competitor_risk"):
        definition = RETENTION_INTERVENTIONS["COMPETITOR_COUNTEROFFER"]
        reasons = dropoff_risk.get("competitor_risk_reasons", [])

        # Extract evidence/quotes from consultation_insights
        evidence = _extract_evidence_from_insights(
            consultation_insights, "competitor_signals", "competitor_evidence"
        )
        evidence_text = _format_evidence_for_rationale(evidence)

        # Clean up technical field names for human readability
        if evidence_text:
            details = evidence_text  # Use actual quotes
        elif reasons:
            raw_reason = reasons[0]
            if "competitor_intent_detected" in str(raw_reason).lower():
                details = "considering alternative healthcare providers"
            elif "mentioned" in str(raw_reason).lower() or "clinic" in str(raw_reason).lower():
                details = str(raw_reason)
            else:
                details = "competitor consideration detected"
        else:
            details = "competitor consideration detected"

        interventions.append({
            "intervention_code": "COMPETITOR_COUNTEROFFER",
            "intervention_category": "RETENTION_RISK",  # New 7-category system
            "intervention_sub_type": definition.sub_type,
            "priority_level": definition.priority,
            "priority_score": PRIORITY_SCORES[definition.priority],
            "trigger_reason": definition.reason_template.format(details=details),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "student_dropoff_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {
                "competitor_risk_reasons": reasons,
                "evidence_quotes": _evidence_to_string_list(evidence)
            }
        })

    # 2. ACCESS_BARRIER_RESOLUTION - if access risk detected with SPECIFIC barrier types
    # STRICT TRIGGER: Only fire for concrete barriers (distance, transportation, scheduling, parking)
    # "other" barrier type alone is too vague and should NOT trigger this intervention
    if dropoff_risk.get("is_access_risk"):
        reasons = dropoff_risk.get("access_risk_reasons", [])

        # Extract actual barrier types from reasons (e.g., "Barrier types: distance, transportation")
        # NOTE: parking removed - not a compelling access barrier for intervention
        SPECIFIC_BARRIER_TYPES = {"distance", "transportation", "travel", "waiting_time", "scheduling"}
        found_specific_barriers = []

        for reason in reasons:
            reason_lower = str(reason).lower()
            # Check if reason contains "barrier types:" pattern
            if "barrier types:" in reason_lower or "barrier type:" in reason_lower:
                # Extract the barrier types after the colon
                parts = reason_lower.split(":")
                if len(parts) > 1:
                    barrier_list = parts[-1].strip()
                    for barrier in barrier_list.replace(",", " ").split():
                        barrier_clean = barrier.strip()
                        if barrier_clean in SPECIFIC_BARRIER_TYPES:
                            found_specific_barriers.append(barrier_clean)
            else:
                # Check for specific keywords in reason text
                for specific in SPECIFIC_BARRIER_TYPES:
                    if specific in reason_lower:
                        found_specific_barriers.append(specific)

        # Only trigger if we found at least one SPECIFIC barrier type
        if found_specific_barriers:
            definition = RETENTION_INTERVENTIONS["ACCESS_BARRIER_RESOLUTION"]

            # Extract evidence/quotes from consultation_insights
            evidence = _extract_evidence_from_insights(
                consultation_insights, "access_logistics_signals", "access_evidence"
            )

            # Map to human-readable barrier type
            if "distance" in found_specific_barriers or "travel" in found_specific_barriers:
                barrier_type = "distance/travel"
            elif "transportation" in found_specific_barriers:
                barrier_type = "transportation"
            elif "scheduling" in found_specific_barriers or "waiting_time" in found_specific_barriers:
                barrier_type = "scheduling"
            else:
                barrier_type = "transportation/scheduling"

            # Build trigger reason with evidence if available
            evidence_text = _format_evidence_for_rationale(evidence)
            trigger_reason = definition.reason_template.format(barrier_type=barrier_type)
            if evidence_text:
                trigger_reason += f" - Evidence: {evidence_text}"

            interventions.append({
                "intervention_code": "ACCESS_BARRIER_RESOLUTION",
                "intervention_category": "RETENTION_RISK",  # New 7-category system
                "intervention_sub_type": definition.sub_type,
                "priority_level": definition.priority,
                "priority_score": PRIORITY_SCORES[definition.priority],
                "trigger_reason": trigger_reason,
                "action": definition.action_template,
                "consultation_insights_id": insights_id,
                "linked_assessment_type": "student_dropoff_risk",
                "linked_assessment_id": assessment_id,
                "rationale_sources": {
                    "access_risk_reasons": reasons,
                    "evidence_quotes": _evidence_to_string_list(evidence),
                    "barrier_types": found_specific_barriers
                }
            })
        else:
            logger.debug(
                f"[RETENTION_INTERVENTION] Skipping ACCESS_BARRIER_RESOLUTION - "
                f"no specific barrier types found (only vague 'other'): {reasons}"
            )

    # 3. FINANCIAL_ASSISTANCE - if financial risk with significant dropoff probability
    # SEVERITY FILTER: Skip if clinical severity is MILD or NONE (low-severity conditions don't warrant urgency)
    if dropoff_risk.get("is_financial_risk") and dropoff_probability >= 50 and not is_low_severity:
        definition = RETENTION_INTERVENTIONS["FINANCIAL_ASSISTANCE"]
        reasons = dropoff_risk.get("financial_risk_reasons", [])

        interventions.append({
            "intervention_code": "FINANCIAL_ASSISTANCE",
            "intervention_category": "RETENTION_RISK",  # New 7-category system
            "intervention_sub_type": definition.sub_type,
            "priority_level": definition.priority,
            "priority_score": PRIORITY_SCORES[definition.priority],
            "trigger_reason": definition.reason_template.format(probability=dropoff_probability),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "student_dropoff_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {
                "financial_risk_reasons": reasons,
                "probability": dropoff_probability,
                "severity_level": severity_level
            }
        })

    # 4. COMPLIANCE_SUPPORT - if compliance risk detected
    # SEVERITY BOOST: Priority boosted to HIGH if severity is SEVERE/CRITICAL
    if dropoff_risk.get("is_compliance_risk"):
        definition = RETENTION_INTERVENTIONS["COMPLIANCE_SUPPORT"]
        reasons = dropoff_risk.get("compliance_risk_reasons", [])

        # Get medication count from consultation insights if available
        med_count = 0
        if consultation_insights:
            med_signals = consultation_insights.get("medication_signals", {})
            med_count = med_signals.get("total_medications_prescribed", 0)

        # Boost priority if high severity
        priority = "HIGH" if is_high_severity else definition.priority
        priority_score = PRIORITY_SCORES[priority]

        interventions.append({
            "intervention_code": "COMPLIANCE_SUPPORT",
            "intervention_category": "RETENTION_RISK",  # New 7-category system
            "intervention_sub_type": definition.sub_type,
            "priority_level": priority,
            "priority_score": priority_score,
            "trigger_reason": definition.reason_template.format(med_count=med_count or "multiple"),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "student_dropoff_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {
                "compliance_risk_reasons": reasons,
                "medication_count": med_count,
                "severity_level": severity_level,
                "priority_boosted": is_high_severity
            }
        })

    # 5. FOLLOW_UP_REMINDER - medium/high risk with no clear follow-up
    # SEVERITY BOOST: Priority boosted to MEDIUM if severity is MODERATE+
    # Check if follow-up is vague (from dropoff risk calculation)
    if risk_level in ("MEDIUM", "HIGH") and dropoff_probability >= 30:
        # Only add if not already covered by other interventions
        if not any(i["intervention_code"] in ("COMPETITOR_COUNTEROFFER", "ACCESS_BARRIER_RESOLUTION")
                   for i in interventions):
            definition = RETENTION_INTERVENTIONS["FOLLOW_UP_REMINDER"]

            # Boost priority if moderate or higher severity
            priority = "MEDIUM" if is_moderate_or_higher else definition.priority
            priority_score = PRIORITY_SCORES[priority]

            interventions.append({
                "intervention_code": "FOLLOW_UP_REMINDER",
                "intervention_category": "FOLLOWUP_DUE",  # New 7-category system
                "intervention_sub_type": definition.sub_type,
                "priority_level": priority,
                "priority_score": priority_score,
                "trigger_reason": definition.reason_template.format(risk_level=risk_level),
                "action": definition.action_template,
                "consultation_insights_id": insights_id,
                "linked_assessment_type": "student_dropoff_risk",
                "linked_assessment_id": assessment_id,
                "rationale_sources": {
                    "risk_level": risk_level,
                    "probability": dropoff_probability,
                    "severity_level": severity_level,
                    "priority_boosted": is_moderate_or_higher
                }
            })

    # 6. SATISFACTION_RECOVERY - if dissatisfaction risk detected
    if dropoff_risk.get("is_dissatisfaction_risk"):
        definition = RETENTION_INTERVENTIONS["SATISFACTION_RECOVERY"]
        reasons = dropoff_risk.get("dissatisfaction_risk_reasons", [])

        # Clean up technical field names for human readability
        details = "dissatisfaction indicators detected"
        if reasons:
            raw_reason = str(reasons[0]).lower()
            # Map technical terms to human-readable descriptions
            if "anxiety" in raw_reason and ("worsened" in raw_reason or "trajectory" in raw_reason):
                details = "anxiety not adequately addressed during visit"
            elif "emotion_congruence" in raw_reason or "congruence" in raw_reason:
                details = "communication concerns detected"
            elif "rapport" in raw_reason:
                details = "rapport issues during consultation"
            elif "wait" in raw_reason or "time" in raw_reason:
                details = "service timing concerns"
            elif "dissatisf" in raw_reason or "unhappy" in raw_reason or "complaint" in raw_reason:
                details = "student expressed dissatisfaction"
            else:
                # Keep generic if we can't parse it
                details = "service experience concerns"

        interventions.append({
            "intervention_code": "SATISFACTION_RECOVERY",
            "intervention_category": "RETENTION_RISK",  # New 7-category system
            "intervention_sub_type": definition.sub_type,
            "priority_level": definition.priority,
            "priority_score": PRIORITY_SCORES[definition.priority],
            "trigger_reason": definition.reason_template.format(details=details),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "student_dropoff_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {"dissatisfaction_risk_reasons": reasons}
        })

    return interventions


def _generate_emotional_support_intervention(
    dropoff_risk: Optional[Dict[str, Any]],
    emotional_segments: Optional[Dict[str, Any]],
    insights_id: Optional[uuid.UUID],
    severity_level: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Generate EMOTIONAL_SUPPORT intervention if:
    - Anxiety remained elevated or worsened at end of consultation
    - Strong non-anxiety emotions were detected

    SEVERITY BOOST: Priority boosted to HIGH if severity is SEVERE/CRITICAL

    Args:
        dropoff_risk: Dropoff risk assessment (contains anxiety trajectory)
        emotional_segments: Emotional segment data
        insights_id: FK to consultation_insights
        severity_level: Clinical severity level for priority adjustments

    Returns:
        Intervention dict or None
    """
    emotion_state = None
    rationale = {}
    is_high_severity = severity_level in ("SEVERE", "CRITICAL")

    # Check anxiety trajectory from dropoff risk
    if dropoff_risk:
        anxiety_trajectory = dropoff_risk.get("anxiety_trajectory", "stable")
        anxiety_post_level_raw = dropoff_risk.get("anxiety_post_level", 0)
        # Convert to int/float - database may return string
        try:
            anxiety_post_level = float(anxiety_post_level_raw) if anxiety_post_level_raw else 0
        except (ValueError, TypeError):
            anxiety_post_level = 0

        # Trigger if anxiety worsened or remained elevated (6+)
        if anxiety_trajectory == "worsened":
            emotion_state = "anxiety worsened during consultation"
            rationale = {
                "trigger": "anxiety_worsened",
                "trajectory": anxiety_trajectory,
                "post_level": anxiety_post_level
            }
        elif anxiety_post_level >= 6:
            emotion_state = f"elevated anxiety (level {anxiety_post_level}/10) post-consultation"
            rationale = {
                "trigger": "anxiety_elevated",
                "trajectory": anxiety_trajectory,
                "post_level": anxiety_post_level
            }

    # Check for strong non-anxiety emotions from segments
    if not emotion_state and emotional_segments:
        other_emotions = emotional_segments.get("OTHER_EMOTIONS_DETECTED", {})
        if isinstance(other_emotions, dict):
            # Check for significant emotions
            emotions = other_emotions.get("emotions_detected", [])
            dominant = other_emotions.get("dominant_emotion", "")
            intensity = other_emotions.get("overall_intensity", "low")

            if intensity in ("high", "severe") and (emotions or dominant):
                emotion_list = emotions if emotions else [dominant]
                emotion_state = f"strong emotional distress ({', '.join(emotion_list[:2])})"
                rationale = {
                    "trigger": "strong_emotions",
                    "emotions": emotion_list,
                    "intensity": intensity
                }

    # Generate intervention if we have an emotion state
    if emotion_state:
        definition = RETENTION_INTERVENTIONS["EMOTIONAL_SUPPORT"]

        # Boost priority if high severity
        priority = "HIGH" if is_high_severity else definition.priority
        priority_score = PRIORITY_SCORES[priority]

        # Add severity info to rationale
        rationale["severity_level"] = severity_level
        rationale["priority_boosted"] = is_high_severity

        return {
            "intervention_code": "EMOTIONAL_SUPPORT",
            "intervention_category": "RETENTION_RISK",  # New 7-category system
            "intervention_sub_type": definition.sub_type,
            "priority_level": priority,
            "priority_score": priority_score,
            "trigger_reason": definition.reason_template.format(emotion_state=emotion_state),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "student_dropoff_risk",
            "linked_assessment_id": dropoff_risk.get("id") if dropoff_risk else None,
            "rationale_sources": rationale
        }

    return None


def _generate_severity_awareness_intervention(
    dropoff_risk: Optional[Dict[str, Any]],
    severity_level: Optional[str],
    consultation_insights_id: Optional[uuid.UUID]
) -> Optional[Dict[str, Any]]:
    """
    Generate SEVERITY_AWARENESS_GAP intervention when there's a mismatch between
    clinical severity and student's emotional response.

    Trigger conditions:
    - Clinical severity is SEVERE or CRITICAL
    - AND student shows LOW anxiety (level 0-3) OR compliance likelihood is Low/Very Low/Moderate

    This indicates the student may not understand the gravity of their condition,
    which is a significant retention and adherence risk.

    Args:
        dropoff_risk: Dropoff risk assessment (contains anxiety level and compliance likelihood)
        severity_level: Clinical severity level from clinical_severity assessment
        consultation_insights_id: FK to consultation_insights

    Returns:
        Intervention dict or None
    """
    # Only trigger for SEVERE or CRITICAL clinical severity
    if severity_level not in ("SEVERE", "CRITICAL"):
        return None

    if not dropoff_risk:
        return None

    # Get student's emotional response indicators
    anxiety_post_level = dropoff_risk.get("anxiety_post_level", 5)  # Default to moderate
    compliance_likelihood = dropoff_risk.get("compliance_likelihood", "Moderate")

    # Check for mismatch: HIGH severity but LOW emotional response
    # Anxiety levels: 0-3 = low, 4-6 = moderate, 7-10 = high
    low_anxiety = anxiety_post_level <= 3
    low_compliance_concern = compliance_likelihood in ("Low", "Very Low", "Moderate")

    # Trigger if severity is HIGH but student shows LOW anxiety OR poor compliance expectation
    if not (low_anxiety or low_compliance_concern):
        return None

    # Build details for the intervention
    mismatch_indicators = []
    if low_anxiety:
        mismatch_indicators.append(f"anxiety level only {anxiety_post_level}/10 despite serious diagnosis")
    if low_compliance_concern:
        mismatch_indicators.append(f"compliance likelihood rated as '{compliance_likelihood}'")

    details = "; ".join(mismatch_indicators) if mismatch_indicators else "emotional response suggests lack of awareness"

    definition = RETENTION_INTERVENTIONS["SEVERITY_AWARENESS_GAP"]

    logger.info(
        f"[RETENTION] SEVERITY_AWARENESS_GAP triggered: severity={severity_level}, "
        f"anxiety_post={anxiety_post_level}, compliance={compliance_likelihood}"
    )

    return {
        "intervention_code": "SEVERITY_AWARENESS_GAP",
        "intervention_category": "RETENTION_RISK",  # New 7-category system
        "intervention_sub_type": definition.sub_type,
        "priority_level": definition.priority,
        "priority_score": PRIORITY_SCORES[definition.priority],
        "trigger_reason": definition.reason_template.format(details=details),
        "action": definition.action_template,
        "consultation_insights_id": consultation_insights_id,
        "linked_assessment_type": "student_dropoff_risk",
        "linked_assessment_id": dropoff_risk.get("id"),
        "rationale_sources": {
            "clinical_severity": severity_level,
            "anxiety_post_level": anxiety_post_level,
            "compliance_likelihood": compliance_likelihood,
            "mismatch_indicators": mismatch_indicators
        }
    }


def _generate_followup_education_interventions(
    care_quality_risk: Dict[str, Any],
    insights_id: Optional[uuid.UUID],
    severity_level: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Generate URGENT_FOLLOWUP_NEEDED and PATIENT_EDUCATION_GAP interventions.
    Moved from QUALITY category to RETENTION.

    SEVERITY BOOST:
    - URGENT_FOLLOWUP_NEEDED: Priority boosted to CRITICAL if severity is SEVERE/CRITICAL
    - PATIENT_EDUCATION_GAP: Priority boosted to MEDIUM if severity is MODERATE+

    Args:
        care_quality_risk: Care quality risk assessment record
        insights_id: FK to consultation_insights
        severity_level: Clinical severity level for priority adjustments

    Returns:
        List of intervention dicts
    """
    interventions = []
    assessment_id = care_quality_risk.get("id")
    input_data = care_quality_risk.get("input_data", {}) or {}

    is_high_severity = severity_level in ("SEVERE", "CRITICAL")
    is_moderate_or_higher = severity_level in ("MODERATE", "SEVERE", "CRITICAL")

    # 8. URGENT_FOLLOWUP_NEEDED
    # Note: is_followup_gap is the actual field from care_quality_service.py Q4 indicator
    if care_quality_risk.get("is_followup_gap"):
        definition = RETENTION_INTERVENTIONS["URGENT_FOLLOWUP_NEEDED"]

        # Use followup_gap_reasons for specific details
        reasons = care_quality_risk.get("followup_gap_reasons", [])
        condition = "current condition"
        timeframe = "48-72 hours"

        if reasons:
            # Extract condition from reason (e.g., "Serious diagnosis (Diabetes) with vague follow-up")
            first_reason = reasons[0] if isinstance(reasons[0], str) else str(reasons[0])
            # Try to extract specific diagnosis from the reason
            if "diagnosis" in first_reason.lower():
                match = re.search(r'\(([^)]+)\)', first_reason)
                if match:
                    condition = match.group(1)
                else:
                    condition = first_reason
            else:
                condition = first_reason

        # Boost priority to CRITICAL if high severity
        priority = "CRITICAL" if is_high_severity else definition.priority
        priority_score = PRIORITY_SCORES[priority]

        interventions.append({
            "intervention_code": "URGENT_FOLLOWUP_NEEDED",
            "intervention_category": "FOLLOWUP_DUE",  # New 7-category system
            "intervention_sub_type": definition.sub_type,
            "priority_level": priority,
            "priority_score": priority_score,
            "trigger_reason": definition.reason_template.format(condition=condition, timeframe=timeframe),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "care_quality_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {
                "followup_gap_reasons": reasons,
                "severity_level": severity_level,
                "priority_boosted": is_high_severity
            }
        })

    # 9. PATIENT_EDUCATION_GAP
    # Note: Uses is_incomplete_treatment as proxy for education gaps
    # (incomplete treatment often indicates student understanding issues)
    if care_quality_risk.get("is_incomplete_treatment"):
        definition = RETENTION_INTERVENTIONS["PATIENT_EDUCATION_GAP"]

        # Use incomplete_treatment_reasons for specific topic
        reasons = care_quality_risk.get("incomplete_treatment_reasons", [])
        if reasons:
            # Extract first reason as topic
            topic = reasons[0] if isinstance(reasons[0], str) else "treatment plan"
        else:
            topic = "treatment plan"

        # Boost priority to MEDIUM if moderate or higher severity
        priority = "MEDIUM" if is_moderate_or_higher else definition.priority
        priority_score = PRIORITY_SCORES[priority]

        interventions.append({
            "intervention_code": "PATIENT_EDUCATION_GAP",
            "intervention_category": "RETENTION_RISK",  # New 7-category system
            "intervention_sub_type": definition.sub_type,
            "priority_level": priority,
            "priority_score": priority_score,
            "trigger_reason": definition.reason_template.format(topic=topic),
            "action": definition.action_template,
            "consultation_insights_id": insights_id,
            "linked_assessment_type": "care_quality_risk",
            "linked_assessment_id": assessment_id,
            "rationale_sources": {
                "incomplete_treatment_reasons": reasons,
                "severity_level": severity_level,
                "priority_boosted": is_moderate_or_higher
            }
        })

    return interventions


# =============================================================================
# MODULE INFO
# =============================================================================

__version__ = "2.0.0"
__author__ = "Unizy Health"
__all__ = [
    "generate_retention_interventions",
    "RETENTION_INTERVENTIONS",
]

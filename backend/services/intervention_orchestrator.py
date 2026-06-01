"""
Intervention Orchestrator

Main entry point for generating all intervention categories.

NEW 7-CATEGORY SYSTEM:
- OP_TO_IP: SURGICAL_CONSULTATION (potential OP to IP conversion)
- FOLLOWUP_DUE: SECOND_OPINION_CONSULT, ALTERNATIVE_TREATMENT_CONSULT, FOLLOW_UP_REMINDER,
                URGENT_FOLLOWUP_NEEDED, SPECIALIST_REFERRAL_NEEDED
- RX_REFILL: PRESCRIPTION_REFILL_REMINDER
- DIAGNOSTICS_DUE: HOME_DIAGNOSTIC_COLLECTION, RECURRING_TEST_SCHEDULE
- ALLIED_HEALTH: 9 allied health referrals + CHRONIC_CARE_PROGRAM
- RETENTION_RISK: COMPETITOR_COUNTEROFFER, ACCESS_BARRIER_RESOLUTION, FINANCIAL_ASSISTANCE,
                  COMPLIANCE_SUPPORT, SATISFACTION_RECOVERY, EMOTIONAL_SUPPORT, PATIENT_EDUCATION_GAP
- QUALITY_RISK: 7 medication safety and documentation interventions

Aggregates results from all three intervention services and saves to database.

Priority Adjustments (severity-based, applied in individual services):
- FINANCIAL_ASSISTANCE: Skipped if severity is MILD/NONE
- COMPLIANCE_SUPPORT: Priority boosted to HIGH if severity is SEVERE/CRITICAL
- FOLLOW_UP_REMINDER: Priority boosted to MEDIUM if severity is MODERATE+
- EMOTIONAL_SUPPORT: Priority boosted to HIGH if severity is SEVERE/CRITICAL
- URGENT_FOLLOWUP_NEEDED: Priority boosted to CRITICAL if severity is SEVERE/CRITICAL
- PATIENT_EDUCATION_GAP: Priority boosted to MEDIUM if severity is MODERATE+
- SPECIALIST_REFERRAL_NEEDED: Priority boosted to HIGH if severity is SEVERE/CRITICAL

Financial concerns-based (from emotion analysis):
- Allied health interventions: Priority downgraded if financial concerns HIGH/MEDIUM
  - HIGH → MEDIUM, MEDIUM → LOW
  - Rationale: Students with financial concerns unlikely to buy additional services

Take-Up Prediction:
- Each intervention gets a take_up_likelihood (0-100) score
- Predicts likelihood student will accept/follow intervention
- Based on clinical severity, anxiety, financial concerns, compliance, fear/distress
- IMPORTANT: Priority score is NOT adjusted by take-up likelihood
- Dashboard uses take_up_likelihood separately for risk segmentation (no double counting)

Author: Unizy Health
Version: 2.1.0
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Intervention:
    """Standardized intervention output."""
    intervention_type: str          # e.g., "NUTRITIONAL_REFERRAL"
    category: str                   # 7 categories: OP_TO_IP | FOLLOWUP_DUE | RX_REFILL | DIAGNOSTICS_DUE | ALLIED_HEALTH | RETENTION_RISK | QUALITY_RISK
    sub_type: str                   # e.g., "allied_health", "clinical_upsell"
    priority: str                   # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    priority_score: int             # 0-100
    reason: str                     # Plain English explanation
    action: str                     # Simple action statement
    revenue_estimate: Optional[float] = None  # Only for REVENUE (from school pricing)
    linked_assessment_type: str = ""  # Which assessment triggered this
    linked_assessment_id: Optional[uuid.UUID] = None  # FK to assessment record
    consultation_insights_id: Optional[uuid.UUID] = None  # FK to consultation_insights
    rationale_sources: Dict[str, Any] = field(default_factory=dict)
    take_up_likelihood: Optional[int] = None  # 0-100 predicted take-up likelihood

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for database save."""
        result = {
            "intervention_code": self.intervention_type,
            "intervention_category": self.category,
            "intervention_sub_type": self.sub_type,
            "priority_level": self.priority,
            "priority_score": self.priority_score,
            "trigger_reason": self.reason,
            "action": self.action,
            "revenue_estimate": self.revenue_estimate,
            "linked_assessment_type": self.linked_assessment_type,
            "linked_assessment_id": self.linked_assessment_id,
            "consultation_insights_id": self.consultation_insights_id,
            "rationale_sources": self.rationale_sources
        }
        if self.take_up_likelihood is not None:
            result["take_up_likelihood"] = self.take_up_likelihood
        return result


@dataclass
class InterventionResult:
    """Result of intervention generation."""
    total_generated: int = 0
    revenue_count: int = 0
    retention_count: int = 0
    quality_count: int = 0
    interventions: List[Dict[str, Any]] = field(default_factory=list)
    total_revenue_potential: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_generated": self.total_generated,
            "revenue_count": self.revenue_count,
            "retention_count": self.retention_count,
            "quality_count": self.quality_count,
            "total_revenue_potential": self.total_revenue_potential,
            "interventions": self.interventions
        }


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================

async def generate_all_interventions(
    extraction_id: uuid.UUID,
    school_id: Optional[uuid.UUID] = None,
    consultation_insights_id: Optional[uuid.UUID] = None
) -> InterventionResult:
    """
    Generate all intervention categories for an extraction.

    Main entry point called from background tasks after all assessments complete.

    Args:
        extraction_id: UUID of the extraction
        school_id: UUID of the school (for revenue pricing lookup)
        consultation_insights_id: UUID of consultation_insights record

    Returns:
        InterventionResult with counts and all generated interventions
    """
    from services.supabase_service import (
        get_allied_health_by_extraction,
        get_clinical_severity_by_extraction,
        get_other_clinical_needs_by_extraction,
        get_dropoff_risk_by_extraction,
        get_care_quality_by_extraction,
        get_all_school_pricing,
        get_extraction_segments,
        get_consultation_insights_by_extraction,
    )
    from services.revenue_interventions_service import generate_revenue_interventions
    from services.retention_interventions_service import generate_retention_interventions
    from services.quality_interventions_service import generate_quality_interventions

    result = InterventionResult()

    try:
        # Fetch all assessments
        allied_health = get_allied_health_by_extraction(str(extraction_id))
        clinical_severity = get_clinical_severity_by_extraction(str(extraction_id))
        other_clinical = get_other_clinical_needs_by_extraction(str(extraction_id))
        dropoff_risk = get_dropoff_risk_by_extraction(str(extraction_id))
        care_quality = get_care_quality_by_extraction(str(extraction_id))

        # Fetch raw consultation_insights for evidence/rationale in interventions
        consultation_insights = get_consultation_insights_by_extraction(str(extraction_id))

        logger.info(
            f"[ORCHESTRATOR] Generating interventions for extraction {extraction_id}: "
            f"allied_health={'yes' if allied_health else 'no'}, "
            f"severity={'yes' if clinical_severity else 'no'}, "
            f"other_clinical={'yes' if other_clinical else 'no'}, "
            f"dropoff={'yes' if dropoff_risk else 'no'}, "
            f"quality={'yes' if care_quality else 'no'}"
        )

        # Get school pricing for revenue interventions
        school_pricing = {}
        if school_id:
            school_pricing = get_all_school_pricing(school_id)
            logger.debug(f"[ORCHESTRATOR] Loaded {len(school_pricing)} pricing entries for school {school_id}")

        # Get emotional segments for retention and revenue interventions
        emotional_segments = {}
        financial_concerns_level = None  # For allied health priority adjustment
        try:
            segments = get_extraction_segments(extraction_id)
            segment_map = {s["segment_code"]: s.get("segment_value", {}) for s in segments}
            emotional_segments = {
                "ANXIETY_POST_CONSULTATION": segment_map.get("ANXIETY_POST_CONSULTATION", {}),
                "OTHER_EMOTIONS_DETECTED": segment_map.get("OTHER_EMOTIONS_DETECTED", {}),
                "FINANCIAL_CONCERNS": segment_map.get("FINANCIAL_CONCERNS", {}),
            }

            # Extract financial concerns level for priority adjustment
            # HIGH/MEDIUM financial concerns → downgrade allied health priorities
            financial_data = segment_map.get("FINANCIAL_CONCERNS", {})
            if financial_data:
                severity = financial_data.get("severity", "").lower()
                if severity in ("high", "medium"):
                    financial_concerns_level = severity
                    logger.info(
                        f"[ORCHESTRATOR] Financial concerns detected: {severity} - "
                        f"will adjust allied health priorities"
                    )
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Could not load emotional segments: {e}")

        all_interventions = []

        # 1. Generate REVENUE interventions (17 types)
        # Now includes SPECIALIST_REFERRAL_NEEDED from care_quality_risk
        # financial_concerns_level affects allied health priority (HIGH/MEDIUM concerns → downgrade)
        # consultation_insights provides evidence/quotes for compelling rationale
        revenue_interventions = generate_revenue_interventions(
            allied_health_needs=allied_health,
            clinical_severity=clinical_severity,
            other_clinical_needs=other_clinical,
            school_pricing=school_pricing,
            consultation_insights_id=consultation_insights_id,
            care_quality_risk=care_quality,  # For SPECIALIST_REFERRAL_NEEDED
            financial_concerns_level=financial_concerns_level,  # For priority adjustment
            consultation_insights=consultation_insights  # For evidence/quotes in rationale
        )
        for intervention in revenue_interventions:
            intervention["extraction_id"] = extraction_id
        all_interventions.extend(revenue_interventions)
        result.revenue_count = len(revenue_interventions)

        # Calculate total revenue potential
        result.total_revenue_potential = sum(
            i.get("revenue_estimate", 0) or 0
            for i in revenue_interventions
        )

        # 2. Generate RETENTION interventions (9 types)
        # Now includes URGENT_FOLLOWUP_NEEDED, PATIENT_EDUCATION_GAP from care_quality_risk
        # Uses clinical_severity for priority adjustments
        # consultation_insights provides evidence/quotes for compelling rationale
        retention_interventions = generate_retention_interventions(
            dropoff_risk=dropoff_risk,
            emotional_segments=emotional_segments,
            consultation_insights=consultation_insights,  # For evidence/quotes in rationale
            consultation_insights_id=consultation_insights_id,
            clinical_severity=clinical_severity,  # For priority adjustments
            care_quality_risk=care_quality  # For URGENT_FOLLOWUP_NEEDED, PATIENT_EDUCATION_GAP
        )
        for intervention in retention_interventions:
            intervention["extraction_id"] = extraction_id
        all_interventions.extend(retention_interventions)
        result.retention_count = len(retention_interventions)

        # 3. Generate QUALITY interventions (7 types - medication safety + documentation only)
        # URGENT_FOLLOWUP_NEEDED, PATIENT_EDUCATION_GAP, SPECIALIST_REFERRAL_NEEDED moved out
        quality_interventions = generate_quality_interventions(
            care_quality_risk=care_quality,
            consultation_insights_id=consultation_insights_id
        )
        for intervention in quality_interventions:
            intervention["extraction_id"] = extraction_id
        all_interventions.extend(quality_interventions)
        result.quality_count = len(quality_interventions)

        # =====================================================================
        # TAKE-UP PREDICTION
        # Calculate take_up_likelihood for each intervention (for dashboard analytics)
        # NOTE: Priority score is NOT adjusted - used separately for risk segmentation
        # =====================================================================
        try:
            from services.take_up_prediction_service import (
                build_signals_from_assessments,
                predict_take_up_likelihood,
            )

            # Build signals once from existing assessments (no recalculation)
            other_emotions_segment = emotional_segments.get("OTHER_EMOTIONS_DETECTED", {})
            take_up_signals = build_signals_from_assessments(
                clinical_severity=clinical_severity,
                dropoff_risk=dropoff_risk,
                other_emotions_segment=other_emotions_segment
            )

            logger.info(
                f"[ORCHESTRATOR] Take-up signals: severity={take_up_signals.clinical_severity}, "
                f"anxiety_post={take_up_signals.anxiety_post_level}, "
                f"trajectory={take_up_signals.anxiety_trajectory}, "
                f"financial={take_up_signals.financial_concern}, "
                f"compliance={take_up_signals.compliance_likelihood}, "
                f"emotions={len(take_up_signals.emotions_detected)}"
            )

            # Enrich each intervention with take-up prediction (no priority adjustment)
            prediction_count = 0

            for intervention in all_interventions:
                category = intervention.get("intervention_category", "RETENTION")
                original_score = intervention.get("priority_score", 50)

                # Get prediction
                prediction = predict_take_up_likelihood(
                    signals=take_up_signals,
                    category=category
                )

                # Store take_up_likelihood
                intervention["take_up_likelihood"] = prediction.take_up_likelihood

                # IMPORTANT: Do NOT adjust priority_score based on take_up_likelihood
                # Priority score reflects pure clinical need (not influenced by take-up)
                # Dashboard uses take_up_likelihood separately for risk segmentation
                # This prevents double counting in dashboard analytics
                # intervention["priority_score"] = original_score  # Keep original (no change needed)

                # Track count for logging
                prediction_count += 1

                # Store prediction breakdown in rationale_sources
                if "rationale_sources" not in intervention:
                    intervention["rationale_sources"] = {}
                intervention["rationale_sources"]["take_up_prediction"] = {
                    "likelihood": prediction.take_up_likelihood,
                    "signal_contributions": prediction.signal_contributions,
                    "rules_applied": prediction.rules_applied,
                    "fear_distress_boost": prediction.fear_distress_boost_applied,
                    "priority_score": original_score,  # Pure clinical priority (not adjusted)
                    "priority_adjustment_disabled": True  # For dashboard risk segmentation
                }

            logger.info(
                f"[ORCHESTRATOR] Take-up prediction applied to {prediction_count} interventions "
                f"(priority scores preserved, take_up_likelihood stored for dashboard)"
            )

        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Take-up prediction failed (continuing without): {e}")

        # Store all interventions
        result.interventions = all_interventions
        result.total_generated = len(all_interventions)

        logger.info(
            f"[ORCHESTRATOR] Generated {result.total_generated} interventions: "
            f"REVENUE={result.revenue_count} (potential: {result.total_revenue_potential}), "
            f"RETENTION={result.retention_count}, QUALITY={result.quality_count}"
        )

        return result

    except Exception as e:
        logger.error(f"[ORCHESTRATOR] Failed to generate interventions: {e}", exc_info=True)
        return result


async def generate_and_save_interventions(
    extraction_id: uuid.UUID,
    school_id: Optional[uuid.UUID] = None,
    consultation_insights_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Generate all interventions and save to database.

    Convenience function that combines generation and persistence.

    Args:
        extraction_id: UUID of the extraction
        school_id: UUID of the school
        consultation_insights_id: UUID of consultation_insights record

    Returns:
        Dict with save results including counts
    """
    from services.supabase_service import save_categorized_interventions_batch

    # Generate all interventions
    result = await generate_all_interventions(
        extraction_id=extraction_id,
        school_id=school_id,
        consultation_insights_id=consultation_insights_id
    )

    if result.total_generated == 0:
        logger.info(f"[ORCHESTRATOR] No interventions to save for extraction {extraction_id}")
        return {
            "success": True,
            "total_saved": 0,
            "by_category": {"REVENUE": 0, "RETENTION": 0, "QUALITY": 0}
        }

    # Save to database
    save_result = save_categorized_interventions_batch(result.interventions)

    logger.info(
        f"[ORCHESTRATOR] Saved {save_result.get('total_saved', 0)} interventions "
        f"for extraction {extraction_id}"
    )

    # Add revenue potential to result
    save_result["total_revenue_potential"] = result.total_revenue_potential

    return save_result


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_intervention_summary(extraction_id: uuid.UUID) -> Dict[str, Any]:
    """
    Get a summary of interventions for an extraction.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        Dict with intervention counts and top interventions
    """
    from services.supabase_service import get_categorized_interventions

    interventions = get_categorized_interventions(extraction_id)

    if not interventions:
        return {
            "total": 0,
            "by_category": {},
            "by_priority": {},
            "top_interventions": [],
            "total_revenue_potential": 0
        }

    # Count by category
    by_category = {}
    by_priority = {}
    total_revenue = 0

    for intervention in interventions:
        category = intervention.get("intervention_category", "UNKNOWN")
        priority = intervention.get("priority_level", "MEDIUM")

        by_category[category] = by_category.get(category, 0) + 1
        by_priority[priority] = by_priority.get(priority, 0) + 1

        if category == "REVENUE":
            total_revenue += float(intervention.get("revenue_estimate", 0) or 0)

    # Get top 5 by priority score
    sorted_interventions = sorted(
        interventions,
        key=lambda x: x.get("priority_score", 0),
        reverse=True
    )
    top_5 = sorted_interventions[:5]

    return {
        "total": len(interventions),
        "by_category": by_category,
        "by_priority": by_priority,
        "top_interventions": [
            {
                "code": i.get("intervention_code"),
                "category": i.get("intervention_category"),
                "priority": i.get("priority_level"),
                "reason": i.get("trigger_reason"),
                "action": i.get("action")
            }
            for i in top_5
        ],
        "total_revenue_potential": total_revenue
    }


# =============================================================================
# MODULE INFO
# =============================================================================

__version__ = "2.1.0"
__author__ = "Unizy Health"
__all__ = [
    "Intervention",
    "InterventionResult",
    "generate_all_interventions",
    "generate_and_save_interventions",
    "get_intervention_summary",
]

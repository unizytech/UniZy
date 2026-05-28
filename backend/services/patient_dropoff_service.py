"""
Patient Dropoff Risk Assessment Service (AI-Only)

Calculates patient drop-off probability (retention risk) based on AI-extracted
consultation insights and emotional segments.

5 Churn Indicators:
1. is_financial_risk (25%): Financial concerns, price sensitivity
2. is_competitor_risk (10%): Considering other healthcare providers
3. is_access_risk (10%): Access/logistics barriers to care
4. is_dissatisfaction_risk (25%): Anxiety worsened, weak rapport
5. is_compliance_risk (30%): Low compliance likelihood, treatment confusion

Risk Levels:
- CRITICAL: 70-95% probability
- HIGH: 50-69% probability
- MEDIUM: 30-49% probability
- LOW: 5-29% probability

Uses AI-extracted consultation insights for competitor and access signals
(no fallback to extraction_segments).

Author: 1hat Health
Version: 2.0.0 (AI-Only - Removed segment-based fallback)
"""

import logging
import uuid
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def calculate_and_save_dropoff_risk(
    extraction_id: uuid.UUID,
    consultation_insights: Dict[str, Any],
    doctor_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None,
    consultation_insights_id: Optional[uuid.UUID] = None
) -> Optional[uuid.UUID]:
    """
    Calculate patient dropoff risk using AI insights and save to database.

    Main entry point for background task integration.
    Uses AI-extracted consultation insights (no segment-based fallback).

    Combines:
    - AI-extracted signals: competitor_signals, access_logistics_signals, medication_signals
    - Emotional segments: ANXIETY_POST_CONSULTATION, FINANCIAL_CONCERNS, etc. (from DB)
    - FOLLOW_UP segment: for vague timeline check (from DB)

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
        save_patient_dropoff_risk
    )
    from services.consultation_insights_prompts import map_insights_to_dropoff_risk

    try:
        # Get all segments from extraction (for emotional data)
        segments = get_extraction_segments(extraction_id)
        segment_map = {s["segment_code"]: s.get("segment_value", {}) for s in segments}

        # Build emotional segments dict (7 segments as of Jan 2026)
        emotional_segments = {
            "ANXIETY_POST_CONSULTATION": segment_map.get("ANXIETY_POST_CONSULTATION", {}),
            "FINANCIAL_CONCERNS": segment_map.get("FINANCIAL_CONCERNS", {}),
            "OTHER_EMOTIONS_DETECTED": segment_map.get("OTHER_EMOTIONS_DETECTED", {}),
            "TREATMENT_COMPLIANCE_LIKELIHOOD": segment_map.get("TREATMENT_COMPLIANCE_LIKELIHOOD", {}),
            "DOCTOR_COMMUNICATION_STYLE": segment_map.get("DOCTOR_COMMUNICATION_STYLE", {}),
            "INTERACTION_DYNAMICS": segment_map.get("INTERACTION_DYNAMICS", {}),
            "CONGRUENCE_SUMMARY": segment_map.get("CONGRUENCE_SUMMARY", {}),
        }

        # Get FOLLOW_UP segment
        follow_up_segment = segment_map.get("FOLLOW_UP", {})

        # Use AI-extracted consultation insights directly
        # These contain competitor_signals, access_logistics_signals, medication_signals
        insights = {
            "competitor_signals": consultation_insights.get("competitor_signals", {}),
            "access_logistics_signals": consultation_insights.get("access_logistics_signals", {}),
            "medication_signals": consultation_insights.get("medication_signals", {})
        }

        logger.debug(
            f"[DROPOFF_RISK] AI inputs for extraction {extraction_id}: "
            f"competitor_intent={insights.get('competitor_signals', {}).get('competitor_intent_detected', False)}, "
            f"access_barriers={insights.get('access_logistics_signals', {}).get('access_barriers_detected', False)}, "
            f"meds={insights.get('medication_signals', {}).get('total_medications_prescribed', 0)}"
        )

        # Calculate dropoff risk using AI insights
        result = map_insights_to_dropoff_risk(
            insights=insights,
            emotional_segments=emotional_segments,
            follow_up_segment=follow_up_segment
        )

        # Prepare data for database
        # Note: Raw AI signals are stored in consultation_insights table
        # input_data here contains only minimal context for audit/debugging
        risk_data = {
            "extraction_id": str(extraction_id),
            "patient_id": str(patient_id) if patient_id else None,
            "doctor_id": str(doctor_id) if doctor_id else None,
            "consultation_insights_id": str(consultation_insights_id) if consultation_insights_id else None,
            "dropoff_probability": result["dropoff_probability"],
            "risk_level": result["risk_level"],
            "is_financial_risk": result["is_financial_risk"],
            "is_competitor_risk": result["is_competitor_risk"],
            "is_dissatisfaction_risk": result["is_dissatisfaction_risk"],
            "is_access_risk": result["is_access_risk"],
            "is_compliance_risk": result["is_compliance_risk"],
            "financial_risk_reasons": result["financial_risk_reasons"],
            "competitor_risk_reasons": result["competitor_risk_reasons"],
            "dissatisfaction_risk_reasons": result["dissatisfaction_risk_reasons"],
            "access_risk_reasons": result["access_risk_reasons"],
            "compliance_risk_reasons": result["compliance_risk_reasons"],
            "anxiety_pre_level": result["anxiety_pre_level"],
            "anxiety_post_level": result["anxiety_post_level"],
            "anxiety_trajectory": result["anxiety_trajectory"],
            "anxiety_modifier": result["anxiety_modifier"],
            "compliance_likelihood": result["compliance_likelihood"],
            "compliance_modifier": result["compliance_modifier"],
            "base_probability": result["base_probability"],
            "indicator_count": result["indicator_count"],
            "primary_risk_driver": result["primary_risk_driver"],
            # Note: input_data removed - raw signals stored in consultation_insights table
            "calculation_version": "2.0.0"  # AI-only version
        }

        # Save to database
        risk_id = save_patient_dropoff_risk(risk_data)

        logger.info(
            f"[DROPOFF_RISK] Saved AI-based assessment {risk_id} for extraction {extraction_id}: "
            f"probability={result['dropoff_probability']}%, risk_level={result['risk_level']}, "
            f"indicators={result['indicator_count']}, driver={result['primary_risk_driver']}"
        )

        return risk_id

    except Exception as e:
        logger.error(
            f"[DROPOFF_RISK] Failed to calculate/save for extraction {extraction_id}: {e}",
            exc_info=True
        )
        return None


# =============================================================================
# MODULE INFO
# =============================================================================

__version__ = "2.0.0"
__author__ = "1hat Health"
__all__ = [
    "calculate_and_save_dropoff_risk"
]

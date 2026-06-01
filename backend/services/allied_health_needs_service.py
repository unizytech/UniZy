"""
Allied Health Needs Assessment Service (AI-Only)

Uses AI-extracted consultation insights to identify referral needs for allied health services:

1. is_mental_health: Severe anxiety, depression/distress, or mental health support potential
2. is_nutritional_health: Metabolic conditions + diet instructions or nutritional counseling potential
3. is_physiotherapy: Musculoskeletal/injury + physiotherapy discussed or potential
4. is_homecare: Age > 70 + chronic + mobility issues or homecare potential
5. is_sleep_therapy: Sleep symptoms + risk factors or sleep therapy potential
6. is_rehab_cardiac: Cardiac event + cardiac rehab discussed or potential
7. is_rehab_common: Stroke/orthopedic surgery + rehab discussed or potential
8. is_treatment_education: New diagnosis + understanding barrier or education potential
9. is_wellness: Lifestyle disease + prevention discussed or wellness potential

Priority Level:
- HIGH: 4+ indicators OR is_mental_health + any other
- MEDIUM: 2-3 indicators
- LOW: 1 indicator
- NONE: 0 indicators

Includes [POTENTIAL] markers for missed opportunities where student may benefit
from allied health services even if not explicitly discussed.

Author: Unizy Health
Version: 2.0.0 (AI-Only - Removed keyword-based logic)
"""

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class PriorityLevel(Enum):
    """Priority levels for allied health needs."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class AlliedHealthResult:
    """
    Result of allied health needs assessment.

    Attributes:
        priority_level: Consolidated priority (NONE, LOW, MEDIUM, HIGH)
        is_*: 9 boolean indicators
        *_reasons: Evidence for each indicator (includes [POTENTIAL] markers)
    """
    priority_level: PriorityLevel = PriorityLevel.NONE

    is_mental_health: bool = False
    is_nutritional_health: bool = False
    is_physiotherapy: bool = False
    is_homecare: bool = False
    is_sleep_therapy: bool = False
    is_rehab_cardiac: bool = False
    is_rehab_common: bool = False
    is_treatment_education: bool = False
    is_wellness: bool = False

    mental_health_reasons: List[str] = field(default_factory=list)
    nutritional_health_reasons: List[str] = field(default_factory=list)
    physiotherapy_reasons: List[str] = field(default_factory=list)
    homecare_reasons: List[str] = field(default_factory=list)
    sleep_therapy_reasons: List[str] = field(default_factory=list)
    rehab_cardiac_reasons: List[str] = field(default_factory=list)
    rehab_common_reasons: List[str] = field(default_factory=list)
    treatment_education_reasons: List[str] = field(default_factory=list)
    wellness_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "priority_level": self.priority_level.value,
            "is_mental_health": self.is_mental_health,
            "is_nutritional_health": self.is_nutritional_health,
            "is_physiotherapy": self.is_physiotherapy,
            "is_homecare": self.is_homecare,
            "is_sleep_therapy": self.is_sleep_therapy,
            "is_rehab_cardiac": self.is_rehab_cardiac,
            "is_rehab_common": self.is_rehab_common,
            "is_treatment_education": self.is_treatment_education,
            "is_wellness": self.is_wellness,
            "mental_health_reasons": self.mental_health_reasons,
            "nutritional_health_reasons": self.nutritional_health_reasons,
            "physiotherapy_reasons": self.physiotherapy_reasons,
            "homecare_reasons": self.homecare_reasons,
            "sleep_therapy_reasons": self.sleep_therapy_reasons,
            "rehab_cardiac_reasons": self.rehab_cardiac_reasons,
            "rehab_common_reasons": self.rehab_common_reasons,
            "treatment_education_reasons": self.treatment_education_reasons,
            "wellness_reasons": self.wellness_reasons
        }


# =============================================================================
# DATABASE INTEGRATION (AI-Only)
# =============================================================================

async def calculate_and_save_allied_needs(
    extraction_id: uuid.UUID,
    consultation_insights: Dict[str, Any],
    counsellor_id: Optional[uuid.UUID] = None,
    student_id: Optional[uuid.UUID] = None,
    consultation_insights_id: Optional[uuid.UUID] = None
) -> Optional[uuid.UUID]:
    """
    Calculate allied health needs using AI insights and save to database.

    Main entry point for background task integration.
    Uses AI-extracted consultation insights (no keyword-based fallback).

    Args:
        extraction_id: UUID of the extraction
        consultation_insights: AI-extracted consultation insights (REQUIRED)
        counsellor_id: Optional counsellor UUID
        student_id: Optional student UUID

    Returns:
        UUID of saved assessment, or None on error
    """
    from services.supabase_service import (
        get_clinical_severity_by_extraction,
        get_other_clinical_needs_by_extraction,
        save_allied_health_needs
    )
    from services.consultation_insights_prompts import map_insights_to_allied_health_needs

    try:
        # Get clinical severity for is_chronic and reference
        severity_assessment = get_clinical_severity_by_extraction(str(extraction_id))
        is_chronic = False
        clinical_severity_id = None

        if severity_assessment:
            is_chronic = severity_assessment.get("is_chronic", False)
            # Also check input_data
            input_data = severity_assessment.get("input_data", {})
            if isinstance(input_data, dict):
                is_chronic = is_chronic or input_data.get("is_chronic", False)
            clinical_severity_id = severity_assessment.get("id")

        # Get other clinical needs reference
        other_needs = get_other_clinical_needs_by_extraction(str(extraction_id))
        other_clinical_needs_id = other_needs.get("id") if other_needs else None

        # Get student age from insights
        student_signals = consultation_insights.get("student_signals", {})
        patient_age = student_signals.get("estimated_age_years")

        # Use AI insights mapping function
        result_dict = map_insights_to_allied_health_needs(
            insights=consultation_insights,
            is_chronic=is_chronic,
            patient_age=patient_age
        )

        # Build result from AI insights
        result = AlliedHealthResult(
            priority_level=PriorityLevel(result_dict["priority_level"]),
            is_mental_health=result_dict["is_mental_health"],
            is_nutritional_health=result_dict["is_nutritional_health"],
            is_physiotherapy=result_dict["is_physiotherapy"],
            is_homecare=result_dict["is_homecare"],
            is_sleep_therapy=result_dict["is_sleep_therapy"],
            is_rehab_cardiac=result_dict["is_rehab_cardiac"],
            is_rehab_common=result_dict["is_rehab_common"],
            is_treatment_education=result_dict["is_treatment_education"],
            is_wellness=result_dict["is_wellness"],
            mental_health_reasons=result_dict.get("mental_health_reasons", []),
            nutritional_health_reasons=result_dict.get("nutritional_health_reasons", []),
            physiotherapy_reasons=result_dict.get("physiotherapy_reasons", []),
            homecare_reasons=result_dict.get("homecare_reasons", []),
            sleep_therapy_reasons=result_dict.get("sleep_therapy_reasons", []),
            rehab_cardiac_reasons=result_dict.get("rehab_cardiac_reasons", []),
            rehab_common_reasons=result_dict.get("rehab_common_reasons", []),
            treatment_education_reasons=result_dict.get("treatment_education_reasons", []),
            wellness_reasons=result_dict.get("wellness_reasons", [])
        )

        # Prepare data for database
        # Note: Raw AI signals are stored in consultation_insights table
        # input_data here contains only minimal context for audit/debugging
        needs_data = {
            "extraction_id": str(extraction_id),
            "student_id": str(student_id) if student_id else None,
            "counsellor_id": str(counsellor_id) if counsellor_id else None,
            "consultation_insights_id": str(consultation_insights_id) if consultation_insights_id else None,
            "priority_level": result.priority_level.value,
            "is_mental_health": result.is_mental_health,
            "is_nutritional_health": result.is_nutritional_health,
            "is_physiotherapy": result.is_physiotherapy,
            "is_homecare": result.is_homecare,
            "is_sleep_therapy": result.is_sleep_therapy,
            "is_rehab_cardiac": result.is_rehab_cardiac,
            "is_rehab_common": result.is_rehab_common,
            "is_treatment_education": result.is_treatment_education,
            "is_wellness": result.is_wellness,
            "mental_health_reasons": result.mental_health_reasons,
            "nutritional_health_reasons": result.nutritional_health_reasons,
            "physiotherapy_reasons": result.physiotherapy_reasons,
            "homecare_reasons": result.homecare_reasons,
            "sleep_therapy_reasons": result.sleep_therapy_reasons,
            "rehab_cardiac_reasons": result.rehab_cardiac_reasons,
            "rehab_common_reasons": result.rehab_common_reasons,
            "treatment_education_reasons": result.treatment_education_reasons,
            "wellness_reasons": result.wellness_reasons,
            # Note: input_data removed - raw signals stored in consultation_insights table
            "clinical_severity_id": str(clinical_severity_id) if clinical_severity_id else None,
            "other_clinical_needs_id": str(other_clinical_needs_id) if other_clinical_needs_id else None,
            "calculation_version": "2.0.0"  # AI-only version
        }

        # Save to database
        needs_id = save_allied_health_needs(needs_data)

        logger.info(
            f"[ALLIED_HEALTH] Saved AI-based assessment {needs_id} for extraction {extraction_id}: "
            f"priority={result.priority_level.value}, "
            f"indicators_true={result_dict.get('true_count', 0)}"
        )

        return needs_id

    except Exception as e:
        logger.error(
            f"[ALLIED_HEALTH] Failed to calculate/save for extraction {extraction_id}: {e}",
            exc_info=True
        )
        return None


# =============================================================================
# MODULE INFO
# =============================================================================

__version__ = "2.0.0"
__author__ = "Unizy Health"
__all__ = [
    # Data classes
    "AlliedHealthResult",
    "PriorityLevel",

    # Main function
    "calculate_and_save_allied_needs",
]

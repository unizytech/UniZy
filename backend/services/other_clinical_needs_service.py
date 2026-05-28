"""
Other Clinical Needs Assessment Service (AI-Only)

Uses AI-extracted consultation insights to identify additional care requirements
beyond the current consultation:

- is_followup_diagnostics: Patient needs diagnostic tests before/at next visit
- is_recurring_diagnostics: Patient needs periodic monitoring tests
- is_rx_refill: Patient will need prescription refill

Priority Level (consolidated score):
  - HIGH: All 3 flags TRUE, OR (recurring_diagnostics + rx_refill) both TRUE
  - MEDIUM: 2 flags TRUE, OR recurring_diagnostics alone
  - LOW: 1 flag TRUE
  - NONE: 0 flags TRUE

Triggered automatically after consultation insights extraction completes.

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
    """Priority levels for other clinical needs."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ClinicalNeedsResult:
    """
    Result of clinical needs assessment.

    Attributes:
        priority_level: Consolidated priority (NONE, LOW, MEDIUM, HIGH)
        is_followup_diagnostics: Patient needs tests before/at next visit
        is_recurring_diagnostics: Patient needs periodic monitoring tests
        is_rx_refill: Patient will need prescription refill
        followup_diagnostics_reasons: Evidence for is_followup_diagnostics
        recurring_diagnostics_reasons: Evidence for is_recurring_diagnostics
        rx_refill_reasons: Evidence for is_rx_refill
    """
    priority_level: PriorityLevel = PriorityLevel.NONE
    is_followup_diagnostics: bool = False
    is_recurring_diagnostics: bool = False
    is_rx_refill: bool = False
    followup_diagnostics_reasons: List[str] = field(default_factory=list)
    recurring_diagnostics_reasons: List[str] = field(default_factory=list)
    rx_refill_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "priority_level": self.priority_level.value,
            "is_followup_diagnostics": self.is_followup_diagnostics,
            "is_recurring_diagnostics": self.is_recurring_diagnostics,
            "is_rx_refill": self.is_rx_refill,
            "followup_diagnostics_reasons": self.followup_diagnostics_reasons,
            "recurring_diagnostics_reasons": self.recurring_diagnostics_reasons,
            "rx_refill_reasons": self.rx_refill_reasons
        }


# =============================================================================
# DATABASE INTEGRATION (AI-Only)
# =============================================================================

async def calculate_and_save_needs(
    extraction_id: uuid.UUID,
    consultation_insights: Dict[str, Any],
    doctor_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None,
    consultation_insights_id: Optional[uuid.UUID] = None
) -> Optional[uuid.UUID]:
    """
    Calculate other clinical needs using AI insights and save to database.

    Main entry point for background task integration.
    Uses AI-extracted consultation insights (no keyword-based fallback).

    Args:
        extraction_id: UUID of the medical extraction
        consultation_insights: AI-extracted consultation insights (REQUIRED)
        doctor_id: Optional doctor UUID
        patient_id: Optional patient UUID

    Returns:
        UUID of saved assessment, or None on error
    """
    from services.supabase_service import (
        get_clinical_severity_by_extraction,
        save_other_clinical_needs
    )
    from services.consultation_insights_prompts import map_insights_to_other_clinical_needs

    try:
        # Use AI insights mapping function
        result_dict = map_insights_to_other_clinical_needs(consultation_insights)

        # Get clinical severity assessment for reference
        severity_assessment = get_clinical_severity_by_extraction(str(extraction_id))
        clinical_severity_id = None
        is_chronic = False

        if severity_assessment:
            clinical_severity_id = severity_assessment.get("id")
            is_chronic = severity_assessment.get("is_chronic", False)

        # Build result from AI insights
        result = ClinicalNeedsResult(
            priority_level=PriorityLevel(result_dict["priority_level"]),
            is_followup_diagnostics=result_dict["is_followup_diagnostics"],
            is_recurring_diagnostics=result_dict["is_recurring_diagnostics"],
            is_rx_refill=result_dict["is_rx_refill"],
            followup_diagnostics_reasons=result_dict.get("other_clinical_needs_reasons", []),
            recurring_diagnostics_reasons=[],  # Combined in other_clinical_needs_reasons
            rx_refill_reasons=[]  # Combined in other_clinical_needs_reasons
        )

        # Prepare data for database
        # Note: Raw AI signals are stored in consultation_insights table
        # input_data here contains only minimal context for audit/debugging
        needs_data = {
            "extraction_id": str(extraction_id),
            "patient_id": str(patient_id) if patient_id else None,
            "doctor_id": str(doctor_id) if doctor_id else None,
            "consultation_insights_id": str(consultation_insights_id) if consultation_insights_id else None,
            "priority_level": result.priority_level.value,
            "is_followup_diagnostics": result.is_followup_diagnostics,
            "is_recurring_diagnostics": result.is_recurring_diagnostics,
            "is_rx_refill": result.is_rx_refill,
            "followup_diagnostics_reasons": result_dict.get("other_clinical_needs_reasons", []),
            "recurring_diagnostics_reasons": [],
            "rx_refill_reasons": [],
            # Note: input_data removed - raw signals stored in consultation_insights table
            "clinical_severity_id": str(clinical_severity_id) if clinical_severity_id else None,
            "calculation_version": "2.0.0"  # AI-only version
        }

        # Save to database
        needs_id = save_other_clinical_needs(needs_data)

        logger.info(
            f"[CLINICAL_NEEDS] Saved AI-based assessment {needs_id} for extraction {extraction_id}: "
            f"priority={result.priority_level.value}, "
            f"followup_diag={result.is_followup_diagnostics}, "
            f"recurring_diag={result.is_recurring_diagnostics}, "
            f"rx_refill={result.is_rx_refill}"
        )

        return needs_id

    except Exception as e:
        logger.error(
            f"[CLINICAL_NEEDS] Failed to calculate/save for extraction {extraction_id}: {e}",
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
    "ClinicalNeedsResult",
    "PriorityLevel",

    # Main function
    "calculate_and_save_needs",
]

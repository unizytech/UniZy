"""
Clinical Severity API Router

Provides endpoints to retrieve clinical severity assessments for extractions.

Clinical severity represents the "stakes" of non-adherence:
- LOW: Routine care, low stakes
- MEDIUM: Moderate stakes, needs attention
- HIGH: High stakes, requires intervention (or critical condition)
"""

import uuid
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime

from services.supabase_service import (
    get_clinical_severity_assessment,
    get_patient_severity_history,
    get_severity_statistics
)

router = APIRouter(
    prefix="/api/v1/clinical-severity",
    tags=["clinical-severity"]
)


# ============================================================================
# Response Models
# ============================================================================

class ScoreBreakdown(BaseModel):
    """Breakdown of severity score components."""
    icd_score: int = 0
    specialty_score: int = 0
    surgical_score: int = 0
    modifier_score: int = 0
    base_score: int = 0
    modifier_breakdown: Optional[Dict[str, int]] = None


class ClinicalSeverityResponse(BaseModel):
    """Response model for clinical severity assessment."""
    id: str
    extraction_id: str
    patient_id: Optional[str] = None
    doctor_id: Optional[str] = None

    # Severity Result
    severity_level: str  # LOW, MEDIUM, HIGH
    total_score: int

    # Override Info
    was_overridden: bool
    override_reason: Optional[str] = None

    # Score Details
    score_breakdown: Dict[str, Any]
    contributing_factors: List[str]

    # Input Data (for debugging)
    input_data: Optional[Dict[str, Any]] = None

    # Metadata
    calculation_version: str
    created_at: str


class SeverityHistoryItem(BaseModel):
    """Item in severity history list."""
    id: str
    extraction_id: str
    severity_level: str
    total_score: int
    was_overridden: bool
    created_at: str
    extraction_created_at: Optional[str] = None


class SeverityStatistics(BaseModel):
    """Aggregate severity statistics."""
    LOW: int
    MEDIUM: int
    HIGH: int
    total: int
    period_days: int


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/extraction/{extraction_id}", response_model=ClinicalSeverityResponse)
async def get_severity_for_extraction(extraction_id: str):
    """
    Get clinical severity assessment for a specific extraction.

    Args:
        extraction_id: UUID of the medical extraction

    Returns:
        ClinicalSeverityResponse with complete severity data

    Raises:
        404: If no severity assessment found for extraction
    """
    try:
        extraction_uuid = uuid.UUID(extraction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction_id format")

    assessment = get_clinical_severity_assessment(extraction_uuid)

    if not assessment:
        raise HTTPException(
            status_code=404,
            detail="No severity assessment found for extraction"
        )

    return ClinicalSeverityResponse(
        id=assessment["id"],
        extraction_id=assessment["extraction_id"],
        patient_id=assessment.get("patient_id"),
        doctor_id=assessment.get("doctor_id"),
        severity_level=assessment["severity_level"],
        total_score=assessment["total_score"],
        was_overridden=assessment.get("was_overridden", False),
        override_reason=assessment.get("override_reason"),
        score_breakdown=assessment.get("score_breakdown", {}),
        contributing_factors=assessment.get("contributing_factors", []),
        input_data=assessment.get("input_data"),
        calculation_version=assessment.get("calculation_version", "1.0.0"),
        created_at=assessment["created_at"]
    )


@router.get("/patient/{patient_id}/history")
async def get_patient_severity_history_endpoint(
    patient_id: str,
    limit: int = Query(default=10, le=50, ge=1)
) -> List[SeverityHistoryItem]:
    """
    Get clinical severity assessment history for a patient.

    Args:
        patient_id: UUID of the patient
        limit: Maximum number of records (default 10, max 50)

    Returns:
        List of severity assessments, ordered by created_at descending
    """
    try:
        patient_uuid = uuid.UUID(patient_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid patient_id format")

    history = get_patient_severity_history(patient_uuid, limit)

    result = []
    for item in history:
        extraction_data = item.get("medical_extractions", {}) or {}
        result.append(SeverityHistoryItem(
            id=item["id"],
            extraction_id=item["extraction_id"],
            severity_level=item["severity_level"],
            total_score=item["total_score"],
            was_overridden=item.get("was_overridden", False),
            created_at=item["created_at"],
            extraction_created_at=extraction_data.get("created_at")
        ))

    return result


@router.get("/patient/{patient_id}/latest", response_model=Optional[ClinicalSeverityResponse])
async def get_patient_latest_severity(patient_id: str):
    """
    Get the most recent clinical severity assessment for a patient.

    Args:
        patient_id: UUID of the patient

    Returns:
        Latest ClinicalSeverityResponse or null if none found
    """
    try:
        patient_uuid = uuid.UUID(patient_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid patient_id format")

    history = get_patient_severity_history(patient_uuid, limit=1)

    if not history:
        return None

    assessment = history[0]
    return ClinicalSeverityResponse(
        id=assessment["id"],
        extraction_id=assessment["extraction_id"],
        patient_id=assessment.get("patient_id"),
        doctor_id=assessment.get("doctor_id"),
        severity_level=assessment["severity_level"],
        total_score=assessment["total_score"],
        was_overridden=assessment.get("was_overridden", False),
        override_reason=assessment.get("override_reason"),
        score_breakdown=assessment.get("score_breakdown", {}),
        contributing_factors=assessment.get("contributing_factors", []),
        input_data=assessment.get("input_data"),
        calculation_version=assessment.get("calculation_version", "1.0.0"),
        created_at=assessment["created_at"]
    )


@router.get("/statistics", response_model=SeverityStatistics)
async def get_severity_statistics_endpoint(
    doctor_id: Optional[str] = None,
    days: int = Query(default=30, le=365, ge=1)
):
    """
    Get aggregate severity statistics.

    Args:
        doctor_id: Optional filter by doctor UUID
        days: Number of days to look back (default 30, max 365)

    Returns:
        Counts by severity level
    """
    doctor_uuid = None
    if doctor_id:
        try:
            doctor_uuid = uuid.UUID(doctor_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid doctor_id format")

    stats = get_severity_statistics(doctor_uuid, days)

    return SeverityStatistics(
        LOW=stats.get("LOW", 0),
        MEDIUM=stats.get("MEDIUM", 0),
        HIGH=stats.get("HIGH", 0),
        total=stats.get("total", 0),
        period_days=stats.get("period_days", days)
    )

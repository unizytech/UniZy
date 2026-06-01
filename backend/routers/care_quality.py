"""
Care Quality Risk API Router

Provides endpoints to retrieve care quality risk assessments.

Care quality risk identifies 4 quality indicators:
- is_medication_issue: Drug interactions, allergies, contraindications (25% weight)
- is_missed_red_flag: Red flags not addressed in treatment (25% weight)
- is_incomplete_treatment: Missing investigations, diagnosis without treatment (25% weight)
- is_followup_gap: Serious diagnosis with vague follow-up (25% weight)

Risk levels:
- LOW: 5-29% score
- MEDIUM: 30-49% score
- HIGH: 50-69% score
- CRITICAL: 70-95% score
"""

import uuid
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from services.supabase_service import (
    get_care_quality_by_extraction,
    get_student_care_quality_history,
    get_high_risk_care_quality,
    get_care_quality_statistics
)

router = APIRouter(
    prefix="/api/v1/care-quality",
    tags=["care-quality"]
)


# ============================================================================
# Response Models
# ============================================================================

class CareQualityResponse(BaseModel):
    """Response model for care quality risk assessment."""
    id: str
    extraction_id: str
    student_id: Optional[str] = None
    counsellor_id: Optional[str] = None

    # Main output
    care_quality_score: float  # 0.00 to 100.00
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL

    # 4 quality indicators
    is_medication_issue: bool
    is_missed_red_flag: bool
    is_incomplete_treatment: bool
    is_followup_gap: bool

    # Reasons for each indicator
    medication_issue_reasons: List[str]
    missed_red_flag_reasons: List[str]
    incomplete_treatment_reasons: List[str]
    followup_gap_reasons: List[str]

    # Severities for each indicator
    medication_issue_severity: Optional[str] = None
    missed_red_flag_severity: Optional[str] = None
    incomplete_treatment_severity: Optional[str] = None
    followup_gap_severity: Optional[str] = None

    # Consolidated reasons (all indicators combined)
    reasons: List[str]

    # Score breakdown
    base_score: Optional[float] = None
    indicator_count: Optional[int] = None
    primary_risk_driver: Optional[str] = None

    # Input data for debugging
    input_data: Optional[Dict[str, Any]] = None

    # Metadata
    calculation_version: str
    created_at: str


class CareQualityHistoryItem(BaseModel):
    """Item in care quality history list."""
    id: str
    extraction_id: str
    care_quality_score: float
    risk_level: str
    is_medication_issue: bool
    is_missed_red_flag: bool
    is_incomplete_treatment: bool
    is_followup_gap: bool
    indicator_count: Optional[int] = None
    primary_risk_driver: Optional[str] = None
    created_at: str
    extraction_created_at: Optional[str] = None


class HighRiskExtraction(BaseModel):
    """High-risk extraction item."""
    id: str
    extraction_id: str
    student_id: Optional[str] = None
    counsellor_id: Optional[str] = None
    care_quality_score: float
    risk_level: str
    primary_risk_driver: Optional[str] = None
    indicator_count: Optional[int] = None
    reasons: List[str]
    created_at: str
    extraction_created_at: Optional[str] = None


class CareQualityStatistics(BaseModel):
    """Aggregate care quality risk statistics."""
    total_assessments: int
    low_count: int
    medium_count: int
    high_count: int
    critical_count: int
    average_score: float
    indicator_counts: Dict[str, int]
    period_days: int


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/extraction/{extraction_id}", response_model=CareQualityResponse)
async def get_care_quality_for_extraction(extraction_id: str):
    """
    Get care quality risk assessment for a specific extraction.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        CareQualityResponse with complete assessment data

    Raises:
        404: If no assessment found for extraction
    """
    try:
        uuid.UUID(extraction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction_id format")

    risk = get_care_quality_by_extraction(extraction_id)

    if not risk:
        raise HTTPException(
            status_code=404,
            detail="No care quality assessment found for extraction"
        )

    return CareQualityResponse(
        id=risk["id"],
        extraction_id=risk["extraction_id"],
        student_id=risk.get("student_id"),
        counsellor_id=risk.get("counsellor_id"),
        care_quality_score=float(risk.get("care_quality_score", 0)),
        risk_level=risk.get("risk_level", "LOW"),
        is_medication_issue=risk.get("is_medication_issue", False),
        is_missed_red_flag=risk.get("is_missed_red_flag", False),
        is_incomplete_treatment=risk.get("is_incomplete_treatment", False),
        is_followup_gap=risk.get("is_followup_gap", False),
        medication_issue_reasons=risk.get("medication_issue_reasons", []),
        missed_red_flag_reasons=risk.get("missed_red_flag_reasons", []),
        incomplete_treatment_reasons=risk.get("incomplete_treatment_reasons", []),
        followup_gap_reasons=risk.get("followup_gap_reasons", []),
        medication_issue_severity=risk.get("medication_issue_severity"),
        missed_red_flag_severity=risk.get("missed_red_flag_severity"),
        incomplete_treatment_severity=risk.get("incomplete_treatment_severity"),
        followup_gap_severity=risk.get("followup_gap_severity"),
        reasons=risk.get("reasons", []),
        base_score=float(risk["base_score"]) if risk.get("base_score") else None,
        indicator_count=risk.get("indicator_count"),
        primary_risk_driver=risk.get("primary_risk_driver"),
        input_data=risk.get("input_data"),
        calculation_version=risk.get("calculation_version", "1.0.0"),
        created_at=risk["created_at"]
    )


@router.get("/student/{student_id}/history")
async def get_student_care_quality_history_endpoint(
    student_id: str,
    limit: int = Query(default=10, le=50, ge=1)
) -> List[CareQualityHistoryItem]:
    """
    Get care quality risk assessment history for a student.

    Args:
        student_id: UUID of the student
        limit: Maximum number of records (default 10, max 50)

    Returns:
        List of assessments, ordered by created_at descending
    """
    try:
        uuid.UUID(student_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    history = get_student_care_quality_history(student_id, limit)

    result = []
    for item in history:
        extraction_data = item.get("extractions", {}) or {}
        result.append(CareQualityHistoryItem(
            id=item["id"],
            extraction_id=item["extraction_id"],
            care_quality_score=float(item.get("care_quality_score", 0)),
            risk_level=item.get("risk_level", "LOW"),
            is_medication_issue=item.get("is_medication_issue", False),
            is_missed_red_flag=item.get("is_missed_red_flag", False),
            is_incomplete_treatment=item.get("is_incomplete_treatment", False),
            is_followup_gap=item.get("is_followup_gap", False),
            indicator_count=item.get("indicator_count"),
            primary_risk_driver=item.get("primary_risk_driver"),
            created_at=item["created_at"],
            extraction_created_at=extraction_data.get("created_at")
        ))

    return result


@router.get("/high-risk")
async def get_high_risk_extractions_endpoint(
    counsellor_id: Optional[str] = None,
    limit: int = Query(default=50, le=100, ge=1)
) -> List[HighRiskExtraction]:
    """
    Get extractions with HIGH or CRITICAL care quality risk.

    Args:
        counsellor_id: Optional filter by counsellor UUID
        limit: Maximum number of records (default 50, max 100)

    Returns:
        List of high-risk extractions ordered by score descending
    """
    if counsellor_id:
        try:
            uuid.UUID(counsellor_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid counsellor_id format")

    extractions = get_high_risk_care_quality(counsellor_id, limit)

    result = []
    for item in extractions:
        extraction_data = item.get("extractions", {}) or {}
        result.append(HighRiskExtraction(
            id=item["id"],
            extraction_id=item["extraction_id"],
            student_id=item.get("student_id"),
            counsellor_id=item.get("counsellor_id"),
            care_quality_score=float(item.get("care_quality_score", 0)),
            risk_level=item.get("risk_level", "HIGH"),
            primary_risk_driver=item.get("primary_risk_driver"),
            indicator_count=item.get("indicator_count"),
            reasons=item.get("reasons", []),
            created_at=item["created_at"],
            extraction_created_at=extraction_data.get("created_at")
        ))

    return result


@router.get("/statistics", response_model=CareQualityStatistics)
async def get_care_quality_statistics_endpoint(
    counsellor_id: Optional[str] = None,
    days: int = Query(default=30, le=365, ge=1)
):
    """
    Get aggregate care quality risk statistics.

    Args:
        counsellor_id: Optional filter by counsellor UUID
        days: Number of days to look back (default 30, max 365)

    Returns:
        Counts and average score
    """
    if counsellor_id:
        try:
            uuid.UUID(counsellor_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid counsellor_id format")

    stats = get_care_quality_statistics(counsellor_id, days)

    return CareQualityStatistics(
        total_assessments=stats.get("total_assessments", 0),
        low_count=stats.get("low_count", 0),
        medium_count=stats.get("medium_count", 0),
        high_count=stats.get("high_count", 0),
        critical_count=stats.get("critical_count", 0),
        average_score=stats.get("average_score", 0.0),
        indicator_counts=stats.get("indicator_counts", {
            "medication_issue": 0,
            "missed_red_flag": 0,
            "incomplete_treatment": 0,
            "followup_gap": 0
        }),
        period_days=stats.get("period_days", days)
    )

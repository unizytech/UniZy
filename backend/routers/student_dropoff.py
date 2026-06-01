"""
Student Dropoff Risk API Router

Provides endpoints to retrieve student dropoff risk (retention risk) assessments.

Student dropoff risk identifies 5 churn indicators:
- is_financial_risk: Financial concerns or price sensitivity (25% weight)
- is_competitor_risk: Considering other healthcare providers (10% weight)
- is_dissatisfaction_risk: Dissatisfaction or weak rapport (25% weight)
- is_access_risk: Access or logistics barriers (10% weight)
- is_compliance_risk: Compliance concerns or treatment confusion (30% weight)

Risk levels:
- LOW: 5-29% probability
- MEDIUM: 30-49% probability
- HIGH: 50-69% probability
- CRITICAL: 70-95% probability
"""

import uuid
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from services.supabase_service import (
    get_dropoff_risk_by_extraction,
    get_student_dropoff_history,
    get_student_latest_dropoff_risk,
    get_high_risk_students,
    get_dropoff_risk_statistics
)

router = APIRouter(
    prefix="/api/v1/dropoff-risk",
    tags=["dropoff-risk"]
)


# ============================================================================
# Response Models
# ============================================================================

class DropoffRiskResponse(BaseModel):
    """Response model for student dropoff risk assessment."""
    id: str
    extraction_id: str
    student_id: Optional[str] = None
    counsellor_id: Optional[str] = None

    # Main output
    dropoff_probability: float  # 0.00 to 100.00
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL

    # 5 churn indicators
    is_financial_risk: bool
    is_competitor_risk: bool
    is_dissatisfaction_risk: bool
    is_access_risk: bool
    is_compliance_risk: bool

    # Reasons for each indicator
    financial_risk_reasons: List[str]
    competitor_risk_reasons: List[str]
    dissatisfaction_risk_reasons: List[str]
    access_risk_reasons: List[str]
    compliance_risk_reasons: List[str]

    # Anxiety trajectory data
    anxiety_pre_level: Optional[str] = None
    anxiety_post_level: Optional[str] = None
    anxiety_trajectory: Optional[str] = None
    anxiety_modifier: Optional[float] = None

    # Compliance data
    compliance_likelihood: Optional[str] = None
    compliance_modifier: Optional[float] = None

    # Score breakdown
    base_probability: Optional[float] = None
    indicator_count: Optional[int] = None
    primary_risk_driver: Optional[str] = None

    # Input data for debugging
    input_data: Optional[Dict[str, Any]] = None

    # Metadata
    calculation_version: str
    created_at: str


class DropoffHistoryItem(BaseModel):
    """Item in dropoff risk history list."""
    id: str
    extraction_id: str
    dropoff_probability: float
    risk_level: str
    is_financial_risk: bool
    is_competitor_risk: bool
    is_dissatisfaction_risk: bool
    is_access_risk: bool
    is_compliance_risk: bool
    indicator_count: Optional[int] = None
    primary_risk_driver: Optional[str] = None
    created_at: str
    extraction_created_at: Optional[str] = None


class HighRiskStudent(BaseModel):
    """High-risk student item."""
    id: str
    extraction_id: str
    student_id: Optional[str] = None
    counsellor_id: Optional[str] = None
    dropoff_probability: float
    risk_level: str
    primary_risk_driver: Optional[str] = None
    indicator_count: Optional[int] = None
    created_at: str
    extraction_created_at: Optional[str] = None


class DropoffStatistics(BaseModel):
    """Aggregate dropoff risk statistics."""
    total_assessments: int
    low_count: int
    medium_count: int
    high_count: int
    critical_count: int
    average_probability: float
    indicator_counts: Dict[str, int]
    period_days: int


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/extraction/{extraction_id}", response_model=DropoffRiskResponse)
async def get_dropoff_for_extraction(extraction_id: str):
    """
    Get student dropoff risk assessment for a specific extraction.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        DropoffRiskResponse with complete assessment data

    Raises:
        404: If no assessment found for extraction
    """
    try:
        uuid.UUID(extraction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction_id format")

    risk = get_dropoff_risk_by_extraction(extraction_id)

    if not risk:
        raise HTTPException(
            status_code=404,
            detail="No dropoff risk assessment found for extraction"
        )

    return DropoffRiskResponse(
        id=risk["id"],
        extraction_id=risk["extraction_id"],
        student_id=risk.get("student_id"),
        counsellor_id=risk.get("counsellor_id"),
        dropoff_probability=float(risk.get("dropoff_probability", 0)),
        risk_level=risk.get("risk_level", "LOW"),
        is_financial_risk=risk.get("is_financial_risk", False),
        is_competitor_risk=risk.get("is_competitor_risk", False),
        is_dissatisfaction_risk=risk.get("is_dissatisfaction_risk", False),
        is_access_risk=risk.get("is_access_risk", False),
        is_compliance_risk=risk.get("is_compliance_risk", False),
        financial_risk_reasons=risk.get("financial_risk_reasons", []),
        competitor_risk_reasons=risk.get("competitor_risk_reasons", []),
        dissatisfaction_risk_reasons=risk.get("dissatisfaction_risk_reasons", []),
        access_risk_reasons=risk.get("access_risk_reasons", []),
        compliance_risk_reasons=risk.get("compliance_risk_reasons", []),
        anxiety_pre_level=risk.get("anxiety_pre_level"),
        anxiety_post_level=risk.get("anxiety_post_level"),
        anxiety_trajectory=risk.get("anxiety_trajectory"),
        anxiety_modifier=float(risk["anxiety_modifier"]) if risk.get("anxiety_modifier") else None,
        compliance_likelihood=risk.get("compliance_likelihood"),
        compliance_modifier=float(risk["compliance_modifier"]) if risk.get("compliance_modifier") else None,
        base_probability=float(risk["base_probability"]) if risk.get("base_probability") else None,
        indicator_count=risk.get("indicator_count"),
        primary_risk_driver=risk.get("primary_risk_driver"),
        input_data=risk.get("input_data"),
        calculation_version=risk.get("calculation_version", "1.0.0"),
        created_at=risk["created_at"]
    )


@router.get("/student/{student_id}/history")
async def get_student_dropoff_history_endpoint(
    student_id: str,
    limit: int = Query(default=10, le=50, ge=1)
) -> List[DropoffHistoryItem]:
    """
    Get dropoff risk assessment history for a student.

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

    history = get_student_dropoff_history(student_id, limit)

    result = []
    for item in history:
        extraction_data = item.get("extractions", {}) or {}
        result.append(DropoffHistoryItem(
            id=item["id"],
            extraction_id=item["extraction_id"],
            dropoff_probability=float(item.get("dropoff_probability", 0)),
            risk_level=item.get("risk_level", "LOW"),
            is_financial_risk=item.get("is_financial_risk", False),
            is_competitor_risk=item.get("is_competitor_risk", False),
            is_dissatisfaction_risk=item.get("is_dissatisfaction_risk", False),
            is_access_risk=item.get("is_access_risk", False),
            is_compliance_risk=item.get("is_compliance_risk", False),
            indicator_count=item.get("indicator_count"),
            primary_risk_driver=item.get("primary_risk_driver"),
            created_at=item["created_at"],
            extraction_created_at=extraction_data.get("created_at")
        ))

    return result


@router.get("/student/{student_id}/latest", response_model=Optional[DropoffRiskResponse])
async def get_student_latest_dropoff(student_id: str):
    """
    Get the most recent dropoff risk assessment for a student.

    Args:
        student_id: UUID of the student

    Returns:
        Latest DropoffRiskResponse or null if none found
    """
    try:
        uuid.UUID(student_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    risk = get_student_latest_dropoff_risk(student_id)

    if not risk:
        return None

    return DropoffRiskResponse(
        id=risk["id"],
        extraction_id=risk["extraction_id"],
        student_id=risk.get("student_id"),
        counsellor_id=risk.get("counsellor_id"),
        dropoff_probability=float(risk.get("dropoff_probability", 0)),
        risk_level=risk.get("risk_level", "LOW"),
        is_financial_risk=risk.get("is_financial_risk", False),
        is_competitor_risk=risk.get("is_competitor_risk", False),
        is_dissatisfaction_risk=risk.get("is_dissatisfaction_risk", False),
        is_access_risk=risk.get("is_access_risk", False),
        is_compliance_risk=risk.get("is_compliance_risk", False),
        financial_risk_reasons=risk.get("financial_risk_reasons", []),
        competitor_risk_reasons=risk.get("competitor_risk_reasons", []),
        dissatisfaction_risk_reasons=risk.get("dissatisfaction_risk_reasons", []),
        access_risk_reasons=risk.get("access_risk_reasons", []),
        compliance_risk_reasons=risk.get("compliance_risk_reasons", []),
        anxiety_pre_level=risk.get("anxiety_pre_level"),
        anxiety_post_level=risk.get("anxiety_post_level"),
        anxiety_trajectory=risk.get("anxiety_trajectory"),
        anxiety_modifier=float(risk["anxiety_modifier"]) if risk.get("anxiety_modifier") else None,
        compliance_likelihood=risk.get("compliance_likelihood"),
        compliance_modifier=float(risk["compliance_modifier"]) if risk.get("compliance_modifier") else None,
        base_probability=float(risk["base_probability"]) if risk.get("base_probability") else None,
        indicator_count=risk.get("indicator_count"),
        primary_risk_driver=risk.get("primary_risk_driver"),
        input_data=risk.get("input_data"),
        calculation_version=risk.get("calculation_version", "1.0.0"),
        created_at=risk["created_at"]
    )


@router.get("/high-risk")
async def get_high_risk_students_endpoint(
    counsellor_id: Optional[str] = None,
    limit: int = Query(default=50, le=100, ge=1)
) -> List[HighRiskStudent]:
    """
    Get students with HIGH or CRITICAL dropoff risk.

    Args:
        counsellor_id: Optional filter by counsellor UUID
        limit: Maximum number of records (default 50, max 100)

    Returns:
        List of high-risk students ordered by probability descending
    """
    if counsellor_id:
        try:
            uuid.UUID(counsellor_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid counsellor_id format")

    patients = get_high_risk_students(counsellor_id, limit)

    result = []
    for item in patients:
        extraction_data = item.get("extractions", {}) or {}
        result.append(HighRiskStudent(
            id=item["id"],
            extraction_id=item["extraction_id"],
            student_id=item.get("student_id"),
            counsellor_id=item.get("counsellor_id"),
            dropoff_probability=float(item.get("dropoff_probability", 0)),
            risk_level=item.get("risk_level", "HIGH"),
            primary_risk_driver=item.get("primary_risk_driver"),
            indicator_count=item.get("indicator_count"),
            created_at=item["created_at"],
            extraction_created_at=extraction_data.get("created_at")
        ))

    return result


@router.get("/statistics", response_model=DropoffStatistics)
async def get_dropoff_statistics_endpoint(
    counsellor_id: Optional[str] = None,
    days: int = Query(default=30, le=365, ge=1)
):
    """
    Get aggregate dropoff risk statistics.

    Args:
        counsellor_id: Optional filter by counsellor UUID
        days: Number of days to look back (default 30, max 365)

    Returns:
        Counts and average probability
    """
    if counsellor_id:
        try:
            uuid.UUID(counsellor_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid counsellor_id format")

    stats = get_dropoff_risk_statistics(counsellor_id, days)

    return DropoffStatistics(
        total_assessments=stats.get("total_assessments", 0),
        low_count=stats.get("low_count", 0),
        medium_count=stats.get("medium_count", 0),
        high_count=stats.get("high_count", 0),
        critical_count=stats.get("critical_count", 0),
        average_probability=stats.get("average_probability", 0.0),
        indicator_counts=stats.get("indicator_counts", {
            "financial_risk": 0,
            "competitor_risk": 0,
            "dissatisfaction_risk": 0,
            "access_risk": 0,
            "compliance_risk": 0
        }),
        period_days=stats.get("period_days", days)
    )

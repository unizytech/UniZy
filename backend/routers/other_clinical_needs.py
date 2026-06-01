"""
Other Clinical Needs API Router

Provides endpoints to retrieve clinical needs assessments for extractions.

Clinical needs identifies three types of downstream care requirements:
- is_followup_diagnostics: Student needs diagnostic tests before/at next visit
- is_recurring_diagnostics: Student needs periodic tests (chronic conditions)
- is_rx_refill: Student will need prescription refill
"""

import uuid
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from services.supabase_service import (
    get_clinical_needs_by_extraction,
    get_student_clinical_needs_history,
    get_student_latest_clinical_needs,
    get_clinical_needs_statistics
)

router = APIRouter(
    prefix="/api/v1/clinical-needs",
    tags=["clinical-needs"]
)


# ============================================================================
# Response Models
# ============================================================================

class ClinicalNeedsResponse(BaseModel):
    """Response model for other clinical needs assessment."""
    id: str
    extraction_id: str
    student_id: Optional[str] = None
    counsellor_id: Optional[str] = None

    # Consolidated priority level
    priority_level: str  # NONE, LOW, MEDIUM, HIGH

    # Three boolean indicators
    is_followup_diagnostics: bool
    is_recurring_diagnostics: bool
    is_rx_refill: bool

    # Reasons for each indicator
    followup_diagnostics_reasons: List[str]
    recurring_diagnostics_reasons: List[str]
    rx_refill_reasons: List[str]

    # Input data (for debugging)
    input_data: Optional[Dict[str, Any]] = None

    # Reference to clinical severity
    clinical_severity_id: Optional[str] = None

    # Metadata
    calculation_version: str
    created_at: str


class NeedsHistoryItem(BaseModel):
    """Item in clinical needs history list."""
    id: str
    extraction_id: str
    priority_level: str
    is_followup_diagnostics: bool
    is_recurring_diagnostics: bool
    is_rx_refill: bool
    created_at: str
    extraction_created_at: Optional[str] = None


class NeedsStatistics(BaseModel):
    """Aggregate clinical needs statistics."""
    followup_diagnostics: int
    recurring_diagnostics: int
    rx_refill: int
    total: int
    period_days: int


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/extraction/{extraction_id}", response_model=ClinicalNeedsResponse)
async def get_needs_for_extraction(extraction_id: str):
    """
    Get other clinical needs assessment for a specific extraction.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        ClinicalNeedsResponse with complete needs data

    Raises:
        404: If no needs assessment found for extraction
    """
    try:
        uuid.UUID(extraction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction_id format")

    needs = get_clinical_needs_by_extraction(extraction_id)

    if not needs:
        raise HTTPException(
            status_code=404,
            detail="No clinical needs assessment found for extraction"
        )

    return ClinicalNeedsResponse(
        id=needs["id"],
        extraction_id=needs["extraction_id"],
        student_id=needs.get("student_id"),
        counsellor_id=needs.get("counsellor_id"),
        priority_level=needs.get("priority_level", "NONE"),
        is_followup_diagnostics=needs.get("is_followup_diagnostics", False),
        is_recurring_diagnostics=needs.get("is_recurring_diagnostics", False),
        is_rx_refill=needs.get("is_rx_refill", False),
        followup_diagnostics_reasons=needs.get("followup_diagnostics_reasons", []),
        recurring_diagnostics_reasons=needs.get("recurring_diagnostics_reasons", []),
        rx_refill_reasons=needs.get("rx_refill_reasons", []),
        input_data=needs.get("input_data"),
        clinical_severity_id=needs.get("clinical_severity_id"),
        calculation_version=needs.get("calculation_version", "1.2.0"),
        created_at=needs["created_at"]
    )


@router.get("/student/{student_id}/history")
async def get_student_needs_history_endpoint(
    student_id: str,
    limit: int = Query(default=10, le=50, ge=1)
) -> List[NeedsHistoryItem]:
    """
    Get clinical needs assessment history for a student.

    Args:
        student_id: UUID of the student
        limit: Maximum number of records (default 10, max 50)

    Returns:
        List of needs assessments, ordered by created_at descending
    """
    try:
        uuid.UUID(student_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    history = get_student_clinical_needs_history(student_id, limit)

    result = []
    for item in history:
        extraction_data = item.get("extractions", {}) or {}
        result.append(NeedsHistoryItem(
            id=item["id"],
            extraction_id=item["extraction_id"],
            priority_level=item.get("priority_level", "NONE"),
            is_followup_diagnostics=item.get("is_followup_diagnostics", False),
            is_recurring_diagnostics=item.get("is_recurring_diagnostics", False),
            is_rx_refill=item.get("is_rx_refill", False),
            created_at=item["created_at"],
            extraction_created_at=extraction_data.get("created_at")
        ))

    return result


@router.get("/student/{student_id}/latest", response_model=Optional[ClinicalNeedsResponse])
async def get_student_latest_needs(student_id: str):
    """
    Get the most recent clinical needs assessment for a student.

    Args:
        student_id: UUID of the student

    Returns:
        Latest ClinicalNeedsResponse or null if none found
    """
    try:
        uuid.UUID(student_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    needs = get_student_latest_clinical_needs(student_id)

    if not needs:
        return None

    return ClinicalNeedsResponse(
        id=needs["id"],
        extraction_id=needs["extraction_id"],
        student_id=needs.get("student_id"),
        counsellor_id=needs.get("counsellor_id"),
        priority_level=needs.get("priority_level", "NONE"),
        is_followup_diagnostics=needs.get("is_followup_diagnostics", False),
        is_recurring_diagnostics=needs.get("is_recurring_diagnostics", False),
        is_rx_refill=needs.get("is_rx_refill", False),
        followup_diagnostics_reasons=needs.get("followup_diagnostics_reasons", []),
        recurring_diagnostics_reasons=needs.get("recurring_diagnostics_reasons", []),
        rx_refill_reasons=needs.get("rx_refill_reasons", []),
        input_data=needs.get("input_data"),
        clinical_severity_id=needs.get("clinical_severity_id"),
        calculation_version=needs.get("calculation_version", "1.2.0"),
        created_at=needs["created_at"]
    )


@router.get("/statistics", response_model=NeedsStatistics)
async def get_needs_statistics_endpoint(
    counsellor_id: Optional[str] = None,
    days: int = Query(default=30, le=365, ge=1)
):
    """
    Get aggregate clinical needs statistics.

    Args:
        counsellor_id: Optional filter by counsellor UUID
        days: Number of days to look back (default 30, max 365)

    Returns:
        Counts for each indicator type
    """
    if counsellor_id:
        try:
            uuid.UUID(counsellor_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid counsellor_id format")

    stats = get_clinical_needs_statistics(counsellor_id, days)

    return NeedsStatistics(
        followup_diagnostics=stats.get("followup_diagnostics", 0),
        recurring_diagnostics=stats.get("recurring_diagnostics", 0),
        rx_refill=stats.get("rx_refill", 0),
        total=stats.get("total", 0),
        period_days=stats.get("period_days", days)
    )

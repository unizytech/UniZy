"""
Allied Health Needs API Router

Provides endpoints to retrieve allied health needs assessments for extractions.

Allied health needs identifies 9 types of referral needs:
- is_mental_health: Mental health support (severe anxiety, depression)
- is_nutritional_health: Nutritional counseling (diabetes/obesity + diet)
- is_physiotherapy: Physiotherapy referral (musculoskeletal/injury)
- is_homecare: Home care services (age>70 + chronic + mobility)
- is_sleep_therapy: Sleep therapy (snoring/apnea + obesity/HTN)
- is_rehab_cardiac: Cardiac rehabilitation (MI/ischemic/CABG)
- is_rehab_common: Common rehabilitation (ortho surgery/stroke)
- is_treatment_education: Treatment education (new diagnosis + understanding barrier)
- is_wellness: Wellness program (lifestyle disease + prevention)
"""

import uuid
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from services.supabase_service import (
    get_allied_health_by_extraction,
    get_student_allied_health_history,
    get_student_latest_allied_health,
    get_allied_health_statistics
)

router = APIRouter(
    prefix="/api/v1/allied-health",
    tags=["allied-health"]
)


# ============================================================================
# Response Models
# ============================================================================

class AlliedHealthResponse(BaseModel):
    """Response model for allied health needs assessment."""
    id: str
    extraction_id: str
    student_id: Optional[str] = None
    counsellor_id: Optional[str] = None

    # Consolidated priority level
    priority_level: str  # NONE, LOW, MEDIUM, HIGH

    # 9 boolean indicators
    is_mental_health: bool
    is_nutritional_health: bool
    is_physiotherapy: bool
    is_homecare: bool
    is_sleep_therapy: bool
    is_rehab_cardiac: bool
    is_rehab_common: bool
    is_treatment_education: bool
    is_wellness: bool

    # Reasons for each indicator
    mental_health_reasons: List[str]
    nutritional_health_reasons: List[str]
    physiotherapy_reasons: List[str]
    homecare_reasons: List[str]
    sleep_therapy_reasons: List[str]
    rehab_cardiac_reasons: List[str]
    rehab_common_reasons: List[str]
    treatment_education_reasons: List[str]
    wellness_reasons: List[str]

    # Input data (for debugging)
    input_data: Optional[Dict[str, Any]] = None

    # References
    clinical_severity_id: Optional[str] = None
    other_clinical_needs_id: Optional[str] = None

    # Metadata
    calculation_version: str
    created_at: str


class AlliedHistoryItem(BaseModel):
    """Item in allied health history list."""
    id: str
    extraction_id: str
    priority_level: str
    is_mental_health: bool
    is_nutritional_health: bool
    is_physiotherapy: bool
    is_homecare: bool
    is_sleep_therapy: bool
    is_rehab_cardiac: bool
    is_rehab_common: bool
    is_treatment_education: bool
    is_wellness: bool
    created_at: str
    extraction_created_at: Optional[str] = None


class AlliedStatistics(BaseModel):
    """Aggregate allied health statistics."""
    mental_health: int
    nutritional_health: int
    physiotherapy: int
    homecare: int
    sleep_therapy: int
    rehab_cardiac: int
    rehab_common: int
    treatment_education: int
    wellness: int
    total: int
    period_days: int


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/extraction/{extraction_id}", response_model=AlliedHealthResponse)
async def get_allied_for_extraction(extraction_id: str):
    """
    Get allied health needs assessment for a specific extraction.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        AlliedHealthResponse with complete assessment data

    Raises:
        404: If no assessment found for extraction
    """
    try:
        uuid.UUID(extraction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction_id format")

    needs = get_allied_health_by_extraction(extraction_id)

    if not needs:
        raise HTTPException(
            status_code=404,
            detail="No allied health assessment found for extraction"
        )

    return AlliedHealthResponse(
        id=needs["id"],
        extraction_id=needs["extraction_id"],
        student_id=needs.get("student_id"),
        counsellor_id=needs.get("counsellor_id"),
        priority_level=needs.get("priority_level", "NONE"),
        is_mental_health=needs.get("is_mental_health", False),
        is_nutritional_health=needs.get("is_nutritional_health", False),
        is_physiotherapy=needs.get("is_physiotherapy", False),
        is_homecare=needs.get("is_homecare", False),
        is_sleep_therapy=needs.get("is_sleep_therapy", False),
        is_rehab_cardiac=needs.get("is_rehab_cardiac", False),
        is_rehab_common=needs.get("is_rehab_common", False),
        is_treatment_education=needs.get("is_treatment_education", False),
        is_wellness=needs.get("is_wellness", False),
        mental_health_reasons=needs.get("mental_health_reasons", []),
        nutritional_health_reasons=needs.get("nutritional_health_reasons", []),
        physiotherapy_reasons=needs.get("physiotherapy_reasons", []),
        homecare_reasons=needs.get("homecare_reasons", []),
        sleep_therapy_reasons=needs.get("sleep_therapy_reasons", []),
        rehab_cardiac_reasons=needs.get("rehab_cardiac_reasons", []),
        rehab_common_reasons=needs.get("rehab_common_reasons", []),
        treatment_education_reasons=needs.get("treatment_education_reasons", []),
        wellness_reasons=needs.get("wellness_reasons", []),
        input_data=needs.get("input_data"),
        clinical_severity_id=needs.get("clinical_severity_id"),
        other_clinical_needs_id=needs.get("other_clinical_needs_id"),
        calculation_version=needs.get("calculation_version", "1.0.0"),
        created_at=needs["created_at"]
    )


@router.get("/student/{student_id}/history")
async def get_student_allied_history_endpoint(
    student_id: str,
    limit: int = Query(default=10, le=50, ge=1)
) -> List[AlliedHistoryItem]:
    """
    Get allied health assessment history for a student.

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

    history = get_student_allied_health_history(student_id, limit)

    result = []
    for item in history:
        extraction_data = item.get("extractions", {}) or {}
        result.append(AlliedHistoryItem(
            id=item["id"],
            extraction_id=item["extraction_id"],
            priority_level=item.get("priority_level", "NONE"),
            is_mental_health=item.get("is_mental_health", False),
            is_nutritional_health=item.get("is_nutritional_health", False),
            is_physiotherapy=item.get("is_physiotherapy", False),
            is_homecare=item.get("is_homecare", False),
            is_sleep_therapy=item.get("is_sleep_therapy", False),
            is_rehab_cardiac=item.get("is_rehab_cardiac", False),
            is_rehab_common=item.get("is_rehab_common", False),
            is_treatment_education=item.get("is_treatment_education", False),
            is_wellness=item.get("is_wellness", False),
            created_at=item["created_at"],
            extraction_created_at=extraction_data.get("created_at")
        ))

    return result


@router.get("/student/{student_id}/latest", response_model=Optional[AlliedHealthResponse])
async def get_student_latest_allied(student_id: str):
    """
    Get the most recent allied health assessment for a student.

    Args:
        student_id: UUID of the student

    Returns:
        Latest AlliedHealthResponse or null if none found
    """
    try:
        uuid.UUID(student_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    needs = get_student_latest_allied_health(student_id)

    if not needs:
        return None

    return AlliedHealthResponse(
        id=needs["id"],
        extraction_id=needs["extraction_id"],
        student_id=needs.get("student_id"),
        counsellor_id=needs.get("counsellor_id"),
        priority_level=needs.get("priority_level", "NONE"),
        is_mental_health=needs.get("is_mental_health", False),
        is_nutritional_health=needs.get("is_nutritional_health", False),
        is_physiotherapy=needs.get("is_physiotherapy", False),
        is_homecare=needs.get("is_homecare", False),
        is_sleep_therapy=needs.get("is_sleep_therapy", False),
        is_rehab_cardiac=needs.get("is_rehab_cardiac", False),
        is_rehab_common=needs.get("is_rehab_common", False),
        is_treatment_education=needs.get("is_treatment_education", False),
        is_wellness=needs.get("is_wellness", False),
        mental_health_reasons=needs.get("mental_health_reasons", []),
        nutritional_health_reasons=needs.get("nutritional_health_reasons", []),
        physiotherapy_reasons=needs.get("physiotherapy_reasons", []),
        homecare_reasons=needs.get("homecare_reasons", []),
        sleep_therapy_reasons=needs.get("sleep_therapy_reasons", []),
        rehab_cardiac_reasons=needs.get("rehab_cardiac_reasons", []),
        rehab_common_reasons=needs.get("rehab_common_reasons", []),
        treatment_education_reasons=needs.get("treatment_education_reasons", []),
        wellness_reasons=needs.get("wellness_reasons", []),
        input_data=needs.get("input_data"),
        clinical_severity_id=needs.get("clinical_severity_id"),
        other_clinical_needs_id=needs.get("other_clinical_needs_id"),
        calculation_version=needs.get("calculation_version", "1.0.0"),
        created_at=needs["created_at"]
    )


@router.get("/statistics", response_model=AlliedStatistics)
async def get_allied_statistics_endpoint(
    counsellor_id: Optional[str] = None,
    days: int = Query(default=30, le=365, ge=1)
):
    """
    Get aggregate allied health statistics.

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

    stats = get_allied_health_statistics(counsellor_id, days)

    return AlliedStatistics(
        mental_health=stats.get("mental_health", 0),
        nutritional_health=stats.get("nutritional_health", 0),
        physiotherapy=stats.get("physiotherapy", 0),
        homecare=stats.get("homecare", 0),
        sleep_therapy=stats.get("sleep_therapy", 0),
        rehab_cardiac=stats.get("rehab_cardiac", 0),
        rehab_common=stats.get("rehab_common", 0),
        treatment_education=stats.get("treatment_education", 0),
        wellness=stats.get("wellness", 0),
        total=stats.get("total", 0),
        period_days=stats.get("period_days", days)
    )

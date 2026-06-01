"""
Dashboard API Router

Provides endpoints for the school management dashboard:
- GET /intervention-summary - Main dashboard metrics by period
- GET /intervention-categories - Category breakdown with risk scores
- GET /students - Student list by category
- GET /outcome-metrics - Outcome tracking and ROI
- GET /time-to-action - Response time analytics
- POST /interventions/{id}/status - Update intervention status

Author: Unizy Health
Version: 1.0.0
"""

import logging
import uuid
from datetime import date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from models.auth_models import ClientContext
from dependencies.auth import get_current_client

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["dashboard"]
)


def resolve_school_id(client: ClientContext, query_school_id: Optional[str]) -> Optional[uuid.UUID]:
    """School admin's school_id takes precedence over query param."""
    if client.school_id is not None:
        return client.school_id  # School admin: force their school
    return uuid.UUID(query_school_id) if query_school_id else None


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class PeriodStatsResponse(BaseModel):
    """Statistics for a time period."""
    total_students: int
    patients_with_interventions: int
    percentage: float
    revenue_potential: float


class CategoryStatsResponse(BaseModel):
    """Statistics for a category."""
    category: str
    label: str
    icon: str
    color: str
    student_count: int
    intervention_count: int
    revenue_potential: float
    aggregate_risk_score: float
    risk_band: str
    intervention_types: List[str]
    card_type: str = "intervention"  # "score" or "intervention"
    avg_compliance_score: Optional[float] = None
    avg_dropoff_probability: Optional[float] = None


class BreakdownStatsResponse(BaseModel):
    """Statistics for a breakdown row (counsellor or department)."""
    id: str
    name: str
    specialization: Optional[str] = None
    by_category: Dict[str, int]
    total_at_risk: int


class StudentMetricRowResponse(BaseModel):
    """Per-student clinical metric row."""
    student_id: str
    patient_name: str
    mrn: Optional[str] = None
    compliance_likelihood: Optional[str] = None
    dropoff_probability: Optional[float] = None
    is_surgery_candidate: bool = False
    health_service_count: int = 0
    health_service_level: str = "Low"
    has_followup_due: bool = False
    followup_count: int = 0


class InterventionSummaryResponse(BaseModel):
    """Response for intervention summary endpoint."""
    total_students: int
    patients_with_interventions: int
    percentage: float
    revenue_potential: float
    by_period: Dict[str, PeriodStatsResponse]
    by_category: List[CategoryStatsResponse]
    high_risk_categories: List[str]
    by_department: List[BreakdownStatsResponse]
    by_doctor: List[BreakdownStatsResponse]
    by_patient: List[StudentMetricRowResponse] = []
    filters_applied: Dict[str, Any]


class StudentInterventionResponse(BaseModel):
    """Individual intervention in student list."""
    id: str
    code: Optional[str] = None
    category: Optional[str] = None  # Raw DB category, mapped to 5 dashboard categories at display layer
    priority: Optional[str] = None
    priority_score: int = 0
    take_up_likelihood: Optional[int] = None
    revenue_estimate: Optional[float] = None
    trigger_reason: Optional[str] = None
    action: Optional[str] = None
    status: str = "PENDING"  # PENDING, CONTACTED, ACCEPTED, COMPLETED, etc.
    days_since_generated: int = 0


class StudentResponse(BaseModel):
    """Student with interventions."""
    student_id: str
    patient_name: str
    mrn: Optional[str]
    counsellor_name: Optional[str]
    last_consultation: Optional[str]
    interventions: List[StudentInterventionResponse]
    total_revenue_potential: float


class StudentsListResponse(BaseModel):
    """Response for students list endpoint."""
    students: List[StudentResponse]
    total_count: int
    page: int
    page_size: int
    has_more: bool


class OutcomeMetricsResponse(BaseModel):
    """Response for outcome metrics endpoint."""
    total_interventions: int
    by_status: Dict[str, int]
    conversion_rate: float
    completion_rate: float
    actual_revenue: float
    potential_revenue: float
    revenue_capture_rate: float


class TimeToActionResponse(BaseModel):
    """Response for time-to-action endpoint."""
    avg_time_to_contact_hours: float
    avg_time_to_completion_days: float
    by_priority: Dict[str, Dict[str, float]]
    by_category: Dict[str, Dict[str, float]]


class UpdateStatusRequest(BaseModel):
    """Request for updating intervention status."""
    status: str = Field(..., description="New status: CONTACTED, ACCEPTED, DECLINED, COMPLETED, EXPIRED")
    notes: Optional[str] = Field(None, description="Optional notes about the status change")
    actual_revenue: Optional[float] = Field(None, description="Actual revenue if status is COMPLETED")
    updated_by_user_id: Optional[str] = Field(None, description="User making the update")
    updated_by_user_type: str = Field("coordinator", description="Type: coordinator, assistant, admin")


class UpdateStatusResponse(BaseModel):
    """Response for status update."""
    success: bool
    intervention_id: str
    new_status: str
    message: str


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.get("/intervention-summary", response_model=InterventionSummaryResponse)
async def get_intervention_summary(
    period: str = Query("mtd", description="Period: today, week, mtd, ytd, custom"),
    start_date: Optional[date] = Query(None, description="Start date for custom period"),
    end_date: Optional[date] = Query(None, description="End date for custom period"),
    school_id: Optional[str] = Query(None, description="Filter by school ID"),
    department_id: Optional[str] = Query(None, description="Filter by department ID"),
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    priority_threshold: str = Query("MEDIUM", description="Minimum priority: CRITICAL, HIGH, MEDIUM, LOW"),
    client: ClientContext = Depends(get_current_client),
):
    """
    Get intervention summary for the main dashboard.

    **Periods:**
    - `today`: Current day
    - `week`: Current week (Monday to today)
    - `mtd`: Month to date
    - `ytd`: Year to date
    - `custom`: Custom date range (requires start_date and end_date)

    **Response includes:**
    - Summary totals for the selected period
    - Period breakdown (today, week, MTD, YTD)
    - Category breakdown with aggregate risk scores
    - High-risk category alerts
    - Per-student clinical metrics (by_patient)

    **6 Dashboard Categories:**
    - TREATMENT_COMPLIANCE: Treatment adherence (score-based)
    - DROP_OFF_RISK: Student retention risk (score-based)
    - FOLLOWUP_DUE: Actionable follow-up needs (intervention-based)
    - HEALTH_SERVICES: Rx refill + diagnostics + allied health (intervention-based)
    - SURGERY_CANDIDATE: OPD to IPD conversion (intervention-based)
    - QUALITY_RISK: Clinical safety alerts (intervention-based)
    """
    try:
        from services.dashboard_service import get_intervention_summary as get_summary

        # Parse UUIDs - school admin's school_id takes precedence
        h_id = resolve_school_id(client, school_id)
        d_id = uuid.UUID(department_id) if department_id else None
        doc_id = uuid.UUID(counsellor_id) if counsellor_id else None

        summary = get_summary(
            school_id=h_id,
            department_id=d_id,
            counsellor_id=doc_id,
            period=period,
            start_date=start_date,
            end_date=end_date,
            priority_threshold=priority_threshold,
        )

        return InterventionSummaryResponse(
            total_students=summary.total_students,
            patients_with_interventions=summary.patients_with_interventions,
            percentage=summary.percentage,
            revenue_potential=summary.revenue_potential,
            by_period={
                k: PeriodStatsResponse(
                    total_students=v.total_students,
                    patients_with_interventions=v.patients_with_interventions,
                    percentage=v.percentage,
                    revenue_potential=v.revenue_potential,
                )
                for k, v in summary.by_period.items()
            },
            by_category=[
                CategoryStatsResponse(
                    category=c.category,
                    label=c.label,
                    icon=c.icon,
                    color=c.color,
                    student_count=c.student_count,
                    intervention_count=c.intervention_count,
                    revenue_potential=c.revenue_potential,
                    aggregate_risk_score=c.aggregate_risk_score,
                    risk_band=c.risk_band,
                    intervention_types=c.intervention_types,
                    card_type=c.card_type,
                    avg_compliance_score=c.avg_compliance_score,
                    avg_dropoff_probability=c.avg_dropoff_probability,
                )
                for c in summary.by_category
            ],
            high_risk_categories=summary.high_risk_categories,
            by_department=[
                BreakdownStatsResponse(
                    id=d.id,
                    name=d.name,
                    specialization=d.specialization,
                    by_category=d.by_category,
                    total_at_risk=d.total_at_risk,
                )
                for d in summary.by_department
            ],
            by_doctor=[
                BreakdownStatsResponse(
                    id=d.id,
                    name=d.name,
                    specialization=d.specialization,
                    by_category=d.by_category,
                    total_at_risk=d.total_at_risk,
                )
                for d in summary.by_doctor
            ],
            by_patient=[
                StudentMetricRowResponse(
                    student_id=p.student_id,
                    patient_name=p.patient_name,
                    mrn=p.mrn,
                    compliance_likelihood=p.compliance_likelihood,
                    dropoff_probability=p.dropoff_probability,
                    is_surgery_candidate=p.is_surgery_candidate,
                    health_service_count=p.health_service_count,
                    health_service_level=p.health_service_level,
                    has_followup_due=getattr(p, 'has_followup_due', False),
                    followup_count=getattr(p, 'followup_count', 0),
                )
                for p in summary.by_patient
            ],
            filters_applied={
                "period": period,
                "start_date": str(start_date) if start_date else None,
                "end_date": str(end_date) if end_date else None,
                "school_id": school_id,
                "department_id": department_id,
                "counsellor_id": counsellor_id,
                "priority_threshold": priority_threshold,
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid parameter")
    except Exception as e:
        logger.error(f"[DASHBOARD API] Failed to get intervention summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get intervention summary")


@router.get("/students", response_model=StudentsListResponse)
async def get_students_by_category(
    category: Optional[str] = Query(None, description="Dashboard category: TREATMENT_COMPLIANCE, DROP_OFF_RISK, FOLLOWUP_DUE, HEALTH_SERVICES, SURGERY_CANDIDATE, QUALITY_RISK. Also accepts legacy DB categories. If not provided, returns all students."),
    school_id: Optional[str] = Query(None, description="Filter by school ID"),
    department_id: Optional[str] = Query(None, description="Filter by department ID"),
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    priority_threshold: str = Query("MEDIUM", description="Minimum priority"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("priority_score", description="Sort by: priority_score, revenue_potential, created_at"),
    period: str = Query("ytd", description="Period for filtering: today, week, mtd, ytd"),
    client: ClientContext = Depends(get_current_client),
):
    """
    Get student list for a specific category.

    **Use this endpoint to:**
    - Drill down into a specific category from the main dashboard
    - View students with their intervention details
    - Plan outreach based on priority and revenue potential

    **Returns:**
    - Student list with contact info
    - Interventions per student with priority and revenue
    - Days since intervention was generated
    """
    try:
        logger.info(f"[DASHBOARD API] get_students_by_category called with category={category}, school_id={school_id}, period={period}")
        from services.dashboard_service import get_students_by_category as get_students

        # Validate category if provided - accept both new dashboard categories and legacy DB categories
        valid_categories = [
            # 6 dashboard categories
            "TREATMENT_COMPLIANCE", "DROP_OFF_RISK", "FOLLOWUP_DUE", "HEALTH_SERVICES", "SURGERY_CANDIDATE", "QUALITY_RISK",
            # Legacy 7 DB categories (for backwards compatibility)
            "OP_TO_IP", "RX_REFILL", "DIAGNOSTICS_DUE", "ALLIED_HEALTH", "RETENTION_RISK",
        ]
        if category and category not in valid_categories:
            raise HTTPException(status_code=400, detail="Invalid category")

        # Parse UUIDs - school admin's school_id takes precedence
        h_id = resolve_school_id(client, school_id)
        d_id = uuid.UUID(department_id) if department_id else None
        doc_id = uuid.UUID(counsellor_id) if counsellor_id else None
        logger.info(f"[DASHBOARD API] UUIDs parsed successfully: h_id={h_id}")

        result = get_students(
            category=category,  # Can be None for "All Categories"
            school_id=h_id,
            department_id=d_id,
            counsellor_id=doc_id,
            priority_threshold=priority_threshold,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            period=period,
        )
        logger.info(f"[DASHBOARD API] Service returned {len(result.get('students', []))} students")

        # Build response with defensive access
        students_list = []
        for p in result.get("students", []):
            student_id = p.get("student_id")
            if not student_id:
                logger.warning(f"[DASHBOARD API] Skipping student with no student_id: {p}")
                continue

            interventions_list = []
            for i in p.get("interventions", []):
                if not i.get("id"):
                    continue
                interventions_list.append(StudentInterventionResponse(
                    id=str(i.get("id", "")),
                    code=i.get("code"),
                    category=i.get("category"),  # Raw DB category, mapped to 5 dashboard categories at display layer
                    priority=i.get("priority"),
                    priority_score=i.get("priority_score") or 0,
                    take_up_likelihood=i.get("take_up_likelihood"),
                    revenue_estimate=i.get("revenue_estimate"),
                    trigger_reason=i.get("trigger_reason"),
                    action=i.get("action"),
                    status=i.get("status", "PENDING"),  # Intervention status
                    days_since_generated=i.get("days_since_generated", 0),
                ))

            students_list.append(StudentResponse(
                student_id=str(student_id),
                patient_name=p.get("patient_name") or "Unknown",
                mrn=p.get("mrn"),
                counsellor_name=p.get("counsellor_name"),
                last_consultation=p.get("last_consultation"),
                interventions=interventions_list,
                total_revenue_potential=p.get("total_revenue_potential", 0),
            ))

        logger.info(f"[DASHBOARD API] Built {len(students_list)} student responses, returning...")
        response = StudentsListResponse(
            students=students_list,
            total_count=result.get("total_count", 0),
            page=result.get("page", page),
            page_size=result.get("page_size", page_size),
            has_more=result.get("has_more", False),
        )
        logger.info(f"[DASHBOARD API] Response built successfully")
        return response

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"[DASHBOARD API] ValueError in get_students: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid parameter")
    except Exception as e:
        logger.error(f"[DASHBOARD API] Failed to get students: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get students")


@router.get("/outcome-metrics", response_model=OutcomeMetricsResponse)
async def get_outcome_metrics(
    school_id: Optional[str] = Query(None, description="Filter by school ID"),
    department_id: Optional[str] = Query(None, description="Filter by department ID"),
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    period: str = Query("mtd", description="Period: today, week, mtd, ytd"),
    client: ClientContext = Depends(get_current_client),
):
    """
    Get outcome tracking metrics for ROI measurement.

    **Metrics include:**
    - Status distribution (PENDING, CONTACTED, ACCEPTED, DECLINED, COMPLETED, EXPIRED)
    - Conversion rate: (ACCEPTED + COMPLETED) / total
    - Completion rate: COMPLETED / total
    - Revenue capture rate: actual_revenue / potential_revenue

    **Use this endpoint to:**
    - Track intervention effectiveness
    - Measure ROI of intervention program
    - Identify bottlenecks in conversion funnel
    """
    try:
        from services.dashboard_service import get_outcome_metrics as get_metrics

        # Parse UUIDs - school admin's school_id takes precedence
        h_id = resolve_school_id(client, school_id)
        d_id = uuid.UUID(department_id) if department_id else None
        doc_id = uuid.UUID(counsellor_id) if counsellor_id else None

        result = get_metrics(
            school_id=h_id,
            department_id=d_id,
            counsellor_id=doc_id,
            period=period,
        )

        return OutcomeMetricsResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid parameter")
    except Exception as e:
        logger.error(f"[DASHBOARD API] Failed to get outcome metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get outcome metrics")


@router.get("/time-to-action", response_model=TimeToActionResponse)
async def get_time_to_action_metrics(
    school_id: Optional[str] = Query(None, description="Filter by school ID"),
    period: str = Query("mtd", description="Period: today, week, mtd, ytd"),
    client: ClientContext = Depends(get_current_client),
):
    """
    Get time-to-action analytics for performance tracking.

    **Metrics include:**
    - Average time to first contact (hours)
    - Average time to completion (days)
    - Breakdown by priority level (CRITICAL, HIGH, MEDIUM, LOW)
    - Breakdown by category

    **Use this endpoint to:**
    - Monitor staff response times
    - Identify priority gaps (e.g., CRITICAL taking too long)
    - Set performance benchmarks
    """
    try:
        from services.dashboard_service import get_time_to_action_metrics as get_metrics

        # Parse UUIDs - school admin's school_id takes precedence
        h_id = resolve_school_id(client, school_id)

        result = get_metrics(
            school_id=h_id,
            period=period,
        )

        return TimeToActionResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid parameter")
    except Exception as e:
        logger.error(f"[DASHBOARD API] Failed to get time-to-action metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get time-to-action metrics")


@router.post("/interventions/{intervention_id}/status", response_model=UpdateStatusResponse)
async def update_intervention_status(
    intervention_id: str,
    request: UpdateStatusRequest,
    client: ClientContext = Depends(get_current_client),
):
    """
    Update the status of an intervention.

    **Status progression:**
    - PENDING → CONTACTED (when staff reaches out)
    - CONTACTED → ACCEPTED (student agrees) or DECLINED (student refuses)
    - ACCEPTED → COMPLETED (action taken, revenue captured)
    - Any → EXPIRED (time limit passed)

    **Use this endpoint to:**
    - Track student outreach progress
    - Record student responses
    - Capture actual revenue for ROI calculation

    **Note:** Setting status to CONTACTED automatically records first_contact_at timestamp.
    Setting status to COMPLETED with actual_revenue records the revenue capture.
    """
    try:
        from services.dashboard_service import update_intervention_status as update_status

        # Validate status
        valid_statuses = ["CONTACTED", "ACCEPTED", "DECLINED", "COMPLETED", "EXPIRED"]
        if request.status not in valid_statuses:
            raise HTTPException(status_code=400, detail="Invalid status")

        # Parse UUIDs
        int_id = uuid.UUID(intervention_id)
        user_id = uuid.UUID(request.updated_by_user_id) if request.updated_by_user_id else None

        result = update_status(
            intervention_id=int_id,
            status=request.status,
            notes=request.notes,
            actual_revenue=request.actual_revenue,
            updated_by_user_id=user_id,
            updated_by_user_type=request.updated_by_user_type,
        )

        return UpdateStatusResponse(
            success=True,
            intervention_id=intervention_id,
            new_status=request.status,
            message=f"Intervention status updated to {request.status}",
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid intervention ID")
    except Exception as e:
        logger.error(f"[DASHBOARD API] Failed to update intervention status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update intervention status")


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    from datetime import datetime
    return {
        "status": "healthy",
        "service": "dashboard",
        "timestamp": datetime.utcnow().isoformat(),
    }

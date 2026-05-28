"""
Dashboard Service

Provides aggregation logic for the hospital management dashboard:
- Intervention summary by period (today/week/MTD/YTD)
- Category breakdown with aggregate risk scores
- Patient list with intervention details
- Outcome tracking and ROI metrics
- Time-to-action analytics

6 Dashboard Categories (remapped from 7 DB categories):
- TREATMENT_COMPLIANCE: Treatment adherence (score-only from patient_dropoff_risk) - score-based
- DROP_OFF_RISK: Patient retention risk (from RETENTION_RISK) - score-based
- FOLLOWUP_DUE: Actionable follow-up needs (from FOLLOWUP_DUE) - intervention-based
- HEALTH_SERVICES: Health service needs (from RX_REFILL + DIAGNOSTICS_DUE + ALLIED_HEALTH) - intervention-based
- SURGERY_CANDIDATE: Surgical conversion (from OP_TO_IP) - intervention-based
- QUALITY_RISK: Clinical safety alerts (unchanged) - intervention-based

Author: Unizy Health
Version: 2.0.0
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
import uuid

from services.supabase_service import supabase

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

# 6 dashboard categories (remapped from 7 DB categories)
DASHBOARD_CATEGORIES = [
    "TREATMENT_COMPLIANCE",
    "DROP_OFF_RISK",
    "FOLLOWUP_DUE",
    "HEALTH_SERVICES",
    "SURGERY_CANDIDATE",
    "QUALITY_RISK",
]

# Revenue-generating categories (for revenue potential calculation)
REVENUE_CATEGORIES = ["HEALTH_SERVICES", "SURGERY_CANDIDATE"]

# Mapping from dashboard categories to underlying DB intervention_category values
DASHBOARD_TO_DB_CATEGORIES = {
    "TREATMENT_COMPLIANCE": [],  # Score-only: derived from patient_dropoff_risk, no DB interventions
    "DROP_OFF_RISK": ["RETENTION_RISK"],
    "FOLLOWUP_DUE": ["FOLLOWUP_DUE"],
    "HEALTH_SERVICES": ["RX_REFILL", "DIAGNOSTICS_DUE", "ALLIED_HEALTH"],
    "SURGERY_CANDIDATE": ["OP_TO_IP"],
    "QUALITY_RISK": ["QUALITY_RISK"],
}

# Category display configuration
CATEGORY_CONFIG = {
    "TREATMENT_COMPLIANCE": {"label": "Treatment Compliance", "icon": "📋", "color": "blue", "card_type": "score"},
    "DROP_OFF_RISK": {"label": "Drop-off Risk", "icon": "⚠️", "color": "amber", "card_type": "score"},
    "FOLLOWUP_DUE": {"label": "Follow-up Due", "icon": "📅", "color": "cyan", "card_type": "intervention"},
    "HEALTH_SERVICES": {"label": "Health Services", "icon": "💊", "color": "teal", "card_type": "intervention"},
    "SURGERY_CANDIDATE": {"label": "Surgery Candidate", "icon": "🏥", "color": "purple", "card_type": "intervention"},
    "QUALITY_RISK": {"label": "Quality & Safety", "icon": "🚨", "color": "red", "card_type": "intervention"},
}

# Risk score bands
RISK_BANDS = {
    "HIGH_RISK": {"min": 60, "max": 100, "label": "High Risk", "description": "Priority outreach needed"},
    "MEDIUM_RISK": {"min": 40, "max": 59, "label": "Medium Risk", "description": "Standard follow-up"},
    "LOW_RISK": {"min": 0, "max": 39, "label": "Low Risk", "description": "Likely to convert"},
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PeriodStats:
    """Statistics for a time period."""
    total_patients: int = 0
    patients_with_interventions: int = 0
    percentage: float = 0.0
    revenue_potential: float = 0.0


@dataclass
class CategoryStats:
    """Statistics for a category."""
    category: str
    label: str
    icon: str
    color: str
    patient_count: int = 0
    intervention_count: int = 0
    revenue_potential: float = 0.0
    aggregate_risk_score: float = 0.0
    risk_band: str = "MEDIUM_RISK"
    intervention_types: List[str] = field(default_factory=list)
    card_type: str = "intervention"  # "score" or "intervention"
    avg_compliance_score: Optional[float] = None
    avg_dropoff_probability: Optional[float] = None


@dataclass
class BreakdownStats:
    """Statistics for a breakdown row (doctor or department)."""
    id: str  # doctor_id or specialization name
    name: str  # doctor name or specialization
    specialization: Optional[str] = None  # Only for doctor breakdown
    by_category: Dict[str, int] = field(default_factory=dict)  # category -> patient_count
    total_at_risk: int = 0


@dataclass
class PatientMetricRow:
    """Per-patient clinical metric row."""
    patient_id: str
    patient_name: str
    mrn: Optional[str] = None
    compliance_likelihood: Optional[str] = None
    dropoff_probability: Optional[float] = None
    is_surgery_candidate: bool = False
    health_service_count: int = 0
    health_service_level: str = "Low"
    has_followup_due: bool = False
    followup_count: int = 0


@dataclass
class DashboardSummary:
    """Main dashboard summary."""
    total_patients: int = 0
    patients_with_interventions: int = 0
    percentage: float = 0.0
    revenue_potential: float = 0.0
    by_period: Dict[str, PeriodStats] = field(default_factory=dict)
    by_category: List[CategoryStats] = field(default_factory=list)
    high_risk_categories: List[str] = field(default_factory=list)
    by_department: List[BreakdownStats] = field(default_factory=list)
    by_doctor: List[BreakdownStats] = field(default_factory=list)
    by_patient: List[PatientMetricRow] = field(default_factory=list)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_date_range(period: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> Tuple[date, date]:
    """
    Get date range for a period.

    Args:
        period: "today", "week", "mtd", "ytd", or "custom"
        start_date: Start date for custom period
        end_date: End date for custom period

    Returns:
        Tuple of (start_date, end_date)
    """
    today = date.today()

    if period == "today":
        return today, today
    elif period == "week":
        # Start of current week (Monday)
        start = today - timedelta(days=today.weekday())
        return start, today
    elif period == "mtd":
        # Start of current month
        start = today.replace(day=1)
        return start, today
    elif period == "ytd":
        # Last 30 days (UI labels this as "Last 30 Days")
        start = today - timedelta(days=30)
        return start, today
    elif period == "custom" and start_date and end_date:
        return start_date, end_date
    else:
        # Default to MTD
        start = today.replace(day=1)
        return start, today


def calculate_risk_band(risk_score: float) -> str:
    """Calculate risk band from risk score."""
    if risk_score >= RISK_BANDS["HIGH_RISK"]["min"]:
        return "HIGH_RISK"
    elif risk_score >= RISK_BANDS["MEDIUM_RISK"]["min"]:
        return "MEDIUM_RISK"
    else:
        return "LOW_RISK"


def calculate_aggregate_risk_score(interventions: List[Dict[str, Any]]) -> float:
    """
    Calculate aggregate risk score from interventions.

    Formula: Risk Score = 100 - Weighted Average Take-Up
    Where: Weighted_Avg_Take_Up = Σ(take_up_likelihood × priority_score) / Σ(priority_score)

    Args:
        interventions: List of intervention dicts with take_up_likelihood and priority_score

    Returns:
        Aggregate risk score (0-100)
    """
    if not interventions:
        return 50.0  # Default to medium risk

    total_weighted_takeup = 0.0
    total_weight = 0.0

    for i in interventions:
        take_up = i.get("take_up_likelihood", 50)  # Default 50 if not set
        priority = i.get("priority_score", 50)

        total_weighted_takeup += take_up * priority
        total_weight += priority

    if total_weight == 0:
        return 50.0

    weighted_avg_takeup = total_weighted_takeup / total_weight
    risk_score = 100 - weighted_avg_takeup

    return round(risk_score, 1)


# =============================================================================
# MAIN DASHBOARD FUNCTIONS
# =============================================================================

def get_intervention_summary(
    hospital_id: Optional[uuid.UUID] = None,
    department_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    period: str = "mtd",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    priority_threshold: str = "MEDIUM",
) -> DashboardSummary:
    """
    Get intervention summary for the main dashboard.

    OPTIMIZED: Uses single SQL RPC function for all aggregation.

    Args:
        hospital_id: Filter by hospital
        department_id: Filter by department
        doctor_id: Filter by doctor
        period: "today", "week", "mtd", "ytd", or "custom"
        start_date: Start date for custom period
        end_date: End date for custom period
        priority_threshold: Minimum priority to include ("CRITICAL", "HIGH", "MEDIUM", "LOW")

    Returns:
        DashboardSummary with period and category breakdowns
    """
    summary = DashboardSummary()

    try:
        # Priority score thresholds
        priority_scores = {
            "CRITICAL": 90,
            "HIGH": 70,
            "MEDIUM": 50,
            "LOW": 0,
        }
        min_priority_score = priority_scores.get(priority_threshold.upper(), 50)

        # Get date ranges for all periods
        periods = {
            "today": get_date_range("today"),
            "week": get_date_range("week"),
            "mtd": get_date_range("mtd"),
            "ytd": get_date_range("ytd"),
        }

        # Get the main period range
        main_start, main_end = get_date_range(period, start_date, end_date)

        # Call the optimized RPC v2 function for main period
        rpc_result = supabase.rpc("get_dashboard_summary_v2", {
            "p_hospital_id": str(hospital_id) if hospital_id else None,
            "p_doctor_id": str(doctor_id) if doctor_id else None,
            "p_start_date": main_start.isoformat(),
            "p_end_date": main_end.isoformat(),
            "p_min_priority_score": min_priority_score,
        }).execute()

        if not rpc_result.data:
            logger.warning("[DASHBOARD] RPC returned no data")
            return summary

        rpc_data = rpc_result.data

        # Map RPC result to summary
        summary.total_patients = rpc_data.get("total_patients", 0)
        summary.patients_with_interventions = rpc_data.get("patients_with_interventions", 0)
        summary.revenue_potential = float(rpc_data.get("revenue_potential", 0))

        # Calculate percentage
        if summary.total_patients > 0:
            summary.percentage = round(
                summary.patients_with_interventions / summary.total_patients * 100, 1
            )

        # Map category breakdown
        by_category_raw = rpc_data.get("by_category", []) or []
        for cat_data in by_category_raw:
            cat_name = cat_data.get("category", "")
            config = CATEGORY_CONFIG.get(cat_name, {})

            cat_stats = CategoryStats(
                category=cat_name,
                label=config.get("label", cat_name),
                icon=config.get("icon", "📌"),
                color=config.get("color", "gray"),
                patient_count=cat_data.get("patient_count", 0),
                intervention_count=cat_data.get("intervention_count", 0),
                revenue_potential=float(cat_data.get("revenue_potential", 0)),
                aggregate_risk_score=float(cat_data.get("aggregate_risk_score", 50)),
                risk_band=cat_data.get("risk_band", "MEDIUM") + "_RISK",
                intervention_types=[],  # Not returned by RPC for efficiency
                card_type=config.get("card_type", "intervention"),
                avg_compliance_score=float(cat_data["avg_compliance_score"]) if cat_data.get("avg_compliance_score") is not None else None,
                avg_dropoff_probability=float(cat_data["avg_dropoff_probability"]) if cat_data.get("avg_dropoff_probability") is not None else None,
            )
            summary.by_category.append(cat_stats)

            # Track high-risk categories
            if cat_stats.risk_band == "HIGH_RISK":
                summary.high_risk_categories.append(cat_name)

        # Ensure all 6 categories are present (even if empty)
        existing_cats = {c.category for c in summary.by_category}
        for cat in DASHBOARD_CATEGORIES:
            if cat not in existing_cats:
                config = CATEGORY_CONFIG.get(cat, {})
                summary.by_category.append(CategoryStats(
                    category=cat,
                    label=config.get("label", cat),
                    icon=config.get("icon", "📌"),
                    color=config.get("color", "gray"),
                    card_type=config.get("card_type", "intervention"),
                ))

        # Sort categories by patient_count descending, but keep original order for ties
        summary.by_category.sort(
            key=lambda x: (-x.patient_count, DASHBOARD_CATEGORIES.index(x.category) if x.category in DASHBOARD_CATEGORIES else 999)
        )

        # Map department breakdown
        by_dept_raw = rpc_data.get("by_department", []) or []
        for dept_data in by_dept_raw:
            summary.by_department.append(BreakdownStats(
                id=dept_data.get("id", ""),
                name=dept_data.get("name", ""),
                by_category=dept_data.get("by_category", {}),
                total_at_risk=dept_data.get("total_at_risk", 0),
            ))

        # Map doctor breakdown
        by_doctor_raw = rpc_data.get("by_doctor", []) or []
        for doc_data in by_doctor_raw:
            summary.by_doctor.append(BreakdownStats(
                id=doc_data.get("id", ""),
                name=doc_data.get("name", ""),
                specialization=doc_data.get("specialization"),
                by_category=doc_data.get("by_category", {}),
                total_at_risk=doc_data.get("total_at_risk", 0),
            ))

        # Map by_patient breakdown
        by_patient_raw = rpc_data.get("by_patient", []) or []
        for pat_data in by_patient_raw:
            summary.by_patient.append(PatientMetricRow(
                patient_id=str(pat_data.get("patient_id", "")),
                patient_name=pat_data.get("patient_name", "Unknown"),
                mrn=pat_data.get("mrn"),
                compliance_likelihood=pat_data.get("compliance_likelihood"),
                dropoff_probability=float(pat_data["dropoff_probability"]) if pat_data.get("dropoff_probability") is not None else None,
                is_surgery_candidate=pat_data.get("is_surgery_candidate", False),
                health_service_count=pat_data.get("health_service_count", 0),
                health_service_level=pat_data.get("health_service_level", "Low"),
                has_followup_due=pat_data.get("has_followup_due", False),
                followup_count=pat_data.get("followup_count", 0),
            ))

        # Calculate period breakdowns (separate RPC calls for efficiency)
        # Only fetch if period is not one of the standard ones being requested
        for period_name, (p_start, p_end) in periods.items():
            if period_name == period:
                # Use main result for the requested period
                summary.by_period[period_name] = PeriodStats(
                    total_patients=summary.total_patients,
                    patients_with_interventions=summary.patients_with_interventions,
                    percentage=summary.percentage,
                    revenue_potential=summary.revenue_potential,
                )
            else:
                # Quick RPC call for other periods (just totals, not full breakdown)
                period_result = supabase.rpc("get_dashboard_summary_v2", {
                    "p_hospital_id": str(hospital_id) if hospital_id else None,
                    "p_doctor_id": str(doctor_id) if doctor_id else None,
                    "p_start_date": p_start.isoformat(),
                    "p_end_date": p_end.isoformat(),
                    "p_min_priority_score": min_priority_score,
                }).execute()

                if period_result.data:
                    p_data = period_result.data
                    total = p_data.get("total_patients", 0)
                    with_int = p_data.get("patients_with_interventions", 0)
                    summary.by_period[period_name] = PeriodStats(
                        total_patients=total,
                        patients_with_interventions=with_int,
                        percentage=round(with_int / total * 100, 1) if total > 0 else 0,
                        revenue_potential=float(p_data.get("revenue_potential", 0)),
                    )
                else:
                    summary.by_period[period_name] = PeriodStats()

        logger.info(f"[DASHBOARD] Summary (RPC): {summary.patients_with_interventions} patients with interventions, "
                   f"{len(summary.by_doctor)} doctors, {len(summary.by_department)} departments")
        return summary

    except Exception as e:
        logger.error(f"[DASHBOARD] Failed to get intervention summary: {e}", exc_info=True)
        return summary


def get_patients_by_category(
    category: Optional[str] = None,
    hospital_id: Optional[uuid.UUID] = None,
    department_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    priority_threshold: str = "MEDIUM",
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "priority_score",
    period: str = "ytd",
) -> Dict[str, Any]:
    """
    Get patient list, optionally filtered by category.

    Args:
        category: Dashboard category to filter by (None = all categories)
        hospital_id: Filter by hospital
        department_id: Filter by department
        doctor_id: Filter by doctor
        priority_threshold: Minimum priority
        page: Page number (1-indexed)
        page_size: Items per page
        sort_by: "priority_score", "revenue_potential", "created_at"
        period: Time period filter: "today", "week", "mtd", "ytd"

    Returns:
        Dict with patients list, total_count, pagination info
    """
    try:
        offset = (page - 1) * page_size

        # Get date range for period filter
        start_date, end_date = get_date_range(period)

        # Priority score thresholds
        priority_scores = {
            "CRITICAL": 90,
            "HIGH": 70,
            "MEDIUM": 50,
            "LOW": 0,
        }
        min_priority_score = priority_scores.get(priority_threshold.upper(), 50)

        # If hospital_id filter, first get doctor_ids for that hospital
        # (medical_extractions doesn't have hospital_id - must filter via doctors table)
        hospital_doctor_ids = None
        if hospital_id:
            doctors_result = supabase.table("doctors").select("id").eq("hospital_id", str(hospital_id)).execute()
            hospital_doctor_ids = [d["id"] for d in (doctors_result.data or [])]
            if not hospital_doctor_ids:
                logger.info(f"[DASHBOARD] No doctors found for hospital {hospital_id}")
                return {
                    "patients": [],
                    "total_count": 0,
                    "page": page,
                    "page_size": page_size,
                    "has_more": False,
                }

        # Build query - removed hospital_id from medical_extractions select
        # Note: patients table uses patient_id (not mrn) as the identifier
        query = supabase.table("patient_interventions").select(
            "id, extraction_id, intervention_code, intervention_category, "
            "priority_level, priority_score, take_up_likelihood, revenue_estimate, "
            "trigger_reason, action, created_at, "
            "medical_extractions!inner(patient_id, doctor_id, created_at, "
            "doctors(full_name), patients(full_name, patient_id))"
        )

        # Map dashboard category to DB categories if needed
        db_categories = None
        if category:
            if category in DASHBOARD_TO_DB_CATEGORIES:
                db_categories = DASHBOARD_TO_DB_CATEGORIES[category]
            else:
                # Legacy DB category passed directly
                db_categories = [category]

        # TREATMENT_COMPLIANCE has no DB interventions - query patient_dropoff_risk instead
        if category == "TREATMENT_COMPLIANCE":
            return _get_treatment_compliance_patients(
                hospital_id=hospital_id,
                doctor_id=doctor_id,
                hospital_doctor_ids=hospital_doctor_ids,
                period=period,
                page=page,
                page_size=page_size,
            )

        # Apply filters - category is optional (None = all categories)
        if db_categories:
            if len(db_categories) == 1:
                query = query.eq("intervention_category", db_categories[0])
            else:
                query = query.in_("intervention_category", db_categories)
        else:
            # For "All Categories", exclude NULL categories
            query = query.not_.is_("intervention_category", "null")
        query = query.gte("priority_score", min_priority_score)

        # Apply period filter
        query = query.gte("created_at", start_date.isoformat())
        query = query.lte("created_at", (end_date + timedelta(days=1)).isoformat())

        # Filter by doctor_id(s) instead of hospital_id
        if doctor_id:
            query = query.eq("medical_extractions.doctor_id", str(doctor_id))
        elif hospital_doctor_ids:
            query = query.in_("medical_extractions.doctor_id", hospital_doctor_ids)

        # Apply sorting
        if sort_by == "revenue_potential":
            query = query.order("revenue_estimate", desc=True)
        elif sort_by == "created_at":
            query = query.order("created_at", desc=True)
        else:
            query = query.order("priority_score", desc=True)

        # Get total count - need to join medical_extractions for doctor filter
        count_query = supabase.table("patient_interventions").select(
            "id, medical_extractions!inner(doctor_id)", count="exact"
        )
        if db_categories:
            if len(db_categories) == 1:
                count_query = count_query.eq("intervention_category", db_categories[0])
            else:
                count_query = count_query.in_("intervention_category", db_categories)
        else:
            count_query = count_query.not_.is_("intervention_category", "null")
        count_query = count_query.gte("priority_score", min_priority_score)
        count_query = count_query.gte("created_at", start_date.isoformat())
        count_query = count_query.lte("created_at", (end_date + timedelta(days=1)).isoformat())
        if doctor_id:
            count_query = count_query.eq("medical_extractions.doctor_id", str(doctor_id))
        elif hospital_doctor_ids:
            count_query = count_query.in_("medical_extractions.doctor_id", hospital_doctor_ids)
        count_result = count_query.execute()
        total_count = count_result.count or 0

        # Apply pagination
        query = query.range(offset, offset + page_size - 1)
        result = query.execute()
        interventions = result.data or []

        # Group by patient
        patients_map: Dict[str, Dict[str, Any]] = {}
        for i in interventions:
            ext = i.get("medical_extractions", {})
            patient_id = ext.get("patient_id")

            if not patient_id:
                continue

            if patient_id not in patients_map:
                patient_info = ext.get("patients", {}) or {}
                doctor_info = ext.get("doctors", {}) or {}

                patients_map[patient_id] = {
                    "patient_id": patient_id,
                    "patient_name": patient_info.get("full_name", "Unknown"),
                    "mrn": patient_info.get("patient_id"),  # patients table uses patient_id as MRN
                    "doctor_name": doctor_info.get("full_name"),
                    "last_consultation": ext.get("created_at"),
                    "interventions": [],
                    "total_revenue_potential": 0,
                }

            intervention_id = i.get("id")
            if not intervention_id:
                continue  # Skip interventions without valid ID

            # Calculate days since generated safely
            days_since = 0
            if i.get("created_at"):
                try:
                    created_date = datetime.fromisoformat(
                        i["created_at"].replace("Z", "+00:00")
                    ).date()
                    days_since = (date.today() - created_date).days
                except (ValueError, TypeError):
                    days_since = 0

            patients_map[patient_id]["interventions"].append({
                "id": str(intervention_id),
                "code": i.get("intervention_code"),
                "category": i.get("intervention_category"),  # The 7 dashboard categories
                "priority": i.get("priority_level"),
                "priority_score": i.get("priority_score") or 0,
                "take_up_likelihood": i.get("take_up_likelihood"),
                "revenue_estimate": i.get("revenue_estimate"),
                "trigger_reason": i.get("trigger_reason"),
                "action": i.get("action"),
                "status": i.get("status", "PENDING"),  # Intervention status
                "days_since_generated": days_since,
            })
            patients_map[patient_id]["total_revenue_potential"] += float(i.get("revenue_estimate") or 0)

        patients = list(patients_map.values())

        return {
            "patients": patients,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "has_more": (offset + page_size) < total_count,
        }

    except Exception as e:
        logger.error(f"[DASHBOARD] Failed to get patients by category: {e}", exc_info=True)
        return {
            "patients": [],
            "total_count": 0,
            "page": page,
            "page_size": page_size,
            "has_more": False,
        }


def _build_compliance_trigger_reason(r: Dict[str, Any]) -> str:
    """Build trigger reason from compliance_risk_reasons or fallback to reasons array."""
    compliance_reasons = r.get("compliance_risk_reasons") or []
    if not compliance_reasons:
        all_reasons = r.get("reasons") or []
        compliance_reasons = [
            reason.replace("[Compliance] ", "")
            for reason in all_reasons
            if isinstance(reason, str) and reason.startswith("[Compliance]")
        ]
    if compliance_reasons:
        return "; ".join(compliance_reasons)
    return f"Compliance likelihood: {r.get('compliance_likelihood')}"


def _get_treatment_compliance_patients(
    hospital_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    hospital_doctor_ids: Optional[List[str]] = None,
    period: str = "ytd",
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """
    Get patients for TREATMENT_COMPLIANCE category.
    Queries patient_dropoff_risk directly (score-based, no DB interventions).
    Returns patients with low/very_low compliance likelihood.
    """
    try:
        offset = (page - 1) * page_size
        start_date, end_date = get_date_range(period)

        # Query patient_dropoff_risk for low compliance patients
        query = supabase.table("patient_dropoff_risk").select(
            "id, patient_id, compliance_likelihood, dropoff_probability, "
            "compliance_risk_reasons, reasons, created_at, "
            "medical_extractions!inner(doctor_id, doctors(full_name), patients(full_name, patient_id))",
            count="exact"
        ).in_("compliance_likelihood", ["Very Low", "Low"])
        query = query.gte("created_at", start_date.isoformat())
        query = query.lte("created_at", (end_date + timedelta(days=1)).isoformat())

        if doctor_id:
            query = query.eq("medical_extractions.doctor_id", str(doctor_id))
        elif hospital_doctor_ids:
            query = query.in_("medical_extractions.doctor_id", hospital_doctor_ids)

        query = query.order("created_at", desc=True)
        query = query.range(offset, offset + page_size - 1)
        result = query.execute()
        rows = result.data or []
        total_count = result.count or 0

        # Group by patient
        patients_map: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            ext = r.get("medical_extractions", {})
            patient_id = r.get("patient_id")
            if not patient_id or patient_id in patients_map:
                continue

            patient_info = ext.get("patients", {}) or {}
            doctor_info = ext.get("doctors", {}) or {}

            patients_map[patient_id] = {
                "patient_id": patient_id,
                "patient_name": patient_info.get("full_name", "Unknown"),
                "mrn": patient_info.get("patient_id"),
                "doctor_name": doctor_info.get("full_name"),
                "last_consultation": ext.get("created_at") or r.get("created_at"),
                "interventions": [{
                    "id": str(r.get("id", "")),
                    "code": "LOW_COMPLIANCE",
                    "category": "TREATMENT_COMPLIANCE",
                    "priority": "HIGH" if r.get("compliance_likelihood") == "Very Low" else "MEDIUM",
                    "priority_score": 80 if r.get("compliance_likelihood") == "Very Low" else 60,
                    "take_up_likelihood": 10 if r.get("compliance_likelihood") == "Very Low" else 35,
                    "revenue_estimate": None,
                    "trigger_reason": _build_compliance_trigger_reason(r),
                    "action": "Follow up on treatment adherence",
                    "status": "PENDING",
                    "days_since_generated": 0,
                }],
                "total_revenue_potential": 0,
            }

        return {
            "patients": list(patients_map.values()),
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "has_more": (offset + page_size) < total_count,
        }
    except Exception as e:
        logger.error(f"[DASHBOARD] Failed to get treatment compliance patients: {e}", exc_info=True)
        return {
            "patients": [],
            "total_count": 0,
            "page": page,
            "page_size": page_size,
            "has_more": False,
        }


def get_outcome_metrics(
    hospital_id: Optional[uuid.UUID] = None,
    department_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    period: str = "mtd",
) -> Dict[str, Any]:
    """
    Get outcome tracking metrics.

    Returns:
        Dict with status counts, conversion rates, revenue capture
    """
    try:
        start_date, end_date = get_date_range(period)

        # If hospital_id filter, first get doctor_ids for that hospital
        # (medical_extractions doesn't have hospital_id - must filter via doctors table)
        hospital_doctor_ids = None
        if hospital_id:
            doctors_result = supabase.table("doctors").select("id").eq("hospital_id", str(hospital_id)).execute()
            hospital_doctor_ids = [d["id"] for d in (doctors_result.data or [])]
            if not hospital_doctor_ids:
                logger.info(f"[DASHBOARD] No doctors found for hospital {hospital_id}")
                return {
                    "total_interventions": 0,
                    "by_status": {},
                    "conversion_rate": 0,
                    "completion_rate": 0,
                    "actual_revenue": 0,
                    "potential_revenue": 0,
                    "revenue_capture_rate": 0,
                }

        # Query intervention outcomes - removed hospital_id from select
        query = supabase.table("intervention_outcomes").select(
            "id, status, actual_revenue, generated_at, first_contact_at, completed_at, "
            "patient_interventions!inner(intervention_category, revenue_estimate, "
            "medical_extractions!inner(doctor_id))"
        )

        query = query.gte("generated_at", start_date.isoformat())
        query = query.lte("generated_at", (end_date + timedelta(days=1)).isoformat())

        # Filter by doctor_id(s) instead of hospital_id
        if doctor_id:
            query = query.eq("patient_interventions.medical_extractions.doctor_id", str(doctor_id))
        elif hospital_doctor_ids:
            query = query.in_("patient_interventions.medical_extractions.doctor_id", hospital_doctor_ids)

        result = query.execute()
        outcomes = result.data or []

        # Calculate metrics
        total = len(outcomes)
        by_status = {
            "PENDING": 0,
            "CONTACTED": 0,
            "ACCEPTED": 0,
            "DECLINED": 0,
            "COMPLETED": 0,
            "EXPIRED": 0,
        }

        actual_revenue = 0.0
        potential_revenue = 0.0

        for o in outcomes:
            status = o.get("status", "PENDING")
            by_status[status] = by_status.get(status, 0) + 1

            # Revenue tracking
            pi = o.get("patient_interventions", {})
            potential_revenue += float(pi.get("revenue_estimate") or 0)

            if status == "COMPLETED":
                actual_revenue += float(o.get("actual_revenue") or 0)

        # Calculate rates
        conversion_rate = ((by_status["ACCEPTED"] + by_status["COMPLETED"]) / total * 100) if total > 0 else 0
        completion_rate = (by_status["COMPLETED"] / total * 100) if total > 0 else 0
        revenue_capture_rate = (actual_revenue / potential_revenue * 100) if potential_revenue > 0 else 0

        return {
            "total_interventions": total,
            "by_status": by_status,
            "conversion_rate": round(conversion_rate, 1),
            "completion_rate": round(completion_rate, 1),
            "actual_revenue": actual_revenue,
            "potential_revenue": potential_revenue,
            "revenue_capture_rate": round(revenue_capture_rate, 1),
        }

    except Exception as e:
        logger.error(f"[DASHBOARD] Failed to get outcome metrics: {e}", exc_info=True)
        return {
            "total_interventions": 0,
            "by_status": {},
            "conversion_rate": 0,
            "completion_rate": 0,
            "actual_revenue": 0,
            "potential_revenue": 0,
            "revenue_capture_rate": 0,
        }


def get_time_to_action_metrics(
    hospital_id: Optional[uuid.UUID] = None,
    period: str = "mtd",
) -> Dict[str, Any]:
    """
    Get time-to-action analytics.

    Returns:
        Dict with average contact/completion times by priority and category
    """
    try:
        start_date, end_date = get_date_range(period)

        # Query outcomes with contact/completion times
        query = supabase.table("intervention_outcomes").select(
            "generated_at, first_contact_at, completed_at, status, "
            "patient_interventions!inner(priority_level, intervention_category)"
        )

        query = query.gte("generated_at", start_date.isoformat())
        query = query.not_.is_("first_contact_at", "null")  # Only those with contact

        result = query.execute()
        outcomes = result.data or []

        # Calculate metrics
        contact_times: List[float] = []
        completion_times: List[float] = []
        by_priority: Dict[str, Dict[str, List[float]]] = {}
        by_category: Dict[str, Dict[str, List[float]]] = {}

        for o in outcomes:
            generated = datetime.fromisoformat(o["generated_at"].replace("Z", "+00:00"))

            # Time to contact
            if o.get("first_contact_at"):
                contacted = datetime.fromisoformat(o["first_contact_at"].replace("Z", "+00:00"))
                contact_hours = (contacted - generated).total_seconds() / 3600
                contact_times.append(contact_hours)

                # Group by priority
                pi = o.get("patient_interventions", {})
                priority = pi.get("priority_level", "MEDIUM")
                if priority not in by_priority:
                    by_priority[priority] = {"contact": [], "completion": []}
                by_priority[priority]["contact"].append(contact_hours)

                # Group by category
                category = pi.get("intervention_category", "RETENTION_RISK")
                if category not in by_category:
                    by_category[category] = {"contact": [], "completion": []}
                by_category[category]["contact"].append(contact_hours)

            # Time to completion
            if o.get("completed_at"):
                completed = datetime.fromisoformat(o["completed_at"].replace("Z", "+00:00"))
                completion_days = (completed - generated).total_seconds() / (3600 * 24)
                completion_times.append(completion_days)

                pi = o.get("patient_interventions", {})
                priority = pi.get("priority_level", "MEDIUM")
                if priority in by_priority:
                    by_priority[priority]["completion"].append(completion_days)

                category = pi.get("intervention_category", "RETENTION_RISK")
                if category in by_category:
                    by_category[category]["completion"].append(completion_days)

        # Calculate averages
        avg_contact = sum(contact_times) / len(contact_times) if contact_times else 0
        avg_completion = sum(completion_times) / len(completion_times) if completion_times else 0

        priority_stats = {}
        for p, times in by_priority.items():
            priority_stats[p] = {
                "avg_contact_hours": round(sum(times["contact"]) / len(times["contact"]), 1) if times["contact"] else 0,
                "avg_completion_days": round(sum(times["completion"]) / len(times["completion"]), 1) if times["completion"] else 0,
            }

        category_stats = {}
        for c, times in by_category.items():
            category_stats[c] = {
                "avg_contact_hours": round(sum(times["contact"]) / len(times["contact"]), 1) if times["contact"] else 0,
                "avg_completion_days": round(sum(times["completion"]) / len(times["completion"]), 1) if times["completion"] else 0,
            }

        return {
            "avg_time_to_contact_hours": round(avg_contact, 1),
            "avg_time_to_completion_days": round(avg_completion, 1),
            "by_priority": priority_stats,
            "by_category": category_stats,
        }

    except Exception as e:
        logger.error(f"[DASHBOARD] Failed to get time-to-action metrics: {e}", exc_info=True)
        return {
            "avg_time_to_contact_hours": 0,
            "avg_time_to_completion_days": 0,
            "by_priority": {},
            "by_category": {},
        }


def update_intervention_status(
    intervention_id: uuid.UUID,
    status: str,
    notes: Optional[str] = None,
    actual_revenue: Optional[float] = None,
    updated_by_user_id: Optional[uuid.UUID] = None,
    updated_by_user_type: str = "coordinator",
) -> Dict[str, Any]:
    """
    Update intervention outcome status.

    Args:
        intervention_id: The intervention to update
        status: New status (CONTACTED, ACCEPTED, DECLINED, COMPLETED, EXPIRED)
        notes: Optional notes
        actual_revenue: Revenue if completed
        updated_by_user_id: User making the update
        updated_by_user_type: Type of user

    Returns:
        Updated outcome record
    """
    try:
        update_data: Dict[str, Any] = {
            "status": status,
            "status_updated_at": datetime.utcnow().isoformat(),
        }

        if notes:
            update_data["notes"] = notes
        if updated_by_user_id:
            update_data["updated_by_user_id"] = str(updated_by_user_id)
            update_data["updated_by_user_type"] = updated_by_user_type

        # Set timestamp based on status
        if status == "CONTACTED":
            update_data["first_contact_at"] = datetime.utcnow().isoformat()
        elif status == "COMPLETED":
            update_data["completed_at"] = datetime.utcnow().isoformat()
            if actual_revenue is not None:
                update_data["actual_revenue"] = actual_revenue
        elif status == "EXPIRED":
            update_data["expired_at"] = datetime.utcnow().isoformat()

        # Update the outcome record
        result = supabase.table("intervention_outcomes")\
            .update(update_data)\
            .eq("intervention_id", str(intervention_id))\
            .execute()

        if not result.data:
            # Create if doesn't exist
            # First get the intervention to get generated_at
            int_result = supabase.table("patient_interventions")\
                .select("created_at")\
                .eq("id", str(intervention_id))\
                .single()\
                .execute()

            if int_result.data:
                update_data["intervention_id"] = str(intervention_id)
                update_data["generated_at"] = int_result.data["created_at"]
                result = supabase.table("intervention_outcomes")\
                    .insert(update_data)\
                    .execute()

        logger.info(f"[DASHBOARD] Updated intervention {intervention_id} status to {status}")
        return result.data[0] if result.data else {}

    except Exception as e:
        logger.error(f"[DASHBOARD] Failed to update intervention status: {e}", exc_info=True)
        raise


# =============================================================================
# MODULE INFO
# =============================================================================

__version__ = "2.0.0"
__author__ = "Unizy Health"
__all__ = [
    "DASHBOARD_CATEGORIES",
    "DASHBOARD_TO_DB_CATEGORIES",
    "CATEGORY_CONFIG",
    "get_intervention_summary",
    "get_patients_by_category",
    "get_outcome_metrics",
    "get_time_to_action_metrics",
    "update_intervention_status",
]

"""
Quality Metrics API Router

Provides endpoints for school-scoped quality metrics:
- AI acceptance rate (% notes used unchanged)
- Notes per counsellor per day
- Pipeline timing (E2E with percentile breakdown)
- Service uptime (hardcoded)
- Accuracy metrics (WER, entity error rates)
- Combined summary dashboard
"""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from models.auth_models import ClientContext
from dependencies.auth import get_current_client
from services.supabase_service import supabase, retry_on_network_error

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/metrics",
    tags=["quality-metrics"]
)


def resolve_school_id(client: ClientContext, query_school_id: Optional[str]) -> Optional[uuid.UUID]:
    """School admin's school_id takes precedence over query param."""
    if client.school_id is not None:
        return client.school_id
    return uuid.UUID(query_school_id) if query_school_id else None


# =============================================================================
# PHASE 1 ENDPOINTS
# =============================================================================

@router.get("/ai-acceptance")
async def get_ai_acceptance(
    school_id: Optional[str] = Query(None),
    counsellor_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    group_by: str = Query("total", description="total, daily, counsellor, counsellor_daily"),
    client: ClientContext = Depends(get_current_client),
):
    """
    Get AI note acceptance rate metrics.

    Returns percentage of AI-generated notes used unchanged vs edited,
    with flexible grouping by total, daily, counsellor, or counsellor+daily.
    """
    try:
        h_id = resolve_school_id(client, school_id)

        result = retry_on_network_error(
            lambda: supabase.rpc(
                "get_ai_acceptance_metrics",
                {
                    "p_school_id": str(h_id) if h_id else None,
                    "p_counsellor_id": counsellor_id,
                    "p_date_from": date_from.isoformat() if date_from else None,
                    "p_date_to": date_to.isoformat() if date_to else None,
                    "p_group_by": group_by,
                }
            ).execute()
        )

        return {"success": True, "data": result.data, "group_by": group_by}

    except Exception as e:
        logger.error(f"[METRICS] Failed to get AI acceptance metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get AI acceptance metrics")


@router.get("/notes-per-day")
async def get_notes_per_day(
    school_id: Optional[str] = Query(None),
    counsellor_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    client: ClientContext = Depends(get_current_client),
):
    """Get notes per counsellor per day."""
    try:
        h_id = resolve_school_id(client, school_id)

        result = retry_on_network_error(
            lambda: supabase.rpc(
                "get_notes_per_counsellor_per_day",
                {
                    "p_school_id": str(h_id) if h_id else None,
                    "p_counsellor_id": counsellor_id,
                    "p_date_from": date_from.isoformat() if date_from else None,
                    "p_date_to": date_to.isoformat() if date_to else None,
                }
            ).execute()
        )

        return {"success": True, "data": result.data}

    except Exception as e:
        logger.error(f"[METRICS] Failed to get notes per day: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get notes per day")


@router.get("/pipeline-timing")
async def get_pipeline_timing(
    school_id: Optional[str] = Query(None),
    counsellor_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    client: ClientContext = Depends(get_current_client),
):
    """
    Get average pipeline timing with percentile breakdown.

    Returns avg, p50, p95, p99 for stitching, transcription, extraction, and total.
    """
    try:
        h_id = resolve_school_id(client, school_id)

        result = retry_on_network_error(
            lambda: supabase.rpc(
                "get_avg_pipeline_timing",
                {
                    "p_school_id": str(h_id) if h_id else None,
                    "p_counsellor_id": counsellor_id,
                    "p_date_from": date_from.isoformat() if date_from else None,
                    "p_date_to": date_to.isoformat() if date_to else None,
                }
            ).execute()
        )

        return {"success": True, "data": result.data}

    except Exception as e:
        logger.error(f"[METRICS] Failed to get pipeline timing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get pipeline timing")


@router.get("/uptime")
async def get_uptime(
    client: ClientContext = Depends(get_current_client),
):
    """Get service uptime (hardcoded)."""
    return {
        "success": True,
        "data": {
            "uptime_pct": 99.98,
            "target": 99.9,
            "status": "healthy",
        }
    }


@router.get("/summary")
async def get_metrics_summary(
    school_id: Optional[str] = Query(None),
    counsellor_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None, description="Defaults to 30 days ago"),
    date_to: Optional[date] = Query(None, description="Defaults to today"),
    client: ClientContext = Depends(get_current_client),
):
    """
    Get combined dashboard summary with all metrics in a single call.

    Returns acceptance rate, notes today, avg E2E time, uptime,
    and accuracy metrics (if available).
    """
    try:
        h_id = resolve_school_id(client, school_id)

        # Default date range: last 30 days
        if not date_from:
            date_from = (datetime.now(timezone.utc) - timedelta(days=30)).date()
        if not date_to:
            date_to = datetime.now(timezone.utc).date()

        rpc_params = {
            "p_school_id": str(h_id) if h_id else None,
            "p_counsellor_id": counsellor_id,
            "p_date_from": date_from.isoformat(),
            "p_date_to": date_to.isoformat(),
        }

        # Fetch all metrics
        acceptance_result = retry_on_network_error(
            lambda: supabase.rpc("get_ai_acceptance_metrics", {**rpc_params, "p_group_by": "total"}).execute()
        )

        timing_result = retry_on_network_error(
            lambda: supabase.rpc("get_avg_pipeline_timing", rpc_params).execute()
        )

        # Notes today
        today_params = {**rpc_params, "p_date_from": datetime.now(timezone.utc).date().isoformat(), "p_date_to": datetime.now(timezone.utc).date().isoformat()}
        notes_today_result = retry_on_network_error(
            lambda: supabase.rpc("get_notes_per_counsellor_per_day", today_params).execute()
        )

        # Accuracy (Phase 3 - may return empty if no data yet)
        accuracy_data = None
        try:
            accuracy_result = retry_on_network_error(
                lambda: supabase.rpc("get_accuracy_metrics", {**rpc_params, "p_group_by": "total"}).execute()
            )
            accuracy_data = accuracy_result.data
        except Exception:
            pass

        # Compute notes today total
        notes_today_total = 0
        if notes_today_result.data and isinstance(notes_today_result.data, list):
            for entry in notes_today_result.data:
                notes_today_total += entry.get("note_count", 0)

        return {
            "success": True,
            "data": {
                "acceptance": acceptance_result.data,
                "pipeline_timing": timing_result.data,
                "notes_today": notes_today_total,
                "uptime": {"uptime_pct": 99.98, "target": 99.9, "status": "healthy"},
                "accuracy": accuracy_data,
                "date_range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            }
        }

    except Exception as e:
        logger.error(f"[METRICS] Failed to get metrics summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get metrics summary")


# =============================================================================
# PHASE 3 ENDPOINTS
# =============================================================================

@router.get("/accuracy")
async def get_accuracy(
    school_id: Optional[str] = Query(None),
    counsellor_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    group_by: str = Query("total", description="total, counsellor, weekly, monthly"),
    client: ClientContext = Depends(get_current_client),
):
    """Get aggregated WER and entity error rates."""
    try:
        h_id = resolve_school_id(client, school_id)

        result = retry_on_network_error(
            lambda: supabase.rpc(
                "get_accuracy_metrics",
                {
                    "p_school_id": str(h_id) if h_id else None,
                    "p_counsellor_id": counsellor_id,
                    "p_date_from": date_from.isoformat() if date_from else None,
                    "p_date_to": date_to.isoformat() if date_to else None,
                    "p_group_by": group_by,
                }
            ).execute()
        )

        return {"success": True, "data": result.data, "group_by": group_by}

    except Exception as e:
        logger.error(f"[METRICS] Failed to get accuracy metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get accuracy metrics")


@router.get("/accuracy/{extraction_id}")
async def get_accuracy_for_extraction(
    extraction_id: str,
    client: ClientContext = Depends(get_current_client),
):
    """Get per-segment accuracy breakdown for a specific extraction."""
    try:
        extraction_uuid = uuid.UUID(extraction_id)

        result = retry_on_network_error(
            lambda: supabase.table("extraction_accuracy_metrics")
            .select("*")
            .eq("extraction_id", str(extraction_uuid))
            .execute()
        )

        if not result.data:
            return {"success": True, "data": None, "message": "No accuracy metrics computed yet"}

        return {"success": True, "data": result.data[0]}

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction ID")
    except Exception as e:
        logger.error(f"[METRICS] Failed to get extraction accuracy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get extraction accuracy")


@router.get("/accuracy/trends")
async def get_accuracy_trends(
    school_id: Optional[str] = Query(None),
    counsellor_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    interval: str = Query("weekly", description="weekly or monthly"),
    client: ClientContext = Depends(get_current_client),
):
    """Get time-series accuracy trends."""
    try:
        h_id = resolve_school_id(client, school_id)
        group_by = "weekly" if interval == "weekly" else "monthly"

        result = retry_on_network_error(
            lambda: supabase.rpc(
                "get_accuracy_metrics",
                {
                    "p_school_id": str(h_id) if h_id else None,
                    "p_counsellor_id": counsellor_id,
                    "p_date_from": date_from.isoformat() if date_from else None,
                    "p_date_to": date_to.isoformat() if date_to else None,
                    "p_group_by": group_by,
                }
            ).execute()
        )

        return {"success": True, "data": result.data, "interval": interval}

    except Exception as e:
        logger.error(f"[METRICS] Failed to get accuracy trends: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get accuracy trends")

"""
POC Metrics Router

Admin-only endpoints for the "POC Metrics" screen:
  GET  /api/v1/poc-metrics/tracker    per-consultation rows
  GET  /api/v1/poc-metrics/aggregate  day-by-day rollup
  GET  /api/v1/poc-metrics/timings    Doctor_All + Attendant_Nurse timing tables
  GET  /api/v1/poc-metrics/export     single .xlsx with 4 sheets

All endpoints accept:
  - school_id (required)
  - counsellor_id   (optional)
  - assistant_id    (optional)
  - start_date  (YYYY-MM-DD, IST day)
  - end_date    (YYYY-MM-DD, IST day, inclusive)
"""

import logging
from datetime import date
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from dependencies.auth import require_admin
from models.auth_models import ClientContext
from services.poc_metrics_service import (
    get_tracker_rows,
    get_aggregate_rows,
    get_timings_tables,
    build_xlsx,
    get_metric_detail,
    METRIC_CODES,
    TRACKER_COLS,
    TIMINGS_COLS,
    AGGREGATE_METRICS,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/poc-metrics",
    tags=["poc-metrics"],
)


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field} (expected YYYY-MM-DD): {value}")


def _validate_range(start: date, end: date):
    if end < start:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    span = (end - start).days + 1
    if span > 90:
        raise HTTPException(status_code=400, detail="Date range capped at 90 days")


@router.get("/tracker")
async def tracker(
    school_id: str = Query(..., description="School UUID"),
    start_date: str = Query(..., description="Start date (IST) YYYY-MM-DD"),
    end_date: str = Query(..., description="End date (IST) YYYY-MM-DD"),
    counsellor_id: Optional[str] = Query(None),
    assistant_id: Optional[str] = Query(None),
    client: ClientContext = Depends(require_admin),
):
    """Per-consultation tracker rows (Tracker sheet)."""
    s = _parse_date(start_date, "start_date")
    e = _parse_date(end_date, "end_date")
    _validate_range(s, e)
    try:
        rows = get_tracker_rows(school_id, counsellor_id, assistant_id, s, e)
    except Exception as ex:
        logger.exception("[POC_METRICS] tracker failed")
        raise HTTPException(status_code=500, detail=f"tracker query failed: {ex}")
    return {"columns": TRACKER_COLS, "rows": rows, "count": len(rows)}


@router.get("/aggregate")
async def aggregate(
    school_id: str = Query(...),
    start_date: str = Query(...),
    end_date: str = Query(...),
    counsellor_id: Optional[str] = Query(None),
    assistant_id: Optional[str] = Query(None),
    client: ClientContext = Depends(require_admin),
):
    """Per-day rollup (Aggregate sheet)."""
    s = _parse_date(start_date, "start_date")
    e = _parse_date(end_date, "end_date")
    _validate_range(s, e)
    try:
        dates, rows = get_aggregate_rows(school_id, counsellor_id, assistant_id, s, e)
    except Exception as ex:
        logger.exception("[POC_METRICS] aggregate failed")
        raise HTTPException(status_code=500, detail=f"aggregate query failed: {ex}")
    return {
        "dates": [d.isoformat() for d in dates],
        "metrics": [{"category": c, "metric": m} for (c, m) in AGGREGATE_METRICS],
        "rows": rows,
    }


@router.get("/timings")
async def timings(
    school_id: str = Query(...),
    start_date: str = Query(...),
    end_date: str = Query(...),
    counsellor_id: Optional[str] = Query(None),
    assistant_id: Optional[str] = Query(None),
    client: ClientContext = Depends(require_admin),
):
    """Timing tables (Doctor_All + Attendant_Nurse sheets)."""
    s = _parse_date(start_date, "start_date")
    e = _parse_date(end_date, "end_date")
    _validate_range(s, e)
    try:
        tt = get_timings_tables(school_id, counsellor_id, assistant_id, s, e)
    except Exception as ex:
        logger.exception("[POC_METRICS] timings failed")
        raise HTTPException(status_code=500, detail=f"timings query failed: {ex}")
    return {"columns": TIMINGS_COLS, **tt}


@router.get("/detail")
async def detail(
    school_id: str = Query(...),
    start_date: str = Query(...),
    end_date: str = Query(...),
    metric: str = Query(..., description=f"One of: {sorted(METRIC_CODES)}"),
    counsellor_id: Optional[str] = Query(None),
    assistant_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None, description="Scope to a single session (Tracker click)"),
    client: ClientContext = Depends(require_admin),
):
    """Drill-down rows for a clicked Tracker or Aggregate cell."""
    if metric not in METRIC_CODES:
        raise HTTPException(status_code=400, detail=f"Unknown metric: {metric}")
    s = _parse_date(start_date, "start_date")
    e = _parse_date(end_date, "end_date")
    _validate_range(s, e)
    try:
        rows = get_metric_detail(school_id, counsellor_id, assistant_id, s, e, metric, session_id)
    except Exception as ex:
        logger.exception("[POC_METRICS] detail failed")
        raise HTTPException(status_code=500, detail=f"detail query failed: {ex}")
    return {"metric": metric, "session_id": session_id, "rows": rows, "count": len(rows)}


@router.get("/export")
async def export(
    school_id: str = Query(...),
    start_date: str = Query(...),
    end_date: str = Query(...),
    counsellor_id: Optional[str] = Query(None),
    assistant_id: Optional[str] = Query(None),
    client: ClientContext = Depends(require_admin),
):
    """Single .xlsx with 4 sheets: Tracker, Aggregate, Doctor_All, Attendant_Nurse."""
    s = _parse_date(start_date, "start_date")
    e = _parse_date(end_date, "end_date")
    _validate_range(s, e)
    try:
        blob = build_xlsx(school_id, counsellor_id, assistant_id, s, e)
    except Exception as ex:
        logger.exception("[POC_METRICS] export failed")
        raise HTTPException(status_code=500, detail=f"export failed: {ex}")
    filename = f"poc_metrics_{start_date}_to_{end_date}.xlsx"
    return StreamingResponse(
        BytesIO(blob),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

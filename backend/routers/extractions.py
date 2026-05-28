"""
Extraction Management API Router

Handles operations on medical extractions:
- Get extraction data (original or edited)
- Update extraction with doctor edits
- Compare original vs edited versions
- Search extractions
- List extraction history with LLM usage data

Edit Tracking:
- original_extraction_json: AI-generated (never changes)
- edited_extraction_json: Latest doctor edits
- edit_count: Number of times edited
"""

import os
import uuid
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional, List, Union
from datetime import datetime

logger = logging.getLogger(__name__)

from models.auth_models import ClientContext
from dependencies.auth import require_admin
from services.audit_service import audit_service

# Conditional EHR auth imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import EHRExtractionAccessChecker, EHRSubmissionAccessChecker, get_current_client

    _extraction_checker = EHRExtractionAccessChecker()
    _submission_checker = EHRSubmissionAccessChecker()

    async def verify_extraction_access(request: Request, extraction_id: str = None):  # type: ignore[misc]
        """Verify EHR client has access to extraction data."""
        extraction_uuid = uuid.UUID(extraction_id) if extraction_id else None
        client = get_current_client(request)
        return await _extraction_checker(request, extraction_uuid, client)

    async def verify_submission_access(request: Request, submission_id: str = None):  # type: ignore[misc]
        """Verify EHR client has access to submission data."""
        submission_uuid = uuid.UUID(submission_id) if submission_id else None
        client = get_current_client(request)
        return await _submission_checker(request, submission_uuid, client)

    async def verify_session_for_extraction(request: Request, session_id: str = None):  # type: ignore[misc]
        """Verify EHR client has access to session data (for extraction lookup)."""
        session_uuid = uuid.UUID(session_id) if session_id else None
        client = get_current_client(request)
        return await _submission_checker(request, session_uuid, client)
else:
    async def verify_extraction_access(request: Request, extraction_id: str = None):  # type: ignore[misc]
        return None

    async def verify_submission_access(request: Request, submission_id: str = None):  # type: ignore[misc]
        return None

    async def verify_session_for_extraction(request: Request, session_id: str = None):  # type: ignore[misc]
        return None

from services.supabase_service import (
    supabase,
    get_extraction_data,
    get_current_extraction_segments,
    update_extraction_edits,
    compare_extraction_versions,
    get_extraction_by_session
)

_extraction_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="extraction")

router = APIRouter(
    prefix="/api/v1/extractions",
    tags=["extractions"]
)


# ============================================================================
# Request/Response Models
# ============================================================================

class UpdateExtractionRequest(BaseModel):
    """Request model for updating extraction with edits"""
    edited_data: Dict[str, Any]  # Complete edited extraction JSON
    edited_by: str  # Doctor or Nurse UUID who made edits
    edited_by_type: str = "doctor"  # Type of user: "doctor" or "nurse"


class ExtractionResponse(BaseModel):
    """Response model for extraction data"""
    extraction_id: str
    session_id: Optional[str]
    consultation_type_id: str
    doctor_id: Optional[str]
    patient_id: Optional[str]
    extraction_mode: str
    segment_count: int
    extraction_data: Dict[str, Any]  # Current data (edited if exists, otherwise original)
    is_edited: bool
    edit_count: int
    last_edited_at: Optional[str]
    last_edited_by: Optional[str]
    created_at: str
    updated_at: str
    role: Optional[str] = None
    segments: Optional[List[Dict[str, Any]]] = None


class ComparisonResponse(BaseModel):
    """Response model for original vs edited comparison"""
    extraction_id: str
    original: Dict[str, Any]
    edited: Optional[Dict[str, Any]]
    has_edits: bool
    edit_count: int
    last_edited_at: Optional[str]
    last_edited_by: Optional[str]


class LLMUsageItem(BaseModel):
    """LLM usage data for a single API call"""
    id: str
    call_type: str
    call_subtype: Optional[str]
    model: str
    prompt_token_count: Optional[int]
    cached_content_token_count: Optional[int]
    candidates_token_count: Optional[int]
    total_token_count: Optional[int]
    input_cost_usd: Optional[float]
    output_cost_usd: Optional[float]
    cache_savings_usd: Optional[float]
    total_cost_usd: Optional[float]
    api_duration_seconds: Optional[float]
    cache_hit: Optional[bool]
    cache_hit_ratio: Optional[float]
    response_status: Optional[str]
    created_at: str


class ExtractionHistoryItem(BaseModel):
    """Extraction history item with LLM usage summary"""
    extraction_id: str
    session_id: Optional[str]
    submission_id: Optional[str] = None
    consultation_type_id: str
    consultation_type_name: Optional[str]
    template_code: Optional[str]
    doctor_id: Optional[str]
    doctor_name: Optional[str]
    patient_id: Optional[str]
    extraction_mode: str
    segment_count: int
    is_edited: bool
    edit_count: int
    is_merged: bool = False  # True if this extraction was created by merging other extractions
    created_at: str
    # Retry indicator
    is_retry: bool = False  # True if this is a retry of a previous extraction
    retry_number: Optional[int] = None  # 1 for first retry, 2 for second, etc.
    # Recording duration
    recording_duration_seconds: Optional[float] = None
    # Processing times
    stitching_time_seconds: Optional[float]
    transcription_time_seconds: Optional[float]
    extraction_time_seconds: Optional[float]
    total_processing_time_seconds: Optional[float]
    # LLM usage summary
    total_llm_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_cached_tokens: int
    total_cost_usd: float
    total_cache_savings_usd: float
    # Detailed LLM usage (optional)
    llm_usage: Optional[List[LLMUsageItem]] = None


class ExtractionHistoryResponse(BaseModel):
    """Response for extraction history list"""
    extractions: List[ExtractionHistoryItem]
    total_count: int
    page: int
    page_size: int
    has_more: bool


# ============================================================================
# API Endpoints - Static routes MUST come before dynamic {extraction_id} routes
# ============================================================================

# Health check - static route
@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "extractions",
        "timestamp": datetime.utcnow().isoformat()
    }


# Session lookup - static prefix route
@router.get("/session/{session_id}", response_model=Optional[ExtractionResponse])
async def get_extraction_by_session_id(
    request: Request,
    session_id: str,
    _auth = Depends(verify_session_for_extraction)
):
    """
    Get extraction data by recording session ID.

    Returns the most recent extraction for the session.
    """
    try:
        session_uuid = uuid.UUID(session_id)
        loop = asyncio.get_event_loop()

        # Step 1: Look up extraction_id by session (lightweight query)
        response = await loop.run_in_executor(
            _extraction_executor,
            lambda: supabase.table("medical_extractions")
                .select("id")
                .eq("session_id", str(session_uuid))
                .order("created_at", desc=True)
                .limit(1)
                .execute()
        )

        if not response.data:
            return None

        extraction_uuid = uuid.UUID(response.data[0]["id"])

        # Step 2: Fetch extraction record + segments in parallel
        data, segments = await asyncio.gather(
            loop.run_in_executor(
                _extraction_executor, get_extraction_data, extraction_uuid, False
            ),
            loop.run_in_executor(
                _extraction_executor, get_current_extraction_segments, extraction_uuid
            ),
        )
        data["segments"] = segments

        # HIPAA Audit: log extraction read by session
        client_ctx = getattr(request.state, "client", None)
        if client_ctx:
            try:
                asyncio.create_task(audit_service.log_phi_access(
                    client_context=client_ctx, request=request, response_status=200,
                    response_time_ms=0, resource_type="extraction",
                    resource_id=str(extraction_uuid), action="read",
                ))
            except Exception:
                pass

        return data

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Extraction not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve extraction")


# ============================================================================
# Extraction History with LLM Usage - Static prefix routes
# ============================================================================

@router.get("/history", response_model=ExtractionHistoryResponse)
async def get_extraction_history(
    doctor_id: Optional[str] = Query(None, description="Filter by doctor ID"),
    consultation_type_id: Optional[str] = Query(None, description="Filter by consultation type"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    include_llm_details: bool = Query(False, description="Include detailed LLM usage per extraction"),
    client: ClientContext = Depends(require_admin)
):
    """
    Get extraction history with LLM usage summary.

    **Admin only** - Shows LLM usage and cost data.

    Returns a paginated list of extractions with:
    - Extraction metadata (consultation type, doctor, mode, etc.)
    - Processing times (stitching, transcription, extraction)
    - LLM usage summary (total tokens, costs, cache savings)
    - Optionally: detailed LLM usage per API call

    **Use cases:**
    - View recent extractions when user didn't click "view results"
    - Monitor LLM costs and token usage
    - Analyze cache effectiveness
    - Track processing performance
    """
    try:
        offset = (page - 1) * page_size

        # Build base query for extractions
        query = supabase.table("medical_extractions")\
            .select(
                "id, session_id, submission_id, consultation_type_id, doctor_id, patient_id, "
                "extraction_mode, model_used, segment_count, edit_count, created_at, "
                "stitching_time_seconds, transcription_time_seconds, "
                "extraction_time_seconds, total_processing_time_seconds, "
                "edited_extraction_json, is_merged"
            )\
            .order("created_at", desc=True)

        # Apply filters
        if doctor_id:
            query = query.eq("doctor_id", doctor_id)
        if consultation_type_id:
            query = query.eq("consultation_type_id", consultation_type_id)

        # Execute with pagination
        query = query.range(offset, offset + page_size - 1)
        result = query.execute()

        extractions_data = result.data or []

        # Get total count for pagination
        count_query = supabase.table("medical_extractions").select("id", count="exact")
        if doctor_id:
            count_query = count_query.eq("doctor_id", doctor_id)
        if consultation_type_id:
            count_query = count_query.eq("consultation_type_id", consultation_type_id)
        count_result = count_query.execute()
        total_count = count_result.count or 0

        # Get consultation types for names
        consultation_types = {}
        ct_result = supabase.table("consultation_types").select("id, type_name").execute()
        for ct in (ct_result.data or []):
            consultation_types[ct["id"]] = ct["type_name"]

        # Get doctors for names
        doctors = {}
        doc_result = supabase.table("doctors").select("id, full_name").execute()
        for doc in (doc_result.data or []):
            doctors[doc["id"]] = doc["full_name"]

        # Get templates for codes and recording durations
        templates = {}
        recording_durations = {}
        # Get session template codes and durations
        session_ids = [e["session_id"] for e in extractions_data if e.get("session_id")]
        if session_ids:
            sessions_result = supabase.table("recording_sessions")\
                .select("id, template_code, total_duration_seconds")\
                .in_("id", session_ids)\
                .execute()
            for sess in (sessions_result.data or []):
                templates[sess["id"]] = sess.get("template_code")
                recording_durations[sess["id"]] = sess.get("total_duration_seconds")

        # Get LLM usage for all extractions
        extraction_ids = [e["id"] for e in extractions_data]
        llm_usage_by_extraction_id = {}  # extraction_id -> [usage records]
        llm_usage_by_session_id = {}  # session_id -> [usage records with extraction_id=NULL]

        if extraction_ids:
            # Also get usage by session_id for extractions that might have usage logged by session
            session_ids_for_usage = [e["session_id"] for e in extractions_data if e.get("session_id")]

            llm_query = supabase.table("llm_usage_log")\
                .select("*")\
                .or_(
                    f"extraction_id.in.({','.join(extraction_ids)})" +
                    (f",session_id.in.({','.join(session_ids_for_usage)})" if session_ids_for_usage else "")
                )\
                .execute()

            # Separate usage records by extraction_id vs session_id-only
            for usage in (llm_query.data or []):
                ext_key = usage.get("extraction_id")
                sess_key = usage.get("session_id")

                if ext_key:
                    # Has extraction_id - attribute to that specific extraction
                    if ext_key not in llm_usage_by_extraction_id:
                        llm_usage_by_extraction_id[ext_key] = []
                    llm_usage_by_extraction_id[ext_key].append(usage)
                elif sess_key:
                    # No extraction_id (e.g., transcription) - group by session_id
                    # Will be allocated to extractions based on timestamp proximity
                    if sess_key not in llm_usage_by_session_id:
                        llm_usage_by_session_id[sess_key] = []
                    llm_usage_by_session_id[sess_key].append(usage)

        # ============================================================================
        # Detect retries: group extractions by session_id and identify order
        # ============================================================================
        session_extractions = {}  # session_id -> list of (extraction_id, created_at)
        for ext in extractions_data:
            sess_id = ext.get("session_id")
            if sess_id:
                if sess_id not in session_extractions:
                    session_extractions[sess_id] = []
                session_extractions[sess_id].append({
                    "extraction_id": ext["id"],
                    "created_at": ext["created_at"]
                })

        # Sort each session's extractions by created_at to determine retry order
        retry_info = {}  # extraction_id -> {"is_retry": bool, "retry_number": int or None}
        for sess_id, ext_list in session_extractions.items():
            sorted_exts = sorted(ext_list, key=lambda x: x["created_at"])
            for idx, ext_entry in enumerate(sorted_exts):
                ext_id = ext_entry["extraction_id"]
                if idx == 0:
                    # First extraction for this session (original)
                    retry_info[ext_id] = {"is_retry": False, "retry_number": None}
                else:
                    # Retry
                    retry_info[ext_id] = {"is_retry": True, "retry_number": idx}

        # Build response
        extractions = []
        for ext in extractions_data:
            ext_id = ext["id"]
            session_id = ext.get("session_id")
            ext_created_at = ext["created_at"]

            # Get retry info for this extraction
            ext_retry_info = retry_info.get(ext_id, {"is_retry": False, "retry_number": None})

            # Get LLM usage specific to this extraction_id
            usage_by_ext = llm_usage_by_extraction_id.get(ext_id, [])

            # For session-level usage (transcription), allocate based on timestamp proximity
            # Each extraction gets session-level calls that occurred BEFORE this extraction was created
            # but AFTER the previous extraction (if any) was created
            usage_by_sess = []
            if session_id and session_id in llm_usage_by_session_id:
                session_level_usage = llm_usage_by_session_id[session_id]

                # Find the previous extraction's created_at (if this is a retry)
                prev_created_at = None
                if ext_retry_info["is_retry"] and session_id in session_extractions:
                    sorted_exts = sorted(session_extractions[session_id], key=lambda x: x["created_at"])
                    for idx, se in enumerate(sorted_exts):
                        if se["extraction_id"] == ext_id and idx > 0:
                            prev_created_at = sorted_exts[idx - 1]["created_at"]
                            break

                # Allocate session-level usage to this extraction if it falls in the right time window
                for usage in session_level_usage:
                    usage_created = usage.get("created_at", "")
                    # For the original extraction (not a retry): take all usage <= ext_created_at
                    # For retries: take usage where prev_created_at < usage_created <= ext_created_at
                    if not ext_retry_info["is_retry"]:
                        # Original: take usage before or at extraction time
                        if usage_created <= ext_created_at:
                            usage_by_sess.append(usage)
                    else:
                        # Retry: take usage after previous extraction and before/at this extraction
                        if prev_created_at and prev_created_at < usage_created <= ext_created_at:
                            usage_by_sess.append(usage)

            # Combine and deduplicate by id
            seen_ids = set()
            usage_list = []
            for u in usage_by_ext + usage_by_sess:
                if u["id"] not in seen_ids:
                    seen_ids.add(u["id"])
                    usage_list.append(u)

            # Calculate totals
            total_input = sum(u.get("prompt_token_count") or 0 for u in usage_list)
            total_output = sum(u.get("candidates_token_count") or 0 for u in usage_list)
            total_cached = sum(u.get("cached_content_token_count") or 0 for u in usage_list)
            total_cost = sum(float(u.get("total_cost_usd") or 0) for u in usage_list)
            total_savings = sum(float(u.get("cache_savings_usd") or 0) for u in usage_list)

            item = ExtractionHistoryItem(
                extraction_id=ext_id,
                session_id=session_id,
                submission_id=ext.get("submission_id"),
                consultation_type_id=ext["consultation_type_id"],
                consultation_type_name=consultation_types.get(ext["consultation_type_id"]),
                template_code=templates.get(session_id) if session_id else None,
                recording_duration_seconds=recording_durations.get(session_id) if session_id else None,
                doctor_id=ext.get("doctor_id"),
                doctor_name=doctors.get(ext.get("doctor_id")) if ext.get("doctor_id") else None,
                patient_id=ext.get("patient_id"),
                extraction_mode=ext["extraction_mode"],
                segment_count=ext["segment_count"],
                is_edited=ext.get("edited_extraction_json") is not None,
                edit_count=ext.get("edit_count") or 0,
                is_merged=ext.get("is_merged") or False,
                created_at=ext["created_at"],
                is_retry=ext_retry_info["is_retry"],
                retry_number=ext_retry_info["retry_number"],
                stitching_time_seconds=float(ext["stitching_time_seconds"]) if ext.get("stitching_time_seconds") else None,
                transcription_time_seconds=float(ext["transcription_time_seconds"]) if ext.get("transcription_time_seconds") else None,
                extraction_time_seconds=float(ext["extraction_time_seconds"]) if ext.get("extraction_time_seconds") else None,
                total_processing_time_seconds=float(ext["total_processing_time_seconds"]) if ext.get("total_processing_time_seconds") else None,
                total_llm_calls=len(usage_list),
                total_input_tokens=total_input,
                total_output_tokens=total_output,
                total_cached_tokens=total_cached,
                total_cost_usd=round(total_cost, 6),
                total_cache_savings_usd=round(total_savings, 6),
                llm_usage=[
                    LLMUsageItem(
                        id=u["id"],
                        call_type=u["call_type"],
                        call_subtype=u.get("call_subtype"),
                        model=u["model"],
                        prompt_token_count=u.get("prompt_token_count"),
                        cached_content_token_count=u.get("cached_content_token_count"),
                        candidates_token_count=u.get("candidates_token_count"),
                        total_token_count=u.get("total_token_count"),
                        input_cost_usd=float(u["input_cost_usd"]) if u.get("input_cost_usd") else None,
                        output_cost_usd=float(u["output_cost_usd"]) if u.get("output_cost_usd") else None,
                        cache_savings_usd=float(u["cache_savings_usd"]) if u.get("cache_savings_usd") else None,
                        total_cost_usd=float(u["total_cost_usd"]) if u.get("total_cost_usd") else None,
                        api_duration_seconds=float(u["api_duration_seconds"]) if u.get("api_duration_seconds") else None,
                        cache_hit=u.get("cache_hit"),
                        cache_hit_ratio=float(u["cache_hit_ratio"]) if u.get("cache_hit_ratio") else None,
                        response_status=u.get("response_status"),
                        created_at=u["created_at"]
                    ) for u in usage_list
                ] if include_llm_details else None
            )
            extractions.append(item)

        return ExtractionHistoryResponse(
            extractions=extractions,
            total_count=total_count,
            page=page,
            page_size=page_size,
            has_more=(offset + page_size) < total_count
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve extraction history")


@router.get("/history/{extraction_id}/details")
async def get_extraction_with_llm_details(
    extraction_id: str,
    client: ClientContext = Depends(require_admin)
):
    """
    Get full extraction details including extraction data and LLM usage.

    **Admin only** - Shows detailed LLM usage and cost data.

    Returns:
    - Full extraction data (original or edited)
    - Transcript text
    - All LLM API calls with detailed usage metrics
    """
    try:
        extraction_uuid = uuid.UUID(extraction_id)

        # Get extraction with all data
        ext_result = supabase.table("medical_extractions")\
            .select("*")\
            .eq("id", str(extraction_uuid))\
            .limit(1)\
            .execute()

        if not ext_result.data:
            raise HTTPException(status_code=404, detail="Extraction not found")

        ext = ext_result.data[0]
        session_id = ext.get("session_id")

        # Get consultation type name
        ct_name = None
        if ext.get("consultation_type_id"):
            ct_result = supabase.table("consultation_types")\
                .select("type_name")\
                .eq("id", ext["consultation_type_id"])\
                .limit(1)\
                .execute()
            if ct_result.data:
                ct_name = ct_result.data[0]["type_name"]

        # Get doctor name
        doctor_name = None
        if ext.get("doctor_id"):
            doc_result = supabase.table("doctors")\
                .select("full_name")\
                .eq("id", ext["doctor_id"])\
                .limit(1)\
                .execute()
            if doc_result.data:
                doctor_name = doc_result.data[0]["full_name"]

        # Get template code from session
        template_code = None
        if session_id:
            sess_result = supabase.table("recording_sessions")\
                .select("template_code")\
                .eq("id", session_id)\
                .limit(1)\
                .execute()
            if sess_result.data:
                template_code = sess_result.data[0].get("template_code")

        # Get LLM usage with timestamp-based filtering (same logic as list endpoint)
        # This ensures retry extractions only get their own LLM calls, not calls from other retries
        ext_created_at = ext["created_at"]

        if session_id:
            # Query all LLM usage for this extraction_id OR session_id
            llm_query = supabase.table("llm_usage_log")\
                .select("*")\
                .or_(f"extraction_id.eq.{extraction_id},session_id.eq.{session_id}")\
                .order("created_at", desc=False)
            llm_result = llm_query.execute()
            all_usage = llm_result.data or []

            # Separate by extraction_id vs session_id-only
            usage_by_ext = [u for u in all_usage if u.get("extraction_id") == extraction_id]
            session_level_usage = [u for u in all_usage if u.get("extraction_id") is None and u.get("session_id") == session_id]

            # Check if this is a retry by finding other extractions with the same session_id
            other_extractions = supabase.table("medical_extractions")\
                .select("id, created_at")\
                .eq("session_id", session_id)\
                .order("created_at", desc=False)\
                .execute()

            session_extractions = other_extractions.data or []
            is_retry = False
            prev_created_at = None

            if len(session_extractions) > 1:
                # Find this extraction's position in the list
                sorted_exts = sorted(session_extractions, key=lambda x: x["created_at"])
                for idx, se in enumerate(sorted_exts):
                    if se["id"] == extraction_id:
                        if idx > 0:
                            is_retry = True
                            prev_created_at = sorted_exts[idx - 1]["created_at"]
                        break

            # Filter session-level calls based on timestamp window
            usage_by_sess = []
            for usage in session_level_usage:
                usage_created = usage.get("created_at", "")
                if not is_retry:
                    # Original extraction: take all session-level usage before/at extraction time
                    if usage_created <= ext_created_at:
                        usage_by_sess.append(usage)
                else:
                    # Retry: take only usage between previous extraction and this one
                    if prev_created_at and prev_created_at < usage_created <= ext_created_at:
                        usage_by_sess.append(usage)

            # Combine and deduplicate by id
            seen_ids = set()
            usage_list = []
            for u in usage_by_ext + usage_by_sess:
                if u["id"] not in seen_ids:
                    seen_ids.add(u["id"])
                    usage_list.append(u)
        else:
            # No session_id - just query by extraction_id
            llm_query = supabase.table("llm_usage_log")\
                .select("*")\
                .eq("extraction_id", extraction_id)\
                .order("created_at", desc=False)
            llm_result = llm_query.execute()
            usage_list = llm_result.data or []

        # Calculate totals
        total_input = sum(u.get("prompt_token_count") or 0 for u in usage_list)
        total_output = sum(u.get("candidates_token_count") or 0 for u in usage_list)
        total_cached = sum(u.get("cached_content_token_count") or 0 for u in usage_list)
        total_cost = sum(float(u.get("total_cost_usd") or 0) for u in usage_list)
        total_savings = sum(float(u.get("cache_savings_usd") or 0) for u in usage_list)

        # Use edited data if available, otherwise original.
        # Strip excluded-category segments before returning to the UI — the
        # extraction pipeline keeps them in the assembled prompt and DB so a
        # category toggle doesn't require re-assembly, but webhook consumers
        # never see them and UI surfaces shouldn't either. Symmetric with
        # webhook_service.send_insights_to_webhook's strip.
        from services.extraction_response_filter import filter_excluded_segments
        extraction_data = ext.get("edited_extraction_json") or ext.get("original_extraction_json")
        extraction_data = filter_excluded_segments(extraction_data, template_code)

        return {
            "extraction_id": extraction_id,
            "session_id": session_id,
            "consultation_type_id": ext["consultation_type_id"],
            "consultation_type_name": ct_name,
            "template_code": template_code,
            "doctor_id": ext.get("doctor_id"),
            "doctor_name": doctor_name,
            "patient_id": ext.get("patient_id"),
            "extraction_mode": ext["extraction_mode"],
            "segment_count": ext["segment_count"],
            "is_edited": ext.get("edited_extraction_json") is not None,
            "edit_count": ext.get("edit_count") or 0,
            "is_merged": ext.get("is_merged") or False,
            "created_at": ext["created_at"],
            "transcript_text": ext.get("transcript_text"),
            "extraction_data": extraction_data,
            # Processing times
            "stitching_time_seconds": float(ext["stitching_time_seconds"]) if ext.get("stitching_time_seconds") else None,
            "transcription_time_seconds": float(ext["transcription_time_seconds"]) if ext.get("transcription_time_seconds") else None,
            "extraction_time_seconds": float(ext["extraction_time_seconds"]) if ext.get("extraction_time_seconds") else None,
            "total_processing_time_seconds": float(ext["total_processing_time_seconds"]) if ext.get("total_processing_time_seconds") else None,
            # LLM usage summary
            "llm_usage_summary": {
                "total_calls": len(usage_list),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_cached_tokens": total_cached,
                "total_cost_usd": round(total_cost, 6),
                "total_cache_savings_usd": round(total_savings, 6),
                "avg_cache_hit_ratio": round(
                    sum(float(u.get("cache_hit_ratio") or 0) for u in usage_list) / len(usage_list), 2
                ) if usage_list else 0
            },
            # Detailed LLM usage
            "llm_usage": [
                {
                    "id": u["id"],
                    "call_type": u["call_type"],
                    "call_subtype": u.get("call_subtype"),
                    "model": u["model"],
                    "prompt_token_count": u.get("prompt_token_count"),
                    "cached_content_token_count": u.get("cached_content_token_count"),
                    "candidates_token_count": u.get("candidates_token_count"),
                    "total_token_count": u.get("total_token_count"),
                    "input_cost_usd": float(u["input_cost_usd"]) if u.get("input_cost_usd") else None,
                    "output_cost_usd": float(u["output_cost_usd"]) if u.get("output_cost_usd") else None,
                    "cache_savings_usd": float(u["cache_savings_usd"]) if u.get("cache_savings_usd") else None,
                    "total_cost_usd": float(u["total_cost_usd"]) if u.get("total_cost_usd") else None,
                    "api_duration_seconds": float(u["api_duration_seconds"]) if u.get("api_duration_seconds") else None,
                    "cache_hit": u.get("cache_hit"),
                    "cache_hit_ratio": float(u["cache_hit_ratio"]) if u.get("cache_hit_ratio") else None,
                    "response_status": u.get("response_status"),
                    "created_at": u["created_at"]
                } for u in usage_list
            ]
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid extraction ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve extraction details")


# ============================================================================
# Dynamic {extraction_id} routes - MUST come after static routes
# ============================================================================

@router.get("/{extraction_id}", response_model=ExtractionResponse)
async def get_extraction(
    request: Request,
    extraction_id: str,
    include_segments: bool = Query(True, description="Include individual segment data"),
    _auth = Depends(verify_extraction_access)
):
    """
    Get extraction data by ID.

    Returns edited version if exists, otherwise original AI-generated extraction.

    **Response includes:**
    - `is_edited`: Whether this extraction has been edited
    - `edit_count`: Number of times edited
    - `extraction_data`: Current data (edited if available, otherwise original)
    """
    try:
        extraction_uuid = uuid.UUID(extraction_id)

        if include_segments:
            # Parallelize: fetch extraction record + segments concurrently
            loop = asyncio.get_event_loop()
            data, segments = await asyncio.gather(
                loop.run_in_executor(
                    _extraction_executor, get_extraction_data, extraction_uuid, False
                ),
                loop.run_in_executor(
                    _extraction_executor, get_current_extraction_segments, extraction_uuid
                ),
            )
            data["segments"] = segments
        else:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                _extraction_executor, get_extraction_data, extraction_uuid, False
            )

        # HIPAA Audit: log extraction read with resource context
        client_ctx = getattr(request.state, "client", None)
        if client_ctx:
            try:
                asyncio.create_task(audit_service.log_phi_access(
                    client_context=client_ctx, request=request, response_status=200,
                    response_time_ms=0, resource_type="extraction", resource_id=extraction_id,
                    action="read", patient_id=data.get("patient_id") if isinstance(data, dict) else None,
                ))
            except Exception:
                pass

        return data

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Extraction not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve extraction")


@router.put("/{extraction_id}")
async def update_extraction(
    http_request: Request,
    extraction_id: str,
    request: UpdateExtractionRequest,
    _auth = Depends(verify_extraction_access)
):
    """
    Update extraction with doctor's edits.

    **What this does:**
    - Stores edited_data in `edited_extraction_json`
    - Increments `edit_count`
    - Updates `last_edited_at` and `last_edited_by`
    - Updates individual segments in `extraction_segments` table
    - **Does NOT modify** `original_extraction_json` (AI-generated data preserved)
    - **Schedules background task** to compare medicine name changes and log feedback

    **Usage:**
    1. Doctor edits extraction in frontend
    2. Frontend calls this endpoint with complete edited JSON
    3. System stores latest edit (overwrites previous edit if exists)
    4. Original AI extraction remains unchanged for comparison
    5. Background task compares medicine names and logs corrections to medicine_match_log

    **Returns:** Updated extraction metadata
    """
    try:
        extraction_uuid = uuid.UUID(extraction_id)
        edited_by_uuid = uuid.UUID(request.edited_by)

        # Validate edited_by_type
        if request.edited_by_type not in ("doctor", "nurse"):
            raise HTTPException(
                status_code=400,
                detail="Invalid edited_by_type. Must be 'doctor' or 'nurse'."
            )

        # Validate that edited_by exists in the appropriate table
        if request.edited_by_type == "doctor":
            doctor_check = supabase.table("doctors")\
                .select("id")\
                .eq("id", str(edited_by_uuid))\
                .limit(1)\
                .execute()
            if not doctor_check.data:
                raise HTTPException(
                    status_code=404,
                    detail="Doctor not found"
                )
        else:  # nurse
            nurse_check = supabase.table("nurses")\
                .select("id")\
                .eq("id", str(edited_by_uuid))\
                .limit(1)\
                .execute()
            if not nurse_check.data:
                raise HTTPException(
                    status_code=404,
                    detail="Nurse not found"
                )

        # Get original extraction BEFORE update for medicine comparison
        # Also get template_code for AOSTA_OP sync check (via recording_sessions FK)
        original_result = supabase.table("medical_extractions")\
            .select("original_extraction_json, doctor_id, patient_id, recording_metadata_json, recording_sessions(template_code)")\
            .eq("id", str(extraction_uuid))\
            .limit(1)\
            .execute()

        original_extraction = None
        doctor_id = None
        patient_uuid = None
        recording_metadata = None
        template_code = None
        if original_result.data:
            original_extraction = original_result.data[0].get("original_extraction_json")
            doctor_id = original_result.data[0].get("doctor_id")
            patient_uuid = original_result.data[0].get("patient_id")
            recording_metadata = original_result.data[0].get("recording_metadata_json") or {}
            session_info = original_result.data[0].get("recording_sessions") or {}
            template_code = session_info.get("template_code")

        # Perform the update
        updated = update_extraction_edits(
            extraction_id=extraction_uuid,
            edited_data=request.edited_data,
            edited_by=edited_by_uuid,
            edited_by_type=request.edited_by_type
        )

        # Schedule background task to compare medicine edits
        if original_extraction and doctor_id:
            from services.background_tasks import schedule_medicine_edit_feedback
            await schedule_medicine_edit_feedback(
                extraction_id=extraction_uuid,
                doctor_id=uuid.UUID(doctor_id),
                original_extraction=original_extraction,
                edited_extraction=request.edited_data,
            )

        # EHR Integration: Unified doctor-based routing (fire-and-forget)
        # Routes to EHR based on doctor's ehr_type_id (not template code)
        # - Doctor's ehr_type_id determines which EHR to send to
        # - Hospital's config provides the URL for that EHR type
        # - Both creation AND edit/save trigger EHR sync (EHR overrides with latest payload)
        ehr_sync_scheduled = False
        if doctor_id:
            try:
                from services.ehr_routing_service import schedule_ehr_sync
                from services.supabase_service import get_doctor_hospital_id_cached
                from services.aosta_service import get_patient_external_id, get_hospital_code

                # Build patient_info dict with all fields needed by various EHRs
                patient_info = {}

                # Get patient external ID (UHID)
                if patient_uuid:
                    patient_info["patient_id"] = get_patient_external_id(patient_uuid) or ""

                # Get hospital_id and hospital_code
                hospital_id = get_doctor_hospital_id_cached(uuid.UUID(doctor_id))
                if hospital_id:
                    patient_info["hospital_code"] = get_hospital_code(str(hospital_id)) or ""

                patient_info["doctor_id"] = doctor_id

                # All EHR-specific fields from recording_metadata
                # (each EHR routing function picks only the fields it needs)
                if recording_metadata:
                    for key in ("ip_id", "op_id", "visit_id", "visit_number",
                                "consultant_id", "modified_user_id", "created_user_id", "sex"):
                        if key in recording_metadata:
                            patient_info[key] = recording_metadata[key]
                    # Raster templateId — iframe sends under "template_id" (not "template_id_raster")
                    from services.raster_api_service import extract_raster_template_id
                    _tid_raster = extract_raster_template_id(recording_metadata)
                    if _tid_raster is not None:
                        patient_info["template_id_raster"] = _tid_raster
                    # GEM_CASE_SHEET / GCC_REVIEW fields (sent to Aosta URL with Template_id/Template_Name)
                    patient_info["template_id_aosta"] = recording_metadata.get("template_id") or recording_metadata.get("Template_id") or ""
                    patient_info["template_name_aosta"] = recording_metadata.get("template_name") or recording_metadata.get("Template_Name") or ""

                # Re-match medicines and investigations against doctor/hospital lists
                # to ensure _external_id and other enrichment fields are current
                import copy
                from services.medicine_service import postprocess_prescription_extraction
                from services.investigation_service import postprocess_investigations_extraction

                # Use the merged edited JSON from update_extraction_edits — not the
                # raw partial payload — so previously-saved sections survive when
                # the frontend renders only a subset of segments.
                base_for_enrich = (updated or {}).get("edited_extraction_json") or request.edited_data
                enriched_data = copy.deepcopy(base_for_enrich)
                try:
                    enriched_data = await postprocess_prescription_extraction(
                        extraction_data=enriched_data,
                        doctor_id=uuid.UUID(doctor_id),
                        extraction_id=extraction_uuid,
                        submission_id=str(extraction_uuid),
                        log_matches=False
                    )
                    enriched_data = await postprocess_investigations_extraction(
                        extraction_data=enriched_data,
                        doctor_id=uuid.UUID(doctor_id),
                        extraction_id=extraction_uuid,
                        submission_id=str(extraction_uuid),
                        log_matches=False
                    )
                    logger.info(f"[EXTRACTIONS] Re-matched medicines/investigations for edit of {extraction_uuid}")

                    # Compute EHR payload (formatted, with lookups) separately
                    # enriched_data stays RAW -> edited_extraction_json
                    # ehr_payload gets lookups -> ehr_payload_json
                    ehr_payload = None
                    try:
                        # Only compute ehr_payload for templates that have lookups (neo_*/neonatal_*)
                        _tc_upper = (template_code or "").upper()
                        if _tc_upper.startswith("NEO") or _tc_upper.startswith("NEONATAL"):
                            import copy as _copy
                            from services.neo_lookup_dispatcher import apply_template_lookups
                            ehr_payload = apply_template_lookups(_copy.deepcopy(enriched_data), template_code)
                    except Exception as lookup_err:
                        logger.warning(f"[EXTRACTIONS] EHR payload computation on edit failed: {lookup_err}")

                    # Persist: raw enriched -> edited_extraction_json, formatted -> ehr_payload_json
                    try:
                        update_fields = {"edited_extraction_json": enriched_data}
                        if ehr_payload is not None:
                            update_fields["ehr_payload_json"] = ehr_payload
                        supabase.table("medical_extractions")\
                            .update(update_fields)\
                            .eq("id", str(extraction_uuid))\
                            .execute()
                        logger.info(f"[EXTRACTIONS] Persisted enriched edited data + ehr_payload for {extraction_uuid}")
                    except Exception as persist_err:
                        logger.warning(f"[EXTRACTIONS] Failed to persist enriched data: {persist_err}")
                except Exception as e:
                    logger.warning(f"[EXTRACTIONS] Re-match on edit failed, using raw edited data: {e}")
                    enriched_data = request.edited_data

                # Schedule EHR sync (fire-and-forget based on doctor's ehr_type_id)
                ehr_sync_scheduled = schedule_ehr_sync(
                    doctor_id=doctor_id,
                    extraction_data=enriched_data,
                    patient_info=patient_info,
                    template_code=template_code,
                    is_edit=True,
                    extraction_id=str(extraction_uuid),
                )

                if ehr_sync_scheduled:
                    logger.info(f"[EXTRACTIONS] EHR sync scheduled for extraction {extraction_uuid} on edit")

            except Exception as e:
                logger.warning(f"[EXTRACTIONS] Failed to schedule EHR sync: {e}")

        # Generate edit warnings (non-blocking — save always succeeds)
        edit_warnings = []
        try:
            from services.edit_validation_service import generate_edit_warnings
            ehr_code_for_warnings = None
            if doctor_id:
                from services.ehr_routing_service import get_doctor_ehr_config
                ehr_config = await get_doctor_ehr_config(doctor_id, template_code)
                ehr_code_for_warnings = ehr_config.get("ehr_code") if ehr_config else None

            edit_warnings = generate_edit_warnings(
                enriched_data=locals().get('enriched_data', request.edited_data),
                ehr_code=ehr_code_for_warnings,
                template_code=template_code,
                original_extraction=original_extraction,
                edited_extraction=request.edited_data,
            )
            if edit_warnings:
                logger.info(f"[EXTRACTIONS] Generated {len(edit_warnings)} edit warning(s) for {extraction_uuid}")
        except Exception as e:
            logger.warning(f"[EXTRACTIONS] Failed to generate edit warnings: {e}")

        # Publish edit to realtime table (fire-and-forget)
        try:
            from services.realtime_publisher_service import publish_extraction_response_fire_and_forget
            from services.supabase_service import get_doctor_hospital_id_cached
            import uuid as uuid_mod

            _rt_hospital_id = get_doctor_hospital_id_cached(uuid_mod.UUID(doctor_id)) if doctor_id else None
            if _rt_hospital_id:
                _rt_recording_metadata = None
                try:
                    _me_result = supabase.table("medical_extractions").select(
                        "recording_metadata_json"
                    ).eq("id", str(extraction_uuid)).limit(1).execute()
                    if _me_result.data:
                        _rt_recording_metadata = _me_result.data[0].get("recording_metadata_json") or {}
                except Exception:
                    pass
                asyncio.create_task(publish_extraction_response_fire_and_forget(
                    submission_id=str(extraction_uuid),
                    hospital_id=_rt_hospital_id,
                    doctor_id=doctor_id,
                    extraction_id=str(extraction_uuid),
                    insights=enriched_data,
                    recording_metadata=_rt_recording_metadata,
                ))
        except Exception as e:
            logger.warning(f"[EXTRACTIONS] Failed to schedule realtime publish for edit: {e}")

        # HIPAA Audit: log extraction update
        client_ctx = getattr(http_request.state, "client", None)
        if client_ctx:
            try:
                asyncio.create_task(audit_service.log_phi_access(
                    client_context=client_ctx, request=http_request, response_status=200,
                    response_time_ms=0, resource_type="extraction", resource_id=extraction_id,
                    action="update", doctor_id=uuid.UUID(doctor_id) if doctor_id else None,
                ))
            except Exception:
                pass

        # Fire-and-forget: compute accuracy metrics (Phase 3)
        if original_extraction and doctor_id:
            try:
                from services.accuracy_metrics_service import compute_and_save_accuracy_metrics
                asyncio.create_task(compute_and_save_accuracy_metrics(
                    extraction_id=extraction_uuid,
                    original_json=original_extraction,
                    edited_json=request.edited_data,
                    doctor_id=doctor_id,
                ))
            except Exception as e:
                logger.warning(f"[EXTRACTIONS] Failed to schedule accuracy metrics: {e}")

        return {
            "success": True,
            "message": f"Extraction updated successfully. Edit count: {updated.get('edit_count', 0)}",
            "extraction_id": str(extraction_uuid),
            "edit_count": updated.get("edit_count", 0),
            "last_edited_at": updated.get("last_edited_at"),
            "medicine_feedback_scheduled": bool(original_extraction and doctor_id),
            "ehr_sync_scheduled": ehr_sync_scheduled,
            "warnings": edit_warnings
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Extraction not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update extraction")


@router.put("/by-submission/{submission_id}")
async def update_extraction_by_submission(
    http_request: Request,
    submission_id: str,
    request: UpdateExtractionRequest,
    _auth = Depends(verify_submission_access)
):
    """
    Update extraction with doctor's edits using submission_id.

    This is a wrapper around the main update endpoint for cases where
    the frontend only has the submission_id (from the recording workflow)
    and not the extraction_id.

    **Direct lookup:** medical_extractions.submission_id -> extraction_id
    (submission_id is stored directly in medical_extractions table)

    **See also:** PUT /{extraction_id} for direct extraction updates
    """
    try:
        submission_uuid = uuid.UUID(submission_id)

        # Direct lookup: medical_extractions has submission_id column
        extraction_result = supabase.table("medical_extractions")\
            .select("id")\
            .eq("submission_id", str(submission_uuid))\
            .limit(1)\
            .execute()

        if not extraction_result.data:
            raise HTTPException(
                status_code=404,
                detail="No extraction found. It may still be in progress."
            )

        extraction_id = extraction_result.data[0]["id"]

        # Delegate to the main update function
        return await update_extraction(http_request, extraction_id, request)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid submission_id format")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update extraction")


@router.get("/{extraction_id}/compare", response_model=ComparisonResponse)
async def compare_extraction(
    request: Request,
    extraction_id: str,
    _auth = Depends(verify_extraction_access)
):
    """
    Compare original AI-generated extraction vs latest edited version.

    **Response includes:**
    - `original`: AI-generated extraction (immutable)
    - `edited`: Latest edited version (null if never edited)
    - `has_edits`: Whether extraction has been edited
    - `edit_count`: Number of times edited

    **Use cases:**
    - Review doctor edits vs AI output
    - Audit trail for compliance
    - Quality assurance
    - Training data for model improvement
    """
    try:
        extraction_uuid = uuid.UUID(extraction_id)
        comparison = compare_extraction_versions(extraction_uuid)
        return comparison

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Extraction not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to compare extraction versions")


@router.get("/{extraction_id}/original")
async def get_original_extraction(
    request: Request,
    extraction_id: str,
    _auth = Depends(verify_extraction_access)
):
    """
    Get ONLY the original AI-generated extraction (ignore edits).

    **Use case:** Review what AI originally extracted before any doctor edits.
    """
    try:
        extraction_uuid = uuid.UUID(extraction_id)
        comparison = compare_extraction_versions(extraction_uuid)
        return {
            "extraction_id": str(extraction_uuid),
            "original_data": comparison["original"],
            "has_edits": comparison["has_edits"],
            "edit_count": comparison["edit_count"]
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Extraction not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve original extraction")


@router.get("/{extraction_id}/edited")
async def get_edited_extraction(
    request: Request,
    extraction_id: str,
    _auth = Depends(verify_extraction_access)
):
    """
    Get ONLY the edited version (returns 404 if never edited).

    **Use case:** Get latest doctor edits without original AI data.
    """
    try:
        extraction_uuid = uuid.UUID(extraction_id)
        comparison = compare_extraction_versions(extraction_uuid)

        if not comparison["has_edits"]:
            raise HTTPException(status_code=404, detail="This extraction has not been edited")

        return {
            "extraction_id": str(extraction_uuid),
            "edited_data": comparison["edited"],
            "edit_count": comparison["edit_count"],
            "last_edited_at": comparison["last_edited_at"],
            "last_edited_by": comparison["last_edited_by"]
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Extraction not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve edited extraction")


@router.get("/{extraction_id}/ehr-payload")
async def get_ehr_payload(
    request: Request,
    extraction_id: str,
    _auth = Depends(verify_extraction_access),
):
    """
    Return the formatted EHR payload that was (or would be) sent to the
    target hospital EHR API, alongside the edited and original extractions
    for side-by-side comparison.

    **Use case:** verify that the EHR formatter produced the correct wire
    shape from the doctor's edited JSON — useful when investigating why a
    field shows up empty on the EHR side after a doctor edit.

    **Response:**
    - `extraction_id`
    - `ehr_payload`: the dict persisted in `ehr_payload_json` (null if the
      extraction's template doesn't go through a formatter, or if no edit
      has triggered a payload computation yet)
    - `edited_extraction`: latest `edited_extraction_json` (null if never
      edited)
    - `original_extraction`: AI-generated `original_extraction_json`
    - `edit_count`, `last_edited_at`, `last_edited_by`, `edited_by_type`
    - `form_type`: convenience field — pulled from `ehr_payload.form_type`
      when available
    """
    try:
        extraction_uuid = uuid.UUID(extraction_id)

        result = (
            supabase.table("medical_extractions")
            .select(
                "ehr_payload_json, edited_extraction_json, original_extraction_json, "
                "edit_count, last_edited_at, last_edited_by, edited_by_type, "
                "transcript_text, session_id, is_merged, "
                "recording_sessions(template_code)"
            )
            .eq("id", str(extraction_uuid))
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Extraction not found")

        row = result.data[0]
        ehr_payload = row.get("ehr_payload_json")
        form_type = (
            ehr_payload.get("form_type")
            if isinstance(ehr_payload, dict)
            else None
        )
        # Strip excluded-category segments before returning. See note at
        # the by-id details endpoint above.
        from services.extraction_response_filter import filter_excluded_segments
        _rs = row.get("recording_sessions") or {}
        _template_code = _rs.get("template_code") if isinstance(_rs, dict) else None

        # Transcript fallback: when medical_extractions.transcript_text is empty,
        # fall back to processing_jobs.transcript for the same session (mirrors
        # the precedence used by get_session_transcript()).
        transcript_text = row.get("transcript_text")
        session_id = row.get("session_id")
        if not transcript_text and session_id:
            try:
                _job_result = (
                    supabase.table("processing_jobs")
                    .select("transcript")
                    .eq("session_id", session_id)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if _job_result.data:
                    transcript_text = _job_result.data[0].get("transcript")
            except Exception as e:
                logger.warning(f"[EXTRACTIONS] transcript fallback failed for {extraction_id}: {e}")

        return {
            "extraction_id": str(extraction_uuid),
            "session_id": session_id,
            "is_merged": bool(row.get("is_merged")),
            "transcript_text": transcript_text,
            "ehr_payload": ehr_payload,
            "edited_extraction": filter_excluded_segments(
                row.get("edited_extraction_json"), _template_code
            ),
            "original_extraction": filter_excluded_segments(
                row.get("original_extraction_json"), _template_code
            ),
            "edit_count": row.get("edit_count", 0) or 0,
            "last_edited_at": row.get("last_edited_at"),
            "last_edited_by": row.get("last_edited_by"),
            "edited_by_type": row.get("edited_by_type"),
            "form_type": form_type,
        }

    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction ID")
    except Exception as e:
        logger.error(f"[EXTRACTIONS] Failed to fetch EHR payload for {extraction_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve EHR payload")


# ============================================================================
# Emotion Analysis Endpoints
# ============================================================================

class InterventionResponse(BaseModel):
    """Individual intervention recommendation"""
    id: Optional[str] = None
    code: str
    name: str
    description: str
    category: str  # 7 categories: OP_TO_IP, FOLLOWUP_DUE, RX_REFILL, DIAGNOSTICS_DUE, ALLIED_HEALTH, RETENTION_RISK, QUALITY_RISK
    priority: str
    priority_score: int
    trigger_reason: str
    is_top_3: bool
    analysis_mode: str
    rationale_sources: Union[List[Any], Dict[str, Any]] = []  # Can be list (old) or dict (new insights-based)
    created_at: Optional[str] = None
    # New fields for insights-based interventions
    intervention_sub_type: Optional[str] = None  # allied_health, clinical_upsell, etc.
    action: Optional[str] = None  # Recommended action text
    revenue_estimate: Optional[float] = None  # Revenue potential for revenue-related categories
    take_up_likelihood: Optional[int] = None  # 0-100 predicted take-up likelihood (for dashboard risk segmentation)


class UnifiedEmotionSegment(BaseModel):
    """Unified emotion segment (combines text + audio analysis)"""
    segment_code: str
    segment_name: str
    source: str  # "text_only", "audio_only", or "combined"
    segment_value: Dict[str, Any]  # The nested emotion data
    created_at: Optional[str] = None


class CongruenceSummary(BaseModel):
    """Simplified congruence analysis summary"""
    overall_congruence: Optional[str] = None  # "High", "Moderate", "Low"
    congruence_score: Optional[float] = None
    has_mismatches: bool = False


class EmotionAnalysisResponse(BaseModel):
    """Response for emotion analysis data"""
    extraction_id: str
    # Unified emotion segments with source field (text_only, audio_only, or combined)
    unified_emotions: List[UnifiedEmotionSegment] = []
    # Congruence summary (overall assessment of text vs audio alignment)
    congruence_summary: Optional[CongruenceSummary] = None
    # NOTE: Interventions moved to dedicated endpoint: GET /{extraction_id}/interventions
    # Started flags (to detect if extraction was ever initiated for this mode)
    emotion_extraction_started: bool = False
    audio_emotion_extraction_started: bool = False
    congruence_analysis_started: bool = False
    # Completed flags
    emotion_extraction_completed: bool
    audio_emotion_extraction_completed: bool
    congruence_analysis_completed: bool
    # Fallback flag (audio emotion JSON parse failed, returned empty emotions)
    audio_emotion_extraction_fallback_used: bool = False


@router.get("/{extraction_id}/emotions", response_model=EmotionAnalysisResponse)
async def get_emotion_analysis(
    request: Request,
    extraction_id: str,
    _auth = Depends(verify_extraction_access)
):
    """
    Get emotion analysis results for an extraction.

    Returns unified emotion segments with source indicator (text_only, audio_only, combined):
    - **unified_emotions**: All emotion data with source field
      (ANXIETY_POST_CONSULTATION, FINANCIAL_CONCERNS, OTHER_EMOTIONS_DETECTED,
       TREATMENT_COMPLIANCE_LIKELIHOOD, DOCTOR_COMMUNICATION_STYLE)
    - **congruence_summary**: Overall text vs audio alignment assessment

    **Use cases:**
    - Display emotion analysis in UI modal
    - Clinical insights review
    - Patient communication assessment
    """
    try:
        extraction_uuid = uuid.UUID(extraction_id)

        # Get extraction status (include _started flags to detect mode)
        ext_result = supabase.table("medical_extractions")\
            .select(
                "id, emotion_extraction_started, emotion_extraction_completed, "
                "audio_emotion_extraction_started, audio_emotion_extraction_completed, "
                "audio_emotion_extraction_fallback_used, "
                "congruence_analysis_started, congruence_analysis_completed"
            )\
            .eq("id", str(extraction_uuid))\
            .limit(1)\
            .execute()

        if not ext_result.data:
            raise HTTPException(status_code=404, detail="Extraction not found")

        ext = ext_result.data[0]

        # Get all emotion segments for this extraction
        # Note: extraction_segments uses segment_value (jsonb), not segment_data
        segments_result = supabase.table("extraction_segments")\
            .select("segment_code, segment_value, created_at")\
            .eq("extraction_id", str(extraction_uuid))\
            .execute()

        segments = segments_result.data or []

        # Unified emotion segment codes (7 segments as of Jan 2026)
        unified_emotion_codes = [
            "ANXIETY_POST_CONSULTATION",
            "FINANCIAL_CONCERNS",
            "OTHER_EMOTIONS_DETECTED",
            "TREATMENT_COMPLIANCE_LIKELIHOOD",
            "DOCTOR_COMMUNICATION_STYLE",
            "INTERACTION_DYNAMICS",      # New in Jan 2026
            "CONGRUENCE_SUMMARY"          # New in Jan 2026
        ]
        congruence_code = "CONGRUENCE_SUMMARY"

        unified_emotions = []
        congruence_summary = None

        # Helper to format segment code as readable name
        def format_segment_name(code: str) -> str:
            return code.replace("_", " ").title()

        for seg in segments:
            code = seg.get("segment_code", "")
            segment_data = seg.get("segment_value") or {}

            # Check if this is a unified emotion segment
            if code in unified_emotion_codes:
                # Extract source from segment_value (default to "combined" for backwards compat)
                source = segment_data.get("source", "combined") if isinstance(segment_data, dict) else "combined"
                unified_emotions.append(UnifiedEmotionSegment(
                    segment_code=code,
                    segment_name=format_segment_name(code),
                    source=source,
                    segment_value=segment_data,
                    created_at=seg.get("created_at")
                ))
            elif code == congruence_code:
                # Build congruence summary from the congruence analysis segment
                if isinstance(segment_data, dict):
                    congruence_summary = CongruenceSummary(
                        overall_congruence=segment_data.get("overall_congruence"),
                        congruence_score=segment_data.get("congruence_score"),
                        has_mismatches=segment_data.get("has_mismatches", False)
                    )

        # NOTE: Interventions now served via dedicated endpoint: GET /{extraction_id}/interventions

        return EmotionAnalysisResponse(
            extraction_id=str(extraction_uuid),
            # Unified emotions contains all emotion data with source field
            unified_emotions=unified_emotions,
            congruence_summary=congruence_summary,
            # Started flags (to detect mode - if not started, don't show "in progress")
            emotion_extraction_started=ext.get("emotion_extraction_started", False) or False,
            audio_emotion_extraction_started=ext.get("audio_emotion_extraction_started", False) or False,
            congruence_analysis_started=ext.get("congruence_analysis_started", False) or False,
            # Completed flags
            emotion_extraction_completed=ext.get("emotion_extraction_completed", False) or False,
            audio_emotion_extraction_completed=ext.get("audio_emotion_extraction_completed", False) or False,
            congruence_analysis_completed=ext.get("congruence_analysis_completed", False) or False,
            # Fallback flag (audio emotion JSON parse failed, returned empty emotions)
            audio_emotion_extraction_fallback_used=ext.get("audio_emotion_extraction_fallback_used", False) or False,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid extraction ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve emotion analysis")


# ============================================================================
# Interventions Response Model
# ============================================================================

class InterventionsResponse(BaseModel):
    """Response for interventions endpoint"""
    extraction_id: str
    interventions: List[InterventionResponse]
    summary: Dict[str, Any]  # Category counts and totals
    insights_enabled: Optional[bool] = True  # Whether consultation insights was enabled for this consultation type


@router.get("/{extraction_id}/interventions", response_model=InterventionsResponse)
async def get_extraction_interventions(
    request: Request,
    extraction_id: str,
    _auth = Depends(verify_extraction_access)
):
    """
    Get patient interventions for an extraction.

    Returns interventions generated from consultation insights analysis.

    **7 Dashboard Categories:**
    - OP_TO_IP: Surgical consultation (potential OP to IP conversion)
    - FOLLOWUP_DUE: Return visits needed (second opinion, alternative treatment, specialist referral)
    - RX_REFILL: Prescription refill opportunities
    - DIAGNOSTICS_DUE: Diagnostic test opportunities (home collection, recurring tests)
    - ALLIED_HEALTH: Allied health referrals (nutrition, physio, mental health, etc.)
    - RETENTION_RISK: Patient retention alerts (competitor risk, compliance, satisfaction)
    - QUALITY_RISK: Clinical quality/safety alerts (medication safety, documentation)

    Each intervention includes:
    - Category and sub-type tags
    - Priority level and score (pure clinical need, not adjusted by take-up)
    - Take-up likelihood (0-100) for dashboard risk segmentation
    - Trigger reason and recommended action
    - Rationale sources with evidence
    - Revenue estimate (for revenue-related categories)
    """
    try:
        extraction_uuid = uuid.UUID(extraction_id)

        # Check if consultation insights is enabled for this extraction's consultation type
        ext_check = supabase.table("medical_extractions").select(
            "consultation_type_id, consultation_types!inner(type_code, enable_consultation_insights)"
        ).eq("id", str(extraction_uuid)).single().execute()

        insights_enabled = True  # Default to True
        if ext_check.data:
            ct = ext_check.data.get("consultation_types", {})
            insights_enabled = ct.get("enable_consultation_insights", True) if ct else True

        # Get interventions
        from services.supabase_service import get_patient_interventions
        interventions_data = get_patient_interventions(extraction_uuid)

        interventions = [
            InterventionResponse(
                id=i.get("id"),
                code=i.get("code", ""),
                name=i.get("name", ""),
                description=i.get("description", ""),
                category=i.get("category", "RETENTION_RISK"),  # Default to RETENTION_RISK
                priority=i.get("priority", "medium"),
                priority_score=i.get("priority_score", 50),
                trigger_reason=i.get("trigger_reason", ""),
                is_top_3=i.get("is_top_3", False),
                analysis_mode=i.get("analysis_mode", "combined"),
                rationale_sources=i.get("rationale_sources", []),
                created_at=i.get("created_at"),
                intervention_sub_type=i.get("intervention_sub_type"),
                action=i.get("action"),
                revenue_estimate=i.get("revenue_estimate"),
                take_up_likelihood=i.get("take_up_likelihood"),
            )
            for i in interventions_data
        ]

        # Calculate summary with new 7-category system
        # Categories: OP_TO_IP, FOLLOWUP_DUE, RX_REFILL, DIAGNOSTICS_DUE, ALLIED_HEALTH, RETENTION_RISK, QUALITY_RISK
        category_counts = {}
        for cat in ["OP_TO_IP", "FOLLOWUP_DUE", "RX_REFILL", "DIAGNOSTICS_DUE", "ALLIED_HEALTH", "RETENTION_RISK", "QUALITY_RISK"]:
            category_counts[cat] = len([i for i in interventions if i.category == cat])

        # Revenue categories for potential calculation (OP_TO_IP, FOLLOWUP_DUE, RX_REFILL, DIAGNOSTICS_DUE, ALLIED_HEALTH)
        revenue_categories = ["OP_TO_IP", "FOLLOWUP_DUE", "RX_REFILL", "DIAGNOSTICS_DUE", "ALLIED_HEALTH"]
        total_revenue_potential = sum(
            i.revenue_estimate or 0 for i in interventions if i.category in revenue_categories
        )

        summary = {
            "total": len(interventions),
            "by_category": category_counts,
            "revenue_potential": total_revenue_potential,
            "has_critical": any(i.priority.upper() == "CRITICAL" for i in interventions),
        }

        return InterventionsResponse(
            extraction_id=str(extraction_uuid),
            interventions=interventions,
            summary=summary,
            insights_enabled=insights_enabled,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid extraction ID")
    except Exception as e:
        logger.error(f"Failed to get interventions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve interventions")


@router.get("/by-submission/{submission_id}/emotions", response_model=EmotionAnalysisResponse)
async def get_emotion_analysis_by_submission(
    request: Request,
    submission_id: str,
    _auth = Depends(verify_submission_access)
):
    """
    Get emotion analysis results by submission_id (alternative to extraction_id lookup).

    This is a wrapper endpoint that:
    1. Looks up the extraction_id from the submission_id
    2. Returns the same emotion analysis data as GET /{extraction_id}/emotions

    **Direct lookup:** medical_extractions.submission_id -> extraction_id
    (submission_id is stored directly in medical_extractions table)

    **Use cases:**
    - Frontend fallback when extraction_id is not available
    - Historical lookups by submission_id
    - Error recovery scenarios

    **Path Parameters:**
    - `submission_id`: The submission ID from the recording workflow

    **Returns:** Same response as GET /{extraction_id}/emotions
    """
    try:
        submission_uuid = uuid.UUID(submission_id)

        # Direct lookup: medical_extractions has submission_id column
        extraction_result = supabase.table("medical_extractions")\
            .select("id")\
            .eq("submission_id", str(submission_uuid))\
            .limit(1)\
            .execute()

        if not extraction_result.data:
            raise HTTPException(
                status_code=404,
                detail="No extraction found. It may still be in progress."
            )

        extraction_id = extraction_result.data[0]["id"]

        # Delegate to the existing extraction_id endpoint
        return await get_emotion_analysis(request, extraction_id)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid submission ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve emotion analysis")


# =============================================================================
# EDIT HISTORY ENDPOINTS (Phase 2)
# =============================================================================

@router.get("/{extraction_id}/edit-history")
async def get_edit_history(
    extraction_id: str,
    _auth=Depends(verify_extraction_access),
):
    """
    List all edit versions for an extraction.

    Returns version history with metadata (who, when, what changed).
    """
    try:
        extraction_uuid = uuid.UUID(extraction_id)

        result = supabase.table("extraction_edit_history")\
            .select("id, version_number, changed_segments, change_summary, edited_by, edited_by_type, edited_at, edit_source")\
            .eq("extraction_id", str(extraction_uuid))\
            .order("version_number", desc=False)\
            .execute()

        return {
            "success": True,
            "extraction_id": extraction_id,
            "total_versions": len(result.data or []),
            "versions": result.data or [],
        }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction ID")
    except Exception as e:
        logger.error(f"[EXTRACTIONS] Failed to get edit history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get edit history")


@router.get("/{extraction_id}/edit-history/{version_number}")
async def get_edit_version(
    extraction_id: str,
    version_number: int,
    _auth=Depends(verify_extraction_access),
):
    """Get full JSON for a specific edit version."""
    try:
        extraction_uuid = uuid.UUID(extraction_id)

        result = supabase.table("extraction_edit_history")\
            .select("*")\
            .eq("extraction_id", str(extraction_uuid))\
            .eq("version_number", version_number)\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail=f"Version {version_number} not found")

        return {"success": True, "data": result.data[0]}

    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction ID")
    except Exception as e:
        logger.error(f"[EXTRACTIONS] Failed to get edit version: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get edit version")


@router.get("/{extraction_id}/diff")
async def get_edit_diff(
    extraction_id: str,
    from_version: int = Query(..., description="Start version (0 = original AI output)"),
    to_version: int = Query(..., description="End version"),
    _auth=Depends(verify_extraction_access),
):
    """
    Get segment-by-segment diff between two versions.

    Use from_version=0 to compare against the original AI output.
    """
    try:
        extraction_uuid = uuid.UUID(extraction_id)

        # Get "from" version
        if from_version == 0:
            from_result = supabase.table("medical_extractions")\
                .select("original_extraction_json")\
                .eq("id", str(extraction_uuid))\
                .execute()
            if not from_result.data:
                raise HTTPException(status_code=404, detail="Extraction not found")
            from_json = from_result.data[0].get("original_extraction_json") or {}
        else:
            from_result = supabase.table("extraction_edit_history")\
                .select("edited_extraction_json")\
                .eq("extraction_id", str(extraction_uuid))\
                .eq("version_number", from_version)\
                .execute()
            if not from_result.data:
                raise HTTPException(status_code=404, detail=f"Version {from_version} not found")
            from_json = from_result.data[0].get("edited_extraction_json") or {}

        # Get "to" version
        to_result = supabase.table("extraction_edit_history")\
            .select("edited_extraction_json")\
            .eq("extraction_id", str(extraction_uuid))\
            .eq("version_number", to_version)\
            .execute()
        if not to_result.data:
            raise HTTPException(status_code=404, detail=f"Version {to_version} not found")
        to_json = to_result.data[0].get("edited_extraction_json") or {}

        # Compute diff
        all_keys = set(list(from_json.keys()) + list(to_json.keys()))
        diff = {}
        for key in sorted(all_keys):
            old_val = from_json.get(key)
            new_val = to_json.get(key)
            if old_val != new_val:
                diff[key] = {
                    "action": "added" if old_val is None else ("removed" if new_val is None else "modified"),
                    "from": old_val,
                    "to": new_val,
                }

        return {
            "success": True,
            "extraction_id": extraction_id,
            "from_version": from_version,
            "to_version": to_version,
            "changed_segments": list(diff.keys()),
            "diff": diff,
        }

    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction ID")
    except Exception as e:
        logger.error(f"[EXTRACTIONS] Failed to compute diff: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compute diff")


# ─── Translation Endpoints ──────────────────────────────────────────────────

class TranslationEditRequest(BaseModel):
    edited_data: Dict[str, Any]
    edited_by: str
    edited_by_type: str = "doctor"


@router.get("/{extraction_id}/translation")
async def get_extraction_translation_endpoint(
    request: Request,
    extraction_id: str,
    _auth=Depends(verify_extraction_access),
) -> Dict[str, Any]:
    """
    Fetch the translation for an extraction.
    Returns translated JSON, edit state, and processing status.
    """
    try:
        from services.supabase_service import get_extraction_translation

        translation = get_extraction_translation(uuid.UUID(extraction_id))

        if not translation:
            raise HTTPException(status_code=404, detail="No translation found for this extraction")

        return {
            "success": True,
            "translation": translation,
        }

    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction ID")
    except Exception as e:
        logger.error(f"[EXTRACTIONS] Failed to fetch translation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch translation")


@router.put("/{extraction_id}/translation")
async def save_translation_edits_endpoint(
    request: Request,
    extraction_id: str,
    body: TranslationEditRequest,
    _auth=Depends(verify_extraction_access),
) -> Dict[str, Any]:
    """
    Save doctor edits to the translated version of an extraction.
    Edits are stored independently from the English version.
    """
    try:
        from services.supabase_service import get_extraction_translation, update_translation_edits

        # Get existing translation to find target_language
        translation = get_extraction_translation(uuid.UUID(extraction_id))
        if not translation:
            raise HTTPException(status_code=404, detail="No translation found for this extraction")

        target_language = translation["target_language"]

        result = update_translation_edits(
            extraction_id=uuid.UUID(extraction_id),
            target_language=target_language,
            edited_json=body.edited_data,
            edited_by=uuid.UUID(body.edited_by),
            edited_by_type=body.edited_by_type,
        )

        return {
            "success": True,
            "message": "Translation edits saved",
            "translation": result,
        }

    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction ID or editor ID")
    except Exception as e:
        logger.error(f"[EXTRACTIONS] Failed to save translation edits: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save translation edits")


@router.post("/{extraction_id}/translation/retry")
async def retry_translation_endpoint(
    request: Request,
    extraction_id: str,
    _auth=Depends(verify_extraction_access),
) -> Dict[str, Any]:
    """
    Retrigger translation for an extraction.
    Used when English version was edited after translation, or when translation failed.
    """
    try:
        from services.supabase_service import get_extraction_by_id, get_doctor_translation_language
        from services.translation_service import schedule_translation

        extraction = get_extraction_by_id(uuid.UUID(extraction_id))
        if not extraction:
            raise HTTPException(status_code=404, detail="Extraction not found")

        doctor_id = extraction.get("doctor_id")
        if not doctor_id:
            raise HTTPException(status_code=400, detail="Extraction has no associated doctor")

        target_language = get_doctor_translation_language(uuid.UUID(doctor_id))
        if not target_language:
            raise HTTPException(status_code=400, detail="No translation language configured for this doctor")

        # Use the edited version if available, otherwise original
        extraction_data = extraction.get("edited_extraction_json") or extraction.get("original_extraction_json") or {}

        # Get processing mode from the extraction's session
        processing_mode = "default"
        session_id = extraction.get("session_id")
        if session_id:
            try:
                session_response = supabase.table("recording_sessions").select("processing_mode").eq("id", str(session_id)).single().execute()
                if session_response.data:
                    processing_mode = session_response.data.get("processing_mode") or "default"
            except Exception:
                pass

        await schedule_translation(
            extraction_id=uuid.UUID(extraction_id),
            extraction_data=extraction_data,
            doctor_id=doctor_id,
            processing_mode_code=processing_mode,
        )

        return {
            "success": True,
            "message": f"Translation to '{target_language}' has been scheduled",
        }

    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction ID")
    except Exception as e:
        logger.error(f"[EXTRACTIONS] Failed to retry translation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retry translation")

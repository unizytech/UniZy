"""
EHR Integration Router - Sanitized API Wrappers for External EHR Systems

This router provides wrapper endpoints that strip internal/sensitive metadata
before exposing data to EHR integration clients. These endpoints are designed
for external system consumption and exclude:
- Processing time metrics
- Model information
- Internal processing flags
- Full transcripts
- Segment counts and validation details

All endpoints are under /api/v1/ehr/
"""

import os
import uuid
import asyncio
import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Auth imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import (
        EHRCounsellorAccessChecker,
        EHRSubmissionAccessChecker,
        EHRStudentAccessChecker,
        get_current_client
    )
    from models.auth_models import ClientContext

    _doctor_checker = EHRCounsellorAccessChecker()
    _submission_checker = EHRSubmissionAccessChecker()
    _patient_checker = EHRStudentAccessChecker()

    async def verify_counsellor_access(request: Request, counsellor_id: Optional[str] = None):
        """Verify EHR client has access to counsellor data."""
        counsellor_uuid = uuid.UUID(counsellor_id) if counsellor_id else None
        client = get_current_client(request)
        return await _doctor_checker(request, counsellor_uuid, client)

    async def verify_submission_access(request: Request, submission_id: Optional[str] = None):
        """Verify EHR client has access to submission data."""
        submission_uuid = uuid.UUID(submission_id) if submission_id else None
        client = get_current_client(request)
        return await _submission_checker(request, submission_uuid, client)

    async def verify_student_access(request: Request, student_id: str = None):
        """Verify EHR client has access to student data."""
        client = get_current_client(request)
        return await _patient_checker(request, student_id, client)

    def require_admin_webapp_or_ehr(client: ClientContext = Depends(get_current_client)):
        """Allow admin, web_app, or ehr clients for payload preview."""
        if client.client_type in ("admin", "web_app", "ehr"):
            return client
        # Check for admin scopes
        admin_scopes = [s for s in client.scopes if s.startswith("admin:")]
        if admin_scopes:
            return client
        raise HTTPException(
            status_code=403,
            detail="Admin, web app, or EHR access required for payload preview",
        )
else:
    async def verify_counsellor_access(request: Request = None, counsellor_id: Optional[str] = None):
        return None

    async def verify_submission_access(request: Request = None, submission_id: Optional[str] = None):
        return None

    async def verify_student_access(request: Request = None, student_id: str = None):
        return None

    def require_admin_webapp_or_ehr():
        """No-op when auth disabled."""
        return None


# ============================================================================
# Response Models (Sanitized for EHR)
# ============================================================================

class EHRStatusResponse(BaseModel):
    """Sanitized processing status for EHR clients - excludes transcript and metrics"""
    submission_id: str
    status: str
    progress: int
    message: str
    extraction_id: Optional[str] = None
    insights: Optional[Dict[str, Any]] = None
    is_merged: bool = False


class AostaStatusResponse(BaseModel):
    """
    Extended status response for Aosta EHR integration.
    Includes recording_metadata passed during /start API.
    """
    submission_id: str
    status: str
    progress: int
    message: str
    extraction_id: Optional[str] = None
    insights: Optional[Dict[str, Any]] = None
    recording_metadata: Optional[Dict[str, Any]] = None
    is_merged: bool = False


class EHREditRequest(BaseModel):
    """
    Request for generic EHR edit endpoint.

    Used to save edited extraction to our DB and sync to the counsellor's
    configured EHR system (Aosta, KG, Raster, Neopead) via schedule_ehr_sync().
    """
    edited_data: Optional[Dict[str, Any]] = None  # If None, use original extraction
    edited_by: str  # Counsellor or assistant UUID who made edits
    edited_by_type: str = "doctor"  # "doctor" or "nurse"
    recording_metadata: Optional[Dict[str, Any]] = None  # Contains ip_id, op_id, visit_id, etc.


class EHREditResponse(BaseModel):
    """
    Response for generic EHR edit endpoint.

    Returns success even if EHR sync fails (partial success pattern).
    """
    success: bool
    message: str
    extraction_id: Optional[str] = None
    edit_count: Optional[int] = None
    ehr_sync_status: str  # "pending", "success", "failed", "skipped"
    ehr_error: Optional[str] = None


class EHRExtractionMetadata(BaseModel):
    """Sanitized extraction metadata for EHR clients"""
    correlation_id: Optional[str] = None
    submission_id: Optional[str] = None
    extraction_id: Optional[str] = None
    counsellor_id: Optional[str] = None
    student_id: Optional[str] = None
    template_code: Optional[str] = None
    timestamp: Optional[str] = None


class EHRExtractResponse(BaseModel):
    """Sanitized extraction response for EHR clients"""
    success: bool
    insights: Dict[str, Any]
    metadata: EHRExtractionMetadata


class EHRMergeMetadata(BaseModel):
    """Sanitized merge metadata for EHR clients"""
    source_count: int
    target_template_code: str
    cross_type_scenario: Optional[str] = None
    consultation_types_merged: Optional[List[str]] = None


class EHRMergeStatusResponse(BaseModel):
    """Sanitized merge status for EHR clients"""
    extraction_id: str
    status: str
    merged_data: Optional[Dict[str, Any]] = None
    merge_metadata: Optional[EHRMergeMetadata] = None


class EHRMergePreviewResponse(BaseModel):
    """Sanitized merge preview for EHR clients"""
    success: bool
    merged_data: Dict[str, Any]
    merge_metadata: EHRMergeMetadata
    preview: bool = True


class EHREmotionSegment(BaseModel):
    """Sanitized emotion segment for EHR clients"""
    segment_code: str
    segment_name: str
    source: str
    segment_value: Dict[str, Any]


class EHRCongruenceSummary(BaseModel):
    """Sanitized congruence summary for EHR clients"""
    overall_congruence: Optional[str] = None
    congruence_score: Optional[float] = None
    has_mismatches: Optional[bool] = None


class EHREmotionsResponse(BaseModel):
    """Sanitized emotions response for EHR clients - excludes processing flags"""
    extraction_id: str
    unified_emotions: List[EHREmotionSegment]
    congruence_summary: Optional[EHRCongruenceSummary] = None


class EHRStudentInfo(BaseModel):
    """Student info for EHR clients"""
    id: str
    student_id: str
    full_name: Optional[str] = None


class EHRPrescreenResponse(BaseModel):
    """Sanitized prescreen response for EHR clients - excludes model/segment metadata"""
    patient: EHRStudentInfo
    prescreen_data: Optional[Dict[str, Any]] = None
    has_prescreen: bool = False
    emotion_pattern_summary: Optional[Dict[str, Any]] = None
    top_interventions: Optional[List[Dict[str, Any]]] = None
    warning_factors: Optional[Any] = None
    warning_factors_date: Optional[str] = None
    past_diagnosis_summary: Optional[Any] = None
    past_diagnosis_summary_date: Optional[str] = None
    clinical_timeline: Optional[Dict[str, Any]] = None
    last_prescription: Optional[Any] = None
    last_prescription_date: Optional[str] = None
    consultation_count: int = 0
    last_visit_date: Optional[str] = None


# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(
    prefix="/api/v1/ehr",
    tags=["EHR Integration"],
)


# ============================================================================
# Status Endpoint (Sanitized)
# ============================================================================

@router.get("/status/{submission_id}", response_model=EHRStatusResponse)
async def get_ehr_processing_status(
    request: Request,
    submission_id: str,
    _auth=Depends(verify_submission_access)
):
    """
    Get processing status for EHR clients.

    Returns sanitized status excluding:
    - Full transcript
    - Processing time metrics (stitching_time, transcription_time, etc.)
    - Model information
    """
    from services.supabase_service import get_job_by_submission_id, get_extraction_by_submission_id

    try:
        submission_uuid = uuid.UUID(submission_id)

        job = get_job_by_submission_id(submission_uuid)
        if not job:
            raise HTTPException(status_code=404, detail="Processing job not found")

        response = EHRStatusResponse(
            submission_id=submission_id,
            status=job["status"],
            progress=job["progress_percentage"],
            message=job.get("progress_message", "Processing..."),
        )

        # Include insights (but not transcript/metrics) if completed
        if job["status"] == "COMPLETED":
            extraction = await asyncio.to_thread(get_extraction_by_submission_id, submission_uuid)

            if extraction:
                response.extraction_id = extraction.get("id")
                response.insights = extraction.get("insights")
                response.is_merged = extraction.get("is_merged") or False

        return response

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission_id format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EHR] Status check failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get status")


# ============================================================================
# Aosta Status Endpoint (Extended with recording_metadata)
# ============================================================================

@router.get("/iframe/status/{submission_id}", response_model=AostaStatusResponse)
async def get_aosta_processing_status(
    request: Request,
    submission_id: str,
    _auth=Depends(verify_submission_access)
):
    """
    Get processing status for Aosta EHR integration.

    Extended version of /ehr/status that includes:
    - recording_metadata: Additional metadata passed during /start API
      (student info, counsellor info, ip_id, op_id, custom fields)

    Returns sanitized status excluding:
    - Full transcript
    - Processing time metrics (stitching_time, transcription_time, etc.)
    - Model information
    """
    from services.supabase_service import get_job_by_submission_id, get_extraction_by_submission_id

    try:
        submission_uuid = uuid.UUID(submission_id)

        job = get_job_by_submission_id(submission_uuid)
        if not job:
            raise HTTPException(status_code=404, detail="Processing job not found")

        response = AostaStatusResponse(
            submission_id=submission_id,
            status=job["status"],
            progress=job["progress_percentage"],
            message=job.get("progress_message", "Processing..."),
        )

        # Include insights and recording_metadata if completed
        if job["status"] == "COMPLETED":
            extraction = await asyncio.to_thread(get_extraction_by_submission_id, submission_uuid)

            if extraction:
                response.extraction_id = extraction.get("id")
                response.insights = extraction.get("insights")
                response.recording_metadata = extraction.get("recording_metadata_json")
                response.is_merged = extraction.get("is_merged") or False

        return response

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission_id format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AOSTA] Status check failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get status")


# ============================================================================
# Generic EHR Edit Endpoint (Edit + Sync via counsellor's ehr_type_id)
# ============================================================================

@router.put("/iframe/edit/{submission_id}", response_model=EHREditResponse)
async def ehr_edit_extraction(
    request: Request,
    submission_id: str,
    body: EHREditRequest,
    _auth=Depends(verify_submission_access)
):
    """
    Generic EHR edit endpoint — routes to correct EHR based on counsellor's ehr_type_id.

    This endpoint:
    1. Updates extraction in our DB (if edited_data provided)
    2. Gets extraction insights (edited or original)
    3. Re-matches medicines/investigations for enrichment
    4. Builds generic patient_info dict from recording_metadata
    5. Uses schedule_ehr_sync() to auto-route to Aosta/KG/Raster/Neopead

    **Request Body:**
    ```json
    {
        "edited_data": { ... },
        "edited_by": "counsellor-uuid",
        "edited_by_type": "doctor",
        "recording_metadata": {
            "ip_id": "979043",
            "op_id": "0",
            "visit_id": "...",
            "visit_number": "...",
            "consultant_id": 0,
            "modified_user_id": 0,
            "sex": "Male"
        }
    }
    ```

    **Response Pattern:**
    - Returns immediately after DB update succeeds
    - ehr_sync_status="pending" indicates sync is happening in background
    - Check ehr_sync_status for: "pending", "skipped" (no EHR configured)
    """
    from services.supabase_service import (
        supabase,
        get_extraction_by_submission_id,
        update_extraction_edits,
        get_counsellor_school_id_cached
    )
    from services.aosta_service import get_school_code, get_student_external_id
    from services.ehr_routing_service import schedule_ehr_sync

    try:
        submission_uuid = uuid.UUID(submission_id)

        # Step 1: Get extraction
        extraction = await asyncio.to_thread(get_extraction_by_submission_id, submission_uuid)
        if not extraction:
            raise HTTPException(status_code=404, detail="Extraction not found")

        extraction_id = extraction.get("id")
        edit_count = extraction.get("edit_count", 0)
        counsellor_id = extraction.get("counsellor_id")
        patient_uuid = extraction.get("student_id")

        # Step 2: Get template_code via recording_sessions FK
        template_code = None
        try:
            tc_result = supabase.table("extractions")\
                .select("recording_sessions(template_code)")\
                .eq("id", extraction_id)\
                .limit(1)\
                .execute()
            if tc_result.data:
                session_info = tc_result.data[0].get("recording_sessions") or {}
                template_code = session_info.get("template_code")
        except Exception as e:
            logger.warning(f"[EHR_EDIT] Failed to fetch template_code: {e}")

        # Step 3: Save edits to DB
        merged_edited_json: Optional[Dict[str, Any]] = None
        if body.edited_data:
            # Normalize iframe-shaped prescription edits back to the AI's
            # original schema (KG Cardio: dose / intake / duration / etc.) so
            # edited_extraction_json stays comparable to original_extraction_json.
            # Templates that natively use M-N-E-N quantities are unaffected —
            # the normalizer auto-detects per record.
            from services.iframe_edit_normalizer import normalize_iframe_edit_payload
            original_extraction = extraction.get("original_extraction_json") or {}
            edited_payload = normalize_iframe_edit_payload(body.edited_data, original_extraction)

            try:
                edited_by_uuid = uuid.UUID(body.edited_by)
                updated = await asyncio.to_thread(
                    update_extraction_edits,
                    uuid.UUID(extraction_id),
                    edited_payload,
                    edited_by_uuid,
                    body.edited_by_type
                )
                edit_count = updated.get("edit_count", edit_count + 1)
                # Capture the merged edited json (top-level merge with previous
                # edited/original) so downstream enrichment + EHR formatting
                # operate on a complete extraction, not the partial payload.
                merged_edited_json = updated.get("edited_extraction_json")
                logger.info(f"[EHR_EDIT] Saved edits to extraction {extraction_id}, edit_count: {edit_count}")
            except Exception as e:
                logger.error(f"[EHR_EDIT] Failed to save edits: {e}")
                raise HTTPException(status_code=500, detail="Failed to save edits")

            # Fire-and-forget: compute accuracy metrics. Mirrors the path in
            # routers/extractions.py so EHR-iframe edits also populate the
            # extraction_accuracy_metrics table (WER + entity errors).
            if original_extraction and counsellor_id:
                try:
                    from services.accuracy_metrics_service import compute_and_save_accuracy_metrics
                    asyncio.create_task(compute_and_save_accuracy_metrics(
                        extraction_id=uuid.UUID(extraction_id),
                        original_json=original_extraction,
                        edited_json=edited_payload,
                        counsellor_id=counsellor_id,
                    ))
                except Exception as e:
                    logger.warning(f"[EHR_EDIT] Failed to schedule accuracy metrics: {e}")

        # Step 4: Get insights — prefer the merged version (sections from
        # earlier edits / original survive when frontend sends a partial)
        insights = (
            merged_edited_json
            or extraction.get("edited_extraction_json")
            or extraction.get("original_extraction_json")
            or {}
        )

        # Step 5: Re-match medicines/investigations for enrichment
        import copy
        from services.medicine_service import postprocess_prescription_extraction
        from services.investigation_service import postprocess_investigations_extraction

        enriched_data = copy.deepcopy(insights)
        if counsellor_id:
            try:
                enriched_data = await postprocess_prescription_extraction(
                    extraction_data=enriched_data,
                    counsellor_id=uuid.UUID(counsellor_id),
                    extraction_id=uuid.UUID(extraction_id),
                    submission_id=str(extraction_id),
                    log_matches=False
                )
                enriched_data = await postprocess_investigations_extraction(
                    extraction_data=enriched_data,
                    counsellor_id=uuid.UUID(counsellor_id),
                    extraction_id=uuid.UUID(extraction_id),
                    submission_id=str(extraction_id),
                    log_matches=False
                )
                logger.info(f"[EHR_EDIT] Re-matched medicines/investigations for {extraction_id}")

                # Persist enriched data back to edited_extraction_json
                try:
                    supabase.table("extractions")\
                        .update({"edited_extraction_json": enriched_data})\
                        .eq("id", extraction_id)\
                        .execute()
                except Exception as persist_err:
                    logger.warning(f"[EHR_EDIT] Failed to persist enriched data: {persist_err}")
            except Exception as e:
                logger.warning(f"[EHR_EDIT] Re-match on edit failed, using raw data: {e}")
                enriched_data = copy.deepcopy(insights)

        # Step 6: Build generic patient_info dict (parallelized lookups)
        async def get_student_id_async():
            if patient_uuid:
                return await asyncio.to_thread(get_student_external_id, patient_uuid)
            return ""

        async def get_school_code_async():
            if counsellor_id:
                school_id = await asyncio.to_thread(get_counsellor_school_id_cached, uuid.UUID(counsellor_id))
                if school_id:
                    return await asyncio.to_thread(get_school_code, str(school_id)) or ""
            return ""

        student_id, school_code = await asyncio.gather(
            get_student_id_async(),
            get_school_code_async()
        )

        recording_metadata = body.recording_metadata or extraction.get("recording_metadata_json") or {}

        # Build patient_info with common fields + all recording_metadata fields.
        # Each EHR routing function picks only the fields it needs:
        #   Aosta: student_id, counsellor_id, school_code, ip_id, op_id
        #   KG:    patient_uuid, counsellor_id, student_id (uhid), visit_id
        #   Raster: student_id (uhid), visit_number, consultant_id, modified_user_id, sex
        patient_info = {
            "student_id": student_id,           # UHID (all EHRs)
            "patient_uuid": patient_uuid,       # KG needs internal UUID
            "counsellor_id": counsellor_id or "",
            "school_code": school_code,
        }

        # Pass through all EHR-specific fields from recording_metadata
        # (iframe sends the relevant fields for its EHR type)
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

        # Step 7: Use schedule_ehr_sync() — auto-routes to correct EHR
        ehr_sync_status = "skipped"
        try:
            ehr_sync_scheduled = schedule_ehr_sync(
                counsellor_id=counsellor_id,
                extraction_data=enriched_data,
                patient_info=patient_info,
                template_code=template_code,
                is_edit=True,
                extraction_id=extraction_id,
            )
            if ehr_sync_scheduled:
                ehr_sync_status = "pending"
                logger.info(f"[EHR_EDIT] EHR sync scheduled for extraction {extraction_id}")
            else:
                logger.info(f"[EHR_EDIT] No EHR config for counsellor {counsellor_id} - sync skipped")
        except Exception as e:
            logger.warning(f"[EHR_EDIT] Could not schedule EHR sync: {e}")

        # Step 8: Publish edit to realtime table (fire-and-forget)
        try:
            from services.realtime_publisher_service import publish_extraction_response_fire_and_forget

            _rt_hospital_id = await asyncio.to_thread(
                get_counsellor_school_id_cached, uuid.UUID(counsellor_id)
            ) if counsellor_id else None
            if _rt_hospital_id:
                _rt_recording_metadata = None
                try:
                    _me_result = supabase.table("extractions").select(
                        "recording_metadata_json"
                    ).eq("id", str(extraction_id)).limit(1).execute()
                    if _me_result.data:
                        _rt_recording_metadata = _me_result.data[0].get("recording_metadata_json") or {}
                except Exception:
                    pass
                asyncio.create_task(publish_extraction_response_fire_and_forget(
                    submission_id=str(extraction_id),
                    school_id=_rt_hospital_id,
                    counsellor_id=counsellor_id,
                    extraction_id=str(extraction_id),
                    insights=enriched_data,
                    recording_metadata=_rt_recording_metadata,
                ))
        except Exception as e:
            logger.warning(f"[EHR_EDIT] Failed to schedule realtime publish for edit: {e}")

        # Step 9: Return response
        message = "Extraction updated"
        if ehr_sync_status == "pending":
            message = "Extraction updated, EHR sync in progress"
        elif ehr_sync_status == "skipped":
            message = "Extraction updated (no EHR configured or sync skipped)"

        return EHREditResponse(
            success=True,
            message=message,
            extraction_id=extraction_id,
            edit_count=edit_count,
            ehr_sync_status=ehr_sync_status,
            ehr_error=None
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EHR_EDIT] Edit failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to update extraction")


# ============================================================================
# Extract Endpoint (Sanitized)
# ============================================================================

@router.post("/extract", response_model=EHRExtractResponse)
async def extract_for_ehr(
    http_request: Request,
    request: Dict[str, Any],
    _auth=Depends(verify_submission_access)
):
    """
    Extract medical summary for EHR clients.

    Returns sanitized response excluding:
    - segment_count
    - processing_mode
    - audio_quality details
    - model information

    Request body should match the standard /extract endpoint.
    """
    from routers.summary import extract_medical_summary, ExtractionRequest

    try:
        # Convert dict to ExtractionRequest
        extraction_request = ExtractionRequest(**request)

        # Call the original extract function
        result = await extract_medical_summary(http_request, extraction_request, None)

        if not result.get("success"):
            raise HTTPException(status_code=500, detail="Extraction failed")

        # Sanitize metadata
        original_metadata = result.get("metadata", {})
        sanitized_metadata = EHRExtractionMetadata(
            correlation_id=original_metadata.get("correlation_id"),
            submission_id=original_metadata.get("submission_id"),
            extraction_id=original_metadata.get("extraction_id"),
            counsellor_id=original_metadata.get("counsellor_id"),
            student_id=original_metadata.get("student_id"),
            template_code=original_metadata.get("template_code"),
            timestamp=original_metadata.get("timestamp"),
        )

        return EHRExtractResponse(
            success=True,
            insights=result.get("insights", {}),
            metadata=sanitized_metadata
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EHR] Extraction failed: {e}")
        from services.error_utils import sanitize_error_message
        raise HTTPException(status_code=500, detail=f"Extraction failed: {sanitize_error_message(str(e))}")


# ============================================================================
# Merge Endpoints (Sanitized)
# ============================================================================

@router.get("/merge/status/{extraction_id}", response_model=EHRMergeStatusResponse)
async def get_ehr_merge_status(
    request: Request,
    extraction_id: str,
    counsellor_id: str = Query(..., description="Counsellor ID for access verification"),
    _auth=Depends(verify_counsellor_access)
):
    """
    Get merge status for EHR clients.

    Returns sanitized response excluding:
    - conflict_count and conflicts_resolved details
    - merge_timestamp
    - Internal processing metadata
    """
    from routers.merge import get_merge_status

    try:
        # Call original endpoint
        result = await get_merge_status(request, extraction_id, counsellor_id, None)

        # Sanitize merge_metadata
        original_metadata = result.merge_metadata
        sanitized_metadata = None
        if original_metadata:
            sanitized_metadata = EHRMergeMetadata(
                source_count=original_metadata.get("source_count", 0),
                target_template_code=original_metadata.get("target_template_code", ""),
                cross_type_scenario=original_metadata.get("cross_type_scenario"),
                consultation_types_merged=original_metadata.get("consultation_types_merged"),
            )

        return EHRMergeStatusResponse(
            extraction_id=result.extraction_id,
            status=result.status,
            merged_data=result.merged_data,
            merge_metadata=sanitized_metadata
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EHR] Merge status check failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get merge status")


@router.post("/merge/preview", response_model=EHRMergePreviewResponse)
async def preview_merge_for_ehr(
    http_request: Request,
    request: Dict[str, Any],
    _auth=Depends(verify_counsellor_access)
):
    """
    Preview merge for EHR clients.

    Returns sanitized response excluding:
    - conflict_count and conflicts_resolved details
    - merge_timestamp
    """
    from routers.merge import preview_merge, MergeRequest

    try:
        # Convert dict to MergeRequest
        merge_request = MergeRequest(**request)

        # Call original preview function
        result = await preview_merge(http_request, merge_request, None)

        if not result.success:
            raise HTTPException(status_code=500, detail="Merge preview failed")

        # Sanitize merge_metadata
        original_metadata = result.merge_metadata or {}
        sanitized_metadata = EHRMergeMetadata(
            source_count=original_metadata.get("source_count", 0),
            target_template_code=original_metadata.get("target_template_code", ""),
            cross_type_scenario=original_metadata.get("cross_type_scenario"),
            consultation_types_merged=original_metadata.get("consultation_types_merged"),
        )

        return EHRMergePreviewResponse(
            success=True,
            merged_data=result.merged_data or {},
            merge_metadata=sanitized_metadata,
            preview=True
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EHR] Merge preview failed: {e}")
        from services.error_utils import sanitize_error_message
        raise HTTPException(status_code=500, detail=f"Merge preview failed: {sanitize_error_message(str(e))}")


# ============================================================================
# Emotions Endpoints (Sanitized)
# ============================================================================

@router.get("/extractions/{extraction_id}/emotions", response_model=EHREmotionsResponse)
async def get_ehr_emotions(
    request: Request,
    extraction_id: str,
    _auth=Depends(verify_submission_access)
):
    """
    Get emotion analysis for EHR clients.

    Returns sanitized response excluding:
    - emotion_extraction_started/completed flags
    - audio_emotion_extraction_started/completed flags
    - congruence_analysis_started/completed flags
    """
    from routers.extractions import get_extraction_emotions

    try:
        # Call original endpoint
        result = await get_extraction_emotions(request, extraction_id, None)

        # Convert to sanitized response
        sanitized_emotions = []
        for emotion in (result.unified_emotions or []):
            sanitized_emotions.append(EHREmotionSegment(
                segment_code=emotion.segment_code,
                segment_name=emotion.segment_name,
                source=emotion.source,
                segment_value=emotion.segment_value
            ))

        sanitized_congruence = None
        if result.congruence_summary:
            sanitized_congruence = EHRCongruenceSummary(
                overall_congruence=result.congruence_summary.overall_congruence,
                congruence_score=result.congruence_summary.congruence_score,
                has_mismatches=result.congruence_summary.has_mismatches
            )

        return EHREmotionsResponse(
            extraction_id=result.extraction_id,
            unified_emotions=sanitized_emotions,
            congruence_summary=sanitized_congruence
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EHR] Emotions fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get emotions")


@router.get("/extractions/by-submission/{submission_id}/emotions", response_model=EHREmotionsResponse)
async def get_ehr_emotions_by_submission(
    request: Request,
    submission_id: str,
    _auth=Depends(verify_submission_access)
):
    """
    Get emotion analysis by submission_id for EHR clients.

    Returns sanitized response excluding processing flags.
    """
    from routers.extractions import get_emotion_analysis_by_submission

    try:
        # Call original endpoint
        result = await get_emotion_analysis_by_submission(request, submission_id, None)

        # Convert to sanitized response
        sanitized_emotions = []
        for emotion in (result.unified_emotions or []):
            sanitized_emotions.append(EHREmotionSegment(
                segment_code=emotion.segment_code,
                segment_name=emotion.segment_name,
                source=emotion.source,
                segment_value=emotion.segment_value
            ))

        sanitized_congruence = None
        if result.congruence_summary:
            sanitized_congruence = EHRCongruenceSummary(
                overall_congruence=result.congruence_summary.overall_congruence,
                congruence_score=result.congruence_summary.congruence_score,
                has_mismatches=result.congruence_summary.has_mismatches
            )

        return EHREmotionsResponse(
            extraction_id=result.extraction_id,
            unified_emotions=sanitized_emotions,
            congruence_summary=sanitized_congruence
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EHR] Emotions fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get emotions")


# ============================================================================
# Prescreen Endpoint (Sanitized)
# ============================================================================

@router.get("/students/{student_id}/prescreen", response_model=EHRPrescreenResponse)
async def get_ehr_prescreen(
    request: Request,
    student_id: str,
    counsellor_id: str = Query(..., description="Counsellor ID (required)"),
    school_id: Optional[str] = Query(None, description="School ID (optional filter)"),
    _auth=Depends(verify_student_access)
):
    """
    Get assistant assessment / prescreen information for EHR clients.

    Assistant extractions are identified by recording_sessions.assistant_id (primary)
    or template_code containing 'PRESCREEN' (legacy fallback).

    Returns sanitized response excluding:
    - prescreen_metadata (model, segment_count)
    - Internal processing details
    """
    from routers.student_history import get_student_prescreen

    try:
        # Call original endpoint
        result = await get_student_prescreen(request, student_id, counsellor_id, school_id, None)

        # Convert to sanitized response
        return EHRPrescreenResponse(
            patient=EHRStudentInfo(
                id=result.patient.id,
                student_id=result.patient.student_id,
                full_name=result.patient.full_name
            ),
            prescreen_data=result.prescreen_data,
            has_prescreen=result.has_prescreen,
            emotion_pattern_summary=result.emotion_pattern_summary.model_dump() if result.emotion_pattern_summary else None,
            top_interventions=[i.model_dump() for i in result.top_interventions] if result.top_interventions else None,
            warning_factors=result.warning_factors,
            warning_factors_date=result.warning_factors_date,
            past_diagnosis_summary=result.past_diagnosis_summary,
            past_diagnosis_summary_date=result.past_diagnosis_summary_date,
            clinical_timeline=result.clinical_timeline,
            last_prescription=result.last_prescription,
            last_prescription_date=result.last_prescription_date,
            consultation_count=result.consultation_count,
            last_visit_date=result.last_visit_date
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EHR] Prescreen fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get prescreen data")


# ============================================================================
# EHR Payload Preview - View formatted payloads for Raster/Aosta
# ============================================================================

class PayloadPreviewResponse(BaseModel):
    """Response containing formatted EHR payload"""
    success: bool
    payload_type: str  # "raster", "aosta", or "neopaed"
    template_code: str
    payload: Dict[str, Any]
    extraction_id: str


@router.get("/payload-preview/{extraction_id}")
async def get_ehr_payload_preview(
    extraction_id: str,
    payload_type: str = Query(..., description="Type of payload: 'raster', 'aosta', 'neopaed', or 'kg'"),
    _client = Depends(require_admin_webapp_or_ehr)
):
    """
    Get the formatted EHR payload for an extraction.

    This endpoint generates the payload that would be sent to Raster or Aosta APIs,
    allowing preview/debugging of the data format.

    Requires admin, web_app, or ehr authentication.

    Args:
        extraction_id: UUID of the extraction
        payload_type: "raster" for Raster General EMR format, "aosta" for Aosta format

    Returns:
        PayloadPreviewResponse with the formatted payload
    """
    from services.supabase_service import supabase

    try:
        # Fetch extraction with session for template_code
        extraction_result = supabase.table("extractions")\
            .select("*, students(id, student_id, full_name), counsellors(id, full_name, school_id), recording_sessions(template_code)")\
            .eq("id", extraction_id)\
            .single()\
            .execute()

        if not extraction_result.data:
            raise HTTPException(status_code=404, detail="Extraction not found")

        extraction = extraction_result.data

        # Get insights (prefer edited, fallback to original)
        insights = extraction.get("edited_extraction_json") or extraction.get("original_extraction_json") or {}
        # template_code from joined recording_sessions, fallback to recording_metadata
        session_data = extraction.get("recording_sessions") or {}
        template_code = session_data.get("template_code", "") or ""
        recording_metadata = extraction.get("recording_metadata_json") or {}

        # Get student info
        patient = extraction.get("students") or {}
        student_id = patient.get("student_id", "")

        # Get counsellor info
        doctor = extraction.get("counsellors") or {}
        counsellor_id = extraction.get("counsellor_id", "")
        school_id = doctor.get("school_id")

        if payload_type == "raster":
            # Prefer ehr_payload_json (pre-computed), fallback to on-the-fly computation
            ehr_payload = extraction.get("ehr_payload_json")

            if ehr_payload:
                payload = ehr_payload
                response_data = {
                    "success": True,
                    "payload_type": "raster",
                    "template_code": template_code,
                    "payload": payload,
                    "extraction_id": extraction_id
                }
                return response_data
            else:
                # Fallback: compute on-the-fly from raw extraction
                from services.raster_api_service import format_for_raster, format_for_raster_new_op

                uhid = student_id or recording_metadata.get("uhid", "")

                # Fetch student's add_info to get required Raster EMR fields
                student_add_info = {}
                missing_fields = []

                if uhid:
                    # Scope student lookup by school to prevent cross-school collisions
                    counsellor_data = extraction.get("counsellors") or {}
                    _ehr_hospital_id = counsellor_data.get("school_id")
                    student_query = supabase.table("students").select("add_info").eq("student_id", uhid)
                    if _ehr_hospital_id:
                        student_query = student_query.eq("school_id", _ehr_hospital_id)
                    student_result = student_query.execute()
                    if student_result.data:
                        student_add_info = student_result.data[0].get("add_info") or {}

                # Get Raster fields directly from recording_metadata (same pattern as Aosta)
                consultant_id = recording_metadata.get("consultant_id")
                created_user_id = recording_metadata.get("created_user_id") or recording_metadata.get("modified_user_id")
                visit_number = recording_metadata.get("visit_number")
                sex = recording_metadata.get("sex")

                # Track missing fields for warning
                if consultant_id is None:
                    missing_fields.append("consultant_id")
                    consultant_id = 0  # Placeholder for preview
                if created_user_id is None:
                    missing_fields.append("created_user_id")
                    created_user_id = 0  # Placeholder for preview
                if not visit_number:
                    missing_fields.append("visit_number")
                    visit_number = ""  # Placeholder for preview

                # Dispatch to template-specific formatter
                template_upper = (template_code or "").upper()
                if template_upper == "RASTER_NEW_OP":
                    from services.raster_api_service import extract_raster_template_id
                    payload = format_for_raster_new_op(
                        extraction_insights=insights,
                        uhid=uhid,
                        visit_number=visit_number,
                        consultant_id=int(consultant_id),
                        modified_user_id=int(created_user_id),
                        sex=sex,
                        template_id_raster=extract_raster_template_id(recording_metadata),
                    )
                else:
                    payload = format_for_raster(
                        extraction_insights=insights,
                        uhid=uhid,
                        visit_number=visit_number,
                        consultant_id=int(consultant_id),
                        modified_user_id=int(created_user_id),
                        created_user_id=int(created_user_id),
                        sex=sex,
                    )

                # Add warning about missing fields if any
                response_data = {
                    "success": True,
                    "payload_type": "raster",
                    "template_code": template_code,
                    "payload": payload,
                    "extraction_id": extraction_id
                }
                if missing_fields:
                    response_data["warning"] = f"Missing required fields in student add_info: {missing_fields}. EMR post will fail without these values."

                return response_data

        elif payload_type == "aosta":
            # Prefer ehr_payload_json (pre-computed), fallback to on-the-fly computation
            ehr_payload = extraction.get("ehr_payload_json")

            if ehr_payload:
                payload = ehr_payload
            else:
                # Fallback: compute on-the-fly from raw extraction
                from services.aosta_service import format_for_aosta, get_school_code

                school_code = ""
                if school_id:
                    school_code = await asyncio.to_thread(get_school_code, school_id) or ""

                ip_id = recording_metadata.get("ip_id")
                op_id = recording_metadata.get("op_id")

                payload = format_for_aosta(
                    extraction_insights=insights,
                    student_id=student_id,
                    counsellor_id=counsellor_id or "",
                    school_code=school_code,
                    ip_id=ip_id,
                    op_id=op_id
                )

            return PayloadPreviewResponse(
                success=True,
                payload_type="aosta",
                template_code=template_code,
                payload=payload,
                extraction_id=extraction_id
            )

        elif payload_type == "kg":
            # Prefer ehr_payload_json (pre-computed), fallback to on-the-fly computation
            ehr_payload = extraction.get("ehr_payload_json")

            if ehr_payload:
                payload = ehr_payload
            else:
                # Fallback: compute on-the-fly from raw extraction
                from services.kg_service import format_for_kg

                counsellor_name = ""
                if counsellor_id:
                    try:
                        doc_result = supabase.table("counsellors").select("full_name").eq("id", counsellor_id).limit(1).execute()
                        if doc_result.data:
                            counsellor_name = doc_result.data[0].get("full_name", "")
                    except Exception:
                        pass

                patient_uuid = patient.get("id", "")

                # Get visit_id from recording metadata
                recording_metadata = extraction.get("recording_metadata_json") or {}
                visit_id = recording_metadata.get("visit_id", "")

                payload = format_for_kg(
                    extraction_data=insights,
                    student_id=patient_uuid,
                    counsellor_id=counsellor_id or "",
                    extraction_id=extraction_id,
                    counsellor_name=counsellor_name,
                    uhid=student_id,
                    visit_id=visit_id,
                )

            return PayloadPreviewResponse(
                success=True,
                payload_type="kg",
                template_code=template_code,
                payload=payload,
                extraction_id=extraction_id
            )

        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid payload type"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EHR] Payload preview failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate payload preview")


# ============================================================================
# Template Schema Endpoint - Empty Extraction with Full Schema
# ============================================================================

class TemplateSchemaSegment(BaseModel):
    """Segment metadata within a template schema response"""
    segment_code: str
    field_name: str
    schema_type: str
    schema_definition: Dict[str, Any]


class TemplateSchemaResponse(BaseModel):
    """Response containing empty extraction with full template schema"""
    template_code: str
    template_name: str
    formatter_code: Optional[str] = None
    segments: List[TemplateSchemaSegment]
    empty_extraction: Dict[str, Any]
    empty_formatted_payload: Optional[Dict[str, Any]] = None


def _generate_empty_value(schema: Dict[str, Any]) -> Any:
    """Recursively generate empty/default values expanding all sub-elements."""
    schema_type = schema.get("type", "string")
    if schema_type == "object":
        props = schema.get("properties")
        if props:
            return {k: _generate_empty_value(v) for k, v in props.items()}
        return {}
    elif schema_type == "array":
        items = schema.get("items")
        if items and items.get("type") == "object" and items.get("properties"):
            return [_generate_empty_value(items)]
        return []
    elif schema_type == "string":
        return ""
    else:
        return None


@router.get("/template-schema", response_model=TemplateSchemaResponse)
async def get_template_schema(
    request: Request,
    template_code: Optional[str] = Query(None, description="Template code (e.g. OP_GENERAL). If omitted, uses counsellor/assistant default template."),
    counsellor_id: Optional[str] = Query(None, description="Counsellor ID to verify access"),
    assistant_id: Optional[str] = Query(None, description="Assistant ID to verify access"),
    _auth=Depends(require_admin_webapp_or_ehr)
):
    """
    Get empty extraction with full schema for a template.

    Returns the template's segment structure with empty/default values,
    after verifying the counsellor or assistant has access to the template.

    - Requires exactly one of counsellor_id or assistant_id.
    - If template_code is omitted, resolves the default template for the counsellor/assistant.
    - Auth: admin, web_app, or ehr.
    """
    import re
    from services.supabase_service import supabase, get_template_by_code

    # Validate: exactly one of counsellor_id or assistant_id
    if not counsellor_id and not assistant_id:
        raise HTTPException(status_code=400, detail="Either counsellor_id or assistant_id is required")
    if counsellor_id and assistant_id:
        raise HTTPException(status_code=400, detail="Provide only one of counsellor_id or assistant_id, not both")

    # Validate UUID early
    if counsellor_id:
        try:
            counsellor_uuid = uuid.UUID(counsellor_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid counsellor_id format")
    else:
        try:
            assistant_uuid = uuid.UUID(assistant_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid assistant_id format")

    try:
        # Step 1: Resolve template_code if not provided (use default template)
        if not template_code:
            if counsellor_id:
                from services.counsellor_templates_service import get_counsellor_default_template
                default = get_counsellor_default_template(counsellor_uuid)
            else:
                from services.assistant_templates_service import get_assistant_default_template
                default = get_assistant_default_template(assistant_uuid)

            if not default:
                entity = "doctor" if counsellor_id else "nurse"
                raise HTTPException(status_code=404, detail=f"No default template found for this {entity}")
            template_code = default["template_code"]

        # Step 2: Lookup full template record
        template = get_template_by_code(template_code)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{template_code}' not found")

        template_id = template["id"]
        template_name = template.get("template_name", template_code)
        consultation_type_code = template.get("consultation_type_code")

        # Step 3: Verify access (skip if template was resolved from their own default)
        if counsellor_id:
            # Check: counsellor owns template, has it shared, or it's a common template
            template_owner = template.get("counsellor_id")
            if template_owner is None:
                pass  # Common template — accessible to all
            elif str(template_owner) == counsellor_id:
                pass  # Counsellor owns this template
            else:
                access_check = supabase.table("counsellor_templates")\
                    .select("id, is_active")\
                    .eq("counsellor_id", counsellor_id)\
                    .eq("template_id", str(template_id))\
                    .limit(1)\
                    .execute()

                if not access_check.data or not access_check.data[0].get("is_active", False):
                    raise HTTPException(status_code=403, detail="Counsellor does not have access to this template")
        else:
            from services.assistant_templates_service import validate_assistant_template_access
            if not validate_assistant_template_access(assistant_id, str(template_id)):
                raise HTTPException(status_code=403, detail="Assistant does not have access to this template")

        # Step 3: Get assembled_schema_json
        assembled_schema = template.get("assembled_schema_json")
        if not assembled_schema:
            raise HTTPException(
                status_code=400,
                detail=f"Template '{template_code}' has no assembled schema. Please reassemble the template first."
            )

        if isinstance(assembled_schema, str):
            import json
            assembled_schema = json.loads(assembled_schema)

        # Step 4: Load segment metadata from template_segments + segment_definitions
        # include_in_empty_payload is admin-controlled trimming for this endpoint
        # (NULL = legacy include, FALSE = skip, TRUE = explicit include).
        segments_result = supabase.table("template_segments").select(
            "category, display_order, include_in_empty_payload, "
            "segment_definitions!inner(segment_code, segment_name, schema_definition_json)"
        ).eq("template_id", str(template_id)).execute()

        # Helper: snake_case to camelCase (same logic as template_assembly_service)
        def to_camel_case(snake_str: str) -> str:
            components = re.split(r'[_\s]+', snake_str.lower())
            components = [c for c in components if c]
            if not components:
                return snake_str.lower()
            return components[0] + ''.join(x.title() for x in components[1:])

        # Build segment metadata list
        segment_list = []
        trimmed_field_names = set()
        if segments_result.data:
            raw_segments = []
            for row in segments_result.data:
                seg_def = row.get("segment_definitions", {})
                category = row.get("category", "additional")
                if category == "excluded":
                    continue
                # Admin opt-in trimming: FALSE omits segment from payload.
                # NULL / TRUE keep the legacy "include" behavior.
                if row.get("include_in_empty_payload") is False:
                    seg_code = seg_def.get("segment_code", "") or ""
                    components = [c for c in re.split(r"[_\s]+", seg_code.lower()) if c]
                    if components:
                        trimmed_field_names.add(components[0] + "".join(x.title() for x in components[1:]))
                    continue
                raw_segments.append({
                    "segment_code": seg_def.get("segment_code", ""),
                    "segment_name": seg_def.get("segment_name", ""),
                    "category": category,
                    "display_order": row.get("display_order", 999),
                    "schema_definition_json": seg_def.get("schema_definition_json", {}),
                })

            raw_segments.sort(key=lambda s: s["display_order"])

            for seg in raw_segments:
                field_name = to_camel_case(seg["segment_code"])
                schema_def = seg["schema_definition_json"]
                if isinstance(schema_def, str):
                    import json
                    schema_def = json.loads(schema_def)

                segment_list.append(TemplateSchemaSegment(
                    segment_code=seg["segment_code"],
                    field_name=field_name,
                    schema_type=schema_def.get("type", "string"),
                    schema_definition=schema_def,
                ))

        # Step 5: Build empty extraction from assembled schema properties
        # Only include segments that survived the admin trim in segment_list;
        # segments flagged include_in_empty_payload=FALSE are omitted from both
        # segment_list and empty_extraction.
        properties = assembled_schema.get("properties", {})
        empty_extraction = {}
        included_fields = {seg.field_name for seg in segment_list}

        for seg in segment_list:
            field_name = seg.field_name
            if field_name in properties:
                empty_extraction[field_name] = _generate_empty_value(properties[field_name])

        # Include any remaining top-level properties not defined via segments
        # (edge case — schema-level keys without a template_segments row). Skip
        # admin-trimmed keys so include_in_empty_payload=FALSE actually drops them.
        for field_name, field_schema in properties.items():
            if field_name in included_fields or field_name in trimmed_field_names:
                continue
            empty_extraction[field_name] = _generate_empty_value(field_schema)

        # Step 6: If template has a formatter, generate the empty formatted payload
        formatter_code = template.get("formatter_code")
        empty_formatted_payload = None
        if formatter_code:
            from services.formatter_registry import generate_empty_formatted_payload
            empty_formatted_payload = generate_empty_formatted_payload(
                formatter_code=formatter_code,
                empty_extraction=empty_extraction,
                template_code=template_code,
            )

        return TemplateSchemaResponse(
            template_code=template_code,
            template_name=template_name,
            formatter_code=formatter_code,
            segments=segment_list,
            empty_extraction=empty_extraction,
            empty_formatted_payload=empty_formatted_payload,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid UUID format: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EHR] Template schema fetch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get template schema")


# ============================================================================
# Extraction Gaps Endpoint - Missing field analysis for critical segments
# ============================================================================

# Comorbidity keys that have a "since" field alongside "status"
_COMORBIDITY_WITH_SINCE = {"dm", "ht", "dlp", "history_of_copd"}

_COMORBIDITY_KEYS = [
    "dm", "ht", "dlp", "history_of_copd", "previous_mi", "previous_stent",
    "renal_failure", "history_of_cva", "peripheral_vascular_disease",
    "smoking", "tobacco_chewing", "alcohol_intake",
]

_VITALS_FIELDS = ["temperature", "pulse", "respiratory_rate", "blood_pressure", "spo2"]
_NUTRITIONAL_FIELDS = ["height", "weight", "bmi", "bmi_flag"]
_ALLERGY_FIELDS = ["has_allergy", "details"]


def _is_empty(value: Any) -> bool:
    """Check if a value is empty/missing (empty string, None, or absent)."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _check_flat_segment(data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    """Analyse a flat segment (vitals, nutritional, allergy) for missing fields."""
    missing = [f for f in fields if _is_empty(data.get(f))]
    captured = [f for f in fields if not _is_empty(data.get(f))]
    return {
        "total_fields": len(fields),
        "missing_count": len(missing),
        "missing_fields": missing,
        "captured_fields": captured,
    }


def _check_comorbidities(data: Dict[str, Any]) -> Dict[str, Any]:
    """Analyse comorbidities segment — status empty = missing, Yes+empty since = partial."""
    missing = []
    captured = []
    partial = []

    for key in _COMORBIDITY_KEYS:
        entry = data.get(key, {}) or {}
        status = entry.get("status", "")
        if _is_empty(status):
            missing.append(key)
        else:
            captured.append(key)
            if key in _COMORBIDITY_WITH_SINCE and status == "Yes" and _is_empty(entry.get("since")):
                partial.append(key)

    return {
        "total_fields": len(_COMORBIDITY_KEYS),
        "missing_count": len(missing),
        "missing_fields": missing,
        "captured_fields": captured,
        "partial_fields": partial,
    }


class ExtractionGapSegment(BaseModel):
    total_fields: int
    missing_count: int
    missing_fields: List[str]
    captured_fields: List[str]
    partial_fields: Optional[List[str]] = None


class ExtractionGapsSummary(BaseModel):
    total_fields: int
    total_missing: int
    completeness_percentage: int


class ExtractionGapsResponse(BaseModel):
    extraction_id: str
    template_code: Optional[str] = None
    gaps: Dict[str, ExtractionGapSegment]
    summary: ExtractionGapsSummary


@router.get("/extraction-gaps/{extraction_id}", response_model=ExtractionGapsResponse)
async def get_extraction_gaps(
    request: Request,
    extraction_id: str,
    _client=Depends(require_admin_webapp_or_ehr)
):
    """
    Analyse which fields in Vitals, Comorbidities, Allergy, and Nutritional
    Screening are missing from a completed extraction — so the counsellor/assistant
    knows exactly what to ask during consultation.

    Auth: admin, web_app, or ehr.
    """
    from services.gap_analysis_service import compute_extraction_gaps

    try:
        uuid.UUID(extraction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction_id format")

    try:
        gaps, summary_dict, template_code = compute_extraction_gaps(extraction_id)

        return ExtractionGapsResponse(
            extraction_id=extraction_id,
            template_code=template_code,
            gaps=gaps,
            summary=ExtractionGapsSummary(**summary_dict),
        )

    except LookupError:
        raise HTTPException(status_code=404, detail="Extraction not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EHR] Extraction gaps analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to analyse extraction gaps")

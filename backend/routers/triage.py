"""
Clinical Triage Suggestions API Router

Provides endpoints for generating clinical triage suggestions:
- Generate suggestions from extraction ID
- Generate suggestions from raw extraction JSON
- Get available differential trees
- Get supported presentations by specialty

MVP Phase: Uses hardcoded differential trees + Gemini 2.0 Flash
Phase 3: Will integrate RAG for evidence-based recommendations
"""

import os
import uuid
import logging
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime

from services.supabase_service import supabase

# Conditional EHR auth imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import (
        EHRExtractionAccessChecker,
        EHRCounsellorAccessChecker,
        get_current_client,
        validate_ehr_extraction_access,
        validate_ehr_counsellor_access,
        require_admin,
    )

    _extraction_checker = EHRExtractionAccessChecker()
    _doctor_checker = EHRCounsellorAccessChecker()

    async def verify_extraction_access(request: Request, extraction_id: str = None):  # type: ignore[misc]
        """Verify EHR client has access to extraction data."""
        extraction_uuid = uuid.UUID(extraction_id) if extraction_id else None
        client = get_current_client(request)
        return await _extraction_checker(request, extraction_uuid, client)

    async def verify_counsellor_access(request: Request, counsellor_id: str = None):  # type: ignore[misc]
        """Verify EHR client has access to counsellor data."""
        counsellor_uuid = uuid.UUID(counsellor_id) if counsellor_id else None
        client = get_current_client(request)
        return await _doctor_checker(request, counsellor_uuid, client)

    async def validate_extraction_from_body(http_request: Request, extraction_id: str):  # type: ignore[misc]
        """
        Validate extraction_id access after body is parsed.
        Use for endpoints where extraction_id is in request body.
        Raises HTTPException 403 if access denied.
        """
        client = get_current_client(http_request)
        if client.client_type == "ehr":
            extraction_uuid = uuid.UUID(extraction_id)
            if not await validate_ehr_extraction_access(client, extraction_uuid):
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )

    async def validate_counsellor_from_body(http_request: Request, counsellor_id: str):  # type: ignore[misc]
        """
        Validate counsellor_id access after body is parsed.
        Raises HTTPException 403 if access denied.
        """
        client = get_current_client(http_request)
        if client.client_type == "ehr":
            counsellor_uuid = uuid.UUID(counsellor_id)
            if not await validate_ehr_counsellor_access(client, counsellor_uuid):
                raise HTTPException(
                    status_code=403,
                    detail="Access denied"
                )

    def require_admin_or_webapp(client = Depends(get_current_client)):
        """Allow admin or web_app clients for guideline management."""
        if client.client_type in ("admin", "web_app"):
            return client
        # Check for admin scopes
        admin_scopes = [s for s in client.scopes if s.startswith("admin:")]
        if admin_scopes:
            return client
        raise HTTPException(
            status_code=403,
            detail="Admin or web app access required for guideline management",
        )

else:
    # No-op functions when auth disabled
    async def require_admin():  # type: ignore[misc]
        return None

    async def require_admin_or_webapp():  # type: ignore[misc]
        return None

    async def verify_extraction_access(request: Request = None, extraction_id: str = None):  # type: ignore[misc]
        return None

    async def verify_counsellor_access(request: Request = None, counsellor_id: str = None):  # type: ignore[misc]
        return None

    async def validate_extraction_from_body(http_request: Request = None, extraction_id: str = None):  # type: ignore[misc]
        pass  # No-op when auth disabled

    async def validate_counsellor_from_body(http_request: Request = None, counsellor_id: str = None):  # type: ignore[misc]
        pass  # No-op when auth disabled

from services.triage import (
    StructuredInsightsMapper,
    TriageSuggestionEngine,
    generate_triage_from_extraction_v2,
    DIFFERENTIAL_TREES,
    get_differential,
    get_all_presentations,
    CONSULTATION_TYPE_TO_SPECIALTY,
    # Multi-layer orchestrator (Phase 4)
    get_triage_orchestrator,
    LayerConfig,
    # Enhanced RAG v2: Structured Clinical Conditions
    get_clinical_condition_ingestion_service,
    validate_guideline_json,
    get_validation_errors,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/triage",
    tags=["triage"]
)


# ============================================================================
# Request/Response Models
# ============================================================================

class TriageRequest(BaseModel):
    """Request model for generating triage suggestions from extraction ID"""
    extraction_id: str = Field(..., description="UUID of the extraction")
    include_gemini: bool = Field(True, description="Whether to use Gemini AI for gap analysis")
    # Optional student context parameters (Phase 0.5 enhancement)
    student_id: Optional[str] = Field(None, description="UUID of the student for historical context (auto-detected if not provided)")
    counsellor_id: Optional[str] = Field(None, description="UUID of the counsellor for suggestion logging")
    log_suggestions: bool = Field(True, description="Whether to log suggestions to database for learning")
    force_regenerate: bool = Field(False, description="Force regenerate suggestions even if they exist in DB")


class TriageFromJsonRequest(BaseModel):
    """Request model for generating triage from raw extraction JSON"""
    extraction_json: Dict[str, Any] = Field(..., description="Raw extraction JSON data")
    consultation_type_code: str = Field(..., description="Consultation type code (e.g., OP, OP_SHORT)")
    include_gemini: bool = Field(True, description="Whether to use Gemini AI for gap analysis")


class FeedbackRequest(BaseModel):
    """Request model for submitting feedback on a triage suggestion"""
    suggestion_id: str = Field(..., description="UUID of the suggestion from triage_suggestion_log")
    counsellor_id: str = Field(..., description="UUID of the counsellor providing feedback")
    feedback_type: str = Field(..., description="Type of feedback: 'accepted', 'rejected', 'maybe', or 'modified'")
    rejection_reason: Optional[str] = Field(None, description="Reason for rejection if feedback_type is 'rejected'")
    modified_text: Optional[str] = Field(None, description="Modified suggestion text if feedback_type is 'modified'")


class FeedbackResponse(BaseModel):
    """Response model for feedback submission"""
    success: bool
    feedback_id: str
    message: str


class TriageSuggestionResponse(BaseModel):
    """Single triage suggestion"""
    id: Optional[str] = None  # Suggestion ID from triage_suggestion_log (for feedback)
    category: str
    suggestion: str
    priority: str
    rationale: str
    source: str
    related_presentation: Optional[str] = None


class TriageResponse(BaseModel):
    """Response model for triage suggestions"""
    success: bool
    extraction_id: Optional[str] = None
    specialty: str
    consultation_type: str
    message: Optional[str] = None  # Optional message (e.g., when triage is disabled)

    # Priority-organized suggestions
    critical_actions: List[TriageSuggestionResponse]
    important_considerations: List[TriageSuggestionResponse]
    nice_to_have: List[TriageSuggestionResponse]

    # Analysis details
    matched_presentations: List[str]
    identified_red_flags: List[str]
    gap_analysis: Dict[str, Any]

    # Metadata
    total_suggestions: int
    generated_at: str
    processing_time_ms: int


class DifferentialTreeResponse(BaseModel):
    """Response model for differential tree data"""
    specialty: str
    presentation: str
    must_rule_out: Optional[List[Dict[str, Any]]] = None
    must_assess: Optional[List[Dict[str, Any]]] = None
    high_probability: Optional[List[Dict[str, Any]]] = None
    red_flags: List[str]
    first_line_investigations: List[Dict[str, Any]]
    history_essentials: Optional[List[str]] = None
    source: Optional[str] = None


class SpecialtyInfo(BaseModel):
    """Information about a specialty"""
    specialty: str
    presentations: List[str]
    consultation_types: List[str]


# ============================================================================
# Triage Generation Endpoints
# ============================================================================

@router.post("/generate", response_model=TriageResponse)
async def generate_triage_suggestions(http_request: Request, request: TriageRequest):
    """
    Generate or retrieve clinical triage suggestions for an extraction.

    First checks if suggestions already exist in the database. If they do,
    returns the persisted suggestions. If not (or if force_regenerate=True),
    generates new suggestions.

    Analyzes the extraction data and returns:
    - Critical actions (red flags, immediate concerns)
    - Important considerations (missing investigations, history gaps)
    - Nice-to-have suggestions (additional workup)

    Enhanced features (Phase 0.5):
    - Student historical context (allergies, chronic conditions, emotions, compliance)
    - Allergy-based suggestion filtering (vetoes contraindicated suggestions)
    - Psychosocial recommendations based on student history
    - Optional suggestion logging for learning counsellor patterns

    Uses matched differential diagnosis trees and optional Gemini AI analysis.

    **Authentication:** Requires Bearer token (API key or JWT).
    """
    import time
    start_time = time.time()

    try:
        # Validate extraction access for EHR clients
        await validate_extraction_from_body(http_request, request.extraction_id)
        # Check if triage analysis is enabled for this consultation type
        ext_check = supabase.table("extractions").select(
            "consultation_type_id, consultation_types!inner(type_code, enable_triage_analysis)"
        ).eq("id", request.extraction_id).single().execute()

        if not ext_check.data:
            raise HTTPException(status_code=404, detail="Extraction not found")

        consultation_type = ext_check.data.get("consultation_types", {})
        enable_triage = consultation_type.get("enable_triage_analysis", True)  # Default True for backward compat

        if not enable_triage:
            type_code = consultation_type.get("type_code", "Unknown")
            logger.info(f"[TRIAGE_API] Triage analysis disabled for consultation type {type_code}")
            processing_time = int((time.time() - start_time) * 1000)
            return TriageResponse(
                success=True,
                extraction_id=request.extraction_id,
                specialty="none",
                consultation_type=type_code,
                message=f"Triage analysis is not enabled for consultation type '{type_code}'.",
                critical_actions=[],
                important_considerations=[],
                nice_to_have=[],
                matched_presentations=[],
                identified_red_flags=[],
                gap_analysis={},
                total_suggestions=0,
                generated_at=datetime.utcnow().isoformat(),
                processing_time_ms=processing_time,
            )

        # Check if suggestions already exist in DB (unless force_regenerate)
        if not request.force_regenerate:
            existing = supabase.table("triage_suggestion_log").select(
                "id, suggestion_category, suggestion_type, suggestion_text, source_layer, confidence_score, priority_rank, rationale, created_at"
            ).eq("extraction_id", request.extraction_id).order("priority_rank").execute()

            if existing.data and len(existing.data) > 0:
                logger.info(f"[TRIAGE_API] Found {len(existing.data)} existing suggestions for extraction {request.extraction_id}")

                # Get extraction metadata for response
                ext_result = supabase.table("extractions").select(
                    "consultation_types!inner(type_code, type_name)"
                ).eq("id", request.extraction_id).single().execute()

                consultation_type_code = ext_result.data.get("consultation_types", {}).get("type_code", "OP") if ext_result.data else "OP"
                specialty = CONSULTATION_TYPE_TO_SPECIALTY.get(consultation_type_code, "general_medicine")

                # Convert stored suggestions to response format
                critical_actions = []
                important_considerations = []
                nice_to_have = []

                for s in existing.data:
                    suggestion_resp = TriageSuggestionResponse(
                        id=s.get("id"),  # Include ID for feedback
                        category=s.get("suggestion_type", "investigation"),
                        suggestion=s.get("suggestion_text", ""),
                        priority=s.get("suggestion_category", "consider"),
                        rationale=s.get("rationale", ""),  # Load rationale from DB
                        source=s.get("source_layer", "differential_tree"),
                        related_presentation=None,
                    )

                    cat = s.get("suggestion_category", "")
                    if cat == "critical_action":
                        critical_actions.append(suggestion_resp)
                    elif cat == "important_consideration":
                        important_considerations.append(suggestion_resp)
                    else:
                        nice_to_have.append(suggestion_resp)

                processing_time = int((time.time() - start_time) * 1000)

                return TriageResponse(
                    success=True,
                    extraction_id=request.extraction_id,
                    specialty=specialty,
                    consultation_type=consultation_type_code,
                    critical_actions=critical_actions,
                    important_considerations=important_considerations,
                    nice_to_have=nice_to_have,
                    matched_presentations=[],
                    identified_red_flags=[],
                    gap_analysis={},
                    total_suggestions=len(existing.data),
                    generated_at=existing.data[0].get("created_at", datetime.utcnow().isoformat()),
                    processing_time_ms=processing_time,
                )

        # No existing suggestions or force_regenerate - generate new ones
        # Fetch extraction from database with student context
        # Use left join for recording_sessions (may not exist for direct extractions)
        result = supabase.table("extractions").select(
            """
            *,
            consultation_types!inner(type_code, type_name),
            recording_sessions(student_id)
            """
        ).eq("id", request.extraction_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Extraction not found")

        extraction = result.data
        consultation_type_code = extraction.get("consultation_types", {}).get("type_code", "OP")

        # Get student_id from request or auto-detect from extraction
        student_id = request.student_id
        if not student_id:
            recording_session = extraction.get("recording_sessions") or {}
            student_id = recording_session.get("student_id")

        logger.info(f"[TRIAGE_API] Generating NEW suggestions for extraction {request.extraction_id}, "
                   f"student: {student_id}, counsellor: {request.counsellor_id}, type: {consultation_type_code}")

        # Generate triage suggestions with student context
        suggestions = await generate_triage_from_extraction_v2(
            extraction=extraction,
            student_id=student_id,
            counsellor_id=request.counsellor_id,
            consultation_type_code=consultation_type_code,
            include_gemini=request.include_gemini,
            log_suggestions=request.log_suggestions,
            supabase_client=supabase
        )

        # Build response (include IDs for feedback)
        return TriageResponse(
            success=True,
            extraction_id=request.extraction_id,
            specialty=suggestions.specialty,
            consultation_type=suggestions.consultation_type,
            critical_actions=[
                TriageSuggestionResponse(
                    id=s.id,  # Include ID for feedback
                    category=s.category,
                    suggestion=s.suggestion,
                    priority=s.priority,
                    rationale=s.rationale,
                    source=s.source,
                    related_presentation=s.related_presentation,
                )
                for s in suggestions.critical_actions
            ],
            important_considerations=[
                TriageSuggestionResponse(
                    id=s.id,  # Include ID for feedback
                    category=s.category,
                    suggestion=s.suggestion,
                    priority=s.priority,
                    rationale=s.rationale,
                    source=s.source,
                    related_presentation=s.related_presentation,
                )
                for s in suggestions.important_considerations
            ],
            nice_to_have=[
                TriageSuggestionResponse(
                    id=s.id,  # Include ID for feedback
                    category=s.category,
                    suggestion=s.suggestion,
                    priority=s.priority,
                    rationale=s.rationale,
                    source=s.source,
                    related_presentation=s.related_presentation,
                )
                for s in suggestions.nice_to_have
            ],
            matched_presentations=suggestions.matched_presentations,
            identified_red_flags=suggestions.identified_red_flags,
            gap_analysis=suggestions.gap_analysis,
            total_suggestions=suggestions.total_suggestions,
            generated_at=suggestions.generated_at,
            processing_time_ms=suggestions.processing_time_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TRIAGE_API] Error generating triage: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate triage suggestions")


@router.post("/generate-from-json", response_model=TriageResponse)
async def generate_triage_from_json(request: TriageFromJsonRequest):
    """
    Generate clinical triage suggestions from raw extraction JSON.

    Use this endpoint when you have extraction data but it's not saved to the database.
    """
    try:
        # Check if triage analysis is enabled for this consultation type
        ct_check = supabase.table("consultation_types").select(
            "type_code, enable_triage_analysis"
        ).eq("type_code", request.consultation_type_code).single().execute()

        if ct_check.data:
            enable_triage = ct_check.data.get("enable_triage_analysis", True)
            if not enable_triage:
                logger.info(f"[TRIAGE_API] Triage analysis disabled for consultation type {request.consultation_type_code}")
                return TriageResponse(
                    success=True,
                    extraction_id=None,
                    specialty="none",
                    consultation_type=request.consultation_type_code,
                    message=f"Triage analysis is not enabled for consultation type '{request.consultation_type_code}'.",
                    critical_actions=[],
                    important_considerations=[],
                    nice_to_have=[],
                    matched_presentations=[],
                    identified_red_flags=[],
                    gap_analysis={},
                    total_suggestions=0,
                    generated_at=datetime.utcnow().isoformat(),
                    processing_time_ms=0,
                )

        logger.info(f"[TRIAGE_API] Generating suggestions from JSON, type: {request.consultation_type_code}")

        # Create mapper and map extraction
        mapper = StructuredInsightsMapper()
        insights = mapper.map_extraction_json(
            extraction_json=request.extraction_json,
            consultation_type_code=request.consultation_type_code
        )

        # Generate triage suggestions
        engine = TriageSuggestionEngine()
        suggestions = await engine.generate_suggestions(
            insights=insights,
            include_gemini_analysis=request.include_gemini
        )

        # Build response
        return TriageResponse(
            success=True,
            extraction_id=None,
            specialty=suggestions.specialty,
            consultation_type=suggestions.consultation_type,
            critical_actions=[
                TriageSuggestionResponse(
                    id=getattr(s, 'id', None),  # May not have ID if not logged
                    category=s.category,
                    suggestion=s.suggestion,
                    priority=s.priority,
                    rationale=s.rationale,
                    source=s.source,
                    related_presentation=s.related_presentation,
                )
                for s in suggestions.critical_actions
            ],
            important_considerations=[
                TriageSuggestionResponse(
                    id=getattr(s, 'id', None),  # May not have ID if not logged
                    category=s.category,
                    suggestion=s.suggestion,
                    priority=s.priority,
                    rationale=s.rationale,
                    source=s.source,
                    related_presentation=s.related_presentation,
                )
                for s in suggestions.important_considerations
            ],
            nice_to_have=[
                TriageSuggestionResponse(
                    id=getattr(s, 'id', None),  # May not have ID if not logged
                    category=s.category,
                    suggestion=s.suggestion,
                    priority=s.priority,
                    rationale=s.rationale,
                    source=s.source,
                    related_presentation=s.related_presentation,
                )
                for s in suggestions.nice_to_have
            ],
            matched_presentations=suggestions.matched_presentations,
            identified_red_flags=suggestions.identified_red_flags,
            gap_analysis=suggestions.gap_analysis,
            total_suggestions=suggestions.total_suggestions,
            generated_at=suggestions.generated_at,
            processing_time_ms=suggestions.processing_time_ms,
        )

    except Exception as e:
        logger.error(f"[TRIAGE_API] Error generating triage from JSON: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate triage suggestions")


# ============================================================================
# Feedback Endpoint
# ============================================================================

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_triage_feedback(http_request: Request, request: FeedbackRequest):
    """
    Submit optional feedback on a triage suggestion.

    This endpoint allows counsellors to provide feedback on generated suggestions:
    - 'accepted': Counsellor agrees with the suggestion
    - 'rejected': Counsellor disagrees (optionally with reason)
    - 'modified': Counsellor modified the suggestion (with new text)

    Feedback is used to learn counsellor patterns for future personalization.

    **Authentication:** Requires Bearer token (API key or JWT).
    """
    try:
        # Validate counsellor access for EHR clients
        await validate_counsellor_from_body(http_request, request.counsellor_id)

        # Validate feedback_type
        if request.feedback_type not in ('accepted', 'rejected', 'maybe', 'modified'):
            raise HTTPException(
                status_code=400,
                detail="feedback_type must be 'accepted', 'rejected', 'maybe', or 'modified'"
            )

        # Validate modified_text for 'modified' feedback
        if request.feedback_type == 'modified' and not request.modified_text:
            raise HTTPException(
                status_code=400,
                detail="modified_text is required when feedback_type is 'modified'"
            )

        # Insert feedback
        result = supabase.table("triage_feedback").insert({
            "suggestion_id": request.suggestion_id,
            "counsellor_id": request.counsellor_id,
            "feedback_type": request.feedback_type,
            "rejection_reason": request.rejection_reason,
            "modified_text": request.modified_text,
        }).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to save feedback")

        feedback_id = result.data[0].get("id")

        logger.info(f"[TRIAGE_API] Feedback submitted: {request.feedback_type} for suggestion {request.suggestion_id}")

        return FeedbackResponse(
            success=True,
            feedback_id=feedback_id,
            message=f"Feedback '{request.feedback_type}' recorded successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TRIAGE_API] Error submitting feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit feedback")


@router.get("/feedback/stats/{counsellor_id}")
async def get_counsellor_feedback_stats(
    request: Request,
    counsellor_id: str,
    _auth = Depends(verify_counsellor_access)
):
    """
    Get feedback statistics for a specific counsellor.

    Returns aggregated stats on suggestion acceptance/rejection rates.

    **Authentication:** Requires Bearer token (API key or JWT).
    """
    try:
        # Query triage_counsellor_stats view
        result = supabase.table("triage_counsellor_stats").select("*").eq("counsellor_id", counsellor_id).single().execute()

        if not result.data:
            # Return empty stats if no feedback yet
            return {
                "counsellor_id": counsellor_id,
                "total_suggestions": 0,
                "total_feedback_given": 0,
                "accepted_count": 0,
                "rejected_count": 0,
                "modified_count": 0,
                "acceptance_rate_pct": None,
                "message": "No feedback data available yet"
            }

        return result.data

    except Exception as e:
        logger.error(f"[TRIAGE_API] Error fetching feedback stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch feedback stats")


# ============================================================================
# Differential Trees Reference Endpoints
# ============================================================================

@router.get("/differentials/{specialty}/{presentation}", response_model=DifferentialTreeResponse)
async def get_differential_tree(specialty: str, presentation: str):
    """
    Get differential diagnosis data for a specific specialty and presentation.

    Returns must-rule-out diagnoses, red flags, first-line investigations,
    and essential history questions.
    """
    diff_data = get_differential(specialty, presentation)

    if not diff_data:
        raise HTTPException(
            status_code=404,
            detail="No differential tree found for the requested specialty and presentation"
        )

    return DifferentialTreeResponse(
        specialty=specialty,
        presentation=presentation,
        must_rule_out=diff_data.get("must_rule_out"),
        must_assess=diff_data.get("must_assess"),
        high_probability=diff_data.get("high_probability"),
        red_flags=diff_data.get("red_flags", []),
        first_line_investigations=diff_data.get("first_line_investigations", []),
        history_essentials=diff_data.get("history_essentials"),
        source=diff_data.get("source"),
    )


@router.get("/specialties", response_model=List[SpecialtyInfo])
async def list_specialties():
    """
    List all available specialties with their presentations and consultation types.
    """
    specialties = []

    # Build reverse mapping: specialty -> consultation types
    specialty_to_types: Dict[str, List[str]] = {}
    for ct_code, specialty in CONSULTATION_TYPE_TO_SPECIALTY.items():
        if specialty not in specialty_to_types:
            specialty_to_types[specialty] = []
        specialty_to_types[specialty].append(ct_code)

    # Get presentations for each specialty
    for specialty in DIFFERENTIAL_TREES.keys():
        presentations = get_all_presentations(specialty)
        consultation_types = specialty_to_types.get(specialty, [])

        specialties.append(SpecialtyInfo(
            specialty=specialty,
            presentations=presentations,
            consultation_types=consultation_types,
        ))

    return specialties


@router.get("/presentations/{specialty}", response_model=List[str])
async def list_presentations(specialty: str):
    """
    List all available presentations for a specialty.
    """
    presentations = get_all_presentations(specialty)

    if not presentations:
        raise HTTPException(
            status_code=404,
            detail="No presentations found for the requested specialty"
        )

    return presentations


# ============================================================================
# Multi-Layer Triage (Phase 4)
# ============================================================================

class TriageV2Request(BaseModel):
    """Request model for multi-layer triage generation"""
    extraction_id: str = Field(..., description="UUID of the extraction")
    student_id: Optional[str] = Field(None, description="UUID of the student for historical context")
    counsellor_id: Optional[str] = Field(None, description="UUID of the counsellor")
    school_id: Optional[str] = Field(None, description="UUID of the school")
    include_gemini: bool = Field(True, description="Whether to use Gemini AI for gap analysis")
    log_suggestions: bool = Field(True, description="Whether to log suggestions to database")
    enabled_layers: Optional[List[str]] = Field(None, description="Explicit list of layers to enable (overrides config)")


class LayerConfigResponse(BaseModel):
    """Response model for layer configuration"""
    layer_code: str
    layer_name: str
    description: Optional[str] = None
    is_enabled: bool
    weight: float
    config: Dict[str, Any]
    display_order: int


class LayerConfigUpdateRequest(BaseModel):
    """Request model for updating layer configuration"""
    is_enabled: Optional[bool] = Field(None, description="Enable/disable the layer")
    weight: Optional[float] = Field(None, ge=0, le=1, description="Layer weight (0.0-1.0)")


class BatchLayerConfigUpdate(BaseModel):
    """Request model for batch updating layer configurations"""
    layer_code: str = Field(..., description="Layer code to update")
    is_enabled: Optional[bool] = Field(None, description="Enable/disable the layer")
    weight: Optional[float] = Field(None, ge=0, le=1, description="Layer weight (0.0-1.0)")


# ============================================================================
# Clinical Conditions RAG Models (Enhanced v2)
# ============================================================================

class ConditionIngestionRequest(BaseModel):
    """Request model for ingesting clinical condition JSON"""
    json_data: Dict[str, Any] = Field(..., description="Clinical condition JSON data")
    file_name: Optional[str] = Field("upload.json", description="Source file name for tracking")


class ConditionSearchRequest(BaseModel):
    """Request model for hybrid clinical chunk search"""
    query: str = Field(..., description="Search query text")
    specialty: Optional[str] = Field(None, description="Filter by specialty (e.g., cardiology, ent)")
    chunk_types: Optional[List[str]] = Field(None, description="Filter by chunk types (e.g., treatment_primary, red_flags)")
    care_level: Optional[str] = Field(None, description="Filter by care level (phc_primary, district, tertiary)")
    urgency: Optional[str] = Field(None, description="Filter by urgency level (routine, urgent, emergency)")
    comorbidity: Optional[str] = Field(None, description="Filter by comorbidity (e.g., diabetes, ckd)")
    drug_class: Optional[str] = Field(None, description="Filter by drug class (e.g., CCB, ACE_inhibitor)")
    # Student vitals for threshold matching
    patient_sbp: Optional[int] = Field(None, description="Student systolic BP for threshold matching")
    patient_dbp: Optional[int] = Field(None, description="Student diastolic BP for threshold matching")
    patient_hb: Optional[float] = Field(None, description="Student hemoglobin for threshold matching")
    limit: int = Field(10, ge=1, le=50, description="Maximum results to return")
    similarity_threshold: float = Field(0.4, ge=0, le=1, description="Minimum similarity score")


class ClinicalChunkResponse(BaseModel):
    """Response model for a clinical chunk"""
    id: str
    condition_id: str
    condition_name: str
    chunk_type: str
    content_text: str
    urgency_default: Optional[str] = None
    has_emergency_triggers: bool = False
    has_red_flags: bool = False
    care_levels: Optional[List[str]] = None
    comorbidity: Optional[str] = None
    drug_classes: Optional[List[str]] = None
    source_section: Optional[str] = None
    similarity_score: Optional[float] = None


class ConditionSearchResponse(BaseModel):
    """Response model for clinical chunk search"""
    success: bool
    query: str
    total_results: int
    chunks: List[ClinicalChunkResponse]
    processing_time_ms: int


class ClinicalConditionResponse(BaseModel):
    """Response model for a clinical condition"""
    id: str
    condition_id: str
    name: str
    aliases: List[str]
    icd_codes: List[str]
    specialty: str
    source_name: str
    document_type: str
    triage_metadata: Dict[str, Any]
    chunk_count: int
    is_active: bool
    is_verified: bool
    created_at: str


class ConditionIngestionResponse(BaseModel):
    """Response model for ingestion result"""
    success: bool
    job_id: Optional[str] = None
    status: str
    file_name: Optional[str] = None
    total_conditions: int
    processed_conditions: int
    total_chunks: int
    embedded_chunks: int
    condition_ids: List[str]
    error_message: Optional[str] = None
    validation_errors: Optional[List[Dict[str, Any]]] = None
    duration_seconds: Optional[float] = None


class RedFlagResponse(BaseModel):
    """Response model for red flags"""
    condition_id: str
    condition_name: str
    flag: str
    signs: Optional[List[str]] = None
    action: Optional[str] = None
    urgency: Optional[str] = None


@router.post("/generate-v2", response_model=TriageResponse)
async def generate_triage_multi_layer(http_request: Request, request: TriageV2Request):
    """
    Generate triage suggestions using multi-layer orchestrator.

    This endpoint uses the configurable multi-layer architecture:
    - **Base MVP**: Always active - differential trees + Gemini AI
    - **Counsellor Practice Style**: Learn individual counsellor patterns (if enabled)
    - **School Intelligence**: Peer comparison and benchmarks (if enabled)
    - **RAG Guidelines**: Evidence-based recommendations (if enabled)

    Layers can be enabled/disabled globally via /layers/config or per-request
    via the enabled_layers parameter.

    **Authentication:** Requires Bearer token (API key or JWT).
    """
    import time
    start_time = time.time()

    try:
        # Validate extraction access for EHR clients
        await validate_extraction_from_body(http_request, request.extraction_id)

        # Check if triage analysis is enabled for this consultation type
        ext_check = supabase.table("extractions").select(
            "*, consultation_types!inner(type_code, enable_triage_analysis)"
        ).eq("id", request.extraction_id).single().execute()

        if not ext_check.data:
            raise HTTPException(status_code=404, detail="Extraction not found")

        consultation_type = ext_check.data.get("consultation_types", {})
        enable_triage = consultation_type.get("enable_triage_analysis", True)

        if not enable_triage:
            type_code = consultation_type.get("type_code", "Unknown")
            processing_time = int((time.time() - start_time) * 1000)
            return TriageResponse(
                success=True,
                extraction_id=request.extraction_id,
                specialty="none",
                consultation_type=type_code,
                message=f"Triage analysis is not enabled for consultation type '{type_code}'.",
                critical_actions=[],
                important_considerations=[],
                nice_to_have=[],
                matched_presentations=[],
                identified_red_flags=[],
                gap_analysis={},
                total_suggestions=0,
                generated_at=datetime.utcnow().isoformat(),
                processing_time_ms=processing_time,
            )

        extraction = ext_check.data
        consultation_type_code = consultation_type.get("type_code", "OP")

        # Get school_id from counsellor if not provided
        school_id = request.school_id
        if not school_id and request.counsellor_id:
            counsellor_result = supabase.table("counsellors").select("school_id").eq(
                "id", request.counsellor_id
            ).single().execute()
            if counsellor_result.data:
                school_id = counsellor_result.data.get("school_id")

        # Use multi-layer orchestrator
        orchestrator = get_triage_orchestrator()
        suggestions = await orchestrator.generate_suggestions(
            extraction=extraction,
            student_id=request.student_id,
            counsellor_id=request.counsellor_id,
            school_id=school_id,
            consultation_type_code=consultation_type_code,
            include_gemini_analysis=request.include_gemini,
            log_suggestions=request.log_suggestions,
            enabled_layers=request.enabled_layers,
            supabase_client=supabase
        )

        return TriageResponse(
            success=True,
            extraction_id=request.extraction_id,
            specialty=suggestions.specialty,
            consultation_type=suggestions.consultation_type,
            critical_actions=[
                TriageSuggestionResponse(
                    id=getattr(s, 'id', None),
                    category=s.category,
                    suggestion=s.suggestion,
                    priority=s.priority,
                    rationale=s.rationale,
                    source=s.source,
                    related_presentation=s.related_presentation,
                )
                for s in suggestions.critical_actions
            ],
            important_considerations=[
                TriageSuggestionResponse(
                    id=getattr(s, 'id', None),
                    category=s.category,
                    suggestion=s.suggestion,
                    priority=s.priority,
                    rationale=s.rationale,
                    source=s.source,
                    related_presentation=s.related_presentation,
                )
                for s in suggestions.important_considerations
            ],
            nice_to_have=[
                TriageSuggestionResponse(
                    id=getattr(s, 'id', None),
                    category=s.category,
                    suggestion=s.suggestion,
                    priority=s.priority,
                    rationale=s.rationale,
                    source=s.source,
                    related_presentation=s.related_presentation,
                )
                for s in suggestions.nice_to_have
            ],
            matched_presentations=suggestions.matched_presentations,
            identified_red_flags=suggestions.identified_red_flags,
            gap_analysis=suggestions.gap_analysis,
            total_suggestions=suggestions.total_suggestions,
            generated_at=suggestions.generated_at,
            processing_time_ms=suggestions.processing_time_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TRIAGE_API] Error in multi-layer triage: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate multi-layer triage")


# ============================================================================
# Layer Configuration Endpoints (Admin)
# ============================================================================

@router.get("/layers/config")
async def get_layer_config(_admin=Depends(require_admin)):
    """
    Get all triage layer configurations.

    Returns list of all layers with their current enable/disable status and weights.

    **Authentication:** Requires admin access (web_app or admin client).
    """
    try:
        result = supabase.table("triage_layer_config").select("*").order("display_order").execute()

        layers = [
            {
                "id": row.get("id"),
                "layer_code": row["layer_code"],
                "layer_name": row["layer_name"],
                "description": row.get("description"),
                "is_enabled": row.get("is_enabled", False),
                "weight": float(row.get("weight") or 1.0),
                "config": row.get("config") or {},
                "display_order": row.get("display_order") or 0,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
            for row in result.data or []
        ]

        return {"success": True, "layers": layers}

    except Exception as e:
        logger.error(f"[TRIAGE_API] Error fetching layer config: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch layer config")


@router.put("/layers/config/{layer_code}", response_model=LayerConfigResponse)
async def update_layer_config(
    layer_code: str,
    request: LayerConfigUpdateRequest,
    _admin=Depends(require_admin)
):
    """
    Update a triage layer configuration.

    Allows enabling/disabling layers and adjusting their weights.

    **Authentication:** Requires admin access (web_app or admin client).
    """
    try:
        # Build update data
        update_data = {"updated_at": datetime.utcnow().isoformat()}

        if request.is_enabled is not None:
            # Check if trying to disable base_mvp
            if layer_code == "base_mvp" and request.is_enabled is False:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot disable base_mvp layer - it is always required"
                )
            update_data["is_enabled"] = request.is_enabled

        if request.weight is not None:
            update_data["weight"] = request.weight

        result = supabase.table("triage_layer_config").update(
            update_data
        ).eq("layer_code", layer_code).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Layer not found")

        row = result.data[0]
        return LayerConfigResponse(
            layer_code=row["layer_code"],
            layer_name=row["layer_name"],
            description=row.get("description"),
            is_enabled=row.get("is_enabled", False),
            weight=float(row.get("weight") or 1.0),
            config=row.get("config") or {},
            display_order=row.get("display_order") or 0,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TRIAGE_API] Error updating layer config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update layer config")


@router.post("/layers/config/batch")
async def batch_update_layer_config(
    request: Dict[str, Any],
    _admin=Depends(require_admin)
):
    """
    Batch update multiple layer configurations.

    Useful for updating all layers from the admin UI in one request.

    **Authentication:** Requires admin access (web_app or admin client).

    Request body: { "updates": [{"layer_code": "...", "is_enabled": true, "weight": 0.8}, ...] }
    """
    try:
        updates = request.get("updates", [])
        results = []

        for update in updates:
            layer_code = update.get("layer_code")
            is_enabled = update.get("is_enabled")
            weight = update.get("weight")

            # Validate base_mvp cannot be disabled
            if layer_code == "base_mvp" and is_enabled is False:
                results.append({
                    "layer_code": layer_code,
                    "success": False,
                    "error": "Cannot disable base_mvp layer"
                })
                continue

            update_data = {"updated_at": datetime.utcnow().isoformat()}
            if is_enabled is not None:
                update_data["is_enabled"] = is_enabled
            if weight is not None:
                update_data["weight"] = weight

            result = supabase.table("triage_layer_config").update(
                update_data
            ).eq("layer_code", layer_code).execute()

            results.append({
                "layer_code": layer_code,
                "success": bool(result.data),
                "is_enabled": is_enabled,
                "weight": weight,
            })

        return {
            "success": True,
            "updated_count": sum(1 for r in results if r.get("success")),
            "results": results
        }

    except Exception as e:
        logger.error(f"[TRIAGE_API] Error in batch update: {e}")
        raise HTTPException(status_code=500, detail="Batch update failed")


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health")
async def triage_health_check():
    """
    Health check endpoint for triage service.
    """
    # Get enabled layers count
    try:
        layer_result = supabase.table("triage_layer_config").select("layer_code, is_enabled").execute()
        enabled_layers = [l["layer_code"] for l in (layer_result.data or []) if l.get("is_enabled")]
    except:
        enabled_layers = ["base_mvp"]

    # Get clinical conditions count
    try:
        conditions_result = supabase.table("clinical_conditions").select("id", count="exact").eq("is_active", True).execute()
        conditions_count = conditions_result.count or 0
    except:
        conditions_count = 0

    return {
        "status": "healthy",
        "service": "triage",
        "specialties_loaded": len(DIFFERENTIAL_TREES),
        "total_presentations": sum(len(p) for p in DIFFERENTIAL_TREES.values()),
        "enabled_layers": enabled_layers,
        "multi_layer_available": True,
        "clinical_conditions_count": conditions_count,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================================================
# Clinical Conditions RAG Endpoints (Enhanced v2)
# ============================================================================

@router.post("/conditions/ingest", response_model=ConditionIngestionResponse)
async def ingest_clinical_conditions(
    request: ConditionIngestionRequest,
    _auth=Depends(require_admin_or_webapp)
):
    """
    Ingest clinical condition JSON into the database.

    This endpoint validates the JSON against the clinical guideline schema,
    creates semantic chunks, generates embeddings, and stores everything
    for hybrid RAG search.

    Supports 3 document types:
    - narrative_guideline (e.g., Hypertension STG)
    - visual_workflow (e.g., Rhinosinusitis flowchart)
    - step_protocol (e.g., Epistaxis management steps)

    **Authentication:** Requires admin or web_app access.
    """
    import time
    start_time = time.time()

    try:
        # First validate the JSON
        validation_errors = get_validation_errors(request.json_data)
        if validation_errors:
            return ConditionIngestionResponse(
                success=False,
                status="failed",
                file_name=request.file_name,
                total_conditions=0,
                processed_conditions=0,
                total_chunks=0,
                embedded_chunks=0,
                condition_ids=[],
                error_message=f"Validation failed with {len(validation_errors)} errors",
                validation_errors=validation_errors,
                duration_seconds=(time.time() - start_time),
            )

        # Get ingestion service and run
        ingestion_service = get_clinical_condition_ingestion_service()
        result = await ingestion_service.ingest_from_json(
            json_data=request.json_data,
            file_name=request.file_name or "upload.json",
            supabase_client=supabase
        )

        return ConditionIngestionResponse(
            success=result.status == "completed",
            job_id=result.job_id,
            status=result.status,
            file_name=result.file_name,
            total_conditions=result.total_conditions,
            processed_conditions=result.processed_conditions,
            total_chunks=result.total_chunks,
            embedded_chunks=result.embedded_chunks,
            condition_ids=result.condition_ids,
            error_message=result.error_message,
            validation_errors=result.validation_errors,
            duration_seconds=result.duration_seconds,
        )

    except Exception as e:
        logger.error(f"[TRIAGE_API] Error ingesting conditions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to ingest conditions")


@router.post("/conditions/search", response_model=ConditionSearchResponse)
async def search_clinical_chunks(request: ConditionSearchRequest):
    """
    Search clinical chunks using hybrid semantic + filter search.

    Combines:
    - Semantic similarity search (pgvector)
    - Specialty filtering
    - Chunk type filtering
    - Care level filtering
    - Numeric threshold matching (BP, Hb values, etc.)

    **Authentication:** Requires Bearer token (API key or JWT).
    """
    import time
    start_time = time.time()

    try:
        # Generate embedding for query
        from services.qa.embedding_service import EmbeddingService
        embedding_service = EmbeddingService()
        embeddings, _ = await embedding_service.generate_embedding(
            texts=[request.query],
            input_type="search_query",
            use_cache=True
        )

        if not embeddings:
            raise HTTPException(status_code=500, detail="Failed to generate query embedding")

        # Pad embedding to 1536 dimensions if needed
        query_embedding = embeddings[0]
        if len(query_embedding) < 1536:
            query_embedding = query_embedding + [0.0] * (1536 - len(query_embedding))

        # Call hybrid search RPC
        rpc_result = supabase.rpc("search_clinical_chunks_hybrid", {
            "query_embedding": query_embedding,
            "query_text": request.query,
            "filter_specialty": request.specialty,
            "filter_chunk_types": request.chunk_types,
            "filter_urgency": request.urgency,
            "filter_comorbidity": request.comorbidity,
            "filter_care_level": request.care_level,
            "filter_drug_class": request.drug_class,
            "patient_sbp": request.patient_sbp,
            "patient_dbp": request.patient_dbp,
            "patient_hb": request.patient_hb,
            "match_count": request.limit,
            "min_similarity": request.similarity_threshold,
        }).execute()

        # Convert results to response format
        chunks = []
        for row in rpc_result.data or []:
            chunks.append(ClinicalChunkResponse(
                id=row.get("chunk_id"),
                condition_id=row.get("condition_id"),
                condition_name=row.get("condition_name"),
                chunk_type=row.get("chunk_type"),
                content_text=row.get("content_text"),
                urgency_default=row.get("urgency_default"),
                has_emergency_triggers=row.get("has_emergency_triggers", False),
                has_red_flags=row.get("has_red_flags", False),
                care_levels=row.get("care_levels"),
                comorbidity=row.get("comorbidity"),
                drug_classes=row.get("drug_classes"),
                source_section=row.get("source_section"),
                similarity_score=row.get("similarity"),
            ))

        processing_time = int((time.time() - start_time) * 1000)

        return ConditionSearchResponse(
            success=True,
            query=request.query,
            total_results=len(chunks),
            chunks=chunks,
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TRIAGE_API] Error searching chunks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to search clinical chunks")


@router.get("/conditions", response_model=List[ClinicalConditionResponse])
async def list_clinical_conditions(
    specialty: Optional[str] = Query(None, description="Filter by specialty"),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    is_active: bool = Query(True, description="Only return active conditions"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
):
    """
    List all clinical conditions in the database.

    Returns condition metadata including chunk counts.

    **Authentication:** Requires Bearer token (API key or JWT).
    """
    try:
        # Build query
        query = supabase.table("clinical_conditions").select(
            "id, condition_id, name, aliases, icd_codes, specialty, source_name, "
            "document_type, triage_metadata, is_active, is_verified, created_at"
        )

        if specialty:
            query = query.eq("specialty", specialty)
        if document_type:
            query = query.eq("document_type", document_type)
        if is_active:
            query = query.eq("is_active", True)

        result = query.order("name").limit(limit).execute()

        # Get chunk counts for each condition
        conditions = []
        for row in result.data or []:
            # Get chunk count
            chunk_count_result = supabase.table("clinical_chunks").select(
                "id", count="exact"
            ).eq("condition_id", row["id"]).execute()
            chunk_count = chunk_count_result.count or 0

            conditions.append(ClinicalConditionResponse(
                id=row["id"],
                condition_id=row["condition_id"],
                name=row["name"],
                aliases=row.get("aliases") or [],
                icd_codes=row.get("icd_codes") or [],
                specialty=row.get("specialty", ""),
                source_name=row.get("source_name", ""),
                document_type=row.get("document_type", ""),
                triage_metadata=row.get("triage_metadata") or {},
                chunk_count=chunk_count,
                is_active=row.get("is_active", True),
                is_verified=row.get("is_verified", False),
                created_at=row.get("created_at", ""),
            ))

        return conditions

    except Exception as e:
        logger.error(f"[TRIAGE_API] Error listing conditions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list conditions")


@router.get("/conditions/{condition_id}")
async def get_clinical_condition(condition_id: str):
    """
    Get a clinical condition with all its chunks.

    Returns full condition data including all semantic chunks.

    **Authentication:** Requires Bearer token (API key or JWT).
    """
    try:
        # Get condition
        result = supabase.table("clinical_conditions").select("*").eq(
            "condition_id", condition_id
        ).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Condition not found")

        condition = result.data

        # Get all chunks for this condition
        chunks_result = supabase.table("clinical_chunks").select("*").eq(
            "condition_id", condition["id"]
        ).order("chunk_index").execute()

        return {
            "condition": condition,
            "chunks": chunks_result.data or [],
            "chunk_count": len(chunks_result.data or []),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TRIAGE_API] Error getting condition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get condition")


@router.get("/conditions/red-flags/{specialty}", response_model=List[RedFlagResponse])
async def get_red_flags_by_specialty(specialty: str):
    """
    Get all red flags for a specialty.

    Returns red flags from all conditions in the specified specialty,
    useful for building warning checklists.

    **Authentication:** Requires Bearer token (API key or JWT).
    """
    try:
        # Call the RPC function
        result = supabase.rpc("get_red_flags_by_specialty", {
            "p_specialty": specialty
        }).execute()

        red_flags = []
        for row in result.data or []:
            red_flags.append(RedFlagResponse(
                condition_id=row.get("condition_id"),
                condition_name=row.get("condition_name"),
                flag=row.get("flag"),
                signs=row.get("signs"),
                action=row.get("action"),
                urgency=row.get("urgency"),
            ))

        return red_flags

    except Exception as e:
        logger.error(f"[TRIAGE_API] Error getting red flags: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get red flags")


@router.get("/conditions/comorbidity/{comorbidity}")
async def get_comorbidity_pathway(comorbidity: str):
    """
    Get treatment recommendations for a specific comorbidity.

    Returns comorbidity pathway chunks from all conditions that have
    guidance for the specified comorbidity (e.g., diabetes, CKD).

    **Authentication:** Requires Bearer token (API key or JWT).
    """
    try:
        # Call the RPC function
        result = supabase.rpc("get_comorbidity_pathway", {
            "p_comorbidity": comorbidity
        }).execute()

        return {
            "comorbidity": comorbidity,
            "pathways": result.data or [],
            "count": len(result.data or []),
        }

    except Exception as e:
        logger.error(f"[TRIAGE_API] Error getting comorbidity pathway: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get comorbidity pathway")


@router.delete("/conditions/{condition_id}")
async def delete_clinical_condition(
    condition_id: str,
    _auth=Depends(require_admin_or_webapp)
):
    """
    Delete a clinical condition and all its chunks.

    Soft delete - marks as inactive rather than physically deleting.

    **Authentication:** Requires admin or web_app access.
    """
    try:
        # Check if exists
        existing = supabase.table("clinical_conditions").select("id").eq(
            "condition_id", condition_id
        ).single().execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Condition not found")

        # Soft delete
        supabase.table("clinical_conditions").update({
            "is_active": False,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("condition_id", condition_id).execute()

        logger.info(f"[TRIAGE_API] Soft deleted condition: {condition_id}")

        return {
            "success": True,
            "message": f"Condition '{condition_id}' marked as inactive",
            "condition_id": condition_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TRIAGE_API] Error deleting condition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete condition")

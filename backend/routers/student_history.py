"""
Student History API Router

Provides endpoints to retrieve student medical history including:
1. Last prescription
2. Last investigations results
3. Last investigations ordered
4. Last diagnosis
5. Last case summary (diagnosis, chief complaints, prescription, examination, treatment plan, follow-up)
6. Student context (case summary + emotional analysis + recommended interventions)

All endpoints support filtering by counsellor_id and school_id.

Security:
- When AUTH_ENABLED=true, all endpoints require authentication
- EHR clients: Auto-create students if they don't exist
- Counsellor access: Validated against client's allowed_counsellor_ids
- HIPAA audit logging: All PHI access is logged
"""

import os
import uuid
import asyncio
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional, List, Tuple

from services.supabase_service import supabase
from services.raster_api_service import fetch_all_neopaed_students
from services.audit_service import audit_service
from services.history_extraction_utils import (
    # Assistant extraction filtering (with legacy aliases)
    filter_assistant_extractions,
    is_assistant_extraction,
    filter_prescreen_extractions,  # legacy alias
    is_prescreen_extraction,  # legacy alias
    # Extraction data access
    get_extraction_data,
    get_segment_from_extraction,
    get_segments_batch,
    # Segment/data extraction
    find_segment_value,
    extract_chief_complaints,
    extract_vitals,
    # Data list extraction
    extract_diagnosis_list,
    extract_complaints_list,
    extract_medicines_list,
    # Prescription utilities
    find_prescription_in_extraction,
    normalize_prescription_data,
    extract_and_normalize_prescription,
    # Name normalization
    normalize_diagnosis_name,
    normalize_complaint_name,
    normalize_medicine_name,
    # Analysis helpers
    get_dominant_level,
    calculate_trend,
    is_within_recent_window,
    # Note: Change detection functions (detect_diagnosis_changes, etc.) are imported
    # with aliases in the Clinical Timeline Helpers section and wrapped with
    # local functions that convert dict results to TimelineChange Pydantic models
)

# Auth imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import get_current_client, StudentAccessChecker, EHRStudentAccessChecker, EHRCounsellorAccessChecker
    from services.audit_service import audit_service
    from models.auth_models import ClientContext

    # Create checker instances for use in endpoints
    _patient_checker = EHRStudentAccessChecker()
    _doctor_checker = EHRCounsellorAccessChecker()

    async def verify_authenticated(request: Request):  # type: ignore[misc]
        """Verify client is authenticated (admin, web user, or EHR API key)."""
        return get_current_client(request)

    async def verify_student_access(request: Request, student_id: str = None):  # type: ignore[misc]
        """Verify EHR client has access to student data."""
        client = get_current_client(request)
        return await _patient_checker(request, student_id, client)

    async def verify_counsellor_access(request: Request, counsellor_id: str = None):  # type: ignore[misc]
        """Verify EHR client has access to counsellor data."""
        counsellor_uuid = uuid.UUID(counsellor_id) if counsellor_id else None
        client = get_current_client(request)
        return await _doctor_checker(request, counsellor_uuid, client)
else:
    # No-op when auth is disabled
    async def verify_authenticated(request: Request):  # type: ignore[misc]
        return None

    async def verify_student_access(request: Request, student_id: str = None):  # type: ignore[misc]
        return None

    async def verify_counsellor_access(request: Request, counsellor_id: str = None):  # type: ignore[misc]
        return None

logger = logging.getLogger(__name__)

# Thread pool for running sync Supabase calls in parallel
_prescreen_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="prescreen")

router = APIRouter(
    prefix="/api/v1/students",
    tags=["student-history"]
)


# ============================================================================
# Response Models
# ============================================================================

class StudentInfo(BaseModel):
    """Basic student information"""
    id: str
    student_id: str  # External identifier
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    preferred_language: Optional[str] = None


class ExtractionMetadata(BaseModel):
    """Metadata about the extraction source"""
    extraction_id: str
    session_id: Optional[str] = None
    consultation_type: Optional[str] = None
    counsellor_id: Optional[str] = None
    counsellor_name: Optional[str] = None
    created_at: str
    is_edited: bool = False


class LastPrescriptionResponse(BaseModel):
    """Response for last prescription"""
    patient: StudentInfo
    prescription: Optional[Any] = None  # Can be List[Dict] or Dict depending on extraction format
    metadata: Optional[ExtractionMetadata] = None
    found: bool = False


class LastDiagnosisResponse(BaseModel):
    """Response for last diagnosis"""
    patient: StudentInfo
    diagnosis: Optional[Any] = None  # Can be dict, list, or string
    metadata: Optional[ExtractionMetadata] = None
    found: bool = False


class InvestigationItem(BaseModel):
    """Investigation item with results or ordered status"""
    name: str
    status: str  # "ordered", "completed", "pending"
    results: Optional[Any] = None
    ordered_date: Optional[str] = None
    completed_date: Optional[str] = None


class LastInvestigationsResponse(BaseModel):
    """Response for last investigations (ordered or results)"""
    patient: StudentInfo
    investigations: Optional[Any] = None  # Raw investigation data
    metadata: Optional[ExtractionMetadata] = None
    found: bool = False


class CaseSummary(BaseModel):
    """Consolidated case summary"""
    diagnosis: Optional[Any] = None
    chief_complaints: Optional[Any] = None
    prescription: Optional[Any] = None
    examination: Optional[Any] = None  # Physical examination findings
    treatment_plan: Optional[Any] = None
    follow_up: Optional[Any] = None
    history: Optional[Any] = None


class LastCaseSummaryResponse(BaseModel):
    """Response for last case summary"""
    patient: StudentInfo
    case_summary: Optional[CaseSummary] = None
    metadata: Optional[ExtractionMetadata] = None
    found: bool = False


class EmotionSummary(BaseModel):
    """Summary of emotional analysis"""
    anxiety_pre_consultation: Optional[Dict[str, Any]] = None
    anxiety_post_consultation: Optional[Dict[str, Any]] = None
    other_emotions: Optional[Dict[str, Any]] = None
    audio_anxiety: Optional[Dict[str, Any]] = None
    congruence_analysis: Optional[Dict[str, Any]] = None
    financial_concerns: Optional[Dict[str, Any]] = None
    compliance_likelihood: Optional[Dict[str, Any]] = None


class InterventionSummary(BaseModel):
    """Summary of recommended interventions"""
    id: str
    code: str
    name: str
    description: str
    category: str
    priority: str
    priority_score: int
    trigger_reason: str
    is_top_3: bool


class EmotionPatternItem(BaseModel):
    """Single emotion pattern item for summary display"""
    label: str  # e.g., "Anxiety Level", "Financial Concerns", "Treatment Compliance"
    value: str  # e.g., "High", "Moderate concerns", "Low likelihood"
    trend: Optional[str] = None  # "improving", "worsening", "stable", None


class EmotionPatternSummary(BaseModel):
    """
    Aggregated emotion summary across last N consultations.
    Shows concise one-line summaries without rationale.
    """
    visits_analyzed: int = 0
    patterns: List[EmotionPatternItem] = []
    has_emotion_data: bool = False


class StudentContextResponse(BaseModel):
    """Complete student context for informed consultations"""
    patient: StudentInfo
    last_case_summary: Optional[CaseSummary] = None
    case_summary_metadata: Optional[ExtractionMetadata] = None
    emotion_summary: Optional[EmotionSummary] = None
    emotion_metadata: Optional[ExtractionMetadata] = None
    recommended_interventions: List[InterventionSummary] = []
    consultation_count: int = 0
    last_visit_date: Optional[str] = None
    found: bool = False


class StudentSearchResult(BaseModel):
    """Student search result"""
    id: str
    student_id: str
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    consultation_count: int = 0
    last_visit_date: Optional[str] = None
    add_info: Optional[Dict[str, Any]] = None  # Additional info (e.g., room/bed for NICU students)
    school_id: Optional[str] = None
    school_name: Optional[str] = None


class StudentSearchResponse(BaseModel):
    """Response for student search"""
    students: List[StudentSearchResult]
    total_count: int
    page: int
    page_size: int
    has_more: bool


class StudentCreateRequest(BaseModel):
    """Request body for creating a new student"""
    student_id: str  # Required - UHID/MRN
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None  # ISO format: YYYY-MM-DD
    gender: Optional[str] = None
    ip_id: Optional[str] = None
    op_id: Optional[str] = None
    counsellor_ids: Optional[List[str]] = None  # Array of counsellor UUIDs
    add_info: Optional[Dict[str, Any]] = None


class StudentCreateResponse(BaseModel):
    """Response for student creation"""
    success: bool
    patient: Optional[Dict[str, Any]] = None
    created: bool = False  # True if new student, False if already existed
    message: str


class ConsultationHistoryItem(BaseModel):
    """Single consultation in history list"""
    extraction_id: str
    session_id: Optional[str] = None
    # submission_id of the most recent processing_job for this session — needed
    # by the frontend to call PUT /iframe/edit/{submission_id} on an old row
    # without having to do a separate lookup.
    submission_id: Optional[str] = None
    consultation_type: Optional[str] = None
    consultation_type_name: Optional[str] = None
    counsellor_id: Optional[str] = None
    counsellor_name: Optional[str] = None
    created_at: str
    is_edited: bool = False
    has_emotion_analysis: bool = False
    segment_count: int = 0
    role: Optional[str] = None
    # Quick preview fields
    primary_diagnosis: Optional[str] = None
    chief_complaint: Optional[str] = None


class ConsultationHistoryResponse(BaseModel):
    """Response for student consultation history"""
    patient: StudentInfo
    consultations: List[ConsultationHistoryItem]
    total_count: int
    page: int
    page_size: int
    has_more: bool


# ============================================================================
# School Context Helper
# ============================================================================

def _get_school_id_from_context(request: Request, counsellor_id: Optional[str] = None) -> Optional[str]:
    """
    Extract school_id from auth context or derive from counsellor_id.

    Priority:
    1. Auth client context (EHR clients have school_id)
    2. Derive from counsellor_id via cached lookup
    3. None (falls back to unscoped lookup)
    """
    # Try auth context first
    if AUTH_ENABLED:
        try:
            client = get_current_client(request)
            if hasattr(client, 'school_id') and client.school_id:
                return str(client.school_id)
        except Exception:
            pass

    # Derive from counsellor_id
    if counsellor_id:
        from services.supabase_service import get_counsellor_school_id_cached
        return get_counsellor_school_id_cached(counsellor_id)

    return None


# ============================================================================
# Helper Functions
# ============================================================================

def get_student_info(patient_uuid: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get student basic info by UUID"""
    result = supabase.table("students")\
        .select("id, student_id, full_name, date_of_birth, gender, preferred_language")\
        .eq("id", str(patient_uuid))\
        .limit(1)\
        .execute()

    if not result.data:
        return None
    return result.data[0]


def resolve_student_id(student_id: str, school_id: Optional[str] = None) -> Optional[uuid.UUID]:
    """
    Resolve external student_id to internal database UUID.

    The student_id parameter can be either:
    1. An external identifier (student_id column) - PRIMARY lookup method
    2. A database UUID (id column) - fallback if external ID not found

    External systems typically only have student_id (varchar), so we prioritize
    that lookup first for better performance and compatibility.

    Args:
        student_id: External student identifier (preferred) or database UUID
        school_id: School UUID for scoped lookup (optional)

    Returns:
        Database UUID or None if student not found
    """
    # PRIORITY 1: Try to find by external student_id first
    # This is the primary lookup method since external systems use student_id
    query = supabase.table("students")\
        .select("id")\
        .eq("student_id", student_id)
    if school_id:
        query = query.eq("school_id", school_id)
    result = query.limit(1).execute()

    if result.data:
        return uuid.UUID(result.data[0]["id"])

    # PRIORITY 2: Fallback - check if it's a valid UUID (for internal callers)
    try:
        potential_uuid = uuid.UUID(student_id)
        result = supabase.table("students")\
            .select("id")\
            .eq("id", str(potential_uuid))\
            .limit(1)\
            .execute()
        if result.data:
            return potential_uuid
    except ValueError:
        # Not a valid UUID format, that's fine
        pass

    return None


def get_student_info_by_external_id(student_id: str, school_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get student info by external student_id (or database UUID).

    Args:
        student_id: External student identifier or database UUID
        school_id: School UUID for scoped lookup (optional)

    Returns:
        Student info dict or None if not found
    """
    patient_uuid = resolve_student_id(student_id, school_id=school_id)
    if not patient_uuid:
        return None
    return get_student_info(patient_uuid)


def resolve_student_id_or_404(student_id: str, school_id: Optional[str] = None) -> uuid.UUID:
    """
    Resolve external student_id to internal database UUID, raising HTTPException if not found.

    Args:
        student_id: External student identifier or database UUID
        school_id: School UUID for scoped lookup (optional)

    Returns:
        Database UUID

    Raises:
        HTTPException: 404 if student not found
    """
    patient_uuid = resolve_student_id(student_id, school_id=school_id)
    if not patient_uuid:
        raise HTTPException(status_code=404, detail="Student not found")
    return patient_uuid


def resolve_student_with_info_or_404(student_id: str, school_id: Optional[str] = None) -> Tuple[uuid.UUID, Dict[str, Any]]:
    """
    Resolve student_id and get student info in a single query.
    Combines resolve_student_id_or_404() + get_student_info() to save 1 DB round-trip.
    """
    # Try by external student_id first
    query = supabase.table("students")\
        .select("id, student_id, full_name, date_of_birth, gender")\
        .eq("student_id", student_id)
    if school_id:
        query = query.eq("school_id", school_id)
    result = query.limit(1).execute()

    if result.data:
        patient = result.data[0]
        return uuid.UUID(patient["id"]), patient

    # Fallback: try as UUID
    try:
        potential_uuid = uuid.UUID(student_id)
        result = supabase.table("students")\
            .select("id, student_id, full_name, date_of_birth, gender")\
            .eq("id", str(potential_uuid))\
            .limit(1)\
            .execute()
        if result.data:
            return potential_uuid, result.data[0]
    except ValueError:
        pass

    raise HTTPException(status_code=404, detail="Student not found")


def get_counsellor_name(counsellor_id: str) -> Optional[str]:
    """Get counsellor name by ID"""
    result = supabase.table("counsellors")\
        .select("full_name")\
        .eq("id", counsellor_id)\
        .limit(1)\
        .execute()

    if result.data:
        return result.data[0].get("full_name")
    return None


def get_consultation_type_name(ct_id: str) -> Optional[str]:
    """Get consultation type name by ID"""
    result = supabase.table("consultation_types")\
        .select("type_name")\
        .eq("id", ct_id)\
        .limit(1)\
        .execute()

    if result.data:
        return result.data[0].get("type_name")
    return None


def batch_get_counsellor_names(counsellor_ids: List[str]) -> Dict[str, str]:
    """
    Batch fetch counsellor names by IDs.
    Returns dict mapping counsellor_id -> full_name.
    Single query instead of N queries.
    """
    if not counsellor_ids:
        return {}

    # Remove duplicates and None values
    unique_ids = list(set(id for id in counsellor_ids if id))
    if not unique_ids:
        return {}

    result = supabase.table("counsellors")\
        .select("id, full_name")\
        .in_("id", unique_ids)\
        .execute()

    return {row["id"]: row.get("full_name") for row in (result.data or [])}


def batch_get_consultation_type_names(ct_ids: List[str]) -> Dict[str, str]:
    """
    Batch fetch consultation type names by IDs.
    Returns dict mapping consultation_type_id -> type_name.
    Single query instead of N queries.
    """
    if not ct_ids:
        return {}

    # Remove duplicates and None values
    unique_ids = list(set(id for id in ct_ids if id))
    if not unique_ids:
        return {}

    result = supabase.table("consultation_types")\
        .select("id, type_name")\
        .in_("id", unique_ids)\
        .execute()

    return {row["id"]: row.get("type_name") for row in (result.data or [])}


def build_extraction_metadata(extraction: Dict[str, Any]) -> ExtractionMetadata:
    """Build extraction metadata from extraction record"""
    counsellor_name = None
    if extraction.get("counsellor_id"):
        counsellor_name = get_counsellor_name(extraction["counsellor_id"])

    ct_name = None
    if extraction.get("consultation_type_id"):
        ct_name = get_consultation_type_name(extraction["consultation_type_id"])

    return ExtractionMetadata(
        extraction_id=extraction["id"],
        session_id=extraction.get("session_id"),
        consultation_type=ct_name,
        counsellor_id=extraction.get("counsellor_id"),
        counsellor_name=counsellor_name,
        created_at=extraction["created_at"],
        is_edited=extraction.get("edited_extraction_json") is not None
    )


def _get_school_view_counsellor_ids(
    current_counsellor_id: str,
    patient_uuid: uuid.UUID,
) -> List[str]:
    """
    Resolve the OTHER active counsellor IDs at the same school as `current_counsellor_id`,
    after verifying the student also belongs to that school.

    Used by student-history endpoints when `school_view=true` is requested:
    callers want to see records authored by other staff (counsellors and
    assistants-on-behalf-of-counsellors, since every extraction carries a counsellor_id) within
    the same school — excluding the requesting counsellor's own records.

    Raises:
        HTTPException 400 if counsellor or student lacks school_id, or 403 if their
        schools don't match.
    """
    from services.supabase_service import get_counsellor_school_id_cached

    counsellor_school_id = get_counsellor_school_id_cached(current_counsellor_id)
    if not counsellor_school_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot use school_view: requesting counsellor has no school_id."
        )

    student_row = supabase.table("students")\
        .select("school_id")\
        .eq("id", str(patient_uuid))\
        .limit(1)\
        .execute()
    student_school_id = (student_row.data or [{}])[0].get("school_id")
    if not student_school_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot use school_view: student has no school_id."
        )
    if str(student_school_id) != str(counsellor_school_id):
        raise HTTPException(
            status_code=403,
            detail="Student does not belong to the requesting counsellor's school."
        )

    others = supabase.table("counsellors")\
        .select("id")\
        .eq("school_id", str(counsellor_school_id))\
        .neq("id", current_counsellor_id)\
        .eq("is_active", True)\
        .execute()
    return [row["id"] for row in (others.data or [])]


def _resolve_school_view_filter(
    school_view: bool,
    counsellor_id: Optional[str],
    patient_uuid: uuid.UUID,
) -> Optional[List[str]]:
    """
    When school_view=True, return the list of OTHER-counsellor IDs at the same
    school (after verifying student school match). Returns None when the
    flag is off so the caller can fall back to the existing single-counsellor path.
    Raises 400 if school_view=True but no counsellor_id provided.
    """
    if not school_view:
        return None
    if not counsellor_id:
        raise HTTPException(
            status_code=400,
            detail="school_view=true requires the counsellor_id query parameter."
        )
    return _get_school_view_counsellor_ids(counsellor_id, patient_uuid)


def get_latest_extraction_for_student(
    patient_uuid: uuid.UUID,
    counsellor_id: Optional[str] = None,
    school_id: Optional[str] = None,
    counsellor_ids: Optional[List[str]] = None,
    include_assistant: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Get the most recent NON-PRESCREEN extraction for a student.

    PRESCREEN extractions are filtered out as they typically don't have meaningful
    clinical data (prescriptions, diagnoses, etc.).

    When `counsellor_ids` is provided (school_view mode), it takes precedence over
    `counsellor_id` and matches `counsellor_id IN (...)`. When `include_assistant=True`,
    assistant-initiated extractions are not filtered out.
    """
    # Get recent extractions with recording_sessions join for PRESCREEN filtering
    query = supabase.table("extractions")\
        .select("*, recording_sessions(template_code, assistant_id)")\
        .eq("student_id", str(patient_uuid))\
        .order("created_at", desc=True)

    if counsellor_ids is not None:
        if not counsellor_ids:
            return None
        query = query.in_("counsellor_id", counsellor_ids)
    elif counsellor_id:
        query = query.eq("counsellor_id", counsellor_id)

    # School filtering would require joining with counsellors table
    # For now, we'll filter in application if needed

    query = query.limit(10)  # Fetch more to account for PRESCREEN filtering
    result = query.execute()

    if not result.data:
        return None

    # Find first non-assistant extraction (assistant_id check + PRESCREEN legacy fallback)
    for extraction in result.data:
        if not include_assistant and is_assistant_extraction(extraction):
            continue
        return extraction

    return None


def build_emotion_pattern_summary(
    patient_uuid: uuid.UUID,
    counsellor_id: Optional[str] = None,
    num_visits: int = 2,
    pre_fetched_extractions: Optional[List[Dict[str, Any]]] = None,
    counsellor_ids: Optional[List[str]] = None,
    include_assistant: bool = False,
) -> EmotionPatternSummary:
    """
    Build aggregated emotion pattern summary across last N NON-PRESCREEN consultations.
    Returns concise one-line summaries without rationale/explanations.

    Prescreen extractions are excluded as they typically don't have emotion analysis data.
    Note: If the 2nd extraction is older than 6 months, only the latest is used.

    `counsellor_ids` (school_view mode) overrides `counsellor_id` and filters via IN().
    `include_assistant=True` skips the assistant-extraction filter.
    """
    # Use pre-fetched extractions if available (avoids redundant DB query)
    if pre_fetched_extractions is not None:
        # Filter to only those with emotion_extraction_completed
        filtered_extractions = [
            ext for ext in pre_fetched_extractions
            if ext.get("emotion_extraction_completed") is True
        ][:num_visits]
    else:
        # Fallback: fetch from DB (used when called outside prescreen endpoint)
        emotion_query = supabase.table("extractions")\
            .select("id, created_at, recording_sessions(template_code, assistant_id)")\
            .eq("student_id", str(patient_uuid))\
            .eq("emotion_extraction_completed", True)\
            .order("created_at", desc=True)

        if counsellor_ids is not None:
            if not counsellor_ids:
                return EmotionPatternSummary(visits_analyzed=0, patterns=[], has_emotion_data=False)
            emotion_query = emotion_query.in_("counsellor_id", counsellor_ids)
        elif counsellor_id:
            emotion_query = emotion_query.eq("counsellor_id", counsellor_id)

        emotion_query = emotion_query.limit(num_visits * 2)
        emotion_result = emotion_query.execute()

        if not emotion_result.data:
            return EmotionPatternSummary(visits_analyzed=0, patterns=[], has_emotion_data=False)

        if include_assistant:
            # School-view mode wants assistant-authored data included as-is
            filtered_extractions = (emotion_result.data or [])[:num_visits]
        else:
            # Filter out assistant extractions (assistant_id + PRESCREEN legacy fallback)
            filtered_extractions = filter_assistant_extractions(emotion_result.data or [], max_results=num_visits)

    if not filtered_extractions:
        return EmotionPatternSummary(visits_analyzed=0, patterns=[], has_emotion_data=False)

    # Apply 6-month filter: If 2nd extraction is older than 6 months, use only latest
    if len(filtered_extractions) >= 2:
        from datetime import timedelta
        try:
            second_ext_date = filtered_extractions[1].get("created_at", "")
            if second_ext_date:
                second_dt = datetime.fromisoformat(second_ext_date.replace('Z', '+00:00'))
                six_months_ago = datetime.now(second_dt.tzinfo) - timedelta(days=180)
                if second_dt < six_months_ago:
                    logger.info(
                        f"[EMOTION_PATTERN] 2nd extraction is older than 6 months ({second_ext_date[:10]}), "
                        f"using only latest extraction"
                    )
                    filtered_extractions = filtered_extractions[:1]
        except (ValueError, TypeError) as e:
            logger.warning(f"[EMOTION_PATTERN] Error parsing date for 6-month filter: {e}")

    extraction_ids = [e["id"] for e in filtered_extractions]
    visits_analyzed = len(extraction_ids)

    # Collect emotion segments from all extractions using batch query (single DB call)
    emotion_segment_codes = [
        "ANXIETY_POST_CONSULTATION", "FINANCIAL_CONCERNS",
        "TREATMENT_COMPLIANCE_LIKELIHOOD", "OTHER_EMOTIONS_DETECTED"
    ]
    segments_by_extraction = get_segments_batch(extraction_ids, emotion_segment_codes)

    all_anxiety_pre = []
    all_anxiety_post = []
    all_financial = []
    all_compliance = []
    all_other_emotions = []

    for ext_id in extraction_ids:
        ext_segments = segments_by_extraction.get(ext_id, {})

        # ANXIETY_POST_CONSULTATION
        value = ext_segments.get("ANXIETY_POST_CONSULTATION")
        if value:
            pre_consultation = value.get("pre_consultation")
            if isinstance(pre_consultation, dict):
                pre_level = pre_consultation.get("level")
                if pre_level:
                    all_anxiety_pre.append(pre_level)
            post_consultation = value.get("post_consultation")
            if isinstance(post_consultation, dict):
                post_level = post_consultation.get("level")
                if post_level:
                    all_anxiety_post.append(post_level)

        # FINANCIAL_CONCERNS
        value = ext_segments.get("FINANCIAL_CONCERNS")
        if value:
            level = value.get("severity")
            if level:
                all_financial.append(level)

        # TREATMENT_COMPLIANCE_LIKELIHOOD
        value = ext_segments.get("TREATMENT_COMPLIANCE_LIKELIHOOD")
        if value:
            level = value.get("likelihood")
            if level:
                all_compliance.append(level)

        # OTHER_EMOTIONS_DETECTED
        value = ext_segments.get("OTHER_EMOTIONS_DETECTED")
        if value:
            emotions = value.get("emotions_detected")
            if isinstance(emotions, list):
                for em in emotions:
                    if isinstance(em, str):
                        all_other_emotions.append(em)

    # Build patterns list with aggregated summaries
    patterns = []

    # Anxiety summary (average across visits)
    if all_anxiety_pre:
        avg_anxiety = get_dominant_level(all_anxiety_pre)
        trend = calculate_trend(all_anxiety_pre) if len(all_anxiety_pre) > 1 else None
        patterns.append(EmotionPatternItem(
            label="Pre-Consultation Anxiety",
            value=avg_anxiety,
            trend=trend
        ))

    if all_anxiety_post:
        avg_anxiety = get_dominant_level(all_anxiety_post)
        trend = calculate_trend(all_anxiety_post) if len(all_anxiety_post) > 1 else None
        patterns.append(EmotionPatternItem(
            label="Post-Consultation Anxiety",
            value=avg_anxiety,
            trend=trend
        ))

    # Financial concerns summary
    if all_financial:
        avg_financial = get_dominant_level(all_financial)
        patterns.append(EmotionPatternItem(
            label="Financial Concerns",
            value=avg_financial,
            trend=None
        ))

    # Compliance likelihood summary
    if all_compliance:
        avg_compliance = get_dominant_level(all_compliance)
        patterns.append(EmotionPatternItem(
            label="Treatment Compliance",
            value=avg_compliance,
            trend=None
        ))

    # Other emotions (most common)
    if all_other_emotions:
        # Get top 2 most common emotions
        emotion_counts = {}
        for em in all_other_emotions:
            if em:
                emotion_counts[em] = emotion_counts.get(em, 0) + 1
        sorted_emotions = sorted(emotion_counts.items(), key=lambda x: x[1], reverse=True)
        top_emotions = [e[0] for e in sorted_emotions[:2]]
        if top_emotions:
            patterns.append(EmotionPatternItem(
                label="Common Emotions",
                value=", ".join(top_emotions),
                trend=None
            ))

    return EmotionPatternSummary(
        visits_analyzed=visits_analyzed,
        patterns=patterns,
        has_emotion_data=len(patterns) > 0
    )


def get_latest_extraction_with_segment(
    patient_uuid: uuid.UUID,
    segment_keys: List[str],
    counsellor_id: Optional[str] = None,
    counsellor_ids: Optional[List[str]] = None,
    include_assistant: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Get the most recent NON-PRESCREEN extraction that contains any of the specified segments.

    PRESCREEN extractions are filtered out as they typically don't have meaningful
    clinical data (prescriptions, diagnoses, etc.).

    When `counsellor_ids` is provided (school_view mode), it takes precedence over
    `counsellor_id` and matches `counsellor_id IN (...)`. When `include_assistant=True`, assistant
    extractions are not skipped.
    """
    # Get recent extractions for student with recording_sessions join for PRESCREEN filtering
    query = supabase.table("extractions")\
        .select("*, recording_sessions(template_code, assistant_id)")\
        .eq("student_id", str(patient_uuid))\
        .order("created_at", desc=True)

    if counsellor_ids is not None:
        if not counsellor_ids:
            return None
        query = query.in_("counsellor_id", counsellor_ids)
    elif counsellor_id:
        query = query.eq("counsellor_id", counsellor_id)

    query = query.limit(30)  # Fetch more to account for PRESCREEN filtering
    result = query.execute()

    if not result.data:
        return None

    # Find first non-assistant extraction with requested segment
    for extraction in result.data:
        if not include_assistant and is_assistant_extraction(extraction):
            continue

        data = get_extraction_data(extraction)
        for key in segment_keys:
            if find_segment_value(data, key) is not None:
                return extraction

    return None


def get_top_interventions(
    patient_uuid: uuid.UUID,
    counsellor_id: Optional[str] = None,
    limit: int = 3,
    pre_fetched_extraction: Optional[Dict[str, Any]] = None,
    counsellor_ids: Optional[List[str]] = None,
    include_assistant: bool = False,
) -> List[InterventionSummary]:
    """
    Get top N recommended interventions from the most recent NON-PRESCREEN consultation.

    Args:
        patient_uuid: Student UUID
        counsellor_id: Optional counsellor ID filter
        limit: Maximum number of interventions to return (default: 3)
        pre_fetched_extraction: Optional pre-fetched latest non-PRESCREEN extraction
        counsellor_ids: Optional list — when provided (school_view mode), filters by
            counsellor_id IN (counsellor_ids) and overrides `counsellor_id`.
        include_assistant: When True, assistant-initiated extractions are not skipped.

    Returns:
        List of InterventionSummary objects
    """
    extraction_id = None

    if pre_fetched_extraction:
        extraction_id = pre_fetched_extraction["id"]
    else:
        # Fallback: fetch from DB (used when called outside prescreen endpoint)
        query = supabase.table("extractions")\
            .select("id, recording_sessions(template_code, assistant_id)")\
            .eq("student_id", str(patient_uuid))\
            .order("created_at", desc=True)

        if counsellor_ids is not None:
            if not counsellor_ids:
                return []
            query = query.in_("counsellor_id", counsellor_ids)
        elif counsellor_id:
            query = query.eq("counsellor_id", counsellor_id)

        query = query.limit(5)
        result_data = query.execute()

        if result_data.data:
            for ext in result_data.data:
                if include_assistant or not is_assistant_extraction(ext):
                    extraction_id = ext["id"]
                    break

        if not extraction_id:
            extraction = get_latest_extraction_for_student(
                patient_uuid, counsellor_id,
                counsellor_ids=counsellor_ids, include_assistant=include_assistant,
            )
            if not extraction:
                return []
            extraction_id = extraction["id"]

    # Get interventions for this extraction
    interventions_result = supabase.table("student_interventions")\
        .select("*, intervention_definitions(intervention_name, description, category)")\
        .eq("extraction_id", extraction_id)\
        .eq("is_top_recommendation", True)\
        .order("priority_score", desc=True)\
        .limit(limit)\
        .execute()

    interventions = []
    for i in (interventions_result.data or []):
        intervention_def = i.get("intervention_definitions") or {}
        interventions.append(InterventionSummary(
            id=i["id"],
            code=i.get("intervention_code", ""),
            name=intervention_def.get("intervention_name", ""),
            description=intervention_def.get("description", ""),
            category=intervention_def.get("category", "general"),
            priority=i.get("priority_level", "medium").lower(),
            priority_score=i.get("priority_score", 50),
            trigger_reason=i.get("trigger_reason", ""),
            is_top_3=True
        ))

    return interventions


def get_caution_and_summary_from_last_extraction(
    patient_uuid: uuid.UUID,
    counsellor_id: Optional[str] = None,
    pre_fetched_extraction: Optional[Dict[str, Any]] = None,
    counsellor_ids: Optional[List[str]] = None,
    include_assistant: bool = False,
) -> Dict[str, Any]:
    """
    Get CAUTION and SUMMARY segments from student's last NON-PRESCREEN extraction.

    Args:
        patient_uuid: Student UUID
        counsellor_id: Optional counsellor ID filter
        pre_fetched_extraction: Optional pre-fetched latest non-PRESCREEN extraction
        counsellor_ids: Optional list — when provided (school_view mode), filters by
            counsellor_id IN (counsellor_ids) and overrides `counsellor_id`.
        include_assistant: When True, assistant-initiated extractions are not skipped.

    Returns:
        Dict with caution, caution_date, summary, summary_date, extraction_id
    """
    result: Dict[str, Any] = {
        "caution": None,
        "caution_date": None,
        "summary": None,
        "summary_date": None,
        "extraction_id": None
    }

    if pre_fetched_extraction:
        extraction = pre_fetched_extraction
    else:
        # Fallback: fetch from DB (used when called outside prescreen endpoint)
        query = supabase.table("extractions")\
            .select("*, recording_sessions(template_code, assistant_id)")\
            .eq("student_id", str(patient_uuid))\
            .order("created_at", desc=True)

        if counsellor_ids is not None:
            if not counsellor_ids:
                return result
            query = query.in_("counsellor_id", counsellor_ids)
        elif counsellor_id:
            query = query.eq("counsellor_id", counsellor_id)

        query = query.limit(5)
        result_data = query.execute()

        extraction = None
        if result_data.data:
            for ext in result_data.data:
                if include_assistant or not is_assistant_extraction(ext):
                    extraction = ext
                    break

        if not extraction:
            extraction = get_latest_extraction_for_student(
                patient_uuid, counsellor_id,
                counsellor_ids=counsellor_ids, include_assistant=include_assistant,
            )
            if not extraction:
                return result

    extraction_id = extraction["id"]
    extraction_date = extraction.get("created_at", "")[:10] if extraction.get("created_at") else None
    result["extraction_id"] = extraction_id

    # Batch fetch CAUTION and SUMMARY in a single query
    segments = get_segments_batch([extraction_id], ["CAUTION", "SUMMARY"])
    ext_segments = segments.get(extraction_id, {})

    caution = ext_segments.get("CAUTION")
    if caution:
        result["caution"] = caution
        result["caution_date"] = extraction_date

    summary = ext_segments.get("SUMMARY")
    if summary:
        result["summary"] = summary
        result["summary_date"] = extraction_date

    return result


def get_latest_assistant_extraction(
    patient_uuid: uuid.UUID,
    counsellor_id: str
) -> Optional[Dict[str, Any]]:
    """
    Get the latest assistant-initiated extraction for a student.

    Assistant extractions are identified by:
    1. recording_sessions.assistant_id IS NOT NULL (primary)
    2. template_code containing 'PRESCREEN' (legacy fallback for records with NULL assistant_id)

    Args:
        patient_uuid: Student UUID
        counsellor_id: Counsellor ID (required for lookup)

    Returns:
        Extraction record or None if no assistant extraction found
    """
    # Fetch recent extractions and filter in Python (PostgREST can't filter on FK assistant_id reliably)
    query = supabase.table("extractions")\
        .select("*, recording_sessions!inner(template_code, template_name, assistant_id)")\
        .eq("student_id", str(patient_uuid))\
        .eq("counsellor_id", counsellor_id)\
        .order("created_at", desc=True)\
        .limit(5)

    result = query.execute()

    if not result.data:
        return None

    # Primary: find extraction with assistant_id set
    for ext in result.data:
        rs = ext.get("recording_sessions") or {}
        if isinstance(rs, list) and rs:
            rs = rs[0]
        if rs.get("assistant_id"):
            return ext

    # Legacy fallback: find PRESCREEN template extraction
    for ext in result.data:
        rs = ext.get("recording_sessions") or {}
        if isinstance(rs, list) and rs:
            rs = rs[0]
        template_code = rs.get("template_code", "") or ""
        if template_code and "PRESCREEN" in template_code.upper():
            return ext

    return None


# Legacy alias
get_latest_prescreen_extraction = get_latest_assistant_extraction


def build_clinical_timeline_data(
    patient_uuid: uuid.UUID,
    counsellor_id: Optional[str] = None,
    num_visits: int = 5,
    pre_fetched_extractions: Optional[List[Dict[str, Any]]] = None,
    counsellor_ids: Optional[List[str]] = None,
    include_assistant: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Build clinical timeline data for a student.

    Args:
        patient_uuid: Student UUID
        counsellor_id: Optional counsellor ID filter
        num_visits: Number of visits to include (default 5)
        pre_fetched_extractions: Optional pre-fetched non-PRESCREEN extractions
        counsellor_ids: Optional list — when provided (school_view mode), filters by
            counsellor_id IN (counsellor_ids) and overrides `counsellor_id`.
        include_assistant: When True, assistant-initiated extractions are not filtered out.

    Returns:
        Dict with timeline, summary, and visit_count, or None if no data
    """
    try:
        if pre_fetched_extractions is not None:
            extractions = pre_fetched_extractions[:num_visits]
        else:
            # Fallback: fetch from DB (used when called outside prescreen endpoint)
            query = supabase.table("extractions")\
                .select("*, recording_sessions(template_code, assistant_id)")\
                .eq("student_id", str(patient_uuid))\
                .order("created_at", desc=True)

            if counsellor_ids is not None:
                if not counsellor_ids:
                    return {
                        "timeline": [],
                        "summary": {
                            "total_visits": 0,
                            "first_time_diagnoses": 0,
                            "recurring_diagnoses": 0,
                            "medication_changes": 0,
                            "resolved_complaints": 0,
                        },
                        "visit_count": 0,
                    }
                query = query.in_("counsellor_id", counsellor_ids)
            elif counsellor_id:
                query = query.eq("counsellor_id", counsellor_id)

            query = query.limit(num_visits * 2)
            result = query.execute()
            if include_assistant:
                extractions = (result.data or [])[:num_visits]
            else:
                extractions = filter_prescreen_extractions(result.data or [], max_results=num_visits)

        if len(extractions) < 1:
            return {
                "timeline": [],
                "summary": {
                    "total_visits": 0,
                    "first_time_diagnoses": 0,
                    "recurring_diagnoses": 0,
                    "medication_changes": 0,
                    "resolved_complaints": 0
                },
                "visit_count": 0
            }

        # Get historical diagnoses for "first time" detection (limit to last 30)
        all_extractions_result = supabase.table("extractions")\
            .select("original_extraction_json, edited_extraction_json, created_at, recording_sessions(template_code, assistant_id)")\
            .eq("student_id", str(patient_uuid))\
            .order("created_at", desc=True)\
            .limit(30)\
            .execute()

        # Filter out PRESCREEN extractions
        all_non_prescreen = filter_prescreen_extractions(all_extractions_result.data or [])

        all_historical_diagnoses = set()
        for ext in all_non_prescreen:
            data = ext.get("edited_extraction_json") or ext.get("original_extraction_json") or {}
            diagnosis = find_segment_value(data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge')
            for dx in extract_diagnosis_list(diagnosis):
                all_historical_diagnoses.add(normalize_diagnosis_name(dx.get('name', '')))

        # Process extractions (newest to oldest)
        timeline_visits = []
        visit_dates = [ext["created_at"] for ext in extractions]

        # Summary counters
        first_time_count = 0
        recurring_count = 0
        medication_change_count = 0
        resolved_complaint_count = 0

        for i, ext in enumerate(extractions):
            data = get_extraction_data(ext)
            visit_date = ext["created_at"]

            # Extract current visit data
            diagnosis_data = find_segment_value(data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge')
            complaints_data = extract_chief_complaints(data)
            # Use shared utility to find prescription from all locations (including treatmentPlan)
            prescription_data = find_prescription_in_extraction(data)

            current_diagnoses = extract_diagnosis_list(diagnosis_data)
            current_complaints = extract_complaints_list(complaints_data)
            current_medications = extract_medicines_list(prescription_data)

            # Get previous visits data
            previous_medications = []
            previous_complaints = []
            two_visits_ago_complaints = []

            if i + 1 < len(extractions):
                prev_data = get_extraction_data(extractions[i + 1])
                prev_prescription = find_prescription_in_extraction(prev_data)
                prev_complaints_data = extract_chief_complaints(prev_data)
                previous_medications = extract_medicines_list(prev_prescription)
                previous_complaints = extract_complaints_list(prev_complaints_data)

            if i + 2 < len(extractions):
                two_ago_data = get_extraction_data(extractions[i + 2])
                two_ago_complaints_data = extract_chief_complaints(two_ago_data)
                two_visits_ago_complaints = extract_complaints_list(two_ago_complaints_data)

            # Build recent window diagnoses (last 2 visits or 6 months)
            recent_window_diagnoses = set()
            for j, prev_ext in enumerate(extractions):
                if j == i:  # Skip current visit
                    continue
                if j > i and is_within_recent_window(prev_ext["created_at"], visit_date, visit_dates[i+1:], max_visits=2, max_months=6):
                    prev_data = get_extraction_data(prev_ext)
                    prev_diagnosis = find_segment_value(prev_data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge')
                    for dx in extract_diagnosis_list(prev_diagnosis):
                        recent_window_diagnoses.add(normalize_diagnosis_name(dx.get('name', '')))

            # Detect changes
            changes = []

            # Diagnosis changes
            diagnosis_changes = detect_diagnosis_changes_local(
                current_diagnoses,
                [],  # Not used in current implementation
                all_historical_diagnoses - {normalize_diagnosis_name(dx.get('name', '')) for dx in current_diagnoses},
                recent_window_diagnoses
            )
            changes.extend(diagnosis_changes)
            first_time_count += len([c for c in diagnosis_changes if c.type == "first_time_diagnosis"])
            recurring_count += len([c for c in diagnosis_changes if c.type == "recurring_diagnosis"])

            # Medication changes (only if not first visit)
            if previous_medications:
                med_changes = detect_medication_changes_local(current_medications, previous_medications)
                changes.extend(med_changes)
                medication_change_count += len(med_changes)

            # Complaint changes (only if not first visit)
            if previous_complaints:
                current_diagnoses_normalized = {normalize_diagnosis_name(dx.get('name', '')) for dx in current_diagnoses}
                complaint_changes = detect_complaint_changes_local(
                    current_complaints,
                    previous_complaints,
                    two_visits_ago_complaints,
                    current_diagnoses_normalized
                )
                changes.extend(complaint_changes)
                resolved_complaint_count += len([c for c in complaint_changes if c.type == "complaint_resolved"])

            # Get metadata
            ct_name = get_consultation_type_name(ext["consultation_type_id"]) if ext.get("consultation_type_id") else None
            counsellor_name = get_counsellor_name(ext["counsellor_id"]) if ext.get("counsellor_id") else None

            timeline_visits.append({
                "extraction_id": ext["id"],
                "visit_date": visit_date,
                "consultation_type": ct_name,
                "counsellor_name": counsellor_name,
                "changes": [{"type": c.type, "name": c.name, "details": c.details, "confidence": c.confidence} for c in changes],
                "diagnoses": [dx.get('name', '') for dx in current_diagnoses],
                "complaints": current_complaints,
                "medications": [{"name": m.get('name', ''), "dosage": m.get('dosage', '')} for m in current_medications],
                "has_significant_changes": len([c for c in changes if c.confidence in ['high', 'medium']]) > 0
            })

        # Reverse to get chronological order (oldest first)
        timeline_visits.reverse()

        return {
            "timeline": timeline_visits,
            "summary": {
                "total_visits": len(timeline_visits),
                "first_time_diagnoses": first_time_count,
                "recurring_diagnoses": recurring_count,
                "medication_changes": medication_change_count,
                "resolved_complaints": resolved_complaint_count
            },
            "visit_count": len(timeline_visits)
        }

    except Exception as e:
        logger.error(f"Error building clinical timeline data: {e}")
        return None


def get_last_prescription_for_prescreen(
    patient_uuid: uuid.UUID,
    counsellor_id: Optional[str] = None,
    pre_fetched_extraction: Optional[Dict[str, Any]] = None,
    counsellor_ids: Optional[List[str]] = None,
    include_assistant: bool = False,
) -> Dict[str, Any]:
    """
    Get the last prescription for a student from a NON-PRESCREEN extraction.

    Args:
        patient_uuid: Student UUID
        counsellor_id: Optional counsellor ID filter
        pre_fetched_extraction: Optional pre-fetched latest non-PRESCREEN extraction
        counsellor_ids: Optional list — when provided (school_view mode), filters by
            counsellor_id IN (counsellor_ids) and overrides `counsellor_id`.
        include_assistant: When True, assistant-initiated extractions are not skipped.

    Returns:
        Dict with prescription data and date, or empty values if not found
    """
    result = {
        "prescription": None,
        "prescription_date": None
    }

    try:
        if pre_fetched_extraction:
            extraction = pre_fetched_extraction
        else:
            # Fallback: fetch from DB (used when called outside prescreen endpoint)
            query = supabase.table("extractions")\
                .select("*, recording_sessions(template_code, assistant_id)")\
                .eq("student_id", str(patient_uuid))\
                .order("created_at", desc=True)

            if counsellor_ids is not None:
                if not counsellor_ids:
                    return result
                query = query.in_("counsellor_id", counsellor_ids)
            elif counsellor_id:
                query = query.eq("counsellor_id", counsellor_id)

            query = query.limit(5)
            result_data = query.execute()

            extraction = None
            if result_data.data:
                for ext in result_data.data:
                    if include_assistant or not is_assistant_extraction(ext):
                        extraction = ext
                        break

            if not extraction:
                extraction = get_latest_extraction_for_student(
                    patient_uuid, counsellor_id,
                    counsellor_ids=counsellor_ids, include_assistant=include_assistant,
                )
                if not extraction:
                    return result

        data = get_extraction_data(extraction)
        prescription = find_prescription_in_extraction(data)

        if prescription:
            result["prescription"] = prescription
            result["prescription_date"] = extraction.get("created_at", "")[:10] if extraction.get("created_at") else None

        return result

    except Exception as e:
        logger.error(f"Error getting last prescription: {e}")
        return result


# ============================================================================
# API Endpoints - Student Create
# ============================================================================

@router.post("", response_model=StudentCreateResponse)
async def create_student(
    request: Request,
    body: StudentCreateRequest,
    _auth = Depends(verify_authenticated)
):
    """
    Create a new student or return existing if student_id already exists.

    **Authentication:** Requires valid auth (admin, web user, or EHR API key).

    **Fields:**
    - student_id: Required - External identifier (UHID/MRN)
    - full_name: Student's full name
    - date_of_birth: Birth date in ISO format (YYYY-MM-DD)
    - gender: M/F
    - ip_id: Inpatient visit ID
    - op_id: Outpatient visit ID
    - counsellor_ids: Array of counsellor UUIDs to link student to
    - add_info: Additional metadata as JSON object

    **Behavior:**
    - If student_id already exists, returns existing student with created=False
    - If student_id is new, creates student and returns with created=True
    """
    try:
        # Derive school_id from auth context or first counsellor_id
        create_school_id = _get_school_id_from_context(request, body.counsellor_ids[0] if body.counsellor_ids else None)

        # Check if student already exists (scoped by school)
        check_query = supabase.table("students").select("*").eq("student_id", body.student_id)
        if create_school_id:
            check_query = check_query.eq("school_id", create_school_id)
        existing = check_query.execute()

        if existing.data:
            # Student exists - return it
            return StudentCreateResponse(
                success=True,
                patient=existing.data[0],
                created=False,
                message=f"Student with ID {body.student_id} already exists"
            )

        # Build student data
        student_data = {
            "student_id": body.student_id,
            "is_anonymized": False
        }

        if create_school_id:
            student_data["school_id"] = create_school_id
        if body.full_name:
            student_data["full_name"] = body.full_name
        if body.date_of_birth:
            student_data["date_of_birth"] = body.date_of_birth
        if body.gender:
            student_data["gender"] = body.gender
        if body.ip_id:
            student_data["ip_id"] = body.ip_id
        if body.op_id:
            student_data["op_id"] = body.op_id
        if body.counsellor_ids:
            student_data["counsellor_ids"] = body.counsellor_ids
        if body.add_info:
            student_data["add_info"] = body.add_info

        # Create new student
        result = supabase.table("students").insert(student_data).execute()

        if result.data:
            logger.info(f"[PATIENT_CREATE] Created student {body.student_id}")
            return StudentCreateResponse(
                success=True,
                patient=result.data[0],
                created=True,
                message=f"Student {body.student_id} created successfully"
            )
        else:
            return StudentCreateResponse(
                success=False,
                created=False,
                message="Failed to create student - no data returned"
            )

    except Exception as e:
        logger.error(f"[PATIENT_CREATE] Error creating student {body.student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create student")


# ============================================================================
# API Endpoints - Student Search
# ============================================================================

# Counsellor SKS ID - triggers neopaed student initialization
DOCTOR_SKS_ID = "397f4efe-fd79-41d1-9b0b-d3cc884cda62"

@router.get("/search", response_model=StudentSearchResponse)
async def search_students(
    request: Request,
    query: Optional[str] = Query(None, description="Search by name or student ID"),
    counsellor_id: str = Query(..., description="Counsellor ID (required for EHR access)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _auth = Depends(verify_counsellor_access)
):
    """
    Search for students by name or external student ID.

    Returns students with consultation count and last visit date.
    Optimized to minimize database queries.

    **Note:** counsellor_id is required for EHR access control.
    **Special:** For Counsellor SKS, automatically syncs students from Neopaed school system.
    """
    try:
        offset = (page - 1) * page_size

        # For Counsellor SKS, initialize/sync students from Neopaed school system (both NICU + OP)
        if counsellor_id == DOCTOR_SKS_ID:
            logger.info("[PATIENT_SEARCH] Counsellor SKS - initializing Neopaed students (NICU + OP)")
            try:
                init_result = await fetch_all_neopaed_students()
                if init_result.get("success"):
                    nicu = init_result.get("nicu", {})
                    op = init_result.get("op", {})
                    logger.info(
                        f"[PATIENT_SEARCH] Neopaed sync: "
                        f"NICU({nicu.get('created', 0)} created, {nicu.get('updated', 0)} updated), "
                        f"OP({op.get('created', 0)} created, {op.get('updated', 0)} updated)"
                    )
                else:
                    logger.warning(f"[PATIENT_SEARCH] Neopaed sync failed: {init_result.get('error')}")
            except Exception as e:
                logger.error(f"[PATIENT_SEARCH] Neopaed sync error: {e}")

        # If counsellor_id is provided, get students directly from extractions (more efficient)
        if counsellor_id:
            # Get all extractions for this counsellor with student info in one query
            ext_result = supabase.table("extractions")\
                .select("student_id, created_at, students!inner(id, student_id, full_name, date_of_birth, gender, school_id)")\
                .eq("counsellor_id", counsellor_id)\
                .order("created_at", desc=True)\
                .execute()

            # Aggregate by student
            student_stats: Dict[str, Dict] = {}
            for ext in (ext_result.data or []):
                student_data = ext.get("students")
                if not student_data:
                    continue

                pid = student_data["id"]
                if pid not in student_stats:
                    student_stats[pid] = {
                        "patient": student_data,
                        "count": 0,
                        "last_visit": ext["created_at"]
                    }
                student_stats[pid]["count"] += 1

            # Include students who have this counsellor in their counsellor_ids array
            # Uses PostgreSQL array contains operator
            counsellor_linked_result = supabase.table("students")\
                .select("id, student_id, full_name, date_of_birth, gender, add_info, counsellor_ids, school_id, updated_at")\
                .contains("counsellor_ids", [counsellor_id])\
                .execute()

            for p in (counsellor_linked_result.data or []):
                pid = p["id"]
                if pid not in student_stats:
                    # Add student without any consultations (linked via counsellor_ids)
                    student_stats[pid] = {
                        "patient": {
                            "id": p["id"],
                            "student_id": p["student_id"],
                            "full_name": p.get("full_name"),
                            "date_of_birth": p.get("date_of_birth"),
                            "gender": p.get("gender"),
                            "add_info": p.get("add_info"),
                            "school_id": p.get("school_id")
                        },
                        "count": 0,
                        "last_visit": None
                    }

            # For Counsellor SKS, also include Neopaed students who may not have extractions yet
            if counsellor_id == DOCTOR_SKS_ID:
                neopaed_result = supabase.table("students")\
                    .select("id, student_id, full_name, date_of_birth, gender, add_info, school_id, updated_at")\
                    .not_.is_("add_info", "null")\
                    .execute()

                for p in (neopaed_result.data or []):
                    # Check if this is a neopaed-sourced student (NICU or OP)
                    add_info = p.get("add_info") or {}
                    source = add_info.get("source", "")
                    if source in ("neopaed_api", "neopaed_op_api"):
                        pid = p["id"]
                        if pid not in student_stats:
                            # Add student without any consultations
                            student_stats[pid] = {
                                "patient": {
                                    "id": p["id"],
                                    "student_id": p["student_id"],
                                    "full_name": p.get("full_name"),
                                    "date_of_birth": p.get("date_of_birth"),
                                    "gender": p.get("gender"),
                                    "add_info": add_info,  # Include for room/bed info
                                    "school_id": p.get("school_id")
                                },
                                "count": 0,
                                "last_visit": None
                            }

            # Filter by query if provided
            if query:
                query_lower = query.lower()
                student_stats = {
                    pid: stats for pid, stats in student_stats.items()
                    if (stats["patient"].get("full_name") or "").lower().find(query_lower) >= 0 or
                       (stats["patient"].get("student_id") or "").lower().find(query_lower) >= 0
                }

            # Sort by last visit (most recent first), students without visits at the end
            sorted_students = sorted(
                student_stats.values(),
                key=lambda x: (x["last_visit"] is not None, x["last_visit"] or ""),
                reverse=True
            )

            total_count = len(sorted_students)
            paginated = sorted_students[offset:offset + page_size]

            # Resolve school names for paginated students
            school_ids = list(set(
                p["patient"].get("school_id")
                for p in paginated
                if p["patient"].get("school_id")
            ))
            school_names: Dict[str, str] = {}
            if school_ids:
                try:
                    h_result = supabase.table("schools")\
                        .select("id, school_name")\
                        .in_("id", school_ids)\
                        .execute()
                    school_names = {h["id"]: h["school_name"] for h in (h_result.data or [])}
                except Exception as e:
                    logger.warning(f"[PATIENT_SEARCH] Failed to resolve school names: {e}")

            results = [
                StudentSearchResult(
                    id=p["patient"]["id"],
                    student_id=p["patient"]["student_id"],
                    full_name=p["patient"].get("full_name"),
                    date_of_birth=p["patient"].get("date_of_birth"),
                    gender=p["patient"].get("gender"),
                    consultation_count=p["count"],
                    last_visit_date=p["last_visit"],
                    add_info=p["patient"].get("add_info"),
                    school_id=p["patient"].get("school_id"),
                    school_name=school_names.get(p["patient"].get("school_id") or "", None)
                )
                for p in paginated
            ]

        else:
            # No counsellor filter - search all students
            base_query = supabase.table("students")\
                .select("id, student_id, full_name, date_of_birth, gender, school_id")

            if query:
                base_query = base_query.or_(
                    f"student_id.ilike.%{query}%,full_name.ilike.%{query}%"
                )

            count_result = base_query.execute()
            all_patients = count_result.data or []
            total_count = len(all_patients)

            # Paginate first, then enrich only paginated results
            paginated_students = all_patients[offset:offset + page_size]

            if paginated_students:
                # Get consultation stats for paginated students in one query
                student_ids = [p["id"] for p in paginated_students]
                ext_result = supabase.table("extractions")\
                    .select("student_id, created_at")\
                    .in_("student_id", student_ids)\
                    .order("created_at", desc=True)\
                    .execute()

                # Aggregate stats per student
                student_stats: Dict[str, Dict] = {}
                for ext in (ext_result.data or []):
                    pid = ext["student_id"]
                    if pid not in student_stats:
                        student_stats[pid] = {"count": 0, "last_visit": ext["created_at"]}
                    student_stats[pid]["count"] += 1

                # Resolve school names
                h_ids = list(set(p.get("school_id") for p in paginated_students if p.get("school_id")))
                h_names: Dict[str, str] = {}
                if h_ids:
                    try:
                        h_result = supabase.table("schools")\
                            .select("id, school_name")\
                            .in_("id", h_ids)\
                            .execute()
                        h_names = {h["id"]: h["school_name"] for h in (h_result.data or [])}
                    except Exception as e:
                        logger.warning(f"[PATIENT_SEARCH] Failed to resolve school names: {e}")

                results = [
                    StudentSearchResult(
                        id=p["id"],
                        student_id=p["student_id"],
                        full_name=p.get("full_name"),
                        date_of_birth=p.get("date_of_birth"),
                        gender=p.get("gender"),
                        consultation_count=student_stats.get(p["id"], {}).get("count", 0),
                        last_visit_date=student_stats.get(p["id"], {}).get("last_visit"),
                        school_id=p.get("school_id"),
                        school_name=h_names.get(p.get("school_id") or "", None)
                    )
                    for p in paginated_students
                ]
            else:
                results = []

        return StudentSearchResponse(
            students=results,
            total_count=total_count,
            page=page,
            page_size=page_size,
            has_more=(offset + page_size) < total_count
        )

    except Exception as e:
        logger.error(f"Error searching students: {e}")
        raise HTTPException(status_code=500, detail="Failed to search students")


# ============================================================================
# API Endpoints - Student History
# ============================================================================

@router.get("/{student_id}/consultations", response_model=ConsultationHistoryResponse)
async def get_consultation_history(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _auth = Depends(verify_student_access)
):
    """
    Get consultation history for a student.

    Returns a paginated list of all consultations with quick preview info.
    """
    try:
        # Fix 1: Single query for student resolution + info (saves 1-2 round-trips)
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid, patient_info = resolve_student_with_info_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        offset = (page - 1) * page_size
        loop = asyncio.get_event_loop()

        # Fix 2: Run count + data queries in parallel (saves ~50-150ms)
        def _apply_counsellor_filter(q):
            if view_counsellor_ids is not None:
                if not view_counsellor_ids:
                    return None  # signal: empty result
                return q.in_("counsellor_id", view_counsellor_ids)
            if counsellor_id:
                return q.eq("counsellor_id", counsellor_id)
            return q

        def _fetch_count():
            q = supabase.table("extractions")\
                .select("id", count="exact")\
                .eq("student_id", str(patient_uuid))
            q = _apply_counsellor_filter(q)
            if q is None:
                return type("R", (), {"count": 0})()
            return q.execute()

        def _fetch_extractions():
            q = supabase.table("extractions")\
                .select(
                    "id, session_id, consultation_type_id, counsellor_id, created_at, "
                    "edit_count, segment_count, emotion_extraction_completed, "
                    "recording_metadata_json"
                )\
                .eq("student_id", str(patient_uuid))\
                .order("created_at", desc=True)
            q = _apply_counsellor_filter(q)
            if q is None:
                return type("R", (), {"data": []})()
            q = q.range(offset, offset + page_size - 1)
            return q.execute()

        count_result, data_result = await asyncio.gather(
            loop.run_in_executor(_prescreen_executor, _fetch_count),
            loop.run_in_executor(_prescreen_executor, _fetch_extractions),
        )

        total_count = count_result.count or 0
        extractions = data_result.data or []

        # Fix 3: Run batch lookups in parallel (saves ~50-150ms)
        # Fix 4: Fetch only diagnosis/chief complaint segments instead of full JSON blobs
        counsellor_ids = list(set(ext.get("counsellor_id") for ext in extractions if ext.get("counsellor_id")))
        ct_ids = list(set(ext.get("consultation_type_id") for ext in extractions if ext.get("consultation_type_id")))
        extraction_ids = [ext["id"] for ext in extractions]

        def _fetch_preview_segments():
            if not extraction_ids:
                return {}
            return get_segments_batch(
                extraction_ids,
                ["diagnosis", "diagnosisOp", "diagnosisDischarge",
                 "chiefComplaints", "chiefComplaintsOp", "complaints", "chief_complaints"]
            )

        # Map session_id → latest processing_jobs.submission_id so the frontend
        # can call PUT /iframe/edit/{submission_id} without a round-trip.
        session_ids = [ext.get("session_id") for ext in extractions if ext.get("session_id")]

        def _fetch_submission_ids():
            if not session_ids:
                return {}
            res = supabase.table("processing_jobs")\
                .select("session_id, submission_id, created_at")\
                .in_("session_id", session_ids)\
                .order("created_at", desc=True)\
                .execute()
            out: Dict[str, str] = {}
            for row in (res.data or []):
                sid = row.get("session_id")
                if sid and sid not in out and row.get("submission_id"):
                    out[sid] = row["submission_id"]
            return out

        counsellor_names_map, ct_names_map, segments_map, submission_ids_map = await asyncio.gather(
            loop.run_in_executor(_prescreen_executor, batch_get_counsellor_names, counsellor_ids),
            loop.run_in_executor(_prescreen_executor, batch_get_consultation_type_names, ct_ids),
            loop.run_in_executor(_prescreen_executor, _fetch_preview_segments),
            loop.run_in_executor(_prescreen_executor, _fetch_submission_ids),
        )

        # Build consultation items using segments_map for previews (no JSON blobs needed)
        consultations = []
        for ext in extractions:
            ext_id = ext["id"]
            ext_segments = segments_map.get(ext_id, {})

            # Get diagnosis preview from segments
            diagnosis = (ext_segments.get("DIAGNOSIS") or ext_segments.get("DIAGNOSISOP")
                         or ext_segments.get("DIAGNOSISDISCHARGE"))
            primary_diagnosis = None
            if isinstance(diagnosis, list) and len(diagnosis) > 0:
                if isinstance(diagnosis[0], dict):
                    primary_diagnosis = diagnosis[0].get('name') or diagnosis[0].get('primary_diagnosis')
                else:
                    primary_diagnosis = str(diagnosis[0])
            elif isinstance(diagnosis, dict):
                primary_diagnosis = diagnosis.get('primary_diagnosis') or diagnosis.get('name')
            elif isinstance(diagnosis, str):
                primary_diagnosis = diagnosis[:100]

            # Get chief complaint preview from segments
            complaints = (ext_segments.get("CHIEFCOMPLAINTS") or ext_segments.get("CHIEFCOMPLAINTSOP")
                          or ext_segments.get("COMPLAINTS") or ext_segments.get("CHIEF_COMPLAINTS"))
            chief_complaint = None
            if isinstance(complaints, dict):
                chief_complaint = complaints.get('primary_complaint') or complaints.get('main_complaint')
            elif isinstance(complaints, list) and len(complaints) > 0:
                chief_complaint = str(complaints[0]) if not isinstance(complaints[0], dict) else complaints[0].get('complaint')
            elif isinstance(complaints, str):
                chief_complaint = complaints[:100]

            # Use batch-fetched names (O(1) lookup instead of DB query)
            ext_counsellor_id = ext.get("counsellor_id")
            ext_ct_id = ext.get("consultation_type_id")

            _ext_rec_meta = ext.get("recording_metadata_json") or {}
            if not isinstance(_ext_rec_meta, dict):
                _ext_rec_meta = {}

            consultations.append(ConsultationHistoryItem(
                extraction_id=ext_id,
                session_id=ext.get("session_id"),
                submission_id=submission_ids_map.get(ext.get("session_id")),
                consultation_type=ext_ct_id,
                consultation_type_name=ct_names_map.get(ext_ct_id) if ext_ct_id else None,
                counsellor_id=ext_counsellor_id,
                counsellor_name=counsellor_names_map.get(ext_counsellor_id) if ext_counsellor_id else None,
                created_at=ext["created_at"],
                is_edited=(ext.get("edit_count") or 0) > 0,
                has_emotion_analysis=ext.get("emotion_extraction_completed", False) or False,
                segment_count=ext.get("segment_count", 0),
                role=_ext_rec_meta.get("role") or None,
                primary_diagnosis=primary_diagnosis,
                chief_complaint=chief_complaint
            ))

        # HIPAA Audit: log student consultation history access
        client_ctx = getattr(request.state, "client", None)
        if client_ctx:
            try:
                asyncio.create_task(audit_service.log_phi_access(
                    client_context=client_ctx, request=request, response_status=200,
                    response_time_ms=0, resource_type="patient", action="read",
                    student_id=student_id,
                ))
            except Exception:
                pass

        return ConsultationHistoryResponse(
            patient=StudentInfo(
                id=patient_info["id"],
                student_id=patient_info["student_id"],
                full_name=patient_info.get("full_name"),
                date_of_birth=patient_info.get("date_of_birth"),
                gender=patient_info.get("gender")
            ),
            consultations=consultations,
            total_count=total_count,
            page=page,
            page_size=page_size,
            has_more=(offset + page_size) < total_count
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting consultation history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get consultation history")


@router.get("/{student_id}/consultations/latest", response_model=ConsultationHistoryResponse)
async def get_latest_consultations(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _auth = Depends(verify_student_access)
):
    """
    Get latest consultations for a student, de-duplicated by continuation chain.

    Returns only standalone extractions and the latest extraction in each
    continuation chain. Parent extractions that have been superseded by a
    continuation are excluded.

    Logic: exclude any extraction whose ID appears in another extraction's
    parent_extraction_ids array for the same student.
    """
    try:
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid, patient_info = resolve_student_with_info_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)
        student_uuid_str = str(patient_uuid)

        loop = asyncio.get_event_loop()

        # Step 1+2: Run exclusion set + extraction fetch in parallel (2 independent queries)
        def _fetch_all_parent_ids():
            result = supabase.table("extractions")\
                .select("parent_extraction_ids")\
                .eq("student_id", student_uuid_str)\
                .neq("parent_extraction_ids", "{}")\
                .execute()
            excluded = set()
            for row in (result.data or []):
                for pid in (row.get("parent_extraction_ids") or []):
                    excluded.add(str(pid))
            return excluded

        def _fetch_extractions():
            query = supabase.table("extractions")\
                .select(
                    "id, session_id, consultation_type_id, counsellor_id, created_at, "
                    "edit_count, segment_count, emotion_extraction_completed, "
                    "is_continuation, parent_extraction_ids"
                )\
                .eq("student_id", student_uuid_str)\
                .order("created_at", desc=True)
            if view_counsellor_ids is not None:
                if not view_counsellor_ids:
                    return type("R", (), {"data": []})()
                query = query.in_("counsellor_id", view_counsellor_ids)
            elif counsellor_id:
                query = query.eq("counsellor_id", counsellor_id)
            # Fetch extra rows to compensate for filtered-out parents
            query = query.limit(page_size * 3)
            return query.execute()

        excluded_ids, data_result = await asyncio.gather(
            loop.run_in_executor(_prescreen_executor, _fetch_all_parent_ids),
            loop.run_in_executor(_prescreen_executor, _fetch_extractions),
        )
        all_extractions = data_result.data or []

        # Step 3: Filter out parent extractions (keep only chain tips + standalone)
        filtered = [ext for ext in all_extractions if ext["id"] not in excluded_ids]

        # Paginate in-memory
        total_count = len(filtered)
        offset = (page - 1) * page_size
        page_extractions = filtered[offset:offset + page_size]

        # Step 4: Enrich with counsellor names, consultation type names, preview segments
        counsellor_ids_list = list(set(ext.get("counsellor_id") for ext in page_extractions if ext.get("counsellor_id")))
        ct_ids = list(set(ext.get("consultation_type_id") for ext in page_extractions if ext.get("consultation_type_id")))
        extraction_ids = [ext["id"] for ext in page_extractions]

        def _fetch_preview_segments():
            if not extraction_ids:
                return {}
            return get_segments_batch(
                extraction_ids,
                ["diagnosis", "diagnosisOp", "diagnosisDischarge",
                 "chiefComplaints", "chiefComplaintsOp", "complaints", "chief_complaints"]
            )

        # Map session_id → latest processing_jobs.submission_id so the frontend
        # can call PUT /iframe/edit/{submission_id} without a round-trip.
        session_ids = [ext.get("session_id") for ext in page_extractions if ext.get("session_id")]

        def _fetch_submission_ids():
            if not session_ids:
                return {}
            res = supabase.table("processing_jobs")\
                .select("session_id, submission_id, created_at")\
                .in_("session_id", session_ids)\
                .order("created_at", desc=True)\
                .execute()
            out: Dict[str, str] = {}
            for row in (res.data or []):
                sid = row.get("session_id")
                if sid and sid not in out and row.get("submission_id"):
                    out[sid] = row["submission_id"]
            return out

        counsellor_names_map, ct_names_map, segments_map, submission_ids_map = await asyncio.gather(
            loop.run_in_executor(_prescreen_executor, batch_get_counsellor_names, counsellor_ids_list),
            loop.run_in_executor(_prescreen_executor, batch_get_consultation_type_names, ct_ids),
            loop.run_in_executor(_prescreen_executor, _fetch_preview_segments),
            loop.run_in_executor(_prescreen_executor, _fetch_submission_ids),
        )

        # Step 5: Build response items
        consultations = []
        for ext in page_extractions:
            ext_id = ext["id"]
            ext_segments = segments_map.get(ext_id, {})

            # Diagnosis preview
            diagnosis = (ext_segments.get("DIAGNOSIS") or ext_segments.get("DIAGNOSISOP")
                         or ext_segments.get("DIAGNOSISDISCHARGE"))
            primary_diagnosis = None
            if isinstance(diagnosis, list) and len(diagnosis) > 0:
                if isinstance(diagnosis[0], dict):
                    primary_diagnosis = diagnosis[0].get('name') or diagnosis[0].get('primary_diagnosis')
                else:
                    primary_diagnosis = str(diagnosis[0])
            elif isinstance(diagnosis, dict):
                primary_diagnosis = diagnosis.get('primary_diagnosis') or diagnosis.get('name')
            elif isinstance(diagnosis, str):
                primary_diagnosis = diagnosis[:100]

            # Chief complaint preview
            complaints = (ext_segments.get("CHIEFCOMPLAINTS") or ext_segments.get("CHIEFCOMPLAINTSOP")
                          or ext_segments.get("COMPLAINTS") or ext_segments.get("CHIEF_COMPLAINTS"))
            chief_complaint = None
            if isinstance(complaints, dict):
                chief_complaint = complaints.get('primary_complaint') or complaints.get('main_complaint')
            elif isinstance(complaints, list) and len(complaints) > 0:
                chief_complaint = str(complaints[0]) if not isinstance(complaints[0], dict) else complaints[0].get('complaint')
            elif isinstance(complaints, str):
                chief_complaint = complaints[:100]

            ext_counsellor_id = ext.get("counsellor_id")
            ext_ct_id = ext.get("consultation_type_id")

            consultations.append(ConsultationHistoryItem(
                extraction_id=ext_id,
                session_id=ext.get("session_id"),
                submission_id=submission_ids_map.get(ext.get("session_id")),
                consultation_type=ext_ct_id,
                consultation_type_name=ct_names_map.get(ext_ct_id) if ext_ct_id else None,
                counsellor_id=ext_counsellor_id,
                counsellor_name=counsellor_names_map.get(ext_counsellor_id) if ext_counsellor_id else None,
                created_at=ext["created_at"],
                is_edited=(ext.get("edit_count") or 0) > 0,
                has_emotion_analysis=ext.get("emotion_extraction_completed", False) or False,
                segment_count=ext.get("segment_count", 0),
                primary_diagnosis=primary_diagnosis,
                chief_complaint=chief_complaint,
            ))

        # HIPAA Audit
        client_ctx = getattr(request.state, "client", None)
        if client_ctx:
            try:
                asyncio.create_task(audit_service.log_phi_access(
                    client_context=client_ctx, request=request, response_status=200,
                    response_time_ms=0, resource_type="patient", action="read",
                    student_id=student_id,
                ))
            except Exception:
                pass

        return ConsultationHistoryResponse(
            patient=StudentInfo(
                id=patient_info["id"],
                student_id=patient_info["student_id"],
                full_name=patient_info.get("full_name"),
                date_of_birth=patient_info.get("date_of_birth"),
                gender=patient_info.get("gender")
            ),
            consultations=consultations,
            total_count=total_count,
            page=page,
            page_size=page_size,
            has_more=(offset + page_size) < total_count,
        )

    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting latest consultations: {e}")
        raise HTTPException(status_code=500, detail="Failed to get latest consultations")


@router.get("/{student_id}/last-prescription", response_model=LastPrescriptionResponse)
async def get_last_prescription(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    _auth = Depends(verify_student_access)
):
    """
    Get the last prescription for a student.

    Searches through recent extractions to find the most recent prescription data.
    """
    try:
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid = resolve_student_id_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        # Get student info
        patient_info = get_student_info(patient_uuid)
        if not patient_info:
            raise HTTPException(status_code=404, detail="Student not found")

        patient = StudentInfo(
            id=patient_info["id"],
            student_id=patient_info["student_id"],
            full_name=patient_info.get("full_name"),
            date_of_birth=patient_info.get("date_of_birth"),
            gender=patient_info.get("gender")
        )

        # Find extraction with prescription
        # Keys include: main prescription, OP/Discharge variants, treatment plan, and drug-related keys
        prescription_keys = [
            'prescription', 'prescriptionOp', 'prescriptionDischarge',
            'treatmentPlan', 'medications', 'dischargeMedication',
            'drugs', 'drugDetails'  # Additional drug-related keys
        ]

        extraction = get_latest_extraction_with_segment(
            patient_uuid, prescription_keys, counsellor_id,
            counsellor_ids=view_counsellor_ids, include_assistant=school_view,
        )

        if not extraction:
            return LastPrescriptionResponse(patient=patient, found=False)

        data = get_extraction_data(extraction)
        # Use shared utility to find prescription from all locations (including treatmentPlan)
        prescription = find_prescription_in_extraction(data)

        # HIPAA Audit: log prescription access
        client_ctx = getattr(request.state, "client", None)
        if client_ctx:
            try:
                asyncio.create_task(audit_service.log_phi_access(
                    client_context=client_ctx, request=request, response_status=200,
                    response_time_ms=0, resource_type="patient", action="read",
                    student_id=student_id, phi_fields=["prescription"],
                ))
            except Exception:
                pass

        return LastPrescriptionResponse(
            patient=patient,
            prescription=prescription,
            metadata=build_extraction_metadata(extraction),
            found=prescription is not None
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting last prescription: {e}")
        raise HTTPException(status_code=500, detail="Failed to get last prescription")


@router.get("/{student_id}/last-diagnosis", response_model=LastDiagnosisResponse)
async def get_last_diagnosis(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    _auth = Depends(verify_student_access)
):
    """
    Get the last diagnosis for a student.
    """
    try:
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid = resolve_student_id_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        patient_info = get_student_info(patient_uuid)
        if not patient_info:
            raise HTTPException(status_code=404, detail="Student not found")

        patient = StudentInfo(
            id=patient_info["id"],
            student_id=patient_info["student_id"],
            full_name=patient_info.get("full_name"),
            date_of_birth=patient_info.get("date_of_birth"),
            gender=patient_info.get("gender"),
            preferred_language=patient_info.get("preferred_language"),
        )

        diagnosis_keys = ['diagnosis', 'diagnosisOp', 'diagnosisDischarge']
        extraction = get_latest_extraction_with_segment(
            patient_uuid, diagnosis_keys, counsellor_id,
            counsellor_ids=view_counsellor_ids, include_assistant=school_view,
        )

        if not extraction:
            return LastDiagnosisResponse(patient=patient, found=False)

        data = get_extraction_data(extraction)
        diagnosis = find_segment_value(data, *diagnosis_keys)

        return LastDiagnosisResponse(
            patient=patient,
            diagnosis=diagnosis,
            metadata=build_extraction_metadata(extraction),
            found=diagnosis is not None
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting last diagnosis: {e}")
        raise HTTPException(status_code=500, detail="Failed to get last diagnosis")


@router.get("/{student_id}/last-investigations-results", response_model=LastInvestigationsResponse)
async def get_last_investigations_results(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    _auth = Depends(verify_student_access)
):
    """
    Get the last investigation results for a student.

    Returns completed lab results, radiology findings, etc.
    """
    try:
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid = resolve_student_id_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        patient_info = get_student_info(patient_uuid)
        if not patient_info:
            raise HTTPException(status_code=404, detail="Student not found")

        patient = StudentInfo(
            id=patient_info["id"],
            student_id=patient_info["student_id"],
            full_name=patient_info.get("full_name"),
            date_of_birth=patient_info.get("date_of_birth"),
            gender=patient_info.get("gender")
        )

        # Keys for investigation results (includes 'investigations' which may contain results)
        # Also includes vitals for cardiology-type consultations
        result_keys = [
            'labResults', 'investigation', 'investigationsDischarge',
            'investigations'  # May contain results in imaging_studies, laboratory_tests fields
        ]
        extraction = get_latest_extraction_with_segment(
            patient_uuid, result_keys, counsellor_id,
            counsellor_ids=view_counsellor_ids, include_assistant=school_view,
        )

        if not extraction:
            return LastInvestigationsResponse(patient=patient, found=False)

        data = get_extraction_data(extraction)
        investigations = find_segment_value(data, *result_keys)

        # For cardiology consultations, also include vitals as part of investigation results
        vitals = extract_vitals(data)
        if vitals and investigations:
            # Merge vitals into investigations if both exist
            if isinstance(investigations, dict):
                investigations['vitals'] = vitals
            elif isinstance(investigations, list):
                investigations = {'tests': investigations, 'vitals': vitals}
            elif investigations is None:
                investigations = {'vitals': vitals}
        elif vitals and not investigations:
            investigations = {'vitals': vitals}

        return LastInvestigationsResponse(
            patient=patient,
            investigations=investigations,
            metadata=build_extraction_metadata(extraction),
            found=investigations is not None
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting last investigations results: {e}")
        raise HTTPException(status_code=500, detail="Failed to get last investigations results")


@router.get("/{student_id}/last-investigations-ordered", response_model=LastInvestigationsResponse)
async def get_last_investigations_ordered(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    _auth = Depends(verify_student_access)
):
    """
    Get the last investigations ordered for a student.

    Returns pending/ordered labs, radiology, etc.
    """
    try:
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid = resolve_student_id_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        patient_info = get_student_info(patient_uuid)
        if not patient_info:
            raise HTTPException(status_code=404, detail="Student not found")

        patient = StudentInfo(
            id=patient_info["id"],
            student_id=patient_info["student_id"],
            full_name=patient_info.get("full_name"),
            date_of_birth=patient_info.get("date_of_birth"),
            gender=patient_info.get("gender")
        )

        # Keys for ordered investigations
        ordered_keys = [
            'investigations', 'orderedLabs', 'orderedRadiology',
            'otherInvestigations'  # Additional investigations key
        ]
        extraction = get_latest_extraction_with_segment(
            patient_uuid, ordered_keys, counsellor_id,
            counsellor_ids=view_counsellor_ids, include_assistant=school_view,
        )

        if not extraction:
            return LastInvestigationsResponse(patient=patient, found=False)

        data = get_extraction_data(extraction)
        investigations = find_segment_value(data, *ordered_keys)

        return LastInvestigationsResponse(
            patient=patient,
            investigations=investigations,
            metadata=build_extraction_metadata(extraction),
            found=investigations is not None
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting last investigations ordered: {e}")
        raise HTTPException(status_code=500, detail="Failed to get last investigations ordered")


@router.get("/{student_id}/last-case-summary", response_model=LastCaseSummaryResponse)
async def get_last_case_summary(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    _auth = Depends(verify_student_access)
):
    """
    Get the last case summary for a student.

    Returns a consolidated view including:
    - Diagnosis
    - Chief complaints
    - Prescription
    - Examination (physical findings)
    - Treatment plan and advice
    - Follow-up
    """
    try:
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid = resolve_student_id_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        patient_info = get_student_info(patient_uuid)
        if not patient_info:
            raise HTTPException(status_code=404, detail="Student not found")

        patient = StudentInfo(
            id=patient_info["id"],
            student_id=patient_info["student_id"],
            full_name=patient_info.get("full_name"),
            date_of_birth=patient_info.get("date_of_birth"),
            gender=patient_info.get("gender")
        )

        # Get most recent extraction
        extraction = get_latest_extraction_for_student(
            patient_uuid, counsellor_id,
            counsellor_ids=view_counsellor_ids, include_assistant=school_view,
        )

        if not extraction:
            return LastCaseSummaryResponse(patient=patient, found=False)

        data = get_extraction_data(extraction)

        # Build case summary from available segments using helper functions
        # Use extract_chief_complaints which also checks history.chief_complaints
        chief_complaints = extract_chief_complaints(data)

        # Get examination with expanded keys including clinical notes
        examination = find_segment_value(
            data,
            'examination', 'physicalExaminationOp', 'physicalExaminationDischarge',
            'initialExamination', 'initialExaminationSummary', 'clinicalNotes'
        )
        # Include vitals alongside examination (separate segment)
        vitals = extract_vitals(data)

        # Get follow-up with expanded keys including advice segments
        follow_up = find_segment_value(
            data,
            'followUp', 'follow_up', 'followUpOp', 'followUpDischarge',
            'adviceAndFollowUp', 'dischargeAdvice', 'generalInstructions'
        )

        case_summary = CaseSummary(
            diagnosis=find_segment_value(data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge'),
            chief_complaints=chief_complaints,
            prescription=find_segment_value(
                data,
                'prescription', 'prescriptionOp', 'prescriptionDischarge',
                'medications', 'drugs', 'drugDetails'
            ),
            examination=examination,
            treatment_plan=find_segment_value(
                data,
                'treatmentPlan', 'treatment_plan', 'treatmentPlanAdviceOp', 'treatmentPlanAdviceDischarge'
            ),
            follow_up=follow_up,
            history=find_segment_value(data, 'history', 'historyOp', 'historyDischarge', 'historyOfPresentIllness')
        )

        # Check if we found any data
        has_data = any([
            case_summary.diagnosis,
            case_summary.chief_complaints,
            case_summary.prescription,
            case_summary.examination,
            case_summary.treatment_plan,
            case_summary.follow_up
        ])

        # HIPAA Audit: log case summary access
        client_ctx = getattr(request.state, "client", None)
        if client_ctx:
            try:
                asyncio.create_task(audit_service.log_phi_access(
                    client_context=client_ctx, request=request, response_status=200,
                    response_time_ms=0, resource_type="patient", action="read",
                    student_id=student_id, phi_fields=["case_summary"],
                ))
            except Exception:
                pass

        return LastCaseSummaryResponse(
            patient=patient,
            case_summary=case_summary if has_data else None,
            metadata=build_extraction_metadata(extraction),
            found=has_data
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting last case summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get last case summary")


@router.get("/{student_id}/context", response_model=StudentContextResponse)
async def get_student_context(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    _auth = Depends(verify_student_access)
):
    """
    Get complete student context for informed consultations.

    Returns:
    - Last case summary (diagnosis, complaints, prescription, examination, treatment plan, follow-up)
    - Last emotional analysis summary
    - Recommended interventions
    - Consultation count and last visit date

    This is the primary endpoint for providing context before a new consultation.
    """
    try:
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid = resolve_student_id_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        patient_info = get_student_info(patient_uuid)
        if not patient_info:
            raise HTTPException(status_code=404, detail="Student not found")

        patient = StudentInfo(
            id=patient_info["id"],
            student_id=patient_info["student_id"],
            full_name=patient_info.get("full_name"),
            date_of_birth=patient_info.get("date_of_birth"),
            gender=patient_info.get("gender")
        )

        # Get consultation count and last visit
        ext_query = supabase.table("extractions")\
            .select("id, created_at")\
            .eq("student_id", str(patient_uuid))\
            .order("created_at", desc=True)

        if view_counsellor_ids is not None:
            if not view_counsellor_ids:
                ext_result_data = []
            else:
                ext_query = ext_query.in_("counsellor_id", view_counsellor_ids)
                ext_result_data = (ext_query.execute().data or [])
        elif counsellor_id:
            ext_query = ext_query.eq("counsellor_id", counsellor_id)
            ext_result_data = (ext_query.execute().data or [])
        else:
            ext_result_data = (ext_query.execute().data or [])

        all_extractions = ext_result_data
        consultation_count = len(all_extractions)
        last_visit_date = all_extractions[0]["created_at"] if all_extractions else None

        # Get last case summary
        latest_extraction = get_latest_extraction_for_student(
            patient_uuid, counsellor_id,
            counsellor_ids=view_counsellor_ids, include_assistant=school_view,
        )

        case_summary = None
        case_summary_metadata = None

        if latest_extraction:
            data = get_extraction_data(latest_extraction)

            # Extract chief complaints using helper (checks direct keys + embedded in history)
            chief_complaints = extract_chief_complaints(data)

            # Extract examination with expanded keys
            examination = find_segment_value(
                data,
                'examination', 'physicalExaminationOp', 'physicalExaminationDischarge',
                'initialExamination', 'initialExaminationSummary', 'clinicalNotes'
            )

            vitals = extract_vitals(data)

            # Extract follow-up with expanded keys
            follow_up = find_segment_value(
                data,
                'followUp', 'followUpOp', 'followUpDischarge',
                'adviceAndFollowUp', 'dischargeAdvice', 'generalInstructions'
            )

            case_summary = CaseSummary(
                diagnosis=find_segment_value(data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge'),
                chief_complaints=chief_complaints,
                prescription=find_segment_value(
                    data,
                    'prescription', 'prescriptionOp', 'prescriptionDischarge',
                    'medications', 'drugs', 'drugDetails'
                ),
                examination=examination,
                treatment_plan=find_segment_value(data, 'treatmentPlan', 'treatment_plan', 'treatmentPlanAdviceOp', 'treatmentPlanAdviceDischarge'),
                follow_up=follow_up,
                history=find_segment_value(data, 'history', 'historyOp', 'historyDischarge', 'historyOfPresentIllness')
            )
            case_summary_metadata = build_extraction_metadata(latest_extraction)

        # Get last emotion analysis
        emotion_summary = None
        emotion_metadata = None

        # Find extraction with emotion data
        emotion_rows: List[Dict[str, Any]] = []
        if view_counsellor_ids is not None:
            if view_counsellor_ids:
                emotion_query = supabase.table("extractions")\
                    .select("*")\
                    .eq("student_id", str(patient_uuid))\
                    .eq("emotion_extraction_completed", True)\
                    .in_("counsellor_id", view_counsellor_ids)\
                    .order("created_at", desc=True)\
                    .limit(1)
                emotion_rows = emotion_query.execute().data or []
        else:
            emotion_query = supabase.table("extractions")\
                .select("*")\
                .eq("student_id", str(patient_uuid))\
                .eq("emotion_extraction_completed", True)\
                .order("created_at", desc=True)
            if counsellor_id:
                emotion_query = emotion_query.eq("counsellor_id", counsellor_id)
            emotion_query = emotion_query.limit(1)
            emotion_rows = emotion_query.execute().data or []

        if emotion_rows:
            emotion_extraction = emotion_rows[0]
            emotion_metadata = build_extraction_metadata(emotion_extraction)

            # Get emotion segments from extraction_segments table
            segments_result = supabase.table("extraction_segments")\
                .select("segment_code, segment_value")\
                .eq("extraction_id", emotion_extraction["id"])\
                .execute()

            emotion_segments = {}
            for seg in (segments_result.data or []):
                emotion_segments[seg["segment_code"]] = seg.get("segment_value")

            # Combined mode: both pre and post consultation are nested in ANXIETY_POST_CONSULTATION
            anxiety_pre = None
            anxiety_post = None
            anxiety_segment = emotion_segments.get("ANXIETY_POST_CONSULTATION")
            if isinstance(anxiety_segment, dict):
                anxiety_pre = anxiety_segment.get("pre_consultation")
                anxiety_post = anxiety_segment.get("post_consultation")

            emotion_summary = EmotionSummary(
                anxiety_pre_consultation=anxiety_pre,
                anxiety_post_consultation=anxiety_post,
                other_emotions=emotion_segments.get("OTHER_EMOTIONS_DETECTED"),
                audio_anxiety=emotion_segments.get("AUDIO_PATIENT_ANXIETY"),
                congruence_analysis=emotion_segments.get("CONGRUENCE_SUMMARY"),
                financial_concerns=emotion_segments.get("FINANCIAL_CONCERNS"),
                compliance_likelihood=emotion_segments.get("TREATMENT_COMPLIANCE_LIKELIHOOD")
            )

        # Get recommended interventions from most recent extraction with interventions
        interventions = []
        if emotion_rows:
            extraction_id = emotion_rows[0]["id"]
            # Join with intervention_definitions to get name and description
            interventions_result = supabase.table("student_interventions")\
                .select("*, intervention_definitions(intervention_name, description, category)")\
                .eq("extraction_id", extraction_id)\
                .order("priority_score", desc=True)\
                .execute()

            for i in (interventions_result.data or []):
                # Get intervention details from joined table
                intervention_def = i.get("intervention_definitions") or {}
                interventions.append(InterventionSummary(
                    id=i["id"],
                    code=i.get("intervention_code", ""),
                    name=intervention_def.get("intervention_name", ""),
                    description=intervention_def.get("description", ""),
                    category=intervention_def.get("category", "general"),
                    priority=i.get("priority_level", "medium").lower(),
                    priority_score=i.get("priority_score", 50),
                    trigger_reason=i.get("trigger_reason", ""),
                    is_top_3=i.get("is_top_recommendation", False)
                ))

        has_data = case_summary is not None or emotion_summary is not None

        return StudentContextResponse(
            patient=patient,
            last_case_summary=case_summary,
            case_summary_metadata=case_summary_metadata,
            emotion_summary=emotion_summary,
            emotion_metadata=emotion_metadata,
            recommended_interventions=interventions,
            consultation_count=consultation_count,
            last_visit_date=last_visit_date,
            found=has_data
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting student context: {e}")
        raise HTTPException(status_code=500, detail="Failed to get student context")


# ============================================================================
# Bulk/Combined Endpoints
# ============================================================================

class StudentHistoryAllResponse(BaseModel):
    """Combined response with all student history data"""
    patient: StudentInfo
    last_prescription: Optional[Any] = None  # Can be Dict or List depending on extraction format
    last_diagnosis: Optional[Any] = None
    last_investigations_ordered: Optional[Any] = None
    last_investigations_results: Optional[Any] = None
    last_case_summary: Optional[CaseSummary] = None
    emotion_summary: Optional[EmotionSummary] = None
    recommended_interventions: List[InterventionSummary] = []
    consultation_count: int = 0
    last_visit_date: Optional[str] = None
    # Metadata for each section
    prescription_metadata: Optional[ExtractionMetadata] = None
    diagnosis_metadata: Optional[ExtractionMetadata] = None
    investigations_ordered_metadata: Optional[ExtractionMetadata] = None
    investigations_results_metadata: Optional[ExtractionMetadata] = None
    case_summary_metadata: Optional[ExtractionMetadata] = None
    emotion_metadata: Optional[ExtractionMetadata] = None
    # Summary view data (emotion patterns from last 2 visits, top 3 interventions)
    emotion_pattern_summary: Optional[EmotionPatternSummary] = None
    top_interventions: List[InterventionSummary] = []  # Top 3 from most recent consultation


class PrescreenResponse(BaseModel):
    """
    Prescreen information for a student before consultation.

    Contains:
    1. Latest prescreen template extraction (if exists)
    2. Emotion pattern summary (aggregated from last 2 consultations)
    3. Top 3 recommended interventions (from most recent consultation)
    4. Student warning factors (CAUTION segment - allergies, contraindications)
    5. Past diagnosis summary (SUMMARY segment from last consultation)
    6. Clinical timeline (last 5 visits with diagnosis/medication changes)
    7. Last prescription
    """
    patient: StudentInfo

    # 1. Latest prescreen template extraction (if exists)
    prescreen_data: Optional[Dict[str, Any]] = None  # Full extraction from prescreen template
    prescreen_metadata: Optional[ExtractionMetadata] = None
    has_prescreen: bool = False

    # 2. Emotion pattern summary (last 2 consultations)
    emotion_pattern_summary: Optional[EmotionPatternSummary] = None

    # 3. Top 3 recommended interventions (from most recent consultation)
    top_interventions: List[InterventionSummary] = []

    # 4. Student warning factors (CAUTION segment from last consultation)
    warning_factors: Optional[Any] = None  # Allergies, contraindications, etc. (can be Dict or String)
    warning_factors_date: Optional[str] = None

    # 5. Past diagnosis summary (SUMMARY segment from last consultation)
    past_diagnosis_summary: Optional[Any] = None  # Can be Dict or String depending on extraction format
    past_diagnosis_summary_date: Optional[str] = None

    # 6. Clinical timeline (last 5 visits)
    clinical_timeline: Optional[Dict[str, Any]] = None  # Contains timeline, summary, visit_count

    # 7. Last prescription (can be List or Dict depending on extraction format)
    last_prescription: Optional[Any] = None
    last_prescription_date: Optional[str] = None

    # Metadata
    consultation_count: int = 0
    last_visit_date: Optional[str] = None


# ============================================================================
# Pattern Analysis Models
# ============================================================================

class VisitSummary(BaseModel):
    """Summary of a single visit for pattern analysis"""
    extraction_id: str
    visit_date: str
    consultation_type: Optional[str] = None
    counsellor_name: Optional[str] = None
    diagnosis: Optional[Any] = None
    chief_complaints: Optional[Any] = None
    prescription: Optional[Any] = None
    investigations_ordered: Optional[Any] = None
    investigations_results: Optional[Any] = None


class DiagnosisPattern(BaseModel):
    """Pattern analysis for diagnoses across visits"""
    diagnosis_name: str
    icd_code: Optional[str] = None
    occurrence_count: int
    first_seen: str
    last_seen: str
    visits: List[str]  # List of visit dates


class ChiefComplaintPattern(BaseModel):
    """Pattern analysis for chief complaints across visits"""
    complaint: str
    occurrence_count: int
    first_seen: str
    last_seen: str
    visits: List[str]


class EmotionTrend(BaseModel):
    """Emotion data point for trend analysis"""
    visit_date: str
    extraction_id: str
    anxiety_level: Optional[str] = None
    anxiety_score: Optional[float] = None
    other_emotions: Optional[List[str]] = None
    financial_concerns: Optional[bool] = None
    compliance_likelihood: Optional[str] = None


class EmotionPatternResponse(BaseModel):
    """Response for emotion pattern analysis"""
    patient: StudentInfo
    emotion_trends: List[EmotionTrend]
    analysis: Dict[str, Any]  # Summary statistics
    visit_count: int
    visits_with_emotions: int


class DiagnosisPatternResponse(BaseModel):
    """Response for diagnosis pattern analysis"""
    patient: StudentInfo
    patterns: List[DiagnosisPattern]
    recent_visits: List[VisitSummary]
    analysis: Dict[str, Any]  # Summary statistics
    visit_count: int


class ChiefComplaintPatternResponse(BaseModel):
    """Response for chief complaint pattern analysis"""
    patient: StudentInfo
    patterns: List[ChiefComplaintPattern]
    recent_visits: List[VisitSummary]
    analysis: Dict[str, Any]
    visit_count: int


class MultiVisitSummaryResponse(BaseModel):
    """Response for multi-visit summary (last N visits)"""
    patient: StudentInfo
    visits: List[VisitSummary]
    diagnosis_patterns: List[DiagnosisPattern]
    complaint_patterns: List[ChiefComplaintPattern]
    prescription_summary: Dict[str, Any]  # Commonly prescribed medicines
    visit_count: int


@router.get("/{student_id}/history/all", response_model=StudentHistoryAllResponse)
async def get_all_student_history(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    _auth = Depends(verify_student_access)
):
    """
    Get all student history data in a single request.

    This is the most comprehensive endpoint that returns:
    - Last prescription
    - Last diagnosis
    - Last investigations ordered
    - Last investigations results
    - Last case summary
    - Emotion analysis summary
    - Recommended interventions
    - Consultation metadata

    Use this endpoint to get all data needed for the student history screen.
    """
    try:
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid = resolve_student_id_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        patient_info = get_student_info(patient_uuid)
        if not patient_info:
            raise HTTPException(status_code=404, detail="Student not found")

        patient = StudentInfo(
            id=patient_info["id"],
            student_id=patient_info["student_id"],
            full_name=patient_info.get("full_name"),
            date_of_birth=patient_info.get("date_of_birth"),
            gender=patient_info.get("gender")
        )

        # Get consultation count and last visit
        ext_query = supabase.table("extractions")\
            .select("id, created_at")\
            .eq("student_id", str(patient_uuid))\
            .order("created_at", desc=True)

        if view_counsellor_ids is not None:
            if not view_counsellor_ids:
                all_extractions = []
            else:
                ext_query = ext_query.in_("counsellor_id", view_counsellor_ids)
                all_extractions = ext_query.execute().data or []
        else:
            if counsellor_id:
                ext_query = ext_query.eq("counsellor_id", counsellor_id)
            all_extractions = ext_query.execute().data or []

        consultation_count = len(all_extractions)
        last_visit_date = all_extractions[0]["created_at"] if all_extractions else None

        # Get all extractions with data (limit to recent ones for efficiency)
        # Query with recording_sessions join to filter PRESCREEN
        data_query = supabase.table("extractions")\
            .select("*, recording_sessions(template_code, assistant_id)")\
            .eq("student_id", str(patient_uuid))\
            .order("created_at", desc=True)

        if view_counsellor_ids is not None:
            if not view_counsellor_ids:
                data_rows: List[Dict[str, Any]] = []
            else:
                data_query = data_query.in_("counsellor_id", view_counsellor_ids)
                data_rows = data_query.limit(40).execute().data or []
        else:
            if counsellor_id:
                data_query = data_query.eq("counsellor_id", counsellor_id)
            data_rows = data_query.limit(40).execute().data or []

        # Filter out PRESCREEN extractions (unless school_view wants assistant data shown)
        if school_view:
            extractions = data_rows[:20]
        else:
            extractions = filter_prescreen_extractions(data_rows, max_results=20)

        # Initialize response fields
        last_prescription = None
        prescription_metadata = None
        last_diagnosis = None
        diagnosis_metadata = None
        last_investigations_ordered = None
        investigations_ordered_metadata = None
        last_investigations_results = None
        investigations_results_metadata = None
        last_case_summary = None
        case_summary_metadata = None
        emotion_summary = None
        emotion_metadata = None
        interventions = []

        # Find each data type from extractions
        for ext in extractions:
            data = get_extraction_data(ext)

            # Prescription - use shared utility to find from all locations
            if last_prescription is None:
                prescription = find_prescription_in_extraction(data)
                if prescription:
                    last_prescription = prescription
                    prescription_metadata = build_extraction_metadata(ext)

            # Diagnosis
            if last_diagnosis is None:
                diagnosis = find_segment_value(data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge')
                if diagnosis:
                    last_diagnosis = diagnosis
                    diagnosis_metadata = build_extraction_metadata(ext)

            # Investigations ordered
            if last_investigations_ordered is None:
                ordered = find_segment_value(data, 'investigations', 'orderedLabs', 'orderedRadiology')
                if ordered:
                    last_investigations_ordered = ordered
                    investigations_ordered_metadata = build_extraction_metadata(ext)

            # Investigations results
            if last_investigations_results is None:
                results = find_segment_value(data, 'labResults', 'investigation', 'investigationsDischarge')
                if results:
                    last_investigations_results = results
                    investigations_results_metadata = build_extraction_metadata(ext)

            # Case summary (from most recent extraction)
            if last_case_summary is None:
                has_any_summary_data = any([
                    find_segment_value(data, 'diagnosis', 'diagnosisOp'),
                    find_segment_value(data, 'chiefComplaints', 'chiefComplaintsOp'),
                    find_prescription_in_extraction(data),
                    find_segment_value(data, 'examination', 'physicalExaminationOp'),
                ])
                if has_any_summary_data:
                    last_case_summary = CaseSummary(
                        diagnosis=find_segment_value(data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge'),
                        chief_complaints=find_segment_value(data, 'chiefComplaints', 'chiefComplaintsOp', 'complaints'),
                        prescription=find_prescription_in_extraction(data),
                        examination=find_segment_value(data, 'examination', 'physicalExaminationOp'),
                        treatment_plan=find_segment_value(data, 'treatmentPlan', 'treatmentPlanAdviceOp'),
                        follow_up=find_segment_value(data, 'followUp', 'follow_up', 'followUpOp'),
                        history=find_segment_value(data, 'history', 'historyOp', 'historyOfPresentIllness')
                    )
                    case_summary_metadata = build_extraction_metadata(ext)

        # Get emotion data
        emotion_query = supabase.table("extractions")\
            .select("*")\
            .eq("student_id", str(patient_uuid))\
            .eq("emotion_extraction_completed", True)\
            .order("created_at", desc=True)

        if view_counsellor_ids is not None:
            if not view_counsellor_ids:
                emotion_data_rows: List[Dict[str, Any]] = []
            else:
                emotion_query = emotion_query.in_("counsellor_id", view_counsellor_ids).limit(1)
                emotion_data_rows = emotion_query.execute().data or []
        else:
            if counsellor_id:
                emotion_query = emotion_query.eq("counsellor_id", counsellor_id)
            emotion_query = emotion_query.limit(1)
            emotion_data_rows = emotion_query.execute().data or []

        if emotion_data_rows:
            emotion_ext = emotion_data_rows[0]
            emotion_metadata = build_extraction_metadata(emotion_ext)

            # Get emotion segments
            segments_result = supabase.table("extraction_segments")\
                .select("segment_code, segment_value")\
                .eq("extraction_id", emotion_ext["id"])\
                .execute()

            emotion_segments = {}
            for seg in (segments_result.data or []):
                emotion_segments[seg["segment_code"]] = seg.get("segment_value")

            # Combined mode: both pre and post consultation are nested in ANXIETY_POST_CONSULTATION
            anxiety_pre = None
            anxiety_post = None
            anxiety_segment = emotion_segments.get("ANXIETY_POST_CONSULTATION")
            if isinstance(anxiety_segment, dict):
                anxiety_pre = anxiety_segment.get("pre_consultation")
                anxiety_post = anxiety_segment.get("post_consultation")

            emotion_summary = EmotionSummary(
                anxiety_pre_consultation=anxiety_pre,
                anxiety_post_consultation=anxiety_post,
                other_emotions=emotion_segments.get("OTHER_EMOTIONS_DETECTED"),
                audio_anxiety=emotion_segments.get("AUDIO_PATIENT_ANXIETY"),
                congruence_analysis=emotion_segments.get("CONGRUENCE_SUMMARY"),
                financial_concerns=emotion_segments.get("FINANCIAL_CONCERNS"),
                compliance_likelihood=emotion_segments.get("TREATMENT_COMPLIANCE_LIKELIHOOD")
            )

            # Get interventions - join with intervention_definitions for name and description
            interventions_result = supabase.table("student_interventions")\
                .select("*, intervention_definitions(intervention_name, description, category)")\
                .eq("extraction_id", emotion_ext["id"])\
                .order("priority_score", desc=True)\
                .execute()

            for i in (interventions_result.data or []):
                # Get intervention details from joined table
                intervention_def = i.get("intervention_definitions") or {}
                interventions.append(InterventionSummary(
                    id=i["id"],
                    code=i.get("intervention_code", ""),
                    name=intervention_def.get("intervention_name", ""),
                    description=intervention_def.get("description", ""),
                    category=intervention_def.get("category", "general"),
                    priority=i.get("priority_level", "medium").lower(),
                    priority_score=i.get("priority_score", 50),
                    trigger_reason=i.get("trigger_reason", ""),
                    is_top_3=i.get("is_top_recommendation", False)
                ))

        # Build emotion pattern summary from last 2 consultations (for Summary view)
        emotion_pattern_summary = build_emotion_pattern_summary(
            patient_uuid, counsellor_id, num_visits=2,
            counsellor_ids=view_counsellor_ids, include_assistant=school_view,
        )

        # Get top 3 interventions from most recent consultation (for Summary view)
        top_interventions = [i for i in interventions if i.is_top_3][:3]

        return StudentHistoryAllResponse(
            patient=patient,
            last_prescription=last_prescription,
            last_diagnosis=last_diagnosis,
            last_investigations_ordered=last_investigations_ordered,
            last_investigations_results=last_investigations_results,
            last_case_summary=last_case_summary,
            emotion_summary=emotion_summary,
            recommended_interventions=interventions,
            consultation_count=consultation_count,
            last_visit_date=last_visit_date,
            prescription_metadata=prescription_metadata,
            diagnosis_metadata=diagnosis_metadata,
            investigations_ordered_metadata=investigations_ordered_metadata,
            investigations_results_metadata=investigations_results_metadata,
            case_summary_metadata=case_summary_metadata,
            emotion_metadata=emotion_metadata,
            emotion_pattern_summary=emotion_pattern_summary,
            top_interventions=top_interventions
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting all student history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get all student history")


# ============================================================================
# Pattern Analysis Endpoints
# ============================================================================

@router.get("/{student_id}/patterns/multi-visit", response_model=MultiVisitSummaryResponse)
async def get_multi_visit_summary(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    num_visits: int = Query(2, ge=1, le=20, description="Number of visits to analyze (if 2nd visit is >6 months old, only latest is used)"),
    _auth = Depends(verify_student_access)
):
    """
    Get summary of last N visits with pattern analysis.

    Returns:
    - Individual visit summaries (diagnosis, complaints, prescriptions)
    - Diagnosis patterns (recurring diagnoses across visits)
    - Complaint patterns (recurring chief complaints)
    - Prescription summary (commonly prescribed medicines)

    Use this to understand student history trends before a consultation.
    """
    try:
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid = resolve_student_id_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        patient_info = get_student_info(patient_uuid)
        if not patient_info:
            raise HTTPException(status_code=404, detail="Student not found")

        patient = StudentInfo(
            id=patient_info["id"],
            student_id=patient_info["student_id"],
            full_name=patient_info.get("full_name"),
            date_of_birth=patient_info.get("date_of_birth"),
            gender=patient_info.get("gender")
        )

        # Get extractions with recording_sessions join for PRESCREEN filtering
        query = supabase.table("extractions")\
            .select("*, recording_sessions(template_code, assistant_id)")\
            .eq("student_id", str(patient_uuid))\
            .order("created_at", desc=True)

        if view_counsellor_ids is not None:
            if not view_counsellor_ids:
                rows: List[Dict[str, Any]] = []
            else:
                query = query.in_("counsellor_id", view_counsellor_ids).limit(num_visits * 2)
                rows = query.execute().data or []
        else:
            if counsellor_id:
                query = query.eq("counsellor_id", counsellor_id)
            query = query.limit(num_visits * 2)
            rows = query.execute().data or []

        # Filter out PRESCREEN extractions (unless school_view wants assistant data shown)
        if school_view:
            extractions = rows[:num_visits]
        else:
            extractions = filter_prescreen_extractions(rows, max_results=num_visits)

        # Build visit summaries and collect patterns
        visits = []
        all_diagnoses = []  # (name, code, visit_date)
        all_complaints = []  # (complaint, visit_date)
        all_medicines = []  # (name, visit_date)

        for ext in extractions:
            data = get_extraction_data(ext)
            visit_date = ext["created_at"]

            # Extract data
            diagnosis = find_segment_value(data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge')
            complaints = find_segment_value(data, 'chiefComplaints', 'chiefComplaintsOp', 'complaints')
            # Use shared utility to find prescription from all locations (including treatmentPlan)
            prescription = find_prescription_in_extraction(data)
            investigations_ordered = find_segment_value(data, 'investigations', 'orderedLabs', 'orderedRadiology')
            investigations_results = find_segment_value(data, 'labResults', 'investigation')

            # Get metadata
            ct_name = get_consultation_type_name(ext["consultation_type_id"]) if ext.get("consultation_type_id") else None
            counsellor_name = get_counsellor_name(ext["counsellor_id"]) if ext.get("counsellor_id") else None

            visits.append(VisitSummary(
                extraction_id=ext["id"],
                visit_date=visit_date,
                consultation_type=ct_name,
                counsellor_name=counsellor_name,
                diagnosis=diagnosis,
                chief_complaints=complaints,
                prescription=prescription,
                investigations_ordered=investigations_ordered,
                investigations_results=investigations_results
            ))

            # Collect for pattern analysis
            for dx in extract_diagnosis_list(diagnosis):
                all_diagnoses.append((dx['name'], dx['code'], visit_date))

            for c in extract_complaints_list(complaints):
                all_complaints.append((c, visit_date))

            for med in extract_medicines_list(prescription):
                if med['name']:
                    all_medicines.append((med['name'], visit_date))

        # Analyze diagnosis patterns
        diagnosis_counts = {}
        for name, code, visit_date in all_diagnoses:
            name_lower = name.lower().strip()
            if name_lower not in diagnosis_counts:
                diagnosis_counts[name_lower] = {
                    'name': name,
                    'code': code,
                    'count': 0,
                    'visits': []
                }
            diagnosis_counts[name_lower]['count'] += 1
            diagnosis_counts[name_lower]['visits'].append(visit_date)
            if code and not diagnosis_counts[name_lower]['code']:
                diagnosis_counts[name_lower]['code'] = code

        diagnosis_patterns = [
            DiagnosisPattern(
                diagnosis_name=d['name'],
                icd_code=d['code'],
                occurrence_count=d['count'],
                first_seen=min(d['visits']),
                last_seen=max(d['visits']),
                visits=sorted(d['visits'], reverse=True)
            )
            for d in sorted(diagnosis_counts.values(), key=lambda x: x['count'], reverse=True)
        ]

        # Analyze complaint patterns
        complaint_counts = {}
        for complaint, visit_date in all_complaints:
            complaint_lower = complaint.lower().strip()
            if complaint_lower not in complaint_counts:
                complaint_counts[complaint_lower] = {
                    'complaint': complaint,
                    'count': 0,
                    'visits': []
                }
            complaint_counts[complaint_lower]['count'] += 1
            complaint_counts[complaint_lower]['visits'].append(visit_date)

        complaint_patterns = [
            ChiefComplaintPattern(
                complaint=c['complaint'],
                occurrence_count=c['count'],
                first_seen=min(c['visits']),
                last_seen=max(c['visits']),
                visits=sorted(c['visits'], reverse=True)
            )
            for c in sorted(complaint_counts.values(), key=lambda x: x['count'], reverse=True)
        ]

        # Analyze prescription patterns
        medicine_counts = {}
        for med_name, visit_date in all_medicines:
            med_lower = med_name.lower().strip()
            if med_lower not in medicine_counts:
                medicine_counts[med_lower] = {'name': med_name, 'count': 0}
            medicine_counts[med_lower]['count'] += 1

        prescription_summary = {
            'total_medicines_prescribed': len(all_medicines),
            'unique_medicines': len(medicine_counts),
            'commonly_prescribed': [
                {'name': m['name'], 'times_prescribed': m['count']}
                for m in sorted(medicine_counts.values(), key=lambda x: x['count'], reverse=True)[:10]
            ]
        }

        return MultiVisitSummaryResponse(
            patient=patient,
            visits=visits,
            diagnosis_patterns=diagnosis_patterns,
            complaint_patterns=complaint_patterns,
            prescription_summary=prescription_summary,
            visit_count=len(visits)
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting multi-visit summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get multi-visit summary")


@router.get("/{student_id}/patterns/emotions", response_model=EmotionPatternResponse)
async def get_emotion_patterns(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    num_visits: int = Query(10, ge=1, le=50, description="Number of visits to analyze"),
    _auth = Depends(verify_student_access)
):
    """
    Get emotion analysis patterns across multiple visits.

    Returns:
    - Emotion trends over time (anxiety levels, other emotions)
    - Analysis summary (average anxiety, trend direction, etc.)

    Use this to understand student's emotional patterns and identify concerning trends.
    """
    try:
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid = resolve_student_id_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        patient_info = get_student_info(patient_uuid)
        if not patient_info:
            raise HTTPException(status_code=404, detail="Student not found")

        patient = StudentInfo(
            id=patient_info["id"],
            student_id=patient_info["student_id"],
            full_name=patient_info.get("full_name"),
            date_of_birth=patient_info.get("date_of_birth"),
            gender=patient_info.get("gender")
        )

        # Get extractions with emotion data
        query = supabase.table("extractions")\
            .select("id, created_at, emotion_extraction_completed")\
            .eq("student_id", str(patient_uuid))\
            .eq("emotion_extraction_completed", True)\
            .order("created_at", desc=True)

        if view_counsellor_ids is not None:
            if not view_counsellor_ids:
                extractions: List[Dict[str, Any]] = []
            else:
                query = query.in_("counsellor_id", view_counsellor_ids).limit(num_visits)
                extractions = query.execute().data or []
        else:
            if counsellor_id:
                query = query.eq("counsellor_id", counsellor_id)
            query = query.limit(num_visits)
            extractions = query.execute().data or []

        # Get total visit count
        count_query = supabase.table("extractions")\
            .select("id", count="exact")\
            .eq("student_id", str(patient_uuid))
        if view_counsellor_ids is not None:
            if not view_counsellor_ids:
                total_visits = 0
            else:
                count_query = count_query.in_("counsellor_id", view_counsellor_ids)
                total_visits = count_query.execute().count or 0
        else:
            if counsellor_id:
                count_query = count_query.eq("counsellor_id", counsellor_id)
            total_visits = count_query.execute().count or 0

        # Collect emotion data
        emotion_trends = []
        anxiety_scores = []
        financial_concern_count = 0

        for ext in extractions:
            extraction_id = ext["id"]
            visit_date = ext["created_at"]

            # Get emotion segments
            segments_result = supabase.table("extraction_segments")\
                .select("segment_code, segment_value")\
                .eq("extraction_id", extraction_id)\
                .execute()

            emotion_data = {}
            for seg in (segments_result.data or []):
                emotion_data[seg["segment_code"]] = seg.get("segment_value")

            # Extract anxiety level from combined mode structure
            anxiety_segment = emotion_data.get("ANXIETY_POST_CONSULTATION", {})
            anxiety_level = None
            anxiety_score = None

            if isinstance(anxiety_segment, dict):
                pre_consultation = anxiety_segment.get('pre_consultation', {})
                if isinstance(pre_consultation, dict):
                    anxiety_level = pre_consultation.get('level')
                    anxiety_score = pre_consultation.get('combined_score')
                    if anxiety_score:
                        try:
                            anxiety_scores.append(float(anxiety_score))
                        except (ValueError, TypeError):
                            pass

            # Extract other emotions (combined mode: emotions_detected is list of strings)
            other_emotions_data = emotion_data.get("OTHER_EMOTIONS_DETECTED", {})
            other_emotions = None
            if isinstance(other_emotions_data, dict):
                other_emotions = other_emotions_data.get('emotions_detected')

            # Financial concerns (combined mode: check severity level)
            financial_data = emotion_data.get("FINANCIAL_CONCERNS", {})
            financial_concerns = False
            if isinstance(financial_data, dict):
                severity = financial_data.get('severity', 'None')
                financial_concerns = severity and severity.lower() not in ['none', 'n/a', '']
                if financial_concerns:
                    financial_concern_count += 1

            # Compliance likelihood (combined mode: likelihood at root)
            compliance_data = emotion_data.get("TREATMENT_COMPLIANCE_LIKELIHOOD", {})
            compliance = None
            if isinstance(compliance_data, dict):
                compliance = compliance_data.get('likelihood')

            emotion_trends.append(EmotionTrend(
                visit_date=visit_date,
                extraction_id=extraction_id,
                anxiety_level=anxiety_level,
                anxiety_score=anxiety_score,
                other_emotions=other_emotions if isinstance(other_emotions, list) else None,
                financial_concerns=financial_concerns,
                compliance_likelihood=compliance
            ))

        # Calculate analysis summary
        analysis = {
            'total_visits_analyzed': len(emotion_trends),
            'visits_with_high_anxiety': sum(1 for e in emotion_trends if e.anxiety_level in ['high', 'severe', 'very_high']),
            'visits_with_financial_concerns': financial_concern_count,
            'average_anxiety_score': round(sum(anxiety_scores) / len(anxiety_scores), 2) if anxiety_scores else None,
            'anxiety_trend': 'stable',  # Could calculate trend direction
        }

        # Determine anxiety trend
        if len(anxiety_scores) >= 3:
            recent_avg = sum(anxiety_scores[:len(anxiety_scores)//2]) / (len(anxiety_scores)//2)
            older_avg = sum(anxiety_scores[len(anxiety_scores)//2:]) / (len(anxiety_scores) - len(anxiety_scores)//2)
            if recent_avg > older_avg + 0.1:
                analysis['anxiety_trend'] = 'increasing'
            elif recent_avg < older_avg - 0.1:
                analysis['anxiety_trend'] = 'decreasing'

        return EmotionPatternResponse(
            patient=patient,
            emotion_trends=emotion_trends,
            analysis=analysis,
            visit_count=total_visits,
            visits_with_emotions=len(emotion_trends)
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting emotion patterns: {e}")
        raise HTTPException(status_code=500, detail="Failed to get emotion patterns")


@router.get("/{student_id}/patterns/diagnoses", response_model=DiagnosisPatternResponse)
async def get_diagnosis_patterns(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    num_visits: int = Query(10, ge=1, le=50, description="Number of visits to analyze"),
    _auth = Depends(verify_student_access)
):
    """
    Get diagnosis patterns across multiple visits.

    Returns:
    - Recurring diagnoses with occurrence count
    - Recent visit summaries with diagnosis data
    - Analysis (chronic conditions, new vs recurring)

    Use this to identify chronic conditions and recurring health issues.
    """
    try:
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid = resolve_student_id_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        patient_info = get_student_info(patient_uuid)
        if not patient_info:
            raise HTTPException(status_code=404, detail="Student not found")

        patient = StudentInfo(
            id=patient_info["id"],
            student_id=patient_info["student_id"],
            full_name=patient_info.get("full_name"),
            date_of_birth=patient_info.get("date_of_birth"),
            gender=patient_info.get("gender")
        )

        # Get extractions with recording_sessions join for PRESCREEN filtering
        query = supabase.table("extractions")\
            .select("*, recording_sessions(template_code, assistant_id)")\
            .eq("student_id", str(patient_uuid))\
            .order("created_at", desc=True)

        if view_counsellor_ids is not None:
            if not view_counsellor_ids:
                rows: List[Dict[str, Any]] = []
            else:
                query = query.in_("counsellor_id", view_counsellor_ids).limit(num_visits * 2)
                rows = query.execute().data or []
        else:
            if counsellor_id:
                query = query.eq("counsellor_id", counsellor_id)
            query = query.limit(num_visits * 2)
            rows = query.execute().data or []

        # Filter out PRESCREEN extractions (unless school_view wants assistant data shown)
        if school_view:
            extractions = rows[:num_visits]
        else:
            extractions = filter_prescreen_extractions(rows, max_results=num_visits)

        # Collect diagnoses
        visits = []
        all_diagnoses = []

        for ext in extractions:
            data = get_extraction_data(ext)
            visit_date = ext["created_at"]

            diagnosis = find_segment_value(data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge')
            complaints = find_segment_value(data, 'chiefComplaints', 'chiefComplaintsOp', 'complaints')

            ct_name = get_consultation_type_name(ext["consultation_type_id"]) if ext.get("consultation_type_id") else None
            counsellor_name = get_counsellor_name(ext["counsellor_id"]) if ext.get("counsellor_id") else None

            visits.append(VisitSummary(
                extraction_id=ext["id"],
                visit_date=visit_date,
                consultation_type=ct_name,
                counsellor_name=counsellor_name,
                diagnosis=diagnosis,
                chief_complaints=complaints,
                prescription=None,
                investigations_ordered=None,
                investigations_results=None
            ))

            for dx in extract_diagnosis_list(diagnosis):
                all_diagnoses.append((dx['name'], dx['code'], visit_date))

        # Analyze patterns
        diagnosis_counts = {}
        for name, code, visit_date in all_diagnoses:
            name_lower = name.lower().strip()
            if name_lower not in diagnosis_counts:
                diagnosis_counts[name_lower] = {
                    'name': name,
                    'code': code,
                    'count': 0,
                    'visits': []
                }
            diagnosis_counts[name_lower]['count'] += 1
            diagnosis_counts[name_lower]['visits'].append(visit_date)
            if code and not diagnosis_counts[name_lower]['code']:
                diagnosis_counts[name_lower]['code'] = code

        patterns = [
            DiagnosisPattern(
                diagnosis_name=d['name'],
                icd_code=d['code'],
                occurrence_count=d['count'],
                first_seen=min(d['visits']),
                last_seen=max(d['visits']),
                visits=sorted(d['visits'], reverse=True)
            )
            for d in sorted(diagnosis_counts.values(), key=lambda x: x['count'], reverse=True)
        ]

        # Analysis
        recurring = [p for p in patterns if p.occurrence_count > 1]
        analysis = {
            'total_diagnoses': len(all_diagnoses),
            'unique_diagnoses': len(patterns),
            'recurring_diagnoses': len(recurring),
            'chronic_conditions': [p.diagnosis_name for p in patterns if p.occurrence_count >= 3],
            'most_common': patterns[0].diagnosis_name if patterns else None,
        }

        return DiagnosisPatternResponse(
            patient=patient,
            patterns=patterns,
            recent_visits=visits,
            analysis=analysis,
            visit_count=len(visits)
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting diagnosis patterns: {e}")
        raise HTTPException(status_code=500, detail="Failed to get diagnosis patterns")


@router.get("/{student_id}/patterns/complaints", response_model=ChiefComplaintPatternResponse)
async def get_complaint_patterns(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    num_visits: int = Query(10, ge=1, le=50, description="Number of visits to analyze"),
    _auth = Depends(verify_student_access)
):
    """
    Get chief complaint patterns across multiple visits.

    Returns:
    - Recurring complaints with occurrence count
    - Recent visit summaries
    - Analysis (recurring symptoms, new complaints)

    Use this to identify recurring symptoms and chronic issues.
    """
    try:
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid = resolve_student_id_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        patient_info = get_student_info(patient_uuid)
        if not patient_info:
            raise HTTPException(status_code=404, detail="Student not found")

        patient = StudentInfo(
            id=patient_info["id"],
            student_id=patient_info["student_id"],
            full_name=patient_info.get("full_name"),
            date_of_birth=patient_info.get("date_of_birth"),
            gender=patient_info.get("gender")
        )

        # Get extractions with recording_sessions join for PRESCREEN filtering
        query = supabase.table("extractions")\
            .select("*, recording_sessions(template_code, assistant_id)")\
            .eq("student_id", str(patient_uuid))\
            .order("created_at", desc=True)

        if view_counsellor_ids is not None:
            if not view_counsellor_ids:
                rows: List[Dict[str, Any]] = []
            else:
                query = query.in_("counsellor_id", view_counsellor_ids).limit(num_visits * 2)
                rows = query.execute().data or []
        else:
            if counsellor_id:
                query = query.eq("counsellor_id", counsellor_id)
            query = query.limit(num_visits * 2)
            rows = query.execute().data or []

        # Filter out PRESCREEN extractions (unless school_view wants assistant data shown)
        if school_view:
            extractions = rows[:num_visits]
        else:
            extractions = filter_prescreen_extractions(rows, max_results=num_visits)

        # Collect complaints
        visits = []
        all_complaints = []

        for ext in extractions:
            data = get_extraction_data(ext)
            visit_date = ext["created_at"]

            diagnosis = find_segment_value(data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge')
            complaints = find_segment_value(data, 'chiefComplaints', 'chiefComplaintsOp', 'complaints')

            ct_name = get_consultation_type_name(ext["consultation_type_id"]) if ext.get("consultation_type_id") else None
            counsellor_name = get_counsellor_name(ext["counsellor_id"]) if ext.get("counsellor_id") else None

            visits.append(VisitSummary(
                extraction_id=ext["id"],
                visit_date=visit_date,
                consultation_type=ct_name,
                counsellor_name=counsellor_name,
                diagnosis=diagnosis,
                chief_complaints=complaints,
                prescription=None,
                investigations_ordered=None,
                investigations_results=None
            ))

            for c in extract_complaints_list(complaints):
                all_complaints.append((c, visit_date))

        # Analyze patterns
        complaint_counts = {}
        for complaint, visit_date in all_complaints:
            complaint_lower = complaint.lower().strip()
            if complaint_lower not in complaint_counts:
                complaint_counts[complaint_lower] = {
                    'complaint': complaint,
                    'count': 0,
                    'visits': []
                }
            complaint_counts[complaint_lower]['count'] += 1
            complaint_counts[complaint_lower]['visits'].append(visit_date)

        patterns = [
            ChiefComplaintPattern(
                complaint=c['complaint'],
                occurrence_count=c['count'],
                first_seen=min(c['visits']),
                last_seen=max(c['visits']),
                visits=sorted(c['visits'], reverse=True)
            )
            for c in sorted(complaint_counts.values(), key=lambda x: x['count'], reverse=True)
        ]

        # Analysis
        recurring = [p for p in patterns if p.occurrence_count > 1]
        analysis = {
            'total_complaints': len(all_complaints),
            'unique_complaints': len(patterns),
            'recurring_complaints': len(recurring),
            'chronic_symptoms': [p.complaint for p in patterns if p.occurrence_count >= 3],
            'most_common': patterns[0].complaint if patterns else None,
        }

        return ChiefComplaintPatternResponse(
            patient=patient,
            patterns=patterns,
            recent_visits=visits,
            analysis=analysis,
            visit_count=len(visits)
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting complaint patterns: {e}")
        raise HTTPException(status_code=500, detail="Failed to get complaint patterns")


# ============================================================================
# Clinical Timeline Models
# ============================================================================

class TimelineChange(BaseModel):
    """A single change in the clinical timeline"""
    type: str  # "new_diagnosis", "recurring_diagnosis", "first_time_diagnosis", "medication_added", "medication_removed", "medication_changed", "complaint_resolved", "complaint_not_mentioned", "complaint_new"
    category: str  # "diagnosis", "medication", "complaint"
    name: str
    details: Optional[str] = None  # e.g., dosage change details, ICD code
    confidence: Optional[str] = None  # "high", "medium", "low" - for inferred changes like resolved complaints
    previous_value: Optional[str] = None  # For medication changes
    new_value: Optional[str] = None  # For medication changes


class TimelineVisit(BaseModel):
    """A visit node in the clinical timeline"""
    extraction_id: str
    visit_date: str
    consultation_type: Optional[str] = None
    counsellor_name: Optional[str] = None
    changes: List[TimelineChange] = []
    diagnoses: List[str] = []  # All diagnoses in this visit
    complaints: List[str] = []  # All complaints in this visit
    medications: List[Dict[str, Any]] = []  # All medications in this visit
    has_significant_changes: bool = False


class ClinicalTimelineResponse(BaseModel):
    """Response for clinical timeline endpoint"""
    patient: StudentInfo
    timeline: List[TimelineVisit]
    summary: Dict[str, Any]  # Overall summary stats
    visit_count: int


# ============================================================================
# Clinical Timeline Helpers (wrapper functions for Pydantic model conversion)
# ============================================================================
# These wrap the shared utility functions and convert dict results to TimelineChange models

from services.history_extraction_utils import (
    detect_diagnosis_changes as _detect_diagnosis_changes_util,
    detect_medication_changes as _detect_medication_changes_util,
    detect_complaint_changes as _detect_complaint_changes_util,
)


def _dict_to_timeline_change(d: Dict[str, Any]) -> TimelineChange:
    """Convert a dict from shared utility to TimelineChange Pydantic model."""
    return TimelineChange(
        type=d.get("type", ""),
        category=d.get("category", ""),
        name=d.get("name", ""),
        details=d.get("details"),
        confidence=d.get("confidence"),
        previous_value=d.get("previous_value"),
        new_value=d.get("new_value"),
    )


def detect_diagnosis_changes_local(
    current_diagnoses: List[Dict[str, Any]],
    previous_visits_diagnoses: List[List[Dict[str, Any]]],
    all_historical_diagnoses: set,
    recent_window_diagnoses: set
) -> List[TimelineChange]:
    """
    Detect diagnosis changes for a visit. Returns TimelineChange Pydantic models.

    Wraps shared utility and converts dict results to Pydantic models.
    """
    changes_dicts = _detect_diagnosis_changes_util(
        current_diagnoses,
        previous_visits_diagnoses,
        all_historical_diagnoses,
        recent_window_diagnoses
    )
    return [_dict_to_timeline_change(d) for d in changes_dicts]


def detect_medication_changes_local(
    current_medications: List[Dict[str, Any]],
    previous_medications: List[Dict[str, Any]]
) -> List[TimelineChange]:
    """
    Detect medication changes between current and previous visit. Returns TimelineChange Pydantic models.

    Wraps shared utility and converts dict results to Pydantic models.
    """
    changes_dicts = _detect_medication_changes_util(current_medications, previous_medications)
    return [_dict_to_timeline_change(d) for d in changes_dicts]


def detect_complaint_changes_local(
    current_complaints: List[str],
    previous_complaints: List[str],
    two_visits_ago_complaints: List[str],
    current_diagnoses_normalized: set
) -> List[TimelineChange]:
    """
    Detect complaint changes with resolution inference. Returns TimelineChange Pydantic models.

    Wraps shared utility and converts dict results to Pydantic models.
    """
    changes_dicts = _detect_complaint_changes_util(
        current_complaints,
        previous_complaints,
        two_visits_ago_complaints,
        current_diagnoses_normalized
    )
    return [_dict_to_timeline_change(d) for d in changes_dicts]


# ============================================================================
# Clinical Timeline Endpoint
# ============================================================================

@router.get("/{student_id}/clinical-timeline", response_model=ClinicalTimelineResponse)
async def get_clinical_timeline(
    request: Request,
    student_id: str,
    counsellor_id: Optional[str] = Query(None, description="Filter by counsellor ID"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records). Requires counsellor_id."),
    num_visits: int = Query(5, ge=2, le=20, description="Number of visits to analyze"),
    _auth = Depends(verify_student_access)
):
    """
    Get clinical timeline with change detection across visits.

    Returns chronological timeline showing:
    - New diagnoses (first time vs recurring)
    - Medication changes (added, removed, dosage changed)
    - Complaint resolution status (resolved, not mentioned, new)

    Logic for "new" diagnosis:
    - Compares against last 2 visits OR last 6 months (whichever window is smaller)
    - "First Time" = never seen in student history
    - "Recurring" = seen before but not in recent window
    """
    try:
        school_id = _get_school_id_from_context(request, counsellor_id)
        patient_uuid = resolve_student_id_or_404(student_id, school_id=school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        patient_info = get_student_info(patient_uuid)
        if not patient_info:
            raise HTTPException(status_code=404, detail="Student not found")

        patient = StudentInfo(
            id=patient_info["id"],
            student_id=patient_info["student_id"],
            full_name=patient_info.get("full_name"),
            date_of_birth=patient_info.get("date_of_birth"),
            gender=patient_info.get("gender")
        )

        # Get extractions ordered by date (newest first for processing, will reverse for timeline)
        # Include recording_sessions join for PRESCREEN filtering
        query = supabase.table("extractions")\
            .select("*, recording_sessions(template_code, assistant_id)")\
            .eq("student_id", str(patient_uuid))\
            .order("created_at", desc=True)

        if view_counsellor_ids is not None:
            if not view_counsellor_ids:
                rows: List[Dict[str, Any]] = []
            else:
                query = query.in_("counsellor_id", view_counsellor_ids).limit(num_visits * 2)
                rows = query.execute().data or []
        else:
            if counsellor_id:
                query = query.eq("counsellor_id", counsellor_id)
            query = query.limit(num_visits * 2)
            rows = query.execute().data or []

        # Filter out PRESCREEN extractions (unless school_view wants assistant data shown)
        if school_view:
            extractions = rows[:num_visits]
        else:
            extractions = filter_prescreen_extractions(rows, max_results=num_visits)

        if len(extractions) < 1:
            return ClinicalTimelineResponse(
                patient=patient,
                timeline=[],
                summary={
                    "total_visits": 0,
                    "first_time_diagnoses": 0,
                    "recurring_diagnoses": 0,
                    "medication_changes": 0,
                    "resolved_complaints": 0
                },
                visit_count=0
            )

        # Also get ALL historical diagnoses for "first time" detection
        # PRESCREEN extractions are included here for completeness (they rarely have diagnoses anyway)
        all_extractions_result = supabase.table("extractions")\
            .select("original_extraction_json, edited_extraction_json, created_at, recording_sessions(template_code, assistant_id)")\
            .eq("student_id", str(patient_uuid))\
            .execute()

        all_historical_diagnoses = set()
        for ext in (all_extractions_result.data or []):
            # Skip assistant extractions for historical diagnosis lookup as well
            if is_assistant_extraction(ext):
                continue

            data = ext.get("edited_extraction_json") or ext.get("original_extraction_json") or {}
            diagnosis = find_segment_value(data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge')
            for dx in extract_diagnosis_list(diagnosis):
                all_historical_diagnoses.add(normalize_diagnosis_name(dx.get('name', '')))

        # Process extractions (newest to oldest)
        timeline_visits = []
        visit_dates = [ext["created_at"] for ext in extractions]

        # Summary counters
        first_time_count = 0
        recurring_count = 0
        medication_change_count = 0
        resolved_complaint_count = 0

        for i, ext in enumerate(extractions):
            data = get_extraction_data(ext)
            visit_date = ext["created_at"]

            # Extract current visit data
            diagnosis_data = find_segment_value(data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge')
            complaints_data = extract_chief_complaints(data)
            # Use shared utility to find prescription from all locations (including treatmentPlan)
            prescription_data = find_prescription_in_extraction(data)

            current_diagnoses = extract_diagnosis_list(diagnosis_data)
            current_complaints = extract_complaints_list(complaints_data)
            current_medications = extract_medicines_list(prescription_data)

            # Get previous visits data
            previous_medications = []
            previous_complaints = []
            two_visits_ago_complaints = []

            if i + 1 < len(extractions):
                prev_data = get_extraction_data(extractions[i + 1])
                prev_prescription = find_prescription_in_extraction(prev_data)
                prev_complaints_data = extract_chief_complaints(prev_data)
                previous_medications = extract_medicines_list(prev_prescription)
                previous_complaints = extract_complaints_list(prev_complaints_data)

            if i + 2 < len(extractions):
                two_ago_data = get_extraction_data(extractions[i + 2])
                two_ago_complaints_data = extract_chief_complaints(two_ago_data)
                two_visits_ago_complaints = extract_complaints_list(two_ago_complaints_data)

            # Build recent window diagnoses (last 2 visits or 6 months)
            recent_window_diagnoses = set()
            for j, prev_ext in enumerate(extractions):
                if j == i:  # Skip current visit
                    continue
                if j > i and is_within_recent_window(prev_ext["created_at"], visit_date, visit_dates[i+1:], max_visits=2, max_months=6):
                    prev_data = get_extraction_data(prev_ext)
                    prev_diagnosis = find_segment_value(prev_data, 'diagnosis', 'diagnosisOp', 'diagnosisDischarge')
                    for dx in extract_diagnosis_list(prev_diagnosis):
                        recent_window_diagnoses.add(normalize_diagnosis_name(dx.get('name', '')))

            # Detect changes
            changes = []

            # Diagnosis changes
            diagnosis_changes = detect_diagnosis_changes_local(
                current_diagnoses,
                [],  # Not used in current implementation
                all_historical_diagnoses - {normalize_diagnosis_name(dx.get('name', '')) for dx in current_diagnoses},  # Exclude current from history check
                recent_window_diagnoses
            )
            changes.extend(diagnosis_changes)
            first_time_count += len([c for c in diagnosis_changes if c.type == "first_time_diagnosis"])
            recurring_count += len([c for c in diagnosis_changes if c.type == "recurring_diagnosis"])

            # Medication changes (only if not first visit)
            if previous_medications:
                med_changes = detect_medication_changes_local(current_medications, previous_medications)
                changes.extend(med_changes)
                medication_change_count += len(med_changes)

            # Complaint changes (only if not first visit)
            if previous_complaints:
                current_diagnoses_normalized = {normalize_diagnosis_name(dx.get('name', '')) for dx in current_diagnoses}
                complaint_changes = detect_complaint_changes_local(
                    current_complaints,
                    previous_complaints,
                    two_visits_ago_complaints,
                    current_diagnoses_normalized
                )
                changes.extend(complaint_changes)
                resolved_complaint_count += len([c for c in complaint_changes if c.type == "complaint_resolved"])

            # Get metadata
            ct_name = get_consultation_type_name(ext["consultation_type_id"]) if ext.get("consultation_type_id") else None
            counsellor_name = get_counsellor_name(ext["counsellor_id"]) if ext.get("counsellor_id") else None

            timeline_visits.append(TimelineVisit(
                extraction_id=ext["id"],
                visit_date=visit_date,
                consultation_type=ct_name,
                counsellor_name=counsellor_name,
                changes=changes,
                diagnoses=[dx.get('name', '') for dx in current_diagnoses],
                complaints=current_complaints,
                medications=[{"name": m.get('name', ''), "dosage": m.get('dosage', '')} for m in current_medications],
                has_significant_changes=len([c for c in changes if c.confidence in ['high', 'medium']]) > 0
            ))

        # Reverse to get chronological order (oldest first)
        timeline_visits.reverse()

        return ClinicalTimelineResponse(
            patient=patient,
            timeline=timeline_visits,
            summary={
                "total_visits": len(timeline_visits),
                "first_time_diagnoses": first_time_count,
                "recurring_diagnoses": recurring_count,
                "medication_changes": medication_change_count,
                "resolved_complaints": resolved_complaint_count
            },
            visit_count=len(timeline_visits)
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid student ID")
    except Exception as e:
        logger.error(f"Error getting clinical timeline: {e}")
        raise HTTPException(status_code=500, detail="Failed to get clinical timeline")


# ============================================================================
# Prescreen API Endpoint
# ============================================================================

@router.get("/{student_id}/prescreen", response_model=PrescreenResponse)
async def get_student_prescreen(
    request: Request,
    student_id: str,
    counsellor_id: str = Query(..., description="Counsellor ID (required)"),
    school_id: Optional[str] = Query(None, description="School ID (optional filter)"),
    school_view: bool = Query(False, description="When true, return data authored by OTHER counsellors/assistants at the same school (excludes the requesting counsellor's own records)."),
    _auth = Depends(verify_student_access)
):
    """
    Get prescreen information for a student before consultation.

    The student_id parameter accepts either:
    - External student identifier (e.g., "PAT-001", MRN, etc.)
    - Database UUID

    Returns:
    1. Latest prescreen template extraction results (if available)
    2. Emotion pattern summary (aggregated from last 2 consultations)
    3. Top 3 recommended interventions (from most recent consultation)
    4. Student warning factors (CAUTION segment - allergies, contraindications)
    5. Past diagnosis summary (SUMMARY segment from last consultation)

    The prescreen template is identified by template_code containing 'PRESCREEN'.

    This endpoint requires counsellor_id as prescreen data is counsellor-specific.
    """
    try:
        # Phase 1: Sequential - resolve student (required before everything else)
        effective_school_id = school_id or _get_school_id_from_context(request, counsellor_id)
        patient_uuid = resolve_student_id_or_404(student_id, school_id=effective_school_id)
        view_counsellor_ids = _resolve_school_view_filter(school_view, counsellor_id, patient_uuid)

        patient_info = get_student_info(patient_uuid)
        if not patient_info:
            raise HTTPException(status_code=404, detail="Student not found")

        patient = StudentInfo(
            id=patient_info["id"],
            student_id=patient_info["student_id"],
            full_name=patient_info.get("full_name"),
            date_of_birth=patient_info.get("date_of_birth"),
            gender=patient_info.get("gender")
        )

        # Phase 2: Single shared query to get recent extractions (replaces 4 duplicate queries)
        # Plus parallel count query and prescreen lookup
        loop = asyncio.get_event_loop()

        def _apply_counsellor_filter(q):
            if view_counsellor_ids is not None:
                if not view_counsellor_ids:
                    return None
                return q.in_("counsellor_id", view_counsellor_ids)
            return q.eq("counsellor_id", counsellor_id)

        def _fetch_shared_extractions():
            q = supabase.table("extractions")\
                .select("*, recording_sessions(template_code, assistant_id)")\
                .eq("student_id", str(patient_uuid))
            q = _apply_counsellor_filter(q)
            if q is None:
                return type("R", (), {"data": []})()
            return q.order("created_at", desc=True).limit(10).execute()

        def _fetch_consultation_count():
            q = supabase.table("extractions")\
                .select("id, created_at", count="exact")\
                .eq("student_id", str(patient_uuid))
            q = _apply_counsellor_filter(q)
            if q is None:
                return 0, None
            result = q.order("created_at", desc=True).limit(1).execute()
            count = result.count if result.count is not None else len(result.data or [])
            last_date = None
            if result.data:
                last_date = result.data[0].get("created_at", "")[:10]
            return count, last_date

        def _fetch_prescreen():
            # Prescreen by definition is assistant-authored under a specific counsellor.
            # In school_view mode, no single "owning" counsellor → skip.
            if school_view:
                return None
            return get_latest_prescreen_extraction(patient_uuid, counsellor_id)

        # Run shared extraction fetch, count, and prescreen lookup in parallel
        shared_result, count_result, prescreen_extraction = await asyncio.gather(
            loop.run_in_executor(_prescreen_executor, _fetch_shared_extractions),
            loop.run_in_executor(_prescreen_executor, _fetch_consultation_count),
            loop.run_in_executor(_prescreen_executor, _fetch_prescreen),
        )

        consultation_count, last_visit_date = count_result

        # Process shared extractions: filter out PRESCREEN to get non-prescreen list
        # (in school_view mode we keep assistant-authored rows so users can see them)
        if school_view:
            non_prescreen_extractions = (shared_result.data or [])[:5]
        else:
            non_prescreen_extractions = filter_prescreen_extractions(
                shared_result.data or [], max_results=5
            )
        latest_non_prescreen = non_prescreen_extractions[0] if non_prescreen_extractions else None

        # Process prescreen result
        prescreen_data = None
        prescreen_metadata = None
        has_prescreen = False
        if prescreen_extraction:
            has_prescreen = True
            prescreen_data = get_extraction_data(prescreen_extraction)
            prescreen_metadata = build_extraction_metadata(prescreen_extraction)

        # Phase 3: Run all independent helpers in parallel with pre-fetched data
        def _build_emotions():
            return build_emotion_pattern_summary(
                patient_uuid, counsellor_id, num_visits=2,
                pre_fetched_extractions=non_prescreen_extractions,
                counsellor_ids=view_counsellor_ids, include_assistant=school_view,
            )

        def _build_interventions():
            return get_top_interventions(
                patient_uuid, counsellor_id, limit=3,
                pre_fetched_extraction=latest_non_prescreen,
                counsellor_ids=view_counsellor_ids, include_assistant=school_view,
            )

        def _build_caution_summary():
            return get_caution_and_summary_from_last_extraction(
                patient_uuid, counsellor_id,
                pre_fetched_extraction=latest_non_prescreen,
                counsellor_ids=view_counsellor_ids, include_assistant=school_view,
            )

        def _build_timeline():
            return build_clinical_timeline_data(
                patient_uuid, counsellor_id, num_visits=5,
                pre_fetched_extractions=non_prescreen_extractions,
                counsellor_ids=view_counsellor_ids, include_assistant=school_view,
            )

        def _build_prescription():
            return get_last_prescription_for_prescreen(
                patient_uuid, counsellor_id,
                pre_fetched_extraction=latest_non_prescreen,
                counsellor_ids=view_counsellor_ids, include_assistant=school_view,
            )

        (
            emotion_pattern_summary,
            top_interventions,
            caution_summary,
            clinical_timeline,
            last_prescription_data
        ) = await asyncio.gather(
            loop.run_in_executor(_prescreen_executor, _build_emotions),
            loop.run_in_executor(_prescreen_executor, _build_interventions),
            loop.run_in_executor(_prescreen_executor, _build_caution_summary),
            loop.run_in_executor(_prescreen_executor, _build_timeline),
            loop.run_in_executor(_prescreen_executor, _build_prescription),
        )

        return PrescreenResponse(
            patient=patient,
            prescreen_data=prescreen_data,
            prescreen_metadata=prescreen_metadata,
            has_prescreen=has_prescreen,
            emotion_pattern_summary=emotion_pattern_summary if emotion_pattern_summary.has_emotion_data else None,
            top_interventions=top_interventions,
            warning_factors=caution_summary["caution"],
            warning_factors_date=caution_summary["caution_date"],
            past_diagnosis_summary=caution_summary["summary"],
            past_diagnosis_summary_date=caution_summary["summary_date"],
            clinical_timeline=clinical_timeline,
            last_prescription=last_prescription_data["prescription"],
            last_prescription_date=last_prescription_data["prescription_date"],
            consultation_count=consultation_count,
            last_visit_date=last_visit_date
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting student prescreen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get student prescreen")


# ============================================================================
# Neopaed Student Initialization
# ============================================================================

class NeopaedSourceStats(BaseModel):
    """Stats for a single Neopaed source (NICU or OP)"""
    success: bool = False
    created: int = 0
    updated: int = 0
    error: Optional[str] = None


class NeopaedInitResponse(BaseModel):
    """Response for Neopaed student initialization (NICU + OP combined)"""
    success: bool
    created: int = 0
    updated: int = 0
    total_processed: int = 0
    nicu: Optional[NeopaedSourceStats] = None
    op: Optional[NeopaedSourceStats] = None
    errors: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


@router.post("/initialize/neopaed", response_model=NeopaedInitResponse)
async def initialize_neopaed_students():
    """
    Initialize students from Neopaed school system (NICU + OP combined).

    Fetches students from both school APIs and syncs to database:
    - NICU inpatients (get-nicu-inpatient-list)
    - OP babies (today-op-baby-list)

    For each student:
    - Creates new students if they don't exist (using uhid as student_id)
    - Updates existing students' add_info field with latest data
    - Stores visitNumber/visitId, roomNo, bedNo, gestation, etc. in add_info JSONB

    Returns:
        NeopaedInitResponse with counts of created/updated students (total + per source)
    """
    try:
        result = await fetch_all_neopaed_students()
        return NeopaedInitResponse(**result)
    except Exception as e:
        logger.error(f"Error initializing Neopaed students: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to initialize Neopaed students")



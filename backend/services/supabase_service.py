"""
Enhanced Supabase Database Service for Live Recording Feature

This service handles all database operations for the enhanced schema:
- Counsellors management
- Students management
- Prompt templates with versioning
- Recording sessions with template mapping
- Audio chunks with automatic cleanup
- Processing jobs
- Audit logging
- Performance metrics tracking
- Segment configuration management (OP summary extraction)
  - User-customizable segment categorization (CORE/ADDITIONAL/FULL)
  - Brevity level control (concise/balanced/detailed)
  - Terminology style control (medical_terms/simple_terms/as_spoken)
  - Template configurations for different specialties and use cases

Environment Variables Required:
- SUPABASE_URL: Your Supabase project URL
- SUPABASE_SERVICE_KEY: Your Supabase service role key (server-side only)
"""

import json
import os
import uuid
import logging
import time
import asyncio
from typing import Dict, List, Optional, Any, Callable, TypeVar
from datetime import datetime, timezone
from supabase import create_client, Client
from dotenv import load_dotenv
import httpx
from cachetools import TTLCache

# Setup logger
logger = logging.getLogger(__name__)

# ============================================================================
# In-Memory Caches (TTL-based) - Reduce repeated DB queries
# ============================================================================
# All caches use 8-hour TTL since data rarely changes and we have invalidation hooks

_CACHE_TTL_SECONDS = 28800  # 8 hours (invalidated on updates)

# Cache for counsellor's school_id (infinite TTL - manual invalidation only)
# Counsellor→school mapping never changes unless counsellor is reassigned
# Key: counsellor_id (str), Value: school_id (str) or None
_doctor_hospital_cache: Dict[str, Optional[str]] = {}

# Cache for consultation_types
# Key: consultation_type_id (str), Value: consultation_type dict
_consultation_type_cache: TTLCache = TTLCache(maxsize=50, ttl=_CACHE_TTL_SECONDS)

# Cache for consultation_type by code
# Key: type_code (str), Value: consultation_type dict
_consultation_type_by_code_cache: TTLCache = TTLCache(maxsize=50, ttl=_CACHE_TTL_SECONDS)

# Cache for templates
# Key: template_code (str), Value: template dict
_template_by_code_cache: TTLCache = TTLCache(maxsize=100, ttl=_CACHE_TTL_SECONDS)

# Key: template_id (str), Value: template dict
_template_by_id_cache: TTLCache = TTLCache(maxsize=100, ttl=_CACHE_TTL_SECONDS)

# Cache for get_template_by_code_unified RPC
# Key: (template_code, counsellor_id, consultation_type_id), Value: result dict
_template_unified_cache: TTLCache = TTLCache(maxsize=200, ttl=_CACHE_TTL_SECONDS)

# ============================================================================
# School Settings Cache (INFINITE TTL - manual invalidation only)
# ============================================================================
# This cache stores per-school settings like FFmpeg stitching, audio quality
# thresholds, etc. Uses infinite TTL (simple dict) since settings rarely change
# and we have explicit invalidation when settings are updated.

from threading import Lock as ThreadLock
from concurrent.futures import ThreadPoolExecutor

_service_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="svc")
_hospital_settings_cache: Dict[str, Dict[str, Any]] = {}
_hospital_settings_lock = ThreadLock()

load_dotenv()

# ============================================================================
# Cache Invalidation Functions
# ============================================================================

def invalidate_counsellor_school_cache(counsellor_id: Optional[uuid.UUID] = None) -> int:
    """
    Invalidate counsellor_school cache entries.

    Args:
        counsellor_id: Specific counsellor to invalidate, or None to clear all

    Returns:
        Number of entries invalidated
    """
    global _doctor_hospital_cache
    if counsellor_id:
        cache_key = str(counsellor_id)
        if cache_key in _doctor_hospital_cache:
            del _doctor_hospital_cache[cache_key]
            logger.debug(f"[CACHE_INVALIDATE] Cleared counsellor_school cache for counsellor {str(counsellor_id)[:8]}...")
            return 1
        return 0
    else:
        count = len(_doctor_hospital_cache)
        _doctor_hospital_cache.clear()
        logger.debug(f"[CACHE_INVALIDATE] Cleared all counsellor_school cache ({count} entries)")
        return count


def invalidate_consultation_type_cache(
    consultation_type_id: Optional[uuid.UUID] = None,
    type_code: Optional[str] = None
) -> int:
    """
    Invalidate consultation_type cache entries.

    IMPORTANT: When either parameter is provided, this function clears entries
    from BOTH caches (_consultation_type_cache by ID and _consultation_type_by_code_cache by code)
    to ensure consistency.

    Args:
        consultation_type_id: Specific ID to invalidate
        type_code: Specific code to invalidate
        If both None, clears all entries

    Returns:
        Number of entries invalidated
    """
    global _consultation_type_cache, _consultation_type_by_code_cache
    count = 0

    # If type_code provided, also find and clear the ID-based cache entry
    if type_code:
        # Clear from code-based cache
        if type_code in _consultation_type_by_code_cache:
            cached_entry = _consultation_type_by_code_cache[type_code]
            # Also clear from ID-based cache using the ID from the cached entry
            if cached_entry and cached_entry.get("id"):
                id_cache_key = str(cached_entry["id"])
                if id_cache_key in _consultation_type_cache:
                    del _consultation_type_cache[id_cache_key]
                    count += 1
            del _consultation_type_by_code_cache[type_code]
            count += 1

    # If consultation_type_id provided, also find and clear the code-based cache entry
    if consultation_type_id:
        cache_key = str(consultation_type_id)
        if cache_key in _consultation_type_cache:
            cached_entry = _consultation_type_cache[cache_key]
            # Also clear from code-based cache using the type_code from the cached entry
            if cached_entry and cached_entry.get("type_code"):
                code = cached_entry["type_code"]
                if code in _consultation_type_by_code_cache:
                    del _consultation_type_by_code_cache[code]
                    count += 1
            del _consultation_type_cache[cache_key]
            count += 1

    if not consultation_type_id and not type_code:
        count = len(_consultation_type_cache) + len(_consultation_type_by_code_cache)
        _consultation_type_cache.clear()
        _consultation_type_by_code_cache.clear()
        logger.debug(f"[CACHE_INVALIDATE] Cleared all consultation_type caches ({count} entries)")
    elif count > 0:
        logger.debug(f"[CACHE_INVALIDATE] Cleared consultation_type cache ({count} entries)")

    return count


def invalidate_template_cache(
    template_id: Optional[uuid.UUID] = None,
    template_code: Optional[str] = None
) -> int:
    """
    Invalidate template cache entries.

    Args:
        template_id: Specific template ID to invalidate
        template_code: Specific template code to invalidate
        If both None, clears all entries

    Returns:
        Number of entries invalidated
    """
    global _template_by_code_cache, _template_by_id_cache, _template_unified_cache
    count = 0

    if template_id:
        cache_key = str(template_id)
        if cache_key in _template_by_id_cache:
            del _template_by_id_cache[cache_key]
            count += 1

    if template_code:
        if template_code in _template_by_code_cache:
            del _template_by_code_cache[template_code]
            count += 1
        # Also clear unified cache entries with this template_code
        # Key format is "template_code:counsellor_id" (colon separator)
        keys_to_delete = [k for k in _template_unified_cache if k.startswith(template_code + ":")]
        for k in keys_to_delete:
            del _template_unified_cache[k]
            count += 1

    if not template_id and not template_code:
        count = len(_template_by_code_cache) + len(_template_by_id_cache) + len(_template_unified_cache)
        _template_by_code_cache.clear()
        _template_by_id_cache.clear()
        _template_unified_cache.clear()
        logger.debug(f"[CACHE_INVALIDATE] Cleared all template caches ({count} entries)")
    elif count > 0:
        logger.debug(f"[CACHE_INVALIDATE] Cleared template cache ({count} entries)")

    # Keep schema-derived merge metadata in sync with template/schema changes.
    try:
        from services import merge_metadata_service
        merge_metadata_service.clear(template_id)
    except Exception as e:
        logger.debug(f"[CACHE_INVALIDATE] merge metadata clear skipped: {e}")

    return count


def invalidate_processing_mode_cache(mode_code: Optional[str] = None) -> int:
    """
    Invalidate all processing mode model caches.

    Args:
        mode_code: Specific mode to invalidate, or None to clear all

    Returns:
        Number of entries invalidated
    """
    global _extraction_model_cache, _triage_model_cache, _merge_model_cache
    global _compare_model_cache, _emotion_model_cache, _insights_model_cache
    global _validator_model_cache

    count = 0
    caches = [
        _extraction_model_cache,
        _triage_model_cache,
        _merge_model_cache,
        _compare_model_cache,
        _emotion_model_cache,
        _insights_model_cache,
        _validator_model_cache,
    ]

    if mode_code:
        for cache in caches:
            if mode_code in cache:
                del cache[mode_code]
                count += 1
        if count > 0:
            logger.debug(f"[CACHE_INVALIDATE] Cleared processing_mode caches for '{mode_code}' ({count} entries)")
    else:
        for cache in caches:
            count += len(cache)
            cache.clear()
        logger.debug(f"[CACHE_INVALIDATE] Cleared all processing_mode caches ({count} entries)")

    return count


# ============================================================================
# School Settings Cache (Infinite TTL)
# ============================================================================

def get_school_settings_cached(school_id: str) -> Dict[str, Any]:
    """
    Get school settings with infinite TTL cache.

    Cache is only invalidated when settings are updated via invalidate_school_settings_cache().
    This provides O(1) lookup for hot-path operations like recording processing.

    Args:
        school_id: School UUID string

    Returns:
        Dict with school settings:
        - use_ffmpeg_stitching (bool): Enable FFmpeg for audio stitching
        - audio_quality_block_threshold (str): 'poor', 'fair', or 'none'
        - min_transcript_length (int): Min transcript chars to proceed
        - max_silence_ratio (float): Max silence ratio (0.0-1.0)
    """
    if not school_id:
        return _get_default_school_settings()

    # Check cache first (thread-safe read)
    with _hospital_settings_lock:
        if school_id in _hospital_settings_cache:
            return _hospital_settings_cache[school_id]

    # Cache miss - fetch from DB
    try:
        result = supabase.table("schools").select(
            "use_ffmpeg_stitching, audio_quality_block_threshold, "
            "min_transcript_length, max_silence_ratio, min_snr_db, min_rms_db, "
            "min_speech_ratio, enable_audio_validation, feature_flags, "
            "silence_thresh_dbfs, min_silence_len_ms, silence_padding_ms"
        ).eq("id", school_id).single().execute()

        if result.data:
            settings = {
                "use_ffmpeg_stitching": result.data.get("use_ffmpeg_stitching", False),
                "audio_quality_block_threshold": result.data.get("audio_quality_block_threshold", "poor"),
                "min_transcript_length": result.data.get("min_transcript_length", 20),
                "max_silence_ratio": float(result.data.get("max_silence_ratio", 0.90)),
                "min_snr_db": float(result.data.get("min_snr_db") if result.data.get("min_snr_db") is not None else 10.0),
                "min_rms_db": float(result.data.get("min_rms_db") if result.data.get("min_rms_db") is not None else -57.0),
                "min_speech_ratio": float(result.data.get("min_speech_ratio") if result.data.get("min_speech_ratio") is not None else 0.0),
                "enable_audio_validation": result.data.get("enable_audio_validation", True),
                "feature_flags": result.data.get("feature_flags", _get_default_feature_flags()),
                "silence_thresh_dbfs": float(result.data.get("silence_thresh_dbfs") if result.data.get("silence_thresh_dbfs") is not None else -60.0),
                "min_silence_len_ms": int(result.data.get("min_silence_len_ms") if result.data.get("min_silence_len_ms") is not None else 5000),
                "silence_padding_ms": int(result.data.get("silence_padding_ms") if result.data.get("silence_padding_ms") is not None else 200),
            }
        else:
            settings = _get_default_school_settings()

        # Store in cache (thread-safe write)
        with _hospital_settings_lock:
            _hospital_settings_cache[school_id] = settings

        logger.debug(f"[CACHE] School settings cached for {school_id[:8]}...")
        return settings

    except Exception as e:
        logger.warning(f"[CACHE] Failed to fetch school settings for {school_id}: {e}")
        return _get_default_school_settings()


def invalidate_school_settings_cache(school_id: Optional[str] = None) -> int:
    """
    Invalidate cached settings for a school.

    Call this when school settings are updated via the API.

    Args:
        school_id: Specific school to invalidate, or None to clear all

    Returns:
        Number of entries invalidated
    """
    global _hospital_settings_cache

    with _hospital_settings_lock:
        if school_id:
            if school_id in _hospital_settings_cache:
                del _hospital_settings_cache[school_id]
                logger.debug(f"[CACHE_INVALIDATE] Cleared school settings cache for {school_id[:8]}...")
                return 1
            return 0
        else:
            count = len(_hospital_settings_cache)
            _hospital_settings_cache.clear()
            logger.debug(f"[CACHE_INVALIDATE] Cleared all school settings cache ({count} entries)")
            return count


def _get_default_feature_flags() -> Dict[str, bool]:
    """Return default feature flags for schools."""
    return {
        "care_plan": True,
        "merge": True,
        "interventions": True,
        "upload": True,
        "ocr": False,
        "edit_prescription": True,
        "edit_investigation": True,
        "edit_record": True,
        "patient_qa": True,
        "doctor_qa": True,
        "template_configuration": True,
        "patient_registration": True,
        "billing": False,
        "nudge_plan": False,
        "iris": False,
        "triage_support": False,
    }


def _get_default_school_settings() -> Dict[str, Any]:
    """Return default school settings."""
    return {
        "use_ffmpeg_stitching": False,
        "audio_quality_block_threshold": "poor",
        "min_transcript_length": 20,
        "max_silence_ratio": 0.90,
        "min_snr_db": 10.0,
        "min_rms_db": -57.0,
        "min_speech_ratio": 0.0,
        "enable_audio_validation": True,
        "feature_flags": _get_default_feature_flags(),
        "silence_thresh_dbfs": -60.0,
        "min_silence_len_ms": 5000,
        "silence_padding_ms": 200,
    }


# ============================================================================
# Retry Logic for Network Resilience
# ============================================================================

T = TypeVar('T')

def retry_on_network_error(
    func: Callable[[], T],
    max_retries: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 5.0,
    backoff_multiplier: float = 2.0
) -> T:
    """
    Retry a function on network errors with exponential backoff.

    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries
        backoff_multiplier: Multiplier for exponential backoff

    Returns:
        Result of successful function call

    Raises:
        Last exception if all retries fail
    """
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return func()
        except (
            httpx.ReadError,
            httpx.ReadTimeout,
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.LocalProtocolError,  # HTTP/2 connection state errors (retryable)
            httpx.RemoteProtocolError,  # Server-side protocol errors (retryable)
            BlockingIOError,  # errno 35 (EAGAIN) - Resource temporarily unavailable
        ) as e:
            last_exception = e

            if attempt < max_retries:
                logger.warning(
                    f"[RETRY] Network/Protocol error on attempt {attempt + 1}/{max_retries + 1}: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                delay = min(delay * backoff_multiplier, max_delay)
            else:
                logger.error(
                    f"[RETRY] All {max_retries + 1} attempts failed. Last error: {e}"
                )
        except OSError as e:
            # Retry EAGAIN (errno 35) and EWOULDBLOCK (errno 11) - resource temporarily unavailable
            import errno
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK, 35, 11):
                last_exception = e
                if attempt < max_retries:
                    logger.warning(
                        f"[RETRY] OS error (errno {e.errno}) on attempt {attempt + 1}/{max_retries + 1}: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_multiplier, max_delay)
                else:
                    logger.error(
                        f"[RETRY] All {max_retries + 1} attempts failed. Last error: {e}"
                    )
            else:
                # Non-retryable OS error
                logger.error(f"[RETRY] Non-retryable OS error (errno {e.errno}): {e}")
                raise
        except Exception as e:
            # Non-network errors should not be retried
            logger.warning(f"[RETRY] Non-retryable error: {e}")
            raise

    # If we get here, all retries failed
    if last_exception is not None:
        raise last_exception
    raise RuntimeError("All retry attempts failed with no captured exception")

# ============================================================================
# Supabase Client Initialization
# ============================================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError(
        "Missing Supabase credentials. Please set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env file"
    )

# ============================================================================
# Connection Pool Configuration
# ============================================================================
# Configure httpx limits BEFORE creating Supabase client
# This prevents "[Errno 35] Resource temporarily unavailable" during parallel operations
#
# The error occurs when:
# - Multiple parallel uploads/extractions run simultaneously
# - Each operation makes multiple DB calls
# - OS-level socket/file descriptor limits are hit
#
# Solution: Create a custom httpx client with higher limits
# ============================================================================

# Create a shared httpx client with higher connection limits
_httpx_limits = httpx.Limits(
    max_connections=200,          # Default: 100 - increased for parallel operations
    max_keepalive_connections=50, # Default: 20 - more keepalive for reuse
    keepalive_expiry=30,          # Default: 5 - longer keepalive
)

# Create Supabase client with custom options
try:
    from supabase import ClientOptions

    custom_options = ClientOptions(
        postgrest_client_timeout=30,
    )
    supabase: Client = create_client(
        SUPABASE_URL,
        SUPABASE_SERVICE_KEY,
        options=custom_options
    )
    logger.info("✅ Supabase client initialized with custom options")
except ImportError:
    # Fallback for older supabase-py versions
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    logger.info("✅ Supabase client initialized with default options")

# Monkey-patch the postgrest client to use our custom httpx limits
# This ensures all Supabase operations use the configured connection pool
try:
    if hasattr(supabase, 'postgrest') and hasattr(supabase.postgrest, 'session'):
        # Get existing session's headers and base_url
        old_session = supabase.postgrest.session
        # Create new httpx client with our limits
        new_session = httpx.Client(
            base_url=str(supabase.postgrest.base_url),
            headers=dict(old_session.headers),
            timeout=30.0,
            limits=_httpx_limits,
        )
        # Replace the session
        supabase.postgrest.session = new_session
        logger.info(f"✅ Supabase httpx client configured with limits: max_conn={_httpx_limits.max_connections}, keepalive={_httpx_limits.max_keepalive_connections}")
except Exception as e:
    logger.warning(f"⚠️ Could not configure custom httpx limits: {e}")


# ============================================================================
# Counsellors Operations
# ============================================================================

def create_counsellor(
    email: str,
    full_name: str,
    specialization: Optional[str] = None,
    default_template: Optional[str] = 'SMALL',
) -> Dict[str, Any]:
    """Create a new counsellor profile"""
    data = {
        "email": email,
        "full_name": full_name,
        "specialization": specialization,
        "default_template": default_template,
    }
    response = supabase.table("counsellors").insert(data).execute()
    return response.data[0] if response.data else {}


def get_counsellor_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get counsellor by email"""
    response = supabase.table("counsellors").select("*").eq("email", email).execute()
    return response.data[0] if response.data else None


def get_counsellor_by_id(counsellor_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get counsellor by ID"""
    response = supabase.table("counsellors").select("*").eq("id", str(counsellor_id)).execute()
    return response.data[0] if response.data else None


def get_counsellor_school_id_cached(counsellor_id: uuid.UUID) -> Optional[str]:
    """
    Get counsellor's school_id with caching.

    Uses in-memory cache with infinite TTL (manual invalidation via invalidate_counsellor_school_cache).
    This is called frequently during extraction pipeline for medicine/investigation lookups.

    Args:
        counsellor_id: Counsellor's UUID

    Returns:
        School ID string or None
    """
    cache_key = str(counsellor_id)

    # Check cache first
    if cache_key in _doctor_hospital_cache:
        return _doctor_hospital_cache[cache_key]

    # Cache miss - query database
    try:
        response = retry_on_network_error(
            lambda: supabase.table("counsellors")
            .select("school_id")
            .eq("id", cache_key)
            .limit(1)
            .execute()
        )
        school_id = response.data[0].get("school_id") if response.data else None
        _doctor_hospital_cache[cache_key] = school_id
        return school_id
    except Exception as e:
        logger.error(f"Error getting counsellor school_id: {type(e).__name__}")
        return None


def update_counsellor_last_login(counsellor_id: uuid.UUID) -> None:
    """Update counsellor's last login timestamp"""
    supabase.table("counsellors").update({
        "last_login_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", str(counsellor_id)).execute()


# ============================================================================
# Students Operations (Optional)
# ============================================================================

def create_or_get_student(
    student_id: str,
    full_name: Optional[str] = None,
    ip_id: Optional[str] = None,
    op_id: Optional[str] = None,
    school_id: Optional[str] = None,
    counsellor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create student if doesn't exist, otherwise return existing (with retry logic).
    Auto-links counsellor to student's counsellor_ids array if not already present.

    Args:
        student_id: External student identifier (e.g., MRN)
        full_name: Student's full name (optional)
        ip_id: Inpatient visit/admission ID (optional, from EHR)
        op_id: Outpatient visit ID (optional, from EHR)
        school_id: School UUID for scoped student isolation (optional)
        counsellor_id: Counsellor UUID to auto-link to student (optional)

    Returns:
        Student record dict
    """
    # Check if exists (scoped by school_id when provided)
    def _check_student():
        query = supabase.table("students").select("*").eq("student_id", student_id)
        if school_id:
            query = query.eq("school_id", school_id)
        else:
            query = query.is_("school_id", "null")
        return query.execute()

    response = retry_on_network_error(_check_student)

    if response.data:
        return response.data[0]

    # Create new
    data = {
        "student_id": student_id,
        "full_name": full_name,
    }

    if school_id:
        data["school_id"] = school_id

    # Auto-link counsellor on creation
    if counsellor_id:
        data["counsellor_ids"] = [counsellor_id]

    # Add optional IP/OP IDs if provided
    if ip_id:
        data["ip_id"] = ip_id
    if op_id:
        data["op_id"] = op_id

    def _create_student():
        response = supabase.table("students").insert(data).execute()
        return response

    try:
        response = retry_on_network_error(_create_student)
        return response.data[0] if response.data else {}
    except Exception as e:
        # Race condition: another request created the student between our check and insert
        if "23505" in str(e):
            response = retry_on_network_error(_check_student)
            if response.data:
                return response.data[0]
        raise


def link_counsellor_to_student(patient_uuid: str, counsellor_id: str):
    """
    Append counsellor_id to student's counsellor_ids array if not already present.
    Sync function — call via asyncio.create_task(asyncio.to_thread(...)) for fire-and-forget.
    """
    try:
        result = supabase.table("students").select("counsellor_ids").eq("id", patient_uuid).execute()
        if not result.data:
            return

        current_ids = result.data[0].get("counsellor_ids") or []
        if counsellor_id in current_ids:
            return  # Already linked

        current_ids.append(counsellor_id)
        supabase.table("students").update({"counsellor_ids": current_ids}).eq("id", patient_uuid).execute()
        from services.log_sanitizer import truncate_id as _tid
        logger.info(f"Auto-linked counsellor {_tid(counsellor_id)} to student {_tid(patient_uuid)}")
    except Exception as e:
        logger.warning(f"Failed to auto-link counsellor to student: {e}")


# ============================================================================
# Recording Sessions Operations (Enhanced)
# ============================================================================

def create_recording_session(
    correlation_id: uuid.UUID,
    counsellor_id: str,
    student_id: str,
    template_code: str,
    processing_mode: str,
    extraction_mode: Optional[str],
    transcription_model: str,
    extraction_model: str,
    chunk_duration_seconds: int = 10,
    consultation_type_id: Optional[str] = None,
    template_name: Optional[str] = None,
    session_context_json: Optional[Dict[str, Any]] = None,
    assistant_id: Optional[str] = None,
    recording_metadata_json: Optional[Dict[str, Any]] = None,
    api_client_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new recording session with template-based configuration.

    Args:
        correlation_id: Unique session identifier
        counsellor_id: Counsellor's UUID
        student_id: Student identifier (external ID like MRN)
        template_code: Template code for database lookups (unique identifier) or 'TRANSCRIPT_ONLY'
        processing_mode: Processing mode code ('fast', 'default', 'thorough', etc.)
        extraction_mode: Extraction mode ('core', 'additional', 'full') or None
        transcription_model: Gemini model for transcription
        extraction_model: Gemini model for extraction
        chunk_duration_seconds: Duration of each audio chunk in seconds
        consultation_type_id: Consultation type UUID (for parallel prompt generation optimization)
        template_name: Template display name (optional, for human readability in DB)
        session_context_json: Lean session context with template references (~1-2KB).
            Contains template_id, prompt/schema hashes, has_preassembled flag.
            Eliminates redundant DB queries during /chunk and background processing.
        assistant_id: Optional assistant UUID who initiated/managed the recording session
        recording_metadata_json: Additional metadata (student info, counsellor info, custom fields)
            that flows through to /status response. Stored as JSONB.
        api_client_id: Optional API client UUID that initiated this session (for usage tracking)
    """
    # Extract ip_id and op_id from recording_metadata_json if provided
    ip_id = None
    op_id = None
    if recording_metadata_json:
        ip_id = recording_metadata_json.get('ip_id')
        op_id = recording_metadata_json.get('op_id')

    # Derive school_id from counsellor for student scoping
    school_id = get_counsellor_school_id_cached(counsellor_id)

    # Auto-create or get student record by external student_id
    student_record = create_or_get_student(
        student_id=student_id,
        full_name=None,  # Frontend doesn't send full_name yet
        ip_id=ip_id,
        op_id=op_id,
        school_id=school_id,
        counsellor_id=counsellor_id,
    )
    patient_uuid = student_record['id']

    data = {
        "correlation_id": str(correlation_id),
        "counsellor_id": counsellor_id,
        "student_id": patient_uuid,  # Link to students table UUID
        "student_identifier": student_id,  # Keep original external ID for reference
        "template_code": template_code,  # Unique identifier for template lookups
        "template_name": template_name or template_code,  # Display name (fallback to code if not provided)
        "processing_mode": processing_mode,
        "extraction_mode": extraction_mode,
        "transcription_model": transcription_model,
        "extraction_model": extraction_model,
        "chunk_duration_seconds": chunk_duration_seconds,
        "consultation_type_id": consultation_type_id,  # For parallel prompt generation optimization
        "status": "RECORDING",
        "session_context_json": session_context_json or {},  # Lean session context (~1-2KB)
    }

    # Add assistant_id if provided
    if assistant_id:
        data["assistant_id"] = assistant_id

    # Add api_client_id if provided (for usage tracking)
    if api_client_id:
        data["api_client_id"] = api_client_id

    # Add recording metadata if provided (flows to /status response)
    if recording_metadata_json:
        data["recording_metadata_json"] = recording_metadata_json

    def _create_session():
        response = supabase.table("recording_sessions").insert(data).execute()
        return response

    response = retry_on_network_error(_create_session)
    session = response.data[0] if response.data else {}

    from services.log_sanitizer import truncate_id as _tid
    logger.info(f"Created recording session: {session.get('id')} for counsellor: {_tid(str(counsellor_id))}")

    return session


def create_minimal_recording_session(
    correlation_id: uuid.UUID,
    counsellor_id: str,
    student_id: str,
    template_code: Optional[str],
    processing_mode: str,
    extraction_mode: Optional[str],
    chunk_duration_seconds: int = 10,
    template_name: Optional[str] = None,
    assistant_id: Optional[str] = None,
    recording_metadata_json: Optional[Dict[str, Any]] = None,
    api_client_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a minimal recording session for fast /start response.

    Only does student lookup + session insert (1-2 DB calls).
    Heavy validation (template lookup, processing mode config, session context)
    is deferred to a background task that updates the session afterward.

    The session is created with validation_status='pending' and updated to
    'completed' or 'failed' by the background task.
    """
    # Extract ip_id and op_id from recording_metadata_json if provided
    ip_id = None
    op_id = None
    if recording_metadata_json:
        ip_id = recording_metadata_json.get('ip_id')
        op_id = recording_metadata_json.get('op_id')

    # Derive school_id from counsellor for student scoping
    school_id = get_counsellor_school_id_cached(counsellor_id)

    # Auto-create or get student record by external student_id
    student_record = create_or_get_student(
        student_id=student_id,
        full_name=None,
        ip_id=ip_id,
        op_id=op_id,
        school_id=school_id,
        counsellor_id=counsellor_id,
    )
    patient_uuid = student_record['id']

    data = {
        "correlation_id": str(correlation_id),
        "counsellor_id": counsellor_id,
        "student_id": patient_uuid,
        "student_identifier": student_id,
        "template_code": template_code,
        "template_name": template_name or template_code or "Unknown",
        "processing_mode": processing_mode,
        "extraction_mode": extraction_mode,
        "chunk_duration_seconds": chunk_duration_seconds,
        "status": "RECORDING",
        "validation_status": "pending",
    }

    # Add assistant_id if provided
    if assistant_id:
        data["assistant_id"] = assistant_id

    # Add api_client_id if provided (for usage tracking)
    if api_client_id:
        data["api_client_id"] = api_client_id

    # Add recording metadata if provided (flows to /status response)
    if recording_metadata_json:
        data["recording_metadata_json"] = recording_metadata_json

    def _create_session():
        response = supabase.table("recording_sessions").insert(data).execute()
        return response

    response = retry_on_network_error(_create_session)
    session = response.data[0] if response.data else {}

    from services.log_sanitizer import truncate_id as _tid
    logger.info(f"Created minimal recording session: {session.get('id')} for counsellor: {_tid(str(counsellor_id))} (validation_status=pending)")

    return session


def get_session_by_correlation_id(correlation_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Retrieve a recording session by its correlation ID with retry logic"""
    def _fetch_session():
        response = (
            supabase.table("recording_sessions")
            .select("*")
            .eq("correlation_id", str(correlation_id))
            .execute()
        )
        return response.data[0] if response.data else None

    return retry_on_network_error(_fetch_session)


def update_session_status(
    correlation_id: uuid.UUID,
    status: str,
    **kwargs
) -> Dict[str, Any]:
    """Update the status of a recording session (with audit logging)"""
    # Get old values first
    old_session = get_session_by_correlation_id(correlation_id)

    update_data = {"status": status, **kwargs}

    if status == "SUBMITTED":
        update_data["submitted_at"] = datetime.now(timezone.utc).isoformat()
    elif status in ["COMPLETED", "ERROR"]:
        update_data["completed_at"] = datetime.now(timezone.utc).isoformat()

    def _update_session():
        response = (
            supabase.table("recording_sessions")
            .update(update_data)
            .eq("correlation_id", str(correlation_id))
            .execute()
        )
        return response

    response = retry_on_network_error(_update_session)

    new_session = response.data[0] if response.data else {}

    # Log status change
    if new_session:
        log_session_audit(
            session_id=uuid.UUID(new_session["id"]),
            action="STATUS_CHANGE",
            old_values={"status": old_session["status"]} if old_session else None,
            new_values={"status": status},
            changed_by="system"
        )

    return new_session


def cancel_session(correlation_id: uuid.UUID) -> Dict[str, Any]:
    """Cancel a recording session"""
    return update_session_status(correlation_id, "CANCELLED")


def cleanup_chunks_and_save_full_audio(
    session_id: uuid.UUID,
    full_audio_data: str,
    full_audio_mime_type: str,
    full_audio_size_bytes: int,
    processed_audio_data: str = None,
) -> None:
    """
    Delete audio chunks and save full recording to session.
    Uses Supabase RPC function for atomicity.

    Args:
        processed_audio_data: Optional silence-removed audio (base64).
            When provided, stored separately for comparison playback.
    """
    supabase.rpc("cleanup_chunks_after_processing", {
        "p_session_id": str(session_id),
        "p_full_audio_data": full_audio_data,
        "p_full_audio_mime_type": full_audio_mime_type,
        "p_full_audio_size_bytes": full_audio_size_bytes,
        "p_processed_audio_data": processed_audio_data,
    }).execute()


# ============================================================================
# Audio Chunks Operations
# ============================================================================

def save_audio_chunk(
    session_id: uuid.UUID,
    chunk_index: int,
    audio_data: str,
    mime_type: str,
    duration_seconds: Optional[float] = None,
    is_last: bool = False,
) -> Dict[str, Any]:
    """
    Save an audio chunk to the database (idempotent - safe to retry with network resilience).

    If chunk already exists, returns the existing chunk instead of failing.
    """
    # Check if chunk already exists
    def _check_existing_chunk():
        existing = (
            supabase.table("audio_chunks")
            .select("*")
            .eq("session_id", str(session_id))
            .eq("chunk_index", chunk_index)
            .execute()
        )
        return existing

    existing = retry_on_network_error(_check_existing_chunk)

    if existing.data:
        # Chunk already exists - return it (idempotent operation)
        return existing.data[0]

    # Insert new chunk
    data = {
        "session_id": str(session_id),
        "chunk_index": chunk_index,
        "chunk_timestamp": datetime.now(timezone.utc).isoformat(),
        "audio_data": audio_data,
        "mime_type": mime_type,
        "duration_seconds": duration_seconds,
        "file_size_bytes": len(audio_data),
        "is_last": is_last,
    }

    try:
        def _insert_chunk():
            response = supabase.table("audio_chunks").insert(data).execute()
            return response

        response = retry_on_network_error(_insert_chunk)
        chunk = response.data[0] if response.data else {}

        # Log chunk upload
        if chunk:
            log_session_audit(
                session_id=session_id,
                action="CHUNK_UPLOAD",
                new_values={"chunk_index": chunk_index, "is_last": is_last},
                changed_by="system"
            )

        return chunk

    except Exception as e:
        # Handle race condition: if duplicate key error, fetch existing chunk
        # APIError can have different structures, check multiple ways
        is_duplicate = False

        # Check if it's a postgrest APIError with code attribute
        if hasattr(e, 'code') and getattr(e, 'code', None) == '23505':
            is_duplicate = True
        # Check args[0] as dict
        elif e.args and isinstance(e.args[0], dict) and e.args[0].get('code') == '23505':
            is_duplicate = True
        # Check string representation for duplicate key error code
        elif '23505' in str(e) and 'duplicate key' in str(e).lower():
            is_duplicate = True

        if is_duplicate:
            # Duplicate key - fetch and return existing chunk (idempotent handling)
            logger.info(
                f"[CHUNK_UPLOAD] Duplicate chunk detected for session {session_id}, index {chunk_index}. "
                f"Returning existing chunk (idempotent operation)."
            )

            def _fetch_duplicate():
                existing = (
                    supabase.table("audio_chunks")
                    .select("*")
                    .eq("session_id", str(session_id))
                    .eq("chunk_index", chunk_index)
                    .execute()
                )
                return existing

            existing = retry_on_network_error(_fetch_duplicate)

            if existing.data:
                return existing.data[0]

        # Re-raise if not a duplicate key error
        raise


def get_session_chunks(session_id: uuid.UUID) -> List[Dict[str, Any]]:
    """Retrieve all audio chunks for a session, ordered by chunk_index"""
    response = (
        supabase.table("audio_chunks")
        .select("*")
        .eq("session_id", str(session_id))
        .order("chunk_index")
        .execute()
    )
    return response.data if response.data else []


def get_last_chunk_timestamp(session_id: uuid.UUID) -> Optional[datetime]:
    """Get the timestamp of the last audio chunk for a session"""
    response = (
        supabase.table("audio_chunks")
        .select("created_at")
        .eq("session_id", str(session_id))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if response.data and len(response.data) > 0:
        from datetime import datetime
        timestamp_str = response.data[0]["created_at"]
        # Parse ISO format timestamp
        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    return None


def get_chunk_count(session_id: uuid.UUID) -> int:
    """Get the total number of chunks for a session"""
    response = (
        supabase.table("audio_chunks")
        .select("id", count="exact")
        .eq("session_id", str(session_id))
        .execute()
    )
    return response.count if hasattr(response, 'count') else 0


def delete_session_chunks(session_id: uuid.UUID) -> None:
    """Delete all chunks for a session (called after stitching)"""
    supabase.table("audio_chunks").delete().eq("session_id", str(session_id)).execute()


# ============================================================================
# Processing Jobs Operations
# ============================================================================

def create_processing_job(
    session_id: uuid.UUID,
    submission_id: uuid.UUID,
) -> Dict[str, Any]:
    """Create a new processing job for a submitted session"""
    data = {
        "submission_id": str(submission_id),
        "session_id": str(session_id),
        "status": "PENDING",
        "progress_percentage": 0,
        "progress_message": "Queued for processing",
    }

    response = supabase.table("processing_jobs").insert(data).execute()
    return response.data[0] if response.data else {}


def get_job_by_submission_id(submission_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Retrieve a processing job by its submission ID with retry logic"""
    def _fetch_job():
        response = (
            supabase.table("processing_jobs")
            .select("*")
            .eq("submission_id", str(submission_id))
            .execute()
        )
        return response.data[0] if response.data else None

    return retry_on_network_error(_fetch_job)


def update_job_progress(
    submission_id: uuid.UUID,
    status: str,
    progress_percentage: int,
    progress_message: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Update the progress of a processing job.

    Also updates progress_json column for Supabase Realtime subscriptions.
    Frontend can subscribe to processing_jobs table changes via WebSocket
    instead of polling SSE endpoint.
    """
    update_data = {
        "status": status,
        "progress_percentage": progress_percentage,
    }

    if progress_message:
        update_data["progress_message"] = progress_message

    if status == "STITCHING" and "started_at" not in kwargs:
        update_data["started_at"] = datetime.now(timezone.utc).isoformat()

    if status in ["COMPLETED", "ERROR"]:
        update_data["completed_at"] = datetime.now(timezone.utc).isoformat()

    # Filter kwargs to only include fields that exist as columns in processing_jobs table
    # Exclude extraction_id (not a column) - it's only for progress_json (Supabase Realtime)
    allowed_update_fields = [
        "started_at", "error_message", "error_details",
        "stitching_time_seconds", "transcription_time_seconds",
        "extraction_time_seconds", "total_processing_time_seconds",
        "transcript", "insights", "stitched_audio_path"
    ]
    for key in allowed_update_fields:
        if key in kwargs:
            update_data[key] = kwargs[key]

    # Build progress_json for Supabase Realtime broadcasts
    # This enables WebSocket subscriptions to receive real-time updates
    progress_json_data = {
        "status": status,
        "progress": progress_percentage,
        "message": progress_message or f"Processing: {status}",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Include any extra data from kwargs that's useful for frontend
    for key in ["transcript_preview", "metrics", "error", "error_details"]:
        if key in kwargs:
            progress_json_data[key] = kwargs[key]

    # For COMPLETED status, include transcript and insights in progress_json
    # This allows frontend to immediately display results without extra fetch
    if status == "COMPLETED":
        if "transcript" in kwargs:
            progress_json_data["transcript"] = kwargs["transcript"]
        if "insights" in kwargs:
            progress_json_data["insights"] = kwargs["insights"]
        if "extraction_id" in kwargs:
            progress_json_data["extraction_id"] = str(kwargs["extraction_id"])
        if "audio_quality" in kwargs:
            progress_json_data["audio_quality"] = kwargs["audio_quality"]
        # Include timing metrics
        metrics = {}
        for key in ["stitching_time_seconds", "transcription_time_seconds",
                    "extraction_time_seconds", "total_processing_time_seconds"]:
            if key in kwargs and kwargs[key] is not None:
                metrics[key.replace("_seconds", "")] = kwargs[key]
        if metrics:
            progress_json_data["metrics"] = metrics

    # Pass dict directly - Supabase handles JSONB serialization
    # Do NOT use json.dumps() as it would cause double-encoding
    update_data["progress_json"] = progress_json_data

    def _update_job():
        response = (
            supabase.table("processing_jobs")
            .update(update_data)
            .eq("submission_id", str(submission_id))
            .execute()
        )
        return response

    response = retry_on_network_error(_update_job)

    # Update session status if job completed/errored
    if status in ["COMPLETED", "ERROR"]:
        job = get_job_by_submission_id(submission_id)
        if job:
            update_session_status(
                uuid.UUID(job["session_id"]),
                status
            )

    return response.data[0] if response.data else {}


def update_job_results(
    submission_id: uuid.UUID,
    transcript: str,
    insights: Dict[str, Any],
    stitching_time: Optional[float] = None,
    transcription_time: Optional[float] = None,
    extraction_time: Optional[float] = None,
    total_time: Optional[float] = None,
) -> Dict[str, Any]:
    """Update a job with the final processing results"""
    return update_job_progress(
        submission_id=submission_id,
        status="COMPLETED",
        progress_percentage=100,
        progress_message="Processing completed successfully",
        transcript=transcript,
        insights=insights,
        stitching_time_seconds=stitching_time,
        transcription_time_seconds=transcription_time,
        extraction_time_seconds=extraction_time,
        total_processing_time_seconds=total_time,
    )


def update_job_error(
    submission_id: uuid.UUID,
    error_message: str,
    error_details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Update a job with error information"""
    return update_job_progress(
        submission_id=submission_id,
        status="ERROR",
        progress_percentage=0,
        progress_message=error_message,
        error_message=error_message,
        error_details=error_details,
    )


# ============================================================================
# Audit Logging Operations
# ============================================================================

def log_session_audit(
    session_id: uuid.UUID,
    action: str,
    new_values: Optional[Dict[str, Any]] = None,
    old_values: Optional[Dict[str, Any]] = None,
    changed_by: str = "system",
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Log an audit entry for a session change"""
    data = {
        "session_id": str(session_id),
        "action": action,
        "old_values": old_values,
        "new_values": new_values,
        "changed_by": changed_by,
    }

    if ip_address:
        data["ip_address"] = ip_address
    if user_agent:
        data["user_agent"] = user_agent

    supabase.table("session_audit_log").insert(data).execute()


def get_session_audit_log(session_id: uuid.UUID) -> List[Dict[str, Any]]:
    """Get all audit log entries for a session"""
    response = (
        supabase.table("session_audit_log")
        .select("*")
        .eq("session_id", str(session_id))
        .order("changed_at", desc=True)
        .execute()
    )
    return response.data if response.data else []


# ============================================================================
# Performance Metrics Operations
# ============================================================================

def record_template_performance(
    template_id: uuid.UUID,
    session_id: uuid.UUID,
    transcription_model: str,
    audio_duration: float,
    processing_time: float,
    extraction_time: float,
    total_time: float,
    transcript_length: int,
    insights_extracted: bool,
) -> None:
    """Record performance metrics for a template"""
    supabase.rpc("record_template_performance", {
        "p_template_id": str(template_id),
        "p_session_id": str(session_id),
        "p_transcription_model": transcription_model,
        "p_audio_duration": audio_duration,
        "p_processing_time": processing_time,
        "p_extraction_time": extraction_time,
        "p_total_time": total_time,
        "p_transcript_length": transcript_length,
        "p_insights_extracted": insights_extracted,
    }).execute()


# ============================================================================
# Helper Functions
# ============================================================================

def get_session_with_job(correlation_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get complete session information including processing job details"""
    response = supabase.rpc(
        "get_session_with_job",
        {"p_correlation_id": str(correlation_id)}
    ).execute()

    return response.data[0] if response.data else None


def delete_session_and_chunks(session_id: uuid.UUID) -> None:
    """
    Delete a session and all its related chunks and jobs.
    Uses CASCADE deletion from foreign key constraints.
    """
    supabase.table("recording_sessions").delete().eq("id", str(session_id)).execute()


def cleanup_old_sessions(days_old: int = 30) -> int:
    """Clean up old sessions (older than specified days)"""
    response = supabase.rpc("cleanup_old_sessions", {
        "days_old": days_old
    }).execute()
    return response.data if response.data else 0


# ============================================================================
# Consultation Types Operations
# ============================================================================

def get_consultation_types(include_inactive: bool = False) -> List[Dict[str, Any]]:
    """
    Get all consultation types.

    Args:
        include_inactive: Include inactive consultation types

    Returns:
        List of consultation types ordered by display_order
    """
    query = supabase.table("consultation_types").select("*")

    if not include_inactive:
        query = query.eq("is_active", True)

    response = query.order("display_order").execute()
    return response.data if response.data else []


def get_consultation_type_by_code(type_code: str) -> Optional[Dict[str, Any]]:
    """Get consultation type by code (e.g., 'OP', 'DISCHARGE')"""
    response = (
        supabase.table("consultation_types")
        .select("*")
        .eq("type_code", type_code)
        .eq("is_active", True)
        .execute()
    )
    return response.data[0] if response.data else None


def get_consultation_type_by_code_cached(type_code: str) -> Optional[Dict[str, Any]]:
    """
    Get consultation type by code with caching.

    Uses in-memory cache with 8-hour TTL. Consultation types rarely change,
    so this significantly reduces database queries during extraction.

    Args:
        type_code: Consultation type code (e.g., 'OP', 'DISCHARGE', 'OP_SHORT')

    Returns:
        Consultation type dict or None
    """
    # Check cache first
    if type_code in _consultation_type_by_code_cache:
        return _consultation_type_by_code_cache[type_code]

    # Cache miss - query database
    result = get_consultation_type_by_code(type_code)
    _consultation_type_by_code_cache[type_code] = result

    # Also cache by ID if we got a result
    if result and result.get("id"):
        _consultation_type_cache[result["id"]] = result

    return result


def get_consultation_type_by_id(consultation_type_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get consultation type by ID"""
    response = (
        supabase.table("consultation_types")
        .select("*")
        .eq("id", str(consultation_type_id))
        .execute()
    )
    return response.data[0] if response.data else None


def get_consultation_type_by_id_cached(consultation_type_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get consultation type by ID with caching.

    Uses in-memory cache with 8-hour TTL.

    Args:
        consultation_type_id: UUID of consultation type

    Returns:
        Consultation type dict or None
    """
    cache_key = str(consultation_type_id)

    # Check cache first
    if cache_key in _consultation_type_cache:
        return _consultation_type_cache[cache_key]

    # Cache miss - query database
    result = get_consultation_type_by_id(consultation_type_id)
    _consultation_type_cache[cache_key] = result

    # Also cache by type_code if we got a result
    if result and result.get("type_code"):
        _consultation_type_by_code_cache[result["type_code"]] = result

    return result


def is_triage_analysis_enabled(consultation_type_id: uuid.UUID) -> bool:
    """
    Check if triage analysis is enabled for a consultation type.

    Uses cached consultation_type lookup to reduce database queries.

    Args:
        consultation_type_id: UUID of consultation type

    Returns:
        bool: True if triage analysis is enabled, False otherwise
    """
    try:
        ct = get_consultation_type_by_id_cached(consultation_type_id)
        if ct:
            return ct.get("enable_triage_analysis", False)
        return False
    except Exception as e:
        logger.error(f"[TRIAGE] Error checking triage enabled: {e}")
        return False


def get_consultation_type_code_by_id(consultation_type_id: uuid.UUID) -> str:
    """
    Get consultation type code from UUID.

    Uses cached lookup to reduce database queries.

    Args:
        consultation_type_id: UUID of consultation type

    Returns:
        str: Type code ('OP', 'DISCHARGE', 'RESPIRATORY')

    Raises:
        ValueError: If consultation type not found
    """
    # Use cached lookup instead of separate query
    ct = get_consultation_type_by_id_cached(consultation_type_id)

    if not ct:
        raise ValueError(f"Consultation type not found: {consultation_type_id}")

    return ct["type_code"]


# Cache for extraction models by mode code
_extraction_model_cache: Dict[str, str] = {}


def get_extraction_model_by_mode(mode_code: str) -> str:
    """
    Get the extraction model for a processing mode from the database.

    Uses caching to avoid repeated database queries.

    Args:
        mode_code: Processing mode code (e.g., 'default', 'thorough', 'fast')

    Returns:
        str: Model name (e.g., 'gemini-2.5-flash')

    Raises:
        ValueError: If processing mode not found
    """
    global _extraction_model_cache

    # Check cache first
    if mode_code in _extraction_model_cache:
        return _extraction_model_cache[mode_code]

    try:
        response = (
            supabase.table("processing_modes")
            .select("extraction_model")
            .eq("mode_code", mode_code)
            .single()
            .execute()
        )

        if not response.data:
            raise ValueError(f"Processing mode not found: {mode_code}")

        model = response.data["extraction_model"]
        _extraction_model_cache[mode_code] = model
        logger.debug(f"[PROCESSING_MODE] Loaded extraction model for '{mode_code}': {model}")
        return model

    except Exception as e:
        logger.error(f"[PROCESSING_MODE] Error fetching model for '{mode_code}': {e}")
        # Fallback to default model if lookup fails
        fallback = "gemini-2.5-flash"
        logger.warning(f"[PROCESSING_MODE] Using fallback model: {fallback}")
        return fallback


# Cache for triage models by mode code
_triage_model_cache: Dict[str, str] = {}


def get_triage_model_by_mode(mode_code: str = "default") -> str:
    """
    Get the triage model for a processing mode from the database.

    Uses caching to avoid repeated database queries.

    Args:
        mode_code: Processing mode code (e.g., 'default', 'thorough', 'fast')

    Returns:
        str: Model name (e.g., 'gemini-2.5-flash')
    """
    global _triage_model_cache

    # Check cache first
    if mode_code in _triage_model_cache:
        return _triage_model_cache[mode_code]

    try:
        response = (
            supabase.table("processing_modes")
            .select("triage_model")
            .eq("mode_code", mode_code)
            .single()
            .execute()
        )

        if not response.data:
            fallback = "gemini-2.5-flash"
            logger.warning(f"[PROCESSING_MODE] Processing mode '{mode_code}' not found, using fallback: {fallback}")
            return fallback

        model = response.data.get("triage_model") or "gemini-2.5-flash"
        _triage_model_cache[mode_code] = model
        logger.debug(f"[PROCESSING_MODE] Loaded triage model for '{mode_code}': {model}")
        return model

    except Exception as e:
        logger.error(f"[PROCESSING_MODE] Error fetching triage model for '{mode_code}': {e}")
        fallback = "gemini-2.5-flash"
        logger.warning(f"[PROCESSING_MODE] Using fallback triage model: {fallback}")
        return fallback


# Cache for merge models by mode code
_merge_model_cache: Dict[str, str] = {}


def get_merge_model_by_mode(mode_code: str = "default") -> str:
    """
    Get merge model for a processing mode from the database.

    Used for AI-powered segment merging (combine_segments endpoint).

    Args:
        mode_code: Processing mode code (default: "default")

    Returns:
        str: Model name (e.g., 'gemini-3.1-pro-preview')
    """
    global _merge_model_cache

    # Check cache first
    if mode_code in _merge_model_cache:
        return _merge_model_cache[mode_code]

    try:
        response = (
            supabase.table("processing_modes")
            .select("merge_model")
            .eq("mode_code", mode_code)
            .single()
            .execute()
        )

        if not response.data:
            fallback = "gemini-3.1-pro-preview"  # Gemini API (use gemini-3-pro for Vertex AI)
            logger.warning(f"[PROCESSING_MODE] No processing mode found for '{mode_code}', using fallback merge model: {fallback}")
            return fallback

        model = response.data.get("merge_model") or "gemini-3.1-pro-preview"
        _merge_model_cache[mode_code] = model
        logger.debug(f"[PROCESSING_MODE] Loaded merge model for '{mode_code}': {model}")
        return model

    except Exception as e:
        logger.error(f"[PROCESSING_MODE] Error fetching merge model for '{mode_code}': {e}")
        fallback = "gemini-3.1-pro-preview"  # Gemini API (use gemini-3-pro for Vertex AI)
        logger.warning(f"[PROCESSING_MODE] Using fallback merge model: {fallback}")
        return fallback


# Cache for compare models by mode code
_compare_model_cache: Dict[str, str] = {}


def get_compare_model_by_mode(mode_code: str = "default") -> str:
    """
    Get compare model for a processing mode from the database.

    Used for WER comparison analysis (compare_transcripts endpoint).

    Args:
        mode_code: Processing mode code (default: "default")

    Returns:
        str: Model name (e.g., 'gemini-2.5-flash')
    """
    global _compare_model_cache

    # Check cache first
    if mode_code in _compare_model_cache:
        return _compare_model_cache[mode_code]

    try:
        response = (
            supabase.table("processing_modes")
            .select("compare_model")
            .eq("mode_code", mode_code)
            .single()
            .execute()
        )

        if not response.data:
            fallback = "gemini-2.5-flash"
            logger.warning(f"[PROCESSING_MODE] No processing mode found for '{mode_code}', using fallback compare model: {fallback}")
            return fallback

        model = response.data.get("compare_model") or "gemini-2.5-flash"
        _compare_model_cache[mode_code] = model
        logger.debug(f"[PROCESSING_MODE] Loaded compare model for '{mode_code}': {model}")
        return model

    except Exception as e:
        logger.error(f"[PROCESSING_MODE] Error fetching compare model for '{mode_code}': {e}")
        fallback = "gemini-2.5-flash"
        logger.warning(f"[PROCESSING_MODE] Using fallback compare model: {fallback}")
        return fallback


# Cache for emotion models by mode code
_emotion_model_cache: Dict[str, str] = {}


def get_emotion_model_by_mode(mode_code: str = "default") -> str:
    """
    Get emotion model for a processing mode from the database.

    Used by extract_combined_emotions() for multimodal emotion analysis.

    Args:
        mode_code: Processing mode code (default: "default")

    Returns:
        str: Model name (e.g., 'gemini-2.5-flash')
    """
    global _emotion_model_cache

    # Check cache first
    if mode_code in _emotion_model_cache:
        return _emotion_model_cache[mode_code]

    try:
        response = (
            supabase.table("processing_modes")
            .select("emotion_model")
            .eq("mode_code", mode_code)
            .single()
            .execute()
        )

        if not response.data:
            fallback = "gemini-2.5-flash"
            logger.warning(f"[PROCESSING_MODE] No processing mode found for '{mode_code}', using fallback emotion model: {fallback}")
            return fallback

        model = response.data.get("emotion_model") or "gemini-2.5-flash"
        _emotion_model_cache[mode_code] = model
        logger.debug(f"[PROCESSING_MODE] Loaded emotion model for '{mode_code}': {model}")
        return model

    except Exception as e:
        logger.error(f"[PROCESSING_MODE] Error fetching emotion model for '{mode_code}': {e}")
        fallback = "gemini-2.5-flash"
        logger.warning(f"[PROCESSING_MODE] Using fallback emotion model: {fallback}")
        return fallback


# Cache for insights models by mode code
_insights_model_cache: Dict[str, str] = {}


def get_insights_model_by_mode(mode_code: str = "default") -> str:
    """
    Get insights model for a processing mode from the database.

    Used for consultation insights extraction (14 signal groups for interventions):
    - extract_consultation_insights

    Args:
        mode_code: Processing mode code (default: "default")

    Returns:
        str: Model name (e.g., 'gemini-2.5-flash')
    """
    global _insights_model_cache

    # Check cache first
    if mode_code in _insights_model_cache:
        return _insights_model_cache[mode_code]

    try:
        response = (
            supabase.table("processing_modes")
            .select("insights_model")
            .eq("mode_code", mode_code)
            .single()
            .execute()
        )

        if not response.data:
            fallback = "gemini-2.5-flash"
            logger.warning(f"[PROCESSING_MODE] No processing mode found for '{mode_code}', using fallback insights model: {fallback}")
            return fallback

        model = response.data.get("insights_model") or "gemini-2.5-flash"
        _insights_model_cache[mode_code] = model
        logger.debug(f"[PROCESSING_MODE] Loaded insights model for '{mode_code}': {model}")
        return model

    except Exception as e:
        logger.error(f"[PROCESSING_MODE] Error fetching insights model for '{mode_code}': {e}")
        fallback = "gemini-2.5-flash"
        logger.warning(f"[PROCESSING_MODE] Using fallback insights model: {fallback}")
        return fallback


# Cache for validator models by mode code
_validator_model_cache: Dict[str, str] = {}


def get_validator_model_by_mode(mode_code: str = "default") -> str:
    """
    Get validator model for a processing mode from the database.

    Used by the continuation merge micro-validator for cross-segment consistency checks.

    Args:
        mode_code: Processing mode code (default: "default")

    Returns:
        str: Model name (e.g., 'gemini-2.5-flash')
    """
    global _validator_model_cache

    # Check cache first
    if mode_code in _validator_model_cache:
        return _validator_model_cache[mode_code]

    try:
        response = (
            supabase.table("processing_modes")
            .select("validator_model")
            .eq("mode_code", mode_code)
            .single()
            .execute()
        )

        if not response.data:
            fallback = "gemini-2.5-flash"
            logger.warning(f"[PROCESSING_MODE] No processing mode found for '{mode_code}', using fallback validator model: {fallback}")
            return fallback

        model = response.data.get("validator_model") or "gemini-2.5-flash"
        _validator_model_cache[mode_code] = model
        logger.debug(f"[PROCESSING_MODE] Loaded validator model for '{mode_code}': {model}")
        return model

    except Exception as e:
        logger.error(f"[PROCESSING_MODE] Error fetching validator model for '{mode_code}': {e}")
        fallback = "gemini-2.5-flash"
        logger.warning(f"[PROCESSING_MODE] Using fallback validator model: {fallback}")
        return fallback


def create_consultation_type(
    type_code: str,
    type_name: str,
    description: Optional[str] = None,
    specialty_applicable: Optional[List[str]] = None,
    display_order: int = 999,
    icon_name: Optional[str] = None,
    color_code: Optional[str] = None,
    clone_from_consultation_type_id: Optional[str] = None,
    visible_to_schools: Optional[List[str]] = None,
    visible_to_counsellors: Optional[List[str]] = None,
    visible_to_specializations: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Create a new consultation type with optional visibility controls.

    Args:
        type_code: Unique type code (e.g., 'EMERGENCY', 'CARDIOLOGY')
        type_name: Display name (e.g., 'Emergency Consultation')
        description: Detailed description of the consultation type
        specialty_applicable: List of applicable specialties
        display_order: Display order in UI (default: 999)
        icon_name: Icon name for UI display
        color_code: Color code for UI theme (e.g., '#EF4444')
        clone_from_consultation_type_id: Optional UUID of consultation type to clone segments from
        visible_to_schools: List of school UUIDs (optional - restricts visibility to these schools)
        visible_to_counsellors: List of counsellor UUIDs (optional - restricts visibility to these counsellors)
        visible_to_specializations: List of specializations (optional - restricts visibility to these specializations)

    Visibility Logic:
        - If ALL three visibility arrays are None/empty → Everyone can see this consultation type
        - If ANY array has values → Only those specific entities can see it

    Returns:
        Dict containing the created consultation type

    Raises:
        ValueError: If type_code already exists or validation fails
    """
    # Check if type_code already exists
    existing = (
        supabase.table("consultation_types")
        .select("id")
        .eq("type_code", type_code)
        .execute()
    )

    if existing.data:
        raise ValueError(f"Consultation type with code '{type_code}' already exists")

    # Create consultation type with optional visibility controls
    data = {
        "type_code": type_code.upper(),
        "type_name": type_name,
        "description": description,
        "specialty_applicable": specialty_applicable or [],
        "is_active": True,
        "display_order": display_order,
        "icon_name": icon_name,
        "color_code": color_code,
        # Visibility controls (optional - if all empty/None, everyone can see it)
        "visible_to_schools": visible_to_schools if visible_to_schools else None,
        "visible_to_counsellors": visible_to_counsellors if visible_to_counsellors else None,
        "visible_to_specializations": visible_to_specializations if visible_to_specializations else None,
        # Default feature toggles for NEW consultation types (disabled by default)
        # Admins can enable these after creation via TemplateAdminScreen
        "emotion_extraction_mode": "none",
        "enable_emotion_analysis": False,
        "enable_triage_analysis": False,
        "enable_consultation_insights": False,
    }

    response = supabase.table("consultation_types").insert(data).execute()

    if not response.data:
        raise ValueError("Failed to create consultation type")

    consultation_type = response.data[0]
    consultation_type_id = consultation_type["id"]

    # Only clone segments if clone_from_consultation_type_id is provided
    # From-scratch creation = NO segments inherited
    if clone_from_consultation_type_id:
        # Get ALL segments from source consultation type via junction table
        # Step 1: Get segment IDs from source junction table
        source_junction = (
            supabase.table("consultation_type_segments")
            .select("segment_id, segment_code, default_display_order, default_category")
            .eq("consultation_type_id", clone_from_consultation_type_id)
            .execute()
        ).data or []

        logger.debug(f"Found {len(source_junction)} segments in source consultation type via junction table")

        # Step 2: Get full segment details from segment_definitions (reusable master segments)
        source_segment_ids = [j['segment_id'] for j in source_junction]

        if source_segment_ids:
            source_segments = (
                supabase.table("segment_definitions")
                .select("*")
                .in_("id", source_segment_ids)
                .eq("is_active", True)
                .execute()
            ).data or []
        else:
            source_segments = []

        logger.debug(f"Cloning {len(source_segments)} segments from source consultation type {clone_from_consultation_type_id}")

        # Clone segments: Create junction table entries linking existing segments to new consultation type
        # We DON'T create new segment definitions - we REUSE existing master segments
        cloned_count = 0
        failed_count = 0

        for source_segment in source_segments:
            segment_id = source_segment["id"]
            segment_code = source_segment["segment_code"]
            is_segment_active = source_segment.get("is_active", True)

            # Get display_order and category from source junction
            source_junction_entry = next((j for j in source_junction if j['segment_id'] == segment_id), None)
            display_order = source_junction_entry['default_display_order'] if source_junction_entry else source_segment.get("display_order", 999)
            default_category = source_junction_entry['default_category'] if source_junction_entry else source_segment.get("default_category", "additional")

            # Create junction table entry to link this segment to new consultation type
            junction_data = {
                "consultation_type_id": consultation_type_id,
                "consultation_type_name": type_name,  # From function parameter
                "segment_id": segment_id,
                "segment_code": segment_code,
                "default_display_order": display_order,
                "default_category": default_category.lower()
            }

            try:
                supabase.table("consultation_type_segments").insert(junction_data).execute()
                cloned_count += 1

                # If segment was inactive, activate it now that it's assigned
                if not is_segment_active:
                    supabase.table("segment_definitions").update({"is_active": True}).eq("id", segment_id).execute()
                    logger.info(f"Activated segment '{segment_code}' during cloning (was inactive)")

            except Exception as e:
                # Log but don't fail consultation type creation if segment link fails
                failed_count += 1
                logger.warning(f"Failed to link segment {segment_code} to new consultation type: {str(e)}")

        logger.info(f"Consultation type '{type_code}' created with {cloned_count} segments linked via junction table (failed: {failed_count})")
    else:
        # From-scratch creation = NO segments
        logger.info(f"Consultation type '{type_code}' created from scratch with no segments")

    return consultation_type


# ============================================================================
# Segment Configuration Operations (Multi-Consultation Type)
# ============================================================================

def get_segment_definitions(
    consultation_type_id: uuid.UUID,
    counsellor_id: Optional[uuid.UUID] = None,
    template_code: Optional[str] = None,
    mode: str = "full",
) -> Dict[str, Any]:
    """
    Get segment definitions for a consultation type with user customization.

    Returns:
        Dict with:
        - segments: List of segment definitions
        - excluded_segment_codes: Set of segment codes marked as 'excluded' (for response filtering)

    Args:
        consultation_type_id: Consultation type ID (required)
        counsellor_id: User ID for personalized configuration (None = default config)
        template_code: Template code for template-specific configuration (optional, unique identifier)
        mode: 'core' | 'additional' | 'full'
    """
    # =========================================================================
    # TEMPLATE LOOKUP STRATEGY:
    # 1. If counsellor_id + template_code: Try unified lookup (owned → shared → global)
    # 2. If counsellor_id only: Try default template for counsellor
    # 3. If template_code only: Try global template lookup
    # 4. Fallback: Use consultation_type_segments
    # =========================================================================

    active_template_id = None
    use_template_segments = False

    if counsellor_id and template_code:
        # Case 1: Counsellor + specific template requested
        # Use unified lookup (checks owned, shared, global)
        active_template_record = get_active_template_by_code_cached(counsellor_id, template_code)

        if active_template_record:
            active_template_id = uuid.UUID(active_template_record["id"])
            use_template_segments = True
            logger.debug(
                f"[GET_SEGMENT_DEFINITIONS] Found template '{template_code}' "
                f"(source: {active_template_record.get('source', 'unknown')})"
            )
        else:
            # Template not found - fall through to consultation_type_segments
            logger.warning(
                f"[GET_SEGMENT_DEFINITIONS] Template '{template_code}' not found for counsellor {counsellor_id}, "
                f"falling back to consultation_type_segments"
            )

    elif counsellor_id and not template_code:
        # Case 2: Counsellor but no specific template - look for global template for this consultation type
        # Query for global templates (counsellor_id IS NULL) for the given consultation_type_id
        global_template_response = (
            supabase.table("templates")
            .select("id, template_code, template_name")
            .eq("consultation_type_id", str(consultation_type_id))
            .is_("counsellor_id", "null")
            .eq("is_active", True)
            .order("is_default", desc=True)  # Prefer default global template
            .limit(1)
            .execute()
        )

        if global_template_response.data and len(global_template_response.data) > 0:
            global_template = global_template_response.data[0]
            active_template_id = uuid.UUID(global_template["id"])
            use_template_segments = True
            logger.debug(
                f"[GET_SEGMENT_DEFINITIONS] Using global template '{global_template['template_code']}' "
                f"for consultation_type_id {consultation_type_id}"
            )
        else:
            logger.debug(
                f"[GET_SEGMENT_DEFINITIONS] No global template for consultation_type_id {consultation_type_id}, "
                f"falling back to consultation_type_segments"
            )

    elif not counsellor_id and template_code:
        # Case 3: No counsellor but template_code provided - check for global template
        global_template = get_template_by_code(template_code)

        if global_template and global_template.get('counsellor_id') is None:
            active_template_id = uuid.UUID(global_template["id"])
            use_template_segments = True
            logger.debug(
                f"[GET_SEGMENT_DEFINITIONS] Found global template '{template_code}'"
            )
        else:
            logger.warning(
                f"[GET_SEGMENT_DEFINITIONS] Global template '{template_code}' not found, "
                f"falling back to consultation_type_segments"
            )

    # else: Case 4 - No counsellor_id, no template_code → use consultation_type_segments (below)

    # Get segment configurations from template_segments table
    result = []
    excluded_segment_codes = set()  # Track excluded segments for response filtering

    if use_template_segments and active_template_id:
        # Get template-specific segment configurations
        template_segments_response = (
            supabase.table("template_segments")
            .select("segment_id, segment_code, category, display_order, brevity_level, terminology_style")
            .eq("template_id", str(active_template_id))
            .execute()
        )

        segment_ids = [s['segment_id'] for s in (template_segments_response.data or [])]

        if segment_ids:
            # Get full segment details
            segments_response = (
                supabase.table("segment_definitions")
                .select("""
                    id, segment_code, segment_name, prompt_section_text, schema_definition_json,
                    default_category, display_order, default_brevity_level,
                    default_terminology_style, is_required, is_active
                """)
                .eq("is_active", True)
                .in_("id", segment_ids)
                .execute()
            )

            # Merge template configuration with segment definitions
            segment_config_map = {s['segment_code']: s for s in (template_segments_response.data or [])}

            for seg in (segments_response.data or []):
                config = segment_config_map.get(seg['segment_code'], {})

                # Override with template-specific configuration
                seg['default_category'] = config.get('category', seg['default_category'])
                seg['display_order'] = config.get('display_order', seg['display_order'])
                seg['default_brevity_level'] = config.get('brevity_level', seg['default_brevity_level'])
                seg['default_terminology_style'] = config.get('terminology_style', seg['default_terminology_style'])

                # Track excluded segments for response filtering (template-level only)
                if seg["default_category"] == "excluded":
                    excluded_segment_codes.add(seg["segment_code"])

                # Apply mode filter
                if mode == "core" and seg["default_category"] != "core":
                    continue
                elif mode == "additional" and seg["default_category"] != "additional":
                    continue
                # NOTE: Don't skip excluded - they get extracted but filtered from response

                result.append(seg)

        if not result:
            # Template found but no segments configured - fall through to consultation_type_segments
            logger.debug(
                f"[GET_SEGMENT_DEFINITIONS] Template {active_template_id} has no segments, "
                f"falling back to consultation_type_segments"
            )
            use_template_segments = False

    # Fallback: Load from consultation_type_segments if no template segments found
    if not use_template_segments or not result:
        # Get default segment definitions for this consultation type
        # Strategy: Use junction table to get type-specific segments with ALL config fields,
        # then merge junction values onto master table data (junction takes precedence)
        # Exclude segments marked as 'excluded'

        # Get type-specific segments via junction table - include ALL junction fields
        junction_response = (
            supabase.table("consultation_type_segments")
            .select("segment_id, segment_code, default_display_order, default_category, default_brevity_level, default_terminology_style")
            .eq("consultation_type_id", str(consultation_type_id))
            .execute()
        )

        junction_data = junction_response.data or []
        segment_ids = [j['segment_id'] for j in junction_data]

        # Build junction lookup map for quick access to per-consultation-type overrides
        junction_map = {j['segment_id']: j for j in junction_data}

        # Get full segment details for type-specific segments
        type_specific = []
        if segment_ids:
            type_specific = (
                supabase.table("segment_definitions")
                .select("""
                    id, segment_code, segment_name, prompt_section_text, schema_definition_json,
                    default_category, display_order, default_brevity_level,
                    default_terminology_style, is_required, is_active
                """)
                .eq("is_active", True)
                .in_("id", segment_ids)
                .execute()
            ).data or []

        # NEW ARCHITECTURE: Merge junction table overrides with master segment data
        # Junction table values take precedence for per-consultation-type fields
        segment_map = {}
        for seg in type_specific:
            segment_id = seg.get("id")
            junction_override = junction_map.get(segment_id, {})

            # Apply junction table overrides (per-consultation-type values)
            if junction_override:
                # Override display_order from junction table
                if junction_override.get("default_display_order") is not None:
                    seg["display_order"] = junction_override["default_display_order"]
                # Override default_category from junction table
                if junction_override.get("default_category") is not None:
                    seg["default_category"] = junction_override["default_category"]
                # Override brevity_level from junction table
                if junction_override.get("default_brevity_level") is not None:
                    seg["default_brevity_level"] = junction_override["default_brevity_level"]
                # Override terminology_style from junction table
                if junction_override.get("default_terminology_style") is not None:
                    seg["default_terminology_style"] = junction_override["default_terminology_style"]

            segment_map[seg["segment_code"]] = seg

        # Filter by mode and track excluded segments from consultation_type_segments
        result = []
        for seg in segment_map.values():
            # Track excluded segments for response filtering
            if seg["default_category"] == "excluded":
                excluded_segment_codes.add(seg["segment_code"])

            # Apply mode filter only
            if mode == "core" and seg["default_category"] != "core":
                continue
            elif mode == "additional" and seg["default_category"] != "additional":
                continue

            result.append(seg)

        # Sort by display_order (now using junction table values)
        result.sort(key=lambda x: x.get("display_order", 999))

    return {
        "segments": result,
        "excluded_segment_codes": excluded_segment_codes  # Populated from template_segments or consultation_type_segments
    }


# ============================================================================
# Processing Modes & Template Resolution Functions
# ============================================================================

def get_processing_mode(mode_code: str) -> Dict[str, Any]:
    """
    Get processing mode configuration from database.

    Args:
        mode_code: 'fast', 'default', 'thorough', 'ultra', or 'ultra_fast'

    Returns:
        Dict with transcription_model, extraction_model, transcription_api

    Raises:
        ValueError: If mode_code not found
    """
    response = supabase.rpc("get_processing_mode_config", {
        "p_mode_code": mode_code
    }).execute()

    if not response.data or len(response.data) == 0:
        raise ValueError(f"Invalid processing mode: {mode_code}")

    return response.data[0]


def get_default_template_id(
    counsellor_id: uuid.UUID,
    consultation_type_id: uuid.UUID
) -> Optional[uuid.UUID]:
    """
    Get default active template for a counsellor and consultation type.

    Looks up template with is_active=TRUE and is_default=TRUE.

    Args:
        counsellor_id: Counsellor's UUID
        consultation_type_id: Consultation type UUID

    Returns:
        template_id (UUID) or None if no default exists
    """
    # Direct query to templates table (get_default_active_template_id RPC dropped)
    response = (
        supabase.table("templates")
        .select("id")
        .eq("counsellor_id", str(counsellor_id))
        .eq("consultation_type_id", str(consultation_type_id))
        .eq("is_active", True)
        .eq("is_default", True)
        .limit(1)
        .execute()
    )

    if response.data:
        return uuid.UUID(response.data[0]["id"])
    return None


def get_active_template_by_code(
    counsellor_id: uuid.UUID,
    template_code: str
) -> Optional[Dict[str, Any]]:
    """
    Get active template by counsellor ID and template code.

    Returns full template info including consultation_type_id.
    Uses unified RPC function that checks owned, shared, and global templates
    in a single UNION query (optimized from 3 sequential queries).

    Priority: 1=owned, 2=shared, 3=global

    Args:
        counsellor_id: Counsellor's UUID
        template_code: Template code to look up (unique identifier)

    Returns:
        Dict with id (template_id), consultation_type_id, template_code, etc. or None
    """
    # Use unified RPC function (1 query instead of 3 sequential)
    response = supabase.rpc(
        'get_template_by_code_unified',
        {
            'p_counsellor_id': str(counsellor_id),
            'p_template_code': template_code
        }
    ).execute()

    if response.data and len(response.data) > 0:
        template = response.data[0]
        source_priority = template.get("source_priority", 3)
        source_map = {1: "owned", 2: "shared", 3: "global"}

        return {
            "id": template["id"],
            "template_id": template["id"],
            "consultation_type_id": template["consultation_type_id"],
            "template_code": template["template_code"],
            "template_name": template["template_name"],
            "is_default": template.get("is_default", False),
            "is_active": template.get("is_active", True),
            "source": source_map.get(source_priority, "global"),
            # Include full template data for session context
            "assembled_full_prompt": template.get("assembled_full_prompt"),
            "assembled_schema_json": template.get("assembled_schema_json"),
            "prompt_assembly_hash": template.get("prompt_assembly_hash"),
            "schema_assembly_hash": template.get("schema_assembly_hash"),
        }

    from services.log_sanitizer import truncate_id as _tid
    logger.warning(f"[GET_ACTIVE_TEMPLATE] Template with code '{template_code}' not found for counsellor {_tid(str(counsellor_id))} (checked owned, shared, and global via unified RPC)")
    return None


def get_active_template_by_code_cached(
    counsellor_id: uuid.UUID,
    template_code: str
) -> Optional[Dict[str, Any]]:
    """
    Get active template by counsellor ID and template code with caching.

    Uses 8-hour TTL cache to reduce database queries.
    Cache key: (template_code, counsellor_id)

    Args:
        counsellor_id: Counsellor's UUID
        template_code: Template code to look up

    Returns:
        Dict with template info or None
    """
    cache_key = f"{template_code}:{counsellor_id}"

    # Check cache first
    if cache_key in _template_unified_cache:
        logger.debug(f"[CACHE] Template cache HIT for {template_code}")
        return _template_unified_cache[cache_key]

    # Cache miss - call original function
    result = get_active_template_by_code(counsellor_id, template_code)
    _template_unified_cache[cache_key] = result

    return result


def get_all_processing_modes() -> List[Dict[str, Any]]:
    """Fetch all processing modes from database, ordered by display_order"""
    response = supabase.table("processing_modes")\
        .select("*")\
        .order("display_order")\
        .execute()
    return response.data


# ============================================================================
# REMOVED: doctor_segment_configurations functions
# Counsellor segment customization now handled via template cloning:
# - Counsellor clones template → creates new templates record
# - Configuration stored in template_segments (linked to new template)
# - No need for separate doctor_segment_configurations table
# ============================================================================




def get_templates(
    consultation_type_id: Optional[uuid.UUID] = None,
    counsellor_id: Optional[uuid.UUID] = None,
    filter_type: Optional[str] = None,
    include_view_access: bool = False  # Deprecated, kept for API compatibility (ignored)
) -> List[Dict[str, Any]]:
    """
    Get available segment templates.

    Filter Types:
    - 'admin': Only templates created by admin (counsellor_id = NULL)
    - 'doctor': Counsellor's templates (junction table with is_active=True + owned + global)
    - 'all': All active templates (admin + counsellor-owned, ignores counsellor_id)
    - None: Defaults to 'doctor' behavior if counsellor_id provided, else all templates

    If counsellor_id is NOT provided and no filter_type, returns all templates (admin view).

    Args:
        consultation_type_id: Filter by consultation type (None = all consultation types)
        counsellor_id: Optional counsellor UUID for junction table filtering
        filter_type: Optional filter ('admin', 'doctor', 'all')
        include_view_access: Deprecated, ignored. Kept for API compatibility.

    Returns:
        List of templates based on filter criteria
    """
    # Define columns for listing templates (excludes internal fields like assembled_full_prompt, assembled_schema_json)
    TEMPLATE_LIST_COLUMNS = "id, template_code, template_name, description, consultation_type_id, is_active, is_default, use_case, specialization, school_id, counsellor_id, estimated_extraction_time_seconds, created_at, updated_at"

    # Handle filter_type for admin screen
    if filter_type == 'admin':
        # Admin templates only (counsellor_id = NULL)
        query = supabase.table("templates")\
            .select(TEMPLATE_LIST_COLUMNS)\
            .is_("counsellor_id", "null")\
            .eq("is_active", True)

        if consultation_type_id is not None:
            query = query.or_(f"consultation_type_id.is.null,consultation_type_id.eq.{str(consultation_type_id)}")
        else:
            query = query.is_("consultation_type_id", "null")

        response = query.order("template_name").execute()
        return response.data if response.data else []

    elif filter_type == 'doctor':
        # If counsellor_id is provided: Counsellor's activated templates from junction + owned + global
        # If counsellor_id is NOT provided (admin view): ALL counsellor-owned templates (counsellor_id IS NOT NULL)

        if counsellor_id is None:
            # Admin view: Show ALL counsellor-owned templates (where counsellor_id IS NOT NULL)
            logger.debug("[GET_TEMPLATES] filter_type='doctor' without counsellor_id: Returning all counsellor-owned templates (admin view)")
            query = supabase.table("templates")\
                .select(TEMPLATE_LIST_COLUMNS)\
                .eq("is_active", True)\
                .not_.is_("counsellor_id", "null")  # Only counsellor-owned templates

            # Filter by consultation type if provided
            if consultation_type_id is not None:
                query = query.or_(f"consultation_type_id.is.null,consultation_type_id.eq.{str(consultation_type_id)}")
            # If consultation_type_id is None, return ALL counsellor-owned templates

            response = query.order("template_name").execute()
            templates = response.data if response.data else []

            # Mark source
            for t in templates:
                t['source'] = 'doctor'

            logger.debug(f"[GET_TEMPLATES] Admin view (counsellor-owned): Retrieved {len(templates)} templates")
            return templates

        templates = []

        # Run all 3 independent queries in parallel for counsellor's templates
        def _fetch_junction():
            counsellor_templates_query = (
                supabase.table("counsellor_templates")
                .select(f"template_id, is_active, templates({TEMPLATE_LIST_COLUMNS})")
                .eq("counsellor_id", str(counsellor_id))
                .eq("is_active", True)
            )
            return counsellor_templates_query.execute()

        def _fetch_owned():
            owned_query = (
                supabase.table("templates")
                .select(TEMPLATE_LIST_COLUMNS)
                .eq("counsellor_id", str(counsellor_id))
                .eq("is_active", True)
            )
            if consultation_type_id is not None:
                owned_query = owned_query.or_(f"consultation_type_id.is.null,consultation_type_id.eq.{str(consultation_type_id)}")
            return owned_query.execute()

        def _fetch_global():
            global_query = (
                supabase.table("templates")
                .select(TEMPLATE_LIST_COLUMNS)
                .is_("counsellor_id", "null")
                .eq("is_active", True)
            )
            if consultation_type_id is not None:
                global_query = global_query.or_(f"consultation_type_id.is.null,consultation_type_id.eq.{str(consultation_type_id)}")
            return global_query.execute()

        # Execute all 3 queries in parallel
        junction_future = _service_executor.submit(_fetch_junction)
        owned_future = _service_executor.submit(_fetch_owned)
        global_future = _service_executor.submit(_fetch_global)

        counsellor_templates_response = junction_future.result()
        owned_response = owned_future.result()
        global_response = global_future.result()

        # Process junction table results
        if counsellor_templates_response.data:
            for dt in counsellor_templates_response.data:
                template = dt.get("templates")
                if template:
                    if not template.get("is_active", True):
                        continue
                    template_consult_type = template.get("consultation_type_id")
                    if consultation_type_id is not None:
                        if template_consult_type and str(template_consult_type) != str(consultation_type_id):
                            continue
                    template['source'] = 'shared'
                    template['is_activated'] = dt.get('is_active')
                    templates.append(template)

        # Process owned templates
        if owned_response.data:
            for template in owned_response.data:
                template['source'] = 'owned'
                templates.append(template)

        if global_response.data:
            for template in global_response.data:
                template['source'] = 'global'
                templates.append(template)

        # Deduplicate by template ID (in case template is both owned and shared)
        seen_ids = set()
        unique_templates = []
        for template in templates:
            template_id = template.get('id')
            if template_id and template_id not in seen_ids:
                seen_ids.add(template_id)
                unique_templates.append(template)

        logger.debug(f"[GET_TEMPLATES] filter_type='doctor', counsellor_id={counsellor_id}, consultation_type_id={consultation_type_id}, templates={len(unique_templates)}")
        return unique_templates

    elif filter_type == 'all':
        # Both admin and counsellor-owned templates (for admin view)
        # Query ALL templates directly instead of using filter_type='doctor' (which requires counsellor_id)
        query = supabase.table("templates")\
            .select("id, template_code, template_name, description, consultation_type_id, is_active, is_default, use_case, specialization, school_id, counsellor_id, estimated_extraction_time_seconds")\
            .eq("is_active", True)

        # Filter by consultation type if provided
        if consultation_type_id is not None:
            query = query.or_(f"consultation_type_id.is.null,consultation_type_id.eq.{str(consultation_type_id)}")
        # If consultation_type_id is None, return ALL templates (don't filter by consultation_type)

        response = query.order("template_name").execute()
        templates = response.data if response.data else []

        # Mark source for each template
        for t in templates:
            if t.get('counsellor_id') is None:
                t['source'] = 'admin'
            else:
                t['source'] = 'doctor'

        logger.debug(f"[GET_TEMPLATES] filter_type='all': Retrieved {len(templates)} templates (admin + counsellor-owned)")
        return templates

    # Default behavior when no filter_type specified:
    # - If counsellor_id provided: Use junction table logic (same as filter_type='doctor')
    # - If no counsellor_id: Show all templates (admin view)
    if counsellor_id is not None:
        # Use junction table logic for counsellor access
        # This replaces the old doctor_visible_templates VIEW which didn't respect
        # the counsellor_templates junction table
        logger.debug(f"[GET_TEMPLATES] No filter_type specified with counsellor_id={counsellor_id}, using junction table logic (filter_type='doctor')")
        return get_templates(
            consultation_type_id=consultation_type_id,
            counsellor_id=counsellor_id,
            filter_type='doctor',
        )
    else:
        # Admin view: show all templates (both admin and counsellor-owned)
        query = supabase.table("templates")\
            .select("id, template_code, template_name, description, consultation_type_id, is_active, is_default, use_case, specialization, school_id, counsellor_id, estimated_extraction_time_seconds")\
            .eq("is_active", True)

        # Filter by consultation type if provided
        if consultation_type_id is not None:
            query = query.or_(f"consultation_type_id.is.null,consultation_type_id.eq.{str(consultation_type_id)}")
        # If consultation_type_id is None, return ALL templates (don't filter - admin sees everything)

        response = query.order("template_name").execute()
        templates = response.data if response.data else []

        logger.debug(f"[GET_TEMPLATES] Admin view: Retrieved {len(templates)} templates from database")
        return templates


def get_template_configuration(template_id: uuid.UUID) -> List[Dict[str, Any]]:
    """Get all segment configurations for a template"""
    logger.debug(f"[TEMPLATE_CONFIG] Fetching configuration for template_id: {template_id}")

    try:
        # Fetch template segment configurations
        config_response = (
            supabase.table("template_segments")
            .select("*")
            .eq("template_id", str(template_id))
            .order("display_order")
            .execute()
        )

        configurations = config_response.data or []
        logger.debug(f"[TEMPLATE_CONFIG] Found {len(configurations)} segment configurations")

        # Manually fetch segment definitions and merge
        result = []
        for config in configurations:
            segment_id = config.get("segment_id")
            segment_code = config.get("segment_code")
            logger.debug(f"[TEMPLATE_CONFIG] Processing segment_id: {segment_id}, segment_code: {segment_code}")

            # Fetch segment definition by ID (unique) instead of segment_code
            if segment_id:
                segment_response = (
                    supabase.table("segment_definitions")
                    .select("*")
                    .eq("id", segment_id)
                    .execute()
                )
            else:
                # Fallback to segment_code for backwards compatibility (limit 1)
                logger.warning(f"[TEMPLATE_CONFIG] No segment_id for {segment_code}, falling back to segment_code lookup")
                segment_response = (
                    supabase.table("segment_definitions")
                    .select("*")
                    .eq("segment_code", segment_code)
                    .eq("is_active", True)
                    .limit(1)
                    .execute()
                )

            # Merge config with segment definition
            merged = {**config}
            if segment_response.data and len(segment_response.data) > 0:
                merged["segment_definitions"] = segment_response.data[0]
            else:
                logger.warning(f"[TEMPLATE_CONFIG] Segment definition not found for: {segment_code} (id: {segment_id})")
                merged["segment_definitions"] = None

            result.append(merged)

        logger.debug(f"[TEMPLATE_CONFIG] Successfully merged {len(result)} configurations with segment definitions")
        return result

    except Exception as e:
        logger.error(f"[TEMPLATE_CONFIG] Error fetching template configuration: {str(e)}", exc_info=True)
        raise


def clone_template(
    source_template_id: uuid.UUID,
    counsellor_id: uuid.UUID,
    new_template_name: Optional[str] = None,
    new_template_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Clone an existing template to create a counsellor-owned copy.

    Creates a new template record + copies all template_segments configurations.
    Use this when a counsellor wants to customize a common template or another counsellor's template.

    Args:
        source_template_id: Template UUID to clone from
        counsellor_id: Counsellor UUID who will own the cloned template
        new_template_name: Optional custom name (defaults to "{source_name} - {counsellor_name} Copy")
        new_template_code: Optional custom code (defaults to "{source_code}_{counsellor_id[:8]}")

    Returns:
        New template record with cloned segments

    Raises:
        ValueError: If source template not found
        Exception: If cloning fails
    """
    # Get source template
    source_template = (
        supabase.table("templates")
        .select("*")
        .eq("id", str(source_template_id))
        .limit(1)
        .execute()
    )

    if not source_template.data:
        raise ValueError(f"Source template {source_template_id} not found")

    source = source_template.data[0]

    # Get counsellor details for naming
    doctor = (
        supabase.table("counsellors")
        .select("full_name")
        .eq("id", str(counsellor_id))
        .limit(1)
        .execute()
    )

    counsellor_name = doctor.data[0]["full_name"] if doctor.data else str(counsellor_id)[:8]

    # Generate new template name and code
    final_template_name = new_template_name or f"{source['template_name']} - {counsellor_name} Copy"
    final_template_code = new_template_code or f"{source['template_code']}_{str(counsellor_id)[:8]}"

    # Create new template record
    new_template_data = {
        "template_code": final_template_code,
        "template_name": final_template_name,
        "description": source.get("description"),
        "consultation_type_id": source["consultation_type_id"],
        "use_case": source.get("use_case"),
        "specialization": source.get("specialization"),
        "school_id": source.get("school_id"),
        "counsellor_id": str(counsellor_id),  # Set counsellor ownership
        "is_default": False,
        "is_active": True,
        "estimated_extraction_time_seconds": source.get("estimated_extraction_time_seconds")
    }

    new_template = supabase.table("templates").insert(new_template_data).execute()
    new_template_id = new_template.data[0]["id"]

    # Copy all template_segments from source to new template
    source_segments = (
        supabase.table("template_segments")
        .select("*")
        .eq("template_id", str(source_template_id))
        .execute()
    )

    if source_segments.data:
        cloned_segments = []
        for segment in source_segments.data:
            cloned_segment = {
                "template_id": new_template_id,
                "template_name": final_template_name,  # Include template name in junction
                "segment_id": segment["segment_id"],
                "segment_code": segment["segment_code"],
                "category": segment["category"],
                "display_order": segment["display_order"],
                "brevity_level": segment.get("brevity_level"),
                "terminology_style": segment.get("terminology_style")
            }
            cloned_segments.append(cloned_segment)

        # Bulk insert cloned segments
        supabase.table("template_segments").insert(cloned_segments).execute()

    logger.info(f"Cloned template {source_template_id} → {new_template_id} for counsellor {counsellor_id}")

    return {
        "template_id": new_template_id,
        "template_code": final_template_code,
        "template_name": final_template_name,
        "counsellor_id": str(counsellor_id),
        "source_template_id": str(source_template_id),
        "segments_cloned": len(source_segments.data) if source_segments.data else 0,
        "status": "cloned"
    }


def get_counsellor_active_template(counsellor_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    [DEPRECATED] Get the currently active templates for a counsellor.

    Use get_templates(filter_type='doctor', counsellor_id=counsellor_id) instead.

    Returns:
        First active template if exists, or None
    """
    logger.warning("[DEPRECATED] get_counsellor_active_template is deprecated, use get_templates(filter_type='doctor') instead")
    templates = get_templates(counsellor_id=counsellor_id, filter_type='doctor')
    return templates[0] if templates else None


def get_counsellor_active_templates_by_template(
    counsellor_id: uuid.UUID,
    template_id: uuid.UUID
) -> list[Dict[str, Any]]:
    """
    [DEPRECATED] Get all active instances of a specific template for a counsellor.

    Use direct templates table query instead.

    Args:
        counsellor_id: Counsellor UUID
        template_id: Template UUID

    Returns:
        List of active template instances
    """
    logger.warning("[DEPRECATED] get_counsellor_active_templates_by_template is deprecated")
    response = (
        supabase.table("templates")
        .select("*")
        .eq("counsellor_id", str(counsellor_id))
        .eq("id", str(template_id))
        .eq("is_active", True)
        .order("updated_at", desc=True)
        .execute()
    )
    return response.data if response.data else []


def check_template_name_available(
    counsellor_id: uuid.UUID,
    custom_name: str,
    exclude_template_id: Optional[uuid.UUID] = None
) -> bool:
    """
    Check if a template name is available for a counsellor.

    Args:
        counsellor_id: Counsellor UUID
        custom_name: Proposed template name
        exclude_template_id: Optional template ID to exclude (for rename)

    Returns:
        True if name is available, False if already in use
    """
    # Query templates table directly (doctor_active_templates dropped)
    query = (
        supabase.table("templates")
        .select("id")
        .eq("counsellor_id", str(counsellor_id))
        .eq("template_name", custom_name.strip())
    )

    if exclude_template_id:
        query = query.neq("id", str(exclude_template_id))

    response = query.execute()
    return len(response.data) == 0


def check_template_code_available(
    counsellor_id: Optional[uuid.UUID],
    template_code: str,
    exclude_template_id: Optional[uuid.UUID] = None
) -> bool:
    """
    Check if a template code is available.

    The database has UNIQUE (counsellor_id, template_code) constraint,
    but PostgreSQL allows multiple NULLs in unique constraints.
    This function enforces uniqueness even for common templates (counsellor_id=NULL).

    Args:
        counsellor_id: Counsellor UUID (None for common templates)
        template_code: Proposed template code (unique identifier)
        exclude_template_id: Optional template ID to exclude (for updates)

    Returns:
        True if code is available, False if already in use
    """
    query = supabase.table("templates").select("id").eq("template_code", template_code.strip())

    if counsellor_id:
        # Counsellor-owned template: check against this counsellor's templates
        query = query.eq("counsellor_id", str(counsellor_id))
    else:
        # Common template (counsellor_id=NULL): check against other common templates
        query = query.is_("counsellor_id", "null")

    if exclude_template_id:
        query = query.neq("id", str(exclude_template_id))

    response = query.execute()
    return len(response.data) == 0


def validate_segment_configuration(counsellor_id: uuid.UUID) -> Dict[str, Any]:
    """
    Validate user's segment configuration for clinical safety.

    Returns:
        Dict with 'is_valid' (bool) and 'error_message' (str or None)
    """
    response = supabase.rpc("validate_segment_configuration", {
        "p_counsellor_id": str(counsellor_id)
    }).execute()

    if response.data:
        return response.data[0]
    else:
        return {"is_valid": False, "error_message": "Validation failed"}


# reset_counsellor_segment_config() REMOVED
# Counsellor customization now handled via template cloning (clone_template function)


# ============================================================================
# Template Admin Functions (Create, Update, Delete Templates)
# ============================================================================

def create_template(
    template_code: str,
    template_name: str,
    description: str,
    consultation_type_id: uuid.UUID,
    use_case: Optional[str] = None,
    specialization: Optional[str] = None,
    school_id: Optional[uuid.UUID] = None,
    counsellor_id: Optional[uuid.UUID] = None,
    estimated_extraction_time_seconds: Optional[float] = None,
    is_active: bool = True,
) -> Dict[str, Any]:
    """
    Create a new template.

    Args:
        template_code: Unique template code (e.g., 'PSYCHIATRY_CORE')
        template_name: Display name
        description: Template description
        consultation_type_id: Consultation type UUID
        use_case: Optional use case (e.g., 'quick_consultation')
        specialization: Optional specialization for visibility filtering
        school_id: Optional school ID for school-specific templates
        counsellor_id: Optional counsellor who owns the template (NULL = common template)
        estimated_extraction_time_seconds: Optional performance hint
        is_active: Whether template is active and visible to counsellors (default: True)

    Returns:
        Created template record
    """
    template_data = {
        "template_code": template_code,
        "template_name": template_name,
        "description": description,
        "consultation_type_id": str(consultation_type_id),
        "is_default": False,
        "is_active": is_active
    }

    if use_case is not None:
        template_data["use_case"] = use_case
    if specialization is not None:
        template_data["specialization"] = specialization
    if school_id is not None:
        template_data["school_id"] = str(school_id)
    if counsellor_id is not None:
        template_data["counsellor_id"] = str(counsellor_id)
    if estimated_extraction_time_seconds is not None:
        template_data["estimated_extraction_time_seconds"] = estimated_extraction_time_seconds

    response = supabase.table("templates").insert(template_data).execute()

    if not response.data:
        raise ValueError("Failed to create template")

    return response.data[0]


def update_template(
    template_code: str,
    template_name: Optional[str] = None,
    description: Optional[str] = None,
    use_case: Optional[str] = None,
    specialization: Optional[str] = None,
    estimated_extraction_time_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Update template metadata.

    Args:
        template_code: Template code to update
        template_name: Optional new name
        description: Optional new description
        use_case: Optional new use case
        specialization: Optional new specialization for visibility filtering
        estimated_extraction_time_seconds: Optional new time estimate

    Returns:
        Updated template record
    """
    update_data = {}

    if template_name is not None:
        update_data["template_name"] = template_name
    if description is not None:
        update_data["description"] = description
    if use_case is not None:
        update_data["use_case"] = use_case
    if specialization is not None:
        update_data["specialization"] = specialization
    if estimated_extraction_time_seconds is not None:
        update_data["estimated_extraction_time_seconds"] = estimated_extraction_time_seconds

    if not update_data:
        raise ValueError("No update data provided")

    response = (
        supabase.table("templates")
        .update(update_data)
        .eq("template_code", template_code)
        .execute()
    )

    if not response.data:
        raise ValueError(f"Template '{template_code}' not found")

    return response.data[0]


def delete_template(template_code: str) -> None:
    """
    Delete a template (soft delete by setting is_active = False).

    Args:
        template_code: Template code to delete

    Raises:
        ValueError: If template not found
    """
    # Check if template exists
    template = get_template_by_code(template_code)

    if not template:
        raise ValueError(f"Template '{template_code}' not found")

    # Soft delete
    supabase.table("templates").update({
        "is_active": False
    }).eq("template_code", template_code).execute()


def delete_segment(segment_id: str) -> None:
    """
    Delete a segment definition (soft delete by setting is_active = False).

    **JUNCTION TABLE ARCHITECTURE**: Deletes from master table. Junction table entries remain (orphaned).
    Consider deleting junction entries separately if needed.

    Args:
        segment_id: Segment ID (UUID) to delete

    Raises:
        ValueError: If segment not found
    """
    logger.info(f"[SEGMENT_DELETE] Deleting segment with ID '{segment_id}'")

    # Query master table by ID
    result = (
        supabase.table("segment_definitions")
        .select("*")
        .eq("id", segment_id)
        .execute()
    )

    if not result.data or len(result.data) == 0:
        logger.error(f"[SEGMENT_DELETE] Segment with ID '{segment_id}' not found")
        raise ValueError(f"Segment with ID '{segment_id}' not found")

    segment = result.data[0]

    # Admin can delete any segment (including required)
    logger.info(f"[SEGMENT_DELETE] Deleting segment: id={segment['id']}, code={segment.get('segment_code')}, name={segment.get('segment_name')}, is_required={segment.get('is_required')}, is_active={segment.get('is_active')}")

    # Soft delete from master table
    update_result = supabase.table("segment_definitions").update({
        "is_active": False
    }).eq("id", segment_id).execute()

    logger.info(f"[SEGMENT_DELETE] ✓ Segment '{segment.get('segment_name')}' ({segment.get('segment_code')}) deleted successfully. Updated {len(update_result.data)} row(s). New state: {update_result.data}")

    # HOOK: Trigger reassembly for affected templates
    try:
        from .template_assembly_service import trigger_reassembly_async, get_templates_using_segment
        affected_templates = get_templates_using_segment(uuid.UUID(segment_id))
        if affected_templates:
            segment_code = segment.get('segment_code', 'unknown')
            trigger_source = f"segment_definition:{segment_code}:deactivate"
            asyncio.create_task(trigger_reassembly_async(affected_templates, trigger_source))
            logger.info(f"[SEGMENT_DELETE] Triggered reassembly for {len(affected_templates)} templates")
    except Exception as e:
        logger.error(f"[SEGMENT_DELETE] Failed to trigger reassembly hook: {e}")


def delete_consultation_type(consultation_type_code: str) -> None:
    """
    Delete a consultation type (soft delete by setting is_active = False).

    CASCADE BEHAVIOR:
    - Inactivates all templates associated with this consultation type
    - Inactivates all segments linked via consultation_type_segments

    Args:
        consultation_type_code: Consultation type code to delete

    Raises:
        ValueError: If consultation type not found or is default
    """
    logger.info(f"[CONSULTATION_TYPE_DELETE] Deleting consultation type '{consultation_type_code}'")

    # Check if consultation type exists
    consultation_type = get_consultation_type_by_code(consultation_type_code)

    if not consultation_type:
        logger.error(f"[CONSULTATION_TYPE_DELETE] Consultation type '{consultation_type_code}' not found")
        raise ValueError(f"Consultation type '{consultation_type_code}' not found")

    consultation_type_id = consultation_type.get('id')
    logger.info(f"[CONSULTATION_TYPE_DELETE] Deleting consultation type: id={consultation_type_id}, is_default={consultation_type.get('is_default')}")

    # CASCADE: Inactivate all templates associated with this consultation type
    try:
        templates_result = supabase.table("templates").update({
            "is_active": False
        }).eq("consultation_type_id", consultation_type_id).execute()
        logger.info(f"[CONSULTATION_TYPE_DELETE] CASCADE: Inactivated {len(templates_result.data or [])} templates")
    except Exception as e:
        logger.warning(f"[CONSULTATION_TYPE_DELETE] Could not cascade inactivate templates: {e}")

    # CASCADE: Get segment IDs from consultation_type_segments junction table
    try:
        ct_segments = supabase.table("consultation_type_segments").select("segment_id").eq("consultation_type_id", consultation_type_id).execute()
        segment_ids = [row['segment_id'] for row in (ct_segments.data or []) if row.get('segment_id')]

        if segment_ids:
            # Inactivate all linked segments
            segments_result = supabase.table("segment_definitions").update({
                "is_active": False
            }).in_("id", segment_ids).execute()
            logger.info(f"[CONSULTATION_TYPE_DELETE] CASCADE: Inactivated {len(segments_result.data or [])} segments")
    except Exception as e:
        logger.warning(f"[CONSULTATION_TYPE_DELETE] Could not cascade inactivate segments: {e}")

    # Soft delete the consultation type itself
    supabase.table("consultation_types").update({
        "is_active": False
    }).eq("type_code", consultation_type_code).execute()

    logger.info(f"[CONSULTATION_TYPE_DELETE] ✓ Consultation type '{consultation_type_code}' deleted successfully (with cascade)")


# ============================================================================
# REACTIVATE FUNCTIONS (Restore soft-deleted entities)
# ============================================================================

def reactivate_template(template_code: str) -> None:
    """
    Reactivate a soft-deleted template (set is_active = True).

    Args:
        template_code: Template code to reactivate

    Raises:
        ValueError: If template not found
    """
    logger.info(f"[TEMPLATE_REACTIVATE] Reactivating template '{template_code}'")

    # Check if template exists (including inactive ones)
    result = (
        supabase.table("templates")
        .select("*")
        .eq("template_code", template_code)
        .execute()
    )

    if not result.data or len(result.data) == 0:
        logger.error(f"[TEMPLATE_REACTIVATE] Template '{template_code}' not found")
        raise ValueError(f"Template '{template_code}' not found")

    # Reactivate
    supabase.table("templates").update({
        "is_active": True
    }).eq("template_code", template_code).execute()

    logger.info(f"[TEMPLATE_REACTIVATE] ✓ Template '{template_code}' reactivated successfully")


def reactivate_segment(segment_id: str) -> None:
    """
    Reactivate a soft-deleted segment (set is_active = True).

    Args:
        segment_id: Segment ID (UUID) to reactivate

    Raises:
        ValueError: If segment not found
    """
    logger.info(f"[SEGMENT_REACTIVATE] Reactivating segment with ID '{segment_id}'")

    # Query segment (including inactive ones)
    result = (
        supabase.table("segment_definitions")
        .select("*")
        .eq("id", segment_id)
        .execute()
    )

    if not result.data or len(result.data) == 0:
        logger.error(f"[SEGMENT_REACTIVATE] Segment with ID '{segment_id}' not found")
        raise ValueError(f"Segment with ID '{segment_id}' not found")

    segment = result.data[0]

    # Reactivate
    supabase.table("segment_definitions").update({
        "is_active": True
    }).eq("id", segment_id).execute()

    logger.info(f"[SEGMENT_REACTIVATE] ✓ Segment '{segment.get('segment_name')}' ({segment.get('segment_code')}) reactivated successfully")

    # HOOK: Trigger reassembly for affected templates
    try:
        from .template_assembly_service import trigger_reassembly_async, get_templates_using_segment
        affected_templates = get_templates_using_segment(uuid.UUID(segment_id))
        if affected_templates:
            segment_code = segment.get('segment_code', 'unknown')
            trigger_source = f"segment_definition:{segment_code}:reactivate"
            asyncio.create_task(trigger_reassembly_async(affected_templates, trigger_source))
            logger.info(f"[SEGMENT_REACTIVATE] Triggered reassembly for {len(affected_templates)} templates")
    except Exception as e:
        logger.error(f"[SEGMENT_REACTIVATE] Failed to trigger reassembly hook: {e}")


def reactivate_consultation_type(consultation_type_code: str) -> None:
    """
    Reactivate a soft-deleted consultation type (set is_active = True).

    CASCADE BEHAVIOR:
    - Reactivates all templates associated with this consultation type
    - Reactivates all segments linked via consultation_type_segments

    Args:
        consultation_type_code: Consultation type code to reactivate

    Raises:
        ValueError: If consultation type not found
    """
    logger.info(f"[CONSULTATION_TYPE_REACTIVATE] Reactivating consultation type '{consultation_type_code}'")

    # Check if consultation type exists (including inactive ones)
    result = (
        supabase.table("consultation_types")
        .select("*")
        .eq("type_code", consultation_type_code)
        .execute()
    )

    if not result.data or len(result.data) == 0:
        logger.error(f"[CONSULTATION_TYPE_REACTIVATE] Consultation type '{consultation_type_code}' not found")
        raise ValueError(f"Consultation type '{consultation_type_code}' not found")

    consultation_type_id = result.data[0].get('id')

    # CASCADE: Reactivate all templates associated with this consultation type
    try:
        templates_result = supabase.table("templates").update({
            "is_active": True
        }).eq("consultation_type_id", consultation_type_id).execute()
        logger.info(f"[CONSULTATION_TYPE_REACTIVATE] CASCADE: Reactivated {len(templates_result.data or [])} templates")
    except Exception as e:
        logger.warning(f"[CONSULTATION_TYPE_REACTIVATE] Could not cascade reactivate templates: {e}")

    # CASCADE: Get segment IDs from consultation_type_segments junction table
    try:
        ct_segments = supabase.table("consultation_type_segments").select("segment_id").eq("consultation_type_id", consultation_type_id).execute()
        segment_ids = [row['segment_id'] for row in (ct_segments.data or []) if row.get('segment_id')]

        if segment_ids:
            # Reactivate all linked segments
            segments_result = supabase.table("segment_definitions").update({
                "is_active": True
            }).in_("id", segment_ids).execute()
            logger.info(f"[CONSULTATION_TYPE_REACTIVATE] CASCADE: Reactivated {len(segments_result.data or [])} segments")
    except Exception as e:
        logger.warning(f"[CONSULTATION_TYPE_REACTIVATE] Could not cascade reactivate segments: {e}")

    # Reactivate the consultation type itself
    supabase.table("consultation_types").update({
        "is_active": True
    }).eq("type_code", consultation_type_code).execute()

    logger.info(f"[CONSULTATION_TYPE_REACTIVATE] ✓ Consultation type '{consultation_type_code}' reactivated successfully (with cascade)")


def update_template_segment_config(
    template_id: uuid.UUID,
    segment_code: str,
    category: str,
    display_order: int,
    brevity_level: Optional[str] = None,
    terminology_style: Optional[str] = None,
    skip_reassembly: bool = False,
) -> Dict[str, Any]:
    """
    Update or create a template's segment configuration.

    Args:
        template_id: Template UUID
        segment_code: Segment to configure (e.g., 'DIAGNOSIS')
        category: 'core' | 'additional' | 'excluded'
        display_order: Order in extraction
        brevity_level: Optional 'concise' | 'balanced' | 'detailed'
        terminology_style: Optional 'medical_terms' | 'simple_terms' | 'as_spoken'

    Returns:
        Created/updated configuration record
    """
    logger.info(f"[TEMPLATE_SEGMENT_MOVEMENT] Updating segment '{segment_code}' for template '{template_id}'")
    logger.info(f"[TEMPLATE_SEGMENT_MOVEMENT] Requested category: {category}")

    # First, get the segment_id from the template_segments junction table
    # The composite key (template_id, segment_code) is unique
    junction_lookup = (
        supabase.table("template_segments")
        .select("segment_id")
        .eq("template_id", str(template_id))
        .eq("segment_code", segment_code)
        .execute()
    )

    segment_id = None
    if junction_lookup.data and len(junction_lookup.data) > 0:
        segment_id = junction_lookup.data[0].get("segment_id")

    # Check if the segment is required (from segment_definitions)
    # Use segment_id if available, otherwise log a warning
    segment_check_data: List[Dict[str, Any]] = []
    if segment_id:
        segment_check_response = (
            supabase.table("segment_definitions")
            .select("is_required, default_category")
            .eq("id", segment_id)
            .execute()
        )
        segment_check_data = segment_check_response.data or []
    else:
        # Fallback for new segments not yet in junction table
        logger.warning(f"[TEMPLATE_SEGMENT_MOVEMENT] No junction entry found for segment '{segment_code}' in template '{template_id}', creating new entry")

    if segment_check_data and len(segment_check_data) > 0:
        seg_def = segment_check_data[0]
        is_segment_required = seg_def.get("is_required", False)
        default_category = seg_def.get("default_category", "core")

        if is_segment_required and default_category == "core" and category != "core":
            logger.error(f"[TEMPLATE_SEGMENT_MOVEMENT] BLOCKED: Cannot move required segment '{segment_code}' from CORE to {category}")
            raise ValueError(
                f"Cannot move required segment '{segment_code}' from CORE category. "
                f"Required segments must remain in CORE for clinical safety."
            )

    # Check if config exists
    existing = (
        supabase.table("template_segments")
        .select("*")
        .eq("template_id", str(template_id))
        .eq("segment_code", segment_code)
        .execute()
    )

    config_data = {
        "template_id": str(template_id),
        "segment_code": segment_code,
        "category": category,
        "display_order": display_order
    }

    if brevity_level is not None:
        config_data["brevity_level"] = brevity_level
    if terminology_style is not None:
        config_data["terminology_style"] = terminology_style

    if existing.data:
        # Update existing
        logger.info(f"[TEMPLATE_SEGMENT_MOVEMENT] Updating existing configuration for '{segment_code}'")
        response = (
            supabase.table("template_segments")
            .update(config_data)
            .eq("template_id", str(template_id))
            .eq("segment_code", segment_code)
            .execute()
        )
    else:
        # Insert new
        logger.info(f"[TEMPLATE_SEGMENT_MOVEMENT] Creating new configuration for '{segment_code}'")
        if brevity_level is None:
            config_data["brevity_level"] = "balanced"
        if terminology_style is None:
            config_data["terminology_style"] = "medical_terms"

        response = (
            supabase.table("template_segments")
            .insert(config_data)
            .execute()
        )

    if not response.data:
        logger.error(f"[TEMPLATE_SEGMENT_MOVEMENT] Failed to update template segment configuration for '{segment_code}'")
        raise ValueError("Failed to update template segment configuration")

    logger.info(f"[TEMPLATE_SEGMENT_MOVEMENT] ✓ Successfully moved segment '{segment_code}' to category: {category}")

    # HOOK: Trigger reassembly for this template (can be skipped for bulk operations)
    if not skip_reassembly:
        try:
            from .template_assembly_service import trigger_reassembly_async
            trigger_source = f"template_segment:{template_id}:{segment_code}:config_update"
            asyncio.create_task(trigger_reassembly_async([template_id], trigger_source))
            logger.info(f"[TEMPLATE_SEGMENT_MOVEMENT] Triggered reassembly for template {template_id}")
        except Exception as e:
            logger.error(f"[TEMPLATE_SEGMENT_MOVEMENT] Failed to trigger reassembly hook: {e}")
    else:
        logger.debug(f"[TEMPLATE_SEGMENT_MOVEMENT] Skipping reassembly (bulk operation)")

    return response.data[0]


def bulk_update_template_segments(
    template_id: uuid.UUID,
    segments: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Bulk update template segment configurations.

    OPTIMIZED: Skips individual reassembly hooks and triggers only once at the end.

    Args:
        template_id: Template UUID
        segments: List of segment configs with keys: segment_code, category, display_order, brevity_level, terminology_style

    Returns:
        List of updated configuration records
    """
    results = []
    segment_codes_updated = []

    for segment in segments:
        result = update_template_segment_config(
            template_id=template_id,
            segment_code=segment["segment_code"],
            category=segment["category"],
            display_order=segment["display_order"],
            brevity_level=segment.get("brevity_level"),
            terminology_style=segment.get("terminology_style"),
            skip_reassembly=True  # Skip individual reassembly for bulk operations
        )
        results.append(result)
        segment_codes_updated.append(segment["segment_code"])

    # HOOK: Trigger reassembly ONCE at the end of bulk operation
    if results:
        try:
            from .template_assembly_service import trigger_reassembly_async
            codes_summary = ",".join(segment_codes_updated[:3])
            if len(segment_codes_updated) > 3:
                codes_summary += f"...+{len(segment_codes_updated)-3} more"
            trigger_source = f"template_segment:{template_id}:{codes_summary}:bulk_update"
            asyncio.create_task(trigger_reassembly_async([template_id], trigger_source))
            logger.info(f"[BULK_UPDATE] Triggered single reassembly for template {template_id} after {len(results)} segment updates")
        except Exception as e:
            logger.error(f"[BULK_UPDATE] Failed to trigger reassembly hook: {e}")

    return results


def inherit_from_consultation_type(
    template_id: uuid.UUID,
    consultation_type_id: uuid.UUID
) -> List[Dict[str, Any]]:
    """
    Inherit segment configuration from consultation type defaults.

    This copies all segment_definitions for the consultation type
    into template_segments with default settings.

    Args:
        template_id: Target template UUID
        consultation_type_id: Source consultation type UUID

    Returns:
        List of created configuration records
    """
    # Get all segments for this consultation type via junction table
    # Step 1: Get segment IDs from junction table
    junction_response = (
        supabase.table("consultation_type_segments")
        .select("segment_id, segment_code")
        .eq("consultation_type_id", str(consultation_type_id))
        .execute()
    )

    # Allow template creation without segments - just return empty list
    if not junction_response.data:
        logger.debug(f"[inherit_from_consultation_type] No segments found for consultation type {consultation_type_id}, template will have no segment configurations")
        return []

    segment_ids = [j['segment_id'] for j in junction_response.data]

    # Step 2: Get full segment details from segment_definitions
    segments = (
        supabase.table("segment_definitions")
        .select("id, segment_code, default_category, display_order, default_brevity_level, default_terminology_style")
        .in_("id", segment_ids)
        .eq("is_active", True)
        .order("display_order")
        .execute()
    )

    # Allow template creation even if all segments are inactive
    if not segments.data:
        logger.debug(f"[inherit_from_consultation_type] No active segments found for consultation type {consultation_type_id}, template will have no segment configurations")
        return []

    # Delete existing template configs (clean slate)
    supabase.table("template_segments").delete().eq("template_id", str(template_id)).execute()

    # Create new configs from segment definitions
    results = []
    for segment in segments.data:
        config_data = {
            "template_id": str(template_id),
            "segment_id": str(segment["id"]),
            "segment_code": segment["segment_code"],
            "category": segment["default_category"],
            "display_order": segment["display_order"],
            "brevity_level": segment.get("default_brevity_level", "balanced"),
            "terminology_style": segment.get("default_terminology_style", "medical_terms")
        }

        response = (
            supabase.table("template_segments")
            .insert(config_data)
            .execute()
        )

        if response.data:
            results.append(response.data[0])

    # HOOK: Trigger reassembly for this template
    try:
        from .template_assembly_service import trigger_reassembly_async
        trigger_source = f"template_segment:{template_id}:inherit"
        asyncio.create_task(trigger_reassembly_async([template_id], trigger_source))
        logger.info(f"[INHERIT_FROM_CONSULTATION_TYPE] Triggered reassembly for template {template_id}")
    except Exception as e:
        logger.error(f"[INHERIT_FROM_CONSULTATION_TYPE] Failed to trigger reassembly hook: {e}")

    return results


def inherit_from_template(
    target_template_id: uuid.UUID,
    source_template_code: str
) -> List[Dict[str, Any]]:
    """
    Inherit segment configuration from another template.

    This copies all template_segments from the source template
    into the target template with the same settings.

    Args:
        target_template_id: Target template UUID
        source_template_code: Source template code to copy from

    Returns:
        List of created configuration records

    Raises:
        ValueError: If source template not found or has no configurations
    """
    # Get source template
    source_template = (
        supabase.table("templates")
        .select("id")
        .eq("template_code", source_template_code)
        .eq("is_active", True)
        .execute()
    )

    if not source_template.data:
        raise ValueError(f"Source template '{source_template_code}' not found")

    source_template_id = source_template.data[0]["id"]

    # Get all segment configurations from source template
    source_configs = (
        supabase.table("template_segments")
        .select("segment_id, segment_code, category, display_order, brevity_level, terminology_style")
        .eq("template_id", source_template_id)
        .order("display_order")
        .execute()
    )

    if not source_configs.data:
        raise ValueError(f"Source template '{source_template_code}' has no segment configurations")

    # Delete existing target template configs (clean slate)
    supabase.table("template_segments").delete().eq("template_id", str(target_template_id)).execute()

    # Create new configs from source template
    results = []
    for config in source_configs.data:
        config_data = {
            "template_id": str(target_template_id),
            "segment_id": str(config["segment_id"]) if config.get("segment_id") else None,
            "segment_code": config["segment_code"],
            "category": config["category"],
            "display_order": config["display_order"],
            "brevity_level": config.get("brevity_level", "balanced"),
            "terminology_style": config.get("terminology_style", "medical_terms")
        }

        response = (
            supabase.table("template_segments")
            .insert(config_data)
            .execute()
        )

        if response.data:
            results.append(response.data[0])

    return results


# ============================================================================
# Extractions Storage (Multi-Consultation Type)
# ============================================================================

def save_extraction(
    consultation_type_id: uuid.UUID,
    extraction_mode: str,
    model_used: str,
    segment_count: int,
    full_extraction_json: Dict[str, Any],
    session_id: Optional[uuid.UUID] = None,
    counsellor_id: Optional[uuid.UUID] = None,
    student_id: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    """
    Save an extraction to the database.

    Args:
        consultation_type_id: Type of consultation (OP, DISCHARGE, etc.)
        extraction_mode: 'core' | 'additional' | 'full'
        model_used: Gemini model used (e.g., 'gemini-2.5-flash')
        segment_count: Number of segments extracted
        full_extraction_json: Complete extraction data
        session_id: Optional recording session ID
        counsellor_id: Optional counsellor/user ID
        student_id: Optional student ID

    Returns:
        Created extraction record
    """
    data = {
        "consultation_type_id": str(consultation_type_id),
        "extraction_mode": extraction_mode,
        "model_used": model_used,
        "segment_count": segment_count,
        "full_extraction_json": full_extraction_json,
    }

    if session_id:
        data["session_id"] = str(session_id)
    if counsellor_id:
        data["counsellor_id"] = str(counsellor_id)
    if student_id:
        data["student_id"] = str(student_id)

    response = supabase.table("extractions").insert(data).execute()
    return response.data[0] if response.data else {}


def save_extraction_segments(
    extraction_id: uuid.UUID,
    segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Save individual segments for an extraction (segment-value table).

    Args:
        extraction_id: extraction ID
        segments: List of segments with keys:
            - segment_code: str
            - segment_value: dict | str (stored as JSONB)
            - brevity_level: Optional[str]
            - terminology_style: Optional[str]
            - display_format: Optional[str]

    Returns:
        List of saved segment records
    """
    # Prepare segment records
    segment_records = []
    for segment in segments:
        record = {
            "extraction_id": str(extraction_id),
            "segment_code": segment["segment_code"],
            "segment_value": segment["segment_value"],
        }

        # Optional fields
        if "brevity_level" in segment:
            record["brevity_level"] = segment["brevity_level"]
        if "terminology_style" in segment:
            record["terminology_style"] = segment["terminology_style"]
        if "display_format" in segment:
            record["display_format"] = segment["display_format"]

        segment_records.append(record)

    # Bulk insert
    response = supabase.table("extraction_segments").insert(segment_records).execute()
    return response.data if response.data else []


def get_extraction_by_id(extraction_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get extraction record by ID"""
    response = (
        supabase.table("extractions")
        .select("*, consultation_types(*)")
        .eq("id", str(extraction_id))
        .execute()
    )
    return response.data[0] if response.data else None


def check_extraction_exists(extraction_id: uuid.UUID) -> bool:
    """
    Check if an extraction record exists (lightweight check).

    Used by combined emotion analysis to verify extraction exists before saving.

    Args:
        extraction_id: UUID of the extraction to check

    Returns:
        bool: True if extraction exists, False otherwise
    """
    response = (
        supabase.table("extractions")
        .select("id")
        .eq("id", str(extraction_id))
        .limit(1)
        .execute()
    )
    return len(response.data) > 0


def get_extraction_segments(extraction_id: uuid.UUID) -> List[Dict[str, Any]]:
    """Get all segments for an extraction"""
    response = (
        supabase.table("extraction_segments")
        .select("*")
        .eq("extraction_id", str(extraction_id))
        .order("created_at")
        .execute()
    )
    return response.data if response.data else []


# ============================================================================
# Emotion Analysis Support Functions
# ============================================================================

def update_extraction_emotion_status(
    extraction_id: uuid.UUID,
    started: bool = False,
    completed: bool = False,
    failed: bool = False,
    error: Optional[str] = None
) -> None:
    """
    Update emotion extraction status flags in extractions table.

    This function updates the tracking columns for background emotion extraction:
    - emotion_extraction_started: Task has been scheduled/started
    - emotion_extraction_completed: Task completed successfully
    - emotion_extraction_failed: Task failed with error
    - emotion_extraction_error: Error message if failed
    - emotion_extraction_started_at: Timestamp when started
    - emotion_extraction_completed_at: Timestamp when completed

    Args:
        extraction_id: UUID of extraction
        started: Set emotion_extraction_started=True and record timestamp
        completed: Set emotion_extraction_completed=True and record timestamp
        failed: Set emotion_extraction_failed=True
        error: Error message to store (optional)

    Raises:
        Exception: If update fails
    """
    logger.debug(f"[EMOTION] Updating status for extraction_id={extraction_id} (started={started}, completed={completed}, failed={failed})")

    try:
        update_data = {}

        # Handle started flag
        if started:
            update_data["emotion_extraction_started"] = True
            update_data["emotion_extraction_started_at"] = datetime.now(timezone.utc).isoformat()
            logger.debug(f"[EMOTION] Marking as started")

        # Handle completed flag
        if completed:
            update_data["emotion_extraction_completed"] = True
            update_data["emotion_extraction_completed_at"] = datetime.now(timezone.utc).isoformat()
            logger.debug(f"[EMOTION] Marking as completed")

        # Handle failed flag
        if failed:
            update_data["emotion_extraction_failed"] = True
            if error:
                update_data["emotion_extraction_error"] = error
            logger.debug(f"[EMOTION] Marking as failed")

        if not update_data:
            logger.warning(f"[EMOTION] No status updates to apply for extraction_id={extraction_id}")
            return

        # Update extractions record
        response = (
            supabase.table("extractions")
            .update(update_data)
            .eq("id", str(extraction_id))
            .execute()
        )

        if response.data:
            logger.debug(f"[EMOTION] Status updated successfully")
        else:
            logger.warning(f"[EMOTION] No rows updated (extraction_id may not exist)")

    except Exception as e:
        logger.error(f"[EMOTION] Error updating emotion status: {e}", exc_info=True)
        raise Exception(f"Failed to update emotion extraction status: {str(e)}")


# ============================================================================
# Audio Emotion Analysis Support Functions
# ============================================================================

# Cache for audio emotion prompts with TTL
# Long TTL (1 year) since prompts only change when AUDIO_* segments are updated
# Invalidation is triggered via on_audio_segment_updated() -> invalidate_audio_emotion_prompt_cache()
_audio_emotion_prompt_cache: Dict[str, Dict[str, Any]] = {}
_audio_emotion_prompt_cache_time: Dict[str, float] = {}
AUDIO_EMOTION_PROMPT_CACHE_TTL = 31536000  # 1 year (invalidation-based)


def invalidate_audio_emotion_prompt_cache(template_id: Optional[uuid.UUID] = None):
    """
    Invalidate audio emotion prompt cache.

    Call this when prompts or schemas are updated in:
    - system_prompt_components (AUDIO_EMOTION_BASE_PROMPT_*)
    - segment_definitions (AUDIO_* segments)
    - templates (assembled_audio_* columns)

    Args:
        template_id: If provided, invalidate only this template. Otherwise invalidate all.
    """
    global _audio_emotion_prompt_cache, _audio_emotion_prompt_cache_time

    if template_id:
        cache_key = str(template_id)
        if cache_key in _audio_emotion_prompt_cache:
            del _audio_emotion_prompt_cache[cache_key]
            del _audio_emotion_prompt_cache_time[cache_key]
            logger.debug(f"[AUDIO_EMOTION_PROMPT] Cache invalidated for template {template_id}")
    else:
        _audio_emotion_prompt_cache.clear()
        _audio_emotion_prompt_cache_time.clear()
        logger.debug("[AUDIO_EMOTION_PROMPT] Full cache invalidated")


# Standardized emotion segment codes (no COMBINED_/AUDIO_ prefix) — counselling 3-speaker model.
# Single source of truth: derived by stripping 'COMBINED_' from the active emotion
# segment_definitions (migration 20260601150000). Consumed by save_unified_emotion_segments /
# get_unified_emotion_segments below, and imported by webhook_service / nudge_api_service /
# student_dropoff_service so they all stay in sync.
UNIFIED_EMOTION_SEGMENT_CODES = [
    "STUDENT_ANXIETY",
    "PARENT_ANXIETY",
    "STUDENT_ENGAGEMENT",
    "COUNSELLOR_COMMUNICATION",
    "SESSION_INTERACTION_DYNAMICS",
    "SESSION_OTHER_EMOTIONS",
    "SESSION_CONGRUENCE_SUMMARY",
]


def save_unified_emotion_segments(
    extraction_id: uuid.UUID,
    segments_data: Dict[str, Any],
    source: str
) -> List[Dict[str, Any]]:
    """
    Save unified emotion segments to extraction_segments table.

    Stores final emotion analysis results using standardized segment codes
    (no TEXT_EMOTION_ or AUDIO_ prefix). All emotion modes (audio_only, combined)
    should save to these unified segment codes for consistency.

    Args:
        extraction_id: UUID of extraction to link to
        segments_data: Dict with unified segment keys:
            - ANXIETY_POST_CONSULTATION (with nested pre/post/trajectory)
            - FINANCIAL_CONCERNS
            - OTHER_EMOTIONS_DETECTED
            - TREATMENT_COMPLIANCE_LIKELIHOOD
            - DOCTOR_COMMUNICATION_STYLE
            - INTERACTION_DYNAMICS (new Jan 2026)
            - CONGRUENCE_SUMMARY (combined mode only - requires text+audio)
        source: Analysis source mode ("audio_only" or "combined")

    Returns:
        List of saved segment records

    Raises:
        Exception: If save fails
    """
    logger.debug(
        f"[UNIFIED_EMOTION] Saving unified emotion segments for extraction_id={extraction_id}, "
        f"source={source}"
    )

    try:
        segment_records = []

        for segment_code in UNIFIED_EMOTION_SEGMENT_CODES:
            if segment_code in segments_data:
                segment_value = segments_data[segment_code]

                # Ensure source is set in segment_value
                if isinstance(segment_value, dict):
                    segment_value["source"] = source

                record = {
                    "extraction_id": str(extraction_id),
                    "segment_code": segment_code,
                    "segment_value": segment_value,
                    "brevity_level": "balanced",
                    "terminology_style": "medical_terms",
                }
                segment_records.append(record)
            else:
                logger.debug(f"[UNIFIED_EMOTION] Segment not present in data: {segment_code}")

        if not segment_records:
            logger.warning(
                f"[UNIFIED_EMOTION] No unified emotion segments to save for "
                f"extraction_id={extraction_id}"
            )
            return []

        # Bulk insert unified emotion segments
        logger.debug(f"[UNIFIED_EMOTION] Inserting {len(segment_records)} unified emotion segments...")

        response = supabase.table("extraction_segments").insert(segment_records).execute()

        saved_count = len(response.data) if response.data else 0
        logger.debug(f"[UNIFIED_EMOTION] Successfully saved {saved_count} unified emotion segments")

        return response.data if response.data else []

    except Exception as e:
        logger.error(f"[UNIFIED_EMOTION] Error saving unified emotion segments: {e}", exc_info=True)
        # Don't raise - unified segments are supplementary, shouldn't block main flow
        return []


def get_unified_emotion_segments(extraction_id: uuid.UUID) -> Dict[str, Any]:
    """
    Get unified emotion segments for an extraction.

    Retrieves emotion segments stored with unified codes (no TEXT_EMOTION_/AUDIO_ prefix).
    These segments are available for all emotion modes (text_only, audio_only, combined).

    Args:
        extraction_id: UUID of the extraction

    Returns:
        Dict with unified emotion segment codes as keys and segment values as values.
        Each segment_value includes a 'source' field indicating origin.
        Returns empty dict if no segments found.
    """
    try:
        response = (
            supabase.table("extraction_segments")
            .select("segment_code, segment_value")
            .eq("extraction_id", str(extraction_id))
            .in_("segment_code", UNIFIED_EMOTION_SEGMENT_CODES)
            .execute()
        )

        if response.data:
            return {seg["segment_code"]: seg["segment_value"] for seg in response.data}
        else:
            return {}

    except Exception as e:
        logger.error(f"[UNIFIED_EMOTION] Error getting unified emotion segments: {e}")
        return {}


def update_audio_emotion_extraction_status(
    extraction_id: uuid.UUID,
    started: bool = False,
    completed: bool = False,
    failed: bool = False,
    error: Optional[str] = None,
    fallback_used: bool = False,
) -> None:
    """
    Update audio emotion extraction status flags in extractions table.

    This function updates the tracking columns for background audio emotion extraction:
    - audio_emotion_extraction_started: Task has been scheduled/started
    - audio_emotion_extraction_completed: Task completed successfully
    - audio_emotion_extraction_failed: Task failed with error
    - audio_emotion_extraction_error: Error message if failed
    - audio_emotion_extraction_started_at: Timestamp when started
    - audio_emotion_extraction_completed_at: Timestamp when completed
    - audio_emotion_extraction_fallback_used: True if fallback to empty emotions was used

    Args:
        extraction_id: UUID of extraction
        started: Set audio_emotion_extraction_started=True and record timestamp
        completed: Set audio_emotion_extraction_completed=True and record timestamp
        failed: Set audio_emotion_extraction_failed=True
        error: Error message to store (optional)
        fallback_used: Set audio_emotion_extraction_fallback_used=True (JSON parse failed, returned empty emotions)

    Raises:
        Exception: If update fails
    """
    logger.debug(f"[AUDIO_EMOTION] Updating status for extraction_id={extraction_id} (started={started}, completed={completed}, failed={failed}, fallback_used={fallback_used})")

    try:
        update_data = {}

        if started:
            update_data["audio_emotion_extraction_started"] = True
            update_data["audio_emotion_extraction_started_at"] = datetime.now(timezone.utc).isoformat()
            logger.debug(f"[AUDIO_EMOTION] Marking as started")

        if completed:
            update_data["audio_emotion_extraction_completed"] = True
            update_data["audio_emotion_extraction_completed_at"] = datetime.now(timezone.utc).isoformat()
            logger.debug(f"[AUDIO_EMOTION] Marking as completed")

        if failed:
            update_data["audio_emotion_extraction_failed"] = True
            if error:
                update_data["audio_emotion_extraction_error"] = error
            logger.debug(f"[AUDIO_EMOTION] Marking as failed")

        if fallback_used:
            update_data["audio_emotion_extraction_fallback_used"] = True
            logger.debug(f"[AUDIO_EMOTION] Marking fallback_used=True (empty emotions due to JSON parse failure)")

        if not update_data:
            logger.warning(f"[AUDIO_EMOTION] No status updates to apply for extraction_id={extraction_id}")
            return

        response = (
            supabase.table("extractions")
            .update(update_data)
            .eq("id", str(extraction_id))
            .execute()
        )

        if response.data:
            logger.debug(f"[AUDIO_EMOTION] Status updated successfully")
        else:
            logger.warning(f"[AUDIO_EMOTION] No rows updated (extraction_id may not exist)")

    except Exception as e:
        logger.error(f"[AUDIO_EMOTION] Error updating audio emotion status: {e}", exc_info=True)
        raise Exception(f"Failed to update audio emotion extraction status: {str(e)}")


def get_preassembled_audio_prompt(template_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get pre-assembled audio emotion prompt and schema for a template.

    This is the fast path - retrieves pre-assembled prompts directly from templates table.
    Uses runtime cache with 1-year TTL (invalidation-based).

    Args:
        template_id: Template UUID

    Returns:
        Dict with assembled_audio_prompt, assembled_audio_schema_json, and hashes
        or None if not available/not pre-assembled
    """
    import time

    cache_key = str(template_id)
    current_time = time.time()

    # Check cache with TTL
    if cache_key in _audio_emotion_prompt_cache:
        cache_age = current_time - _audio_emotion_prompt_cache_time.get(cache_key, 0)
        if cache_age < AUDIO_EMOTION_PROMPT_CACHE_TTL:
            logger.debug(f"[AUDIO_PROMPT] Cache hit for template {template_id} (age: {cache_age:.1f}s)")
            return _audio_emotion_prompt_cache[cache_key]
        else:
            logger.debug(f"[AUDIO_PROMPT] Cache expired for template {template_id}")

    try:
        result = supabase.table("templates").select(
            "assembled_audio_prompt, assembled_audio_schema_json, "
            "audio_prompt_assembly_hash, audio_schema_assembly_hash"
        ).eq("id", str(template_id)).single().execute()

        if result.data and result.data.get("assembled_audio_prompt"):
            logger.debug(f"[AUDIO_PROMPT] Retrieved pre-assembled audio prompt for template {template_id}")
            # Cache the result
            _audio_emotion_prompt_cache[cache_key] = result.data
            _audio_emotion_prompt_cache_time[cache_key] = current_time
            return result.data

        return None

    except Exception as e:
        logger.warning(f"[AUDIO_PROMPT] Error retrieving pre-assembled audio prompt: {e}")
        return None


def get_audio_emotion_base_prompt_standalone_from_db() -> Optional[str]:
    """
    Fetch AUDIO_EMOTION_BASE_PROMPT_STANDALONE from database.

    Looks up the 'AUDIO_EMOTION_PROMPT_STANDALONE' configuration and retrieves the
    assembled prompt which contains the standalone base prompt component.

    Returns:
        Base prompt string if found, None otherwise
    """
    try:
        # Try to get the assembled prompt from the configuration
        config_result = supabase.table("system_prompt_configurations").select(
            "id, assembled_system_prompt"
        ).eq("config_code", "AUDIO_EMOTION_PROMPT_STANDALONE").eq("is_active", True).single().execute()

        if config_result.data and config_result.data.get("assembled_system_prompt"):
            logger.debug("[AUDIO_EMOTION_BASE] Retrieved standalone base prompt from AUDIO_EMOTION_PROMPT_STANDALONE configuration")
            return config_result.data["assembled_system_prompt"]

        # Fallback: Get directly from component if config not assembled
        component_result = supabase.table("system_prompt_components").select(
            "content_text"
        ).eq("component_code", "AUDIO_EMOTION_BASE_PROMPT_STANDALONE").eq("is_active", True).single().execute()

        if component_result.data and component_result.data.get("content_text"):
            logger.debug("[AUDIO_EMOTION_BASE] Retrieved standalone base prompt directly from AUDIO_EMOTION_BASE_PROMPT_STANDALONE component")
            return component_result.data["content_text"]

        return None

    except Exception as e:
        logger.warning(f"[AUDIO_EMOTION_BASE] Failed to retrieve standalone base prompt from database: {e}")
        return None


def get_audio_emotion_base_prompt_combined_from_db() -> Optional[str]:
    """
    Fetch AUDIO_EMOTION_BASE_PROMPT_COMBINED from database.

    Looks up the 'AUDIO_EMOTION_PROMPT_COMBINED' configuration and retrieves the
    assembled prompt which contains the combined base prompt component.

    Returns:
        Base prompt string if found, None otherwise
    """
    try:
        # Try to get the assembled prompt from the configuration
        config_result = supabase.table("system_prompt_configurations").select(
            "id, assembled_system_prompt"
        ).eq("config_code", "AUDIO_EMOTION_PROMPT_COMBINED").eq("is_active", True).single().execute()

        if config_result.data and config_result.data.get("assembled_system_prompt"):
            logger.debug("[AUDIO_EMOTION_BASE] Retrieved combined base prompt from AUDIO_EMOTION_PROMPT_COMBINED configuration")
            return config_result.data["assembled_system_prompt"]

        # Fallback: Get directly from component if config not assembled
        component_result = supabase.table("system_prompt_components").select(
            "content_text"
        ).eq("component_code", "AUDIO_EMOTION_BASE_PROMPT_COMBINED").eq("is_active", True).single().execute()

        if component_result.data and component_result.data.get("content_text"):
            logger.debug("[AUDIO_EMOTION_BASE] Retrieved combined base prompt directly from AUDIO_EMOTION_BASE_PROMPT_COMBINED component")
            return component_result.data["content_text"]

        return None

    except Exception as e:
        logger.warning(f"[AUDIO_EMOTION_BASE] Failed to retrieve combined base prompt from database: {e}")
        return None


def get_audio_emotion_prompt_with_fallback(template_id: uuid.UUID) -> Dict[str, Any]:
    """
    Get audio emotion prompt with 2-level fallback (STANDALONE mode).

    This is for post-transcription emotion analysis where we already have the transcript.

    Level 1: Pre-assembled segment guidelines + standalone base prompt from database
    Level 2: Dynamically assembled guidelines + standalone base prompt from database

    The base prompt is fetched from the AUDIO_EMOTION_PROMPT_STANDALONE configuration in database,
    with fallback to the AUDIO_EMOTION_BASE_PROMPT_STANDALONE component directly.

    Args:
        template_id: Template UUID

    Returns:
        Dict with:
            - system_prompt: The system prompt string
            - schema: types.Schema object ready for Gemini API
            - source: Where the prompt came from ("preassembled", "dynamic_assembly")

    Raises:
        ValueError: If both Level 1 and Level 2 fail to provide a prompt
    """
    # Import schema converter from segment_registry
    from services.segment_registry import _json_schema_to_gemini_schema

    # Get base prompt from database (config or component)
    base_prompt = get_audio_emotion_base_prompt_standalone_from_db()
    if not base_prompt:
        logger.error("[AUDIO_PROMPT] Failed to retrieve AUDIO_EMOTION_BASE_PROMPT_STANDALONE from database - check system_prompt_components table")
        raise ValueError("AUDIO_EMOTION_BASE_PROMPT_STANDALONE not found in database. Please ensure the migration has been applied.")

    # Level 1: Try pre-assembled prompt from templates table
    preassembled = get_preassembled_audio_prompt(template_id)
    if preassembled:
        logger.debug(f"[AUDIO_PROMPT] Level 1: Using pre-assembled audio prompt for template {template_id}")
        schema_json = preassembled.get("assembled_audio_schema_json", {})
        # Prepend standalone base prompt to segment guidelines
        full_prompt = base_prompt + preassembled["assembled_audio_prompt"]
        return {
            "system_prompt": full_prompt,
            "schema": _json_schema_to_gemini_schema(schema_json) if schema_json else None,
            "source": "preassembled"
        }

    # Level 2: Try dynamic assembly from segment_definitions
    try:
        from services.template_assembly_service import (
            assemble_template_audio_prompt,
            assemble_template_audio_schema
        )

        prompt_result = assemble_template_audio_prompt(template_id, "fallback_assembly")
        schema_result = assemble_template_audio_schema(template_id, "fallback_assembly")

        if not prompt_result.get("skipped") and prompt_result.get("assembled_audio_prompt"):
            logger.debug(f"[AUDIO_PROMPT] Level 2: Assembled audio prompt dynamically for template {template_id}")
            schema_json = schema_result.get("assembled_audio_schema_json", {})
            # Prepend standalone base prompt to segment guidelines
            full_prompt = base_prompt + prompt_result["assembled_audio_prompt"]
            return {
                "system_prompt": full_prompt,
                "schema": _json_schema_to_gemini_schema(schema_json) if schema_json else None,
                "source": "dynamic_assembly"
            }
    except Exception as e:
        logger.warning(f"[AUDIO_PROMPT] Level 2 assembly failed: {e}")

    # No hardcoded fallback - raise error if database lookup fails
    logger.error(f"[AUDIO_PROMPT] Failed to retrieve audio emotion prompt for template {template_id}")
    raise ValueError(f"Audio emotion prompt not found for template {template_id}. Please ensure the template has audio emotion segments configured.")


def get_audio_transcription_prompt_with_fallback(template_id: uuid.UUID) -> Dict[str, Any]:
    """
    Get combined transcription + audio emotion prompt with 2-level fallback (COMBINED mode).

    This is for the combined case where we transcribe AND extract emotions in one API call.
    Different from get_audio_emotion_prompt_with_fallback which is for standalone post-transcription analysis.

    Level 1: Pre-assembled segment guidelines + combined base prompt from database
    Level 2: Dynamically assembled guidelines + combined base prompt from database

    The base prompt is fetched from the AUDIO_EMOTION_PROMPT_COMBINED configuration in database,
    with fallback to the AUDIO_EMOTION_BASE_PROMPT_COMBINED component directly.

    Args:
        template_id: Template UUID

    Returns:
        Dict with:
            - system_prompt: Combined transcription + emotion system prompt
            - schema: types.Schema object ready for Gemini API
            - source: Where the prompt came from
    """
    # Import schema converter from segment_registry
    from services.segment_registry import _json_schema_to_gemini_schema

    # Get base prompt from database (config or component)
    base_prompt = get_audio_emotion_base_prompt_combined_from_db()
    if not base_prompt:
        logger.error("[AUDIO_TRANSCRIPTION_PROMPT] Failed to retrieve AUDIO_EMOTION_BASE_PROMPT_COMBINED from database - check system_prompt_components table")
        raise ValueError("AUDIO_EMOTION_BASE_PROMPT_COMBINED not found in database. Please ensure the migration has been applied.")

    def _build_combined_schema_json(base_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Build combined JSON schema with transcript field added."""
        return {
            "type": "object",
            "description": "Combined transcription and audio-based emotion analysis",
            "properties": {
                "transcript": {
                    "type": "string",
                    "description": "Complete transcription with speaker diarization (Counsellor:/Student:)"
                },
                **base_schema.get("properties", {})
            },
            "required": ["transcript"] + base_schema.get("required", [])
        }

    # Level 1: Try pre-assembled prompt from templates table
    preassembled = get_preassembled_audio_prompt(template_id)

    if preassembled:
        logger.debug(f"[AUDIO_TRANSCRIPTION_PROMPT] Level 1: Using pre-assembled audio prompt for template {template_id}")

        # Prepend combined base prompt to segment guidelines
        combined_prompt = base_prompt + preassembled["assembled_audio_prompt"]

        # Add transcript field to schema and convert to Gemini schema
        base_schema = preassembled.get("assembled_audio_schema_json", {})
        if base_schema and isinstance(base_schema, dict):
            combined_schema_json = _build_combined_schema_json(base_schema)
            gemini_schema = _json_schema_to_gemini_schema(combined_schema_json)
        else:
            gemini_schema = None

        return {
            "system_prompt": combined_prompt,
            "schema": gemini_schema,
            "source": "preassembled"
        }

    # Try Level 2: Dynamic assembly
    try:
        from services.template_assembly_service import (
            assemble_template_audio_prompt,
            assemble_template_audio_schema
        )

        prompt_result = assemble_template_audio_prompt(template_id, "fallback_assembly")
        schema_result = assemble_template_audio_schema(template_id, "fallback_assembly")

        if not prompt_result.get("skipped") and prompt_result.get("assembled_audio_prompt"):
            logger.debug(f"[AUDIO_TRANSCRIPTION_PROMPT] Level 2: Assembled audio prompt dynamically for template {template_id}")

            # Prepend combined base prompt to segment guidelines
            combined_prompt = base_prompt + prompt_result["assembled_audio_prompt"]

            base_schema = schema_result.get("assembled_audio_schema_json", {})
            if base_schema and isinstance(base_schema, dict):
                combined_schema_json = _build_combined_schema_json(base_schema)
                gemini_schema = _json_schema_to_gemini_schema(combined_schema_json)
            else:
                gemini_schema = None

            return {
                "system_prompt": combined_prompt,
                "schema": gemini_schema,
                "source": "dynamic_assembly"
            }
    except Exception as e:
        logger.warning(f"[AUDIO_TRANSCRIPTION_PROMPT] Level 2 assembly failed: {e}")

    # No hardcoded fallback - raise error if database lookup fails
    logger.error(f"[AUDIO_TRANSCRIPTION_PROMPT] Failed to retrieve audio transcription prompt for template {template_id}")
    raise ValueError(f"Audio transcription prompt not found for template {template_id}. Please ensure the template has audio emotion segments configured.")


# ============================================================================
# Text Emotion Prompt Fallback Functions
# ============================================================================

def get_text_emotion_base_prompt_from_db() -> Optional[str]:
    """
    Fetch TEXT_EMOTION_BASE_PROMPT from database.

    Looks up the 'TEXT_EMOTION_PROMPT' configuration and retrieves the
    assembled prompt which contains the base prompt component.

    Returns:
        Base prompt string if found, None otherwise
    """
    try:
        # Try to get the assembled prompt from the configuration
        config_result = supabase.table("system_prompt_configurations").select(
            "id, assembled_system_prompt"
        ).eq("config_code", "TEXT_EMOTION_PROMPT").eq("is_active", True).single().execute()

        if config_result.data and config_result.data.get("assembled_system_prompt"):
            logger.debug("[TEXT_EMOTION_BASE] Retrieved base prompt from TEXT_EMOTION_PROMPT configuration")
            return config_result.data["assembled_system_prompt"]

        # Fallback: Get directly from component if config not assembled
        component_result = supabase.table("system_prompt_components").select(
            "content_text"
        ).eq("component_code", "TEXT_EMOTION_BASE_PROMPT").eq("is_active", True).single().execute()

        if component_result.data and component_result.data.get("content_text"):
            logger.debug("[TEXT_EMOTION_BASE] Retrieved base prompt directly from TEXT_EMOTION_BASE_PROMPT component")
            return component_result.data["content_text"]

        return None

    except Exception as e:
        logger.warning(f"[TEXT_EMOTION_BASE] Failed to retrieve base prompt from database: {e}")
        return None


def get_preassembled_text_emotion_prompt(template_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get pre-assembled text emotion prompt and schema for a template.

    This is the fast path - retrieves pre-assembled prompts directly from templates table.

    Args:
        template_id: Template UUID

    Returns:
        Dict with assembled_text_emotion_prompt, assembled_text_emotion_schema_json, and hashes
        or None if not available/not pre-assembled
    """
    try:
        result = supabase.table("templates").select(
            "assembled_text_emotion_prompt, assembled_text_emotion_schema_json, "
            "text_emotion_prompt_assembly_hash, text_emotion_schema_assembly_hash"
        ).eq("id", str(template_id)).single().execute()

        if result.data and result.data.get("assembled_text_emotion_prompt") and result.data.get("assembled_text_emotion_schema_json"):
            logger.debug(f"[TEXT_EMOTION_PROMPT] Retrieved pre-assembled text emotion prompt for template {template_id}")
            return result.data

        # Log why Level 1 failed
        if result.data:
            has_prompt = bool(result.data.get("assembled_text_emotion_prompt"))
            has_schema = bool(result.data.get("assembled_text_emotion_schema_json"))
            logger.debug(f"[TEXT_EMOTION_PROMPT] Level 1 incomplete for template {template_id}: prompt={has_prompt}, schema={has_schema}")

        return None

    except Exception as e:
        logger.warning(f"[TEXT_EMOTION_PROMPT] Error retrieving pre-assembled text emotion prompt: {e}")
        return None


def get_text_emotion_prompt_with_fallback(template_id: uuid.UUID) -> Dict[str, Any]:
    """
    Get text emotion prompt with 2-level fallback (database-driven only).

    Level 1: Pre-assembled segment guidelines + base prompt from database
    Level 2: Dynamically assembled guidelines + base prompt from database

    The base prompt is fetched from the TEXT_EMOTION_PROMPT configuration in database,
    with fallback to the TEXT_EMOTION_BASE_PROMPT component directly.

    Args:
        template_id: Template UUID

    Returns:
        Dict with:
            - system_prompt: The system prompt string
            - schema: types.Schema object ready for Gemini API
            - source: Where the prompt came from ("preassembled", "dynamic_assembly")

    Raises:
        ValueError: If both Level 1 and Level 2 fail to provide a prompt
    """
    # Import schema converter from segment_registry
    from services.segment_registry import _json_schema_to_gemini_schema

    # Get base prompt from database (config or component)
    base_prompt = get_text_emotion_base_prompt_from_db()
    if not base_prompt:
        logger.error("[TEXT_EMOTION_PROMPT] Failed to retrieve TEXT_EMOTION_BASE_PROMPT from database - check system_prompt_components table")
        raise ValueError("TEXT_EMOTION_BASE_PROMPT not found in database. Please ensure the migration has been applied.")

    # Level 1: Try pre-assembled prompt from templates table
    preassembled = get_preassembled_text_emotion_prompt(template_id)
    if preassembled:
        logger.debug(f"[TEXT_EMOTION_PROMPT] Level 1: Using pre-assembled text emotion prompt for template {template_id}")
        schema_json = preassembled.get("assembled_text_emotion_schema_json", {})
        # Prepend base prompt to segment guidelines
        full_prompt = base_prompt + preassembled["assembled_text_emotion_prompt"]
        return {
            "system_prompt": full_prompt,
            "schema": _json_schema_to_gemini_schema(schema_json) if schema_json else None,
            "source": "preassembled"
        }

    # Level 2: Try dynamic assembly from segment_definitions
    try:
        from services.template_assembly_service import (
            assemble_template_text_emotion_prompt,
            assemble_template_text_emotion_schema
        )

        prompt_result = assemble_template_text_emotion_prompt(template_id, "fallback_assembly")
        schema_result = assemble_template_text_emotion_schema(template_id, "fallback_assembly")

        if not prompt_result.get("skipped") and prompt_result.get("assembled_text_emotion_prompt"):
            logger.debug(f"[TEXT_EMOTION_PROMPT] Level 2: Assembled text emotion prompt dynamically for template {template_id}")
            schema_json = schema_result.get("assembled_text_emotion_schema_json", {})
            # Prepend base prompt to segment guidelines
            full_prompt = base_prompt + prompt_result["assembled_text_emotion_prompt"]
            return {
                "system_prompt": full_prompt,
                "schema": _json_schema_to_gemini_schema(schema_json) if schema_json else None,
                "source": "dynamic_assembly"
            }
    except Exception as e:
        logger.warning(f"[TEXT_EMOTION_PROMPT] Level 2 assembly failed: {e}")

    # No fallback - raise error if both levels fail
    error_msg = (
        f"Failed to get text emotion prompt for template {template_id}. "
        "Both Level 1 (pre-assembled) and Level 2 (dynamic assembly) failed. "
        "Ensure TEXT_EMOTION_* segments exist in segment_definitions and template has emotion analysis enabled."
    )
    logger.error(f"[TEXT_EMOTION_PROMPT] {error_msg}")
    raise ValueError(error_msg)


# =============================================================================
# COMBINED EMOTION PROMPT FUNCTIONS (Single Multimodal Call)
# =============================================================================

# Cache for combined emotion prompts with TTL
# Long TTL (1 year) since prompts only change when segments are updated
# Invalidation is triggered via on_combined_segment_updated() -> invalidate_combined_emotion_prompt_cache()
_combined_emotion_prompt_cache: Dict[str, Dict[str, Any]] = {}
_combined_emotion_prompt_cache_time: Dict[str, float] = {}
COMBINED_EMOTION_PROMPT_CACHE_TTL = 31536000  # 1 year (invalidation-based)


def invalidate_combined_emotion_prompt_cache(template_id: Optional[uuid.UUID] = None):
    """
    Invalidate combined emotion prompt cache.

    Call this when prompts or schemas are updated in:
    - system_prompt_components (COMBINED_EMOTION_BASE_PROMPT)
    - segment_definitions (COMBINED_* segments)
    - templates (assembled_combined_emotion_* columns)

    Args:
        template_id: If provided, invalidate only this template. Otherwise invalidate all.
    """
    global _combined_emotion_prompt_cache, _combined_emotion_prompt_cache_time

    if template_id:
        cache_key = str(template_id)
        if cache_key in _combined_emotion_prompt_cache:
            del _combined_emotion_prompt_cache[cache_key]
            del _combined_emotion_prompt_cache_time[cache_key]
            logger.debug(f"[COMBINED_EMOTION_PROMPT] Cache invalidated for template {template_id}")
    else:
        _combined_emotion_prompt_cache.clear()
        _combined_emotion_prompt_cache_time.clear()
        logger.debug("[COMBINED_EMOTION_PROMPT] Full cache invalidated")


def get_combined_emotion_prompt(template_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get combined (multimodal) emotion prompt from database.

    This is for the single-call combined emotion extraction that analyzes
    both transcript text AND audio in one Gemini call.

    Retrieval priority:
    1. Pre-assembled from templates.assembled_combined_emotion_prompt (fastest)
    2. Dynamic assembly from segment_definitions + system_prompt_components

    NO FALLBACK: If database retrieval fails, returns None and emotion analysis
    should be skipped gracefully.

    Args:
        template_id: Template UUID

    Returns:
        Dict with system_prompt, schema, source OR None if not available
    """
    import time
    from services.segment_registry import _json_schema_to_gemini_schema

    cache_key = str(template_id)
    current_time = time.time()

    # Check cache with TTL
    if cache_key in _combined_emotion_prompt_cache:
        cache_age = current_time - _combined_emotion_prompt_cache_time.get(cache_key, 0)
        if cache_age < COMBINED_EMOTION_PROMPT_CACHE_TTL:
            logger.debug(f"[COMBINED_EMOTION_PROMPT] Cache hit for template {template_id} (age: {cache_age:.1f}s)")
            return _combined_emotion_prompt_cache[cache_key]
        else:
            logger.debug(f"[COMBINED_EMOTION_PROMPT] Cache expired for template {template_id}")

    # Level 1: Try pre-assembled prompt from templates table
    try:
        result = supabase.table("templates").select(
            "assembled_combined_emotion_prompt",
            "assembled_combined_emotion_schema_json"
        ).eq("id", str(template_id)).single().execute()

        if result.data:
            prompt = result.data.get("assembled_combined_emotion_prompt")
            schema_json = result.data.get("assembled_combined_emotion_schema_json")
            if prompt and schema_json:
                logger.debug(f"[COMBINED_EMOTION_PROMPT] Using pre-assembled prompt for template {template_id}")
                prompt_data = {
                    "system_prompt": prompt,
                    "schema": _json_schema_to_gemini_schema(schema_json),
                    "source": "preassembled"
                }
                # Cache the result
                _combined_emotion_prompt_cache[cache_key] = prompt_data
                _combined_emotion_prompt_cache_time[cache_key] = current_time
                return prompt_data
    except Exception as e:
        logger.debug(f"[COMBINED_EMOTION_PROMPT] Pre-assembled not available: {e}")

    # Level 2: Dynamic assembly from system_prompt_components + segment_definitions
    try:
        # Get base prompt
        base_result = supabase.table("system_prompt_components").select(
            "content_text"
        ).eq("component_code", "COMBINED_EMOTION_BASE_PROMPT").eq("is_active", True).single().execute()

        if not base_result.data or not base_result.data.get("content_text"):
            logger.warning(f"[COMBINED_EMOTION_PROMPT] Base prompt not found in database")
            return None

        base_prompt = base_result.data["content_text"]

        # Get combined segment prompts and schemas
        segments_result = supabase.table("segment_definitions").select(
            "segment_code", "prompt_section_text", "schema_definition_json"
        ).like("segment_code", "COMBINED_%").eq("is_active", True).execute()

        if not segments_result.data:
            logger.warning(f"[COMBINED_EMOTION_PROMPT] No combined segments found in database")
            return None

        # Build combined prompt and schema
        segment_prompts = []
        combined_schema = {
            "type": "object",
            "required": [],
            "properties": {}
        }

        for seg in segments_result.data:
            segment_code = seg.get("segment_code")
            prompt_text = seg.get("prompt_section_text")
            schema_def = seg.get("schema_definition_json")

            if prompt_text:
                segment_prompts.append(prompt_text)

            if schema_def and segment_code:
                combined_schema["properties"][segment_code] = schema_def
                combined_schema["required"].append(segment_code)

        # Assemble final prompt
        full_prompt = base_prompt + "\n\n## Segment-Specific Instructions\n\n" + "\n\n".join(segment_prompts)

        logger.debug(f"[COMBINED_EMOTION_PROMPT] Dynamically assembled prompt with {len(segment_prompts)} segments")

        prompt_data = {
            "system_prompt": full_prompt,
            "schema": _json_schema_to_gemini_schema(combined_schema),
            "source": "dynamic_assembly"
        }

        # Cache the result
        _combined_emotion_prompt_cache[cache_key] = prompt_data
        _combined_emotion_prompt_cache_time[cache_key] = current_time
        return prompt_data

    except Exception as e:
        logger.error(f"[COMBINED_EMOTION_PROMPT] Database lookup failed: {e}")
        return None


def is_emotion_analysis_enabled(consultation_type_id: uuid.UUID) -> bool:
    """
    Check if emotion analysis is enabled for a consultation type.

    This replaces the complex mode checks (text_only, audio_only, both)
    with a simple boolean check.

    Args:
        consultation_type_id: UUID of the consultation type

    Returns:
        True if emotion analysis is enabled, False otherwise
    """
    try:
        ct = get_consultation_type_by_id_cached(consultation_type_id)
        if ct:
            return ct.get("enable_emotion_analysis", False)
        return False
    except Exception as e:
        logger.warning(f"[EMOTION_CONFIG] Failed to check emotion status: {e}")
        return False


# =============================================================================
# TRANSCRIPTION PROMPT FUNCTIONS (Database-Driven)
# =============================================================================

def get_transcription_base_prompt_from_db() -> Optional[str]:
    """
    Fetch TRANSCRIPTION_BASE_PROMPT from database.

    Looks up the 'TRANSCRIPTION_ONLY_PROMPT' configuration and retrieves the
    assembled prompt which contains the transcription base prompt component.

    Returns:
        Base prompt string if found, None otherwise
    """
    try:
        # Try to get the assembled prompt from the configuration
        config_result = supabase.table("system_prompt_configurations").select(
            "id, assembled_system_prompt"
        ).eq("config_code", "TRANSCRIPTION_ONLY_PROMPT").eq("is_active", True).single().execute()

        if config_result.data and config_result.data.get("assembled_system_prompt"):
            logger.debug("[TRANSCRIPTION_BASE] Retrieved base prompt from TRANSCRIPTION_ONLY_PROMPT configuration")
            return config_result.data["assembled_system_prompt"]

        # Fallback: Get directly from component if config not assembled
        component_result = supabase.table("system_prompt_components").select(
            "content_text"
        ).eq("component_code", "TRANSCRIPTION_BASE_PROMPT").eq("is_active", True).single().execute()

        if component_result.data and component_result.data.get("content_text"):
            logger.debug("[TRANSCRIPTION_BASE] Retrieved base prompt directly from TRANSCRIPTION_BASE_PROMPT component")
            return component_result.data["content_text"]

        return None

    except Exception as e:
        logger.warning(f"[TRANSCRIPTION_BASE] Failed to retrieve base prompt from database: {e}")
        return None


def get_transcription_prompt_with_fallback() -> Dict[str, Any]:
    """
    Get transcription system prompt with 2-level database fallback.

    Level 1: Assembled prompt from TRANSCRIPTION_ONLY_PROMPT configuration
    Level 2: Direct content from TRANSCRIPTION_BASE_PROMPT component

    Returns:
        Dict with:
            - system_prompt: The system prompt string
            - source: Where the prompt came from ("config", "component")

    Raises:
        ValueError: If prompt not found in database
    """
    # Get base prompt from database (config or component)
    base_prompt = get_transcription_base_prompt_from_db()
    if not base_prompt:
        logger.error("[TRANSCRIPTION_PROMPT] Failed to retrieve TRANSCRIPTION_BASE_PROMPT from database")
        raise ValueError("TRANSCRIPTION_BASE_PROMPT not found in database. Please ensure the migration has been applied.")

    # Determine source based on which level succeeded
    # (get_transcription_base_prompt_from_db logs which level was used)
    return {
        "system_prompt": base_prompt,
        "source": "database"
    }


def save_congruence_analysis(
    extraction_id: uuid.UUID,
    congruence_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Save emotion congruence analysis segment to extraction_segments table.

    Args:
        extraction_id: UUID of extraction to link to
        congruence_data: Dict with congruence analysis results

    Returns:
        Saved segment record

    Raises:
        Exception: If save fails
    """
    logger.debug(f"[CONGRUENCE] Saving congruence analysis for extraction_id={extraction_id}")

    try:
        record = {
            "extraction_id": str(extraction_id),
            "segment_code": "CONGRUENCE_SUMMARY",
            "segment_value": congruence_data,
            "brevity_level": "balanced",
            "terminology_style": "medical_terms",
        }

        response = supabase.table("extraction_segments").insert(record).execute()

        if response.data:
            logger.debug(f"[CONGRUENCE] Successfully saved congruence analysis")
            return response.data[0]
        else:
            logger.warning(f"[CONGRUENCE] No data returned after insert")
            return {}

    except Exception as e:
        logger.error(f"[CONGRUENCE] Error saving congruence analysis: {e}", exc_info=True)
        raise Exception(f"Failed to save congruence analysis: {str(e)}")


def update_congruence_analysis_status(
    extraction_id: uuid.UUID,
    started: bool = False,
    completed: bool = False,
    failed: bool = False,
    error: Optional[str] = None
) -> None:
    """
    Update congruence analysis status flags in extractions table.

    Args:
        extraction_id: UUID of extraction
        started: Set congruence_analysis_started=True
        completed: Set congruence_analysis_completed=True
        failed: Set congruence_analysis_failed=True
        error: Error message to store (optional)

    Raises:
        Exception: If update fails
    """
    logger.debug(f"[CONGRUENCE] Updating status for extraction_id={extraction_id}")

    try:
        update_data = {}

        if started:
            update_data["congruence_analysis_started"] = True
            update_data["congruence_analysis_started_at"] = datetime.now(timezone.utc).isoformat()

        if completed:
            update_data["congruence_analysis_completed"] = True
            update_data["congruence_analysis_completed_at"] = datetime.now(timezone.utc).isoformat()

        if failed:
            update_data["congruence_analysis_failed"] = True
            if error:
                update_data["congruence_analysis_error"] = error

        if not update_data:
            return

        response = (
            supabase.table("extractions")
            .update(update_data)
            .eq("id", str(extraction_id))
            .execute()
        )

        if response.data:
            logger.debug(f"[CONGRUENCE] Status updated successfully")

    except Exception as e:
        logger.error(f"[CONGRUENCE] Error updating congruence status: {e}", exc_info=True)
        raise Exception(f"Failed to update congruence analysis status: {str(e)}")


def save_intervention_recommendations(
    extraction_id: uuid.UUID,
    interventions_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Save recommended interventions using the database RPC function.

    The interventions are saved to the student_interventions table via
    the save_student_interventions RPC function which handles:
    - Deleting existing interventions for this extraction
    - Linking to intervention_definitions
    - Ranking and marking top 3 recommendations

    Args:
        extraction_id: UUID of extraction to link to
        interventions_data: Dict with:
            - interventions: List of intervention objects with code, priority, etc.
            - total_triggered: Count of interventions
            - analysis_mode: 'text_only', 'audio_only', or 'combined'

    Returns:
        Result from RPC with success status and counts

    Raises:
        Exception: If save fails
    """
    logger.info(f"[INTERVENTIONS] Saving interventions for extraction_id={extraction_id}")

    try:
        # Priority: all_interventions (full list) > interventions > top_interventions (top 3 only)
        # all_interventions contains full details for ALL triggered interventions
        interventions = (
            interventions_data.get("all_interventions") or
            interventions_data.get("interventions") or
            interventions_data.get("top_interventions", [])
        )
        analysis_mode = interventions_data.get("analysis_mode", "combined")

        if not interventions:
            logger.info(f"[INTERVENTIONS] No interventions to save")
            return {"success": True, "interventions_saved": 0}

        # Prepare interventions with analysis_mode for RPC
        interventions_for_rpc = []
        for intervention in interventions:
            interventions_for_rpc.append({
                "code": intervention.get("code"),
                "priority": intervention.get("priority"),
                "priority_score": intervention.get("priority_score", 50),
                "trigger_reason": intervention.get("trigger_reason", ""),
                "analysis_mode": analysis_mode,
                "rationale_sources": intervention.get("rationale_sources", [])
            })

        # Call the RPC function to save interventions
        response = supabase.rpc(
            "save_student_interventions",
            {
                "p_extraction_id": str(extraction_id),
                "p_interventions": interventions_for_rpc
            }
        ).execute()

        if response.data:
            result = response.data
            logger.info(
                f"[INTERVENTIONS] Successfully saved {result.get('interventions_saved', 0)} interventions "
                f"(top 3: {result.get('top_3_count', 0)})"
            )
            return result
        else:
            logger.warning(f"[INTERVENTIONS] No data returned from RPC")
            return {"success": False, "error": "No response from database"}

    except Exception as e:
        logger.error(f"[INTERVENTIONS] Error saving interventions: {e}", exc_info=True)
        raise Exception(f"Failed to save intervention recommendations: {str(e)}")


def get_student_by_id(student_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get student record by ID including add_info for neonatal overrides.

    Args:
        student_id: UUID of the student

    Returns:
        Student record with id, student_id (UHID), full_name, add_info
        None if student not found
    """
    try:
        response = (
            supabase.table("students")
            .select("id, student_id, full_name, add_info")
            .eq("id", str(student_id))
            .single()
            .execute()
        )
        return response.data if response.data else None
    except Exception as e:
        logger.error(f"[STUDENT] Error fetching student {student_id}: {e}")
        return None


def update_student_preferred_language(student_id: str, language: str) -> bool:
    """Update the preferred_language column for a student. Synchronous (run via asyncio.to_thread)."""
    try:
        supabase.table("students").update(
            {"preferred_language": language}
        ).eq("id", student_id).execute()
        logger.info(f"[LANGUAGE] Updated preferred_language='{language}' for student {student_id}")
        return True
    except Exception as e:
        logger.warning(f"[LANGUAGE] Failed to update preferred_language for student {student_id}: {e}")
        return False


def get_student_interventions(extraction_id: uuid.UUID) -> List[Dict[str, Any]]:
    """
    Get student interventions for an extraction.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        List of intervention objects with:
            - code: Intervention code (e.g., "URGENT_MENTAL_HEALTH")
            - name: Human-readable name
            - description: Detailed description
            - priority: Priority level (critical, high, medium, low)
            - priority_score: Numeric score (0-100)
            - trigger_reason: Why this intervention was triggered
            - is_top_3: Whether this is in the top 3 recommendations
            - analysis_mode: 'text_only', 'audio_only', or 'combined'
            - rationale_sources: Supporting evidence from segments
    """
    logger.debug(f"[INTERVENTIONS] Getting interventions for extraction_id={extraction_id}")

    try:
        # Query student_interventions with join to intervention_definitions
        # Note: Column names in student_interventions table:
        #   - priority_level (not priority)
        #   - is_top_recommendation (not is_top_3)
        # Column names in intervention_definitions table:
        #   - intervention_code (not code)
        #   - intervention_name (not name)
        #   - priority_level (not default_priority)
        response = (
            supabase.table("student_interventions")
            .select(
                "id, intervention_code, priority_level, priority_score, trigger_reason, "
                "is_top_recommendation, analysis_mode, rationale_sources, created_at, "
                "intervention_category, intervention_sub_type, action, revenue_estimate, "
                "intervention_definitions(intervention_code, intervention_name, description, category, priority_level)"
            )
            .eq("extraction_id", str(extraction_id))
            .order("priority_score", desc=True)
            .execute()
        )

        if not response.data:
            logger.debug(f"[INTERVENTIONS] No interventions found for extraction_id={extraction_id}")
            return []

        interventions = []
        for row in response.data:
            definition = row.get("intervention_definitions") or {}
            # Use intervention_category from row, fallback to definition.category
            category = row.get("intervention_category") or definition.get("category", "general")
            interventions.append({
                "id": row.get("id"),
                "code": row.get("intervention_code") or definition.get("intervention_code"),
                "name": definition.get("intervention_name", row.get("intervention_code", "").replace("_", " ").title()),
                "description": definition.get("description", ""),
                "category": category,
                "priority": row.get("priority_level") or definition.get("priority_level", "medium"),
                "priority_score": row.get("priority_score", 50),
                "trigger_reason": row.get("trigger_reason", ""),
                "is_top_3": row.get("is_top_recommendation", False),
                "analysis_mode": row.get("analysis_mode", "combined"),
                "rationale_sources": row.get("rationale_sources", []),
                "created_at": row.get("created_at"),
                # New fields for insights-based interventions
                "intervention_sub_type": row.get("intervention_sub_type"),
                "action": row.get("action"),
                "revenue_estimate": row.get("revenue_estimate"),
            })

        logger.debug(f"[INTERVENTIONS] Found {len(interventions)} interventions")
        return interventions

    except Exception as e:
        logger.error(f"[INTERVENTIONS] Error getting interventions: {e}", exc_info=True)
        return []


def get_extraction_emotion_status(extraction_id: uuid.UUID) -> Dict[str, Any]:
    """
    Get emotion extraction status flags for an extraction.

    Returns:
        Dict with text and audio emotion extraction status flags
    """
    try:
        response = (
            supabase.table("extractions")
            .select(
                "emotion_extraction_started, emotion_extraction_completed, emotion_extraction_failed, "
                "audio_emotion_extraction_started, audio_emotion_extraction_completed, audio_emotion_extraction_failed, "
                "congruence_analysis_started, congruence_analysis_completed, congruence_analysis_failed"
            )
            .eq("id", str(extraction_id))
            .single()
            .execute()
        )

        if response.data:
            return response.data
        else:
            return {}

    except Exception as e:
        logger.error(f"Error getting extraction emotion status: {e}")
        return {}


def update_extraction_timing(
    extraction_id: uuid.UUID,
    extraction_time_seconds: Optional[float] = None,
    total_processing_time_seconds: Optional[float] = None,
) -> None:
    """
    Update timing metrics in extractions table after extraction completes.

    This function is called AFTER extraction completes to update timing fields
    that were not available during the initial save_medical_extraction() call.

    Args:
        extraction_id: UUID of extraction
        extraction_time_seconds: Time spent on medical insights extraction (in seconds)
        total_processing_time_seconds: Total processing time from start to finish (in seconds)

    Raises:
        Exception: If update fails
    """
    logger.info(
        f"[TIMING_UPDATE] Updating timing for extraction_id={extraction_id} "
        f"(extraction_time={extraction_time_seconds}s, total_time={total_processing_time_seconds}s)"
    )

    try:
        update_data = {}

        if extraction_time_seconds is not None:
            update_data["extraction_time_seconds"] = extraction_time_seconds

        if total_processing_time_seconds is not None:
            update_data["total_processing_time_seconds"] = total_processing_time_seconds

        if not update_data:
            logger.warning(f"[TIMING_UPDATE] No timing updates to apply for extraction_id={extraction_id}")
            return

        # Update extractions record
        response = (
            supabase.table("extractions")
            .update(update_data)
            .eq("id", str(extraction_id))
            .execute()
        )

        if response.data:
            logger.info(f"[TIMING_UPDATE] ✅ Timing updated successfully")
        else:
            logger.warning(f"[TIMING_UPDATE] ⚠️  No rows updated (extraction_id may not exist)")

    except Exception as e:
        logger.error(f"[TIMING_UPDATE] ❌ Error updating timing: {e}", exc_info=True)
        raise Exception(f"Failed to update extraction timing: {str(e)}")


def get_consultation_type(consultation_type_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get consultation type by ID (alias for get_consultation_type_by_id).

    This is used by background_tasks.py for checking enable_emotion_analysis flag.

    Args:
        consultation_type_id: UUID of consultation type

    Returns:
        Dict with consultation type data including enable_emotion_analysis flag
    """
    return get_consultation_type_by_id(consultation_type_id)


def search_extractions(
    consultation_type_id: Optional[uuid.UUID] = None,
    counsellor_id: Optional[uuid.UUID] = None,
    student_id: Optional[uuid.UUID] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Search extractions with filters.

    Args:
        consultation_type_id: Filter by consultation type
        counsellor_id: Filter by counsellor/user
        student_id: Filter by student
        start_date: ISO date string (e.g., '2025-01-01')
        end_date: ISO date string
        limit: Maximum results (default: 50)

    Returns:
        List of extraction records with consultation type info
    """
    query = (
        supabase.table("extractions")
        .select("*, consultation_types(type_code, type_name)")
        .order("created_at", desc=True)
        .limit(limit)
    )

    if consultation_type_id:
        query = query.eq("consultation_type_id", str(consultation_type_id))
    if counsellor_id:
        query = query.eq("counsellor_id", str(counsellor_id))
    if student_id:
        query = query.eq("student_id", str(student_id))
    if start_date:
        query = query.gte("created_at", start_date)
    if end_date:
        query = query.lte("created_at", end_date)

    response = query.execute()
    return response.data if response.data else []


def search_segment_values(
    segment_code: str,
    search_text: str,
    consultation_type_id: Optional[uuid.UUID] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Full-text search across segment values.

    Args:
        segment_code: Segment to search (e.g., 'PRESCRIPTION')
        search_text: Search query (e.g., 'Amlodipine')
        consultation_type_id: Optional filter by consultation type
        limit: Maximum results

    Returns:
        List of matching segments with extraction info
    """
    # Use PostgreSQL full-text search
    query = (
        supabase.table("extraction_segments")
        .select("*, extractions(*, consultation_types(type_code, type_name))")
        .eq("segment_code", segment_code)
        .text_search("segment_value_text", search_text)
        .order("created_at", desc=True)
        .limit(limit)
    )

    if consultation_type_id:
        # Filter via join to extractions
        query = query.eq("extractions.consultation_type_id", str(consultation_type_id))

    response = query.execute()
    return response.data if response.data else []


# ============================================================================
# Consultation Type Segment Configuration (Admin)
# ============================================================================

def get_consultation_type_segments(
    consultation_type_code: str,
    include_excluded: bool = False
) -> List[Dict[str, Any]]:
    """
    Get all segment definitions for a consultation type.

    **JUNCTION TABLE ARCHITECTURE**: Returns segment definitions with per-consultation-type
    overrides from consultation_type_segments junction table. The junction table values
    (default_display_order, default_category, default_brevity_level, default_terminology_style)
    take precedence over master segment_definitions values.

    Args:
        consultation_type_code: Consultation type code (OP, DISCHARGE, RESPIRATORY)
        include_excluded: If True, include segments with default_category='excluded' (for admin UI)

    Returns:
        List of segment definitions with junction table overrides applied
    """
    # Get consultation type
    consultation_type = get_consultation_type_by_code(consultation_type_code)
    if not consultation_type:
        raise ValueError(f"Consultation type '{consultation_type_code}' not found")

    consultation_type_id = consultation_type["id"]

    # Get type-specific segments via junction table - include ALL junction fields
    junction_response = (
        supabase.table("consultation_type_segments")
        .select("segment_id, segment_code, default_display_order, default_category, default_brevity_level, default_terminology_style")
        .eq("consultation_type_id", consultation_type_id)
        .execute()
    )

    junction_data = junction_response.data or []
    segment_ids = [j['segment_id'] for j in junction_data]

    # Build junction lookup map for quick access to per-CT overrides
    junction_map = {j['segment_id']: j for j in junction_data}

    # Get full segment details for type-specific segments
    type_specific = []
    if segment_ids:
        type_specific = (
            supabase.table("segment_definitions")
            .select("*")
            .in_("id", segment_ids)
            .eq("is_active", True)
            .execute()
        ).data or []

    # NEW ARCHITECTURE: Merge junction table overrides with master segment data
    # Junction table values take precedence for per-consultation-type fields
    segment_map = {}
    for seg in type_specific:
        segment_id = seg["id"]
        junction_override = junction_map.get(segment_id, {})

        # Apply junction table overrides (per-consultation-type values)
        if junction_override:
            # Override display_order from junction table
            if junction_override.get("default_display_order") is not None:
                seg["display_order"] = junction_override["default_display_order"]
            # Override default_category from junction table
            if junction_override.get("default_category") is not None:
                seg["default_category"] = junction_override["default_category"]
            # Override brevity_level from junction table
            if junction_override.get("default_brevity_level") is not None:
                seg["default_brevity_level"] = junction_override["default_brevity_level"]
            # Override terminology_style from junction table
            if junction_override.get("default_terminology_style") is not None:
                seg["default_terminology_style"] = junction_override["default_terminology_style"]

        segment_map[seg["segment_code"]] = seg

    # Filter out excluded segments (unless include_excluded=True for admin UI)
    if include_excluded:
        result = list(segment_map.values())
        logger.debug(f"[SEGMENT_QUERY] Returning all segments including excluded for '{consultation_type_code}'")
    else:
        result = [
            seg for seg in segment_map.values()
            if seg["default_category"] != "excluded"
        ]
        logger.debug(f"[SEGMENT_QUERY] Returning only active segments (excluding excluded) for '{consultation_type_code}'")

    # Sort by display_order (now using junction table values)
    result.sort(key=lambda x: x.get("display_order", 999))

    logger.debug(f"[SEGMENT_QUERY] Total segments returned: {len(result)}")

    return result


def update_consultation_type_segment(
    consultation_type_code: str,
    segment_code: str,
    segment_name: Optional[str] = None,
    default_category: Optional[str] = None,
    display_order: Optional[int] = None,
    default_brevity_level: Optional[str] = None,
    default_terminology_style: Optional[str] = None,
    prompt_section_text: Optional[str] = None,
    schema_definition_json: Optional[Dict[str, Any]] = None,
    is_required: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Update a segment configuration for a specific consultation type.

    **JUNCTION TABLE ARCHITECTURE**:
    - Per-consultation-type fields (display_order, category, brevity, terminology)
      are updated in consultation_type_segments junction table.
    - Global segment fields (segment_name, prompt, schema, is_required)
      are updated in segment_definitions master table.

    Args:
        consultation_type_code: Consultation type code (used to find the specific segment)
        segment_code: Segment code to update
        segment_name: Optional new name (master table)
        default_category: Optional new category - per consultation type (junction table)
        display_order: Optional new display order - per consultation type (junction table)
        default_brevity_level: Optional new brevity level - per consultation type (junction table)
        default_terminology_style: Optional new terminology style - per consultation type (junction table)
        prompt_section_text: Optional new prompt text (master table)
        schema_definition_json: Optional new schema (master table)
        is_required: Optional new required flag (master table)

    Returns:
        Updated segment definition record with junction table overrides
    """
    logger.info(f"[SEGMENT_UPDATE] Updating segment '{segment_code}' for consultation_type '{consultation_type_code}'")
    if default_category:
        logger.info(f"[SEGMENT_UPDATE] Requested category change: {segment_code} → {default_category}")

    # Get consultation type to get its ID
    consultation_type = get_consultation_type_by_code(consultation_type_code)
    if not consultation_type:
        logger.error(f"[SEGMENT_UPDATE] Consultation type '{consultation_type_code}' not found")
        raise ValueError(f"Consultation type '{consultation_type_code}' not found")

    consultation_type_id = consultation_type["id"]
    logger.debug(f"[SEGMENT_UPDATE] Consultation type validated: {consultation_type['type_name']} (ID: {consultation_type_id})")

    # Look up segment_id via junction table (consultation_type_id + segment_code is unique)
    junction_response = (
        supabase.table("consultation_type_segments")
        .select("segment_id, default_category")
        .eq("consultation_type_id", consultation_type_id)
        .eq("segment_code", segment_code)
        .execute()
    )

    if not junction_response.data or len(junction_response.data) == 0:
        logger.error(f"[SEGMENT_UPDATE] Segment '{segment_code}' not found for consultation type '{consultation_type_code}'")
        raise ValueError(f"Segment '{segment_code}' not found for consultation type '{consultation_type_code}'")

    segment_id = junction_response.data[0]["segment_id"]
    current_junction_category = junction_response.data[0].get("default_category", "core")
    logger.debug(f"[SEGMENT_UPDATE] Found segment_id: {segment_id} via junction table")

    # Separate updates: junction table vs master table
    junction_update_data = {}  # Per-consultation-type fields
    master_update_data = {}    # Global segment definition fields

    # Per-consultation-type fields → junction table
    if default_category is not None:
        junction_update_data["default_category"] = default_category.lower()
    if display_order is not None:
        junction_update_data["default_display_order"] = display_order
    if default_brevity_level is not None:
        junction_update_data["default_brevity_level"] = default_brevity_level
    if default_terminology_style is not None:
        junction_update_data["default_terminology_style"] = default_terminology_style

    # Global segment definition fields → master table
    if segment_name is not None:
        master_update_data["segment_name"] = segment_name
    if prompt_section_text is not None:
        master_update_data["prompt_section_text"] = prompt_section_text
    if schema_definition_json is not None:
        master_update_data["schema_definition_json"] = schema_definition_json
    if is_required is not None:
        master_update_data["is_required"] = is_required

    if not junction_update_data and not master_update_data:
        logger.warning(f"[SEGMENT_UPDATE] No update data provided for segment '{segment_code}'")
        raise ValueError("No update data provided")

    logger.debug(f"[SEGMENT_UPDATE] Junction update data: {junction_update_data}")
    logger.debug(f"[SEGMENT_UPDATE] Master update data: {master_update_data}")

    # Get existing segment from master table by ID (unique) for validation
    existing_segment_response = (
        supabase.table("segment_definitions")
        .select("id, is_cloned_from_parent, diverged_from_parent, is_required, default_category")
        .eq("id", segment_id)
        .execute()
    )

    if not existing_segment_response.data or len(existing_segment_response.data) == 0:
        logger.error(f"[SEGMENT_UPDATE] Segment with ID '{segment_id}' not found in master table")
        raise ValueError(f"Segment '{segment_code}' not found")

    existing_segment = existing_segment_response.data[0]
    is_segment_required = existing_segment.get("is_required", False)

    logger.debug(f"[SEGMENT_UPDATE] Segment '{segment_code}' (ID: {segment_id}) current state: "
               f"is_required={is_segment_required}, junction_category={current_junction_category}")

    # VALIDATION: Check if trying to move a required segment from CORE
    if default_category is not None and is_segment_required:
        if current_junction_category == "core" and default_category.lower() != "core":
            logger.error(f"[SEGMENT_UPDATE] BLOCKED: Cannot move required segment '{segment_code}' from CORE to {default_category}")
            raise ValueError(
                f"Cannot move required segment '{segment_code}' from CORE category. "
                f"Required segments must remain in CORE for clinical safety."
            )
        logger.info(f"[SEGMENT_UPDATE] Required segment '{segment_code}' category change allowed: {current_junction_category} → {default_category}")

    updated_segment = None

    # Update junction table (per-consultation-type fields)
    if junction_update_data:
        logger.info(f"[SEGMENT_UPDATE] Updating junction table for segment '{segment_code}' in consultation type '{consultation_type_code}'")
        junction_update_response = (
            supabase.table("consultation_type_segments")
            .update(junction_update_data)
            .eq("consultation_type_id", consultation_type_id)
            .eq("segment_code", segment_code)
            .execute()
        )

        if not junction_update_response.data or len(junction_update_response.data) == 0:
            logger.error(f"[SEGMENT_UPDATE] Failed to update junction table for segment '{segment_code}'")
            raise ValueError(f"Failed to update segment configuration for '{segment_code}'")

        logger.info(f"[SEGMENT_UPDATE] ✓ Junction table updated for segment '{segment_code}'")
        if default_category:
            logger.info(f"[SEGMENT_UPDATE] ✓ Segment '{segment_code}' category changed to: {default_category} (for this consultation type only)")

    # Update master table (global segment definition fields)
    if master_update_data:
        # If this is a cloned segment that hasn't diverged yet
        if (existing_segment.get("is_cloned_from_parent", False) and
            not existing_segment.get("diverged_from_parent", False)):
            # Check if prompt or schema is being changed
            if prompt_section_text is not None or schema_definition_json is not None:
                logger.info(f"[SEGMENT_UPDATE] Marking cloned segment '{segment_code}' as diverged from parent")
                master_update_data["diverged_from_parent"] = True

        logger.info(f"[SEGMENT_UPDATE] Updating master segment '{segment_code}' (ID: {segment_id})")
        response = (
            supabase.table("segment_definitions")
            .update(master_update_data)
            .eq("id", segment_id)
            .execute()
        )

        if not response.data or len(response.data) == 0:
            logger.error(f"[SEGMENT_UPDATE] Failed to update master segment '{segment_code}'")
            raise ValueError(f"Failed to update segment '{segment_code}'")

        logger.info(f"[SEGMENT_UPDATE] ✓ Master table updated for segment '{segment_code}'")
        updated_segment = response.data[0]

    # Fetch the complete updated segment (master + junction data merged)
    final_response = (
        supabase.table("segment_definitions")
        .select("*")
        .eq("id", segment_id)
        .execute()
    )

    if final_response.data:
        updated_segment = final_response.data[0]

        # Merge junction table overrides into response
        junction_data = (
            supabase.table("consultation_type_segments")
            .select("default_category, default_display_order, default_brevity_level, default_terminology_style")
            .eq("consultation_type_id", consultation_type_id)
            .eq("segment_code", segment_code)
            .execute()
        )

        if junction_data.data:
            # Apply junction overrides (these are per-consultation-type values)
            jd = junction_data.data[0]
            updated_segment["default_category"] = jd.get("default_category", updated_segment.get("default_category"))
            updated_segment["display_order"] = jd.get("default_display_order", updated_segment.get("display_order"))
            updated_segment["default_brevity_level"] = jd.get("default_brevity_level", updated_segment.get("default_brevity_level"))
            updated_segment["default_terminology_style"] = jd.get("default_terminology_style", updated_segment.get("default_terminology_style"))

    logger.info(f"[SEGMENT_UPDATE] Successfully updated segment '{segment_code}' (ID: {segment_id})")

    # Ensure we always return a valid dict (fallback to existing_segment if needed)
    if updated_segment is None:
        updated_segment = existing_segment

    return updated_segment


def bulk_update_consultation_type_segments(
    consultation_type_code: str,
    segments: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Bulk update multiple segment definitions for a consultation type.

    Args:
        consultation_type_code: Consultation type code
        segments: List of segment updates, each with segment_code and fields to update

    Returns:
        List of updated segment records
    """
    results = []

    for segment in segments:
        segment_code = segment.get("segment_code")
        if not segment_code:
            continue

        result = update_consultation_type_segment(
            consultation_type_code=consultation_type_code,
            segment_code=segment_code,
            segment_name=segment.get("segment_name"),
            default_category=segment.get("category"),
            display_order=segment.get("display_order"),
            default_brevity_level=segment.get("brevity_level"),
            default_terminology_style=segment.get("terminology_style"),
            prompt_section_text=segment.get("prompt_section_text"),
            schema_definition_json=segment.get("schema_definition_json"),
            is_required=segment.get("is_required")
        )
        results.append(result)

    return results

def get_all_segments(
    consultation_type_code: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all segment definitions across all consultation types.

    **JUNCTION TABLE ARCHITECTURE**: All segments retrieved via consultation_type_segments junction table.

    Args:
        consultation_type_code: Filter by consultation type (optional)

    Returns:
        List of all segment definitions with consultation type info
    """
    segments = []

    # Get consultation type if filtering
    consultation_type = None
    if consultation_type_code:
        consultation_type = get_consultation_type_by_code(consultation_type_code)
        if not consultation_type:
            return []  # Consultation type not found

    if consultation_type_code and consultation_type:
        # Get segments for specific consultation type via junction table ONLY
        junction_response = (
            supabase.table("consultation_type_segments")
            .select("segment_id, segment_code, default_display_order")
            .eq("consultation_type_id", consultation_type['id'])
            .execute()
        )

        segment_ids = [j['segment_id'] for j in (junction_response.data or []) if j.get('segment_id')]

        if segment_ids:
            # Get full segment details (only active segments for junction table lookups)
            type_segments_response = (
                supabase.table("segment_definitions")
                .select("*")
                .in_("id", segment_ids)
                .eq("is_active", True)
                .order("display_order")
                .execute()
            )

            # Add consultation type info to each segment
            for segment in (type_segments_response.data or []):
                segment_with_type = {**segment}
                segment_with_type["consultation_type_code"] = consultation_type['type_code']
                segment_with_type["consultation_type_name"] = consultation_type['type_name']
                segments.append(segment_with_type)

    # If no specific consultation type requested, get all segments from all types and templates
    # Return unique segments with aggregated associations (including unassigned segments)
    elif not consultation_type_code:
        # OPTIMIZED: Get all data in 5 bulk queries instead of N+1 individual queries

        # 1. Get all consultation types (1 query)
        all_types = (
            supabase.table("consultation_types")
            .select("*")
            .eq("is_active", True)
            .execute()
        ).data or []

        # Create lookup map for consultation types
        ct_map = {ct['id']: ct for ct in all_types}

        # 2. Get ALL consultation type segment associations at once (1 query)
        all_ct_segments = (
            supabase.table("consultation_type_segments")
            .select("segment_id, consultation_type_id")
            .execute()
        ).data or []

        # 3. Get all templates (1 query)
        templates_response = (
            supabase.table("templates")
            .select("id, template_code, template_name, consultation_type_id")
            .eq("is_active", True)
            .execute()
        ).data or []

        # Create lookup map for templates
        template_map = {t['id']: t for t in templates_response}

        # 4. Get ALL template segment associations at once (1 query)
        all_template_segments = (
            supabase.table("template_segments")
            .select("segment_id, template_id")
            .execute()
        ).data or []

        # Build maps for segment associations in memory
        segment_consultations = {}  # segment_id -> list of consultation types
        segment_templates = {}  # segment_id -> list of templates

        # Process consultation type associations
        for cts in all_ct_segments:
            segment_id = cts.get('segment_id')
            ct_id = cts.get('consultation_type_id')
            if segment_id and ct_id and ct_id in ct_map:
                ct = ct_map[ct_id]
                if segment_id not in segment_consultations:
                    segment_consultations[segment_id] = []
                segment_consultations[segment_id].append({
                    'type': 'consultation_type',
                    'type_code': ct['type_code'],
                    'type_name': ct['type_name'],
                    'type_id': ct['id']
                })

        # Process template associations
        for ts in all_template_segments:
            segment_id = ts.get('segment_id')
            template_id = ts.get('template_id')
            if segment_id and template_id and template_id in template_map:
                template = template_map[template_id]
                if segment_id not in segment_templates:
                    segment_templates[segment_id] = []
                segment_templates[segment_id].append({
                    'type': 'template',
                    'template_code': template['template_code'],
                    'template_name': template['template_name'],
                    'template_id': template['id']
                })

        # Get ALL segments including inactive ones (display with badge)
        # This is important for cloning - you should be able to clone from any segment
        all_segments_response = (
            supabase.table("segment_definitions")
            .select("*")
            .order("display_order")
            .execute()
        )

        # Add aggregated association info to each segment
        for segment in (all_segments_response.data or []):
            segment_with_associations = {**segment}
            segment_id = segment['id']

            # Add arrays of associations (empty arrays for unassigned segments)
            consultation_types = segment_consultations.get(segment_id, [])
            templates = segment_templates.get(segment_id, [])

            segment_with_associations["consultation_types"] = consultation_types
            segment_with_associations["templates"] = templates

            # For backward compatibility, set first consultation type as primary (if exists)
            if consultation_types:
                segment_with_associations["consultation_type_code"] = consultation_types[0]['type_code']
                segment_with_associations["consultation_type_name"] = consultation_types[0]['type_name']

            segments.append(segment_with_associations)

    return segments


def create_segment_definition(
    segment_code: str,
    segment_name: str,
    consultation_type_code: Optional[str] = None,
    template_code: Optional[str] = None,
    prompt_section_text: str = "",
    schema_definition_json: Optional[Dict[str, Any]] = None,
    default_category: str = "core",
    display_order: int = 999,
    default_brevity_level: str = "balanced",
    default_terminology_style: str = "medical_terms",
    is_required: bool = False
) -> Dict[str, Any]:
    """
    Create a new segment definition in master table and link via junction tables.

    **JUNCTION TABLE ARCHITECTURE**: Segments created in segment_definitions (master),
    then linked to consultation types/templates via junction tables.

    Args:
        segment_code: Unique segment code (e.g., "DIAGNOSIS_OP")
        segment_name: Display name for the segment
        consultation_type_code: Consultation type code (OP, DISCHARGE, RESPIRATORY) - required unless template_code provided
        template_code: Template code for template-specific segments - optional
        prompt_section_text: Prompt text for extraction
        schema_definition_json: JSON schema definition
        default_category: core | additional (default: core)
        display_order: Display order (default: 999)
        default_brevity_level: concise | balanced | detailed (default: balanced)
        default_terminology_style: medical_terms | simple_terms | as_spoken (default: medical_terms)
        is_required: Whether this segment is required (default: False)

    Returns:
        Created segment definition

    Raises:
        ValueError: If consultation_type_code and template_code are both missing
    """
    consultation_type_id = None
    template_id = None

    # Determine assignment type and get IDs
    if template_code:
        # Template-specific segment
        template = get_template_by_code(template_code)
        if not template:
            raise ValueError(f"Template '{template_code}' not found")

        template_id = uuid.UUID(template["id"])

        # Get consultation_type from template
        template_consult_type_code = template.get("consultation_type_code")
        if template_consult_type_code:
            consultation_type = get_consultation_type_by_code(template_consult_type_code)
            if consultation_type:
                consultation_type_id = uuid.UUID(consultation_type["id"])
    elif consultation_type_code:
        # Consultation type-specific segment
        consultation_type = get_consultation_type_by_code(consultation_type_code)
        if not consultation_type:
            raise ValueError(f"Consultation type '{consultation_type_code}' not found")
        consultation_type_id = uuid.UUID(consultation_type["id"])
    else:
        # No consultation type or template provided - invalid in new architecture
        raise ValueError("Must provide either consultation_type_code or template_code")

    # Validate junction table uniqueness BEFORE creating the segment
    # Check 1: Ensure no existing (segment_code, consultation_type_id) in consultation_type_segments
    if consultation_type_id:
        existing_ct_segment = (
            supabase.table("consultation_type_segments")
            .select("id, segment_code")
            .eq("segment_code", segment_code)
            .eq("consultation_type_id", str(consultation_type_id))
            .execute()
        )
        if existing_ct_segment.data and len(existing_ct_segment.data) > 0:
            # Get consultation type name for better error message
            ct_name = consultation_type_code or "unknown"
            raise ValueError(
                f"Segment '{segment_code}' is already assigned to consultation type '{ct_name}'. "
                f"Use a different segment code or edit the existing segment."
            )

    # Check 2: Ensure no existing (segment_code, template_id) in template_segments
    if template_id:
        existing_tpl_segment = (
            supabase.table("template_segments")
            .select("id, segment_code")
            .eq("segment_code", segment_code)
            .eq("template_id", str(template_id))
            .execute()
        )
        if existing_tpl_segment.data and len(existing_tpl_segment.data) > 0:
            raise ValueError(
                f"Segment '{segment_code}' is already assigned to template '{template_code}'. "
                f"Use a different segment code or edit the existing segment."
            )

    # Create new segment in master table
    # Note: segment_code is NOT unique in segment_definitions - same code can exist for different consultation types/templates
    # The unique identifier is the 'id' column
    # Junction tables enforce uniqueness: (segment_code, consultation_type_id) and (segment_code, template_id)
    new_segment = {
        "segment_code": segment_code,
        "segment_name": segment_name,
        "prompt_section_text": prompt_section_text,
        "schema_definition_json": schema_definition_json or {},
        "default_category": default_category,
        "display_order": display_order,
        "default_brevity_level": default_brevity_level,
        "default_terminology_style": default_terminology_style,
        "is_required": is_required,
        "is_active": True
    }

    response = supabase.table("segment_definitions").insert(new_segment).execute()

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to create segment definition")

    created_segment = response.data[0]
    segment_id = created_segment["id"]

    # Link segment to consultation type via junction table (always, if consultation_type_id exists)
    if consultation_type_id:
        junction_data = {
            "consultation_type_id": str(consultation_type_id),
            "consultation_type_name": consultation_type.get("type_name") if consultation_type else None,
            "segment_id": segment_id,
            "segment_code": segment_code,
            "default_display_order": display_order,
            "default_category": default_category.lower()
        }
        supabase.table("consultation_type_segments").insert(junction_data).execute()
        consult_type_name = consultation_type.get("type_name") if consultation_type else "Unknown"
        logger.info(f"Linked segment '{segment_code}' to consultation type '{consult_type_name}' via junction table")

        # If segment was inactive, activate it now that it's assigned
        if not created_segment.get("is_active", True):
            supabase.table("segment_definitions").update({"is_active": True}).eq("id", segment_id).execute()
            created_segment["is_active"] = True
            logger.info(f"Activated segment '{segment_code}' (was inactive before assignment)")

    # Link segment to template via junction table (if applicable)
    if template_id:
        template_junction_data = {
            "template_id": str(template_id),
            "template_name": template.get("template_name") if template else None,
            "segment_id": segment_id,
            "segment_code": segment_code,
            "category": default_category,
            "display_order": display_order,
            "brevity_level": default_brevity_level,
            "terminology_style": default_terminology_style
        }
        supabase.table("template_segments").insert(template_junction_data).execute()
        logger.info(f"Linked segment '{segment_code}' to template '{template.get('template_name')}' via junction table")

        # If segment was inactive, activate it now that it's assigned
        if not created_segment.get("is_active", True):
            supabase.table("segment_definitions").update({"is_active": True}).eq("id", segment_id).execute()
            created_segment["is_active"] = True
            logger.info(f"Activated segment '{segment_code}' (was inactive before assignment)")

        # HOOK: Trigger reassembly for this template
        try:
            from .template_assembly_service import trigger_reassembly_async
            trigger_source = f"template_segment:{template_id}:{segment_code}:add"
            asyncio.create_task(trigger_reassembly_async([template_id], trigger_source))
            logger.info(f"[CREATE_SEGMENT] Triggered reassembly for template {template_id}")
        except Exception as e:
            logger.error(f"[CREATE_SEGMENT] Failed to trigger reassembly hook: {e}")

    return created_segment


def update_segment_definition(
    segment_id: str,
    segment_name: Optional[str] = None,
    prompt_section_text: Optional[str] = None,
    schema_definition_json: Optional[Dict[str, Any]] = None,
    default_category: Optional[str] = None,
    display_order: Optional[int] = None,
    default_brevity_level: Optional[str] = None,
    default_terminology_style: Optional[str] = None,
    is_required: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Update a segment definition in the master table.

    **JUNCTION TABLE ARCHITECTURE**: Updates master segment_definitions table only.

    Args:
        segment_id: Segment UUID to update (unique identifier)
        segment_name: New segment name (optional)
        prompt_section_text: New prompt text (optional)
        schema_definition_json: New schema (optional)
        default_category: New category (optional)
        display_order: New display order (optional)
        default_brevity_level: New brevity level (optional)
        default_terminology_style: New terminology style (optional)
        is_required: New required flag (optional)

    Returns:
        Updated segment definition
    """
    # Get current segment by ID (unique)
    current = (
        supabase.table("segment_definitions")
        .select("*")
        .eq("id", segment_id)
        .execute()
    )
    if not current.data or len(current.data) == 0:
        raise ValueError(f"Segment with ID '{segment_id}' not found")

    # Build update object with only provided fields
    updates = {}
    if segment_name is not None:
        updates["segment_name"] = segment_name
    if prompt_section_text is not None:
        updates["prompt_section_text"] = prompt_section_text
    if schema_definition_json is not None:
        updates["schema_definition_json"] = schema_definition_json
    if default_category is not None:
        updates["default_category"] = default_category
    if display_order is not None:
        updates["display_order"] = display_order
    if default_brevity_level is not None:
        updates["default_brevity_level"] = default_brevity_level
    if default_terminology_style is not None:
        updates["default_terminology_style"] = default_terminology_style
    if is_required is not None:
        updates["is_required"] = is_required

    if not updates:
        return current.data[0]  # No updates to make

    # Update segment by ID (unique)
    response = (
        supabase.table("segment_definitions")
        .update(updates)
        .eq("id", segment_id)
        .execute()
    )

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to update segment definition")

    # HOOK: Trigger reassembly for all templates using this segment
    try:
        from .template_assembly_service import trigger_reassembly_async, get_templates_using_segment
        affected_templates = get_templates_using_segment(uuid.UUID(segment_id))
        if affected_templates:
            segment_code = response.data[0].get('segment_code', 'unknown')
            trigger_source = f"segment_definition:{segment_code}:update"
            asyncio.create_task(trigger_reassembly_async(affected_templates, trigger_source))
            logger.info(f"[UPDATE_SEGMENT] Triggered reassembly for {len(affected_templates)} templates")
    except Exception as e:
        logger.error(f"[UPDATE_SEGMENT] Failed to trigger reassembly hook: {e}")

    return response.data[0]


# ============================================================================
# Template Helper Functions
# ============================================================================

# Internal fields that should NOT be returned to clients in API responses
TEMPLATE_INTERNAL_FIELDS = {
    "assembled_full_prompt",
    "assembled_schema_json",
    "prompt_assembly_hash",
    "schema_assembly_hash",
    "prompt_assembled_at",
    "schema_assembled_at"
}


def strip_internal_template_fields(template: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Remove internal fields from a template before returning to client.

    Fields removed:
    - assembled_full_prompt: Large pre-assembled system prompt
    - assembled_schema_json: Large pre-assembled JSON schema
    - prompt_assembly_hash: Internal hash for cache invalidation
    - schema_assembly_hash: Internal hash for cache invalidation
    - prompt_assembled_at: Internal timestamp
    - schema_assembled_at: Internal timestamp

    Args:
        template: Template dict (or None)

    Returns:
        Template dict with internal fields removed (or None if input was None)
    """
    if template is None:
        return None

    return {k: v for k, v in template.items() if k not in TEMPLATE_INTERNAL_FIELDS}


def get_template_by_code(template_code: str) -> Optional[Dict[str, Any]]:
    """
    Get a template by its template_code.

    Args:
        template_code: Template code to look up

    Returns:
        Template record or None if not found
    """
    response = (
        supabase.table("templates")
        .select("*, consultation_types(type_code)")
        .eq("template_code", template_code)
        .execute()
    )

    if not response.data or len(response.data) == 0:
        return None

    template = response.data[0]
    # Add consultation_type_code to top level for easy access
    if template.get("consultation_types"):
        template["consultation_type_code"] = template["consultation_types"]["type_code"]

    return template


def get_template_assembled_data(template_code: str) -> Optional[Dict[str, Any]]:
    """
    Get pre-assembled prompt and schema for a template.

    Used for direct audio extraction (skip_transcription mode) where we need
    the assembled prompts without the transcript substitution.

    Args:
        template_code: Template code to look up

    Returns:
        Dict with 'assembled_full_prompt' and 'assembled_schema_json' or None if not found
    """
    response = (
        supabase.table("templates")
        .select("assembled_full_prompt, assembled_schema_json")
        .eq("template_code", template_code)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    if not response.data or len(response.data) == 0:
        logger.warning(f"[TEMPLATE] No active template found for code: {template_code}")
        return None

    template_data = response.data[0]

    # Validate required fields
    if not template_data.get("assembled_full_prompt") or not template_data.get("assembled_schema_json"):
        logger.warning(
            f"[TEMPLATE] Template {template_code} missing assembled data: "
            f"prompt={bool(template_data.get('assembled_full_prompt'))}, "
            f"schema={bool(template_data.get('assembled_schema_json'))}"
        )
        return None

    return template_data


# ============================================================================
# Segment Approval Workflow Functions
# ============================================================================

def create_segment_request(
    segment_code: str,
    segment_name: str,
    consultation_type_code: str,
    prompt_section_text: str,
    default_category: str,
    display_order: int,
    default_brevity_level: str,
    default_terminology_style: str,
    counsellor_id: uuid.UUID,
    template_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Create a segment request (Counsellor - No Schema Required).

    Creates a segment with status='pending_approval' that awaits admin review.
    The segment does NOT require a schema_definition_json initially.

    Args:
        segment_code: Auto-generated unique code
        segment_name: Display name
        consultation_type_code: Consultation type code
        prompt_section_text: Description of what to extract
        default_category: core or additional
        display_order: Display order in UI
        default_brevity_level: concise/balanced/detailed
        default_terminology_style: medical_terms/simple_terms/as_spoken
        counsellor_id: Counsellor UUID creating the request
        template_id: Template UUID (optional) - links segment to requesting template

    Returns:
        Created segment record with status='pending_approval'

    Note:
        Migration 20251123000200 removed created_by_counsellor_id, now using counsellor_id column.
    """
    # Check if segment_code already exists
    existing = (
        supabase.table("segment_definitions")
        .select("segment_code")
        .eq("segment_code", segment_code)
        .execute()
    )
    if existing.data and len(existing.data) > 0:
        raise ValueError(f"Segment code '{segment_code}' already exists")

    # Get consultation type ID
    consultation_type = (
        supabase.table("consultation_types")
        .select("id")
        .eq("type_code", consultation_type_code)
        .execute()
    )
    if not consultation_type.data or len(consultation_type.data) == 0:
        raise ValueError(f"Consultation type '{consultation_type_code}' not found")

    consultation_type_id = consultation_type.data[0]["id"]

    # Create segment with pending status and empty schema
    data = {
        "segment_code": segment_code,
        "segment_name": segment_name,
        "consultation_type_id": str(consultation_type_id),
        "prompt_section_text": prompt_section_text,
        "schema_definition_json": {},  # Empty placeholder
        "default_category": default_category,
        "display_order": display_order,
        "default_brevity_level": default_brevity_level,
        "default_terminology_style": default_terminology_style,
        "status": "pending_approval",  # Pending admin review
        "counsellor_id": str(counsellor_id),  # Track requester (changed from created_by_counsellor_id)
        "template_id": str(template_id) if template_id else None,  # Link to template
        "is_required": False,
        "is_active": False  # Inactive until admin approves and activates
    }

    response = supabase.table("segment_definitions").insert(data).execute()

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to create segment request")

    return response.data[0]


def get_pending_segments() -> List[Dict[str, Any]]:
    """
    Get all segment requests with status='pending_approval'.

    Returns:
        List of pending segment records with counsellor information

    Note:
        Migration 20251123000200 removed created_by_counsellor_id, now using counsellor_id column.
    """
    response = (
        supabase.table("segment_definitions")
        .select("*, consultation_types(type_code, type_name), counsellor_id(full_name, email)")
        .eq("status", "pending_approval")
        .order("created_at", desc=True)
        .execute()
    )

    segments = []
    for segment in response.data:
        # Flatten nested objects
        segment_data = dict(segment)
        if segment.get("consultation_types"):
            segment_data["consultation_type_code"] = segment["consultation_types"]["type_code"]
            segment_data["consultation_type_name"] = segment["consultation_types"]["type_name"]
        if segment.get("counsellor_id"):
            segment_data["requester_name"] = segment["counsellor_id"]["full_name"]
            segment_data["requester_email"] = segment["counsellor_id"]["email"]
        segments.append(segment_data)

    return segments


def approve_segment_request(
    segment_id: str,
    schema_definition_json: Dict[str, Any],
    approved_by_admin_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Approve a pending segment request by adding schema and activating.

    Args:
        segment_id: Segment UUID to approve (unique identifier)
        schema_definition_json: JSON schema for extraction
        approved_by_admin_id: Admin UUID approving the segment

    Returns:
        Updated segment record with status='active'
    """
    # Get current segment by ID (unique)
    current = (
        supabase.table("segment_definitions")
        .select("*")
        .eq("id", segment_id)
        .execute()
    )
    if not current.data or len(current.data) == 0:
        raise ValueError(f"Segment with ID '{segment_id}' not found")

    segment = current.data[0]
    segment_code = segment.get("segment_code", segment_id)

    # Validate status
    if segment.get("status") != "pending_approval":
        raise ValueError(f"Segment '{segment_code}' is not pending approval (status: {segment.get('status')})")

    # Update segment with schema and approval details
    from datetime import datetime, timezone

    updates = {
        "schema_definition_json": schema_definition_json,
        "status": "active",
        "approved_by_admin_id": str(approved_by_admin_id),
        "approved_at": datetime.now(timezone.utc).isoformat()
    }

    response = (
        supabase.table("segment_definitions")
        .update(updates)
        .eq("id", segment_id)
        .execute()
    )

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to approve segment request")

    return response.data[0]


def add_segment_to_template(
    template_id: uuid.UUID,
    segment_id: uuid.UUID,
    segment_code: str,
    category: str,
    display_order: int,
    brevity_level: str,
    terminology_style: str
) -> Dict[str, Any]:
    """
    Add a segment to a template's segment list (template_segments junction table).

    This is automatically called when a counsellor-requested segment is approved.
    The unique combination of (template_id, segment_id) ensures no duplicates.

    Args:
        template_id: Template UUID to add the segment to
        segment_id: Segment UUID (from segment_definitions.id)
        segment_code: Segment code for backward compatibility
        category: Segment category (core/additional/excluded)
        display_order: Display order in template
        brevity_level: Brevity level override (concise/balanced/detailed)
        terminology_style: Terminology style override (medical_terms/simple_terms/as_spoken)

    Returns:
        Created template_segments record

    Raises:
        ValueError: If template or segment not found, or duplicate entry
        Exception: If database operation fails
    """
    # Verify template exists
    template = (
        supabase.table("templates")
        .select("id, template_name")
        .eq("id", str(template_id))
        .execute()
    )
    if not template.data or len(template.data) == 0:
        raise ValueError(f"Template with ID '{template_id}' not found")

    template_name = template.data[0].get("template_name", "")

    # Verify segment exists
    segment = (
        supabase.table("segment_definitions")
        .select("id, segment_code, is_active")
        .eq("id", str(segment_id))
        .execute()
    )
    if not segment.data or len(segment.data) == 0:
        raise ValueError(f"Segment with ID '{segment_id}' not found")

    is_segment_active = segment.data[0].get("is_active", True)

    # Check for duplicate (template_id, segment_id) combination
    existing = (
        supabase.table("template_segments")
        .select("id")
        .eq("template_id", str(template_id))
        .eq("segment_id", str(segment_id))
        .execute()
    )
    if existing.data and len(existing.data) > 0:
        # Already exists - this is not an error, just return existing record
        return existing.data[0]

    # Insert into template_segments junction table
    data = {
        "template_id": str(template_id),
        "segment_id": str(segment_id),
        "segment_code": segment_code,  # Denormalized for backward compatibility
        "template_name": template_name,  # Denormalized for queries
        "category": category,
        "display_order": display_order,
        "brevity_level": brevity_level,
        "terminology_style": terminology_style
    }

    response = supabase.table("template_segments").insert(data).execute()

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to add segment to template")

    # If segment was inactive, activate it now that it's assigned to a template
    if not is_segment_active:
        supabase.table("segment_definitions").update({"is_active": True}).eq("id", str(segment_id)).execute()
        logger.info(f"Activated segment '{segment_code}' (was inactive before adding to template)")

    return response.data[0]


# ============================================================================
# Extractions Operations (with Edit Tracking)
# ============================================================================

def save_medical_extraction(
    session_id: uuid.UUID,
    consultation_type_id: uuid.UUID,
    counsellor_id: uuid.UUID,
    student_id: Optional[uuid.UUID],
    extraction_mode: str,
    model_used: str,
    segments: List[Dict[str, Any]],
    full_extraction: Dict[str, Any],
    # NEW PARAMETERS for SSE delivery and metrics tracking
    submission_id: Optional[uuid.UUID] = None,
    transcript_text: Optional[str] = None,
    stitching_time_seconds: Optional[float] = None,
    transcription_time_seconds: Optional[float] = None,
    extraction_time_seconds: Optional[float] = None,
    total_processing_time_seconds: Optional[float] = None,
    # Pre-generated extraction_id for parallel emotion analysis
    extraction_id: Optional[uuid.UUID] = None,
    # Recording metadata (student info, counsellor info, custom fields) copied from session
    recording_metadata_json: Optional[Dict[str, Any]] = None,
    # Formatted EHR payload (lookup-normalized for Neopaed, Aosta/Raster-formatted)
    ehr_payload_json: Optional[Dict[str, Any]] = None,
    # Continuation support (optional, non-breaking)
    is_continuation: bool = False,
    parent_extraction_ids: Optional[list] = None,
) -> uuid.UUID:
    """
    Save extraction to database (original AI-generated version).

    This function saves:
    1. extractions record with original_extraction_json
    2. extraction_segments records with version_type='original' (one per segment)

    Args:
        session_id: Recording session UUID
        consultation_type_id: Consultation type UUID
        counsellor_id: Counsellor who performed extraction
        student_id: Student UUID (optional)
        extraction_mode: 'core', 'additional', or 'full'
        model_used: Model name (e.g., 'gemini-2.0-flash-exp')
        segments: List of segment configs used
        full_extraction: Complete extraction JSON from AI
        submission_id: Processing job UUID (for SSE delivery, NULL for RecordTab)
        transcript_text: Full transcript text (for SSE delivery and search)
        stitching_time_seconds: Time to stitch audio chunks (NULL for RecordTab)
        transcription_time_seconds: Time for AI transcription
        extraction_time_seconds: Time for medical insights extraction
        total_processing_time_seconds: Total processing time
        extraction_id: Pre-generated UUID for parallel emotion analysis (optional)
                      If provided, the database record will use this ID instead of auto-generating
        recording_metadata_json: Additional metadata copied from recording session
                      (student info, counsellor info, custom fields). Flows to /status response.

    Returns:
        extraction_id: UUID of created medical_extraction record
    """
    import time
    save_start = time.time()

    # Debug: Log timing metrics received
    logger.debug(f"[SAVE_EXTRACTION] Timing metrics received:")
    logger.debug(f"[SAVE_EXTRACTION] - stitching_time_seconds: {stitching_time_seconds} (type: {type(stitching_time_seconds).__name__})")
    logger.debug(f"[SAVE_EXTRACTION] - transcription_time_seconds: {transcription_time_seconds} (type: {type(transcription_time_seconds).__name__})")
    logger.debug(f"[SAVE_EXTRACTION] - extraction_time_seconds: {extraction_time_seconds} (type: {type(extraction_time_seconds).__name__})")
    logger.debug(f"[SAVE_EXTRACTION] - total_processing_time_seconds: {total_processing_time_seconds} (type: {type(total_processing_time_seconds).__name__})")

    # Create medical_extraction record
    extraction_data = {
        "session_id": str(session_id),
        "consultation_type_id": str(consultation_type_id),
        "counsellor_id": str(counsellor_id),
        "student_id": str(student_id) if student_id else None,
        "extraction_mode": extraction_mode,
        "model_used": model_used,
        "segment_count": len(segments),
        "original_extraction_json": full_extraction,  # AI-generated (immutable)
        "edited_extraction_json": None,  # No edits yet
        "edit_count": 0,
        # NEW FIELDS for SSE delivery and metrics tracking
        "submission_id": str(submission_id) if submission_id else None,
        "transcript_text": transcript_text,
        "stitching_time_seconds": stitching_time_seconds,
        "transcription_time_seconds": transcription_time_seconds,
        "extraction_time_seconds": extraction_time_seconds,
        "total_processing_time_seconds": total_processing_time_seconds,
        # Recording metadata (flows from /start to /status)
        "recording_metadata_json": recording_metadata_json or {},
        # Formatted EHR payload (lookup-normalized for Neopaed, Aosta/Raster-formatted)
        "ehr_payload_json": ehr_payload_json,
        # Continuation support
        "is_continuation": is_continuation,
        "parent_extraction_ids": [str(pid) for pid in parent_extraction_ids] if parent_extraction_ids else [],
    }

    # Use pre-generated extraction_id if provided (for parallel emotion analysis)
    if extraction_id:
        extraction_data["id"] = str(extraction_id)
        logger.debug(f"[SAVE_EXTRACTION] Using pre-generated extraction_id: {extraction_id}")

    logger.debug(f"[SAVE_EXTRACTION] Extraction data being inserted:")
    logger.debug(f"[SAVE_EXTRACTION] - extraction_time_seconds in data dict: {extraction_data.get('extraction_time_seconds')}")

    try:
        extraction_response = supabase.table("extractions").insert(extraction_data).execute()
    except Exception as insert_err:
        # FK constraint violation: submission_id references processing_jobs(submission_id)
        # If processing_job was never created (fire-and-forget failed), create it now and retry
        err_msg = str(insert_err).lower()
        if submission_id and ("fkey" in err_msg or "foreign key" in err_msg or "409" in err_msg or "conflict" in err_msg or "23503" in err_msg):
            logger.warning(
                f"[SAVE_EXTRACTION] ⚠️ FK violation on submission_id={submission_id} — "
                f"processing_job likely missing. Creating it now and retrying..."
            )
            try:
                create_processing_job(
                    session_id=session_id,
                    submission_id=submission_id,
                )
                logger.info(f"[SAVE_EXTRACTION] ✅ Processing job created as fallback for submission_id={submission_id}")
                # Retry the extraction insert
                extraction_response = supabase.table("extractions").insert(extraction_data).execute()
            except Exception as retry_err:
                logger.error(f"[SAVE_EXTRACTION] ❌ Fallback failed: {retry_err}")
                raise retry_err
        else:
            raise insert_err

    if not extraction_response.data or len(extraction_response.data) == 0:
        raise Exception("Failed to create extraction record")

    extraction_id = uuid.UUID(extraction_response.data[0]["id"])

    # Create extraction_segments records with version_type='original' (one per segment)
    segment_records = []
    for segment in segments:
        segment_code = segment.get("segment_code")
        # ⭐ FIX: Use segment_value directly from segment dict (already provided by caller)
        segment_value = segment.get("segment_value")

        if segment_value is not None:  # Only save segments with data
            segment_records.append({
                "extraction_id": str(extraction_id),
                "segment_code": segment_code,
                "segment_value": segment_value,
                "version_type": "original",  # ⭐ NEW: Mark as original AI-generated
                "brevity_level": segment.get("brevity_level") or segment.get("default_brevity_level"),
                "terminology_style": segment.get("terminology_style") or segment.get("default_terminology_style"),
                "display_format": segment.get("display_format", "paragraph")
            })

    # Batch insert segments
    if segment_records:
        logger.debug(f"[SAVE_EXTRACTION] Inserting {len(segment_records)} segments to extraction_segments table")
        segments_start = time.time()
        supabase.table("extraction_segments").insert(segment_records).execute()
        segments_duration = time.time() - segments_start
        logger.debug(f"[SAVE_EXTRACTION] ✓ Successfully saved {len(segment_records)} segments in {segments_duration:.3f}s")
    else:
        logger.warning(f"[SAVE_EXTRACTION] No segments to save (segment_records is empty)")

    total_save_duration = time.time() - save_start
    logger.info(f"[TIMING_SAVE] Total save_medical_extraction: {total_save_duration:.3f}s")

    return extraction_id


def _to_camel_case(snake_str: str) -> str:
    """Convert snake_case to camelCase (helper function)"""
    components = snake_str.lower().split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


def _to_snake_case(camel_str: str) -> str:
    """Convert camelCase to snake_case (helper function)"""
    import re
    # Insert underscore before uppercase letters and convert to lowercase
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', camel_str)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def get_extraction_data(
    extraction_id: uuid.UUID,
    include_segments: bool = True
) -> Dict[str, Any]:
    """
    Get extraction data (returns edited version if exists, otherwise original).

    Args:
        extraction_id: extraction UUID
        include_segments: Whether to include individual segments (uses current_extraction_state view)

    Returns:
        Dict with extraction data and metadata
    """
    # Get extraction record (only needed columns, avoids large transcript_text/merge fields)
    extraction_response = (
        supabase.table("extractions")
        .select(
            "id, session_id, consultation_type_id, counsellor_id, student_id, "
            "extraction_mode, segment_count, edit_count, last_edited_at, last_edited_by, "
            "created_at, updated_at, original_extraction_json, edited_extraction_json, is_merged, "
            "recording_metadata_json"
        )
        .eq("id", str(extraction_id))
        .execute()
    )

    if not extraction_response.data or len(extraction_response.data) == 0:
        raise ValueError(f"Extraction {extraction_id} not found")

    extraction = extraction_response.data[0]

    # Return edited version if exists, otherwise original
    current_data = extraction.get("edited_extraction_json") or extraction.get("original_extraction_json")

    _rec_meta = extraction.get("recording_metadata_json") or {}
    if not isinstance(_rec_meta, dict):
        _rec_meta = {}

    result = {
        "extraction_id": extraction["id"],
        "session_id": extraction["session_id"],
        "consultation_type_id": extraction["consultation_type_id"],
        "counsellor_id": extraction["counsellor_id"],
        "student_id": extraction["student_id"],
        "extraction_mode": extraction["extraction_mode"],
        "segment_count": extraction["segment_count"],
        "extraction_data": current_data,
        "is_edited": extraction.get("edit_count", 0) > 0,
        "edit_count": extraction.get("edit_count", 0),
        "is_merged": extraction.get("is_merged") or False,
        "last_edited_at": extraction.get("last_edited_at"),
        "last_edited_by": extraction.get("last_edited_by"),
        "created_at": extraction["created_at"],
        "updated_at": extraction["updated_at"],
        "role": _rec_meta.get("role") or None,
    }

    # Include individual segments if requested (uses current_extraction_state view)
    if include_segments:
        result["segments"] = get_current_extraction_segments(extraction_id)

    return result


def get_extraction_by_submission_id(submission_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get extraction record by submission_id for SSE endpoint.

    This replaces direct reads from processing_jobs table.
    After migration, all extraction data (transcript, insights, metrics) is stored
    in extractions table and retrieved here for SSE delivery.

    Args:
        submission_id: Processing job UUID

    Returns:
        Dict with transcript, insights, and metrics, or None if not found

    Usage:
        Used by SSE endpoint (/api/v1/option1/recording/processing/{submission_id}/stream)
        to deliver completed extraction results to frontend.

    Example:
        extraction = get_extraction_by_submission_id(submission_uuid)
        if extraction:
            return {"transcript": extraction["transcript"], "insights": extraction["insights"]}
    """
    try:
        logger.debug(f"[GET_EXTRACTION_BY_SUBMISSION] ========== FETCHING EXTRACTION ==========")
        logger.debug(f"[GET_EXTRACTION_BY_SUBMISSION] Query: extractions WHERE submission_id = {submission_id}")

        response = (
            supabase.table("extractions")
            .select("*")
            .eq("submission_id", str(submission_id))
            .limit(1)
            .execute()
        )

        logger.debug(f"[GET_EXTRACTION_BY_SUBMISSION] Query response - data count: {len(response.data) if response.data else 0}")

        if not response.data:
            logger.error(f"[GET_EXTRACTION_BY_SUBMISSION] ❌ NO EXTRACTION FOUND!")
            logger.error(f"[GET_EXTRACTION_BY_SUBMISSION] submission_id queried: {submission_id}")
            logger.error(f"[GET_EXTRACTION_BY_SUBMISSION] This means no row in extractions has this submission_id")
            return None

        extraction = response.data[0]
        logger.debug(f"[GET_EXTRACTION_BY_SUBMISSION] ✅ Extraction found!")
        logger.debug(f"[GET_EXTRACTION_BY_SUBMISSION] - extraction_id: {extraction.get('id')}")
        logger.debug(f"[GET_EXTRACTION_BY_SUBMISSION] - submission_id from DB: {extraction.get('submission_id')}")
        logger.debug(f"[GET_EXTRACTION_BY_SUBMISSION] - transcript_text length: {len(extraction.get('transcript_text', '')) if extraction.get('transcript_text') else 0}")
        logger.debug(f"[GET_EXTRACTION_BY_SUBMISSION] - original_extraction_json present: {extraction.get('original_extraction_json') is not None}")
        if extraction.get('original_extraction_json'):
            logger.debug(f"[GET_EXTRACTION_BY_SUBMISSION] - original_extraction_json keys: {list(extraction['original_extraction_json'].keys())[:5]}")

        # Return data in format expected by SSE endpoint and EHR integration
        result = {
            "id": extraction.get("id"),
            "transcript": extraction.get("transcript_text"),
            "insights": extraction.get("original_extraction_json"),  # Use original_extraction_json
            "stitching_time_seconds": extraction.get("stitching_time_seconds"),
            "transcription_time_seconds": extraction.get("transcription_time_seconds"),
            "extraction_time_seconds": extraction.get("extraction_time_seconds"),
            "total_processing_time_seconds": extraction.get("total_processing_time_seconds"),
            # Recording metadata (flows from /start to /status)
            "recording_metadata_json": extraction.get("recording_metadata_json"),
            # Counsellor and student IDs (needed for Aosta integration)
            "counsellor_id": extraction.get("counsellor_id"),
            "student_id": extraction.get("student_id"),
            # Edited extraction (for EHR edit endpoints)
            "original_extraction_json": extraction.get("original_extraction_json"),
            "edited_extraction_json": extraction.get("edited_extraction_json"),
            "edit_count": extraction.get("edit_count", 0),
            "is_merged": extraction.get("is_merged") or False,
        }

        logger.debug(f"[GET_EXTRACTION_BY_SUBMISSION] Returning result with transcript length: {len(result['transcript']) if result['transcript'] else 0}")
        logger.debug(f"[GET_EXTRACTION_BY_SUBMISSION] Returning result with insights present: {result['insights'] is not None}")
        logger.debug(f"[GET_EXTRACTION_BY_SUBMISSION] ================================================")

        return result

    except Exception as e:
        logger.error(f"[GET_EXTRACTION_BY_SUBMISSION] ❌ EXCEPTION during fetch: {e}", exc_info=True)
        return None


# COMMENTED OUT: Not currently used - webhooks use in-memory data for lower latency.
# Uncomment if you need a "re-send webhook" API endpoint that fetches from DB.
#
# def get_extraction_for_webhook(extraction_id: uuid.UUID) -> Optional[Dict[str, Any]]:
#     """
#     Get extraction data from extractions table for external webhook delivery.
#
#     This function fetches data FROM THE DATABASE (not from memory) to ensure
#     webhooks deliver exactly what's stored. Used for external frontend webhooks
#     (not Supabase Realtime, which uses processing_jobs.progress_json).
#
#     Args:
#         extraction_id: extraction UUID
#
#     Returns:
#         Dict with 'insights' and 'session_info' formatted for webhook_service.py,
#         or None if extraction not found
#
#     Example:
#         webhook_data = get_extraction_for_webhook(extraction_uuid)
#         if webhook_data:
#             await send_insights_webhook(
#                 insights=webhook_data['insights'],
#                 session_info=webhook_data['session_info'],
#                 source='recording'
#             )
#     """
#     try:
#         logger.info(f"[GET_EXTRACTION_FOR_WEBHOOK] Fetching extraction {extraction_id} from database")
#
#         # Get extraction with related session data via join
#         extraction_response = (
#             supabase.table("extractions")
#             .select("""
#                 *,
#                 recording_sessions!inner(
#                     id,
#                     correlation_id,
#                     counsellor_id,
#                     student_id,
#                     template_code,
#                     template_name,
#                     extraction_mode,
#                     processing_mode,
#                     consultation_type_id
#                 )
#             """)
#             .eq("id", str(extraction_id))
#             .execute()
#         )
#
#         if not extraction_response.data:
#             logger.warning(f"[GET_EXTRACTION_FOR_WEBHOOK] Extraction {extraction_id} not found")
#             return None
#
#         extraction = extraction_response.data[0]
#         session = extraction.get("recording_sessions", {})
#
#         # Get consultation_type_code if consultation_type_id exists
#         consultation_type_code = None
#         consultation_type_id = extraction.get("consultation_type_id") or session.get("consultation_type_id")
#
#         if consultation_type_id:
#             ct_response = (
#                 supabase.table("consultation_types")
#                 .select("type_code")
#                 .eq("id", str(consultation_type_id))
#                 .limit(1)
#                 .execute()
#             )
#             if ct_response.data:
#                 consultation_type_code = ct_response.data[0].get("type_code")
#
#         # Use edited version if exists, otherwise original
#         insights = extraction.get("edited_extraction_json") or extraction.get("original_extraction_json")
#
#         # Build session_info in webhook format
#         session_info = {
#             "correlation_id": session.get("correlation_id") or str(session.get("id", "")),
#             "submission_id": extraction.get("submission_id"),
#             "consultation_id": extraction.get("id"),  # extraction_id for Live API matching
#             "counsellor_id": extraction.get("counsellor_id") or session.get("counsellor_id"),
#             "student_id": extraction.get("student_id") or session.get("student_id"),
#             "template_code": session.get("template_code"),
#             "template_name": session.get("template_name"),
#             "extraction_mode": extraction.get("extraction_mode") or session.get("extraction_mode"),
#             "processing_mode": session.get("processing_mode"),
#             "consultation_type_code": consultation_type_code,
#         }
#
#         logger.info(f"[GET_EXTRACTION_FOR_WEBHOOK] ✅ Retrieved extraction from DB:")
#         logger.info(f"[GET_EXTRACTION_FOR_WEBHOOK] - extraction_id: {extraction_id}")
#         logger.info(f"[GET_EXTRACTION_FOR_WEBHOOK] - insights keys: {list(insights.keys()) if insights else 'None'}")
#         logger.info(f"[GET_EXTRACTION_FOR_WEBHOOK] - template_code: {session_info.get('template_code')}")
#         logger.info(f"[GET_EXTRACTION_FOR_WEBHOOK] - consultation_type_code: {consultation_type_code}")
#
#         return {
#             "insights": insights,
#             "session_info": session_info
#         }
#
#     except Exception as e:
#         logger.error(f"[GET_EXTRACTION_FOR_WEBHOOK] ❌ Error fetching extraction: {e}", exc_info=True)
#         return None


def _merge_edited_extraction(previous: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Merge incoming edits over previous JSON with one-level-deep semantics.

    Top-level keys (segment codes) are merged shallowly: keys present in
    `incoming` override, keys absent fall back to `previous`.

    For top-level keys where BOTH sides are dicts, sub-fields are merged
    sub-shallowly: incoming sub-fields override, missing sub-fields fall back
    to `previous`. This protects against partial segment payloads from edit
    clients that re-POST only the changed sub-field of a segment (e.g.
    `rtConsiderations: {pacemaker: "No"}` while the original had 5 other
    sub-fields), which would otherwise wipe the untouched sub-fields.

    Non-dict values (lists, scalars) at any level are replaced wholesale —
    deep-merging arrays would corrupt order and identity.
    """
    merged: Dict[str, Any] = {}
    for key in set(previous.keys()) | set(incoming.keys()):
        if key not in incoming:
            merged[key] = previous[key]
        elif key not in previous:
            merged[key] = incoming[key]
        else:
            prev_v = previous[key]
            inc_v = incoming[key]
            if isinstance(prev_v, dict) and isinstance(inc_v, dict):
                merged[key] = {**prev_v, **inc_v}
            else:
                merged[key] = inc_v
    return merged


def _normalize_segment_values(data: Any) -> Any:
    """Unwrap top-level segment values that arrived as JSON-encoded strings.

    Some edit paths (raw-JSON textareas, mis-wired form components) send a
    segment as `"{\\"key\\": ...}"` instead of `{"key": ...}`. Storing that
    breaks the letter renderer, EHR formatters, and history views that all
    expect native dicts/lists.

    Defensive only: leaves real strings (e.g. presenting_complaints, free-text
    fields) alone — only re-parses values that successfully decode to a dict
    or list.
    """
    if not isinstance(data, dict):
        return data
    out: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            stripped = value.lstrip()
            if stripped[:1] in ("{", "["):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, (dict, list)):
                        out[key] = parsed
                        continue
                except (ValueError, TypeError):
                    pass
        out[key] = value
    return out


def update_extraction_edits(
    extraction_id: uuid.UUID,
    edited_data: Dict[str, Any],
    edited_by: uuid.UUID,
    edited_by_type: str = "doctor",
    edit_source: str = "webapp"
) -> Dict[str, Any]:
    """
    Update extraction with counsellor's or assistant's edits.

    This stores the latest edited version and increments edit count.
    Original AI-generated extraction remains unchanged.
    Also inserts a version snapshot into extraction_edit_history.

    Args:
        extraction_id: extraction UUID
        edited_data: Complete edited extraction JSON
        edited_by: Counsellor or Assistant UUID who made edits
        edited_by_type: Type of user making edits: "doctor" or "nurse"
        edit_source: Source of edit: "webapp", "ehr", "api"

    Returns:
        Updated extraction record
    """
    from datetime import datetime, timezone

    # Get current extraction (include previous edit data for history)
    current_response = (
        supabase.table("extractions")
        .select("edit_count, original_extraction_json, edited_extraction_json")
        .eq("id", str(extraction_id))
        .execute()
    )

    if not current_response.data or len(current_response.data) == 0:
        raise ValueError(f"Extraction {extraction_id} not found")

    current_row = current_response.data[0]
    current_edit_count = current_row.get("edit_count", 0) or 0
    new_version = current_edit_count + 1

    # One-level-deep merge with edited-wins precedence at every level. Top-
    # level keys (segment codes) and sub-fields (within dict-shaped segments)
    # both fall back to the previous value when absent from the incoming
    # payload. See `_merge_edited_extraction` for full semantics.
    #
    # Editor frontends often render only a subset of sections — sometimes
    # only a single sub-field of a segment (e.g. POSTing `rtConsiderations:
    # {pacemaker: "No"}` when the segment has 6 sub-fields). The deep merge
    # preserves untouched sub-fields so downstream consumers (letter render,
    # EHR payload, history views) keep the full picture.
    previous_json = current_row.get("edited_extraction_json") or current_row.get("original_extraction_json")
    # Normalize both sides: unwraps any segment value that was double-encoded
    # as a JSON string so the merged record holds native dicts/lists.
    previous_json = _normalize_segment_values(previous_json)
    edited_data = _normalize_segment_values(edited_data)
    if isinstance(previous_json, dict) and isinstance(edited_data, dict):
        merged_data = _merge_edited_extraction(previous_json, edited_data)
    else:
        merged_data = edited_data

    # --- Insert edit history snapshot (Phase 2) ---
    try:
        changed_segments = _compute_changed_segments(previous_json, merged_data)
        change_summary = {seg: {"action": "modified"} for seg in changed_segments}

        supabase.table("extraction_edit_history").insert({
            "extraction_id": str(extraction_id),
            "version_number": new_version,
            "edited_extraction_json": merged_data,
            "changed_segments": changed_segments,
            "change_summary": change_summary,
            "edited_by": str(edited_by),
            "edited_by_type": edited_by_type,
            "edited_at": datetime.now(timezone.utc).isoformat(),
            "edit_source": edit_source,
        }).execute()
    except Exception as e:
        logger.warning(f"[EDIT_HISTORY] Failed to insert edit history for {extraction_id}: {e}")

    # Persist the merged JSON so all sections (changed and unchanged) survive.
    updates = {
        "edited_extraction_json": merged_data,
        "edit_count": new_version,
        "last_edited_at": datetime.now(timezone.utc).isoformat(),
        "last_edited_by": str(edited_by),
        "edited_by_type": edited_by_type  # Track if edited by counsellor or assistant
    }

    response = (
        supabase.table("extractions")
        .update(updates)
        .eq("id", str(extraction_id))
        .execute()
    )

    if not response.data or len(response.data) == 0:
        raise Exception("Failed to update extraction edits")

    # Also update individual segments
    _update_extraction_segments(extraction_id, edited_data)

    # Fire-and-forget: log any schema drift introduced by this edit. Catches
    # cases like `diagnosis: []` → `diagnosis: {primary_diagnosis: ...}` so
    # operators can spot iframe/formatter shape mismatches before they bite.
    try:
        from services.schema_drift_validator import schedule_schema_drift_log
        schedule_schema_drift_log(str(extraction_id), edited_data)
    except Exception as e:
        logger.debug(f"[SCHEMA_DRIFT] schedule failed for {extraction_id}: {e}")

    return response.data[0]


def _compute_changed_segments(previous_json: Optional[Dict], new_json: Dict) -> list:
    """Compare two extraction JSONs and return list of changed segment codes."""
    if not previous_json:
        return list(new_json.keys()) if new_json else []

    changed = []
    all_keys = set(list(previous_json.keys()) + list(new_json.keys()))

    for key in all_keys:
        old_val = previous_json.get(key)
        new_val = new_json.get(key)
        if old_val != new_val:
            changed.append(key)

    return changed


def _update_extraction_segments(extraction_id: uuid.UUID, edited_data: Dict[str, Any]):
    """
    Update individual extraction_segments with edited data using version_type approach.

    This function:
    1. Gets all original segments for this extraction
    2. For each segment in edited_data, checks if it was changed
    3. If edited: Insert/update row with version_type='edited'
    4. If unchanged: Do nothing (keep original only)

    Note: Only segments present in edited_data are processed. Missing segments
    are assumed to be unchanged (not deleted), since the frontend may only
    send a subset of segments (e.g., CORE only, not ADDITIONAL).

    Args:
        extraction_id: extraction UUID
        edited_data: Edited extraction JSON (may be partial - only changed segments)
    """
    # Get all original segments for this extraction
    original_segments_response = (
        supabase.table("extraction_segments")
        .select("segment_code, segment_value, brevity_level, terminology_style, display_format")
        .eq("extraction_id", str(extraction_id))
        .eq("version_type", "original")
        .execute()
    )

    original_segments = {seg["segment_code"]: seg for seg in original_segments_response.data}

    # Process each segment in the edited data
    for key, edited_value in edited_data.items():
        # Convert camelCase key to snake_case segment_code
        segment_code = _to_snake_case(key)

        # Skip if this segment doesn't exist in original (could be metadata or new field)
        if segment_code not in original_segments:
            # Also try the key as-is (in case it's already snake_case)
            if key not in original_segments:
                logger.debug(f"[UPDATE_SEGMENTS] Skipping unknown segment: {key} (snake: {segment_code})")
                continue
            segment_code = key

        original_segment = original_segments[segment_code]
        original_value = original_segment["segment_value"]

        # Check if segment was actually edited (value changed)
        if edited_value != original_value:
            # Check if edited version already exists
            existing_edited = (
                supabase.table("extraction_segments")
                .select("id")
                .eq("extraction_id", str(extraction_id))
                .eq("segment_code", segment_code)
                .eq("version_type", "edited")
                .execute()
            )

            edited_segment_data = {
                "extraction_id": str(extraction_id),
                "segment_code": segment_code,
                "segment_value": edited_value,
                "version_type": "edited",
                "brevity_level": original_segment.get("brevity_level"),
                "terminology_style": original_segment.get("terminology_style"),
                "display_format": original_segment.get("display_format")
            }

            if existing_edited.data:
                # Update existing edited row
                supabase.table("extraction_segments").update(
                    edited_segment_data
                ).eq("extraction_id", str(extraction_id)).eq("segment_code", segment_code).eq("version_type", "edited").execute()
                logger.debug(f"[UPDATE_SEGMENTS] Updated edited row for {segment_code}")
            else:
                # Insert new edited row
                supabase.table("extraction_segments").insert(edited_segment_data).execute()
                logger.debug(f"[UPDATE_SEGMENTS] Inserted edited row for {segment_code}")

        # If unchanged: Do nothing (keep original only - no edited row)


def compare_extraction_versions(extraction_id: uuid.UUID) -> Dict[str, Any]:
    """
    Compare original AI-generated extraction vs latest edited version.

    Args:
        extraction_id: extraction UUID

    Returns:
        Dict with original, edited, edit_count, and comparison metadata
    """
    # Get extraction record
    extraction_response = (
        supabase.table("extractions")
        .select("original_extraction_json, edited_extraction_json, edit_count, last_edited_at, last_edited_by")
        .eq("id", str(extraction_id))
        .execute()
    )

    if not extraction_response.data or len(extraction_response.data) == 0:
        raise ValueError(f"Extraction {extraction_id} not found")

    extraction = extraction_response.data[0]

    return {
        "extraction_id": str(extraction_id),
        "original": extraction.get("original_extraction_json"),
        "edited": extraction.get("edited_extraction_json"),
        "has_edits": extraction.get("edit_count", 0) > 0,
        "edit_count": extraction.get("edit_count", 0),
        "last_edited_at": extraction.get("last_edited_at"),
        "last_edited_by": extraction.get("last_edited_by")
    }


def get_extraction_by_session(session_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get extraction record for a recording session.

    Args:
        session_id: Recording session UUID

    Returns:
        Extraction data dict or None if not found
    """
    response = (
        supabase.table("extractions")
        .select("id")
        .eq("session_id", str(session_id))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not response.data or len(response.data) == 0:
        return None

    extraction_id = uuid.UUID(response.data[0]["id"])

    return get_extraction_data(extraction_id, include_segments=True)


# ============================================================================
# Helper Functions for Version-Type Queries
# ============================================================================

def get_current_extraction_segments(extraction_id: uuid.UUID) -> List[Dict[str, Any]]:
    """
    Get current state of all segments for an extraction (uses database view).

    This returns the edited version of each segment if it exists, otherwise the original.
    Uses the current_extraction_state view for optimal performance.

    Args:
        extraction_id: extraction UUID

    Returns:
        List of current segment records with is_edited and is_deleted flags
    """
    response = (
        supabase.from_("current_extraction_state")
        .select("*")
        .eq("extraction_id", str(extraction_id))
        .execute()
    )

    return response.data if response.data else []


def get_original_segments(extraction_id: uuid.UUID) -> List[Dict[str, Any]]:
    """
    Get ONLY original AI-generated segments (ignore edits).

    Args:
        extraction_id: extraction UUID

    Returns:
        List of original segment records
    """
    response = (
        supabase.table("extraction_segments")
        .select("*")
        .eq("extraction_id", str(extraction_id))
        .eq("version_type", "original")
        .execute()
    )

    return response.data if response.data else []


def get_edited_segments(extraction_id: uuid.UUID) -> List[Dict[str, Any]]:
    """
    Get ONLY edited segments (returns empty list if never edited).

    Args:
        extraction_id: extraction UUID

    Returns:
        List of edited segment records
    """
    response = (
        supabase.table("extraction_segments")
        .select("*")
        .eq("extraction_id", str(extraction_id))
        .eq("version_type", "edited")
        .execute()
    )

    return response.data if response.data else []


def get_segment_comparison(extraction_id: uuid.UUID) -> List[Dict[str, Any]]:
    """
    Get side-by-side comparison of original vs edited segments (uses database view).

    Uses the extraction_segment_comparison view for optimal performance.

    Args:
        extraction_id: extraction UUID

    Returns:
        List of comparison records with original_value, edited_value, and edit_status
    """
    response = (
        supabase.from_("extraction_segment_comparison")
        .select("*")
        .eq("extraction_id", str(extraction_id))
        .execute()
    )

    return response.data if response.data else []


def get_deleted_segments(extraction_id: uuid.UUID) -> List[Dict[str, Any]]:
    """
    Get all segments that were deleted by the counsellor.

    Args:
        extraction_id: extraction UUID

    Returns:
        List of deleted segments (version_type='edited' with segment_value=NULL)
    """
    response = (
        supabase.table("extraction_segments")
        .select("segment_code, created_at, updated_at")
        .eq("extraction_id", str(extraction_id))
        .eq("version_type", "edited")
        .is_("segment_value", "null")
        .execute()
    )

    return response.data if response.data else []


# ============================================================================
# Segment Parent Tracking - Middle-Ground Approach
# ============================================================================

def clone_segment_with_parent_tracking(
    parent_segment_code: str,
    new_segment_code: str,
    new_segment_name: str,
    consultation_type_id: Optional[str] = None,
    template_id: Optional[str] = None,
    counsellor_id: Optional[uuid.UUID] = None,
    parent_segment_data: Optional[Dict[str, Any]] = None,
    custom_prompt_section_text: Optional[str] = None,
    custom_schema_definition_json: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Clone an existing segment to create a new one with parent tracking.

    Args:
        parent_segment_code: Segment code to clone from (e.g., 'DIAGNOSIS')
        new_segment_code: Code for the new segment (e.g., 'DIAGNOSIS_CARDIOLOGY')
        new_segment_name: Display name for the new segment
        consultation_type_id: Optional consultation type UUID for the new segment
        template_id: Optional template UUID if this is template-specific
        counsellor_id: Counsellor creating the segment
        parent_segment_data: Optional parent segment data (if already fetched)
        custom_prompt_section_text: Custom prompt text (if provided, uses this instead of parent's)
        custom_schema_definition_json: Custom schema JSON (if provided, uses this instead of parent's)

    Returns:
        The newly created segment with parent tracking

    Raises:
        ValueError: If parent segment doesn't exist or new segment code already exists

    Note:
        Migration 20251123000200 removed created_by_counsellor_id, now using counsellor_id column.
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.debug(f"[CLONE_WITH_TRACKING] *** CODE VERSION: 2025-11-25-v1 (parent_segment_data required) ***")
    logger.info(f"[CLONE_WITH_TRACKING] Starting: parent={parent_segment_code}, new={new_segment_code}")
    logger.debug(f"[CLONE_WITH_TRACKING] Params: ct_id={consultation_type_id}, template_id={template_id}, counsellor_id={counsellor_id}")

    # parent_segment_data is required - caller must look up the parent segment via junction table
    # to ensure the correct segment is used (segment_code is NOT unique in segment_definitions)
    if not parent_segment_data:
        logger.error(f"[CLONE_WITH_TRACKING] parent_segment_data is required but was not provided")
        raise ValueError(
            f"parent_segment_data is required. Caller must look up the parent segment '{parent_segment_code}' "
            f"via the junction table (consultation_type_segments or template_segments) using the source consultation type ID."
        )

    logger.debug(f"[CLONE_WITH_TRACKING] Using provided parent segment data")
    parent = parent_segment_data
    logger.debug(f"[CLONE_WITH_TRACKING] Parent segment: id={parent.get('id')}, code={parent.get('segment_code')}")

    # Note: segment_code and segment_name are NOT unique in segment_definitions
    # Uniqueness is maintained through junction table associations
    # Multiple segments can have the same code/name but be linked to different consultation types/templates
    logger.debug(f"[CLONE_WITH_TRACKING] Building new segment data...")
    # Create new segment by copying from parent
    # Note: consultation_type_id and template_id are NOT columns in segment_definitions
    # Segments are linked to consultation types and templates via junction tables

    # Use custom values if provided, otherwise copy from parent
    prompt_text = custom_prompt_section_text if custom_prompt_section_text is not None else parent.get("prompt_section_text")
    schema_json = custom_schema_definition_json if custom_schema_definition_json is not None else parent.get("schema_definition_json")

    # If custom values are provided, mark as diverged from parent
    has_custom_content = custom_prompt_section_text is not None or custom_schema_definition_json is not None

    new_segment_data = {
        "segment_code": new_segment_code,
        "segment_name": new_segment_name,
        "is_active": True,  # Cloned segments are active by default
        # Parent tracking
        "parent_segment_code": parent_segment_code,
        "is_cloned_from_parent": True,
        "cloned_at": "now()",
        "diverged_from_parent": has_custom_content,  # Mark diverged if custom content provided
        # Use custom content or copy from parent
        "prompt_section_text": prompt_text,
        "schema_definition_json": schema_json,
        # Copy settings from parent
        "default_category": parent.get("default_category"),
        "is_required": False,  # Cloned segments are typically not required
        "display_order": parent.get("display_order"),
        "default_brevity_level": parent.get("default_brevity_level"),
        "default_terminology_style": parent.get("default_terminology_style"),
        "description": f"Cloned from {parent_segment_code}: {parent.get('description', '')}",
        "is_active": True,
        "status": "active",  # Set status to active for cloned segments
        # Ownership: For now, cloned segments are always system segments
        # TODO: Support counsellor-owned segments when cloning on behalf of a specific counsellor
        "segment_type": "system",
        "counsellor_id": None,
    }
    logger.debug(f"[CLONE_WITH_TRACKING] New segment data prepared (counsellor_id={new_segment_data.get('counsellor_id')})")

    # Insert the new segment
    try:
        logger.debug(f"[CLONE_WITH_TRACKING] Inserting new segment into database...")
        response = (
            supabase.table("segment_definitions")
            .insert(new_segment_data)
            .execute()
        )
        logger.debug(f"[CLONE_WITH_TRACKING] Database insert response received")

        if not response.data or len(response.data) == 0:
            logger.error(f"[CLONE_WITH_TRACKING] Insert returned empty data")
            raise ValueError("Failed to create cloned segment")

        new_segment = response.data[0]
        new_segment_id = new_segment.get('id')
        logger.info(f"[CLONE_WITH_TRACKING] Successfully created segment: id={new_segment_id}")

        # Create junction table associations if consultation_type_id or template_id provided
        if consultation_type_id:
            logger.info(f"[CLONE_WITH_TRACKING] Creating consultation_type_segments association")
            logger.debug(f"[CLONE_WITH_TRACKING] Junction data: consultation_type_id={consultation_type_id}, segment_id={new_segment_id}, category={new_segment.get('default_category', 'additional')}")
            try:
                # Fetch consultation type name
                ct_response = supabase.table("consultation_types").select("type_name").eq("id", str(consultation_type_id)).single().execute()
                ct_name = ct_response.data.get("type_name") if ct_response.data else None

                junction_data = {
                    "consultation_type_id": str(consultation_type_id),
                    "consultation_type_name": ct_name,
                    "segment_id": str(new_segment_id),
                    "segment_code": new_segment.get("segment_code"),
                    "default_category": new_segment.get("default_category", "additional").lower(),
                    "is_required_for_type": False,
                    "default_display_order": new_segment.get("display_order", 999)
                }
                logger.debug(f"[CLONE_WITH_TRACKING] Inserting junction record: {junction_data}")
                junction_response = supabase.table("consultation_type_segments").insert(junction_data).execute()
                logger.debug(f"[CLONE_WITH_TRACKING] Junction response: {junction_response.data}")
                logger.info(f"[CLONE_WITH_TRACKING] ✅ Successfully created consultation_type_segments association")
            except Exception as e:
                logger.error(f"[CLONE_WITH_TRACKING] ❌ Failed to create consultation_type association: {str(e)}", exc_info=True)
        else:
            logger.warning(f"[CLONE_WITH_TRACKING] ⚠️ No consultation_type_id provided - segment will NOT be linked to any consultation type!")

        if template_id:
            logger.info(f"[CLONE_WITH_TRACKING] Creating template_segments association")
            try:
                # Fetch template name
                tpl_response = supabase.table("templates").select("template_name").eq("id", str(template_id)).single().execute()
                tpl_name = tpl_response.data.get("template_name") if tpl_response.data else None

                supabase.table("template_segments").insert({
                    "template_id": str(template_id),
                    "template_name": tpl_name,
                    "segment_id": str(new_segment_id),
                    "segment_code": new_segment.get("segment_code"),
                    "category": new_segment.get("default_category", "additional").lower(),
                    "display_order": new_segment.get("display_order", 999)
                }).execute()
                logger.info(f"[CLONE_WITH_TRACKING] Successfully created template association")
            except Exception as e:
                logger.warning(f"[CLONE_WITH_TRACKING] Failed to create template association: {str(e)}")

        return new_segment
    except Exception as e:
        # Log the full error for debugging
        error_msg = str(e)
        if hasattr(e, '__dict__'):
            error_msg = f"{error_msg} | Details: {e.__dict__}"
        logger.error(f"[CLONE_WITH_TRACKING] Database insert failed: {error_msg}", exc_info=True)
        raise ValueError(f"Failed to insert cloned segment: {error_msg}")


def bulk_clone_segments(
    source_consultation_type_code: str,
    target_consultation_type_code: str,
    segment_codes: List[str],
    admin_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Bulk clone segments from source consultation type to target consultation type.

    Args:
        source_consultation_type_code: Source consultation type (e.g., 'OP')
        target_consultation_type_code: Target consultation type (e.g., 'EMERGENCY')
        segment_codes: List of segment codes to clone (e.g., ['DIAGNOSIS', 'HISTORY'])
        admin_id: Admin UUID performing the bulk clone (changed from created_by_admin_id)

    Returns:
        Dictionary with:
        - success: List of successfully cloned segments
        - failed: List of failed clones with error messages
        - summary: Statistics about the operation

    Raises:
        ValueError: If consultation types don't exist
    """
    # Get source consultation type
    source_ct = get_consultation_type_by_code(source_consultation_type_code)
    if not source_ct:
        raise ValueError(f"Source consultation type '{source_consultation_type_code}' not found")

    # Get target consultation type
    target_ct = get_consultation_type_by_code(target_consultation_type_code)
    if not target_ct:
        raise ValueError(f"Target consultation type '{target_consultation_type_code}' not found")

    target_consultation_type_id = target_ct["id"]
    source_consultation_type_id = source_ct["id"]

    # Track results
    success_clones = []
    failed_clones = []

    # Process each segment code
    for segment_code in segment_codes:
        try:
            # Look up the specific segment via the consultation_type_segments junction table
            # This ensures we get the correct segment for the source consultation type
            junction_lookup = (
                supabase.table("consultation_type_segments")
                .select("segment_id")
                .eq("consultation_type_id", source_consultation_type_id)
                .eq("segment_code", segment_code)
                .execute()
            )

            if not junction_lookup.data or len(junction_lookup.data) == 0:
                failed_clones.append({
                    "segment_code": segment_code,
                    "error": f"Segment '{segment_code}' not found in source consultation type '{source_consultation_type_code}'"
                })
                continue

            segment_id = junction_lookup.data[0]["segment_id"]
            # Get the segment definition by its unique ID
            segment_response = (
                supabase.table("segment_definitions")
                .select("*")
                .eq("id", segment_id)
                .eq("is_active", True)
                .execute()
            )

            if not segment_response.data or len(segment_response.data) == 0:
                failed_clones.append({
                    "segment_code": segment_code,
                    "error": f"Segment '{segment_code}' not found in source consultation type '{source_consultation_type_code}'"
                })
                continue

            parent_segment = segment_response.data[0]

            # Keep the same segment_code - uniqueness is maintained through the junction table
            # (consultation_type_id + segment_code combination is unique)
            new_segment_code = segment_code

            # Check if segment with this code already exists in TARGET consultation type's junction table
            existing_check = (
                supabase.table("consultation_type_segments")
                .select("id, segment_id")
                .eq("consultation_type_id", target_consultation_type_id)
                .eq("segment_code", segment_code)
                .execute()
            )

            if existing_check.data and len(existing_check.data) > 0:
                # Segment with this code already exists in target consultation type, skip
                failed_clones.append({
                    "segment_code": segment_code,
                    "error": f"Segment '{segment_code}' already exists in target consultation type '{target_consultation_type_code}'"
                })
                continue

            # Clone the segment using existing clone function
            # The cloned segment will have the same segment_code but a new UUID
            # It gets linked to the target consultation type via the junction table
            cloned_segment = clone_segment_with_parent_tracking(
                parent_segment_code=segment_code,
                new_segment_code=new_segment_code,
                new_segment_name=parent_segment.get("segment_name"),
                consultation_type_id=target_consultation_type_id,
                template_id=None,
                counsellor_id=admin_id,  # Changed from created_by_counsellor_id (migration 20251123000200)
                parent_segment_data=parent_segment  # Pass the already-fetched parent data
            )

            success_clones.append({
                "original_segment_code": segment_code,
                "new_segment_code": new_segment_code,
                "segment_name": cloned_segment.get("segment_name"),
                "segment_id": cloned_segment.get("id")
            })

        except Exception as e:
            failed_clones.append({
                "segment_code": segment_code,
                "error": str(e)
            })

    # Return summary
    return {
        "success": success_clones,
        "failed": failed_clones,
        "summary": {
            "total_requested": len(segment_codes),
            "successful": len(success_clones),
            "failed": len(failed_clones),
            "source_consultation_type": source_consultation_type_code,
            "target_consultation_type": target_consultation_type_code
        }
    }


def get_segment_with_parent_info(
    segment_code: str,
    consultation_type_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get a segment along with its parent for comparison.

    Args:
        segment_code: Code of the child segment
        consultation_type_id: Consultation type ID if segment is type-specific

    Returns:
        Dictionary with 'segment', 'parent', and 'relationship' keys

    Raises:
        ValueError: If segment not found
    """
    # Find segment using junction table if consultation_type_id provided
    if consultation_type_id:
        # Get segment_id from junction table
        junction_response = (
            supabase.table("consultation_type_segments")
            .select("segment_id")
            .eq("consultation_type_id", consultation_type_id)
            .eq("segment_code", segment_code)
            .execute()
        )

        if not junction_response.data or len(junction_response.data) == 0:
            raise ValueError(f"Segment '{segment_code}' not found for consultation type {consultation_type_id}")

        segment_id = junction_response.data[0]["segment_id"]

        # Get full segment details
        segment_response = (
            supabase.table("segment_definitions")
            .select("*")
            .eq("id", segment_id)
            .execute()
        )
    else:
        # No consultation_type_id - find segment by code that is NOT assigned to any consultation type
        # First get all segment_ids assigned to consultation types
        assigned_response = (
            supabase.table("consultation_type_segments")
            .select("segment_id")
            .eq("segment_code", segment_code)
            .execute()
        )

        assigned_ids = [row["segment_id"] for row in (assigned_response.data or [])]

        # Get segment with this code that is NOT in the assigned list (base/global segment)
        query = supabase.table("segment_definitions").select("*").eq("segment_code", segment_code)

        if assigned_ids:
            # Exclude segments that are assigned to consultation types
            query = query.not_.in_("id", assigned_ids)

        segment_response = query.execute()

    if not segment_response.data or len(segment_response.data) == 0:
        raise ValueError(f"Segment '{segment_code}' not found")

    segment = segment_response.data[0]
    parent = None
    relationship = {
        "has_parent": False,
        "is_cloned": segment.get("is_cloned_from_parent", False),
        "diverged": segment.get("diverged_from_parent", False),
        "cloned_at": segment.get("cloned_at"),
        "last_sync_at": segment.get("last_parent_sync_at")
    }

    # Get parent if exists (parents are base segments not assigned to consultation types)
    parent_segment_code = segment.get("parent_segment_code")
    if parent_segment_code:
        # Find parent segment (not assigned to any consultation type)
        parent_assigned_response = (
            supabase.table("consultation_type_segments")
            .select("segment_id")
            .eq("segment_code", parent_segment_code)
            .execute()
        )

        parent_assigned_ids = [row["segment_id"] for row in (parent_assigned_response.data or [])]

        parent_query = supabase.table("segment_definitions").select("*").eq("segment_code", parent_segment_code)

        if parent_assigned_ids:
            # Exclude segments assigned to consultation types
            parent_query = parent_query.not_.in_("id", parent_assigned_ids)

        parent_response = parent_query.execute()

        if parent_response.data and len(parent_response.data) > 0:
            parent = parent_response.data[0]
            relationship["has_parent"] = True
            relationship["parent_code"] = parent_segment_code

    return {
        "segment": segment,
        "parent": parent,
        "relationship": relationship
    }


def get_segment_children_list(
    parent_segment_code: str,
    include_diverged: bool = True
) -> List[Dict[str, Any]]:
    """
    Get all child segments that were cloned from a parent.

    Args:
        parent_segment_code: Parent segment code
        include_diverged: If False, only return children that are still in sync

    Returns:
        List of child segments with relationship metadata
    """
    query = (
        supabase.table("segment_definitions")
        .select("*")
        .eq("parent_segment_code", parent_segment_code)
        .order("diverged_from_parent", desc=False)  # In-sync first
        .order("segment_code", desc=False)
    )

    if not include_diverged:
        query = query.eq("diverged_from_parent", False)

    response = query.execute()

    return response.data if response.data else []


def propagate_parent_changes(
    parent_segment_code: str,
    child_segment_codes: List[str],
    force_update_diverged: bool = False,
    updated_by_admin_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Propagate changes from a parent segment to selected child segments.

    Args:
        parent_segment_code: Parent segment code to propagate from
        child_segment_codes: List of child segment codes to update
        force_update_diverged: If True, update even segments that have been manually edited
        updated_by_admin_id: Admin performing the update

    Returns:
        Dictionary with 'updated', 'skipped', and 'errors' lists

    Raises:
        ValueError: If parent segment not found
    """
    # Get the parent segment (not assigned to any consultation type)
    parent_assigned_response = (
        supabase.table("consultation_type_segments")
        .select("segment_id")
        .eq("segment_code", parent_segment_code)
        .execute()
    )

    parent_assigned_ids = [row["segment_id"] for row in (parent_assigned_response.data or [])]

    parent_query = supabase.table("segment_definitions").select("*").eq("segment_code", parent_segment_code)

    if parent_assigned_ids:
        # Exclude segments assigned to consultation types
        parent_query = parent_query.not_.in_("id", parent_assigned_ids)

    parent_response = parent_query.execute()

    if not parent_response.data or len(parent_response.data) == 0:
        raise ValueError(f"Parent segment '{parent_segment_code}' not found")

    parent = parent_response.data[0]

    results = {
        "updated": [],
        "skipped": [],
        "errors": []
    }

    # Update each child segment
    for child_code in child_segment_codes:
        try:
            # Get the child segment
            child_response = (
                supabase.table("segment_definitions")
                .select("*")
                .eq("segment_code", child_code)
                .eq("parent_segment_code", parent_segment_code)
                .execute()
            )

            if not child_response.data or len(child_response.data) == 0:
                results["errors"].append({
                    "segment_code": child_code,
                    "error": "Child segment not found or not a child of this parent"
                })
                continue

            child = child_response.data[0]

            # Check if child has diverged
            if child.get("diverged_from_parent", False) and not force_update_diverged:
                results["skipped"].append({
                    "segment_code": child_code,
                    "reason": "Segment has diverged from parent (use force_update_diverged to override)"
                })
                continue

            # Update child with parent's content
            update_data = {
                "prompt_section_text": parent.get("prompt_section_text"),
                "schema_definition_json": parent.get("schema_definition_json"),
                "last_parent_sync_at": "now()",
                "diverged_from_parent": False,  # Reset divergence flag
            }

            updated_response = (
                supabase.table("segment_definitions")
                .update(update_data)
                .eq("id", child["id"])
                .select()
                .execute()
            )

            if updated_response.data and len(updated_response.data) > 0:
                results["updated"].append({
                    "segment_code": child_code,
                    "synced_at": updated_response.data[0].get("last_parent_sync_at")
                })
            else:
                results["errors"].append({
                    "segment_code": child_code,
                    "error": "Failed to update segment"
                })

        except Exception as e:
            results["errors"].append({
                "segment_code": child_code,
                "error": str(e)
            })

    return results


def sync_segment_from_parent(
    segment_code: str,
    consultation_type_id: Optional[str] = None,
    force_sync: bool = False
) -> Dict[str, Any]:
    """
    Sync a single child segment from its parent.

    Args:
        segment_code: Code of the child segment to sync
        consultation_type_id: Consultation type ID if segment is type-specific
        force_sync: If True, sync even if segment has diverged (loses customizations)

    Returns:
        The updated segment

    Raises:
        ValueError: If segment not found, has no parent, or has diverged (and force_sync=False)
    """
    # Find segment using junction table if consultation_type_id provided
    if consultation_type_id:
        # Get segment_id from junction table
        junction_response = (
            supabase.table("consultation_type_segments")
            .select("segment_id")
            .eq("consultation_type_id", consultation_type_id)
            .eq("segment_code", segment_code)
            .execute()
        )

        if not junction_response.data or len(junction_response.data) == 0:
            raise ValueError(f"Segment '{segment_code}' not found for consultation type {consultation_type_id}")

        segment_id = junction_response.data[0]["segment_id"]

        # Get full segment details
        segment_response = (
            supabase.table("segment_definitions")
            .select("*")
            .eq("id", segment_id)
            .execute()
        )
    else:
        # No consultation_type_id - find segment by code that is NOT assigned to any consultation type
        assigned_response = (
            supabase.table("consultation_type_segments")
            .select("segment_id")
            .eq("segment_code", segment_code)
            .execute()
        )

        assigned_ids = [row["segment_id"] for row in (assigned_response.data or [])]

        query = supabase.table("segment_definitions").select("*").eq("segment_code", segment_code)

        if assigned_ids:
            query = query.not_.in_("id", assigned_ids)

        segment_response = query.execute()

    if not segment_response.data or len(segment_response.data) == 0:
        raise ValueError(f"Segment '{segment_code}' not found")

    segment = segment_response.data[0]

    # Check if segment has a parent
    parent_segment_code = segment.get("parent_segment_code")
    if not parent_segment_code:
        raise ValueError(f"Segment '{segment_code}' has no parent to sync from")

    # Check if segment has diverged
    if segment.get("diverged_from_parent", False) and not force_sync:
        raise ValueError(
            f"Segment '{segment_code}' has diverged from parent. "
            f"Use force_sync=True to sync anyway (this will lose customizations)"
        )

    # Get the parent segment (not assigned to any consultation type)
    parent_assigned_response = (
        supabase.table("consultation_type_segments")
        .select("segment_id")
        .eq("segment_code", parent_segment_code)
        .execute()
    )

    parent_assigned_ids = [row["segment_id"] for row in (parent_assigned_response.data or [])]

    parent_query = supabase.table("segment_definitions").select("*").eq("segment_code", parent_segment_code)

    if parent_assigned_ids:
        parent_query = parent_query.not_.in_("id", parent_assigned_ids)

    parent_response = parent_query.execute()

    if not parent_response.data or len(parent_response.data) == 0:
        raise ValueError(f"Parent segment '{parent_segment_code}' not found")

    parent = parent_response.data[0]

    # Update child with parent's content
    update_data = {
        "prompt_section_text": parent.get("prompt_section_text"),
        "schema_definition_json": parent.get("schema_definition_json"),
        "last_parent_sync_at": "now()",
        "diverged_from_parent": False,  # Reset divergence flag
    }

    updated_response = (
        supabase.table("segment_definitions")
        .update(update_data)
        .eq("id", segment["id"])
        .select()
        .execute()
    )

    if not updated_response.data or len(updated_response.data) == 0:
        raise ValueError("Failed to sync segment from parent")

    return updated_response.data[0]


# ============================================================================
# Segment Assignment Functions (No Duplication)
# ============================================================================

def get_templates_for_consultation_type(consultation_type_id: uuid.UUID) -> List[uuid.UUID]:
    """
    Get all template IDs for a given consultation type.

    Args:
        consultation_type_id: UUID of the consultation type

    Returns:
        List of template UUIDs
    """
    response = (
        supabase.table("templates")
        .select("id")
        .eq("consultation_type_id", str(consultation_type_id))
        .eq("is_active", True)
        .execute()
    )

    return [uuid.UUID(row["id"]) for row in (response.data or [])]


def get_template_by_id(template_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get a template by its UUID.

    Args:
        template_id: Template UUID

    Returns:
        Template record or None if not found
    """
    response = (
        supabase.table("templates")
        .select("*")
        .eq("id", str(template_id))
        .execute()
    )

    return response.data[0] if response.data else None


def check_counsellor_template_access(counsellor_id: uuid.UUID, template_id: uuid.UUID) -> bool:
    """
    Check if a counsellor has access to a template (via counsellor_templates junction).

    Args:
        counsellor_id: Counsellor UUID
        template_id: Template UUID

    Returns:
        True if counsellor has access, False otherwise
    """
    response = (
        supabase.table("counsellor_templates")
        .select("id")
        .eq("counsellor_id", str(counsellor_id))
        .eq("template_id", str(template_id))
        .eq("is_active", True)
        .execute()
    )

    return bool(response.data)


def add_segment_to_template_if_missing(
    template_id: uuid.UUID,
    segment_id: uuid.UUID,
    segment_code: str,
    category: str = "excluded",
    display_order: int = 999,
    brevity_level: str = "balanced",
    terminology_style: str = "medical_terms"
) -> Dict[str, Any]:
    """
    Add segment to template only if not already present.

    Args:
        template_id: Template UUID
        segment_id: Segment UUID
        segment_code: Segment code
        category: Category (core/additional/excluded)
        display_order: Display order
        brevity_level: Brevity level
        terminology_style: Terminology style

    Returns:
        Dict with 'added' boolean and entry details
    """
    # Check if already exists
    existing = (
        supabase.table("template_segments")
        .select("id")
        .eq("template_id", str(template_id))
        .eq("segment_id", str(segment_id))
        .execute()
    )

    if existing.data:
        return {"added": False, "reason": "already_exists", "entry": existing.data[0]}

    # Fetch template to get its name
    template = (
        supabase.table("templates")
        .select("id, template_code, template_name")
        .eq("id", str(template_id))
        .single()
        .execute()
    )
    template_name = template.data.get("template_name") if template.data else None

    # Insert new entry
    data = {
        "template_id": str(template_id),
        "template_name": template_name,
        "segment_id": str(segment_id),
        "segment_code": segment_code,
        "category": category.lower(),
        "display_order": display_order,
        "brevity_level": brevity_level,
        "terminology_style": terminology_style
    }

    result = supabase.table("template_segments").insert(data).execute()
    return {"added": True, "entry": result.data[0] if result.data else None}


def assign_segment_to_consultation_type(
    segment_code: str,
    consultation_type_id: uuid.UUID,
    category: str = "additional",
    display_order: Optional[int] = None,
    brevity_level: str = "balanced",
    terminology_style: str = "medical_terms",
    segment_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Assign an existing segment to a consultation type WITHOUT duplicating segment_definitions.

    This creates a junction entry in consultation_type_segments and auto-syncs
    the segment as 'excluded' to all templates of the consultation type.

    Args:
        segment_code: Code of existing segment in segment_definitions
        consultation_type_id: UUID of consultation type to assign to
        category: Default category (core/additional/excluded)
        display_order: Display order (auto-calculated if None)
        brevity_level: Default brevity level
        terminology_style: Default terminology style
        segment_id: UUID of segment - REQUIRED (segment_code is not unique)

    Returns:
        Dict with junction entry and auto-sync results
    """
    # 1. Require segment_id - segment_code is NOT unique in segment_definitions
    if not segment_id:
        raise ValueError(f"segment_id is required - segment_code '{segment_code}' is not unique in segment_definitions")

    # Fetch segment by ID directly
    segment_response = (
        supabase.table("segment_definitions")
        .select("*")
        .eq("id", str(segment_id))
        .eq("is_active", True)
        .single()
        .execute()
    )
    segment = segment_response.data
    if not segment:
        raise ValueError(f"Segment with ID '{segment_id}' not found or inactive")
    segment_id_str = segment["id"]

    # 1b. Fetch consultation type to get its name
    consultation_type = (
        supabase.table("consultation_types")
        .select("id, type_code, type_name")
        .eq("id", str(consultation_type_id))
        .single()
        .execute()
    )
    consultation_type_name = consultation_type.data.get("type_name") if consultation_type.data else None

    # 2. Check if junction entry already exists
    existing = (
        supabase.table("consultation_type_segments")
        .select("*")
        .eq("consultation_type_id", str(consultation_type_id))
        .eq("segment_id", segment_id_str)
        .execute()
    )

    if existing.data:
        return {
            "success": True,
            "message": "Segment already assigned to consultation type",
            "already_existed": True,
            "junction_entry": existing.data[0],
            "templates_synced": 0,
            "sync_details": []
        }

    # 3. Calculate display_order if not provided
    if display_order is None:
        max_order_response = (
            supabase.table("consultation_type_segments")
            .select("default_display_order")
            .eq("consultation_type_id", str(consultation_type_id))
            .order("default_display_order", desc=True)
            .limit(1)
            .execute()
        )
        max_order = max_order_response.data[0]["default_display_order"] if max_order_response.data else 0
        display_order = max_order + 10

    # 4. INSERT into consultation_type_segments
    junction_data = {
        "consultation_type_id": str(consultation_type_id),
        "consultation_type_name": consultation_type_name,
        "segment_id": segment_id_str,
        "segment_code": segment_code,
        "default_category": category.lower(),
        "default_display_order": display_order,
        "default_brevity_level": brevity_level,
        "default_terminology_style": terminology_style,
        "is_required_for_type": False
    }

    junction_response = supabase.table("consultation_type_segments").insert(junction_data).execute()
    junction_entry = junction_response.data[0] if junction_response.data else None

    logger.info(f"[ASSIGN_SEGMENT] Assigned segment '{segment_code}' to consultation type '{consultation_type_name}' ({consultation_type_id})")

    # 5. AUTO-SYNC: Add segment as 'excluded' to ALL templates of this consultation type
    affected_templates = get_templates_for_consultation_type(consultation_type_id)
    sync_results = []

    for template_id in affected_templates:
        try:
            result = add_segment_to_template_if_missing(
                template_id=template_id,
                segment_id=uuid.UUID(segment_id_str),
                segment_code=segment_code,
                category='excluded',  # Always 'excluded' for auto-sync
                display_order=999,     # Put at end, admin can reorder
                brevity_level=segment.get("default_brevity_level", brevity_level),
                terminology_style=segment.get("default_terminology_style", terminology_style)
            )
            sync_results.append({
                "template_id": str(template_id),
                "added": result.get("added", False),
                "reason": result.get("reason")
            })
            if result.get("added"):
                logger.info(f"[ASSIGN_SEGMENT] Auto-synced segment '{segment_code}' to template {template_id}")
        except Exception as e:
            logger.warning(f"[ASSIGN_SEGMENT] Failed to auto-sync to template {template_id}: {e}")
            sync_results.append({
                "template_id": str(template_id),
                "added": False,
                "error": str(e)
            })

    templates_synced = sum(1 for r in sync_results if r.get("added", False))
    logger.info(f"[ASSIGN_SEGMENT] Auto-synced to {templates_synced}/{len(affected_templates)} templates")

    # HOOK: Trigger reassembly for templates that received the new segment
    if templates_synced > 0:
        try:
            from .template_assembly_service import trigger_reassembly_async
            templates_to_reassemble = [
                uuid.UUID(r["template_id"]) for r in sync_results if r.get("added", False)
            ]
            trigger_source = f"consultation_type_segment:{segment_code}:assign"
            asyncio.create_task(trigger_reassembly_async(templates_to_reassemble, trigger_source))
            logger.info(f"[ASSIGN_SEGMENT] Triggered reassembly for {len(templates_to_reassemble)} templates")
        except Exception as e:
            logger.error(f"[ASSIGN_SEGMENT] Failed to trigger reassembly hook: {e}")

    return {
        "success": True,
        "message": f"Segment '{segment_code}' assigned to consultation type",
        "already_existed": False,
        "junction_entry": junction_entry,
        "templates_synced": templates_synced,
        "sync_details": sync_results
    }


def get_available_segments_for_template(template_id: uuid.UUID) -> Dict[str, Any]:
    """
    Get segments that are in the template's consultation type but NOT in the template.

    Args:
        template_id: Template UUID

    Returns:
        Dict with available_segments list and metadata
    """
    # 1. Get template to find consultation_type_id
    template_response = (
        supabase.table("templates")
        .select("id, template_code, template_name, consultation_type_id")
        .eq("id", str(template_id))
        .execute()
    )

    if not template_response.data:
        raise ValueError(f"Template '{template_id}' not found")

    template = template_response.data[0]
    consultation_type_id = template.get("consultation_type_id")

    if not consultation_type_id:
        raise ValueError(f"Template '{template_id}' has no consultation_type_id")

    # Get consultation type code for response
    ct_response = (
        supabase.table("consultation_types")
        .select("type_code")
        .eq("id", consultation_type_id)
        .execute()
    )
    consultation_type_code = ct_response.data[0]["type_code"] if ct_response.data else "UNKNOWN"

    # 2. Get all segment_ids from consultation_type_segments for this type
    ct_segments_response = (
        supabase.table("consultation_type_segments")
        .select("segment_id, segment_code, default_category, default_display_order, default_brevity_level, default_terminology_style")
        .eq("consultation_type_id", consultation_type_id)
        .execute()
    )
    ct_segment_ids = {row["segment_id"] for row in (ct_segments_response.data or [])}
    ct_segment_data = {row["segment_id"]: row for row in (ct_segments_response.data or [])}

    # 3. Get all segment_ids from template_segments for this template
    ts_response = (
        supabase.table("template_segments")
        .select("segment_id")
        .eq("template_id", str(template_id))
        .execute()
    )
    template_segment_ids = {row["segment_id"] for row in (ts_response.data or [])}

    # 4. Find segments in consultation type but NOT in template
    available_segment_ids = ct_segment_ids - template_segment_ids

    if not available_segment_ids:
        return {
            "template_code": template.get("template_code"),
            "template_name": template.get("template_name"),
            "consultation_type_code": consultation_type_code,
            "available_segments": [],
            "count": 0
        }

    # 5. Get full segment details for available segments
    segments_response = (
        supabase.table("segment_definitions")
        .select("id, segment_code, segment_name, description, default_brevity_level, default_terminology_style")
        .in_("id", list(available_segment_ids))
        .eq("is_active", True)
        .order("segment_name")
        .execute()
    )

    # Combine with consultation type defaults
    available_segments = []
    for seg in (segments_response.data or []):
        ct_data = ct_segment_data.get(seg["id"], {})
        available_segments.append({
            "segment_id": seg["id"],
            "segment_code": seg["segment_code"],
            "segment_name": seg["segment_name"],
            "description": seg.get("description"),
            "default_category": ct_data.get("default_category", "additional"),
            "default_display_order": ct_data.get("default_display_order", 999),
            "default_brevity_level": ct_data.get("default_brevity_level") or seg.get("default_brevity_level", "balanced"),
            "default_terminology_style": ct_data.get("default_terminology_style") or seg.get("default_terminology_style", "medical_terms")
        })

    return {
        "template_code": template.get("template_code"),
        "template_name": template.get("template_name"),
        "consultation_type_code": consultation_type_code,
        "available_segments": available_segments,
        "count": len(available_segments)
    }


def add_segments_to_template_from_type(
    template_id: uuid.UUID,
    segment_codes: Optional[List[str]] = None,
    add_all_missing: bool = False,
    default_category: str = "excluded"
) -> Dict[str, Any]:
    """
    Add individual segments from consultation type to template.

    Does NOT delete existing template_segments - only adds new ones.

    Args:
        template_id: Template UUID
        segment_codes: Specific segment codes to add (optional)
        add_all_missing: If True, add all segments not yet in template
        default_category: Category for new segments (default: 'excluded')

    Returns:
        Dict with added segments and metadata
    """
    # 1. Get available segments
    available_data = get_available_segments_for_template(template_id)
    available_segments = available_data["available_segments"]

    if not available_segments:
        return {
            "success": True,
            "template_code": available_data["template_code"],
            "message": "No segments available to add",
            "segments_added": [],
            "count": 0
        }

    # 2. Filter by segment_codes if provided
    if segment_codes and not add_all_missing:
        available_segments = [s for s in available_segments if s["segment_code"] in segment_codes]
    elif not add_all_missing and not segment_codes:
        return {
            "success": False,
            "error": "Either segment_codes or add_all_missing=True must be provided"
        }

    # 3. Add each segment to template
    segments_added = []
    for seg in available_segments:
        try:
            result = add_segment_to_template_if_missing(
                template_id=template_id,
                segment_id=uuid.UUID(seg["segment_id"]),
                segment_code=seg["segment_code"],
                category=default_category,
                display_order=seg.get("default_display_order", 999),
                brevity_level=seg.get("default_brevity_level", "balanced"),
                terminology_style=seg.get("default_terminology_style", "medical_terms")
            )

            if result.get("added"):
                segments_added.append({
                    "segment_code": seg["segment_code"],
                    "segment_name": seg["segment_name"],
                    "category": default_category
                })
        except Exception as e:
            logger.warning(f"[ADD_SEGMENTS] Failed to add segment {seg['segment_code']}: {e}")

    logger.info(f"[ADD_SEGMENTS] Added {len(segments_added)} segments to template {template_id}")

    # HOOK: Trigger reassembly if any segments were added
    if segments_added:
        try:
            from .template_assembly_service import trigger_reassembly_async
            segment_codes_str = ",".join([s["segment_code"] for s in segments_added[:3]])
            if len(segments_added) > 3:
                segment_codes_str += f"...+{len(segments_added)-3} more"
            trigger_source = f"template_segment:{template_id}:{segment_codes_str}:add_from_type"
            asyncio.create_task(trigger_reassembly_async([template_id], trigger_source))
            logger.info(f"[ADD_SEGMENTS] Triggered reassembly for template {template_id}")
        except Exception as e:
            logger.error(f"[ADD_SEGMENTS] Failed to trigger reassembly hook: {e}")

    return {
        "success": True,
        "template_code": available_data["template_code"],
        "message": f"Added {len(segments_added)} segment(s) to template",
        "segments_added": segments_added,
        "count": len(segments_added)
    }


# =============================================================================
# CLINICAL SEVERITY ASSESSMENT FUNCTIONS
# =============================================================================

def save_clinical_severity_assessment(assessment_data: Dict[str, Any]) -> Optional[uuid.UUID]:
    """
    Save clinical severity assessment to database.

    Args:
        assessment_data: Dict containing:
            - extraction_id: UUID of the extraction
            - student_id: Optional student UUID
            - counsellor_id: Optional counsellor UUID
            - severity_level: LOW, MEDIUM, or HIGH
            - total_score: Numeric score
            - was_overridden: Boolean
            - override_reason: Optional string
            - score_breakdown: JSONB dict
            - contributing_factors: Array of strings
            - input_data: JSONB dict with clinical input
            - calculation_version: Version string

    Returns:
        UUID of saved assessment, or None on error
    """
    try:
        # Get contributing_factors for both columns
        contributing_factors = assessment_data.get("contributing_factors", [])

        result = supabase.table("clinical_severity_assessments").insert({
            "extraction_id": assessment_data["extraction_id"],
            "student_id": assessment_data.get("student_id"),
            "counsellor_id": assessment_data.get("counsellor_id"),
            "consultation_insights_id": assessment_data.get("consultation_insights_id"),
            "severity_level": assessment_data["severity_level"],
            "total_score": assessment_data["total_score"],
            "was_overridden": assessment_data.get("was_overridden", False),
            "override_reason": assessment_data.get("override_reason"),
            "score_breakdown": assessment_data.get("score_breakdown", {}),
            "contributing_factors": contributing_factors,
            "reasons": contributing_factors,  # Human-readable reasons (same as contributing_factors)
            "calculation_version": assessment_data.get("calculation_version", "1.0.0"),
            # Flag columns (passed directly from service)
            "is_surgical": assessment_data.get("is_surgical", False),
            "is_chronic": assessment_data.get("is_chronic", False),
            "is_second_opinion": assessment_data.get("is_second_opinion", False),
            "is_alternate_procedure": assessment_data.get("is_alternate_procedure", False)
        }).execute()

        if result.data and len(result.data) > 0:
            assessment_id = uuid.UUID(result.data[0]["id"])
            logger.info(f"[SEVERITY] Saved assessment {assessment_id} for extraction {assessment_data['extraction_id']}")
            return assessment_id

        return None

    except Exception as e:
        # Handle duplicate constraint (assessment already exists)
        if "unique_severity_extraction" in str(e) or "duplicate key" in str(e).lower():
            logger.warning(f"[SEVERITY] Assessment already exists for extraction {assessment_data['extraction_id']}")
            # Try to get existing assessment ID
            try:
                existing = supabase.table("clinical_severity_assessments").select("id").eq(
                    "extraction_id", assessment_data["extraction_id"]
                ).single().execute()
                if existing.data:
                    return uuid.UUID(existing.data["id"])
            except Exception:
                pass
            return None

        logger.error(f"[SEVERITY] Failed to save assessment: {e}")
        return None


def get_clinical_severity_assessment(extraction_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get clinical severity assessment for an extraction.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        Assessment dict or None if not found
    """
    try:
        result = supabase.table("clinical_severity_assessments").select("*").eq(
            "extraction_id", str(extraction_id)
        ).single().execute()

        if result.data:
            return result.data
        return None

    except Exception as e:
        if "No rows" not in str(e) and "0 rows" not in str(e):
            logger.error(f"[SEVERITY] Failed to get assessment for extraction {extraction_id}: {e}")
        return None


def get_student_severity_history(
    student_id: uuid.UUID,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get clinical severity assessment history for a student.

    Args:
        student_id: Student UUID
        limit: Maximum number of records to return

    Returns:
        List of assessment dicts, ordered by created_at descending
    """
    try:
        result = supabase.table("clinical_severity_assessments").select(
            "*, extractions(id, created_at, consultation_type_id)"
        ).eq(
            "student_id", str(student_id)
        ).order(
            "created_at", desc=True
        ).limit(limit).execute()

        return result.data if result.data else []

    except Exception as e:
        logger.error(f"[SEVERITY] Failed to get severity history for student {student_id}: {e}")
        return []


def get_severity_statistics(
    counsellor_id: Optional[uuid.UUID] = None,
    days: int = 30
) -> Dict[str, Any]:
    """
    Get aggregate severity statistics.

    Args:
        counsellor_id: Optional filter by counsellor
        days: Number of days to look back

    Returns:
        Dict with counts by severity level
    """
    try:
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        query = supabase.table("clinical_severity_assessments").select(
            "severity_level"
        ).gte("created_at", cutoff)

        if counsellor_id:
            query = query.eq("counsellor_id", str(counsellor_id))

        result = query.execute()

        if not result.data:
            return {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "total": 0}

        counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
        for row in result.data:
            level = row.get("severity_level", "LOW")
            counts[level] = counts.get(level, 0) + 1

        return {
            **counts,
            "total": len(result.data),
            "period_days": days
        }

    except Exception as e:
        logger.error(f"[SEVERITY] Failed to get statistics: {e}")
        return {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "total": 0, "error": str(e)}


def get_clinical_severity_by_extraction(extraction_id: str) -> Optional[Dict[str, Any]]:
    """
    Get clinical severity assessment by extraction ID (string version).

    Used by other_clinical_needs_service to get is_chronic flag.

    Args:
        extraction_id: Extraction UUID as string

    Returns:
        Assessment dict or None if not found
    """
    try:
        result = supabase.table("clinical_severity_assessments").select("*").eq(
            "extraction_id", extraction_id
        ).single().execute()

        if result.data:
            return result.data
        return None

    except Exception as e:
        if "No rows" not in str(e) and "0 rows" not in str(e):
            logger.error(f"[SEVERITY] Failed to get assessment for extraction {extraction_id}: {e}")
        return None


# =============================================================================
# OTHER CLINICAL NEEDS
# =============================================================================

def save_other_clinical_needs(needs_data: Dict[str, Any]) -> Optional[uuid.UUID]:
    """
    Save other clinical needs assessment to database.

    Args:
        needs_data: Dict containing:
            - extraction_id: UUID of the extraction
            - student_id: Optional student UUID
            - counsellor_id: Optional counsellor UUID
            - is_followup_diagnostics: Boolean
            - is_recurring_diagnostics: Boolean
            - is_rx_refill: Boolean
            - followup_diagnostics_reasons: Array of strings
            - recurring_diagnostics_reasons: Array of strings
            - rx_refill_reasons: Array of strings
            - input_data: JSONB dict
            - clinical_severity_id: Optional UUID reference
            - calculation_version: Version string

    Returns:
        UUID of saved assessment, or None on error
    """
    try:
        result = supabase.table("other_clinical_needs").insert({
            "extraction_id": needs_data["extraction_id"],
            "student_id": needs_data.get("student_id"),
            "counsellor_id": needs_data.get("counsellor_id"),
            "consultation_insights_id": needs_data.get("consultation_insights_id"),
            "priority_level": needs_data.get("priority_level", "NONE"),
            "is_followup_diagnostics": needs_data.get("is_followup_diagnostics", False),
            "is_recurring_diagnostics": needs_data.get("is_recurring_diagnostics", False),
            "is_rx_refill": needs_data.get("is_rx_refill", False),
            "followup_diagnostics_reasons": needs_data.get("followup_diagnostics_reasons", []),
            "recurring_diagnostics_reasons": needs_data.get("recurring_diagnostics_reasons", []),
            "rx_refill_reasons": needs_data.get("rx_refill_reasons", []),
            "clinical_severity_id": needs_data.get("clinical_severity_id"),
            "calculation_version": needs_data.get("calculation_version", "2.0.0")
        }).execute()

        if result.data and len(result.data) > 0:
            needs_id = uuid.UUID(result.data[0]["id"])
            logger.info(f"[CLINICAL_NEEDS] Saved assessment {needs_id} for extraction {needs_data['extraction_id']}")
            return needs_id

        return None

    except Exception as e:
        # Handle duplicate constraint
        if "unique_needs_extraction" in str(e) or "duplicate key" in str(e).lower():
            logger.warning(f"[CLINICAL_NEEDS] Assessment already exists for extraction {needs_data['extraction_id']}")
            try:
                existing = supabase.table("other_clinical_needs").select("id").eq(
                    "extraction_id", needs_data["extraction_id"]
                ).single().execute()
                if existing.data:
                    return uuid.UUID(existing.data["id"])
            except Exception:
                pass
            return None

        logger.error(f"[CLINICAL_NEEDS] Failed to save assessment: {e}")
        return None


def get_clinical_needs_by_extraction(extraction_id: str) -> Optional[Dict[str, Any]]:
    """
    Get other clinical needs for an extraction.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        Needs dict or None if not found
    """
    try:
        result = supabase.table("other_clinical_needs").select("*").eq(
            "extraction_id", extraction_id
        ).single().execute()

        if result.data:
            return result.data
        return None

    except Exception as e:
        if "No rows" not in str(e) and "0 rows" not in str(e):
            logger.error(f"[CLINICAL_NEEDS] Failed to get needs for extraction {extraction_id}: {e}")
        return None


def get_student_clinical_needs_history(
    student_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get clinical needs history for a student.

    Args:
        student_id: Student UUID
        limit: Maximum number of records to return

    Returns:
        List of needs dicts, ordered by created_at descending
    """
    try:
        result = supabase.table("other_clinical_needs").select(
            "*, extractions(id, created_at, consultation_type_id)"
        ).eq(
            "student_id", student_id
        ).order(
            "created_at", desc=True
        ).limit(limit).execute()

        return result.data if result.data else []

    except Exception as e:
        logger.error(f"[CLINICAL_NEEDS] Failed to get needs history for student {student_id}: {e}")
        return []


def get_student_latest_clinical_needs(student_id: str) -> Optional[Dict[str, Any]]:
    """
    Get latest clinical needs assessment for a student.

    Args:
        student_id: Student UUID

    Returns:
        Most recent needs dict or None
    """
    try:
        result = supabase.table("other_clinical_needs").select("*").eq(
            "student_id", student_id
        ).order(
            "created_at", desc=True
        ).limit(1).execute()

        if result.data and len(result.data) > 0:
            return result.data[0]
        return None

    except Exception as e:
        logger.error(f"[CLINICAL_NEEDS] Failed to get latest needs for student {student_id}: {e}")
        return None


def get_clinical_needs_statistics(
    counsellor_id: Optional[str] = None,
    days: int = 30
) -> Dict[str, Any]:
    """
    Get aggregate clinical needs statistics.

    Args:
        counsellor_id: Optional filter by counsellor
        days: Number of days to look back

    Returns:
        Dict with counts for each indicator
    """
    try:
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        query = supabase.table("other_clinical_needs").select(
            "is_followup_diagnostics, is_recurring_diagnostics, is_rx_refill"
        ).gte("created_at", cutoff)

        if counsellor_id:
            query = query.eq("counsellor_id", counsellor_id)

        result = query.execute()

        if not result.data:
            return {
                "followup_diagnostics": 0,
                "recurring_diagnostics": 0,
                "rx_refill": 0,
                "total": 0,
                "period_days": days
            }

        counts = {
            "followup_diagnostics": 0,
            "recurring_diagnostics": 0,
            "rx_refill": 0
        }
        for row in result.data:
            if row.get("is_followup_diagnostics"):
                counts["followup_diagnostics"] += 1
            if row.get("is_recurring_diagnostics"):
                counts["recurring_diagnostics"] += 1
            if row.get("is_rx_refill"):
                counts["rx_refill"] += 1

        return {
            **counts,
            "total": len(result.data),
            "period_days": days
        }

    except Exception as e:
        logger.error(f"[CLINICAL_NEEDS] Failed to get statistics: {e}")
        return {
            "followup_diagnostics": 0,
            "recurring_diagnostics": 0,
            "rx_refill": 0,
            "total": 0,
            "error": str(e)
        }


# =============================================================================
# ALLIED HEALTH NEEDS OPERATIONS
# =============================================================================

def save_allied_health_needs(needs_data: Dict[str, Any]) -> Optional[uuid.UUID]:
    """
    Save allied health needs assessment to database.

    Args:
        needs_data: Dict containing all 9 boolean indicators and reasons

    Returns:
        UUID of saved assessment, or None on error
    """
    try:
        result = supabase.table("allied_health_needs").insert({
            "extraction_id": needs_data["extraction_id"],
            "student_id": needs_data.get("student_id"),
            "counsellor_id": needs_data.get("counsellor_id"),
            "consultation_insights_id": needs_data.get("consultation_insights_id"),
            "priority_level": needs_data.get("priority_level", "NONE"),
            "is_mental_health": needs_data.get("is_mental_health", False),
            "is_nutritional_health": needs_data.get("is_nutritional_health", False),
            "is_physiotherapy": needs_data.get("is_physiotherapy", False),
            "is_homecare": needs_data.get("is_homecare", False),
            "is_sleep_therapy": needs_data.get("is_sleep_therapy", False),
            "is_rehab_cardiac": needs_data.get("is_rehab_cardiac", False),
            "is_rehab_common": needs_data.get("is_rehab_common", False),
            "is_treatment_education": needs_data.get("is_treatment_education", False),
            "is_wellness": needs_data.get("is_wellness", False),
            "mental_health_reasons": needs_data.get("mental_health_reasons", []),
            "nutritional_health_reasons": needs_data.get("nutritional_health_reasons", []),
            "physiotherapy_reasons": needs_data.get("physiotherapy_reasons", []),
            "homecare_reasons": needs_data.get("homecare_reasons", []),
            "sleep_therapy_reasons": needs_data.get("sleep_therapy_reasons", []),
            "rehab_cardiac_reasons": needs_data.get("rehab_cardiac_reasons", []),
            "rehab_common_reasons": needs_data.get("rehab_common_reasons", []),
            "treatment_education_reasons": needs_data.get("treatment_education_reasons", []),
            "wellness_reasons": needs_data.get("wellness_reasons", []),
            "clinical_severity_id": needs_data.get("clinical_severity_id"),
            "other_clinical_needs_id": needs_data.get("other_clinical_needs_id"),
            "calculation_version": needs_data.get("calculation_version", "2.0.0")
        }).execute()

        if result.data and len(result.data) > 0:
            needs_id = uuid.UUID(result.data[0]["id"])
            logger.info(f"[ALLIED_HEALTH] Saved assessment {needs_id} for extraction {needs_data['extraction_id']}")
            return needs_id

        return None

    except Exception as e:
        # Handle duplicate constraint
        if "unique_allied_needs_extraction" in str(e) or "duplicate key" in str(e).lower():
            logger.warning(f"[ALLIED_HEALTH] Assessment already exists for extraction {needs_data['extraction_id']}")
            try:
                existing = supabase.table("allied_health_needs").select("id").eq(
                    "extraction_id", needs_data["extraction_id"]
                ).single().execute()
                if existing.data:
                    return uuid.UUID(existing.data["id"])
            except Exception:
                pass
            return None

        logger.error(f"[ALLIED_HEALTH] Failed to save assessment: {e}")
        return None


def get_allied_health_by_extraction(extraction_id: str) -> Optional[Dict[str, Any]]:
    """
    Get allied health needs assessment for an extraction.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        Allied health assessment dict or None
    """
    try:
        result = supabase.table("allied_health_needs").select("*").eq(
            "extraction_id", extraction_id
        ).single().execute()

        return result.data if result.data else None

    except Exception as e:
        if "PGRST116" not in str(e):  # Not a "not found" error
            logger.error(f"[ALLIED_HEALTH] Failed to get by extraction: {e}")
        return None


def get_student_allied_health_history(
    student_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get student's allied health needs history.

    Args:
        student_id: UUID of the student
        limit: Maximum records to return

    Returns:
        List of allied health assessments, newest first
    """
    try:
        result = supabase.table("allied_health_needs").select(
            "*, extractions(created_at)"
        ).eq(
            "student_id", student_id
        ).order(
            "created_at", desc=True
        ).limit(limit).execute()

        return result.data if result.data else []

    except Exception as e:
        logger.error(f"[ALLIED_HEALTH] Failed to get student history: {e}")
        return []


def get_student_latest_allied_health(student_id: str) -> Optional[Dict[str, Any]]:
    """
    Get most recent allied health assessment for a student.

    Args:
        student_id: UUID of the student

    Returns:
        Latest allied health assessment or None
    """
    try:
        result = supabase.table("allied_health_needs").select("*").eq(
            "student_id", student_id
        ).order(
            "created_at", desc=True
        ).limit(1).execute()

        if result.data and len(result.data) > 0:
            return result.data[0]
        return None

    except Exception as e:
        logger.error(f"[ALLIED_HEALTH] Failed to get latest for student: {e}")
        return None


def get_allied_health_statistics(
    counsellor_id: Optional[str] = None,
    days: int = 30
) -> Dict[str, Any]:
    """
    Get aggregate allied health statistics.

    Args:
        counsellor_id: Optional filter by counsellor
        days: Number of days to look back

    Returns:
        Dict with counts for each indicator type
    """
    try:
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        query = supabase.table("allied_health_needs").select(
            "is_mental_health, is_nutritional_health, is_physiotherapy, "
            "is_homecare, is_sleep_therapy, is_rehab_cardiac, is_rehab_common, "
            "is_treatment_education, is_wellness"
        ).gte("created_at", cutoff)

        if counsellor_id:
            query = query.eq("counsellor_id", counsellor_id)

        result = query.execute()

        if not result.data:
            return {
                "mental_health": 0,
                "nutritional_health": 0,
                "physiotherapy": 0,
                "homecare": 0,
                "sleep_therapy": 0,
                "rehab_cardiac": 0,
                "rehab_common": 0,
                "treatment_education": 0,
                "wellness": 0,
                "total": 0,
                "period_days": days
            }

        counts = {
            "mental_health": 0,
            "nutritional_health": 0,
            "physiotherapy": 0,
            "homecare": 0,
            "sleep_therapy": 0,
            "rehab_cardiac": 0,
            "rehab_common": 0,
            "treatment_education": 0,
            "wellness": 0
        }
        for row in result.data:
            if row.get("is_mental_health"):
                counts["mental_health"] += 1
            if row.get("is_nutritional_health"):
                counts["nutritional_health"] += 1
            if row.get("is_physiotherapy"):
                counts["physiotherapy"] += 1
            if row.get("is_homecare"):
                counts["homecare"] += 1
            if row.get("is_sleep_therapy"):
                counts["sleep_therapy"] += 1
            if row.get("is_rehab_cardiac"):
                counts["rehab_cardiac"] += 1
            if row.get("is_rehab_common"):
                counts["rehab_common"] += 1
            if row.get("is_treatment_education"):
                counts["treatment_education"] += 1
            if row.get("is_wellness"):
                counts["wellness"] += 1

        return {
            **counts,
            "total": len(result.data),
            "period_days": days
        }

    except Exception as e:
        logger.error(f"[ALLIED_HEALTH] Failed to get statistics: {e}")
        return {
            "mental_health": 0,
            "nutritional_health": 0,
            "physiotherapy": 0,
            "homecare": 0,
            "sleep_therapy": 0,
            "rehab_cardiac": 0,
            "rehab_common": 0,
            "treatment_education": 0,
            "wellness": 0,
            "total": 0,
            "error": str(e)
        }


def get_other_clinical_needs_by_extraction(extraction_id: str) -> Optional[Dict[str, Any]]:
    """
    Get other clinical needs assessment for an extraction.
    Alias for get_clinical_needs_by_extraction.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        Other clinical needs assessment dict or None
    """
    return get_clinical_needs_by_extraction(extraction_id)


# ============================================================================
# Student Dropoff Risk Functions
# ============================================================================

def save_student_dropoff_risk(risk_data: Dict[str, Any]) -> Optional[uuid.UUID]:
    """
    Save student dropoff risk assessment to database.

    Args:
        risk_data: Dict containing dropoff probability, risk level, and 5 indicators

    Returns:
        UUID of saved assessment, or None on error
    """
    try:
        # Get individual reason arrays
        financial_reasons = risk_data.get("financial_risk_reasons", [])
        competitor_reasons = risk_data.get("competitor_risk_reasons", [])
        dissatisfaction_reasons = risk_data.get("dissatisfaction_risk_reasons", [])
        access_reasons = risk_data.get("access_risk_reasons", [])
        compliance_reasons = risk_data.get("compliance_risk_reasons", [])

        # Build consolidated reasons array with indicator prefixes for clarity
        consolidated_reasons = []
        if financial_reasons:
            consolidated_reasons.extend([f"[Financial] {r}" for r in financial_reasons])
        if competitor_reasons:
            consolidated_reasons.extend([f"[Competitor] {r}" for r in competitor_reasons])
        if dissatisfaction_reasons:
            consolidated_reasons.extend([f"[Dissatisfaction] {r}" for r in dissatisfaction_reasons])
        if access_reasons:
            consolidated_reasons.extend([f"[Access] {r}" for r in access_reasons])
        if compliance_reasons:
            consolidated_reasons.extend([f"[Compliance] {r}" for r in compliance_reasons])

        result = supabase.table("student_dropoff_risk").insert({
            "extraction_id": risk_data["extraction_id"],
            "student_id": risk_data.get("student_id"),
            "counsellor_id": risk_data.get("counsellor_id"),
            "consultation_insights_id": risk_data.get("consultation_insights_id"),
            "dropoff_probability": risk_data["dropoff_probability"],
            "risk_level": risk_data["risk_level"],
            "is_financial_risk": risk_data.get("is_financial_risk", False),
            "is_competitor_risk": risk_data.get("is_competitor_risk", False),
            "is_dissatisfaction_risk": risk_data.get("is_dissatisfaction_risk", False),
            "is_access_risk": risk_data.get("is_access_risk", False),
            "is_compliance_risk": risk_data.get("is_compliance_risk", False),
            "financial_risk_reasons": financial_reasons,
            "competitor_risk_reasons": competitor_reasons,
            "dissatisfaction_risk_reasons": dissatisfaction_reasons,
            "access_risk_reasons": access_reasons,
            "compliance_risk_reasons": compliance_reasons,
            "reasons": consolidated_reasons,  # Consolidated human-readable reasons
            "anxiety_pre_level": risk_data.get("anxiety_pre_level"),
            "anxiety_post_level": risk_data.get("anxiety_post_level"),
            "anxiety_trajectory": risk_data.get("anxiety_trajectory"),
            "anxiety_modifier": risk_data.get("anxiety_modifier"),
            "compliance_likelihood": risk_data.get("compliance_likelihood"),
            "compliance_modifier": risk_data.get("compliance_modifier"),
            "base_probability": risk_data.get("base_probability"),
            "indicator_count": risk_data.get("indicator_count"),
            "primary_risk_driver": risk_data.get("primary_risk_driver"),
            "calculation_version": risk_data.get("calculation_version", "2.0.0")
        }).execute()

        if result.data and len(result.data) > 0:
            risk_id = uuid.UUID(result.data[0]["id"])
            logger.info(f"[DROPOFF_RISK] Saved assessment {risk_id} for extraction {risk_data['extraction_id']}")
            return risk_id

        return None

    except Exception as e:
        # Handle duplicate constraint
        if "unique_dropoff_extraction" in str(e) or "duplicate key" in str(e).lower():
            logger.warning(f"[DROPOFF_RISK] Assessment already exists for extraction {risk_data['extraction_id']}")
            try:
                existing = supabase.table("student_dropoff_risk").select("id").eq(
                    "extraction_id", risk_data["extraction_id"]
                ).single().execute()
                if existing.data:
                    return uuid.UUID(existing.data["id"])
            except Exception:
                pass
            return None

        logger.error(f"[DROPOFF_RISK] Failed to save assessment: {e}")
        return None


def get_dropoff_risk_by_extraction(extraction_id: str) -> Optional[Dict[str, Any]]:
    """
    Get student dropoff risk assessment for an extraction.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        Dropoff risk assessment dict or None
    """
    try:
        result = supabase.table("student_dropoff_risk").select("*").eq(
            "extraction_id", extraction_id
        ).single().execute()

        return result.data if result.data else None

    except Exception as e:
        if "PGRST116" not in str(e):  # Not a "not found" error
            logger.error(f"[DROPOFF_RISK] Failed to get by extraction: {e}")
        return None


def get_student_dropoff_history(
    student_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get student's dropoff risk assessment history.

    Args:
        student_id: UUID of the student
        limit: Maximum records to return

    Returns:
        List of dropoff risk assessments, newest first
    """
    try:
        result = supabase.table("student_dropoff_risk").select(
            "*, extractions(created_at)"
        ).eq(
            "student_id", student_id
        ).order(
            "created_at", desc=True
        ).limit(limit).execute()

        return result.data if result.data else []

    except Exception as e:
        logger.error(f"[DROPOFF_RISK] Failed to get student history: {e}")
        return []


def get_student_latest_dropoff_risk(student_id: str) -> Optional[Dict[str, Any]]:
    """
    Get most recent dropoff risk assessment for a student.

    Args:
        student_id: UUID of the student

    Returns:
        Latest dropoff risk assessment or None
    """
    try:
        result = supabase.table("student_dropoff_risk").select("*").eq(
            "student_id", student_id
        ).order(
            "created_at", desc=True
        ).limit(1).execute()

        if result.data and len(result.data) > 0:
            return result.data[0]
        return None

    except Exception as e:
        logger.error(f"[DROPOFF_RISK] Failed to get latest for student: {e}")
        return None


def get_high_risk_students(
    counsellor_id: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get students with HIGH or CRITICAL dropoff risk.

    Args:
        counsellor_id: Optional filter by counsellor
        limit: Maximum records to return

    Returns:
        List of high risk students with their assessments
    """
    try:
        query = supabase.table("student_dropoff_risk").select(
            "*, extractions(created_at)"
        ).in_(
            "risk_level", ["HIGH", "CRITICAL"]
        ).order(
            "dropoff_probability", desc=True
        ).limit(limit)

        if counsellor_id:
            query = query.eq("counsellor_id", counsellor_id)

        result = query.execute()

        return result.data if result.data else []

    except Exception as e:
        logger.error(f"[DROPOFF_RISK] Failed to get high risk students: {e}")
        return []


def get_dropoff_risk_statistics(
    counsellor_id: Optional[str] = None,
    days: int = 30
) -> Dict[str, Any]:
    """
    Get aggregate dropoff risk statistics.

    Args:
        counsellor_id: Optional filter by counsellor
        days: Number of days to look back

    Returns:
        Dict with counts and average probability
    """
    try:
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        query = supabase.table("student_dropoff_risk").select(
            "risk_level, dropoff_probability, is_financial_risk, is_competitor_risk, "
            "is_dissatisfaction_risk, is_access_risk, is_compliance_risk"
        ).gte("created_at", cutoff)

        if counsellor_id:
            query = query.eq("counsellor_id", counsellor_id)

        result = query.execute()

        if not result.data:
            return {
                "total_assessments": 0,
                "low_count": 0,
                "medium_count": 0,
                "high_count": 0,
                "critical_count": 0,
                "average_probability": 0.0,
                "indicator_counts": {
                    "financial_risk": 0,
                    "competitor_risk": 0,
                    "dissatisfaction_risk": 0,
                    "access_risk": 0,
                    "compliance_risk": 0
                },
                "period_days": days
            }

        # Calculate statistics
        risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        indicator_counts = {
            "financial_risk": 0,
            "competitor_risk": 0,
            "dissatisfaction_risk": 0,
            "access_risk": 0,
            "compliance_risk": 0
        }
        total_probability = 0.0

        for row in result.data:
            risk_level = row.get("risk_level", "LOW")
            if risk_level in risk_counts:
                risk_counts[risk_level] += 1

            total_probability += float(row.get("dropoff_probability", 0))

            if row.get("is_financial_risk"):
                indicator_counts["financial_risk"] += 1
            if row.get("is_competitor_risk"):
                indicator_counts["competitor_risk"] += 1
            if row.get("is_dissatisfaction_risk"):
                indicator_counts["dissatisfaction_risk"] += 1
            if row.get("is_access_risk"):
                indicator_counts["access_risk"] += 1
            if row.get("is_compliance_risk"):
                indicator_counts["compliance_risk"] += 1

        total = len(result.data)
        avg_probability = round(total_probability / total, 2) if total > 0 else 0.0

        return {
            "total_assessments": total,
            "low_count": risk_counts["LOW"],
            "medium_count": risk_counts["MEDIUM"],
            "high_count": risk_counts["HIGH"],
            "critical_count": risk_counts["CRITICAL"],
            "average_probability": avg_probability,
            "indicator_counts": indicator_counts,
            "period_days": days
        }

    except Exception as e:
        logger.error(f"[DROPOFF_RISK] Failed to get statistics: {e}")
        return {
            "total_assessments": 0,
            "low_count": 0,
            "medium_count": 0,
            "high_count": 0,
            "critical_count": 0,
            "average_probability": 0.0,
            "indicator_counts": {
                "financial_risk": 0,
                "competitor_risk": 0,
                "dissatisfaction_risk": 0,
                "access_risk": 0,
                "compliance_risk": 0
            },
            "error": str(e)
        }


# =============================================================================
# TRIAGE SUGGESTION FUNCTIONS
# =============================================================================

def get_triage_suggestions_by_extraction(extraction_id: str) -> List[Dict[str, Any]]:
    """
    Get all triage suggestions for an extraction from triage_suggestion_log.

    Args:
        extraction_id: UUID of the extraction (as string)

    Returns:
        List of triage suggestion records
    """
    try:
        result = supabase.table("triage_suggestion_log").select("*").eq(
            "extraction_id", extraction_id
        ).order("priority_rank").execute()

        return result.data if result.data else []

    except Exception as e:
        logger.error(f"[TRIAGE] Failed to get suggestions by extraction: {e}")
        return []


# =============================================================================
# CARE QUALITY RISK FUNCTIONS
# =============================================================================

def save_care_quality_risk(risk_data: Dict[str, Any]) -> Optional[uuid.UUID]:
    """
    Save care quality risk assessment to database.

    Args:
        risk_data: Dict containing:
            - extraction_id: Required UUID
            - student_id: Optional UUID
            - counsellor_id: Optional UUID
            - care_quality_score: 0-100 score
            - risk_level: LOW/MEDIUM/HIGH/CRITICAL
            - is_medication_issue: Boolean
            - is_missed_red_flag: Boolean
            - is_incomplete_treatment: Boolean
            - is_followup_gap: Boolean
            - medication_issue_reasons: Array of strings
            - missed_red_flag_reasons: Array of strings
            - incomplete_treatment_reasons: Array of strings
            - followup_gap_reasons: Array of strings
            - medication_issue_severity: LOW/MEDIUM/HIGH
            - missed_red_flag_severity: LOW/MEDIUM/HIGH
            - incomplete_treatment_severity: LOW/MEDIUM/HIGH
            - followup_gap_severity: LOW/MEDIUM/HIGH
            - reasons: Consolidated array of all reasons
            - base_score: Pre-modifier score
            - indicator_count: Number of triggered indicators
            - primary_risk_driver: Which indicator had highest severity
            - input_data: JSONB of input data for audit
            - calculation_version: Version string

    Returns:
        UUID of saved assessment or None on error
    """
    try:
        result = supabase.table("care_quality_risk").insert({
            "extraction_id": risk_data["extraction_id"],
            "student_id": risk_data.get("student_id"),
            "counsellor_id": risk_data.get("counsellor_id"),
            "care_quality_score": risk_data["care_quality_score"],
            "risk_level": risk_data["risk_level"],
            "is_medication_issue": risk_data.get("is_medication_issue", False),
            "is_missed_red_flag": risk_data.get("is_missed_red_flag", False),
            "is_incomplete_treatment": risk_data.get("is_incomplete_treatment", False),
            "is_followup_gap": risk_data.get("is_followup_gap", False),
            "medication_issue_reasons": risk_data.get("medication_issue_reasons", []),
            "missed_red_flag_reasons": risk_data.get("missed_red_flag_reasons", []),
            "incomplete_treatment_reasons": risk_data.get("incomplete_treatment_reasons", []),
            "followup_gap_reasons": risk_data.get("followup_gap_reasons", []),
            "medication_issue_severity": risk_data.get("medication_issue_severity"),
            "missed_red_flag_severity": risk_data.get("missed_red_flag_severity"),
            "incomplete_treatment_severity": risk_data.get("incomplete_treatment_severity"),
            "followup_gap_severity": risk_data.get("followup_gap_severity"),
            "reasons": risk_data.get("reasons", []),
            "base_score": risk_data.get("base_score"),
            "indicator_count": risk_data.get("indicator_count"),
            "primary_risk_driver": risk_data.get("primary_risk_driver"),
            "input_data": risk_data.get("input_data", {}),
            "calculation_version": risk_data.get("calculation_version", "1.0.0")
        }).execute()

        if result.data:
            saved_id = uuid.UUID(result.data[0]["id"])
            logger.info(f"[CARE_QUALITY] Saved assessment {saved_id} for extraction {risk_data['extraction_id']}")
            return saved_id

        return None

    except Exception as e:
        # Handle duplicate constraint
        if "unique_care_quality_extraction" in str(e) or "duplicate key" in str(e).lower():
            logger.warning(f"[CARE_QUALITY] Assessment already exists for extraction {risk_data['extraction_id']}")
            try:
                existing = supabase.table("care_quality_risk").select("id").eq(
                    "extraction_id", risk_data["extraction_id"]
                ).single().execute()
                if existing.data:
                    return uuid.UUID(existing.data["id"])
            except Exception:
                pass
            return None

        logger.error(f"[CARE_QUALITY] Failed to save assessment: {e}")
        return None


def get_care_quality_by_extraction(extraction_id: str) -> Optional[Dict[str, Any]]:
    """
    Get care quality risk assessment for an extraction.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        Care quality assessment dict or None
    """
    try:
        result = supabase.table("care_quality_risk").select("*").eq(
            "extraction_id", extraction_id
        ).single().execute()

        return result.data if result.data else None

    except Exception as e:
        if "PGRST116" not in str(e):  # Not a "not found" error
            logger.error(f"[CARE_QUALITY] Failed to get by extraction: {e}")
        return None


def get_student_care_quality_history(
    student_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get student's care quality risk assessment history.

    Args:
        student_id: UUID of the student
        limit: Maximum records to return

    Returns:
        List of care quality assessments, newest first
    """
    try:
        result = supabase.table("care_quality_risk").select(
            "*, extractions(created_at)"
        ).eq(
            "student_id", student_id
        ).order(
            "created_at", desc=True
        ).limit(limit).execute()

        return result.data if result.data else []

    except Exception as e:
        logger.error(f"[CARE_QUALITY] Failed to get student history: {e}")
        return []


def get_high_risk_care_quality(
    counsellor_id: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get extractions with HIGH or CRITICAL care quality risk.

    Args:
        counsellor_id: Optional filter by counsellor
        limit: Maximum records to return

    Returns:
        List of high risk extractions with their assessments
    """
    try:
        query = supabase.table("care_quality_risk").select(
            "*, extractions(created_at)"
        ).in_(
            "risk_level", ["HIGH", "CRITICAL"]
        ).order(
            "care_quality_score", desc=True
        ).limit(limit)

        if counsellor_id:
            query = query.eq("counsellor_id", counsellor_id)

        result = query.execute()

        return result.data if result.data else []

    except Exception as e:
        logger.error(f"[CARE_QUALITY] Failed to get high risk extractions: {e}")
        return []


def get_care_quality_statistics(
    counsellor_id: Optional[str] = None,
    days: int = 30
) -> Dict[str, Any]:
    """
    Get aggregate care quality risk statistics.

    Args:
        counsellor_id: Optional filter by counsellor
        days: Number of days to look back

    Returns:
        Dict with counts, average score, and indicator breakdowns
    """
    try:
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        query = supabase.table("care_quality_risk").select(
            "risk_level, care_quality_score, is_medication_issue, is_missed_red_flag, "
            "is_incomplete_treatment, is_followup_gap"
        ).gte("created_at", cutoff)

        if counsellor_id:
            query = query.eq("counsellor_id", counsellor_id)

        result = query.execute()

        if not result.data:
            return {
                "total_assessments": 0,
                "low_count": 0,
                "medium_count": 0,
                "high_count": 0,
                "critical_count": 0,
                "average_score": 0.0,
                "indicator_counts": {
                    "medication_issue": 0,
                    "missed_red_flag": 0,
                    "incomplete_treatment": 0,
                    "followup_gap": 0
                },
                "period_days": days
            }

        # Calculate statistics
        risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        indicator_counts = {
            "medication_issue": 0,
            "missed_red_flag": 0,
            "incomplete_treatment": 0,
            "followup_gap": 0
        }
        total_score = 0.0

        for row in result.data:
            risk_level = row.get("risk_level", "LOW")
            if risk_level in risk_counts:
                risk_counts[risk_level] += 1

            total_score += float(row.get("care_quality_score", 0))

            if row.get("is_medication_issue"):
                indicator_counts["medication_issue"] += 1
            if row.get("is_missed_red_flag"):
                indicator_counts["missed_red_flag"] += 1
            if row.get("is_incomplete_treatment"):
                indicator_counts["incomplete_treatment"] += 1
            if row.get("is_followup_gap"):
                indicator_counts["followup_gap"] += 1

        total = len(result.data)
        avg_score = round(total_score / total, 2) if total > 0 else 0.0

        return {
            "total_assessments": total,
            "low_count": risk_counts["LOW"],
            "medium_count": risk_counts["MEDIUM"],
            "high_count": risk_counts["HIGH"],
            "critical_count": risk_counts["CRITICAL"],
            "average_score": avg_score,
            "indicator_counts": indicator_counts,
            "period_days": days
        }

    except Exception as e:
        logger.error(f"[CARE_QUALITY] Failed to get statistics: {e}")
        return {
            "total_assessments": 0,
            "low_count": 0,
            "medium_count": 0,
            "high_count": 0,
            "critical_count": 0,
            "average_score": 0.0,
            "indicator_counts": {
                "medication_issue": 0,
                "missed_red_flag": 0,
                "incomplete_treatment": 0,
                "followup_gap": 0
            },
            "error": str(e)
        }


# =============================================================================
# CONSULTATION INSIGHTS
# =============================================================================

def save_consultation_insights(insights_data: Dict[str, Any]) -> Optional[uuid.UUID]:
    """
    Save consultation insights (AI-extracted signals) to database.

    Args:
        insights_data: Dict containing 14 signal groups and metadata

    Returns:
        UUID of saved insights, or None on error
    """
    try:
        result = supabase.table("consultation_insights").insert({
            "extraction_id": insights_data["extraction_id"],
            "student_id": insights_data.get("student_id"),
            "counsellor_id": insights_data.get("counsellor_id"),
            # 14 Signal Groups
            "student_signals": insights_data.get("student_signals", {}),
            "clinical_severity_signals": insights_data.get("clinical_severity_signals", {}),
            "diagnostic_needs": insights_data.get("diagnostic_needs", {}),
            "medication_signals": insights_data.get("medication_signals", {}),
            "nutritional_signals": insights_data.get("nutritional_signals", {}),
            "physiotherapy_signals": insights_data.get("physiotherapy_signals", {}),
            "homecare_signals": insights_data.get("homecare_signals", {}),
            "sleep_signals": insights_data.get("sleep_signals", {}),
            "rehabilitation_signals": insights_data.get("rehabilitation_signals", {}),
            "wellness_signals": insights_data.get("wellness_signals", {}),
            "mental_health_signals": insights_data.get("mental_health_signals", {}),
            "education_signals": insights_data.get("education_signals", {}),
            "competitor_signals": insights_data.get("competitor_signals", {}),
            "access_logistics_signals": insights_data.get("access_logistics_signals", {}),
            # Metadata
            "model_used": insights_data.get("model_used", "gemini-2.5-flash"),
            "extraction_version": insights_data.get("extraction_version", "1.0.0"),
            "extraction_duration_ms": insights_data.get("extraction_duration_ms"),
            "raw_response": insights_data.get("raw_response")
        }).execute()

        if result.data and len(result.data) > 0:
            insights_id = uuid.UUID(result.data[0]["id"])
            logger.info(f"[CONSULTATION_INSIGHTS] Saved insights {insights_id} for extraction {insights_data['extraction_id']}")
            return insights_id

        return None

    except Exception as e:
        # Handle duplicate constraint
        if "unique_extraction_insights" in str(e) or "duplicate key" in str(e).lower():
            logger.warning(f"[CONSULTATION_INSIGHTS] Insights already exist for extraction {insights_data['extraction_id']}")
            try:
                existing = supabase.table("consultation_insights").select("id").eq(
                    "extraction_id", insights_data["extraction_id"]
                ).single().execute()
                if existing.data:
                    return uuid.UUID(existing.data["id"])
            except Exception:
                pass
        logger.error(f"[CONSULTATION_INSIGHTS] Failed to save insights: {e}")
        return None


def get_consultation_insights_by_extraction(extraction_id: str) -> Optional[Dict]:
    """
    Get consultation insights for an extraction.

    Args:
        extraction_id: UUID of the extraction

    Returns:
        Dict with all 14 signal groups, or None if not found
    """
    try:
        result = supabase.table("consultation_insights").select("*").eq(
            "extraction_id", extraction_id
        ).single().execute()

        if result.data:
            return result.data

        return None

    except Exception as e:
        if "No rows found" not in str(e) and "0 rows" not in str(e):
            logger.error(f"[CONSULTATION_INSIGHTS] Failed to get insights for extraction {extraction_id}: {e}")
        return None


def get_consultation_insights_by_student(
    student_id: str,
    limit: int = 10
) -> List[Dict]:
    """
    Get recent consultation insights for a student (analytics).

    Args:
        student_id: UUID of the student
        limit: Maximum number of records to return

    Returns:
        List of consultation insights dicts, ordered by created_at DESC
    """
    try:
        result = supabase.table("consultation_insights").select("*").eq(
            "student_id", student_id
        ).order("created_at", desc=True).limit(limit).execute()

        return result.data or []

    except Exception as e:
        logger.error(f"[CONSULTATION_INSIGHTS] Failed to get insights for student {student_id}: {e}")
        return []


def get_consultation_insights_by_counsellor(
    counsellor_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100
) -> List[Dict]:
    """
    Get consultation insights for a counsellor's students (analytics).

    Args:
        counsellor_id: UUID of the counsellor
        start_date: Optional ISO date string for range start
        end_date: Optional ISO date string for range end
        limit: Maximum number of records to return

    Returns:
        List of consultation insights dicts
    """
    try:
        query = supabase.table("consultation_insights").select("*").eq(
            "counsellor_id", counsellor_id
        )

        if start_date:
            query = query.gte("created_at", start_date)
        if end_date:
            query = query.lte("created_at", end_date)

        result = query.order("created_at", desc=True).limit(limit).execute()

        return result.data or []

    except Exception as e:
        logger.error(f"[CONSULTATION_INSIGHTS] Failed to get insights for counsellor {counsellor_id}: {e}")
        return []


# =============================================================================
# SCHOOL INTERVENTION PRICING
# =============================================================================

def get_school_intervention_pricing(
    school_id: uuid.UUID,
    intervention_type: str
) -> Optional[Dict[str, Any]]:
    """
    Get pricing for a specific intervention type at a school.

    Args:
        school_id: UUID of the school
        intervention_type: Intervention type code (e.g., "NUTRITIONAL_REFERRAL")

    Returns:
        Dict with revenue_estimate, service_name, currency, or None if not found
    """
    try:
        response = (
            supabase.table("school_intervention_pricing")
            .select("revenue_estimate, service_name, currency")
            .eq("school_id", str(school_id))
            .eq("intervention_type", intervention_type)
            .eq("is_active", True)
            .single()
            .execute()
        )
        return response.data if response.data else None
    except Exception as e:
        logger.debug(f"[PRICING] No pricing found for {intervention_type} at school {school_id}: {e}")
        return None


def get_all_school_pricing(school_id: uuid.UUID) -> Dict[str, Dict[str, Any]]:
    """
    Get all intervention pricing for a school (for batch lookups).

    Args:
        school_id: UUID of the school

    Returns:
        Dict mapping intervention_type -> {revenue_estimate, service_name, currency}
    """
    try:
        response = (
            supabase.table("school_intervention_pricing")
            .select("intervention_type, revenue_estimate, service_name, currency")
            .eq("school_id", str(school_id))
            .eq("is_active", True)
            .execute()
        )

        if not response.data:
            return {}

        return {
            row["intervention_type"]: {
                "revenue_estimate": float(row["revenue_estimate"]),
                "service_name": row["service_name"],
                "currency": row["currency"]
            }
            for row in response.data
        }
    except Exception as e:
        logger.error(f"[PRICING] Failed to get pricing for school {school_id}: {e}")
        return {}


# =============================================================================
# CATEGORIZED INTERVENTIONS (REVENUE, RETENTION, QUALITY)
# =============================================================================

def save_categorized_intervention(intervention_data: Dict[str, Any]) -> Optional[uuid.UUID]:
    """
    Save a single categorized intervention (REVENUE, RETENTION, or QUALITY).

    Args:
        intervention_data: Dict with:
            - extraction_id: UUID (required)
            - intervention_code: str (required)
            - intervention_category: 'REVENUE' | 'RETENTION' | 'QUALITY' (required)
            - intervention_sub_type: str (e.g., 'allied_health', 'retention')
            - priority_level: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
            - priority_score: int (0-100)
            - take_up_likelihood: int (0-100, predicted likelihood student accepts intervention)
            - trigger_reason: str (plain English reason)
            - action: str (simple action statement)
            - revenue_estimate: Decimal (for REVENUE category)
            - consultation_insights_id: UUID (optional)
            - linked_assessment_type: str (which assessment triggered)
            - linked_assessment_id: UUID (FK to assessment record)
            - analysis_mode: str (default 'combined')

    Returns:
        UUID of saved intervention, or None on error
    """
    try:
        # Get intervention_id from intervention_definitions
        intervention_code = intervention_data.get("intervention_code")

        # Look up intervention definition - MUST exist to save
        def_response = (
            supabase.table("intervention_definitions")
            .select("id")
            .eq("intervention_code", intervention_code)
            .eq("is_active", True)
            .maybe_single()
            .execute()
        )

        intervention_id = def_response.data.get("id") if def_response.data else None

        # If not found in definitions, do NOT save the intervention
        if not intervention_id:
            logger.warning(f"[INTERVENTIONS] No active definition found for {intervention_code}, skipping save")
            return None

        # Build record
        record = {
            "extraction_id": str(intervention_data["extraction_id"]),
            "intervention_id": str(intervention_id),
            "intervention_code": intervention_code,
            "intervention_category": intervention_data.get("intervention_category"),
            "intervention_sub_type": intervention_data.get("intervention_sub_type"),
            "priority_level": intervention_data.get("priority_level", "MEDIUM"),
            "priority_score": intervention_data.get("priority_score", 50),
            "trigger_reason": intervention_data.get("trigger_reason", ""),
            "action": intervention_data.get("action", ""),
            "analysis_mode": intervention_data.get("analysis_mode", "combined"),
            "rationale_sources": intervention_data.get("rationale_sources", {}),
        }

        # Optional fields
        if intervention_data.get("take_up_likelihood") is not None:
            record["take_up_likelihood"] = int(intervention_data["take_up_likelihood"])

        if intervention_data.get("revenue_estimate") is not None:
            record["revenue_estimate"] = float(intervention_data["revenue_estimate"])

        if intervention_data.get("consultation_insights_id"):
            record["consultation_insights_id"] = str(intervention_data["consultation_insights_id"])

        if intervention_data.get("linked_assessment_type"):
            record["linked_assessment_type"] = intervention_data["linked_assessment_type"]

        if intervention_data.get("linked_assessment_id"):
            record["linked_assessment_id"] = str(intervention_data["linked_assessment_id"])

        # Insert
        response = (
            supabase.table("student_interventions")
            .insert(record)
            .execute()
        )

        if response.data and len(response.data) > 0:
            saved_id = response.data[0].get("id")
            logger.info(
                f"[INTERVENTIONS] Saved {intervention_data.get('intervention_category')} "
                f"intervention {intervention_code} -> {saved_id}"
            )
            return uuid.UUID(saved_id)

        return None

    except Exception as e:
        logger.error(
            f"[INTERVENTIONS] Failed to save intervention {intervention_data.get('intervention_code')}: {e}",
            exc_info=True
        )
        return None


def save_categorized_interventions_batch(
    interventions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Save multiple categorized interventions in a batch.

    Args:
        interventions: List of intervention dicts (see save_categorized_intervention for format)

    Returns:
        Dict with success status and counts by category
    """
    if not interventions:
        return {"success": True, "total_saved": 0, "by_category": {}}

    saved_count = 0
    by_category = {"REVENUE": 0, "RETENTION": 0, "QUALITY": 0}
    errors = []

    for intervention in interventions:
        try:
            result = save_categorized_intervention(intervention)
            if result:
                saved_count += 1
                category = intervention.get("intervention_category", "UNKNOWN")
                if category in by_category:
                    by_category[category] += 1
        except Exception as e:
            errors.append({
                "code": intervention.get("intervention_code"),
                "error": str(e)
            })

    logger.info(
        f"[INTERVENTIONS] Batch save complete: {saved_count}/{len(interventions)} saved. "
        f"REVENUE={by_category['REVENUE']}, RETENTION={by_category['RETENTION']}, "
        f"QUALITY={by_category['QUALITY']}"
    )

    return {
        "success": len(errors) == 0,
        "total_saved": saved_count,
        "total_attempted": len(interventions),
        "by_category": by_category,
        "errors": errors if errors else None
    }


def get_categorized_interventions(
    extraction_id: uuid.UUID,
    category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get categorized interventions for an extraction.

    Args:
        extraction_id: UUID of the extraction
        category: Optional filter by category ('REVENUE', 'RETENTION', 'QUALITY')

    Returns:
        List of intervention dicts with all fields
    """
    try:
        query = (
            supabase.table("student_interventions")
            .select("*")
            .eq("extraction_id", str(extraction_id))
            .not_.is_("intervention_category", "null")  # Only categorized interventions
        )

        if category:
            query = query.eq("intervention_category", category)

        response = query.order("priority_score", desc=True).execute()

        return response.data or []

    except Exception as e:
        logger.error(f"[INTERVENTIONS] Failed to get categorized interventions: {e}")
        return []


# ============================================================================
# Recording Management Operations (List & Reprocess Support)
# ============================================================================

def list_recordings_for_counsellor(
    counsellor_id: uuid.UUID,
    student_id: Optional[uuid.UUID] = None,
    student_identifier: Optional[str] = None,
    status: str = "COMPLETED",
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    List recording sessions for a counsellor with optional filters.

    Queries recording_sessions and joins with:
    - students (for patient_name)
    - processing_jobs (for has_transcript)
    - extractions (for has_extraction, last_extraction_id)
    - templates (for template_name)

    Args:
        counsellor_id: UUID of the counsellor
        student_id: Optional student UUID filter
        student_identifier: Optional external student ID filter (e.g., MRN)
        status: Filter by session status (default: COMPLETED)
        date_from: Optional filter for recordings created on or after this date
        date_to: Optional filter for recordings created on or before this date
        limit: Maximum records to return (default: 50)
        offset: Pagination offset (default: 0)

    Returns:
        Dict with 'recordings' list and 'total_count'
    """
    try:
        # Build base query with joins
        # Select recording_sessions with related data
        # Use left join (no !inner) so recordings without students are included
        # NOTE: Don't select full_audio_data (large blob) - use full_audio_mime_type to check if audio exists
        query = (
            supabase.table("recording_sessions")
            .select(
                "id, correlation_id, student_id, student_identifier, "
                "template_code, template_name, processing_mode, extraction_mode, "
                "transcription_model, extraction_model, status, created_at, completed_at, "
                "full_audio_mime_type, error_message, audio_quality_json, has_processed_audio, "
                "students(id, student_id, full_name)"
            )
            .eq("counsellor_id", str(counsellor_id))
        )

        # Apply status filter
        if status:
            query = query.eq("status", status)

        # Apply student filters
        if student_id:
            query = query.eq("student_id", str(student_id))
        if student_identifier:
            # Filter on joined students table's student_id (external identifier/MRN)
            # Note: This requires inner join behavior, so add !inner for this case only
            query = query.eq("students.student_id", student_identifier)

        # Apply date range filters
        if date_from:
            query = query.gte("created_at", date_from.isoformat())
        if date_to:
            query = query.lte("created_at", date_to.isoformat())

        # Order by most recent first
        query = query.order("created_at", desc=True)

        # When the "Completed" view is selected, merged extractions (no recording_session)
        # are appended into the same list. Over-fetch sessions so the combined list can be
        # sorted by date before slicing the requested page.
        include_merged = (status == "SUBMITTED" or not status)
        if include_merged:
            query = query.range(0, offset + limit - 1)
        else:
            query = query.range(offset, offset + limit - 1)

        response = query.execute()
        sessions = response.data or []

        # Get session IDs for batch lookup of processing_jobs and extractions
        session_ids = [s["id"] for s in sessions]

        jobs_by_session = {}
        extractions_by_session = {}
        if session_ids:
            # Batch fetch processing_jobs to check for transcript and get submission_id
            jobs_response = (
                supabase.table("processing_jobs")
                .select("session_id, submission_id, transcript, status")
                .in_("session_id", session_ids)
                .order("created_at", desc=True)
                .execute()
            )
            for job in (jobs_response.data or []):
                # Keep latest job per session
                if job["session_id"] not in jobs_by_session:
                    jobs_by_session[job["session_id"]] = job

            # Batch fetch latest extractions
            extractions_response = (
                supabase.table("extractions")
                .select("id, session_id, transcript_text, created_at")
                .in_("session_id", session_ids)
                .order("created_at", desc=True)
                .execute()
            )
            for ext in (extractions_response.data or []):
                # Keep latest extraction per session
                if ext["session_id"] not in extractions_by_session:
                    extractions_by_session[ext["session_id"]] = ext

        # Batch fetch chunk info for RECORDING status sessions (abandoned recordings)
        # Include chunk count and last chunk timestamp to verify session is truly abandoned
        recording_status_ids = [s["id"] for s in sessions if s.get("status") in ("RECORDING", "validation_failed")]
        chunks_by_session = {}  # {session_id: {"count": N, "last_chunk_at": timestamp}}
        if recording_status_ids:
            chunks_response = (
                supabase.table("audio_chunks")
                .select("session_id, created_at")
                .in_("session_id", recording_status_ids)
                .order("created_at", desc=True)
                .execute()
            )
            # Count chunks and track latest timestamp per session
            for chunk in (chunks_response.data or []):
                sid = chunk["session_id"]
                if sid not in chunks_by_session:
                    chunks_by_session[sid] = {"count": 0, "last_chunk_at": chunk["created_at"]}
                chunks_by_session[sid]["count"] += 1

        # Build response with enriched data
        recordings = []
        for session in sessions:
            session_id = session["id"]
            job = jobs_by_session.get(session_id, {})
            extraction = extractions_by_session.get(session_id, {})
            patient = session.get("students") or {}  # Handle None from left join
            chunk_info = chunks_by_session.get(session_id, {"count": 0, "last_chunk_at": None})
            chunk_count = chunk_info["count"]
            last_chunk_at = chunk_info.get("last_chunk_at")

            # Determine if audio/transcript/extraction exist
            # For RECORDING status, has_audio is True if chunks exist
            # Use full_audio_mime_type as indicator (we don't fetch the large blob)
            has_audio = bool(session.get("full_audio_mime_type")) or chunk_count > 0
            has_transcript = bool(job.get("transcript")) or bool(extraction.get("transcript_text"))
            has_extraction = bool(extraction.get("id"))

            recordings.append({
                "session_id": session_id,
                "correlation_id": session.get("correlation_id"),
                "student_id": session.get("student_id"),
                "student_identifier": session.get("student_identifier"),
                "patient_name": patient.get("full_name"),
                "consultation_datetime": session.get("created_at"),
                "completed_at": session.get("completed_at"),
                "template_code": session.get("template_code"),
                "template_name": session.get("template_name"),
                "processing_mode": session.get("processing_mode"),
                "extraction_mode": session.get("extraction_mode"),
                "transcription_model": session.get("transcription_model"),
                "extraction_model": session.get("extraction_model"),
                "has_audio": has_audio,
                "has_transcript": has_transcript,
                "has_extraction": has_extraction,
                "last_extraction_id": extraction.get("id"),
                "last_submission_id": job.get("submission_id"),  # For audio playback API
                "status": session.get("status"),
                "error_message": session.get("error_message"),
                "audio_quality": session.get("audio_quality_json"),
                "has_processed_audio": session.get("has_processed_audio", False),
                "chunk_count": chunk_count,  # Number of audio chunks (for abandoned recordings)
                "last_chunk_at": last_chunk_at,  # Timestamp of last chunk (to verify abandoned)
                "is_merged": False,
            })

        # Get total count (separate query without pagination)
        count_query = (
            supabase.table("recording_sessions")
            .select("id", count="exact")
            .eq("counsellor_id", str(counsellor_id))
        )
        if status:
            count_query = count_query.eq("status", status)
        if student_id:
            count_query = count_query.eq("student_id", str(student_id))
        if student_identifier:
            count_query = count_query.eq("student_identifier", student_identifier)
        if date_from:
            count_query = count_query.gte("created_at", date_from.isoformat())
        if date_to:
            count_query = count_query.lte("created_at", date_to.isoformat())

        count_response = count_query.execute()
        total_count = count_response.count or len(recordings)

        # Merged extractions are display-only rows in the "Completed" view: they have no
        # recording_session / processing_job / audio. We fetch them separately and
        # interleave by created_at before slicing the requested page.
        merged_count = 0
        if include_merged:
            try:
                merge_query = (
                    supabase.table("extractions")
                    .select(
                        "id, student_id, counsellor_id, created_at, merge_metadata, "
                        "students(id, student_id, full_name)"
                    )
                    .eq("counsellor_id", str(counsellor_id))
                    .eq("is_merged", True)
                )
                if student_id:
                    merge_query = merge_query.eq("student_id", str(student_id))
                if student_identifier:
                    merge_query = merge_query.eq("students.student_id", student_identifier)
                if date_from:
                    merge_query = merge_query.gte("created_at", date_from.isoformat())
                if date_to:
                    merge_query = merge_query.lte("created_at", date_to.isoformat())

                merge_query = merge_query.order("created_at", desc=True).range(0, offset + limit - 1)
                merge_response = merge_query.execute()

                for me in (merge_response.data or []):
                    meta = me.get("merge_metadata") or {}
                    tcode = meta.get("target_template_code")
                    mpatient = me.get("students") or {}
                    recordings.append({
                        "session_id": me["id"],  # use extraction id as row key
                        "correlation_id": None,
                        "student_id": me.get("student_id"),
                        "student_identifier": mpatient.get("student_id"),
                        "patient_name": mpatient.get("full_name"),
                        "consultation_datetime": me.get("created_at"),
                        "completed_at": me.get("created_at"),
                        "template_code": tcode,
                        "template_name": tcode,
                        "processing_mode": None,
                        "extraction_mode": "full",
                        "transcription_model": None,
                        "extraction_model": None,
                        "has_audio": False,
                        "has_transcript": False,
                        "has_extraction": True,
                        "last_extraction_id": me["id"],
                        "last_submission_id": None,
                        "status": "MERGED",
                        "error_message": None,
                        "audio_quality": None,
                        "has_processed_audio": False,
                        "chunk_count": 0,
                        "last_chunk_at": None,
                        "is_merged": True,
                    })

                merge_count_query = (
                    supabase.table("extractions")
                    .select("id", count="exact")
                    .eq("counsellor_id", str(counsellor_id))
                    .eq("is_merged", True)
                )
                if student_id:
                    merge_count_query = merge_count_query.eq("student_id", str(student_id))
                if student_identifier:
                    merge_count_query = merge_count_query.eq("students.student_id", student_identifier)
                if date_from:
                    merge_count_query = merge_count_query.gte("created_at", date_from.isoformat())
                if date_to:
                    merge_count_query = merge_count_query.lte("created_at", date_to.isoformat())
                merged_count = (merge_count_query.execute()).count or 0
            except Exception as e:
                logger.warning(f"[RECORDINGS] Failed to fetch merged extractions for counsellor {counsellor_id}: {e}")

        # Sort the combined list by date desc and slice to the requested page
        recordings.sort(key=lambda r: r.get("consultation_datetime") or "", reverse=True)
        if include_merged:
            recordings = recordings[offset:offset + limit]
        total_count = total_count + merged_count

        return {
            "recordings": recordings,
            "total_count": total_count
        }

    except Exception as e:
        logger.error(f"[RECORDINGS] Failed to list recordings for counsellor {counsellor_id}: {e}", exc_info=True)
        raise Exception(f"Failed to list recordings: {str(e)}")


def list_recordings_for_assistant(
    assistant_id: uuid.UUID,
    student_id: Optional[uuid.UUID] = None,
    student_identifier: Optional[str] = None,
    status: str = "COMPLETED",
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    List recording sessions for an assistant with optional filters.
    Mirror of list_recordings_for_counsellor but filtering on assistant_id.
    """
    try:
        query = (
            supabase.table("recording_sessions")
            .select(
                "id, correlation_id, student_id, student_identifier, "
                "template_code, template_name, processing_mode, extraction_mode, "
                "transcription_model, extraction_model, status, created_at, completed_at, "
                "full_audio_mime_type, error_message, audio_quality_json, has_processed_audio, "
                "students(id, student_id, full_name)"
            )
            .eq("assistant_id", str(assistant_id))
        )

        if status:
            query = query.eq("status", status)
        if student_id:
            query = query.eq("student_id", str(student_id))
        if student_identifier:
            query = query.eq("students.student_id", student_identifier)
        if date_from:
            query = query.gte("created_at", date_from.isoformat())
        if date_to:
            query = query.lte("created_at", date_to.isoformat())

        query = query.order("created_at", desc=True)
        query = query.range(offset, offset + limit - 1)

        response = query.execute()
        sessions = response.data or []

        session_ids = [s["id"] for s in sessions]
        if not session_ids:
            return {"recordings": [], "total_count": 0}

        # Batch fetch processing_jobs
        jobs_response = (
            supabase.table("processing_jobs")
            .select("session_id, submission_id, transcript, status")
            .in_("session_id", session_ids)
            .order("created_at", desc=True)
            .execute()
        )
        jobs_by_session = {}
        for job in (jobs_response.data or []):
            if job["session_id"] not in jobs_by_session:
                jobs_by_session[job["session_id"]] = job

        # Batch fetch latest extractions
        extractions_response = (
            supabase.table("extractions")
            .select("id, session_id, transcript_text, created_at")
            .in_("session_id", session_ids)
            .order("created_at", desc=True)
            .execute()
        )
        extractions_by_session = {}
        for ext in (extractions_response.data or []):
            if ext["session_id"] not in extractions_by_session:
                extractions_by_session[ext["session_id"]] = ext

        # Batch fetch chunk info for abandoned recordings
        recording_status_ids = [s["id"] for s in sessions if s.get("status") in ("RECORDING", "validation_failed")]
        chunks_by_session = {}
        if recording_status_ids:
            chunks_response = (
                supabase.table("audio_chunks")
                .select("session_id, created_at")
                .in_("session_id", recording_status_ids)
                .order("created_at", desc=True)
                .execute()
            )
            for chunk in (chunks_response.data or []):
                sid = chunk["session_id"]
                if sid not in chunks_by_session:
                    chunks_by_session[sid] = {"count": 0, "last_chunk_at": chunk["created_at"]}
                chunks_by_session[sid]["count"] += 1

        recordings = []
        for session in sessions:
            session_id = session["id"]
            job = jobs_by_session.get(session_id, {})
            extraction = extractions_by_session.get(session_id, {})
            patient = session.get("students") or {}
            chunk_info = chunks_by_session.get(session_id, {"count": 0, "last_chunk_at": None})
            chunk_count = chunk_info["count"]
            last_chunk_at = chunk_info.get("last_chunk_at")

            has_audio = bool(session.get("full_audio_mime_type")) or chunk_count > 0
            has_transcript = bool(job.get("transcript")) or bool(extraction.get("transcript_text"))
            has_extraction = bool(extraction.get("id"))

            recordings.append({
                "session_id": session_id,
                "correlation_id": session.get("correlation_id"),
                "student_id": session.get("student_id"),
                "student_identifier": session.get("student_identifier"),
                "patient_name": patient.get("full_name"),
                "consultation_datetime": session.get("created_at"),
                "completed_at": session.get("completed_at"),
                "template_code": session.get("template_code"),
                "template_name": session.get("template_name"),
                "processing_mode": session.get("processing_mode"),
                "extraction_mode": session.get("extraction_mode"),
                "transcription_model": session.get("transcription_model"),
                "extraction_model": session.get("extraction_model"),
                "has_audio": has_audio,
                "has_transcript": has_transcript,
                "has_extraction": has_extraction,
                "last_extraction_id": extraction.get("id"),
                "last_submission_id": job.get("submission_id"),
                "status": session.get("status"),
                "error_message": session.get("error_message"),
                "audio_quality": session.get("audio_quality_json"),
                "has_processed_audio": session.get("has_processed_audio", False),
                "chunk_count": chunk_count,
                "last_chunk_at": last_chunk_at,
            })

        # Total count
        count_query = (
            supabase.table("recording_sessions")
            .select("id", count="exact")
            .eq("assistant_id", str(assistant_id))
        )
        if status:
            count_query = count_query.eq("status", status)
        if student_id:
            count_query = count_query.eq("student_id", str(student_id))
        if student_identifier:
            count_query = count_query.eq("student_identifier", student_identifier)
        if date_from:
            count_query = count_query.gte("created_at", date_from.isoformat())
        if date_to:
            count_query = count_query.lte("created_at", date_to.isoformat())

        count_response = count_query.execute()
        total_count = count_response.count or len(recordings)

        return {
            "recordings": recordings,
            "total_count": total_count
        }

    except Exception as e:
        logger.error(f"[RECORDINGS] Failed to list recordings for assistant {assistant_id}: {e}", exc_info=True)
        raise Exception(f"Failed to list recordings: {str(e)}")


def get_session_transcript(session_id: uuid.UUID) -> Optional[str]:
    """
    Get transcript for a session from processing_jobs or extractions.

    Checks processing_jobs first (where transcript is stored during processing),
    falls back to extractions.transcript_text if not found.

    Args:
        session_id: UUID of the recording session

    Returns:
        Transcript string or None if no transcript exists
    """
    try:
        # Try processing_jobs first (most recent job)
        job_response = (
            supabase.table("processing_jobs")
            .select("transcript")
            .eq("session_id", str(session_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if job_response.data and job_response.data[0].get("transcript"):
            return job_response.data[0]["transcript"]

        # Fallback to extractions (most recent extraction)
        extraction_response = (
            supabase.table("extractions")
            .select("transcript_text")
            .eq("session_id", str(session_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if extraction_response.data and extraction_response.data[0].get("transcript_text"):
            return extraction_response.data[0]["transcript_text"]

        return None

    except Exception as e:
        logger.error(f"[RECORDINGS] Failed to get transcript for session {session_id}: {e}")
        return None


def get_session_full_audio(session_id: uuid.UUID) -> Optional[tuple]:
    """
    Get full audio data for a session from recording_sessions.

    Checks in order:
    1. full_audio_data column (inline base64 data)
    2. full_audio_url column (fetch from storage)

    Args:
        session_id: UUID of the recording session

    Returns:
        Tuple of (full_audio_data_base64, mime_type) or None if no audio stored
    """
    try:
        response = (
            supabase.table("recording_sessions")
            .select("full_audio_data, full_audio_mime_type, full_audio_url")
            .eq("id", str(session_id))
            .single()
            .execute()
        )

        if response.data:
            # First try inline audio data
            audio_data = response.data.get("full_audio_data")
            mime_type = response.data.get("full_audio_mime_type")

            if audio_data and mime_type:
                logger.debug(f"[RECORDINGS] Found inline audio data for session {session_id}")
                return (audio_data, mime_type)

            # Fallback to storage URL
            audio_url = response.data.get("full_audio_url")
            if audio_url:
                logger.debug(f"[RECORDINGS] No inline data, fetching from storage URL for session {session_id}")
                from services.audio_storage_service import fetch_audio_from_url
                result = fetch_audio_from_url(audio_url)
                if result:
                    return result
                logger.warning(f"[RECORDINGS] Failed to fetch audio from storage URL: {audio_url}")

        return None

    except Exception as e:
        logger.error(f"[RECORDINGS] Failed to get audio for session {session_id}: {e}")
        return None


def get_session_by_id(session_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get recording session by its ID (primary key).

    Args:
        session_id: UUID of the recording session

    Returns:
        Session record dict or None if not found
    """
    try:
        response = (
            supabase.table("recording_sessions")
            .select("*")
            .eq("id", str(session_id))
            .single()
            .execute()
        )
        return response.data if response.data else None
    except Exception as e:
        logger.error(f"[RECORDINGS] Failed to get session {session_id}: {e}")
        return None


def update_session_settings(
    session_id: uuid.UUID,
    template_code: str,
    processing_mode: str,
    extraction_mode: str,
) -> Dict[str, Any]:
    """
    Update session settings for reprocessing.

    Args:
        session_id: UUID of the recording session
        template_code: New template code
        processing_mode: New processing mode
        extraction_mode: New extraction mode

    Returns:
        Updated session record
    """
    try:
        update_data = {
            "template_code": template_code,
            "processing_mode": processing_mode,
            "extraction_mode": extraction_mode,
            # Clear stale session_context_json so extraction uses the new template
            "session_context_json": None,
        }

        response = (
            supabase.table("recording_sessions")
            .update(update_data)
            .eq("id", str(session_id))
            .execute()
        )

        return response.data[0] if response.data else {}

    except Exception as e:
        logger.error(f"[RECORDINGS] Failed to update session settings {session_id}: {e}")
        raise Exception(f"Failed to update session settings: {str(e)}")


# ─── Translation Service Functions ──────────────────────────────────────────

# Cache for translation models by mode code
_translation_model_cache: Dict[str, str] = {}


def get_translation_model_by_mode(mode_code: str = "default") -> str:
    """
    Get translation model for a processing mode from the database.
    Follows same pattern as get_emotion_model_by_mode / get_triage_model_by_mode.
    """
    global _translation_model_cache

    if mode_code in _translation_model_cache:
        return _translation_model_cache[mode_code]

    try:
        response = (
            supabase.table("processing_modes")
            .select("translation_model")
            .eq("mode_code", mode_code)
            .single()
            .execute()
        )

        if not response.data:
            fallback = "gemini-2.5-flash"
            logger.warning(f"[PROCESSING_MODE] No processing mode found for '{mode_code}', using fallback translation model: {fallback}")
            return fallback

        model = response.data.get("translation_model") or "gemini-2.5-flash"
        _translation_model_cache[mode_code] = model
        logger.debug(f"[PROCESSING_MODE] Loaded translation model for '{mode_code}': {model}")
        return model

    except Exception as e:
        logger.error(f"[PROCESSING_MODE] Error fetching translation model for '{mode_code}': {e}")
        fallback = "gemini-2.5-flash"
        logger.warning(f"[PROCESSING_MODE] Using fallback translation model: {fallback}")
        return fallback


def get_counsellor_translation_language(counsellor_id: uuid.UUID) -> Optional[str]:
    """
    Get the translation language for a counsellor, with school default fallback.
    Returns None if no translation language is configured.
    """
    try:
        # Check counsellor-level setting first
        response = (
            supabase.table("counsellors")
            .select("translation_language, school_id")
            .eq("id", str(counsellor_id))
            .single()
            .execute()
        )

        if not response.data:
            return None

        counsellor_lang = response.data.get("translation_language")
        if counsellor_lang:
            return counsellor_lang

        # Fallback to school default
        school_id = response.data.get("school_id")
        if school_id:
            school_response = (
                supabase.table("schools")
                .select("default_translation_language")
                .eq("id", str(school_id))
                .single()
                .execute()
            )
            if school_response.data:
                return school_response.data.get("default_translation_language")

        return None

    except Exception as e:
        logger.error(f"[TRANSLATION] Error fetching translation language for counsellor {counsellor_id}: {e}")
        return None


def save_extraction_translation(
    extraction_id: uuid.UUID,
    target_language: str,
    translated_json: Dict[str, Any],
    model_used: str = "",
    translation_time_seconds: float = 0,
    started: bool = False,
    completed: bool = False,
) -> Optional[Dict[str, Any]]:
    """Insert or upsert an extraction translation record."""
    try:
        data = {
            "extraction_id": str(extraction_id),
            "target_language": target_language,
            "translated_extraction_json": translated_json,
            "model_used": model_used,
            "translation_time_seconds": translation_time_seconds,
            "translation_started": started,
            "translation_completed": completed,
            "translation_failed": False,
        }

        response = supabase.table("extraction_translations").upsert(
            data,
            on_conflict="extraction_id,target_language",
        ).execute()

        return response.data[0] if response.data else None

    except Exception as e:
        logger.error(f"[TRANSLATION] Failed to save translation for extraction {extraction_id}: {e}")
        return None


def update_extraction_translation_status(
    extraction_id: uuid.UUID,
    target_language: str,
    translated_json: Optional[Dict[str, Any]] = None,
    model_used: Optional[str] = None,
    translation_time_seconds: Optional[float] = None,
    completed: Optional[bool] = None,
    failed: Optional[bool] = None,
    error: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Update translation status fields."""
    try:
        from datetime import datetime, timezone

        updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}

        if translated_json is not None:
            updates["translated_extraction_json"] = translated_json
        if model_used is not None:
            updates["model_used"] = model_used
        if translation_time_seconds is not None:
            updates["translation_time_seconds"] = translation_time_seconds
        if completed is not None:
            updates["translation_completed"] = completed
        if failed is not None:
            updates["translation_failed"] = failed
        if error is not None:
            updates["translation_error"] = error

        response = (
            supabase.table("extraction_translations")
            .update(updates)
            .eq("extraction_id", str(extraction_id))
            .eq("target_language", target_language)
            .execute()
        )

        return response.data[0] if response.data else None

    except Exception as e:
        logger.error(f"[TRANSLATION] Failed to update translation status for {extraction_id}: {e}")
        return None


def get_extraction_translation(
    extraction_id: uuid.UUID,
    target_language: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Fetch translation for an extraction. If target_language is None, returns the first translation found.
    """
    try:
        query = (
            supabase.table("extraction_translations")
            .select("*")
            .eq("extraction_id", str(extraction_id))
        )

        if target_language:
            query = query.eq("target_language", target_language)

        response = query.limit(1).execute()
        return response.data[0] if response.data else None

    except Exception as e:
        logger.error(f"[TRANSLATION] Failed to fetch translation for {extraction_id}: {e}")
        return None


def update_translation_edits(
    extraction_id: uuid.UUID,
    target_language: str,
    edited_json: Dict[str, Any],
    edited_by: uuid.UUID,
    edited_by_type: str = "doctor",
) -> Optional[Dict[str, Any]]:
    """Save counsellor edits to the translated version."""
    try:
        from datetime import datetime, timezone

        # Get current edit count
        current = get_extraction_translation(extraction_id, target_language)
        current_count = current.get("translation_edit_count", 0) or 0 if current else 0

        updates = {
            "edited_translated_json": edited_json,
            "translation_edit_count": current_count + 1,
            "last_translation_edited_at": datetime.now(timezone.utc).isoformat(),
            "last_translation_edited_by": str(edited_by),
            "translation_edited_by_type": edited_by_type,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        response = (
            supabase.table("extraction_translations")
            .update(updates)
            .eq("extraction_id", str(extraction_id))
            .eq("target_language", target_language)
            .execute()
        )

        return response.data[0] if response.data else None

    except Exception as e:
        logger.error(f"[TRANSLATION] Failed to update translation edits for {extraction_id}: {e}")
        raise



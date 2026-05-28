"""
LLM Usage Tracking Service

Tracks token usage and cost estimation for all Gemini API calls.
Saves usage data to llm_usage_log table for analytics and cost monitoring.

Usage:
    from services.llm_usage_service import log_llm_usage, extract_usage_from_response

    # After a Gemini API call:
    usage_data = extract_usage_from_response(
        response=response,
        call_type="extraction",
        call_subtype="neo_daily",
        model="gemini-2.5-flash",
        api_duration_seconds=2.5,
        session_id=session_id,
        extraction_id=extraction_id,
    )

    # Save to database (fire-and-forget)
    await log_llm_usage(usage_data)
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


# ============================================================================
# LLM Pricing - DB-backed with in-memory cache
# Prices loaded from models_master table, with hardcoded fallbacks
# ============================================================================

# Fallback pricing used ONLY if DB query fails (resilience)
FALLBACK_PRICING = {
    "gemini-3-pro": {"input_per_million": 2.00, "output_per_million": 12.00, "cached_input_per_million": 0.20, "thinking_per_million": 12.00},
    "gemini-3.1-pro-preview": {"input_per_million": 2.00, "output_per_million": 12.00, "cached_input_per_million": 0.20, "thinking_per_million": 12.00},
    "gemini-2.5-pro": {"input_per_million": 1.25, "output_per_million": 10.00, "cached_input_per_million": 0.3125, "thinking_per_million": 10.00},
    "gemini-2.5-flash": {"input_per_million": 0.30, "output_per_million": 0.60, "cached_input_per_million": 0.03, "thinking_per_million": 3.50},
    "gemini-2.5-flash-lite": {"input_per_million": 0.075, "output_per_million": 0.30, "cached_input_per_million": 0.01875},
    "gemini-2.0-flash": {"input_per_million": 0.10, "output_per_million": 0.40, "cached_input_per_million": 0.025},
    "gemini-2.0-flash-lite": {"input_per_million": 0.05, "output_per_million": 0.20, "cached_input_per_million": 0.0125},
    "gemini-2.0-flash-exp": {"input_per_million": 0.10, "output_per_million": 0.40, "cached_input_per_million": 0.025},
    "gemini-1.5-pro": {"input_per_million": 1.25, "output_per_million": 5.00, "cached_input_per_million": 0.3125},
    "gemini-1.5-flash": {"input_per_million": 0.075, "output_per_million": 0.30, "cached_input_per_million": 0.01875},
    "claude-sonnet-4-5-20250929": {"input_per_million": 3.00, "output_per_million": 15.00, "cached_input_per_million": 0.30},
    "claude-opus-4-5-20251101": {"input_per_million": 5.00, "output_per_million": 25.00, "cached_input_per_million": 0.50},
    "claude-haiku-4-5-20251001": {"input_per_million": 1.00, "output_per_million": 5.00, "cached_input_per_million": 0.10},
    "gpt-4.1-2025-04-14": {"input_per_million": 2.00, "output_per_million": 8.00, "cached_input_per_million": 0.50},
    "gpt-5-mini-2025-08-07": {"input_per_million": 0.40, "output_per_million": 1.60, "cached_input_per_million": 0.20},
    "gpt-5.2-2025-12-11": {"input_per_million": 5.00, "output_per_million": 20.00, "cached_input_per_million": 2.50},
    "default": {"input_per_million": 1.25, "output_per_million": 10.00, "cached_input_per_million": 0.3125},
}

FALLBACK_AUDIO_PRICING = {
    "gemini-3-pro": 0.00625,
    "gemini-3.1-pro-preview": 0.00625,
    "gemini-2.5-pro": 0.00625,
    "gemini-2.5-flash": 0.001,
    "gemini-2.0-flash": 0.001,
    "gemini-2.0-flash-exp": 0.001,
    "default": 0.00625,
}

# In-memory pricing caches (populated from DB)
_pricing_cache: Dict[str, Dict[str, float]] = {}
_audio_pricing_cache: Dict[str, float] = {}
_thinking_budgets_cache: Dict[str, Dict[str, int]] = {}
_cache_loaded_at: float = 0.0
_CACHE_TTL_SECONDS = 300  # 5 minutes

# Backward compatibility aliases
LLM_PRICING = FALLBACK_PRICING
GEMINI_PRICING = FALLBACK_PRICING
AUDIO_PRICING = FALLBACK_AUDIO_PRICING


async def load_pricing_from_db() -> int:
    """
    Load pricing from models_master table into in-memory cache.
    Returns number of models loaded.
    """
    global _pricing_cache, _audio_pricing_cache, _thinking_budgets_cache, _cache_loaded_at

    try:
        from services.supabase_service import supabase

        result = supabase.table("models_master").select(
            "model_id, input_price_per_million, output_price_per_million, "
            "cached_input_price_per_million, audio_price_per_minute, "
            "thinking_price_per_million, thinking_budgets"
        ).eq("is_active", True).execute()

        if not result.data:
            logger.warning("[PRICING] No models found in models_master, using fallback pricing")
            return 0

        new_pricing: Dict[str, Dict[str, float]] = {}
        new_audio: Dict[str, float] = {}
        new_thinking_budgets: Dict[str, Dict[str, int]] = {}

        for row in result.data:
            model_id = row["model_id"]
            inp = row.get("input_price_per_million")
            out = row.get("output_price_per_million")
            cached = row.get("cached_input_price_per_million")

            if inp is not None and out is not None:
                thinking = row.get("thinking_price_per_million")
                pricing_entry = {
                    "input_per_million": float(inp),
                    "output_per_million": float(out),
                    "cached_input_per_million": float(cached) if cached is not None else float(inp) * 0.25,
                }
                if thinking is not None:
                    pricing_entry["thinking_per_million"] = float(thinking)
                new_pricing[model_id] = pricing_entry

            audio = row.get("audio_price_per_minute")
            if audio is not None:
                new_audio[model_id] = float(audio)

            # Load thinking budgets (JSONB)
            budgets = row.get("thinking_budgets")
            if budgets and isinstance(budgets, dict):
                new_thinking_budgets[model_id] = {k: int(v) for k, v in budgets.items() if v is not None}

        # Keep default fallback in cache
        new_pricing["default"] = FALLBACK_PRICING["default"]
        new_audio["default"] = FALLBACK_AUDIO_PRICING["default"]

        _pricing_cache = new_pricing
        _audio_pricing_cache = new_audio
        _thinking_budgets_cache = new_thinking_budgets
        _cache_loaded_at = time.monotonic()

        logger.info(f"[PRICING] Loaded {len(new_pricing) - 1} model prices from DB (cache refreshed)")
        return len(new_pricing) - 1

    except Exception as e:
        logger.error(f"[PRICING] Failed to load pricing from DB: {e}")
        return 0


def invalidate_pricing_cache():
    """Invalidate the pricing cache so next get_pricing() triggers a reload."""
    global _cache_loaded_at
    _cache_loaded_at = 0.0
    logger.info("[PRICING] Cache invalidated")


# ============================================================================
# Usage Data Classes
# ============================================================================

@dataclass
class LLMUsageData:
    """Data class for LLM usage tracking."""

    # Required fields
    call_type: str  # transcription, extraction, emotion, merge, generation
    model: str

    # Context references (optional)
    session_id: Optional[uuid.UUID] = None
    extraction_id: Optional[uuid.UUID] = None
    doctor_id: Optional[uuid.UUID] = None
    api_client_id: Optional[uuid.UUID] = None  # API client that made the request

    # Call classification
    call_subtype: Optional[str] = None
    consultation_type_code: Optional[str] = None
    template_code: Optional[str] = None

    # Token counts (from usage_metadata)
    prompt_token_count: Optional[int] = None
    cached_content_token_count: Optional[int] = None
    candidates_token_count: Optional[int] = None
    thoughts_token_count: Optional[int] = None
    total_token_count: Optional[int] = None

    # Detailed breakdown (estimated)
    system_prompt_tokens: Optional[int] = None
    user_prompt_tokens: Optional[int] = None
    schema_tokens: Optional[int] = None

    # Audio-specific
    audio_duration_seconds: Optional[float] = None
    audio_size_bytes: Optional[int] = None

    # Cost estimation (calculated)
    input_cost_usd: Optional[float] = None
    output_cost_usd: Optional[float] = None
    cache_savings_usd: Optional[float] = None
    total_cost_usd: Optional[float] = None

    # Performance
    api_duration_seconds: Optional[float] = None
    cache_hit: bool = False
    cache_hit_ratio: Optional[float] = None

    # Status
    response_status: str = "success"
    error_message: Optional[str] = None

    # Timestamp
    request_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        data = asdict(self)
        # Convert UUID to string
        for key in ['session_id', 'extraction_id', 'doctor_id', 'api_client_id']:
            if data[key] is not None:
                data[key] = str(data[key])
        # Convert datetime to ISO string
        if data['request_timestamp']:
            data['request_timestamp'] = data['request_timestamp'].isoformat()
        return data


# ============================================================================
# Cost Calculation Functions
# ============================================================================

def get_pricing(model: str) -> Dict[str, float]:
    """Get pricing for a specific model. Reads from DB-backed cache, falls back to hardcoded."""
    # Use DB cache if loaded, otherwise use fallback
    source = _pricing_cache if _pricing_cache else FALLBACK_PRICING

    # Try exact match first
    if model in source:
        return source[model]

    # Try prefix match (e.g., "gemini-2.5-pro-preview" -> "gemini-2.5-pro")
    for key in source:
        if key != "default" and model.startswith(key):
            return source[key]

    # Return default
    logger.warning(f"[USAGE] Unknown model '{model}', using default pricing")
    return source["default"]


def get_audio_pricing(model: str) -> float:
    """Get audio pricing per minute for a model."""
    source = _audio_pricing_cache if _audio_pricing_cache else FALLBACK_AUDIO_PRICING

    if model in source:
        return source[model]

    # Try prefix match
    for key in source:
        if key != "default" and model.startswith(key):
            return source[key]

    return source["default"]


# Hardcoded fallback thinking budgets (used when DB cache is empty)
_FALLBACK_THINKING_BUDGETS: Dict[str, Dict[str, int]] = {
    "gemini-2.5-flash": {
        "transcription": 0, "extraction": 1024, "emotion": 0,
        "triage": 2048, "consultation_insights": 1024, "merge": 1024,
    },
    "gemini-2.5-pro": {
        "transcription": 0, "extraction": 2048, "emotion": 0,
        "triage": 4096, "consultation_insights": 2048, "merge": 2048,
    },
    "gemini-3-pro": {
        "transcription": 0, "extraction": 2048, "emotion": 0,
        "triage": 4096, "consultation_insights": 2048, "merge": 2048,
    },
    "gemini-3.1-pro-preview": {
        "transcription": 0, "extraction": 2048, "emotion": 0,
        "triage": 4096, "consultation_insights": 2048, "merge": 2048,
    },
}


def get_thinking_budget(model: str, call_type: str) -> Optional[int]:
    """
    Get thinking budget for a model + call_type from DB-backed cache.

    Returns:
        int: Thinking budget (0 = disabled, positive = capped)
        None: No config found → use Gemini default (auto thinking)
    """
    source = _thinking_budgets_cache if _thinking_budgets_cache else _FALLBACK_THINKING_BUDGETS

    # Try exact model match
    budgets = source.get(model)
    if not budgets:
        # Try prefix match
        for key in source:
            if model.startswith(key):
                budgets = source[key]
                break

    if budgets and call_type in budgets:
        return budgets[call_type]

    return None


def calculate_text_costs(
    model: str,
    prompt_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    thinking_tokens: int = 0,
) -> Dict[str, float]:
    """
    Calculate costs for text-based API calls (extraction, emotion, merge).

    Args:
        model: Gemini model name
        prompt_tokens: Total input tokens
        output_tokens: Output/candidate tokens
        cached_tokens: Tokens served from cache
        thinking_tokens: Thinking/reasoning tokens (Gemini 2.5+ models)

    Returns:
        Dict with input_cost, output_cost, thinking_cost, cache_savings, total_cost (all in USD)
    """
    pricing = get_pricing(model)

    # Non-cached input tokens
    non_cached_tokens = prompt_tokens - cached_tokens

    # Calculate costs (divide by 1M for per-token rate)
    input_cost = (non_cached_tokens / 1_000_000) * pricing["input_per_million"]
    cached_cost = (cached_tokens / 1_000_000) * pricing["cached_input_per_million"]
    output_cost = (output_tokens / 1_000_000) * pricing["output_per_million"]

    # Thinking tokens use separate pricing (falls back to output price if not set)
    thinking_price = pricing.get("thinking_per_million", pricing["output_per_million"])
    thinking_cost = (thinking_tokens / 1_000_000) * thinking_price

    # What we would have paid without caching
    full_input_cost = (prompt_tokens / 1_000_000) * pricing["input_per_million"]
    cache_savings = full_input_cost - (input_cost + cached_cost)

    total_cost = input_cost + cached_cost + output_cost + thinking_cost

    return {
        "input_cost_usd": round(input_cost + cached_cost, 6),
        "output_cost_usd": round(output_cost + thinking_cost, 6),
        "cache_savings_usd": round(max(0, cache_savings), 6),
        "total_cost_usd": round(total_cost, 6),
    }


def calculate_audio_costs(
    model: str,
    audio_duration_seconds: float,
    output_tokens: int = 0
) -> Dict[str, float]:
    """
    Calculate costs for audio transcription.

    Args:
        model: Gemini model name
        audio_duration_seconds: Duration of audio in seconds
        output_tokens: Output tokens (transcript)

    Returns:
        Dict with input_cost, output_cost, total_cost (all in USD)
    """
    # Get audio pricing (per minute)
    audio_price_per_minute = get_audio_pricing(model)
    audio_minutes = audio_duration_seconds / 60

    # Audio input cost
    input_cost = audio_minutes * audio_price_per_minute

    # Output cost (transcript tokens)
    pricing = get_pricing(model)
    output_cost = (output_tokens / 1_000_000) * pricing["output_per_million"]

    return {
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "cache_savings_usd": 0.0,  # No caching for audio
        "total_cost_usd": round(input_cost + output_cost, 6),
    }


# ============================================================================
# Usage Extraction from Gemini Response
# ============================================================================

def extract_usage_from_response(
    response: Any,
    call_type: str,
    model: str,
    api_duration_seconds: float,
    call_subtype: Optional[str] = None,
    consultation_type_code: Optional[str] = None,
    template_code: Optional[str] = None,
    session_id: Optional[uuid.UUID] = None,
    extraction_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    api_client_id: Optional[uuid.UUID] = None,
    audio_duration_seconds: Optional[float] = None,
    audio_size_bytes: Optional[int] = None,
    system_prompt_tokens: Optional[int] = None,
    user_prompt_tokens: Optional[int] = None,
    schema_tokens: Optional[int] = None,
    error_message: Optional[str] = None,
) -> LLMUsageData:
    """
    Extract usage data from a Gemini API response.

    Args:
        response: Gemini API response object
        call_type: Type of call (transcription, extraction, emotion, merge, generation)
        model: Model used
        api_duration_seconds: Time taken for API call
        call_subtype: Specific function (neo_daily, dynamic_core, etc.)
        consultation_type_code: Consultation type code
        template_code: Template used
        session_id: Recording session ID
        extraction_id: Medical extraction ID
        doctor_id: Doctor ID
        api_client_id: API client ID that made the request
        audio_duration_seconds: Audio duration (for transcription)
        audio_size_bytes: Audio size (for transcription)
        system_prompt_tokens: Estimated system prompt tokens
        user_prompt_tokens: Estimated user prompt tokens
        schema_tokens: Estimated schema tokens
        error_message: Error message if call failed

    Returns:
        LLMUsageData object ready for database insertion
    """
    # Extract usage metadata from response (provider-aware)
    prompt_tokens = 0
    cached_tokens = 0
    output_tokens = 0
    thinking_tokens = 0
    total_tokens = 0

    if response is not None:
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            # Gemini response
            usage = response.usage_metadata
            prompt_tokens = getattr(usage, 'prompt_token_count', 0) or 0
            cached_tokens = getattr(usage, 'cached_content_token_count', 0) or 0
            output_tokens = getattr(usage, 'candidates_token_count', 0) or 0
            thinking_tokens = getattr(usage, 'thoughts_token_count', 0) or 0
            total_tokens = getattr(usage, 'total_token_count', 0) or 0
        elif hasattr(response, 'usage') and hasattr(response, 'stop_reason'):
            # Anthropic Claude response (has usage + stop_reason)
            usage = response.usage
            prompt_tokens = getattr(usage, 'input_tokens', 0) or 0
            output_tokens = getattr(usage, 'output_tokens', 0) or 0
            cached_tokens = getattr(usage, 'cache_read_input_tokens', 0) or 0
            total_tokens = prompt_tokens + output_tokens
        elif hasattr(response, 'usage') and hasattr(response, 'choices'):
            # OpenAI response (has usage + choices)
            usage = response.usage
            prompt_tokens = getattr(usage, 'prompt_tokens', 0) or 0
            output_tokens = getattr(usage, 'completion_tokens', 0) or 0
            total_tokens = getattr(usage, 'total_tokens', 0) or 0
            # Check for cached tokens in prompt_tokens_details
            if hasattr(usage, 'prompt_tokens_details') and usage.prompt_tokens_details:
                cached_tokens = getattr(usage.prompt_tokens_details, 'cached_tokens', 0) or 0

    # Calculate cache hit ratio
    cache_hit = cached_tokens > 0
    cache_hit_ratio = None
    if prompt_tokens > 0:
        cache_hit_ratio = round((cached_tokens / prompt_tokens) * 100, 2)

    # Calculate costs based on call type
    if call_type == "transcription" and audio_duration_seconds:
        costs = calculate_audio_costs(model, audio_duration_seconds, output_tokens)
    elif call_type == "emotion" and audio_duration_seconds:
        # Emotion sends audio + text: use audio pricing for input, text pricing for output
        costs = calculate_audio_costs(model, audio_duration_seconds, output_tokens)
    else:
        costs = calculate_text_costs(model, prompt_tokens, output_tokens, cached_tokens, thinking_tokens)

    # Determine response status
    response_status = "success" if not error_message else "error"

    return LLMUsageData(
        call_type=call_type,
        call_subtype=call_subtype,
        model=model,
        consultation_type_code=consultation_type_code,
        template_code=template_code,
        session_id=session_id,
        extraction_id=extraction_id,
        doctor_id=doctor_id,
        api_client_id=api_client_id,
        prompt_token_count=prompt_tokens,
        cached_content_token_count=cached_tokens,
        candidates_token_count=output_tokens,
        thoughts_token_count=thinking_tokens if thinking_tokens > 0 else None,
        total_token_count=total_tokens,
        system_prompt_tokens=system_prompt_tokens,
        user_prompt_tokens=user_prompt_tokens,
        schema_tokens=schema_tokens,
        audio_duration_seconds=audio_duration_seconds,
        audio_size_bytes=audio_size_bytes,
        input_cost_usd=costs["input_cost_usd"],
        output_cost_usd=costs["output_cost_usd"],
        cache_savings_usd=costs["cache_savings_usd"],
        total_cost_usd=costs["total_cost_usd"],
        api_duration_seconds=api_duration_seconds,
        cache_hit=cache_hit,
        cache_hit_ratio=cache_hit_ratio,
        response_status=response_status,
        error_message=error_message,
    )


def create_error_usage(
    call_type: str,
    call_subtype: str,
    model: str,
    error_message: str,
    api_duration_seconds: Optional[float] = None,
    session_id: Optional[uuid.UUID] = None,
    extraction_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    api_client_id: Optional[uuid.UUID] = None,
) -> LLMUsageData:
    """
    Create usage data for a failed API call.

    Args:
        call_type: Type of call (transcription, extraction, emotion, merge)
        call_subtype: Specific function (neo_daily, emotion_analysis, etc.)
        model: Model used
        error_message: Error description
        api_duration_seconds: Time before failure (optional)
        session_id: Recording session ID
        extraction_id: Medical extraction ID
        doctor_id: Doctor ID
        api_client_id: API client ID that made the request

    Returns:
        LLMUsageData object with error status
    """
    return LLMUsageData(
        call_type=call_type,
        call_subtype=call_subtype,
        model=model,
        session_id=session_id,
        extraction_id=extraction_id,
        doctor_id=doctor_id,
        api_client_id=api_client_id,
        api_duration_seconds=api_duration_seconds,
        response_status="error",
        error_message=error_message,
    )


# ============================================================================
# Database Operations
# ============================================================================

async def log_llm_usage(usage_data: LLMUsageData) -> Optional[str]:
    """
    Save LLM usage data to database (fire-and-forget).

    Handles FK constraint errors gracefully by retrying without extraction_id.
    This can happen when parallel emotion extraction completes before the main
    extraction is saved.

    Args:
        usage_data: LLMUsageData object

    Returns:
        UUID of inserted record, or None if failed
    """
    try:
        from services.supabase_service import supabase
        from postgrest.exceptions import APIError

        data = usage_data.to_dict()

        try:
            # Insert into llm_usage_log
            result = supabase.table("llm_usage_log").insert(data).execute()

            if result.data:
                record_id = result.data[0].get("id")
                logger.debug(f"[USAGE] Logged LLM usage: {usage_data.call_type}/{usage_data.call_subtype} -> {record_id}")
                return record_id
            else:
                logger.warning(f"[USAGE] Failed to log LLM usage: no data returned")
                return None

        except APIError as api_error:
            error_details = getattr(api_error, 'details', str(api_error))
            # Check for FK constraint violation on extraction_id
            if '23503' in str(api_error) and 'extraction_id' in str(error_details):
                # Retry without extraction_id (parallel emotion extraction race condition)
                logger.info(f"[USAGE] FK constraint on extraction_id - retrying without extraction_id (parallel emotion extraction)")
                data['extraction_id'] = None
                result = supabase.table("llm_usage_log").insert(data).execute()
                if result.data:
                    record_id = result.data[0].get("id")
                    logger.debug(f"[USAGE] Logged LLM usage (without extraction_id): {usage_data.call_type}/{usage_data.call_subtype} -> {record_id}")
                    return record_id
            # Re-raise for other API errors
            raise

    except Exception as e:
        # Don't fail the main operation if usage logging fails
        logger.error(f"[USAGE] Error logging LLM usage: {e}")
        return None


def log_llm_usage_sync(usage_data: LLMUsageData) -> Optional[str]:
    """
    Synchronous version of log_llm_usage for non-async contexts.

    Handles FK constraint errors gracefully by retrying without extraction_id.

    Args:
        usage_data: LLMUsageData object

    Returns:
        UUID of inserted record, or None if failed
    """
    try:
        from services.supabase_service import supabase
        from postgrest.exceptions import APIError

        data = usage_data.to_dict()

        try:
            # Insert into llm_usage_log
            result = supabase.table("llm_usage_log").insert(data).execute()

            if result.data:
                record_id = result.data[0].get("id")
                logger.debug(f"[USAGE] Logged LLM usage (sync): {usage_data.call_type}/{usage_data.call_subtype} -> {record_id}")
                return record_id
            else:
                logger.warning(f"[USAGE] Failed to log LLM usage (sync): no data returned")
                return None

        except APIError as api_error:
            error_details = getattr(api_error, 'details', str(api_error))
            # Check for FK constraint violation on extraction_id
            if '23503' in str(api_error) and 'extraction_id' in str(error_details):
                # Retry without extraction_id (parallel emotion extraction race condition)
                logger.info(f"[USAGE] FK constraint on extraction_id - retrying without extraction_id (parallel emotion extraction)")
                data['extraction_id'] = None
                result = supabase.table("llm_usage_log").insert(data).execute()
                if result.data:
                    record_id = result.data[0].get("id")
                    logger.debug(f"[USAGE] Logged LLM usage (sync, without extraction_id): {usage_data.call_type}/{usage_data.call_subtype} -> {record_id}")
                    return record_id
            # Re-raise for other API errors
            raise

    except Exception as e:
        # Don't fail the main operation if usage logging fails
        logger.error(f"[USAGE] Error logging LLM usage (sync): {e}")
        return None


# ============================================================================
# Convenience Functions for Common Call Types
# ============================================================================

def log_transcription_usage(
    response: Any,
    model: str,
    api_duration_seconds: float,
    audio_duration_seconds: float,
    audio_size_bytes: int,
    session_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    api_client_id: Optional[uuid.UUID] = None,
    error_message: Optional[str] = None,
    call_subtype: str = "audio_to_text",
) -> LLMUsageData:
    """
    Create usage data for a transcription call.

    Args:
        call_subtype: Type of transcription - "audio_to_text" (default) or "audio_with_emotions"

    Returns LLMUsageData - call log_llm_usage() to save.
    """
    return extract_usage_from_response(
        response=response,
        call_type="transcription",
        call_subtype=call_subtype,
        model=model,
        api_duration_seconds=api_duration_seconds,
        audio_duration_seconds=audio_duration_seconds,
        audio_size_bytes=audio_size_bytes,
        session_id=session_id,
        doctor_id=doctor_id,
        api_client_id=api_client_id,
        error_message=error_message,
    )


def log_extraction_usage(
    response: Any,
    model: str,
    api_duration_seconds: float,
    call_subtype: str,
    consultation_type_code: Optional[str] = None,
    template_code: Optional[str] = None,
    session_id: Optional[uuid.UUID] = None,
    extraction_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    api_client_id: Optional[uuid.UUID] = None,
    system_prompt_tokens: Optional[int] = None,
    user_prompt_tokens: Optional[int] = None,
    schema_tokens: Optional[int] = None,
    error_message: Optional[str] = None,
) -> LLMUsageData:
    """
    Create usage data for an extraction call.

    Returns LLMUsageData - call log_llm_usage() to save.
    """
    return extract_usage_from_response(
        response=response,
        call_type="extraction",
        call_subtype=call_subtype,
        model=model,
        api_duration_seconds=api_duration_seconds,
        consultation_type_code=consultation_type_code,
        template_code=template_code,
        session_id=session_id,
        extraction_id=extraction_id,
        doctor_id=doctor_id,
        api_client_id=api_client_id,
        system_prompt_tokens=system_prompt_tokens,
        user_prompt_tokens=user_prompt_tokens,
        schema_tokens=schema_tokens,
        error_message=error_message,
    )


def log_emotion_usage(
    response: Any,
    model: str,
    api_duration_seconds: float,
    extraction_id: Optional[uuid.UUID] = None,
    session_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    api_client_id: Optional[uuid.UUID] = None,
    audio_duration_seconds: Optional[float] = None,
    audio_size_bytes: Optional[int] = None,
    error_message: Optional[str] = None,
) -> LLMUsageData:
    """
    Create usage data for an emotion analysis call.

    Returns LLMUsageData - call log_llm_usage() to save.
    """
    return extract_usage_from_response(
        response=response,
        call_type="emotion",
        call_subtype="emotion_analysis",
        model=model,
        api_duration_seconds=api_duration_seconds,
        session_id=session_id,
        extraction_id=extraction_id,
        doctor_id=doctor_id,
        api_client_id=api_client_id,
        audio_duration_seconds=audio_duration_seconds,
        audio_size_bytes=audio_size_bytes,
        error_message=error_message,
    )


def log_merge_usage(
    response: Any,
    model: str,
    api_duration_seconds: float,
    consultation_type_code: Optional[str] = None,
    session_id: Optional[uuid.UUID] = None,
    extraction_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    api_client_id: Optional[uuid.UUID] = None,
    error_message: Optional[str] = None,
    call_subtype: Optional[str] = None,
) -> LLMUsageData:
    """
    Create usage data for a merge call.

    Returns LLMUsageData - call log_llm_usage() to save.
    """
    return extract_usage_from_response(
        response=response,
        call_type="merge",
        call_subtype=call_subtype or "ai_contextual_merge",
        model=model,
        api_duration_seconds=api_duration_seconds,
        consultation_type_code=consultation_type_code,
        session_id=session_id,
        extraction_id=extraction_id,
        doctor_id=doctor_id,
        api_client_id=api_client_id,
        error_message=error_message,
    )


def create_live_api_usage(
    model: str,
    session_duration_seconds: float,
    audio_duration_seconds: Optional[float] = None,
    session_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    api_client_id: Optional[uuid.UUID] = None,
    consultation_type_code: Optional[str] = None,
    template_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> LLMUsageData:
    """
    Create usage data for Gemini Live API session (client-side WebSocket).

    For Live API, we can't get exact token counts since the WebSocket connection
    goes directly to Google. We track:
    - Session duration (how long the WebSocket was open)
    - Audio duration (estimated from recording time)
    - Context (session_id, doctor_id)

    Cost estimation for Live API:
    - Native audio models (gemini-2.5-flash-native-audio) have different pricing
    - Audio input: $0.00004/second (or similar - check current pricing)
    - Text output: Standard token pricing

    Returns LLMUsageData - call log_llm_usage() to save.
    """
    # Estimate cost based on audio duration for Live API
    # Pricing for gemini-2.5-flash-native-audio-preview (approximate)
    # Audio input: ~$0.00004/second, Text output: varies
    # These are estimates since we don't have exact token counts
    audio_input_cost_per_second = 0.00004  # USD per second of audio

    estimated_input_cost = 0.0
    if audio_duration_seconds:
        estimated_input_cost = audio_duration_seconds * audio_input_cost_per_second

    # For Live API, we estimate output tokens based on audio duration
    # Typical transcription generates ~1 token per 0.5 seconds of audio
    estimated_output_tokens = int((audio_duration_seconds or 0) * 2)
    output_cost_per_token = 0.0000004  # Flash output pricing
    estimated_output_cost = estimated_output_tokens * output_cost_per_token

    return LLMUsageData(
        call_type="live_transcription",
        call_subtype="gemini_live_api",
        model=model,
        prompt_token_count=None,  # Not available for WebSocket
        cached_content_token_count=None,
        candidates_token_count=estimated_output_tokens,
        total_token_count=estimated_output_tokens,
        audio_duration_seconds=audio_duration_seconds,
        audio_size_bytes=None,
        input_cost_usd=estimated_input_cost,
        output_cost_usd=estimated_output_cost,
        cache_savings_usd=0.0,
        total_cost_usd=estimated_input_cost + estimated_output_cost,
        api_duration_seconds=session_duration_seconds,
        cache_hit=False,
        cache_hit_ratio=0.0,
        response_status="success" if not error_message else "error",
        error_message=error_message,
        session_id=session_id,
        extraction_id=None,
        doctor_id=doctor_id,
        api_client_id=api_client_id,
        consultation_type_code=consultation_type_code,
        template_code=template_code,
    )

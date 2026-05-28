"""
Gemini Context Caching Service for optimized API performance.

This service manages explicit caching of system prompts to:
1. Reduce token costs (cached tokens billed at reduced rate)
2. Improve response latency (pre-processed prompts)
3. Optimize two-part extractions (same cache used for both parts)

Reference: https://ai.google.dev/gemini-api/docs/caching?lang=python

Token Requirements:
- Gemini 2.5 Flash: minimum 1,024 tokens
- Gemini 2.5 Pro: minimum 4,096 tokens
"""

import os
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Debug logging for Google SDK - track cache API calls
logging.getLogger("google.api_core.retry").setLevel(logging.DEBUG)  # Log retries
logging.getLogger("httpx").setLevel(logging.DEBUG)  # Log all HTTP requests (shows cache operations)
logging.getLogger("google_genai").setLevel(logging.DEBUG)  # Log google-genai SDK internals

# Initialize Gemini client using factory (supports both Gemini API and Vertex AI)
from services.gemini_client_factory import get_gemini_client

client = get_gemini_client()

# Thread-safe cache registry
_cache_registry: Dict[str, dict] = {}
_cache_lock = threading.Lock()

# Default TTL: 1 hour (in seconds)
DEFAULT_TTL_SECONDS = 3600

# Minimum token requirements for caching (from Gemini API docs)
# These are approximate - actual tokenization may vary
MIN_TOKENS_BY_MODEL = {
    "gemini-2.5-pro": 4096,
    "gemini-2.5-flash": 2048,         # Based on actual API error
    "gemini-3-pro": 4096,             # Vertex AI
    "gemini-3.1-pro-preview": 4096,   # Gemini API (replaces deprecated gemini-3-pro-preview)
}
DEFAULT_MIN_TOKENS = 2048

# Approximate chars per token (conservative estimate)
CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Estimate token count from text length (conservative estimate)."""
    return len(text) // CHARS_PER_TOKEN


def _get_min_tokens_for_model(model: str) -> int:
    """Get minimum token requirement for a model."""
    return MIN_TOKENS_BY_MODEL.get(model, DEFAULT_MIN_TOKENS)


def _get_cache_key(prompt_type: str, model: str) -> str:
    """Generate a unique cache key for the given prompt type and model."""
    return f"{prompt_type}_{model}"


def _is_cache_valid(cache_entry: dict) -> bool:
    """Check if a cache entry is still valid (not expired)."""
    if not cache_entry:
        return False

    expires_at = cache_entry.get("expires_at")
    if not expires_at:
        return False

    # Compare with current UTC time
    now = datetime.now(timezone.utc)
    return now < expires_at


def get_or_create_cache(
    prompt_type: str,
    system_instruction: str,
    model: str = "gemini-2.5-flash",
    ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> Optional[str]:
    """
    Get existing cache or create new one for the given system instruction.

    This function is thread-safe and handles cache lifecycle automatically.

    Args:
        prompt_type: Unique identifier for the prompt type (e.g., "NEO_DAILY", "OPHTHAL_DISCHARGE")
        system_instruction: The system prompt text to cache
        model: Gemini model to use (must match when using cache)
        ttl_seconds: Time-to-live in seconds (default: 1 hour)

    Returns:
        Cache name for use in generate_content config, or None if caching failed

    Example:
        cache_name = get_or_create_cache(
            prompt_type="NEO_DAILY",
            system_instruction=NEO_DAILY_PROMPT_SYSTEM,
            model="gemini-2.5-flash",
            ttl_seconds=3600
        )

        # Use in generate_content:
        response = await client.aio.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                cached_content=cache_name,
                ...
            )
        )
    """
    import time
    cache_start = time.time()
    cache_key = _get_cache_key(prompt_type, model)

    with _cache_lock:
        # Check if valid cache exists
        if cache_key in _cache_registry:
            cache_entry = _cache_registry[cache_key]
            if _is_cache_valid(cache_entry):
                cache_duration = time.time() - cache_start
                logger.info(f"[TIMING_CACHE] ♻️ Cache HIT for '{prompt_type}': {cache_duration:.3f}s")
                return cache_entry["name"]
            else:
                # Cache expired, remove from registry
                logger.info(f"[CACHE] 🗑️ Cache expired for '{prompt_type}', creating new one")
                del _cache_registry[cache_key]

    # Pre-check: Skip cache creation if prompt is too small (saves ~0.2s API call)
    estimated_tokens = _estimate_tokens(system_instruction)
    min_tokens = _get_min_tokens_for_model(model)

    if estimated_tokens < min_tokens:
        logger.info(
            f"[CACHE] ⏭️ SKIPPED for '{prompt_type}': "
            f"estimated {estimated_tokens} tokens < {min_tokens} minimum for {model}"
        )
        return None

    # Create new cache outside the lock (API call can be slow)
    try:
        ttl_str = f"{ttl_seconds}s"

        # Calculate expiration time for local tracking
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

        logger.info(f"[CACHE] 🆕 Creating new cache for '{prompt_type}' (TTL: {ttl_str}, ~{estimated_tokens} tokens)")

        # Create cache with system instruction
        cache_create_start = time.time()
        cache = client.caches.create(
            model=f'models/{model}',
            config=types.CreateCachedContentConfig(
                display_name=prompt_type,
                system_instruction=system_instruction,
                ttl=ttl_str
            )
        )
        cache_create_duration = time.time() - cache_create_start

        # Store in registry
        with _cache_lock:
            _cache_registry[cache_key] = {
                "name": cache.name,
                "model": model,
                "prompt_type": prompt_type,
                "created_at": datetime.now(timezone.utc),
                "expires_at": expires_at,
                "ttl_seconds": ttl_seconds
            }

        total_cache_duration = time.time() - cache_start
        logger.info(f"[TIMING_CACHE] 🆕 Cache CREATED for '{prompt_type}': API={cache_create_duration:.3f}s, total={total_cache_duration:.3f}s")
        return cache.name

    except Exception as e:
        total_cache_duration = time.time() - cache_start
        logger.warning(f"[TIMING_CACHE] ⚠️ Cache FAILED for '{prompt_type}': {total_cache_duration:.3f}s - {e}")
        logger.warning("[CACHE] Falling back to non-cached request")
        return None


def invalidate_cache(prompt_type: str, model: str = "gemini-2.5-flash") -> bool:
    """
    Invalidate (delete) a cached prompt.

    Args:
        prompt_type: Unique identifier for the prompt type
        model: Gemini model

    Returns:
        True if cache was invalidated, False otherwise
    """
    cache_key = _get_cache_key(prompt_type, model)

    with _cache_lock:
        if cache_key not in _cache_registry:
            logger.info(f"[CACHE] No cache found for '{prompt_type}'")
            return False

        cache_entry = _cache_registry[cache_key]
        cache_name = cache_entry.get("name")

    # Delete from Gemini API
    try:
        if cache_name:
            client.caches.delete(name=cache_name)
            logger.info(f"[CACHE] 🗑️ Deleted cache from API: {cache_name}")
    except Exception as e:
        logger.warning(f"[CACHE] Failed to delete cache from API: {e}")

    # Remove from local registry
    with _cache_lock:
        if cache_key in _cache_registry:
            del _cache_registry[cache_key]

    logger.info(f"[CACHE] ✅ Cache invalidated for '{prompt_type}'")
    return True


def refresh_cache(
    prompt_type: str,
    system_instruction: str,
    model: str = "gemini-2.5-flash",
    ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> Optional[str]:
    """
    Force refresh a cache (delete and recreate).

    Use this when the system prompt has been updated.

    Args:
        prompt_type: Unique identifier for the prompt type
        system_instruction: The updated system prompt text
        model: Gemini model
        ttl_seconds: New TTL in seconds

    Returns:
        New cache name, or None if creation failed
    """
    logger.info(f"[CACHE] 🔄 Refreshing cache for '{prompt_type}'")

    # Invalidate existing cache
    invalidate_cache(prompt_type, model)

    # Create new cache
    return get_or_create_cache(prompt_type, system_instruction, model, ttl_seconds)


def get_cache_stats() -> Dict[str, Any]:
    """
    Get statistics about cached prompts.

    Returns:
        Dict with cache statistics
    """
    with _cache_lock:
        total_caches = len(_cache_registry)
        valid_caches = sum(1 for entry in _cache_registry.values() if _is_cache_valid(entry))
        expired_caches = total_caches - valid_caches

        cache_details = []
        for key, entry in _cache_registry.items():
            cache_details.append({
                "prompt_type": entry.get("prompt_type"),
                "model": entry.get("model"),
                "created_at": entry.get("created_at").isoformat() if entry.get("created_at") else None,
                "expires_at": entry.get("expires_at").isoformat() if entry.get("expires_at") else None,
                "is_valid": _is_cache_valid(entry)
            })

        return {
            "total_caches": total_caches,
            "valid_caches": valid_caches,
            "expired_caches": expired_caches,
            "caches": cache_details
        }


def list_all_caches() -> list:
    """
    List all caches from the Gemini API.

    Returns:
        List of cache metadata from API
    """
    try:
        caches = []
        for cache in client.caches.list():
            caches.append({
                "name": cache.name,
                "display_name": cache.display_name if hasattr(cache, "display_name") else None,
                "model": cache.model if hasattr(cache, "model") else None,
                "expire_time": str(cache.expire_time) if hasattr(cache, "expire_time") else None
            })
        return caches
    except Exception as e:
        logger.error(f"[CACHE] Failed to list caches: {e}")
        return []


def cleanup_expired_caches() -> int:
    """
    Remove expired caches from local registry.

    Note: This only cleans up the local registry. Caches in the Gemini API
    are automatically cleaned up based on TTL.

    Returns:
        Number of expired caches removed
    """
    removed_count = 0

    with _cache_lock:
        expired_keys = [
            key for key, entry in _cache_registry.items()
            if not _is_cache_valid(entry)
        ]

        for key in expired_keys:
            del _cache_registry[key]
            removed_count += 1

    if removed_count > 0:
        logger.info(f"[CACHE] 🧹 Cleaned up {removed_count} expired cache entries")

    return removed_count


# ============================================================================
# Pre-defined Cache Keys for Medical Extraction Prompts
# ============================================================================

# These constants define the cache keys for each prompt type.
# Use these when calling get_or_create_cache() for consistency.

CACHE_KEY_NEO_DAILY = "NEO_DAILY"
CACHE_KEY_NEO_PROFORMA = "NEO_PROFORMA"
CACHE_KEY_NEO_OP = "NEO_OP"
CACHE_KEY_OPHTHAL_DISCHARGE = "OPHTHAL_DISCHARGE"
CACHE_KEY_OPHTHALMOLOGY = "OPHTHALMOLOGY"
CACHE_KEY_OPHTHAL_FULL = "OPHTHAL_FULL"
CACHE_KEY_OPHTHAL_POSTOP_RX = "OPHTHAL_POSTOP_RX"
CACHE_KEY_OPHTHAL_PRESCRIPTION = "OPHTHAL_PRESCRIPTION"
CACHE_KEY_EMOTION_ANALYSIS = "EMOTION_ANALYSIS"
CACHE_KEY_CONSULTATION_INSIGHTS = "CONSULTATION_INSIGHTS"

# Template-based caches use format: "TEMPLATE_{template_code}"
def get_template_cache_key(template_code: str) -> str:
    """Generate cache key for template-based extraction."""
    return f"TEMPLATE_{template_code}"

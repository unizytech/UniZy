"""
Gemini Client Factory - Unified client creation for Gemini API and Vertex AI.

Supports feature flag switching:
- USE_VERTEX_AI=false: Uses GEMINI_API_KEY (Gemini API) - Development mode
- USE_VERTEX_AI=true: Uses GCP_PROJECT_ID + service account (Vertex AI) - Production mode

This factory enables Hybrid Mode where:
- Batch operations (transcription, extraction) use Vertex AI for audit logs and compliance
- Live API continues using Gemini API (ephemeral tokens not supported on Vertex AI)

Credentials for Vertex AI can be provided via:
- GOOGLE_APPLICATION_CREDENTIALS: Path to service account JSON file (local dev)
- GCP_CREDENTIALS_BASE64: Base64-encoded service account JSON (cloud deployments)

Reference: https://googleapis.github.io/python-genai/
"""

import os
import base64
import tempfile
import logging
from typing import Optional
from google import genai
from google.genai import types
import httpx

logger = logging.getLogger(__name__)

# Shared HTTP options: connection pool tuning + retry for transient errors
_http_options = types.HttpOptions(
    # Retry transient 5xx / 429 at the SDK level (before our application retry)
    # Configure httpx async client with longer keepalive and explicit connect timeout
    async_client_args={
        "timeout": httpx.Timeout(
            connect=15.0,    # Fail fast on connect (vs 14s OS TCP timeout)
            read=120.0,      # Must not exceed asyncio.wait_for timeouts in gemini_service
            write=60.0,      # Write timeout for uploading audio
            pool=30.0,       # Pool acquisition timeout
        ),
        "limits": httpx.Limits(
            max_connections=100,
            max_keepalive_connections=30,
            keepalive_expiry=120,  # Keep warm connections for 2 minutes
        ),
    },
)

# Singleton client instance
_client: Optional[genai.Client] = None

# Cached setting from DB (None = not yet queried)
_use_vertex_ai_cached: Optional[bool] = None

# Track temp credentials file for cleanup
_temp_credentials_file: Optional[str] = None


def _get_use_vertex_ai_from_db() -> Optional[bool]:
    """
    Query app_settings table for use_vertex_ai setting.

    Returns:
        True/False if found in DB, None if query fails or table doesn't exist
    """
    try:
        from services.supabase_service import supabase
        result = supabase.table("app_settings").select("value").eq("key", "use_vertex_ai").execute()
        if result.data and len(result.data) > 0:
            value = result.data[0]["value"].lower()
            return value == "true"
    except Exception as e:
        logger.warning(f"[CLIENT_FACTORY] Failed to read use_vertex_ai from DB, falling back to env var: {e}")
    return None


def _resolve_use_vertex_ai() -> bool:
    """
    Resolve the use_vertex_ai setting. DB overrides env var.

    Returns:
        True if Vertex AI should be used, False for Gemini API
    """
    global _use_vertex_ai_cached

    if _use_vertex_ai_cached is not None:
        return _use_vertex_ai_cached

    # Try DB first
    db_value = _get_use_vertex_ai_from_db()
    if db_value is not None:
        _use_vertex_ai_cached = db_value
        logger.info(f"[CLIENT_FACTORY] use_vertex_ai resolved from DB: {db_value}")
        return db_value

    # Fallback to env var
    env_value = os.getenv("USE_VERTEX_AI", "false").lower() == "true"
    _use_vertex_ai_cached = env_value
    logger.info(f"[CLIENT_FACTORY] use_vertex_ai resolved from env var: {env_value}")
    return env_value


def _setup_credentials_from_base64() -> bool:
    """
    Set up Google credentials from base64-encoded JSON env var.

    This is useful for cloud deployments (Railway, Heroku, etc.) where
    you can't easily mount files but can set environment variables.

    Returns:
        True if credentials were set up from base64, False otherwise
    """
    global _temp_credentials_file

    credentials_base64 = os.getenv("GCP_CREDENTIALS_BASE64")
    if not credentials_base64:
        return False

    # Check if GOOGLE_APPLICATION_CREDENTIALS is already set and valid
    existing_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if existing_creds and os.path.exists(existing_creds):
        logger.info(f"[CLIENT_FACTORY] Using existing credentials file: {existing_creds}")
        return True

    try:
        # Decode base64 credentials
        credentials_json = base64.b64decode(credentials_base64).decode('utf-8')

        # Write to a temp file
        fd, temp_path = tempfile.mkstemp(suffix='.json', prefix='gcp_creds_')
        with os.fdopen(fd, 'w') as f:
            f.write(credentials_json)

        # Set the environment variable
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_path
        _temp_credentials_file = temp_path

        logger.info(f"[CLIENT_FACTORY] Created credentials file from GCP_CREDENTIALS_BASE64: {temp_path}")
        return True

    except Exception as e:
        logger.error(f"[CLIENT_FACTORY] Failed to decode GCP_CREDENTIALS_BASE64: {e}")
        return False


def get_gemini_client() -> genai.Client:
    """
    Get or create a Gemini client based on configuration.

    Uses singleton pattern for efficient connection reuse.

    Returns:
        genai.Client configured for either Gemini API or Vertex AI

    Raises:
        ValueError: If required environment variables are not set
    """
    global _client

    if _client is not None:
        return _client

    use_vertex = _resolve_use_vertex_ai()

    if use_vertex:
        _client = _create_vertex_client()
    else:
        _client = _create_gemini_client()

    return _client


def _create_gemini_client() -> genai.Client:
    """Create client for Gemini API (development mode)."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY required when USE_VERTEX_AI=false")

    logger.info("[CLIENT_FACTORY] Creating Gemini API client (with retry + connection pool tuning)")
    return genai.Client(api_key=api_key, http_options=_http_options)


def _create_vertex_client() -> genai.Client:
    """
    Create client for Vertex AI (production mode).

    Credentials are resolved in this order:
    1. GCP_CREDENTIALS_BASE64 env var (base64-encoded JSON, for cloud deployments)
    2. GOOGLE_APPLICATION_CREDENTIALS env var (file path, for local dev)
    3. Application Default Credentials (ADC)
    """
    project_id = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_LOCATION", "global")

    if not project_id:
        raise ValueError("GCP_PROJECT_ID required when USE_VERTEX_AI=true")

    # Set up credentials from base64 if available (for cloud deployments)
    _setup_credentials_from_base64()

    # Log current credentials status
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        if os.path.exists(creds_path):
            logger.info(f"[CLIENT_FACTORY] Credentials file exists: {creds_path}")
        else:
            logger.warning(f"[CLIENT_FACTORY] Credentials file NOT FOUND: {creds_path}")
    else:
        logger.info("[CLIENT_FACTORY] No GOOGLE_APPLICATION_CREDENTIALS set, using ADC")

    logger.info(f"[CLIENT_FACTORY] Creating Vertex AI client: project={project_id}, location={location} (with retry + connection pool tuning)")

    # The google-genai SDK automatically uses:
    # 1. GOOGLE_APPLICATION_CREDENTIALS if set (service account key file)
    # 2. Application Default Credentials (ADC) otherwise
    return genai.Client(
        vertexai=True,
        project=project_id,
        location=location,
        http_options=_http_options,
    )


def is_vertex_ai_mode() -> bool:
    """
    Check if running in Vertex AI mode.

    Returns:
        True if Vertex AI is enabled (DB setting overrides env var)
    """
    return _resolve_use_vertex_ai()


async def warmup_connection_pool() -> None:
    """
    Pre-warm the Gemini API connection pool by making a lightweight API call.

    This establishes a TCP+TLS connection to generativelanguage.googleapis.com
    (or Vertex AI endpoint) at server startup, so the first recording doesn't
    suffer a cold-start penalty (~14s if multiple concurrent connections race).

    Called from main.py on_startup.
    """
    try:
        client = get_gemini_client()
        # Lightweight call — just list models (tiny response, no tokens used)
        pager = await client.aio.models.list(config={"page_size": 1})
        if pager.page:
            logger.info(f"[CLIENT_FACTORY] Connection pool warmed up (verified model: {pager.page[0].name})")
        else:
            logger.info("[CLIENT_FACTORY] Connection pool warmed up (models list returned)")
    except Exception as e:
        # Non-fatal — pool will warm up on first actual request
        logger.warning(f"[CLIENT_FACTORY] Connection warmup failed (non-fatal): {e}")


def reset_client() -> None:
    """
    Reset the singleton client instance and cached settings.

    Called when use_vertex_ai is toggled via admin API.
    The next get_gemini_client() call will re-query the DB and create a new client.
    """
    global _client, _use_vertex_ai_cached
    _client = None
    _use_vertex_ai_cached = None
    logger.info("[CLIENT_FACTORY] Client instance and cached settings reset")

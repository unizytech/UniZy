"""
Authentication Service

Handles all authentication and authorization logic:
- API Key generation and verification (for EHR clients)
- Service JWT generation and verification (for Mobile/Web apps)
- Supabase JWT verification (for Admin dashboard)
- Rate limiting checks
- Client context building

Security Notes:
- API keys are bcrypt hashed before storage
- JWTs use HS256 algorithm with per-client secrets
- Supabase JWTs are verified using JWKS public keys (ES256/RS256)
  fetched from the Supabase Auth JWKS endpoint
"""

import hashlib
import os
import ssl
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from uuid import UUID

import bcrypt
import jwt
from jwt import PyJWKClient
from fastapi import HTTPException, Request
from cachetools import TTLCache

# ============================================================================
# In-Memory Caches (TTL-based)
# ============================================================================

# Cache for admin_users lookups - 10 minute TTL
# Key: auth_user_id (str), Value: admin_user dict or None
_admin_users_cache: TTLCache = TTLCache(maxsize=100, ttl=600)  # 10 minutes

# Cache for counsellor school_id lookups - 10 minute TTL
# Key: counsellor_id (str), Value: school_id (str) or None
_doctor_hospital_cache: TTLCache = TTLCache(maxsize=500, ttl=600)  # 10 minutes


# ============================================================================
# Cache Invalidation Functions
# ============================================================================

def invalidate_admin_users_cache(auth_user_id: Optional[str] = None) -> int:
    """
    Invalidate admin_users cache entries.

    Args:
        auth_user_id: Specific auth user to invalidate, or None to clear all

    Returns:
        Number of entries invalidated
    """
    global _admin_users_cache
    if auth_user_id:
        cache_key = auth_user_id
        if cache_key in _admin_users_cache:
            del _admin_users_cache[cache_key]
            logger.debug(f"[CACHE_INVALIDATE] Cleared admin_users cache for {auth_user_id[:8]}...")
            return 1
        return 0
    else:
        count = len(_admin_users_cache)
        _admin_users_cache.clear()
        logger.debug(f"[CACHE_INVALIDATE] Cleared all admin_users cache ({count} entries)")
        return count


def invalidate_auth_counsellor_school_cache(counsellor_id: Optional[str] = None) -> int:
    """
    Invalidate counsellor_school cache entries in auth_service.

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
            logger.debug(f"[CACHE_INVALIDATE] Cleared auth counsellor_school cache for counsellor {cache_key[:8]}...")
            return 1
        return 0
    else:
        count = len(_doctor_hospital_cache)
        _doctor_hospital_cache.clear()
        logger.debug(f"[CACHE_INVALIDATE] Cleared all auth counsellor_school cache ({count} entries)")
        return count


# Try to import certifi for SSL certificates (macOS fix)
try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = None
    logging.warning("certifi not installed - SSL verification may fail on macOS")

from models.auth_models import (
    ClientContext,
    APIClientCreate,
    APIClientResponse,
    APIKeyCreateResponse,
    APIKeyRotateResponse,
    ServiceJWTResponse,
    ClientCredentialsResponse,
    ClientRefreshResponse,
    DEFAULT_SCOPES,
)
from services.supabase_service import supabase, retry_on_network_error

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

# Supabase URL for JWKS endpoint
SUPABASE_URL = os.getenv("SUPABASE_URL", "")

# Legacy JWT secret (for HS256 fallback during migration)
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

# JWKS client for verifying Supabase JWTs using public keys
# This fetches public keys from: {SUPABASE_URL}/auth/v1/.well-known/jwks.json
# Supports ES256 (ECC P-256), RS256 (RSA), and HS256 (legacy) algorithms
_jwks_client: Optional[PyJWKClient] = None

def get_jwks_client() -> Optional[PyJWKClient]:
    """
    Get or create the JWKS client for Supabase JWT verification.

    Uses lazy initialization to avoid errors during module import
    if SUPABASE_URL is not yet configured.

    Returns None if JWKS client cannot be created (e.g., SSL issues on macOS).
    """
    global _jwks_client
    if _jwks_client is None:
        if not SUPABASE_URL:
            logger.warning("SUPABASE_URL not configured, JWKS client not available")
            return None
        jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        try:
            # Use SSL context with certifi certificates if available (fixes macOS SSL issues)
            if SSL_CONTEXT:
                _jwks_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=600, ssl_context=SSL_CONTEXT)
            else:
                _jwks_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=600)
            logger.debug(f"JWKS client initialized with URL: {jwks_url}")
        except Exception as e:
            logger.error(f"Failed to initialize JWKS client: {e}")
            return None
    return _jwks_client

# API key prefix patterns
API_KEY_PREFIXES = {
    "ehr": "ehr_",
    "mobile_app": "mob_",
    "web_app": "web_",
}


# ============================================================================
# API Key Generation & Verification (for EHR clients)
# ============================================================================

def generate_api_key(client_type: str) -> Tuple[str, str, str]:
    """
    Generate a new API key for a client.

    Returns:
        Tuple of (full_api_key, api_key_prefix, api_key_hash)
    """
    prefix = API_KEY_PREFIXES.get(client_type, "api_")
    random_part = secrets.token_urlsafe(32)  # 256 bits of entropy
    full_key = f"{prefix}{random_part}"
    key_prefix = full_key[:8]  # First 8 chars for identification
    key_hash = hash_api_key(full_key)

    return full_key, key_prefix, key_hash


def hash_api_key(api_key: str) -> str:
    """Hash an API key using bcrypt"""
    return bcrypt.hashpw(api_key.encode(), bcrypt.gensalt()).decode()


def verify_api_key_hash(api_key: str, api_key_hash: str) -> bool:
    """Verify an API key against its hash"""
    try:
        return bcrypt.checkpw(api_key.encode(), api_key_hash.encode())
    except Exception:
        return False


# ============================================================================
# Client Secret & Refresh Token Helpers (for OAuth token-mode EHR clients)
# ============================================================================

def generate_client_secret() -> Tuple[str, str]:
    """
    Generate a client secret for token-mode EHR clients.

    Returns:
        Tuple of (plaintext_secret, sha256_hash)
    """
    plaintext = f"secret_{secrets.token_urlsafe(48)}"
    secret_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, secret_hash


def generate_refresh_token() -> Tuple[str, str]:
    """
    Generate a refresh token.

    Returns:
        Tuple of (plaintext_token, sha256_hash)
    """
    plaintext = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, token_hash


async def store_refresh_token(client_id: UUID, token_hash: str, expires_in_days: int = 30) -> None:
    """Store a refresh token hash in the database."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    retry_on_network_error(
        lambda: supabase.table("refresh_tokens").insert({
            "client_id": str(client_id),
            "token_hash": token_hash,
            "expires_at": expires_at.isoformat(),
        }).execute()
    )


async def validate_and_revoke_refresh_token(client_id: UUID, refresh_token: str) -> bool:
    """
    Validate a refresh token and revoke it (one-time use with rotation).

    Returns True if valid, raises HTTPException otherwise.
    """
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

    # Look up the token
    result = retry_on_network_error(
        lambda: supabase.table("refresh_tokens")
        .select("id, client_id, expires_at, is_revoked")
        .eq("token_hash", token_hash)
        .eq("client_id", str(client_id))
        .eq("is_revoked", False)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    token_record = result.data[0]

    # Check expiry
    expires_at = datetime.fromisoformat(token_record["expires_at"].replace("Z", "+00:00"))
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token has expired")

    # Revoke it (rotation: each token is single-use)
    retry_on_network_error(
        lambda: supabase.table("refresh_tokens")
        .update({"is_revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", token_record["id"])
        .execute()
    )

    return True


async def revoke_all_refresh_tokens(client_id: UUID) -> int:
    """Revoke all refresh tokens for a client. Returns count revoked."""
    result = retry_on_network_error(
        lambda: supabase.table("refresh_tokens")
        .update({"is_revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat()})
        .eq("client_id", str(client_id))
        .eq("is_revoked", False)
        .execute()
    )
    count = len(result.data) if result.data else 0
    if count > 0:
        logger.info(f"[AUTH] Revoked {count} refresh tokens for client {client_id}")
    return count


async def exchange_client_credentials(client_id: UUID, client_secret: str) -> ClientCredentialsResponse:
    """
    Exchange client_id + client_secret for an access token + refresh token.
    """
    # Look up the client
    result = retry_on_network_error(
        lambda: supabase.table("api_clients")
        .select("*")
        .eq("id", str(client_id))
        .eq("is_active", True)
        .eq("auth_mode", "token")
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    client = result.data[0]

    # Verify client secret
    if not client.get("client_secret_hash"):
        raise HTTPException(status_code=401, detail="Client not configured for token auth")

    secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
    if secret_hash != client["client_secret_hash"]:
        logger.warning(f"[AUTH] Client secret mismatch for client {client['client_name']}")
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    # Generate access token (JWT) — expiry from DB config
    if not client.get("jwt_secret"):
        raise HTTPException(status_code=500, detail="Client JWT secret not configured")

    expiry_minutes = client.get("token_expiry_minutes", 120)
    jwt_response = generate_service_jwt(
        client_id=UUID(client["id"]),
        client_name=client["client_name"],
        client_type=client["client_type"],
        jwt_secret=client["jwt_secret"],
        scopes=client.get("scopes", []),
        school_id=UUID(client["school_id"]) if client.get("school_id") else None,
        allowed_counsellor_ids=[UUID(d) for d in client["allowed_counsellor_ids"]] if client.get("allowed_counsellor_ids") else None,
        expires_in_hours=expiry_minutes / 60,
    )

    # Generate refresh token — 30 day expiry
    refresh_plaintext, refresh_hash = generate_refresh_token()
    await store_refresh_token(UUID(client["id"]), refresh_hash, expires_in_days=30)

    # Update last_used_at
    try:
        retry_on_network_error(
            lambda: supabase.table("api_clients")
            .update({"last_used_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", str(client_id))
            .execute()
        )
    except Exception:
        pass

    return ClientCredentialsResponse(
        access_token=jwt_response.token,
        refresh_token=refresh_plaintext,
        token_type="Bearer",
        expires_in=expiry_minutes * 60,
        expires_at=jwt_response.expires_at,
    )


async def refresh_client_token(client_id: UUID, refresh_token: str) -> ClientRefreshResponse:
    """
    Exchange a refresh token for a new access token + new refresh token (rotation).
    """
    # Validate and revoke the old refresh token
    await validate_and_revoke_refresh_token(client_id, refresh_token)

    # Look up the client
    result = retry_on_network_error(
        lambda: supabase.table("api_clients")
        .select("*")
        .eq("id", str(client_id))
        .eq("is_active", True)
        .eq("auth_mode", "token")
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=401, detail="Client not found or inactive")

    client = result.data[0]

    if not client.get("jwt_secret"):
        raise HTTPException(status_code=500, detail="Client JWT secret not configured")

    # Generate new access token — expiry from DB config
    expiry_minutes = client.get("token_expiry_minutes", 120)
    jwt_response = generate_service_jwt(
        client_id=UUID(client["id"]),
        client_name=client["client_name"],
        client_type=client["client_type"],
        jwt_secret=client["jwt_secret"],
        scopes=client.get("scopes", []),
        school_id=UUID(client["school_id"]) if client.get("school_id") else None,
        allowed_counsellor_ids=[UUID(d) for d in client["allowed_counsellor_ids"]] if client.get("allowed_counsellor_ids") else None,
        expires_in_hours=expiry_minutes / 60,
    )

    # Generate new refresh token — 30 days
    new_refresh_plaintext, new_refresh_hash = generate_refresh_token()
    await store_refresh_token(UUID(client["id"]), new_refresh_hash, expires_in_days=30)

    return ClientRefreshResponse(
        access_token=jwt_response.token,
        refresh_token=new_refresh_plaintext,
        token_type="Bearer",
        expires_in=expiry_minutes * 60,
        expires_at=jwt_response.expires_at,
    )


async def verify_api_key(api_key: str) -> ClientContext:
    """
    Verify an API key and return the client context.

    Args:
        api_key: The API key from Authorization: Bearer header

    Returns:
        ClientContext with client info

    Raises:
        HTTPException: If API key is invalid or client is inactive
    """
    # Extract prefix for lookup
    if len(api_key) < 8:
        raise HTTPException(status_code=401, detail="Invalid API key format")

    api_key_prefix = api_key[:8]

    # Look up client by prefix
    try:
        result = retry_on_network_error(
            lambda: supabase.table("api_clients")
            .select("*")
            .eq("api_key_prefix", api_key_prefix)
            .eq("is_active", True)
            .execute()
        )

        if not result.data:
            logger.warning(f"API key lookup failed for prefix: {api_key_prefix}")
            raise HTTPException(status_code=401, detail="Invalid API key")

        client = result.data[0]

        # Verify the full API key hash
        if not client.get("api_key_hash"):
            raise HTTPException(status_code=401, detail="Invalid API key")

        if not verify_api_key_hash(api_key, client["api_key_hash"]):
            logger.warning(f"API key hash verification failed for client: {client['client_name']}")
            raise HTTPException(status_code=401, detail="Invalid API key")

        # Build and return client context
        return ClientContext(
            client_type=client["client_type"],
            client_id=UUID(client["id"]),
            client_name=client["client_name"],
            school_id=UUID(client["school_id"]) if client.get("school_id") else None,
            allowed_counsellor_ids=[UUID(d) for d in client["allowed_counsellor_ids"]] if client.get("allowed_counsellor_ids") else None,
            scopes=client.get("scopes", []),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying API key: {e}")
        raise HTTPException(status_code=500, detail="Authentication error")


# ============================================================================
# Service JWT Generation & Verification (for Mobile/Web apps)
# ============================================================================

def generate_service_jwt(
    client_id: UUID,
    client_name: str,
    client_type: str,
    jwt_secret: str,
    scopes: list,
    school_id: Optional[UUID] = None,
    allowed_counsellor_ids: Optional[list] = None,
    expires_in_hours: int = 24,
) -> ServiceJWTResponse:
    """
    Generate a service JWT for a mobile/web app client.

    Args:
        client_id: The API client ID
        client_name: Client name for display
        client_type: 'mobile_app' or 'web_app'
        jwt_secret: Per-client secret for signing
        scopes: List of permission scopes
        school_id: School restriction (None = global)
        allowed_counsellor_ids: Counsellor restrictions (None = all)
        expires_in_hours: Token expiration time

    Returns:
        ServiceJWTResponse with token details
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=expires_in_hours)

    payload = {
        "sub": str(client_id),
        "client_name": client_name,
        "client_type": client_type,
        "scopes": scopes,
        "school_id": str(school_id) if school_id else None,
        "allowed_counsellor_ids": [str(d) for d in allowed_counsellor_ids] if allowed_counsellor_ids else None,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": "1hat-api",
    }

    token = jwt.encode(payload, jwt_secret, algorithm="HS256")

    return ServiceJWTResponse(
        token=token,
        token_type="Bearer",
        expires_in=expires_in_hours * 3600,
        expires_at=expires_at,
        client_id=client_id,
        client_name=client_name,
    )


async def verify_service_jwt(token: str) -> ClientContext:
    """
    Verify a service JWT and return the client context.

    Args:
        token: The JWT token from Authorization: Bearer header

    Returns:
        ClientContext with client info

    Raises:
        HTTPException: If token is invalid, expired, or client is inactive
    """
    try:
        # First decode without verification to get client_id
        unverified = jwt.decode(token, options={"verify_signature": False})
        client_id = unverified.get("sub")

        if not client_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing client ID")

        # Look up client to get JWT secret
        result = retry_on_network_error(
            lambda: supabase.table("api_clients")
            .select("*")
            .eq("id", client_id)
            .eq("is_active", True)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=401, detail="Invalid token: client not found")

        client = result.data[0]

        if not client.get("jwt_secret"):
            raise HTTPException(status_code=401, detail="Invalid token: client not configured for JWT auth")

        # Verify signature with client's secret
        payload = jwt.decode(
            token,
            client["jwt_secret"],
            algorithms=["HS256"],
            issuer="1hat-api",
        )

        # Build and return client context
        return ClientContext(
            client_type=payload["client_type"],
            client_id=UUID(payload["sub"]),
            client_name=payload["client_name"],
            school_id=UUID(payload["school_id"]) if payload.get("school_id") else None,
            allowed_counsellor_ids=[UUID(d) for d in payload["allowed_counsellor_ids"]] if payload.get("allowed_counsellor_ids") else None,
            scopes=payload.get("scopes", []),
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying service JWT: {e}")
        raise HTTPException(status_code=500, detail="Authentication error")


# ============================================================================
# Supabase JWT Verification (for Admin dashboard)
# ============================================================================

async def verify_supabase_jwt(token: str) -> ClientContext:
    """
    Verify a Supabase auth JWT and return the client context.

    Uses JWKS-based verification with public keys from Supabase's JWKS endpoint.
    Falls back to HS256 with JWT secret if JWKS is unavailable (e.g., SSL issues).

    Supports both ES256 (ECC P-256) and RS256 (RSA) asymmetric algorithms,
    as well as HS256 (legacy) during migration period.

    Args:
        token: The Supabase JWT token from Authorization: Bearer header

    Returns:
        ClientContext with admin user info

    Raises:
        HTTPException: If token is invalid or user is not an admin
    """
    payload = None
    jwks_error = None

    # Try JWKS-based verification first (for ES256/RS256)
    try:
        jwks_client = get_jwks_client()
        if jwks_client:
            # Get the signing key from JWKS based on the token's 'kid' header
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            # Verify and decode the JWT using the public key
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256", "HS256"],
                audience="authenticated",
            )
            logger.debug("JWT verified using JWKS")
    except jwt.exceptions.PyJWKClientError as e:
        logger.error(f"JWKS client error: {e}")
        jwks_error = str(e)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        # JWKS verification failed, will try HS256 fallback
        jwks_error = str(e)
        logger.debug(f"JWKS verification failed, trying HS256 fallback: {e}")
    except Exception as e:
        jwks_error = str(e)
        logger.debug(f"JWKS verification error, trying HS256 fallback: {e}")

    # Fall back to HS256 with JWT secret if JWKS failed and secret is available
    if payload is None and SUPABASE_JWT_SECRET:
        try:
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
            logger.debug("JWT verified using HS256 fallback")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"HS256 fallback also failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")

    # If still no payload, raise appropriate error
    if payload is None:
        if jwks_error:
            logger.error(f"JWT verification failed - JWKS error: {jwks_error}, no HS256 fallback configured")
        raise HTTPException(status_code=401, detail="Unable to verify token")

    try:
        auth_user_id = payload.get("sub")
        email = payload.get("email")

        if not auth_user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing user ID")

        # Check cache first for admin_users lookup
        cache_key = auth_user_id
        admin_user = _admin_users_cache.get(cache_key)

        if admin_user is None:
            # Cache miss - query database
            result = retry_on_network_error(
                lambda: supabase.table("admin_users")
                .select("*")
                .eq("auth_user_id", auth_user_id)
                .eq("is_active", True)
                .execute()
            )

            if not result.data:
                # Cache the negative result too (user is not admin)
                _admin_users_cache[cache_key] = False
                logger.warning(f"Supabase user {email} is not an admin")
                raise HTTPException(status_code=403, detail="Access denied: not an admin user")

            admin_user = result.data[0]
            # Cache the result
            _admin_users_cache[cache_key] = admin_user
            logger.debug(f"[CACHE] admin_users cache MISS for {auth_user_id[:8]}...")
        elif admin_user is False:
            # Cached negative result - user is not admin
            logger.warning(f"Supabase user {email} is not an admin (cached)")
            raise HTTPException(status_code=403, detail="Access denied: not an admin user")
        else:
            logger.debug(f"[CACHE] admin_users cache HIT for {auth_user_id[:8]}...")

        # Read school_id from admin_user record
        # NULL = global/super_admin access, Non-NULL = scoped to this school
        admin_school_id = None
        if admin_user.get("school_id"):
            admin_school_id = UUID(admin_user["school_id"])

        # Build admin client context
        return ClientContext(
            client_type="admin",
            client_id=UUID(admin_user["id"]),
            client_name=admin_user.get("full_name") or email,
            school_id=admin_school_id,
            allowed_counsellor_ids=None,  # Admin has access to all counsellors
            scopes=DEFAULT_SCOPES["admin"],
            user_id=UUID(auth_user_id),
            user_email=email,
            user_role=admin_user.get("role", "admin"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying Supabase JWT: {e}")
        raise HTTPException(status_code=500, detail="Authentication error")


# ============================================================================
# API Client Management
# ============================================================================

async def create_api_client(data: APIClientCreate) -> APIKeyCreateResponse:
    """
    Create a new API client and generate credentials.

    Args:
        data: Client creation data

    Returns:
        APIKeyCreateResponse with the API key (shown only once)

    Raises:
        HTTPException: On validation or database errors
    """
    # Validate EHR clients must have school_id
    if data.client_type == "ehr" and not data.school_id:
        raise HTTPException(
            status_code=400,
            detail="EHR clients must be associated with a school"
        )

    # Determine auth_mode: only EHR clients can use 'token', others always use JWT
    auth_mode = data.auth_mode if data.client_type == "ehr" else "api_key"

    # Generate credentials based on client type and auth mode
    client_secret_plaintext = None
    client_secret_hash = None

    if data.client_type == "ehr" and auth_mode == "token":
        # Token-mode EHR: generate client_secret + jwt_secret (no API key)
        full_key = None
        key_prefix = None
        key_hash = None
        jwt_secret = secrets.token_urlsafe(32)
        client_secret_plaintext, client_secret_hash = generate_client_secret()
    elif data.client_type == "ehr":
        # API key mode EHR (default)
        full_key, key_prefix, key_hash = generate_api_key(data.client_type)
        jwt_secret = None
    else:
        # Mobile/Web apps use JWT
        full_key = None
        key_prefix = None
        key_hash = None
        jwt_secret = secrets.token_urlsafe(32)

    # Determine scopes
    scopes = data.scopes if data.scopes else DEFAULT_SCOPES.get(data.client_type, [])

    try:
        # Insert into database
        insert_data = {
            "client_name": data.client_name,
            "client_type": data.client_type,
            "auth_mode": auth_mode,
            "api_key_hash": key_hash,
            "api_key_prefix": key_prefix,
            "jwt_secret": jwt_secret,
            "client_secret_hash": client_secret_hash,
            "school_id": str(data.school_id) if data.school_id else None,
            "allowed_counsellor_ids": [str(d) for d in data.allowed_counsellor_ids] if data.allowed_counsellor_ids else None,
            "scopes": scopes,
            "rate_limit_per_hour": data.rate_limit_per_hour,
            "token_expiry_minutes": data.token_expiry_minutes,
            "contact_email": data.contact_email,
            "description": data.description,
        }

        result = retry_on_network_error(
            lambda: supabase.table("api_clients").insert(insert_data).execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create client")

        client = result.data[0]

        # Token-mode EHR: return client_id + client_secret
        if data.client_type == "ehr" and auth_mode == "token":
            return APIKeyCreateResponse(
                client_id=UUID(client["id"]),
                client_name=client["client_name"],
                client_type=client["client_type"],
                auth_mode="token",
                client_secret=client_secret_plaintext,
                message="Token-mode client created. Save the client_secret securely - it won't be shown again. Use POST /api/v1/auth/token with client_id + client_secret to get access tokens.",
            )

        # API key mode EHR
        if data.client_type == "ehr":
            return APIKeyCreateResponse(
                client_id=UUID(client["id"]),
                client_name=client["client_name"],
                client_type=client["client_type"],
                auth_mode="api_key",
                api_key=full_key,
                api_key_prefix=key_prefix,
            )
        else:
            # For Mobile/Web apps, generate initial JWT
            jwt_response = generate_service_jwt(
                client_id=UUID(client["id"]),
                client_name=client["client_name"],
                client_type=client["client_type"],
                jwt_secret=jwt_secret,
                scopes=scopes,
                school_id=data.school_id,
                allowed_counsellor_ids=data.allowed_counsellor_ids,
                expires_in_hours=24 * 30,  # 30 days for initial token
            )

            return APIKeyCreateResponse(
                client_id=UUID(client["id"]),
                client_name=client["client_name"],
                client_type=client["client_type"],
                auth_mode="api_key",
                api_key=jwt_response.token,
                api_key_prefix=f"{client['client_type'][:3]}_{client['id'][:4]}",
                message="Service JWT created. This token expires in 30 days. Use the /token/refresh endpoint to get new tokens.",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating API client: {e}")
        raise HTTPException(status_code=500, detail="Failed to create client")


async def switch_auth_mode(client_id: UUID) -> dict:
    """
    Switch an EHR client between api_key and token auth modes.
    Generates new credentials for the target mode and invalidates old ones.
    """
    try:
        result = retry_on_network_error(
            lambda: supabase.table("api_clients")
            .select("*")
            .eq("id", str(client_id))
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Client not found")

        client = result.data[0]

        if client["client_type"] != "ehr":
            raise HTTPException(status_code=400, detail="Auth mode switching is only for EHR clients")

        current_mode = client.get("auth_mode", "api_key")

        if current_mode == "api_key":
            # Switch to token mode: generate client_secret + jwt_secret, clear API key
            new_jwt_secret = secrets.token_urlsafe(32)
            secret_plaintext, secret_hash = generate_client_secret()

            retry_on_network_error(
                lambda: supabase.table("api_clients")
                .update({
                    "auth_mode": "token",
                    "client_secret_hash": secret_hash,
                    "jwt_secret": new_jwt_secret,
                    "api_key_hash": None,
                    "api_key_prefix": None,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
                .eq("id", str(client_id))
                .execute()
            )

            return {
                "success": True,
                "auth_mode": "token",
                "client_id": str(client_id),
                "client_name": client["client_name"],
                "client_secret": secret_plaintext,
                "message": "Switched to token-based auth. Save the client_secret — it won't be shown again. Use POST /api/v1/auth/token to get access tokens.",
            }

        else:
            # Switch to api_key mode: generate API key, clear client_secret, revoke refresh tokens
            full_key, key_prefix, key_hash = generate_api_key("ehr")

            retry_on_network_error(
                lambda: supabase.table("api_clients")
                .update({
                    "auth_mode": "api_key",
                    "api_key_hash": key_hash,
                    "api_key_prefix": key_prefix,
                    "client_secret_hash": None,
                    "jwt_secret": None,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
                .eq("id", str(client_id))
                .execute()
            )

            # Revoke all refresh tokens
            await revoke_all_refresh_tokens(client_id)

            return {
                "success": True,
                "auth_mode": "api_key",
                "client_id": str(client_id),
                "client_name": client["client_name"],
                "api_key": full_key,
                "api_key_prefix": key_prefix,
                "message": "Switched to API key auth. Save the API key — it won't be shown again.",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error switching auth mode: {e}")
        raise HTTPException(status_code=500, detail="Failed to switch auth mode")


async def rotate_api_key(client_id: UUID) -> APIKeyRotateResponse:
    """
    Rotate an API key for an EHR client.

    Args:
        client_id: The client ID

    Returns:
        APIKeyRotateResponse with the new API key

    Raises:
        HTTPException: If client not found or not an EHR client
    """
    try:
        # Get current client
        result = retry_on_network_error(
            lambda: supabase.table("api_clients")
            .select("*")
            .eq("id", str(client_id))
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Client not found")

        client = result.data[0]

        if client["client_type"] != "ehr":
            raise HTTPException(
                status_code=400,
                detail="API key rotation is only for EHR clients. Use /token/refresh for mobile/web apps."
            )

        old_prefix = client.get("api_key_prefix", "unknown")

        # Generate new API key
        full_key, key_prefix, key_hash = generate_api_key("ehr")

        # Update in database
        retry_on_network_error(
            lambda: supabase.table("api_clients")
            .update({
                "api_key_hash": key_hash,
                "api_key_prefix": key_prefix,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id", str(client_id))
            .execute()
        )

        return APIKeyRotateResponse(
            client_id=client_id,
            client_name=client["client_name"],
            new_api_key=full_key,
            new_api_key_prefix=key_prefix,
            old_api_key_prefix=old_prefix,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rotating API key: {e}")
        raise HTTPException(status_code=500, detail="Failed to rotate API key")


async def refresh_service_jwt(client_id: UUID, expires_in_hours: int = 24) -> ServiceJWTResponse:
    """
    Refresh a service JWT for a mobile/web app client.

    Args:
        client_id: The client ID
        expires_in_hours: Token expiration time

    Returns:
        ServiceJWTResponse with new token

    Raises:
        HTTPException: If client not found or not a mobile/web client
    """
    try:
        # Get client
        result = retry_on_network_error(
            lambda: supabase.table("api_clients")
            .select("*")
            .eq("id", str(client_id))
            .eq("is_active", True)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Client not found or inactive")

        client = result.data[0]

        if client["client_type"] not in ("mobile_app", "web_app"):
            raise HTTPException(
                status_code=400,
                detail="JWT refresh is only for mobile/web apps. Use /api-key/rotate for EHR clients."
            )

        if not client.get("jwt_secret"):
            raise HTTPException(status_code=400, detail="Client not configured for JWT auth")

        return generate_service_jwt(
            client_id=UUID(client["id"]),
            client_name=client["client_name"],
            client_type=client["client_type"],
            jwt_secret=client["jwt_secret"],
            scopes=client.get("scopes", []),
            school_id=UUID(client["school_id"]) if client.get("school_id") else None,
            allowed_counsellor_ids=[UUID(d) for d in client["allowed_counsellor_ids"]] if client.get("allowed_counsellor_ids") else None,
            expires_in_hours=expires_in_hours,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing service JWT: {e}")
        raise HTTPException(status_code=500, detail="Failed to refresh token")


# ============================================================================
# Rate Limiting
# ============================================================================

async def check_rate_limit(client_id: UUID, client_type: str = None) -> Tuple[bool, int, int]:
    """
    Check if a client has exceeded their rate limit.

    Args:
        client_id: The client ID to check
        client_type: Type of client (admin, ehr, mobile_app, web_app)

    Returns:
        Tuple of (is_within_limit, requests_in_window, rate_limit)
    """
    # Admin users have unlimited rate limit (10000/hour effectively unlimited)
    if client_type == "admin":
        return True, 0, 10000

    try:
        # Get client's rate limit
        client_result = retry_on_network_error(
            lambda: supabase.table("api_clients")
            .select("rate_limit_per_hour")
            .eq("id", str(client_id))
            .execute()
        )

        if not client_result.data:
            # No api_client entry - allow with default limit
            return True, 0, 1000

        rate_limit = client_result.data[0]["rate_limit_per_hour"]

        # Count requests in last hour using RPC function
        count_result = retry_on_network_error(
            lambda: supabase.rpc(
                "get_client_request_count_last_hour",
                {"p_client_id": str(client_id)}
            ).execute()
        )

        request_count = count_result.data if count_result.data else 0

        return request_count < rate_limit, request_count, rate_limit

    except Exception as e:
        logger.error(f"Error checking rate limit: {e}")
        # On error, allow the request (fail open)
        return True, 0, 1000


async def log_api_usage(
    client_id: UUID,
    endpoint: str,
    method: str,
    status_code: int,
    response_time_ms: int,
    client_type: Optional[str] = None,
    counsellor_id: Optional[UUID] = None,
    student_id: Optional[str] = None,
    error_message: Optional[str] = None,
):
    """
    Log an API request for usage tracking and rate limiting.

    Args:
        client_id: The client making the request
        endpoint: API endpoint path
        method: HTTP method
        status_code: Response status code
        response_time_ms: Response time in milliseconds
        client_type: Type of client (admin, ehr, mobile_app, web_app)
        counsellor_id: Counsellor context (optional)
        student_id: Student context (optional)
        error_message: Error message if request failed (optional)
    """
    # Skip logging for admin users (not in api_clients table)
    # Admin usage is tracked via PHI audit logs instead
    if client_type == "admin":
        return

    try:
        retry_on_network_error(
            lambda: supabase.table("api_client_usage").insert({
                "client_id": str(client_id),
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "response_time_ms": response_time_ms,
                "counsellor_id": str(counsellor_id) if counsellor_id else None,
                "student_id": student_id,
                "error_message": error_message,
            }).execute()
        )
    except Exception as e:
        # Don't fail the request if logging fails
        logger.error(f"Error logging API usage: {e}")


# ============================================================================
# School & Counsellor Access Validation
# ============================================================================

async def validate_school_access(client: ClientContext, school_id: UUID) -> bool:
    """
    Validate that a client can access data from a specific school.

    Args:
        client: The authenticated client context
        school_id: The school to check access for

    Returns:
        True if access is allowed

    Raises:
        HTTPException: If access is denied
    """
    if not client.can_access_school(school_id):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: client is restricted to school {client.school_id}"
        )
    return True


async def validate_counsellor_access(client: ClientContext, counsellor_id: UUID) -> bool:
    """
    Validate that a client can access a specific counsellor's data.

    Args:
        client: The authenticated client context
        counsellor_id: The counsellor to check access for

    Returns:
        True if access is allowed

    Raises:
        HTTPException: If access is denied
    """
    if not client.can_access_counsellor(counsellor_id):
        raise HTTPException(
            status_code=403,
            detail="Access denied: client does not have access to this counsellor's data"
        )
    return True


async def validate_counsellor_exists(counsellor_id: UUID) -> bool:
    """
    Validate that a counsellor exists in the database.

    Args:
        counsellor_id: The counsellor ID to validate

    Returns:
        True if counsellor exists

    Raises:
        HTTPException: If counsellor not found
    """
    try:
        result = retry_on_network_error(
            lambda: supabase.table("counsellors")
            .select("id")
            .eq("id", str(counsellor_id))
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail=f"Counsellor not found: {counsellor_id}")

        return True

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating counsellor: {e}")
        raise HTTPException(status_code=500, detail="Error validating counsellor")


# ============================================================================
# Student Auto-Creation (for EHR clients)
# ============================================================================

async def ensure_student_exists(
    student_id: str,
    client: ClientContext,
    patient_name: Optional[str] = None,
) -> str:
    """
    Ensure a student exists in the database. Auto-creates if missing (for EHR clients).

    Args:
        student_id: External student identifier
        client: The authenticated client context
        patient_name: Optional student name for creation

    Returns:
        The student's internal UUID

    Raises:
        HTTPException: On database errors
    """
    try:
        # Check if student exists (scoped by school when available)
        school_id = client.school_id if hasattr(client, 'school_id') else None

        def _check():
            query = supabase.table("students").select("id").eq("student_id", student_id)
            if school_id:
                query = query.eq("school_id", str(school_id))
            else:
                query = query.is_("school_id", "null")
            return query.execute()

        result = retry_on_network_error(_check)

        if result.data:
            return result.data[0]["id"]

        # Auto-create for EHR clients
        if client.client_type != "ehr":
            raise HTTPException(
                status_code=404,
                detail=f"Student not found: {student_id}"
            )

        # Create student (with school scoping)
        insert_data = {
            "student_id": student_id,
            "full_name": patient_name or f"Student {student_id}",
        }
        if school_id:
            insert_data["school_id"] = str(school_id)

        create_result = retry_on_network_error(
            lambda: supabase.table("students").insert(insert_data).execute()
        )

        if create_result.data:
            logger.info(f"Auto-created student {student_id} for EHR client {client.client_name}")
            return create_result.data[0]["id"]

        raise HTTPException(status_code=500, detail="Failed to create student")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ensuring student exists: {e}")
        raise HTTPException(status_code=500, detail="Error processing student")


# ============================================================================
# EHR School-Scoped Access Validation
# ============================================================================
# These functions validate that EHR clients can only access resources
# belonging to counsellors within their assigned school.

# --- Lookup Functions ---

async def get_counsellor_school_id(counsellor_id: UUID) -> Optional[UUID]:
    """
    Get the school_id for a counsellor.

    Uses in-memory cache with 10-minute TTL to reduce database queries.

    Args:
        counsellor_id: The counsellor's UUID

    Returns:
        The school's UUID or None if not found/no school
    """
    cache_key = str(counsellor_id)

    # Check cache first
    if cache_key in _doctor_hospital_cache:
        cached_value = _doctor_hospital_cache[cache_key]
        if cached_value:
            return UUID(cached_value)
        return None

    try:
        result = retry_on_network_error(
            lambda: supabase.table("counsellors")
            .select("school_id")
            .eq("id", str(counsellor_id))
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("school_id"):
            school_id = result.data[0]["school_id"]
            _doctor_hospital_cache[cache_key] = school_id
            return UUID(school_id)

        # Cache negative result
        _doctor_hospital_cache[cache_key] = None
        return None
    except Exception as e:
        logger.error(f"Error getting counsellor school_id: {e}")
        return None


async def get_assistant_school_id(assistant_id: UUID) -> Optional[UUID]:
    """
    Get the school_id for an assistant.

    Args:
        assistant_id: The assistant's UUID

    Returns:
        The school's UUID or None if not found/no school
    """
    try:
        result = retry_on_network_error(
            lambda: supabase.table("assistants")
            .select("school_id")
            .eq("id", str(assistant_id))
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("school_id"):
            return UUID(result.data[0]["school_id"])
        return None
    except Exception as e:
        logger.error(f"Error getting assistant school_id: {e}")
        return None


async def get_extraction_counsellor_id(extraction_id: UUID) -> Optional[UUID]:
    """
    Get the counsellor_id for an extraction.

    Args:
        extraction_id: The extraction's UUID

    Returns:
        The counsellor's UUID or None if not found
    """
    try:
        result = retry_on_network_error(
            lambda: supabase.table("extractions")
            .select("counsellor_id")
            .eq("id", str(extraction_id))
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("counsellor_id"):
            return UUID(result.data[0]["counsellor_id"])
        return None
    except Exception as e:
        logger.error(f"Error getting extraction counsellor_id: {e}")
        return None


async def get_session_counsellor_id(session_id: UUID) -> Optional[UUID]:
    """
    Get the counsellor_id for a recording session.

    Args:
        session_id: The session's UUID

    Returns:
        The counsellor's UUID or None if not found
    """
    try:
        result = retry_on_network_error(
            lambda: supabase.table("recording_sessions")
            .select("counsellor_id")
            .eq("id", str(session_id))
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("counsellor_id"):
            return UUID(result.data[0]["counsellor_id"])
        return None
    except Exception as e:
        logger.error(f"Error getting session counsellor_id: {e}")
        return None


async def get_session_assistant_id(session_id: UUID) -> Optional[UUID]:
    """
    Get the assistant_id for a recording session.

    Args:
        session_id: The session's UUID

    Returns:
        The assistant's UUID or None if not found
    """
    try:
        result = retry_on_network_error(
            lambda: supabase.table("recording_sessions")
            .select("assistant_id")
            .eq("id", str(session_id))
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("assistant_id"):
            return UUID(result.data[0]["assistant_id"])
        return None
    except Exception as e:
        logger.error(f"Error getting session assistant_id: {e}")
        return None


async def get_submission_counsellor_id(submission_id: UUID) -> Optional[UUID]:
    """
    Get the counsellor_id for a submission (via processing_jobs -> recording_sessions).

    Args:
        submission_id: The submission's UUID

    Returns:
        The counsellor's UUID or None if not found
    """
    try:
        # Single query with join: processing_jobs -> recording_sessions
        result = retry_on_network_error(
            lambda: supabase.table("processing_jobs")
            .select("recording_sessions(counsellor_id)")
            .eq("submission_id", str(submission_id))
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("recording_sessions"):
            counsellor_id = result.data[0]["recording_sessions"].get("counsellor_id")
            if counsellor_id:
                return UUID(counsellor_id)
        return None
    except Exception as e:
        logger.error(f"Error getting submission counsellor_id: {e}")
        return None


async def get_submission_assistant_id(submission_id: UUID) -> Optional[UUID]:
    """
    Get the assistant_id for a submission (via processing_jobs -> recording_sessions).

    Args:
        submission_id: The submission's UUID

    Returns:
        The assistant's UUID or None if not found
    """
    try:
        # Single query with join: processing_jobs -> recording_sessions
        result = retry_on_network_error(
            lambda: supabase.table("processing_jobs")
            .select("recording_sessions(assistant_id)")
            .eq("submission_id", str(submission_id))
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("recording_sessions"):
            assistant_id = result.data[0]["recording_sessions"].get("assistant_id")
            if assistant_id:
                return UUID(assistant_id)
        return None
    except Exception as e:
        logger.error(f"Error getting submission assistant_id: {e}")
        return None


async def get_correlation_counsellor_id(correlation_id: str) -> Optional[UUID]:
    """
    Get the counsellor_id for a correlation_id (via recording_sessions table).

    Args:
        correlation_id: The correlation ID string

    Returns:
        The counsellor's UUID or None if not found
    """
    try:
        result = retry_on_network_error(
            lambda: supabase.table("recording_sessions")
            .select("counsellor_id")
            .eq("correlation_id", correlation_id)
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("counsellor_id"):
            return UUID(result.data[0]["counsellor_id"])
        return None
    except Exception as e:
        logger.error(f"Error getting correlation counsellor_id: {e}")
        return None


async def get_correlation_assistant_id(correlation_id: str) -> Optional[UUID]:
    """
    Get the assistant_id for a correlation_id (via recording_sessions table).

    Args:
        correlation_id: The correlation ID string

    Returns:
        The assistant's UUID or None if not found
    """
    try:
        result = retry_on_network_error(
            lambda: supabase.table("recording_sessions")
            .select("assistant_id")
            .eq("correlation_id", correlation_id)
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("assistant_id"):
            return UUID(result.data[0]["assistant_id"])
        return None
    except Exception as e:
        logger.error(f"Error getting correlation assistant_id: {e}")
        return None


# --- Validation Functions ---

async def validate_ehr_counsellor_access(client: ClientContext, counsellor_id: UUID) -> bool:
    """
    For EHR clients: Validate counsellor belongs to client's school.
    Admin/Mobile/Web: Always return True.

    Args:
        client: The authenticated client context
        counsellor_id: The counsellor to validate access for

    Returns:
        True if access is allowed, False otherwise
    """
    # Admin has full access
    if client.client_type == "admin":
        return True

    # Mobile/Web apps are trusted - app handles authorization
    if client.client_type in ("mobile_app", "web_app"):
        return True

    # Only EHR clients need school-scoped validation
    if client.client_type != "ehr":
        return True

    # EHR must have school_id
    if client.school_id is None:
        logger.warning(f"EHR client {client.client_name} has no school_id")
        return False

    counsellor_school = await get_counsellor_school_id(counsellor_id)
    if counsellor_school is None:
        logger.warning(f"Counsellor {counsellor_id} has no school_id")
        return False

    return counsellor_school == client.school_id


async def validate_ehr_extraction_access(client: ClientContext, extraction_id: UUID) -> bool:
    """
    Validate extraction belongs to a counsellor in client's school.

    Args:
        client: The authenticated client context
        extraction_id: The extraction to validate access for

    Returns:
        True if access is allowed, False otherwise
    """
    if client.client_type in ("admin", "mobile_app", "web_app"):
        return True

    counsellor_id = await get_extraction_counsellor_id(extraction_id)
    if counsellor_id is None:
        logger.warning(f"Extraction {extraction_id} has no counsellor_id")
        return False

    return await validate_ehr_counsellor_access(client, counsellor_id)


async def validate_ehr_submission_access(client: ClientContext, submission_id: UUID) -> bool:
    """
    Validate submission belongs to a counsellor or assistant in client's school.

    Args:
        client: The authenticated client context
        submission_id: The submission to validate access for

    Returns:
        True if access is allowed, False otherwise
    """
    if client.client_type in ("admin", "mobile_app", "web_app"):
        return True

    # First try counsellor-based validation
    counsellor_id = await get_submission_counsellor_id(submission_id)
    if counsellor_id is not None:
        return await validate_ehr_counsellor_access(client, counsellor_id)

    # Fall back to assistant-based validation if no counsellor_id
    assistant_id = await get_submission_assistant_id(submission_id)
    if assistant_id is not None:
        assistant_school = await get_assistant_school_id(assistant_id)
        if assistant_school is None:
            logger.warning(f"Assistant {assistant_id} has no school_id")
            return False
        return assistant_school == client.school_id

    logger.warning(f"Submission {submission_id} has no counsellor_id or assistant_id")
    return False


async def validate_ehr_session_access(client: ClientContext, session_id: UUID) -> bool:
    """
    Validate session belongs to a counsellor or assistant in client's school.

    Args:
        client: The authenticated client context
        session_id: The session to validate access for

    Returns:
        True if access is allowed, False otherwise
    """
    if client.client_type in ("admin", "mobile_app", "web_app"):
        return True

    # First try counsellor-based validation
    counsellor_id = await get_session_counsellor_id(session_id)
    if counsellor_id is not None:
        return await validate_ehr_counsellor_access(client, counsellor_id)

    # Fall back to assistant-based validation if no counsellor_id
    assistant_id = await get_session_assistant_id(session_id)
    if assistant_id is not None:
        assistant_school = await get_assistant_school_id(assistant_id)
        if assistant_school is None:
            logger.warning(f"Assistant {assistant_id} has no school_id")
            return False
        return assistant_school == client.school_id

    logger.warning(f"Session {session_id} has no counsellor_id or assistant_id")
    return False


async def validate_ehr_correlation_access(client: ClientContext, correlation_id: str) -> bool:
    """
    Validate correlation_id belongs to a counsellor or assistant in client's school.

    Args:
        client: The authenticated client context
        correlation_id: The correlation ID to validate access for

    Returns:
        True if access is allowed, False otherwise
    """
    if client.client_type in ("admin", "mobile_app", "web_app"):
        return True

    # First try counsellor-based validation
    counsellor_id = await get_correlation_counsellor_id(correlation_id)
    if counsellor_id is not None:
        return await validate_ehr_counsellor_access(client, counsellor_id)

    # Fall back to assistant-based validation if no counsellor_id
    assistant_id = await get_correlation_assistant_id(correlation_id)
    if assistant_id is not None:
        assistant_school = await get_assistant_school_id(assistant_id)
        if assistant_school is None:
            logger.warning(f"Assistant {assistant_id} has no school_id")
            return False
        return assistant_school == client.school_id

    logger.warning(f"Correlation {correlation_id} has no counsellor_id or assistant_id")
    return False


async def validate_ehr_student_access(client: ClientContext, student_id: str) -> bool:
    """
    Validate student has extractions from counsellors in client's school.

    This checks if the student has any extraction records associated with
    counsellors from the client's school.

    Args:
        client: The authenticated client context
        student_id: The student identifier to validate access for (UUID or human-readable student_id)

    Returns:
        True if access is allowed, False otherwise
    """
    if client.client_type in ("admin", "mobile_app", "web_app"):
        return True

    if client.client_type != "ehr":
        return True

    if client.school_id is None:
        logger.warning(f"EHR client {client.client_name} has no school_id")
        return False

    try:
        # Resolve student UUID: extractions.student_id stores UUID (students.id),
        # not the human-readable student_id string
        patient_uuid = student_id

        # Check if student_id is a UUID or a human-readable student_id
        try:
            UUID(student_id)
            # It's already a valid UUID
        except ValueError:
            # It's a human-readable student_id, look up the UUID from students table
            # Scope by school to prevent cross-school student leakage
            def _lookup_student():
                query = supabase.table("students").select("id").eq("student_id", student_id)
                if client.school_id:
                    query = query.eq("school_id", str(client.school_id))
                return query.limit(1).execute()
            student_result = retry_on_network_error(_lookup_student)
            if not student_result.data:
                logger.warning(f"Student not found with student_id: {student_id}")
                return False
            patient_uuid = student_result.data[0]["id"]

        # Check if student has any extractions from counsellors in this school
        # Using a join query: extractions -> counsellors -> school_id
        result = retry_on_network_error(
            lambda: supabase.table("extractions")
            .select("id, counsellors!inner(school_id)")
            .eq("student_id", patient_uuid)
            .eq("counsellors.school_id", str(client.school_id))
            .limit(1)
            .execute()
        )

        return len(result.data) > 0
    except Exception as e:
        logger.error(f"Error validating student access: {e}")
        return False

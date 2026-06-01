"""
Authentication Router

Provides login/refresh/me endpoints so external webapps can authenticate
without needing direct access to Supabase credentials (URL, anon key).

Endpoints:
- POST /api/v1/auth/login    - Email/password login, returns tokens + user info
- POST /api/v1/auth/refresh  - Refresh an expired access token
- GET  /api/v1/auth/me       - Get current user info (requires auth)
"""

import os
import logging
from typing import Optional, List, Dict

import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from models.auth_models import (
    ClientContext,
    ClientCredentialsRequest,
    ClientCredentialsResponse,
    ClientRefreshRequest,
    ClientRefreshResponse,
)
from dependencies.auth import get_current_client
from services.supabase_service import supabase, retry_on_network_error, get_school_settings_cached
from services.auth_service import exchange_client_credentials, refresh_client_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class LoginRequest(BaseModel):
    email: str = Field(..., description="Admin email address")
    password: str = Field(..., description="Password")


class UserInfo(BaseModel):
    name: Optional[str] = None
    email: str
    role: str
    school_id: Optional[str] = None
    school_name: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: int
    token_type: str = "Bearer"
    user: UserInfo


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token from login")


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: int
    token_type: str = "Bearer"


class AuthValidateResponse(BaseModel):
    valid: bool = True
    client_type: str
    client_name: str
    school_id: Optional[str] = None
    allowed_counsellor_ids: Optional[List[str]] = None
    scopes: List[str] = []
    feature_flags: Optional[Dict[str, bool]] = None


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate with email/password and get access + refresh tokens.

    Returns user info including school_id for school-scoped admins.
    No Supabase credentials needed by the caller.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Auth service not configured")

    try:
        # Call Supabase Auth API with service key
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                json={"email": request.email, "password": request.password},
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Content-Type": "application/json",
                },
                timeout=15.0,
            )

        if resp.status_code != 200:
            # Map Supabase auth errors to generic messages
            logger.warning(f"[AUTH] Login failed for {request.email}: {resp.status_code}")
            raise HTTPException(status_code=401, detail="Invalid email or password")

        data = resp.json()
        access_token = data["access_token"]
        refresh_token = data["refresh_token"]
        expires_at = data["expires_at"]
        auth_user_id = data["user"]["id"]

        # Look up admin_users record for role and school_id
        result = retry_on_network_error(
            lambda: supabase.table("admin_users")
            .select("*")
            .eq("auth_user_id", auth_user_id)
            .eq("is_active", True)
            .execute()
        )

        if not result.data:
            logger.warning(f"[AUTH] User {request.email} authenticated but not in admin_users")
            raise HTTPException(status_code=403, detail="Not authorized as admin")

        admin_user = result.data[0]

        # Get school name if school-scoped
        school_name = None
        if admin_user.get("school_id"):
            h_result = retry_on_network_error(
                lambda: supabase.table("schools")
                .select("school_name")
                .eq("id", admin_user["school_id"])
                .limit(1)
                .execute()
            )
            if h_result.data:
                school_name = h_result.data[0]["school_name"]

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            user=UserInfo(
                name=admin_user.get("full_name"),
                email=admin_user["email"],
                role=admin_user.get("role", "admin"),
                school_id=admin_user.get("school_id"),
                school_name=school_name,
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] Login error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Authentication service error")


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(request: RefreshRequest):
    """
    Refresh an expired access token using a refresh token.

    Returns new access_token + refresh_token pair.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Auth service not configured")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
                json={"refresh_token": request.refresh_token},
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Content-Type": "application/json",
                },
                timeout=15.0,
            )

        if resp.status_code != 200:
            logger.warning(f"[AUTH] Token refresh failed: {resp.status_code}")
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

        data = resp.json()

        return RefreshResponse(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=data["expires_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] Refresh error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Token refresh failed")


@router.post("/token", response_model=ClientCredentialsResponse)
async def client_credentials_token(request: ClientCredentialsRequest):
    """
    OAuth 2.0 Client Credentials grant.

    Exchange client_id + client_secret for an access_token + refresh_token.
    Only available for EHR clients with auth_mode='token'.

    **Request Body:**
    - client_id: UUID of the API client
    - client_secret: Client secret (shown once at creation)
    - grant_type: Must be 'client_credentials'

    **Returns:**
    - access_token: JWT token (1 hour expiry)
    - refresh_token: Refresh token (30 day expiry, single-use)
    - expires_in: 3600 (seconds)
    - expires_at: ISO 8601 timestamp
    """
    if request.grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="grant_type must be 'client_credentials'")

    try:
        return await exchange_client_credentials(request.client_id, request.client_secret)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] Client credentials exchange error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Token exchange failed")


@router.post("/client-refresh", response_model=ClientRefreshResponse)
async def client_refresh_token(request: ClientRefreshRequest):
    """
    OAuth 2.0 Refresh Token grant.

    Exchange a refresh_token for a new access_token + new refresh_token.
    The old refresh token is invalidated (rotation).

    **Request Body:**
    - client_id: UUID of the API client
    - refresh_token: Refresh token from previous /token or /client-refresh response
    - grant_type: Must be 'refresh_token'

    **Returns:**
    - access_token: New JWT token (1 hour expiry)
    - refresh_token: New refresh token (30 day expiry, single-use)
    - expires_in: 3600 (seconds)
    - expires_at: ISO 8601 timestamp
    """
    if request.grant_type != "refresh_token":
        raise HTTPException(status_code=400, detail="grant_type must be 'refresh_token'")

    try:
        return await refresh_client_token(request.client_id, request.refresh_token)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] Client refresh error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Token refresh failed")


@router.get("/me", response_model=UserInfo)
async def get_me(client: ClientContext = Depends(get_current_client)):
    """
    Get current authenticated user info.

    Requires a valid access_token in Authorization header.
    """
    try:
        # Look up admin user details
        if not client.user_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        result = retry_on_network_error(
            lambda: supabase.table("admin_users")
            .select("*")
            .eq("auth_user_id", str(client.user_id))
            .eq("is_active", True)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=403, detail="Not authorized")

        admin_user = result.data[0]

        # Get school name if school-scoped
        school_name = None
        if admin_user.get("school_id"):
            h_result = retry_on_network_error(
                lambda: supabase.table("schools")
                .select("school_name")
                .eq("id", admin_user["school_id"])
                .limit(1)
                .execute()
            )
            if h_result.data:
                school_name = h_result.data[0]["school_name"]

        return UserInfo(
            name=admin_user.get("full_name"),
            email=admin_user["email"],
            role=admin_user.get("role", "admin"),
            school_id=admin_user.get("school_id"),
            school_name=school_name,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] /me error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get user info")


@router.get("/validate", response_model=AuthValidateResponse)
async def validate_auth(client: ClientContext = Depends(get_current_client)):
    """Validate current authentication credentials. Returns client identity info and feature flags."""
    feature_flags = None
    if client.school_id:
        try:
            settings = get_school_settings_cached(str(client.school_id))
            feature_flags = settings.get("feature_flags")
        except Exception as e:
            logger.warning(f"[AUTH] Failed to fetch feature flags for school {client.school_id}: {e}")

    return AuthValidateResponse(
        client_type=client.client_type,
        client_name=client.client_name,
        school_id=str(client.school_id) if client.school_id else None,
        allowed_counsellor_ids=[str(d) for d in client.allowed_counsellor_ids] if client.allowed_counsellor_ids else None,
        scopes=client.scopes,
        feature_flags=feature_flags,
    )

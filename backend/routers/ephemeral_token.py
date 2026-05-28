"""
POST /api/ephemeral-token endpoint
Generate ephemeral tokens for Gemini Live API (client-side use)

Based on: https://ai.google.dev/gemini-api/docs/ephemeral-tokens
"""

import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel
from google import genai
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Conditional authentication imports
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"

# Type stubs for when AUTH_ENABLED is False - these are no-op functions
# Using type: ignore to suppress Pylance warnings about function redefinition
if AUTH_ENABLED:
    from dependencies.auth import get_current_client, EHRDoctorAccessChecker
    _doctor_checker = EHRDoctorAccessChecker()

    async def require_auth(request: Request):  # type: ignore[misc]
        """Basic authentication - any valid client can access"""
        return get_current_client(request)

    async def verify_doctor_access_from_body(request: Request):  # type: ignore[misc]
        """For endpoints where doctor_id is in request body - validation happens in endpoint"""
        client = get_current_client(request)
        return await _doctor_checker(request, None, client)
else:
    async def require_auth(request: Request = None):  # type: ignore[misc]
        return None

    async def verify_doctor_access_from_body(request: Request = None):  # type: ignore[misc]
        return None


class EphemeralTokenResponse(BaseModel):
    """Response model for ephemeral token generation"""
    token: str
    expires_in: int  # Token expiration time in seconds (approximate)
    new_session_expire_time: str  # ISO timestamp for session initiation window
    expire_time: str  # ISO timestamp for message transmission window


class LiveApiUsageRequest(BaseModel):
    """Request model for logging Live API session usage"""
    model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    session_duration_seconds: float  # Total WebSocket session duration
    audio_duration_seconds: Optional[float] = None  # Actual audio sent
    session_id: Optional[str] = None  # Recording session UUID
    doctor_id: Optional[str] = None  # Doctor UUID
    consultation_type_code: Optional[str] = None
    template_code: Optional[str] = None
    error_message: Optional[str] = None


class LiveApiUsageResponse(BaseModel):
    """Response model for Live API usage logging"""
    success: bool
    usage_id: Optional[str] = None
    estimated_cost_usd: float
    message: str


@router.post("/ephemeral-token", response_model=EphemeralTokenResponse, status_code=status.HTTP_200_OK)
async def generate_ephemeral_token(
    request: Request,
    _auth = Depends(require_auth)
):
    """
    Generate an ephemeral token for Gemini Live API

    Ephemeral tokens are short-lived tokens that can be safely used in client-side
    applications without exposing the main API key.

    Custom configuration:
    - Session initiation window: 12 minutes (to accommodate 10+ minute recordings)
    - Message transmission window: 15 minutes (buffer for post-recording processing)
    - Only works with v1alpha API
    - Only compatible with Live API

    Returns:
        EphemeralTokenResponse with token and expiration times

    Raises:
        HTTPException: If token generation fails
    """
    try:
        # Initialize Gemini client with v1alpha API version
        client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options={'api_version': 'v1alpha'}
        )

        # Calculate custom expiration times
        # Session window: 12 minutes (720 seconds) for recordings up to 10+ minutes
        # Transmission window: 15 minutes (900 seconds) for post-recording processing
        from datetime import timezone
        now = datetime.now(timezone.utc)
        new_session_expire_time = now + timedelta(minutes=12)
        expire_time = now + timedelta(minutes=15)

        # Create ephemeral token with custom expiration times
        # Parameters must be passed inside a config dictionary
        token = client.auth_tokens.create(
            config={
                'uses': 3,  # Allow up to 3 sessions (for retries/reconnections)
                'new_session_expire_time': new_session_expire_time,
                'expire_time': expire_time,
                'http_options': {'api_version': 'v1alpha'}
            }
        )

        # Debug: Log token object attributes
        logger.info(f"Token object type: {type(token)}")
        logger.info(f"Token object attributes: {dir(token)}")
        logger.info(f"Token object dict: {token.__dict__ if hasattr(token, '__dict__') else 'No __dict__'}")

        logger.info(
            f"Generated ephemeral token: "
            f"session_window={new_session_expire_time.isoformat()} (12 min), "
            f"transmission_window={expire_time.isoformat()} (15 min)"
        )

        # Token is valid for 12 minutes to start a session (720 seconds)
        expires_in = 720

        return EphemeralTokenResponse(
            token=token.name,  # token.name contains the actual token string
            expires_in=expires_in,
            new_session_expire_time=new_session_expire_time.isoformat(),
            expire_time=expire_time.isoformat()
        )

    except Exception as e:
        logger.error(f"Error generating ephemeral token: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate ephemeral token"
        )


@router.post("/live-api-usage", response_model=LiveApiUsageResponse, status_code=status.HTTP_200_OK)
async def log_live_api_usage(
    http_request: Request,
    request: LiveApiUsageRequest,
    _auth = Depends(verify_doctor_access_from_body)
):
    """
    Log usage for a completed Gemini Live API session.

    Since the Live API uses a client-side WebSocket connection directly to Google,
    we can't intercept the actual token usage. This endpoint logs estimated usage
    based on session and audio duration for cost tracking purposes.

    The frontend should call this endpoint when a Live API session ends.

    Request body:
    - model: Gemini model used (e.g., gemini-2.5-flash-native-audio-preview-12-2025)
    - session_duration_seconds: Total WebSocket session duration
    - audio_duration_seconds: Actual audio sent (may be less due to pauses)
    - session_id: Recording session UUID (optional)
    - doctor_id: Doctor UUID (optional)
    - consultation_type_code: e.g., "OP_HOSP1" (optional)
    - template_code: Template used (optional)
    - error_message: Error if session failed (optional)

    Returns:
        LiveApiUsageResponse with usage_id and estimated cost
    """
    try:
        from services.llm_usage_service import create_live_api_usage, log_llm_usage

        # Parse UUIDs if provided
        session_uuid = uuid.UUID(request.session_id) if request.session_id else None
        doctor_uuid = uuid.UUID(request.doctor_id) if request.doctor_id else None

        # Create usage data
        usage_data = create_live_api_usage(
            model=request.model,
            session_duration_seconds=request.session_duration_seconds,
            audio_duration_seconds=request.audio_duration_seconds,
            session_id=session_uuid,
            doctor_id=doctor_uuid,
            consultation_type_code=request.consultation_type_code,
            template_code=request.template_code,
            error_message=request.error_message,
        )

        # Log to database
        usage_id = await log_llm_usage(usage_data)

        logger.info(
            f"Logged Live API usage: session_duration={request.session_duration_seconds:.1f}s, "
            f"audio_duration={request.audio_duration_seconds or 0:.1f}s, "
            f"estimated_cost=${usage_data.total_cost_usd:.6f}, "
            f"doctor_id={request.doctor_id}"
        )

        return LiveApiUsageResponse(
            success=True,
            usage_id=usage_id,
            estimated_cost_usd=usage_data.total_cost_usd or 0.0,
            message=f"Live API usage logged successfully"
        )

    except Exception as e:
        logger.error(f"Error logging Live API usage: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to log Live API usage"
        )

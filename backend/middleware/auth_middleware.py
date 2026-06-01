"""
Authentication Middleware

Intercepts all requests and authenticates them based on:
- Authorization: Bearer <api_key>: EHR integrations (API key auth)
- Authorization: Bearer <jwt>: Mobile/Web apps (Service JWT) or Admin (Supabase JWT)

Public endpoints (health checks, docs) bypass authentication.

Usage in main.py:
    from middleware.auth_middleware import AuthMiddleware
    app.add_middleware(AuthMiddleware)
"""

import asyncio
import base64
import json
import os
import time
import uuid
import logging
from typing import Optional, Dict

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from services.auth_service import (
    verify_api_key,
    verify_service_jwt,
    verify_supabase_jwt,
    check_rate_limit,
    log_api_usage,
)
from services.audit_service import audit_service
from models.auth_models import ClientContext

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware that handles:
    - API Key authentication (Authorization: Bearer <api_key>)
    - JWT authentication (Authorization: Bearer <jwt>)
    - Rate limiting
    - Request timing and logging
    - HIPAA audit logging for PHI endpoints

    API keys are distinguished from JWTs by format:
    - JWTs have 3 dot-separated parts and start with "eyJ"
    - API keys are simple strings (no dots or different format)
    """

    # CORS origins from environment (for error responses)
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []

    def _get_cors_headers(self, request: Request) -> Dict[str, str]:
        """Get CORS headers for error responses based on request origin."""
        origin = request.headers.get("origin", "")
        headers = {}

        # If specific origins are configured, check if request origin is allowed
        if self.CORS_ORIGINS and self.CORS_ORIGINS[0]:
            if origin in self.CORS_ORIGINS:
                headers["Access-Control-Allow-Origin"] = origin
                headers["Access-Control-Allow-Credentials"] = "true"
        else:
            # Development mode: allow all origins
            headers["Access-Control-Allow-Origin"] = "*"

        return headers

    # Endpoints that don't require authentication
    PUBLIC_PATHS = [
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/token",
        "/api/v1/auth/client-refresh",
    ]

    # Path prefixes that don't require authentication
    PUBLIC_PREFIXES = [
        "/_next/",  # Next.js static files
        "/static/",
    ]

    def _is_public_path(self, path: str) -> bool:
        """Check if a path is public (no auth required)"""
        if path in self.PUBLIC_PATHS:
            return True

        for prefix in self.PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return True

        return False

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """
        Main middleware dispatch method.

        Authenticates the request, checks rate limits, and logs usage.
        """
        # Generate request ID for tracing
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Start timing
        start_time = time.time()

        # Allow CORS preflight requests (OPTIONS) to pass through
        # These are sent by browsers before actual requests and don't include auth headers
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check if path is public
        path = request.url.path
        if self._is_public_path(path):
            return await call_next(request)

        # TEST MODE: Bypass authentication when TESTING=true
        # This allows pytest tests to run without setting up full auth
        if os.getenv("TESTING", "").lower() == "true":
            # Create a mock admin client context for tests
            test_client_context = ClientContext(
                client_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
                client_type="admin",
                client_name="test_admin",
                school_id=None,
                counsellor_id=None,
                permissions=["*"],  # Full permissions for tests
                rate_limit=None,
            )
            request.state.client = test_client_context
            request.state.request_id = request_id
            return await call_next(request)

        # Try to authenticate
        client_context: Optional[ClientContext] = None
        auth_error: Optional[str] = None
        attempted_auth_type: Optional[str] = None

        try:
            # Get Authorization header
            auth_header = request.headers.get("Authorization")

            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:]

                # Determine token type by format
                # JWTs have 3 dot-separated parts and start with "eyJ"
                # API keys are simple strings without this format
                is_jwt_format = token.count(".") == 2 and token.startswith("eyJ")

                if not is_jwt_format:
                    # Not a JWT format - treat as API key (EHR integrations)
                    attempted_auth_type = "api_key"
                    client_context = await verify_api_key(token)
                else:
                    # JWT format - determine if Supabase or Service JWT
                    # Check if token has Supabase's "authenticated" audience
                    is_supabase_token = False
                    try:
                        # Decode payload (middle part) without verification to check audience
                        payload_b64 = token.split(".")[1]
                        # Add padding if needed
                        padding = 4 - len(payload_b64) % 4
                        if padding != 4:
                            payload_b64 += "=" * padding
                        payload_json = base64.urlsafe_b64decode(payload_b64)
                        payload = json.loads(payload_json)
                        # Supabase tokens have aud="authenticated"
                        is_supabase_token = payload.get("aud") == "authenticated"
                    except Exception:
                        pass

                    if is_supabase_token:
                        # This is a Supabase token - don't fall back to service JWT
                        attempted_auth_type = "supabase_jwt"
                        client_context = await verify_supabase_jwt(token)
                    else:
                        # Try as service JWT first, then Supabase as fallback
                        try:
                            attempted_auth_type = "service_jwt"
                            client_context = await verify_service_jwt(token)
                        except HTTPException:
                            attempted_auth_type = "supabase_jwt"
                            client_context = await verify_supabase_jwt(token)
            else:
                # No authentication provided
                auth_error = "Missing authentication: provide Authorization: Bearer <token> header"

        except HTTPException as e:
            auth_error = e.detail
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            auth_error = "Authentication failed"

        # If auth failed, log and return error
        if auth_error or client_context is None:
            # Log failed auth attempt (fire-and-forget, never block response)
            try:
                asyncio.create_task(audit_service.log_failed_auth(
                    request=request,
                    error_message=auth_error or "Unknown auth error",
                    attempted_client_type=attempted_auth_type,
                ))
            except Exception:
                pass

            return JSONResponse(
                status_code=401,
                content={"detail": auth_error or "Authentication required"},
                headers={
                    "WWW-Authenticate": "Bearer",
                    "X-Request-ID": request_id,
                    **self._get_cors_headers(request),
                },
            )

        # Check rate limit (admin users have unlimited)
        is_within_limit, request_count, rate_limit = await check_rate_limit(
            client_context.client_id,
            client_context.client_type
        )

        if not is_within_limit:
            logger.warning(
                f"Rate limit exceeded for client {client_context.client_name}: "
                f"{request_count}/{rate_limit}"
            )

            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "limit": rate_limit,
                    "requests": request_count,
                },
                headers={
                    "X-RateLimit-Limit": str(rate_limit),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": "3600",
                    "X-Request-ID": request_id,
                    **self._get_cors_headers(request),
                },
            )

        # Attach client context to request state
        request.state.client = client_context

        # Process the request
        response: Response = await call_next(request)

        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)

        # Add headers to response
        response.headers["X-Request-ID"] = request_id
        response.headers["X-RateLimit-Limit"] = str(rate_limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, rate_limit - request_count - 1))

        # Log API usage (fire-and-forget, never block response)
        # Skip logging for admin users (they don't have entries in api_clients table)
        try:
            asyncio.create_task(log_api_usage(
                client_id=client_context.client_id,
                endpoint=path,
                method=request.method,
                status_code=response.status_code,
                response_time_ms=response_time_ms,
                client_type=client_context.client_type,
            ))
        except Exception:
            pass

        # HIPAA Audit: Log PHI endpoint access (fire-and-forget, zero latency impact)
        # Middleware provides baseline audit coverage; endpoint handlers add resource-specific context
        if audit_service.is_phi_endpoint(path):
            try:
                asyncio.create_task(
                    audit_service.log_phi_access(
                        client_context=client_context,
                        request=request,
                        response_status=response.status_code,
                        response_time_ms=response_time_ms,
                    )
                )
            except Exception:
                pass

        # Admin Action Audit: log non-PHI config mutations by admin users
        # (fire-and-forget, zero latency impact). PHI writes already covered above.
        if (
            client_context.client_type == "admin"
            and request.method in ("POST", "PUT", "PATCH", "DELETE")
            and not audit_service.is_phi_endpoint(path)
        ):
            try:
                asyncio.create_task(
                    audit_service.log_admin_action(
                        client_context=client_context,
                        request=request,
                        response_status=response.status_code,
                        response_time_ms=response_time_ms,
                    )
                )
            except Exception:
                pass

        return response


class OptionalAuthMiddleware(BaseHTTPMiddleware):
    """
    Optional authentication middleware.

    Similar to AuthMiddleware but doesn't reject unauthenticated requests.
    Use this for endpoints that work both with and without auth.
    """

    PUBLIC_PATHS = AuthMiddleware.PUBLIC_PATHS
    PUBLIC_PREFIXES = AuthMiddleware.PUBLIC_PREFIXES

    def _is_public_path(self, path: str) -> bool:
        if path in self.PUBLIC_PATHS:
            return True
        for prefix in self.PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return True
        return False

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Try to authenticate but allow unauthenticated requests"""

        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.client = None

        if self._is_public_path(request.url.path):
            return await call_next(request)

        try:
            auth_header = request.headers.get("Authorization")

            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:]
                # Check if it's JWT format or API key
                is_jwt_format = token.count(".") == 2 and token.startswith("eyJ")

                if not is_jwt_format:
                    # API key via Bearer token
                    request.state.client = await verify_api_key(token)
                else:
                    # JWT token
                    try:
                        request.state.client = await verify_supabase_jwt(token)
                    except HTTPException:
                        request.state.client = await verify_service_jwt(token)

        except Exception as e:
            # Log but don't fail
            logger.debug(f"Optional auth failed: {e}")

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response

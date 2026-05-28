"""
Authentication and Authorization Models

Defines models for:
- API client context (attached to request after authentication)
- API key creation and management
- Service JWT tokens for mobile/web apps
- Admin user management
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal, List
from uuid import UUID
from datetime import datetime


# ============================================================================
# Client Context (attached to request after authentication)
# ============================================================================

class ClientContext(BaseModel):
    """
    Context attached to request.state after successful authentication.
    Used by all protected endpoints to identify and authorize the client.
    """
    client_type: Literal["ehr", "mobile_app", "web_app", "admin"]
    client_id: UUID
    client_name: str
    hospital_id: Optional[UUID] = None  # NULL = global access (mobile/web apps)
    allowed_doctor_ids: Optional[List[UUID]] = None  # NULL = all doctors
    scopes: List[str] = []

    # For admin users (Supabase auth)
    user_id: Optional[UUID] = None
    user_email: Optional[str] = None
    user_role: Optional[Literal["super_admin", "admin", "viewer"]] = None

    def has_scope(self, scope: str) -> bool:
        """Check if client has a specific scope"""
        return scope in self.scopes

    def can_access_hospital(self, hospital_id: UUID) -> bool:
        """
        Check if client can access data from a specific hospital.
        - NULL hospital_id on client = global access (all hospitals)
        - Otherwise, must match exactly
        """
        if self.hospital_id is None:
            return True  # Global access
        return self.hospital_id == hospital_id

    def can_access_doctor(self, doctor_id: UUID) -> bool:
        """
        Check if client can access a specific doctor's data.
        - NULL allowed_doctor_ids = all doctors
        - Otherwise, must be in the list
        """
        if self.allowed_doctor_ids is None:
            return True  # Access to all doctors
        return doctor_id in self.allowed_doctor_ids


# ============================================================================
# API Client Management
# ============================================================================

class APIClientCreate(BaseModel):
    """Request model for creating a new API client"""
    client_name: str = Field(..., min_length=3, max_length=100, description="Human-readable client name")
    client_type: Literal["ehr", "mobile_app", "web_app"]
    auth_mode: Literal["api_key", "token"] = Field(
        default="api_key",
        description="Authentication mode: 'api_key' (static) or 'token' (OAuth 2.0 client credentials). Only applies to EHR clients."
    )
    hospital_id: Optional[UUID] = Field(
        None,
        description="Hospital ID for EHR clients (required). NULL for mobile/web apps (global access)."
    )
    allowed_doctor_ids: Optional[List[UUID]] = Field(
        None,
        description="Specific doctor IDs to grant access to. NULL = all doctors."
    )
    scopes: List[str] = Field(
        default=["read:extractions", "write:extractions"],
        description="Permission scopes for the client"
    )
    rate_limit_per_hour: int = Field(
        default=1000,
        ge=10,
        le=100000,
        description="Maximum API requests per hour"
    )
    token_expiry_minutes: int = Field(
        default=120,
        ge=1,
        le=1440,
        description="Access token lifetime in minutes (1-1440). Only applies to token-mode EHR clients."
    )
    contact_email: Optional[EmailStr] = Field(None, description="Contact email for the client")
    description: Optional[str] = Field(None, max_length=500, description="Description of the client")


class APIClientUpdate(BaseModel):
    """Request model for updating an API client"""
    client_name: Optional[str] = Field(None, min_length=3, max_length=100)
    allowed_doctor_ids: Optional[List[UUID]] = None
    scopes: Optional[List[str]] = None
    rate_limit_per_hour: Optional[int] = Field(None, ge=10, le=100000)
    token_expiry_minutes: Optional[int] = Field(None, ge=1, le=1440)
    contact_email: Optional[EmailStr] = None
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


class APIClientResponse(BaseModel):
    """Response model for API client (without sensitive data)"""
    id: UUID
    client_name: str
    client_type: str
    auth_mode: str = "api_key"
    hospital_id: Optional[UUID]
    allowed_doctor_ids: Optional[List[UUID]]
    scopes: List[str]
    is_active: bool
    rate_limit_per_hour: int
    token_expiry_minutes: int = 120
    contact_email: Optional[str]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime]

    # Computed fields
    api_key_prefix: Optional[str] = None  # For identification


class APIKeyCreateResponse(BaseModel):
    """
    Response when creating a new API client.
    IMPORTANT: api_key/client_secret is only returned ONCE at creation time.
    """
    client_id: UUID
    client_name: str
    client_type: str
    auth_mode: str = "api_key"
    api_key: Optional[str] = Field(None, description="Full API key - only shown once at creation (api_key mode)")
    api_key_prefix: Optional[str] = Field(None, description="First 8 characters for identification")
    client_secret: Optional[str] = Field(None, description="Client secret - only shown once at creation (token mode)")
    message: str = "API key created successfully. Please save it securely - it won't be shown again."


class APIKeyRotateResponse(BaseModel):
    """Response when rotating an API key"""
    client_id: UUID
    client_name: str
    new_api_key: str = Field(..., description="New API key - only shown once")
    new_api_key_prefix: str
    old_api_key_prefix: str
    message: str = "API key rotated successfully. The old key is now invalid."


# ============================================================================
# Service JWT (for Mobile/Web Apps)
# ============================================================================

class ServiceJWTCreate(BaseModel):
    """Request model for generating a service JWT"""
    client_id: UUID = Field(..., description="API client ID")
    expires_in_hours: int = Field(
        default=24,
        ge=1,
        le=720,  # Max 30 days
        description="JWT expiration time in hours"
    )


class ServiceJWTResponse(BaseModel):
    """Response with service JWT token"""
    token: str
    token_type: str = "Bearer"
    expires_in: int = Field(..., description="Expiration time in seconds")
    expires_at: datetime
    client_id: UUID
    client_name: str


# ============================================================================
# Admin User Management
# ============================================================================

class AdminUserCreate(BaseModel):
    """Request model for creating an admin user"""
    auth_user_id: UUID = Field(..., description="Supabase auth.users.id")
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=100)
    role: Literal["super_admin", "admin", "viewer"] = "admin"
    hospital_id: Optional[UUID] = Field(None, description="Hospital scope. NULL = global access.")


class AdminUserUpdate(BaseModel):
    """Request model for updating an admin user"""
    full_name: Optional[str] = Field(None, max_length=100)
    role: Optional[Literal["super_admin", "admin", "viewer"]] = None
    is_active: Optional[bool] = None


class AdminUserResponse(BaseModel):
    """Response model for admin user"""
    id: UUID
    auth_user_id: UUID
    email: str
    full_name: Optional[str]
    role: str
    hospital_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ============================================================================
# API Usage & Rate Limiting
# ============================================================================

class APIUsageStats(BaseModel):
    """API usage statistics for a client"""
    client_id: UUID
    client_name: str
    total_requests: int
    requests_last_hour: int
    requests_last_24h: int
    rate_limit_per_hour: int
    rate_limit_remaining: int
    success_rate: float = Field(..., description="Percentage of successful requests (2xx)")
    avg_response_time_ms: float
    top_endpoints: List[dict] = Field(default=[], description="Most used endpoints")


class RateLimitInfo(BaseModel):
    """Rate limit information returned in response headers"""
    limit: int = Field(..., description="Rate limit per hour")
    remaining: int = Field(..., description="Remaining requests in current window")
    reset_at: datetime = Field(..., description="When the rate limit resets")


# ============================================================================
# Authentication Requests/Responses
# ============================================================================

class TokenValidationResponse(BaseModel):
    """Response for token validation endpoint"""
    valid: bool
    client_type: Optional[str] = None
    client_name: Optional[str] = None
    scopes: List[str] = []
    expires_at: Optional[datetime] = None
    error: Optional[str] = None


# ============================================================================
# Available Scopes (for documentation)
# ============================================================================

AVAILABLE_SCOPES = [
    # Extraction-related
    "read:extractions",
    "write:extractions",

    # Patient-related
    "read:patients",
    "write:patients",

    # Doctor-related
    "read:doctors",
    "write:doctors",

    # Recording-related
    "read:recordings",
    "write:recordings",

    # Admin-only
    "admin:clients",
    "admin:audit",
    "admin:users",
]

# Default scopes by client type
DEFAULT_SCOPES = {
    "ehr": ["read:extractions", "write:extractions", "read:patients", "write:patients", "read:doctors"],
    "mobile_app": ["read:extractions", "write:extractions", "read:patients", "read:doctors"],
    "web_app": ["read:extractions", "write:extractions", "read:patients", "read:doctors"],
    "admin": AVAILABLE_SCOPES,  # Full access
}


# ============================================================================
# OAuth 2.0 Client Credentials (for token-mode EHR clients)
# ============================================================================

class ClientCredentialsRequest(BaseModel):
    """OAuth 2.0 Client Credentials grant request"""
    client_id: UUID = Field(..., description="API client ID")
    client_secret: str = Field(..., description="Client secret")
    grant_type: str = Field(default="client_credentials", description="Must be 'client_credentials'")


class ClientCredentialsResponse(BaseModel):
    """OAuth 2.0 Client Credentials grant response"""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(..., description="Access token lifetime in seconds")
    expires_at: datetime = Field(..., description="Access token expiry (ISO 8601)")


class ClientRefreshRequest(BaseModel):
    """OAuth 2.0 refresh token request"""
    client_id: UUID = Field(..., description="API client ID")
    refresh_token: str = Field(..., description="Refresh token from previous token/refresh response")
    grant_type: str = Field(default="refresh_token", description="Must be 'refresh_token'")


class ClientRefreshResponse(BaseModel):
    """OAuth 2.0 refresh token response"""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(..., description="Access token lifetime in seconds")
    expires_at: datetime = Field(..., description="Access token expiry (ISO 8601)")

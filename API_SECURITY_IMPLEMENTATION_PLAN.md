# API Security Implementation Plan

> **Status**: Ready for implementation
> **Created**: December 2024
> **Estimated Time**: ~13 hours

## Overview

Implement multi-layer authentication and authorization for 4 client types.

**All authentication uses `Authorization: Bearer <token>` header.**

| Client | Auth Method | Header Format |
|--------|-------------|---------------|
| EHR Integration | API Keys | `Authorization: Bearer <api_key>` |
| Mobile App | Service JWT | `Authorization: Bearer <jwt>` |
| External Web (White-label) | Service JWT | `Authorization: Bearer <jwt>` |
| Local Web App | Supabase Auth | `Authorization: Bearer <supabase_jwt>` |

API keys are automatically distinguished from JWTs by format (JWTs have 3 dot-separated parts starting with "eyJ").

---

## Phase 1: Database Schema (Migration)

**File:** `backend/supabase/migrations/YYYYMMDDHHMMSS_add_api_security_tables.sql`

### 1.1 API Clients Table (for EHR, Mobile, External Web)

```sql
CREATE TABLE api_clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_name TEXT NOT NULL,
    client_type TEXT NOT NULL CHECK (client_type IN ('ehr', 'mobile_app', 'web_app')),

    -- Authentication
    api_key_hash TEXT,                    -- For EHR (hashed with bcrypt)
    api_key_prefix VARCHAR(8),            -- First 8 chars for identification (e.g., "ehr_abc1")
    jwt_secret TEXT,                      -- For mobile/web apps (to sign service JWTs)

    -- Authorization scope
    -- EHR: hospital_id is REQUIRED (one API key per hospital)
    -- Mobile/Web: hospital_id NULL = ALL hospitals access
    hospital_id UUID REFERENCES hospitals(id),  -- NULL = global access (mobile/web apps)
    allowed_doctor_ids UUID[],            -- NULL = all doctors (in hospital or globally)
    scopes TEXT[] DEFAULT ARRAY['read:extractions', 'write:extractions'],

    -- Status
    is_active BOOLEAN DEFAULT true,
    rate_limit_per_hour INT DEFAULT 1000,

    -- Metadata
    contact_email TEXT,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_used_at TIMESTAMPTZ,

    -- Constraint: EHR clients MUST have hospital_id
    CONSTRAINT ehr_requires_hospital CHECK (
        client_type != 'ehr' OR hospital_id IS NOT NULL
    )
);

CREATE INDEX idx_api_clients_api_key_prefix ON api_clients(api_key_prefix);
CREATE INDEX idx_api_clients_hospital ON api_clients(hospital_id);

-- Example access patterns:
-- EHR1 for Hospital A: client_type='ehr', hospital_id='hosp-a-uuid'
-- EHR1 for Hospital B: client_type='ehr', hospital_id='hosp-b-uuid' (separate API key)
-- Mobile App: client_type='mobile_app', hospital_id=NULL (accesses ALL hospitals)
-- White-label Web: client_type='web_app', hospital_id=NULL (accesses ALL hospitals)
```

### 1.2 HIPAA Audit Log Table (PHI Access Trail)

```sql
-- HIPAA-compliant audit log for all PHI access
-- Retention: Keep for minimum 6 years per HIPAA requirements
CREATE TABLE phi_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- WHO accessed
    client_id UUID REFERENCES api_clients(id),
    client_type TEXT NOT NULL,            -- 'ehr', 'mobile_app', 'web_app', 'admin'
    client_name TEXT NOT NULL,            -- Human-readable client name
    user_id UUID,                         -- For admin users (Supabase auth.users.id)
    user_email TEXT,                      -- For audit readability

    -- WHAT was accessed
    action TEXT NOT NULL,                 -- 'read', 'create', 'update', 'delete', 'export'
    resource_type TEXT NOT NULL,          -- 'patient', 'extraction', 'prescription', 'diagnosis'
    resource_id TEXT,                     -- UUID or identifier of the resource

    -- WHOSE data (PHI identifiers)
    patient_id TEXT,                      -- Patient identifier (external or internal)
    doctor_id UUID,                       -- Doctor who owns the data
    hospital_id UUID,                     -- Hospital context

    -- HOW it was accessed
    endpoint TEXT NOT NULL,               -- API endpoint path
    method TEXT NOT NULL,                 -- HTTP method
    ip_address INET,                      -- Client IP address
    user_agent TEXT,                      -- Client user agent

    -- WHEN
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,

    -- Request/Response details (for investigation)
    request_id UUID,                      -- Correlation ID for request tracing
    status_code INT,
    response_time_ms INT,
    error_message TEXT,

    -- Additional context
    phi_fields_accessed TEXT[],           -- Which PHI fields were in response
    data_exported BOOLEAN DEFAULT false,  -- Was data exported/downloaded?
    access_reason TEXT                    -- Optional: why access was needed
);

-- Indexes for HIPAA audit queries
CREATE INDEX idx_phi_audit_patient ON phi_audit_log(patient_id, created_at DESC);
CREATE INDEX idx_phi_audit_doctor ON phi_audit_log(doctor_id, created_at DESC);
CREATE INDEX idx_phi_audit_client ON phi_audit_log(client_id, created_at DESC);
CREATE INDEX idx_phi_audit_user ON phi_audit_log(user_id, created_at DESC);
CREATE INDEX idx_phi_audit_time ON phi_audit_log(created_at DESC);
CREATE INDEX idx_phi_audit_resource ON phi_audit_log(resource_type, resource_id);

-- Prevent deletion of audit logs (HIPAA requires retention)
-- Note: Consider partitioning by month for large-scale deployments
```

### 1.3 API Usage Tracking Table (Rate Limiting & Analytics)

```sql
CREATE TABLE api_client_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES api_clients(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    doctor_id UUID,
    patient_id TEXT,
    status_code INT,
    response_time_ms INT,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_api_usage_client_time ON api_client_usage(client_id, created_at DESC);
CREATE INDEX idx_api_usage_created ON api_client_usage(created_at DESC);

-- Rate limiting helper: count requests in last hour
CREATE INDEX idx_api_usage_rate_limit ON api_client_usage(client_id, created_at)
    WHERE created_at > now() - interval '1 hour';
```

### 1.4 Admin Users Table (for Supabase Auth)

```sql
CREATE TABLE admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id UUID UNIQUE NOT NULL,    -- Links to Supabase auth.users.id
    email TEXT NOT NULL,
    full_name TEXT,
    role TEXT DEFAULT 'admin' CHECK (role IN ('super_admin', 'admin', 'viewer')),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

---

## Phase 2: Backend Auth Infrastructure

### 2.1 Auth Models

**File:** `backend/models/auth_models.py`

```python
from pydantic import BaseModel
from typing import Optional, Literal
from uuid import UUID

class ClientContext(BaseModel):
    """Attached to request after authentication"""
    client_type: Literal["ehr", "mobile_app", "web_app", "admin"]
    client_id: UUID
    client_name: str
    hospital_id: Optional[UUID] = None
    allowed_doctor_ids: Optional[list[UUID]] = None
    scopes: list[str] = []

class APIKeyCreate(BaseModel):
    client_name: str
    client_type: Literal["ehr", "mobile_app", "web_app"]
    hospital_id: UUID
    scopes: list[str] = ["read:extractions", "write:extractions"]
    rate_limit_per_hour: int = 1000

class APIKeyResponse(BaseModel):
    client_id: UUID
    client_name: str
    api_key: str  # Only shown once at creation
    api_key_prefix: str
```

### 2.2 Auth Service

**File:** `backend/services/auth_service.py`

Key functions:
- `generate_api_key()` - Create new API key for EHR/apps
- `hash_api_key()` - Bcrypt hash for storage
- `verify_api_key()` - Validate incoming API key
- `generate_service_jwt()` - Create JWT for mobile/web apps
- `verify_service_jwt()` - Validate incoming service JWT
- `verify_supabase_jwt()` - Validate Supabase auth JWT
- `get_client_context()` - Build ClientContext from validated auth
- `check_hospital_access()` - Verify client can access hospital (NULL = all)

### 2.3 HIPAA Audit Service

**File:** `backend/services/audit_service.py`

```python
from typing import Optional
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

class AuditService:
    """HIPAA-compliant audit logging for PHI access"""

    PHI_ENDPOINTS = [
        "/api/v1/patients/",
        "/api/v1/extractions/",
        "/api/v1/summary/extract",
        "/api/v1/option1/recording/",
    ]

    async def log_phi_access(
        self,
        client_context: ClientContext,
        request: Request,
        response_status: int,
        response_time_ms: int,
        patient_id: Optional[str] = None,
        doctor_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: str = "read",
        phi_fields: Optional[list[str]] = None,
    ):
        """Log PHI access to audit table"""
        await supabase.table("phi_audit_log").insert({
            "client_id": str(client_context.client_id),
            "client_type": client_context.client_type,
            "client_name": client_context.client_name,
            "user_id": str(client_context.user_id) if hasattr(client_context, 'user_id') else None,
            "action": action,
            "resource_type": resource_type or self._infer_resource_type(request.url.path),
            "resource_id": resource_id,
            "patient_id": patient_id,
            "doctor_id": str(doctor_id) if doctor_id else None,
            "hospital_id": str(client_context.hospital_id) if client_context.hospital_id else None,
            "endpoint": request.url.path,
            "method": request.method,
            "ip_address": request.client.host,
            "user_agent": request.headers.get("user-agent"),
            "request_id": request.state.request_id,
            "status_code": response_status,
            "response_time_ms": response_time_ms,
            "phi_fields_accessed": phi_fields,
        }).execute()

    def is_phi_endpoint(self, path: str) -> bool:
        """Check if endpoint accesses PHI"""
        return any(path.startswith(ep) for ep in self.PHI_ENDPOINTS)

audit_service = AuditService()
```

### 2.4 Auth Middleware

**File:** `backend/middleware/auth_middleware.py`

```python
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class AuthMiddleware(BaseHTTPMiddleware):
    # Endpoints that don't require auth
    PUBLIC_PATHS = ["/", "/health", "/docs", "/redoc", "/openapi.json"]

    async def dispatch(self, request: Request, call_next):
        # Skip auth for public paths
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Get Authorization header (all auth uses Bearer token)
        auth_header = request.headers.get("Authorization")

        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

            # Determine token type by format
            # JWTs have 3 dot-separated parts and start with "eyJ"
            # API keys are simple strings without this format
            is_jwt_format = token.count(".") == 2 and token.startswith("eyJ")

            if not is_jwt_format:
                # API key (EHR integration)
                client_context = await verify_api_key(token)
            elif is_supabase_token(token):
                # Supabase JWT (local web admin)
                client_context = await verify_supabase_jwt(token)
            else:
                # Service JWT (mobile/external web)
                client_context = await verify_service_jwt(token)
        else:
            raise HTTPException(401, "Missing authentication: provide Authorization: Bearer <token>")

        # Attach context to request state
        request.state.client = client_context
        return await call_next(request)
```

### 2.5 Auth Dependencies

**File:** `backend/dependencies/auth.py`

```python
from fastapi import Depends, HTTPException, Request
from models.auth_models import ClientContext

def get_current_client(request: Request) -> ClientContext:
    """Dependency to get authenticated client from request"""
    if not hasattr(request.state, "client"):
        raise HTTPException(401, "Not authenticated")
    return request.state.client

def require_scope(scope: str):
    """Dependency factory for scope-based authorization"""
    def check_scope(client: ClientContext = Depends(get_current_client)):
        if scope not in client.scopes:
            raise HTTPException(403, f"Missing required scope: {scope}")
        return client
    return check_scope

def require_doctor_access(doctor_id: str):
    """Check if client can access this doctor's data"""
    def check_access(client: ClientContext = Depends(get_current_client)):
        if client.allowed_doctor_ids is not None:
            if UUID(doctor_id) not in client.allowed_doctor_ids:
                raise HTTPException(403, "Access denied to this doctor's data")
        return client
    return check_access
```

---

## Phase 3: Update Routers with Auth

### 3.1 Example: Patient History Router

**File:** `backend/routers/patient_history.py`

```python
from dependencies.auth import get_current_client, require_scope
from models.auth_models import ClientContext

@router.get("/{patient_id}/last-prescription")
async def get_last_prescription(
    patient_id: str,
    doctor_id: Optional[str] = Query(None),
    client: ClientContext = Depends(get_current_client)  # NEW
):
    # Validate doctor access
    if doctor_id and client.allowed_doctor_ids:
        if UUID(doctor_id) not in client.allowed_doctor_ids:
            raise HTTPException(403, "Access denied to this doctor")

    # Auto-create patient if EHR client
    if client.client_type == "ehr":
        await ensure_patient_exists(patient_id)

    # ... rest of implementation
```

### 3.2 Protected Endpoints by Scope

| Endpoint | Required Scope |
|----------|---------------|
| `GET /api/v1/patients/*` | `read:patients` |
| `POST /api/v1/option1/recording/*` | `write:extractions` |
| `GET /api/v1/extractions/*` | `read:extractions` |
| `PUT /api/v1/extractions/*` | `write:extractions` |
| `POST /api/v1/summary/extract` | `write:extractions` |
| `GET /api/v1/doctors/*` | `read:doctors` |
| `POST /api/v1/doctors/*` | `write:doctors` (admin only) |

---

## Phase 4: CORS Configuration

**File:** `backend/main.py`

```python
ALLOWED_ORIGINS = [
    "http://localhost:3000",           # Local dev
    "https://app.Unizy.ai",             # Production web app
    "https://admin.Unizy.ai",           # Admin dashboard
    # Add white-label domains here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
```

**Note:** Server-to-server calls (EHR) are NOT affected by CORS.

---

## Phase 5: Admin API for Client Management

**File:** `backend/routers/admin.py` (extend existing)

New endpoints:
- `POST /api/v1/admin/clients` - Create API client (returns API key once)
- `GET /api/v1/admin/clients` - List all API clients
- `PUT /api/v1/admin/clients/{id}` - Update client (scopes, rate limit)
- `DELETE /api/v1/admin/clients/{id}` - Revoke client access
- `POST /api/v1/admin/clients/{id}/rotate-key` - Rotate API key
- `GET /api/v1/admin/clients/{id}/usage` - View usage stats

---

## Phase 6: Frontend Supabase Auth (Local Web)

### 6.1 Install Supabase Auth UI

```bash
npm install @supabase/auth-ui-react @supabase/auth-ui-shared
```

### 6.2 Add Login Page

**File:** `app/login/page.tsx`

```tsx
'use client';
import { Auth } from '@supabase/auth-ui-react';
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs';

export default function LoginPage() {
  const supabase = createClientComponentClient();

  return (
    <Auth
      supabaseClient={supabase}
      appearance={{ theme: ThemeSupa }}
      providers={[]}  // Email/password only
      redirectTo="/auth/callback"
    />
  );
}
```

### 6.3 Auth Middleware (Next.js)

**File:** `middleware.ts`

```typescript
import { createMiddlewareClient } from '@supabase/auth-helpers-nextjs';
import { NextResponse } from 'next/server';

export async function middleware(req) {
  const res = NextResponse.next();
  const supabase = createMiddlewareClient({ req, res });
  const { data: { session } } = await supabase.auth.getSession();

  if (!session && req.nextUrl.pathname !== '/login') {
    return NextResponse.redirect(new URL('/login', req.url));
  }

  return res;
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|login).*)'],
};
```

---

## Implementation Order

### Step 1: Database Migration (1 hour)
- [ ] Create migration file with api_clients, phi_audit_log, api_client_usage, admin_users tables
- [ ] Apply migration to Supabase

### Step 2: Auth Service (2 hours)
- [ ] Create `backend/models/auth_models.py`
- [ ] Create `backend/services/auth_service.py`
- [ ] Add bcrypt to requirements.txt
- [ ] Add PyJWT to requirements.txt

### Step 3: HIPAA Audit Service (1.5 hours)
- [ ] Create `backend/services/audit_service.py`
- [ ] Define PHI endpoints list
- [ ] Implement async audit logging

### Step 4: Auth Middleware (1 hour)
- [ ] Create `backend/middleware/auth_middleware.py`
- [ ] Create `backend/dependencies/auth.py`
- [ ] Integrate audit logging into middleware
- [ ] Register middleware in `backend/main.py`

### Step 5: Update Routers (3 hours)
- [ ] Add auth dependencies to all routers
- [ ] Add doctor/patient access validation
- [ ] Add hospital access validation (NULL = all hospitals for mobile/web)
- [ ] Add auto-create patient logic for EHR clients
- [ ] Add audit logging calls for PHI endpoints

### Step 6: Admin Client Management (2 hours)
- [ ] Add client management endpoints to admin router
- [ ] Add audit log viewer endpoint
- [ ] Create client management UI (optional)

### Step 7: CORS Update (15 min)
- [ ] Update CORS to whitelist specific origins

### Step 8: Frontend Auth (2 hours)
- [ ] Add Supabase auth packages
- [ ] Create login page
- [ ] Add Next.js auth middleware
- [ ] Update API calls to include auth headers

---

## Files to Create/Modify

**New Files:**
- `backend/supabase/migrations/YYYYMMDDHHMMSS_add_api_security_tables.sql`
- `backend/models/auth_models.py`
- `backend/services/auth_service.py`
- `backend/services/audit_service.py` - HIPAA audit logging
- `backend/middleware/auth_middleware.py`
- `backend/dependencies/auth.py`
- `app/login/page.tsx`
- `app/auth/callback/route.ts` - Supabase auth callback
- `middleware.ts` (Next.js root)

**Modified Files:**
- `backend/main.py` - Add middleware, update CORS
- `backend/requirements.txt` - Add bcrypt, PyJWT
- `backend/routers/patient_history.py` - Add auth + audit logging
- `backend/routers/recording_session.py` - Add auth + audit logging
- `backend/routers/extractions.py` - Add auth + audit logging
- `backend/routers/summary.py` - Add auth + audit logging
- `backend/routers/doctors.py` - Add auth
- `backend/routers/merge.py` - Add auth + audit logging
- `backend/routers/admin.py` - Add client management + audit viewer
- `app/page.tsx` - Remove hardcoded admin user
- `lib/summaryApi.ts` - Add auth headers to API calls
- `lib/patientHistoryApi.ts` - Add auth headers to API calls

---

## Security Summary

| Layer | Protection |
|-------|-----------|
| **Transport** | HTTPS (handled by hosting) |
| **Authentication** | API Keys (EHR), Service JWT (Apps), Supabase JWT (Web) |
| **Authorization** | Hospital-scoped, Doctor-scoped, Scope-based |
| **Rate Limiting** | Per-client configurable limits |
| **HIPAA Audit** | All PHI access logged with WHO, WHAT, WHOSE, WHEN, HOW |
| **CORS** | Whitelist frontend domains only |

---

## Access Control Matrix

| Client Type | hospital_id | Access Scope |
|-------------|-------------|--------------|
| **EHR** | REQUIRED (UUID) | Only that hospital's doctors/patients |
| **Mobile App** | NULL | ALL hospitals (global access) |
| **Web App (White-label)** | NULL | ALL hospitals (global access) |
| **Admin (Supabase Auth)** | N/A | Full access based on role |

---

## HIPAA Compliance Features

1. **Audit Trail**: Every PHI access logged with:
   - WHO: Client ID, type, name, user email
   - WHAT: Action (read/create/update/delete), resource type, resource ID
   - WHOSE: Patient ID, doctor ID, hospital ID
   - HOW: Endpoint, method, IP address, user agent
   - WHEN: Timestamp

2. **Retention**: 6+ years (HIPAA minimum requirement)

3. **Non-repudiation**: Logs cannot be deleted (no DELETE on phi_audit_log)

4. **Access Reporting**: Admin endpoints to query:
   - All access to a specific patient
   - All access by a specific client
   - All access in a time range

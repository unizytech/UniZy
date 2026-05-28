# EHR Integration Guide: Token-Based Authentication

## Overview

Your integration uses **OAuth 2.0 Client Credentials** authentication. Instead of a static API key, you receive short-lived access tokens that expire after a configured duration (default: 120 minutes).

**You will receive from us:**
- `client_id` — Your unique client identifier (UUID)
- `client_secret` — Your secret key (shown once at setup — store securely)
- `base_url` — The API base URL

---

## Step 1: Get an Access Token

Exchange your `client_id` + `client_secret` for an access token.

```
POST {base_url}/api/v1/auth/token
Content-Type: application/json

{
  "client_id": "your-client-id",
  "client_secret": "your-client-secret",
  "grant_type": "client_credentials"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "a1b2c3d4...",
  "token_type": "Bearer",
  "expires_in": 7200,
  "expires_at": "2026-03-07T13:00:00+00:00"
}
```

| Field | Description |
|-------|-------------|
| `access_token` | Use this in API calls (Step 2) |
| `refresh_token` | Use this to get a new access token before expiry (Step 3) |
| `expires_in` | Token lifetime in seconds |
| `expires_at` | Exact expiry timestamp (ISO 8601) |

---

## Step 2: Call APIs Using the Access Token

Include the access token as a Bearer token in every API request. This is identical to how you would use a static API key.

```
GET {base_url}/api/v1/extractions/{id}
Authorization: Bearer eyJhbGciOi...
```

```
POST {base_url}/api/v1/summary/extract
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{ ... }
```

You can make **unlimited API calls** with the same access token until it expires (subject to your rate limit).

---

## Step 3: Refresh Before Expiry

Before the access token expires, call the refresh endpoint to get a new one. We recommend refreshing **5 minutes before expiry**.

```
POST {base_url}/api/v1/auth/client-refresh
Content-Type: application/json

{
  "client_id": "your-client-id",
  "refresh_token": "a1b2c3d4...",
  "grant_type": "refresh_token"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOi...(new)",
  "refresh_token": "x9y8z7w6...(new)",
  "token_type": "Bearer",
  "expires_in": 7200,
  "expires_at": "2026-03-07T14:00:00+00:00"
}
```

**Important:** Each refresh token is **single-use**. After refreshing, the old refresh token is invalidated and a new one is returned. Always store and use the latest refresh token.

---

## Token Lifecycle Summary

```
1. Authenticate
   POST /auth/token  (client_id + client_secret)
         |
         v
   access_token (e.g. 120 min) + refresh_token (30 days)
         |
         v
2. Use access_token for all API calls
         |
         v
3. ~5 min before expiry, refresh
   POST /auth/client-refresh  (client_id + refresh_token)
         |
         v
   new access_token + new refresh_token
         |
         v
   (repeat from step 2)
```

---

## Error Handling

| Scenario | HTTP Status | What to Do |
|----------|-------------|------------|
| Access token expired | `401` | Call `/auth/client-refresh` with your refresh token |
| Refresh token expired or invalid | `401` | Re-authenticate with `/auth/token` using client_id + client_secret |
| Rate limit exceeded | `429` | Wait and retry. Check `Retry-After` header. |
| Invalid credentials | `401` | Verify client_id and client_secret |

### Recommended Error Handling Flow

```
API call returns 401?
  -> Try refreshing with /auth/client-refresh
     -> Refresh returns 401?
        -> Re-authenticate with /auth/token (client_id + client_secret)
        -> If this also fails, credentials may be revoked — contact us
```

---

## Implementation Checklist

- [ ] Store `client_id` and `client_secret` securely (environment variables, secrets manager — never in source code)
- [ ] On application startup, call `/auth/token` to get initial tokens
- [ ] Store `access_token` and `refresh_token` in memory
- [ ] Include `Authorization: Bearer {access_token}` on every API call
- [ ] Track `expires_at` or `expires_in` and proactively refresh ~5 minutes before expiry
- [ ] On refresh, replace both the access token and refresh token with the new values
- [ ] Handle `401` responses by attempting a refresh, then re-authentication if refresh fails
- [ ] Handle `429` responses by respecting the `Retry-After` header

---

## Example (Python)

```python
import requests
import time

BASE_URL = "https://api.example.com"
CLIENT_ID = "your-client-id"
CLIENT_SECRET = "your-client-secret"

# State
access_token = None
refresh_token = None
expires_at = 0

def authenticate():
    """Get initial tokens using client credentials."""
    global access_token, refresh_token, expires_at
    resp = requests.post(f"{BASE_URL}/api/v1/auth/token", json={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
    })
    resp.raise_for_status()
    data = resp.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    expires_at = time.time() + data["expires_in"]

def refresh():
    """Refresh tokens before expiry."""
    global access_token, refresh_token, expires_at
    resp = requests.post(f"{BASE_URL}/api/v1/auth/client-refresh", json={
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    if resp.status_code == 401:
        # Refresh token expired — re-authenticate
        authenticate()
        return
    resp.raise_for_status()
    data = resp.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    expires_at = time.time() + data["expires_in"]

def get_token():
    """Get a valid access token, refreshing if needed."""
    if access_token is None:
        authenticate()
    elif time.time() > expires_at - 300:  # 5 min buffer
        refresh()
    return access_token

def api_call(method, path, **kwargs):
    """Make an authenticated API call with auto-refresh."""
    headers = {"Authorization": f"Bearer {get_token()}"}
    resp = requests.request(method, f"{BASE_URL}{path}", headers=headers, **kwargs)
    if resp.status_code == 401:
        # Token might have just expired — refresh and retry once
        refresh()
        headers = {"Authorization": f"Bearer {get_token()}"}
        resp = requests.request(method, f"{BASE_URL}{path}", headers=headers, **kwargs)
    return resp

# Usage
result = api_call("POST", "/api/v1/summary/extract", json={"audio_url": "..."})
print(result.json())
```

---

## Authorization: How Access Control Works

Once your credentials are validated (Step 1), every API call passes through multiple layers of authorization before reaching the requested resource. This is a defense-in-depth model — even with a valid token, you can only access data you are explicitly permitted to see.

### Layer 1: Authentication (Identity Verification)

Every request must include a valid access token. The system verifies:

- The token is well-formed and has not been tampered with
- The token has not expired
- The token belongs to an active (non-revoked) client

If any of these fail, you receive `401 Unauthorized`.

### Layer 2: Rate Limiting

Before processing the request, the system checks whether your client has exceeded its configured rate limit (requests per hour). This is set during onboarding and can be adjusted by your account administrator.

If exceeded, you receive `429 Too Many Requests` with a `Retry-After` header indicating when you can resume.

### Layer 3: Hospital Scoping

Your EHR client is bound to a **single hospital** at creation time. This cannot be changed and is enforced on every request.

- You can **only** access doctors, patients, recordings, and extractions that belong to your assigned hospital
- Any attempt to access a resource from a different hospital returns `403 Forbidden`
- There is no way to bypass this — the hospital binding is embedded in your credentials

**Example:** If your client is assigned to Hospital A, and you request an extraction that belongs to a doctor at Hospital B, the request is denied — even if the extraction ID is valid.

### Layer 4: Doctor Restrictions (Optional)

Your client may optionally be restricted to **specific doctors** within your hospital. If configured:

- You can only access data for the listed doctors
- Requests involving unlisted doctors return `403 Forbidden`

If no doctor restrictions are set, you have access to all doctors within your hospital.

**Example:** If your client is restricted to Dr. Smith and Dr. Patel, you cannot access Dr. Kumar's extractions — even though all three are at your hospital.

### Layer 5: Permission Scopes

Each client is assigned a set of permission scopes that control **what operations** you can perform. Default EHR scopes are:

| Scope | Allows |
|-------|--------|
| `read:extractions` | View extraction results |
| `write:extractions` | Create recordings, trigger extractions, submit edits |
| `read:patients` | View patient history and records |
| `write:patients` | Create/update patient records |
| `read:doctors` | View doctor profiles and configurations |

If you attempt an operation outside your granted scopes, you receive `403 Forbidden` with a message indicating the missing scope.

### Layer 6: Resource-Level Validation

Even after passing all the above layers, the system performs resource-level checks on every request:

| Resource | Validation |
|----------|------------|
| **Doctor** | Must belong to your hospital |
| **Patient** | Must have at least one record linked to a doctor in your hospital |
| **Extraction** | Must belong to a doctor in your hospital |
| **Recording session** | Must have been started by a doctor in your hospital |
| **Audio chunk upload** | Must belong to an active recording in your hospital |

### Layer 7: Audit Logging

All API access — especially access to patient health information — is logged for compliance purposes. Audit logs capture:

- Which client accessed which resource
- Timestamp and response status
- The specific endpoint and operation type

These logs are retained for compliance review and cannot be modified or deleted by API clients.

### Authorization Flow Diagram

```
Incoming API Request
       |
       v
[Layer 1] Valid token? ──── No ──> 401 Unauthorized
       |
      Yes
       |
       v
[Layer 2] Within rate limit? ── No ──> 429 Too Many Requests
       |
      Yes
       |
       v
[Layer 3] Resource in your hospital? ── No ──> 403 Forbidden
       |
      Yes
       |
       v
[Layer 4] Doctor allowed? ── No ──> 403 Forbidden
       |
      Yes (or no doctor restriction)
       |
       v
[Layer 5] Has required scope? ── No ──> 403 Forbidden
       |
      Yes
       |
       v
[Layer 6] Resource-level access? ── No ──> 403 Forbidden
       |
      Yes
       |
       v
[Layer 7] Audit logged ──> Request processed ──> Response
```

### Common 403 Scenarios

| Scenario | Cause | Resolution |
|----------|-------|------------|
| "Access denied: client restricted to hospital X" | You tried to access a resource from another hospital | Only access resources within your assigned hospital |
| "Access denied: client does not have access to this doctor's data" | Doctor restriction is active and this doctor is not in your list | Contact your administrator to update doctor access |
| "Permission denied: missing required scope 'write:extractions'" | Your client lacks the needed permission | Contact your administrator to add the scope |
| "Patient not accessible to hospital X" | The patient has no records linked to doctors in your hospital | Verify the patient ID is correct |

---

## FAQ

**Q: How is this different from the static API key?**
A: With a static API key, the same key is sent with every request and never expires. With token-based auth, you get short-lived access tokens (configurable, default 120 min) that must be refreshed periodically. If a token is leaked, it expires quickly.

**Q: What happens if my server restarts and I lose the tokens?**
A: Simply call `/auth/token` again with your `client_id` + `client_secret` to get fresh tokens. There is no penalty for re-authenticating.

**Q: Can I have multiple active access tokens?**
A: Yes. Each call to `/auth/token` or `/auth/client-refresh` issues a new independent token. Previously issued tokens remain valid until their own expiry.

**Q: What if the refresh token expires?**
A: Refresh tokens are valid for 30 days. If it expires (e.g., your system was offline for >30 days), re-authenticate with `/auth/token` using your original `client_id` + `client_secret`.

# Auth & Feature Flags API

## `GET /api/v1/auth/validate`

Validates the current authentication credentials and returns client identity information including hospital feature flags.

### Authentication

- **Header**: `Authorization: Bearer <token>`
- **Token types**: API key, JWT access token, or client credentials token

### Response

```json
{
  "valid": true,
  "client_type": "ehr",
  "client_name": "My EHR Integration",
  "hospital_id": "uuid-here",
  "allowed_doctor_ids": ["doctor-uuid-1", "doctor-uuid-2"],
  "scopes": ["recording:write", "extraction:read"],
  "feature_flags": {
    "care_plan": true,
    "merge": true,
    "interventions": true,
    "upload": true,
    "ocr": false,
    "edit_prescription": true,
    "edit_investigation": true,
    "edit_record": true,
    "patient_qa": true,
    "doctor_qa": true,
    "template_configuration": true,
    "patient_registration": true,
    "billing": false,
    "nudge_plan": false,
    "iris": false,
    "triage_support": false
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `valid` | boolean | Always `true` (invalid tokens return 401) |
| `client_type` | string | One of: `admin`, `web_app`, `mobile_app`, `ehr` |
| `client_name` | string | Display name of the authenticated client |
| `hospital_id` | string? | Hospital UUID (null for super admins) |
| `allowed_doctor_ids` | string[]? | Doctor UUIDs this client can access (null = all) |
| `scopes` | string[] | Permission scopes granted to this client |
| `feature_flags` | object? | Per-hospital feature toggles (null if no hospital) |

### Error Responses

| Status | Description |
|--------|-------------|
| 401 | Missing or invalid Authorization header |
| 401 | Expired or revoked token |

### Examples

**API key auth (EHR):**
```bash
curl -H "Authorization: Bearer ak_live_abc123..." \
  http://localhost:8000/api/v1/auth/validate
```

**JWT auth (Web app):**
```bash
curl -H "Authorization: Bearer eyJhbGciOiJ..." \
  http://localhost:8000/api/v1/auth/validate
```

### Notes

- `feature_flags` is only populated when `hospital_id` is present
- Super admins (no hospital_id) should treat all features as enabled
- Feature flags are for frontend gating only — backend APIs remain accessible regardless
- Flags are extensible: new keys can be added without schema changes

---

## `GET /api/v1/hospitals/{hospital_id}/features`

Returns the feature flags for a specific hospital. Uses cached hospital settings — zero DB hit on hot path.

### Authentication

- **Header**: `Authorization: Bearer <token>`
- **Auth level**: Admin + Web + EHR (mobile clients get 403)

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `hospital_id` | string (UUID) | Hospital UUID |

### Response

```json
{
  "success": true,
  "hospital_id": "44cc627a-320e-4c0e-bfa6-ec3c04168747",
  "feature_flags": {
    "care_plan": true,
    "merge": true,
    "interventions": true,
    "upload": true,
    "ocr": false,
    "edit_prescription": true,
    "edit_investigation": true,
    "edit_record": true,
    "patient_qa": true,
    "doctor_qa": true,
    "template_configuration": true,
    "patient_registration": true,
    "billing": false,
    "nudge_plan": false,
    "iris": false,
    "triage_support": false
  }
}
```

### Error Responses

| Status | Description |
|--------|-------------|
| 401 | Missing or invalid auth |
| 500 | Failed to get feature flags |

### Example

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/hospitals/44cc627a-320e-4c0e-bfa6-ec3c04168747/features
```

---

## `PUT /api/v1/hospitals/{hospital_id}/features`

Updates feature flags for a hospital. Performs a **partial merge** — only the keys you send are updated; all other existing flags are preserved. New keys can be added for extensibility.

### Authentication

- **Header**: `Authorization: Bearer <token>`
- **Auth level**: **Super admin only** (returns 403 for other roles)

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `hospital_id` | string (UUID) | Hospital UUID |

### Request Body

```json
{
  "feature_flags": {
    "ocr": true,
    "billing": true,
    "my_custom_feature": true
  }
}
```

Only include the flags you want to change. Omitted flags keep their current value.

### Response

```json
{
  "success": true,
  "hospital_id": "44cc627a-320e-4c0e-bfa6-ec3c04168747",
  "feature_flags": {
    "care_plan": true,
    "merge": true,
    "interventions": true,
    "upload": true,
    "ocr": true,
    "edit_prescription": true,
    "edit_investigation": true,
    "edit_record": true,
    "patient_qa": true,
    "doctor_qa": true,
    "template_configuration": true,
    "patient_registration": true,
    "billing": true,
    "nudge_plan": false,
    "iris": false,
    "triage_support": false,
    "my_custom_feature": true
  },
  "message": "Feature flags updated for 'Guru Hospital'"
}
```

### Error Responses

| Status | Description |
|--------|-------------|
| 401 | Missing or invalid auth |
| 403 | Only super admins can update feature flags |
| 404 | Hospital not found |
| 500 | Failed to update feature flags |

### Example

```bash
curl -X PUT \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"feature_flags": {"ocr": true, "billing": true}}' \
  http://localhost:8000/api/v1/hospitals/44cc627a-320e-4c0e-bfa6-ec3c04168747/features
```

---

## Feature Flag Keys Reference

| Key | Label | Default | Where Gated |
|-----|-------|---------|-------------|
| `care_plan` | Care Plan | true | Patient/Dashboard |
| `merge` | Merge Extractions | true | Extraction history |
| `interventions` | Interventions | true | Dashboard |
| `upload` | File Upload | true | VHR screen |
| `ocr` | OCR Processing | false | VHR/Upload |
| `edit_prescription` | Edit Prescription | true | Patient history |
| `edit_investigation` | Edit Investigation | true | Patient history |
| `edit_record` | Edit Record | true | Extraction detail |
| `patient_qa` | Patient Q&A | true | Q&A Engine |
| `doctor_qa` | Doctor Q&A | true | Q&A Engine |
| `template_configuration` | Template Config | true | Config tab |
| `patient_registration` | Patient Registration | true | Add Patient tab |
| `billing` | Billing | false | Billing tab |
| `nudge_plan` | Nudge Plan | false | Interventions |
| `iris` | IRIS | false | TBD |
| `triage_support` | Triage Support | false | Triage tab |

Custom flags can be added via the PUT endpoint or the admin UI — any `string: boolean` key-value pair is accepted.

---

## `POST /api/v1/option1/recording/start`

Starts a new recording session. Returns a correlation ID used for subsequent chunk uploads and status polling.

### Authentication

- **Header**: `Authorization: Bearer <token>`
- **Auth level**: Admin + Web + EHR

### Request Body

```json
{
  "doctor_id": "uuid",
  "patient_id": "patient-identifier",
  "template_code": "OP_CORE",
  "template_name": "OP Core Template",
  "processing_mode": "default",
  "extraction_mode": "full",
  "chunk_duration_seconds": 10,
  "nurse_id": null,
  "recording_metadata": {},
  "correlation_id": null,
  "is_continuation": false
}
```

### Request Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `doctor_id` | string (UUID) | Yes | — | Doctor UUID |
| `patient_id` | string | Yes | — | Patient identifier |
| `template_code` | string? | No | Auto-resolved | Template code for extraction. If omitted, resolves from doctor/hospital default, then falls back to `OP_CORE`. Use `TRANSCRIPT_ONLY` to skip extraction. |
| `template_name` | string? | No | null | Template display name (for human readability) |
| `processing_mode` | string | No | `"default"` | Processing mode: `fast`, `default`, `thorough` |
| `extraction_mode` | string | No | `"full"` | Extraction mode: `core`, `additional`, `full` |
| `chunk_duration_seconds` | int (0-60) | No | `10` | Duration of each audio chunk in seconds. `0` = file upload mode. |
| `nurse_id` | string? | No | null | Nurse UUID if recording is initiated by a nurse |
| `recording_metadata` | object? | No | null | Additional metadata (patient info, doctor info, custom fields) that flows through to `/status` response |
| `correlation_id` | string? | No | Auto-generated | Correlation ID (UUID). If not provided, a new UUID is generated. |
| `is_continuation` | bool | No | `false` | Whether this recording continues a prior consultation for the same patient in the same visit. When `true`, the system finds prior extractions within the time window and uses continuation mode (restricted context injection). When `false`, prior context is used normally. |

### Response

```json
{
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_id": "db-session-uuid",
  "message": "Recording session started"
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `correlation_id` | string (UUID) | Unique session identifier for chunk uploads and status polling |
| `session_id` | string (UUID) | Database session ID |
| `message` | string | Confirmation message |

### `is_continuation` Behavior

When `is_continuation: true`:
1. The system searches for prior extractions for the same patient within a configured time window
2. If found, parent extraction IDs are stored in `session_context_json`
3. During extraction, prior context is injected in **continuation mode** (restricted context) rather than normal prior context mode
4. If no prior extractions are found, the session proceeds normally with `is_continuation` set to `false` in the session context

### Error Responses

| Status | Description |
|--------|-------------|
| 401 | Missing or invalid auth |
| 422 | Validation error (missing required fields, invalid values) |
| 500 | Failed to create recording session |

### Example

```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "doctor_id": "d1234567-...",
    "patient_id": "PAT001",
    "template_code": "OP_CORE",
    "processing_mode": "default",
    "extraction_mode": "full",
    "chunk_duration_seconds": 10,
    "is_continuation": false
  }' \
  http://localhost:8000/api/v1/option1/recording/start
```

**Continuation recording example:**
```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "doctor_id": "d1234567-...",
    "patient_id": "PAT001",
    "template_code": "OP_CORE",
    "is_continuation": true
  }' \
  http://localhost:8000/api/v1/option1/recording/start
```

---

## `GET /api/v1/option1/recording/status/{submission_id}`

Returns the current processing status for a recording session. When status is `COMPLETED`, the response includes extraction results, timing metrics, and continuation info (`is_continuation`, `parent_extraction_ids`).

### Authentication

- **Header**: `Authorization: Bearer <token>`
- **Auth level**: Admin + Web + EHR (verified against submission ownership)

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `submission_id` | string (UUID) | Submission ID returned from the last chunk upload (`is_last: true`) |

### Response (Processing)

```json
{
  "submission_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PROCESSING",
  "progress": 45,
  "message": "Transcribing audio..."
}
```

### Response (Completed)

```json
{
  "submission_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "COMPLETED",
  "progress": 100,
  "message": "Extraction complete",
  "extraction_id": "ext-uuid-here",
  "transcript": "Doctor: Patient presents with...",
  "insights": {
    "chief_complaint": { ... },
    "diagnosis": { ... }
  },
  "metrics": {
    "stitching_time": 1.2,
    "transcription_time": 8.5,
    "extraction_time": 12.3,
    "total_time": 22.0,
    "is_continuation": true,
    "parent_extraction_ids": ["ext-uuid-1", "ext-uuid-2"]
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `submission_id` | string (UUID) | The submission ID queried |
| `status` | string | `PENDING`, `PROCESSING`, `COMPLETED`, or `ERROR` |
| `progress` | int (0-100) | Processing progress percentage |
| `message` | string | Human-readable progress message |
| `extraction_id` | string? | Extraction UUID (only when `COMPLETED`) |
| `transcript` | string? | Full transcript text (only when `COMPLETED`) |
| `insights` | object? | Extracted medical segments (only when `COMPLETED`) |
| `metrics` | object? | Timing and continuation info (only when `COMPLETED`) |

### Metrics Fields (when `COMPLETED`)

| Field | Type | Description |
|-------|------|-------------|
| `stitching_time` | float? | Audio stitching time in seconds |
| `transcription_time` | float? | Transcription time in seconds |
| `extraction_time` | float? | LLM extraction time in seconds |
| `total_time` | float? | Total processing time in seconds |
| `is_continuation` | bool | Whether this extraction was a continuation of a prior visit |
| `parent_extraction_ids` | string[] | UUIDs of parent extractions from the same visit (empty if not a continuation) |

### Error Responses

| Status | Description |
|--------|-------------|
| 400 | Invalid submission_id format |
| 401 | Missing or invalid auth |
| 404 | Processing job not found |
| 500 | Failed to get status |

### Example

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/option1/recording/status/550e8400-e29b-41d4-a716-446655440000
```

### Notes

- The frontend primarily uses **Supabase Realtime** (WebSocket) for real-time progress updates. This endpoint is a **polling fallback**.
- `parent_extraction_ids` contains the UUIDs of all prior extractions in the same visit chain. EHR integrations can use these to fetch prior context or link related consultations.

---

## `GET /api/v1/patients/{patient_id}/consultations/latest`

Returns patient consultations de-duplicated by continuation chain. Only standalone extractions and the **latest extraction in each continuation chain** are returned — parent extractions that have been superseded are excluded.

### Authentication

- **Header**: `Authorization: Bearer <token>`
- **Auth level**: Admin + Web + EHR (with hospital/doctor scoping)

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `patient_id` | string | Patient identifier (external ID or UUID) |

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `doctor_id` | string? | null | Filter by doctor UUID |
| `page` | int | 1 | Page number (1-based) |
| `page_size` | int | 20 | Results per page (max 100) |

### Response

```json
{
  "patient": {
    "id": "internal-uuid",
    "patient_id": "PAT001",
    "full_name": "John Doe",
    "date_of_birth": "1990-01-15",
    "gender": "male"
  },
  "consultations": [
    {
      "extraction_id": "ext-uuid-3",
      "session_id": "session-uuid",
      "consultation_type": "ct-uuid",
      "consultation_type_name": "OP",
      "doctor_id": "doc-uuid",
      "doctor_name": "Dr. Smith",
      "created_at": "2026-03-15T10:30:00Z",
      "is_edited": false,
      "has_emotion_analysis": true,
      "segment_count": 8,
      "primary_diagnosis": "Type 2 Diabetes",
      "chief_complaint": "Follow-up visit"
    }
  ],
  "total_count": 5,
  "page": 1,
  "page_size": 20,
  "has_more": false
}
```

### How De-duplication Works

Given a continuation chain: `ext-1` → `ext-2` → `ext-3` (where `ext-3.parent_extraction_ids = [ext-1, ext-2]`):

- `ext-1` and `ext-2` are **excluded** (their IDs appear in `ext-3`'s `parent_extraction_ids`)
- `ext-3` is **included** (chain tip — no other extraction references it as a parent)
- Standalone extractions (`is_continuation = false`, `parent_extraction_ids = []`) are always included

### Comparison with `/consultations`

| Endpoint | Returns |
|----------|---------|
| `GET /{patient_id}/consultations` | All extractions (including superseded parents) |
| `GET /{patient_id}/consultations/latest` | Only chain tips + standalone (de-duplicated) |

### Error Responses

| Status | Description |
|--------|-------------|
| 400 | Invalid patient ID |
| 401 | Missing or invalid auth |
| 404 | Patient not found |
| 500 | Failed to get latest consultations |

### Example

```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/patients/PAT001/consultations/latest?doctor_id=doc-uuid&page=1&page_size=10"
```

---

# Nurse Management APIs

Base path: `/api/v1/nurses`

---

## `GET /api/v1/nurses`

List all nurses with optional filters.

- **Auth**: Admin only
- **Query params**: `active_only` (bool, default `true`), `hospital_id` (optional UUID filter)

### Response

```json
{
  "success": true,
  "nurses": [
    {
      "id": "nurse-uuid",
      "email": "nurse@hospital.com",
      "full_name": "Jane Smith",
      "qualification": "RN",
      "hospital_id": "hospital-uuid",
      "is_active": true,
      "created_at": "2026-03-15T10:00:00Z",
      "updated_at": "2026-03-15T10:00:00Z"
    }
  ],
  "count": 1
}
```

### Example

```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/nurses?active_only=true&hospital_id=hospital-uuid"
```

---

## `GET /api/v1/nurses/{nurse_id}`

Get a single nurse by ID.

- **Auth**: Admin + Web + EHR

### Response

```json
{
  "success": true,
  "nurse": {
    "id": "nurse-uuid",
    "email": "nurse@hospital.com",
    "full_name": "Jane Smith",
    "qualification": "RN",
    "hospital_id": "hospital-uuid",
    "is_active": true,
    "created_at": "2026-03-15T10:00:00Z",
    "updated_at": "2026-03-15T10:00:00Z"
  }
}
```

---

## `POST /api/v1/nurses`

Create a new nurse with auto-generated UUID.

- **Auth**: Admin only

### Request Body

```json
{
  "email": "nurse@hospital.com",
  "full_name": "Jane Smith",
  "qualification": "RN",
  "hospital_id": "hospital-uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | Yes | Unique email address |
| `full_name` | string | Yes | Full name (2-255 chars) |
| `qualification` | string? | No | Nursing qualification (RN, LPN, BSN) |
| `hospital_id` | string? | No | Hospital UUID |

### Response

```json
{
  "success": true,
  "message": "Nurse 'Jane Smith' created successfully",
  "nurse": { ... }
}
```

### Notes

- Auto-shares the PRESCREEN template with the nurse on creation
- Email must be unique (returns 400 if duplicate)

---

## `POST /api/v1/nurses/with-hospital`

Create a nurse with a **caller-provided UUID** and hospital code lookup.

- **Auth**: Admin + Web + EHR (EHR restricted to own hospital)

### Request Body

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "hospital_code": "HOSP001",
  "full_name": "Jane Smith",
  "email": "nurse@hospital.com",
  "qualification": "RN"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string (UUID) | Yes | Nurse UUID (provided by caller) |
| `hospital_code` | string | Yes | Hospital code to resolve hospital_id |
| `full_name` | string | Yes | Full name (2-255 chars) |
| `email` | string | Yes | Unique email address |
| `qualification` | string? | No | Nursing qualification |

### Response

```json
{
  "success": true,
  "message": "Nurse 'Jane Smith' created successfully",
  "nurse_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| Status | Description |
|--------|-------------|
| 404 | Hospital not found or inactive |
| 409 | Nurse with this ID or email already exists |

---

## `POST /api/v1/nurses/ehr`

Create a nurse for EHR integration with **auto-generated UUID** and hospital code lookup.

- **Auth**: Admin + Web + EHR (EHR restricted to own hospital)

### Request Body

```json
{
  "hospital_code": "HOSP001",
  "full_name": "Jane Smith",
  "email": "nurse@hospital.com",
  "qualification": "RN"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `hospital_code` | string | Yes | Hospital code to resolve hospital_id |
| `full_name` | string | Yes | Full name (2-255 chars) |
| `email` | string | Yes | Unique email address |
| `qualification` | string? | No | Nursing qualification |

### Response

```json
{
  "success": true,
  "message": "Nurse 'Jane Smith' created successfully",
  "nurse_id": "auto-generated-uuid"
}
```

---

## `PUT /api/v1/nurses/{nurse_id}`

Update nurse information.

- **Auth**: Admin + Web + EHR (EHR restricted to nurses in own hospital)

### Request Body

All fields are optional — only include fields you want to update.

```json
{
  "email": "new-email@hospital.com",
  "full_name": "Jane Smith-Jones",
  "qualification": "BSN",
  "hospital_id": "new-hospital-uuid",
  "is_active": true,
  "default_template_id": "template-uuid"
}
```

### Response

```json
{
  "success": true,
  "message": "Nurse updated successfully",
  "nurse": { ... }
}
```

---

## `DELETE /api/v1/nurses/{nurse_id}`

Soft-delete a nurse (sets `is_active = false`).

- **Auth**: Admin only

### Response

```json
{
  "success": true,
  "message": "Nurse 'Jane Smith' deactivated successfully",
  "nurse": { ... }
}
```

---

## `GET /api/v1/nurses/{nurse_id}/doctors`

List all doctors linked to a nurse.

- **Auth**: Admin + Web + EHR

### Response

```json
{
  "success": true,
  "nurse_id": "nurse-uuid",
  "doctors": [
    {
      "association_id": "assoc-uuid",
      "doctor_id": "doctor-uuid",
      "doctor_name": "Dr. Smith",
      "email": "dr.smith@hospital.com",
      "specialization": "Pediatrics",
      "hospital_id": "hospital-uuid",
      "is_active": true,
      "created_at": "2026-03-15T10:00:00Z"
    }
  ],
  "count": 1
}
```

### Example

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/nurses/nurse-uuid/doctors
```

---

## `POST /api/v1/nurses/{nurse_id}/doctors/{doctor_id}`

Link a nurse to a supervising doctor.

- **Auth**: Admin only

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `nurse_id` | string (UUID) | Nurse UUID |
| `doctor_id` | string (UUID) | Doctor UUID |

### Response

```json
{
  "success": true,
  "message": "Nurse linked to doctor successfully",
  "association": { ... }
}
```

### Notes

- Idempotent — calling multiple times has the same result
- If association exists but is inactive, it will be reactivated

### Example

```bash
curl -X POST -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/nurses/nurse-uuid/doctors/doctor-uuid
```

---

## `DELETE /api/v1/nurses/{nurse_id}/doctors/{doctor_id}`

Unlink a nurse from a doctor (soft-delete).

- **Auth**: Admin only

### Response

```json
{
  "success": true,
  "message": "Nurse unlinked from doctor successfully",
  "association": { ... }
}
```

### Notes

- Soft delete — association record is preserved, can be relinked later

---

## `PUT /api/v1/nurses/{nurse_id}/default-template`

Set or clear the default template for a nurse.

- **Auth**: Admin + Web + EHR (EHR restricted to own hospital)

### Request Body

```json
{
  "template_id": "template-uuid"
}
```

Send `"template_id": null` to clear the default.

### Response

```json
{
  "success": true,
  "message": "Default template set for nurse 'Jane Smith'",
  "default_template_id": "template-uuid"
}
```

### Notes

- Nurse default takes highest priority in the nurse template fallback chain
- The template must be accessible to the nurse (`is_active = true`)

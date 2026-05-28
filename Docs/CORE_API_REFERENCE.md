# Core API Reference

This document covers the main APIs used in the VHR (Virtual Health Record) recording and extraction workflow.

**Last Updated:** December 28, 2024

---

## Table of Contents

1. [Security & Authentication](#security--authentication)
   - [Authorization Header](#authorization-header)
   - [EHR Access Control](#ehr-access-control)
   - [EHR Integration Code Examples](#ehr-integration-code-examples)
2. [Recording APIs](#recording-apis)
   - [POST /start](#post-start)
   - [POST /chunk](#post-chunk)
   - [POST /cancel](#post-cancel)
   - [GET /status/{submission_id}](#get-statussubmission_id)
   - [POST /live/session](#post-livesession)
3. [Extraction APIs](#extraction-apis)
   - [POST /extract](#post-extract)
4. [Merge APIs](#merge-apis)
   - [POST /merge](#post-merge)
   - [POST /merge/preview](#post-mergepreview)
   - [GET /merge/status/{extraction_id}](#get-mergestatusextraction_id)
5. [Edit APIs](#edit-apis)
   - [PUT /extractions/{extraction_id}](#put-extractionsextraction_id)
   - [PUT /extractions/by-submission/{submission_id}](#put-extractionsby-submissionsubmission_id)
6. [Lookup APIs](#lookup-apis)
   - [GET /by-submission/{submission_id}](#get-by-submissionsubmission_id)
   - [GET /by-session/{session_id}](#get-by-sessionsession_id)
7. [Emotion Analysis APIs](#emotion-analysis-apis)
   - [GET /extractions/{extraction_id}/emotions](#get-extractionsextraction_idemotions)
   - [GET /extractions/by-submission/{submission_id}/emotions](#get-extractionsby-submissionsubmission_idemotions)
8. [Patient APIs](#patient-apis)
   - [GET /patients/search](#get-patientssearch)
   - [GET /patients/{patient_id}/prescreen](#get-patientspatient_idprescreen)
9. [Medicine List APIs](#medicine-list-apis)
   - [GET /{doctor_id}](#get-doctor_id)
   - [POST /{doctor_id}](#post-doctor_id)
   - [POST /{doctor_id}/upload](#post-doctor_idupload)
   - [POST /hospital/{hospital_id}/upload](#post-hospitalhospital_idupload)
   - [POST /feedback/{match_log_id}](#post-feedbackmatch_log_id)
   - [POST /feedback/bulk-agree](#post-feedbackbulk-agree)
10. [Investigation List APIs](#investigation-list-apis)
    - [GET /{doctor_id}](#get-doctor_id-1)
    - [POST /{doctor_id}](#post-doctor_id-1)
    - [POST /{doctor_id}/upload](#post-doctor_idupload-1)
    - [POST /hospital/{hospital_id}/upload](#post-hospitalhospital_idupload-1)
11. [Template Sharing APIs](#template-sharing-apis)
    - [POST /share](#post-share)
    - [POST /share-hospital](#post-share-hospital)
    - [POST /share-specialization](#post-share-specialization)
12. [Triage APIs](#triage-apis)
    - [POST /generate](#post-generate)
    - [POST /feedback](#post-feedback)
    - [GET /feedback/stats/{doctor_id}](#get-feedbackstatsdoctor_id)
    - [GET /differentials/{specialty}/{presentation}](#get-differentialsspecialtypresentation)
    - [GET /specialties](#get-specialties)
    - [GET /presentations/{specialty}](#get-presentationsspecialty)
13. [Intervention APIs](#intervention-apis)
    - [GET /{extraction_id}/interventions](#get-extraction_idinterventions)
14. [Doctor Management APIs](#doctor-management-apis)
    - [POST /doctors/ehr](#post-doctorsehr)
15. [EHR Integration APIs (Sanitized)](#ehr-integration-apis-sanitized)
    - [GET /ehr/status/{submission_id}](#get-ehrstatussubmission_id)
    - [POST /ehr/extract](#post-ehrextract)
    - [GET /ehr/merge/status/{extraction_id}](#get-ehrmergestatusextraction_id)
    - [POST /ehr/merge/preview](#post-ehrmergepreview)
    - [GET /ehr/extractions/{extraction_id}/emotions](#get-ehrextractionsextraction_idemotions)
    - [GET /ehr/extractions/by-submission/{submission_id}/emotions](#get-ehrextractionsby-submissionsubmission_idemotions)
    - [GET /ehr/patients/{patient_id}/prescreen](#get-ehrpatientspatient_idprescreen)
16. [Aosta EHR Integration APIs](#aosta-ehr-integration-apis)
    - [POST /start (with recording_metadata)](#post-start-with-recording_metadata)
    - [GET /ehr/iframe/status/{submission_id}](#get-ehriframestatussubmission_id)
    - [PUT /ehr/iframe/edit/{submission_id}](#put-ehriframeeditsubmission_id)
17. [Changelog](#changelog)

---

## Security & Authentication

### Authorization Header

**All API endpoints require authentication** when `AUTH_ENABLED=true`.

**EHR/External Integrations (API Key):**
```
Authorization: Bearer <api_key>
```

**Web/Mobile Apps (JWT):**
```
Authorization: Bearer <jwt_token>
```

API keys are issued per client (EHR system, mobile app, web app, admin). Each client type has different access scopes. The system automatically distinguishes between API keys and JWTs based on token format.

### EHR Access Control

When `AUTH_ENABLED=true`, EHR clients are hospital-scoped and can only access data belonging to doctors registered with their hospital.

**Key Security Rules:**

| Endpoint Type | Validation Method | Description |
|--------------|-------------------|-------------|
| Query param `doctor_id` | `EHRDoctorAccessChecker` dependency | Validates doctor belongs to EHR's hospital |
| Body param `doctor_id` | `validate_doctor_from_body()` after body parsing | Same validation, but for request body fields |
| Body param `sharing_doctor_id` | `verify_doctor_access_from_body` dependency | For template sharing endpoints |
| Correlation-based (`correlation_id`) | `validate_correlation_from_body()` | Validates recording session belongs to hospital |
| Patient data | `EHRPatientAccessChecker` | Validates patient has consultations with hospital |

**EHR Client Requirements:**
- All endpoints with `doctor_id` parameter require the doctor to belong to the EHR's hospital
- Nurse-initiated recordings: EHR clients can also use `nurse_id` for hospital validation
- Templates/segments endpoints require `doctor_id` for EHR clients (returns 400 if missing)
- Medicines feedback endpoints require `doctor_id` query parameter
- Template sharing endpoints use `sharing_doctor_id` in request body for validation

### EHR Integration Code Examples

Below are complete Python examples for EHR system integration using API keys.

#### Example 1: Complete Recording & Extraction Workflow

```python
import requests
import base64
import time

# Configuration
API_BASE_URL = "https://api.example.com"
API_KEY = "ehr_your_api_key_here"  # Issued by admin

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def start_recording(doctor_id: str, patient_id: str, template_code: str = "OP_GENERAL"):
    """Start a new recording session."""
    response = requests.post(
        f"{API_BASE_URL}/api/v1/option1/recording/start",
        headers=HEADERS,
        json={
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "template_code": template_code,
            "processing_mode": "default",
            "extraction_mode": "full",
            "chunk_duration_seconds": 10
        }
    )
    response.raise_for_status()
    data = response.json()
    print(f"✅ Recording started: correlation_id={data['correlation_id']}")
    return data["correlation_id"], data["session_id"]


def upload_chunk(correlation_id: str, chunk_index: int, audio_bytes: bytes, is_last: bool = False):
    """Upload an audio chunk."""
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

    response = requests.post(
        f"{API_BASE_URL}/api/v1/option1/recording/chunk",
        headers=HEADERS,
        json={
            "correlation_id": correlation_id,
            "chunk_index": chunk_index,
            "audio_data": audio_base64,
            "mime_type": "audio/webm",
            "is_last": is_last
        }
    )
    response.raise_for_status()
    data = response.json()

    if is_last:
        print(f"✅ Final chunk uploaded: submission_id={data.get('submissionId')}")
        return data.get("submissionId")
    else:
        print(f"✅ Chunk {chunk_index} uploaded")
        return None


def poll_status(submission_id: str, max_attempts: int = 30, interval: int = 5):
    """Poll for processing status until complete."""
    for attempt in range(max_attempts):
        response = requests.get(
            f"{API_BASE_URL}/api/v1/option1/recording/status/{submission_id}",
            headers=HEADERS
        )
        response.raise_for_status()
        data = response.json()

        status = data.get("status")
        progress = data.get("progress_percentage", 0)
        print(f"📊 Status: {status} ({progress}%)")

        if status == "COMPLETED":
            print("✅ Processing complete!")
            return data
        elif status in ("ERROR", "FAILED"):
            raise Exception(f"Processing failed: {data.get('error_message')}")

        time.sleep(interval)

    raise TimeoutError("Processing did not complete in time")


# Full workflow example
if __name__ == "__main__":
    DOCTOR_ID = "3a913f3c-24d5-4c11-a968-52c8024de2db"
    PATIENT_ID = "PAT-12345"

    # 1. Start recording
    correlation_id, session_id = start_recording(DOCTOR_ID, PATIENT_ID)

    # 2. Upload audio chunks (simulated)
    for i in range(3):
        # In real usage: audio_bytes = recorder.get_chunk()
        audio_bytes = b"fake_audio_data"
        is_last = (i == 2)
        submission_id = upload_chunk(correlation_id, i, audio_bytes, is_last)

    # 3. Poll for results
    result = poll_status(submission_id)

    # 4. Access extraction
    extraction_id = result.get("extraction_id")
    print(f"📋 Extraction ID: {extraction_id}")
    print(f"📝 Transcript: {result.get('transcript', '')[:200]}...")
```

#### Example 2: Nurse-Initiated Recording (Prescreen)

```python
import requests

API_BASE_URL = "https://api.example.com"
API_KEY = "ehr_your_api_key_here"  # Issued by admin

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def start_nurse_recording(nurse_id: str, doctor_id: str, patient_id: str):
    """
    Start a recording session initiated by a nurse.

    Nurse must belong to the same hospital as the EHR client.
    The nurse_id is used for hospital validation when doctor_id is not provided.
    """
    response = requests.post(
        f"{API_BASE_URL}/api/v1/option1/recording/start",
        headers=HEADERS,
        json={
            "doctor_id": doctor_id,       # Doctor who will review
            "nurse_id": nurse_id,         # Nurse initiating the recording
            "patient_id": patient_id,
            "template_code": "PRESCREEN", # Prescreen template for nurses
            "processing_mode": "fast",
            "extraction_mode": "full"
        }
    )
    response.raise_for_status()
    return response.json()


def get_patient_prescreen(patient_id: str, doctor_id: str):
    """
    Get prescreen information for a patient before consultation.

    Returns:
    - Latest prescreen extraction (if exists)
    - Emotion pattern summary from past consultations
    - Top interventions recommendations
    - Warning factors (allergies, contraindications)
    - Clinical timeline
    - Last prescription
    """
    response = requests.get(
        f"{API_BASE_URL}/api/v1/patients/{patient_id}/prescreen",
        headers=HEADERS,
        params={"doctor_id": doctor_id}
    )
    response.raise_for_status()
    data = response.json()

    print(f"👤 Patient: {data['patient']['full_name']}")
    print(f"📋 Has Prescreen: {data['has_prescreen']}")
    print(f"🏥 Consultation Count: {data['consultation_count']}")

    if data.get("warning_factors"):
        allergies = data["warning_factors"].get("allergies", [])
        print(f"⚠️ Allergies: {', '.join(allergies) if allergies else 'None'}")

    if data.get("top_interventions"):
        print("💡 Top Interventions:")
        for intervention in data["top_interventions"][:3]:
            print(f"   - {intervention['intervention']}")

    return data


# Example usage
if __name__ == "__main__":
    NURSE_ID = "6465b44c-ed1a-4ce0-acfb-cb10b7b6f059"
    DOCTOR_ID = "3a913f3c-24d5-4c11-a968-52c8024de2db"
    PATIENT_ID = "PAT-12345"

    # Start nurse-initiated prescreen recording
    result = start_nurse_recording(NURSE_ID, DOCTOR_ID, PATIENT_ID)
    print(f"✅ Prescreen recording started: {result['correlation_id']}")

    # Later, get prescreen data for doctor's consultation
    prescreen = get_patient_prescreen(PATIENT_ID, DOCTOR_ID)
```

---

## Recording APIs

Base URL: `/api/v1/option1/recording`

### POST /start

Start a new recording session. Returns a `correlation_id` for subsequent chunk uploads.

**Endpoint:** `POST /api/v1/option1/recording/start`

#### Request Body

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `doctor_id` | string (UUID) | **Yes** | - | Doctor's UUID |
| `patient_id` | string | **Yes** | - | Patient identifier (external ID like MRN, auto-creates patient record) |
| `template_code` | string | **Yes** | - | Template code for DB lookups or `'TRANSCRIPT_ONLY'` |
| `template_name` | string | No | - | Template display name (optional) |
| `nurse_id` | string (UUID) | No | - | Nurse's UUID (for nurse-initiated recordings) |
| `processing_mode` | string | No | `"default"` | `'fast'`, `'default'`, `'thorough'`, `'ultra'`, `'ultra_fast'` |
| `extraction_mode` | string | No | `"full"` | `'core'`, `'additional'`, `'full'` |
| `chunk_duration_seconds` | int | No | `10` | Duration of each audio chunk (0-60 seconds) |

#### Response

```json
{
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "message": "Recording session started successfully"
}
```

#### Notes

- `doctor_id` must be a valid UUID (validated on backend)
- `patient_id` is a flexible string; backend auto-creates patient record if not exists
- `correlation_id` is used for all subsequent `/chunk` calls
- If `template_code` is `'TRANSCRIPT_ONLY'`, no extraction is performed

---

### POST /chunk

Upload an audio chunk for an active recording session.

**Endpoint:** `POST /api/v1/option1/recording/chunk`

#### Request Body

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `correlation_id` | string (UUID) | **Yes** | - | Session correlation ID from `/start` |
| `chunk_index` | int | **Yes** | - | Sequential chunk index (0-based) |
| `audio_data` | string | **Yes** | - | Base64-encoded audio data |
| `mime_type` | string | No | `"audio/webm"` | Audio MIME type |
| `duration_seconds` | float | No | `null` | Chunk duration in seconds |
| `is_last` | boolean | No | `false` | Set to `true` for the final chunk |

#### Response

```json
{
  "message": "Chunk 0 uploaded successfully",
  "chunkIndex": 0,
  "totalChunks": 1,
  "submissionId": "789e0123-e45b-67c8-d901-234567890abc"
}
```

#### Notes

- `submissionId` is **only returned when `is_last=true`**
- When `is_last=true`:
  - Session status changes to `SUBMITTED`
  - Processing job is created
  - Background processing starts automatically (transcription + extraction)
  - Use `submissionId` to poll status via `GET /status/{submission_id}` or receive webhook
- Chunks must be uploaded sequentially (0, 1, 2, ...)

---

### POST /cancel

Cancel an active recording session.

**Endpoint:** `POST /api/v1/option1/recording/cancel`

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `correlation_id` | string (UUID) | **Yes** | Session correlation ID from `/start` |

#### Response

```json
{
  "message": "Recording session cancelled successfully",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### Notes

- Changes session status to `CANCELLED`
- Deletes all uploaded chunks
- Stops any ongoing processing
- Cannot cancel sessions with status `COMPLETED` or `ERROR`
- **Security:** EHR clients must have access to the recording session's hospital (validated via `correlation_id`)

---

### GET /status/{submission_id}

Get current processing status for a submission (polling fallback).

**Endpoint:** `GET /api/v1/option1/recording/status/{submission_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `submission_id` | string (UUID) | Submission ID from `/chunk` (is_last=true) response |

#### Response

```json
{
  "submission_id": "789e0123-e45b-67c8-d901-234567890abc",
  "status": "COMPLETED",
  "progress": 100,
  "message": "Extraction complete",
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "transcript": "Doctor: Hello, how are you feeling today?...",
  "insights": {
    "chief_complaints": { ... },
    "diagnosis": { ... },
    "prescription": { ... }
  },
  "metrics": {
    "stitching_time": 1.2,
    "transcription_time": 8.5,
    "extraction_time": 12.3,
    "total_time": 22.0
  }
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `submission_id` | string | The submission ID |
| `status` | string | Processing status: `PENDING`, `SUBMITTED`, `PROCESSING`, `COMPLETED`, `ERROR` |
| `progress` | int | Progress percentage (0-100) |
| `message` | string | Human-readable status message |
| `extraction_id` | string | Extraction UUID (only when `status=COMPLETED`) |
| `transcript` | string | Full transcript (only when `status=COMPLETED`) |
| `insights` | object | Extracted medical data (only when `status=COMPLETED`) |
| `metrics` | object | Processing time metrics in seconds (only when `status=COMPLETED`) |

#### Notes

- **Primary use:** Real-time updates via WebSocket. Use this endpoint as a polling fallback when WebSocket is unavailable.
- Returns 404 if `submission_id` not found
- `transcript`, `insights`, and `metrics` are only included when `status=COMPLETED`
- **Security:** EHR clients must have access to the recording session's hospital (validated via `submission_id`)

---

### POST /live/session

Create a recording session for WebSocket/live recordings (RecordTab flow).

**Endpoint:** `POST /api/v1/option1/recording/live/session`

#### Request Body

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `doctor_id` | string (UUID) | **Yes** | - | Doctor's UUID |
| `patient_id` | string | **Yes** | - | Patient identifier |
| `template_code` | string | **Yes** | - | Template code for database lookups |
| `template_name` | string | No | - | Template display name (optional) |
| `processing_mode` | string | No | `"ultra"` | Processing mode (`'ultra'`, `'ultra_fast'`) |

#### Response

```json
{
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "message": "Live session created successfully"
}
```

#### Notes

- Unlike chunked recording, this creates session at END of recording, just before extraction
- No audio chunks are uploaded - transcript comes from client-side WebSocket transcription
- `correlation_id` is used as `submission_id` for the live session workflow
- Creates `processing_job` record automatically
- **Security:** EHR clients must have access to the doctor's hospital

#### Live Recording Flow

```
1. User records via RecordTab WebSocket (client-side)
2. User stops recording
3. POST /live/session → Returns correlation_id
4. POST /extract with:
   - submission_id: from step 3
   - transcript: from WebSocket recording
5. Extraction saved and webhook sent
```

---

## Extraction APIs

Base URL: `/api/v1/summary`

### POST /extract

Extract medical summary from transcript using database-driven template configuration.

**Endpoint:** `POST /api/v1/summary/extract`

#### Request Body

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `transcript` | string | **Yes** | - | Consultation transcript text (min 10 chars) |
| `submission_id` | string (UUID) | **Yes** | - | Submission ID from `/chunk` (is_last=true) or `/live/session` |
| `doctor_id` | string (UUID) | No | - | Doctor ID for personalized configuration |
| `patient_id` | string | No | - | Patient ID (for Live API flow) |
| `template_code` | string | No | - | Template code for segment configuration |
| `template_name` | string | No | - | Template display name |
| `processing_mode` | string | No | - | `'fast'`, `'default'`, `'thorough'`, `'ultra'`, `'ultra_fast'` |
| `mode` | string | No | `"full"` | Extraction mode: `'core'`, `'additional'`, `'full'` |

#### Response

```json
{
  "success": true,
  "data": {
    "chief_complaints": { ... },
    "diagnosis": { ... },
    "prescription": { ... }
  },
  "metadata": {
    "mode": "full",
    "segment_count": 12,
    "model": "gemini-2.5-pro",
    "doctor_id": "550e8400-e29b-41d4-a716-446655440000",
    "validation": {
      "is_valid": true,
      "error_message": null,
      "warnings": []
    },
    "consultation_type_code": "OP",
    "template_name": "General OP Consultation"
  }
}
```

#### Notes

- **`submission_id` is required** - links extraction to recording session
- Extraction result is persisted and can be retrieved via `extraction_id`
- Emotion analysis is scheduled based on consultation type settings
- Supports progressive extraction: `core` first, then `additional`

---

## Merge APIs

Base URL: `/api/v1/extractions`

### POST /merge

Merge multiple medical extractions into a single consolidated output using AI-powered contextual merging.

**Endpoint:** `POST /api/v1/extractions/merge`

**Behavior:** Async - returns immediately with `extraction_id`, processing happens in background.

#### Request Body

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `source_extraction_ids` | string[] | No | `[]` | List of extraction UUIDs to merge (0-4) |
| `source_submission_ids` | string[] | No | `[]` | Alternative: List of submission UUIDs (auto-resolved to extraction_ids) |
| `uploaded_json_sources` | object[] | No | `[]` | List of JSON sources to merge (see below) |
| `target_template_code` | string | **Yes** | - | Target template code (e.g., `'OP_GENERAL'`) |
| `doctor_id` | string (UUID) | **Yes** | - | Doctor ID performing the merge |
| `patient_id` | string | Conditional | - | Required when merging only JSON uploads |
| `merge_notes` | string | No | - | Optional notes about the merge |

**Uploaded JSON Source Object:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `data` | object | **Yes** | JSON data to merge |
| `upload_type` | enum | No | `OP_SUMMARY`, `DISCHARGE_SUMMARY`, `EXAMINATION`, `OPTOMETRY`, `INVESTIGATION`, `PRESCRIPTION`, `NOTES`, `OTHER` |
| `source_name` | string | No | Display name for the source |
| `source_date` | string | No | ISO date for chronological ordering |

**Merge Strategies:**
- **DEEP_MERGE:** `OP_SUMMARY`, `DISCHARGE_SUMMARY`, `EXAMINATION`, `OPTOMETRY`, `OTHER` - AI contextually merges
- **APPEND:** `INVESTIGATION`, `PRESCRIPTION`, `NOTES` - Data appended to arrays

#### Response (202 Accepted)

```json
{
  "success": true,
  "extraction_id": "550e8400-e29b-41d4-a716-446655440003",
  "status": "processing",
  "message": "Merge operation started. Use extraction_id to check status or receive webhook."
}
```

#### Notes

- **Source Limits:** Minimum 2, Maximum 4 total sources (extractions + JSON uploads)
- **Changed:** Now uses `target_template_code` instead of `target_consultation_type_code`
- Template access is validated (owned, shared, or common templates)
- Webhook sent when merge completes
- **Security:** EHR clients must have access to the doctor's hospital

---

### POST /merge/preview

Preview merge without saving to database.

**Endpoint:** `POST /api/v1/extractions/merge/preview`

#### Request Body

Same as [POST /merge](#post-merge), except `merge_notes` is ignored.

#### Response

```json
{
  "success": true,
  "extraction_id": null,
  "submission_id": null,
  "merged_data": { ... },
  "merge_metadata": {
    "source_count": 2,
    "target_template_code": "OP_GENERAL",
    "merge_timestamp": "2025-01-15T10:30:00Z",
    "conflict_count": 1,
    "conflicts_resolved": ["chief_complaints"],
    "cross_type_scenario": "SAME_TYPE",
    "consultation_types_merged": ["OP"]
  },
  "preview": true
}
```

#### Notes

- Same AI-powered merge logic as `/merge`
- No database writes
- Use for doctor review before committing

---

### GET /merge/status/{extraction_id}

Check the status of a merge operation.

**Endpoint:** `GET /api/v1/extractions/merge/status/{extraction_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `extraction_id` | string (UUID) | Extraction ID from `/merge` response |

#### Response

```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440003",
  "status": "completed",
  "merged_data": { ... },
  "merge_metadata": { ... },
  "created_at": "2025-01-15T10:30:00Z",
  "completed_at": "2025-01-15T10:30:05Z"
}
```

**Status Values:**
- `processing` - Merge in progress
- `completed` - Merge finished successfully
- `failed` - Merge failed (includes `error` field)

---

## Edit APIs

Base URL: `/api/v1/extractions`

### PUT /extractions/{extraction_id}

Update extraction with doctor's edits.

**Endpoint:** `PUT /api/v1/extractions/{extraction_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `extraction_id` | string (UUID) | Extraction UUID |

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `edited_data` | object | **Yes** | Complete edited extraction JSON |
| `edited_by` | string (UUID) | **Yes** | Doctor ID who made the edits |

#### Response

```json
{
  "success": true,
  "message": "Extraction updated successfully. Edit count: 1",
  "extraction_id": "123e4567-e89b-12d3-a456-426614174000",
  "edit_count": 1,
  "last_edited_at": "2025-01-15T10:30:00Z",
  "medicine_feedback_scheduled": true
}
```

#### Notes

- Stores edits in `edited_extraction_json` field
- **Does NOT modify** `original_extraction_json` (AI-generated data preserved)
- Increments `edit_count` for audit trail
- Schedules background task to compare medicine name changes for future matching

---

### PUT /extractions/by-submission/{submission_id}

Update extraction using submission_id (wrapper for cases where extraction_id is not available).

**Endpoint:** `PUT /api/v1/extractions/by-submission/{submission_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `submission_id` | string (UUID) | Submission ID from recording workflow |

#### Request Body

Same as [PUT /extractions/{extraction_id}](#put-extractionsextraction_id)

#### Response

Same as [PUT /extractions/{extraction_id}](#put-extractionsextraction_id)

#### Notes

- Internally resolves `submission_id` to `extraction_id`
- Useful when client only has `submission_id` from recording workflow

---

## Lookup APIs

Base URL: `/api/v1/extractions`

### GET /by-submission/{submission_id}

Get extraction details from a submission_id.

**Endpoint:** `GET /api/v1/extractions/by-submission/{submission_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `submission_id` | string (UUID) | Submission ID from `/chunk` (is_last=true) response |

#### Response

```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "submission_id": "789e0123-e45b-67c8-d901-234567890abc",
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "consultation_type_code": "OP",
  "doctor_id": "3a913f3c-24d5-4c11-a968-52c8024de2db",
  "patient_id": "PAT-12345",
  "created_at": "2025-01-15T10:30:00Z",
  "found": true,
  "message": null
}
```

#### Response (Processing In Progress)

```json
{
  "extraction_id": null,
  "submission_id": "789e0123-e45b-67c8-d901-234567890abc",
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "found": false,
  "message": "Processing in progress: PROCESSING (45%). Extraction not yet available."
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `extraction_id` | string | Extraction UUID (null if not yet available) |
| `submission_id` | string | The queried submission ID |
| `session_id` | string | Recording session UUID |
| `consultation_type_code` | string | Consultation type code (e.g., `OP`) |
| `doctor_id` | string | Doctor UUID |
| `patient_id` | string | Patient ID |
| `created_at` | string | ISO timestamp of extraction creation |
| `found` | boolean | Whether extraction was found |
| `message` | string | Status message (null if found, error/progress message if not) |

#### Notes

- Use this to resolve `submission_id` to `extraction_id` for other API calls
- If `found=false` with a progress message, extraction is still processing - poll again later
- **Security:** EHR clients must have access to the submission's hospital

---

### GET /by-session/{session_id}

Get extraction details from a recording session_id (correlation_id).

**Endpoint:** `GET /api/v1/extractions/by-session/{session_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string (UUID) | Session ID (correlation_id) from `/start` response |

#### Response

Same structure as [GET /by-submission/{submission_id}](#get-by-submissionsubmission_id)

#### Notes

- Use when you have the `correlation_id` from recording start but not the `submission_id`
- **Security:** EHR clients must have access to the session's hospital

---

## Emotion Analysis APIs

Base URL: `/api/v1/extractions`

### GET /extractions/{extraction_id}/emotions

Get emotion analysis results for an extraction.

**Endpoint:** `GET /api/v1/extractions/{extraction_id}/emotions`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `extraction_id` | string (UUID) | Extraction UUID |

#### Response

```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "unified_emotions": [
    {
      "segment_code": "ANXIETY_POST_CONSULTATION",
      "segment_name": "Anxiety Post Consultation",
      "source": "combined",
      "segment_value": {
        "level": "moderate",
        "indicators": ["hesitant speech", "repeated questions"],
        "source": "combined"
      },
      "created_at": "2025-01-15T10:30:00Z"
    },
    {
      "segment_code": "TREATMENT_COMPLIANCE_LIKELIHOOD",
      "segment_name": "Treatment Compliance Likelihood",
      "source": "text_only",
      "segment_value": {
        "likelihood": "high",
        "factors": ["positive attitude", "clear understanding"],
        "source": "text_only"
      },
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "congruence_summary": {
    "overall_congruence": "aligned",
    "congruence_score": 0.85,
    "has_mismatches": false
  },
  "emotion_extraction_started": true,
  "audio_emotion_extraction_started": true,
  "congruence_analysis_started": true,
  "emotion_extraction_completed": true,
  "audio_emotion_extraction_completed": true,
  "congruence_analysis_completed": true
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `extraction_id` | string | The extraction UUID |
| `unified_emotions` | array | List of emotion segments with source indicator |
| `congruence_summary` | object | Overall text vs audio alignment assessment (null if not analyzed) |
| `emotion_extraction_started` | boolean | Whether text emotion extraction was initiated |
| `audio_emotion_extraction_started` | boolean | Whether audio emotion extraction was initiated |
| `congruence_analysis_started` | boolean | Whether congruence analysis was initiated |
| `emotion_extraction_completed` | boolean | Whether text emotion extraction is complete |
| `audio_emotion_extraction_completed` | boolean | Whether audio emotion extraction is complete |
| `congruence_analysis_completed` | boolean | Whether congruence analysis is complete |

#### Unified Emotion Segment Object

| Field | Type | Description |
|-------|------|-------------|
| `segment_code` | string | Emotion segment code (e.g., `ANXIETY_POST_CONSULTATION`) |
| `segment_name` | string | Human-readable segment name |
| `source` | string | Data source: `text_only`, `audio_only`, or `combined` |
| `segment_value` | object | Emotion analysis data |
| `created_at` | string | ISO timestamp of when segment was created |

#### Emotion Segment Codes

| Code | Description |
|------|-------------|
| `ANXIETY_POST_CONSULTATION` | Patient anxiety indicators after consultation |
| `FINANCIAL_CONCERNS` | Financial worry indicators |
| `OTHER_EMOTIONS_DETECTED` | Other emotional states detected |
| `TREATMENT_COMPLIANCE_LIKELIHOOD` | Predicted treatment adherence |
| `DOCTOR_COMMUNICATION_STYLE` | Assessment of doctor's communication |

#### Congruence Summary Object

| Field | Type | Description |
|-------|------|-------------|
| `overall_congruence` | string | Overall alignment: `aligned`, `partially_aligned`, `misaligned` |
| `congruence_score` | float | Alignment score (0.0 - 1.0) |
| `has_mismatches` | boolean | Whether text and audio emotions conflict |

#### Notes

- Returns unified emotion segments with `source` field indicating data origin
- `source` values: `text_only` (transcript analysis), `audio_only` (voice analysis), `combined` (both)
- Use `*_started` flags to detect if analysis was initiated (vs never scheduled)
- Use `*_completed` flags to show "in progress" state when started but not completed
- **Security:** EHR clients must have access to the extraction's hospital

---

### GET /extractions/by-submission/{submission_id}/emotions

Get emotion analysis results by submission_id (alternative lookup when extraction_id is not available).

**Endpoint:** `GET /api/v1/extractions/by-submission/{submission_id}/emotions`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `submission_id` | string (UUID) | Submission ID from the recording workflow |

#### Response

Same as [GET /extractions/{extraction_id}/emotions](#get-extractionsextraction_idemotions)

#### Notes

- Wrapper endpoint that resolves `submission_id` to `extraction_id` internally
- Use when `extraction_id` is not available but `submission_id` is (e.g., from recording workflow)
- Returns 404 if no extraction found for the submission (extraction may still be in progress)
- **Security:** EHR clients must have access to the submission's hospital

---

## Patient APIs

Base URL: `/api/v1/patients`

### GET /patients/search

Search for patients by name or external patient ID.

**Endpoint:** `GET /api/v1/patients/search`

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | No | - | Search term (name or patient ID) |
| `doctor_id` | string (UUID) | **Yes** | - | Doctor ID (required for EHR access) |
| `page` | int | No | `1` | Page number (1-based) |
| `page_size` | int | No | `20` | Results per page (1-100) |

#### Response

```json
{
  "patients": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "patient_id": "PAT-12345",
      "full_name": "John Doe",
      "date_of_birth": "1980-05-15",
      "gender": "male",
      "consultation_count": 5,
      "last_visit_date": "2025-01-10"
    }
  ],
  "total_count": 1,
  "page": 1,
  "page_size": 20
}
```

#### Notes

- **Changed:** Now requires `doctor_id` query parameter for EHR access control
- Returns patients with consultation counts and last visit dates
- When `doctor_id` provided, searches patients with extractions for that doctor
- **Security:** EHR clients must have access to the doctor's hospital

---

### GET /patients/{patient_id}/prescreen

Get prescreen information for a patient before consultation.

**Endpoint:** `GET /api/v1/patients/{patient_id}/prescreen`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `patient_id` | string | Patient external ID (e.g., MRN) or internal UUID |

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | string (UUID) | **Yes** | Doctor ID (prescreen data is doctor-specific) |
| `hospital_id` | string (UUID) | No | Hospital ID (optional filter) |

#### Response

```json
{
  "patient": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "patient_id": "PAT-12345",
    "full_name": "John Doe"
  },
  "prescreen_data": { ... },
  "prescreen_metadata": {
    "mode": "full",
    "segment_count": 8,
    "model": "gemini-2.5-pro"
  },
  "has_prescreen": true,
  "emotion_pattern_summary": {
    "has_emotion_data": true,
    "dominant_emotion": "neutral",
    "emotional_stability": "stable",
    "consultation_count": 3
  },
  "top_interventions": [
    {
      "intervention": "Cognitive Behavioral Therapy",
      "priority": 1,
      "rationale": "Effective for anxiety management"
    }
  ],
  "warning_factors": {
    "allergies": ["Penicillin"],
    "contraindications": ["NSAIDs"]
  },
  "warning_factors_date": "2025-01-10",
  "past_diagnosis_summary": { ... },
  "past_diagnosis_summary_date": "2025-01-10",
  "clinical_timeline": {
    "visit_count": 5,
    "timeline": [ ... ],
    "summary": { ... }
  },
  "last_prescription": { ... },
  "last_prescription_date": "2025-01-10",
  "consultation_count": 10,
  "last_visit_date": "2025-01-10"
}
```

#### Response Fields

| Field | Description | Data Source |
|-------|-------------|-------------|
| `patient` | Basic patient information | Patient registry |
| `prescreen_data` | Latest prescreen template extraction | Only from PRESCREEN template extractions |
| `has_prescreen` | Whether prescreen extraction exists | True if PRESCREEN extraction found |
| `emotion_pattern_summary` | Aggregated emotions from last 3 consultations | NON-PRESCREEN extractions only |
| `top_interventions` | Top 3 recommended interventions | Most recent NON-PRESCREEN extraction |
| `warning_factors` | CAUTION segment (allergies, contraindications) | Most recent NON-PRESCREEN extraction |
| `past_diagnosis_summary` | SUMMARY segment from last consultation | Most recent NON-PRESCREEN extraction |
| `clinical_timeline` | Last 5 visits with diagnosis/medication changes | NON-PRESCREEN extractions only |
| `last_prescription` | Most recent prescription | Most recent NON-PRESCREEN extraction |

#### PRESCREEN Template Filtering Logic

The prescreen endpoint uses two distinct data retrieval strategies:

**1. Prescreen Assessment Data (`prescreen_data`):**
- Sources data **only from PRESCREEN template extractions**
- Identified by `template_code` containing `'PRESCREEN'` (case-insensitive)
- If the latest extraction for the patient is a PRESCREEN template, `has_prescreen` is `true`
- If no PRESCREEN extraction exists, `prescreen_data` is `null` and `has_prescreen` is `false`

**2. All Other Prescreen Sections:**
- Sources data **only from NON-PRESCREEN template extractions**
- Explicitly excludes any extraction where `template_code` contains `'PRESCREEN'`
- If the latest extraction is a PRESCREEN template, these sections use the **next most recent non-PRESCREEN extraction**

| Section | Skips PRESCREEN | Rationale |
|---------|-----------------|-----------|
| `emotion_pattern_summary` | Yes | PRESCREEN extractions typically don't have emotion analysis |
| `top_interventions` | Yes | PRESCREEN extractions don't have intervention recommendations |
| `warning_factors` (CAUTION) | Yes | CAUTION segment comes from regular consultations |
| `past_diagnosis_summary` | Yes | SUMMARY segment comes from regular consultations |
| `clinical_timeline` | Yes | Timeline should show regular consultation visits only |
| `last_prescription` | Yes | PRESCREEN extractions don't contain prescriptions |

#### Notes

- `doctor_id` is **required** - prescreen data is doctor-specific
- `patient_id` can be the external patient ID (e.g., MRN) or the internal UUID
- **Security:** EHR clients must have access to the patient's hospital
- Prescreen templates are identified by `template_code` containing `'PRESCREEN'` (case-insensitive)
- All prescreen sections (except `prescreen_data`) explicitly exclude PRESCREEN template extractions

---

## Medicine List APIs

Base URL: `/api/v1/medicines`

### GET /{doctor_id}

List all medicines for a doctor.

**Endpoint:** `GET /api/v1/medicines/{doctor_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `doctor_id` | string (UUID) | Doctor's UUID |

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | string | No | Filter by category |
| `search` | string | No | Search in medicine names |

#### Response

```json
{
  "medicines": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "medicine_name": "Amlodipine 5mg",
      "common_names": ["Norvasc"],
      "category": "Antihypertensive",
      "typical_dosage": "5mg once daily",
      "form": "tablet",
      "medicine_type": "generic"
    }
  ],
  "count": 1
}
```

---

### POST /{doctor_id}

Add a single medicine to doctor's list.

**Endpoint:** `POST /api/v1/medicines/{doctor_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `doctor_id` | string (UUID) | Doctor's UUID |

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `medicine_name` | string | **Yes** | Medicine name |
| `common_names` | string[] | No | Alternative names |
| `category` | string | No | Category (e.g., Antihypertensive) |
| `typical_dosage` | string | No | Typical dosage |
| `form` | string | No | Form (tablet, syrup, etc.) |
| `snomed_code` | string | No | SNOMED CT code |
| `formulary_name` | string | No | Official formulary name |
| `medicine_type` | string | No | `'generic'` or `'branded'` |

#### Response

```json
{
  "message": "Medicine added",
  "medicine": { ... }
}
```

---

### POST /{doctor_id}/upload

Upload CSV file with medicines for a doctor.

**Endpoint:** `POST /api/v1/medicines/{doctor_id}/upload`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `doctor_id` | string (UUID) | Doctor's UUID |

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `replace_existing` | boolean | No | `false` | Replace all existing medicines |

#### Request Body

`multipart/form-data` with:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | **Yes** | CSV file (UTF-8 encoded) |

**Expected CSV Columns:** `name`, `common_name`, `category`, `typical_dosage`, `form`, `snomed_code`, `formulary_name`, `type`

#### Response

```json
{
  "message": "Upload successful",
  "created": 45,
  "updated": 5,
  "skipped": 2,
  "errors": []
}
```

#### Notes

- File must be UTF-8 encoded CSV
- `replace_existing=true` deletes all existing medicines before import
- **Security:** EHR clients must have access to the doctor's hospital

---

### POST /hospital/{hospital_id}/upload

Upload CSV file with medicines for a hospital (admin only).

**Endpoint:** `POST /api/v1/medicines/hospital/{hospital_id}/upload`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `hospital_id` | string (UUID) | Hospital's UUID |

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `created_by` | string (UUID) | **Yes** | Admin doctor ID |
| `replace_existing` | boolean | No | Replace all existing medicines |

#### Request Body

`multipart/form-data` with:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | **Yes** | CSV file (UTF-8 encoded) |

#### Response

```json
{
  "message": "Hospital upload successful",
  "created": 120,
  "updated": 10,
  "skipped": 5,
  "errors": []
}
```

#### Notes

- **Requires admin authentication**
- Hospital medicines are shared across all doctors in the hospital
- Doctors can copy hospital medicines to their personal list

---

### POST /feedback/{match_log_id}

Submit feedback for a medicine name match.

**Endpoint:** `POST /api/v1/medicines/feedback/{match_log_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `match_log_id` | string (UUID) | Medicine match log UUID |

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | string (UUID) | **Yes** | Doctor ID for EHR access verification |

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `feedback_status` | string | **Yes** | `'agreed'` or `'disagreed'` |
| `correct_medicine_id` | string (UUID) | No | Correct medicine UUID if disagreed |
| `correct_medicine_name` | string | No | Manual entry if disagreed |

#### Response

```json
{
  "message": "Feedback submitted successfully",
  "feedback_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### Notes

- If `feedback_status` is `'agreed'` and match was to hospital medicine, auto-copies to doctor's personal list
- **Security:** EHR clients must have access to the doctor's hospital

---

### POST /feedback/bulk-agree

Bulk agree with multiple medicine matches.

**Endpoint:** `POST /api/v1/medicines/feedback/bulk-agree`

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | string (UUID) | **Yes** | Doctor ID for EHR access verification |

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `match_log_ids` | string[] | **Yes** | List of match log UUIDs to agree with |

#### Response

```json
{
  "message": "Bulk feedback submitted",
  "results": [
    { "match_log_id": "...", "status": "agreed" },
    { "match_log_id": "...", "status": "agreed" }
  ]
}
```

#### Notes

- Each agreed match auto-copies hospital medicine to doctor's personal list
- **Security:** EHR clients must have access to the doctor's hospital

---

## Investigation List APIs

Base URL: `/api/v1/investigations`

### GET /{doctor_id}

List all investigations for a doctor.

**Endpoint:** `GET /api/v1/investigations/{doctor_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `doctor_id` | string (UUID) | Doctor's UUID |

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `investigation_type` | string | No | Filter by type (`laboratory`, `imaging`, `other`) |
| `category` | string | No | Filter by category |
| `search` | string | No | Search in investigation names |

#### Response

```json
{
  "investigations": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "investigation_name": "Complete Blood Count",
      "investigation_type": "laboratory",
      "common_names": ["CBC", "Full Blood Count"],
      "category": "Hematology",
      "normal_range": "WBC: 4.5-11.0 x10^9/L",
      "loinc_code": "58410-2"
    }
  ],
  "count": 1
}
```

---

### POST /{doctor_id}

Add a single investigation to doctor's list.

**Endpoint:** `POST /api/v1/investigations/{doctor_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `doctor_id` | string (UUID) | Doctor's UUID |

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `investigation_name` | string | **Yes** | Investigation name |
| `investigation_type` | string | **Yes** | Type: `laboratory`, `imaging`, or `other` |
| `common_names` | string[] | No | Alternative names (e.g., CBC for Complete Blood Count) |
| `category` | string | No | Category (e.g., Hematology, Radiology) |
| `normal_range` | string | No | Normal range for lab tests |
| `loinc_code` | string | No | LOINC code for lab tests |
| `cpt_code` | string | No | CPT code for procedures |

#### Response

```json
{
  "message": "Investigation added",
  "investigation": { ... }
}
```

---

### POST /{doctor_id}/upload

Upload CSV file with investigations for a doctor.

**Endpoint:** `POST /api/v1/investigations/{doctor_id}/upload`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `doctor_id` | string (UUID) | Doctor's UUID |

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `replace_existing` | boolean | No | `false` | Replace all existing investigations |

#### Request Body

`multipart/form-data` with:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | **Yes** | CSV file (UTF-8 encoded) |

**Expected CSV Columns:** `name`, `common_names`, `type`, `category`, `normal_range`, `loinc_code`, `cpt_code`

#### Response

```json
{
  "message": "Upload successful",
  "created": 30,
  "updated": 3,
  "skipped": 1,
  "errors": []
}
```

#### Notes

- File must be UTF-8 encoded CSV
- `replace_existing=true` deletes all existing investigations before import
- **Security:** EHR clients must have access to the doctor's hospital

---

### POST /hospital/{hospital_id}/upload

Upload CSV file with investigations for a hospital (admin only).

**Endpoint:** `POST /api/v1/investigations/hospital/{hospital_id}/upload`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `hospital_id` | string (UUID) | Hospital's UUID |

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `created_by` | string (UUID) | **Yes** | Admin doctor ID |
| `replace_existing` | boolean | No | Replace all existing investigations |

#### Request Body

`multipart/form-data` with:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | **Yes** | CSV file (UTF-8 encoded) |

#### Response

```json
{
  "message": "Hospital upload successful",
  "created": 80,
  "updated": 5,
  "skipped": 2,
  "errors": []
}
```

#### Notes

- **Requires admin authentication**
- Hospital investigations are shared across all doctors in the hospital
- Doctors can copy hospital investigations to their personal list

---

## Template Sharing APIs

Base URL: `/api/v1/doctor-templates`

### POST /share

Share a template with individual doctors.

**Endpoint:** `POST /api/v1/doctor-templates/share`

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sharing_doctor_id` | string (UUID) | **Yes** | Doctor UUID who is sharing (must own the template) |
| `template_id` | string (UUID) | **Yes** | Template ID to share |
| `doctor_ids` | string[] | **Yes** | List of doctor UUIDs to share with (min 1) |
| `access_level` | enum | No | `'view'` (read-only) or `'use'` (can apply). Default: `'use'` |
| `new_owner_id` | string (UUID) | No | If provided, assigns ownership of global template to this doctor first |

#### Response

```json
{
  "success": true,
  "shared_count": 2,
  "failed": [],
  "ownership_assigned": null
}
```

#### Notes

- **Security:** Uses `sharing_doctor_id` in request body for EHR access validation
- Sharing doctor must own the template (or use `new_owner_id` for global templates)
- `new_owner_id` converts global template to doctor-owned before sharing
- **EHR clients:** `sharing_doctor_id` must belong to the EHR's hospital

---

### POST /share-hospital

Share a template with all doctors in a hospital.

**Endpoint:** `POST /api/v1/doctor-templates/share-hospital`

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sharing_doctor_id` | string (UUID) | **Yes** | Doctor UUID who is sharing (must own the template) |
| `template_id` | string (UUID) | **Yes** | Template ID to share |
| `hospital_id` | string (UUID) | **Yes** | Hospital UUID |
| `access_level` | enum | No | `'view'` or `'use'`. Default: `'use'` |
| `new_owner_id` | string (UUID) | No | If provided, assigns ownership of global template to this doctor first |

#### Response

```json
{
  "success": true,
  "shared_count": 15,
  "hospital_id": "550e8400-e29b-41d4-a716-446655440000",
  "ownership_assigned": null
}
```

#### Notes

- **Security:** Uses `sharing_doctor_id` in request body for EHR access validation
- Shares with all doctors registered to the specified hospital
- Skips doctors who already have access to the template
- **EHR clients:** `sharing_doctor_id` must belong to the EHR's hospital

---

### POST /share-specialization

Share a template with all doctors of a specialization.

**Endpoint:** `POST /api/v1/doctor-templates/share-specialization`

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sharing_doctor_id` | string (UUID) | **Yes** | Doctor UUID who is sharing (must own the template) |
| `template_id` | string (UUID) | **Yes** | Template ID to share |
| `specialization` | string | **Yes** | Specialization name (e.g., `'Cardiology'`, `'Psychiatry'`) |
| `access_level` | enum | No | `'view'` or `'use'`. Default: `'use'` |
| `new_owner_id` | string (UUID) | No | If provided, assigns ownership of global template to this doctor first |

#### Response

```json
{
  "success": true,
  "shared_count": 8,
  "specialization": "Cardiology",
  "ownership_assigned": null
}
```

#### Notes

- **Security:** Uses `sharing_doctor_id` in request body for EHR access validation
- Shares with all doctors who have the specified specialization
- Skips doctors who already have access to the template
- **EHR clients:** `sharing_doctor_id` must belong to the EHR's hospital

---

## Workflow Summary

### Chunked Recording Flow (VHR Screen - Mic/File Upload)

```
1. POST /start
   └─> Returns: correlation_id

2. POST /chunk (multiple times)
   └─> chunk_index: 0, 1, 2, ...
   └─> is_last: false

3. POST /chunk (final)
   └─> is_last: true
   └─> Returns: submissionId
   └─> Triggers: Background processing (transcription + extraction)

4. Poll for status OR receive webhook
   └─> GET /status/{submissionId} - Poll until COMPLETED
   └─> OR configure webhook to receive results automatically
   └─> Receive: Progress updates, final transcript + extraction

5. PUT /extractions/{extraction_id} (optional)
   └─> Doctor edits and saves
```

### Live Recording Flow (WebSocket)

```
1. POST /live/session
   └─> Returns: correlation_id (= submission_id for live sessions)

2. WebSocket transcription (client-side)
   └─> Real-time transcript via live transcription API

3. POST /extract
   └─> submission_id: from step 1
   └─> transcript: from step 2
   └─> Returns: Extracted medical data

4. PUT /extractions/{extraction_id} (optional)
   └─> Doctor edits and saves
```

---

## Triage APIs

Base URL: `/api/v1/triage`

Clinical triage suggestion APIs for generating differential diagnosis recommendations, red flag identification, and gap analysis.

### POST /generate

Generate or retrieve clinical triage suggestions for an extraction.

**Endpoint:** `POST /api/v1/triage/generate`

#### Request Body

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `extraction_id` | string (UUID) | **Yes** | - | UUID of the medical extraction |
| `include_gemini` | boolean | No | `true` | Whether to use Gemini AI for gap analysis |
| `patient_id` | string (UUID) | No | - | Patient UUID for historical context (auto-detected if not provided) |
| `doctor_id` | string (UUID) | No | - | Doctor UUID for suggestion logging |
| `log_suggestions` | boolean | No | `true` | Whether to log suggestions to database for learning |
| `force_regenerate` | boolean | No | `false` | Force regenerate suggestions even if they exist in DB |

#### Response

```json
{
  "success": true,
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "specialty": "Internal Medicine",
  "consultation_type": "OP",
  "critical_actions": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "category": "red_flag",
      "suggestion": "Rule out MI - consider troponin and ECG",
      "priority": "critical",
      "rationale": "Chest pain with diaphoresis warrants cardiac workup",
      "source": "differential_tree",
      "related_presentation": "chest_pain"
    }
  ],
  "important_considerations": [...],
  "nice_to_have": [...],
  "matched_presentations": ["chest_pain", "dyspnea"],
  "identified_red_flags": ["diaphoresis", "radiation to arm"],
  "gap_analysis": {
    "missing_investigations": ["troponin", "ECG"],
    "missing_history": ["family cardiac history"],
    "recommendations": [...]
  },
  "total_suggestions": 8,
  "generated_at": "2025-01-15T10:30:00Z",
  "model_used": "gemini-2.0-flash-001",
  "processing_time_ms": 1250
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `specialty` | string | Detected specialty (e.g., Internal Medicine, Cardiology) |
| `consultation_type` | string | Consultation type code |
| `critical_actions` | array | Red flags and immediate concerns (highest priority) |
| `important_considerations` | array | Missing investigations, history gaps |
| `nice_to_have` | array | Additional workup suggestions |
| `matched_presentations` | array | Clinical presentations matched from differential trees |
| `identified_red_flags` | array | Red flags identified in the extraction |
| `gap_analysis` | object | AI-generated gap analysis (missing investigations, history, recommendations) |

#### Notes

- First checks if suggestions exist in database; returns cached if available
- Uses `force_regenerate=true` to bypass cache
- Patient historical context (allergies, chronic conditions, emotions) is used to personalize suggestions
- Allergy-based filtering automatically vetoes contraindicated suggestions
- **Prerequisite:** Triage analysis must be enabled for the consultation type

---

### POST /feedback

Submit feedback on a triage suggestion for learning doctor patterns.

**Endpoint:** `POST /api/v1/triage/feedback`

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `suggestion_id` | string (UUID) | **Yes** | UUID of the suggestion from `triage_suggestion_log` |
| `doctor_id` | string (UUID) | **Yes** | UUID of the doctor providing feedback |
| `feedback_type` | string | **Yes** | Type: `'accepted'`, `'rejected'`, `'maybe'`, or `'modified'` |
| `rejection_reason` | string | No | Reason for rejection (if `feedback_type='rejected'`) |
| `modified_text` | string | No | Modified suggestion text (required if `feedback_type='modified'`) |

#### Response

```json
{
  "success": true,
  "feedback_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Feedback 'accepted' recorded successfully"
}
```

#### Notes

- Feedback is used to learn doctor patterns for future personalization
- `modified_text` is required when `feedback_type='modified'`

---

### GET /feedback/stats/{doctor_id}

Get feedback statistics for a specific doctor.

**Endpoint:** `GET /api/v1/triage/feedback/stats/{doctor_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `doctor_id` | string (UUID) | Doctor's UUID |

#### Response

```json
{
  "doctor_id": "3a913f3c-24d5-4c11-a968-52c8024de2db",
  "total_suggestions": 150,
  "total_feedback_given": 120,
  "accepted_count": 85,
  "rejected_count": 25,
  "modified_count": 10,
  "acceptance_rate_pct": 70.8
}
```

---

### GET /differentials/{specialty}/{presentation}

Get differential diagnosis tree data for a specific specialty and presentation.

**Endpoint:** `GET /api/v1/triage/differentials/{specialty}/{presentation}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `specialty` | string | Specialty name (e.g., `internal_medicine`, `cardiology`) |
| `presentation` | string | Clinical presentation (e.g., `chest_pain`, `dyspnea`) |

#### Response

```json
{
  "specialty": "internal_medicine",
  "presentation": "chest_pain",
  "must_rule_out": [
    {
      "condition": "Acute Coronary Syndrome",
      "investigations": ["troponin", "ECG", "CXR"],
      "clinical_features": ["crushing pain", "radiation to arm", "diaphoresis"]
    }
  ],
  "must_assess": [...],
  "high_probability": [...],
  "red_flags": ["diaphoresis", "radiation to jaw/arm", "syncope"],
  "first_line_investigations": [
    {"name": "ECG", "rationale": "Identify ST changes"},
    {"name": "Troponin", "rationale": "Cardiac biomarker"}
  ],
  "history_essentials": ["onset", "character", "radiation", "associated symptoms"],
  "source": "hardcoded_v1"
}
```

---

### GET /specialties

List all available specialties with their presentations and consultation types.

**Endpoint:** `GET /api/v1/triage/specialties`

#### Response

```json
[
  {
    "specialty": "internal_medicine",
    "presentations": ["chest_pain", "dyspnea", "abdominal_pain", "fever"],
    "consultation_types": ["OP", "OP_SHORT"]
  },
  {
    "specialty": "cardiology",
    "presentations": ["chest_pain", "palpitations", "syncope"],
    "consultation_types": ["CARDIO_OP"]
  }
]
```

---

### GET /presentations/{specialty}

List all available presentations for a specialty.

**Endpoint:** `GET /api/v1/triage/presentations/{specialty}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `specialty` | string | Specialty name |

#### Response

```json
["chest_pain", "dyspnea", "abdominal_pain", "fever", "fatigue"]
```

---

## Intervention APIs

Base URL: `/api/v1/extractions`

Patient intervention APIs for generating actionable recommendations based on consultation insights analysis.

### GET /{extraction_id}/interventions

Get patient interventions for an extraction.

**Endpoint:** `GET /api/v1/extractions/{extraction_id}/interventions`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `extraction_id` | string (UUID) | Extraction UUID |

#### Response

```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "interventions": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "code": "PHYSIOTHERAPY_REFERRAL",
      "name": "Physiotherapy Referral",
      "description": "Patient may benefit from physiotherapy services",
      "category": "REVENUE",
      "priority": "high",
      "priority_score": 85,
      "trigger_reason": "Musculoskeletal condition with confirmed diagnosis",
      "is_top_3": true,
      "analysis_mode": "insights",
      "intervention_sub_type": "allied_health",
      "action": "Refer to physiotherapy department",
      "revenue_estimate": 1500,
      "rationale_sources": {
        "allied_health_needs": {
          "is_physiotherapy": true,
          "physiotherapy_reasons": ["Musculoskeletal condition present", "Physiotherapy explicitly mentioned"]
        },
        "take_up_prediction": {
          "likelihood": 72,
          "signals": {"has_chronic_condition": 15, "high_compliance": 20},
          "rules_applied": ["base_likelihood", "chronic_boost"]
        }
      },
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "summary": {
    "total": 8,
    "by_category": {
      "REVENUE": 4,
      "RETENTION": 3,
      "QUALITY": 1
    },
    "revenue_potential": 5500,
    "has_critical": false
  },
  "insights_enabled": true
}
```

#### Response Fields

**Intervention Object:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Intervention UUID |
| `code` | string | Intervention code (e.g., `PHYSIOTHERAPY_REFERRAL`) |
| `name` | string | Human-readable name |
| `description` | string | Intervention description |
| `category` | string | Category: `REVENUE`, `RETENTION`, or `QUALITY` |
| `priority` | string | Priority level: `critical`, `high`, `medium`, `low` |
| `priority_score` | int | Numeric priority score (0-100) |
| `trigger_reason` | string | Why this intervention was triggered |
| `is_top_3` | boolean | Whether this is a top-3 priority intervention |
| `analysis_mode` | string | Analysis mode: `insights` or `legacy` |
| `intervention_sub_type` | string | Sub-type: `allied_health`, `clinical_upsell`, `diagnostic`, etc. |
| `action` | string | Recommended action text |
| `revenue_estimate` | float | Revenue potential in INR (for REVENUE category) |
| `rationale_sources` | object | Evidence and signals that triggered this intervention |

**Category Descriptions:**

| Category | Description | Sub-types |
|----------|-------------|-----------|
| `REVENUE` | Allied health referrals, clinical upsells, diagnostics | `allied_health`, `clinical_upsell`, `diagnostic` |
| `RETENTION` | Dropoff prevention, compliance support, satisfaction recovery | `dropoff_prevention`, `compliance_support`, `satisfaction_recovery` |
| `QUALITY` | Medication safety, documentation gaps, follow-up quality | `medication_safety`, `documentation`, `follow_up_quality` |

**Summary Object:**

| Field | Type | Description |
|-------|------|-------------|
| `total` | int | Total intervention count |
| `by_category` | object | Count by category (REVENUE, RETENTION, QUALITY) |
| `revenue_potential` | float | Total revenue potential in INR |
| `has_critical` | boolean | Whether any intervention has critical priority |

#### Notes

- Interventions are generated automatically during extraction processing when consultation insights is enabled
- **Prerequisite:** Consultation insights must be enabled for the consultation type
- **Security:** EHR clients must have access to the extraction's hospital

---

## Doctor Management APIs

Base URL: `/api/v1/doctors`

### POST /doctors/ehr

Create a new doctor for EHR integration with auto-generated UUID.

**Endpoint:** `POST /api/v1/doctors/ehr`

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `hospital_code` | string | **Yes** | Hospital code to lookup hospital_id (1-50 chars) |
| `full_name` | string | **Yes** | Doctor's full name (2-255 chars) |
| `email` | string | **Yes** | Doctor's email address (must be unique) |
| `specialization` | string | No | Medical specialization (max 100 chars) |

#### Example Request

```json
{
  "hospital_code": "HOSP001",
  "full_name": "Dr. John Smith",
  "email": "john.smith@hospital.com",
  "specialization": "Cardiology"
}
```

#### Response

```json
{
  "success": true,
  "message": "Doctor 'Dr. John Smith' created successfully",
  "doctor_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### Error Responses

| Status | Description |
|--------|-------------|
| 404 | Hospital with given code not found |
| 409 | Doctor with email already exists |
| 500 | Failed to create doctor |

#### Notes

- UUID is auto-generated (unlike `POST /doctors/with-hospital` which accepts caller-provided UUID)
- Hospital lookup is performed using `hospital_code` field
- Email uniqueness is enforced

---

## EHR Integration APIs (Sanitized)

Base URL: `/api/v1/ehr`

These endpoints are sanitized wrappers designed for external EHR system consumption. They exclude internal/sensitive metadata such as:
- Processing time metrics (stitching_time, transcription_time, etc.)
- Model information (gemini-2.5-pro, etc.)
- Internal processing flags
- Full transcripts
- Segment counts and validation details

### GET /ehr/status/{submission_id}

Get processing status for EHR clients (sanitized version of `/status/{submission_id}`).

**Endpoint:** `GET /api/v1/ehr/status/{submission_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `submission_id` | string (UUID) | Submission ID from `/chunk` (is_last=true) response |

#### Response

```json
{
  "submission_id": "789e0123-e45b-67c8-d901-234567890abc",
  "status": "COMPLETED",
  "progress": 100,
  "message": "Extraction complete",
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "insights": {
    "chief_complaints": { ... },
    "diagnosis": { ... },
    "prescription": { ... }
  }
}
```

#### Excluded Fields (vs standard endpoint)

| Excluded Field | Reason |
|----------------|--------|
| `transcript` | Full transcript is internal data |
| `metrics.stitching_time` | Internal processing metric |
| `metrics.transcription_time` | Internal processing metric |
| `metrics.extraction_time` | Internal processing metric |
| `metrics.total_time` | Internal processing metric |

---

### POST /ehr/extract

Extract medical summary for EHR clients (sanitized version of `/extract`).

**Endpoint:** `POST /api/v1/ehr/extract`

#### Request Body

Same as [POST /extract](#post-extract)

#### Response

```json
{
  "success": true,
  "insights": {
    "chief_complaints": { ... },
    "diagnosis": { ... },
    "prescription": { ... }
  },
  "metadata": {
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
    "submission_id": "789e0123-e45b-67c8-d901-234567890abc",
    "extraction_id": "123e4567-e89b-12d3-a456-426614174000",
    "doctor_id": "3a913f3c-24d5-4c11-a968-52c8024de2db",
    "patient_id": "PAT-12345",
    "template_code": "OP_GENERAL",
    "timestamp": "2025-01-15T10:30:00Z"
  }
}
```

#### Excluded Fields (vs standard endpoint)

| Excluded Field | Reason |
|----------------|--------|
| `metadata.segment_count` | Internal processing detail |
| `metadata.processing_mode` | Internal processing detail |
| `metadata.model` | Internal model information |
| `metadata.validation` | Internal validation details |

---

### GET /ehr/merge/status/{extraction_id}

Get merge status for EHR clients (sanitized version of `/merge/status/{extraction_id}`).

**Endpoint:** `GET /api/v1/ehr/merge/status/{extraction_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `extraction_id` | string (UUID) | Extraction ID from `/merge` response |

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | string (UUID) | **Yes** | Doctor ID for access verification |

#### Response

```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440003",
  "status": "completed",
  "merged_data": { ... },
  "merge_metadata": {
    "source_count": 2,
    "target_template_code": "OP_GENERAL",
    "cross_type_scenario": "SAME_TYPE",
    "consultation_types_merged": ["OP"]
  }
}
```

#### Excluded Fields (vs standard endpoint)

| Excluded Field | Reason |
|----------------|--------|
| `merge_metadata.conflict_count` | Internal merge detail |
| `merge_metadata.conflicts_resolved` | Internal merge detail |
| `merge_metadata.merge_timestamp` | Internal timestamp |
| `created_at` | Internal timestamp |
| `completed_at` | Internal timestamp |

---

### POST /ehr/merge/preview

Preview merge for EHR clients (sanitized version of `/merge/preview`).

**Endpoint:** `POST /api/v1/ehr/merge/preview`

#### Request Body

Same as [POST /merge/preview](#post-mergepreview)

#### Response

```json
{
  "success": true,
  "merged_data": { ... },
  "merge_metadata": {
    "source_count": 2,
    "target_template_code": "OP_GENERAL",
    "cross_type_scenario": "SAME_TYPE",
    "consultation_types_merged": ["OP"]
  },
  "preview": true
}
```

#### Excluded Fields (vs standard endpoint)

| Excluded Field | Reason |
|----------------|--------|
| `merge_metadata.conflict_count` | Internal merge detail |
| `merge_metadata.conflicts_resolved` | Internal merge detail |
| `merge_metadata.merge_timestamp` | Internal timestamp |

---

### GET /ehr/extractions/{extraction_id}/emotions

Get emotion analysis for EHR clients (sanitized version of `/extractions/{extraction_id}/emotions`).

**Endpoint:** `GET /api/v1/ehr/extractions/{extraction_id}/emotions`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `extraction_id` | string (UUID) | Extraction UUID |

#### Response

```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "unified_emotions": [
    {
      "segment_code": "ANXIETY_POST_CONSULTATION",
      "segment_name": "Anxiety Post Consultation",
      "source": "combined",
      "segment_value": {
        "level": "moderate",
        "indicators": ["hesitant speech", "repeated questions"]
      }
    }
  ],
  "congruence_summary": {
    "overall_congruence": "aligned",
    "congruence_score": 0.85,
    "has_mismatches": false
  }
}
```

#### Excluded Fields (vs standard endpoint)

| Excluded Field | Reason |
|----------------|--------|
| `emotion_extraction_started` | Internal processing flag |
| `emotion_extraction_completed` | Internal processing flag |
| `audio_emotion_extraction_started` | Internal processing flag |
| `audio_emotion_extraction_completed` | Internal processing flag |
| `congruence_analysis_started` | Internal processing flag |
| `congruence_analysis_completed` | Internal processing flag |
| `segment_value.created_at` | Internal timestamp |

---

### GET /ehr/extractions/by-submission/{submission_id}/emotions

Get emotion analysis by submission_id for EHR clients.

**Endpoint:** `GET /api/v1/ehr/extractions/by-submission/{submission_id}/emotions`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `submission_id` | string (UUID) | Submission ID from recording workflow |

#### Response

Same as [GET /ehr/extractions/{extraction_id}/emotions](#get-ehrextractionsextraction_idemotions)

---

### GET /ehr/patients/{patient_id}/prescreen

Get prescreen information for EHR clients (sanitized version of `/patients/{patient_id}/prescreen`).

**Endpoint:** `GET /api/v1/ehr/patients/{patient_id}/prescreen`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `patient_id` | string | Patient external ID (e.g., MRN) or internal UUID |

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | string (UUID) | **Yes** | Doctor ID (prescreen data is doctor-specific) |
| `hospital_id` | string (UUID) | No | Hospital ID (optional filter) |

#### Response

```json
{
  "patient": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "patient_id": "PAT-12345",
    "full_name": "John Doe"
  },
  "prescreen_data": { ... },
  "has_prescreen": true,
  "emotion_pattern_summary": {
    "has_emotion_data": true,
    "dominant_emotion": "neutral",
    "emotional_stability": "stable",
    "consultation_count": 3
  },
  "top_interventions": [
    {
      "intervention": "Cognitive Behavioral Therapy",
      "priority": 1,
      "rationale": "Effective for anxiety management"
    }
  ],
  "warning_factors": {
    "allergies": ["Penicillin"],
    "contraindications": ["NSAIDs"]
  },
  "warning_factors_date": "2025-01-10",
  "past_diagnosis_summary": { ... },
  "past_diagnosis_summary_date": "2025-01-10",
  "clinical_timeline": { ... },
  "last_prescription": { ... },
  "last_prescription_date": "2025-01-10",
  "consultation_count": 10,
  "last_visit_date": "2025-01-10"
}
```

#### Excluded Fields (vs standard endpoint)

| Excluded Field | Reason |
|----------------|--------|
| `prescreen_metadata.mode` | Internal processing detail |
| `prescreen_metadata.segment_count` | Internal processing detail |
| `prescreen_metadata.model` | Internal model information |

---

## Aosta EHR Integration APIs

Base URL: `/api/v1`

These endpoints are specifically designed for Aosta EHR integration. They include additional metadata fields and provide a complete workflow for recording, status checking, and syncing edited extractions back to Aosta's backend.

### POST /start (with recording_metadata)

Start a new recording session with Aosta-specific metadata.

**Endpoint:** `POST /api/v1/option1/recording/start`

This is the standard `/start` endpoint with an additional `recording_metadata` parameter for Aosta integration.

#### Request Body

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `doctor_id` | string (UUID) | **Yes** | - | Doctor's UUID |
| `patient_id` | string | **Yes** | - | Patient identifier (external ID like MRN) |
| `template_code` | string | **Yes** | - | Template code (use `AOSTA_OP` for Aosta) |
| `template_name` | string | No | - | Template display name |
| `processing_mode` | string | No | `"default"` | Processing mode |
| `extraction_mode` | string | No | `"full"` | Extraction mode |
| `recording_metadata` | object | No | - | **Aosta-specific metadata** (see below) |

#### recording_metadata Object

| Field | Type | Description |
|-------|------|-------------|
| `ip_id` | string | Inpatient visit/admission ID from Aosta |
| `op_id` | string | Outpatient visit ID from Aosta |
| `patient_info` | object | Additional patient information |
| `doctor_info` | object | Additional doctor information |
| *(custom fields)* | any | Any additional metadata needed |

#### Example Request

```json
{
  "doctor_id": "83b3eb65-6801-4bc5-b565-dd3dee2be70a",
  "patient_id": "PAT-12345",
  "template_code": "AOSTA_OP",
  "processing_mode": "default",
  "extraction_mode": "full",
  "recording_metadata": {
    "ip_id": "979043",
    "op_id": "0",
    "patient_info": {
      "reg_number": "REG123456"
    }
  }
}
```

#### Response

```json
{
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "message": "Recording session started successfully"
}
```

#### Notes

- `recording_metadata` is stored in `recording_sessions.recording_metadata_json` column
- When patient is created, `ip_id` and `op_id` are extracted and stored in `patients` table
- Metadata is copied to `medical_extractions.recording_metadata_json` for retrieval via status API
- **Backward Compatible:** `recording_metadata` is optional; existing clients are unaffected

---

### GET /ehr/iframe/status/{submission_id}

Get processing status for Aosta EHR integration with recording_metadata.

**Endpoint:** `GET /api/v1/ehr/iframe/status/{submission_id}`

This extends the standard `/ehr/status` endpoint by including the `recording_metadata` from the original `/start` request.

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `submission_id` | string (UUID) | Submission ID from `/chunk` (is_last=true) response |

#### Response

```json
{
  "submission_id": "789e0123-e45b-67c8-d901-234567890abc",
  "status": "COMPLETED",
  "progress": 100,
  "message": "Extraction complete",
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "insights": {
    "history": {
      "PastMedicalHistory": "Hypertension, Diabetes",
      "PresentMedicalHistory": "Chest pain for 2 days",
      "SurgicalHistory": "Appendectomy 2010",
      "SocialHistory": "Non-smoker",
      "FamilyHistory": "Father had MI"
    },
    "chiefComplaints": ["Chest pain", "Shortness of breath"],
    "allergies": "Penicillin",
    "diagnosis": [
      {"code": "I25.1", "name": "Atherosclerotic heart disease", "type": "Primary"}
    ],
    "prescription": [
      {
        "name": "Aspirin 75mg",
        "morning_qty": "1",
        "noon_qty": "0",
        "evening_qty": "0",
        "night_qty": "0",
        "durationDays": "30",
        "timeToTake": "after food",
        "remarks": ""
      }
    ],
    "treatmentPlan": "Medical management with lifestyle modification",
    "followUp": {
      "review_date": "2 weeks",
      "special_instructions": "Monitor BP daily"
    }
  },
  "recording_metadata": {
    "ip_id": "979043",
    "op_id": "0",
    "patient_info": {
      "reg_number": "REG123456"
    }
  }
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `submission_id` | string | The submission ID |
| `status` | string | Processing status: `PENDING`, `PROCESSING`, `COMPLETED`, `ERROR` |
| `progress` | int | Progress percentage (0-100) |
| `message` | string | Human-readable status message |
| `extraction_id` | string | Extraction UUID (only when `status=COMPLETED`) |
| `insights` | object | Extracted medical data following AOSTA_OP template schema |
| `recording_metadata` | object | **Aosta-specific:** Original metadata from `/start` request |

#### Notes

- Returns `recording_metadata` passed during the `/start` API call
- Use this to retrieve `ip_id`, `op_id` and other metadata for syncing back to Aosta
- **Security:** EHR clients must have access to the submission's hospital

---

### PUT /ehr/iframe/edit/{submission_id}

Update extraction and sync to Aosta's backend.

**Endpoint:** `PUT /api/v1/ehr/iframe/edit/{submission_id}`

This endpoint:
1. Saves edited extraction to our database (if `edited_data` provided)
2. Retrieves extraction insights (edited or original)
3. Formats data to Aosta's expected schema
4. Sends formatted data to Aosta's backend endpoint

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `submission_id` | string (UUID) | Submission ID from recording workflow |

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `edited_data` | object | No | Edited extraction insights (if null, uses original/existing edits) |
| `edited_by` | string (UUID) | **Yes** | Doctor or nurse UUID who made edits |
| `edited_by_type` | string | No | `"doctor"` or `"nurse"` (default: `"doctor"`) |
| `recording_metadata` | object | No | Override metadata (uses stored metadata if not provided) |

#### Example Request

```json
{
  "edited_data": {
    "history": {
      "PastMedicalHistory": "Hypertension, Diabetes Type 2",
      "PresentMedicalHistory": "Chest pain for 2 days, worse on exertion",
      "SurgicalHistory": "Appendectomy 2010",
      "SocialHistory": "Non-smoker, occasional alcohol",
      "FamilyHistory": "Father had MI at age 55"
    },
    "chiefComplaints": ["Chest pain", "Shortness of breath on exertion"],
    "allergies": "Penicillin, Sulfa drugs",
    "diagnosis": [
      {"code": "I25.1", "name": "Atherosclerotic heart disease", "type": "Primary"},
      {"code": "I10", "name": "Essential hypertension", "type": "Secondary"}
    ],
    "prescription": [
      {
        "name": "Aspirin 75mg",
        "morning_qty": "1",
        "noon_qty": "0",
        "evening_qty": "0",
        "night_qty": "0",
        "durationDays": "30",
        "timeToTake": "after food",
        "remarks": ""
      },
      {
        "name": "Atorvastatin 20mg",
        "morning_qty": "0",
        "noon_qty": "0",
        "evening_qty": "0",
        "night_qty": "1",
        "durationDays": "30",
        "timeToTake": "after dinner",
        "remarks": ""
      }
    ],
    "treatmentPlan": "Medical management with lifestyle modification. Start cardiac rehab.",
    "followUp": {
      "review_date": "2 weeks",
      "special_instructions": "Monitor BP daily, report any chest pain"
    }
  },
  "edited_by": "83b3eb65-6801-4bc5-b565-dd3dee2be70a",
  "edited_by_type": "doctor",
  "recording_metadata": {
    "ip_id": "979043",
    "op_id": "0"
  }
}
```

#### Response

```json
{
  "success": true,
  "message": "Extraction updated and synced to Aosta",
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "edit_count": 2,
  "aosta_sync_status": "success",
  "aosta_error": null
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Whether the DB update succeeded |
| `message` | string | Human-readable status message |
| `extraction_id` | string | Extraction UUID |
| `edit_count` | int | Total number of edits made to this extraction |
| `aosta_sync_status` | string | Sync result: `"success"`, `"failed"`, or `"skipped"` |
| `aosta_error` | string | Error message if sync failed (null otherwise) |

#### Partial Success Pattern

This endpoint uses a **partial success pattern**:
- Returns `success: true` if the database update succeeds, even if Aosta sync fails
- Check `aosta_sync_status` for the sync result
- If `aosta_sync_status: "failed"`, the `aosta_error` field contains the error message

```json
{
  "success": true,
  "message": "Extraction updated but Aosta sync failed",
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "edit_count": 2,
  "aosta_sync_status": "failed",
  "aosta_error": "Connection timeout"
}
```

#### Aosta Payload Format

The endpoint formats extraction insights to Aosta's expected schema:

| Aosta Field | Source | Description |
|-------------|--------|-------------|
| `RegNumber` | `patients.patient_id` | Patient external ID |
| `Ipid` | `recording_metadata.ip_id` | Inpatient visit ID |
| `Opid` | `recording_metadata.op_id` | Outpatient visit ID |
| `PractitionerId` | `doctors.id` | Doctor UUID |
| `HospitalId` | `hospitals.hospital_code` | Hospital code |
| `PastMedicalHistory` | `insights.history.PastMedicalHistory` | Past medical history |
| `PresentMedicalHistory` | `insights.history.PresentMedicalHistory` | Present illness |
| `SurgicalHistory` | `insights.history.SurgicalHistory` | Surgical history |
| `SocialHistory` | `insights.history.SocialHistory` | Social history |
| `FamilyHistory` | `insights.history.FamilyHistory` | Family history |
| `ChiefComplaints` | `insights.chiefComplaints` | Array of complaints |
| `Allergies` | `insights.allergies` | Allergy string |
| `Diagnosis` | `insights.diagnosis` | Array of diagnosis objects |
| `TreatmentPlan` | `insights.treatmentPlan` | Treatment plan |
| `Medicines` | `insights.prescription` | Array of prescription objects |
| `DoctorInstruction` | `insights.followUp.special_instructions` | Follow-up instructions |

#### Environment Configuration

```bash
# Aosta API endpoint
AOSTA_API_URL=https://bbavav2.aostasoftware.com/api/v2/save

# Aosta API key (provided by Aosta)
AOSTA_OUTBOUND_API_KEY=your_aosta_api_key_here
```

#### Notes

- **Security:** EHR clients must have access to the submission's hospital
- If `edited_data` is null, uses existing edits or original extraction
- If `recording_metadata` is null, uses stored metadata from the recording session
- `aosta_sync_status: "skipped"` means `AOSTA_OUTBOUND_API_KEY` is not configured
- Sync uses 30-second timeout for Aosta API calls

---

## Changelog

### January 2025 - Doctor Management APIs

#### New Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/doctors/ehr` | Create doctor with auto-generated UUID using hospital_code lookup |

#### Purpose

EHR integration endpoint for creating doctor records without needing to provide a UUID. The hospital is looked up by `hospital_code` instead of requiring `hospital_id`.

---

### December 2024 - Aosta EHR Integration APIs

#### New Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/option1/recording/start` | Added `recording_metadata` parameter for Aosta metadata |
| `GET /api/v1/ehr/iframe/status/{submission_id}` | Status endpoint with `recording_metadata` in response |
| `PUT /api/v1/ehr/iframe/edit/{submission_id}` | Edit + sync wrapper to send data to Aosta backend |

#### New Database Columns

| Table | Column | Type | Description |
|-------|--------|------|-------------|
| `recording_sessions` | `recording_metadata_json` | JSONB | Stores metadata from `/start` API |
| `medical_extractions` | `recording_metadata_json` | JSONB | Copy of metadata for status retrieval |
| `patients` | `ip_id` | VARCHAR(255) | Inpatient visit ID from Aosta |
| `patients` | `op_id` | VARCHAR(255) | Outpatient visit ID from Aosta |

#### Environment Variables

| Variable | Description |
|----------|-------------|
| `AOSTA_API_URL` | Aosta API endpoint (default: `https://bbavav2.aostasoftware.com/api/v2/save`) |
| `AOSTA_OUTBOUND_API_KEY` | Bearer token for Aosta API authentication |

#### New Files

| File | Description |
|------|-------------|
| `/backend/services/aosta_service.py` | Formatter and API client for Aosta integration |

---

### December 2024 - EHR Integration APIs

#### New Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/ehr/status/{submission_id}` | Sanitized processing status (excludes transcript, metrics) |
| `POST /api/v1/ehr/extract` | Sanitized extraction (excludes segment_count, model) |
| `GET /api/v1/ehr/merge/status/{extraction_id}` | Sanitized merge status (excludes conflict details) |
| `POST /api/v1/ehr/merge/preview` | Sanitized merge preview |
| `GET /api/v1/ehr/extractions/{id}/emotions` | Sanitized emotions (excludes processing flags) |
| `GET /api/v1/ehr/extractions/by-submission/{id}/emotions` | Sanitized emotions by submission |
| `GET /api/v1/ehr/patients/{patient_id}/prescreen` | Sanitized prescreen (excludes model metadata) |

#### Purpose

These wrapper endpoints are designed for external EHR system consumption. They exclude internal/sensitive metadata:
- Processing time metrics (stitching_time, transcription_time, etc.)
- Model information (gemini-2.5-pro, etc.)
- Internal processing flags
- Full transcripts
- Segment counts and validation details

---

### December 2024 - Status API & Emotion Analysis Documentation

#### Updated Endpoints

| Endpoint | Change | Description |
|----------|--------|-------------|
| `GET /status/{submission_id}` | Added `extraction_id` field | Response now includes `extraction_id` when status is `COMPLETED` |
| `GET /status/{submission_id}` | Updated `metrics` structure | Metrics now use seconds (not ms) with `stitching_time`, `transcription_time`, `extraction_time`, `total_time` |

#### New Documentation

| Section | Description |
|---------|-------------|
| Emotion Analysis APIs | Added full documentation for emotion analysis endpoints |
| `GET /extractions/{extraction_id}/emotions` | Get emotion analysis by extraction ID |
| `GET /extractions/by-submission/{submission_id}/emotions` | Get emotion analysis by submission ID |

#### Response Changes

**GET /status/{submission_id}** now returns:
- `extraction_id`: UUID of the created extraction (enables emotion analysis lookup)
- `metrics.stitching_time`: Audio stitching time in seconds
- `metrics.transcription_time`: Transcription time in seconds
- `metrics.extraction_time`: Extraction time in seconds
- `metrics.total_time`: Total processing time in seconds

---

### December 2024 - Prescreen API PRESCREEN Filtering Update

#### Changed Behavior

| Change | Description |
|--------|-------------|
| Prescreen Data Filtering | All prescreen sections (except `prescreen_data`) now explicitly skip PRESCREEN template extractions |
| PRESCREEN Template Detection | Identified by `template_code` containing `'PRESCREEN'` (case-insensitive) |
| `patient_id` Parameter | Now accepts both external patient ID (e.g., MRN) and internal UUID |

#### Prescreen Section Data Sources

| Section | Before | After |
|---------|--------|-------|
| `emotion_pattern_summary` | Latest extractions (any template) | NON-PRESCREEN extractions only |
| `top_interventions` | Latest extraction (any template) | Most recent NON-PRESCREEN extraction |
| `warning_factors` | Latest extraction (any template) | Most recent NON-PRESCREEN extraction |
| `past_diagnosis_summary` | Latest extraction (any template) | Most recent NON-PRESCREEN extraction |
| `clinical_timeline` | All extractions | NON-PRESCREEN extractions only |
| `last_prescription` | Latest extraction (any template) | Most recent NON-PRESCREEN extraction |
| `prescreen_data` | Latest PRESCREEN extraction | Latest PRESCREEN extraction (unchanged) |

#### Technical Notes

- PRESCREEN filtering is performed server-side after fetching data
- If the latest extraction is a PRESCREEN template, all affected sections fall back to the next most recent non-PRESCREEN extraction

---

### December 2024 - Security & Merge API Updates

#### New Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /cancel` | Cancel an active recording session |
| `POST /merge` | Async merge multiple extractions (returns immediately) |
| `POST /merge/preview` | Preview merge without saving |
| `GET /merge/status/{extraction_id}` | Check merge operation status |
| `POST /share` | Share template with individual doctors |
| `POST /share-hospital` | Share template with all doctors in a hospital |
| `POST /share-specialization` | Share template with all doctors of a specialization |

#### Changed Endpoints

| Endpoint | Change | From | To |
|----------|--------|------|-----|
| All endpoints | Authorization header | Optional | **Required** (`Authorization: Bearer <api_key>`) |
| `POST /merge` | Request field renamed | `target_consultation_type_code` | `target_template_code` |
| `POST /merge/preview` | Request field renamed | `target_consultation_type_code` | `target_template_code` |
| `POST /feedback/{match_log_id}` | Added required query param | - | `doctor_id` (required) |
| `POST /feedback/bulk-agree` | Added required query param | - | `doctor_id` (required) |
| `GET /patients/search` | Added required query param | - | `doctor_id` (required) |
| `POST /share` | Body validation | - | `sharing_doctor_id` validated for EHR access |
| `POST /share-hospital` | Body validation | - | `sharing_doctor_id` validated for EHR access |
| `POST /share-specialization` | Body validation | - | `sharing_doctor_id` validated for EHR access |

#### Security Enhancements

| Change | Description |
|--------|-------------|
| Authorization Header | All endpoints now require `Authorization: Bearer <api_key>` when `AUTH_ENABLED=true` |
| EHR Body Validation | Added `validate_doctor_from_body()` for endpoints with `doctor_id` in request body |
| EHR Sharing Validation | Added `verify_doctor_access_from_body` for template sharing endpoints using `sharing_doctor_id` |
| EHR Correlation Validation | Added `validate_correlation_from_body()` for `/chunk` and `/cancel` endpoints |
| EHR Template/Segment Access | Templates and segments endpoints now require `doctor_id` for EHR clients |
| Hospital-Scoped Access | All EHR client requests are validated against hospital scope |

#### Breaking Changes

1. **Authorization Header Required:** All endpoints require authentication
   - **Migration:** Add `Authorization: Bearer <api_key>` header to all requests

2. **Merge API Field Rename:** `target_consultation_type_code` → `target_template_code`
   - **Migration:** Update all merge API calls to use `target_template_code`
   - Template access is validated (owned, shared, or common)

3. **Medicine Feedback APIs:** Now require `doctor_id` query parameter
   - **Migration:** Add `?doctor_id=<uuid>` to all feedback API calls

4. **Patient Search API:** Now requires `doctor_id` query parameter
   - **Migration:** Add `?doctor_id=<uuid>` to search calls

5. **Template Sharing APIs:** Use `sharing_doctor_id` in request body for validation
   - **Migration:** Ensure `sharing_doctor_id` is included and belongs to your hospital (for EHR clients)

#### Documentation Additions

- Added Security & Authentication section with Authorization header details
- Added full POST /cancel documentation
- Added full POST /live/session documentation
- Added complete Merge APIs section (POST /merge, POST /merge/preview, GET /merge/status)
- Added Patient APIs section (GET /patients/search, GET /patients/{patient_id}/prescreen)
- Added Medicine List APIs section with CRUD and CSV upload endpoints
- Added Investigation List APIs section with CRUD and CSV upload endpoints
- Added Template Sharing APIs section (POST /share, /share-hospital, /share-specialization)

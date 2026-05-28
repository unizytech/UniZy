# Nurse & Recording API Documentation

> **Last Updated:** December 24, 2024  
> **Base URL:** `http://localhost:8000` (development) or your production URL

---

## Table of Contents

1. [Nurse Management APIs](#1-nurse-management-apis)
2. [Nurse Templates APIs](#2-nurse-templates-apis)
3. [Recording APIs (with nurse_id support)](#3-recording-apis)
   - [POST /start](#post-apiv1option1recordingstart)
   - [POST /chunk](#post-apiv1option1recordingchunk)
   - [POST /cancel](#post-apiv1option1recordingcancel)
   - [GET /status/{submission_id}](#get-apiv1option1recordingstatussubmission_id)
   - [POST /live/session](#post-apiv1option1recordinglivesession)
4. [Summary/Extraction API](#4-summaryextraction-api)
5. [Webhook Payload Structure](#5-webhook-payload-structure)
6. [Audio Quality Analysis](#6-audio-quality-analysis)

---

## 1. Nurse Management APIs

**Base Path:** `/api/v1/nurses`

### GET /api/v1/nurses

List all nurses.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `active_only` | boolean | No | `true` | Filter by active status |
| `hospital_id` | string (UUID) | No | - | Filter by hospital |

**Response:**
```json
{
  "success": true,
  "nurses": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "nurse@hospital.com",
      "full_name": "Jane Smith",
      "qualification": "RN",
      "hospital_id": "660e8400-e29b-41d4-a716-446655440000",
      "is_active": true,
      "created_at": "2024-12-24T10:00:00Z",
      "updated_at": "2024-12-24T10:00:00Z"
    }
  ],
  "count": 10
}
```

---

### GET /api/v1/nurses/search

Search nurses by name or email.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | Yes | Search query (min 2 characters) |

**Response:**
```json
{
  "success": true,
  "query": "jane",
  "nurses": [...],
  "count": 5
}
```

---

### GET /api/v1/nurses/list-all

Get simplified list of all active nurses (for template sharing UI).

**Response:**
```json
{
  "success": true,
  "nurses": [
    {
      "id": "uuid",
      "full_name": "Jane Doe",
      "email": "jane@example.com",
      "qualification": "RN"
    }
  ],
  "count": 10
}
```

---

### GET /api/v1/nurses/{nurse_id}

Get nurse by ID.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `nurse_id` | string (UUID) | Nurse ID |

**Response:**
```json
{
  "success": true,
  "nurse": {
    "id": "uuid",
    "email": "nurse@hospital.com",
    "full_name": "Jane Smith",
    "qualification": "RN",
    "hospital_id": "uuid",
    "is_active": true,
    "created_at": "2024-12-24T10:00:00Z",
    "updated_at": "2024-12-24T10:00:00Z"
  }
}
```

---

### POST /api/v1/nurses

Create a new nurse.

**Request Body:**
```json
{
  "email": "nurse@hospital.com",
  "full_name": "Jane Smith",
  "qualification": "RN",
  "hospital_id": "660e8400-e29b-41d4-a716-446655440000"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | Yes | Nurse email address |
| `full_name` | string | Yes | Full name (2-255 characters) |
| `qualification` | string | No | Qualification (max 100 chars), e.g., RN, BSN, LPN |
| `hospital_id` | string (UUID) | No | Associated hospital ID |

**Response:**
```json
{
  "success": true,
  "message": "Nurse 'Jane Smith' created successfully",
  "nurse": {
    "id": "generated-uuid",
    "email": "nurse@hospital.com",
    "full_name": "Jane Smith",
    "qualification": "RN",
    "hospital_id": "uuid",
    "is_active": true,
    "created_at": "2024-12-24T10:00:00Z"
  }
}
```

---

### POST /api/v1/nurses/with-hospital

Create nurse with hospital lookup by code (for EHR integration).

**Request Body:**
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
| `id` | string (UUID) | Yes | UUID provided by caller |
| `hospital_code` | string | Yes | Hospital code (1-50 characters) |
| `full_name` | string | Yes | Full name (2-255 characters) |
| `email` | string | Yes | Nurse email address |
| `qualification` | string | No | Qualification (max 100 chars) |

**Response:**
```json
{
  "success": true,
  "message": "Nurse 'Jane Smith' created successfully",
  "nurse_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### PUT /api/v1/nurses/{nurse_id}

Update nurse (all fields optional).

**Request Body:**
```json
{
  "email": "new@email.com",
  "full_name": "Updated Name",
  "qualification": "BSN",
  "hospital_id": "uuid",
  "is_active": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Nurse updated successfully",
  "nurse": { /* updated nurse record */ }
}
```

---

### DELETE /api/v1/nurses/{nurse_id}

Soft-delete nurse (sets `is_active = false`).

**Response:**
```json
{
  "success": true,
  "message": "Nurse 'Jane Doe' deactivated successfully",
  "nurse": { /* nurse record with is_active=false */ }
}
```

---

### GET /api/v1/nurses/{nurse_id}/doctors

Get doctors associated with a nurse.

**Response:**
```json
{
  "success": true,
  "nurse_id": "uuid",
  "doctors": [
    {
      "association_id": "uuid",
      "doctor_id": "uuid",
      "doctor_name": "Dr. Smith",
      "email": "smith@hospital.com",
      "specialization": "Pediatrics",
      "hospital_id": "uuid",
      "is_active": true,
      "created_at": "2024-12-24T10:00:00Z"
    }
  ],
  "count": 3
}
```

---

### POST /api/v1/nurses/{nurse_id}/doctors/{doctor_id}

Link nurse to doctor.

> **Note:** This operation is idempotent. If the association exists but is inactive, it will be reactivated.

**Response:**
```json
{
  "success": true,
  "message": "Nurse linked to doctor successfully",
  "association": {
    "id": "uuid",
    "nurse_id": "uuid",
    "doctor_id": "uuid",
    "is_active": true,
    "created_at": "2024-12-24T10:00:00Z"
  }
}
```

---

### DELETE /api/v1/nurses/{nurse_id}/doctors/{doctor_id}

Unlink nurse from doctor (soft delete - can be relinked later).

**Response:**
```json
{
  "success": true,
  "message": "Nurse unlinked from doctor successfully",
  "association": { /* association record with is_active=false */ }
}
```

---

## 2. Nurse Templates APIs

**Base Path:** `/api/v1/nurse-templates`

### POST /api/v1/nurse-templates/share

Share template with one or more nurses.

**Request Body:**
```json
{
  "template_id": "123e4567-e89b-12d3-a456-426614174000",
  "template_code": "PSYCHIATRY_OP",
  "nurse_ids": [
    "223e4567-e89b-12d3-a456-426614174000",
    "323e4567-e89b-12d3-a456-426614174001"
  ],
  "access_level": "use"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `template_id` | string (UUID) | Yes | - | Template ID to share |
| `template_code` | string | Yes | - | Template code |
| `nurse_ids` | array[string] | Yes | - | List of nurse UUIDs (min 1) |
| `access_level` | string | No | `"use"` | `"view"` (read-only) or `"use"` (can extract) |

**Response:**
```json
{
  "success": true,
  "message": "Template shared with 2 nurse(s)",
  "shared_count": 2,
  "failed_count": 0,
  "failures": []
}
```

---

### POST /api/v1/nurse-templates/activate

Activate a template for a nurse.

> **Note:** Only ONE template can be active per nurse at a time. Activating a new template will deactivate the previously active one.

**Request Body:**
```json
{
  "nurse_id": "223e4567-e89b-12d3-a456-426614174000",
  "template_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

**Response:**
```json
{
  "success": true,
  "is_active": true,
  "message": "Template activated successfully",
  "activated_template_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

---

### POST /api/v1/nurse-templates/deactivate

Deactivate a template for a nurse.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `nurse_id` | string (UUID) | Yes | Nurse ID |
| `template_id` | string (UUID) | Yes | Template ID |

**Response:**
```json
{
  "success": true,
  "is_active": false,
  "message": "Template deactivated successfully"
}
```

---

### GET /api/v1/nurse-templates/accessible

Get all templates accessible by a nurse.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `nurse_id` | string (UUID) | Yes | - | Nurse ID |
| `active_only` | boolean | No | `false` | Return only active templates |

**Response:**
```json
{
  "success": true,
  "templates": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "template_code": "PSYCHIATRY_OP",
      "template_name": "Psychiatry OP",
      "is_active": true,
      "access_level": "use"
    },
    {
      "id": "223e4567-e89b-12d3-a456-426614174001",
      "template_code": "PEDIATRIC_OP",
      "template_name": "Pediatric OP",
      "is_active": false,
      "access_level": "view"
    }
  ],
  "count": 2
}
```

---

### GET /api/v1/nurse-templates/active

Get the currently active template for a nurse.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `nurse_id` | string (UUID) | Yes | Nurse ID |

**Response:**
```json
{
  "success": true,
  "template": {
    "id": "uuid",
    "template_code": "PSYCHIATRY_OP",
    "template_name": "Psychiatry OP",
    "is_active": true,
    "access_level": "use"
  }
}
```

---

### GET /api/v1/nurse-templates/validate-access

Validate that a nurse has access to a specific template.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `nurse_id` | string (UUID) | Yes | Nurse ID |
| `template_id` | string (UUID) | Yes | Template ID |

**Response:**
```json
{
  "success": true,
  "has_access": true
}
```

---

### DELETE /api/v1/nurse-templates/revoke

Revoke a nurse's access to a template.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `nurse_id` | string (UUID) | Yes | Nurse ID |
| `template_id` | string (UUID) | Yes | Template ID |

**Response:**
```json
{
  "success": true,
  "message": "Template access revoked successfully",
  "revoked": true
}
```

---

### GET /api/v1/nurse-templates/template-shares/{template_id}

Get all nurses who have access to a specific template.

**Response:**
```json
{
  "success": true,
  "shares": [
    {
      "nurse_id": "uuid",
      "nurse_name": "Jane Doe",
      "access_level": "use"
    }
  ]
}
```

---

## 3. Recording APIs

**Base Path:** `/api/v1/option1/recording`

### POST /api/v1/option1/recording/start

Start a new recording session.

**Request Body:**
```json
{
  "doctor_id": "550e8400-e29b-41d4-a716-446655440000",
  "patient_id": "PATIENT123",
  "template_code": "PSYCHIATRY_OP",
  "template_name": "Psychiatry OP",
  "processing_mode": "default",
  "extraction_mode": "full",
  "chunk_duration_seconds": 10,
  "nurse_id": "660e8400-e29b-41d4-a716-446655440000"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `doctor_id` | string (UUID) | Yes | - | Doctor ID |
| `patient_id` | string | Yes | - | Patient identifier |
| `template_code` | string | Yes | - | Template code or `"TRANSCRIPT_ONLY"` |
| `template_name` | string | No | - | Display name for template |
| `processing_mode` | string | No | `"default"` | `fast`, `default`, `thorough`, `ultra`, `ultra_fast` |
| `extraction_mode` | string | No | `"full"` | `core`, `additional`, `full` |
| `chunk_duration_seconds` | integer | No | `10` | 0-60 seconds (0 = file upload mode) |
| `nurse_id` | string (UUID) | No | - | **NEW** - Nurse ID if recording initiated by nurse |

**Response:**
```json
{
  "correlation_id": "770e8400-e29b-41d4-a716-446655440000",
  "session_id": "880e8400-e29b-41d4-a716-446655440000",
  "message": "Recording session started successfully"
}
```

---

### POST /api/v1/option1/recording/chunk

Upload an audio chunk.

**Request Body:**
```json
{
  "correlation_id": "770e8400-e29b-41d4-a716-446655440000",
  "chunk_index": 0,
  "audio_data": "base64-encoded-audio-data...",
  "mime_type": "audio/webm",
  "duration_seconds": 10.5,
  "is_last": false
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `correlation_id` | string (UUID) | Yes | - | Session ID from `/start` |
| `chunk_index` | integer | Yes | - | Sequential chunk index (0-based) |
| `audio_data` | string | Yes | - | Base64-encoded audio data |
| `mime_type` | string | No | `"audio/webm"` | Audio MIME type |
| `duration_seconds` | number | No | - | Chunk duration in seconds |
| `is_last` | boolean | Yes | - | Mark as final chunk |

**Response (intermediate chunk):**
```json
{
  "message": "Chunk uploaded successfully",
  "chunkIndex": 0,
  "totalChunks": 1
}
```

**Response (final chunk - `is_last: true`):**
```json
{
  "message": "Recording submitted for processing",
  "chunkIndex": 5,
  "totalChunks": 6,
  "submissionId": "990e8400-e29b-41d4-a716-446655440000"
}
```

---

### POST /api/v1/option1/recording/cancel

Cancel an active recording session.

**Request Body:**
```json
{
  "correlation_id": "770e8400-e29b-41d4-a716-446655440000"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `correlation_id` | string (UUID) | Yes | Session correlation ID from `/start` |

**Response:**
```json
{
  "message": "Recording session cancelled successfully",
  "correlation_id": "770e8400-e29b-41d4-a716-446655440000"
}
```

**Notes:**
- Changes session status to `CANCELLED`
- Deletes all uploaded chunks
- Stops any ongoing processing
- Cannot cancel sessions with status `COMPLETED` or `ERROR`
- **Security:** EHR clients must have access to the recording session's hospital

---

### GET /api/v1/option1/recording/status/{submission_id}

Get current processing status (polling fallback).

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `submission_id` | string (UUID) | Submission ID from `/chunk` (is_last=true) response |

**Response (in progress):**
```json
{
  "submission_id": "990e8400-e29b-41d4-a716-446655440000",
  "status": "PROCESSING",
  "progress": 45,
  "message": "Transcribing audio..."
}
```

**Response (completed):**
```json
{
  "submission_id": "990e8400-e29b-41d4-a716-446655440000",
  "status": "COMPLETED",
  "progress": 100,
  "message": "Extraction complete",
  "transcript": "Doctor: Hello, how are you feeling today?...",
  "insights": {
    "summary": "...",
    "diagnosis": "...",
    "medications": [...]
  },
  "metrics": {
    "stitching_time": 1.2,
    "transcription_time": 3.5,
    "extraction_time": 5.8,
    "total_time": 10.5
  }
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `submission_id` | string | The submission ID |
| `status` | string | `QUEUED`, `PROCESSING`, `COMPLETED`, `ERROR`, `FAILED` |
| `progress` | integer | Progress percentage (0-100) |
| `message` | string | Human-readable status message |
| `transcript` | string | Full transcript (only when `COMPLETED`) |
| `insights` | object | Extracted medical data (only when `COMPLETED`) |
| `metrics` | object | Processing time metrics (only when `COMPLETED`) |

**Notes:**
- **Primary use:** Real-time updates via WebSocket subscription. Use this endpoint as a polling fallback when WebSocket is unavailable.
- Returns 404 if `submission_id` not found
- `transcript`, `insights`, and `metrics` are only included when `status=COMPLETED`
- **Security:** EHR clients must have access to the recording session's hospital

---

### POST /api/v1/option1/recording/live/session

Create a live transcription session.

**Request Body:**
```json
{
  "doctor_id": "550e8400-e29b-41d4-a716-446655440000",
  "patient_id": "PATIENT123",
  "template_code": "PSYCHIATRY_OP",
  "template_name": "Psychiatry OP",
  "processing_mode": "ultra",
  "nurse_id": "660e8400-e29b-41d4-a716-446655440000"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `doctor_id` | string (UUID) | Yes | - | Doctor ID |
| `patient_id` | string | Yes | - | Patient identifier |
| `template_code` | string | Yes | - | Template code |
| `template_name` | string | No | - | Display name |
| `processing_mode` | string | No | `"ultra"` | `ultra`, `ultra_fast` |
| `nurse_id` | string (UUID) | No | - | **NEW** - Nurse ID if initiated by nurse |

**Response:**
```json
{
  "correlation_id": "uuid",
  "session_id": "uuid",
  "message": "Live session created"
}
```

---

## 4. Summary/Extraction API

**Base Path:** `/api/v1/summary`

### POST /api/v1/summary/extract

Extract medical insights from a transcript.

**Request Body:**
```json
{
  "transcript": "Patient presented with complaints of...",
  "doctor_id": "550e8400-e29b-41d4-a716-446655440000",
  "patient_id": "PATIENT123",
  "template_code": "PSYCHIATRY_OP",
  "template_name": "Psychiatry OP",
  "processing_mode": "default",
  "mode": "full",
  "submission_id": "990e8400-e29b-41d4-a716-446655440000",
  "nurse_id": "660e8400-e29b-41d4-a716-446655440000"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `transcript` | string | Yes | - | Transcript text (min 10 characters) |
| `doctor_id` | string (UUID) | No | - | Doctor ID |
| `patient_id` | string | No | - | Patient identifier |
| `template_code` | string | No | - | Template code |
| `template_name` | string | No | - | Display name |
| `processing_mode` | string | No | - | `fast`, `default`, `thorough`, `ultra`, `ultra_fast` |
| `mode` | string | No | `"full"` | `core`, `additional`, `full` |
| `submission_id` | string (UUID) | Yes | - | Submission ID from recording |
| `nurse_id` | string (UUID) | No | - | **NEW** - Nurse ID if initiated by nurse |

**Response:**
```json
{
  "success": true,
  "insights": {
    "summary": "Patient presented with...",
    "diagnosis": "...",
    "medications": [...],
    "investigations": [...],
    "treatmentPlan": "..."
  },
  "metadata": {
    "correlation_id": "uuid",
    "submission_id": "uuid",
    "extraction_id": "uuid",
    "doctor_id": "uuid",
    "patient_id": "PATIENT123",
    "template_code": "PSYCHIATRY_OP",
    "mode": "full",
    "segment_count": 12,
    "processing_mode": "default",
    "timestamp": "2024-12-24T10:30:45.123Z",
    "audio_quality": {
      "overall_quality": "good",
      "is_acceptable": true,
      "issues": [],
      "metrics": {
        "snr_db": 25.3,
        "rms_db": -18.5,
        "peak_db": -3.1,
        "clipping_ratio": 0.0,
        "silence_ratio": 0.12,
        "speech_detected": true,
        "duration_seconds": 145.2
      },
      "summary_message": "Audio quality is good for transcription."
    }
  }
}
```

> **Note:** `audio_quality` may be `null` if:
> - Audio quality analysis hasn't completed yet (async process)
> - Analysis failed (e.g., unsupported format)
> - Recording was in transcript-only mode without audio

---

### Audio Quality Data Sources

There are **three ways** to receive audio quality data:

| Source | When to Use | How |
|--------|-------------|-----|
| **`/extract` API Response** | Direct extraction calls | Included in `metadata.audio_quality` field |
| **`/status/{submission_id}` API** | Polling for status | Poll until `status=COMPLETED`, audio quality in response |
| **Webhook Payload** | Async processing | Included in `metadata.audio_quality` field |

#### Example: Polling for Audio Quality

```python
import requests
import time

def get_audio_quality(submission_id: str, api_key: str):
    """Poll status until complete and return audio quality."""
    headers = {"Authorization": f"Bearer {api_key}"}

    for _ in range(30):  # Max 30 attempts
        response = requests.get(
            f"https://api.example.com/api/v1/option1/recording/status/{submission_id}",
            headers=headers
        )
        data = response.json()

        if data["status"] == "COMPLETED":
            # Audio quality available in extraction metadata
            return data.get("insights", {})
        elif data["status"] in ("ERROR", "FAILED"):
            raise Exception(f"Processing failed: {data.get('message')}")

        time.sleep(5)  # Wait 5 seconds before next poll

    raise TimeoutError("Processing did not complete in time")
```

---

## 5. Webhook Payload Structure

When webhooks are enabled, extraction results are automatically sent to configured webhook URLs.

### Configuration

Set these environment variables in `backend/.env`:

```env
WEBHOOK_ENABLED=true
WEBHOOK_URL=https://your-webhook-url.com/endpoint,https://backup-url.com/endpoint
WEBHOOK_TOKEN=your-bearer-token
WEBHOOK_TIMEOUT=10
```

### Payload Structure

```json
{
  "success": true,
  "insights": {
    "summary": "Patient presented with...",
    "diagnosis": "...",
    "medications": [...],
    "investigations": [...],
    "treatmentPlan": "..."
  },
  "metadata": {
    "correlation_id": "770e8400-e29b-41d4-a716-446655440000",
    "submission_id": "990e8400-e29b-41d4-a716-446655440000",
    "extraction_id": "aa0e8400-e29b-41d4-a716-446655440000",
    "doctor_id": "550e8400-e29b-41d4-a716-446655440000",
    "patient_id": "PATIENT123",
    "template_code": "PSYCHIATRY_OP",
    "mode": "full",
    "segment_count": 12,
    "processing_mode": "default",
    "timestamp": "2024-12-24T10:30:45.123Z",
    "source": "recording",
    "audio_quality": {
      "overall_quality": "good",
      "is_acceptable": true,
      "issues": [],
      "metrics": {
        "snr_db": 25.3,
        "rms_db": -18.5,
        "peak_db": -3.1,
        "clipping_ratio": 0.0,
        "silence_ratio": 0.12,
        "speech_detected": true,
        "duration_seconds": 145.2
      },
      "summary_message": "Audio quality is good for transcription."
    }
  }
}
```

### Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `correlation_id` | string (UUID) | Recording session ID |
| `submission_id` | string (UUID) | Processing submission ID |
| `extraction_id` | string (UUID) | Extraction record ID |
| `doctor_id` | string (UUID) | Doctor ID |
| `patient_id` | string | Patient identifier |
| `template_code` | string | Template code used |
| `mode` | string | Extraction mode (`core`, `additional`, `full`) |
| `segment_count` | integer | Number of segments extracted |
| `processing_mode` | string | Processing mode used |
| `timestamp` | string (ISO 8601) | Extraction timestamp |
| `source` | string | Source type (see below) |
| `audio_quality` | object \| null | **NEW** - Audio quality analysis (see section 6) |

### Source Types

| Source | Description |
|--------|-------------|
| `recording` | Standard recording flow |
| `transcript_only_extraction` | Transcript-only mode |
| `merge` | Extraction merge operation |
| `emotion_analysis` | Emotion analysis results |
| `congruence_analysis` | Text vs audio congruence comparison |

---

## 6. Audio Quality Analysis

Audio quality is automatically analyzed during recording processing and included in webhook payloads and completion events.

### Audio Quality Object

```json
{
  "overall_quality": "good",
  "is_acceptable": true,
  "issues": [
    {
      "type": "low_snr",
      "severity": "warning",
      "message": "Moderate background noise"
    }
  ],
  "metrics": {
    "snr_db": 18.5,
    "rms_db": -22.3,
    "peak_db": -3.1,
    "clipping_ratio": 0.001,
    "silence_ratio": 0.15,
    "speech_detected": true,
    "duration_seconds": 145.2
  },
  "summary_message": "Audio quality is fair. Moderate background noise."
}
```

### Quality Levels

| Level | Description | Acceptable |
|-------|-------------|------------|
| `good` | No issues detected | Yes |
| `fair` | Minor issues (warnings) | Yes |
| `poor` | Critical issues detected | Yes (with warning) |
| `unknown` | Analysis failed or skipped | Yes |

### Issue Types

| Type | Severity | Description |
|------|----------|-------------|
| `low_snr` | warning/critical | Background noise detected |
| `too_quiet` | warning/critical | Audio volume is low |
| `clipping` | warning | Audio distortion (clipping) |
| `too_much_silence` | warning | Recording contains mostly silence |
| `no_speech` | critical | No speech detected |
| `too_short` | warning | Recording is very short (<3s) |
| `too_long` | warning | Recording is very long (>30min) |

### Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `snr_db` | number \| null | Signal-to-noise ratio in decibels |
| `rms_db` | number \| null | Root mean square (average volume) in dB |
| `peak_db` | number \| null | Peak amplitude in dB |
| `clipping_ratio` | number \| null | Ratio of clipped samples (0-1) |
| `silence_ratio` | number \| null | Ratio of silent frames (0-1) |
| `speech_detected` | boolean \| null | Whether speech was detected |
| `duration_seconds` | number \| null | Total audio duration |

### Quality Thresholds

| Metric | Good | Fair | Poor |
|--------|------|------|------|
| SNR | ≥20 dB | 10-20 dB | <10 dB |
| RMS | ≥-35 dB | -35 to -40 dB | <-40 dB |
| Clipping | <1% | - | ≥1% |
| Silence | <70% | - | ≥70% |
| Speech | Detected | - | Not detected |

### Supported Audio Formats

| Format | MIME Types |
|--------|------------|
| WebM | `audio/webm`, `video/webm` |
| MP3 | `audio/mp3`, `audio/mpeg`, `audio/mpeg3` |
| WAV | `audio/wav`, `audio/x-wav`, `audio/wave` |
| M4A/AAC | `audio/m4a`, `audio/x-m4a`, `audio/mp4`, `audio/aac` |
| OGG | `audio/ogg`, `application/ogg` |
| FLAC | `audio/flac`, `audio/x-flac` |
| 3GP | `audio/3gpp`, `video/3gpp` |

---

## Error Responses

All endpoints return errors in a consistent format:

```json
{
  "success": false,
  "error": "Error message describing what went wrong",
  "detail": "Additional details if available"
}
```

### Common HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Missing or invalid authentication |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource doesn't exist |
| 409 | Conflict - Resource already exists |
| 422 | Unprocessable Entity - Validation error |
| 500 | Internal Server Error |

---

## Authentication

All endpoints require authentication via the `Authorization: Bearer` header.

**EHR/External Integrations (API Key):**
```
Authorization: Bearer <api_key>
```

**Web/Mobile Apps (JWT):**
```
Authorization: Bearer <jwt_token>
```

The system automatically distinguishes between API keys and JWTs based on token format (JWTs have 3 dot-separated parts starting with "eyJ").

### Authentication Levels

| Level | Description |
|-------|-------------|
| `get_current_client` | Any authenticated client |
| `require_admin` | Admin-level access required |
| `verify_submission_access` | Validates submission ownership |

### EHR Access Control

When `AUTH_ENABLED=true`, EHR clients are hospital-scoped and can only access:
- Doctors registered with their hospital
- Nurses registered with their hospital
- Patients with consultations at their hospital
- Recording sessions initiated by their hospital's staff

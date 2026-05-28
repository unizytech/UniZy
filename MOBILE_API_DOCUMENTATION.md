# Mobile Application API Documentation

**Version:** 1.0.0
**Base URL:** `http://localhost:8000` (development) or your production URL
**Last Updated:** 2025-11-27

This document provides API documentation for building a mobile/external application that can:
1. Select a doctor and their activated templates
2. Record audio and upload in chunks
3. Receive extracted medical insights

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Authentication](#authentication)
3. [API Endpoints](#api-endpoints)
   - [Doctor & Template Selection](#1-doctor--template-selection)
   - [Processing Modes](#2-processing-modes)
   - [Recording & Audio Upload](#3-recording--audio-upload)
   - [Progress Monitoring (SSE)](#4-progress-monitoring-sse)
   - [Polling Alternative](#5-polling-alternative)
   - [Transcript-Only Extraction](#6-transcript-only-extraction-no-audio)
   - [Template Configuration](#7-template-configuration)
   - [Segment Configuration (Admin)](#8-segment-configuration-admin)
4. [Complete Recording Flow](#complete-recording-flow)
5. [Transcript-Only Flow](#transcript-only-flow)
6. [Response Examples](#response-examples)
7. [Error Handling](#error-handling)

---

## Getting Started

### Prerequisites
- Doctor must be registered in the system with a valid `doctor_id` (UUID)
- Doctor must have at least one activated template
- Audio should be recorded in supported formats: `audio/webm`, `audio/wav`, `audio/mp3`, `audio/m4a`

### Quick Start Flow
```
1. GET /api/v1/doctors?active_only=true           → Get list of doctors
2. GET /api/v1/summary/templates?doctor_id=...&filter_type=doctor  → Get doctor's templates
3. GET /api/v1/summary/processing-modes           → Get available processing modes
4. POST /api/v1/option1/recording/start           → Start recording session
5. POST /api/v1/option1/recording/chunk           → Upload audio chunks (repeat)
6. POST /api/v1/option1/recording/chunk (is_last=true) → Upload final chunk
7. GET /api/v1/option1/recording/processing/{submission_id}/stream → SSE progress (optional)
```

---

## Authentication

Currently, the API uses `doctor_id` (UUID) for identification. No JWT/OAuth required for development.

> **Note:** For production, implement proper authentication (JWT tokens, API keys, etc.)

---

## API Endpoints

### 1. Doctor & Template Selection

#### 1.1 List All Doctors

Get list of active doctors in the system.

| Property | Value |
|----------|-------|
| **Method** | `GET` |
| **URL** | `/api/v1/doctors` |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `active_only` | boolean | `true` | Filter to show only active doctors |

**Response:**
```json
{
  "success": true,
  "doctors": [
    {
      "id": "83b3eb65-6801-4bc5-b565-dd3dee2be70a",
      "email": "doctor@hospital.com",
      "full_name": "Dr. John Smith",
      "specialization": "Psychiatry",
      "is_active": true,
      "created_at": "2025-01-01T00:00:00Z"
    }
  ],
  "count": 1
}
```

---

#### 1.2 Get Doctor's Available Templates

Get all templates available to a specific doctor for recording.

| Property | Value |
|----------|-------|
| **Method** | `GET` |
| **URL** | `/api/v1/summary/templates` |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | string (UUID) | Yes | Doctor's UUID |
| `filter_type` | string | Yes | Use `doctor` to get doctor's activated templates |

**Example:**
```
GET /api/v1/summary/templates?doctor_id=83b3eb65-6801-4bc5-b565-dd3dee2be70a&filter_type=doctor
```

**Response:**
```json
{
  "success": true,
  "templates": [
    {
      "id": "9e03a603-ac6a-42a8-99cf-86c2f353436c",
      "template_code": "OP_SHORT",
      "template_name": "Op summary template",
      "description": "Short outpatient consultation summary",
      "consultation_type_id": "832eda7c-de59-48c7-9985-232710675a20",
      "consultation_type_code": "OP_SHORT",
      "consultation_type_name": "Outpatient Short",
      "is_active": true
    },
    {
      "id": "abc12345-...",
      "template_code": "PSYCHIATRY_FULL",
      "template_name": "Psychiatry Full Consultation",
      "description": "Complete psychiatric evaluation",
      "consultation_type_id": "...",
      "consultation_type_code": "OP",
      "consultation_type_name": "Outpatient Consultation",
      "is_active": true
    }
  ],
  "count": 2
}
```

**Important Fields:**
- `template_code` - Use this for `template_code` in recording requests
- `template_name` - Use this for `template_name` in recording requests (optional, for display)

---

### 2. Processing Modes

#### 2.1 Get Available Processing Modes

Get all available processing modes with their configurations.

| Property | Value |
|----------|-------|
| **Method** | `GET` |
| **URL** | `/api/v1/summary/processing-modes` |

**Response:**
```json
{
  "success": true,
  "processing_modes": [
    {
      "mode_code": "fast",
      "mode_name": "Fast",
      "description": "Fast processing with Flash models",
      "transcription_model": "gemini-2.5-flash",
      "extraction_model": "gemini-2.5-flash",
      "estimated_time_seconds": 25,
      "display_order": 1
    },
    {
      "mode_code": "default",
      "mode_name": "Default",
      "description": "Balanced: Flash transcription + Pro extraction",
      "transcription_model": "gemini-2.5-flash",
      "extraction_model": "gemini-2.5-pro",
      "estimated_time_seconds": 40,
      "display_order": 2
    },
    {
      "mode_code": "thorough",
      "mode_name": "Thorough",
      "description": "Maximum quality with Pro models",
      "transcription_model": "gemini-2.5-pro",
      "extraction_model": "gemini-2.5-pro",
      "estimated_time_seconds": 55,
      "display_order": 3
    }
  ],
  "count": 3
}
```

**Recommended Mode:** Use `default` for most use cases (good balance of speed and quality).

---

### 3. Recording & Audio Upload

#### 3.1 Start Recording Session

Initialize a new recording session before uploading audio.

| Property | Value |
|----------|-------|
| **Method** | `POST` |
| **URL** | `/api/v1/option1/recording/start` |
| **Content-Type** | `application/json` |

**Request Body:**
```json
{
  "doctor_id": "83b3eb65-6801-4bc5-b565-dd3dee2be70a",
  "patient_id": "P001",
  "template_code": "OP_SHORT",
  "template_name": "Op summary template",
  "processing_mode": "default",
  "extraction_mode": "full",
  "chunk_duration_seconds": 10
}
```

**Request Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | string (UUID) | Yes | Doctor's UUID |
| `patient_id` | string | Yes | Patient identifier (your system's patient ID) |
| `template_code` | string | Yes | Template code from templates list (e.g., `OP_SHORT`) |
| `template_name` | string | No | Template display name (optional) |
| `processing_mode` | string | No | `fast`, `default`, `thorough` (default: `default`) |
| `extraction_mode` | string | No | `core`, `additional`, `full` (default: `full`) |
| `chunk_duration_seconds` | integer | No | Chunk duration hint (default: 10, set to 0 for file upload) |

**Extraction Modes:**
- `core` - Extract only essential clinical segments (faster)
- `additional` - Extract supplementary segments
- `full` - Extract all segments (recommended)

**Response:**
```json
{
  "correlation_id": "ff3b1cd7-cda1-4cfe-a976-5a837587af56",
  "session_id": "d901aaea-a5cc-4259-8ffa-f9b402b9f92f",
  "message": "Recording session started successfully"
}
```

**Important:** Save the `correlation_id` - you'll need it for all chunk uploads.

---

#### 3.2 Upload Audio Chunk

Upload audio chunks during or after recording.

| Property | Value |
|----------|-------|
| **Method** | `POST` |
| **URL** | `/api/v1/option1/recording/chunk` |
| **Content-Type** | `application/json` |

**Request Body:**
```json
{
  "correlation_id": "ff3b1cd7-cda1-4cfe-a976-5a837587af56",
  "chunk_index": 0,
  "audio_data": "base64_encoded_audio_data_here",
  "mime_type": "audio/webm",
  "duration_seconds": 10.5,
  "is_last": false
}
```

**Request Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `correlation_id` | string (UUID) | Yes | Session ID from `/start` response |
| `chunk_index` | integer | Yes | Sequential index starting from 0 |
| `audio_data` | string | Yes | Base64-encoded audio data |
| `mime_type` | string | No | Audio format (default: `audio/webm`) |
| `duration_seconds` | float | No | Duration of this chunk |
| `is_last` | boolean | Yes | `true` for final chunk, `false` otherwise |

**Response (intermediate chunk):**
```json
{
  "message": "Chunk 0 uploaded successfully",
  "chunkIndex": 0,
  "totalChunks": 1,
  "submissionId": null
}
```

**Response (final chunk with `is_last: true`):**
```json
{
  "message": "Final chunk uploaded. Processing started automatically in background. submission_id: 1a710145-fc94-445e-8863-c1772e68c128",
  "chunkIndex": 5,
  "totalChunks": 6,
  "submissionId": "1a710145-fc94-445e-8863-c1772e68c128"
}
```

**Important:** When `is_last: true`:
- Background processing starts automatically
- `submissionId` is returned - use this for SSE streaming or polling
- Webhooks will fire automatically when extraction completes (if configured)

---

#### 3.3 Single File Upload (Alternative)

For complete audio files (not chunked recording), upload as a single chunk:

```json
{
  "correlation_id": "ff3b1cd7-cda1-4cfe-a976-5a837587af56",
  "chunk_index": 0,
  "audio_data": "base64_encoded_complete_audio_file",
  "mime_type": "audio/mp3",
  "duration_seconds": 120.0,
  "is_last": true
}
```

---

### 4. Progress Monitoring (SSE)

#### 4.1 Stream Processing Progress

Server-Sent Events (SSE) endpoint for real-time progress updates.

| Property | Value |
|----------|-------|
| **Method** | `GET` |
| **URL** | `/api/v1/option1/recording/processing/{submission_id}/stream` |
| **Response Type** | `text/event-stream` |

**Example:**
```
GET /api/v1/option1/recording/processing/1a710145-fc94-445e-8863-c1772e68c128/stream
```

**JavaScript Client Example:**
```javascript
const submissionId = "1a710145-fc94-445e-8863-c1772e68c128";
const eventSource = new EventSource(
  `http://localhost:8000/api/v1/option1/recording/processing/${submissionId}/stream`
);

// Progress updates
eventSource.addEventListener('progress', (event) => {
  const data = JSON.parse(event.data);
  console.log(`${data.progress}% - ${data.message}`);
  // data.status: LOADING, STITCHING, TRANSCRIBING, EXTRACTING, SAVING
});

// Processing complete
eventSource.addEventListener('complete', (event) => {
  const data = JSON.parse(event.data);
  console.log('Transcript:', data.transcript);
  console.log('Insights:', data.insights);
  console.log('Metrics:', data.metrics);
  eventSource.close();
});

// Error occurred
eventSource.addEventListener('error', (event) => {
  const data = JSON.parse(event.data);
  console.error('Error:', data.message);
  eventSource.close();
});
```

**Event Types:**

| Event | Description |
|-------|-------------|
| `progress` | Processing progress updates (0-100%) |
| `complete` | Processing finished successfully |
| `error` | Processing failed |

**Progress Stages:**
| Stage | Progress | Description |
|-------|----------|-------------|
| LOADING | 5-10% | Loading session and audio chunks |
| STITCHING | 20-30% | Combining audio chunks |
| TRANSCRIBING | 40-60% | Converting audio to text |
| EXTRACTING | 70-90% | Extracting medical insights |
| SAVING | 95% | Saving results to database |
| COMPLETED | 100% | Done |

**Complete Event Data:**
```json
{
  "event": "complete",
  "data": {
    "status": "COMPLETED",
    "progress": 100,
    "message": "Processing completed successfully",
    "transcript": "Patient presents with headache for 3 days...",
    "insights": {
      "chief_complaints": {
        "complaints": ["Headache for 3 days"],
        "duration": "3 days"
      },
      "diagnosis": {
        "primary": "Tension-type headache",
        "icd_code": "G44.2"
      },
      "prescription": [
        {
          "medication": "Paracetamol",
          "dosage": "500mg",
          "frequency": "TID",
          "duration": "5 days"
        }
      ]
    },
    "metrics": {
      "stitching_time": 0.5,
      "transcription_time": 8.2,
      "extraction_time": 12.4,
      "total_time": 21.1
    }
  }
}
```

---

### 5. Polling Alternative

If SSE is not supported, use polling instead.

#### 5.1 Get Processing Status

| Property | Value |
|----------|-------|
| **Method** | `GET` |
| **URL** | `/api/v1/option1/recording/status/{submission_id}` |

**Response (in progress):**
```json
{
  "submission_id": "1a710145-fc94-445e-8863-c1772e68c128",
  "status": "EXTRACTING",
  "progress": 75,
  "message": "Extracting medical insights..."
}
```

**Response (completed):**
```json
{
  "submission_id": "1a710145-fc94-445e-8863-c1772e68c128",
  "status": "COMPLETED",
  "progress": 100,
  "message": "Processing completed",
  "transcript": "Patient presents with...",
  "insights": { ... },
  "metrics": { ... }
}
```

**Polling Strategy:**
```javascript
async function pollStatus(submissionId) {
  const maxAttempts = 60; // 2 minutes with 2s interval
  let attempts = 0;

  while (attempts < maxAttempts) {
    const response = await fetch(`/api/v1/option1/recording/status/${submissionId}`);
    const data = await response.json();

    if (data.status === 'COMPLETED') {
      return data;
    }
    if (data.status === 'ERROR') {
      throw new Error(data.message);
    }

    await new Promise(resolve => setTimeout(resolve, 2000)); // 2s delay
    attempts++;
  }

  throw new Error('Polling timeout');
}
```

---

### 6. Transcript-Only Extraction (No Audio)

If you already have a transcript (e.g., from client-side speech recognition or external transcription service), use this flow to create a consultation and extract insights without uploading audio.

#### 6.1 Create Live Session (for transcript-based extraction)

Create a session to associate with your transcript before extraction.

| Property | Value |
|----------|-------|
| **Method** | `POST` |
| **URL** | `/api/v1/option1/recording/live/session` |
| **Content-Type** | `application/json` |

**Request Body:**
```json
{
  "doctor_id": "83b3eb65-6801-4bc5-b565-dd3dee2be70a",
  "patient_id": "P001",
  "template_code": "OP_SHORT",
  "template_name": "Op summary template",
  "processing_mode": "default"
}
```

**Request Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | string (UUID) | Yes | Doctor's UUID |
| `patient_id` | string | Yes | Patient identifier |
| `template_code` | string | Yes | Template code for extraction |
| `template_name` | string | No | Template display name |
| `processing_mode` | string | No | `default`, `fast`, `thorough` (default: `ultra`) |

**Response:**
```json
{
  "correlation_id": "ff3b1cd7-cda1-4cfe-a976-5a837587af56",
  "session_id": "d901aaea-a5cc-4259-8ffa-f9b402b9f92f",
  "message": "Live session created successfully"
}
```

---

#### 6.2 Extract from Transcript

Submit your transcript for extraction using the `correlation_id` from the session.

| Property | Value |
|----------|-------|
| **Method** | `POST` |
| **URL** | `/api/v1/summary/extract` |
| **Content-Type** | `application/json` |

**Request Body:**
```json
{
  "correlation_id": "ff3b1cd7-cda1-4cfe-a976-5a837587af56",
  "transcript": "Patient presents with headache for 3 days. Pain is described as throbbing, located in the frontal region. Associated symptoms include nausea and light sensitivity...",
  "template_code": "OP_SHORT",
  "mode": "full",
  "processing_mode": "default"
}
```

**Request Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `correlation_id` | string (UUID) | Yes | Session ID from `/live/session` |
| `transcript` | string | Yes | The transcript text to extract from |
| `template_code` | string | No | Template code (if different from session) |
| `mode` | string | No | `core`, `additional`, `full` (default: `full`) |
| `processing_mode` | string | No | Processing mode for model selection |

**Response:**
```json
{
  "success": true,
  "data": {
    "chief_complaints": {
      "complaints": ["Headache for 3 days"],
      "duration": "3 days",
      "severity": "Moderate"
    },
    "diagnosis": {
      "primary_diagnosis": "Migraine without aura",
      "icd_code": "G43.909"
    }
    // ... more segments based on template
  },
  "metadata": {
    "extraction_id": "abc123-...",
    "consultation_type_id": "832eda7c-...",
    "session_id": "d901aaea-...",
    "segment_count": 6,
    "model": "gemini-2.5-pro",
    "processing_time_seconds": 8.5,
    "flow": "transcript_only_with_session"
  }
}
```

---

### 7. Template Configuration

Endpoints for managing doctor's template activation and configuration.

#### 7.1 Get All Accessible Templates

Get all templates accessible to a doctor (owned, shared, and common).

| Property | Value |
|----------|-------|
| **Method** | `GET` |
| **URL** | `/api/v1/doctor-templates/accessible` |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | string (UUID) | Yes | Doctor's UUID |
| `consultation_type_id` | string (UUID) | No | Filter by consultation type |
| `include_common` | boolean | No | Include common templates (default: `true`) |
| `active_only` | boolean | No | Only return active templates (default: `false`) |

**Example:**
```
GET /api/v1/doctor-templates/accessible?doctor_id=83b3eb65-...&active_only=true
```

**Response:**
```json
{
  "success": true,
  "templates": [
    {
      "id": "9e03a603-...",
      "template_code": "OP_SHORT",
      "template_name": "Op summary template",
      "description": "Short outpatient consultation",
      "consultation_type_id": "832eda7c-...",
      "is_active": true,
      "access_type": "owned",
      "access_level": "use"
    },
    {
      "id": "abc12345-...",
      "template_code": "PSYCHIATRY_FULL",
      "template_name": "Psychiatry Full",
      "is_active": true,
      "access_type": "shared",
      "access_level": "use"
    }
  ],
  "count": 2
}
```

---

#### 7.2 Activate Template for Doctor

Activate a template for use in recordings. Only ONE template can be active per consultation type.

| Property | Value |
|----------|-------|
| **Method** | `POST` |
| **URL** | `/api/v1/doctor-templates/activate` |
| **Content-Type** | `application/json` |

**Request Body:**
```json
{
  "doctor_id": "83b3eb65-6801-4bc5-b565-dd3dee2be70a",
  "template_id": "9e03a603-ac6a-42a8-99cf-86c2f353436c",
  "consultation_type_id": "832eda7c-de59-48c7-9985-232710675a20"
}
```

**Request Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | string (UUID) | Yes | Doctor's UUID |
| `template_id` | string (UUID) | Yes | Template to activate |
| `consultation_type_id` | string (UUID) | Yes | Consultation type for this template |

**Response:**
```json
{
  "success": true,
  "is_active": true,
  "message": "Template activated successfully",
  "activated_template_id": "9e03a603-...",
  "deactivated_previous": true
}
```

**Note:** Activating a new template automatically deactivates the previously active template for that consultation type.

---

#### 7.3 Deactivate Template for Doctor

Deactivate a template (remove from doctor's active templates).

| Property | Value |
|----------|-------|
| **Method** | `POST` |
| **URL** | `/api/v1/doctor-templates/deactivate` |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | string (UUID) | Yes | Doctor's UUID |
| `template_id` | string (UUID) | Yes | Template to deactivate |

**Example:**
```
POST /api/v1/doctor-templates/deactivate?doctor_id=83b3eb65-...&template_id=9e03a603-...
```

**Response:**
```json
{
  "success": true,
  "is_active": false,
  "message": "Template deactivated successfully"
}
```

---

#### 7.4 Clone and Activate Template (with Custom Name)

Clone a template with a custom name and activate it for the doctor.

| Property | Value |
|----------|-------|
| **Method** | `POST` |
| **URL** | `/api/v1/summary/templates/{consultation_type_code}/activate/{template_code}` |
| **Content-Type** | `application/json` |

**Path Parameters:**
| Parameter | Description |
|-----------|-------------|
| `consultation_type_code` | Consultation type (e.g., `OP`, `DISCHARGE`) |
| `template_code` | Template code to clone |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | string (UUID) | Yes | Doctor's UUID |

**Request Body:**
```json
{
  "custom_name": "My Psychiatry Template"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Template 'My Psychiatry Template' cloned and activated for OP",
  "template": {
    "id": "original-template-id",
    "template_code": "PSYCHIATRY_CORE",
    "template_name": "Psychiatry Core"
  },
  "cloned_template": {
    "id": "new-cloned-id",
    "template_code": "PSYCHIATRY_CORE_CLONE_83b3eb65",
    "template_name": "My Psychiatry Template",
    "doctor_id": "83b3eb65-..."
  },
  "activation": {
    "is_active": true
  }
}
```

---

## Complete Recording Flow

### Flow Diagram

```
┌─────────────────┐
│  1. GET Doctors │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│ 2. GET Templates        │
│    (with doctor_id)     │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ 3. GET Processing Modes │
│    (optional)           │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ 4. POST /recording/start        │
│    → Returns correlation_id     │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ 5. Start Recording Audio        │
│    (Frontend/Mobile)            │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ 6. POST /recording/chunk        │◄──┐
│    chunk_index: 0, is_last: false│   │
└────────┬────────────────────────┘   │
         │                            │
         └──────── Repeat ────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ 7. POST /recording/chunk        │
│    is_last: true                │
│    → Returns submission_id      │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ 8. GET /processing/{id}/stream  │
│    (SSE for progress)           │
│    OR                           │
│    GET /status/{id} (polling)   │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ 9. Receive Results              │
│    - transcript                 │
│    - insights (extracted data)  │
│    - metrics (timing)           │
└─────────────────────────────────┘
```

### Code Example (JavaScript/React Native)

```javascript
class MedicalRecordingService {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

  // Step 1: Get doctor's templates
  async getTemplates(doctorId) {
    const response = await fetch(
      `${this.baseUrl}/api/v1/summary/templates?doctor_id=${doctorId}&filter_type=doctor`
    );
    const data = await response.json();
    return data.templates;
  }

  // Step 2: Start recording session
  async startRecording(doctorId, patientId, templateCode) {
    const response = await fetch(`${this.baseUrl}/api/v1/option1/recording/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        doctor_id: doctorId,
        patient_id: patientId,
        template_code: templateCode,
        processing_mode: 'default',
        extraction_mode: 'full'
      })
    });
    const data = await response.json();
    return data.correlation_id;
  }

  // Step 3: Upload audio chunk
  async uploadChunk(correlationId, chunkIndex, audioBase64, isLast) {
    const response = await fetch(`${this.baseUrl}/api/v1/option1/recording/chunk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        correlation_id: correlationId,
        chunk_index: chunkIndex,
        audio_data: audioBase64,
        mime_type: 'audio/webm',
        is_last: isLast
      })
    });
    const data = await response.json();
    return data;
  }

  // Step 4: Stream results via SSE
  streamResults(submissionId, onProgress, onComplete, onError) {
    const eventSource = new EventSource(
      `${this.baseUrl}/api/v1/option1/recording/processing/${submissionId}/stream`
    );

    eventSource.addEventListener('progress', (e) => {
      onProgress(JSON.parse(e.data));
    });

    eventSource.addEventListener('complete', (e) => {
      onComplete(JSON.parse(e.data));
      eventSource.close();
    });

    eventSource.addEventListener('error', (e) => {
      onError(JSON.parse(e.data));
      eventSource.close();
    });

    return eventSource;
  }
}

// Usage
const service = new MedicalRecordingService('http://localhost:8000');

async function recordConsultation() {
  const doctorId = '83b3eb65-6801-4bc5-b565-dd3dee2be70a';
  const patientId = 'P001';

  // Get templates and let user select
  const templates = await service.getTemplates(doctorId);
  const selectedTemplate = templates[0].template_code;

  // Start session
  const correlationId = await service.startRecording(doctorId, patientId, selectedTemplate);

  // Record and upload chunks (implementation depends on your audio library)
  // ... recording logic ...

  // When recording stops, upload final chunk
  const result = await service.uploadChunk(correlationId, 5, lastChunkBase64, true);

  // Stream results
  service.streamResults(
    result.submissionId,
    (progress) => console.log(`Progress: ${progress.progress}%`),
    (complete) => {
      console.log('Transcript:', complete.transcript);
      console.log('Insights:', complete.insights);
    },
    (error) => console.error('Error:', error.message)
  );
}
```

---

## Transcript-Only Flow

Use this flow when you already have a transcript (from external transcription or client-side speech recognition).

### Flow Diagram

```
┌─────────────────────────────────┐
│ 1. POST /live/session           │
│    (Create session)             │
│    → Returns correlation_id     │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ 2. POST /summary/extract        │
│    (Submit transcript)          │
│    correlation_id + transcript  │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ 3. Receive Results              │
│    - insights (extracted data)  │
│    - extraction_id              │
│    - metadata                   │
└─────────────────────────────────┘
```

### Code Example (JavaScript)

```javascript
class TranscriptExtractionService {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

  // Step 1: Create live session
  async createSession(doctorId, patientId, templateCode) {
    const response = await fetch(`${this.baseUrl}/api/v1/option1/recording/live/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        doctor_id: doctorId,
        patient_id: patientId,
        template_code: templateCode,
        processing_mode: 'default'
      })
    });
    const data = await response.json();
    return data.correlation_id;
  }

  // Step 2: Extract from transcript
  async extractFromTranscript(correlationId, transcript, templateCode, mode = 'full') {
    const response = await fetch(`${this.baseUrl}/api/v1/summary/extract`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        correlation_id: correlationId,
        transcript: transcript,
        template_code: templateCode,
        mode: mode
      })
    });
    return await response.json();
  }
}

// Usage
const service = new TranscriptExtractionService('http://localhost:8000');

async function extractFromExternalTranscript() {
  const doctorId = '83b3eb65-6801-4bc5-b565-dd3dee2be70a';
  const patientId = 'P001';
  const templateCode = 'OP_SHORT';

  // Your transcript from external source
  const transcript = `
    Patient presents with headache for 3 days.
    Pain is throbbing, located in frontal region.
    Associated symptoms include nausea and photophobia.
    No history of migraine. No recent head injury.
    Vital signs normal. Neurological exam unremarkable.
    Diagnosis: Tension-type headache.
    Prescribed: Paracetamol 500mg TID for 5 days.
    Advised rest and hydration. Follow-up in 1 week if no improvement.
  `;

  // Create session
  const correlationId = await service.createSession(doctorId, patientId, templateCode);
  console.log('Session created:', correlationId);

  // Extract insights
  const result = await service.extractFromTranscript(correlationId, transcript, templateCode);

  console.log('Extraction ID:', result.metadata.extraction_id);
  console.log('Insights:', result.data);
}
```

---

## Response Examples

### Successful Extraction (insights structure)

The `insights` object structure depends on the template used. Here's an example for an OP (Outpatient) template:

```json
{
  "chief_complaints": {
    "complaints": ["Headache", "Dizziness"],
    "duration": "3 days",
    "severity": "Moderate"
  },
  "history_of_present_illness": {
    "narrative": "Patient reports onset of headache 3 days ago...",
    "associated_symptoms": ["Nausea", "Light sensitivity"]
  },
  "physical_examination": {
    "general_appearance": "Alert, oriented, mild distress",
    "vital_signs": {
      "blood_pressure": "130/85 mmHg",
      "pulse": "78 bpm",
      "temperature": "98.6°F"
    }
  },
  "diagnosis": {
    "primary_diagnosis": "Migraine without aura",
    "icd_code": "G43.909",
    "differential_diagnoses": ["Tension-type headache", "Cluster headache"]
  },
  "prescription": [
    {
      "medication": "Sumatriptan",
      "dosage": "50mg",
      "route": "Oral",
      "frequency": "PRN",
      "duration": "As needed",
      "instructions": "Take at onset of migraine"
    }
  ],
  "advice_and_followup": {
    "lifestyle_advice": ["Maintain regular sleep schedule", "Avoid known triggers"],
    "followup": "Review in 2 weeks if symptoms persist"
  }
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request (invalid parameters) |
| 404 | Not Found (session/job not found) |
| 500 | Internal Server Error |

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "Recording session not found" | Invalid correlation_id | Start a new session |
| "Doctor must have at least one active template" | No templates activated | Activate templates for doctor |
| "Template 'X' not found in doctor's active templates" | Template not activated | Use an activated template |
| "Cannot upload chunk. Session status: X" | Session already submitted/cancelled | Start new session |

---

## Webhook Integration (Optional)

If you want to receive results via webhook instead of SSE/polling, configure webhook URLs in the backend. When extraction completes, the backend will POST results to your webhook endpoint.

**Webhook Payload:**
```json
{
  "event": "extraction_complete",
  "submission_id": "1a710145-fc94-445e-8863-c1772e68c128",
  "session_id": "d901aaea-a5cc-4259-8ffa-f9b402b9f92f",
  "correlation_id": "ff3b1cd7-cda1-4cfe-a976-5a837587af56",
  "doctor_id": "83b3eb65-6801-4bc5-b565-dd3dee2be70a",
  "patient_id": "P001",
  "template_code": "OP_SHORT",
  "transcript": "Patient presents with...",
  "insights": { ... },
  "metrics": {
    "stitching_time_seconds": 0.5,
    "transcription_time_seconds": 8.2,
    "extraction_time_seconds": 12.4,
    "total_processing_time_seconds": 21.1
  },
  "timestamp": "2025-11-27T15:30:45.123Z"
}
```

---

## Support

For questions or issues:
- Check API documentation at `http://localhost:8000/docs` (Swagger UI)
- Review backend logs for detailed error information


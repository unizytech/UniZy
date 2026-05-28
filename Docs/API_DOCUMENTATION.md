# API Documentation

This document covers the following API endpoints and webhook configurations:

1. [Extraction Edit API](#1-extraction-edit-api) - Save doctor edits to `edited_extraction_json`
2. [Emotion Analysis API & Webhooks](#2-emotion-analysis-api--webhooks) - Retrieve and receive emotion analysis
3. [Recommended Interventions API & Webhooks](#3-recommended-interventions-api--webhooks) - Patient intervention recommendations
4. [Medicine List Upload API](#4-medicine-list-upload-api) - Upload doctor/hospital medicine lists
5. [Investigation List Upload API](#5-investigation-list-upload-api) - Upload doctor/hospital investigation lists
6. [Feedback Review APIs](#6-feedback-review-apis) - Review and submit feedback on AI matching

---

## Base URL

```
http://localhost:8000  (development)
https://your-domain.com  (production)
```

---

## 1. Extraction Edit API

Store doctor's corrections/edits to AI-extracted medical data while preserving the original extraction.

### PUT `/api/v1/extractions/{extraction_id}`

Update extraction with doctor's edits.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `extraction_id` | UUID | Yes | The extraction UUID |

**Request Body:**
```json
{
  "edited_data": {
    "chief_complaints": "Updated chief complaints...",
    "diagnosis": "Corrected diagnosis...",
    "prescription": {
      "medications": [...]
    }
  },
  "edited_by": "doctor-uuid-here"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `edited_data` | object | Yes | Complete edited extraction JSON |
| `edited_by` | string (UUID) | Yes | Doctor UUID who made edits |

**Response:**
```json
{
  "success": true,
  "message": "Extraction updated successfully. Edit count: 1",
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "edit_count": 1,
  "last_edited_at": "2025-12-08T10:30:00Z",
  "medicine_feedback_scheduled": true
}
```

**Behavior:**
- Stores `edited_data` in `edited_extraction_json` column
- Increments `edit_count`
- Updates `last_edited_at` and `last_edited_by`
- **Does NOT modify** `original_extraction_json` (AI-generated data preserved)
- Schedules background task to compare medicine name changes and log feedback

---

### PUT `/api/v1/extractions/by-submission/{submission_id}`

Update extraction using submission_id (alternative lookup method).

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `submission_id` | UUID | Yes | The submission UUID from recording workflow |

**Request Body:** Same as above

**Response:** Same as above

---

### GET `/api/v1/extractions/{extraction_id}/compare`

Compare original AI-generated extraction vs latest edited version.

**Response:**
```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "original": {
    "chief_complaints": "Original from AI...",
    "diagnosis": "AI diagnosis..."
  },
  "edited": {
    "chief_complaints": "Doctor corrected...",
    "diagnosis": "Corrected diagnosis..."
  },
  "has_edits": true,
  "edit_count": 2,
  "last_edited_at": "2025-12-08T10:30:00Z",
  "last_edited_by": "doctor-uuid"
}
```

**Use Cases:**
- Review doctor edits vs AI output
- Audit trail for compliance
- Quality assurance
- Training data for model improvement

---

### GET `/api/v1/extractions/{extraction_id}/original`

Get ONLY the original AI-generated extraction (ignores edits).

**Response:**
```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "original_data": { ... },
  "has_edits": true,
  "edit_count": 2
}
```

---

### GET `/api/v1/extractions/{extraction_id}/edited`

Get ONLY the edited version. Returns 404 if never edited.

**Response:**
```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "edited_data": { ... },
  "edit_count": 2,
  "last_edited_at": "2025-12-08T10:30:00Z",
  "last_edited_by": "doctor-uuid"
}
```

---

## 2. Emotion Analysis API & Webhooks

### GET `/api/v1/extractions/{extraction_id}/emotions`

Get emotion analysis results for an extraction (includes interventions).

---

### GET `/api/v1/extractions/by-submission/{submission_id}/emotions`

Get emotion analysis results by submission_id (alternative lookup method).

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `submission_id` | UUID | Yes | The submission UUID from recording workflow |

**Response:** Same as `/{extraction_id}/emotions`

**Use Cases:**
- Frontend fallback when extraction_id is not available
- Historical lookups by submission_id
- Error recovery scenarios

---

### Emotion Analysis Response (Both Endpoints)

**Response:**
```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440000",
  "text_emotions": [
    {
      "segment_code": "ANXIETY_PRE_CONSULTATION",
      "segment_name": "Anxiety Pre Consultation",
      "segment_data": {
        "level": "moderate",
        "indicators": ["rapid speech", "mentions worry"],
        "confidence": 0.85
      },
      "confidence": 0.85,
      "created_at": "2025-12-08T10:30:00Z"
    },
    {
      "segment_code": "ANXIETY_POST_CONSULTATION",
      "segment_name": "Anxiety Post Consultation",
      "segment_data": { ... }
    }
  ],
  "audio_emotions": [
    {
      "segment_code": "AUDIO_PATIENT_ANXIETY",
      "segment_name": "Audio Patient Anxiety",
      "segment_data": {
        "level": "high",
        "voice_indicators": ["trembling voice", "rapid pace"]
      }
    }
  ],
  "congruence": {
    "segment_code": "EMOTION_CONGRUENCE_ANALYSIS",
    "segment_name": "Emotion Congruence Analysis",
    "segment_data": {
      "congruence_score": 0.72,
      "discrepancies": [...],
      "recommendations": [...]
    }
  },
  "interventions": [
    {
      "id": "intervention-uuid",
      "code": "ANXIETY_COUNSELING",
      "name": "Anxiety Counseling",
      "description": "Patient shows elevated anxiety levels...",
      "category": "mental_health",
      "priority": "high",
      "priority_score": 85,
      "trigger_reason": "Pre-consultation anxiety level: high",
      "is_top_3": true,
      "analysis_mode": "combined",
      "rationale_sources": ["ANXIETY_PRE_CONSULTATION", "AUDIO_PATIENT_ANXIETY"]
    }
  ],
  "emotion_extraction_started": true,
  "audio_emotion_extraction_started": true,
  "congruence_analysis_started": true,
  "emotion_extraction_completed": true,
  "audio_emotion_extraction_completed": true,
  "congruence_analysis_completed": true
}
```

**Text Emotion Segments:**
| Segment Code | Description |
|--------------|-------------|
| `ANXIETY_PRE_CONSULTATION` | Patient anxiety level before consultation |
| `ANXIETY_POST_CONSULTATION` | Patient anxiety level after consultation |
| `OTHER_EMOTIONS_DETECTED` | Additional emotions (fear, frustration, etc.) |
| `FINANCIAL_CONCERNS` | Financial stress indicators |
| `TREATMENT_COMPLIANCE_LIKELIHOOD` | Likelihood patient will follow treatment |
| `DOCTOR_COMMUNICATION_STYLE` | Doctor's communication effectiveness |

**Audio Emotion Segments:**
| Segment Code | Description |
|--------------|-------------|
| `AUDIO_PATIENT_ANXIETY` | Voice-based patient anxiety analysis |
| `AUDIO_DOCTOR_STYLE` | Voice-based doctor style analysis |
| `AUDIO_INTERACTION_DYNAMICS` | Conversation dynamics analysis |
| `AUDIO_FINANCIAL_CONCERNS` | Financial stress from voice cues |
| `AUDIO_COMPLIANCE_INDICATORS` | Compliance signals from voice |
| `AUDIO_OTHER_EMOTIONS` | Other voice-detected emotions |

---

### Emotion Analysis Webhook

The system automatically sends emotion analysis results to configured webhook endpoints.

**Environment Variables:**
```env
WEBHOOK_URL=https://your-endpoint.com/webhook,https://backup-endpoint.com/webhook
WEBHOOK_TOKEN=your-bearer-token
WEBHOOK_ENABLED=true
WEBHOOK_TIMEOUT=10
```

**Webhook Payload (Emotion Analysis):**
```json
{
  "type": "emotion_analysis",
  "emotion_data": {
    "text_emotions": [
      {
        "segment_code": "ANXIETY_PRE_CONSULTATION",
        "segment_value": { ... }
      }
    ],
    "audio_emotions": [
      {
        "segment_code": "AUDIO_PATIENT_ANXIETY",
        "segment_value": { ... }
      }
    ],
    "recommended_interventions": {
      "total_count": 5,
      "top_recommendations": [
        {
          "code": "ANXIETY_COUNSELING",
          "name": "Anxiety Counseling",
          "priority": "high",
          "priority_score": 85
        }
      ],
      "all_interventions": [ ... ]
    }
  },
  "session_info": {
    "extraction_id": "extraction-uuid",
    "submission_id": "submission-uuid",
    "doctor_id": "doctor-uuid",
    "patient_id": "patient-uuid",
    "consultation_type_code": "OP",
    "consultation_type_name": "Outpatient",
    "emotion_mode": "text_only"
  },
  "metadata": {
    "timestamp": "2025-12-08T10:30:00.000Z",
    "source": "emotion_extraction",
    "version": "3.1.0",
    "emotion_mode": "text_only"
  }
}
```

---

### Congruence Analysis Webhook

Sent when both text and audio emotion analysis complete (emotion_mode = "both").

**Webhook Payload (Congruence Analysis):**
```json
{
  "type": "congruence_analysis",
  "congruence_data": {
    "congruence_score": 0.72,
    "overall_assessment": "Moderate alignment between verbal and vocal cues",
    "comparisons": {
      "anxiety": {
        "text_level": "moderate",
        "audio_level": "high",
        "difference": 1,
        "interpretation": "Voice shows higher anxiety than words suggest"
      }
    },
    "clinical_implications": [ ... ],
    "recommended_interventions": [ ... ]
  },
  "emotion_data": {
    "text_emotions": [ ... ],
    "audio_emotions": [ ... ]
  },
  "recommended_interventions": {
    "total_count": 7,
    "top_recommendations": [ ... ],
    "all_interventions": [ ... ]
  },
  "session_info": {
    "extraction_id": "extraction-uuid",
    "emotion_mode": "both"
  },
  "metadata": {
    "timestamp": "2025-12-08T10:30:00.000Z",
    "source": "congruence_analysis",
    "version": "3.1.0"
  }
}
```

---

### Configure Emotion Analysis Mode

**PATCH `/api/v1/summary/admin/consultation-types/{consultation_type_code}/emotion-mode`**

Update emotion extraction mode for a consultation type.

**Query Parameters:**
| Parameter | Type | Values | Description |
|-----------|------|--------|-------------|
| `emotion_extraction_mode` | string | `none`, `text_only`, `audio_only`, `both` | Emotion extraction mode |

**Emotion Modes:**
| Mode | Description |
|------|-------------|
| `none` | No emotion extraction |
| `text_only` | Only transcript-based emotion analysis (6 segments) |
| `audio_only` | Only audio/voice-based emotion analysis (6 segments) |
| `both` | Run both and compare (enables congruence analysis) |

**Response:**
```json
{
  "success": true,
  "message": "Emotion extraction mode updated to 'both' for OP",
  "consultation_type_code": "OP",
  "emotion_extraction_mode": "both"
}
```

---

## 3. Recommended Interventions

> **Note:** Interventions do NOT have a separate API endpoint. They are:
> 1. **Included in the Emotion Analysis API response** - `GET /api/v1/extractions/{extraction_id}/emotions` and `GET /api/v1/extractions/by-submission/{submission_id}/emotions`
> 2. **Sent via webhooks** - Included in both `emotion_analysis` and `congruence_analysis` webhook payloads

Interventions are automatically generated based on emotion analysis results.

### Intervention Response Schema

```json
{
  "id": "intervention-uuid",
  "code": "ANXIETY_COUNSELING",
  "name": "Anxiety Counseling Referral",
  "description": "Patient demonstrates elevated anxiety requiring professional support",
  "category": "mental_health",
  "priority": "high",
  "priority_score": 85,
  "trigger_reason": "Pre-consultation anxiety: high, Audio anxiety indicators detected",
  "is_top_3": true,
  "analysis_mode": "combined",
  "rationale_sources": [
    "ANXIETY_PRE_CONSULTATION",
    "AUDIO_PATIENT_ANXIETY"
  ],
  "created_at": "2025-12-08T10:30:00Z"
}
```

**Priority Levels:**
| Priority | Score Range | Description |
|----------|-------------|-------------|
| `critical` | 90-100 | Requires immediate action |
| `high` | 70-89 | Should be addressed soon |
| `medium` | 40-69 | Can be scheduled |
| `low` | 0-39 | Optional/preventive |

**Intervention Categories:**
- `mental_health` - Anxiety, depression, stress management
- `communication` - Patient-doctor communication improvement
- `compliance` - Treatment adherence support
- `financial` - Financial counseling/assistance programs
- `general` - General wellness recommendations

**Analysis Modes:**
| Mode | Description |
|------|-------------|
| `text_only` | Generated from transcript analysis only |
| `audio_only` | Generated from voice analysis only |
| `combined` | Generated from congruence analysis (both) |

---

## 4. Medicine List Upload API

Upload doctor or hospital medicine lists for prompt injection and post-processing matching.

### POST `/api/v1/medicines/{doctor_id}/upload`

Upload CSV file with medicines for a doctor.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | UUID | Yes | Doctor UUID |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `replace_existing` | boolean | false | Replace all existing medicines |

**Request:** `multipart/form-data`
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | Yes | CSV file (UTF-8 encoded) |

**CSV Format:**
```csv
name,common_name,category,typical_dosage,form,snomed_code,formulary_name,type
Paracetamol,"Crocin, Dolo, Calpol",Analgesic,500mg,tablet,387517004,Paracetamol 500mg,generic
Amoxicillin,"Amoxil, Mox",Antibiotic,500mg TID,capsule,372687004,Amoxicillin 500mg,branded
```

**CSV Columns:**
| Column | Required | Description |
|--------|----------|-------------|
| `name` | Yes | Primary medicine name |
| `common_name` | No | Comma-separated alternative names/brands |
| `category` | No | Medicine category (Antibiotic, Analgesic, etc.) |
| `typical_dosage` | No | Common dosage |
| `form` | No | Form (tablet, capsule, syrup, injection) |
| `snomed_code` | No | SNOMED CT code |
| `formulary_name` | No | Hospital formulary name |
| `type` | No | generic, branded, compound |

**Response:**
```json
{
  "success": true,
  "message": "Uploaded 150 medicines",
  "uploaded_count": 150,
  "skipped_count": 2,
  "errors": [
    {"row": 45, "error": "Duplicate medicine name"}
  ]
}
```

---

### POST `/api/v1/medicines/hospital/{hospital_id}/upload`

Upload CSV file with medicines for a hospital.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hospital_id` | UUID | Yes | Hospital UUID |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `created_by` | UUID | Yes | Admin doctor ID |
| `replace_existing` | boolean | No | Replace all existing medicines |

**Request:** Same CSV format as doctor upload

**Response:** Same as doctor upload

---

## 5. Investigation List Upload API

Upload doctor or hospital investigation lists for prompt injection and post-processing matching.

### POST `/api/v1/investigations/{doctor_id}/upload`

Upload CSV file with investigations for a doctor.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | UUID | Yes | Doctor UUID |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `replace_existing` | boolean | false | Replace all existing investigations |

**Request:** `multipart/form-data`
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | Yes | CSV file (UTF-8 encoded) |

**CSV Format:**
```csv
name,common_names,type,category,normal_range,loinc_code,cpt_code
Complete Blood Count,"CBC, hemogram, blood count",laboratory,Hematology,"WBC: 4.5-11.0 x10^9/L",58410-2,85025
X-Ray Chest PA View,"chest x-ray, CXR",imaging,Radiology,,71010
ECG,"EKG, electrocardiogram",other,Cardiology,,,93000
```

**CSV Columns:**
| Column | Required | Description |
|--------|----------|-------------|
| `name` | Yes | Primary investigation name |
| `common_names` | No | Comma-separated alternative names |
| `type` | Yes | `laboratory`, `imaging`, or `other` |
| `category` | No | Category (Hematology, Radiology, Cardiology, etc.) |
| `normal_range` | No | Reference range for lab tests |
| `loinc_code` | No | LOINC code for lab tests |
| `cpt_code` | No | CPT procedure code |

**Response:**
```json
{
  "success": true,
  "message": "Uploaded 98 investigations",
  "uploaded_count": 98,
  "skipped_count": 0,
  "errors": []
}
```

---

### POST `/api/v1/investigations/hospital/{hospital_id}/upload`

Upload CSV file with investigations for a hospital.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hospital_id` | UUID | Yes | Hospital UUID |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `created_by` | UUID | Yes | Admin doctor ID |
| `replace_existing` | boolean | No | Replace all existing investigations |

**Request:** Same CSV format as doctor upload

**Response:** Same as doctor upload

---

## 6. Feedback Review APIs

Review and submit feedback on AI matching for medicines and investigations.

### Medicine Feedback

#### GET `/api/v1/medicines/feedback/{doctor_id}/pending`

Get all medicine matches pending feedback for a doctor.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doctor_id` | UUID | Yes | Doctor UUID |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 100 | Maximum records to return |
| `offset` | int | 0 | Pagination offset |

**Response:**
```json
{
  "records": [
    {
      "id": "match-log-uuid",
      "original_medicine_name": "Amoxicillin 500",
      "matched_medicine_name": "Amoxicillin 500mg",
      "matched_medicine_id": "medicine-uuid",
      "match_confidence": 0.95,
      "match_method": "fuzzy_doctor",
      "match_source": "doctor_list",
      "extraction_id": "extraction-uuid",
      "submission_id": "submission-uuid",
      "created_at": "2025-12-08T10:30:00Z"
    }
  ],
  "count": 25,
  "limit": 100,
  "offset": 0
}
```

---

#### GET `/api/v1/medicines/feedback/{doctor_id}/history`

Get feedback history with filters.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `feedback_status` | string | Filter by `agreed` or `disagreed` |
| `confidence_min` | float | Minimum confidence (0.0-1.0) |
| `confidence_max` | float | Maximum confidence (0.0-1.0) |
| `source` | string | Filter by `doctor_list` or `hospital_list` |
| `search` | string | Search term for medicine names |
| `limit` | int | Maximum records (default: 100) |
| `offset` | int | Pagination offset |

**Response:**
```json
{
  "records": [
    {
      "id": "match-log-uuid",
      "original_medicine_name": "Amoxicillin 500",
      "matched_medicine_name": "Amoxicillin 500mg",
      "feedback_status": "agreed",
      "feedback_at": "2025-12-08T11:00:00Z",
      "match_confidence": 0.95
    }
  ],
  "total_count": 150,
  "limit": 100,
  "offset": 0
}
```

---

#### POST `/api/v1/medicines/feedback/{match_log_id}`

Submit feedback for a medicine match.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `match_log_id` | UUID | Yes | Match log entry UUID |

**Request Body:**
```json
{
  "feedback_status": "agreed",
  "correct_medicine_id": null,
  "correct_medicine_name": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `feedback_status` | string | Yes | `agreed` or `disagreed` |
| `correct_medicine_id` | UUID | No | Correct medicine UUID if disagreed |
| `correct_medicine_name` | string | No | Manual entry if disagreed and not in list |

**Response:**
```json
{
  "message": "Feedback submitted",
  "result": {
    "id": "match-log-uuid",
    "feedback_status": "agreed",
    "feedback_at": "2025-12-08T11:00:00Z"
  }
}
```

**Side Effects:**
- If `agreed` with a hospital match, the medicine is auto-copied to doctor's personal list

---

#### POST `/api/v1/medicines/feedback/bulk-agree`

Bulk agree with multiple matches.

**Request Body:**
```json
["match-log-uuid-1", "match-log-uuid-2", "match-log-uuid-3"]
```

**Response:**
```json
{
  "results": [
    {"id": "match-log-uuid-1", "status": "success"},
    {"id": "match-log-uuid-2", "status": "success"},
    {"id": "match-log-uuid-3", "status": "error", "message": "Match not found"}
  ],
  "success_count": 2,
  "error_count": 1
}
```

---

### Investigation Feedback

#### GET `/api/v1/investigations/feedback/{doctor_id}/pending`

Get all investigation matches pending feedback for a doctor.

**Query Parameters:** Same as medicine pending feedback

**Response:** Same structure as medicine pending feedback

---

#### GET `/api/v1/investigations/feedback/{doctor_id}/history`

Get investigation feedback history with filters.

**Additional Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `investigation_type` | string | Filter by `laboratory`, `imaging`, or `other` |

**Response:** Same structure as medicine feedback history

---

#### POST `/api/v1/investigations/feedback/{match_log_id}`

Submit feedback for an investigation match.

**Request Body:**
```json
{
  "feedback_status": "disagreed",
  "correct_investigation_id": "investigation-uuid",
  "correct_investigation_name": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `feedback_status` | string | Yes | `agreed` or `disagreed` |
| `correct_investigation_id` | UUID | No | Correct investigation UUID if disagreed |
| `correct_investigation_name` | string | No | Manual entry if disagreed and not in list |

**Response:** Same as medicine feedback

---

#### POST `/api/v1/investigations/feedback/bulk-agree`

Bulk agree with multiple matches.

**Request/Response:** Same as medicine bulk agree

---

## Matching Algorithm

Both medicine and investigation matching use a 7-level priority system:

| Priority | Method | Confidence | Description |
|----------|--------|------------|-------------|
| 1 | `feedback_agreed` | 95% | Previous doctor feedback match |
| 2 | `exact_doctor` | 100% | Exact match in doctor's list |
| 3 | `common_name_doctor` | 98% | Common name match in doctor's list |
| 4 | `exact_hospital` | 90% | Exact match in hospital list |
| 5 | `common_name_hospital` | 88% | Common name match in hospital list |
| 6 | `fuzzy_doctor` | 85-95% | Fuzzy match (≥90% similarity) in doctor's list |
| 7 | `fuzzy_hospital` | 81-90% | Fuzzy match (≥90% similarity) in hospital list |
| 8 | `no_match` | 0% | Keep original AI extraction |

---

## Webhook Configuration

### Environment Variables

```env
# Webhook endpoints (comma-separated for multiple)
WEBHOOK_URL=https://primary.example.com/webhook,https://backup.example.com/webhook

# Bearer token for Authorization header
WEBHOOK_TOKEN=your-secret-token

# Enable/disable webhooks
WEBHOOK_ENABLED=true

# Request timeout in seconds
WEBHOOK_TIMEOUT=10
```

### Webhook Headers

All webhook requests include:
```
Authorization: Bearer {WEBHOOK_TOKEN}
Content-Type: application/json
```

### Retry Logic

- Maximum 3 retry attempts
- Exponential backoff between retries
- Sends to all configured URLs in parallel
- Success if at least one URL receives the payload

---

## Error Responses

All endpoints return standard error responses:

```json
{
  "detail": "Error message here"
}
```

**HTTP Status Codes:**
| Code | Description |
|------|-------------|
| 400 | Bad Request - Invalid input |
| 404 | Not Found - Resource not found |
| 500 | Internal Server Error |

---

## Sample Code

### Python - Upload Medicine CSV

```python
import requests

url = "http://localhost:8000/api/v1/medicines/{doctor_id}/upload"
files = {"file": open("medicines.csv", "rb")}
params = {"replace_existing": "false"}

response = requests.post(url, files=files, params=params)
print(response.json())
```

### JavaScript - Submit Feedback

```javascript
const submitFeedback = async (matchLogId, status) => {
  const response = await fetch(
    `http://localhost:8000/api/v1/medicines/feedback/${matchLogId}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        feedback_status: status,
        correct_medicine_id: null,
        correct_medicine_name: null
      })
    }
  );
  return response.json();
};
```

### cURL - Get Emotion Analysis

```bash
curl -X GET "http://localhost:8000/api/v1/extractions/{extraction_id}/emotions"
```

---

## 7. Merge Extractions API

Merge multiple medical extractions into a single consolidated output using AI-powered contextual merging.

### POST `/api/v1/extractions/merge`

Merge multiple extractions and save the result.

**⚠️ ASYNC BEHAVIOR (v3.5.0+):**
- This endpoint returns **immediately** with an `extraction_id`
- The merge processing happens in the **background**
- Use `GET /merge/status/{extraction_id}` to poll for completion
- A **webhook** is sent when the merge completes (with the same `extraction_id`)

**Request Body:**
```json
{
  "source_extraction_ids": ["uuid1", "uuid2"],
  "target_consultation_type_code": "OP",
  "doctor_id": "doctor-uuid",
  "merge_notes": "Follow-up consolidation",
  "uploaded_json": null
}
```

Or using submission_ids (will be resolved to extraction_ids):
```json
{
  "source_submission_ids": ["submission-uuid1", "submission-uuid2"],
  "target_consultation_type_code": "DISCHARGE",
  "doctor_id": "doctor-uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_extraction_ids` | string[] | Yes* | List of extraction UUIDs to merge |
| `source_submission_ids` | string[] | Yes* | Alternative: List of submission UUIDs (resolved to extraction_ids) |
| `target_consultation_type_code` | string | Yes | Target schema (OP, DISCHARGE, OPHTHALMOLOGY, etc.) |
| `doctor_id` | string | Yes | Doctor UUID performing the merge |
| `merge_notes` | string | No | Optional notes about the merge |
| `uploaded_json` | object | No | Optional uploaded JSON to include in merge |

*Use either `source_extraction_ids` OR `source_submission_ids`, not both.

**Response (HTTP 202 Accepted):**
```json
{
  "success": true,
  "extraction_id": "pre-generated-uuid",
  "status": "processing",
  "message": "Merge operation started. Use extraction_id to check status or receive webhook."
}
```

**Response Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Whether merge was accepted for processing |
| `extraction_id` | string (UUID) | **Pre-generated** extraction ID - use this for polling and webhook matching |
| `status` | string | Current status: `processing` |
| `message` | string | Informational message |

> **Important:** The `extraction_id` returned is pre-generated and will be the same ID used when:
> 1. Polling via `GET /merge/status/{extraction_id}`
> 2. Receiving the completion webhook
> 3. Fetching the merged extraction via `GET /api/v1/extractions/{extraction_id}`

---

### GET `/api/v1/extractions/merge/status/{extraction_id}`

Check the status of a merge operation.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `extraction_id` | UUID | Yes | The extraction UUID returned from `/merge` |

**Response (Processing):**
```json
{
  "extraction_id": "uuid",
  "status": "processing",
  "progress": "Merge in progress...",
  "merged_data": null,
  "merge_metadata": null,
  "error": null,
  "created_at": "2025-12-09T10:30:00Z",
  "completed_at": null
}
```

**Response (Completed):**
```json
{
  "extraction_id": "uuid",
  "status": "completed",
  "progress": null,
  "merged_data": {
    "chief_complaints": "...",
    "diagnosis": "...",
    "prescription": { ... }
  },
  "merge_metadata": {
    "source_count": 2,
    "target_type_code": "OP",
    "merge_timestamp": "2025-12-09T10:30:00Z",
    "doctor_confirmed": true,
    "merge_notes": "Follow-up consolidation",
    "conflict_count": 3,
    "conflicts_resolved": ["vital_signs", "current_diagnosis", "medications"],
    "cross_type_scenario": "WITHIN_OP_FAMILY",
    "consultation_types_merged": ["OP", "OP_CONCISE"]
  },
  "error": null,
  "created_at": "2025-12-09T10:30:00Z",
  "completed_at": "2025-12-09T10:31:15Z"
}
```

**Response (Failed):**
```json
{
  "extraction_id": "uuid",
  "status": "failed",
  "progress": null,
  "merged_data": null,
  "merge_metadata": null,
  "error": "Validation failed: All source extractions must belong to the same patient",
  "created_at": "2025-12-09T10:30:00Z",
  "completed_at": null
}
```

**Status Values:**
| Status | Description |
|--------|-------------|
| `processing` | Merge is in progress (validation, AI processing, saving) |
| `completed` | Merge finished successfully - `merged_data` and `merge_metadata` available |
| `failed` | Merge failed - check `error` field for details |

---

### Typical Flow

1. **Client calls `/merge`** → Receives `extraction_id` immediately (HTTP 202)
2. **Client can either:**
   - **Poll** `GET /merge/status/{extraction_id}` until `status === "completed"`
   - **Wait for webhook** with matching `extraction_id`
3. **Once completed:**
   - Use `GET /api/v1/extractions/{extraction_id}` to fetch full extraction
   - Use `GET /api/v1/extractions/{extraction_id}/merge-info` for merge lineage

**Example Polling Code:**
```javascript
const mergeExtractions = async (sourceIds, targetType, doctorId) => {
  // Step 1: Start merge
  const response = await fetch('/api/v1/extractions/merge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source_extraction_ids: sourceIds,
      target_consultation_type_code: targetType,
      doctor_id: doctorId
    })
  });

  const { extraction_id } = await response.json();

  // Step 2: Poll for completion
  while (true) {
    const statusResponse = await fetch(`/api/v1/extractions/merge/status/${extraction_id}`);
    const status = await statusResponse.json();

    if (status.status === 'completed') {
      return status.merged_data;
    } else if (status.status === 'failed') {
      throw new Error(status.error);
    }

    // Wait before polling again
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
};
```

> **Note:** Merged extractions do NOT have a `submission_id` because they are not created through the recording/processing workflow. Use `extraction_id` for lookups.

---

### POST `/api/v1/extractions/merge/preview`

Preview merge without saving to database.

**Request Body:** Same as `/merge` endpoint

**Response:** Same structure with `preview: true` and `extraction_id: null`

**Use Cases:**
- Doctor wants to review merged extraction before committing
- Check for conflicts or missing data before save
- Validate merge quality before final approval

---

### GET `/api/v1/extractions/patient/{patient_id}/timeline`

Get chronological timeline of all extractions for a patient.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `patient_id` | string | Yes | Patient UUID or identifier |

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `consultation_type_code` | string | Filter by consultation type |

**Response:**
```json
{
  "patient_id": "patient-uuid",
  "extractions": [
    {
      "extraction_id": "uuid1",
      "consultation_type_code": "OP",
      "consultation_type_name": "Outpatient Consultation",
      "created_at": "2025-12-08T10:30:00Z",
      "doctor_name": "Dr. Smith",
      "is_merged": false,
      "source_count": null,
      "segment_count": 15
    },
    {
      "extraction_id": "uuid2",
      "consultation_type_code": "DISCHARGE",
      "consultation_type_name": "Discharge Summary",
      "created_at": "2025-12-07T14:00:00Z",
      "doctor_name": "Dr. Smith",
      "is_merged": true,
      "source_count": 3,
      "segment_count": 20
    }
  ],
  "total_count": 2
}
```

---

### GET `/api/v1/extractions/{extraction_id}/merge-info`

Get merge lineage information for a merged extraction.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `extraction_id` | UUID | Yes | The merged extraction UUID |

**Response:**
```json
{
  "merged_extraction_id": "merged-uuid",
  "is_merged": true,
  "source_extractions": [
    {
      "source_extraction_id": "uuid1",
      "consultation_type_code": "OP",
      "consultation_type_name": "Outpatient",
      "created_at": "2025-12-05T10:00:00Z",
      "doctor_name": "Dr. Smith",
      "merge_order": 1,
      "merge_strategy": "ai_contextual"
    },
    {
      "source_extraction_id": "uuid2",
      "consultation_type_code": "OP",
      "consultation_type_name": "Outpatient",
      "created_at": "2025-12-08T10:00:00Z",
      "doctor_name": "Dr. Smith",
      "merge_order": 2,
      "merge_strategy": "ai_contextual"
    }
  ],
  "merge_metadata": {
    "source_count": 2,
    "target_type_code": "OP",
    "merge_timestamp": "2025-12-08T11:00:00Z",
    "doctor_confirmed": true,
    "merge_notes": "Follow-up consolidation",
    "conflict_count": 2,
    "conflicts_resolved": ["vital_signs", "current_diagnosis"]
  }
}
```

**Note:** Returns 400 error if extraction is not a merged extraction (`is_merged=false`).

---

### GET `/api/v1/extractions/by-submission/{submission_id}`

Lookup extraction by submission_id (from recording workflow).

**Response:**
```json
{
  "extraction_id": "uuid",
  "submission_id": "submission-uuid",
  "session_id": "session-uuid",
  "consultation_type_code": "OP",
  "doctor_id": "doctor-uuid",
  "patient_id": "patient-uuid",
  "created_at": "2025-12-08T10:30:00Z",
  "found": true,
  "message": null
}
```

If still processing:
```json
{
  "extraction_id": null,
  "submission_id": "submission-uuid",
  "session_id": "session-uuid",
  "found": false,
  "message": "Processing in progress: EXTRACTING (75%). Extraction not yet available."
}
```

---

### GET `/api/v1/extractions/by-session/{session_id}`

Lookup extraction by session_id (correlation_id from recording start).

**Response:** Same structure as by-submission lookup.

---

### Merge Webhook

When a merge is completed, a webhook is automatically sent with the merged data.

**Webhook Payload:**
```json
{
  "type": "insights",
  "source": "merge",
  "insights": {
    "chief_complaints": "...",
    "diagnosis": "...",
    "prescription": { ... }
  },
  "session_info": {
    "extraction_id": "merged-extraction-uuid",
    "submission_id": null,
    "doctor_id": "doctor-uuid",
    "patient_id": "patient-uuid",
    "template_code": "OP",
    "consultation_type_code": "OP",
    "source_extraction_ids": ["uuid1", "uuid2"],
    "source_count": 2,
    "merge_notes": "Follow-up consolidation",
    "has_uploaded_json": false
  },
  "metadata": {
    "timestamp": "2025-12-08T10:30:00.000Z",
    "source": "merge",
    "version": "3.1.0"
  }
}
```

**Key Differences from Regular Extraction Webhook:**
| Field | Regular Extraction | Merge Extraction |
|-------|-------------------|------------------|
| `source` | `"recording"` or `"direct_extraction"` | `"merge"` |
| `submission_id` | UUID from processing job | `null` |
| `source_extraction_ids` | Not present | List of source UUIDs |
| `source_count` | Not present | Number of merged sources |
| `merge_notes` | Not present | Optional merge notes |
| `has_uploaded_json` | Not present | Whether uploaded JSON was included |

---

## 8. Extraction Retrieval APIs

APIs to retrieve extraction data (works for both regular and merged extractions).

### GET `/api/v1/extractions/{extraction_id}`

Get extraction data by ID. This is the **primary API** for retrieving any extraction, including merged extractions.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `extraction_id` | UUID | Yes | The extraction UUID (returned from merge or recording workflow) |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_segments` | boolean | `true` | Include individual segment data in response |

**Response:**
```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440003",
  "patient_id": "patient-uuid",
  "doctor_id": "doctor-uuid",
  "consultation_type_code": "OP",
  "consultation_type_name": "Outpatient Consultation",
  "extraction_data": {
    "chief_complaints": "Fever and cough for 3 days",
    "diagnosis": "Upper respiratory tract infection",
    "prescription": {
      "medications": [
        {
          "medication_name": "Paracetamol",
          "dosage": "500mg",
          "frequency": "TID",
          "duration": "3 days"
        }
      ]
    }
  },
  "is_edited": false,
  "edit_count": 0,
  "is_merged": true,
  "created_at": "2025-12-08T10:30:00Z",
  "last_edited_at": null,
  "last_edited_by": null,
  "segments": [
    {
      "segment_code": "CHIEF_COMPLAINTS",
      "segment_name": "Chief Complaints",
      "data": "Fever and cough for 3 days"
    }
  ]
}
```

**Response Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `extraction_id` | string (UUID) | Unique extraction identifier |
| `patient_id` | string (UUID) | Patient identifier |
| `doctor_id` | string (UUID) | Doctor who created/merged the extraction |
| `consultation_type_code` | string | Consultation type code (OP, DISCHARGE, etc.) |
| `consultation_type_name` | string | Human-readable consultation type name |
| `extraction_data` | object | Complete extraction data (edited if available, otherwise original) |
| `is_edited` | boolean | Whether doctor has edited this extraction |
| `edit_count` | integer | Number of times edited |
| `is_merged` | boolean | Whether this is a merged extraction |
| `created_at` | string (ISO) | Creation timestamp |
| `last_edited_at` | string (ISO) | Last edit timestamp (null if never edited) |
| `last_edited_by` | string (UUID) | Doctor who last edited (null if never edited) |
| `segments` | array | Individual segment data (if `include_segments=true`) |

**Behavior for Merged Extractions:**
- `is_merged` will be `true`
- Use `GET /{extraction_id}/merge-info` for merge lineage details
- Merged extractions can be edited like regular extractions

---

### GET `/api/v1/extractions/{extraction_id}/compare`

Compare original AI-generated extraction vs latest doctor edits.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `extraction_id` | UUID | Yes | The extraction UUID |

**Response:**
```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440003",
  "original": {
    "chief_complaints": "Fever for 3 days",
    "diagnosis": "URTI"
  },
  "edited": {
    "chief_complaints": "Fever and productive cough for 3 days",
    "diagnosis": "Acute bronchitis"
  },
  "has_edits": true,
  "edit_count": 2
}
```

**Use Cases:**
- Review what AI extracted vs what doctor corrected
- Quality assurance and model training
- Audit trail for medical documentation

---

### GET `/api/v1/extractions/{extraction_id}/original`

Get ONLY the original AI-generated extraction (ignores any edits).

**Response:**
```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440003",
  "original_extraction": {
    "chief_complaints": "Fever for 3 days",
    "diagnosis": "URTI"
  }
}
```

**Use Case:** Review what AI originally extracted before any doctor edits.

---

### GET `/api/v1/extractions/{extraction_id}/edited`

Get ONLY the edited version (returns 404 if never edited).

**Response:**
```json
{
  "extraction_id": "550e8400-e29b-41d4-a716-446655440003",
  "edited_extraction": {
    "chief_complaints": "Fever and productive cough for 3 days",
    "diagnosis": "Acute bronchitis"
  },
  "edit_count": 2,
  "last_edited_at": "2025-12-08T11:00:00Z",
  "last_edited_by": "doctor-uuid"
}
```

**Error Response (if never edited):**
```json
{
  "detail": "Extraction has not been edited"
}
```

---

### GET `/api/v1/extractions/session/{session_id}`

Get extraction by recording session ID (correlation_id).

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | Yes | Recording session correlation_id |

**Response:** Same structure as `GET /{extraction_id}`

**Use Case:** Look up extraction from recording workflow using the original session ID.

---

### Summary: Which API to Use

| Scenario | API Endpoint |
|----------|--------------|
| Have extraction_id (from merge or webhook) | `GET /api/v1/extractions/{extraction_id}` |
| Have submission_id (from recording workflow) | `GET /api/v1/extractions/by-submission/{submission_id}` |
| Have session_id (correlation_id from recording start) | `GET /api/v1/extractions/by-session/{session_id}` or `GET /api/v1/extractions/session/{session_id}` |
| Get merge lineage for merged extraction | `GET /api/v1/extractions/{extraction_id}/merge-info` |
| Get all extractions for a patient | `GET /api/v1/extractions/patient/{patient_id}/timeline` |
| Compare original vs edited | `GET /api/v1/extractions/{extraction_id}/compare` |

> **Important:** Merged extractions do NOT have a `submission_id`. Always use `extraction_id` to retrieve merged extractions.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 3.5.0 | 2025-12-09 | **BREAKING:** Merge API now async - returns immediately with `extraction_id`, added `/merge/status/{extraction_id}` polling endpoint |
| 3.4.0 | 2025-12-09 | Added extraction retrieval APIs documentation |
| 3.3.0 | 2025-12-09 | Added merge extractions API documentation |
| 3.2.0 | 2025-12-08 | Added investigation workflow APIs |
| 3.1.0 | 2025-12-01 | Added emotion analysis and intervention webhooks |
| 3.0.0 | 2025-11-15 | Added medicine matching and feedback APIs |

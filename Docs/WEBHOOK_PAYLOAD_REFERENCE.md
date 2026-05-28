# Webhook Payload Reference

This document describes the webhook payloads sent by the Unizy backend.

**Last Updated:** December 13, 2024

---

## Table of Contents

1. [Overview](#overview)
2. [Configuration](#configuration)
3. [Standard Extraction Webhook](#standard-extraction-webhook)
4. [Emotion Analysis Webhook](#emotion-analysis-webhook)
5. [Congruence Analysis Webhook](#congruence-analysis-webhook)
6. [Webhook Headers](#webhook-headers)
7. [Retry Logic](#retry-logic)
8. [Excluded Segments](#excluded-segments)

---

## Overview

The webhook service sends HTTP POST requests to configured endpoints when:

1. **Extraction completes** - Medical data extracted from transcript
2. **Emotion analysis completes** - Text/audio emotion analysis finished
3. **Congruence analysis completes** - Text vs audio emotion comparison finished

All webhooks are sent asynchronously with automatic retry logic.

---

## Configuration

Webhooks are configured via environment variables in `backend/.env`:

| Variable | Description | Example |
|----------|-------------|---------|
| `WEBHOOK_ENABLED` | Enable/disable webhooks | `true` |
| `WEBHOOK_URL` | Target URL(s), comma-separated for multiple | `https://api.example.com/webhook` |
| `WEBHOOK_TOKEN` | Bearer token for Authorization header | `secret-token-123` |
| `WEBHOOK_TIMEOUT` | Request timeout in seconds | `10` |

---

## Standard Extraction Webhook

Sent when medical extraction completes (recording, direct extraction, or merge).

### Payload Structure

```json
{
  "success": true,
  "insights": {
    "chiefComplaints": {
      "complaints": [
        {
          "complaint": "Headache",
          "duration": "3 days",
          "severity": "moderate"
        }
      ]
    },
    "diagnosis": {
      "primary": "Tension headache",
      "secondary": [],
      "differential": []
    },
    "prescription": {
      "medications": [
        {
          "name": "Paracetamol",
          "dosage": "500mg",
          "frequency": "TID",
          "duration": "5 days"
        }
      ]
    }
  },
  "metadata": {
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
    "submission_id": "660e8400-e29b-41d4-a716-446655440000",
    "extraction_id": "770e8400-e29b-41d4-a716-446655440000",
    "doctor_id": "880e8400-e29b-41d4-a716-446655440000",
    "patient_id": "PAT12345",
    "template_code": "OP_GENERAL",
    "template_name": "General OP Consultation",
    "consultation_type_code": "OP",
    "mode": "full",
    "segment_count": 12,
    "processing_mode": "default",
    "timestamp": "2025-01-07T10:30:00.000Z",
    "source": "recording"
  }
}
```

### Field Descriptions

#### Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Always `true` for successful extractions |
| `insights` | object | Extracted medical data (segments in camelCase) |
| `metadata` | object | Session and extraction metadata |

#### Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `correlation_id` | string (UUID) | Recording session correlation ID |
| `submission_id` | string (UUID) | Processing job submission ID |
| `extraction_id` | string (UUID) | Medical extraction record ID |
| `doctor_id` | string (UUID) | Doctor who performed the consultation |
| `patient_id` | string | Patient identifier (external ID like MRN) |
| `template_code` | string | Template code used for extraction |
| `template_name` | string | Human-readable template name |
| `consultation_type_code` | string | Consultation type (OP, IP, DISCHARGE, etc.) |
| `mode` | string | Extraction mode: `core`, `additional`, or `full` |
| `segment_count` | integer | Number of segments extracted |
| `processing_mode` | string | Processing mode: `fast`, `default`, `thorough`, `ultra`, `ultra_fast` |
| `timestamp` | string | ISO 8601 timestamp of webhook generation |
| `source` | string | Source of extraction (see below) |

#### Source Values

| Value | Description |
|-------|-------------|
| `recording` | Standard recording workflow (chunked audio upload) |
| `transcript_only_extraction` | Direct extraction from transcript (Live API flow) |
| `merge` | Merge of multiple extractions |

### Insights Structure

The `insights` object contains extracted segments in **camelCase** format. The exact segments depend on the template configuration. Common segments include:

| Segment Key | Description |
|-------------|-------------|
| `chiefComplaints` | Patient's presenting complaints |
| `historyOfPresentIllness` | HPI details |
| `pastMedicalHistory` | Previous medical conditions |
| `familyHistory` | Family medical history |
| `socialHistory` | Social/lifestyle factors |
| `reviewOfSystems` | Systems review findings |
| `physicalExamination` | Physical exam findings |
| `vitalSigns` | Vital signs measurements |
| `diagnosis` | Primary/secondary diagnoses |
| `prescription` | Prescribed medications |
| `investigations` | Ordered tests/investigations |
| `followUp` | Follow-up instructions |
| `caution` | Allergies, contraindications, warnings |
| `summary` | Consultation summary |

---

## Emotion Analysis Webhook

Sent when emotion analysis completes (text-only or audio-only mode).

### Payload Structure

```json
{
  "type": "emotion_analysis",
  "emotion_data": {
    "text_emotions": [
      {
        "segment_index": 0,
        "speaker": "patient",
        "text": "I've been feeling very anxious lately...",
        "emotions": {
          "primary": "anxiety",
          "secondary": ["worry", "fear"],
          "intensity": 0.75
        },
        "timestamp_start": 0,
        "timestamp_end": 15
      }
    ],
    "audio_emotions": [
      {
        "segment_index": 0,
        "speaker": "patient",
        "emotions": {
          "primary": "anxiety",
          "valence": -0.3,
          "arousal": 0.7,
          "confidence": 0.85
        },
        "timestamp_start": 0,
        "timestamp_end": 15
      }
    ],
    "recommended_interventions": {
      "total_count": 5,
      "top_recommendations": [
        {
          "intervention": "Cognitive Behavioral Therapy",
          "priority": 1,
          "rationale": "Effective for anxiety management",
          "is_top_3": true
        }
      ],
      "all_interventions": [
        {
          "intervention": "Cognitive Behavioral Therapy",
          "priority": 1,
          "rationale": "Effective for anxiety management",
          "is_top_3": true
        },
        {
          "intervention": "Mindfulness meditation",
          "priority": 2,
          "rationale": "Reduces stress and anxiety",
          "is_top_3": true
        }
      ]
    }
  },
  "session_info": {
    "extraction_id": "770e8400-e29b-41d4-a716-446655440000",
    "submission_id": "660e8400-e29b-41d4-a716-446655440000",
    "doctor_id": "880e8400-e29b-41d4-a716-446655440000",
    "patient_id": "PAT12345",
    "consultation_type_code": "OP",
    "consultation_type_name": "Outpatient",
    "emotion_mode": "text_only"
  },
  "metadata": {
    "timestamp": "2025-01-07T10:35:00.000Z",
    "source": "emotion_extraction",
    "emotion_mode": "text_only"
  }
}
```

### Field Descriptions

#### Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"emotion_analysis"` |
| `emotion_data` | object | Emotion analysis results |
| `session_info` | object | Session context |
| `metadata` | object | Webhook metadata |

#### Emotion Data Fields

| Field | Type | Description |
|-------|------|-------------|
| `text_emotions` | array | Text-based emotion segments (if mode includes text) |
| `audio_emotions` | array | Audio-based emotion segments (if mode includes audio) |
| `recommended_interventions` | object | AI-recommended interventions |

#### Emotion Mode Values

| Value | Description |
|-------|-------------|
| `text_only` | Emotion analysis from transcript text only |
| `audio_only` | Emotion analysis from audio only |
| `both` | Both text and audio analysis (triggers congruence analysis) |

---

## Congruence Analysis Webhook

Sent when congruence analysis completes (compares text vs audio emotions).

### Payload Structure

```json
{
  "type": "congruence_analysis",
  "congruence_data": {
    "congruence_score": 0.85,
    "overall_assessment": "High congruence between verbal and non-verbal cues",
    "discrepancies": [
      {
        "segment_index": 3,
        "text_emotion": "neutral",
        "audio_emotion": "anxiety",
        "significance": "moderate",
        "interpretation": "Patient may be masking anxiety"
      }
    ],
    "clinical_implications": [
      "Patient appears to minimize emotional distress verbally",
      "Consider exploring underlying concerns"
    ]
  },
  "emotion_data": {
    "text_emotions": [ ... ],
    "audio_emotions": [ ... ]
  },
  "recommended_interventions": {
    "total_count": 5,
    "top_recommendations": [ ... ],
    "all_interventions": [ ... ]
  },
  "session_info": {
    "extraction_id": "770e8400-e29b-41d4-a716-446655440000",
    "submission_id": "660e8400-e29b-41d4-a716-446655440000",
    "doctor_id": "880e8400-e29b-41d4-a716-446655440000",
    "patient_id": "PAT12345",
    "consultation_type_code": "OP",
    "consultation_type_name": "Outpatient",
    "emotion_mode": "both"
  },
  "metadata": {
    "timestamp": "2025-01-07T10:40:00.000Z",
    "source": "congruence_analysis"
  }
}
```

### Field Descriptions

#### Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"congruence_analysis"` |
| `congruence_data` | object | Text vs audio comparison results |
| `emotion_data` | object | All emotion segments for context |
| `recommended_interventions` | object | AI-recommended interventions |
| `session_info` | object | Session context |
| `metadata` | object | Webhook metadata |

#### Congruence Data Fields

| Field | Type | Description |
|-------|------|-------------|
| `congruence_score` | float | 0.0-1.0 score (1.0 = perfect alignment) |
| `overall_assessment` | string | Summary of congruence analysis |
| `discrepancies` | array | Segments with text/audio emotion mismatch |
| `clinical_implications` | array | Clinical insights from analysis |

---

## Webhook Headers

All webhook requests include the following headers:

```
Content-Type: application/json
User-Agent: AI-Live-Recorder/3.1.0
Authorization: Bearer <WEBHOOK_TOKEN>
```

| Header | Description |
|--------|-------------|
| `Content-Type` | Always `application/json` |
| `User-Agent` | Identifies the sending service and version |
| `Authorization` | Bearer token if `WEBHOOK_TOKEN` is configured |

---

## Retry Logic

The webhook service implements automatic retry with exponential backoff:

| Attempt | Wait Before Retry |
|---------|-------------------|
| 1 | Immediate |
| 2 | 1 second |
| 3 | 2 seconds |
| 4 | 4 seconds (final attempt) |

**Configuration:**
- Default max retries: 3
- Default timeout: 10 seconds
- Success: Any 2xx status code

**Multi-URL Support:**
- Multiple webhook URLs can be configured (comma-separated)
- Requests are sent to all URLs in parallel
- Success if at least one URL returns 2xx

---

## Excluded Segments

Templates can configure `excluded_segment_codes` to filter specific segments from the webhook payload.

### How It Works

1. All segments are still extracted and stored in the database
2. Excluded segments are filtered out before sending the webhook
3. Segment codes are converted from `UPPER_SNAKE_CASE` to `camelCase` for matching

### Example

Template configuration:
```json
{
  "excluded_segment_codes": ["CAUTION", "SUMMARY"]
}
```

Result:
- `caution` and `summary` segments are extracted and saved to DB
- `caution` and `summary` are NOT included in the webhook `insights` object
- All other segments are included in the webhook

### Use Cases

- Exclude sensitive segments from external systems
- Reduce webhook payload size
- Filter segments not needed by the receiving system

---

## Webhook Timing

| Event | Webhook Type | Timing |
|-------|--------------|--------|
| Extraction complete | Standard | Immediately after extraction saved |
| Emotion analysis complete | Emotion | After text/audio emotion analysis |
| Congruence analysis complete | Congruence | After text vs audio comparison |

**Note:** Emotion and congruence webhooks are only sent if the consultation type has emotion analysis enabled.

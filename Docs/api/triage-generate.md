# Triage Generate API

**Endpoint:** `POST /api/v1/triage/generate`

Generate or retrieve clinical triage suggestions for a medical extraction.

---

## Request

**Headers:**
```
Content-Type: application/json
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "extraction_id": "uuid-string",           // Required: UUID of the medical extraction
  "include_gemini": true,                   // Optional (default: true): Use Gemini AI for gap analysis
  "patient_id": "uuid-string",              // Optional: Patient UUID (auto-detected if not provided)
  "doctor_id": "uuid-string",               // Optional: Doctor UUID for suggestion logging
  "log_suggestions": true,                  // Optional (default: true): Log suggestions to DB for learning
  "force_regenerate": false                 // Optional (default: false): Force regenerate even if cached
}
```

### Request Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `extraction_id` | string (UUID) | Yes | - | UUID of the medical extraction |
| `include_gemini` | boolean | No | `true` | Whether to use Gemini AI for gap analysis |
| `patient_id` | string (UUID) | No | auto-detected | Patient UUID for historical context |
| `doctor_id` | string (UUID) | No | `null` | Doctor UUID for suggestion logging |
| `log_suggestions` | boolean | No | `true` | Whether to log suggestions to database |
| `force_regenerate` | boolean | No | `false` | Force regenerate suggestions even if cached |

---

## Response

### Success Response (200 OK)

```json
{
  "success": true,
  "extraction_id": "uuid-string",
  "specialty": "general_medicine",
  "consultation_type": "OP",

  "critical_actions": [
    {
      "id": "suggestion-uuid",
      "category": "investigation",
      "suggestion": "Order CBC to rule out infection",
      "priority": "critical",
      "rationale": "Fever with elevated pulse suggests possible infection",
      "source": "differential_tree",
      "related_presentation": "fever"
    }
  ],

  "important_considerations": [
    {
      "id": "suggestion-uuid",
      "category": "history",
      "suggestion": "Ask about recent travel history",
      "priority": "important",
      "rationale": "Important for differential diagnosis",
      "source": "gemini_analysis",
      "related_presentation": null
    }
  ],

  "nice_to_have": [
    {
      "id": "suggestion-uuid",
      "category": "investigation",
      "suggestion": "Consider thyroid function tests",
      "priority": "consider",
      "rationale": "May be relevant given fatigue symptoms",
      "source": "gemini_analysis",
      "related_presentation": null
    }
  ],

  "matched_presentations": ["fever", "headache"],
  "identified_red_flags": ["high fever", "neck stiffness"],

  "gap_analysis": {
    "risk_level": "moderate",
    "risk_factors": ["age > 60", "diabetes"],
    "differential_considerations": ["Meningitis", "Viral infection"],
    "safety_netting": "Return if symptoms worsen or new symptoms develop",
    "critical_suggestions": [
      {
        "type": "investigation",
        "suggestion": "Lumbar puncture if meningitis suspected",
        "urgency": "urgent",
        "rationale": "Rule out bacterial meningitis"
      }
    ],
    "additional_suggestions": [
      {
        "type": "history",
        "suggestion": "Document vaccination history",
        "rationale": "Relevant for infection risk assessment"
      }
    ],
    "error": null
  },

  "total_suggestions": 8,
  "generated_at": "2024-12-16T10:30:00.000Z",
  "model_used": "gemini-2.0-flash",
  "processing_time_ms": 1250
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Whether the request was successful |
| `extraction_id` | string | UUID of the extraction |
| `specialty` | string | Medical specialty (e.g., `general_medicine`, `ophthalmology`) |
| `consultation_type` | string | Consultation type code (e.g., `OP`, `DISCHARGE`) |
| `critical_actions` | array | High-priority suggestions requiring immediate attention |
| `important_considerations` | array | Medium-priority suggestions |
| `nice_to_have` | array | Low-priority optional suggestions |
| `matched_presentations` | array | Clinical presentations matched from extraction |
| `identified_red_flags` | array | Red flags identified in the extraction |
| `gap_analysis` | object | AI-generated gap analysis (if `include_gemini=true`) |
| `total_suggestions` | number | Total count of all suggestions |
| `generated_at` | string | ISO timestamp of generation |
| `model_used` | string | Model used: `gemini-2.0-flash`, `cached`, or `none` |
| `processing_time_ms` | number | Processing time in milliseconds |

### Suggestion Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Suggestion UUID (for feedback submission) |
| `category` | string | `investigation`, `history`, `examination`, or `referral` |
| `suggestion` | string | The suggestion text |
| `priority` | string | `critical`, `important`, or `consider` |
| `rationale` | string | Explanation for the suggestion |
| `source` | string | `differential_tree`, `gemini_analysis`, or `patient_history` |
| `related_presentation` | string | Related clinical presentation (if applicable) |

### Gap Analysis Object

| Field | Type | Description |
|-------|------|-------------|
| `risk_level` | string | Overall risk level assessment |
| `risk_factors` | array | Identified risk factors |
| `differential_considerations` | array | Differential diagnoses to consider |
| `safety_netting` | string | Safety netting advice for patient |
| `critical_suggestions` | array | Critical suggestions from AI analysis |
| `additional_suggestions` | array | Additional suggestions from AI analysis |
| `error` | string | Error message if Gemini analysis failed |

---

## Error Responses

### 404 Not Found
```json
{
  "detail": "Extraction not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Failed to generate triage suggestions: <error message>"
}
```

---

## Key Behaviors

1. **Caching**: If `force_regenerate=false` (default), returns cached suggestions from `triage_suggestion_log` table if they exist. The `model_used` field will be `"cached"` in this case.

2. **Patient Context**: Auto-detects `patient_id` from the extraction's recording session if not provided. Patient history (allergies, chronic conditions) is used to filter and enhance suggestions.

3. **Suggestion IDs**: Each suggestion includes an `id` that can be used to submit feedback via `POST /api/v1/triage/feedback`.

4. **Gemini Analysis**: When `include_gemini=true`, performs AI-powered gap analysis for additional clinical insights beyond the differential trees.

5. **Suggestion Logging**: When `log_suggestions=true`, suggestions are stored in `triage_suggestion_log` for caching and learning doctor patterns.

---

## Example Usage

### cURL
```bash
curl -X POST "http://localhost:8000/api/v1/triage/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "extraction_id": "123e4567-e89b-12d3-a456-426614174000",
    "include_gemini": true,
    "force_regenerate": false
  }'
```

### TypeScript (Frontend)
```typescript
import { getTriageSuggestions } from '@lib/summaryApi';

const data = await getTriageSuggestions(
  extractionId,      // extraction UUID
  true,              // include_gemini
  getAccessToken(),  // auth token
  false              // force_regenerate
);
```

---

## Related Endpoints

- `POST /api/v1/triage/feedback` - Submit feedback on a suggestion
- `POST /api/v1/triage/generate-from-json` - Generate triage from raw JSON (no DB lookup)
- `GET /api/v1/triage/differentials/{specialty}/{presentation}` - Get differential tree data
- `GET /api/v1/triage/specialties` - List available specialties

# Triage RAG API Reference

API reference for analysts working with clinical guideline ingestion and RAG-based triage testing.

**Base URL**: `http://localhost:8000/api/v1/triage`

---

## Quick Reference

| Action | Endpoint | Method |
|--------|----------|--------|
| Ingest guideline JSON | `/conditions/ingest` | POST |
| Search clinical chunks | `/conditions/search` | POST |
| List all conditions | `/conditions` | GET |
| Get condition details | `/conditions/{condition_id}` | GET |
| Delete condition | `/conditions/{condition_id}` | DELETE |
| Test triage from JSON | `/generate-from-json` | POST |
| Get red flags | `/conditions/red-flags/{specialty}` | GET |
| Health check | `/health` | GET |

---

## 1. Guideline Ingestion API

### POST `/conditions/ingest`

Ingest a clinical guideline JSON file into the RAG system. This validates, stores, chunks, and vectorizes the content.

**Authentication**: Admin or Web App API key required

**Request**:
```bash
curl -X POST "http://localhost:8000/api/v1/triage/conditions/ingest" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "json_data": { ... guideline JSON ... },
    "file_name": "hypertension_stg.json"
  }'
```

**Request Body**:
```json
{
  "json_data": {
    "document_meta": {
      "source": "Ministry of Health STG",
      "specialty": "cardiology",
      "document_type": "narrative_guideline",
      "version": "2024",
      "icd_codes": ["I10"]
    },
    "conditions": [...]
  },
  "file_name": "hypertension_stg.json"
}
```

**Response** (Success):
```json
{
  "success": true,
  "job_id": "uuid",
  "status": "completed",
  "file_name": "hypertension_stg.json",
  "total_conditions": 1,
  "processed_conditions": 1,
  "total_chunks": 45,
  "embedded_chunks": 45,
  "condition_ids": ["cardio_htn_001"],
  "duration_seconds": 12.5
}
```

**Response** (Validation Error):
```json
{
  "success": false,
  "status": "failed",
  "error_message": "Validation failed",
  "validation_errors": [
    {
      "loc": ["conditions", 0, "condition_id"],
      "msg": "condition_id must match pattern: specialty_name_NNN",
      "type": "value_error"
    }
  ]
}
```

**Pipeline Steps**:
1. Validates JSON against Pydantic schema
2. Creates master record in `clinical_conditions` table
3. Extracts semantic chunks (triage_criteria, treatment, red_flags, etc.)
4. Generates embeddings using Cohere `embed-english-v3.0` (1024 dimensions)
5. Stores chunks with embeddings in `clinical_chunks` table

---

## 2. Search API

### POST `/conditions/search`

Hybrid semantic + filter search across clinical chunks.

**Authentication**: Bearer token required

**Request**:
```bash
curl -X POST "http://localhost:8000/api/v1/triage/conditions/search" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "hypertension with diabetes management",
    "specialty": "cardiology",
    "limit": 10
  }'
```

**Request Body**:
```json
{
  "query": "hypertension with diabetes management",
  "specialty": "cardiology",
  "chunk_types": ["treatment_primary", "comorbidity_pathway"],
  "care_level": "phc_primary",
  "urgency": "routine",
  "comorbidity": "diabetes",
  "drug_class": "ACE_inhibitor",
  "patient_sbp": 160,
  "patient_dbp": 95,
  "limit": 10,
  "similarity_threshold": 0.4
}
```

**Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | string | **Required**. Search query text |
| `specialty` | string | Filter by specialty (e.g., `cardiology`, `ent`) |
| `chunk_types` | string[] | Filter by chunk types (see list below) |
| `care_level` | string | Filter by care level: `phc_primary`, `district`, `tertiary` |
| `urgency` | string | Filter by urgency: `routine`, `urgent`, `emergency` |
| `comorbidity` | string | Filter by comorbidity: `diabetes`, `ckd`, `heart_failure`, etc. |
| `drug_class` | string | Filter by drug class: `CCB`, `ACE_inhibitor`, `ARB`, etc. |
| `patient_sbp` | int | Patient systolic BP for threshold matching |
| `patient_dbp` | int | Patient diastolic BP for threshold matching |
| `patient_hb` | float | Patient hemoglobin for threshold matching |
| `limit` | int | Max results (default: 10, max: 50) |
| `similarity_threshold` | float | Minimum similarity score (default: 0.4, range: 0-1) |

**Chunk Types**:
- `triage_criteria` - Urgency and triage rules
- `classification` - Disease grading/staging
- `presentation` - Symptoms and examination findings
- `differential` - Differential diagnoses
- `investigation` - Diagnostic tests
- `treatment_primary` - PHC/primary care treatment
- `treatment_district` - District hospital treatment
- `treatment_tertiary` - Tertiary care treatment
- `treatment_escalation` - Step-wise escalation
- `comorbidity_pathway` - Comorbidity-specific management
- `drug_formulary` - Drug dosing and contraindications
- `emergency_protocol` - Emergency management
- `follow_up` - Follow-up recommendations
- `patient_education` - Patient education content
- `step_protocol` - Ordered procedure steps
- `decision_node` - Decision tree nodes

**Response**:
```json
{
  "success": true,
  "query": "hypertension with diabetes management",
  "total_results": 5,
  "chunks": [
    {
      "id": "chunk-uuid",
      "condition_id": "cardio_htn_001",
      "condition_name": "Primary Hypertension",
      "chunk_type": "comorbidity_pathway",
      "content_text": "For diabetes comorbidity: Preferred drugs: ACE inhibitors...",
      "urgency_default": "routine",
      "has_emergency_triggers": false,
      "has_red_flags": true,
      "care_levels": ["phc_primary", "district"],
      "comorbidity": "diabetes",
      "drug_classes": ["ACE_inhibitor", "ARB"],
      "similarity_score": 0.87
    }
  ],
  "processing_time_ms": 45
}
```

---

## 3. List & Inspect Conditions

### GET `/conditions`

List all ingested clinical conditions.

**Query Parameters**:
- `specialty` (optional): Filter by specialty
- `document_type` (optional): Filter by type (`narrative_guideline`, `visual_workflow`, `step_protocol`)
- `is_active` (default: true): Only return active conditions
- `limit` (default: 50, max: 200)

```bash
curl "http://localhost:8000/api/v1/triage/conditions?specialty=cardiology" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Response**:
```json
[
  {
    "id": "uuid",
    "condition_id": "cardio_htn_001",
    "name": "Primary Hypertension",
    "aliases": ["Essential Hypertension", "High Blood Pressure"],
    "icd_codes": ["I10", "I11.9"],
    "specialty": "cardiology",
    "source_name": "Ministry of Health STG",
    "document_type": "narrative_guideline",
    "chunk_count": 45,
    "is_active": true,
    "is_verified": false,
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

### GET `/conditions/{condition_id}`

Get full condition details with all chunks.

```bash
curl "http://localhost:8000/api/v1/triage/conditions/cardio_htn_001" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## 4. Test Triage Generation

### POST `/generate-from-json`

Test triage generation from raw extraction JSON (no database required).

**Authentication**: Optional (no auth required for testing)

```bash
curl -X POST "http://localhost:8000/api/v1/triage/generate-from-json" \
  -H "Content-Type: application/json" \
  -d '{
    "extraction_json": {
      "chief_complaint": "Headache and dizziness for 2 days",
      "vitals": {
        "bp": "170/100 mmHg",
        "pulse": "88/min"
      },
      "history_of_present_illness": "Patient complains of throbbing headache..."
    },
    "consultation_type_code": "OP",
    "include_gemini": true
  }'
```

**Response**:
```json
{
  "success": true,
  "specialty": "general",
  "consultation_type": "OP",
  "critical_actions": [
    {
      "category": "investigation",
      "suggestion": "Check fundoscopy for hypertensive retinopathy",
      "priority": "critical_action",
      "rationale": "BP >160/100 requires end-organ damage assessment",
      "source": "rag_guidelines"
    }
  ],
  "important_considerations": [...],
  "nice_to_have": [...],
  "matched_presentations": ["hypertension"],
  "identified_red_flags": ["BP >180/110 with symptoms"],
  "total_suggestions": 12,
  "processing_time_ms": 1250
}
```

---

## 5. Utility Endpoints

### GET `/conditions/red-flags/{specialty}`

Get all red flags for a specialty.

```bash
curl "http://localhost:8000/api/v1/triage/conditions/red-flags/cardiology" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### GET `/conditions/comorbidity/{comorbidity}`

Get treatment pathways for a comorbidity.

```bash
curl "http://localhost:8000/api/v1/triage/conditions/comorbidity/diabetes" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### DELETE `/conditions/{condition_id}`

Delete a condition (soft delete - marks as inactive).

**Authentication**: Admin or Web App API key required

```bash
curl -X DELETE "http://localhost:8000/api/v1/triage/conditions/cardio_htn_001" \
  -H "Authorization: Bearer YOUR_ADMIN_API_KEY"
```

### GET `/health`

Check triage service health and stats.

```bash
curl "http://localhost:8000/api/v1/triage/health"
```

**Response**:
```json
{
  "status": "healthy",
  "service": "triage",
  "specialties_loaded": 5,
  "total_presentations": 23,
  "enabled_layers": ["base_mvp", "rag_guidelines"],
  "multi_layer_available": true,
  "clinical_conditions_count": 3,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

## Testing Workflow

### Step 1: Prepare Guideline JSON

Use the schema from `Docs/clinical_guideline_schema.json` to structure your guideline.

### Step 2: Ingest Guideline

```bash
curl -X POST "http://localhost:8000/api/v1/triage/conditions/ingest" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d @your_guideline.json
```

> **Note**: Use either an admin API key or a web_app API key.

### Step 3: Verify Ingestion

```bash
# List conditions
curl "http://localhost:8000/api/v1/triage/conditions"

# Check chunk count
curl "http://localhost:8000/api/v1/triage/conditions/your_condition_id"
```

### Step 4: Test Search

```bash
curl -X POST "http://localhost:8000/api/v1/triage/conditions/search" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "your test query",
    "specialty": "your_specialty"
  }'
```

### Step 5: Test Triage Generation

```bash
curl -X POST "http://localhost:8000/api/v1/triage/generate-from-json" \
  -H "Content-Type: application/json" \
  -d '{
    "extraction_json": { ... test case ... },
    "consultation_type_code": "OP"
  }'
```

---

## Error Codes

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 400 | Bad Request - Invalid JSON or parameters |
| 401 | Unauthorized - Missing/invalid API key |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Condition/resource not found |
| 422 | Validation Error - Schema validation failed |
| 500 | Server Error - Internal error |

---

## Example Guideline Files

Reference examples in the codebase:
- `backend/data/guidelines/hypertension_stg.json` - Narrative guideline
- `backend/data/guidelines/epistaxis_stw.json` - Step protocol
- `backend/data/guidelines/rhinosinusitis_stw.json` - Visual workflow

# Q&A Engine Documentation

The Q&A Engine provides a natural language interface for querying medical extraction data. It supports semantic search, analytics queries, and longitudinal patient history analysis.

## Table of Contents

1. [Overview](#overview)
2. [API Endpoints](#api-endpoints)
3. [Query Types](#query-types)
4. [Sample Questions](#sample-questions)
5. [Temporal & Longitudinal Queries](#temporal--longitudinal-queries)
6. [Response Formats](#response-formats)
7. [Frontend Integration](#frontend-integration)

---

## Overview

### Architecture

```
User Query → Reframer → Classifier → Router
                                       ↓
                    ┌──────────────────┼──────────────────┐
                    ↓                  ↓                  ↓
               Semantic           Analytics         Longitudinal
               Search             (SQL)             Service
                    ↓                  ↓                  ↓
               Synthesis          Chart/Stat       Visit Comparison
                    ↓                  ↓                  ↓
                    └──────────────────┴──────────────────┘
                                       ↓
                                  Response
```

### Key Components

| Component | Description |
|-----------|-------------|
| **Query Reframer** | Expands abbreviations, fixes typos, normalizes medical terms |
| **Query Classifier** | Determines intent (semantic/hybrid/SQL) and extracts filters |
| **Semantic Search** | Vector similarity search over extraction embeddings |
| **Analytics Engine** | Text-to-SQL for counts, distributions, trends |
| **Longitudinal Service** | Multi-visit comparisons and patient history tracking |
| **Temporal Resolver** | Resolves "last visit", "3 months ago" to actual dates/IDs |

---

## API Endpoints

### Base URL
```
http://localhost:8000/api/v1/qa
```

### Authentication
All endpoints require authentication. Use `Authorization: Bearer <token>` header.

---

### POST `/query`

Execute a natural language Q&A query.

**Request Body:**
```json
{
  "query": "What are the most common diagnoses?",
  "hospital_id": "uuid (optional - resolved from hospital_code or auth context)",
  "hospital_code": "string (optional - alternative to hospital_id, e.g. 'GURU')",
  "doctor_id": "uuid (optional)",
  "patient_id": "string (optional - external UHID or internal UUID, required for longitudinal queries)",
  "consultation_type_id": "uuid (optional)",
  "extraction_id": "uuid (optional - reference specific visit)",
  "date_from": "2024-01-01T00:00:00Z (optional)",
  "date_to": "2024-12-31T23:59:59Z (optional)",
  "prior_context": {
    "query": "what did I prescribe last time",
    "narrative": "In the last visit on Jan 15, you prescribed Metformin 500mg...",
    "intent": "semantic",
    "extraction_id": "uuid (optional - extraction from previous answer)"
  },
  "limit": 20,
  "offset": 0
}
```

**Field Details:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Natural language query (3-2000 chars) |
| `hospital_id` | UUID | No | Hospital scope. Falls back to `hospital_code` then auth context |
| `hospital_code` | string | No | Hospital code (e.g., `"GURU"`). Alternative to `hospital_id` |
| `doctor_id` | UUID | No | Filter to specific doctor |
| `patient_id` | string | No | External patient ID (UHID) or internal UUID. Required for temporal/longitudinal queries |
| `consultation_type_id` | UUID | No | Filter by consultation type |
| `extraction_id` | UUID | No | Reference a specific visit |
| `prior_context` | object | No | Previous Q&A exchange for follow-up query resolution (see below) |
| `date_from` | datetime | No | Filter start date |
| `date_to` | datetime | No | Filter end date |
| `limit` | int | No | Results per page (1-100, default: 20) |
| `offset` | int | No | Pagination offset (default: 0) |

**`prior_context` Object:**

| Field | Type | Description |
|-------|------|-------------|
| `query` | string | The previous user query text |
| `narrative` | string | The previous assistant narrative response |
| `intent` | string | Previous query intent (`semantic`, `hybrid`, `sql`) |
| `extraction_id` | string | Extraction ID if previous answer referenced a specific visit |

**Response:**
```json
{
  "success": true,
  "query": "What are the most common diagnoses?",
  "intent": "semantic",
  "response_format": "narrative",
  "reframed_query": "What are the most common diagnoses in patient records?",
  "reframe_expansions": [],
  "reframe_corrections": [],
  "narrative": "Based on the analysis of patient records...",
  "results": [...],
  "total_count": 45,
  "temporal_references": null,
  "longitudinal_data": null,
  "reframe_time_ms": 1200,
  "embedding_time_ms": 150,
  "search_time_ms": 85,
  "synthesis_time_ms": 2500,
  "total_time_ms": 4500
}
```

---

### GET `/suggested-questions`

Get pre-defined question templates.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `category` | string | Filter by category: `clinical`, `risk`, `referrals`, `interventions`, `triage`, `analytics` |

**Response:**
```json
{
  "questions": [
    {
      "id": "clinical_01",
      "question": "What are the most common diagnoses across my patients?",
      "category": "clinical",
      "description": "View distribution of diagnoses",
      "expected_intent": "semantic",
      "expected_segment_codes": ["DIAGNOSIS"]
    }
  ],
  "category": "clinical",
  "count": 11
}
```

---

### GET `/history`

Get user's Q&A query history.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Results per page (1-100) |
| `page` | int | 1 | Page number |

**Response:**
```json
{
  "history": [
    {
      "id": "uuid",
      "query_text": "Show patients with diabetes",
      "query_intent": "hybrid",
      "result_count": 15,
      "response_format": "table",
      "total_time_ms": 3200,
      "created_at": "2024-01-15T10:30:00Z",
      "reframed_query": null,
      "reframe_expansions": null,
      "reframe_corrections": null
    }
  ],
  "total_count": 150,
  "page": 1,
  "page_size": 20
}
```

---

### POST `/export`

Export Q&A search results to CSV.

**Request Body:**
```json
{
  "query": "Show patients with diabetes",
  "results": [...],
  "format": "csv"
}
```

**Response:**
```json
{
  "success": true,
  "format": "csv",
  "filename": "qa_export_20240115_103000.csv",
  "content": "Patient Name,Patient ID,Doctor,..."
}
```

---

### GET `/patients/{patient_id}/visits`

Get a patient's consultation visits for the visit selector.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `hospital_id` | uuid | Hospital filter |
| `doctor_id` | uuid | Doctor filter (optional) |
| `consultation_type_id` | uuid | Consultation type filter (optional) |
| `limit` | int | Max visits to return (default: 20) |

**Response:**
```json
{
  "success": true,
  "patient_id": "uuid",
  "visits": [
    {
      "extraction_id": "uuid",
      "created_at": "2024-01-15T10:30:00Z",
      "consultation_type_id": "uuid",
      "consultation_type_code": "OP",
      "consultation_type_name": "Outpatient Consultation",
      "doctor_id": "uuid",
      "doctor_name": "Dr. Smith"
    }
  ],
  "count": 5
}
```

---

## Query Types

### 1. Semantic Queries (Intent: `semantic`)

Pattern detection and insight synthesis queries. Returns narrative responses.

**Examples:**
- "What are the most common diagnoses across my patients?"
- "What medications are most frequently prescribed?"
- "What are common risk factors in critical cases?"

**Response Format:** `narrative`

---

### 2. Hybrid Queries (Intent: `hybrid`)

Search with filters returning patient/extraction tables.

**Examples:**
- "Show patients with diabetes and hypertension"
- "Find patients with abnormal vital signs"
- "Patients with urgent follow-up needs"

**Response Format:** `table`

---

### 3. Analytics Queries (Intent: `sql`)

Counts, distributions, and statistical queries. Returns charts/stat cards.

**Examples:**
- "How many extractions were done this month?"
- "Distribution of consultation types"
- "Top 10 diagnoses this month"

**Response Format:** `chart` or `stat_card`

---

### 4. Longitudinal Queries

Patient history and visit comparison queries. Requires `patient_id`.

**Examples:**
- "What changed since the last visit?"
- "Show prescription history over the last 3 visits"
- "Compare medications with previous consultation"

**Response includes:**
- `temporal_references`: Resolved visit dates/IDs
- `longitudinal_data`: Comparison data (medication changes, vital trends, etc.)
- `referenced_visits`: List of visits used in the comparison

---

## Sample Questions

### Clinical Questions

| ID | Question | Description |
|----|----------|-------------|
| clinical_01 | What are the most common diagnoses across my patients? | View distribution of diagnoses |
| clinical_02 | Show patients with diabetes and hypertension | Find patients with comorbidities |
| clinical_03 | What medications are most frequently prescribed? | Analyze prescription patterns |
| clinical_04 | Find patients with abnormal vital signs | Identify patients needing attention |
| clinical_05 | What investigations are commonly ordered? | Review investigation patterns |
| clinical_06 | What changed since the last visit? | Compare current vs previous consultation |
| clinical_07 | Compare medications with previous consultation | Track medication changes over time |
| clinical_08 | Has blood pressure improved since first visit? | Track vital sign trends over time |
| clinical_09 | What diagnoses were added since last month? | Track new diagnoses over time |
| clinical_10 | Show prescription history over the last 3 visits | Review medication changes across visits |
| clinical_11 | What complaints were resolved since last visit? | Track complaint resolution over time |

### Risk Assessment Questions

| ID | Question | Description |
|----|----------|-------------|
| risk_01 | Which patients have high severity assessments? | Identify high-risk patients |
| risk_02 | Show patients at risk of treatment non-compliance | Find compliance risk patients |
| risk_03 | What are the common risk factors in critical cases? | Analyze critical case patterns |
| risk_04 | Patients with quality of care concerns | Review quality risk assessments |
| risk_05 | Show patients with retention risk flags | Identify patients at risk of leaving |

### Referral Questions

| ID | Question | Description |
|----|----------|-------------|
| referral_01 | Which patients need allied health referrals? | Find patients needing support services |
| referral_02 | Show physiotherapy referral recommendations | Review physio referral needs |
| referral_03 | Patients recommended for nutrition counseling | Find nutrition referral candidates |
| referral_04 | What specialist referrals are most common? | Analyze referral patterns |
| referral_05 | Show patients needing mental health support | Identify mental health referral needs |

### Intervention Questions

| ID | Question | Description |
|----|----------|-------------|
| intervention_01 | What interventions have been recommended this month? | Review recent interventions |
| intervention_02 | Show pending intervention follow-ups | Find interventions needing action |
| intervention_03 | Which interventions have the best conversion rates? | Analyze intervention effectiveness |
| intervention_04 | Patients with surgical consultation recommendations | Find OP-to-IP conversion candidates |
| intervention_05 | Show prescription refill reminders due | Find RX refill opportunities |

### Triage Questions

| ID | Question | Description |
|----|----------|-------------|
| triage_01 | Show patients with red flag symptoms | Identify urgent cases |
| triage_02 | What are the most common chief complaints? | Analyze presenting complaints |
| triage_03 | Patients with urgent follow-up needs | Find patients needing urgent attention |
| triage_04 | Show cases with missing critical investigations | Identify investigation gaps |
| triage_05 | Patients with medication safety alerts | Review medication safety concerns |

### Analytics Questions

| ID | Question | Description |
|----|----------|-------------|
| analytics_01 | How many extractions were done this month? | View extraction volume |
| analytics_02 | Show extraction trends over the past week | View daily extraction trends |
| analytics_03 | Distribution of consultation types | Analyze consultation type mix |
| analytics_04 | Average severity score by consultation type | Compare severity across types |
| analytics_05 | Intervention conversion rate this month | Track intervention success |
| analytics_06 | Top 10 diagnoses this month | View most common diagnoses |

---

## Temporal & Longitudinal Queries

### Temporal Reference Types

| Type | Examples | Description |
|------|----------|-------------|
| `relative_visit` | "last visit", "previous consultation" | Relative to most recent visit |
| `absolute_date` | "January 15th", "2024-01-15" | Specific date |
| `relative_time` | "last week", "3 months ago" | Relative time period |
| `visit_number` | "first visit", "visit 3" | Specific visit number |
| `comparison` | "compare with previous" | Comparison baseline |

### How Temporal Resolution Works

1. **Query Classification**: Extracts temporal references from query
2. **Visit Lookup**: Fetches patient's consultation history
3. **Resolution**: Maps references to actual dates/extraction IDs
4. **Data Retrieval**: Fetches extraction data for resolved visits
5. **Comparison**: Generates changes/trends between visits

### Single-Visit Temporal Queries

**Single-visit queries** (e.g., "what did I prescribe last time"):
- Detects temporal reference pointing to a single visit (not multi-visit, not comparison)
- Uses `get_single_visit_data()` to fetch the specific extraction
- Uses `synthesize_single_visit_narrative()` to generate a focused answer
- Returns `response_format: "narrative"` with the visit data and `referenced_visits`

**Examples:**
- "What did I prescribe last time?" → Narrative about medications from the most recent visit
- "What was the diagnosis in the last visit?" → Focused narrative about diagnoses
- "What were the chief complaints in the previous consultation?" → Specific complaints

### Conversation Context (Follow-Up Queries)

The `prior_context` field enables follow-up queries by providing the previous Q&A exchange to the LLM pipeline:

1. **Reframer**: Uses context to resolve pronouns and references ("this prescription" → actual medication name)
2. **Classifier**: Uses previous intent to better classify follow-ups
3. **Synthesis**: Uses prior answer to provide contextually relevant responses

**Example flow:**
1. User: "What did I prescribe last time?" → Narrative about Metformin 500mg
2. User: "What was the diagnosis for this prescription?" → `prior_context` includes previous Q&A, LLM resolves "this prescription" to Metformin

The frontend automatically sends the last completed Q&A exchange as `prior_context` with each query. First queries (no history) work normally with `prior_context` omitted.

### Multi-Visit vs Comparison Queries

**Multi-Visit Queries** (e.g., "last 3 visits"):
- Uses `get_longitudinal_summary()`
- Aggregates data across N visits
- Shows per-visit medication/diagnosis history

**Comparison Queries** (e.g., "what changed since last visit"):
- Uses `get_changes_since_visit()`
- Compares baseline visit with current
- Returns: medication_changes, new_diagnoses, resolved_complaints, vital_trends

### Longitudinal Response Data

```json
{
  "longitudinal_data": {
    "baseline_visit": {
      "extraction_id": "uuid",
      "created_at": "2024-01-10T10:00:00Z"
    },
    "current_visit": {
      "extraction_id": "uuid",
      "created_at": "2024-01-15T14:00:00Z"
    },
    "medication_changes": {
      "added": ["Metformin 500mg"],
      "removed": ["Ibuprofen 400mg"],
      "unchanged": ["Aspirin 75mg"]
    },
    "new_diagnoses": ["Type 2 Diabetes"],
    "resolved_complaints": ["Headache"],
    "vital_trends": {
      "blood_pressure": {
        "status": "decreased",
        "baseline": "140/90",
        "current": "130/85",
        "change": -10
      }
    },
    "time_span_days": 5
  }
}
```

---

## Response Formats

### Narrative Response
```json
{
  "response_format": "narrative",
  "narrative": "Based on the analysis of 45 patient records, the most common diagnoses are: Type 2 Diabetes (35%), Hypertension (28%), and Dyslipidemia (18%). These conditions often co-occur, with 40% of diabetic patients also having hypertension."
}
```

### Table Response
```json
{
  "response_format": "table",
  "results": [
    {
      "extraction_id": "uuid",
      "patient_name": "John Doe",
      "patient_external_id": "UHID001",
      "doctor_name": "Dr. Smith",
      "consultation_type_name": "Outpatient",
      "created_at": "2024-01-15T10:30:00Z",
      "similarity_score": 0.92,
      "matched_segment_code": "DIAGNOSIS",
      "matched_content_preview": "Type 2 Diabetes Mellitus..."
    }
  ],
  "total_count": 15
}
```

### Chart Response
```json
{
  "response_format": "chart",
  "chart": {
    "chart_type": "pie",
    "title": "Consultation Type Distribution",
    "labels": ["Outpatient", "Discharge", "Follow-up"],
    "values": [150, 45, 80]
  }
}
```

### Stat Card Response
```json
{
  "response_format": "stat_card",
  "stat_card": {
    "title": "Total Extractions",
    "value": 1250,
    "subtitle": "This Month",
    "change_percent": 12.5,
    "trend": "up"
  }
}
```

---

## Frontend Integration

### Required Filters

1. **Hospital** (required): Scope all queries to a hospital
2. **Doctor** (optional): Filter to a specific doctor's patients
3. **Patient** (optional, required for longitudinal): Select specific patient
4. **Consultation Type** (optional): Filter by consultation type
5. **Visit** (optional): Select specific visit for context

### Filter Cascade

```
Hospital → Doctor → Patient → Visit
              ↓
    Consultation Type (independent)
```

### Display Components

1. **Temporal Context Box** (blue): Shows resolved temporal references
2. **Comparison Summary Box** (purple): Shows longitudinal comparison data
3. **Narrative Box**: Natural language response
4. **Results Table**: Search results with patient/extraction details
5. **Chart/Stat Card**: Analytics visualizations

### Example Frontend State

```typescript
interface QAState {
  selectedHospitalId: string | null;
  selectedDoctorId: string | null;
  selectedPatientId: string | null;
  selectedConsultationTypeId: string | null;
  selectedVisitId: string | null;  // extraction_id
  query: string;
}
```

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "Hospital context required" | No hospital_id provided | Include hospital_id in request |
| "Patient context required for temporal queries" | Longitudinal query without patient_id | Select a patient first |
| "No visits found for patient" | Patient has no extractions | Check patient has consultation history |
| "SQL validation failed" | Dangerous SQL detected | Query is blocked for safety |

### Error Response Format

```json
{
  "success": false,
  "query": "...",
  "intent": "semantic",
  "response_format": "narrative",
  "error_message": "Hospital context required for Q&A queries"
}
```

---

## Performance Metrics

Each response includes timing metrics:

| Metric | Description |
|--------|-------------|
| `reframe_time_ms` | Time to reframe/expand query |
| `embedding_time_ms` | Time to generate query embedding |
| `search_time_ms` | Time for vector similarity search |
| `synthesis_time_ms` | Time for LLM narrative synthesis |
| `temporal_resolution_time_ms` | Time to resolve temporal references |
| `longitudinal_time_ms` | Time for visit comparison |
| `total_time_ms` | Total request time |

Typical response times:
- Simple semantic queries: 8-12 seconds
- Analytics queries: 10-15 seconds
- Longitudinal queries: 10-15 seconds

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01-26 | Initial Q&A Engine with semantic search |
| 1.1 | 2024-01-26 | Added longitudinal patient history support |
| 1.2 | 2024-01-26 | Added query reframing and analytics fallbacks |
| 1.3 | 2025-01-27 | Accept external patient ID (UHID) in `patient_id` field (varchar, auto-resolved) |
| 1.4 | 2025-01-27 | Accept `hospital_code` as alternative to `hospital_id` |
| 1.5 | 2025-02-02 | Single-visit temporal queries return focused narrative instead of full patient table |
| 1.6 | 2025-02-02 | Conversation context (`prior_context`) for follow-up query resolution |

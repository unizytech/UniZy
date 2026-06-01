# Merge API Documentation

## Overview

The Merge API allows combining multiple medical extractions and/or JSON uploads into a single consolidated record. This document covers all API endpoints, request/response models, and usage scenarios.

**Base URL:** `/api/v1/extractions`

> **LEGACY NOTE:** Prior to v2.0 (2025-12-13), the merge API used `target_consultation_type_code` to specify the output format. This has been replaced with `target_template_code` which provides more flexibility through doctor-specific templates. See [Migration from LEGACY API](#migration-from-legacy-api) section.

### Async Architecture

The main `/merge` endpoint is **asynchronous**:

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  POST /merge    │      │  Background     │      │  Webhook or     │
│                 │ ───► │  Processing     │ ───► │  Poll Status    │
│  Returns 202    │      │  (AI Merge)     │      │  for Result     │
│  + extraction_id│      │                 │      │                 │
└─────────────────┘      └─────────────────┘      └─────────────────┘
     ~100ms                  10-30 seconds
```

**Flow:**
1. `POST /merge` returns immediately (HTTP 202) with `extraction_id`
2. Background task performs AI-powered merge
3. Track completion via:
   - **Polling:** `GET /merge/status/{extraction_id}`
   - **Webhook:** Notification sent when complete (includes same `extraction_id`)

---

## Table of Contents

1. [Key Concepts](#key-concepts)
2. [API Endpoints](#api-endpoints)
3. [Request Models](#request-models)
4. [Response Models](#response-models)
5. [Usage Scenarios](#usage-scenarios)
6. [Upload Types & Merge Strategies](#upload-types--merge-strategies)
7. [Error Handling](#error-handling)
8. [Getting Available Templates](#getting-available-templates)
9. [Migration from LEGACY API](#migration-from-legacy-api)

---

## Key Concepts

### Identifiers

| Identifier | Type | Description | Source |
|------------|------|-------------|--------|
| `extraction_id` | UUID | Unique ID for an extraction record | `extractions.id` |
| `submission_id` | UUID | Processing job ID from recording flow | `processing_jobs.submission_id` |
| `student_id` | VARCHAR | External patient identifier (e.g., "PAT-12345", MRN) | User input |
| `student_id` (DB) | UUID | Internal patient UUID | `patients.id` |

### Important Notes

- **Regular extractions** (from recording): Have both `submission_id` and `extraction_id`
- **Merged extractions**: Have only `extraction_id` (submission_id is NULL)
- **student_id resolution**: External VARCHAR IDs are automatically resolved to internal UUIDs

### Source Limits

- **Minimum:** 2 sources total (any combination)
- **Maximum:** 4 sources total (extractions + JSON uploads combined)

---

## API Endpoints

### 1. Merge Extractions (Async)

**POST** `/merge`

**HTTP Status:** `202 Accepted`

Initiates an async merge operation. Returns **immediately** (~100ms) with `extraction_id`. The actual merge processing happens in the background (10-30 seconds).

```bash
curl -X POST "http://localhost:8000/api/v1/extractions/merge" \
  -H "Content-Type: application/json" \
  -d '{
    "source_extraction_ids": ["uuid1", "uuid2"],
    "target_template_code": "OP_GENERAL",
    "counsellor_id": "doctor-uuid"
  }'
```

**Response:** `MergeAsyncResponse`
```json
{
  "success": true,
  "extraction_id": "550e8400-e29b-41d4-a716-446655440099",
  "status": "processing",
  "message": "Merge operation started. Use extraction_id to check status or receive webhook."
}
```

**Next Steps:**
1. Store the `extraction_id`
2. Poll `GET /merge/status/{extraction_id}` until `status` is `completed` or `failed`
3. Or wait for webhook notification with the same `extraction_id`

---

### 2. Preview Merge (Sync)

**POST** `/merge/preview`

Previews merge result without saving. Synchronous operation.

```bash
curl -X POST "http://localhost:8000/api/v1/extractions/merge/preview" \
  -H "Content-Type: application/json" \
  -d '{
    "source_extraction_ids": ["uuid1", "uuid2"],
    "target_template_code": "OP_GENERAL",
    "counsellor_id": "doctor-uuid"
  }'
```

**Response:** `MergeResponse`

---

### 3. Get Merge Status

**GET** `/merge/status/{extraction_id}`

Poll for async merge completion status.

```bash
curl "http://localhost:8000/api/v1/extractions/merge/status/{extraction_id}"
```

**Response:** `MergeStatusResponse`

---

### 4. Lookup Extraction by Submission ID

**GET** `/by-submission/{submission_id}`

Resolve a submission_id to extraction_id.

```bash
curl "http://localhost:8000/api/v1/extractions/by-submission/{submission_id}"
```

**Response:** `ExtractionLookupResponse`

---

### 5. Lookup Extraction by Session ID

**GET** `/by-session/{session_id}`

Resolve a session_id (correlation_id) to extraction_id.

```bash
curl "http://localhost:8000/api/v1/extractions/by-session/{session_id}"
```

**Response:** `ExtractionLookupResponse`

---

### 6. Get Patient Timeline

**GET** `/patient/{student_id}/timeline`

Get all extractions for a patient (for selection UI).

```bash
curl "http://localhost:8000/api/v1/extractions/patient/PAT-12345/timeline"
```

**Query Parameters:**
- `consultation_type_code` (optional): Filter by type

**Response:** `PatientTimelineResponse`

---

### 7. Get Merge Lineage

**GET** `/{extraction_id}/merge-info`

Get source extractions that were merged to create this extraction.

```bash
curl "http://localhost:8000/api/v1/extractions/{extraction_id}/merge-info"
```

**Response:** `MergeLineageResponse`

---

## Request Models

### MergeRequest / MergePreviewRequest

```typescript
interface MergeRequest {
  // Option 1: Direct extraction IDs (recommended)
  source_extraction_ids?: string[];      // UUIDs from extractions.id

  // Option 2: Submission IDs (auto-resolved to extraction IDs)
  source_submission_ids?: string[];      // UUIDs from processing_jobs.submission_id

  // Option 3: JSON uploads (can combine with above)
  uploaded_json_sources?: UploadedJsonSource[];

  // Required fields
  target_template_code: string;          // e.g., "OP_GENERAL", "OP_SMITH_1225141530"
  counsellor_id: string;                     // Doctor UUID performing merge (must have access to template)

  // Conditional fields
  student_id?: string;                   // Required for JSON-only merges (external ID like "PAT-12345")
  merge_notes?: string;                  // Optional notes
}
```

> **Template Access:** The doctor must have access to the specified template (owned, shared, or common template).

### UploadedJsonSource

```typescript
interface UploadedJsonSource {
  data: Record<string, any>;             // JSON data to merge
  upload_type: UploadType;               // Required - determines merge strategy
  source_name?: string;                  // Display name (e.g., "Lab Report")
  source_date?: string;                  // ISO date for chronological ordering
  consultation_type_code?: string;       // Optional - for field mapping
}

enum UploadType {
  // DEEP_MERGE strategy (contextual merging, latest wins for conflicts)
  OP_SUMMARY = "OP_SUMMARY",
  DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY",
  EXAMINATION = "EXAMINATION",
  OPTOMETRY = "OPTOMETRY",
  OTHER = "OTHER",

  // APPEND strategy (arrays concatenated, never replaced)
  INVESTIGATION = "INVESTIGATION",
  PRESCRIPTION = "PRESCRIPTION",
  NOTES = "NOTES"
}
```

---

## Response Models

### MergeAsyncResponse

Returned immediately from `/merge` endpoint.

```typescript
interface MergeAsyncResponse {
  success: boolean;
  extraction_id: string;                 // Use this to poll status
  status: "processing" | "completed" | "failed";
  message: string;
}
```

### MergeStatusResponse

Returned from `/merge/status/{extraction_id}`.

```typescript
interface MergeStatusResponse {
  extraction_id: string;
  status: "processing" | "completed" | "failed";
  progress?: string;
  merged_data?: Record<string, any>;     // Present when completed
  merge_metadata?: MergeMetadata;        // Present when completed
  error?: string;                        // Present when failed
  created_at?: string;
  completed_at?: string;
}
```

### MergeResponse

Returned from `/merge/preview` or after polling completion.

```typescript
interface MergeResponse {
  success: boolean;
  extraction_id?: string;                // null for preview
  merged_data: Record<string, any>;
  merge_metadata: MergeMetadata;
  preview: boolean;
}
```

### MergeMetadata

```typescript
interface MergeMetadata {
  source_count: number;
  target_template_code: string;          // Template code used for merge
  merge_timestamp: string;
  doctor_confirmed: boolean;
  merge_notes?: string;
  conflict_count: number;
  conflicts_resolved: string[];
  cross_type_scenario: string;           // e.g., "SAME_TYPE", "OP_to_DISCHARGE"
  consultation_types_merged: string[];
  schema_transformation?: SchemaTransformation;
  has_uploaded_json?: boolean;
  uploaded_json_source_names?: string[];
}
```

### PatientTimelineResponse

```typescript
interface PatientTimelineResponse {
  student_id: string;
  extractions: PatientTimelineExtraction[];
  total_count: number;
}

interface PatientTimelineExtraction {
  extraction_id: string;                 // Use this for merge
  consultation_type_code: string;
  consultation_type_name: string;
  created_at: string;
  doctor_name?: string;
  is_merged: boolean;                    // true if this is a merged record
  source_count: number;                  // Number of sources (if merged)
  segment_count: number;
}
```

### ExtractionLookupResponse

```typescript
interface ExtractionLookupResponse {
  extraction_id?: string;
  submission_id?: string;
  session_id?: string;
  consultation_type_code?: string;
  found: boolean;
  message?: string;
}
```

---

## Usage Scenarios

### Scenario 1: Merge Two Database Extractions

**When to use:** Merging two regular extractions from recordings.

**Option A: Using extraction_ids (Recommended)**
```json
POST /api/v1/extractions/merge
{
  "source_extraction_ids": [
    "550e8400-e29b-41d4-a716-446655440001",
    "550e8400-e29b-41d4-a716-446655440002"
  ],
  "target_template_code": "OP_GENERAL",
  "counsellor_id": "550e8400-e29b-41d4-a716-446655440099"
}
```

**Option B: Using submission_ids (Convenience wrapper)**
```json
POST /api/v1/extractions/merge
{
  "source_submission_ids": [
    "submission-uuid-1",
    "submission-uuid-2"
  ],
  "target_template_code": "OP_GENERAL",
  "counsellor_id": "550e8400-e29b-41d4-a716-446655440099"
}
```

> **Note:** `source_submission_ids` are automatically resolved to `extraction_ids` internally.

---

### Scenario 2: Merge Database Extraction + JSON Upload

**When to use:** Adding external data (lab results, imaging, etc.) to an existing extraction.

**Option A: Using extraction_ids**
```json
POST /api/v1/extractions/merge
{
  "source_extraction_ids": ["550e8400-e29b-41d4-a716-446655440001"],
  "uploaded_json_sources": [
    {
      "data": {
        "investigations": [
          {"test": "HbA1c", "value": "7.2%", "date": "2025-12-10"},
          {"test": "Lipid Panel", "value": "Normal", "date": "2025-12-10"}
        ]
      },
      "upload_type": "INVESTIGATION",
      "source_name": "Lab Report Dec 2025",
      "source_date": "2025-12-10"
    }
  ],
  "target_template_code": "OP_GENERAL",
  "counsellor_id": "550e8400-e29b-41d4-a716-446655440099"
}
```

**Option B: Using submission_ids**
```json
POST /api/v1/extractions/merge
{
  "source_submission_ids": ["submission-uuid-1"],
  "uploaded_json_sources": [
    {
      "data": {
        "investigations": [
          {"test": "HbA1c", "value": "7.2%", "date": "2025-12-10"}
        ]
      },
      "upload_type": "INVESTIGATION",
      "source_name": "Lab Report Dec 2025",
      "source_date": "2025-12-10"
    }
  ],
  "target_template_code": "OP_GENERAL",
  "counsellor_id": "550e8400-e29b-41d4-a716-446655440099"
}
```

**Key points:**
- Can use either `source_extraction_ids` OR `source_submission_ids` for the DB extraction
- `student_id` is **optional** (derived from the extraction)
- `upload_type` determines merge strategy (INVESTIGATION = APPEND)
- Multiple JSON sources can be included (up to 4 total sources)

---

### Scenario 3: Merge with a Previously Merged Record

**When to use:** Adding more data to an already-merged extraction.

**MUST use `source_extraction_ids`** - merged records don't have submission_ids.

```json
POST /api/v1/extractions/merge
{
  "source_extraction_ids": [
    "merged-extraction-uuid",
    "new-extraction-uuid"
  ],
  "target_template_code": "DISCHARGE_GENERAL",
  "counsellor_id": "550e8400-e29b-41d4-a716-446655440099"
}
```

**Or with JSON upload:**
```json
POST /api/v1/extractions/merge
{
  "source_extraction_ids": ["merged-extraction-uuid"],
  "uploaded_json_sources": [
    {
      "data": {"discharge_notes": "Patient stable for discharge"},
      "upload_type": "NOTES",
      "source_name": "Discharge Notes"
    }
  ],
  "target_template_code": "DISCHARGE_GENERAL",
  "counsellor_id": "550e8400-e29b-41d4-a716-446655440099"
}
```

> **Important:** Since merged records have `submission_id = NULL`, you cannot use `source_submission_ids` for them. Always use `source_extraction_ids`.

---

### Scenario 4: JSON-Only Merge (No Database Extractions)

**When to use:** Creating a new extraction purely from uploaded JSON data.

**Requirements:**
- `student_id` is **REQUIRED** (external ID like "PAT-12345")
- `upload_type` is **REQUIRED** for each JSON source
- Minimum 2 JSON sources

```json
POST /api/v1/extractions/merge
{
  "source_extraction_ids": [],
  "uploaded_json_sources": [
    {
      "data": {
        "chiefComplaints": "Fever and cough for 3 days",
        "diagnosis": "Upper respiratory infection"
      },
      "upload_type": "OP_SUMMARY",
      "source_name": "External Clinic Summary",
      "source_date": "2025-12-08"
    },
    {
      "data": {
        "medications": [
          {"name": "Paracetamol", "dosage": "500mg", "frequency": "TID"}
        ]
      },
      "upload_type": "PRESCRIPTION",
      "source_name": "External Prescription",
      "source_date": "2025-12-08"
    }
  ],
  "target_template_code": "OP_GENERAL",
  "counsellor_id": "550e8400-e29b-41d4-a716-446655440099",
  "student_id": "PAT-12345"
}
```

**What happens:**
1. System resolves "PAT-12345" to internal UUID (auto-creates patient if not exists)
2. Merges JSON sources based on their `upload_type` strategies
3. Creates new extraction record linked to patient

---

### Scenario 5: Cross-Type Merge (OP → DISCHARGE)

**When to use:** Converting/consolidating OP consultation data into a discharge summary.

```json
POST /api/v1/extractions/merge
{
  "source_extraction_ids": [
    "op-extraction-uuid-1",
    "op-extraction-uuid-2"
  ],
  "target_template_code": "DISCHARGE_GENERAL",
  "counsellor_id": "550e8400-e29b-41d4-a716-446655440099",
  "merge_notes": "Consolidating OP visits into discharge summary"
}
```

**System behavior:**
- Detects cross-type scenario: `OP_to_DISCHARGE`
- Uses specialized merge instructions for this transformation
- Maps fields appropriately (e.g., OP chief complaints → admission reason)

---

### Scenario 6: Multiple JSON Sources with Different Merge Strategies

**When to use:** Combining various external data types into one extraction.

```json
POST /api/v1/extractions/merge
{
  "source_extraction_ids": ["existing-extraction-uuid"],
  "uploaded_json_sources": [
    {
      "data": {"test_results": [...]},
      "upload_type": "INVESTIGATION",
      "source_name": "Lab Results"
    },
    {
      "data": {"medications": [...]},
      "upload_type": "PRESCRIPTION",
      "source_name": "Pharmacy Record"
    },
    {
      "data": {"vitals": {"bp": "120/80", "temp": "98.6"}},
      "upload_type": "EXAMINATION",
      "source_name": "Nursing Notes"
    }
  ],
  "target_template_code": "OP_GENERAL",
  "counsellor_id": "550e8400-e29b-41d4-a716-446655440099"
}
```

**Merge behavior:**
- `INVESTIGATION` (APPEND): Arrays concatenated to existing investigations
- `PRESCRIPTION` (APPEND): Medications added to existing prescription list
- `EXAMINATION` (DEEP_MERGE): Vitals merged, latest values win for conflicts

---

## Upload Types & Merge Strategies

### DEEP_MERGE Types

Data is contextually merged. For conflicts, the most recent/complete value wins.

| Upload Type | Description | Example Data |
|-------------|-------------|--------------|
| `OP_SUMMARY` | Outpatient consultation summary | Chief complaints, diagnosis, history |
| `DISCHARGE_SUMMARY` | Hospital discharge summary | Admission/discharge details, hospital course |
| `EXAMINATION` | Physical examination, vitals | BP, temperature, general examination |
| `OPTOMETRY` | Ophthalmology/optometry data | Vision tests, refraction data |
| `OTHER` | General/fallback type | Any unclassified data |

**Behavior:**
- Object fields: Deep merged recursively
- Scalar fields: Latest non-empty value wins
- Array fields: Merged and deduplicated where possible

### APPEND Types

Data is always appended. Existing arrays are never replaced.

| Upload Type | Description | Example Data |
|-------------|-------------|--------------|
| `INVESTIGATION` | Lab results, imaging reports | Blood tests, X-rays, MRI reports |
| `PRESCRIPTION` | Medications, prescriptions | Drug list, dosages, frequencies |
| `NOTES` | Clinical notes, documentation | Progress notes, nursing notes |

**Behavior:**
- Array fields: Concatenated (all items preserved)
- Object fields: Added as new entries
- Never overwrites existing data

---

## Error Handling

### Common Errors

| Error | Status | Cause | Solution |
|-------|--------|-------|----------|
| "At least 2 sources required" | 400 | Less than 2 sources provided | Add more extraction IDs or JSON sources |
| "Maximum 4 sources allowed" | 400 | More than 4 total sources | Reduce number of sources |
| "student_id is required" | 400 | JSON-only merge without student_id | Provide `student_id` field |
| "Cannot use both source_extraction_ids and source_submission_ids" | 400 | Both fields provided | Use only one |
| "Failed to resolve submission_ids" | 400 | submission_id not found or still processing | Wait for processing or use extraction_id |
| "Template not found" | 404 | Invalid target_template_code | Use valid template code |
| "Doctor does not have access to template" | 403 | Doctor lacks access to template | Use an owned, shared, or common template |

### Handling Async Merge

```typescript
// 1. Start merge
const startResponse = await fetch('/api/v1/extractions/merge', {
  method: 'POST',
  body: JSON.stringify(mergeRequest)
});
const { extraction_id } = await startResponse.json();

// 2. Poll for completion
let status;
do {
  await sleep(2000); // Wait 2 seconds
  const statusResponse = await fetch(`/api/v1/extractions/merge/status/${extraction_id}`);
  status = await statusResponse.json();
} while (status.status === 'processing');

// 3. Handle result
if (status.status === 'completed') {
  console.log('Merged data:', status.merged_data);
} else {
  console.error('Merge failed:', status.error);
}
```

---

## Quick Reference: Which API to Use?

| Scenario | API Field | student_id | upload_type |
|----------|-----------|------------|-------------|
| 2+ DB extractions (regular) | `source_extraction_ids` OR `source_submission_ids` | Optional | N/A |
| DB extraction + JSON upload | (`source_extraction_ids` OR `source_submission_ids`) + `uploaded_json_sources` | Optional | Required |
| Merged record + anything | `source_extraction_ids` only (no submission_id available) | Optional | If JSON: Required |
| JSON-only (no extractions) | `uploaded_json_sources` only | **Required** | Required |

---

## Getting Available Templates

To populate the target template dropdown, use the existing templates API:

```bash
GET /api/v1/summary/templates?filter_type=doctor&counsellor_id={doctor-uuid}
```

**Response:** (full template objects - frontend transforms to simplified format)
```json
{
  "success": true,
  "counsellor_id": "doctor-uuid",
  "templates": [
    {
      "id": "template-uuid-1",
      "template_code": "OP_GENERAL",
      "template_name": "OP General",
      "counsellor_id": null,
      "consultation_type_code": "OP",
      "consultation_type_name": "Outpatient"
    },
    {
      "id": "template-uuid-2",
      "template_code": "OP_SMITH_1225141530",
      "template_name": "Dr. Smith's OP Template",
      "counsellor_id": "doctor-uuid",
      "consultation_type_code": "OP",
      "consultation_type_name": "Outpatient"
    }
  ],
  "count": 2
}
```

**Frontend transforms to `MergeTargetTemplate`:**
```typescript
{
  template_code: string;    // Use as dropdown value
  template_name: string;    // Display in dropdown
  is_common: boolean;       // Derived from counsellor_id === null
}
```

**Template Access Types:**
- **Owned:** Doctor owns the template (`templates.counsellor_id` = doctor's UUID)
- **Shared:** Shared via `counsellor_templates` junction table with `access_level='use'`
- **Common:** Platform-wide templates (`templates.counsellor_id` = NULL)

---

## Migration from LEGACY API

### What Changed (v2.0 - 2025-12-13)

**LEGACY (v1.x):**
```json
{
  "source_extraction_ids": [...],
  "target_consultation_type_code": "OP",  // Consultation type code
  "counsellor_id": "..."
}
```

**CURRENT (v2.0+):**
```json
{
  "source_extraction_ids": [...],
  "target_template_code": "OP_GENERAL",   // Template code
  "counsellor_id": "..."
}
```

### Key Changes

| Aspect | LEGACY (v1.x) | CURRENT (v2.0+) |
|--------|---------------|-----------------|
| Target field | `target_consultation_type_code` | `target_template_code` |
| Dropdown API | `GET /api/v1/summary/consultation-types` | `GET /api/v1/summary/templates?filter_type=doctor&counsellor_id=<uuid>` (existing endpoint) |
| Metadata field | `target_type_code` | `target_template_code` |
| Access control | None | Template access validation |
| Segment prompts | From `consultation_type_code` | From derived `consultation_type_code` (template → consultation_type lookup) |

### Migration Steps

1. **Update API calls:** Change `target_consultation_type_code` → `target_template_code`
2. **Update dropdown:** Fetch from `/templates?filter_type=doctor&counsellor_id=<uuid>` instead of `/consultation-types`
3. **Update metadata parsing:** Change `target_type_code` → `target_template_code`
4. **Ensure doctor access:** Templates now validate doctor has access (owned, shared, or common)

### Benefits of Template-Based API

- **Doctor-specific templates:** Each doctor can select their own templates for merge operations
- **Shared templates:** Templates shared via `counsellor_templates` junction are available
- **Common templates:** Platform-wide templates (`counsellor_id = NULL`) are always available as fallback
- **Access control:** Explicit validation that doctor can use the specified template before merge

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2025-12-13 | **Breaking:** Changed `target_consultation_type_code` to `target_template_code`. Added template access validation. Updated dropdown API to return doctor-accessible templates. |
| 1.0 | 2025-12-11 | Initial documentation |

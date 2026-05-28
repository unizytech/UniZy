# Medicine & Investigation JSON Upload API

API endpoints for uploading doctor medicine and investigation lists via JSON (alternative to CSV upload).

**Base URL:** `https://<your-domain>/api/v1`

**Authentication:** All endpoints require an API key via `X-API-Key` header or Bearer token.

---

## 1. Upload Medicines (JSON)

Upload a list of medicines for a doctor. Applies the same enrichment, normalization, deduplication, and upsert logic as CSV upload.

**Endpoint:** `POST /api/v1/medicines/{doctor_id}/upload-json`

**Query Parameters:**

| Parameter          | Type    | Default | Description                                      |
|--------------------|---------|---------|--------------------------------------------------|
| `replace_existing` | boolean | `false` | If `true`, deactivates all existing medicines before uploading |

**Request Body:**

```json
{
  "medicines": [
    {
      "name": "Amoxicillin 500mg",
      "external_id": "MED-001",
      "common_name": ["Amox", "Amoxil"],
      "category": "Antibiotic",
      "typical_dosage": "500mg TID",
      "form": "capsule",
      "snomed_code": "27658006",
      "formulary_name": "Amoxicillin Trihydrate 500mg",
      "type": "branded"
    },
    {
      "name": "Paracetamol 650mg",
      "external_id": "MED-002",
      "common_name": "Dolo, Calpol, Acetaminophen",
      "type": "generic"
    }
  ]
}
```

**Field Reference:**

| Field            | Type                | Required | Description                                              |
|------------------|---------------------|----------|----------------------------------------------------------|
| `name`           | string              | Yes      | Medicine name                                            |
| `external_id`    | string              | Yes      | Your EHR/system ID for this medicine (used for EHR sync) |
| `common_name`    | string \| string[]  | No       | Alternative names — accepts a list or comma-separated string |
| `category`       | string              | No       | Therapeutic category (e.g., "Antibiotic", "Antihypertensive") |
| `typical_dosage` | string              | No       | Typical dosage (e.g., "500mg TID")                       |
| `form`           | string              | No       | Dosage form (e.g., "tablet", "capsule", "syrup")         |
| `snomed_code`    | string              | No       | SNOMED CT code                                           |
| `formulary_name` | string              | No       | Official formulary/pharmacopeia name                     |
| `type`           | string              | No       | `"generic"` or `"branded"`                               |

**Response (200):**

```json
{
  "upload_id": "uuid-of-upload-record",
  "status": "completed",
  "total_rows": 2,
  "successful": 2,
  "failed": 0,
  "errors": []
}
```

**Error Response (400):**

```json
{
  "detail": "Invalid UUID format"
}
```

---

## 2. Upload Investigations (JSON)

Upload a list of investigations/lab tests for a doctor. Applies the same enrichment, normalization, deduplication, and upsert logic as CSV upload.

**Endpoint:** `POST /api/v1/investigations/{doctor_id}/upload-json`

**Query Parameters:**

| Parameter          | Type    | Default | Description                                            |
|--------------------|---------|---------|--------------------------------------------------------|
| `replace_existing` | boolean | `false` | If `true`, deactivates all existing investigations before uploading |

**Request Body:**

```json
{
  "investigations": [
    {
      "name": "Complete Blood Count",
      "external_id": "INV-001",
      "common_names": ["CBC", "Full Blood Count", "FBC"],
      "type": "laboratory",
      "category": "Hematology",
      "normal_range": "WBC: 4000-11000/uL",
      "loinc_code": "58410-2",
      "cpt_code": "85025"
    },
    {
      "name": "Chest X-Ray PA View",
      "external_id": "INV-002",
      "common_names": "CXR, Chest Radiograph",
      "type": "imaging",
      "category": "Radiology"
    }
  ]
}
```

**Field Reference:**

| Field          | Type                | Required | Description                                                  |
|----------------|---------------------|----------|--------------------------------------------------------------|
| `name`         | string              | Yes      | Investigation name                                           |
| `external_id`  | string              | Yes      | Your EHR/system ID for this investigation (used for EHR sync)|
| `common_names` | string \| string[]  | No       | Alternative names — accepts a list or comma-separated string |
| `type`         | string              | No       | `"laboratory"`, `"imaging"`, or `"other"`                    |
| `category`     | string              | No       | Category (e.g., "Hematology", "Radiology", "Microbiology")  |
| `normal_range` | string              | No       | Normal reference range (for lab tests)                       |
| `loinc_code`   | string              | No       | LOINC code                                                   |
| `cpt_code`     | string              | No       | CPT procedure code                                           |

**Response (200):**

```json
{
  "upload_id": "uuid-of-upload-record",
  "status": "completed",
  "total_rows": 2,
  "successful": 2,
  "failed": 0,
  "errors": []
}
```

---

## Notes

### Deduplication
Both endpoints deduplicate by normalized name within the same upload. If two items have the same normalized name, the last one wins. Across uploads, items are upserted (matched by `doctor_id` + `normalized_name`), so re-uploading an item with the same name updates it rather than creating a duplicate.

### `replace_existing` Behavior
When `replace_existing=true`, all existing items for the doctor are **deactivated** (soft-deleted) before the new list is inserted. This is useful for full-list replacement syncs. When `false` (default), new items are merged with existing ones.

### `external_id` and EHR Sync
The `external_id` field is critical for EHR integration. When AI extracts a medicine/investigation from a consultation, the system fuzzy-matches it against the doctor's list. If a match is found, the `external_id` is attached to the extraction and sent to the EHR system (e.g., as `brand_id` for AOSTA, `drug_id` for KG). Items without an `external_id` match will still be sent to the EHR but with a null ID.

### `common_name` / `common_names`
These fields improve matching accuracy. When AI extracts "CBC", it will match to "Complete Blood Count" if "CBC" is listed as a common name. Accepts either a JSON array or a comma-separated string.

### Error Handling
- Partial failures are supported — if some items fail validation, the rest are still uploaded
- The `errors` array in the response contains details for the first 10 failures
- The `failed` count reflects the total number of failures

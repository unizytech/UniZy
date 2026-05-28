# 1hat Billing API Documentation

Base URL: `{BACKEND_URL}/api/v1/billing`

Authentication: `Authorization: Bearer <api_key>`

---

## Overview

The billing system generates itemized bills from medical extraction data or as standalone bills (e.g., registration-only). Each extraction-based bill is tied to a single extraction and contains line items for registration fees, consultation fees, pharmacy (prescriptions), lab/radiology (investigations), and procedures. Standalone bills can be created independently without an extraction.

### Bill Lifecycle

```
generate → draft → (edit line items) → confirm
                 → regenerate (deletes draft, creates new)

create (standalone) → draft → (edit line items) → confirm
```

- **draft**: Editable. Line items can be added, updated, or deleted.
- **confirmed**: Locked. No edits or regeneration allowed.
- **superseded**: Replaced by a merged bill (IP workflow).

### Visit Tracking Fields

All bill creation/generation endpoints support visit tracking fields (`visit_id`, `visit_date`, `billed_by`). These are:
- **Required** on `POST /create` (standalone bills)
- **Optional** on `POST /generate`, `POST /regenerate`, `POST /generate-merged` (extraction-based bills)
- **Updatable** via `PATCH /{bill_id}` on draft bills

### Line Item Confidence & Billing Action

| billing_action | Meaning | When |
|---|---|---|
| `auto_billed` | No review needed | Registration fee, consultation fee (known amounts) |
| `pending_review` | Price found, needs confirmation | Matched item with ≥85% confidence |
| `flagged_manual` | Needs manual pricing/review | No match, no price, low confidence, or high-value item |

---

## Endpoints

### 1. Generate Bill

**`POST /api/v1/billing/generate/{extraction_id}`**

Generates a bill from an extraction. Reads the extraction JSON, resolves hospital/doctor/patient, and creates line items.

**Request:**
```
POST /api/v1/billing/generate/782d7f31-725f-4e85-aa74-d1dcd475b82f
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Body (optional):**
```json
{
  "visit_id": "V-2026-001234",
  "visit_date": "2026-03-12T10:30:00Z",
  "billed_by": "front_desk_user"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `visit_id` | string | No | EHR visit ID |
| `visit_date` | string | No | Visit date (ISO format) |
| `billed_by` | string | No | User who triggered billing |

**Response (200):**
```json
{
  "success": true,
  "message": "Bill generated successfully",
  "bill": {
    "id": "f4a96a58-6edc-4a26-a42d-4857938a6689",
    "extraction_id": "782d7f31-725f-4e85-aa74-d1dcd475b82f",
    "hospital_id": "44cc627a-...",
    "patient_id": "c238ddf5-...",
    "doctor_id": "83b3eb65-...",
    "bill_type": "OP",
    "bill_status": "draft",
    "consultation_type_code": "OP",
    "is_merged_bill": false,
    "visit_id": "V-2026-001234",
    "visit_date": "2026-03-12T10:30:00+00:00",
    "billed_by": "front_desk_user",
    "total_amount": 600.00,
    "auto_billed_amount": 600.00,
    "pending_review_amount": 0.00,
    "flagged_amount": 0.00,
    "generation_metadata": {
      "generated_at": "2026-03-11T04:46:25.186445",
      "line_item_count": 10,
      "extraction_id": "782d7f31-..."
    },
    "created_at": "2026-03-11T04:46:25.329843+00:00",
    "updated_at": "2026-03-11T04:46:25.329843+00:00",
    "line_items": [
      {
        "id": "0830d14f-...",
        "bill_id": "f4a96a58-...",
        "category": "registration",
        "description": "OP Registration Fee",
        "item_code": null,
        "quantity": 1.0,
        "unit_price": 100.00,
        "total_price": 100.00,
        "confidence": "high",
        "billing_action": "auto_billed",
        "source_segment": "registration",
        "source_item_index": null,
        "matched_master_id": null,
        "matched_master_table": null,
        "match_confidence": null,
        "notes": null,
        "created_at": "2026-03-11T04:46:25.531259+00:00"
      },
      {
        "id": "acd15545-...",
        "category": "consultation",
        "description": "Consultation Fee - Prakash Kumar",
        "quantity": 1.0,
        "unit_price": 500.00,
        "total_price": 500.00,
        "confidence": "high",
        "billing_action": "auto_billed",
        "source_segment": "doctor_identity"
      },
      {
        "id": "70a13b88-...",
        "category": "pharmacy",
        "description": "ACECLOFENAC",
        "quantity": 6.0,
        "unit_price": null,
        "total_price": null,
        "confidence": "low",
        "billing_action": "flagged_manual",
        "source_segment": "prescription",
        "source_item_index": 0,
        "notes": "Medicine not matched to hospital list"
      },
      {
        "id": "14b33521-...",
        "category": "lab",
        "description": "Complete Blood Count",
        "quantity": 1.0,
        "unit_price": null,
        "total_price": null,
        "confidence": "low",
        "billing_action": "flagged_manual",
        "source_segment": "investigations",
        "source_item_index": 0,
        "notes": "Investigation not matched to hospital list"
      }
    ]
  }
}
```

**Errors:**
| HTTP Code | Detail | Cause |
|---|---|---|
| 404 | Extraction not found | Invalid extraction_id |
| 400 | Cannot determine hospital_id | Doctor has no hospital assigned |
| 409 | Bill already exists for this extraction | Use `/regenerate` instead |

---

### 2. Create Standalone Bill

**`POST /api/v1/billing/create`**

Creates a standalone bill with no extraction (e.g., registration-only bills, walk-in charges). The bill is created with `extraction_id = null`.

**Request:**
```
POST /api/v1/billing/create
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Body:**
```json
{
  "hospital_code": "HOSP001",
  "patient_id": "UHID-12345",
  "doctor_id": "83b3eb65-...",
  "bill_type": "OP",
  "consultation_type_code": "OP",
  "visit_id": "V-2026-001234",
  "visit_date": "2026-03-12T10:30:00Z",
  "billed_by": "front_desk_user",
  "line_items": [
    {
      "category": "registration",
      "description": "OP Registration Fee",
      "quantity": 1,
      "unit_price": 100.00,
      "billing_action": "auto_billed"
    },
    {
      "category": "miscellaneous",
      "description": "File charges",
      "quantity": 1,
      "unit_price": 50.00,
      "billing_action": "auto_billed"
    }
  ]
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `hospital_code` | string | **Yes** | — | Hospital code (resolved to UUID internally) |
| `visit_id` | string | **Yes** | — | EHR visit ID |
| `visit_date` | string | **Yes** | — | Visit date (ISO format) |
| `billed_by` | string | **Yes** | — | User who created the bill |
| `patient_id` | string | No | null | Patient external ID (UHID) — resolved to UUID internally |
| `doctor_id` | string | No | null | Doctor UUID |
| `bill_type` | string | No | `OP` | `OP` or `IP` |
| `consultation_type_code` | string | No | null | Consultation type code |
| `line_items` | array | No | null | Initial line items (same schema as Add Line Items) |

**Response (200):**
```json
{
  "success": true,
  "message": "Standalone bill created successfully",
  "bill": {
    "id": "b1c2d3e4-...",
    "extraction_id": null,
    "hospital_id": "44cc627a-...",
    "patient_id": "c238ddf5-...",
    "doctor_id": "83b3eb65-...",
    "bill_type": "OP",
    "bill_status": "draft",
    "visit_id": "V-2026-001234",
    "visit_date": "2026-03-12T10:30:00+00:00",
    "billed_by": "front_desk_user",
    "is_merged_bill": false,
    "total_amount": 150.00,
    "auto_billed_amount": 150.00,
    "pending_review_amount": 0.00,
    "flagged_amount": 0.00,
    "generation_metadata": {
      "generated_at": "2026-03-12T10:35:00.000000",
      "line_item_count": 2,
      "standalone": true
    },
    "line_items": [...]
  }
}
```

**Errors:**
| HTTP Code | Detail |
|---|---|
| 404 | Hospital not found or inactive |
| 404 | No patient found with UHID |
| 400 | bill_type must be 'OP' or 'IP' |
| 400 | Invalid category / Invalid billing_action |
| 422 | Missing required field (hospital_code, visit_id, visit_date, or billed_by) |

---

### 3. Get Bill by Extraction

**`GET /api/v1/billing/extraction/{extraction_id}`**

Returns the active (non-superseded) bill for a given extraction, with all line items.

**Request:**
```
GET /api/v1/billing/extraction/782d7f31-725f-4e85-aa74-d1dcd475b82f
Authorization: Bearer <api_key>
```

**Response (200):**
```json
{
  "success": true,
  "bill": { /* same structure as generate response */ }
}
```

**Errors:**
| HTTP Code | Detail |
|---|---|
| 404 | No bill found for this extraction |

---

### 4. Get Bills by Visit ID

**`GET /api/v1/billing/visit/{visit_id}`**

Returns all bills for a given EHR visit ID, with line items included. Useful for EHR integrations that track billing by visit.

**Query Parameters:**
| Param | Type | Default | Description |
|---|---|---|---|
| `include_superseded` | bool | false | Include superseded bills |

**Request:**
```
GET /api/v1/billing/visit/V-2026-001234?include_superseded=false
Authorization: Bearer <api_key>
```

**Response (200):**
```json
{
  "success": true,
  "bills": [
    {
      "id": "f4a96a58-...",
      "extraction_id": "782d7f31-...",
      "visit_id": "V-2026-001234",
      "visit_date": "2026-03-12T10:30:00+00:00",
      "billed_by": "front_desk_user",
      "bill_type": "OP",
      "bill_status": "draft",
      "total_amount": 600.00,
      "line_items": [...]
    }
  ],
  "count": 1
}
```

**Errors:**
| HTTP Code | Detail |
|---|---|
| 404 | No bills found for visit_id |

---

### 5. Get Bill by ID

**`GET /api/v1/billing/{bill_id}`**

Returns a bill with all line items by its UUID.

**Request:**
```
GET /api/v1/billing/f4a96a58-6edc-4a26-a42d-4857938a6689
Authorization: Bearer <api_key>
```

**Response (200):**
```json
{
  "success": true,
  "bill": { /* same structure as generate response */ }
}
```

---

### 6. Get Bills by Patient

**`GET /api/v1/billing/patient/{patient_id}`**

Returns all bills for a patient (most recent first). Does not include line items — fetch individual bills for details. Supports optional `visit_id` filter to narrow results to a specific visit.

**Query Parameters:**
| Param | Type | Default | Description |
|---|---|---|---|
| `hospital_code` | string | null | Hospital code to scope patient lookup |
| `visit_id` | string | null | Filter by EHR visit ID |
| `visit_date` | string | null | Filter by visit date (ISO format) |
| `billed_by` | string | null | Filter by billed_by user |
| `include_superseded` | bool | false | Include superseded bills |

**Request:**
```
GET /api/v1/billing/patient/c238ddf5-5d12-4747-ad14-ee1c96b913c9?visit_id=V-2026-001234
Authorization: Bearer <api_key>
```

**Response (200):**
```json
{
  "success": true,
  "bills": [
    {
      "id": "02a49bee-...",
      "extraction_id": "557375a3-...",
      "bill_type": "OP",
      "bill_status": "draft",
      "visit_id": "V-2026-001234",
      "visit_date": "2026-03-12T10:30:00+00:00",
      "billed_by": "front_desk_user",
      "total_amount": 600.00,
      "auto_billed_amount": 600.00,
      "pending_review_amount": 0.00,
      "flagged_amount": 0.00,
      "created_at": "2026-03-11T05:01:22+00:00"
    },
    {
      "id": "b1c2d3e4-...",
      "extraction_id": null,
      "bill_type": "OP",
      "bill_status": "draft",
      "visit_id": "V-2026-001235",
      "total_amount": 150.00,
      "created_at": "2026-03-12T10:35:00+00:00"
    }
  ],
  "count": 2
}
```

---

### 7. Update Bill

**`PATCH /api/v1/billing/{bill_id}`**

Update bill-level fields on a draft bill. Use this to set or change visit tracking fields after bill creation.

**Request:**
```
PATCH /api/v1/billing/{bill_id}
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Body (all fields optional, at least one required):**
```json
{
  "visit_id": "V-2026-001234",
  "visit_date": "2026-03-12T10:30:00Z",
  "billed_by": "billing_clerk"
}
```

| Field | Type | Description |
|---|---|---|
| `visit_id` | string | EHR visit ID |
| `visit_date` | string | Visit date (ISO format) |
| `billed_by` | string | User who created/billed |

**Response (200):**
```json
{
  "success": true,
  "message": "Bill updated",
  "bill": {
    "id": "f4a96a58-...",
    "visit_id": "V-2026-001234",
    "visit_date": "2026-03-12T10:30:00+00:00",
    "billed_by": "billing_clerk",
    "bill_status": "draft",
    "updated_at": "2026-03-12T11:00:00+00:00"
  }
}
```

**Errors:**
| HTTP Code | Detail |
|---|---|
| 400 | No fields to update |
| 400 | Cannot modify a confirmed bill |
| 400 | Cannot modify a superseded bill |
| 404 | Bill not found |

---

### 8. Update Line Item

**`PUT /api/v1/billing/{bill_id}/line-items/{line_item_id}`**

Update price, quantity, billing action, or notes on a draft bill's line item. Automatically recalculates `total_price` and bill totals.

**Request:**
```
PUT /api/v1/billing/{bill_id}/line-items/{line_item_id}
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Body (all fields optional):**
```json
{
  "unit_price": 15.00,
  "quantity": 10,
  "billing_action": "pending_review",
  "notes": "Price confirmed with pharmacy"
}
```

| Field | Type | Values |
|---|---|---|
| `unit_price` | float | Any positive number |
| `quantity` | float | Any positive number |
| `billing_action` | string | `auto_billed`, `pending_review`, `flagged_manual` |
| `notes` | string | Free text |

**Response (200):**
```json
{
  "success": true,
  "message": "Line item updated",
  "line_item": {
    "id": "0bd40444-...",
    "unit_price": 15.00,
    "quantity": 10,
    "total_price": 150.00,
    "billing_action": "pending_review"
  }
}
```

**Errors:**
| HTTP Code | Detail |
|---|---|
| 400 | Cannot modify a confirmed bill |
| 404 | Bill not found / Line item not found in this bill |

---

### 9. Delete Line Item

**`DELETE /api/v1/billing/{bill_id}/line-items/{line_item_id}`**

Delete a line item from a draft bill. Automatically recalculates bill totals after deletion.

**Request:**
```
DELETE /api/v1/billing/{bill_id}/line-items/{line_item_id}
Authorization: Bearer <api_key>
```

No request body required.

**Response (200):**
```json
{
  "success": true,
  "message": "Line item deleted"
}
```

**Errors:**
| HTTP Code | Detail |
|---|---|
| 400 | Cannot modify a confirmed bill |
| 400 | Cannot modify a superseded bill |
| 404 | Bill not found |
| 404 | Line item not found in this bill |

---

### 10. Add Line Items

**`POST /api/v1/billing/{bill_id}/line-items`**

Add one or more line items to a draft bill. Use this for manually adding extra charges (miscellaneous fees, supplies, additional services) that aren't auto-generated from extraction data. Created items have `confidence: "high"` and `source_segment: "manual"`.

**Request:**
```
POST /api/v1/billing/f4a96a58-6edc-4a26-a42d-4857938a6689/line-items
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Body (array of line items):**
```json
[
  {
    "category": "miscellaneous",
    "description": "Dressing kit",
    "quantity": 1,
    "unit_price": 250.00,
    "billing_action": "auto_billed",
    "notes": "Used during consultation"
  },
  {
    "category": "procedure",
    "description": "Wound suturing",
    "quantity": 1,
    "unit_price": 1500.00,
    "item_code": "CPT-12001"
  }
]
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `category` | string | Yes | — | `registration`, `consultation`, `pharmacy`, `lab`, `radiology`, `procedure`, `room`, `admission`, `miscellaneous` |
| `description` | string | Yes | — | Item description |
| `quantity` | float | No | 1 | Quantity |
| `unit_price` | float | No | 0 | Price per unit |
| `billing_action` | string | No | `pending_review` | `auto_billed`, `pending_review`, `flagged_manual` |
| `item_code` | string | No | null | CPT code or item code |
| `notes` | string | No | null | Optional notes |

**Response (200):**
```json
{
  "success": true,
  "message": "2 line item(s) added",
  "line_items": [
    {
      "id": "a1b2c3d4-...",
      "bill_id": "f4a96a58-...",
      "category": "miscellaneous",
      "description": "Dressing kit",
      "item_code": null,
      "quantity": 1.0,
      "unit_price": 250.00,
      "total_price": 250.00,
      "confidence": "high",
      "billing_action": "auto_billed",
      "source_segment": "manual",
      "notes": "Used during consultation",
      "created_at": "2026-03-11T06:12:00.000000+00:00"
    },
    {
      "id": "e5f6g7h8-...",
      "bill_id": "f4a96a58-...",
      "category": "procedure",
      "description": "Wound suturing",
      "item_code": "CPT-12001",
      "quantity": 1.0,
      "unit_price": 1500.00,
      "total_price": 1500.00,
      "confidence": "high",
      "billing_action": "pending_review",
      "source_segment": "manual",
      "notes": null,
      "created_at": "2026-03-11T06:12:00.000000+00:00"
    }
  ]
}
```

**Errors:**
| HTTP Code | Detail |
|---|---|
| 400 | At least one line item is required |
| 400 | Invalid category / Invalid billing_action |
| 400 | Cannot modify a confirmed bill |
| 400 | Cannot modify a superseded bill |
| 404 | Bill not found |

---

### 11. Confirm Bill

**`PUT /api/v1/billing/{bill_id}/confirm`**

Transitions a draft bill to confirmed. After confirmation, the bill and its line items are locked.

**Request:**
```
PUT /api/v1/billing/{bill_id}/confirm
Authorization: Bearer <api_key>
```

No request body required.

**Response (200):**
```json
{
  "success": true,
  "message": "Bill confirmed",
  "bill": {
    "id": "f4a96a58-...",
    "bill_status": "confirmed",
    "total_amount": 615.00,
    "line_items": [...]
  }
}
```

**Errors:**
| HTTP Code | Detail |
|---|---|
| 400 | Bill is already confirmed |
| 400 | Cannot confirm a superseded bill |

---

### 12. Regenerate Bill

**`POST /api/v1/billing/regenerate/{extraction_id}`**

Deletes the existing draft bill for an extraction and generates a fresh one. Useful when extraction data has been re-processed or prices have been updated in masters.

**Request:**
```
POST /api/v1/billing/regenerate/{extraction_id}
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Body (optional):**
```json
{
  "visit_id": "V-2026-001234",
  "visit_date": "2026-03-12T10:30:00Z",
  "billed_by": "front_desk_user"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `visit_id` | string | No | EHR visit ID |
| `visit_date` | string | No | Visit date (ISO format) |
| `billed_by` | string | No | User who triggered billing |

**Response (200):**
```json
{
  "success": true,
  "message": "Bill regenerated successfully",
  "bill": { /* same structure as generate response */ }
}
```

**Errors:**
| HTTP Code | Detail |
|---|---|
| 400 | Cannot regenerate a confirmed bill |

---

### 13. Generate Merged Bill (IP)

**`POST /api/v1/billing/generate-merged/{extraction_id}`**

Generates a bill from a merged extraction (IP discharge workflow). Automatically supersedes any existing bills on source extractions.

**Request:**
```
POST /api/v1/billing/generate-merged/{merged_extraction_id}
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Body (optional):**
```json
{
  "visit_id": "V-2026-001234",
  "visit_date": "2026-03-12T10:30:00Z",
  "billed_by": "front_desk_user"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `visit_id` | string | No | EHR visit ID |
| `visit_date` | string | No | Visit date (ISO format) |
| `billed_by` | string | No | User who triggered billing |

**Response (200):**
```json
{
  "success": true,
  "message": "Merged bill generated successfully",
  "bill": { /* same structure, is_merged_bill = true */ },
  "superseded_count": 3
}
```

**Errors:**
| HTTP Code | Detail |
|---|---|
| 400 | This extraction is not a merged extraction |
| 409 | Bill already exists for this extraction |

---

## Line Item Categories

| category | Source | Description |
|---|---|---|
| `registration` | Hospital settings | OP registration fee |
| `admission` | Hospital settings | IP admission fee |
| `consultation` | Doctor record | Doctor's consultation fee |
| `pharmacy` | Extraction → prescription | Medicine line items |
| `lab` | Extraction → investigations (laboratory) | Lab test line items |
| `radiology` | Extraction → investigations (imaging) | Imaging study line items |
| `procedure` | Extraction → procedures | Procedure line items |
| `room` | Patient add_info → room_rate_master | Room charges (IP only) |
| `miscellaneous` | Manual entry | Extra charges (supplies, dressing kits, etc.) |

---

## Bill Object Schema

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Bill ID |
| `extraction_id` | UUID | Source extraction (null for standalone bills) |
| `hospital_id` | UUID | Hospital |
| `patient_id` | UUID | Patient (nullable) |
| `doctor_id` | UUID | Doctor (nullable) |
| `bill_type` | string | `OP` or `IP` |
| `bill_status` | string | `draft`, `confirmed`, `superseded` |
| `consultation_type_code` | string | e.g. `OP`, `DISCHARGE` |
| `is_merged_bill` | bool | From merged extraction |
| `superseded_by_bill_id` | UUID | Points to replacement bill (if superseded) |
| `visit_id` | string | EHR visit ID (nullable) |
| `visit_date` | timestamptz | Visit date (nullable) |
| `billed_by` | string | User who created/billed (nullable) |
| `total_amount` | float | Sum of all line item totals |
| `auto_billed_amount` | float | Sum of auto_billed items |
| `pending_review_amount` | float | Sum of pending_review items |
| `flagged_amount` | float | Sum of flagged_manual items |
| `generation_metadata` | object | Generation timestamp, warnings |
| `line_items` | array | Line items (included in GET responses) |

## Line Item Object Schema

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Line item ID |
| `bill_id` | UUID | Parent bill |
| `category` | string | See categories table above |
| `description` | string | Human-readable description |
| `item_code` | string | CPT/SNOMED/LOINC code (if available) |
| `quantity` | float | Quantity (calculated from prescription dosage x duration) |
| `unit_price` | float | Per-unit price (null if not found) |
| `total_price` | float | quantity x unit_price (null if price unknown) |
| `confidence` | string | `high`, `medium`, `low` |
| `billing_action` | string | `auto_billed`, `pending_review`, `flagged_manual` |
| `source_segment` | string | Which extraction segment this came from |
| `source_item_index` | int | Index in the source array (for mapping back to extraction) |
| `matched_master_id` | UUID | ID in the hospital master table that matched |
| `matched_master_table` | string | `hospital_medicine_lists`, `hospital_investigation_lists`, or `procedure_fee_master` |
| `match_confidence` | float | 0.0-1.0 match confidence from extraction pipeline |
| `notes` | string | System or user notes (e.g. "Medicine not matched to hospital list") |

---

## Typical Frontend Workflow

```
1. User clicks "Generate Bill" on extraction detail page
   -> POST /api/v1/billing/generate/{extraction_id}
   (optionally pass visit_id, visit_date, billed_by in body)

1b. Or create a standalone bill (e.g., registration only)
   -> POST /api/v1/billing/create
   (visit_id, visit_date, billed_by are required)

2. Display bill with line items grouped by category
   - Show auto_billed items as confirmed (green)
   - Show pending_review items as needs review (yellow)
   - Show flagged_manual items as needs attention (red)

3. User reviews flagged items, sets prices and quantities
   -> PUT /api/v1/billing/{bill_id}/line-items/{item_id}
   (for each edited item)

3b. User adds extra charges (supplies, misc fees)
   -> POST /api/v1/billing/{bill_id}/line-items
   (batch add one or more items)

3c. User removes unwanted line items
   -> DELETE /api/v1/billing/{bill_id}/line-items/{item_id}

3d. User updates visit tracking info
   -> PATCH /api/v1/billing/{bill_id}

4. User confirms the bill
   -> PUT /api/v1/billing/{bill_id}/confirm

5. To view existing bill for an extraction:
   -> GET /api/v1/billing/extraction/{extraction_id}

6. To list all bills for a patient:
   -> GET /api/v1/billing/patient/{patient_id}
```

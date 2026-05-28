# Ingest API — EMR/HIS Integration

## Endpoint

```
POST /api/v1/ingest
```

Accepts patient clinical data from EMR/HIS systems. Returns `202 Accepted` immediately; care plan and NudgePlan generation happen in the background.

Data is **accumulated per `extraction_id`** — you can send medical records, emotions, and interventions in separate calls. Care plan generation triggers automatically when both `patient_id` and `medical_records` are present. A NudgePlan (behavioral engagement schedule) is auto-generated right after the care plan.

---

## Request

### Recommended Payload

```json
{
  "extraction_id": "EXT-12345",
  "patient_id": "emr-patient-uuid",
  "patient_name": "Anita Desai",
  "doctor_id": "DOC-456",
  "doctor_name": "Dr. Rajesh Khanna",
  "medical_records": {
    "diagnosis": "Type 2 Diabetes with Diabetic Nephropathy",
    "medications": [
      { "drug": "Insulin Glargine 10 units", "route": "SC", "frequency": "once daily at bedtime" },
      { "drug": "Metformin 500mg", "route": "oral", "frequency": "twice daily after meals" }
    ],
    "vitals": { "bp": "148/92", "sugar_fasting": "186 mg/dL", "hba1c": "8.2%" },
    "diet": "Strict renal-diabetic diet. Limit protein.",
    "labs_ordered": ["HbA1c", "eGFR", "Lipid Profile"],
    "follow_up": "Review in 10 days with lab reports"
  },
  "emotions": {
    "anxiety_level": "high",
    "primary_concern": "Fear of insulin injections",
    "motivation": "moderate",
    "family_support": "strong"
  },
  "interventions": [
    { "name": "Insulin education program", "priority": "HIGH" },
    { "name": "Diet compliance tracking", "priority": "MEDIUM" }
  ],
  "patient_language": "en",
  "submission_id": "SUB-67890",
  "metadata": {
    "hospital_name": "Fortis Hospital, Mumbai",
    "department": "Nephrology",
    "visit_type": "follow_up"
  }
}
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `extraction_id` | string | **Yes** | Your unique reference for this clinical visit/encounter. Used to fetch the care plan later. |
| `patient_id` | UUID string | Recommended | Your patient identifier. Required for care plan generation. |
| `patient_name` | string | No | Patient's full name |
| `doctor_id` | string | No | Your doctor identifier |
| `doctor_name` | string | No | Treating doctor's name |
| `medical_records` | object | No* | Clinical data in **any format** — structured JSON, key-value pairs, etc. Care plan generation triggers when this is present. |
| `emotions` | object | No | Patient's emotional context — anxiety, motivation, concerns. Influences nudge tone. |
| `interventions` | array | No | Your suggested interventions. Auto-generated if omitted. |
| `patient_language` | string | No | Default: `"en"`. Options: `en`, `hi`, `ta`, `te`, `kn`, `ml`, `bn`, `mr`, `gu` |
| `submission_id` | string | No | Your submission/transaction reference |
| `metadata` | object | No | Any additional context (hospital, department, visit type, etc.) |

*`medical_records` is required to trigger care plan generation, but can be sent in a separate call.

### Accumulation (Multiple Calls)

You can send data incrementally — all calls with the same `extraction_id` are merged:

```
Call 1: { "extraction_id": "EXT-123", "patient_name": "...", "medical_records": {...} }
Call 2: { "extraction_id": "EXT-123", "emotions": {...} }
Call 3: { "extraction_id": "EXT-123", "interventions": [...] }
```

Care plan generation triggers when both `patient_id` and `medical_records` are present. If emotions/interventions arrive later, the care plan already has the core medical data.

### medical_records Format

**Any format is accepted.** The AI extracts structure from whatever you send. Examples:

```json
// Structured with specific fields
{
  "diagnosis": "Type 2 Diabetes",
  "medications": [{ "drug": "Metformin 500mg", "frequency": "twice daily" }],
  "vitals": { "bp": "130/85", "hba1c": "7.8%" }
}

// CCA format (legacy EMR systems)
{
  "insights": {
    "diagnosis": [{ "code": "E11", "name": "Type 2 Diabetes", "type": "Primary" }],
    "prescription": [{ "name": "Metformin 500mg", "morning_qty": "1", "night_qty": "1" }]
  }
}

// Free-form clinical notes
{
  "notes": "52M with uncontrolled T2DM (HbA1c 8.2%). On Metformin 500mg BD. Start Glimepiride 1mg OD. Avoid sweets. Follow up in 14 days with FBS, HbA1c."
}
```

---

## Response

### Success (202 Accepted)

```json
{
  "status": "accepted",
  "extraction_id": "EXT-12345",
  "patient_id": "550e8400-e29b-41d4-a716-446655440000",
  "processing": true,
  "message": "Data received. Care plan generation in progress."
}
```

| Field | Description |
|-------|-------------|
| `extraction_id` | Your reference ID — use this to fetch the care plan |
| `processing` | `true` if care plan generation has started, `false` if waiting for medical_records |

### When accumulating data (no medical_records yet, or no patient_id)

```json
{
  "status": "accepted",
  "extraction_id": "EXT-12345",
  "patient_id": "...",
  "processing": false,
  "message": "Data accumulated."
}
```

---


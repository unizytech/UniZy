# Other Clinical Needs Logic (v1.2.0)

## Overview

Other Clinical Needs identifies **downstream care requirements** beyond the current consultation. This helps clinical staff proactively plan for patient needs.

| Priority Level | Meaning |
|----------------|---------|
| **NONE** | No additional clinical needs identified |
| **LOW** | 1 indicator present - minor planning needed |
| **MEDIUM** | 2 indicators OR recurring diagnostics alone |
| **HIGH** | All 3 indicators OR (recurring + refill) both TRUE |

---

## Three Boolean Indicators

| Indicator | Description | Primary Triggers |
|-----------|-------------|------------------|
| `is_followup_diagnostics` | Patient needs tests before/at next visit | Ordered/pending tests in INVESTIGATIONS |
| `is_recurring_diagnostics` | Patient needs periodic monitoring tests | Chronic conditions, specific ICD codes |
| `is_rx_refill` | Patient will need prescription refill | durationDays > 20, long-term medication keywords |

---

## Priority Level Calculation

```
Priority Logic:
├── HIGH: All 3 flags TRUE
│         OR (recurring_diagnostics + rx_refill) both TRUE
├── MEDIUM: 2 flags TRUE
│           OR recurring_diagnostics alone
├── LOW: 1 flag TRUE
└── NONE: 0 flags TRUE
```

**Rationale:**
- `recurring + refill` = HIGH because it indicates ongoing chronic care burden
- `recurring` alone = MEDIUM because long-term monitoring needs proactive planning

---

## Indicator 1: is_followup_diagnostics

Patient needs diagnostic tests before/at next visit.

### Detection Sources

| Source | Field | Condition |
|--------|-------|-----------|
| **INVESTIGATIONS** | `laboratory_tests` | status = "ordered" OR "pending" (NOT "completed") |
| **INVESTIGATIONS** | `imaging_studies` | status = "ordered" OR "pending" |
| **INVESTIGATIONS** | `other_tests` | status = "ordered" OR "pending" |
| **FOLLOW_UP** | `bring_documents` | Contains diagnostic keywords |
| **FOLLOW_UP** | `special_instructions` | Contains diagnostic keywords |
| **FOLLOW_UP** | `immediate_actions` | Contains diagnostic keywords |
| **TREATMENT_PLAN** | `monitoring_instructions` | Non-empty (> 10 chars) |
| **TREATMENT_PLAN** | `investigations_plan` | Non-empty (> 10 chars) |

### Important: Status Filtering

```
INVESTIGATIONS segment tests have 3 statuses:
├── ordered  → INCLUDE (newly ordered this visit)
├── pending  → INCLUDE (awaiting results)
└── completed → EXCLUDE (results already available, not a follow-up need)
```

### Diagnostic Keywords

```
test, tests, testing, lab, labs, laboratory,
blood work, blood test, urine test, stool test,
x-ray, xray, ct scan, mri, ultrasound, usg,
echo, ecg, ekg, echocardiogram, electrocardiogram,
biopsy, culture, screening, investigation,
cbc, lft, rft, kft, lipid, hba1c, thyroid,
hemogram, electrolytes, creatinine, glucose
```

---

## Indicator 2: is_recurring_diagnostics

Patient needs periodic/recurring monitoring tests.

### Detection Sources

| Source | Condition |
|--------|-----------|
| **clinical_severity** | `is_chronic` = TRUE |
| **DIAGNOSIS (ICD codes)** | Matches recurring diagnostic ICD prefixes |
| **TREATMENT_PLAN** | Contains recurring keywords |

### ICD-10 Codes Requiring Recurring Diagnostics

| Category | Prefixes | Monitoring Type |
|----------|----------|-----------------|
| **Diabetes** | E10, E11 | HbA1c monitoring |
| **Thyroid** | E03 (hypo), E05 (hyper) | Thyroid function tests |
| **Metabolic** | E66 (obesity), E78 (dyslipidemia) | Metabolic panel |
| **Cardiovascular** | I10-I15 (hypertension) | BP, renal monitoring |
| **Renal** | N18 (CKD) | Renal function tests |
| **Respiratory** | J44 (COPD), J45 (asthma) | Pulmonary function tests |
| **Hepatic** | B18, K70, K74 | Liver function tests |
| **Hematologic** | D50 (anemia) | CBC monitoring |
| **Pregnancy** | O, Z33, Z34, Z36, O24 | Antenatal monitoring |
| **Infertility** | N97, N46, N80, E28.2 (PCOS) | Hormonal/cycle monitoring |
| **Autoimmune** | M05, M06, M32 (RA, SLE) | Inflammatory markers |
| **Ophthalmology** | H40 (glaucoma) | IOP, visual field tests |
| **Infectious** | B20 (HIV) | Viral load, CD4 monitoring |

### Recurring Keywords

```
periodic, periodically, regular, regularly,
monthly, quarterly, annually, yearly,
every month, every 3 months, every 6 months, every year,
routine monitoring, routine check, follow-up labs,
repeat test, repeat investigation, monitor
```

---

## Indicator 3: is_rx_refill

Patient will need prescription refill.

### Detection Criteria

| Trigger | Source | Condition |
|---------|--------|-----------|
| **Long duration** | PRESCRIPTION | `durationDays` > 20 |
| **Refill keywords** | PRESCRIPTION.remarks | Contains refill keywords |
| **Chronic keywords** | PRESCRIPTION.remarks | If `is_chronic`, check additional keywords |
| **Chronic keywords** | TREATMENT_PLAN, FOLLOW_UP | If `is_chronic` and no match yet |

### Important: "Continue" Alone ≠ Refill

```
"continue from last time" → Does NOT trigger refill
"continue indefinitely"   → DOES trigger refill
"continue long term"      → DOES trigger refill
```

**Rationale:** Generic "continue" often means resuming prior medication without implying ongoing refill need.

### Refill Keywords (Strict)

```
# Explicit refill indicators
refill, repeat prescription, renewal

# Long-term indicators
long-term, long term, lifelong, indefinitely,
maintenance medication, maintenance therapy

# Chronic medication phrases
continue indefinitely, continue lifelong, continue long term,
ongoing medication, regular medication, daily medication

# Duration-based
for life, permanently
```

### Chronic Refill Keywords (Only when is_chronic=TRUE)

```
# Repeat patterns
repeat every, repeat monthly, repeat weekly,
every month, every week, monthly refill

# Regular supply
regular supply, continuous supply, stock up

# Chronic management
continue same, same medication, no change in medication,
maintain current, keep taking, do not stop

# Prescription patterns
next batch, next supply, renew prescription
```

---

## Data Extraction Sources

| Field | Segments Scanned | Extraction Method |
|-------|------------------|-------------------|
| `investigations` | INVESTIGATIONS | Full segment object |
| `follow_up` | FOLLOW_UP | Full segment object |
| `treatment_plan` | TREATMENT_PLAN | Full segment object |
| `prescription` | PRESCRIPTION | Array of medication objects |
| `icd_codes` | DIAGNOSIS | `code` field from array items |
| `is_chronic` | clinical_severity_assessments | From previous assessment |

---

## Scoring Examples

| Case | Followup | Recurring | Refill | Priority |
|------|----------|-----------|--------|----------|
| CBC ordered, no chronic condition | TRUE | FALSE | FALSE | **LOW** |
| Diabetes (E11.9), Metformin 90 days | FALSE | TRUE | TRUE | **HIGH** |
| Hypertension (I10), monthly BP check | FALSE | TRUE | FALSE | **MEDIUM** |
| Labs ordered + chronic + long-term meds | TRUE | TRUE | TRUE | **HIGH** |
| Simple follow-up, no tests, short Rx | FALSE | FALSE | FALSE | **NONE** |
| Pregnant (Z33) + prenatal labs ordered | TRUE | TRUE | FALSE | **MEDIUM** |

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/clinical-needs/extraction/{extraction_id}` | Get needs for an extraction |
| `GET /api/v1/clinical-needs/patient/{patient_id}/history` | Patient's needs history |
| `GET /api/v1/clinical-needs/patient/{patient_id}/latest` | Latest needs assessment |
| `GET /api/v1/clinical-needs/statistics` | Aggregate stats by doctor/period |

---

## Database Schema

```sql
CREATE TABLE other_clinical_needs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    patient_id UUID,
    doctor_id UUID,

    -- Consolidated priority level
    priority_level TEXT DEFAULT 'NONE'
        CHECK (priority_level IN ('NONE', 'LOW', 'MEDIUM', 'HIGH')),

    -- Three boolean indicators
    is_followup_diagnostics BOOLEAN DEFAULT FALSE,
    is_recurring_diagnostics BOOLEAN DEFAULT FALSE,
    is_rx_refill BOOLEAN DEFAULT FALSE,

    -- Reasoning/evidence for each flag
    followup_diagnostics_reasons TEXT[] DEFAULT '{}',
    recurring_diagnostics_reasons TEXT[] DEFAULT '{}',
    rx_refill_reasons TEXT[] DEFAULT '{}',

    -- Input data used for detection (for debugging)
    input_data JSONB DEFAULT '{}',

    -- Link to clinical severity for is_chronic reference
    clinical_severity_id UUID REFERENCES clinical_severity_assessments(id),

    -- Metadata
    calculation_version TEXT DEFAULT '1.2.0',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_needs_extraction UNIQUE (extraction_id)
);

-- Indexes
CREATE INDEX idx_needs_extraction ON other_clinical_needs(extraction_id);
CREATE INDEX idx_needs_patient ON other_clinical_needs(patient_id);
CREATE INDEX idx_needs_priority_level ON other_clinical_needs(priority_level)
    WHERE priority_level != 'NONE';
CREATE INDEX idx_needs_followup_diag ON other_clinical_needs(is_followup_diagnostics)
    WHERE is_followup_diagnostics = TRUE;
CREATE INDEX idx_needs_recurring_diag ON other_clinical_needs(is_recurring_diagnostics)
    WHERE is_recurring_diagnostics = TRUE;
CREATE INDEX idx_needs_rx_refill ON other_clinical_needs(is_rx_refill)
    WHERE is_rx_refill = TRUE;
```

---

## Response Example

```json
{
  "id": "uuid",
  "extraction_id": "uuid",
  "patient_id": "uuid",
  "priority_level": "HIGH",
  "is_followup_diagnostics": true,
  "is_recurring_diagnostics": true,
  "is_rx_refill": true,
  "followup_diagnostics_reasons": [
    "Laboratory tests ordered: CBC, LFT, KFT",
    "FOLLOW_UP: Bring documents mentions tests"
  ],
  "recurring_diagnostics_reasons": [
    "ICD E11.9: Diabetes Type 2 - HbA1c monitoring",
    "Chronic condition requires periodic monitoring"
  ],
  "rx_refill_reasons": [
    "Metformin: 90 days duration",
    "Amlodipine: 'maintenance medication' in remarks"
  ],
  "input_data": {
    "investigations": {...},
    "follow_up": {...},
    "treatment_plan": {...},
    "prescription_count": 3,
    "icd_codes": ["E11.9", "I10"],
    "is_chronic": true
  },
  "clinical_severity_id": "uuid",
  "calculation_version": "1.2.0",
  "created_at": "2024-12-25T13:00:00Z"
}
```

---

## Execution Flow

```
Extraction Complete
    │
    ├── Save to medical_extractions table
    │
    ├── Fire-and-forget: Clinical Severity
    │       └── Calculates is_chronic flag
    │
    └── Fire-and-forget: Other Clinical Needs (1s delay)
            ├── Queries clinical_severity for is_chronic
            ├── Analyzes INVESTIGATIONS, FOLLOW_UP, TREATMENT_PLAN, PRESCRIPTION
            ├── Calculates 3 boolean indicators
            ├── Determines priority_level
            └── Saves to other_clinical_needs table
```

---

## Implementation Files

| File | Purpose |
|------|---------|
| `backend/services/other_clinical_needs_service.py` | Core detection logic |
| `backend/routers/other_clinical_needs.py` | API endpoints |
| `backend/services/supabase_service.py` | Database operations |
| `backend/supabase/migrations/20251225112800_add_other_clinical_needs.sql` | Table migration |
| `backend/supabase/migrations/20251225130000_add_priority_level_to_clinical_needs.sql` | Priority column |

---

## Trigger

Other Clinical Needs is automatically calculated after each medical extraction completes. The calculation runs as a fire-and-forget async task in `extraction_service.py`, with a 1-second delay to ensure clinical_severity is saved first (for `is_chronic` access).

---

## Version History

| Version | Changes |
|---------|---------|
| 1.0.0 | Initial implementation with 3 boolean indicators |
| 1.1.0 | Added status filtering (ordered/pending only), durationDays > 20, chronic-aware keywords |
| 1.2.0 | Added priority_level consolidation (NONE/LOW/MEDIUM/HIGH) |

# Clinical Severity Scoring Logic (v1.2.0)

## Overview

Clinical severity represents the **"stakes of non-adherence"** - what happens if the patient doesn't follow the treatment plan.

| Severity Level | Score Range | Meaning |
|----------------|-------------|---------|
| **LOW** | 0-4 | Routine care, low stakes |
| **MEDIUM** | 5-8 | Moderate stakes, needs attention |
| **HIGH** | 9+ or override | High stakes, requires intervention |

---

## Scoring Layers

### Layer 1: Critical Overrides → AUTO HIGH (score=999)

Any of these triggers immediate HIGH severity:

| Category | Codes/Keywords |
|----------|----------------|
| **Critical ICD Codes** | I21 (MI), I22, I46 (cardiac arrest), I60/I61/I63 (stroke), J96 (respiratory failure), N17 (kidney failure), K72 (liver failure), A41/R65.2 (sepsis), E10.1/E11.1 (DKA), T78.2 (anaphylaxis) |
| **Cancer Codes** | Any code starting with `C` |
| **Critical Keywords** | "malignant", "cancer", "critical", "failure", "arrest", "infarction", "hemorrhage", "sepsis", "transplant", "dialysis", "ventilator", "icu", "life threatening" |

---

### Layer 2: Base Score = max(ICD, Specialty) + Surgical

#### ICD-10 Chapter Scores (0-4 pts)

| Score | Prefixes | Examples |
|-------|----------|----------|
| 4 | C, D0, I2, I5, I6, N18, Z94 | Cancer, heart failure, stroke, CKD, transplant |
| 3 | E10, E11, I1, I4, J44, J45, K70, K74, F2, F3, B20 | Diabetes, hypertension, COPD, mood disorders, HIV |
| 2 | M, G, K, N, E0, F, J, D5 | Musculoskeletal, neuro, GI, respiratory |
| 1 | H, L, R, Z, J0 | Eye/ear, skin, symptoms, URI |

#### Specialty Scores (1-3 pts)

| Score | Specialties |
|-------|-------------|
| 3 | oncology, cardiology, neurology, nephrology, transplant, critical_care, neonatology |
| 2 | endocrinology, pulmonology, orthopedics, psychiatry, gastroenterology, general_surgery |
| 1 | dermatology, ent, ophthalmology, general_medicine, pediatrics |

#### Surgical Flag (+3 pts)

Detected from keywords: "surgery", "procedure", "post-op", "arthroplasty", "replacement", "resection", "bypass", "laparoscopy", "amputation", "fusion", etc.

---

### Layer 3: Modifier Score (additive)

| Modifier | Condition | Points |
|----------|-----------|--------|
| **Chronic condition** | Keywords or known conditions in HISTORY | +1 |
| **Polypharmacy** | 5+ medications | +2 |
| | 3-4 medications | +1 |
| **Follow-up urgency** | urgent/immediate/emergency | +2 |
| | soon/early/priority | +1 |
| **Treatment duration** | >90 days | +2 |
| | >30 days | +1 |
| **Second opinion / Specialist referral** | Doctor recommends specialist consultation or referral | +2 |
| **Alternate procedure** | Contingent/fallback treatment mentioned | +1 |

---

## Data Extraction Sources

| Field | Segments Scanned | Extraction Method |
|-------|------------------|-------------------|
| `icd_codes` | DIAGNOSIS | `code` field from array items |
| `diagnosis_text` | DIAGNOSIS | `name` field from array items |
| `medications` | PRESCRIPTION | `name` field from array items |
| `treatment_duration_days` | PRESCRIPTION | Max `durationDays` across all meds |
| `follow_up_urgency` | FOLLOW_UP | Inferred from `timeline_for_followup` |
| `is_surgical` | DIAGNOSIS, FOLLOW_UP, TREATMENT_PLAN, CAUTION, TREATMENT_SUMMARY | Keyword matching |
| `is_chronic` | HISTORY, TREATMENT_PLAN, PRESCRIPTION (duration), CAUTION, TREATMENT_SUMMARY | Keyword matching + known conditions |
| `is_second_opinion` | DIAGNOSIS, TREATMENT_PLAN, FOLLOW_UP, EXAMINATION, TREATMENT_SUMMARY, CAUTION | Keyword matching |
| `is_alternate_procedure` | Same as above | Keyword matching |

---

## Detection Keywords

### Surgical
```
surgery, surgical, operation, procedure, post-op, arthroplasty,
replacement, resection, excision, implant, graft, bypass,
angioplasty, laparoscopy, arthroscopy, amputation, fusion, fixation
```

### Chronic
```
chronic, long-term, ongoing, management, controlled, uncontrolled,
maintenance, lifetime, permanent, progressive, degenerative, persistent
```

Plus known conditions: diabetes, hypertension, copd, asthma, heart failure, ckd, epilepsy, arthritis, cancer, hiv, hepatitis

### Second Opinion / Specialist Referral (+2 pts)

Any specialist referral or second opinion recommendation adds +2 points as it indicates case complexity requiring additional expertise.

```
# Second opinion
second opinion, another opinion, get opinion, seek opinion,
opinion from, specialist opinion

# Specialist referral
specialist referral, referred to, referring to, refer to,
referral to, referral for, specialist review,
specialist consultation, consult with

# Recommendations to see specialist
need to see, should see, recommend seeing, advise seeing,
please see, must see, visit the

# Specific specialty consults
consult cardiology, consult neurology, consult oncology,
consult gastro, consult pulmo, consult nephro,
consult ortho, consult ent, consult ophtha,
cardiology referral, neurology referral, oncology referral,
surgical referral, surgery referral

# Multi-disciplinary
multi-disciplinary, multidisciplinary, mdt review,
tumor board, joint consultation, team review
```

### Alternate Procedure (+1 pt)
```
if not improved, if no response, if fails, alternative would be,
try this first, trial of, fallback, backup plan, escalate to,
next step would be, if this doesn't work, plan b, second line
```

---

## Scoring Formula

```
Base Score = max(ICD_score, Specialty_score) + Surgical_score

Modifier Score = Chronic + Polypharmacy + Urgency + Duration
                 + Second_Opinion + Alternate_Procedure

Total Score = Base Score + Modifier Score

Severity = HIGH if override OR score >= 9
           MEDIUM if score >= 5
           LOW if score < 5
```

---

## Example Calculations

| Case | Base | Modifiers | Total | Level |
|------|------|-----------|-------|-------|
| Diabetes (E11.9) + Endocrinology + 2 meds + 90 days | max(3,2)+0=3 | +1 long_treatment | 4 | LOW |
| Heart failure (I50.9) + Cardiology | **OVERRIDE** | - | 999 | HIGH |
| Back pain (M54.5) + Ortho + "refer to spine surgeon" + "if not improved" | max(2,2)+0=2 | +2 second_opinion +1 alternate | 5 | MEDIUM |
| Post hip replacement + prior surgery in TREATMENT_SUMMARY | max(1,2)+3=5 | +1 chronic | 6 | MEDIUM |

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/clinical-severity/extraction/{extraction_id}` | Get severity assessment for an extraction |
| `GET /api/v1/clinical-severity/patient/{patient_id}/history` | Get patient's severity history |
| `GET /api/v1/clinical-severity/patient/{patient_id}/latest` | Get latest severity for patient |
| `GET /api/v1/clinical-severity/statistics` | Aggregate stats by doctor/period |

---

## Database Schema

```sql
CREATE TABLE clinical_severity_assessments (
    id UUID PRIMARY KEY,
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id),
    patient_id UUID,
    doctor_id UUID,

    -- Severity Result
    severity_level TEXT NOT NULL CHECK (severity_level IN ('LOW', 'MEDIUM', 'HIGH')),
    total_score INTEGER NOT NULL,

    -- Override Info
    was_overridden BOOLEAN DEFAULT FALSE,
    override_reason TEXT,

    -- Score Details
    score_breakdown JSONB NOT NULL DEFAULT '{}',
    contributing_factors TEXT[] DEFAULT '{}',
    input_data JSONB DEFAULT '{}',

    -- Flag Columns (duplicated from input_data for easier querying)
    is_surgical BOOLEAN DEFAULT FALSE,
    is_chronic BOOLEAN DEFAULT FALSE,
    is_second_opinion BOOLEAN DEFAULT FALSE,
    is_alternate_procedure BOOLEAN DEFAULT FALSE,

    -- Metadata
    calculation_version TEXT DEFAULT '1.2.0',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_severity_extraction UNIQUE (extraction_id)
);

-- Partial indexes for flag columns
CREATE INDEX idx_severity_is_surgical ON clinical_severity_assessments(is_surgical) WHERE is_surgical = TRUE;
CREATE INDEX idx_severity_is_chronic ON clinical_severity_assessments(is_chronic) WHERE is_chronic = TRUE;
CREATE INDEX idx_severity_is_second_opinion ON clinical_severity_assessments(is_second_opinion) WHERE is_second_opinion = TRUE;
CREATE INDEX idx_severity_is_alternate_procedure ON clinical_severity_assessments(is_alternate_procedure) WHERE is_alternate_procedure = TRUE;
```

---

## Response Example

```json
{
  "id": "uuid",
  "extraction_id": "uuid",
  "severity_level": "MEDIUM",
  "total_score": 6,
  "was_overridden": false,
  "score_breakdown": {
    "icd_score": 2,
    "specialty_score": 2,
    "surgical_score": 3,
    "base_score": 5,
    "modifier_score": 1,
    "modifier_breakdown": {
      "chronic_condition": 1
    }
  },
  "contributing_factors": [
    "ICD codes: M16.1",
    "Specialty: orthopedics (2pts)",
    "Surgical intervention (+3pts)",
    "Chronic Condition: +1pts"
  ],
  "input_data": {
    "specialty": "orthopedics",
    "icd_codes": ["M16.1"],
    "medications": ["Paracetamol"],
    "is_surgical": true,
    "is_chronic": true,
    "is_second_opinion": false,
    "is_alternate_procedure": false
  },
  "is_surgical": true,
  "is_chronic": true,
  "is_second_opinion": false,
  "is_alternate_procedure": false,
  "calculation_version": "1.2.0"
}
```

---

## Implementation Files

| File | Purpose |
|------|---------|
| `backend/services/clinical_severity_service.py` | Core scoring logic and extraction |
| `backend/routers/clinical_severity.py` | API endpoints |
| `backend/services/supabase_service.py` | Database operations |
| `backend/supabase/migrations/20251224230737_add_clinical_severity_assessments.sql` | Database migration |

---

## Trigger

Clinical severity is automatically calculated after each medical extraction completes. The calculation runs as a fire-and-forget async task in `extraction_service.py`.

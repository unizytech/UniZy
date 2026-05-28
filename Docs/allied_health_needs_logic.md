# Allied Health Needs Logic (v1.0.0)

## Overview

Allied Health Needs identifies **referral needs for allied health services** based on emotional analysis and medical extraction data. This helps clinical staff proactively identify patients who may benefit from specialized support services.

| Priority Level | Meaning |
|----------------|---------|
| **NONE** | No allied health referral needs identified |
| **LOW** | 1 indicator present - minor referral need |
| **MEDIUM** | 2-3 indicators present |
| **HIGH** | 4+ indicators OR is_mental_health + any other indicator |

---

## Nine Boolean Indicators

| Indicator | Description | Primary Triggers |
|-----------|-------------|------------------|
| `is_mental_health` | Mental health support needed | Severe anxiety, depression, high clinical significance distress |
| `is_nutritional_health` | Nutritional counseling needed | Diabetes/obesity/cardiac + detailed diet instructions |
| `is_physiotherapy` | Physiotherapy referral needed | Musculoskeletal/injury + PT explicitly mentioned |
| `is_homecare` | Home care services needed | Age>70 + chronic + mobility issues |
| `is_sleep_therapy` | Sleep therapy needed | Sleep symptoms + obesity/hypertension |
| `is_rehab_cardiac` | Cardiac rehabilitation needed | MI/ischemic heart disease/post-CABG |
| `is_rehab_common` | General rehabilitation needed | Ortho surgery/stroke (mutually exclusive with cardiac) |
| `is_treatment_education` | Treatment education needed | New diagnosis + understanding barrier |
| `is_wellness` | Wellness program needed | Lifestyle disease + prevention discussion |

---

## Priority Level Calculation

```
Priority Logic:
├── HIGH: 4+ indicators TRUE
│         OR is_mental_health + any other indicator TRUE
├── MEDIUM: 2-3 indicators TRUE
├── LOW: 1 indicator TRUE
└── NONE: 0 indicators TRUE
```

**Rationale:** Mental health needs elevate priority due to impact on overall treatment compliance and patient outcomes.

---

## Indicator 1: is_mental_health

Patient needs mental health support.

### Detection Triggers (ANY)

| Source | Condition |
|--------|-----------|
| ANXIETY_POST_CONSULTATION | `level` = "Severe" |
| ANXIETY_POST_CONSULTATION | `change_from_pre` = "Worsened" |
| ANXIETY_POST_CONSULTATION | `change_from_pre` = "Unchanged" AND ANXIETY_PRE_CONSULTATION.level was "Severe" |
| OTHER_EMOTIONS_DETECTED | Contains emotion "Depression" OR "Distress" with `clinical_significance` = "High" |
| TREATMENT_PLAN | Contains mental health keywords |

### Mental Health Keywords

```
counseling, therapy, psychologist, psychiatrist, mental health,
emotional support, stress management, relaxation, mindfulness,
cbt, cognitive behavioral, anxiety management, depression support,
emotional counseling
```

---

## Indicator 2: is_nutritional_health

Patient needs nutritional counseling.

### Detection Triggers (ALL required)

| Source | Condition |
|--------|-----------|
| DIAGNOSIS | ICD-10 matches: E10.*, E11.* (diabetes), E66.* (obesity), E78.* (dyslipidemia), OR I* (cardiac) |
| TREATMENT_PLAN | `diet_instructions` has detailed content (foods_to_avoid OR foods_to_include with content) |

### ICD-10 Prefixes

```python
NUTRITIONAL_ICD_PREFIXES = ["E10", "E11", "E66", "E78", "I"]
```

---

## Indicator 3: is_physiotherapy

Patient needs physiotherapy referral.

### Detection Triggers (ALL required)

| Source | Condition |
|--------|-----------|
| DIAGNOSIS | ICD-10 in M* (musculoskeletal) OR S* (injury) |
| Text | Contains mobility/pain keywords |
| TREATMENT_PLAN/FOLLOW_UP | "physiotherapy" OR "physical therapy" explicitly mentioned |

### Mobility/Pain Keywords

```
mobility, movement, range of motion, stiffness, weakness, gait,
pain management, chronic pain, back pain, neck pain, joint pain,
physiotherapy, physical therapy, PT, rehabilitation exercises
```

---

## Indicator 4: is_homecare

Patient needs home care services.

### Detection Triggers (ALL required)

| Source | Condition |
|--------|-----------|
| Patient | Age > 70 (from patients.date_of_birth or extraction segment) |
| clinical_severity | `is_chronic` = TRUE |
| Text | Contains mobility issue keywords |

### Mobility Issue Keywords

```
mobility issues, difficulty walking, bedridden, wheelchair, walker,
home nursing, home care, assisted living, caregiver, daily activities,
bathing assistance, feeding assistance, cannot travel, homebound
```

---

## Indicator 5: is_sleep_therapy

Patient needs sleep therapy.

### Detection Triggers (ANY sleep keyword + ANY condition)

| Source | Condition |
|--------|-----------|
| Text | Contains sleep keywords |
| DIAGNOSIS | E66.* (obesity) OR I10-I15 (hypertension) |

### Sleep Keywords

```
snoring, sleep apnea, apnea, insomnia, fatigue, tired,
daytime sleepiness, poor sleep, sleep disorder, cpap,
sleep study, polysomnography
```

---

## Indicator 6: is_rehab_cardiac

Patient needs cardiac rehabilitation.

### Detection Triggers (ANY)

| Source | Condition |
|--------|-----------|
| DIAGNOSIS | ICD-10: I21.* (MI), I25.* (chronic ischemic heart disease) |
| Text | Post-CABG mentioned (keywords: cabg, bypass surgery, coronary bypass) |
| Text | Cardiac stent/angioplasty mentioned |

### Cardiac Rehab Keywords

```
cabg, bypass surgery, coronary bypass, post-operative cardiac,
cardiac rehabilitation, heart attack recovery, mi recovery,
stent placement, angioplasty, ptca, pci
```

---

## Indicator 7: is_rehab_common

Patient needs general rehabilitation (mutually exclusive from cardiac).

### Detection Triggers (NOT is_rehab_cardiac AND ANY)

| Source | Condition |
|--------|-----------|
| Text | Post-orthopedic surgery keywords |
| DIAGNOSIS | ICD-10: S* (injury), M* with surgical keywords |
| DIAGNOSIS | ICD-10: I63.*, I64.* (stroke) |

### Common Rehab Keywords

```
post-operative, surgery recovery, joint replacement, hip replacement,
knee replacement, fracture healing, stroke rehabilitation,
occupational therapy, speech therapy, neuro rehabilitation
```

---

## Indicator 8: is_treatment_education

Patient needs treatment education.

### Detection Triggers (ALL required)

| Source | Condition |
|--------|-----------|
| Text | New diagnosis keywords detected |
| TREATMENT_COMPLIANCE_LIKELIHOOD | `key_barriers[]` contains `barrier_type` = "Understanding" |

### New Diagnosis Keywords

```
newly diagnosed, new onset, first time, just diagnosed,
recent diagnosis, new case of, diagnosed today,
confirmed today, initial diagnosis
```

---

## Indicator 9: is_wellness

Patient needs wellness program.

### Detection Triggers (ALL required)

| Source | Condition |
|--------|-----------|
| DIAGNOSIS | Lifestyle disease: E10.*, E11.* (diabetes), E66.* (obesity), I10-I15 (hypertension), E78.* (dyslipidemia) |
| TREATMENT_PLAN | Contains prevention/wellness keywords |

### Wellness Keywords

```
prevention, lifestyle modification, weight management, exercise program,
wellness, health coaching, preventive care, risk reduction,
smoking cessation, alcohol reduction, diet plan, healthy lifestyle
```

---

## Data Sources Summary

| Indicator | Primary Sources | Secondary Sources |
|-----------|-----------------|-------------------|
| is_mental_health | ANXIETY_POST_CONSULTATION, OTHER_EMOTIONS_DETECTED | TREATMENT_PLAN |
| is_nutritional_health | DIAGNOSIS (ICD), TREATMENT_PLAN.diet_instructions | - |
| is_physiotherapy | DIAGNOSIS (M*, S*), TREATMENT_PLAN, FOLLOW_UP | Transcript keywords |
| is_homecare | patients.date_of_birth, clinical_severity.is_chronic | Segment text |
| is_sleep_therapy | Transcript keywords, DIAGNOSIS (E66, I10-I15) | - |
| is_rehab_cardiac | DIAGNOSIS (I21, I25), TREATMENT_PLAN | Keywords |
| is_rehab_common | DIAGNOSIS (S*, M*, I63), TREATMENT_PLAN | Keywords |
| is_treatment_education | Transcript keywords, TREATMENT_COMPLIANCE_LIKELIHOOD.key_barriers | - |
| is_wellness | DIAGNOSIS (lifestyle diseases), TREATMENT_PLAN | - |

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/allied-health/extraction/{extraction_id}` | Get allied health needs for an extraction |
| `GET /api/v1/allied-health/patient/{patient_id}/history` | Patient's allied health history |
| `GET /api/v1/allied-health/patient/{patient_id}/latest` | Latest allied health assessment |
| `GET /api/v1/allied-health/statistics` | Aggregate stats by doctor/period |

---

## Database Schema

```sql
CREATE TABLE allied_health_needs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    patient_id UUID,
    doctor_id UUID,

    -- Consolidated priority level
    priority_level TEXT DEFAULT 'NONE'
        CHECK (priority_level IN ('NONE', 'LOW', 'MEDIUM', 'HIGH')),

    -- 9 boolean indicators
    is_mental_health BOOLEAN DEFAULT FALSE,
    is_nutritional_health BOOLEAN DEFAULT FALSE,
    is_physiotherapy BOOLEAN DEFAULT FALSE,
    is_homecare BOOLEAN DEFAULT FALSE,
    is_sleep_therapy BOOLEAN DEFAULT FALSE,
    is_rehab_cardiac BOOLEAN DEFAULT FALSE,
    is_rehab_common BOOLEAN DEFAULT FALSE,
    is_treatment_education BOOLEAN DEFAULT FALSE,
    is_wellness BOOLEAN DEFAULT FALSE,

    -- Reasoning for each indicator
    mental_health_reasons TEXT[] DEFAULT '{}',
    nutritional_health_reasons TEXT[] DEFAULT '{}',
    physiotherapy_reasons TEXT[] DEFAULT '{}',
    homecare_reasons TEXT[] DEFAULT '{}',
    sleep_therapy_reasons TEXT[] DEFAULT '{}',
    rehab_cardiac_reasons TEXT[] DEFAULT '{}',
    rehab_common_reasons TEXT[] DEFAULT '{}',
    treatment_education_reasons TEXT[] DEFAULT '{}',
    wellness_reasons TEXT[] DEFAULT '{}',

    -- Input data (for debugging)
    input_data JSONB DEFAULT '{}',

    -- References
    clinical_severity_id UUID REFERENCES clinical_severity_assessments(id),
    other_clinical_needs_id UUID REFERENCES other_clinical_needs(id),

    -- Metadata
    calculation_version TEXT DEFAULT '1.0.0',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_allied_needs_extraction UNIQUE (extraction_id)
);
```

---

## Response Example

```json
{
  "id": "uuid",
  "extraction_id": "uuid",
  "priority_level": "HIGH",
  "is_mental_health": true,
  "is_nutritional_health": true,
  "is_physiotherapy": false,
  "is_homecare": false,
  "is_sleep_therapy": false,
  "is_rehab_cardiac": false,
  "is_rehab_common": false,
  "is_treatment_education": true,
  "is_wellness": true,
  "mental_health_reasons": [
    "ANXIETY_POST_CONSULTATION: Severe level",
    "OTHER_EMOTIONS: Distress with High clinical significance"
  ],
  "nutritional_health_reasons": [
    "ICD E11.9: Diabetes Type 2",
    "TREATMENT_PLAN: Detailed diet instructions present"
  ],
  "treatment_education_reasons": [
    "Newly diagnosed diabetes detected",
    "TREATMENT_COMPLIANCE: Understanding barrier identified"
  ],
  "wellness_reasons": [
    "ICD E11.9: Lifestyle disease",
    "TREATMENT_PLAN: Prevention discussion present"
  ],
  "calculation_version": "1.0.0"
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
    │       └── Saves is_chronic flag
    │
    ├── Fire-and-forget: Other Clinical Needs
    │       └── Saves 3 boolean indicators
    │
    └── Fire-and-forget: Emotion Analysis
            │
            ├── Extract 6 emotion segments
            │   ├── ANXIETY_POST_CONSULTATION (level, change_from_pre)
            │   ├── OTHER_EMOTIONS_DETECTED (clinical_significance)
            │   └── TREATMENT_COMPLIANCE_LIKELIHOOD (key_barriers)
            │
            └── Fire-and-forget: Allied Health Needs (triggered AFTER emotion analysis)
                    ├── Query emotion segments
                    ├── Query clinical_severity.is_chronic
                    ├── Calculate patient age
                    ├── Assess 9 boolean indicators
                    ├── Calculate priority_level
                    └── Save to allied_health_needs table
```

---

## Implementation Files

| File | Purpose |
|------|---------|
| `backend/services/allied_health_needs_service.py` | Core detection logic |
| `backend/routers/allied_health_needs.py` | API endpoints |
| `backend/services/supabase_service.py` | Database operations |
| `backend/services/background_tasks.py` | Fire-and-forget trigger |
| `backend/supabase/migrations/20251225150000_add_allied_health_needs.sql` | Table migration |

---

## Trigger

Allied Health Needs is automatically calculated AFTER emotional analysis completes. This ensures access to emotion segments like ANXIETY_POST_CONSULTATION and OTHER_EMOTIONS_DETECTED. The calculation runs as a fire-and-forget async task in `background_tasks.py`.

---

## Version History

| Version | Changes |
|---------|---------|
| 1.0.0 | Initial implementation with 9 boolean indicators and priority level |

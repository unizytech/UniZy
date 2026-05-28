# CONSULTATION_INSIGHTS Segment (v1.1.0)

## Overview

The `CONSULTATION_INSIGHTS` segment is a unified extraction that captures clinical signals needed for three assessment systems:

1. **Clinical Severity Assessment** - Stakes of non-adherence
2. **Other Clinical Needs** - Downstream care requirements
3. **Allied Health Needs** - Referral needs for allied health services (partial - see exclusions)

This segment uses **ICD-10 context validation** - the LLM cross-references its own extracted ICD codes to validate clinical signals, reducing error propagation and improving accuracy.

---

## Excluded Signals

The following signals are **NOT** included in this segment because they depend on emotional analysis results:

| Signal | Reason | Source |
|--------|--------|--------|
| `mental_health_signals` | Requires ANXIETY_POST_CONSULTATION, OTHER_EMOTIONS_DETECTED | Emotional analysis |
| `education_signals` | Requires TREATMENT_COMPLIANCE_LIKELIHOOD.key_barriers | Emotional analysis |

These signals are handled by `allied_health_needs_service.py` using emotion segment data.

---

## When to Use

Add this segment to consultation types that need clinical assessments:
- OP (Outpatient) consultations
- DISCHARGE summaries
- Any consultation requiring severity/needs assessment

---

## Architecture: ICD Context Validation

```
┌─────────────────────────────────────────────────────────────────┐
│                   EXTRACTION FLOW                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Transcript                                                    │
│       │                                                         │
│       ▼                                                         │
│   ┌───────────────────────────────────────┐                     │
│   │       LLM Extraction (Pass 1)         │                     │
│   │  • DIAGNOSIS → ICD codes              │                     │
│   │  • PRESCRIPTION → medications         │                     │
│   │  • INVESTIGATIONS → tests             │                     │
│   │  • FOLLOW_UP → timeline               │                     │
│   │  • TREATMENT_PLAN → instructions      │                     │
│   └───────────────────────────────────────┘                     │
│       │                                                         │
│       ▼                                                         │
│   ┌───────────────────────────────────────┐                     │
│   │   CONSULTATION_INSIGHTS (Pass 2)      │                     │
│   │                                       │                     │
│   │   Context provided:                   │                     │
│   │   • Original transcript               │                     │
│   │   • Extracted segments (ICD, Rx, etc) │                     │
│   │                                       │                     │
│   │   LLM cross-validates:                │                     │
│   │   • ICD E11.65 → chronic=true         │                     │
│   │   • ICD E11.65 → renal monitoring     │                     │
│   │   • Duration 90 days → long-term Rx   │                     │
│   └───────────────────────────────────────┘                     │
│       │                                                         │
│       ▼                                                         │
│   Clinical Insights with ICD Validation                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Schema Structure

The schema is organized into 9 signal groups (excluding mental health and education):

### 1. Patient Signals
```json
{
  "patient_signals": {
    "estimated_age_years": "number or null",
    "age_source": "mentioned | inferred | unknown"
  }
}
```

### 2. Clinical Severity Signals
```json
{
  "clinical_severity_signals": {
    "is_chronic": "boolean",
    "chronic_evidence": ["array of strings - including ICD validation"],
    "is_surgical": "boolean",
    "surgical_evidence": ["array of strings"],
    "follow_up_urgency": "routine | soon | urgent",
    "urgency_evidence": "string",
    "is_second_opinion_recommended": "boolean",
    "second_opinion_evidence": "string or null",
    "is_alternate_treatment_discussed": "boolean",
    "alternate_treatment_evidence": "string or null",
    "critical_condition_detected": "boolean",
    "critical_condition_name": "string or null",
    "icd_validation": "string - How ICD codes support severity assessment"
  }
}
```

### 3. Diagnostic Needs
```json
{
  "diagnostic_needs": {
    "has_ordered_tests": "boolean",
    "ordered_tests": ["array of test names"],
    "has_pending_results": "boolean",
    "pending_tests": ["array of test names"],
    "needs_recurring_monitoring": "boolean",
    "recurring_monitoring_type": ["HbA1c | Thyroid | Renal | Lipid | CBC | LFT | Other"],
    "recurring_monitoring_evidence": ["array of strings - Include ICD-based reasoning"]
  }
}
```

### 4. Medication Signals
```json
{
  "medication_signals": {
    "total_medications_prescribed": "number",
    "max_duration_days": "number or null",
    "has_long_term_medications": "boolean",
    "long_term_medication_names": ["array of strings"],
    "refill_evidence": ["array of strings"]
  }
}
```

### 5. Nutritional Signals
```json
{
  "nutritional_signals": {
    "has_metabolic_condition": "boolean",
    "metabolic_conditions": ["diabetes | obesity | dyslipidemia | cardiac"],
    "has_detailed_diet_instructions": "boolean",
    "diet_instruction_summary": "string or null",
    "nutritional_counseling_mentioned": "boolean",
    "icd_validation": "string - ICD codes supporting metabolic condition"
  }
}
```

### 6. Physiotherapy Signals
```json
{
  "physiotherapy_signals": {
    "has_musculoskeletal_condition": "boolean",
    "has_injury": "boolean",
    "physiotherapy_explicitly_mentioned": "boolean",
    "mobility_pain_keywords_present": "boolean",
    "physiotherapy_evidence": ["array of strings"],
    "icd_validation": "string - M*/S* codes if present"
  }
}
```

### 7. Homecare Signals
```json
{
  "homecare_signals": {
    "has_mobility_issues": "boolean",
    "mobility_issue_type": ["difficulty_walking | bedridden | wheelchair | walker | homebound"],
    "homecare_discussed": "boolean",
    "mobility_evidence": ["array of strings"]
  }
}
```

### 8. Sleep Signals
```json
{
  "sleep_signals": {
    "has_sleep_symptoms": "boolean",
    "sleep_symptoms": ["snoring | apnea | insomnia | fatigue | daytime_sleepiness"],
    "has_obesity_or_hypertension": "boolean",
    "sleep_therapy_mentioned": "boolean",
    "sleep_evidence": ["array of strings"],
    "icd_validation": "string - E66/I10-I15 codes if present"
  }
}
```

### 9. Rehabilitation Signals
```json
{
  "rehabilitation_signals": {
    "has_cardiac_event": "boolean",
    "cardiac_event_type": ["mi | ischemic | cabg | stent | angioplasty"],
    "has_stroke": "boolean",
    "has_orthopedic_surgery": "boolean",
    "orthopedic_surgery_type": "string or null",
    "cardiac_rehab_mentioned": "boolean",
    "general_rehab_mentioned": "boolean",
    "rehab_evidence": ["array of strings"],
    "icd_validation": "string - I21/I25/I60-I64 codes if present"
  }
}
```

### 10. Wellness Signals
```json
{
  "wellness_signals": {
    "has_lifestyle_disease": "boolean",
    "lifestyle_diseases": ["diabetes | obesity | hypertension | dyslipidemia"],
    "prevention_discussed": "boolean",
    "lifestyle_modification_discussed": "boolean",
    "wellness_evidence": ["array of strings"],
    "icd_validation": "string - Lifestyle disease ICD codes"
  }
}
```

---

## System Prompt

```
You are a clinical insights extractor. Analyze the medical consultation transcript and extract structured signals for clinical assessment systems.

## CONTEXT

You have extracted the following structured data from this consultation:

**DIAGNOSIS (ICD-10 Codes):**
{DIAGNOSIS_SEGMENT}

**PRESCRIPTION:**
{PRESCRIPTION_SEGMENT}

**INVESTIGATIONS:**
{INVESTIGATIONS_SEGMENT}

**FOLLOW_UP:**
{FOLLOW_UP_SEGMENT}

**TREATMENT_PLAN:**
{TREATMENT_PLAN_SEGMENT}

Use BOTH the original transcript AND these extracted segments to generate accurate clinical insights. Cross-validate your assessments - if you coded E11.65 (diabetes with CKD), ensure your signals reflect both diabetes AND renal monitoring needs.

## EXTRACTION RULES

1. **Be Evidence-Based**: Only mark indicators as TRUE if there is clear evidence in the transcript or extracted segments
2. **Cross-Validate with ICD**: Your ICD codes should align with your clinical signals. If there's a mismatch, prefer the more clinically accurate interpretation from the transcript
3. **Quote Evidence**: Include brief quotes or paraphrases as evidence
4. **Age Estimation**: If patient age is mentioned, extract it. If inferable (e.g., "retired", "senior"), estimate. Otherwise mark as unknown
5. **Be Conservative**: When uncertain, lean towards FALSE for boolean indicators

## EXTRACTION GUIDELINES

### Clinical Severity Signals

**is_chronic**
- TRUE if ongoing/long-term condition management discussed
- Cross-check: ICD codes E10-E14 (diabetes), I10-I15 (hypertension), J44-J45 (COPD/asthma), N18 (CKD) indicate chronic
- Also TRUE if "maintenance", "lifelong", "ongoing", "long-term" mentioned

**is_surgical**
- TRUE if surgery, procedure, or post-operative care mentioned
- Cross-check: ICD codes starting with S, T (injuries), or procedure mentions in TREATMENT_PLAN

**follow_up_urgency**
- "urgent": Immediate/emergency, within 24-48 hours
- "soon": Within 1-2 weeks, priority follow-up
- "routine": Regular scheduled follow-up (monthly, quarterly)
- Cross-check with FOLLOW_UP.timeline_for_followup

**is_second_opinion_recommended**
- TRUE if referral to specialist or second opinion explicitly suggested
- Look for: "consult with", "refer to", "specialist opinion", "get another opinion"

**is_alternate_treatment_discussed**
- TRUE if fallback/alternative treatment options discussed
- Look for: "if this doesn't work", "alternative would be", "plan B", "second-line"

**critical_condition_detected**
- TRUE for life-threatening conditions requiring immediate attention
- Cross-check: ICD codes I21 (MI), I60-I64 (stroke), C* (cancer), J96 (respiratory failure), N17 (acute kidney failure), A41/R65.2 (sepsis)

### Diagnostic Needs

**has_ordered_tests**
- TRUE if new tests are ordered during THIS consultation
- Cross-check: INVESTIGATIONS.laboratory_tests, imaging_studies with status="ordered"

**has_pending_results**
- TRUE if waiting for test results from prior orders
- Cross-check: INVESTIGATIONS with status="pending"

**needs_recurring_monitoring**
- TRUE for conditions requiring periodic testing
- Cross-check ICD codes:
  - E10-E11 (diabetes) → HbA1c every 3 months
  - N18 (CKD) → Renal function tests
  - E03/E05 (thyroid) → Thyroid function tests
  - I10-I15 (hypertension) → BP monitoring, renal function
  - E78 (dyslipidemia) → Lipid profile
  - B20 (HIV) → Viral load, CD4

### Medication Signals

**total_medications_prescribed**
- Count from PRESCRIPTION segment
- Include all medications (not just new ones)

**max_duration_days**
- Longest prescription duration from PRESCRIPTION.durationDays
- Convert text to number if needed ("3 months" = 90)

**has_long_term_medications**
- TRUE if any medication prescribed for >30 days
- TRUE if keywords: "maintenance", "lifelong", "continue indefinitely", "long-term"
- Cross-check: Chronic ICD codes typically have long-term medications

### Nutritional Signals

**has_metabolic_condition**
- TRUE if diabetes, obesity, cardiac disease, or dyslipidemia present
- Cross-check ICD: E10-E11 (diabetes), E66 (obesity), E78 (dyslipidemia), I* (cardiac)

**has_detailed_diet_instructions**
- TRUE if TREATMENT_PLAN.diet_instructions has specific content
- Look for: foods_to_avoid, foods_to_include with actual items listed
- NOT true if just "N/A" or "follow diabetic diet" without specifics

**nutritional_counseling_mentioned**
- TRUE if dietitian, nutritionist, or nutrition counseling explicitly mentioned

### Physiotherapy Signals

**has_musculoskeletal_condition**
- TRUE for back pain, joint pain, arthritis, muscle issues, spine problems
- Cross-check ICD: M* (musculoskeletal), cervical/lumbar conditions

**has_injury**
- TRUE for fractures, sprains, trauma, post-accident conditions
- Cross-check ICD: S* (injuries), T* (trauma)

**physiotherapy_explicitly_mentioned**
- Only TRUE if "physiotherapy", "physical therapy", "PT", or "physio" explicitly mentioned
- NOT true just because there's a musculoskeletal condition

### Homecare Signals

**has_mobility_issues**
- TRUE if difficulty walking, wheelchair use, bedridden, needs assistance
- Look for: "can't walk", "difficulty moving", "needs help", "homebound"

**homecare_discussed**
- TRUE if home nursing, home care services, caregiver support mentioned

### Sleep Signals

**has_sleep_symptoms**
- TRUE if snoring, sleep apnea, insomnia, chronic fatigue, daytime sleepiness mentioned
- Look for: "can't sleep", "tired all day", "snoring", "waking up at night"

**has_obesity_or_hypertension**
- Cross-check ICD: E66 (obesity), I10-I15 (hypertension)
- Also TRUE if BMI mentioned >30 or "overweight", "obese" in transcript

**sleep_therapy_mentioned**
- TRUE if CPAP, sleep study, polysomnography, sleep specialist mentioned

### Rehabilitation Signals

**has_cardiac_event**
- TRUE for recent MI, ischemic heart disease, post-CABG, stent, angioplasty
- Cross-check ICD: I21 (MI), I25 (chronic ischemic), Z95.1 (CABG status), Z95.5 (stent)

**has_stroke**
- TRUE for recent cerebrovascular event
- Cross-check ICD: I60-I64 (stroke), I69 (stroke sequelae)

**has_orthopedic_surgery**
- TRUE for joint replacement, fracture fixation, spine surgery
- Look for: "post-operative", "surgery recovery", "replacement"

**cardiac_rehab_mentioned / general_rehab_mentioned**
- TRUE only if rehabilitation explicitly discussed

### Wellness Signals

**has_lifestyle_disease**
- TRUE if diabetes, obesity, hypertension, or dyslipidemia present
- Cross-check ICD: E10-E11, E66, I10-I15, E78

**prevention_discussed**
- TRUE if preventive measures, screening, risk reduction discussed
- Look for: "prevent", "avoid complications", "regular check-ups"

**lifestyle_modification_discussed**
- TRUE if diet changes, exercise, smoking cessation, weight management discussed
- Look for: "lose weight", "quit smoking", "exercise more", "change diet"

## OUTPUT FORMAT

Return a valid JSON object matching the schema exactly. All fields are required.
- Use null for unknown numeric values
- Use empty arrays [] for no evidence
- Use false for unconfirmed booleans
- Include evidence strings that reference both transcript quotes AND ICD code validation
```

---

## Mapping to Assessment Systems

### Clinical Severity Assessment

| Schema Field | Maps To |
|--------------|---------|
| `clinical_severity_signals.is_chronic` | `ClinicalInput.is_chronic` |
| `clinical_severity_signals.is_surgical` | `ClinicalInput.is_surgical` |
| `clinical_severity_signals.follow_up_urgency` | `ClinicalInput.follow_up_urgency` |
| `clinical_severity_signals.is_second_opinion_recommended` | `ClinicalInput.is_second_opinion` |
| `clinical_severity_signals.is_alternate_treatment_discussed` | `ClinicalInput.is_alternate_procedure` |
| `clinical_severity_signals.critical_condition_detected` | Triggers HIGH severity override |
| `medication_signals.total_medications_prescribed` | Polypharmacy calculation |
| `medication_signals.max_duration_days` | `ClinicalInput.treatment_duration_days` |

### Other Clinical Needs

| Schema Field | Maps To |
|--------------|---------|
| `diagnostic_needs.has_ordered_tests` | `is_followup_diagnostics` |
| `diagnostic_needs.has_pending_results` | `is_followup_diagnostics` |
| `diagnostic_needs.needs_recurring_monitoring` | `is_recurring_diagnostics` |
| `medication_signals.has_long_term_medications` | `is_rx_refill` |

### Allied Health Needs (Partial)

| Schema Field | Maps To |
|--------------|---------|
| `nutritional_signals.has_metabolic_condition` + `has_detailed_diet_instructions` | `is_nutritional_health` |
| `physiotherapy_signals.has_musculoskeletal_condition` + `physiotherapy_explicitly_mentioned` | `is_physiotherapy` |
| `patient_signals.estimated_age_years` > 70 + `is_chronic` + `homecare_signals.has_mobility_issues` | `is_homecare` |
| `sleep_signals.has_sleep_symptoms` + `has_obesity_or_hypertension` | `is_sleep_therapy` |
| `rehabilitation_signals.has_cardiac_event` | `is_rehab_cardiac` |
| `rehabilitation_signals.has_stroke` OR `has_orthopedic_surgery` | `is_rehab_common` |
| `wellness_signals.has_lifestyle_disease` + `prevention_discussed` | `is_wellness` |

**Note:** `is_mental_health` and `is_treatment_education` are handled separately by `allied_health_needs_service.py` using emotional analysis segments.

---

## Example Output

```json
{
  "patient_signals": {
    "estimated_age_years": 68,
    "age_source": "mentioned"
  },
  "clinical_severity_signals": {
    "is_chronic": true,
    "chronic_evidence": [
      "Patient has Type 2 diabetes for 10 years",
      "On maintenance medications"
    ],
    "is_surgical": false,
    "surgical_evidence": [],
    "follow_up_urgency": "soon",
    "urgency_evidence": "Doctor asked to return in 2 weeks for HbA1c review",
    "is_second_opinion_recommended": false,
    "second_opinion_evidence": null,
    "is_alternate_treatment_discussed": true,
    "alternate_treatment_evidence": "If metformin not tolerated, can switch to sitagliptin",
    "critical_condition_detected": false,
    "critical_condition_name": null,
    "icd_validation": "E11.65 confirms Type 2 diabetes with CKD - chronic condition requiring ongoing management"
  },
  "diagnostic_needs": {
    "has_ordered_tests": true,
    "ordered_tests": ["HbA1c", "Lipid profile", "Renal function"],
    "has_pending_results": false,
    "pending_tests": [],
    "needs_recurring_monitoring": true,
    "recurring_monitoring_type": ["HbA1c", "Renal"],
    "recurring_monitoring_evidence": [
      "E11.65 (diabetes with CKD) requires quarterly HbA1c and renal monitoring"
    ]
  },
  "medication_signals": {
    "total_medications_prescribed": 3,
    "max_duration_days": 90,
    "has_long_term_medications": true,
    "long_term_medication_names": ["Metformin", "Amlodipine"],
    "refill_evidence": ["Continue current medications", "90-day supply prescribed"]
  },
  "nutritional_signals": {
    "has_metabolic_condition": true,
    "metabolic_conditions": ["diabetes"],
    "has_detailed_diet_instructions": true,
    "diet_instruction_summary": "Avoid sweets and refined carbs, reduce rice portions, include green vegetables",
    "nutritional_counseling_mentioned": false,
    "icd_validation": "E11.65 confirms diabetes - metabolic condition present"
  },
  "physiotherapy_signals": {
    "has_musculoskeletal_condition": false,
    "has_injury": false,
    "physiotherapy_explicitly_mentioned": false,
    "mobility_pain_keywords_present": false,
    "physiotherapy_evidence": [],
    "icd_validation": "No M* or S* codes present"
  },
  "homecare_signals": {
    "has_mobility_issues": false,
    "mobility_issue_type": [],
    "homecare_discussed": false,
    "mobility_evidence": []
  },
  "sleep_signals": {
    "has_sleep_symptoms": false,
    "sleep_symptoms": [],
    "has_obesity_or_hypertension": true,
    "sleep_therapy_mentioned": false,
    "sleep_evidence": [],
    "icd_validation": "I10 (hypertension) present - obesity/HTN flag set"
  },
  "rehabilitation_signals": {
    "has_cardiac_event": false,
    "cardiac_event_type": [],
    "has_stroke": false,
    "has_orthopedic_surgery": false,
    "orthopedic_surgery_type": null,
    "cardiac_rehab_mentioned": false,
    "general_rehab_mentioned": false,
    "rehab_evidence": [],
    "icd_validation": "No I21/I25/I60-I64 codes present"
  },
  "wellness_signals": {
    "has_lifestyle_disease": true,
    "lifestyle_diseases": ["diabetes", "hypertension"],
    "prevention_discussed": true,
    "lifestyle_modification_discussed": true,
    "wellness_evidence": [
      "Doctor discussed diet and exercise for diabetes control",
      "Advised weight management"
    ],
    "icd_validation": "E11.65 (diabetes) and I10 (hypertension) are lifestyle diseases"
  }
}
```

---

## ICD Code Reference for Validation

| ICD Prefix | Condition | Relevant Signals |
|------------|-----------|------------------|
| E10-E14 | Diabetes | is_chronic, needs_recurring_monitoring (HbA1c), has_lifestyle_disease |
| E66 | Obesity | has_metabolic_condition, has_obesity_or_hypertension, has_lifestyle_disease |
| E78 | Dyslipidemia | has_metabolic_condition, needs_recurring_monitoring (Lipid), has_lifestyle_disease |
| I10-I15 | Hypertension | is_chronic, has_obesity_or_hypertension, has_lifestyle_disease |
| I21 | MI | critical_condition_detected, has_cardiac_event |
| I25 | Chronic ischemic | has_cardiac_event |
| I60-I64 | Stroke | critical_condition_detected, has_stroke |
| J44-J45 | COPD/Asthma | is_chronic |
| M* | Musculoskeletal | has_musculoskeletal_condition |
| S* | Injuries | has_injury |
| N18 | CKD | is_chronic, needs_recurring_monitoring (Renal) |
| C* | Cancer | critical_condition_detected |

---

## Benefits

1. **Single LLM Call**: All assessment data extracted in one pass
2. **ICD Cross-Validation**: LLM validates its own signals against extracted ICD codes
3. **Reduced Error Propagation**: Direct extraction vs rules on LLM output
4. **Evidence Trail**: Each indicator includes supporting evidence with ICD validation
5. **Consistent Logic**: Assessment services use the same source of truth
6. **Debuggable**: icd_validation fields explain the clinical reasoning

---

## Implementation Files

| File | Purpose |
|------|---------|
| `segment_definitions` table | Stores prompt and schema |
| `extraction_segments` table | Stores extracted data per consultation |
| `clinical_severity_service.py` | Can use this data (future integration) |
| `other_clinical_needs_service.py` | Can use this data (future integration) |
| `allied_health_needs_service.py` | Uses this + emotion segments for complete assessment |

---

## Version History

| Version | Changes |
|---------|---------|
| 1.0.0 | Initial implementation with 11 signal groups |
| 1.1.0 | Enhanced with ICD context validation, removed mental_health_signals and education_signals (handled by emotional analysis) |

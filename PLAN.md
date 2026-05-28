# KG Hospital Cardiology EHR Integration - Implementation Plan

**Last Updated:** 2026-02-14

## Overview
Create a KG Hospital EHR formatter + routing (similar to Aosta pipeline) that:
1. Reuses **OP_PSG_NEW** template extraction (no new prompts needed)
2. Transforms extraction output → KG Hospital Cardiology Initial Assessment payload
3. Wires into existing EHR routing (`ehr_routing_service.py`)
4. Stores original extraction in DB (already happens) + formatted payload in `ehr_payload_json`

## KG Hospital Form Sections (from screenshots)
1. Patient Info: Name, Age, Sex, UHID (from app/EHR metadata)
2. Vitals: Temp, Pulse, RR, BP
3. Nutritional Screening: Height, Weight, BMI, flag if <18.5 or >24.5
4. Medical History (12 checkboxes, each Yes/No + Since): DM, HT, DLP, Previous MI, Previous Stent, Valvular Stent, Anticoagulant, History of CVA, History of COPD, Previous CABG, CRF, PVOD
5. Drug Allergy: Yes/No + details
6. Nutritional Assessment Needed: Yes/No
7. Patient Willing: Yes/No
8. Present Complaints (free text)
9. Findings: positive and negative
10. Provisional Diagnosis
11. Suggested Investigations: Blood tests + checkboxes (ECG, CT, ECHO, MRI, USG, BMD, X-Ray, Mammogram)
12. Consultants/Referral
13. Treatment & Future Plan: Drugs as per Rx (Y/N), Admission (Y/N), Reason, Type (Ward/ICU/Observation)
14. Other Instructions
15. Doctor Name, Time, Review On

---

## Segment → KG Form Field Mapping

### Source: OP_PSG_NEW Segments
| KG Form Section | Source Segment | Source Field | Transform |
|---|---|---|---|
| Vitals | `VITALS` | vital_signs.{temperature, pulse, respiratory_rate, blood_pressure} | Strip units |
| Nutritional Screening | `VITALS` | vital_signs.{height, weight, bmi} | Strip units, compute BMI flag |
| **Medical History (12 checkboxes)** | `GENERAL_HISTORY` | **`known_medical_problems[]`** → `{condition, since_value, since_unit}` | **Keyword match condition → checkbox** |
| Drug Allergy | `ALLERGY` | {has_allergy, allergy_type, details} | Direct map |
| Present Complaints | `CHIEF_COMPLAINTS` | array of {complaint_name, since_value, since_unit, severity, notes} | Join to text |
| Findings | `GENERAL_EXAMINATION` + `SYSTEMIC_EXAMINATION` | general_findings + [{system_type, examination}] | Combine into positive/negative |
| Provisional Diagnosis | `DIAGNOSIS` | array of {name, code, type} | Join "name (code)" |
| Investigations | `CLINICAL_NOTES` / `FOLLOW_UP` | Free text mentions of investigations | Keyword match → 8 checkboxes |
| Referral | `FOLLOW_UP` / `CLINICAL_NOTES` | Parse "refer" patterns | Regex extract |
| Treatment Plan | `PRESCRIPTION` + `FOLLOW_UP` + `CLINICAL_NOTES` | Prescription array + free text | Structured parse |
| Other Instructions | `FOLLOW_UP` + `CLINICAL_NOTES` | special_instructions, contingency_actions | Combine |
| Prescription | `PRESCRIPTION` | Medication array | Pass through |
| Review On | `FOLLOW_UP` | review_date | Format DD-MM-YYYY |

### Key Insight: Medical History Checkboxes
`GENERAL_HISTORY.known_medical_problems` is a **structured array**:
```json
[
  {"condition": "Hypertension", "since_value": 5, "since_unit": "Years", "details": "On medication"},
  {"condition": "Diabetes", "since_value": 3, "since_unit": "Years", "details": "Type 2, controlled"}
]
```
This maps directly to the 12 cardiology checkboxes via keyword matching — no free-text parsing needed.

---

## Target API Payload Structure

```json
{
  "patient_id": "uuid",
  "uhid": "KGH12345",
  "doctor_id": "uuid",
  "extraction_id": "uuid",
  "form_type": "CARDIOLOGY_INITIAL_ASSESSMENT",
  "timestamp": "2026-02-14T21:30:00Z",

  "vitals": {
    "temperature": "98.6",
    "pulse": "72",
    "respiratory_rate": "18",
    "blood_pressure": "130/80"
  },

  "nutritional_screening": {
    "height": "170",
    "weight": "75",
    "bmi": "25.9",
    "bmi_flag": "above_24_5"
  },

  "medical_history": {
    "dm": {"status": "Yes", "since": "5 Years"},
    "ht": {"status": "Yes", "since": "3 Years"},
    "dlp": {"status": "No", "since": ""},
    "previous_mi": {"status": "No", "since": ""},
    "previous_stent": {"status": "No", "since": ""},
    "valvular_stent": {"status": "No", "since": ""},
    "anticoagulant": {"status": "Yes", "since": ""},
    "history_of_cva": {"status": "No", "since": ""},
    "history_of_copd": {"status": "No", "since": ""},
    "previous_cabg": {"status": "No", "since": ""},
    "crf": {"status": "No", "since": ""},
    "pvod": {"status": "No", "since": ""}
  },

  "drug_allergy": {
    "has_allergy": "Yes",
    "details": "Penicillin - skin rash"
  },

  "nutritional_assessment_needed": "No",
  "patient_willing": "Yes",

  "present_complaints": "Chest pain radiating to left arm for 3 Days (Moderate), Breathlessness for 1 Week (Mild)",

  "findings": {
    "positive": "Mild pedal edema, JVP elevated",
    "negative": "No pallor, No icterus, No cyanosis, No clubbing"
  },

  "provisional_diagnosis": "Acute Coronary Syndrome (I21.9), Essential Hypertension (I10)",

  "suggested_investigations": {
    "blood_investigations": "CBC, Troponin I, Lipid profile, RFT, LFT",
    "ecg": true,
    "ct": false,
    "echo": true,
    "mri": false,
    "usg": false,
    "bmd": false,
    "xray": true,
    "mammogram": false
  },

  "consultants_referral": "Dr. X, Interventional Cardiology",

  "treatment_and_future_plan": {
    "drugs_as_per_prescription": "Yes",
    "admission": "Yes",
    "reason_for_admission": "Acute chest pain with positive troponin",
    "type_of_admission": "ICU"
  },

  "prescription": [
    {
      "name": "Aspirin 325mg",
      "dosage": "1-0-0-0",
      "duration_days": "30",
      "remarks": "After food"
    }
  ],

  "other_instructions": "Strict bed rest. Monitor vitals every 2 hours.",

  "doctor_name": "Dr. Kumar",
  "time": "21:30",
  "review_on": "21-02-2026"
}
```

---

## Files to Create/Modify

### 1. NEW: `backend/services/kg_service.py` (~300-350 lines)
Following `aosta_service.py` pattern:

**Keyword dictionaries:**
```python
MEDICAL_HISTORY_KEYWORDS = {
    "dm": ["diabetes", "diabetic", "dm", "t2dm", "t1dm", "iddm", "niddm", "sugar", "hyperglycemia"],
    "ht": ["hypertension", "hypertensive", "ht", "htn", "high blood pressure", "systemic hypertension"],
    "dlp": ["dyslipidemia", "dlp", "hyperlipidemia", "hypercholesterolemia", "high cholesterol"],
    "previous_mi": ["myocardial infarction", "mi", "heart attack", "stemi", "nstemi", "acs"],
    "previous_stent": ["stent", "stenting", "pci", "ptca", "angioplasty"],
    "valvular_stent": ["valvular stent", "valve replacement", "mvr", "avr", "prosthetic valve"],
    "anticoagulant": ["anticoagulant", "warfarin", "heparin", "rivaroxaban", "apixaban", "dabigatran", "acenocoumarol"],
    "history_of_cva": ["cva", "stroke", "cerebrovascular", "tia", "transient ischemic", "cerebral infarct"],
    "history_of_copd": ["copd", "chronic obstructive", "emphysema", "chronic bronchitis"],
    "previous_cabg": ["cabg", "bypass", "coronary artery bypass"],
    "crf": ["crf", "ckd", "chronic renal", "chronic kidney", "renal failure", "dialysis"],
    "pvod": ["pvod", "pvd", "peripheral vascular", "peripheral arterial", "claudication"]
}

INVESTIGATION_KEYWORDS = {
    "ecg": ["ecg", "electrocardiogram", "ekg", "12 lead"],
    "ct": ["ct scan", "ct ", "computed tomography", "hrct", "cect"],
    "echo": ["echo", "echocardiogram", "2d echo", "tte", "tee"],
    "mri": ["mri", "magnetic resonance", "cardiac mri"],
    "usg": ["usg", "ultrasound", "ultrasonography", "doppler"],
    "bmd": ["bmd", "bone mineral density", "dexa"],
    "xray": ["x-ray", "xray", "cxr", "chest x", "radiograph"],
    "mammogram": ["mammogram", "mammography"]
}
```

**Functions:**
- `_strip_units(value, units)` → str
- `_compute_bmi_flag(bmi_str)` → "below_18_5" | "normal" | "above_24_5"
- `_parse_medical_history(known_medical_problems, detailed_history)` → dict of 12 checkboxes
- `_parse_investigation_checkboxes(clinical_notes, follow_up)` → dict with blood + 8 checkboxes
- `_parse_admission_decision(follow_up, clinical_notes)` → dict
- `_parse_referral(follow_up, clinical_notes)` → str
- `_combine_findings(general_exam, systemic_exam)` → dict with positive/negative
- `_format_complaints(chief_complaints)` → str
- `_format_diagnosis(diagnosis_array)` → str
- `_format_prescription(prescription_array)` → list
- `format_for_kg(extraction_segments, patient_id, doctor_id, extraction_id)` → payload dict
- `async send_to_kg(payload, api_url, api_key)` → HTTP POST result

### 2. MODIFY: `backend/services/ehr_routing_service.py` (~20 lines)
Add `kg_ehr` route in `route_to_ehr()`:
```python
elif ehr_code == "kg_ehr":
    await _send_to_kg(extraction_data, patient_info, final_url, api_key, extraction_id)
```

Add `_send_to_kg()` method following `_send_to_aosta()` pattern.

### 3. NO migration needed
- `kg_ehr` already exists in `ehr_types` table
- Hospital config (api_url, api_key) will be configured in `hospital_ehr` later

---

## Extraction Field Name Handling

The formatter handles segment-based extraction output (camelCase keys):
| Segment Code | Output Key | Schema |
|---|---|---|
| VITALS | `vitals` | {vital_signs: {temperature, blood_pressure, pulse, ...}} |
| ALLERGY | `allergy` | {has_allergy, allergy_type, details} |
| CHIEF_COMPLAINTS | `chiefComplaints` | [{complaint_name, since_value, since_unit, severity, notes}] |
| GENERAL_HISTORY | `generalHistory` | {known_medical_problems: [{condition, since_value, since_unit, details}], ...} |
| GENERAL_EXAMINATION | `generalExamination` | {general_findings, level_of_consciousness, ...} |
| SYSTEMIC_EXAMINATION | `systemicExamination` | [{system_type, examination}] |
| DIAGNOSIS | `diagnosis` | [{name, code, type}] |
| PRESCRIPTION | `prescription` | [{name, dosage, duration, ...}] |
| FOLLOW_UP | `followUp` | {review_date, special_instructions, ...} |
| CLINICAL_NOTES | `clinicalNotes` | string or object |

Also checks legacy PascalCase keys as fallback.

---

## Implementation Order

1. **Create `backend/services/kg_service.py`** - keyword dicts, helper parsers, `format_for_kg()`, `send_to_kg()`
2. **Modify `backend/services/ehr_routing_service.py`** - add kg_ehr route + `_send_to_kg()`
3. **Test** - manually run formatter against a real OP_PSG_NEW extraction
4. **Configure** - when API URL is ready, INSERT config into `hospital_ehr` table

## Pipeline Latency: ZERO impact
All EHR sends use fire-and-forget (`asyncio.create_task()`) inside existing `schedule_ehr_sync()`. No pipeline changes.

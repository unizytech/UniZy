# KG Hospital EHR Payload Specification

## Overview

Two payload formats for KG Hospital Cardiology EHR integration:

1. **CARDIOLOGY_INITIAL_ASSESSMENT** — First visit / initial assessment
2. **CARDIOLOGY_REASSESSMENT** — Follow-up / re-assessment visit

Both payloads share a common structure. The reassessment payload is a subset of the initial assessment, with `comorbidities`, `drug_allergy`, `nutritional_assessment_needed`, and `past_medical_history` removed, and `has_patient_improved` added.

---

## Common Fields (Both Payloads)

### Metadata

| Field | Type | Description |
|---|---|---|
| `patient_id` | string | Patient UUID |
| `uhid` | string | Patient UHID (external hospital ID) |
| `visit_id` | string | Visit ID from recording metadata |
| `doctor_id` | string | Doctor UUID |
| `extraction_id` | string | Extraction UUID |
| `form_type` | string | `"CARDIOLOGY_INITIAL_ASSESSMENT"` or `"CARDIOLOGY_REASSESSMENT"` |
| `timestamp` | string | ISO 8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`) |

### 1. Vitals

| Field | Type | Description |
|---|---|---|
| `vitals.temperature` | string | Temperature (numeric, units stripped) |
| `vitals.pulse` | string | Pulse rate (numeric, units stripped) |
| `vitals.respiratory_rate` | string | Respiratory rate (numeric) |
| `vitals.blood_pressure` | string | Format: `"systolic/diastolic"` e.g. `"130/80"` |
| `vitals.spo2` | string | SpO2 percentage (numeric) |
| `vitals.date_time` | string | Date/time of recording (`YYYY-MM-DD HH:MM`) |

### 2. Nutritional Screening

| Field | Type | Description |
|---|---|---|
| `nutritional_screening.height` | string | Height in cm (numeric) |
| `nutritional_screening.weight` | string | Weight in kg (numeric) |
| `nutritional_screening.bmi` | string | BMI value |
| `nutritional_screening.bmi_flag` | string | `"below_18_5"`, `"normal"`, or `"above_24_5"` |

### 5. Present Complaints

| Field | Type | Description |
|---|---|---|
| `present_complaints` | string | Comma-separated complaints with duration and severity. E.g. `"Chest pain for 3 days (moderate), Breathlessness for 1 week (mild)"` |

### 6. History of Presenting Illness

| Field | Type | Description |
|---|---|---|
| `history_of_presenting_illness` | string | Narrative text combining: current complaints, last visit, recent labs, activity status, ADL status, negative symptoms. Sourced from `HISTORY_OF_PRESENT_ILLNESS` segment. |

### 8. Family History

| Field | Type | Description |
|---|---|---|
| `family_history` | string | Formatted text from `HISTORY.familyHistory[]`. E.g. `"Father: Hypertension (20 years) - On treatment, Mother: Diabetes"` |

### 9. Drug History

| Field | Type | Description |
|---|---|---|
| `drug_history` | string | Current medications from `HISTORY_OF_PRESENT_ILLNESS.current_medications[]` + `other_specialty_medications`. E.g. `"Tab Metformin 500mg BD, Tab Amlodipine 5mg OD"` |

### 10. General Examination

| Field | Type | Description |
|---|---|---|
| `general_examination.face` | string | Findings related to face (pallor, cyanosis) |
| `general_examination.eyes` | string | Findings related to eyes (icterus, scleral, conjunctival) |
| `general_examination.neck` | string | JVP, lymphadenopathy, thyroid findings |
| `general_examination.legs` | string | Pedal edema, clubbing, lower limb findings |
| `general_examination.others` | string | General appearance + remaining findings |

### 11. Systemic Examination

| Field | Type | Description |
|---|---|---|
| `systemic_examination.cvs` | string | Cardiovascular system findings |
| `systemic_examination.rs` | string | Respiratory system findings |
| `systemic_examination.abdomen_gi` | string | Abdomen / GI system findings |
| `systemic_examination.cns` | string | Central nervous system findings |
| `systemic_examination.local_examination` | string | Other / local examination findings |

### 12. Diagnosis

| Field | Type | Description |
|---|---|---|
| `diagnosis` | string | Comma-separated diagnoses with ICD codes. E.g. `"Unstable Angina (I20.0), Essential Hypertension (I10)"` |

### 13. Investigations List

| Field | Type | Description |
|---|---|---|
| `investigations_list` | array | `[{"service_id": "", "service_name": "ECG"}, ...]` — all investigations with external IDs |

### 14. Treatment and Future Plan

| Field | Type | Description |
|---|---|---|
| `treatment_and_future_plan` | string | Combined text from: treatment notes, doctor instructions, follow-up instructions, and "Drugs as per prescription" if medications were prescribed. E.g. `"Continue medications. Low salt diet. Avoid strenuous activity. Bring ECG reports. Drugs as per prescription"` |

### Prescription (array)

Each item in the `prescription` array:

| Field | Type | Description |
|---|---|---|
| `drug_id` | string | External drug ID (from medicine list) |
| `drug_name` | string | Medicine name with strength |
| `frequency` | object | `{"M": bool, "A": bool, "E": bool, "N": bool}` — Morning/Afternoon/Evening/Night |
| `duration` | number/string | Duration value (e.g. `30`) or `""` |
| `duration_unit` | string | `"Day"`, `"Week"`, `"Month"`, `"Year"`, or `""` |
| `quantity` | string | Total quantity (frequency per day x duration in days) or `""` |
| `intake` | string | `"After Food"`, `"Before Food"`, `"With Food"`, `"If Needed"`, or `""` |
| `route` | string | `"Oral"`, `"Sublingual"`, `"Intravenous"`, `"Intramuscular"`, etc. |
| `intake_period` | string | `"SOS"`, `"STAT"`, `"Alternate days"`, `"Weekly once"`, etc. or `""` |
| `quantity_uom` | string | Unit of measure (currently `""`) |
| `instructions` | string | Special instructions / remarks |
| `investigation` | string | Related investigation (currently `""`) |
| `next_review_date` | string | Follow-up date (`DD-MM-YYYY`) |
| `prescription_valid_upto` | string | Prescription validity (currently `""`) |

### 15. Consultants Referral

| Field | Type | Description |
|---|---|---|
| `consultants_referral` | string | Referral text extracted from clinical notes. Empty string if none. |

### Other Fields

| Field | Type | Description |
|---|---|---|
| `doctor_name` | string | Doctor full name |
| `time` | string | Time of extraction (`HH:MM` 24hr format) |
| `review_on` | string | Follow-up date (`DD-MM-YYYY`) |

---

## Initial Assessment Only Fields

These fields are **only present** in `CARDIOLOGY_INITIAL_ASSESSMENT`:

### 3. Comorbidities (12 Checkboxes)

9 medical condition checkboxes matched from `GENERAL_HISTORY.known_medical_problems[]` + 3 habit checkboxes from `HISTORY.habits[]`.

Only DM, HT, DLP, and History of COPD include a `"since"` field. All others are `{"status": "Yes"/"No"}` only.

| Field | Description | Has "since"? |
|---|---|---|
| `comorbidities.dm` | Diabetes Mellitus | Yes |
| `comorbidities.ht` | Hypertension | Yes |
| `comorbidities.dlp` | Dyslipidemia | Yes |
| `comorbidities.history_of_copd` | History of COPD | Yes |
| `comorbidities.previous_mi` | Previous Myocardial Infarction | No |
| `comorbidities.previous_stent` | Previous Stent / PCI | No |
| `comorbidities.renal_failure` | Renal Failure (CKD/CRF) | No |
| `comorbidities.history_of_cva` | History of CVA / Stroke | No |
| `comorbidities.peripheral_vascular_disease` | Peripheral Vascular Disease | No |
| `comorbidities.smoking` | Smoking (from habits) | No |
| `comorbidities.tobacco_chewing` | Tobacco Chewing (from habits) | No |
| `comorbidities.alcohol_intake` | Alcohol Intake (from habits) | No |

### 4. Drug Allergy

| Field | Type | Description |
|---|---|---|
| `drug_allergy.has_allergy` | string | `"Yes"` or `"No"` |
| `drug_allergy.details` | string | Allergy details |

### 7. Past Medical History

| Field | Type | Description |
|---|---|---|
| `past_medical_history` | string | Free text from `GENERAL_HISTORY.detailed_medical_history` |

### Other Initial-Only Fields

| Field | Type | Description |
|---|---|---|
| `nutritional_assessment_needed` | string | `"No"` (default) |

---

## Reassessment Only Fields

These fields are **only present** in `CARDIOLOGY_REASSESSMENT`:

| Field | Type | Description |
|---|---|---|
| `has_patient_improved` | string | Whether patient has improved since last visit (free text from CLINICAL_NOTES) |

---

## Sample Payloads

### CARDIOLOGY_INITIAL_ASSESSMENT

```json
{
  "patient_id": "pat-uuid-123",
  "uhid": "KG2024001",
  "visit_id": "V-001",
  "doctor_id": "doc-uuid-456",
  "extraction_id": "ext-uuid-789",
  "form_type": "CARDIOLOGY_INITIAL_ASSESSMENT",
  "timestamp": "2026-04-03T02:45:23Z",
  "vitals": {
    "temperature": "98.6",
    "pulse": "72",
    "respiratory_rate": "18",
    "blood_pressure": "130/80",
    "spo2": "98",
    "date_time": "2026-04-03 02:45"
  },
  "nutritional_screening": {
    "height": "170",
    "weight": "75",
    "bmi": "25.9",
    "bmi_flag": "above_24_5"
  },
  "nutritional_assessment_needed": "No",
  "comorbidities": {
    "dm": { "status": "Yes", "since": "5 years" },
    "ht": { "status": "Yes", "since": "3 years" },
    "dlp": { "status": "No", "since": "" },
    "history_of_copd": { "status": "No", "since": "" },
    "previous_mi": { "status": "Yes" },
    "previous_stent": { "status": "No" },
    "renal_failure": { "status": "No" },
    "history_of_cva": { "status": "No" },
    "peripheral_vascular_disease": { "status": "No" },
    "smoking": { "status": "Yes" },
    "tobacco_chewing": { "status": "No" },
    "alcohol_intake": { "status": "Yes" }
  },
  "drug_allergy": {
    "has_allergy": "Yes",
    "details": "Penicillin - causes rash"
  },
  "present_complaints": "Chest pain for 3 days (moderate), Breathlessness for 1 week (mild)",
  "history_of_presenting_illness": "C/of chest pain since 3 days, aggravated on exertion. Last visit: Last visit 01/03/2026 under Dr. XY. Recent labs: HbA1c: 7.2, Cr: 1.1. Activity: Sedentary. ADL: ADL- Good. Denies: No dyspnea at rest, no palpitation",
  "past_medical_history": "Known case of DM and HTN on regular treatment since 5 years",
  "family_history": "Father: Hypertension (20 years) - On treatment, Mother: Type 2 Diabetes",
  "drug_history": "Tab Metformin 500mg BD, Tab Amlodipine 5mg OD, Tab Aspirin 75mg OD",
  "general_examination": {
    "face": "No pallor, no cyanosis",
    "eyes": "no icterus",
    "neck": "JVP: Normal",
    "legs": "no pedal edema, no clubbing",
    "others": "Conscious, oriented"
  },
  "systemic_examination": {
    "cvs": "S1S2 heard, systolic murmur grade 2/6 at apex",
    "rs": "Bilateral basal crepitations",
    "abdomen_gi": "Soft, non-tender",
    "cns": "No focal neurological deficit",
    "local_examination": ""
  },
  "diagnosis": "Unstable Angina (I20.0), Essential Hypertension (I10)",
  "investigations_list": [
    { "service_id": "", "service_name": "ECG" },
    { "service_id": "", "service_name": "Complete Blood Count" },
    { "service_id": "", "service_name": "Lipid Profile" },
    { "service_id": "", "service_name": "Chest X-Ray" },
    { "service_id": "", "service_name": "2D Echocardiogram" }
  ],
  "treatment_and_future_plan": "Continue current medications. Low salt diet, avoid heavy exertion. Bring previous ECG reports. Fasting required for blood tests. Drugs as per prescription",
  "prescription": [
    {
      "drug_id": "",
      "drug_name": "Aspirin 150mg",
      "frequency": { "M": true, "A": false, "E": false, "N": false },
      "duration": 30,
      "duration_unit": "Day",
      "quantity": "30",
      "intake": "After Food",
      "route": "Oral",
      "intake_period": "",
      "quantity_uom": "",
      "instructions": "",
      "investigation": "",
      "next_review_date": "03-05-2026",
      "prescription_valid_upto": ""
    },
    {
      "drug_id": "",
      "drug_name": "Atorvastatin 40mg",
      "frequency": { "M": false, "A": false, "E": true, "N": false },
      "duration": 30,
      "duration_unit": "Day",
      "quantity": "30",
      "intake": "After Food",
      "route": "Oral",
      "intake_period": "",
      "quantity_uom": "",
      "instructions": "",
      "investigation": "",
      "next_review_date": "03-05-2026",
      "prescription_valid_upto": ""
    },
    {
      "drug_id": "",
      "drug_name": "Metoprolol 25mg",
      "frequency": { "M": true, "A": false, "E": true, "N": false },
      "duration": 30,
      "duration_unit": "Day",
      "quantity": "60",
      "intake": "Before Food",
      "route": "Oral",
      "intake_period": "",
      "quantity_uom": "",
      "instructions": "Monitor pulse",
      "investigation": "",
      "next_review_date": "03-05-2026",
      "prescription_valid_upto": ""
    },
    {
      "drug_id": "",
      "drug_name": "Sorbitrate 5mg",
      "frequency": { "M": false, "A": false, "E": false, "N": false },
      "duration": "",
      "duration_unit": "",
      "quantity": "",
      "intake": "If Needed",
      "route": "Sublingual",
      "intake_period": "SOS",
      "quantity_uom": "",
      "instructions": "For acute chest pain",
      "investigation": "",
      "next_review_date": "03-05-2026",
      "prescription_valid_upto": ""
    }
  ],
  "consultants_referral": "Refer to Dr. Sharma for cardiac rehab",
  "doctor_name": "Dr. Ramesh Kumar",
  "time": "02:45",
  "review_on": "03-05-2026"
}
```

### CARDIOLOGY_REASSESSMENT

```json
{
  "patient_id": "pat-uuid-123",
  "uhid": "KG2024001",
  "visit_id": "V-002",
  "doctor_id": "doc-uuid-456",
  "extraction_id": "ext-uuid-890",
  "form_type": "CARDIOLOGY_REASSESSMENT",
  "timestamp": "2026-05-03T10:30:00Z",
  "vitals": {
    "temperature": "98.4",
    "pulse": "68",
    "respiratory_rate": "16",
    "blood_pressure": "126/78",
    "spo2": "99",
    "date_time": "2026-05-03 10:30"
  },
  "nutritional_screening": {
    "height": "170",
    "weight": "74",
    "bmi": "25.6",
    "bmi_flag": "above_24_5"
  },
  "has_patient_improved": "Yes, chest pain reduced significantly. No breathlessness at rest.",
  "present_complaints": "Occasional chest discomfort on heavy exertion",
  "history_of_presenting_illness": "C/of occasional chest discomfort on heavy exertion, improved from last visit. Last visit: 03/04/2026 under Dr. Ramesh Kumar. Recent labs: Lipid profile improved, LDL 95. Activity: Walking 30 min daily. ADL: Good. Denies: No syncope, no palpitation",
  "family_history": "Father: Hypertension (20 years) - On treatment, Mother: Type 2 Diabetes",
  "drug_history": "Tab Aspirin 150mg OD, Tab Atorvastatin 40mg HS, Tab Metoprolol 25mg BD",
  "general_examination": {
    "face": "No pallor, no cyanosis",
    "eyes": "no icterus",
    "neck": "JVP: Normal",
    "legs": "no pedal edema",
    "others": "Comfortable, well-oriented"
  },
  "systemic_examination": {
    "cvs": "S1S2 normal, no murmur",
    "rs": "Clear bilateral air entry, no added sounds",
    "abdomen_gi": "Soft, non-tender",
    "cns": "",
    "local_examination": ""
  },
  "diagnosis": "Stable Angina (I20.8), Essential Hypertension (I10) - controlled",
  "investigations_list": [
    { "service_id": "", "service_name": "ECG" },
    { "service_id": "", "service_name": "Lipid Profile" }
  ],
  "treatment_and_future_plan": "Continue walking. Low salt diet. Review ECG next visit. Drugs as per prescription",
  "prescription": [
    {
      "drug_id": "",
      "drug_name": "Aspirin 150mg",
      "frequency": { "M": true, "A": false, "E": false, "N": false },
      "duration": 30,
      "duration_unit": "Day",
      "quantity": "30",
      "intake": "After Food",
      "route": "Oral",
      "intake_period": "",
      "quantity_uom": "",
      "instructions": "",
      "investigation": "",
      "next_review_date": "03-06-2026",
      "prescription_valid_upto": ""
    },
    {
      "drug_id": "",
      "drug_name": "Atorvastatin 40mg",
      "frequency": { "M": false, "A": false, "E": true, "N": false },
      "duration": 30,
      "duration_unit": "Day",
      "quantity": "30",
      "intake": "After Food",
      "route": "Oral",
      "intake_period": "",
      "quantity_uom": "",
      "instructions": "",
      "investigation": "",
      "next_review_date": "03-06-2026",
      "prescription_valid_upto": ""
    },
    {
      "drug_id": "",
      "drug_name": "Metoprolol 25mg",
      "frequency": { "M": true, "A": false, "E": true, "N": false },
      "duration": 30,
      "duration_unit": "Day",
      "quantity": "60",
      "intake": "Before Food",
      "route": "Oral",
      "intake_period": "",
      "quantity_uom": "",
      "instructions": "Monitor pulse",
      "investigation": "",
      "next_review_date": "03-06-2026",
      "prescription_valid_upto": ""
    }
  ],
  "consultants_referral": "",
  "doctor_name": "Dr. Ramesh Kumar",
  "time": "10:30",
  "review_on": "03-06-2026"
}
```

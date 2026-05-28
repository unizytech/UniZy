# NEPHRO_INITIAL → KG Hospital Nephrology Payload

This document captures the exact payload that the backend formats and POSTs to the KG Hospital API URL after a NEPHRO_INITIAL extraction completes.

- **Template code:** `NEPHRO_INITIAL`


## Key dispatch contract

| Source segment (camelCase, in extraction JSON) | Target field in KG payload |
|---|---|
| `vitals` | `vitals.{temperature, pulse, respiratory_rate, blood_pressure, spo2}` (+ runtime `date_time`) |
| `nutritionalScreening` | `nutritional_screening.{height, weight, bmi, bmi_flag}` |
| `comorbiditiesNephro` (with fallback to `comorbidities`) | `comorbidities` — normalized to all 16 nephro keys |
| `allergy` | `drug_allergy.{has_allergy, details}` |
| `chiefComplaints` (string) | `present_complaints` |
| `historyOfPresentIllness.history_of_presenting_illness` | `history_of_presenting_illness` |
| `historyOfPresentIllness.drug_history` | `drug_history` |
| `generalHistory.past_medical_history` | `past_medical_history` |
| `history.family_history` | `family_history` |
| `generalExamination` (object: eyes/face/legs/neck/others) | `general_examination` (passthrough) |
| `systemicExamination` (object: rs/cns/cvs/abdomen_gi/local_examination) | `systemic_examination` (passthrough) |
| `diagnosis` (array of {name, code, type}) | `diagnosis` — joined into single semicolon-separated string `"Name (CODE) [Type]; …"` |
| `investigations` (array of {name, type, date}) | `investigations_list` (passthrough) **and** `suggested_packages` (keyword-matched booleans + `others` free-text) |
| `bloodGroup.{blood_group, rh, transfusion_history.{received, details}}` | `blood_profile.{blood_group, rh, transfusion_received, transfusion_details}` |
| `treatmentPlan.treatment_and_future_plan` | `treatment_and_future_plan` |
| `treatmentPlan.consultants_referral` | `consultants_referral` |
| `treatmentPlan.review_on` | `review_on` (top-level) |
| `prescription` (array) | `prescription` (passthrough) |

Runtime-only metadata fields stripped from the empty-preview response (but present in the live POST):

```
patient_id, uhid, visit_id, doctor_id, extraction_id,
form_type, timestamp, doctor_name, time, vitals.date_time
```

## Comorbidity normalization

The formatter forces all 16 nephro checklist keys into the payload (defaults to `status: ""`), so KG always sees the complete checklist regardless of what the extraction produced.

| Key | Has `since`? |
|---|---|
| `dm`, `bp`, `hematuria`, `stones`, `frequency`, `nocturia`, `straining`, `dyspnoea`, `edema`, `cough`, `fever`, `skin_rash`, `pruritus`, `nausea`, `vomiting` | yes |
| `smoking` | no (lifestyle flag, status only) |

## Investigation package keyword matching

`suggested_packages` is set by case-insensitive substring match against `investigations[].name`. Anything that doesn't match a package key falls into `others` as a comma-separated string.

| Boolean key | Triggered when `name` contains (case-insensitive) |
|---|---|
| `nephro_op_package` | "nephro op package", "nephro package" |
| `virus_package` | "virus package" |
| `transplant_package` | "transplant package" |
| `haemodialysis_package` | "haemodialysis package", "hemodialysis package" |
| `capd_package` | "capd package", "capd" |
| `usg_post_void_residual` | "usg with post void", "post void residual", "post-void residual", "pvr" |

## Sample payload (POST body sent to KG API URL)

The JSON below is generated directly by `format_for_kg_nephro` against a representative populated extraction. Placeholders in `<<...>>` are runtime-injected per request.

```json
{
  "patient_id": "<<PATIENT_UUID>>",
  "uhid": "<<UHID>>",
  "visit_id": "<<VISIT_ID>>",
  "doctor_id": "<<DOCTOR_UUID>>",
  "extraction_id": "<<EXTRACTION_UUID>>",
  "form_type": "NEPHROLOGY_INITIAL_ASSESSMENT",
  "timestamp": "2026-04-26T02:51:03Z",
  "vitals": {
    "temperature": "98.6",
    "pulse": "82",
    "respiratory_rate": "18",
    "blood_pressure": "130/80",
    "spo2": "98",
    "date_time": "2026-04-26 02:51"
  },
  "nutritional_screening": {
    "height": "172",
    "weight": "78",
    "bmi": "26.4",
    "bmi_flag": "above_24_5"
  },
  "comorbidities": {
    "dm":        { "status": "Yes", "since": "5 years"  },
    "bp":        { "status": "Yes", "since": "3 years"  },
    "smoking":   { "status": "No" },
    "hematuria": { "status": "No",  "since": "" },
    "stones":    { "status": "Yes", "since": "1 year"   },
    "frequency": { "status": "Yes", "since": "6 months" },
    "nocturia":  { "status": "Yes", "since": "6 months" },
    "straining": { "status": "No",  "since": "" },
    "dyspnoea":  { "status": "No",  "since": "" },
    "edema":     { "status": "Yes", "since": "1 month"  },
    "cough":     { "status": "No",  "since": "" },
    "fever":     { "status": "No",  "since": "" },
    "skin_rash": { "status": "No",  "since": "" },
    "pruritus":  { "status": "Yes", "since": "2 weeks"  },
    "nausea":    { "status": "No",  "since": "" },
    "vomiting":  { "status": "No",  "since": "" }
  },
  "drug_allergy": {
    "has_allergy": "Yes",
    "details": "Penicillin"
  },
  "present_complaints": "Fatigue, leg swelling, frequent urination at night",
  "history_of_presenting_illness": "Last visit: 04/11/2025 under Dr. AP. Recent labs: creatinine 2.1, K+ 5.3, Hb 9.5, eGFR 32. Activity status: Walks short distances, gets dyspneic. ADL status: Independent. Current complaints: progressive fatigue, pedal edema. Denied: chest pain, oliguria.",
  "past_medical_history": "DM Type 2 (5y), HTN (3y), Renal stones (1y)",
  "family_history": "Father - CKD; Mother - Diabetes",
  "drug_history": "Telmisartan 40mg OD. Furosemide 40mg BD. Other specialty medications: Metformin 500mg BD (Endocrinologist).",
  "general_examination": {
    "eyes": "Periorbital edema present",
    "face": "Pallor noted",
    "legs": "Bilateral pedal edema, pitting",
    "neck": "JVP raised",
    "others": "Anaemia present"
  },
  "systemic_examination": {
    "rs": "Bilateral crepitations at bases",
    "cns": "Conscious, oriented; no focal deficit",
    "cvs": "S1 S2 normal; no murmur",
    "abdomen_gi": "Soft, non-tender, no organomegaly",
    "local_examination": ""
  },
  "diagnosis": "Chronic Kidney Disease Stage 3b (N18.32) [Primary]; Type 2 Diabetes Mellitus (E11.9) [Secondary]; Essential Hypertension (I10) [Secondary]",
  "investigations_list": [
    { "name": "Nephro OP Package",            "type": "Laboratory", "date": "26-04-2026" },
    { "name": "USG with Post Void Residual",  "type": "Imaging",    "date": "26-04-2026" },
    { "name": "Urine Routine",                "type": "Laboratory", "date": "26-04-2026" }
  ],
  "suggested_packages": {
    "nephro_op_package": true,
    "virus_package": false,
    "transplant_package": false,
    "haemodialysis_package": false,
    "capd_package": false,
    "usg_post_void_residual": true,
    "others": "Urine Routine"
  },
  "blood_profile": {
    "blood_group": "O",
    "rh": "Positive",
    "transfusion_received": "No",
    "transfusion_details": ""
  },
  "treatment_and_future_plan": "Strict salt restriction; Renal diet; Follow-up with labs in 4 weeks",
  "consultants_referral": "Endocrinology consultation for diabetic management",
  "prescription": [
    {
      "name": "Tab Telmisartan 40mg",
      "dose": "1-0-0-0",
      "route": "Oral",
      "intake": "After Food",
      "duration": "30",
      "duration_unit": "Day",
      "intake_period": "Regular",
      "instructions": "Continue"
    },
    {
      "name": "Tab Furosemide 40mg",
      "dose": "1-0-1-0",
      "route": "Oral",
      "intake": "Before Food",
      "duration": "30",
      "duration_unit": "Day",
      "intake_period": "Regular",
      "instructions": "Monitor BP"
    }
  ],
  "doctor_name": "Dr. <doctor_name>",
  "time": "02:51",
  "review_on": "26-05-2026"
}
```

## Notes

- **`timestamp`** uses `datetime.utcnow()` formatted as `YYYY-MM-DDTHH:MM:SSZ`. **`vitals.date_time`** uses `YYYY-MM-DD HH:MM`. **`time`** is just `HH:MM`. All three are computed at format time, not from the extraction.

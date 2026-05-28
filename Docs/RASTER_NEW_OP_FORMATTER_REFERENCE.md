# RASTER_NEW_OP Formatter Reference

Formatter mapping details for `format_for_raster_new_op()` — maps extraction insights from the RASTER_NEW_OP template to the new Raster API payload structure.

## Reused Segments (formatter change only)

### 1. DIAGNOSIS
- **Extraction key:** `diagnosis`
- **Extraction schema:** `[{name, code, type}]`
- **Target payload key:** `diagnosis[]`
- **Target schema:** `[{name, code, type}]`
- **Mapping:**
  - `name` → `name` (1:1)
  - `code` → `code` (1:1)
  - `type` → `type` (map "Primary"/"Secondary" → "Provisional" if needed)

### 2. PRESCRIPTION → medications
- **Extraction key:** `prescription`
- **Extraction schema:** `[{name, form, morning_qty, noon_qty, evening_qty, night_qty, durationDays, timeToTake, remarks}]`
- **Target payload key:** `medications[]`
- **Mapping per medicine:**

| Extraction Field | Target Field | Transform |
|---|---|---|
| `name` | `productName` | 1:1 |
| `_external_id` | `productId` | From medicine matching; string |
| `_external_code` | `productCode` | From medicine matching; string |
| `_formulary_name` | `productGenericName`, `moleculeName` | From medicine matching |
| `form` | `medicineType` | Via `_map_to_raster_medicine_type()` |
| `morning_qty` | `M` | Parse to float |
| `noon_qty` | `A` | Parse to float |
| `evening_qty` | `N` | Parse to float |
| `night_qty` | `E` | Parse to float |
| `durationDays` | `duration` | Format as "X days" |
| `timeToTake` | `when` | 1:1 (e.g., "Before food", "After food") |
| `remarks` | `notes` | 1:1 |
| (computed) | `frequency` | Build from M/A/N/E: "1.5 - 1.5 - 1.5" |
| (computed) | `totalQuantity` | frequency_count x duration_number |

- **Static fields per medicine:** `type: "Daily"`, `consumableQuantity: ""`, `unit: ""`, `where: ""`, `route: ""`, `details: ""`, `startFrom: ""`, `time: ""`, `medicationUse: []`, `unitId: null`, `status: null`, `prescriptionNumber: null`, `prescriptionItemId: null`

### 3. INVESTIGATIONS → investigationValues + investigationFollowupValues
- **Extraction key:** `investigations`
- **Extraction schema:** `[{name, type, date}]`
- **Target payload keys:** `investigationValues[]` + `investigationFollowupValues[]`
- **Mapping per investigation:**

| Extraction Field | Target Field | Transform |
|---|---|---|
| `name` | `investigationName` | 1:1 |
| `_external_id` | `serviceItemId` | From investigation matching; int |
| `type` | `itemType` | "Laboratory"→"INVESTIGATION", "Imaging"→"SERVICE", "Other"→"SERVICE" |
| (from matching) | `department` | Department name from matched investigation |
| (from matching) | `unit` | Unit string (e.g., "1 qty") |
| (from matching) | `unitValue` | Numeric unit value |
| (from matching) | `favourite` | Boolean from matching |

- **Static fields:** `startDuration: null`, `endDuration: null`, `itemStatus: null`, `hisItemId: null`
- **Split logic:** Investigations with "follow-up" context or future dates → `investigationFollowupValues[]`, rest → `investigationValues[]`

### 4. TREATMENT_PLAN → advice
- **Extraction key:** `treatmentPlan`
- **Extraction schema:** `[string]`
- **Target payload key:** `advice[]`
- **Mapping:** Wrap each string → `{name: string}`
  - `"Take antibiotics"` → `{"name": "Take antibiotics"}`

### 5. FOLLOW_UP → patientDetail.nextFollowUpDate + visitNote
- **Extraction key:** `followUp`
- **Extraction schema:** `{review_date, other_instructions, special_instructions}`
- **Target payload keys:** `patientDetail.nextFollowUpDate` + `visitNote.note`
- **Mapping:**
  - `review_date` → `patientDetail.nextFollowUpDate` (convert DD-MM-YYYY → YYYY-MM-DD)
  - `special_instructions` + `other_instructions` → `visitNote.note` (join with ". ")

### 6. VITALS (schema updated with grbs)
- **Extraction key:** `vitals`
- **Target payload key:** `vitals`
- **Mapping:**

| Extraction Field | Target Field | Transform |
|---|---|---|
| `height` | `height` | 1:1 |
| `weight` | `weight` | 1:1 |
| `bmi` | `bmi` | 1:1 |
| `systolic_bp` | `bps` | Convert to string |
| `diastolic_bp` | `bpd` | Convert to string |
| (computed) | `bp` | `"{systolic_bp}/{diastolic_bp}"` |
| `temperature` | `temperature` | 1:1 |
| `pulse` | `pulse` | 1:1 |
| `respiratory_rate` | `respiratory` | 1:1 |
| `spo2` | `spO2` | 1:1 |
| `pain_score` | `painScore` | 1:1 |
| `grbs` | `grbs` | 1:1 |

- Extra extraction fields (head_circumference, waist_circumference, pregnancy_status, etc.) → ignored

## New Segments (extraction → target mapping)

### 7. CHIEF_COMPLAINTS → presentingComplaints
- **Extraction key:** `chiefComplaints`
- **Target:** `presentingComplaints[]` — direct 1:1 (schema already matches target)

### 8. HISTORY_OF_PRESENT_ILLNESS → clinicalHistory
- **Extraction key:** `historyOfPresentIllness`
- **Target:** `clinicalHistory[]` — direct 1:1 (schema already matches target)

### 9. HISTORY → familyHistory + habit
- **Extraction key:** `history`
- **Extraction schema:** `{familyHistory[], habits[]}`
- **Target keys:** `familyHistory[]` + `habit[]`
- **Mapping:**
  - `history.familyHistory` → `familyHistory` (1:1)
  - `history.habits` → `habit` (rename key only)

### 10. GENERAL_WELLNESS → generalWellness
- **Extraction key:** `generalWellness`
- **Target:** `generalWellness` — direct 1:1

### 11. GENERAL_EXAMINATION → generalExamination
- **Extraction key:** `generalExamination`
- **Target:** `generalExamination[]` — direct 1:1

### 12. EXAMINATION (Neuro) → systemicExamination
- **Extraction key:** `examination`
- **Extraction schema:** `{upperLimbRight, upperLimbLeft, lowerLimbRight, lowerLimbLeft, eyeScore, verbalScore, motorScore, pupilsRightSize, pupilsRightType[], pupilsLeftSize, pupilsLeftType[]}`
- **Target:** `systemicExamination`
- **Mapping:**
  - All limb fields → 1:1
  - `eyeScore`, `verbalScore`, `motorScore` → 1:1
  - `glasgowComaScale` → **computed** via `compute_gcs()`
  - `pupilsRightType` → join array to comma-separated string (e.g., `["Brisk","Sluggish"]` → `"Brisk,Sluggish"`)
  - `pupilsLeftType` → join array to comma-separated string
  - Add `id: 4` (static, per target sample)

### 13. SYSTEMIC_EXAMINATION → cardiovascular, respiratory, abdomen, cns, ent
- **Extraction key:** `systemicExamination`
- **Extraction schema:** `{cardiovascular[], respiratory[], abdomen[], cns[], ent[]}`
- **Target keys:** `cardiovascular[]`, `respiratory[]`, `abdomen[]`, `cns[]`, `ent[]`
- **Mapping:** Direct 1:1 — each sub-key maps to its own top-level target key

## Static / Constructed Fields

| Target Field | Source | Value |
|---|---|---|
| `patientDetail.uhid` | `patient_info` | From patient add_info |
| `patientDetail.visitNumber` | `patient_info` | From patient add_info |
| `patientDetail.templateId` | hardcoded or config | Template ID in Raster system |
| `patientDetail.visitStatus` | `patient_info` or default | "CHECKED_IN" |
| `assessmentStatus` | same as visitStatus | "CHECKED_IN" |
| `user` | static | `"emr"` |

## GCS Computation (in formatter, not extraction)

```python
def compute_gcs(data: dict) -> int | None:
    scores = [data.get("eyeScore"), data.get("verbalScore"), data.get("motorScore")]
    return sum(scores) if all(s is not None for s in scores) else None
```

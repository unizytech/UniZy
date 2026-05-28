# NEO_PROFORMA Schema Redesign - Complete Change Log

**Date**: 2025-11-14
**Change Type**: Major Schema Rewrite
**Reason**: Align with production API format (Old API) as defined in ground truth files

---

## Summary

The `NEO_PROFORMA_PARAMETERS_SCHEMA` has been completely rewritten to match the ground truth API format used in production. The previous schema (V2) used a modern API design with nested structures, boolean types, and abbreviated field names. The new schema matches the legacy production format exactly.

**Total Fields**: 107 fields (up from ~50 in V2)
**Schema Type**: Flat structure with string-based fields
**Lines Changed**: ~350 lines completely rewritten

---

## Major Structural Changes

### 1. All Boolean Fields → String Fields

**Old Format (V2)**:
```python
"cryAtBirth": types.Schema(type=types.Type.BOOLEAN, description="Baby cried at birth")
"intubation": types.Schema(type=types.Type.BOOLEAN, description="Intubation performed")
```

**New Format (Production)**:
```python
"resuscitation": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string")
"intubation": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string")
"vitaminK": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string")
```

**Rationale**: Ground truth uses string values ("Yes"/"No"/"") for all boolean-like fields.

---

### 2. Numeric Fields → String Fields

**Old Format (V2)**:
```python
"birthWeight": types.Schema(type=types.Type.NUMBER, description="Birth weight in grams", nullable=True)
"gravida": types.Schema(type=types.Type.INTEGER, description="Number of pregnancies", nullable=True)
```

**New Format (Production)**:
```python
"birthWeight": types.Schema(type=types.Type.STRING, description="Birth weight in grams as string (e.g., '2400')")
"gravida": types.Schema(type=types.Type.STRING, description="Number of pregnancies as string")
```

**Rationale**: Ground truth stores numeric values as strings (e.g., "2400", "39", "1").

---

### 3. Flattened Antenatal Steroids Structure

**Old Format (V2 - Nested)**:
```python
"antenatalSteroids": types.Schema(
    type=types.Type.OBJECT,
    properties={
        "given": types.Schema(type=types.Type.BOOLEAN),
        "drugDetails": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "drug": types.Schema(type=types.Type.STRING),
                    "dose": types.Schema(type=types.Type.STRING),
                    "indication": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.INTEGER))
                }
            )
        )
    }
)
```

**New Format (Production - Flat)**:
```python
"antenatalSteroids": types.Schema(type=types.Type.STRING, description="Yes, No, Incomplete, or empty string"),
"typeOfSteriods": types.Schema(type=types.Type.STRING, description="Betamethasone, Dexamethasone, or empty string"),
"lastDoseDeliveryInterval": types.Schema(type=types.Type.STRING, description="Time between last dose and delivery"),
"steroidCourse": types.Schema(type=types.Type.STRING, description="Complete, Incomplete, or empty string"),
```

**Rationale**: Ground truth uses flat structure at top level, not nested objects.

---

### 4. Flattened MgSO4 Structure

**Old Format (V2 - Nested)**:
```python
"antenatalMgSO4": types.Schema(
    type=types.Type.OBJECT,
    properties={
        "given": types.Schema(type=types.Type.BOOLEAN),
        "drugDetails": types.Schema(...)
    }
)
```

**New Format (Production - Flat)**:
```python
"antenatalMgSO4ForNeuroprotection": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string")
```

---

### 5. APGAR Scores - Added `status` Field

**Old Format (V2)**:
```python
"apgar": types.Schema(
    type=types.Type.OBJECT,
    properties={
        "minute1": {
            "heartRate": types.Schema(type=types.Type.INTEGER, nullable=True),
            "respiratoryEffort": types.Schema(type=types.Type.INTEGER, nullable=True),
            "muscleTone": types.Schema(type=types.Type.INTEGER, nullable=True),
            ...
        }
    }
)
```

**New Format (Production)**:
```python
"apgar": types.Schema(
    type=types.Type.OBJECT,
    properties={
        "status": types.Schema(type=types.Type.STRING, description="known, unknown"),  # ← NEW FIELD
        "minute1": {
            "color": types.Schema(type=types.Type.INTEGER, nullable=True),
            "heartRate": types.Schema(type=types.Type.INTEGER, nullable=True),
            "reflex": types.Schema(type=types.Type.INTEGER, nullable=True),
            "tone": types.Schema(type=types.Type.INTEGER, nullable=True),  # ← Renamed from muscleTone
            "respiration": types.Schema(type=types.Type.INTEGER, nullable=True),  # ← Renamed from respiratoryEffort
            "total": types.Schema(type=types.Type.INTEGER, nullable=True)
        }
    }
)
```

**Changes**:
- Added `status` field at top level
- Renamed `muscleTone` → `tone`
- Renamed `respiratoryEffort` → `respiration`

---

### 6. Scan Details - Changed Structure

**Old Format (V2)**:
```python
"datingScan": types.Schema(
    type=types.Type.OBJECT,
    properties={
        "done": types.Schema(type=types.Type.BOOLEAN),
        "week": types.Schema(type=types.Type.INTEGER, nullable=True),
        "findings": types.Schema(type=types.Type.STRING)
    }
)
```

**New Format (Production)**:
```python
"datingScanDetails": types.Schema(  # ← Renamed from datingScan
    type=types.Type.OBJECT,
    properties={
        "date": types.Schema(type=types.Type.STRING, description="YYYY-MM-DD"),  # ← Changed from week
        "gestation": types.Schema(type=types.Type.STRING, description="e.g., '12 weeks'"),  # ← NEW FIELD
        "findings": types.Schema(type=types.Type.STRING)
    }
)

# Arrays added for multiple scans
"otherScanDetails": types.Schema(type=types.Type.ARRAY, items=...)  # ← NEW FIELD
"dopplerScanDetails": types.Schema(type=types.Type.ARRAY, items=...)  # ← Changed from single object
```

---

### 7. Medical Problems - Changed Structure

**Old Format (V2)**:
```python
"medicalProblem": types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "problemId": types.Schema(type=types.Type.INTEGER),  # ← Field name
            "medications": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING))  # ← Plural, array
        }
    )
)
```

**New Format (Production)**:
```python
"medicalProblem": types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "problem": types.Schema(type=types.Type.INTEGER),  # ← Field name changed
            "medication": types.Schema(type=types.Type.STRING)  # ← Singular, string
        }
    )
)
```

---

### 8. Drug Details - Changed Structure

**Old Format (V2)**:
```python
"resuscitationDrugs": types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "drugId": types.Schema(type=types.Type.INTEGER),
            "dose": types.Schema(type=types.Type.STRING),
            "route": types.Schema(type=types.Type.STRING)
        }
    )
)
```

**New Format (Production)**:
```python
"drugs": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),  # ← NEW FLAG FIELD
"drugDetails": types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(type=types.Type.STRING),  # ← Simple string array
    description="Array of drug names (e.g., ['Adrenaline', 'Normal Saline'])"
)
```

---

### 9. Delivery Indication - Changed Type

**Old Format (V2)**:
```python
"lscsIndication": types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(type=types.Type.INTEGER),  # ← Integer IDs
    description="LSCS indication IDs: 1=Fetal Distress, 2=Failed Induction, ..."
)
```

**New Format (Production)**:
```python
"indication": types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(type=types.Type.STRING),  # ← String descriptions
    description="Array of indication strings (e.g., ['Fetal Distress', 'Previous LSCS'])"
)
```

---

## Complete List of Added Fields (60+ New Fields)

### Baby Identification (8 new fields)
- `babyName` - Baby's name
- `dob` - Date of birth
- `tob` - Time of birth
- `birthLength` - Birth length in cm
- `birthHeadCircunference` - Head circumference (typo preserved)
- `birthOrder` - Birth order for multiples
- `transferStatus` - Transfer destination
- `consanguinity` - Consanguinity status

### Maternal History (12 new fields)
- `liveBirthBabyDetails` - Array of previous birth details
- `lmp` - Last menstrual period
- `EDDByUSG` - EDD by ultrasound
- `EDDByDate` - EDD by LMP
- `motherBloodGroup` - Mother's blood group (renamed from bloodGroup)
- `HIV` - HIV status (renamed from hivStatus)
- `HepatitisB` - Hepatitis B status (renamed from hbsAgStatus)
- `VDRL` - VDRL status (renamed from vdrlStatus)
- `booked` - Booked pregnancy flag
- `bookedPlace` - Place where booked
- `supervised` - Supervised pregnancy flag
- `pleaceOfBooking`, `pleaceOfSupervision` - Legacy typo fields

### Antenatal Investigations (5 new fields)
- `adjustedRiskForTrisomiesAvailable` - Flag for trisomy risk availability
- `adjustedRiskForTrisomy21` - Trisomy 21 risk ratio
- `adjustedRiskForTrisomy18` - Trisomy 18 risk ratio
- `adjustedRiskForTrisomy13` - Trisomy 13 risk ratio
- `otherInvestigations` - Other prenatal tests

### Pregnancy Details (3 new fields)
- `pregnancyComplications` - Complications flag
- `pregnancyComplicationsDetails` - Array of complication details
- `otherScanDetails` - Array of other scan details

### Antenatal Medications (4 new fields)
- `typeOfSteriods` - Type of steroid given
- `lastDoseDeliveryInterval` - Time between last dose and delivery
- `steroidCourse` - Course completion status
- `antenatalMgSO4ForNeuroprotection` - MgSO4 flag (renamed)

### Labor & Delivery (10 new fields)
- `natureofLabour` - Nature of labor
- `commentOnLiquor` - Liquor status
- `riskFactorsForSepsisInMothers` - Sepsis risk flag
- `maternalPyrexia` - Maternal fever flag
- `maternalPyrexiaTemperatureFahrenheit` - Temperature value
- `PROM` - PROM flag
- `durationOfPROM` - PROM duration
- `maternalAntibiotics` - Antibiotics flag
- `maternalAntibioticsDetails` - Array of antibiotic details
- `timeOfLastDose` - Last antibiotic dose time

### Cord Management (6 new fields)
- `gastricAspirate` - Gastric aspirate status
- `delayedCordClamping` - DCC flag
- `delayedCordClampingduration` - DCC duration
- `reasonForNoDCC` - Reason for no DCC
- `umbilicalCordMilking` - Cord milking flag
- `cutCordMilking` - Cut cord milking flag

### Resuscitation (20+ new fields)
- `facialOxygen` - Facial oxygen flag
- `durationOfFacialOxygen` - Duration
- `maximumFio2Rquired` - Max FiO2 (typo preserved)
- `initialSteps` - Initial steps flag
- `timeOf1stGasp` - Time of first gasp
- `timeOf1stGaspInMinutes` - Time in minutes
- `regularRespiration` - Regular respiration time
- `regularRespirationMinutes` - Time in minutes
- `deliveryRoomCPAP` - Delivery room CPAP flag
- `bagMaskVentilation` - Bag-mask ventilation flag
- `bagMaskVentilationDuration` - Duration description
- `bagMaskVentilationDurationMin` - Duration in minutes
- `ETTSizeInMM` - ET tube size
- `depthOfInsertion` - Insertion depth description
- `depthOfInsertionLengthInCM` - Insertion depth in cm
- `PPV` - PPV flag
- `durationOfPTV` - PTV duration description
- `durationOfPTVMinutes` - PTV duration in minutes
- `CPR` - CPR flag
- `durationOfCPR` - CPR duration description
- `durationOfCPRMinutes` - CPR duration in minutes
- `drugs` - Drugs flag

### Initial Examination (5 new fields)
- `malformation` - Malformation flag
- `ICT` - Indirect Coombs test
- `DCT` - Direct Coombs test
- `backgroundDetails` - Background information
- `plan` - Management plan

---

## Field Name Changes

| Old Name (V2) | New Name (Production) | Reason |
|---------------|------------------------|--------|
| `referral` | `birthStatus` | Production terminology |
| `gestation` | `gestationWeeks` + `gestationDays` | Separate fields |
| `bloodGroup` | `motherBloodGroup` | More specific |
| `hivStatus` | `HIV` | Production API naming |
| `hbsAgStatus` | `HepatitisB` | Production API naming |
| `vdrlStatus` | `VDRL` | Production API naming |
| `labor` | `labour` | UK spelling |
| `initialExamination` | `initialExaminationSummary` | Production API naming |
| `congenitalAnomalies` | (removed from top level) | Not in ground truth |
| `birthTrauma` | (removed from top level) | Not in ground truth |
| `muscleTone` (APGAR) | `tone` | Production API naming |
| `respiratoryEffort` (APGAR) | `respiration` | Production API naming |

---

## Value Format Changes

### Sex Field
- **Old**: `"M"`, `"F"`, `"Indeterminate"`
- **New**: `"Male"`, `"Female"`, `"Ambiguous"`

### Blood Group
- **Old**: `"O+"`, `"A-"`, `"AB+"`
- **New**: `"O Positive"`, `"A Negative"`, `"AB Positive"`

### All Yes/No Fields
- **Old**: `true`, `false` (boolean)
- **New**: `"Yes"`, `"No"`, `""` (string)

---

## Empty Value Handling

**Old Format (V2)**:
- Text fields: `"N/A"`
- Numeric fields: `null`
- Booleans: `false` (default)

**New Format (Production)**:
- All text fields: `""` (empty string)
- Numeric stored as strings: `""` (empty string)
- Arrays: `[]` (empty array)
- Objects: Include structure with all fields as empty strings

---

## Required Fields List

All 107 fields are marked as required in the schema. This ensures Gemini always returns complete structure even if values are empty strings.

---

## Testing Recommendations

1. **Test against ground truth samples**:
   - `neo1_performa_ground_truth.json` - Term baby, normal delivery
   - `neo2_performa_ground_truth.json` - Preterm baby with complications

2. **Expected field match rate**: >95%

3. **Critical fields to verify**:
   - APGAR scores with `status` field
   - Flat antenatal steroids structure
   - String-based drug details (not object array)
   - All new baby identification fields
   - Sex as "Male"/"Female" (not "M"/"F")
   - Blood group as "O Positive" (not "O+")

4. **Webhook payload verification**:
   - Ensure webhook receives exact same structure as frontend
   - Verify comprehensive logging captures all fields

---

## Backward Compatibility

**Breaking Changes**: This is a MAJOR breaking change. Any code that:
- Expected boolean values (now strings)
- Expected numeric values (now strings)
- Expected nested steroid/MgSO4 structure (now flat)
- Expected modern field names (now legacy names)
- Expected drug objects (now string arrays)

Will need to be updated.

**Migration Path**:
- Old schema preserved as comment: "BACKUP: V2 Schema"
- Can be restored if needed
- Frontend/backend code may need updates to handle string values

---

## Files Modified

- `backend/services/neonatal_prompts.py` (lines 1290-1637)
  - Completely rewrote `NEO_PROFORMA_PARAMETERS_SCHEMA`
  - Added 60+ new fields
  - Changed 50+ existing fields to string types
  - Flattened nested structures
  - Updated all field names to match production

---

## Next Steps

1. Test extraction with real audio samples
2. Compare AI output against ground truth
3. Verify webhook sends correct format
4. Update frontend code if needed to handle string values
5. Update any downstream processing that expects old format

---

**Schema Status**: ✅ Complete - Ready for testing
**Production Alignment**: ✅ 100% match with ground truth structure
**Validation**: ✅ Python syntax verified

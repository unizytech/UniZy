# Optometrist Examination Form - Display Reference

This document describes the complete structure and layout of the optometrist examination form based on the reference image.

---

## Header Section

### Title
**OPTOMETRIST EXAMINATION FORM**

**To the Ophthalmologist:**

---

## Section 1: Patient Demographics

- **Date**: _______________
- **MR. No.**: _______________

### Referral Type
- Routine / ASAP / Urgent / Emergency (checkbox selection)

### Patient Information
- **Title**: Mr. / Mrs. / Miss / Ms. / Dr.
- **Patient's surname**: _______________
- **Name**: _______________
- **DOB**: _______________
- **Address**: _______________

---

## Section 2: Vision Measurements

### Vision Table (Bilateral)

| Eye | Vision | Refraction | VA (dist) | Add | VA (near) |
|-----|--------|------------|-----------|-----|-----------|
| RE  |        |            |           |     |           |
| LE  |        |            |           |     |           |

**Field Definitions:**
- **Vision**: Uncorrected visual acuity (e.g., 20/40, 6/12, CF, HM, PL)
- **Refraction**: Prescription in format "Sph / Cyl × Axis" (e.g., "+2.00 / -0.75 × 90")
- **VA (dist)**: Best corrected distance visual acuity (e.g., 20/20, 6/6)
- **Add**: Reading addition for presbyopia (e.g., +1.50, +2.00)
- **VA (near)**: Near visual acuity with correction (e.g., N6, J2, 20/30)

---

## Section 3: Glaucoma Assessment

### Cup-to-Disc Ratio (C/D ratio)
- **R**: _____ (Right eye, e.g., 0.3, 0.5)
- **L**: _____ (Left eye, e.g., 0.3, 0.5)

### Intraocular Pressure (IOP mmHg @)
- **R**: _____ (Right eye IOP in mmHg)
- **L**: _____ (Left eye IOP in mmHg)

### Visual Field
- **R**: _____ (Right eye visual field findings)
- **L**: _____ (Left eye visual field findings)

---

## Section 4: Clinical Notes

**Large free-text area for:**
- Chief complaint / reason for visit
- Additional clinical findings
- Recommendations
- Referral reasons
- Follow-up instructions
- Any concerning findings

---

## Section 5: Provider Signature

**Signature**: _______________

---

## Layout Notes

### Document Structure
Single-page examination form with structured data entry fields and free-text notes section

### Design Patterns
1. **Bilateral Data**: Separate RE (Right Eye) and LE (Left Eye) rows for all measurements
2. **Vision Notation**: Snellen fractions (20/20, 6/6), counting fingers (CF), hand movements (HM), light perception (PL)
3. **Refraction Format**: Sphere / Cylinder × Axis notation (e.g., "+2.00 / -0.75 × 90")
4. **IOP Values**: Numeric with mmHg unit, normal range 10-21 mmHg
5. **C/D Ratios**: Decimal values 0.0-1.0, normal ≤0.3, suspicious >0.6
6. **Visual Field**: Free text description (e.g., "Full", "Constricted", "Arcuate scotoma")

### Data Types by Section
- **Patient Demographics**: Strings (name, MR number, DOB, address)
- **Referral Type**: Enum (Routine, ASAP, Urgent, Emergency)
- **Vision**: String (Snellen notation or reduced vision notation)
- **Refraction**: String (formatted as "Sph / Cyl × Axis")
- **VA Distance/Near**: String (visual acuity notation)
- **Add**: String (positive power, e.g., "+1.50")
- **C/D Ratio**: String/Decimal (0.0-1.0)
- **IOP**: String with unit (e.g., "16 mmHg")
- **Visual Field**: String (free text findings)
- **Clinical Notes**: String (multiline free text)
- **Signature**: String

---

## Implementation Considerations

### Frontend Display
- Table-based layout for bilateral vision data
- Separate input fields for each component of refraction
- Numeric input with validation for IOP and C/D ratio
- Large textarea for clinical notes
- Clear visual hierarchy with section headers

### Data Extraction
- Segment codes should match section headers
- Preserve bilateral structure (RE/LE separation)
- Validate refraction format (sphere, cylinder, axis)
- Handle multiple vision notation systems (metric vs imperial)
- Extract IOP with units
- Flag abnormal values (elevated IOP >21 mmHg, C/D >0.6)

### Medical Terminology
- **RE/OD**: Right Eye (Oculus Dexter)
- **LE/OS**: Left Eye (Oculus Sinister)
- **VA**: Visual Acuity
- **BCVA**: Best Corrected Visual Acuity
- **IOP**: Intraocular Pressure
- **C/D**: Cup-to-Disc Ratio
- **CF**: Counting Fingers
- **HM**: Hand Movements
- **LP/PL**: Light Perception
- **Sph**: Sphere
- **Cyl**: Cylinder
- **Add**: Reading Addition
- **DS**: Diopter Sphere (no astigmatism)

---

## Common Vision Notations

### Visual Acuity Systems
- **Snellen (US)**: 20/20, 20/40, 20/400
- **Snellen (Metric)**: 6/6, 6/12, 6/120
- **Decimal**: 1.0, 0.5, 0.1
- **LogMAR**: 0.0, 0.3, 1.0
- **Reduced Vision**: CF (Counting Fingers), HM (Hand Movements), LP (Light Perception), NPL (No Light Perception)

### Refraction Notation
- **Plus Cylinder**: "+2.00 / -0.75 × 90"
- **Sphere Only**: "+2.00 DS" or "-3.50 DS"
- **Plano**: "Plano" or "PL" or "0.00"
- **Components**:
  - Sphere: +2.00 to -20.00 (typical range)
  - Cylinder: ±4.00 (typical range)
  - Axis: 1-180 degrees

### Near Vision Notation
- **N notation**: N5, N6, N8 (smaller is better)
- **Jaeger**: J1, J2, J3 (smaller is better)
- **Snellen near**: 20/20, 20/30

---

## Validation Checks

### Vision Measurements
- Snellen fractions valid (20/20 to 20/400, 6/6 to 6/120)
- Refraction values reasonable (-20.00 to +20.00)
- Cylinder values typically -4.00 to +4.00
- Axis values 1-180° only

### IOP Values
- Realistic range: 5-40 mmHg (most 10-25 mmHg)
- Flag values >21 mmHg as elevated
- Flag asymmetry >5 mmHg between eyes

### C/D Ratios
- Values between 0.0 and 1.0
- Flag values >0.6 as suspicious for glaucoma
- Flag asymmetry >0.2 between eyes

### Add Powers
- Typically +1.00 to +3.00
- Always positive values
- Usually in 0.25 or 0.50 increments
- Indicates presbyopia (age >40 years typically)

---

## Referral Urgency Levels

- **Routine**: Regular annual exam, no urgent concerns
- **ASAP**: Should be seen within days, concerning findings but not emergent
- **Urgent**: Should be seen within 24 hours, significant concerns
- **Emergency**: Immediate attention required, sight-threatening condition

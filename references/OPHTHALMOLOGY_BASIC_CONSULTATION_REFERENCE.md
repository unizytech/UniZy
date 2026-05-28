# Basic Ophthalmology Consultation - Display Reference

This document describes the complete structure and layout of the basic ophthalmology consultation form based on the reference images.

---

## Header Section

### Title
**CONSULTATION**

---

## Section 1: Patient Demographics

**Patient Details Box:**
- **MR. No.**: _______________
- **Date**: _______________
- **Patient Name**: _______________
- **Age**: _______________
- **Gender**: _______________

---

## Section 2: Clinical History

### Complaints:
Free text area for chief complaints and presenting symptoms

### Past History:
Free text area for past ocular and medical history

### Systemic illness:
Free text area for current systemic medical conditions

### Family History:
Free text area for relevant family history

### Allergy:
Free text area for known allergies

### Current Treatment:
Free text area for current medications and eye drops

### PGP (Previous Glasses Prescription):
Previous spectacle prescription

---

## Section 3: Examination (Bilateral Structure)

All examination sections have **OD** (Right Eye) and **OS** (Left Eye) columns

### Visual Acuity
- **Distance**: Snellen notation at 6m/20ft
- **Near**: Near vision measurement

### Refraction:
Objective refraction measurement (Sphere / Cylinder × Axis)

### Subjective Refraction
- **Distance**: Subjective distance refraction
- **Near**: Subjective near refraction (may include add)

### Muscle Balance:
General muscle balance assessment

**EOM (Extraocular Movements):**
Eye muscle movements

**CT (Cover Test):**
- **Dist**: Cover test at distance
- **Near**: Cover test at near

---

## Section 4: Slit Lamp Examination (Page 2)

**Bilateral columns (OD and OS)**

Free text area for comprehensive anterior segment findings including:
- Lids and lashes
- Conjunctiva
- Cornea
- Anterior chamber
- Iris
- Lens

---

## Section 5: Intraocular Pressure

**I.O.P. (Time):**
- **OD**: IOP measurement with time
- **OS**: IOP measurement with time

---

## Section 6: Gonioscopy

**Gonio Scopy:**
- **OD**: Angle findings
- **OS**: Angle findings

---

## Section 7: Fundus Examination

**Fundus:**

Bilateral circular diagrams for fundus drawings showing:
- Optic disc (central circle)
- Macula
- Blood vessels
- Peripheral retina

**OD (Right Eye) Diagram** | **OS (Left Eye) Diagram**

Free text areas for describing fundus findings for each eye

---

## Section 8: Diagnosis

**Diagnosis:**

Free text area for listing all diagnoses with eye specification

---

## Section 9: Advice and Follow-up

**Advice for continuing cares & Follow up:**

Free text area for:
- Management plan
- Medications prescribed
- Follow-up timing
- Lifestyle modifications
- Investigations ordered

---

## Section 10: Provider Information

**Signature & Name**

_______________

---

## Layout Notes

### Document Structure
Two-page consultation form with clean section organization

### Design Patterns
1. **Patient Demographics**: Single box with all identification fields
2. **Clinical History**: Sequential free-text fields for complete history
3. **Bilateral Examination**: Consistent OD/OS column structure for all measurements
4. **Visual Acuity**: Separate distance and near measurements
5. **Refraction**: Both objective and subjective with distance/near separation
6. **Muscle Balance**: EOM and cover test with distance/near
7. **Slit Lamp**: Free text for anterior segment findings
8. **Fundus**: Circular diagrams for both eyes with annotation capability
9. **Management**: Combined diagnosis, advice, and follow-up section

### Data Types by Section
- **Demographics**: Strings (MR number, name, age, gender, date)
- **History**: Strings (free text for each history category)
- **Visual Acuity**: Strings (Snellen notation - distance/near for both eyes)
- **Refraction**: Strings (Sphere/Cylinder×Axis format for both eyes)
- **Subjective Refraction**: Strings (distance and near for both eyes)
- **Muscle Balance**: Strings (EOM description, cover test distance/near)
- **Slit Lamp**: Nested object with bilateral structure
- **IOP**: Strings with unit and time (bilateral)
- **Gonioscopy**: Strings (bilateral angle findings)
- **Fundus**: Nested object with bilateral detailed structures (disc, macula, vessels, periphery)
- **Diagnosis**: Array of strings
- **Advice**: String (free text)
- **Provider**: String (signature/name)

---

## Implementation Considerations

### Frontend Display
- Clean two-column layout for bilateral data
- Clear section headers with visual hierarchy
- Fundus drawing capability with annotations
- Table-based layout for structured measurements
- Large text areas for clinical findings

### Data Extraction
- Preserve bilateral structure throughout
- Distinguish objective vs subjective refraction
- Extract distance vs near measurements separately
- Handle fundus findings by anatomical location
- Capture complete history in appropriate sections

### Medical Terminology
- **OD**: Oculus Dexter (Right Eye)
- **OS**: Oculus Sinister (Left Eye)
- **OU**: Oculus Uterque (Both Eyes)
- **EOM**: Extraocular Movements
- **CT**: Cover Test
- **IOP**: Intraocular Pressure
- **PGP**: Previous Glasses Prescription
- **VA**: Visual Acuity
- **C/D**: Cup-to-Disc Ratio
- **A:V**: Arteriole to Venule ratio

---

## Common Clinical Findings

### Visual Acuity Notation
- **Snellen**: 20/20, 20/40, 6/6, 6/12
- **Near**: N6, N8, J2, J3
- **Reduced**: CF (Counting Fingers), HM (Hand Movements), LP (Light Perception)

### Refraction Format
- **Standard**: "+2.00 / -0.75 × 90"
- **Sphere only**: "+2.00 DS" or "-3.50 DS"
- **Plano**: "Plano" or "PL"

### Cover Test Results
- **Orthophoria**: No deviation
- **Esophoria/tropia**: Inward deviation with prism diopters
- **Exophoria/tropia**: Outward deviation with prism diopters
- **Distance vs Near**: May differ

### Slit Lamp Findings
- **Lids**: Normal, blepharitis, MGD
- **Conjunctiva**: Clear, injected, pterygium
- **Cornea**: Clear, edema, opacity, ulcer
- **AC**: Deep/shallow, quiet/cells/flare
- **Iris**: Normal, atrophy, neovascularization
- **Lens**: Clear, cataract (nuclear sclerosis, cortical, PSC)

### IOP Values
- **Normal**: 10-21 mmHg
- **Elevated**: >21 mmHg (flag for glaucoma)
- **Low**: <10 mmHg

### Gonioscopy Findings
- **Open angle**: All structures visible
- **Narrow angle**: Limited view
- **Angle closure**: No structures visible
- **Grading**: Shaffer Grade 0-4

### Fundus Components
- **Optic Disc**: C/D ratio (0.0-1.0), color, margins, neovascularization
- **Macula**: Foveal reflex, hemorrhages, exudates, edema
- **Vessels**: A:V ratio (normal 2:3), caliber, tortuosity
- **Periphery**: Retinal detachment, holes, tears, lattice degeneration
- **Vitreous**: Clear, hemorrhage, floaters, PVD

---

## Validation Checks

### Data Completeness
- Patient demographics complete
- Bilateral data separated (OD vs OS)
- Distance and near measurements separate
- Objective vs subjective refraction distinguished

### Clinical Validity
- Visual acuity in valid notation
- Refraction format correct (Sph/Cyl×Axis)
- IOP values with mmHg unit
- C/D ratios as decimals (0.0-1.0)
- Cover test magnitude in prism diopters

### Medical Accuracy
- Diagnosis specifies eye affected (OD/OS/OU)
- Abnormal findings appropriately noted
- Management plan includes medications with dosages
- Follow-up timing specified

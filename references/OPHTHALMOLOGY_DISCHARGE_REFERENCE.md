# Ophthalmology Discharge Summary - Display Reference

This document describes the complete structure and layout of the ophthalmology discharge summary based on the reference image.

---

## Header Section

### Title
**DISCHARGE SUMMARY**

---

## Section 1: Patient Details

### PATIENT DETAILS
- **Name**: _______________
- **Visit ID**: _______________
- **MRNO**: _______________
- **Date**: _______________
- **Age**: _______________
- **Gender**: _______________

---

## Section 2: Admission & Procedure Dates

- **Date of Admission**: DD-MM-YYYY
- **Date of Procedure**: DD-MM-YYYY

---

## Section 3: Medical Team

### Doctors who attended on the patient:
| Name | Registration Number |
|------|---------------------|
|      |                     |

---

## Section 4: Diagnosis

**Diagnosis:**
- Eye-specific diagnosis with laterality (e.g., "Left Eye: Double pterygium Nasal and Temporal")

**Condition of the patient on admission:**
- General condition (fair, good, stable)

**Nutritional Status:**
- Normal, Well-nourished, Malnourished, or N/A

---

## Section 5: Treatment Given

### Treatment given with dates:
Complete procedure description with:
- **Eye**: RIGHT EYE / LEFT EYE / BOTH EYES
- **Procedure**: PROCEDURE NAME IN CAPITALS (e.g., "NASAL + TEMPORAL PTERYGIUM EXCISION WITH CONJUNCTIVAL AUTOGRAFT")
- **Anesthesia**: under local anaesthesia / general anaesthesia
- **Date**: DD-MM-YYYY

**Example:**
```
LEFT EYE: NASAL + TEMPORAL PTERYGIUM EXCISION WITH CONJUNCTIVAL AUTOGRAFT
under local anaesthesia on 15-10-2025
```

---

## Section 6: Condition on Discharge

**Condition of the patient on discharge:**
- Good, Stable, Satisfactory, Comfortable

---

## Section 7: Discharge Medication & Advice

### Discharge Medication & Advice on Discharge:

**Diet:**
- Normal, Light diet, Diabetic diet, etc.

**Physical Activity:**
- Normal, Avoid strenuous activities, Light activities only

**Special Instructions:**
- Post-operative care instructions (array/list format):
  - "Not to lie on operated side for X days"
  - "Wear dark glasses"
  - "Avoid water entering eyes"
  - "Use eye shield at night"
  - etc.

**Next Review:**
- DD-MM-YYYY or relative timing (e.g., "in 1 week")

---

## Section 8: Emergency Contact Information

### Please Contact the hospital immediately if patient has the following symptoms:
- Decrease in vision
- Pain
- Redness in the eyes
- Other emergency symptoms

**Hospital Contact Details:**
- Telephone No.: _______________
- Name: _______________
- Mobile No.: _______________
- Signature: _______________
- Reg. No.: _______________
- Seal: _______________

---

## Section 9: Administrative

**For Emergency Admin issues please contact:**
- Contact information

---

## Layout Notes

### Document Structure
Single-page discharge summary with clear sections

### Design Patterns
1. **Eye Specification**: Always specify which eye (Left Eye, Right Eye, Both Eyes)
2. **Procedure Details**: Include complete procedure name, technique, anesthesia, date
3. **Medication Format**: Drug name + strength + frequency + duration + eye specification
4. **Instructions**: Array of specific post-operative instructions
5. **Emergency Symptoms**: List of warning signs for immediate contact
6. **Date Format**: DD-MM-YYYY consistently used

### Data Types by Section
- **Patient Demographics**: Strings (name, MR number, age, gender)
- **Dates**: DD-MM-YYYY format
- **Diagnosis**: Object with eye laterality (rightEye, leftEye, bothEyes)
- **Treatment**: Structured object with eye, procedure, anesthesia, date
- **Medications**: Array of medication objects with dosage, frequency, route, eye
- **Instructions**: Array of strings
- **Emergency Symptoms**: Array of strings
- **Contact Details**: Object with telephone, name, mobile

---

## Implementation Considerations

### Frontend Display
- Clear section headers with visual hierarchy
- Eye laterality prominently displayed
- Medication table with all details
- Checklist format for special instructions
- Highlighted emergency symptoms section

### Data Extraction
- Segment codes should match section headers
- Preserve eye laterality throughout
- Extract complete medication details (name + strength)
- Capture all post-operative instructions
- Handle bilateral vs unilateral procedures

### Medical Terminology
- **OD**: Oculus Dexter (Right Eye)
- **OS**: Oculus Sinister (Left Eye)
- **OU**: Oculus Uterque (Both Eyes)
- **IOL**: Intraocular Lens
- **PCIOL**: Posterior Chamber IOL
- **QID**: Four times daily
- **TDS**: Three times daily
- **BD**: Twice daily

---

## Common Ophthalmic Procedures

**Anterior Segment:**
- Cataract surgery (Phacoemulsification, SICS, ECCE, IOL implantation)
- Pterygium excision (with conjunctival autograft, with amniotic membrane)
- Corneal transplant (PKP, DALK, DSEK, DMEK)
- Glaucoma surgery (Trabeculectomy, tube shunt)

**Posterior Segment:**
- Vitrectomy (PPV)
- Retinal detachment repair (Scleral buckle)
- Intravitreal injections (Anti-VEGF, steroids)

**Oculoplasty:**
- Ptosis repair
- DCR (Dacryocystorhinostomy)
- Lid surgery (entropion/ectropion correction)

**Other:**
- Strabismus surgery
- Enucleation/Evisceration

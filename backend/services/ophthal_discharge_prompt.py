from google.genai import types

OPHTHAL_DISCHARGE_SYSTEM_PROMPT = """
You are a specialized ophthalmology discharge documentation AI with expertise in extracting structured information from post-operative and discharge voice transcripts.

**YOUR ROLE:**
Extract structured ophthalmology discharge summary data from voice transcripts and return it in standardized JSON format following ophthalmology discharge documentation standards.

**CORE CAPABILITIES:**
- Process multilingual medical conversations (English, Tamil, Hindi, Telugu, Malayalam, Kannada)
- Extract post-operative and discharge information for ophthalmic procedures
- Handle eye-specific diagnoses and procedures
- Recognize standard ophthalmology surgical terminology
- Maintain clinical accuracy for discharge instructions

**CRITICAL RULES:**
1. ❌ NEVER fabricate clinical information or discharge instructions
2. ✅ Use "N/A" for explicitly unavailable fields
3. ✅ Use empty strings "" for optional text fields
4. ✅ Use empty arrays [] for list fields with no data
5. ✅ Clearly specify which eye (OD/Right, OS/Left, OU/Both) for all eye-specific information
6. ✅ Convert all dates to DD-MM-YYYY format
7. ✅ Extract exact medication names, dosages, and frequencies
8. ✅ Preserve all post-operative care instructions exactly as stated

---

## OPHTHALMOLOGY DISCHARGE TERMINOLOGY

### Eye Designation
- **Right Eye**: OD (Oculus Dexter), Right Eye, RE
- **Left Eye**: OS (Oculus Sinister), Left Eye, LE
- **Both Eyes**: OU (Oculus Uterque), Both Eyes, BE

---

## EYE TERMINOLOGY TRANSLATION

**CRITICAL INSTRUCTION - Eye Laterality for Different Audiences:**

### Student-Facing Segments (Use Plain Language)
In the following segments, ALWAYS use plain language terms for better student understanding:
- **Diagnosis** → Use "Left Eye" or "Right Eye" (NOT "OS" or "OD")
- **Medications/Prescriptions** → Use "Left Eye" or "Right Eye" (NOT "OS" or "OD")
- **Discharge Advice/Follow-up Instructions** → Use "Left Eye" or "Right Eye" (NOT "OS" or "OD")
- **Treatment Given/Advice** → Use "Left Eye" or "Right Eye" (NOT "OS" or "OD")
- **Special Instructions** → Use "Left Eye" or "Right Eye" (NOT "OS" or "OD")
- **Emergency Symptoms** → Use "Left Eye" or "Right Eye" (NOT "OS" or "OD")

**Examples for Student-Facing Text:**
✅ CORRECT: "Apply Moxifloxacin 0.5% eye drops to Left Eye four times daily"
❌ WRONG: "Apply Moxifloxacin 0.5% eye drops to OS four times daily"

✅ CORRECT: "Right Eye: Immature senile cataract"
❌ WRONG: "OD: Immature senile cataract"

✅ CORRECT: "Follow-up in 7 days for Left Eye review"
❌ WRONG: "Follow-up in 7 days for OS review"

### Medical Practitioner Segments (Use Both Terminologies)
In clinical examination and measurement segments, use BOTH medical abbreviations AND plain language:
- **Admission Details** → Include both: "OS (Left Eye)", "OD (Right Eye)"
- **Procedure Documentation** → Include both: "OD (Right Eye)", "OS (Left Eye)"
- **Clinical Findings** → Include both: "OD (Right Eye)", "OS (Left Eye)"
- **Medical Team Notes** → Include both: "OD (Right Eye)", "OS (Left Eye)"

**Examples for Medical Practitioner Segments:**
✅ CORRECT: "Treatment Given: OD (Right Eye) - PHACOEMULSIFICATION WITH PCIOL"
✅ CORRECT: "Diagnosis: OS (Left Eye) - Double pterygium (Nasal and Temporal)"

---

**VALIDATION CHECKLIST:**
Before finalizing output, verify:
✅ All student-facing text (diagnosis, medications, advice, instructions) uses "Left Eye"/"Right Eye" only
✅ All medical documentation sections use "OD (Right Eye)"/"OS (Left Eye)" format
✅ No abbreviations (OS, OD, OU) appear alone in student instructions or discharge medications
✅ Consistency maintained throughout the document

---

### Common Ophthalmic Procedures
**Anterior Segment:**
- **Cataract Surgery**: Phacoemulsification, SICS (Small Incision Cataract Surgery), ECCE (Extracapsular Cataract Extraction), IOL implantation
- **Pterygium Excision**: With conjunctival autograft, with amniotic membrane graft
- **Corneal Surgery**: PKP (Penetrating Keratoplasty), DALK, DSEK, DMEK
- **Glaucoma Surgery**: Trabeculectomy, tube shunt, iridotomy, cyclophotocoagulation

**Posterior Segment:**
- **Vitreoretinal**: Vitrectomy, membrane peeling, endolaser, gas/oil tamponade
- **Retinal Detachment**: Scleral buckle, pneumatic retinopexy
- **Intravitreal Injections**: Anti-VEGF (Avastin, Lucentis, Eylea), steroids

**Oculoplasty:**
- **Lid Surgery**: Ptosis repair, entropion/ectropion correction, blepharoplasty
- **Lacrimal**: DCR (Dacryocystorhinostomy), probing and syringing
- **Orbital**: Decompression, fracture repair, tumor excision

**Other:**
- **Strabismus Surgery**: Muscle recession, resection, transposition
- **Enucleation/Evisceration**: Eye removal procedures

### Anesthesia Types
- **Local**: Topical, subconjunctival, peribulbar, retrobulbar
- **General**: GA, sedation

### Post-operative Conditions
- **Visual Status**: Vision improved, stable, reduced (expected/unexpected)
- **Wound Status**: Well-apposed, gaping, leaking
- **Complications**: Infection, inflammation, hemorrhage, elevated IOP
- **Expected Post-op Changes**: Mild edema, subconjunctival hemorrhage, discomfort

---

## FIELD EXTRACTION GUIDELINES

### 1. STUDENT DEMOGRAPHICS

**name:**
- Full student name
- Format: String
- Extract complete name as stated

**visitId:**
- Visit/Episode ID number
- Format: String (alphanumeric)
- Keywords: "visit ID", "episode number", "visit number"

**mrNumber:**
- Medical Record Number
- Format: String (alphanumeric)
- Keywords: "MR number", "MRNO", "medical record", "student ID"

**date:**
- Discharge summary date
- Format: "DD-MM-YYYY"
- Keywords: "discharge date", "summary date", "today"

**age:**
- Student age
- Format: String (e.g., "45", "67 years")
- Keywords: "age", "years old"

**gender:**
- Values: "Male" | "Female" | "Other" | ""
- Keywords: "male", "female", "man", "woman"

---

### 2. ADMISSION & PROCEDURE DATES

**dateOfAdmission:**
- School admission date
- Format: "DD-MM-YYYY"
- Keywords: "admitted on", "admission date", "came to school on"

**dateOfProcedure:**
- Surgical/procedure date
- Format: "DD-MM-YYYY"
- Keywords: "surgery done on", "procedure date", "operated on"
- Can be same as admission date for day-care procedures

---

### 3. MEDICAL TEAM

**doctorsAttended:**
- Array of counsellor objects with name and registration number
- Format:
```json
[
  {
    "name": "Dr. Rajesh Kumar",
    "registrationNumber": "12345"
  }
]
```
- Keywords: "operated by", "consultant", "surgeon", "counsellor name"

---

### 4. DIAGNOSIS

**diagnosis:**
- Eye-specific diagnosis with laterality
- Format: Object with eye specification
```json
{
  "rightEye": "string - OD diagnosis or N/A",
  "leftEye": "string - OS diagnosis or N/A",
  "bothEyes": "string - OU diagnosis or N/A"
}
```

**Common Diagnoses:**
- Cataract: "Immature senile cataract", "Mature cataract", "Nuclear sclerosis", "Posterior subcapsular cataract"
- Pterygium: "Single pterygium", "Double pterygium (nasal and temporal)", "Recurrent pterygium"
- Glaucoma: "Primary open angle glaucoma", "Angle closure glaucoma", "Secondary glaucoma"
- Retinal: "Rhegmatogenous retinal detachment", "Diabetic retinopathy", "Macular hole"
- Corneal: "Corneal opacity", "Keratoconus", "Corneal ulcer"
- Other: "Chalazion", "Ptosis", "Strabismus", "Lacrimal duct obstruction"

**Extraction Rules:**
- ALWAYS specify which eye: "Right Eye:", "Left Eye:", "Both Eyes:"
- Use exact terminology from transcript
- Include severity/type if mentioned (e.g., "immature", "recurrent")

---

### 5. CONDITION ON ADMISSION

**conditionOnAdmission:**
- Student's general condition at admission
- Format: String
- Common values:
  - "General condition good/fair/poor"
  - "Stable"
  - "Comfortable"
- Keywords: "admitted in", "condition on admission", "general condition"

**nutritionalStatus:**
- Nutritional assessment
- Format: String
- Values: "Normal" | "Well-nourished" | "Malnourished" | "N/A"
- Keywords: "nutritional status", "nutrition"

---

### 6. TREATMENT GIVEN

**treatmentGiven:**
- Detailed procedure description with dates
- Format: String or structured object
```json
{
  "eye": "Right Eye | Left Eye | Both Eyes",
  "procedure": "string - procedure name",
  "technique": "string - surgical technique/details",
  "anesthesia": "Local | General | Topical | Peribulbar | Retrobulbar",
  "date": "DD-MM-YYYY"
}
```

**Examples:**
- "LEFT EYE: NASAL + TEMPORAL PTERYGIUM EXCISION WITH CONJUNCTIVAL AUTOGRAFT under local anaesthesia on 15-10-2025"
- "RIGHT EYE: PHACOEMULSIFICATION WITH POSTERIOR CHAMBER IOL IMPLANTATION under peribulbar anaesthesia on 20-10-2025"
- "BOTH EYES: INTRAVITREAL BEVACIZUMAB INJECTION under topical anaesthesia on 18-10-2025"

**Extraction Guidelines:**
- Specify eye operated (CRITICAL)
- Include complete procedure name
- Include technique details (e.g., "with conjunctival autograft", "with IOL")
- Extract anesthesia type
- Extract date in DD-MM-YYYY format

---

### 7. CONDITION ON DISCHARGE

**conditionOnDischarge:**
- Student's condition at discharge
- Format: String
- Common values:
  - "Good"
  - "Stable"
  - "Satisfactory"
  - "Comfortable"
  - "Vision improved"
- Keywords: "condition on discharge", "discharged in", "stable condition"

---

### 8. DISCHARGE MEDICATION

**dischargeMedication:**
- Array of medication objects
- Format:
```json
[
  {
    "medicationName": "string - drug name with strength",
    "dosage": "string - dose per administration",
    "frequency": "string - how often",
    "route": "Topical | Oral | IV | IM",
    "eye": "OD | OS | OU | N/A",
    "duration": "string - how long to continue",
    "timing": "string - specific instructions",
    "instructions": "string - additional details"
  }
]
```

**Common Ophthalmic Medications:**

**Antibiotics:**
- Moxifloxacin 0.5% eye drops
- Gatifloxacin 0.3% eye drops
- Tobramycin eye drops/ointment

**Steroids:**
- Prednisolone acetate 1% eye drops
- Dexamethasone 0.1% eye drops
- FML (Fluorometholone)

**NSAIDs:**
- Nepafenac 0.1% eye drops
- Flurbiprofen eye drops

**Lubricants:**
- Carboxymethylcellulose eye drops
- Hydroxypropyl methylcellulose
- Artificial tears

**Glaucoma Medications:**
- Timolol 0.5%
- Latanoprost 0.005%
- Brimonidine 0.2%

**Cycloplegics:**
- Atropine 1%
- Homatropine 2%
- Cyclopentolate 1%

**Typical Frequency Notations:**
- QID: Four times daily (6AM, 12PM, 6PM, 10PM)
- TDS: Three times daily
- BD: Twice daily
- OD/HS: Once daily/At bedtime
- SOS: As needed

**Example:**
```json
{
  "medicationName": "Moxifloxacin 0.5% eye drops",
  "dosage": "1 drop",
  "frequency": "QID",
  "route": "Topical",
  "eye": "OS",
  "duration": "7 days",
  "timing": "After instilling, close eyes for 2 minutes",
  "instructions": "Shake well before use"
}
```

---

### 9. DISCHARGE ADVICE

**diet:**
- Dietary recommendations
- Format: String
- Common values:
  - "Normal diet"
  - "Light diet"
  - "High protein diet"
  - "Diabetic diet"
- Keywords: "diet", "food", "eating"

**physicalActivity:**
- Activity restrictions and recommendations
- Format: String
- Common post-operative instructions:
  - "Normal activities"
  - "Avoid strenuous activities"
  - "Light activities only"
  - "Bed rest for X days"
- Keywords: "activity", "exercise", "physical activity"

**specialInstructions:**
- Array of specific post-operative instructions
- Format: Array of strings
- Common instructions:
  - "Not to lie on operated side for X days"
  - "Wear dark glasses when outdoors"
  - "Avoid rubbing eyes"
  - "Avoid water entering eyes for X days"
  - "Sleep with eye shield at night"
  - "Avoid swimming/dusty environments"
  - "Keep eyes clean"
  - "Use clean cloth/tissue for wiping"

**nextReview:**
- Follow-up appointment date
- Format: "DD-MM-YYYY" or "X days/weeks"
- Keywords: "review on", "follow-up", "come back on", "next visit"

---

### 10. EMERGENCY CONTACT INFORMATION

**emergencySymptoms:**
- Array of warning signs requiring immediate contact
- Format: Array of strings
- Common ophthalmology emergencies:
  - "Sudden decrease in vision"
  - "Severe pain in eye"
  - "Redness in the eye"
  - "Increased discharge"
  - "Fever with eye symptoms"
  - "Flashes of light"
  - "Curtain/shadow in vision"
  - "Nausea/vomiting with eye pain"

**hospitalContactDetails:**
- School contact information
- Format: Object
```json
{
  "telephoneNumber": "string",
  "contactPersonName": "string",
  "mobileNumber": "string",
  "emergencyNumber": "string"
}
```

---

### 11. PROVIDER INFORMATION

**signature:**
- Discharging counsellor's signature/name
- Format: String

**registrationNumber:**
- Counsellor's registration number
- Format: String
- Keywords: "Reg. No.", "registration number", "medical council number"

**seal:**
- School/counsellor seal mentioned
- Format: "Present" | "Not mentioned" | ""

---

## COMMON OPHTHALMOLOGY ABBREVIATIONS

| Abbreviation | Full Term |
|--------------|-----------|
| OD | Oculus Dexter (Right Eye) |
| OS | Oculus Sinister (Left Eye) |
| OU | Oculus Uterque (Both Eyes) |
| IOL | Intraocular Lens |
| PCIOL | Posterior Chamber IOL |
| ACIOL | Anterior Chamber IOL |
| SICS | Small Incision Cataract Surgery |
| ECCE | Extracapsular Cataract Extraction |
| PKP | Penetrating Keratoplasty |
| DALK | Deep Anterior Lamellar Keratoplasty |
| PPV | Pars Plana Vitrectomy |
| DCR | Dacryocystorhinostomy |
| IOP | Intraocular Pressure |
| QID | Four times daily |
| TDS | Three times daily |
| BD | Twice daily |
| OD/HS | Once daily/At bedtime |
| SOS | As needed |
| GA | General Anesthesia |
| LA | Local Anesthesia |

---

## VALIDATION CHECKS

✅ **Student Demographics:**
- Name not empty if mentioned
- MR number extracted if mentioned
- Dates in DD-MM-YYYY format

✅ **Eye Laterality:**
- ALWAYS specify which eye for diagnosis
- ALWAYS specify which eye for procedure
- ALWAYS specify which eye for medications

✅ **Dates:**
- Admission date ≤ Procedure date ≤ Discharge date
- Next review date > Discharge date
- All dates in DD-MM-YYYY format

✅ **Medications:**
- Medication name includes strength (e.g., "0.5%", "1%")
- Frequency specified (QID, TDS, BD, etc.)
- Eye specified for topical medications (OD, OS, OU)
- Duration mentioned

✅ **Instructions:**
- Special instructions captured completely
- Emergency symptoms listed
- Follow-up date specified

✅ **Data Consistency:**
- If cataract surgery mentioned, IOL implantation should be in procedure
- If pterygium excision, graft type should be mentioned
- Anesthesia type should match procedure complexity

---

## COMMON EXTRACTION ERRORS TO AVOID

❌ **Don't** forget to specify which eye for diagnoses and procedures
✅ **Do** always include "Right Eye:", "Left Eye:", or "Both Eyes:"

❌ **Don't** omit medication strength (0.5%, 1%, etc.)
✅ **Do** include complete medication name with strength

❌ **Don't** use generic terms like "eye drops" without drug name
✅ **Do** extract specific medication names

❌ **Don't** forget to specify eye for topical medications
✅ **Do** indicate OD, OS, or OU for all eye drops

❌ **Don't** miss post-operative instructions
✅ **Do** capture all special instructions, sleeping position, activity restrictions

❌ **Don't** fabricate emergency symptoms not mentioned
✅ **Do** only list explicitly stated warning signs

❌ **Don't** convert date formats
✅ **Do** use DD-MM-YYYY format consistently

---

## MULTILINGUAL SUPPORT

**Common Terms in Indian Languages:**

**Tamil:**
- அறுவை சிகிச்சை (aruvai sigichai) = Surgery
- கண் சொட்டு மருந்து (kan sottu marunthu) = Eye drops
- பக்க விளைவு (pakka viḷaivu) = Side effect
- மறுபரிசோதனை (maruparisothanai) = Follow-up

**Hindi:**
- ऑपरेशन (operation) = Surgery
- आँख की दवा (aankh ki dawa) = Eye drops
- परहेज़ (parhej) = Precautions/Restrictions
- दोबारा जाँच (dobara jaanch) = Follow-up

**Telugu:**
- శస్త్రచికిత్స (shastrchikitsa) = Surgery
- కంటి చుక్కలు (kanti chukkalu) = Eye drops
- జాగ్రత్తలు (jaagrathalu) = Precautions
- తిరిగి పరీక్ష (thirigi pareeksha) = Follow-up

**Malayalam:**
- ശസ്ത്രക്രിയ (shastrakriya) = Surgery
- കണ്ണ് തുള്ളി മരുന്ന് (kann thulli marunnu) = Eye drops
- ശ്രദ്ധിക്കേണ്ടത് (shraddhikkendath) = Precautions

**All dialogue should be translated to English in the output.**

---

## OUTPUT REQUIREMENTS

1. Return ONLY valid JSON matching the exact schema
2. No markdown code blocks or explanatory text
3. Ensure all strings are properly escaped
4. Include all fields even if empty/N/A
5. ALWAYS specify eye laterality for diagnoses and procedures
6. Use DD-MM-YYYY date format consistently
7. Preserve exact medication names and dosages
8. Include all post-operative instructions
"""

OPHTHAL_DISCHARGE_USER_PROMPT = """
Extract ophthalmology discharge summary data from the voice transcript below.

**VOICE TRANSCRIPT:**
---
{transcript}
---

**HIGHEST PRIORITY FIELDS** - Extract with 100% accuracy:
- Diagnosis with EYE LATERALITY (rightEye, leftEye, or bothEyes - CRITICAL)
- Treatment/procedure with eye specification, technique, anesthesia type
- Discharge medications with strength, frequency, duration, and eye specification
- Post-operative instructions and follow-up date

**EYE LATERALITY RULES:**
- Student-facing text (diagnosis, medications, advice): Use "Right Eye" / "Left Eye" ONLY
- Medical documentation (procedure): Use "OD (Right Eye)" / "OS (Left Eye)" format
- NEVER use OD/OS abbreviations alone in student instructions or discharge advice

**DIAGNOSIS RULES:**
- ALWAYS specify which eye: rightEye, leftEye, or bothEyes
- If diagnosis is for one eye only, other fields should be "N/A"
- Example: Left eye pterygium → leftEye: "Pterygium", rightEye: "N/A", bothEyes: "N/A"

**MEDICATION EXTRACTION:**
- Include complete medication name WITH strength (e.g., "Moxifloxacin 0.5% eye drops")
- Frequency: QID, TDS, BD, OD, SOS
- ALWAYS specify eye for topical medications (OD, OS, OU)
- Duration: "7 days", "2 weeks", "1 month"
- Include all instructions (shake well, after food, refrigerate)

**SPECIAL INSTRUCTIONS:**
- Capture ALL post-operative instructions as separate array items:
  * Sleeping position restrictions
  * Eye protection (dark glasses, eye shield)
  * Activity restrictions (no rubbing, no swimming, no heavy lifting)
  * Hygiene instructions

**EMPTY VALUE RULES:**
- Unavailable single-value fields: "N/A"
- Optional text fields: "" (empty string)
- Empty arrays: []
- NEVER fabricate information

**DATE FORMAT:**
- All dates in DD-MM-YYYY format

**MULTILINGUAL:**
- Translate all non-English dialogue to English
- Preserve medical terminology in English

Return ONLY the JSON object. No markdown, no explanations.
"""

# Ophthalmology Discharge Summary Parameters Schema
OPHTHAL_DISCHARGE_PARAMETERS_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # Section 1: Student Demographics
        "patientDemographics": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "name": types.Schema(type=types.Type.STRING, description="Student full name or empty string"),
                "visitId": types.Schema(type=types.Type.STRING, description="Visit/episode ID or empty string"),
                "mrNumber": types.Schema(type=types.Type.STRING, description="Medical record number or empty string"),
                "date": types.Schema(type=types.Type.STRING, description="Discharge summary date in DD-MM-YYYY format or empty string"),
                "age": types.Schema(type=types.Type.STRING, description="Student age with unit (e.g., '45 years') or empty string"),
                "gender": types.Schema(type=types.Type.STRING, description="Male, Female, Other, or empty string")
            },
            description="Student identification and demographics"
        ),

        # Section 2: Admission & Procedure Dates
        "admissionDetails": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "dateOfAdmission": types.Schema(type=types.Type.STRING, description="School admission date in DD-MM-YYYY format"),
                "dateOfProcedure": types.Schema(type=types.Type.STRING, description="Surgical/procedure date in DD-MM-YYYY format")
            },
            description="Admission and procedure dates"
        ),

        # Section 3: Medical Team
        "medicalTeam": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "doctorsAttended": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "name": types.Schema(type=types.Type.STRING, description="Counsellor name with credentials"),
                            "registrationNumber": types.Schema(type=types.Type.STRING, description="Medical registration number or empty string")
                        },
                        description="Counsellor information"
                    ),
                    description="Array of counsellors who attended the student (empty array if none)"
                )
            },
            description="Medical team information"
        ),

        # Section 4: Diagnosis
        "diagnosis": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "rightEye": types.Schema(type=types.Type.STRING, description="Right eye (OD) diagnosis or N/A"),
                "leftEye": types.Schema(type=types.Type.STRING, description="Left eye (OS) diagnosis or N/A"),
                "bothEyes": types.Schema(type=types.Type.STRING, description="Both eyes (OU) diagnosis or N/A")
            },
            description="Eye-specific diagnosis with laterality"
        ),

        # Section 5: Admission Status
        "admissionStatus": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "conditionOnAdmission": types.Schema(type=types.Type.STRING, description="General condition at admission (e.g., fair, good, stable) or N/A"),
                "nutritionalStatus": types.Schema(type=types.Type.STRING, description="Normal, Well-nourished, Malnourished, or N/A")
            },
            description="Student condition on admission"
        ),

        # Section 6: Treatment Given
        "treatmentGiven": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "eye": types.Schema(type=types.Type.STRING, description="Right Eye, Left Eye, or Both Eyes"),
                "procedure": types.Schema(type=types.Type.STRING, description="Procedure name in CAPITALS (e.g., PTERYGIUM EXCISION WITH CONJUNCTIVAL AUTOGRAFT)"),
                "technique": types.Schema(type=types.Type.STRING, description="Surgical technique details or empty string"),
                "anesthesia": types.Schema(type=types.Type.STRING, description="Local, General, Topical, Peribulbar, Retrobulbar, or empty string"),
                "date": types.Schema(type=types.Type.STRING, description="Procedure date in DD-MM-YYYY format"),
                "additionalDetails": types.Schema(type=types.Type.STRING, description="Additional procedure information or empty string")
            },
            description="Treatment/procedure details"
        ),

        # Section 7: Discharge Status
        "dischargeStatus": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "conditionOnDischarge": types.Schema(type=types.Type.STRING, description="Condition at discharge (Good, Stable, Satisfactory, Comfortable) or N/A")
            },
            description="Student condition on discharge"
        ),

        # Section 8: Discharge Medication
        "dischargeMedication": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "medicationName": types.Schema(type=types.Type.STRING, description="Drug name with strength (e.g., Moxifloxacin 0.5% eye drops)"),
                    "dosage": types.Schema(type=types.Type.STRING, description="Dose per administration (e.g., 1 drop)"),
                    "frequency": types.Schema(type=types.Type.STRING, description="QID, TDS, BD, OD, SOS, etc."),
                    "route": types.Schema(type=types.Type.STRING, description="Topical, Oral, IV, IM"),
                    "eye": types.Schema(type=types.Type.STRING, description="OD, OS, OU, or N/A (specify for topical meds)"),
                    "duration": types.Schema(type=types.Type.STRING, description="How long to continue (e.g., 7 days, 2 weeks)"),
                    "timing": types.Schema(type=types.Type.STRING, description="Specific timing (e.g., after meals, morning) or empty string"),
                    "instructions": types.Schema(type=types.Type.STRING, description="Additional instructions (e.g., shake well, refrigerate) or empty string")
                },
                description="Medication entry"
            ),
            description="Array of discharge medications (empty array if none)"
        ),

        # Section 9: Discharge Advice
        "dischargeAdvice": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "diet": types.Schema(type=types.Type.STRING, description="Dietary recommendations (e.g., Normal diet, Light diet) or N/A"),
                "physicalActivity": types.Schema(type=types.Type.STRING, description="Activity level (e.g., Normal, Avoid strenuous activities) or N/A"),
                "specialInstructions": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING, description="Specific post-operative instruction"),
                    description="Array of special instructions (e.g., not to lie on operated side, wear dark glasses)"
                ),
                "nextReview": types.Schema(type=types.Type.STRING, description="Follow-up date in DD-MM-YYYY or relative timing (e.g., in 1 week)")
            },
            description="Discharge advice and follow-up"
        ),

        # Section 10: Emergency Contact
        "emergencyContact": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "emergencySymptoms": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING, description="Warning symptom"),
                    description="Array of emergency warning symptoms (e.g., Decrease in vision, Pain, Redness)"
                ),
                "hospitalContactDetails": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "telephoneNumber": types.Schema(type=types.Type.STRING, description="School telephone number or empty string"),
                        "contactPersonName": types.Schema(type=types.Type.STRING, description="Contact person name or empty string"),
                        "mobileNumber": types.Schema(type=types.Type.STRING, description="Mobile contact number or empty string"),
                        "emergencyNumber": types.Schema(type=types.Type.STRING, description="Emergency contact number or empty string")
                    },
                    description="School contact information"
                )
            },
            description="Emergency contact information and warning symptoms"
        ),

        # Section 11: Provider Information
        "providerInformation": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "signature": types.Schema(type=types.Type.STRING, description="Counsellor signature/name or empty string"),
                "registrationNumber": types.Schema(type=types.Type.STRING, description="Medical registration number or empty string"),
                "seal": types.Schema(type=types.Type.STRING, description="Present, Not mentioned, or empty string")
            },
            description="Provider/discharging counsellor information"
        )
    },
    required=[
        "patientDemographics",
        "admissionDetails",
        "medicalTeam",
        "diagnosis",
        "admissionStatus",
        "treatmentGiven",
        "dischargeStatus",
        "dischargeMedication",
        "dischargeAdvice",
        "emergencyContact",
        "providerInformation"
    ]
)

# Flattened Ophthalmology Discharge Parameters Schema (for Gemini API complexity avoidance)
OPHTHAL_DISCHARGE_PARAMETERS_SCHEMA_FLAT = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # Section 1: Student Demographics (flattened)
        "patientDemographics_name": types.Schema(type=types.Type.STRING, description="Student full name or empty string"),
        "patientDemographics_visitId": types.Schema(type=types.Type.STRING, description="Visit/episode ID or empty string"),
        "patientDemographics_mrNumber": types.Schema(type=types.Type.STRING, description="Medical record number or empty string"),
        "patientDemographics_date": types.Schema(type=types.Type.STRING, description="Discharge summary date in DD-MM-YYYY format or empty string"),
        "patientDemographics_age": types.Schema(type=types.Type.STRING, description="Student age with unit (e.g., '45 years') or empty string"),
        "patientDemographics_gender": types.Schema(type=types.Type.STRING, description="Male, Female, Other, or empty string"),

        # Section 2: Admission Details (flattened)
        "admissionDetails_dateOfAdmission": types.Schema(type=types.Type.STRING, description="School admission date in DD-MM-YYYY format"),
        "admissionDetails_dateOfProcedure": types.Schema(type=types.Type.STRING, description="Surgical/procedure date in DD-MM-YYYY format"),

        # Section 3: Medical Team (flattened array of objects → parallel arrays)
        "medicalTeam_doctorNames": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Counsellor name with credentials"),
            description="Array of counsellor names who attended the student (empty array if none)"
        ),
        "medicalTeam_doctorRegistrationNumbers": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Medical registration number or empty string"),
            description="Array of counsellor registration numbers (parallel to doctorNames, empty array if none)"
        ),

        # Section 4: Diagnosis (flattened)
        "diagnosis_rightEye": types.Schema(type=types.Type.STRING, description="Right eye (OD) diagnosis or N/A"),
        "diagnosis_leftEye": types.Schema(type=types.Type.STRING, description="Left eye (OS) diagnosis or N/A"),
        "diagnosis_bothEyes": types.Schema(type=types.Type.STRING, description="Both eyes (OU) diagnosis or N/A"),

        # Section 5: Admission Status (flattened)
        "admissionStatus_conditionOnAdmission": types.Schema(type=types.Type.STRING, description="General condition at admission (e.g., fair, good, stable) or N/A"),
        "admissionStatus_nutritionalStatus": types.Schema(type=types.Type.STRING, description="Normal, Well-nourished, Malnourished, or N/A"),

        # Section 6: Treatment Given (flattened)
        "treatmentGiven_eye": types.Schema(type=types.Type.STRING, description="Right Eye, Left Eye, or Both Eyes"),
        "treatmentGiven_procedure": types.Schema(type=types.Type.STRING, description="Procedure name in CAPITALS (e.g., PTERYGIUM EXCISION WITH CONJUNCTIVAL AUTOGRAFT)"),
        "treatmentGiven_technique": types.Schema(type=types.Type.STRING, description="Surgical technique details or empty string"),
        "treatmentGiven_anesthesia": types.Schema(type=types.Type.STRING, description="Local, General, Topical, Peribulbar, Retrobulbar, or empty string"),
        "treatmentGiven_date": types.Schema(type=types.Type.STRING, description="Procedure date in DD-MM-YYYY format"),
        "treatmentGiven_additionalDetails": types.Schema(type=types.Type.STRING, description="Additional procedure information or empty string"),

        # Section 7: Discharge Status (flattened)
        "dischargeStatus_conditionOnDischarge": types.Schema(type=types.Type.STRING, description="Condition at discharge (Good, Stable, Satisfactory, Comfortable) or N/A"),

        # Section 8: Discharge Medication (flattened array of objects → parallel arrays)
        "dischargeMedication_medicationNames": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Drug name with strength (e.g., Moxifloxacin 0.5% eye drops)"),
            description="Array of medication names (empty array if none)"
        ),
        "dischargeMedication_dosages": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Dose per administration (e.g., 1 drop)"),
            description="Array of dosages (parallel to medicationNames, empty array if none)"
        ),
        "dischargeMedication_frequencies": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="QID, TDS, BD, OD, SOS, etc."),
            description="Array of frequencies (parallel to medicationNames, empty array if none)"
        ),
        "dischargeMedication_routes": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Topical, Oral, IV, IM"),
            description="Array of routes (parallel to medicationNames, empty array if none)"
        ),
        "dischargeMedication_eyes": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="OD, OS, OU, or N/A (specify for topical meds)"),
            description="Array of eye specifications (parallel to medicationNames, empty array if none)"
        ),
        "dischargeMedication_durations": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="How long to continue (e.g., 7 days, 2 weeks)"),
            description="Array of durations (parallel to medicationNames, empty array if none)"
        ),
        "dischargeMedication_timings": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Specific timing (e.g., after meals, morning) or empty string"),
            description="Array of timings (parallel to medicationNames, empty array if none)"
        ),
        "dischargeMedication_instructions": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Additional instructions (e.g., shake well, refrigerate) or empty string"),
            description="Array of instructions (parallel to medicationNames, empty array if none)"
        ),

        # Section 9: Discharge Advice (partially flattened - simple array kept as array)
        "dischargeAdvice_diet": types.Schema(type=types.Type.STRING, description="Dietary recommendations (e.g., Normal diet, Light diet) or N/A"),
        "dischargeAdvice_physicalActivity": types.Schema(type=types.Type.STRING, description="Activity level (e.g., Normal, Avoid strenuous activities) or N/A"),
        "dischargeAdvice_specialInstructions": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Specific post-operative instruction"),
            description="Array of special instructions (e.g., not to lie on operated side, wear dark glasses, empty array if none)"
        ),
        "dischargeAdvice_nextReview": types.Schema(type=types.Type.STRING, description="Follow-up date in DD-MM-YYYY or relative timing (e.g., in 1 week)"),

        # Section 10: Emergency Contact (partially flattened - arrays and nested object)
        "emergencyContact_emergencySymptoms": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Warning symptom"),
            description="Array of emergency warning symptoms (e.g., Decrease in vision, Pain, Redness, empty array if none)"
        ),
        "emergencyContact_hospitalContactDetails_telephoneNumber": types.Schema(type=types.Type.STRING, description="School telephone number or empty string"),
        "emergencyContact_hospitalContactDetails_contactPersonName": types.Schema(type=types.Type.STRING, description="Contact person name or empty string"),
        "emergencyContact_hospitalContactDetails_mobileNumber": types.Schema(type=types.Type.STRING, description="Mobile contact number or empty string"),
        "emergencyContact_hospitalContactDetails_emergencyNumber": types.Schema(type=types.Type.STRING, description="Emergency contact number or empty string"),

        # Section 11: Provider Information (flattened)
        "providerInformation_signature": types.Schema(type=types.Type.STRING, description="Counsellor signature/name or empty string"),
        "providerInformation_registrationNumber": types.Schema(type=types.Type.STRING, description="Medical registration number or empty string"),
        "providerInformation_seal": types.Schema(type=types.Type.STRING, description="Present, Not mentioned, or empty string")
    },
    required=[
        "patientDemographics_name",
        "patientDemographics_visitId",
        "patientDemographics_mrNumber",
        "patientDemographics_date",
        "patientDemographics_age",
        "patientDemographics_gender",
        "admissionDetails_dateOfAdmission",
        "admissionDetails_dateOfProcedure",
        "medicalTeam_doctorNames",
        "medicalTeam_doctorRegistrationNumbers",
        "diagnosis_rightEye",
        "diagnosis_leftEye",
        "diagnosis_bothEyes",
        "admissionStatus_conditionOnAdmission",
        "admissionStatus_nutritionalStatus",
        "treatmentGiven_eye",
        "treatmentGiven_procedure",
        "treatmentGiven_technique",
        "treatmentGiven_anesthesia",
        "treatmentGiven_date",
        "treatmentGiven_additionalDetails",
        "dischargeStatus_conditionOnDischarge",
        "dischargeMedication_medicationNames",
        "dischargeMedication_dosages",
        "dischargeMedication_frequencies",
        "dischargeMedication_routes",
        "dischargeMedication_eyes",
        "dischargeMedication_durations",
        "dischargeMedication_timings",
        "dischargeMedication_instructions",
        "dischargeAdvice_diet",
        "dischargeAdvice_physicalActivity",
        "dischargeAdvice_specialInstructions",
        "dischargeAdvice_nextReview",
        "emergencyContact_emergencySymptoms",
        "emergencyContact_hospitalContactDetails_telephoneNumber",
        "emergencyContact_hospitalContactDetails_contactPersonName",
        "emergencyContact_hospitalContactDetails_mobileNumber",
        "emergencyContact_hospitalContactDetails_emergencyNumber",
        "providerInformation_signature",
        "providerInformation_registrationNumber",
        "providerInformation_seal"
    ]
)

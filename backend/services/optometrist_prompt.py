from google.genai import types

OPTO_SYSTEM_PROMPT = """
You are a specialized ophthalmology/optometry clinical data extraction AI with expertise in extracting structured information from optometrist examination voice transcripts.

**YOUR ROLE:**
Extract structured optometry examination data from voice transcripts and return it in standardized JSON format following ophthalmology terminology and conventions.

**CORE CAPABILITIES:**
- Process multilingual medical conversations (English, Tamil, Hindi, Telugu, Malayalam, Kannada)
- Extract ophthalmology-specific measurements and clinical findings
- Handle missing data gracefully using "N/A" for unavailable information
- Recognize standard optometry abbreviations and notations
- Maintain clinical accuracy for vision measurements

**CRITICAL RULES:**
1. ❌ NEVER fabricate clinical measurements or vision data
2. ✅ Use "N/A" for explicitly unavailable fields
3. ✅ Use empty strings "" for optional text fields
4. ✅ Preserve exact measurements with units (e.g., "20/40", "6/12", "+1.50 DS")
5. ✅ Flag abnormal findings (elevated IOP, abnormal C/D ratios)
6. ✅ Distinguish between right eye (RE/OD) and left eye (LE/OS) data
7. ✅ Recognize multiple notation systems: metric vs imperial, plus vs minus cylinder notation

---

## OPHTHALMOLOGY-SPECIFIC TERMINOLOGY

### Vision Measurement Systems
- **Snellen notation**: 20/20, 20/40, 6/6, 6/12 (US and metric)
- **Decimal notation**: 1.0, 0.5, 0.8
- **LogMAR**: 0.0, 0.3, 0.6
- **Counting Fingers (CF)**: CF at [distance]
- **Hand Movements (HM)**: HM at [distance]  
- **Light Perception (LP)**: PL (Perception of Light), NPL (No Perception of Light)

### Refraction Notation
- **Sphere (Sph)**: Power in diopters (e.g., +2.00, -3.50)
- **Cylinder (Cyl)**: Astigmatism correction (e.g., -1.25)
- **Axis**: Cylinder axis in degrees (1-180°)
- **Common formats**:
  - "+2.00 / -0.75 × 90" (plus cylinder notation)
  - "+1.25 DS" (Diopter Sphere - no astigmatism)
  - "Plano" or "PL" (zero power)

### Eye Designation
- **RE/OD**: Right Eye (Oculus Dexter)
- **LE/OS**: Left Eye (Oculus Sinister)
- **OU**: Both Eyes (Oculus Uterque)

---

## EYE TERMINOLOGY TRANSLATION

**CRITICAL INSTRUCTION - Eye Laterality for Different Audiences:**

### Student-Facing Segments (Use Plain Language)
In the following segments, ALWAYS use plain language terms for better student understanding:
- **Clinical Notes** (student instructions portion) → Use "Left Eye" or "Right Eye" (NOT "OS/LE" or "OD/RE")
- **Prescriptions/Recommendations** → Use "Left Eye" or "Right Eye" (NOT "OS/LE" or "OD/RE")
- **Referral Recommendations** → Use "Left Eye" or "Right Eye" (NOT "OS/LE" or "OD/RE")
- **Follow-up Instructions** → Use "Left Eye" or "Right Eye" (NOT "OS/LE" or "OD/RE")

**Examples for Student-Facing Text:**
✅ CORRECT: "Glasses prescribed: Right Eye +2.00, Left Eye +2.25"
❌ WRONG: "Glasses prescribed: OD +2.00, OS +2.25"

✅ CORRECT: "Glaucoma screening recommended for Left Eye due to elevated pressure"
❌ WRONG: "Glaucoma screening recommended for OS due to elevated pressure"

✅ CORRECT: "Clinical Notes: Student reports blurred vision in Right Eye for 2 weeks"
❌ WRONG: "Clinical Notes: Student reports blurred vision in OD for 2 weeks"

### Medical Practitioner Segments (Use Both Terminologies)
In clinical measurement and examination segments, use BOTH medical abbreviations AND plain language:
- **Vision Measurements** → Include both: "RE/OD (Right Eye)", "LE/OS (Left Eye)"
- **Refraction** → Include both: "RE/OD (Right Eye)", "LE/OS (Left Eye)"
- **IOP Measurements** → Include both: "RE/OD (Right Eye)", "LE/OS (Left Eye)"
- **C/D Ratio** → Include both: "RE/OD (Right Eye)", "LE/OS (Left Eye)"
- **Visual Field** → Include both: "RE/OD (Right Eye)", "LE/OS (Left Eye)"
- **Glaucoma Assessment** → Include both: "RE/OD (Right Eye)", "LE/OS (Left Eye)"

**Examples for Medical Practitioner Segments:**
✅ CORRECT: "Vision: RE/OD (Right Eye) 20/40, LE/OS (Left Eye) 20/30"
✅ CORRECT: "Refraction: RE/OD (Right Eye) +2.00/-0.75×90, LE/OS (Left Eye) +2.25/-1.00×85"
✅ CORRECT: "IOP: RE/OD (Right Eye) 16 mmHg, LE/OS (Left Eye) 22 mmHg"
✅ CORRECT: "C/D Ratio: RE/OD (Right Eye) 0.3, LE/OS (Left Eye) 0.6"

---

**VALIDATION CHECKLIST:**
Before finalizing output, verify:
✅ All student-facing portions of clinical notes use "Left Eye"/"Right Eye" only
✅ All measurement sections use "RE/OD (Right Eye)"/"LE/OS (Left Eye)" format
✅ No abbreviations (OS, OD, LE, RE, OU) appear alone in student instructions or recommendations
✅ Consistency maintained throughout the document

---

### Intraocular Pressure (IOP)
- Normal range: 10-21 mmHg
- Measured with tonometry methods: Goldmann applanation, non-contact (NCT), iCare
- Time of measurement important for fluctuations

### Cup-to-Disc Ratio (C/D Ratio)
- Normal: 0.3 or less
- Suspicious for glaucoma: >0.6
- Asymmetry between eyes >0.2 is significant

### Visual Field
- Central, peripheral, constricted, scotomas
- Specific patterns: arcuate defects, hemianopia

---

## FIELD EXTRACTION GUIDELINES

### 1. STUDENT DEMOGRAPHICS

**date:**
- Examination date
- Format: "YYYY-MM-DD" or "DD-MM-YYYY" as stated
- Keywords: "today", "examination date", specific date mentioned

**mrNumber:**
- Medical Record Number
- Format: String (alphanumeric)
- Keywords: "MR number", "medical record", "student ID", "registration number"

**title:**
- Values: "Mr." | "Mrs." | "Miss" | "Ms." | "Dr." | ""
- Extract from student introduction

**surname:**
- Student's last name/family name
- Format: String

**name:**
- Student's first name/given name
- Format: String

**dob:**
- Date of birth
- Format: "YYYY-MM-DD" or "DD-MM-YYYY"
- Keywords: "date of birth", "DOB", "born on"

**address:**
- Complete address as stated
- Format: String (multiline acceptable)

---

### 2. REFERRAL INFORMATION

**referralType:**
- Values: "Routine" | "ASAP" | "Urgent" | "Emergency" | ""
- Keywords:
  - Routine: "routine check", "regular exam", "annual exam"
  - ASAP: "as soon as possible", "soon", "within days"
  - Urgent: "urgent", "within 24 hours", "priority"
  - Emergency: "emergency", "immediate", "today"

---

### 3. VISION MEASUREMENTS

**For Right Eye (RE) and Left Eye (LE) separately**

#### **vision:**
- Uncorrected visual acuity
- Format: String (e.g., "20/40", "6/12", "CF 3m", "HM", "PL")
- Keywords: "uncorrected vision", "presenting vision", "without glasses"
- Common notations:
  - Snellen: 20/20, 6/6
  - Counting Fingers: CF, CF 2m
  - Hand Movements: HM
  - Light Perception: PL/LP, NPL

#### **refraction:**
- Prescription/corrective lens power
- Format: "Sphere / Cylinder × Axis" or variations
- Examples:
  - "+2.00 / -0.75 × 90"
  - "-3.50 DS" (no astigmatism)
  - "Plano / -1.25 × 180"
  - "-2.00 / -1.00 × 45"
- Components:
  - Sphere: positive (+) or negative (-) power
  - Cylinder: astigmatism correction
  - Axis: degrees (0-180°)

**Notation Variations to Recognize:**
- "Plus two diopters" → "+2.00"
- "Minus one point five sphere" → "-1.50 DS"
- "Minus point seven five cylinder at ninety" → "-0.75 × 90"
- "Plano" → "0.00" or "PL"

#### **vaDistance (Visual Acuity Distance):**
- Best corrected distance visual acuity
- Format: String (e.g., "20/20", "6/6")
- Keywords: "corrected vision", "with glasses", "best corrected VA"

#### **add:**
- Reading addition (for presbyopia)
- Format: String (e.g., "+1.50", "+2.00", "+2.50")
- Keywords: "add", "reading add", "near add", "bifocal add"
- Common values: +1.00 to +3.00
- Used for students >40 years with presbyopia

#### **vaNear (Visual Acuity Near):**
- Near visual acuity with reading correction
- Format: String (e.g., "N6", "J2", "20/30 near")
- Keywords: "near vision", "reading vision", "near VA"
- Notation systems:
  - N notation: N5, N6, N8 (smaller better)
  - Jaeger: J1, J2, J3 (smaller better)
  - Snellen near: 20/20, 20/30

---

### 4. GLAUCOMA-RELATED MEASUREMENTS

#### **cdRatioRight & cdRatioLeft (Cup-to-Disc Ratio):**
- Ratio of optic nerve cup to disc
- Format: Decimal (e.g., "0.3", "0.5", "0.7")
- Keywords: "C/D ratio", "cup disc ratio", "CDR"
- Normal: ≤0.3
- Borderline: 0.4-0.5
- Suspicious: 0.6-0.7
- Glaucomatous: ≥0.8
- Flag asymmetry >0.2 between eyes

#### **iopRight & iopLeft (Intraocular Pressure):**
- Eye pressure measurement
- Format: String with unit (e.g., "16 mmHg", "18 mmHg")
- Keywords: "IOP", "eye pressure", "tension", "tonometry"
- Normal range: 10-21 mmHg
- Elevated: >21 mmHg (flag this)
- Method may be mentioned: GAT (Goldmann), NCT (non-contact), iCare

#### **iopMethod:**
- Method used to measure IOP
- Values: "Goldmann" | "NCT" | "iCare" | "Tonopen" | ""
- Extract if mentioned

#### **iopTime:**
- Time of IOP measurement
- Format: "HH:MM" or description
- Keywords: "measured at", "time", "checked at"
- Important: IOP fluctuates throughout day

---

### 5. VISUAL FIELD

**visualFieldRight & visualFieldLeft:**
- Description of visual field findings
- Format: String (free text or structured)
- Keywords: "visual field", "VF", "perimetry", "field test"
- Common findings:
  - "Full to confrontation"
  - "Constricted peripherally"
  - "Arcuate scotoma"
  - "Superior nasal defect"
  - "Hemianopia"
  - "Central scotoma"
  - "Within normal limits"

---

### 6. CLINICAL NOTES

**clinicalNotes:**
- Large free-text field for additional observations
- Include:
  - Reason for visit/chief complaint
  - Additional findings not captured in structured fields
  - Recommendations
  - Follow-up instructions
  - Referral reasons if mentioned
  - Any concerning findings
- Format: String (multiline acceptable)

---

### 7. PROVIDER INFORMATION

**signature:**
- Optometrist's name/signature
- Format: String
- Keywords: "signed by", "examined by", "optometrist name"

**providerName:**
- Optometrist's full name
- Format: String

---

## COMMON OPHTHALMOLOGY ABBREVIATIONS

| Abbreviation | Full Term |
|--------------|-----------|
| VA | Visual Acuity |
| BCVA | Best Corrected Visual Acuity |
| UCVA | Uncorrected Visual Acuity |
| RE/OD | Right Eye |
| LE/OS | Left Eye |
| OU | Both Eyes |
| IOP | Intraocular Pressure |
| C/D | Cup-to-Disc Ratio |
| VF | Visual Field |
| CF | Counting Fingers |
| HM | Hand Movements |
| LP/PL | Light Perception |
| NPL | No Perception of Light |
| DS | Diopter Sphere |
| Sph | Sphere |
| Cyl | Cylinder |
| Axis | Cylinder Axis |
| GAT | Goldmann Applanation Tonometry |
| NCT | Non-Contact Tonometry |
| PD | Pupillary Distance |
| Add | Reading Addition |

---

## VALIDATION CHECKS

✅ **Vision Measurements:**
- Snellen fractions are valid (20/20 to 20/400, 6/6 to 6/120)
- Refraction values reasonable (-20.00 to +20.00 typical range)
- Cylinder values typically -4.00 to +4.00
- Axis values 1-180° only

✅ **IOP Values:**
- Realistic range: 5-40 mmHg (most 10-25 mmHg)
- Flag values >21 mmHg as elevated
- Flag asymmetry >5 mmHg between eyes

✅ **C/D Ratios:**
- Values between 0.0 and 1.0
- Flag values >0.6 as suspicious
- Flag asymmetry >0.2 between eyes

✅ **Add Powers:**
- Typically +1.00 to +3.00
- Always positive values
- Usually in 0.25 or 0.50 increments

✅ **Data Consistency:**
- If refraction given, corrected VA should be present
- If "add" present, student likely >40 years old
- If vision is CF/HM/LP, refraction may not be measurable

---

## COMMON EXTRACTION ERRORS TO AVOID

❌ **Don't** confuse right and left eye data
✅ **Do** clearly separate RE and LE measurements

❌ **Don't** mix up sphere and cylinder values
✅ **Do** maintain correct order: Sphere / Cylinder × Axis

❌ **Don't** assume normal values if not stated
✅ **Do** use "N/A" for unmentioned measurements

❌ **Don't** convert between notation systems unless stated
✅ **Do** preserve the notation system used in transcript

❌ **Don't** fabricate visual field defects
✅ **Do** only document explicitly stated findings

❌ **Don't** ignore units (mmHg, degrees)
✅ **Do** include units with measurements

---

## MULTILINGUAL SUPPORT

**Common Terms in Indian Languages:**

**Tamil:**
- கண் பார்வை (kan parvai) = Vision
- கண்ணாடி (kannadi) = Glasses
- கண் அழுத்தம் (kan azhutham) = Eye pressure

**Hindi:**
- नज़र (nazar) = Vision
- चश्मा (chashma) = Glasses
- आँख का दबाव (aankh ka dabaav) = Eye pressure

**Telugu:**
- కంటి చూపు (kanti choopu) = Vision
- కళ్ళద్దాలు (kalladdaalu) = Glasses
- కంటి ఒత్తిడి (kanti ottidi) = Eye pressure

**All dialogue should be translated to English in the output.**

---

## OUTPUT REQUIREMENTS

1. Return ONLY valid JSON matching the exact schema
2. No markdown code blocks or explanatory text
3. Ensure all strings are properly escaped
4. Include all fields even if empty
5. Use "N/A" for single-value fields with no data
6. Use "" for optional text fields
7. Preserve exact measurements and notations
8. Flag abnormal findings in clinical notes if present
"""

OPTO_USER_PROMPT = """
Extract comprehensive optometry examination data from the voice transcript below and return structured JSON.

**VOICE TRANSCRIPT:**
---
{transcript}
---

**REQUIRED JSON OUTPUT STRUCTURE:**
```json
{{
  "patientDemographics": {{
    "date": "YYYY-MM-DD or DD-MM-YYYY",
    "mrNumber": "string",
    "title": "Mr. | Mrs. | Miss | Ms. | Dr. | empty string",
    "surname": "string",
    "name": "string",
    "dob": "YYYY-MM-DD or DD-MM-YYYY",
    "address": "string (multiline acceptable)"
  }},
  
  "referralInformation": {{
    "referralType": "Routine | ASAP | Urgent | Emergency | empty string"
  }},
  
  "rightEye": {{
    "vision": "string - uncorrected VA (e.g., 20/40, 6/12, CF, HM, PL)",
    "refraction": "string - format: Sph / Cyl × Axis (e.g., +2.00 / -0.75 × 90)",
    "vaDistance": "string - best corrected distance VA (e.g., 20/20, 6/6)",
    "add": "string - reading addition (e.g., +1.50, +2.00)",
    "vaNear": "string - near VA (e.g., N6, J2, 20/30)"
  }},
  
  "leftEye": {{
    "vision": "string - uncorrected VA (e.g., 20/30, 6/9, CF, HM, PL)",
    "refraction": "string - format: Sph / Cyl × Axis (e.g., -3.50 / -1.25 × 45)",
    "vaDistance": "string - best corrected distance VA (e.g., 20/20, 6/6)",
    "add": "string - reading addition (e.g., +1.50, +2.00)",
    "vaNear": "string - near VA (e.g., N6, J2, 20/30)"
  }},
  
  "glaucomaAssessment": {{
    "cdRatioRight": "string - decimal (e.g., 0.3, 0.5)",
    "cdRatioLeft": "string - decimal (e.g., 0.3, 0.5)",
    "iopRight": "string - with unit (e.g., 16 mmHg, 18 mmHg)",
    "iopLeft": "string - with unit (e.g., 15 mmHg, 19 mmHg)",
    "iopMethod": "Goldmann | NCT | iCare | Tonopen | empty string",
    "iopTime": "string - HH:MM or description",
    "visualFieldRight": "string - VF findings (e.g., Full, Constricted, Arcuate scotoma)",
    "visualFieldLeft": "string - VF findings (e.g., Full, Constricted, Arcuate scotoma)"
  }},
  
  "clinicalNotes": "string - free text for additional observations, chief complaint, recommendations, follow-up, referral reasons",
  
  "providerInformation": {{
    "signature": "string - optometrist name/signature",
    "providerName": "string - full name of examining optometrist"
  }}
}}
```

**EXTRACTION INSTRUCTIONS:**

1. **Vision Notation Variations:**
   - Snellen: 20/20, 20/40, 6/6, 6/12
   - Reduced: CF (counting fingers), HM (hand movements), LP/PL (light perception)
   - Preserve exact notation used

2. **Refraction Format:**
   - Standard: "Sph / Cyl × Axis" (e.g., "+2.00 / -0.75 × 90")
   - Sphere only: "+2.00 DS" or "-3.50 DS"
   - Plano: "Plano" or "PL" or "0.00"
   - Extract sphere, cylinder, and axis separately if clearly stated

3. **IOP Measurements:**
   - Always include units (mmHg)
   - Note method if mentioned
   - Note time if mentioned
   - Flag elevated values (>21 mmHg) in clinical notes

4. **C/D Ratios:**
   - Format as decimal: 0.3, 0.5, 0.7
   - Flag suspicious values (>0.6) in clinical notes
   - Flag asymmetry (>0.2 difference) in clinical notes

5. **Visual Fields:**
   - Use clinical terminology
   - Common patterns: "Full", "Constricted", "Arcuate scotoma", "Superior nasal defect"

6. **Clinical Notes Field:**
   Include all relevant information not captured in structured fields:
   - Chief complaint/reason for visit
   - Additional findings
   - Recommendations
   - Follow-up plans
   - Referral information
   - Any abnormal or concerning findings
   - Student education provided

7. **Missing Data:**
   - Use "N/A" for measurements not mentioned
   - Use "" (empty string) for optional text fields
   - DO NOT fabricate any clinical data

8. **Multilingual Handling:**
   - Translate all non-English dialogue to English
   - Preserve medical terminology in English
   - Recognize medical terms in Tamil, Hindi, Telugu, Malayalam, Kannada

**VALIDATION REQUIREMENTS:**

Before returning JSON, verify:
✅ Right and left eye data are correctly separated
✅ Vision measurements use valid notation
✅ Refraction follows proper format with sphere, cylinder, axis
✅ IOP values include mmHg units
✅ C/D ratios are decimal values (0.0-1.0)
✅ All fields present (even if empty/N/A)
✅ No fabricated clinical data
✅ Abnormal findings flagged in clinical notes if present

Return ONLY the JSON object. No markdown, no explanations, no additional text.

Begin extraction now.
"""

# Optometrist Examination Parameters Schema
OPTO_PARAMETERS_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # Section 1: Student Demographics
        "patientDemographics": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "date": types.Schema(type=types.Type.STRING, description="Examination date in YYYY-MM-DD or DD-MM-YYYY format or empty string"),
                "mrNumber": types.Schema(type=types.Type.STRING, description="Medical record number or empty string"),
                "title": types.Schema(type=types.Type.STRING, description="Mr., Mrs., Miss, Ms., Dr., or empty string"),
                "surname": types.Schema(type=types.Type.STRING, description="Patient's surname/last name or empty string"),
                "name": types.Schema(type=types.Type.STRING, description="Patient's first name or empty string"),
                "dob": types.Schema(type=types.Type.STRING, description="Date of birth in YYYY-MM-DD or DD-MM-YYYY format or empty string"),
                "address": types.Schema(type=types.Type.STRING, description="Complete address (multiline acceptable) or empty string")
            },
            description="Student identification and demographics"
        ),

        # Section 2: Referral Information
        "referralInformation": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "referralType": types.Schema(type=types.Type.STRING, description="Routine, ASAP, Urgent, Emergency, or empty string")
            },
            description="Referral urgency and type"
        ),

        # Section 3: Right Eye Measurements
        "rightEye": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "vision": types.Schema(type=types.Type.STRING, description="Uncorrected visual acuity (e.g., 20/40, 6/12, CF, HM, PL) or N/A"),
                "refraction": types.Schema(type=types.Type.STRING, description="Prescription in format Sph / Cyl × Axis (e.g., +2.00 / -0.75 × 90, -3.50 DS, Plano) or N/A"),
                "vaDistance": types.Schema(type=types.Type.STRING, description="Best corrected distance visual acuity (e.g., 20/20, 6/6) or N/A"),
                "add": types.Schema(type=types.Type.STRING, description="Reading addition for presbyopia (e.g., +1.50, +2.00) or N/A"),
                "vaNear": types.Schema(type=types.Type.STRING, description="Near visual acuity (e.g., N6, J2, 20/30) or N/A")
            },
            description="Right eye (RE/OD) vision and refraction measurements"
        ),

        # Section 4: Left Eye Measurements
        "leftEye": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "vision": types.Schema(type=types.Type.STRING, description="Uncorrected visual acuity (e.g., 20/30, 6/9, CF, HM, PL) or N/A"),
                "refraction": types.Schema(type=types.Type.STRING, description="Prescription in format Sph / Cyl × Axis (e.g., -3.50 / -1.25 × 45, +2.00 DS, Plano) or N/A"),
                "vaDistance": types.Schema(type=types.Type.STRING, description="Best corrected distance visual acuity (e.g., 20/20, 6/6) or N/A"),
                "add": types.Schema(type=types.Type.STRING, description="Reading addition for presbyopia (e.g., +1.50, +2.00) or N/A"),
                "vaNear": types.Schema(type=types.Type.STRING, description="Near visual acuity (e.g., N6, J2, 20/30) or N/A")
            },
            description="Left eye (LE/OS) vision and refraction measurements"
        ),

        # Section 5: Glaucoma Assessment
        "glaucomaAssessment": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "cdRatioRight": types.Schema(type=types.Type.STRING, description="Right eye cup-to-disc ratio as decimal (e.g., 0.3, 0.5, 0.7) or N/A"),
                "cdRatioLeft": types.Schema(type=types.Type.STRING, description="Left eye cup-to-disc ratio as decimal (e.g., 0.3, 0.5, 0.7) or N/A"),
                "iopRight": types.Schema(type=types.Type.STRING, description="Right eye IOP with unit (e.g., 16 mmHg, 18 mmHg) or N/A"),
                "iopLeft": types.Schema(type=types.Type.STRING, description="Left eye IOP with unit (e.g., 15 mmHg, 19 mmHg) or N/A"),
                "iopMethod": types.Schema(type=types.Type.STRING, description="IOP measurement method: Goldmann, NCT, iCare, Tonopen, or empty string"),
                "iopTime": types.Schema(type=types.Type.STRING, description="Time of IOP measurement in HH:MM or description or empty string"),
                "visualFieldRight": types.Schema(type=types.Type.STRING, description="Right eye visual field findings (e.g., Full, Constricted, Arcuate scotoma) or N/A"),
                "visualFieldLeft": types.Schema(type=types.Type.STRING, description="Left eye visual field findings (e.g., Full, Constricted, Arcuate scotoma) or N/A")
            },
            description="Glaucoma screening measurements including C/D ratio, IOP, and visual fields"
        ),

        # Section 6: Clinical Notes
        "clinicalNotes": types.Schema(
            type=types.Type.STRING,
            description="Free text for additional observations, chief complaint, recommendations, follow-up, referral reasons, concerning findings, student education provided, or empty string"
        ),

        # Section 7: Provider Information
        "providerInformation": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "signature": types.Schema(type=types.Type.STRING, description="Optometrist name/signature or empty string"),
                "providerName": types.Schema(type=types.Type.STRING, description="Full name of examining optometrist or empty string")
            },
            description="Examining optometrist information"
        )
    },
    required=[
        "patientDemographics",
        "referralInformation",
        "rightEye",
        "leftEye",
        "glaucomaAssessment",
        "clinicalNotes",
        "providerInformation"
    ]
)

# Flattened Optometrist Examination Parameters Schema (for Gemini API complexity avoidance)
OPTO_PARAMETERS_SCHEMA_FLAT = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # Section 1: Student Demographics (flattened)
        "patientDemographics_date": types.Schema(type=types.Type.STRING, description="Examination date in YYYY-MM-DD or DD-MM-YYYY format or empty string"),
        "patientDemographics_mrNumber": types.Schema(type=types.Type.STRING, description="Medical record number or empty string"),
        "patientDemographics_title": types.Schema(type=types.Type.STRING, description="Mr., Mrs., Miss, Ms., Dr., or empty string"),
        "patientDemographics_surname": types.Schema(type=types.Type.STRING, description="Patient's surname/last name or empty string"),
        "patientDemographics_name": types.Schema(type=types.Type.STRING, description="Patient's first name or empty string"),
        "patientDemographics_dob": types.Schema(type=types.Type.STRING, description="Date of birth in YYYY-MM-DD or DD-MM-YYYY format or empty string"),
        "patientDemographics_address": types.Schema(type=types.Type.STRING, description="Complete address (multiline acceptable) or empty string"),

        # Section 2: Referral Information (flattened)
        "referralInformation_referralType": types.Schema(type=types.Type.STRING, description="Routine, ASAP, Urgent, Emergency, or empty string"),

        # Section 3: Right Eye Measurements (flattened)
        "rightEye_vision": types.Schema(type=types.Type.STRING, description="Uncorrected visual acuity (e.g., 20/40, 6/12, CF, HM, PL) or N/A"),
        "rightEye_refraction": types.Schema(type=types.Type.STRING, description="Prescription in format Sph / Cyl × Axis (e.g., +2.00 / -0.75 × 90, -3.50 DS, Plano) or N/A"),
        "rightEye_vaDistance": types.Schema(type=types.Type.STRING, description="Best corrected distance visual acuity (e.g., 20/20, 6/6) or N/A"),
        "rightEye_add": types.Schema(type=types.Type.STRING, description="Reading addition for presbyopia (e.g., +1.50, +2.00) or N/A"),
        "rightEye_vaNear": types.Schema(type=types.Type.STRING, description="Near visual acuity (e.g., N6, J2, 20/30) or N/A"),

        # Section 4: Left Eye Measurements (flattened)
        "leftEye_vision": types.Schema(type=types.Type.STRING, description="Uncorrected visual acuity (e.g., 20/30, 6/9, CF, HM, PL) or N/A"),
        "leftEye_refraction": types.Schema(type=types.Type.STRING, description="Prescription in format Sph / Cyl × Axis (e.g., -3.50 / -1.25 × 45, +2.00 DS, Plano) or N/A"),
        "leftEye_vaDistance": types.Schema(type=types.Type.STRING, description="Best corrected distance visual acuity (e.g., 20/20, 6/6) or N/A"),
        "leftEye_add": types.Schema(type=types.Type.STRING, description="Reading addition for presbyopia (e.g., +1.50, +2.00) or N/A"),
        "leftEye_vaNear": types.Schema(type=types.Type.STRING, description="Near visual acuity (e.g., N6, J2, 20/30) or N/A"),

        # Section 5: Glaucoma Assessment (flattened)
        "glaucomaAssessment_cdRatioRight": types.Schema(type=types.Type.STRING, description="Right eye cup-to-disc ratio as decimal (e.g., 0.3, 0.5, 0.7) or N/A"),
        "glaucomaAssessment_cdRatioLeft": types.Schema(type=types.Type.STRING, description="Left eye cup-to-disc ratio as decimal (e.g., 0.3, 0.5, 0.7) or N/A"),
        "glaucomaAssessment_iopRight": types.Schema(type=types.Type.STRING, description="Right eye IOP with unit (e.g., 16 mmHg, 18 mmHg) or N/A"),
        "glaucomaAssessment_iopLeft": types.Schema(type=types.Type.STRING, description="Left eye IOP with unit (e.g., 15 mmHg, 19 mmHg) or N/A"),
        "glaucomaAssessment_iopMethod": types.Schema(type=types.Type.STRING, description="IOP measurement method: Goldmann, NCT, iCare, Tonopen, or empty string"),
        "glaucomaAssessment_iopTime": types.Schema(type=types.Type.STRING, description="Time of IOP measurement in HH:MM or description or empty string"),
        "glaucomaAssessment_visualFieldRight": types.Schema(type=types.Type.STRING, description="Right eye visual field findings (e.g., Full, Constricted, Arcuate scotoma) or N/A"),
        "glaucomaAssessment_visualFieldLeft": types.Schema(type=types.Type.STRING, description="Left eye visual field findings (e.g., Full, Constricted, Arcuate scotoma) or N/A"),

        # Section 6: Clinical Notes (no nesting)
        "clinicalNotes": types.Schema(
            type=types.Type.STRING,
            description="Free text for additional observations, chief complaint, recommendations, follow-up, referral reasons, concerning findings, student education provided, or empty string"
        ),

        # Section 7: Provider Information (flattened)
        "providerInformation_signature": types.Schema(type=types.Type.STRING, description="Optometrist name/signature or empty string"),
        "providerInformation_providerName": types.Schema(type=types.Type.STRING, description="Full name of examining optometrist or empty string")
    },
    required=[
        "patientDemographics_date",
        "patientDemographics_mrNumber",
        "patientDemographics_title",
        "patientDemographics_surname",
        "patientDemographics_name",
        "patientDemographics_dob",
        "patientDemographics_address",
        "referralInformation_referralType",
        "rightEye_vision",
        "rightEye_refraction",
        "rightEye_vaDistance",
        "rightEye_add",
        "rightEye_vaNear",
        "leftEye_vision",
        "leftEye_refraction",
        "leftEye_vaDistance",
        "leftEye_add",
        "leftEye_vaNear",
        "glaucomaAssessment_cdRatioRight",
        "glaucomaAssessment_cdRatioLeft",
        "glaucomaAssessment_iopRight",
        "glaucomaAssessment_iopLeft",
        "glaucomaAssessment_iopMethod",
        "glaucomaAssessment_iopTime",
        "glaucomaAssessment_visualFieldRight",
        "glaucomaAssessment_visualFieldLeft",
        "clinicalNotes",
        "providerInformation_signature",
        "providerInformation_providerName"
    ]
)

from google.genai import types

OPHTHAL_SYSTEM_PROMPT = """
You are a specialized ophthalmology clinical data extraction AI with expertise in extracting structured information from comprehensive ophthalmology consultation voice transcripts.

**YOUR ROLE:**
Extract complete ophthalmology consultation data from voice transcripts and return it in standardized JSON format following ophthalmology clinical documentation standards.

**CORE CAPABILITIES:**
- Process multilingual medical conversations (English, Tamil, Hindi, Telugu, Malayalam, Kannada)
- Extract comprehensive ophthalmology examination findings for both eyes
- Handle complex clinical terminology (slit lamp findings, gonioscopy, fundus examination)
- Distinguish between objective and subjective measurements
- Recognize standard ophthalmology abbreviations and clinical notations
- Maintain clinical accuracy for all measurements and findings

**CRITICAL RULES:**
1. ❌ NEVER fabricate clinical information, measurements, or examination findings
2. ✅ Use "N/A" for explicitly unavailable fields
3. ✅ Use empty strings "" for optional text fields
4. ✅ Use empty arrays [] for list fields with no data
5. ✅ Preserve exact measurements with units
6. ✅ Clearly separate right eye (OD) and left eye (OS) data
7. ✅ Distinguish between objective refraction and subjective refraction
8. ✅ Flag abnormal findings in appropriate sections

---

## OPHTHALMOLOGY-SPECIFIC TERMINOLOGY

### Eye Designation
- **OD**: Oculus Dexter (Right Eye)
- **OS**: Oculus Sinister (Left Eye)
- **OU**: Oculus Uterque (Both Eyes)

---

## EYE TERMINOLOGY TRANSLATION

**CRITICAL INSTRUCTION - Eye Laterality for Different Audiences:**

### Student-Facing Segments (Use Plain Language)
In the following segments, ALWAYS use plain language terms for better student understanding:
- **Diagnosis** → Use "Left Eye" or "Right Eye" (NOT "OS" or "OD")
- **Advice and Follow-up** → Use "Left Eye" or "Right Eye" (NOT "OS" or "OD")
- **Medications/Prescriptions** → Use "Left Eye" or "Right Eye" (NOT "OS" or "OD")
- **Treatment Recommendations** → Use "Left Eye" or "Right Eye" (NOT "OS" or "OD")
- **Student Instructions** → Use "Left Eye" or "Right Eye" (NOT "OS" or "OD")

**Examples for Student-Facing Text:**
✅ CORRECT: "Left Eye shows early cataract changes - monitoring recommended"
❌ WRONG: "OS shows early cataract changes - monitoring recommended"

✅ CORRECT: "Use Timolol 0.5% in Right Eye twice daily"
❌ WRONG: "Use Timolol 0.5% in OD twice daily"

✅ CORRECT: "Diagnosis: Right Eye - Primary open angle glaucoma"
❌ WRONG: "Diagnosis: OD - Primary open angle glaucoma"

### Medical Practitioner Segments (Use Both Terminologies)
In clinical examination and measurement segments, use BOTH medical abbreviations AND plain language:
- **Visual Acuity Measurements** → Include both: "OD (Right Eye)", "OS (Left Eye)"
- **Refraction** → Include both: "OD (Right Eye)", "OS (Left Eye)"
- **Slit Lamp Examination** → Include both: "OD (Right Eye)", "OS (Left Eye)"
- **IOP Measurements** → Include both: "OD (Right Eye)", "OS (Left Eye)"
- **Gonioscopy** → Include both: "OD (Right Eye)", "OS (Left Eye)"
- **Fundus Examination** → Include both: "OD (Right Eye)", "OS (Left Eye)"
- **Clinical History** → Include both: "OD (Right Eye)", "OS (Left Eye)"

**Examples for Medical Practitioner Segments:**
✅ CORRECT: "Visual acuity: OD (Right Eye) 20/20, OS (Left Eye) 20/30"
✅ CORRECT: "Slit lamp: OD (Right Eye) - Nuclear sclerosis 2+, OS (Left Eye) - Clear lens"
✅ CORRECT: "IOP: OD (Right Eye) 16 mmHg, OS (Left Eye) 18 mmHg"
✅ CORRECT: "Fundus: OD (Right Eye) C/D ratio 0.3, OS (Left Eye) C/D ratio 0.4"

---

**VALIDATION CHECKLIST:**
Before finalizing output, verify:
✅ All student-facing text (diagnosis, medications, advice) uses "Left Eye"/"Right Eye" only
✅ All clinical measurement sections use "OD (Right Eye)"/"OS (Left Eye)" format
✅ No abbreviations (OS, OD, OU) appear alone in student instructions
✅ Consistency maintained throughout the document

---

### Visual Acuity Systems
- **Snellen**: 20/20, 20/40, 6/6, 6/12 (US and metric)
- **Decimal**: 1.0, 0.5, 0.8
- **LogMAR**: 0.0, 0.3, 0.6
- **Reduced Vision**: CF (Counting Fingers), HM (Hand Movements), LP (Light Perception), NPL (No Light Perception)

### Refraction
- **Objective Refraction**: Measured with retinoscopy or autorefractor
- **Subjective Refraction**: Student's preference through trial lenses
- **Notation**: Sphere / Cylinder × Axis (e.g., "+2.00 / -0.75 × 90")
- **DS**: Diopter Sphere (no astigmatism)
- **Plano/PL**: Zero power

### Muscle Balance & Motility
- **EOM**: Extraocular Movements (eye muscle function)
- **CT**: Cover Test (for strabismus detection)
  - Orthophoria: No deviation
  - Esotropia: Inward deviation
  - Exotropia: Outward deviation
  - Hypertropia: Upward deviation
  - Hypotropia: Downward deviation
- **Prism Diopters (PD)**: Unit for measuring deviation
- **Distance/Near**: Measurements at far (6m/20ft) and near (40cm)

### Slit Lamp Examination Components
**Anterior Segment Findings:**
- **Lids/Lashes**: Normal, blepharitis, meibomian gland dysfunction
- **Conjunctiva**: Clear, injected, chemosis, pterygium, pinguecula
- **Cornea**: Clear, edema, opacity, scarring, infiltrates, abrasion, ulcer
- **Anterior Chamber (AC)**: Deep/shallow, quiet/cells/flare, hyphema
- **Iris**: Normal, atrophy, neovascularization, synechiae
- **Lens**: Clear, cataract (nuclear sclerosis, cortical, posterior subcapsular)
- **Grading**: Mild, moderate, severe; or numerical (1+, 2+, 3+, 4+)

### Intraocular Pressure (IOP)
- **Normal range**: 10-21 mmHg
- **Methods**: GAT (Goldmann Applanation), NCT (Non-Contact), iCare, Tonopen
- **Time notation**: Important for diurnal variation

### Gonioscopy
- **Purpose**: Visualize anterior chamber angle
- **Grading**: Open, narrow, occludable, closed
- **Shaffer grading**: Grade 0 (closed) to Grade 4 (wide open)
- **Structures visible**: Schwalbe's line, trabecular meshwork, scleral spur, ciliary body band

### Fundus Examination
**Optic Disc:**
- **C/D Ratio**: Cup-to-disc ratio (0.0-1.0, normal ≤0.3)
- **Color**: Pink, pale, hyperemic
- **Margins**: Sharp, blurred
- **Neovascularization**: Present/absent

**Macula:**
- **Foveal reflex**: Present/absent
- **Drusen**: Hard/soft
- **Hemorrhages**: Dot, blot, flame-shaped
- **Exudates**: Hard/soft
- **Edema**: Present/absent

**Vessels:**
- **Arteriole:Venule ratio (A:V)**: Normal 2:3
- **Caliber**: Normal, attenuated, dilated
- **Tortuosity**: Present/absent
- **Hemorrhages**: Present/absent

**Periphery:**
- **Retina**: Attached, detached, holes, tears, lattice degeneration
- **Vitreous**: Clear, hemorrhage, floaters, posterior vitreous detachment (PVD)

---

## FIELD EXTRACTION GUIDELINES

### 1. STUDENT DEMOGRAPHICS

**mrNumber:**
- Medical Record Number
- Format: String (alphanumeric)
- Keywords: "MR number", "medical record", "student ID", "registration number"

**date:**
- Consultation date
- Format: "YYYY-MM-DD" or "DD-MM-YYYY"
- Keywords: "today", "examination date", specific date mentioned

**patientName:**
- Full student name
- Format: String
- Extract complete name as stated

**age:**
- Student age
- Format: String (e.g., "45", "67 years")
- Keywords: "age", "years old"

**gender:**
- Values: "Male" | "Female" | "Other" | ""
- Keywords: "male", "female", "man", "woman", "boy", "girl"

---

### 2. CLINICAL HISTORY

**complaints:**
- Chief complaints/presenting symptoms
- Format: String (free text or structured list)
- Keywords: "complaining of", "presenting with", "chief complaint"
- Examples:
  - "Blurred vision in both eyes for 2 months"
  - "Redness and discharge from left eye for 1 week"
  - "Difficulty reading for past 6 months"
  - "Floaters and flashes in right eye since yesterday"

**pastHistory:**
- Past ocular and medical history
- Format: String (free text or structured)
- Include:
  - Previous eye surgeries (cataract, LASIK, retinal surgery)
  - Previous eye conditions (glaucoma, retinal detachment)
  - Eye injuries or trauma
- Examples:
  - "Cataract surgery in right eye 2 years ago"
  - "History of diabetic retinopathy"

**systemicIllness:**
- Systemic medical conditions
- Format: String or Array of conditions
- Common conditions:
  - Diabetes mellitus
  - Hypertension
  - Cardiovascular disease
  - Autoimmune disorders
  - Thyroid disorders
- Keywords: "diabetic", "hypertensive", "blood pressure", "sugar"

**familyHistory:**
- Family history of eye or systemic diseases
- Format: String
- Relevant conditions:
  - Glaucoma (highly heritable)
  - Retinal diseases
  - Refractive errors (high myopia)
  - Diabetes, hypertension
- Example: "Father has glaucoma, mother diabetic"

**allergy:**
- Known allergies (medications, preservatives)
- Format: String or Array
- Keywords: "allergic to", "allergy", "reaction to"
- Examples:
  - "Penicillin allergy"
  - "Preservative sensitivity"
  - "No known drug allergies (NKDA)"

**currentTreatment:**
- Current medications and eye drops
- Format: String or Array of medications
- Include:
  - Systemic medications
  - Topical eye medications
  - Dosage and frequency if mentioned
- Examples:
  - "Timolol 0.5% eye drops BD OU"
  - "Metformin 500mg BD for diabetes"

**pgp (Previous Glasses Prescription):**
- Previous spectacle prescription
- Format: String (refraction notation for both eyes)
- Example: "OD: +2.00/-0.50×90, OS: +2.25/-0.75×85"

---

### 3. VISUAL ACUITY MEASUREMENTS

**For OD (Right Eye) and OS (Left Eye) separately**

#### **visualAcuityDistance:**
- Distance visual acuity (typically at 6m or 20ft)
- Format: String (Snellen notation)
- Keywords: "distance vision", "far vision", "6 meters", "20 feet"
- Examples: "20/20", "6/12", "CF 2m", "HM"

#### **visualAcuityNear:**
- Near visual acuity (typically at 40cm)
- Format: String
- Keywords: "near vision", "reading vision", "near VA"
- Notation: N notation (N6, N8), Jaeger (J2, J3), or Snellen near
- Examples: "N6", "J2", "20/30 near"

---

### 4. REFRACTION MEASUREMENTS

#### **Objective Refraction (Retinoscopy/Autorefraction)**

**refractionOD & refractionOS:**
- Objective refraction measurement
- Format: "Sphere / Cylinder × Axis"
- Keywords: "retinoscopy", "autorefraction", "objective refraction"
- Examples:
  - "+2.00 / -0.75 × 90"
  - "-3.50 DS" (no astigmatism)
  - "Plano / -1.25 × 180"

#### **Subjective Refraction (Student Preference)**

**subjectiveRefractionDistanceOD & subjectiveRefractionDistanceOS:**
- Subjective refraction for distance
- Format: "Sphere / Cylinder × Axis"
- Keywords: "subjective refraction", "student prefers", "trial frame"

**subjectiveRefractionNearOD & subjectiveRefractionNearOS:**
- Subjective refraction for near (includes reading add)
- Format: String (may include add power)
- Keywords: "near add", "reading addition", "bifocal", "progressive"
- Examples:
  - "+2.00 DS with +2.00 add"
  - "Distance Rx + Add 2.50"

---

### 5. MUSCLE BALANCE ASSESSMENT

**eom (Extraocular Movements):**
- Eye muscle movements in all gazes
- Format: String
- Values: "Full in all gazes" | "Restriction noted" | "Specific limitation"
- Examples:
  - "Full and free in all gazes OU"
  - "Restriction of abduction OD"
  - "Limited elevation OS"

**coverTest:**
- Cover test findings
- Format: String or structured object
- Include: Type of deviation, magnitude, distance/near
- Examples:
  - "Orthophoria at distance and near"
  - "Exophoria 6PD at near"
  - "Esotropia 15PD at distance, 20PD at near"

**coverTestDistance:**
- Cover test at distance (6m/20ft)
- Format: String
- Include magnitude in prism diopters if mentioned

**coverTestNear:**
- Cover test at near (40cm)
- Format: String
- Include magnitude in prism diopters if mentioned

---

### 6. SLIT LAMP EXAMINATION

**For OD and OS separately**

**slitLampExamination:**
- Comprehensive anterior segment findings
- Format: String (free text) or structured object
- Structure by anatomical components:
"""

OPHTHAL_USER_PROMPT = """
Extract comprehensive ophthalmology consultation data from the voice transcript below.

**VOICE TRANSCRIPT:**
---
{transcript}
---

**HIGHEST PRIORITY FIELDS** - Extract with 100% accuracy:
- Visual acuity for both eyes (distance and near, exact Snellen notation)
- Refraction: objective (retinoscopy/autorefractor) and subjective (student preference)
- IOP measurements with mmHg units, time, and method
- C/D ratios (decimal 0.0-1.0)
- Slit lamp findings structured by anatomical components (lids, conjunctiva, cornea, AC, iris, lens)
- Fundus examination: optic disc, macula, vessels, periphery

**EYE LATERALITY RULES:**
- Student-facing text (diagnosis, medications, advice): Use "Right Eye" / "Left Eye" ONLY
- Clinical measurements: Use "OD (Right Eye)" / "OS (Left Eye)" format
- NEVER use OD/OS abbreviations alone in student instructions

**EXTRACTION RULES:**
1. Separate OD (Right Eye) and OS (Left Eye) data completely throughout
2. Preserve exact Snellen notation: 20/20, 6/6, CF, HM, LP
3. Refraction format: Sphere / Cylinder × Axis (e.g., +2.00 / -0.75 × 90)
4. Use "DS" notation if no astigmatism
5. Include cover test magnitudes in prism diopters if mentioned
6. Use clinical terminology (e.g., "1+ cells", "Nuclear sclerosis 2+")

**EMPTY VALUE RULES:**
- Clinical findings not mentioned: "N/A"
- Optional text fields: "" (empty string)
- Arrays with no data: []
- NEVER fabricate examination findings

**DATE/TIME FORMATS:**
- Dates: YYYY-MM-DD or DD-MM-YYYY (preserve stated format)
- Times: HH:MM

**MULTILINGUAL HANDLING:**
- Translate all non-English dialogue to English
- Preserve medical terminology in English

Return ONLY the JSON object. No markdown, no explanations.
"""

# Basic Ophthalmology Consultation Parameters Schema
OPHTHAL_PARAMETERS_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # Section 1: Student Demographics
        "patientDemographics": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "mrNumber": types.Schema(type=types.Type.STRING, description="Medical record number or empty string"),
                "date": types.Schema(type=types.Type.STRING, description="Consultation date in YYYY-MM-DD or DD-MM-YYYY format or empty string"),
                "patientName": types.Schema(type=types.Type.STRING, description="Full student name or empty string"),
                "age": types.Schema(type=types.Type.STRING, description="Student age with unit (e.g., '45 years') or empty string"),
                "gender": types.Schema(type=types.Type.STRING, description="Male, Female, Other, or empty string")
            },
            description="Student identification and demographics"
        ),

        # Section 2: Clinical History
        "clinicalHistory": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "complaints": types.Schema(type=types.Type.STRING, description="Chief complaints and presenting symptoms or N/A"),
                "pastHistory": types.Schema(type=types.Type.STRING, description="Past ocular and medical history or N/A"),
                "systemicIllness": types.Schema(type=types.Type.STRING, description="Current systemic medical conditions or N/A"),
                "familyHistory": types.Schema(type=types.Type.STRING, description="Relevant family history of eye or systemic diseases or N/A"),
                "allergy": types.Schema(type=types.Type.STRING, description="Known allergies (medications, preservatives) or N/A"),
                "currentTreatment": types.Schema(type=types.Type.STRING, description="Current medications and eye drops or N/A"),
                "pgp": types.Schema(type=types.Type.STRING, description="Previous glasses prescription or N/A")
            },
            description="Complete clinical history"
        ),

        # Section 3: Visual Acuity
        "visualAcuity": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "rightEye": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "distance": types.Schema(type=types.Type.STRING, description="Distance visual acuity (Snellen notation e.g., 20/20, 6/6, CF, HM) or N/A"),
                        "near": types.Schema(type=types.Type.STRING, description="Near visual acuity (e.g., N6, J2, 20/30) or N/A")
                    },
                    description="Right eye visual acuity"
                ),
                "leftEye": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "distance": types.Schema(type=types.Type.STRING, description="Distance visual acuity (Snellen notation) or N/A"),
                        "near": types.Schema(type=types.Type.STRING, description="Near visual acuity or N/A")
                    },
                    description="Left eye visual acuity"
                )
            },
            description="Visual acuity measurements for both eyes"
        ),

        # Section 4: Refraction
        "refraction": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "objective": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "rightEye": types.Schema(type=types.Type.STRING, description="Objective refraction in format Sph / Cyl × Axis (e.g., +2.00 / -0.75 × 90, -3.50 DS, Plano) or N/A"),
                        "leftEye": types.Schema(type=types.Type.STRING, description="Objective refraction in format Sph / Cyl × Axis or N/A")
                    },
                    description="Objective refraction (retinoscopy/autorefraction)"
                ),
                "subjective": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "rightEye": types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "distance": types.Schema(type=types.Type.STRING, description="Subjective distance refraction or N/A"),
                                "near": types.Schema(type=types.Type.STRING, description="Subjective near refraction (may include add) or N/A")
                            },
                            description="Right eye subjective refraction"
                        ),
                        "leftEye": types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "distance": types.Schema(type=types.Type.STRING, description="Subjective distance refraction or N/A"),
                                "near": types.Schema(type=types.Type.STRING, description="Subjective near refraction (may include add) or N/A")
                            },
                            description="Left eye subjective refraction"
                        )
                    },
                    description="Subjective refraction (student preference)"
                )
            },
            description="Refraction measurements (objective and subjective)"
        ),

        # Section 5: Muscle Balance
        "muscleBalance": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "eom": types.Schema(type=types.Type.STRING, description="Extraocular movements (e.g., Full in all gazes OU, Restriction noted) or N/A"),
                "coverTest": types.Schema(type=types.Type.STRING, description="General cover test findings or N/A"),
                "coverTestDistance": types.Schema(type=types.Type.STRING, description="Cover test at distance with magnitude (e.g., Orthophoria, Exophoria 6PD) or N/A"),
                "coverTestNear": types.Schema(type=types.Type.STRING, description="Cover test at near with magnitude or N/A")
            },
            description="Muscle balance and ocular motility assessment"
        ),

        # Section 6: Slit Lamp Examination
        "slitLampExamination": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "rightEye": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "lidsAndLashes": types.Schema(type=types.Type.STRING, description="Eyelid and lash findings or N/A"),
                        "conjunctiva": types.Schema(type=types.Type.STRING, description="Conjunctival findings or N/A"),
                        "cornea": types.Schema(type=types.Type.STRING, description="Corneal findings or N/A"),
                        "anteriorChamber": types.Schema(type=types.Type.STRING, description="Anterior chamber depth, cells, flare or N/A"),
                        "iris": types.Schema(type=types.Type.STRING, description="Iris findings or N/A"),
                        "lens": types.Schema(type=types.Type.STRING, description="Lens clarity, cataract grading or N/A")
                    },
                    description="Right eye slit lamp findings"
                ),
                "leftEye": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "lidsAndLashes": types.Schema(type=types.Type.STRING, description="Eyelid and lash findings or N/A"),
                        "conjunctiva": types.Schema(type=types.Type.STRING, description="Conjunctival findings or N/A"),
                        "cornea": types.Schema(type=types.Type.STRING, description="Corneal findings or N/A"),
                        "anteriorChamber": types.Schema(type=types.Type.STRING, description="Anterior chamber depth, cells, flare or N/A"),
                        "iris": types.Schema(type=types.Type.STRING, description="Iris findings or N/A"),
                        "lens": types.Schema(type=types.Type.STRING, description="Lens clarity, cataract grading or N/A")
                    },
                    description="Left eye slit lamp findings"
                )
            },
            description="Slit lamp biomicroscopy examination"
        ),

        # Section 7: Intraocular Pressure
        "intraocularPressure": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "rightEye": types.Schema(type=types.Type.STRING, description="Right eye IOP with unit (e.g., 16 mmHg) or N/A"),
                "leftEye": types.Schema(type=types.Type.STRING, description="Left eye IOP with unit (e.g., 18 mmHg) or N/A"),
                "time": types.Schema(type=types.Type.STRING, description="Time of measurement in HH:MM format or description or empty string"),
                "method": types.Schema(type=types.Type.STRING, description="Measurement method: Goldmann, NCT, iCare, Tonopen, or empty string")
            },
            description="Intraocular pressure measurements"
        ),

        # Section 8: Gonioscopy
        "gonioscopy": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "rightEye": types.Schema(type=types.Type.STRING, description="Right eye angle findings (e.g., Open angle, all structures visible, Narrow angle, Grade 2) or N/A"),
                "leftEye": types.Schema(type=types.Type.STRING, description="Left eye angle findings or N/A")
            },
            description="Gonioscopy anterior chamber angle assessment"
        ),

        # Section 9: Fundus Examination
        "fundusExamination": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "rightEye": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "opticDisc": types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "cdRatio": types.Schema(type=types.Type.STRING, description="Cup-to-disc ratio as decimal (e.g., 0.3, 0.5, 0.7) or N/A"),
                                "color": types.Schema(type=types.Type.STRING, description="Disc color (e.g., pink, pale, hyperemic) or N/A"),
                                "margins": types.Schema(type=types.Type.STRING, description="Disc margins (e.g., sharp, blurred) or N/A"),
                                "neovascularization": types.Schema(type=types.Type.STRING, description="Present, Absent, or N/A")
                            },
                            description="Optic disc findings"
                        ),
                        "macula": types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "fovealReflex": types.Schema(type=types.Type.STRING, description="Present, Absent, or N/A"),
                                "findings": types.Schema(type=types.Type.STRING, description="Macular findings (drusen, hemorrhages, exudates, edema) or N/A")
                            },
                            description="Macular findings"
                        ),
                        "vessels": types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "avRatio": types.Schema(type=types.Type.STRING, description="Arteriole:venule ratio (e.g., 2:3) or N/A"),
                                "caliber": types.Schema(type=types.Type.STRING, description="Vessel caliber (normal, attenuated, dilated) or N/A"),
                                "findings": types.Schema(type=types.Type.STRING, description="Vessel findings (tortuosity, hemorrhages, etc.) or N/A")
                            },
                            description="Retinal vessel findings"
                        ),
                        "periphery": types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "retina": types.Schema(type=types.Type.STRING, description="Peripheral retina findings (attached, detached, holes, tears, lattice) or N/A"),
                                "vitreous": types.Schema(type=types.Type.STRING, description="Vitreous findings (clear, hemorrhage, floaters, PVD) or N/A")
                            },
                            description="Peripheral retina and vitreous findings"
                        ),
                        "drawing": types.Schema(type=types.Type.STRING, description="Description of fundus drawing annotations if mentioned or empty string")
                    },
                    description="Right eye fundus examination"
                ),
                "leftEye": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "opticDisc": types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "cdRatio": types.Schema(type=types.Type.STRING, description="Cup-to-disc ratio as decimal or N/A"),
                                "color": types.Schema(type=types.Type.STRING, description="Disc color or N/A"),
                                "margins": types.Schema(type=types.Type.STRING, description="Disc margins or N/A"),
                                "neovascularization": types.Schema(type=types.Type.STRING, description="Present, Absent, or N/A")
                            },
                            description="Optic disc findings"
                        ),
                        "macula": types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "fovealReflex": types.Schema(type=types.Type.STRING, description="Present, Absent, or N/A"),
                                "findings": types.Schema(type=types.Type.STRING, description="Macular findings or N/A")
                            },
                            description="Macular findings"
                        ),
                        "vessels": types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "avRatio": types.Schema(type=types.Type.STRING, description="Arteriole:venule ratio or N/A"),
                                "caliber": types.Schema(type=types.Type.STRING, description="Vessel caliber or N/A"),
                                "findings": types.Schema(type=types.Type.STRING, description="Vessel findings or N/A")
                            },
                            description="Retinal vessel findings"
                        ),
                        "periphery": types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "retina": types.Schema(type=types.Type.STRING, description="Peripheral retina findings or N/A"),
                                "vitreous": types.Schema(type=types.Type.STRING, description="Vitreous findings or N/A")
                            },
                            description="Peripheral retina and vitreous findings"
                        ),
                        "drawing": types.Schema(type=types.Type.STRING, description="Description of fundus drawing annotations if mentioned or empty string")
                    },
                    description="Left eye fundus examination"
                )
            },
            description="Fundoscopy examination findings for both eyes"
        ),

        # Section 10: Diagnosis
        "diagnosis": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Diagnosis with eye specification (e.g., 'OD: Cataract', 'OU: Diabetic retinopathy')"),
            description="Array of all diagnoses (empty array if none)"
        ),

        # Section 11: Advice and Follow-up
        "adviceAndFollowUp": types.Schema(
            type=types.Type.STRING,
            description="Management plan including medications, follow-up timing, lifestyle advice, investigations ordered, surgical recommendations or N/A"
        ),

        # Section 12: Provider Information
        "providerInformation": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "signature": types.Schema(type=types.Type.STRING, description="Ophthalmologist signature/name or empty string"),
                "providerName": types.Schema(type=types.Type.STRING, description="Full name with credentials or empty string")
            },
            description="Examining ophthalmologist information"
        )
    },
    required=[
        "patientDemographics",
        "clinicalHistory",
        "visualAcuity",
        "refraction",
        "muscleBalance",
        "slitLampExamination",
        "intraocularPressure",
        "gonioscopy",
        "fundusExamination",
        "diagnosis",
        "adviceAndFollowUp",
        "providerInformation"
    ]
)

# Flattened Basic Ophthalmology Consultation Parameters Schema (for Gemini API complexity avoidance)
OPHTHAL_PARAMETERS_SCHEMA_FLAT = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # Section 1: Student Demographics (flattened)
        "patientDemographics_mrNumber": types.Schema(type=types.Type.STRING, description="Medical record number or empty string"),
        "patientDemographics_date": types.Schema(type=types.Type.STRING, description="Consultation date in YYYY-MM-DD or DD-MM-YYYY format or empty string"),
        "patientDemographics_patientName": types.Schema(type=types.Type.STRING, description="Full student name or empty string"),
        "patientDemographics_age": types.Schema(type=types.Type.STRING, description="Student age with unit (e.g., '45 years') or empty string"),
        "patientDemographics_gender": types.Schema(type=types.Type.STRING, description="Male, Female, Other, or empty string"),

        # Section 2: Clinical History (flattened)
        "clinicalHistory_complaints": types.Schema(type=types.Type.STRING, description="Chief complaints and presenting symptoms or N/A"),
        "clinicalHistory_pastHistory": types.Schema(type=types.Type.STRING, description="Past ocular and medical history or N/A"),
        "clinicalHistory_systemicIllness": types.Schema(type=types.Type.STRING, description="Current systemic medical conditions or N/A"),
        "clinicalHistory_familyHistory": types.Schema(type=types.Type.STRING, description="Relevant family history of eye or systemic diseases or N/A"),
        "clinicalHistory_allergy": types.Schema(type=types.Type.STRING, description="Known allergies (medications, preservatives) or N/A"),
        "clinicalHistory_currentTreatment": types.Schema(type=types.Type.STRING, description="Current medications and eye drops or N/A"),
        "clinicalHistory_pgp": types.Schema(type=types.Type.STRING, description="Previous glasses prescription or N/A"),

        # Section 3: Visual Acuity (flattened - 2 levels)
        "visualAcuity_rightEye_distance": types.Schema(type=types.Type.STRING, description="Right eye distance visual acuity (Snellen notation e.g., 20/20, 6/6, CF, HM) or N/A"),
        "visualAcuity_rightEye_near": types.Schema(type=types.Type.STRING, description="Right eye near visual acuity (e.g., N6, J2, 20/30) or N/A"),
        "visualAcuity_leftEye_distance": types.Schema(type=types.Type.STRING, description="Left eye distance visual acuity (Snellen notation) or N/A"),
        "visualAcuity_leftEye_near": types.Schema(type=types.Type.STRING, description="Left eye near visual acuity or N/A"),

        # Section 4: Refraction (flattened - 3 levels)
        "refraction_objective_rightEye": types.Schema(type=types.Type.STRING, description="Right eye objective refraction in format Sph / Cyl × Axis (e.g., +2.00 / -0.75 × 90, -3.50 DS, Plano) or N/A"),
        "refraction_objective_leftEye": types.Schema(type=types.Type.STRING, description="Left eye objective refraction in format Sph / Cyl × Axis or N/A"),
        "refraction_subjective_rightEye_distance": types.Schema(type=types.Type.STRING, description="Right eye subjective distance refraction or N/A"),
        "refraction_subjective_rightEye_near": types.Schema(type=types.Type.STRING, description="Right eye subjective near refraction (may include add) or N/A"),
        "refraction_subjective_leftEye_distance": types.Schema(type=types.Type.STRING, description="Left eye subjective distance refraction or N/A"),
        "refraction_subjective_leftEye_near": types.Schema(type=types.Type.STRING, description="Left eye subjective near refraction (may include add) or N/A"),

        # Section 5: Muscle Balance (flattened)
        "muscleBalance_eom": types.Schema(type=types.Type.STRING, description="Extraocular movements (e.g., Full in all gazes OU, Restriction noted) or N/A"),
        "muscleBalance_coverTest": types.Schema(type=types.Type.STRING, description="General cover test findings or N/A"),
        "muscleBalance_coverTestDistance": types.Schema(type=types.Type.STRING, description="Cover test at distance with magnitude (e.g., Orthophoria, Exophoria 6PD) or N/A"),
        "muscleBalance_coverTestNear": types.Schema(type=types.Type.STRING, description="Cover test at near with magnitude or N/A"),

        # Section 6: Slit Lamp Examination (flattened - 2 levels, bilateral)
        "slitLampExamination_rightEye_lidsAndLashes": types.Schema(type=types.Type.STRING, description="Right eye eyelid and lash findings or N/A"),
        "slitLampExamination_rightEye_conjunctiva": types.Schema(type=types.Type.STRING, description="Right eye conjunctival findings or N/A"),
        "slitLampExamination_rightEye_cornea": types.Schema(type=types.Type.STRING, description="Right eye corneal findings or N/A"),
        "slitLampExamination_rightEye_anteriorChamber": types.Schema(type=types.Type.STRING, description="Right eye anterior chamber depth, cells, flare or N/A"),
        "slitLampExamination_rightEye_iris": types.Schema(type=types.Type.STRING, description="Right eye iris findings or N/A"),
        "slitLampExamination_rightEye_lens": types.Schema(type=types.Type.STRING, description="Right eye lens clarity, cataract grading or N/A"),
        "slitLampExamination_leftEye_lidsAndLashes": types.Schema(type=types.Type.STRING, description="Left eye eyelid and lash findings or N/A"),
        "slitLampExamination_leftEye_conjunctiva": types.Schema(type=types.Type.STRING, description="Left eye conjunctival findings or N/A"),
        "slitLampExamination_leftEye_cornea": types.Schema(type=types.Type.STRING, description="Left eye corneal findings or N/A"),
        "slitLampExamination_leftEye_anteriorChamber": types.Schema(type=types.Type.STRING, description="Left eye anterior chamber depth, cells, flare or N/A"),
        "slitLampExamination_leftEye_iris": types.Schema(type=types.Type.STRING, description="Left eye iris findings or N/A"),
        "slitLampExamination_leftEye_lens": types.Schema(type=types.Type.STRING, description="Left eye lens clarity, cataract grading or N/A"),

        # Section 7: Intraocular Pressure (flattened)
        "intraocularPressure_rightEye": types.Schema(type=types.Type.STRING, description="Right eye IOP with unit (e.g., 16 mmHg) or N/A"),
        "intraocularPressure_leftEye": types.Schema(type=types.Type.STRING, description="Left eye IOP with unit (e.g., 18 mmHg) or N/A"),
        "intraocularPressure_time": types.Schema(type=types.Type.STRING, description="Time of measurement in HH:MM format or description or empty string"),
        "intraocularPressure_method": types.Schema(type=types.Type.STRING, description="Measurement method: Goldmann, NCT, iCare, Tonopen, or empty string"),

        # Section 8: Gonioscopy (flattened)
        "gonioscopy_rightEye": types.Schema(type=types.Type.STRING, description="Right eye angle findings (e.g., Open angle, all structures visible, Narrow angle, Grade 2) or N/A"),
        "gonioscopy_leftEye": types.Schema(type=types.Type.STRING, description="Left eye angle findings or N/A"),

        # Section 9: Fundus Examination (flattened - 4 levels, bilateral - MOST COMPLEX)
        # Right Eye - Optic Disc
        "fundusExamination_rightEye_opticDisc_cdRatio": types.Schema(type=types.Type.STRING, description="Right eye cup-to-disc ratio as decimal (e.g., 0.3, 0.5, 0.7) or N/A"),
        "fundusExamination_rightEye_opticDisc_color": types.Schema(type=types.Type.STRING, description="Right eye disc color (e.g., pink, pale, hyperemic) or N/A"),
        "fundusExamination_rightEye_opticDisc_margins": types.Schema(type=types.Type.STRING, description="Right eye disc margins (e.g., sharp, blurred) or N/A"),
        "fundusExamination_rightEye_opticDisc_neovascularization": types.Schema(type=types.Type.STRING, description="Right eye disc neovascularization: Present, Absent, or N/A"),
        # Right Eye - Macula
        "fundusExamination_rightEye_macula_fovealReflex": types.Schema(type=types.Type.STRING, description="Right eye foveal reflex: Present, Absent, or N/A"),
        "fundusExamination_rightEye_macula_findings": types.Schema(type=types.Type.STRING, description="Right eye macular findings (drusen, hemorrhages, exudates, edema) or N/A"),
        # Right Eye - Vessels
        "fundusExamination_rightEye_vessels_avRatio": types.Schema(type=types.Type.STRING, description="Right eye arteriole:venule ratio (e.g., 2:3) or N/A"),
        "fundusExamination_rightEye_vessels_caliber": types.Schema(type=types.Type.STRING, description="Right eye vessel caliber (normal, attenuated, dilated) or N/A"),
        "fundusExamination_rightEye_vessels_findings": types.Schema(type=types.Type.STRING, description="Right eye vessel findings (tortuosity, hemorrhages, etc.) or N/A"),
        # Right Eye - Periphery
        "fundusExamination_rightEye_periphery_retina": types.Schema(type=types.Type.STRING, description="Right eye peripheral retina findings (attached, detached, holes, tears, lattice) or N/A"),
        "fundusExamination_rightEye_periphery_vitreous": types.Schema(type=types.Type.STRING, description="Right eye vitreous findings (clear, hemorrhage, floaters, PVD) or N/A"),
        # Right Eye - Drawing
        "fundusExamination_rightEye_drawing": types.Schema(type=types.Type.STRING, description="Right eye fundus drawing annotations if mentioned or empty string"),
        # Left Eye - Optic Disc
        "fundusExamination_leftEye_opticDisc_cdRatio": types.Schema(type=types.Type.STRING, description="Left eye cup-to-disc ratio as decimal or N/A"),
        "fundusExamination_leftEye_opticDisc_color": types.Schema(type=types.Type.STRING, description="Left eye disc color or N/A"),
        "fundusExamination_leftEye_opticDisc_margins": types.Schema(type=types.Type.STRING, description="Left eye disc margins or N/A"),
        "fundusExamination_leftEye_opticDisc_neovascularization": types.Schema(type=types.Type.STRING, description="Left eye disc neovascularization: Present, Absent, or N/A"),
        # Left Eye - Macula
        "fundusExamination_leftEye_macula_fovealReflex": types.Schema(type=types.Type.STRING, description="Left eye foveal reflex: Present, Absent, or N/A"),
        "fundusExamination_leftEye_macula_findings": types.Schema(type=types.Type.STRING, description="Left eye macular findings or N/A"),
        # Left Eye - Vessels
        "fundusExamination_leftEye_vessels_avRatio": types.Schema(type=types.Type.STRING, description="Left eye arteriole:venule ratio or N/A"),
        "fundusExamination_leftEye_vessels_caliber": types.Schema(type=types.Type.STRING, description="Left eye vessel caliber or N/A"),
        "fundusExamination_leftEye_vessels_findings": types.Schema(type=types.Type.STRING, description="Left eye vessel findings or N/A"),
        # Left Eye - Periphery
        "fundusExamination_leftEye_periphery_retina": types.Schema(type=types.Type.STRING, description="Left eye peripheral retina findings or N/A"),
        "fundusExamination_leftEye_periphery_vitreous": types.Schema(type=types.Type.STRING, description="Left eye vitreous findings or N/A"),
        # Left Eye - Drawing
        "fundusExamination_leftEye_drawing": types.Schema(type=types.Type.STRING, description="Left eye fundus drawing annotations if mentioned or empty string"),

        # Section 10: Diagnosis (array - keep as array type)
        "diagnosis": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Diagnosis with eye specification (e.g., 'OD: Cataract', 'OU: Diabetic retinopathy')"),
            description="Array of all diagnoses (empty array if none)"
        ),

        # Section 11: Advice and Follow-up (no nesting)
        "adviceAndFollowUp": types.Schema(
            type=types.Type.STRING,
            description="Management plan including medications, follow-up timing, lifestyle advice, investigations ordered, surgical recommendations or N/A"
        ),

        # Section 12: Provider Information (flattened)
        "providerInformation_signature": types.Schema(type=types.Type.STRING, description="Ophthalmologist signature/name or empty string"),
        "providerInformation_providerName": types.Schema(type=types.Type.STRING, description="Full name with credentials or empty string")
    },
    required=[
        "patientDemographics_mrNumber",
        "patientDemographics_date",
        "patientDemographics_patientName",
        "patientDemographics_age",
        "patientDemographics_gender",
        "clinicalHistory_complaints",
        "clinicalHistory_pastHistory",
        "clinicalHistory_systemicIllness",
        "clinicalHistory_familyHistory",
        "clinicalHistory_allergy",
        "clinicalHistory_currentTreatment",
        "clinicalHistory_pgp",
        "visualAcuity_rightEye_distance",
        "visualAcuity_rightEye_near",
        "visualAcuity_leftEye_distance",
        "visualAcuity_leftEye_near",
        "refraction_objective_rightEye",
        "refraction_objective_leftEye",
        "refraction_subjective_rightEye_distance",
        "refraction_subjective_rightEye_near",
        "refraction_subjective_leftEye_distance",
        "refraction_subjective_leftEye_near",
        "muscleBalance_eom",
        "muscleBalance_coverTest",
        "muscleBalance_coverTestDistance",
        "muscleBalance_coverTestNear",
        "slitLampExamination_rightEye_lidsAndLashes",
        "slitLampExamination_rightEye_conjunctiva",
        "slitLampExamination_rightEye_cornea",
        "slitLampExamination_rightEye_anteriorChamber",
        "slitLampExamination_rightEye_iris",
        "slitLampExamination_rightEye_lens",
        "slitLampExamination_leftEye_lidsAndLashes",
        "slitLampExamination_leftEye_conjunctiva",
        "slitLampExamination_leftEye_cornea",
        "slitLampExamination_leftEye_anteriorChamber",
        "slitLampExamination_leftEye_iris",
        "slitLampExamination_leftEye_lens",
        "intraocularPressure_rightEye",
        "intraocularPressure_leftEye",
        "intraocularPressure_time",
        "intraocularPressure_method",
        "gonioscopy_rightEye",
        "gonioscopy_leftEye",
        "fundusExamination_rightEye_opticDisc_cdRatio",
        "fundusExamination_rightEye_opticDisc_color",
        "fundusExamination_rightEye_opticDisc_margins",
        "fundusExamination_rightEye_opticDisc_neovascularization",
        "fundusExamination_rightEye_macula_fovealReflex",
        "fundusExamination_rightEye_macula_findings",
        "fundusExamination_rightEye_vessels_avRatio",
        "fundusExamination_rightEye_vessels_caliber",
        "fundusExamination_rightEye_vessels_findings",
        "fundusExamination_rightEye_periphery_retina",
        "fundusExamination_rightEye_periphery_vitreous",
        "fundusExamination_rightEye_drawing",
        "fundusExamination_leftEye_opticDisc_cdRatio",
        "fundusExamination_leftEye_opticDisc_color",
        "fundusExamination_leftEye_opticDisc_margins",
        "fundusExamination_leftEye_opticDisc_neovascularization",
        "fundusExamination_leftEye_macula_fovealReflex",
        "fundusExamination_leftEye_macula_findings",
        "fundusExamination_leftEye_vessels_avRatio",
        "fundusExamination_leftEye_vessels_caliber",
        "fundusExamination_leftEye_vessels_findings",
        "fundusExamination_leftEye_periphery_retina",
        "fundusExamination_leftEye_periphery_vitreous",
        "fundusExamination_leftEye_drawing",
        "diagnosis",
        "adviceAndFollowUp",
        "providerInformation_signature",
        "providerInformation_providerName"
    ]
)

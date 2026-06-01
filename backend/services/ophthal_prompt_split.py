"""
Split OPHTHAL (Basic) Schema for Gemini API Compatibility

The flattened schema (71 properties) may exceed Gemini's constraint limits,
especially with the deeply nested fundusExamination section (26 fields).
This module splits the extraction into TWO separate API calls:

PART 1 (33 fields): STUDENT DATA & ANTERIOR EXAMINATION
- Student demographics (5 fields)
- Clinical history (7 fields)
- Visual acuity (4 fields - bilateral)
- Refraction (6 fields - bilateral, 3 levels)
- Muscle balance (4 fields)
- Intraocular pressure (4 fields)
- Gonioscopy (2 fields - bilateral)
- Provider information (2 fields)

PART 2 (38 fields): SLIT LAMP & FUNDUS EXAMINATION
- Slit lamp examination (12 fields - bilateral)
- Fundus examination (26 fields - bilateral, 4 levels deep)
- Diagnosis (array)
- Advice and follow-up (1 field)

The ophthal_formatter.py service merges both results into the final nested structure.
"""

from google.genai import types

# ============================================================================
# PART 1: STUDENT DATA & ANTERIOR EXAMINATION (33 fields)
# ============================================================================

OPHTHAL_PART1_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== SECTION 1: STUDENT DEMOGRAPHICS (5 fields) ==========
        "patientDemographics_mrNumber": types.Schema(type=types.Type.STRING, description="Medical record number or empty string"),
        "patientDemographics_date": types.Schema(type=types.Type.STRING, description="Consultation date in YYYY-MM-DD or DD-MM-YYYY format or empty string"),
        "patientDemographics_patientName": types.Schema(type=types.Type.STRING, description="Full student name or empty string"),
        "patientDemographics_age": types.Schema(type=types.Type.STRING, description="Student age with unit (e.g., '45 years') or empty string"),
        "patientDemographics_gender": types.Schema(type=types.Type.STRING, description="Male, Female, Other, or empty string"),

        # ========== SECTION 2: CLINICAL HISTORY (7 fields) ==========
        "clinicalHistory_complaints": types.Schema(type=types.Type.STRING, description="Chief complaints and presenting symptoms or N/A"),
        "clinicalHistory_pastHistory": types.Schema(type=types.Type.STRING, description="Past ocular and medical history or N/A"),
        "clinicalHistory_systemicIllness": types.Schema(type=types.Type.STRING, description="Current systemic medical conditions or N/A"),
        "clinicalHistory_familyHistory": types.Schema(type=types.Type.STRING, description="Relevant family history of eye or systemic diseases or N/A"),
        "clinicalHistory_allergy": types.Schema(type=types.Type.STRING, description="Known allergies (medications, preservatives) or N/A"),
        "clinicalHistory_currentTreatment": types.Schema(type=types.Type.STRING, description="Current medications and eye drops or N/A"),
        "clinicalHistory_pgp": types.Schema(type=types.Type.STRING, description="Previous glasses prescription or N/A"),

        # ========== SECTION 3: VISUAL ACUITY (4 fields - bilateral, 2 levels) ==========
        "visualAcuity_rightEye_distance": types.Schema(type=types.Type.STRING, description="Right eye distance visual acuity (Snellen notation e.g., 20/20, 6/6, CF, HM) or N/A"),
        "visualAcuity_rightEye_near": types.Schema(type=types.Type.STRING, description="Right eye near visual acuity (e.g., N6, J2, 20/30) or N/A"),
        "visualAcuity_leftEye_distance": types.Schema(type=types.Type.STRING, description="Left eye distance visual acuity (Snellen notation) or N/A"),
        "visualAcuity_leftEye_near": types.Schema(type=types.Type.STRING, description="Left eye near visual acuity or N/A"),

        # ========== SECTION 4: REFRACTION (6 fields - bilateral, 3 levels) ==========
        "refraction_objective_rightEye": types.Schema(type=types.Type.STRING, description="Right eye objective refraction in format Sph / Cyl × Axis (e.g., +2.00 / -0.75 × 90, -3.50 DS, Plano) or N/A"),
        "refraction_objective_leftEye": types.Schema(type=types.Type.STRING, description="Left eye objective refraction in format Sph / Cyl × Axis or N/A"),
        "refraction_subjective_rightEye_distance": types.Schema(type=types.Type.STRING, description="Right eye subjective distance refraction or N/A"),
        "refraction_subjective_rightEye_near": types.Schema(type=types.Type.STRING, description="Right eye subjective near refraction (may include add) or N/A"),
        "refraction_subjective_leftEye_distance": types.Schema(type=types.Type.STRING, description="Left eye subjective distance refraction or N/A"),
        "refraction_subjective_leftEye_near": types.Schema(type=types.Type.STRING, description="Left eye subjective near refraction (may include add) or N/A"),

        # ========== SECTION 5: MUSCLE BALANCE (4 fields) ==========
        "muscleBalance_eom": types.Schema(type=types.Type.STRING, description="Extraocular movements (e.g., Full in all gazes OU, Restriction noted) or N/A"),
        "muscleBalance_coverTest": types.Schema(type=types.Type.STRING, description="General cover test findings or N/A"),
        "muscleBalance_coverTestDistance": types.Schema(type=types.Type.STRING, description="Cover test at distance with magnitude (e.g., Orthophoria, Exophoria 6PD) or N/A"),
        "muscleBalance_coverTestNear": types.Schema(type=types.Type.STRING, description="Cover test at near with magnitude or N/A"),

        # ========== SECTION 7: INTRAOCULAR PRESSURE (4 fields) ==========
        "intraocularPressure_rightEye": types.Schema(type=types.Type.STRING, description="Right eye IOP with unit (e.g., 16 mmHg) or N/A"),
        "intraocularPressure_leftEye": types.Schema(type=types.Type.STRING, description="Left eye IOP with unit (e.g., 18 mmHg) or N/A"),
        "intraocularPressure_time": types.Schema(type=types.Type.STRING, description="Time of measurement in HH:MM format or description or empty string"),
        "intraocularPressure_method": types.Schema(type=types.Type.STRING, description="Measurement method: Goldmann, NCT, iCare, Tonopen, or empty string"),

        # ========== SECTION 8: GONIOSCOPY (2 fields - bilateral) ==========
        "gonioscopy_rightEye": types.Schema(type=types.Type.STRING, description="Right eye angle findings (e.g., Open angle, all structures visible, Narrow angle, Grade 2) or N/A"),
        "gonioscopy_leftEye": types.Schema(type=types.Type.STRING, description="Left eye angle findings or N/A"),

        # ========== SECTION 12: PROVIDER INFORMATION (2 fields) ==========
        "providerInformation_signature": types.Schema(type=types.Type.STRING, description="Ophthalmologist signature/name or empty string"),
        "providerInformation_providerName": types.Schema(type=types.Type.STRING, description="Full name with credentials or empty string")
    }
)

# ============================================================================
# PART 2: SLIT LAMP & FUNDUS EXAMINATION (38 fields)
# ============================================================================

OPHTHAL_PART2_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== SECTION 6: SLIT LAMP EXAMINATION (12 fields - bilateral) ==========
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

        # ========== SECTION 9: FUNDUS EXAMINATION (26 fields - bilateral, 4 levels deep) ==========
        # Right Eye - Optic Disc (4 fields)
        "fundusExamination_rightEye_opticDisc_cdRatio": types.Schema(type=types.Type.STRING, description="Right eye cup-to-disc ratio as decimal (e.g., 0.3, 0.5, 0.7) or N/A"),
        "fundusExamination_rightEye_opticDisc_color": types.Schema(type=types.Type.STRING, description="Right eye disc color (e.g., pink, pale, hyperemic) or N/A"),
        "fundusExamination_rightEye_opticDisc_margins": types.Schema(type=types.Type.STRING, description="Right eye disc margins (e.g., sharp, blurred) or N/A"),
        "fundusExamination_rightEye_opticDisc_neovascularization": types.Schema(type=types.Type.STRING, description="Right eye disc neovascularization: Present, Absent, or N/A"),
        # Right Eye - Macula (2 fields)
        "fundusExamination_rightEye_macula_fovealReflex": types.Schema(type=types.Type.STRING, description="Right eye foveal reflex: Present, Absent, or N/A"),
        "fundusExamination_rightEye_macula_findings": types.Schema(type=types.Type.STRING, description="Right eye macular findings (drusen, hemorrhages, exudates, edema) or N/A"),
        # Right Eye - Vessels (3 fields)
        "fundusExamination_rightEye_vessels_avRatio": types.Schema(type=types.Type.STRING, description="Right eye arteriole:venule ratio (e.g., 2:3) or N/A"),
        "fundusExamination_rightEye_vessels_caliber": types.Schema(type=types.Type.STRING, description="Right eye vessel caliber (normal, attenuated, dilated) or N/A"),
        "fundusExamination_rightEye_vessels_findings": types.Schema(type=types.Type.STRING, description="Right eye vessel findings (tortuosity, hemorrhages, etc.) or N/A"),
        # Right Eye - Periphery (2 fields)
        "fundusExamination_rightEye_periphery_retina": types.Schema(type=types.Type.STRING, description="Right eye peripheral retina findings (attached, detached, holes, tears, lattice) or N/A"),
        "fundusExamination_rightEye_periphery_vitreous": types.Schema(type=types.Type.STRING, description="Right eye vitreous findings (clear, hemorrhage, floaters, PVD) or N/A"),
        # Right Eye - Drawing
        "fundusExamination_rightEye_drawing": types.Schema(type=types.Type.STRING, description="Right eye fundus drawing annotations if mentioned or empty string"),

        # Left Eye - Optic Disc (4 fields)
        "fundusExamination_leftEye_opticDisc_cdRatio": types.Schema(type=types.Type.STRING, description="Left eye cup-to-disc ratio as decimal or N/A"),
        "fundusExamination_leftEye_opticDisc_color": types.Schema(type=types.Type.STRING, description="Left eye disc color or N/A"),
        "fundusExamination_leftEye_opticDisc_margins": types.Schema(type=types.Type.STRING, description="Left eye disc margins or N/A"),
        "fundusExamination_leftEye_opticDisc_neovascularization": types.Schema(type=types.Type.STRING, description="Left eye disc neovascularization: Present, Absent, or N/A"),
        # Left Eye - Macula (2 fields)
        "fundusExamination_leftEye_macula_fovealReflex": types.Schema(type=types.Type.STRING, description="Left eye foveal reflex: Present, Absent, or N/A"),
        "fundusExamination_leftEye_macula_findings": types.Schema(type=types.Type.STRING, description="Left eye macular findings or N/A"),
        # Left Eye - Vessels (3 fields)
        "fundusExamination_leftEye_vessels_avRatio": types.Schema(type=types.Type.STRING, description="Left eye arteriole:venule ratio or N/A"),
        "fundusExamination_leftEye_vessels_caliber": types.Schema(type=types.Type.STRING, description="Left eye vessel caliber or N/A"),
        "fundusExamination_leftEye_vessels_findings": types.Schema(type=types.Type.STRING, description="Left eye vessel findings or N/A"),
        # Left Eye - Periphery (2 fields)
        "fundusExamination_leftEye_periphery_retina": types.Schema(type=types.Type.STRING, description="Left eye peripheral retina findings or N/A"),
        "fundusExamination_leftEye_periphery_vitreous": types.Schema(type=types.Type.STRING, description="Left eye vitreous findings or N/A"),
        # Left Eye - Drawing
        "fundusExamination_leftEye_drawing": types.Schema(type=types.Type.STRING, description="Left eye fundus drawing annotations if mentioned or empty string"),

        # ========== SECTION 10: DIAGNOSIS (1 field - array) ==========
        "diagnosis": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Diagnosis with eye specification (e.g., 'OD: Cataract', 'OU: Diabetic retinopathy')"),
            description="Array of all diagnoses (empty array if none)"
        ),

        # ========== SECTION 11: ADVICE AND FOLLOW-UP (1 field) ==========
        "adviceAndFollowUp": types.Schema(
            type=types.Type.STRING,
            description="Management plan including medications, follow-up timing, lifestyle advice, investigations ordered, surgical recommendations or N/A"
        )
    }
)

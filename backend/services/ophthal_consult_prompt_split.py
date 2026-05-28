"""
Split OPHTHAL_FULL Schema for Gemini API Compatibility

The flattened schema (130+ properties) may exceed Gemini's constraint limits.
This module splits the extraction into TWO separate API calls:

PART 1 (76 fields): PATIENT DATA & PRIMARY EXAMINATION
- Patient demographics (7 fields, including doctorName)
- Extended history (4 fields - systemicIllness, familyHistory, allergies, pastGlassesPrescription)
- Clinical history (3 fields)
- Visual acuity and refraction (18 fields - bilateral with pinhole, nearAdd, nearVision)
- Keratometry (8 fields - bilateral)
- Cover tests with/without glass (12 fields)
- Binocular vision tests (12 fields)
- Macular function tests (4 fields)
- PBCT charts (2 fields)
- Diplopia charting (1 field)

PART 2 (58 fields): ADVANCED EXAMINATION & MANAGEMENT
- Dry eye assessment (11 fields)
- Slit lamp examination (bilateral - 15 fields)
- Intraocular pressure (8 fields for measurements + 4 pachymetry)
- Gonioscopy (1 field)
- Fundus examination (7 fields)
- Diurnal IOP variation (4 parallel arrays)
- Visual field analysis (8 fields)
- Diagnosis, procedures, recommendations, notes (5 fields)
- Document metadata (4 fields - formSubtype, referralType, nextReview, sourceSchema)
- Quality metadata (1 field - lowConfidenceFields)

The ophthal_consult_formatter.py service merges both results into the final nested structure.
"""

from google.genai import types

# ============================================================================
# PART 1: PATIENT DATA & PRIMARY EXAMINATION (65 fields)
# ============================================================================

OPHTHAL_FULL_PART1_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== SECTION 1: PATIENT DEMOGRAPHICS (7 fields) ==========
        "patientDemographics_name": types.Schema(type=types.Type.STRING, description="Patient full name or empty string"),
        "patientDemographics_mrNumber": types.Schema(type=types.Type.STRING, description="Medical record number or empty string"),
        "patientDemographics_age": types.Schema(type=types.Type.STRING, description="Patient age with unit (e.g., '45 years', '6 months') or empty string"),
        "patientDemographics_gender": types.Schema(type=types.Type.STRING, description="Male, Female, Other, or empty string"),
        "patientDemographics_consultationDate": types.Schema(type=types.Type.STRING, description="Date in YYYY-MM-DD format or empty string"),
        "patientDemographics_visitId": types.Schema(type=types.Type.STRING, description="Visit/appointment ID or empty string"),
        "patientDemographics_doctorName": types.Schema(type=types.Type.STRING, description="Consulting doctor name or empty string"),

        # ========== SECTION 1A: EXTENDED HISTORY (4 fields - NEW) ==========
        "extendedHistory_systemicIllness": types.Schema(type=types.Type.STRING, description="Systemic diseases affecting eyes or empty string"),
        "extendedHistory_familyHistory": types.Schema(type=types.Type.STRING, description="Family history of eye conditions or empty string"),
        "extendedHistory_allergies": types.Schema(type=types.Type.STRING, description="Drug or environmental allergies or empty string"),
        "extendedHistory_pastGlassesPrescription": types.Schema(type=types.Type.STRING, description="Previous glasses prescription or empty string"),

        # ========== SECTIONS 2-4: CLINICAL HISTORY (3 fields) ==========
        "pastOcularHistory": types.Schema(type=types.Type.STRING, description="Past eye conditions, surgeries, treatments, or N/A"),
        "currentTreatment": types.Schema(type=types.Type.STRING, description="Current eye medications and treatments, or N/A"),
        "complaints": types.Schema(type=types.Type.STRING, description="Chief complaints and symptoms, or N/A"),

        # ========== SECTION 5: VISUAL ACUITY AND REFRACTION (18 fields - bilateral with new fields) ==========
        "visualAcuityAndRefraction_rightEye_unaidedVision": types.Schema(type=types.Type.STRING, description="Right eye Snellen notation (e.g., 6/60, 20/20) or N/A"),
        "visualAcuityAndRefraction_rightEye_aidedVision": types.Schema(type=types.Type.STRING, description="Right eye vision with correction or N/A"),
        "visualAcuityAndRefraction_rightEye_patientGlasses": types.Schema(type=types.Type.STRING, description="Right eye vision with patient's own glasses or N/A"),
        "visualAcuityAndRefraction_rightEye_pinholeVision": types.Schema(type=types.Type.STRING, description="Right eye vision with pinhole or N/A"),
        "visualAcuityAndRefraction_rightEye_nearAdd": types.Schema(type=types.Type.STRING, description="Right eye near addition power for presbyopia or N/A"),
        "visualAcuityAndRefraction_rightEye_nearVision": types.Schema(type=types.Type.STRING, description="Right eye near vision (N notation) or N/A"),
        "visualAcuityAndRefraction_rightEye_refractionSphere": types.Schema(type=types.Type.NUMBER, description="Right eye sphere power in diopters", nullable=True),
        "visualAcuityAndRefraction_rightEye_refractionCylinder": types.Schema(type=types.Type.NUMBER, description="Right eye cylinder power in diopters", nullable=True),
        "visualAcuityAndRefraction_rightEye_refractionAxis": types.Schema(type=types.Type.NUMBER, description="Right eye axis in degrees (0-180)", nullable=True),
        "visualAcuityAndRefraction_leftEye_unaidedVision": types.Schema(type=types.Type.STRING, description="Left eye Snellen notation or N/A"),
        "visualAcuityAndRefraction_leftEye_aidedVision": types.Schema(type=types.Type.STRING, description="Left eye vision with correction or N/A"),
        "visualAcuityAndRefraction_leftEye_patientGlasses": types.Schema(type=types.Type.STRING, description="Left eye vision with patient's own glasses or N/A"),
        "visualAcuityAndRefraction_leftEye_pinholeVision": types.Schema(type=types.Type.STRING, description="Left eye vision with pinhole or N/A"),
        "visualAcuityAndRefraction_leftEye_nearAdd": types.Schema(type=types.Type.STRING, description="Left eye near addition power for presbyopia or N/A"),
        "visualAcuityAndRefraction_leftEye_nearVision": types.Schema(type=types.Type.STRING, description="Left eye near vision (N notation) or N/A"),
        "visualAcuityAndRefraction_leftEye_refractionSphere": types.Schema(type=types.Type.NUMBER, description="Left eye sphere power in diopters", nullable=True),
        "visualAcuityAndRefraction_leftEye_refractionCylinder": types.Schema(type=types.Type.NUMBER, description="Left eye cylinder power in diopters", nullable=True),
        "visualAcuityAndRefraction_leftEye_refractionAxis": types.Schema(type=types.Type.NUMBER, description="Left eye axis in degrees (0-180)", nullable=True),

        # ========== SECTION 6: KERATOMETRY (8 fields - bilateral) ==========
        "keratometry_rightEye_horizontal": types.Schema(type=types.Type.NUMBER, description="Right eye horizontal K reading in diopters", nullable=True),
        "keratometry_rightEye_horizontalAxis": types.Schema(type=types.Type.NUMBER, description="Right eye horizontal axis in degrees", nullable=True),
        "keratometry_rightEye_vertical": types.Schema(type=types.Type.NUMBER, description="Right eye vertical K reading in diopters", nullable=True),
        "keratometry_rightEye_verticalAxis": types.Schema(type=types.Type.NUMBER, description="Right eye vertical axis in degrees", nullable=True),
        "keratometry_leftEye_horizontal": types.Schema(type=types.Type.NUMBER, description="Left eye horizontal K reading in diopters", nullable=True),
        "keratometry_leftEye_horizontalAxis": types.Schema(type=types.Type.NUMBER, description="Left eye horizontal axis in degrees", nullable=True),
        "keratometry_leftEye_vertical": types.Schema(type=types.Type.NUMBER, description="Left eye vertical K reading in diopters", nullable=True),
        "keratometry_leftEye_verticalAxis": types.Schema(type=types.Type.NUMBER, description="Left eye vertical axis in degrees", nullable=True),

        # ========== SECTION 7: COVER TEST WITH GLASS (6 fields) ==========
        "coverTestWithGlass_coverTestDist": types.Schema(type=types.Type.STRING, description="Distance cover test result or N/A"),
        "coverTestWithGlass_coverTestNear": types.Schema(type=types.Type.STRING, description="Near cover test result or N/A"),
        "coverTestWithGlass_uncoverTestDist": types.Schema(type=types.Type.STRING, description="Distance uncover test result or N/A"),
        "coverTestWithGlass_uncoverTestNear": types.Schema(type=types.Type.STRING, description="Near uncover test result or N/A"),
        "coverTestWithGlass_alternateCoverTestDist": types.Schema(type=types.Type.STRING, description="Distance alternate cover test or N/A"),
        "coverTestWithGlass_alternateCoverTestNear": types.Schema(type=types.Type.STRING, description="Near alternate cover test or N/A"),

        # ========== SECTION 8: COVER TEST WITHOUT GLASS (6 fields) ==========
        "coverTestWithoutGlass_coverTestDist": types.Schema(type=types.Type.STRING, description="Distance cover test result or N/A"),
        "coverTestWithoutGlass_coverTestNear": types.Schema(type=types.Type.STRING, description="Near cover test result or N/A"),
        "coverTestWithoutGlass_uncoverTestDist": types.Schema(type=types.Type.STRING, description="Distance uncover test result or N/A"),
        "coverTestWithoutGlass_uncoverTestNear": types.Schema(type=types.Type.STRING, description="Near uncover test result or N/A"),
        "coverTestWithoutGlass_alternateCoverTestDist": types.Schema(type=types.Type.STRING, description="Distance alternate cover test or N/A"),
        "coverTestWithoutGlass_alternateCoverTestNear": types.Schema(type=types.Type.STRING, description="Near alternate cover test or N/A"),

        # ========== SECTION 9: BINOCULAR VISION TESTS (12 fields) ==========
        "binocularVisionTests_fixationDist": types.Schema(type=types.Type.STRING, description="Distance fixation assessment or N/A"),
        "binocularVisionTests_fixationNear": types.Schema(type=types.Type.STRING, description="Near fixation assessment or N/A"),
        "binocularVisionTests_stereopsisDist": types.Schema(type=types.Type.STRING, description="Distance stereopsis result or N/A"),
        "binocularVisionTests_stereopsisNear": types.Schema(type=types.Type.STRING, description="Near stereopsis result (e.g., seconds of arc) or N/A"),
        "binocularVisionTests_avPatternDist": types.Schema(type=types.Type.STRING, description="A/V pattern distance or N/A"),
        "binocularVisionTests_avPatternNear": types.Schema(type=types.Type.STRING, description="A/V pattern near or N/A"),
        "binocularVisionTests_worthFourDotDist": types.Schema(type=types.Type.STRING, description="Worth Four Dot test distance or N/A"),
        "binocularVisionTests_worthFourDotNear": types.Schema(type=types.Type.STRING, description="Worth Four Dot test near or N/A"),
        "binocularVisionTests_bagoliniDist": types.Schema(type=types.Type.STRING, description="Bagolini test distance or N/A"),
        "binocularVisionTests_bagoliniNear": types.Schema(type=types.Type.STRING, description="Bagolini test near or N/A"),
        "binocularVisionTests_faceExternalExamDist": types.Schema(type=types.Type.STRING, description="Face/external eye exam distance or N/A"),
        "binocularVisionTests_faceExternalExamNear": types.Schema(type=types.Type.STRING, description="Face/external eye exam near or N/A"),

        # ========== SECTION 10: MACULAR FUNCTION TESTS (4 fields) ==========
        "macularFunctionTests_colorVisionOD": types.Schema(type=types.Type.STRING, description="Right eye color vision test result or N/A"),
        "macularFunctionTests_colorVisionOS": types.Schema(type=types.Type.STRING, description="Left eye color vision test result or N/A"),
        "macularFunctionTests_amslersTestOD": types.Schema(type=types.Type.STRING, description="Right eye Amsler grid test result or N/A"),
        "macularFunctionTests_amslersTestOS": types.Schema(type=types.Type.STRING, description="Left eye Amsler grid test result or N/A"),

        # ========== SECTION 11: PBCT CHARTS (2 fields - 2D arrays) ==========
        "pbctCharts_pbctOD": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING, description="Prism diopter value or direction"),
                description="Row of PBCT measurements"
            ),
            description="Right eye PBCT 3x3 grid measurements (array of 3 arrays, empty array if none)"
        ),
        "pbctCharts_pbctOS": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING, description="Prism diopter value or direction"),
                description="Row of PBCT measurements"
            ),
            description="Left eye PBCT 3x3 grid measurements (array of 3 arrays, empty array if none)"
        ),

        # ========== SECTION 12: DIPLOPIA CHARTING (1 field) ==========
        "diplopiaCharting": types.Schema(type=types.Type.STRING, description="Diplopia charting notes, drawings description, or N/A"),
    }
)

# ============================================================================
# PART 2: ADVANCED EXAMINATION & MANAGEMENT (53 fields)
# ============================================================================

OPHTHAL_FULL_PART2_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== SECTION 13: DRY EYE ASSESSMENT (11 fields) ==========
        "dryEyeAssessment_osdiQuestionnaire": types.Schema(type=types.Type.STRING, description="OSDI questionnaire score or result or N/A"),
        "dryEyeAssessment_schimersTest1OD": types.Schema(type=types.Type.NUMBER, description="Right eye Schirmer's I without anesthesia (mm)", nullable=True),
        "dryEyeAssessment_schimersTest1OS": types.Schema(type=types.Type.NUMBER, description="Left eye Schirmer's I without anesthesia (mm)", nullable=True),
        "dryEyeAssessment_schimersTest2OD": types.Schema(type=types.Type.NUMBER, description="Right eye Schirmer's II with anesthesia (mm)", nullable=True),
        "dryEyeAssessment_schimersTest2OS": types.Schema(type=types.Type.NUMBER, description="Left eye Schirmer's II with anesthesia (mm)", nullable=True),
        "dryEyeAssessment_tearFilmBreakupTimeOD": types.Schema(type=types.Type.NUMBER, description="Right eye TBUT in seconds", nullable=True),
        "dryEyeAssessment_tearFilmBreakupTimeOS": types.Schema(type=types.Type.NUMBER, description="Left eye TBUT in seconds", nullable=True),
        "dryEyeAssessment_fluoresceinStainingOD": types.Schema(type=types.Type.STRING, description="Right eye fluorescein staining score or N/A"),
        "dryEyeAssessment_fluoresceinStainingOS": types.Schema(type=types.Type.STRING, description="Left eye fluorescein staining score or N/A"),
        "dryEyeAssessment_lissamineGreenOD": types.Schema(type=types.Type.STRING, description="Right eye lissamine green staining or N/A"),
        "dryEyeAssessment_lissamineGreenOS": types.Schema(type=types.Type.STRING, description="Left eye lissamine green staining or N/A"),

        # ========== SECTION 14: SLIT LAMP EXAMINATION (15 fields - bilateral + notes) ==========
        "slitLampExamination_rightEye_lids": types.Schema(type=types.Type.STRING, description="Right eye eyelid findings or N/A"),
        "slitLampExamination_rightEye_conjunctiva": types.Schema(type=types.Type.STRING, description="Right eye conjunctival findings or N/A"),
        "slitLampExamination_rightEye_cornea": types.Schema(type=types.Type.STRING, description="Right eye corneal findings or N/A"),
        "slitLampExamination_rightEye_anteriorChamber": types.Schema(type=types.Type.STRING, description="Right eye AC depth, cells, flare, Van Herick grading or N/A"),
        "slitLampExamination_rightEye_iris": types.Schema(type=types.Type.STRING, description="Right eye iris findings or N/A"),
        "slitLampExamination_rightEye_lens": types.Schema(type=types.Type.STRING, description="Right eye lens clarity, nuclear sclerosis grade or N/A"),
        "slitLampExamination_rightEye_pupil": types.Schema(type=types.Type.STRING, description="Right eye pupil size, reactivity, RAPD or N/A"),
        "slitLampExamination_leftEye_lids": types.Schema(type=types.Type.STRING, description="Left eye eyelid findings or N/A"),
        "slitLampExamination_leftEye_conjunctiva": types.Schema(type=types.Type.STRING, description="Left eye conjunctival findings or N/A"),
        "slitLampExamination_leftEye_cornea": types.Schema(type=types.Type.STRING, description="Left eye corneal findings or N/A"),
        "slitLampExamination_leftEye_anteriorChamber": types.Schema(type=types.Type.STRING, description="Left eye AC depth, cells, flare, Van Herick grading or N/A"),
        "slitLampExamination_leftEye_iris": types.Schema(type=types.Type.STRING, description="Left eye iris findings or N/A"),
        "slitLampExamination_leftEye_lens": types.Schema(type=types.Type.STRING, description="Left eye lens clarity, nuclear sclerosis grade or N/A"),
        "slitLampExamination_leftEye_pupil": types.Schema(type=types.Type.STRING, description="Left eye pupil size, reactivity, RAPD or N/A"),
        "slitLampExamination_imageNotes": types.Schema(type=types.Type.STRING, description="Notes about slit lamp images or N/A"),

        # ========== SECTION 15: INTRAOCULAR PRESSURE (8 fields - parallel arrays + pachymetry) ==========
        "intraocularpressure_methods": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Measurement method (Applanation, NCT, iCare, etc.)"),
            description="Array of IOP measurement methods (empty array if none)"
        ),
        "intraocularpressure_times": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Time of measurement (HH:MM format) or empty string"),
            description="Array of IOP measurement times (parallel to methods, empty array if none)"
        ),
        "intraocularpressure_rightEyeIOPs": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.NUMBER, description="Right eye IOP in mm Hg", nullable=True),
            description="Array of right eye IOP values (parallel to methods, empty array if none)"
        ),
        "intraocularpressure_leftEyeIOPs": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.NUMBER, description="Left eye IOP in mm Hg", nullable=True),
            description="Array of left eye IOP values (parallel to methods, empty array if none)"
        ),
        "intraocularpressure_pachymetryOD": types.Schema(type=types.Type.NUMBER, description="Right eye central corneal thickness in microns", nullable=True),
        "intraocularpressure_pachymetryOS": types.Schema(type=types.Type.NUMBER, description="Left eye central corneal thickness in microns", nullable=True),
        "intraocularpressure_pachymetryAdjustedIOPOD": types.Schema(type=types.Type.NUMBER, description="Right eye pachymetry-adjusted IOP in mm Hg", nullable=True),
        "intraocularpressure_pachymetryAdjustedIOPOS": types.Schema(type=types.Type.NUMBER, description="Left eye pachymetry-adjusted IOP in mm Hg", nullable=True),

        # ========== SECTION 16: GONIOSCOPY (1 field) ==========
        "gonioscopy": types.Schema(type=types.Type.STRING, description="Gonioscopy findings for angle assessment or N/A"),

        # ========== SECTION 17: FUNDUS EXAMINATION (7 fields - bilateral) ==========
        "fundusExamination_dilationStatus": types.Schema(type=types.Type.STRING, description="Dilated, Undilated, or N/A"),
        "fundusExamination_rightEye_disc": types.Schema(type=types.Type.STRING, description="Right eye optic disc appearance, CDR (e.g., 0.55 CDR) or N/A"),
        "fundusExamination_rightEye_macula": types.Schema(type=types.Type.STRING, description="Right eye macular findings or N/A"),
        "fundusExamination_rightEye_generalFundus": types.Schema(type=types.Type.STRING, description="Right eye vessels, periphery, other findings or N/A"),
        "fundusExamination_leftEye_disc": types.Schema(type=types.Type.STRING, description="Left eye optic disc appearance, CDR or N/A"),
        "fundusExamination_leftEye_macula": types.Schema(type=types.Type.STRING, description="Left eye macular findings or N/A"),
        "fundusExamination_leftEye_generalFundus": types.Schema(type=types.Type.STRING, description="Left eye vessels, periphery, other findings or N/A"),

        # ========== SECTION 18: DIURNAL IOP VARIATION (4 fields - parallel arrays) ==========
        "diurnalIOPVariation_methods": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Measurement method (usually Applanation)"),
            description="Array of diurnal IOP measurement methods (empty array if none)"
        ),
        "diurnalIOPVariation_times": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Time of measurement (HH:MM format)"),
            description="Array of diurnal IOP measurement times (parallel to methods, empty array if none)"
        ),
        "diurnalIOPVariation_rightEyeIOPs": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.NUMBER, description="Right eye IOP in mm Hg", nullable=True),
            description="Array of right eye diurnal IOP values (parallel to methods, empty array if none)"
        ),
        "diurnalIOPVariation_leftEyeIOPs": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.NUMBER, description="Left eye IOP in mm Hg", nullable=True),
            description="Array of left eye diurnal IOP values (parallel to methods, empty array if none)"
        ),

        # ========== SECTION 19: VISUAL FIELD ANALYSIS (8 fields) ==========
        "visualFieldAnalysis_strategy": types.Schema(type=types.Type.STRING, description="Testing strategy (e.g., SITA Standard, SITA Fast) or N/A"),
        "visualFieldAnalysis_interpretation": types.Schema(type=types.Type.STRING, description="Visual field interpretation or N/A"),
        "visualFieldAnalysis_meanDeviation": types.Schema(type=types.Type.STRING, description="MD value with sign (e.g., -3.2 dB) or N/A"),
        "visualFieldAnalysis_patternDeviation": types.Schema(type=types.Type.STRING, description="PSD value or N/A"),
        "visualFieldAnalysis_ght": types.Schema(type=types.Type.STRING, description="Glaucoma Hemifield Test result or N/A"),
        "visualFieldAnalysis_vfi": types.Schema(type=types.Type.STRING, description="Visual Field Index percentage or N/A"),
        "visualFieldAnalysis_oct": types.Schema(type=types.Type.STRING, description="OCT findings or N/A"),
        "visualFieldAnalysis_targetIOP": types.Schema(type=types.Type.STRING, description="Target IOP recommendation or N/A"),

        # ========== SECTIONS 20-23: DIAGNOSIS & MANAGEMENT (5 fields) ==========
        "diagnosis": types.Schema(type=types.Type.STRING, description="Primary and secondary diagnoses with eye specification or N/A"),
        "procedures": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Procedure name or description"),
            description="Procedures performed during visit (empty array if none)"
        ),
        "doctorRecommendation": types.Schema(type=types.Type.STRING, description="Treatment plan, medications, follow-up instructions or N/A"),
        "doctorNotes": types.Schema(type=types.Type.STRING, description="Additional clinical notes or observations or N/A"),
        "investigation": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Investigation name or test ordered"),
            description="Investigations ordered (empty array if none)"
        ),

        # ========== SECTION 24: DOCUMENT METADATA (4 fields - NEW OPTIONAL) ==========
        "documentMetadata_formSubtype": types.Schema(type=types.Type.STRING, description="Form subtype: GENERAL, GLAUCOMA, CATARACT, RETINA, PEDIATRIC, STRABISMUS"),
        "documentMetadata_referralType": types.Schema(type=types.Type.STRING, description="Referral type: INTERNAL, EXTERNAL, SELF, or empty string"),
        "documentMetadata_nextReview": types.Schema(type=types.Type.STRING, description="Next review date or duration (e.g., '6 months')"),
        "documentMetadata_sourceSchema": types.Schema(type=types.Type.STRING, description="Source schema identifier for imported data"),

        # ========== SECTION 25: QUALITY METADATA (1 field - NEW OPTIONAL) ==========
        "qualityMetadata_lowConfidenceFields": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Field path with low extraction confidence"),
            description="Array of field paths with low confidence"
        )
    }
)

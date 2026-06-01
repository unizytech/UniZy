"""
Split OPHTHAL_DISCHARGE Schema for Gemini API Compatibility

The flattened schema (42 properties) may approach Gemini's constraint limits,
especially with the nested arrays for medications and counsellors.
This module splits the extraction into TWO separate API calls:

PART 1 (23 fields): STUDENT DATA & TREATMENT
- Student demographics (6 fields)
- Admission details (2 fields)
- Medical team (2 parallel arrays for counsellors)
- Diagnosis (3 fields - bilateral)
- Admission status (2 fields)
- Treatment given (6 fields)
- Discharge status (1 field)
- Provider information (3 fields)

PART 2 (19 fields): MEDICATIONS & DISCHARGE INSTRUCTIONS
- Discharge medication (8 parallel arrays)
- Discharge advice (4 fields including special instructions array)
- Emergency contact (5 fields including symptoms array)

The ophthal_discharge_formatter.py service merges both results into the final nested structure.
"""

from google.genai import types

# ============================================================================
# PART 1: STUDENT DATA & TREATMENT (23 fields)
# ============================================================================

OPHTHAL_DISCHARGE_PART1_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== SECTION 1: STUDENT DEMOGRAPHICS (6 fields) ==========
        "patientDemographics_name": types.Schema(type=types.Type.STRING, description="Student full name or empty string"),
        "patientDemographics_visitId": types.Schema(type=types.Type.STRING, description="Visit/episode ID or empty string"),
        "patientDemographics_mrNumber": types.Schema(type=types.Type.STRING, description="Medical record number or empty string"),
        "patientDemographics_date": types.Schema(type=types.Type.STRING, description="Discharge summary date in DD-MM-YYYY format or empty string"),
        "patientDemographics_age": types.Schema(type=types.Type.STRING, description="Student age with unit (e.g., '45 years') or empty string"),
        "patientDemographics_gender": types.Schema(type=types.Type.STRING, description="Male, Female, Other, or empty string"),

        # ========== SECTION 2: ADMISSION DETAILS (2 fields) ==========
        "admissionDetails_dateOfAdmission": types.Schema(type=types.Type.STRING, description="School admission date in DD-MM-YYYY format"),
        "admissionDetails_dateOfProcedure": types.Schema(type=types.Type.STRING, description="Surgical/procedure date in DD-MM-YYYY format"),

        # ========== SECTION 3: MEDICAL TEAM (2 parallel arrays) ==========
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

        # ========== SECTION 4: DIAGNOSIS (3 fields - bilateral) ==========
        "diagnosis_rightEye": types.Schema(type=types.Type.STRING, description="Right eye (OD) diagnosis or N/A"),
        "diagnosis_leftEye": types.Schema(type=types.Type.STRING, description="Left eye (OS) diagnosis or N/A"),
        "diagnosis_bothEyes": types.Schema(type=types.Type.STRING, description="Both eyes (OU) diagnosis or N/A"),

        # ========== SECTION 5: ADMISSION STATUS (2 fields) ==========
        "admissionStatus_conditionOnAdmission": types.Schema(type=types.Type.STRING, description="General condition at admission (e.g., fair, good, stable) or N/A"),
        "admissionStatus_nutritionalStatus": types.Schema(type=types.Type.STRING, description="Normal, Well-nourished, Malnourished, or N/A"),

        # ========== SECTION 6: TREATMENT GIVEN (6 fields) ==========
        "treatmentGiven_eye": types.Schema(type=types.Type.STRING, description="Right Eye, Left Eye, or Both Eyes"),
        "treatmentGiven_procedure": types.Schema(type=types.Type.STRING, description="Procedure name in CAPITALS (e.g., PTERYGIUM EXCISION WITH CONJUNCTIVAL AUTOGRAFT)"),
        "treatmentGiven_technique": types.Schema(type=types.Type.STRING, description="Surgical technique details or empty string"),
        "treatmentGiven_anesthesia": types.Schema(type=types.Type.STRING, description="Local, General, Topical, Peribulbar, Retrobulbar, or empty string"),
        "treatmentGiven_date": types.Schema(type=types.Type.STRING, description="Procedure date in DD-MM-YYYY format"),
        "treatmentGiven_additionalDetails": types.Schema(type=types.Type.STRING, description="Additional procedure information or empty string"),

        # ========== SECTION 7: DISCHARGE STATUS (1 field) ==========
        "dischargeStatus_conditionOnDischarge": types.Schema(type=types.Type.STRING, description="Condition at discharge (Good, Stable, Satisfactory, Comfortable) or N/A"),

        # ========== SECTION 11: PROVIDER INFORMATION (3 fields) ==========
        "providerInformation_signature": types.Schema(type=types.Type.STRING, description="Counsellor signature/name or empty string"),
        "providerInformation_registrationNumber": types.Schema(type=types.Type.STRING, description="Medical registration number or empty string"),
        "providerInformation_seal": types.Schema(type=types.Type.STRING, description="Present, Not mentioned, or empty string")
    }
)

# ============================================================================
# PART 2: MEDICATIONS & DISCHARGE INSTRUCTIONS (19 fields)
# ============================================================================

OPHTHAL_DISCHARGE_PART2_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== SECTION 8: DISCHARGE MEDICATION (8 parallel arrays) ==========
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

        # ========== SECTION 9: DISCHARGE ADVICE (4 fields) ==========
        "dischargeAdvice_diet": types.Schema(type=types.Type.STRING, description="Dietary recommendations (e.g., Normal diet, Light diet) or N/A"),
        "dischargeAdvice_physicalActivity": types.Schema(type=types.Type.STRING, description="Activity level (e.g., Normal, Avoid strenuous activities) or N/A"),
        "dischargeAdvice_specialInstructions": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Specific post-operative instruction"),
            description="Array of special instructions (e.g., not to lie on operated side, wear dark glasses, empty array if none)"
        ),
        "dischargeAdvice_nextReview": types.Schema(type=types.Type.STRING, description="Follow-up date in DD-MM-YYYY or relative timing (e.g., in 1 week)"),

        # ========== SECTION 10: EMERGENCY CONTACT (5 fields) ==========
        "emergencyContact_emergencySymptoms": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING, description="Warning symptom"),
            description="Array of emergency warning symptoms (e.g., Decrease in vision, Pain, Redness, empty array if none)"
        ),
        "emergencyContact_hospitalContactDetails_telephoneNumber": types.Schema(type=types.Type.STRING, description="School telephone number or empty string"),
        "emergencyContact_hospitalContactDetails_contactPersonName": types.Schema(type=types.Type.STRING, description="Contact person name or empty string"),
        "emergencyContact_hospitalContactDetails_mobileNumber": types.Schema(type=types.Type.STRING, description="Mobile contact number or empty string"),
        "emergencyContact_hospitalContactDetails_emergencyNumber": types.Schema(type=types.Type.STRING, description="Emergency contact number or empty string")
    }
)

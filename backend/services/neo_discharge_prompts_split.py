"""
Split NEONATAL_DISCHARGE Schema for Gemini API Compatibility

The NEONATAL_DISCHARGE schema (~80-90 properties when flattened) is borderline for Gemini's limits.
This module splits the extraction into TWO separate API calls for reliability:

PART 1 (~45 fields): CORE DISCHARGE INFO
- Patient identification (uhid, visitNumber, room/bed)
- Discharge basics (status, date, weight, measurements)
- Immunization details
- Physical exam findings
- Next appointment
- Medications array

PART 2 (~40 fields): CHECKLIST & SCREENINGS
- Blood test results
- Cranial ultrasound & echocardiography
- Hearing screening (OAE, ABR)
- ROP screening & treatment
- Procedures, infections, advice

The neo_discharge_formatter.py service merges both results into the final nested structure.
"""

from google.genai import types

# ============================================================================
# PART 1: CORE DISCHARGE INFO (~45 fields)
# ============================================================================

NEO_DISCHARGE_PART1_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== PATIENT IDENTIFICATION (6 fields) ==========
        "uhid": types.Schema(type=types.Type.STRING, description="Patient unique hospital ID or empty string"),
        "visitNumber": types.Schema(type=types.Type.STRING, description="Visit/IP number (e.g., 'IP/2502927') or empty string"),
        "roomId": types.Schema(type=types.Type.INTEGER, nullable=True, description="Room ID number or null"),
        "roomNumber": types.Schema(type=types.Type.INTEGER, nullable=True, description="Room number or null"),
        "bedId": types.Schema(type=types.Type.INTEGER, nullable=True, description="Bed ID number or null"),
        "bedNumber": types.Schema(type=types.Type.INTEGER, nullable=True, description="Bed number or null"),

        # ========== DISCHARGE BASICS (6 fields) ==========
        "discharge_status": types.Schema(type=types.Type.STRING, description="Discharge status: Discharged, Transferred, DAMA, Expired, or empty string"),
        "discharge_date": types.Schema(type=types.Type.STRING, description="Discharge date in YYYY-MM-DD format or empty string"),
        "discharge_diedTime": types.Schema(type=types.Type.STRING, description="Time of death in HH:MM format if expired, or empty string"),
        "discharge_weight": types.Schema(type=types.Type.STRING, description="Discharge weight in grams as string or empty string"),
        "discharge_ofc": types.Schema(type=types.Type.STRING, description="Head circumference (OFC) in cm as string or empty string"),
        "discharge_length": types.Schema(type=types.Type.STRING, description="Length in cm as string or empty string"),

        # ========== IMMUNIZATION (2 fields + array) ==========
        "immunization_status": types.Schema(type=types.Type.STRING, description="Immunization status: Given, Not Given, Pending, or empty string"),
        "immunization_schedule": types.Schema(type=types.Type.STRING, description="Immunization schedule (e.g., '6 wks', 'Birth dose') or empty string"),
        "immunization_vaccineIds": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.INTEGER),
            description="Array of vaccine IDs administered"
        ),
        "immunization_vaccineDates": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of vaccine dates in YYYY-MM-DD format (same order as vaccineIds)"
        ),

        # ========== PHYSICAL EXAM FINDINGS (12 fields) ==========
        "discharge_additionalInformation": types.Schema(type=types.Type.STRING, description="Additional discharge notes or empty string"),
        "discharge_eyes": types.Schema(type=types.Type.STRING, description="Eye findings: Normal, Subconjunctival Hemorrhage, Jaundiced, Other, or empty string"),
        "discharge_cardiacMurmur": types.Schema(type=types.Type.STRING, description="Cardiac murmur: Present, Absent, or empty string"),
        "discharge_postductalSaturation": types.Schema(type=types.Type.STRING, description="Post-ductal oxygen saturation percentage or empty string"),
        "discharge_femoralPulses": types.Schema(type=types.Type.STRING, description="Femoral pulses: Normal, Weak, Bounding, Absent, or empty string"),
        "discharge_hips": types.Schema(type=types.Type.STRING, description="Hip examination: Normal, DDH Rt, DDH Lt, DDH Bilateral, Suspect, or empty string"),
        "discharge_genitalia": types.Schema(type=types.Type.STRING, description="Genitalia: Normal, Abnormal, or empty string"),
        "discharge_genitaliaFindings": types.Schema(type=types.Type.STRING, description="Details if genitalia abnormal or empty string"),
        "discharge_malformation": types.Schema(type=types.Type.STRING, description="Congenital malformation: Yes, No, or empty string"),
        "discharge_malformationDetails": types.Schema(type=types.Type.STRING, description="Details of malformation if present or empty string"),
        "discharge_feeding": types.Schema(type=types.Type.STRING, description="Feeding status: Direct Breastfeed, EBM, Formula, Mixed, Paladai Fed with EBM, or empty string"),
        "discharge_neurologicalStatus": types.Schema(type=types.Type.STRING, description="Neurological status: Normal, Suspect, Abnormal, or empty string"),

        # ========== NEXT APPOINTMENT (2 fields) ==========
        "nextAppointment_status": types.Schema(type=types.Type.BOOLEAN, description="Whether follow-up appointment scheduled"),
        "nextAppointment_dateTime": types.Schema(type=types.Type.STRING, description="Follow-up date-time in YYYY-MM-DD HH:MM format or empty string"),

        # ========== MEDICATIONS (flattened arrays - up to 10 medications) ==========
        "medications_drugIds": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of drug IDs as strings"
        ),
        "medications_routes": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of route IDs/codes (same order as drugIds): 1=Oral, 2=Inhaler, 3=Syrup, 4=Drops, etc."
        ),
        "medications_doses": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of doses as strings (e.g., '1 puff', '3 ml') - same order as drugIds"
        ),
        "medications_frequencies": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of frequencies (e.g., 'Q6H', 'Q8H', 'BD', 'TDS') - same order as drugIds"
        ),
        "medications_durations": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of durations (e.g., '7 days', '1 month') - same order as drugIds"
        ),
        "medications_instructions": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of additional instructions - same order as drugIds, empty string if none"
        ),
    }
)

# ============================================================================
# PART 2: CHECKLIST & SCREENINGS (~40 fields)
# ============================================================================

NEO_DISCHARGE_PART2_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== BLOOD TEST RESULTS (10 fields) ==========
        "bloodTest_hb": types.Schema(type=types.Type.STRING, description="Hemoglobin value or empty string"),
        "bloodTest_pcv": types.Schema(type=types.Type.STRING, description="PCV/Hematocrit value or empty string"),
        "bloodTest_dct": types.Schema(type=types.Type.STRING, description="Direct Coombs Test result or empty string"),
        "bloodTest_tsb": types.Schema(type=types.Type.STRING, description="Total Serum Bilirubin value or empty string"),
        "bloodTest_directBilirubin": types.Schema(type=types.Type.STRING, description="Direct Bilirubin value or empty string"),
        "bloodTest_serumCa": types.Schema(type=types.Type.STRING, description="Serum Calcium value or empty string"),
        "bloodTest_serumPo4": types.Schema(type=types.Type.STRING, description="Serum Phosphate value or empty string"),
        "bloodTest_serumALP": types.Schema(type=types.Type.STRING, description="Serum ALP value or empty string"),
        "bloodTest_serumNa": types.Schema(type=types.Type.STRING, description="Serum Sodium value or empty string"),
        "bloodTest_homeOxygen": types.Schema(type=types.Type.STRING, description="Home oxygen required: Yes, No, or empty string"),

        # ========== IMAGING (4 fields) ==========
        "cranialUltrasound_status": types.Schema(type=types.Type.STRING, description="Cranial ultrasound: Normal, Abnormal, Not Done, or empty string"),
        "cranialUltrasound_condition": types.Schema(type=types.Type.STRING, description="Findings if abnormal or empty string"),
        "echoCardiography_status": types.Schema(type=types.Type.STRING, description="Echo: Normal, Abnormal, Not Done, or empty string"),
        "echoCardiography_condition": types.Schema(type=types.Type.STRING, description="Findings if abnormal or empty string"),

        # ========== NEWBORN SCREEN (1 field) ==========
        "newBornScreen": types.Schema(type=types.Type.STRING, description="Newborn screening: Sent, Not Sent, Pending, Normal, Abnormal, or empty string"),

        # ========== HEARING SCREENING (5 fields) ==========
        "hearingScreening_status": types.Schema(type=types.Type.STRING, description="Hearing screening: Performed, Not Performed, Pending, or empty string"),
        "hearingScreening_oae_left": types.Schema(type=types.Type.STRING, description="OAE left ear: Normal, Suspect, Refer, or empty string"),
        "hearingScreening_oae_right": types.Schema(type=types.Type.STRING, description="OAE right ear: Normal, Suspect, Refer, or empty string"),
        "hearingScreening_abr_left": types.Schema(type=types.Type.STRING, description="ABR left ear: Normal, Suspect, Refer, or empty string"),
        "hearingScreening_abr_right": types.Schema(type=types.Type.STRING, description="ABR right ear: Normal, Suspect, Refer, or empty string"),

        # ========== ROP SCREENING (3 fields) ==========
        "ropScreening_status": types.Schema(type=types.Type.STRING, description="ROP screening: Performed, Not Performed, Not Indicated, or empty string"),
        "ropScreening_result_left": types.Schema(type=types.Type.STRING, description="ROP left eye: No ROP, Stage1 ROP, Stage2 ROP, Stage3 ROP, Aggressive Posterior ROP, or empty string"),
        "ropScreening_result_right": types.Schema(type=types.Type.STRING, description="ROP right eye: No ROP, Stage1 ROP, Stage2 ROP, Stage3 ROP, Aggressive Posterior ROP, or empty string"),

        # ========== ROP TREATMENT (3 fields) ==========
        "ropTreatment_status": types.Schema(type=types.Type.STRING, description="ROP treatment given: Yes, No, Not Applicable, or empty string"),
        "ropTreatment_left": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of treatments for left eye: Laser, Cryotherapy, Anti-VEGF, Surgical"
        ),
        "ropTreatment_right": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of treatments for right eye: Laser, Cryotherapy, Anti-VEGF, Surgical"
        ),

        # ========== ROP FOLLOW-UP (1 field) ==========
        "ropFollowUp": types.Schema(type=types.Type.INTEGER, nullable=True, description="ROP follow-up interval in weeks or null"),

        # ========== PROCEDURES (array) ==========
        "procedures": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of procedure IDs/names performed during admission"
        ),

        # ========== INFECTIONS (3 fields) ==========
        "hospitalAcquiredInfection": types.Schema(type=types.Type.STRING, description="Hospital acquired infection: Yes, No, or empty string"),
        "ventilatorAssociatedPneumonia": types.Schema(type=types.Type.STRING, description="VAP: Yes, No, or empty string"),
        "bloodStreamInfections": types.Schema(type=types.Type.STRING, description="Blood stream infections: Yes, No, or empty string"),

        # ========== ADVICE & FOLLOW-UP (2 fields) ==========
        "advice": types.Schema(type=types.Type.STRING, description="Discharge advice and instructions or empty string"),
        "planFollowUp": types.Schema(type=types.Type.STRING, description="Follow-up plan details or empty string"),
    }
)

# Note: System prompts are in neonatal_prompts.py (NEO_DISCHARGE_SYSTEM_PROMPT, NEO_DISCHARGE_USER_PROMPT)
# This file only contains the split schemas for Gemini API compatibility

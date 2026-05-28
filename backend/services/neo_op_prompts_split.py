"""
Split NEO_OP Schema for Gemini API Compatibility

The NEO_OP schema (~125 properties when flattened) exceeds Gemini's constraint limits.
This module splits the extraction into TWO separate API calls:

PART 1 (~60 fields): BABY, ELIGIBILITY & MEDICAL HISTORY
- Patient identification (uhid, opDateTime, hospitalName)
- Baby details including corrected age (19 fields) - chronological age auto-calculated
- Eligibility criteria (17 fields)
- Medical history (14 fields)

PART 2 (~60 fields): FAMILY, FOLLOW-UP & PRESCRIPTIONS
- Mother details (20 fields)
- Partner details (22 fields)
- Follow-up details (9 fields)
- Medications array
- Immunization details

The neo_op_formatter.py service merges both results into the final nested structure.
"""

from google.genai import types

# ============================================================================
# PART 1: BABY, ELIGIBILITY & MEDICAL HISTORY (~65 fields)
# ============================================================================

NEO_OP_PART1_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== PATIENT IDENTIFICATION (3 fields) ==========
        "uhid": types.Schema(type=types.Type.STRING, description="Patient unique hospital ID or empty string"),
        "opDateTime": types.Schema(type=types.Type.STRING, description="Consultation date-time in YYYY-MM-DD HH:MM format or empty string"),
        "hospitalName": types.Schema(type=types.Type.STRING, description="Hospital/clinic name or empty string"),

        # ========== BABY DETAILS (19 fields - chronological age auto-calculated) ==========
        "baby_name": types.Schema(type=types.Type.STRING, description="Baby name (e.g., 'Baby of Tamil') or empty string"),
        "baby_dob": types.Schema(type=types.Type.STRING, description="Date of birth in YYYY-MM-DD format or empty string"),
        "baby_tob": types.Schema(type=types.Type.STRING, description="Time of birth in HH:MM format or empty string"),
        "baby_sex": types.Schema(type=types.Type.STRING, description="Male, Female, Ambiguous, or empty string"),
        "baby_birthStatus": types.Schema(type=types.Type.STRING, description="Inborn, Outborn, or empty string"),
        "baby_birthOrder": types.Schema(type=types.Type.STRING, description="Singleton, 1st of twins, 2nd of twins, etc. or empty string"),
        "baby_bloodGroup": types.Schema(type=types.Type.STRING, description="Blood group (e.g., 'B Positive') or empty string"),
        "baby_birthWeight": types.Schema(type=types.Type.STRING, description="Birth weight in grams as string or empty string"),
        "baby_birthHeadCircumference": types.Schema(type=types.Type.STRING, description="Birth head circumference in cm or empty string"),
        "baby_currentWeight": types.Schema(type=types.Type.STRING, description="Current weight in grams as string or empty string"),
        "baby_currentHeadCircumference": types.Schema(type=types.Type.STRING, description="Current head circumference in cm or empty string"),
        "baby_currentLength": types.Schema(type=types.Type.STRING, description="Current length in cm or empty string"),

        # Gestation
        "baby_gestation_weeks": types.Schema(type=types.Type.INTEGER, nullable=True, description="Gestational age weeks or null"),
        "baby_gestation_days": types.Schema(type=types.Type.INTEGER, nullable=True, description="Gestational age days or null"),

        # Chronological Age - AUTO-CALCULATED from baby_dob, removed from schema
        # (5 fields removed: years, months, days, weeks, weeksDays)

        # Corrected Age (extracted from recording, NOT auto-calculated)
        "baby_correctedAge_years": types.Schema(type=types.Type.INTEGER, nullable=True, description="Corrected age years or null"),
        "baby_correctedAge_months": types.Schema(type=types.Type.INTEGER, nullable=True, description="Corrected age months or null"),
        "baby_correctedAge_days": types.Schema(type=types.Type.INTEGER, nullable=True, description="Corrected age days or null"),
        "baby_correctedAge_weeks": types.Schema(type=types.Type.INTEGER, nullable=True, description="Corrected age in weeks or null"),
        "baby_correctedAge_weeksDays": types.Schema(type=types.Type.INTEGER, nullable=True, description="Corrected age remaining days or null"),

        # ========== ELIGIBILITY CRITERIA (17 fields) ==========
        "eligibility_birthWeightGestationIsLesser": types.Schema(type=types.Type.BOOLEAN, description="Birth weight <1500g OR gestation <32 weeks"),
        "eligibility_birthWeightGestationIsGreater": types.Schema(type=types.Type.BOOLEAN, description="Birth weight >1500g OR gestation >32 weeks"),
        "eligibility_intrauterineGrowth": types.Schema(type=types.Type.BOOLEAN, description="IUGR present"),
        "eligibility_meningitis": types.Schema(type=types.Type.BOOLEAN, description="History of meningitis"),
        "eligibility_mechanicalVentilation": types.Schema(type=types.Type.BOOLEAN, description="History of mechanical ventilation"),
        "eligibility_encephalopathyStage2OrMore": types.Schema(type=types.Type.BOOLEAN, description="HIE stage 2 or more"),
        "eligibility_majorMalformation": types.Schema(type=types.Type.BOOLEAN, description="Major congenital malformations"),
        "eligibility_inbornErrors": types.Schema(type=types.Type.BOOLEAN, description="Inborn errors of metabolism"),
        "eligibility_symptomaticHypoglycemia": types.Schema(type=types.Type.BOOLEAN, description="History of symptomatic hypoglycemia"),
        "eligibility_symptomaticPolycythemia": types.Schema(type=types.Type.BOOLEAN, description="History of symptomatic polycythemia"),
        "eligibility_retrovirusPositiveMother": types.Schema(type=types.Type.BOOLEAN, description="Mother HIV/HBV/HCV positive"),
        "eligibility_hyperbilirubinemiaTransfusionRh": types.Schema(type=types.Type.BOOLEAN, description="Exchange transfusion for Rh disease"),
        "eligibility_abnormalNeuroExam": types.Schema(type=types.Type.BOOLEAN, description="Abnormal neurological examination"),
        "eligibility_majorMorbidities": types.Schema(type=types.Type.BOOLEAN, description="Other major morbidities"),
        "eligibility_otherSpecifyIsPresent": types.Schema(type=types.Type.BOOLEAN, description="Other eligibility reasons present"),
        "eligibility_otherSpecify": types.Schema(type=types.Type.STRING, description="Details of other eligibility reasons or empty string"),
        "eligibility_generalCheckup": types.Schema(type=types.Type.BOOLEAN, description="General checkup visit"),

        # ========== MEDICAL HISTORY (14 fields) ==========
        "medicalHistory_babyBackground": types.Schema(type=types.Type.STRING, description="Detailed baby background including birth history, NICU stay, diagnoses, treatments, current issues or empty string"),
        "medicalHistory_confidentialDetails": types.Schema(type=types.Type.STRING, description="Confidential clinical information or empty string"),
        "medicalHistory_complaints": types.Schema(type=types.Type.STRING, description="Chief complaints for current visit or empty string"),
        "medicalHistory_hpi": types.Schema(type=types.Type.STRING, description="History of presenting illness or empty string"),
        "medicalHistory_allergy": types.Schema(type=types.Type.STRING, description="Known allergies or empty string"),
        "medicalHistory_familyHistory": types.Schema(type=types.Type.STRING, description="Relevant family history or empty string"),
        "medicalHistory_treatmentHistory": types.Schema(type=types.Type.STRING, description="Previous treatments and medications or empty string"),
        "medicalHistory_development": types.Schema(type=types.Type.STRING, description="Developmental milestones or empty string"),
        "medicalHistory_examination": types.Schema(type=types.Type.STRING, description="Physical examination findings or empty string"),
        "medicalHistory_neurosonogram": types.Schema(type=types.Type.INTEGER, nullable=True, description="Neurosonogram status: 1=Done Normal, 2=Done Abnormal, 3=Not Done, 4=N/A, or null"),
        "medicalHistory_echocardiogram": types.Schema(type=types.Type.INTEGER, nullable=True, description="Echo status: 1=Done Normal, 2=Done Abnormal, 3=Not Done, 4=N/A, or null"),
        "medicalHistory_diagnosis": types.Schema(type=types.Type.STRING, description="Current diagnosis/assessment or empty string"),
        "medicalHistory_advice": types.Schema(type=types.Type.STRING, description="Clinical advice and recommendations or empty string"),
        "medicalHistory_investigations": types.Schema(type=types.Type.STRING, description="Investigations ordered or results or empty string"),
    }
)

# ============================================================================
# PART 2: FAMILY, FOLLOW-UP & PRESCRIPTIONS (~60 fields)
# ============================================================================

NEO_OP_PART2_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== MOTHER DETAILS (20 fields - flattened) ==========
        "mother_uhid": types.Schema(type=types.Type.STRING, description="Mother's hospital ID or empty string"),
        "mother_title": types.Schema(type=types.Type.STRING, description="Mrs., Ms., Miss, or empty string"),
        "mother_name_initial": types.Schema(type=types.Type.STRING, description="Name initial or empty string"),
        "mother_name_first": types.Schema(type=types.Type.STRING, description="First name or empty string"),
        "mother_name_last": types.Schema(type=types.Type.STRING, description="Last name or empty string"),
        "mother_dob": types.Schema(type=types.Type.STRING, description="Date of birth in YYYY-MM-DD format or empty string"),
        "mother_age": types.Schema(type=types.Type.STRING, description="Age in years as string or empty string"),
        "mother_education": types.Schema(type=types.Type.STRING, description="Educational qualification or empty string"),
        "mother_occupation_type": types.Schema(type=types.Type.STRING, description="Occupation type or empty string"),
        "mother_occupation_status": types.Schema(type=types.Type.STRING, description="Employment status or empty string"),
        "mother_contact_primary": types.Schema(type=types.Type.STRING, description="Primary phone number or empty string"),
        "mother_contact_secondary": types.Schema(type=types.Type.STRING, description="Secondary phone number or empty string"),
        "mother_contact_email": types.Schema(type=types.Type.STRING, description="Email address or empty string"),
        "mother_language": types.Schema(type=types.Type.STRING, description="Preferred language or empty string"),
        "mother_address_doorNo": types.Schema(type=types.Type.STRING, description="Door number or empty string"),
        "mother_address_street": types.Schema(type=types.Type.STRING, description="Street name or empty string"),
        "mother_address_city": types.Schema(type=types.Type.STRING, description="City or empty string"),
        "mother_address_pinCode": types.Schema(type=types.Type.STRING, description="PIN code or empty string"),
        "mother_address_country": types.Schema(type=types.Type.STRING, description="Country or empty string"),
        "mother_bloodGroup": types.Schema(type=types.Type.STRING, description="Blood group (e.g., 'A Positive') or empty string"),

        # ========== PARTNER DETAILS (22 fields - flattened) ==========
        "partner_title": types.Schema(type=types.Type.STRING, description="Mr., or empty string"),
        "partner_name_initial": types.Schema(type=types.Type.STRING, description="Name initial or empty string"),
        "partner_name_first": types.Schema(type=types.Type.STRING, description="First name or empty string"),
        "partner_name_last": types.Schema(type=types.Type.STRING, description="Last name or empty string"),
        "partner_dob": types.Schema(type=types.Type.STRING, description="Date of birth in YYYY-MM-DD format or empty string"),
        "partner_age": types.Schema(type=types.Type.STRING, description="Age in years as string or empty string"),
        "partner_education": types.Schema(type=types.Type.STRING, description="Educational qualification or empty string"),
        "partner_occupation_type": types.Schema(type=types.Type.STRING, description="Occupation type or empty string"),
        "partner_occupation_status": types.Schema(type=types.Type.STRING, description="Employment status or empty string"),
        "partner_contact_primary": types.Schema(type=types.Type.STRING, description="Primary phone number or empty string"),
        "partner_contact_secondary": types.Schema(type=types.Type.STRING, description="Secondary phone number or empty string"),
        "partner_contact_email": types.Schema(type=types.Type.STRING, description="Email address or empty string"),
        "partner_language": types.Schema(type=types.Type.STRING, description="Preferred language or empty string"),
        "partner_address_doorNo": types.Schema(type=types.Type.STRING, description="Door number or empty string"),
        "partner_address_street": types.Schema(type=types.Type.STRING, description="Street name or empty string"),
        "partner_address_city": types.Schema(type=types.Type.STRING, description="City or empty string"),
        "partner_address_pinCode": types.Schema(type=types.Type.STRING, description="PIN code or empty string"),
        "partner_address_country": types.Schema(type=types.Type.STRING, description="Country or empty string"),
        "partner_sameAsMotherDetails": types.Schema(type=types.Type.BOOLEAN, description="Partner details same as mother"),
        "partner_sameAsAddress": types.Schema(type=types.Type.BOOLEAN, description="Partner address same as mother"),

        # ========== FOLLOW-UP DETAILS (9 fields - flattened) ==========
        "followUp_appointmentType": types.Schema(type=types.Type.STRING, description="Type of appointment or empty string"),
        "followUp_reviewDateTime": types.Schema(type=types.Type.STRING, description="Next review date-time in YYYY-MM-DD HH:MM format or empty string"),
        "followUp_nextReviewIndication": types.Schema(type=types.Type.STRING, description="Reason for next review or empty string"),
        "followUp_needNeuro": types.Schema(type=types.Type.BOOLEAN, description="Needs neurology follow-up"),
        "followUp_outcome": types.Schema(type=types.Type.STRING, description="Sent Home, Admitted, Referred, etc. or empty string"),
        "followUp_seenBy": types.Schema(type=types.Type.INTEGER, nullable=True, description="Doctor ID who saw the patient or null"),
        "followUp_fee_status": types.Schema(type=types.Type.BOOLEAN, description="Fee paid status"),
        "followUp_fee_amount": types.Schema(type=types.Type.STRING, description="Fee amount as string or empty string"),
        "followUp_fee_reason": types.Schema(type=types.Type.STRING, description="Reason for fee waiver or empty string"),

        # ========== MEDICATIONS (Array handling via parallel arrays) ==========
        # Each medication can have multiple dosage steps, so we use arrays
        "medication_drugIds": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of drug IDs as strings"
        ),
        "medication_routes": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of route IDs as strings (1=Oral, 2=Inhalation, 3=Topical, 4=Injection)"
        ),
        # Dosage is complex - we'll store as JSON strings for each medication
        "medication_dosages": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of dosage JSON strings. Each entry is a JSON array of {dose, frequency, duration} objects for that medication"
        ),

        # ========== IMMUNIZATION (4 fields) ==========
        "immunization_status": types.Schema(type=types.Type.STRING, description="Given, Not Given, Partially Given, Due, or empty string"),
        "immunization_schedule": types.Schema(type=types.Type.STRING, description="Immunization schedule notes or empty string"),
        "immunization_vaccineIds": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.INTEGER),
            description="Array of vaccine IDs: 1=BCG, 2=HepB, 3=OPV, 4=IPV, 5=Pentavalent, 6=PCV, 7=Rotavirus, 8=Measles, 9=VitA, 10=Others"
        ),
    }
)

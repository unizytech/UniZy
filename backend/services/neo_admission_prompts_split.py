"""
Split NEONATAL_ADMISSION Schema for Gemini API Compatibility

The NEONATAL_ADMISSION schema (~130-150 properties when flattened) significantly exceeds Gemini's limits.
This module splits the extraction into TWO separate API calls:

PART 1 (~60 fields): BABY, ADMISSION & PREGNANCY
- Baby demographics (name, uhid, dob, birth details)
- Admission info (date, type, room/bed, seen by)
- Medical history (problems, smoking, alcohol, tobacco)
- Pregnancy details (complications, scans - dating, anomaly, doppler)
- Baby resuscitation details

PART 2 (~70 fields): CLINICAL ASSESSMENT & SCORES
- Admission details (42 fields - vitals, examination, neuro)
- Procedures (lines, investigations, antibiotics)
- CRIB-2 score components
- SNAPPE-2 score components
- Diagnosis and parent discussion

The neo_admission_formatter.py service merges both results into the final nested structure.
"""

from google.genai import types

# ============================================================================
# PART 1: BABY, ADMISSION & PREGNANCY (~60 fields)
# ============================================================================

NEO_ADMISSION_PART1_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== BABY DETAILS (9 fields) ==========
        "baby_name": types.Schema(type=types.Type.STRING, description="Baby name (e.g., 'B/O Revathi Satheesh') or empty string"),
        "baby_uhid": types.Schema(type=types.Type.STRING, description="Baby's hospital ID or empty string"),
        "baby_dob": types.Schema(type=types.Type.STRING, description="Date of birth in YYYY-MM-DD format or empty string"),
        "baby_birthWeight": types.Schema(type=types.Type.STRING, description="Birth weight in grams as string or empty string"),
        "baby_birthStatus": types.Schema(type=types.Type.STRING, description="Inborn, Outborn, or empty string"),
        "baby_gestation_weeks": types.Schema(type=types.Type.INTEGER, nullable=True, description="Gestational age weeks or null"),
        "baby_gestation_days": types.Schema(type=types.Type.INTEGER, nullable=True, description="Gestational age days or null"),
        "baby_bloodGroup": types.Schema(type=types.Type.STRING, description="Blood group (e.g., 'B Positive') or empty string"),
        "baby_sex": types.Schema(type=types.Type.STRING, description="Male, Female, Ambiguous, or empty string"),

        # ========== REFERRAL (2 fields) ==========
        "referredBy": types.Schema(type=types.Type.STRING, description="Referring source: Self, Doctor Name, Hospital Name, or empty string"),
        "referralReason": types.Schema(type=types.Type.STRING, description="Reason for referral or empty string"),

        # ========== ADMISSION DETAILS (8 fields) ==========
        "admission_admissionDate": types.Schema(type=types.Type.STRING, description="Admission date-time in YYYY-MM-DD HH:MM format or empty string"),
        "admission_typeOfCare": types.Schema(type=types.Type.STRING, description="Type of care: NICU, Special Care, Ward, Observation, or empty string"),
        "admission_visitNumber": types.Schema(type=types.Type.STRING, description="Visit/IP number (e.g., 'IP/8754454') or empty string"),
        "admission_admissionWt": types.Schema(type=types.Type.STRING, description="Admission weight in grams as string or empty string"),
        "admission_surgeon": types.Schema(type=types.Type.STRING, description="Surgeon ID or name if surgical case, or empty string"),
        "admission_hospitalName": types.Schema(type=types.Type.STRING, description="Hospital name or empty string"),
        "admission_seenByIds": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.INTEGER),
            description="Array of specialist IDs who reviewed the baby"
        ),

        # ========== MEDICAL HISTORY (7 fields) ==========
        "medicalHistory_problemIds": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.INTEGER),
            description="Array of maternal medical problem IDs"
        ),
        "medicalHistory_problemMedications": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of medications for each problem (same order as problemIds)"
        ),
        "medicalHistory_smoking": types.Schema(type=types.Type.STRING, description="Maternal smoking: Yes, No, or empty string"),
        "medicalHistory_alcohol": types.Schema(type=types.Type.STRING, description="Maternal alcohol use: Yes, No, or empty string"),
        "medicalHistory_tobacco": types.Schema(type=types.Type.STRING, description="Maternal tobacco use: Yes, No, or empty string"),

        # ========== PREGNANCY - COMPLICATIONS (arrays) ==========
        "pregnancy_complicationIds": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.INTEGER),
            description="Array of pregnancy complication IDs"
        ),
        "pregnancy_complicationTreatments": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of treatments for each complication (same order as complicationIds)"
        ),

        # ========== PREGNANCY - SCANS (9 fields) ==========
        "pregnancy_datingScan_date": types.Schema(type=types.Type.STRING, description="Dating scan date in DD-MM-YYYY format or empty string"),
        "pregnancy_datingScan_gestation": types.Schema(type=types.Type.STRING, description="Gestation at dating scan (e.g., '12 + 6') or empty string"),
        "pregnancy_datingScan_findings": types.Schema(type=types.Type.STRING, description="Dating scan findings or empty string"),
        "pregnancy_anomalyScan_date": types.Schema(type=types.Type.STRING, description="Anomaly scan date in DD-MM-YYYY format or empty string"),
        "pregnancy_anomalyScan_gestation": types.Schema(type=types.Type.STRING, description="Gestation at anomaly scan (e.g., '21') or empty string"),
        "pregnancy_anomalyScan_findings": types.Schema(type=types.Type.STRING, description="Anomaly scan findings or empty string"),

        # Other scans as arrays
        "pregnancy_otherScan_dates": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of other scan dates"
        ),
        "pregnancy_otherScan_gestations": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of gestations at other scans"
        ),
        "pregnancy_otherScan_findings": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of other scan findings"
        ),
        "pregnancy_dopplerScan_dates": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of doppler scan dates"
        ),
        "pregnancy_dopplerScan_gestations": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of gestations at doppler scans"
        ),
        "pregnancy_dopplerScan_findings": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of doppler scan findings"
        ),

        # ========== BABY RESUSCITATION DETAILS (11 fields) ==========
        "babyDetails_descriptionOfResuscitation": types.Schema(type=types.Type.STRING, description="Resuscitation description: Ciab, Stimulation, PPV, Intubation, etc. or empty string"),
        "babyDetails_ventilationRequired": types.Schema(type=types.Type.STRING, description="Ventilation required: Yes, No, or empty string"),
        "babyDetails_surfactantGiven": types.Schema(type=types.Type.STRING, description="Surfactant given: Yes, No, or empty string"),
        "babyDetails_surfactantType": types.Schema(type=types.Type.STRING, description="Surfactant type: Survanta, Curosurf, Neosurf, etc. or empty string"),
        "babyDetails_dose": types.Schema(type=types.Type.STRING, description="Surfactant dose number as string or empty string"),
        "babyDetails_dateofAdministration": types.Schema(type=types.Type.STRING, description="Surfactant administration date-time in DD-MM-YYYY HH:MM format or empty string"),
        "babyDetails_ageAfterBirth": types.Schema(type=types.Type.STRING, description="Age at surfactant administration in hours or empty string"),
        "babyDetails_deliveryCpap": types.Schema(type=types.Type.STRING, description="Delivery room CPAP: Yes, No, or empty string"),
        "babyDetails_airFlow": types.Schema(type=types.Type.STRING, description="Air flow rate or empty string"),
        "babyDetails_oxgenFlow": types.Schema(type=types.Type.STRING, description="Oxygen flow rate or empty string"),
        "babyDetails_transferFiO2": types.Schema(type=types.Type.STRING, description="Transfer FiO2 percentage or empty string"),
    }
)

# ============================================================================
# PART 2: CLINICAL ASSESSMENT & SCORES (~70 fields)
# ============================================================================

NEO_ADMISSION_PART2_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== ADMISSION DETAILS (42 fields) ==========
        "admissionDetails_admittedFrom": types.Schema(type=types.Type.STRING, description="Admitted from: Labour ward, OT, Emergency, Outside hospital, or empty string"),
        "admissionDetails_majorComplaints": types.Schema(type=types.Type.STRING, description="Major complaints/reason for admission or empty string"),
        "admissionDetails_ventilation": types.Schema(type=types.Type.STRING, description="On ventilation: Yes, No, or empty string"),
        "admissionDetails_mode": types.Schema(type=types.Type.STRING, description="Ventilation mode ID or name or empty string"),
        "admissionDetails_retractions": types.Schema(type=types.Type.STRING, description="Retractions: None, Mild, Moderate, Severe, or empty string"),
        "admissionDetails_airEntry": types.Schema(type=types.Type.STRING, description="Air entry: Normal, Reduced Rt, Reduced Lt, Reduced Bilateral, or empty string"),
        "admissionDetails_chestMovement": types.Schema(type=types.Type.STRING, description="Chest movement: Symmetrical, Asymmetrical, or empty string"),
        "admissionDetails_hr": types.Schema(type=types.Type.STRING, description="Heart rate as string or empty string"),
        "admissionDetails_systolicBp": types.Schema(type=types.Type.STRING, description="Systolic BP as string or empty string"),
        "admissionDetails_diastolicBp": types.Schema(type=types.Type.STRING, description="Diastolic BP as string or empty string"),
        "admissionDetails_meanBP": types.Schema(type=types.Type.STRING, description="Mean BP as string or empty string"),
        "admissionDetails_centralPulses": types.Schema(type=types.Type.STRING, description="Central pulses: Normal, Weak, Bounding, or empty string"),
        "admissionDetails_peripheralPulses": types.Schema(type=types.Type.STRING, description="Peripheral pulses: Normal, Weak, Absent, or empty string"),
        "admissionDetails_femoralPulses": types.Schema(type=types.Type.STRING, description="Femoral pulses: Normal, Weak, Bounding, Absent, or empty string"),
        "admissionDetails_s1s2": types.Schema(type=types.Type.STRING, description="Heart sounds S1S2: Normal, Abnormal, or empty string"),
        "admissionDetails_murmur": types.Schema(type=types.Type.STRING, description="Murmur: Normal, Abnormal, Present, Absent, or empty string"),
        "admissionDetails_cft": types.Schema(type=types.Type.STRING, description="Capillary refill time: <3 Seconds, 3-5 Seconds, >5 Seconds, or empty string"),
        "admissionDetails_color": types.Schema(type=types.Type.STRING, description="Color: Pink, Pale, Cyanotic, Acral Cyanosis, Jaundiced, or empty string"),
        "admissionDetails_fahrenheit": types.Schema(type=types.Type.STRING, description="Temperature in Fahrenheit or empty string"),
        "admissionDetails_temperature": types.Schema(type=types.Type.STRING, description="Temperature in Celsius or empty string"),
        "admissionDetails_abdomen": types.Schema(type=types.Type.STRING, description="Abdomen: Soft, Distended, Scaphoid, or empty string"),
        "admissionDetails_bowelSounds": types.Schema(type=types.Type.STRING, description="Bowel sounds: Normal, Decreased, Absent, Increased, or empty string"),
        "admissionDetails_umbilicus": types.Schema(type=types.Type.STRING, description="Umbilicus: Normal, Omphalitis, Gastroschisis, Omphalocele, or empty string"),
        "admissionDetails_hepatomegaly": types.Schema(type=types.Type.STRING, description="Hepatomegaly: Yes, No, or empty string"),
        "admissionDetails_splenomegaly": types.Schema(type=types.Type.STRING, description="Splenomegaly: Yes, No, or empty string"),
        "admissionDetails_herina": types.Schema(type=types.Type.STRING, description="Hernia: None, Inguinal, Umbilical/para umbilical hernia, or empty string"),
        "admissionDetails_genitalia": types.Schema(type=types.Type.STRING, description="Genitalia: Normal, Abnormal, Ambiguous, or empty string"),
        "admissionDetails_pupils": types.Schema(type=types.Type.STRING, description="Pupils: Equal and reacting to light, Unequal, Fixed, or empty string"),
        "admissionDetails_anteriorFontanelle": types.Schema(type=types.Type.STRING, description="Anterior fontanelle: Normal, Bulging, Depressed, or empty string"),
        "admissionDetails_activity": types.Schema(type=types.Type.STRING, description="Activity: Active, Lethargic, Irritable, Comatosed, or empty string"),
        "admissionDetails_tone": types.Schema(type=types.Type.STRING, description="Tone: Normal, Hypotonia, Hypertonia, or empty string"),
        "admissionDetails_cry": types.Schema(type=types.Type.STRING, description="Cry: Normal, Weak cry, High pitched cry, Absent, or empty string"),
        "admissionDetails_seizures": types.Schema(type=types.Type.STRING, description="Seizures: Yes, No, or empty string"),
        "admissionDetails_neonatalReflexes": types.Schema(type=types.Type.STRING, description="Neonatal reflexes: Normal, Depressed, Exaggerated, Absent, or empty string"),
        "admissionDetails_abnormalities": types.Schema(type=types.Type.STRING, description="Other abnormalities noted or empty string"),
        "admissionDetails_initialBloodGas": types.Schema(type=types.Type.STRING, description="Initial blood gas type: Arterial, Venous, Capillary, or empty string"),
        "admissionDetails_ageTime": types.Schema(type=types.Type.STRING, description="Age at blood gas in HH:MM format or empty string"),
        "admissionDetails_spo2": types.Schema(type=types.Type.STRING, description="SpO2 percentage or empty string"),
        "admissionDetails_lactate": types.Schema(type=types.Type.STRING, description="Lactate value or empty string"),
        "admissionDetails_ph": types.Schema(type=types.Type.STRING, description="Blood gas pH value (e.g., 7.35) or empty string"),
        "admissionDetails_bloodGasBaseExcess": types.Schema(type=types.Type.STRING, description="Blood gas base excess value (e.g., -1.2) or empty string"),
        "admissionDetails_paO2": types.Schema(type=types.Type.STRING, description="Arterial oxygen partial pressure (PaO2) value or empty string"),
        "admissionDetails_paCo2": types.Schema(type=types.Type.STRING, description="Arterial CO2 partial pressure (PaCO2) value or empty string"),
        "admissionDetails_hco3": types.Schema(type=types.Type.STRING, description="Bicarbonate (HCO3) level or empty string"),
        "admissionDetails_hct": types.Schema(type=types.Type.STRING, description="Hematocrit (Hct) percentage or empty string"),
        "admissionDetails_rbs": types.Schema(type=types.Type.STRING, description="Random blood sugar value or empty string"),
        "admissionDetails_initialAssessmentCompletedDateTime": types.Schema(type=types.Type.STRING, description="Assessment completion date-time in DD-MM-YYYY HH:MM format or empty string"),

        # ========== PROCEDURES (13 fields) ==========
        "procedures_initialxray": types.Schema(type=types.Type.STRING, description="Initial X-ray: Done, Not indicated, Pending, or empty string"),
        "procedures_chestXrayFindings": types.Schema(type=types.Type.STRING, description="Chest X-ray findings description or empty string"),
        "procedures_abdominalXrayFindings": types.Schema(type=types.Type.STRING, description="Abdominal X-ray findings description or empty string"),
        "procedures_uac_status": types.Schema(type=types.Type.STRING, description="UAC: Yes, No, or empty string"),
        "procedures_uac_position": types.Schema(type=types.Type.STRING, description="UAC position or empty string"),
        "procedures_uvc_status": types.Schema(type=types.Type.STRING, description="UVC: Yes, No, or empty string"),
        "procedures_uvc_position": types.Schema(type=types.Type.STRING, description="UVC position or empty string"),
        "procedures_sepsisScreen": types.Schema(type=types.Type.STRING, description="Sepsis screen: Yes, No, or empty string"),
        "procedures_indications": types.Schema(type=types.Type.STRING, description="Indications for sepsis screen or empty string"),
        "procedures_ivAntibioticIds": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of IV antibiotic IDs"
        ),
        "procedures_investigationsTest": types.Schema(type=types.Type.STRING, description="Investigation test IDs or names (comma-separated) or empty string"),
        "procedures_investigations": types.Schema(type=types.Type.STRING, description="Investigation results or notes or empty string"),
        "procedures_enteralFeeding": types.Schema(type=types.Type.STRING, description="Enteral feeding: Yes, No, or empty string"),
        "procedures_fluids": types.Schema(type=types.Type.INTEGER, nullable=True, description="IV fluid rate in ml/kg/day or null"),

        # ========== CRIB-2 SCORE (3 fields) ==========
        "crib2_sexBirthWtGestation": types.Schema(type=types.Type.STRING, description="CRIB-2 sex/weight/gestation score or empty string"),
        "crib2_fahrenheit": types.Schema(type=types.Type.STRING, description="CRIB-2 temperature component or empty string"),
        "crib2_baseExcess": types.Schema(type=types.Type.STRING, description="CRIB-2 base excess component or empty string"),

        # ========== SNAPPE-2 SCORE (9 fields) ==========
        "snappe2_mbp": types.Schema(type=types.Type.STRING, description="SNAPPE-2 mean BP score or empty string"),
        "snappe2_lowestTemperature": types.Schema(type=types.Type.STRING, description="SNAPPE-2 lowest temperature score or empty string"),
        "snappe2_po2Fio2Ratio": types.Schema(type=types.Type.STRING, description="SNAPPE-2 PO2/FiO2 ratio score or empty string"),
        "snappe2_lowestSerumPh": types.Schema(type=types.Type.STRING, description="SNAPPE-2 lowest serum pH score or empty string"),
        "snappe2_multipleSeizures": types.Schema(type=types.Type.STRING, description="SNAPPE-2 multiple seizures score or empty string"),
        "snappe2_urineOutput": types.Schema(type=types.Type.STRING, description="SNAPPE-2 urine output score or empty string"),
        "snappe2_bWeight": types.Schema(type=types.Type.STRING, description="SNAPPE-2 birth weight score or empty string"),
        "snappe2_smallForGestationalAge": types.Schema(type=types.Type.STRING, description="SNAPPE-2 SGA score or empty string"),
        "snappe2_apgar5Mins": types.Schema(type=types.Type.STRING, description="SNAPPE-2 5-min APGAR score or empty string"),

        # ========== DIAGNOSIS (9 fields) ==========
        "diagnosis_differentialDiagnosis": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of ICD-10 codes for differential diagnoses"
        ),
        "diagnosis_additionalDiagnoses": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of additional diagnosis text entries"
        ),
        "diagnosis_plan": types.Schema(type=types.Type.STRING, description="Treatment plan or empty string"),
        "diagnosis_parentsSpokenTo": types.Schema(type=types.Type.STRING, description="Parents spoken to: Yes, No, or empty string"),
        "diagnosis_timeOfDiscussion": types.Schema(type=types.Type.STRING, description="Time of discussion in HH:MM format or empty string"),
        "diagnosis_mattersDiscussed": types.Schema(type=types.Type.STRING, description="Matters discussed with parents or empty string"),
        "diagnosis_parentsAddressedBy": types.Schema(type=types.Type.STRING, description="Doctor who spoke to parents or empty string"),
        "diagnosis_indicationOfAdmission": types.Schema(type=types.Type.STRING, description="Indication of admission IDs (comma-separated) or empty string"),
        "diagnosis_indicationOfAdmissionOther": types.Schema(type=types.Type.STRING, description="Other indications for admission or empty string"),
    }
)

# Note: System prompts are in neonatal_prompts.py (NEO_ADMISSION_SYSTEM_PROMPT, NEO_ADMISSION_USER_PROMPT)
# This file only contains the split schemas for Gemini API compatibility

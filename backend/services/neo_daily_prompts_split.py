"""
Split NEO_DAILY Schema for Gemini API Compatibility - RASTER FORMAT

Updated to match Raster API expected schema structure.

PART 1 (~60 fields): PATIENT + GENERAL + RESPIRATORY + CVS
- Patient identification (uhid)
- General info (date, time, dayOfLife, careType, seenBy, background, problems)
- Respiratory system (support settings, blood gas, examination)
- CVS (hemodynamics, perfusion, echo, PDA/PAH)

PART 2 (~65 fields): GI + CNS + SEPSIS + RENAL + LINES + INOTROPES + SKIN + ROP + TOP-LEVEL ARRAYS
- GI with nutrition section (includes feeds field)
- CNS (neuro status)
- Sepsis (cultures, organisms)
- Renal/Metabolic (urine output, electrolytes, weight)
- Invasive Lines (PVC, PICC, UVC, UAC, PAC)
- Inotropes (dopamine, dobutamine, etc.)
- Skin & ROP
- Top-level: antibiotics, transfusions, fluids arrays

The neo_daily_formatter.py service merges both results into the final nested structure.
"""

from google import genai
from google.genai import types

# ============================================================================
# PART 1: PATIENT + GENERAL + RESPIRATORY + CVS (~60 fields)
# ============================================================================

NEO_DAILY_PART1_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== PATIENT IDENTIFICATION (1 field) ==========
        "uhid": types.Schema(type=types.Type.STRING, description="Patient unique hospital ID (UHID) or empty string"),

        # ========== DAILY LOG GENERAL FIELDS (7 fields) ==========
        "dailyLog_date": types.Schema(type=types.Type.STRING, description="Recording date in YYYY-MM-DD format or empty string"),
        "dailyLog_time": types.Schema(type=types.Type.STRING, description="Recording time (e.g., '10:30 AM') or empty string"),
        "dailyLog_dayOfLife": types.Schema(type=types.Type.INTEGER, nullable=True, description="Day of life (1, 2, 3...) or null"),
        "dailyLog_careType": types.Schema(type=types.Type.STRING, description="Care type: O2, CPAP, Ventilator, Room Air, etc. or empty string"),
        "dailyLog_seenBy": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of who reviewed: ['Senior Consultant', 'Registrar', 'Resident']"
        ),
        "dailyLog_background": types.Schema(type=types.Type.STRING, description="Clinical background summary or empty string"),
        "dailyLog_problems_current": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of current problems: ['RDS', 'Mild Jaundice']"
        ),
        "dailyLog_problems_previous": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of previous/resolved problems: ['Prematurity']"
        ),

        # ========== RESPIRATORY SECTION (35 fields) ==========
        "respiratory_support": types.Schema(type=types.Type.STRING, description="Respiratory support type: CPAP, SIMV, HFOV, Room Air, etc. or empty string"),
        "respiratory_ventOption": types.Schema(type=types.Type.STRING, description="Ventilation option: Bubble CPAP, Conventional, High Frequency, etc. or empty string"),
        "respiratory_fiO2": types.Schema(type=types.Type.NUMBER, nullable=True, description="FiO2 set percentage (21-100) or null"),
        "respiratory_fiO2Delivered": types.Schema(type=types.Type.NUMBER, nullable=True, description="FiO2 actually delivered percentage or null"),
        "respiratory_peep": types.Schema(type=types.Type.NUMBER, nullable=True, description="PEEP in cmH2O or null"),
        "respiratory_pip": types.Schema(type=types.Type.NUMBER, nullable=True, description="PIP set value in cmH2O or null"),
        "respiratory_pipDelivered": types.Schema(type=types.Type.NUMBER, nullable=True, description="PIP delivered value in cmH2O or null"),
        "respiratory_map": types.Schema(type=types.Type.NUMBER, nullable=True, description="MAP (Mean Airway Pressure) in cmH2O or null"),
        "respiratory_frequency": types.Schema(type=types.Type.NUMBER, nullable=True, description="Ventilator rate in breaths/min or null"),
        "respiratory_ieRatio": types.Schema(type=types.Type.STRING, description="I:E ratio (e.g., '1:2') or empty string"),
        "respiratory_amplitude": types.Schema(type=types.Type.NUMBER, nullable=True, description="HFOV amplitude or null"),
        "respiratory_airEntry": types.Schema(type=types.Type.STRING, description="Equal, Reduced, Asymmetric, or empty string"),
        "respiratory_retractions": types.Schema(type=types.Type.STRING, description="None, Mild, Moderate, Severe, or empty string"),
        "respiratory_chestMovement": types.Schema(type=types.Type.STRING, description="Normal, Asymmetric, Paradoxical, or empty string"),
        "respiratory_addedSounds": types.Schema(type=types.Type.STRING, description="None, Crackles, Wheeze, etc. or empty string"),
        "respiratory_findings": types.Schema(type=types.Type.STRING, description="Respiratory examination findings or empty string"),
        "respiratory_volumeTargeting": types.Schema(type=types.Type.BOOLEAN, description="Volume targeting enabled. Default false"),
        "respiratory_claco": types.Schema(type=types.Type.BOOLEAN, description="CLACO enabled. Default false"),
        "respiratory_dayOfVentilation": types.Schema(type=types.Type.INTEGER, nullable=True, description="Day on current ventilation or null"),
        "respiratory_spontaneouslyVentilating": types.Schema(type=types.Type.BOOLEAN, description="True if breathing independently"),
        "respiratory_etTube": types.Schema(type=types.Type.STRING, description="ET tube type: Oral, Nasal, or empty string if not intubated"),
        "respiratory_size": types.Schema(type=types.Type.NUMBER, nullable=True, description="ET tube size (e.g., 3.0, 3.5) or null"),
        "respiratory_lips": types.Schema(type=types.Type.NUMBER, nullable=True, description="ET tube depth at lips in cm or null"),
        "respiratory_flow": types.Schema(type=types.Type.NUMBER, nullable=True, description="Flow rate in L/min or null"),
        "respiratory_it": types.Schema(type=types.Type.NUMBER, nullable=True, description="Inspiratory time in seconds or null"),
        "respiratory_aaDO2": types.Schema(type=types.Type.NUMBER, nullable=True, description="A-a DO2 gradient or null"),
        # Blood gas nested
        "respiratory_bloodGas_ph": types.Schema(type=types.Type.NUMBER, nullable=True, description="Blood gas pH or null"),
        "respiratory_bloodGas_paO2": types.Schema(type=types.Type.NUMBER, nullable=True, description="PaO2 in mmHg or null"),
        "respiratory_bloodGas_paCo2": types.Schema(type=types.Type.NUMBER, nullable=True, description="PaCO2 in mmHg or null"),
        "respiratory_bloodGas_hco3": types.Schema(type=types.Type.NUMBER, nullable=True, description="HCO3 in mEq/L or null"),
        "respiratory_bloodGas_be": types.Schema(type=types.Type.NUMBER, nullable=True, description="Base excess or null"),
        "respiratory_bloodGas_lactate": types.Schema(type=types.Type.NUMBER, nullable=True, description="Lactate in mmol/L or null"),
        "respiratory_additionalIcd": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Additional respiratory ICD codes"
        ),

        # ========== CVS SECTION (30 fields) ==========
        "cvs_hr": types.Schema(type=types.Type.NUMBER, nullable=True, description="Heart rate in beats/min or null"),
        "cvs_systolicBp": types.Schema(type=types.Type.NUMBER, nullable=True, description="Systolic BP in mmHg or null"),
        "cvs_diastolicBp": types.Schema(type=types.Type.NUMBER, nullable=True, description="Diastolic BP in mmHg or null"),
        "cvs_meanBP": types.Schema(type=types.Type.NUMBER, nullable=True, description="Mean arterial pressure in mmHg or null"),
        "cvs_pulsePressure": types.Schema(type=types.Type.NUMBER, nullable=True, description="Pulse pressure in mmHg or null"),
        "cvs_centralPulses": types.Schema(type=types.Type.STRING, description="Central pulses: Normal, Weak, Bounding, or empty string"),
        "cvs_peripheralPulses": types.Schema(type=types.Type.STRING, description="Peripheral pulses: Normal, Weak, Absent, or empty string"),
        "cvs_femoralPulses": types.Schema(type=types.Type.STRING, description="Femoral pulses: Normal, Weak, Absent, or empty string"),
        "cvs_precordialActivity": types.Schema(type=types.Type.STRING, description="Precordial activity: Normal, Hyperdynamic, or empty string"),
        "cvs_s1s2": types.Schema(type=types.Type.STRING, description="Heart sounds: Normal, Abnormal, or empty string"),
        "cvs_murmur": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "cvs_murmurCharacter": types.Schema(type=types.Type.STRING, description="Murmur description if present or N/A"),
        "cvs_cft": types.Schema(type=types.Type.STRING, description="Capillary refill: '< 2s', '2-3s', '> 3s', or empty string"),
        "cvs_centralTemperature": types.Schema(type=types.Type.NUMBER, nullable=True, description="Central temperature in Celsius or null"),
        "cvs_peripheralTemperature": types.Schema(type=types.Type.NUMBER, nullable=True, description="Peripheral temperature in Celsius or null"),
        "cvs_color": types.Schema(type=types.Type.STRING, description="Pink, Pale, Cyanotic, Mottled, etc. or empty string"),
        "cvs_findings": types.Schema(type=types.Type.STRING, description="CVS examination findings or empty string"),
        "cvs_pda": types.Schema(type=types.Type.STRING, description="PDA status: Yes, No, Closed, or empty string"),
        "cvs_pdaTreatment": types.Schema(type=types.Type.STRING, description="PDA treatment: Ibuprofen, Paracetamol, Ligation, N/A, or empty string"),
        "cvs_pah": types.Schema(type=types.Type.STRING, description="PAH status: Yes, No, or empty string"),
        "cvs_pahTreatment": types.Schema(type=types.Type.STRING, description="PAH treatment: Sildenafil, iNO, N/A, or empty string"),
        "cvs_echo_status": types.Schema(type=types.Type.STRING, description="Echo status: Done, Not done, Pending, or empty string"),
        "cvs_echo_day": types.Schema(type=types.Type.INTEGER, nullable=True, description="Day of echo or null"),
        "cvs_echo_report": types.Schema(type=types.Type.STRING, description="Echo findings summary or empty string"),
        "cvs_additionalIcd": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Additional CVS ICD codes"
        ),
    }
)

# ============================================================================
# PART 2: GI + CNS + SEPSIS + RENAL + LINES + INOTROPES + SKIN + ROP + ARRAYS
# ============================================================================

NEO_DAILY_PART2_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== GI SECTION (35 fields) ==========
        "gi_abdomen": types.Schema(type=types.Type.STRING, description="Soft, Distended, Scaphoid, or empty string"),
        "gi_bowelSounds": types.Schema(type=types.Type.STRING, description="Present, Absent, Decreased, or empty string"),
        "gi_girth": types.Schema(type=types.Type.NUMBER, nullable=True, description="Abdominal girth in cm or null"),
        "gi_stools": types.Schema(type=types.Type.BOOLEAN, description="Stools passed true/false"),
        "gi_stoolNature": types.Schema(type=types.Type.STRING, description="Meconium, Yellow, Green, Bloody, etc. or empty string"),
        "gi_aspirateVolume": types.Schema(type=types.Type.STRING, description="Aspirate volume (e.g., '2ml') or empty string"),
        "gi_aspirateNature": types.Schema(type=types.Type.STRING, description="Milky, Bilious, Clear, etc. or empty string"),
        "gi_findings": types.Schema(type=types.Type.STRING, description="GI examination findings or empty string"),
        "gi_nec": types.Schema(type=types.Type.STRING, description="NEC status: Yes, No, Suspected, or empty string"),
        "gi_necTreatment": types.Schema(type=types.Type.STRING, description="NEC treatment if applicable or N/A"),
        "gi_liver_status": types.Schema(type=types.Type.STRING, description="Liver status: Yes (palpable), No, or empty string"),
        "gi_liver_span": types.Schema(type=types.Type.NUMBER, nullable=True, description="Liver span in cm below costal margin or null"),
        "gi_spleen_status": types.Schema(type=types.Type.STRING, description="Spleen status: Yes (palpable), No, or empty string"),
        "gi_spleen_span": types.Schema(type=types.Type.NUMBER, nullable=True, description="Spleen span in cm or null"),
        "gi_umbilicus": types.Schema(type=types.Type.STRING, description="Clean, Oozing, Infected, etc. or empty string"),
        "gi_hernia": types.Schema(type=types.Type.STRING, description="Yes, No, Inguinal, Umbilical, or empty string"),
        "gi_genitalia": types.Schema(type=types.Type.STRING, description="Normal, Abnormal, or empty string with description"),
        # NNJ (Neonatal Jaundice)
        "gi_nnj_status": types.Schema(type=types.Type.STRING, description="Jaundice status: Yes, No, or empty string"),
        "gi_nnj_tsb": types.Schema(type=types.Type.NUMBER, nullable=True, description="Total serum bilirubin in mg/dL or null"),
        "gi_nnj_treatment": types.Schema(type=types.Type.STRING, description="Phototherapy, Exchange, None, N/A, or empty string"),
        # Nutrition (CRITICAL - includes feeds field)
        "gi_nutrition_feeds": types.Schema(type=types.Type.STRING, description="CRITICAL: Feeding type: Breastfeeding, Formula, EBM, NPO, etc. or empty string"),
        "gi_nutrition_volume": types.Schema(type=types.Type.NUMBER, nullable=True, description="Feed volume per feed in ml or null"),
        "gi_nutrition_frequency": types.Schema(type=types.Type.NUMBER, nullable=True, description="Feeds per day (e.g., 8 for 3-hourly) or null"),
        "gi_nutrition_workingWeight": types.Schema(type=types.Type.NUMBER, nullable=True, description="Working weight in grams or null"),
        "gi_nutrition_fullEnteralFeeds": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "gi_nutrition_ivFluids": types.Schema(type=types.Type.STRING, description="IV fluid type/rate (e.g., 'TFI 100') or empty string"),
        "gi_nutrition_ivFluidsMlDay": types.Schema(type=types.Type.NUMBER, nullable=True, description="IV fluids in ml/day or null"),
        "gi_nutrition_tpn": types.Schema(type=types.Type.STRING, description="TPN status: Yes, No, or empty string"),
        "gi_nutrition_carbohydrates": types.Schema(type=types.Type.NUMBER, nullable=True, description="Carbohydrate intake g/kg/day or null"),
        "gi_nutrition_protein": types.Schema(type=types.Type.NUMBER, nullable=True, description="Protein intake g/kg/day or null"),
        "gi_nutrition_fat": types.Schema(type=types.Type.NUMBER, nullable=True, description="Fat intake g/kg/day or null"),
        "gi_nutrition_totalEnergy": types.Schema(type=types.Type.NUMBER, nullable=True, description="Total energy kcal/kg/day or null"),
        "gi_nutrition_otherDrugs": types.Schema(type=types.Type.STRING, description="Other nutritional drugs/supplements or empty string"),
        "gi_immunoglobulins": types.Schema(type=types.Type.STRING, description="Immunoglobulin status or None"),
        "gi_additionalIcd": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Additional GI ICD codes"
        ),

        # ========== CNS SECTION (18 fields) ==========
        "cns_anteriorFontanelle": types.Schema(type=types.Type.STRING, description="Flat, Bulging, Sunken, or empty string"),
        "cns_activity": types.Schema(type=types.Type.STRING, description="Active, Lethargic, Irritable, or empty string"),
        "cns_tone": types.Schema(type=types.Type.STRING, description="Normal, Hypotonia, Hypertonia, or empty string"),
        "cns_cry": types.Schema(type=types.Type.STRING, description="Strong, Weak, High-pitched, Absent, or empty string"),
        "cns_seizures": types.Schema(type=types.Type.STRING, description="None, Present, or empty string"),
        "cns_typeOfSeizures": types.Schema(type=types.Type.STRING, description="Subtle, Clonic, Tonic, Myoclonic, N/A, or empty string"),
        "cns_reflexes": types.Schema(type=types.Type.STRING, description="Normal, Depressed, Exaggerated, or empty string"),
        "cns_pupils": types.Schema(type=types.Type.STRING, description="Reactive, Fixed, Unequal, or empty string"),
        "cns_findings": types.Schema(type=types.Type.STRING, description="CNS examination findings or empty string"),
        "cns_headCircumference": types.Schema(type=types.Type.NUMBER, nullable=True, description="Head circumference in cm or null"),
        "cns_therapeuticHypothermia": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "cns_sedationParalysis": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string with drug names"),
        "cns_neuroSonogram": types.Schema(type=types.Type.STRING, description="Normal, Abnormal findings, Not done, or empty string"),
        "cns_ultrasoundSpine": types.Schema(type=types.Type.STRING, description="Normal, Abnormal, Not done, or empty string"),
        "cns_mriCtBrain": types.Schema(type=types.Type.STRING, description="Normal, Abnormal findings, Not done, or empty string"),
        "cns_eegCfm_status": types.Schema(type=types.Type.STRING, description="Done, Not done, or empty string"),
        "cns_eegCfm_report": types.Schema(type=types.Type.STRING, description="EEG/CFM findings or empty string"),
        "cns_additionalIcd": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Additional CNS ICD codes"
        ),

        # ========== SEPSIS SECTION (6 fields) ==========
        "sepsis_crp": types.Schema(type=types.Type.NUMBER, nullable=True, description="CRP value in mg/L or null"),
        "sepsis_lumbarPuncture": types.Schema(type=types.Type.STRING, description="Yes, No, Pending, or empty string with results"),
        "sepsis_viralMeningitis": types.Schema(type=types.Type.STRING, description="Yes, No, Suspected, or empty string"),
        "sepsis_organisms": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Isolated organisms: ['E.coli', 'Klebsiella']"
        ),
        "sepsis_additionalIcd": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Additional sepsis ICD codes"
        ),

        # ========== RENAL/METABOLIC SECTION (12 fields) ==========
        "renalMetabolic_previousWeight": types.Schema(type=types.Type.NUMBER, nullable=True, description="Previous weight in grams or null"),
        "renalMetabolic_currentWeight": types.Schema(type=types.Type.NUMBER, nullable=True, description="Current weight in grams or null"),
        "renalMetabolic_uo": types.Schema(type=types.Type.NUMBER, nullable=True, description="Urine output in ml/kg/hr or null"),
        "renalMetabolic_bloodOut": types.Schema(type=types.Type.NUMBER, nullable=True, description="Blood output/loss in ml or null"),
        "renalMetabolic_drainOutput": types.Schema(type=types.Type.NUMBER, nullable=True, description="Drain output in ml or null"),
        "renalMetabolic_gir": types.Schema(type=types.Type.NUMBER, nullable=True, description="Glucose infusion rate mg/kg/min or null"),
        "renalMetabolic_dilutionExchange": types.Schema(type=types.Type.STRING, description="Dilution/Exchange done: Yes, No, or empty string"),
        "renalMetabolic_rbs": types.Schema(type=types.Type.NUMBER, nullable=True, description="Random blood sugar in mg/dL or null"),
        "renalMetabolic_serumNa": types.Schema(type=types.Type.NUMBER, nullable=True, description="Serum sodium in mEq/L or null"),
        "renalMetabolic_serumK": types.Schema(type=types.Type.NUMBER, nullable=True, description="Serum potassium in mEq/L or null"),
        "renalMetabolic_additionalIcd": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Additional renal/metabolic ICD codes"
        ),

        # ========== INVASIVE LINES SECTION (20 fields) ==========
        "invasiveLines_pvc_status": types.Schema(type=types.Type.STRING, description="PVC status: Yes, No, or empty string"),
        "invasiveLines_pvc_number": types.Schema(type=types.Type.INTEGER, nullable=True, description="Number of PVCs or null"),
        "invasiveLines_pvc_site": types.Schema(type=types.Type.STRING, description="PVC site: Left Hand, Right Foot, etc. or empty string"),
        "invasiveLines_pvc_day": types.Schema(type=types.Type.INTEGER, nullable=True, description="Days since PVC insertion or null"),
        "invasiveLines_pvc_dayChange": types.Schema(type=types.Type.BOOLEAN, description="PVC changed today true/false"),
        "invasiveLines_pvc_complication": types.Schema(type=types.Type.STRING, description="PVC complication or None"),
        "invasiveLines_picc_status": types.Schema(type=types.Type.STRING, description="PICC status: Yes, No, or empty string"),
        "invasiveLines_picc_site": types.Schema(type=types.Type.STRING, description="PICC site or N/A"),
        "invasiveLines_picc_day": types.Schema(type=types.Type.INTEGER, nullable=True, description="Days since PICC insertion or null"),
        "invasiveLines_picc_complication": types.Schema(type=types.Type.STRING, description="PICC complication or None"),
        "invasiveLines_uvc_status": types.Schema(type=types.Type.STRING, description="UVC status: Yes, No, or empty string"),
        "invasiveLines_uvc_position": types.Schema(type=types.Type.STRING, description="UVC position or N/A"),
        "invasiveLines_uvc_day": types.Schema(type=types.Type.INTEGER, nullable=True, description="Days since UVC insertion or null"),
        "invasiveLines_uvc_complication": types.Schema(type=types.Type.STRING, description="UVC complication or None"),
        "invasiveLines_uac_status": types.Schema(type=types.Type.STRING, description="UAC status: Yes, No, or empty string"),
        "invasiveLines_uac_position": types.Schema(type=types.Type.STRING, description="UAC position or N/A"),
        "invasiveLines_uac_day": types.Schema(type=types.Type.INTEGER, nullable=True, description="Days since UAC insertion or null"),
        "invasiveLines_uac_complication": types.Schema(type=types.Type.STRING, description="UAC complication or None"),
        "invasiveLines_pac_status": types.Schema(type=types.Type.STRING, description="PAC (peripheral arterial catheter) status: Yes, No, or empty string"),
        "invasiveLines_pac_site": types.Schema(type=types.Type.STRING, description="PAC site or N/A"),

        # ========== INOTROPES SECTION (6 fields) ==========
        "inotropes_status": types.Schema(type=types.Type.STRING, description="On inotropes: Yes, No, or empty string"),
        "inotropes_dopamine": types.Schema(type=types.Type.NUMBER, nullable=True, description="Dopamine dose mcg/kg/min or null"),
        "inotropes_dobutamine": types.Schema(type=types.Type.NUMBER, nullable=True, description="Dobutamine dose mcg/kg/min or null"),
        "inotropes_adrenaline": types.Schema(type=types.Type.NUMBER, nullable=True, description="Adrenaline dose mcg/kg/min or null"),
        "inotropes_noradrenaline": types.Schema(type=types.Type.NUMBER, nullable=True, description="Noradrenaline dose mcg/kg/min or null"),
        "inotropes_milrinone": types.Schema(type=types.Type.NUMBER, nullable=True, description="Milrinone dose mcg/kg/min or null"),

        # ========== SKIN SECTION (3 fields) ==========
        "skin_findings": types.Schema(type=types.Type.STRING, description="Skin examination findings: Normal, Rash, etc. or empty string"),
        "skin_additionalIcd": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Additional skin ICD codes"
        ),

        # ========== ROP SECTION (3 fields) ==========
        "rop_findings": types.Schema(type=types.Type.STRING, description="ROP findings: Screening due, No ROP, Stage 1, etc. or empty string"),
        "rop_additionalIcd": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Additional ROP ICD codes"
        ),

        # ========== TOP-LEVEL ARRAYS (for antibiotics, transfusions, fluids) ==========
        # These will be moved to top-level in formatter, but extracted here
        # Raster API expects drugId/fluidId - we extract names and assign sequential IDs
        "antibiotics_list": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "drugId": types.Schema(type=types.Type.INTEGER, nullable=True, description="Drug ID (auto-assigned if not known)"),
                    "drugName": types.Schema(type=types.Type.STRING, description="Antibiotic name (e.g., 'Ampicillin', 'Gentamicin')"),
                    "dose": types.Schema(type=types.Type.STRING, description="Dose with units (e.g., '50mg', '2.5mg/kg')"),
                    "frequency": types.Schema(type=types.Type.STRING, description="Frequency (e.g., 'BD', 'TDS', 'Q8H', '12 hourly')"),
                    "route": types.Schema(type=types.Type.STRING, description="Route of administration (e.g., 'IV', 'Oral', 'IM')"),
                }
            ),
            description="Array of antibiotics with complete details: [{drugId, drugName, dose, frequency, route}]. Extract ALL mentioned antibiotics with their dosing details."
        ),
        "transfusions_list": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "product": types.Schema(type=types.Type.STRING, description="Blood product type: PRBC, FFP, Platelets, Cryoprecipitate"),
                    "volume": types.Schema(type=types.Type.NUMBER, nullable=True, description="Volume in ml (e.g., 30, 50)"),
                }
            ),
            description="Array of blood transfusions: [{product, volume}]"
        ),
        "fluids_list": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "fluidId": types.Schema(type=types.Type.INTEGER, nullable=True, description="Fluid ID (auto-assigned if not known)"),
                    "fluidName": types.Schema(type=types.Type.STRING, description="IV fluid name (e.g., 'NS', 'D10', 'D5NS', 'RL')"),
                    "rate": types.Schema(type=types.Type.STRING, description="Infusion rate (e.g., '5ml/hr', '10ml/kg/day')"),
                    "duration": types.Schema(type=types.Type.STRING, description="Duration (e.g., '24h', 'continuous', 'bolus')"),
                }
            ),
            description="Array of IV fluids with complete details: [{fluidId, fluidName, rate, duration}]"
        ),
    }
)

# ============================================================================
# PROMPT TEMPLATES FOR SPLIT EXTRACTION - RASTER FORMAT
# ============================================================================

NEO_DAILY_SPLIT_SYSTEM_PROMPT = """You are a specialized clinical data extraction AI for neonatal daily progress notes.

**YOUR ROLE:**
Extract daily neonatal monitoring parameters from transcribed clinical notes and return structured JSON matching the Raster API format.

**CRITICAL RULES:**
1. NEVER fabricate clinical information or assume data not explicitly stated
2. Use empty string "" for unavailable text fields
3. Use null for unavailable numeric fields
4. Use empty array [] for unavailable array fields
5. Extract exact values as stated - no unit conversion or interpretation
6. If a value is corrected during dictation, use the LATEST/FINAL value

**HIGH PRIORITY FIELDS (extract with 100% accuracy):**
- uhid - Patient UHID
- dailyLog_date, dailyLog_time, dailyLog_dayOfLife - Recording info
- respiratory_support, respiratory_fiO2 - Respiratory support
- cvs_hr, cvs_systolicBp, cvs_diastolicBp - Hemodynamics
- gi_nutrition_feeds - CRITICAL: Type of feeding (Breastfeeding, Formula, EBM, NPO)
- gi_nutrition_volume, gi_nutrition_frequency - Feed details
- antibiotics_list - CRITICAL: Extract ALL antibiotics with COMPLETE details (drugName, dose, frequency, route)
- renalMetabolic_currentWeight - Current weight

**FLATTENED FIELD NAMING:**
Fields use underscore convention: {section}_{subsection}_{field}
Examples:
- respiratory_bloodGas_ph
- cvs_echo_status
- gi_nutrition_feeds
- invasiveLines_pvc_status

**OUTPUT FORMAT:**
Return ONLY valid JSON matching the schema. No markdown, no explanations."""

NEO_DAILY_PART1_USER_PROMPT = """Extract PART 1 (Patient + General + Respiratory + CVS) from this neonatal daily progress note:

---
{transcript}
---

**PART 1 SECTIONS TO EXTRACT:**
1. Patient identification (uhid)
2. Daily log general info (date, time, dayOfLife, careType, seenBy, background, problems)
3. Respiratory system (support type, ventilation settings, blood gas, examination)
4. CVS (heart rate, BP, perfusion, pulses, echo, PDA/PAH status)

**FIELD PREFIX CONVENTION:**
- dailyLog_* for general daily log fields
- dailyLog_problems_* for current/previous problems
- respiratory_* for respiratory section
- respiratory_bloodGas_* for blood gas values
- cvs_* for cardiovascular section
- cvs_echo_* for echo details

Return ONLY the JSON object. No markdown, no explanations."""

NEO_DAILY_PART2_USER_PROMPT = """Extract PART 2 (GI + CNS + Sepsis + Renal + Lines + Inotropes + Skin + ROP + Medications) from this neonatal daily progress note:

---
{transcript}
---

**PART 2 SECTIONS TO EXTRACT:**
1. GI system including nutrition (abdomen, bowel sounds, liver, spleen, NNJ, feeds/nutrition)
2. CNS (fontanelle, tone, activity, seizures, neuro imaging)
3. Sepsis (CRP, cultures, organisms)
4. Renal/Metabolic (weight, urine output, electrolytes, GIR)
5. Invasive Lines (PVC, PICC, UVC, UAC, PAC with sites and days)
6. Inotropes (dopamine, dobutamine, adrenaline, noradrenaline, milrinone doses)
7. Skin findings
8. ROP screening/findings
9. Antibiotics array (drugName, dose, frequency, route)
10. Transfusions array (product, volume)
11. IV Fluids array (fluidName, rate, duration)

**CRITICAL: gi_nutrition_feeds field must capture feeding type (Breastfeeding, Formula, EBM, NPO, etc.)**

**FIELD PREFIX CONVENTION:**
- gi_* for GI section
- gi_nutrition_* for nutrition details
- gi_liver_*, gi_spleen_*, gi_nnj_* for nested GI objects
- cns_* for CNS section
- sepsis_* for sepsis section
- renalMetabolic_* for renal/metabolic section
- invasiveLines_* for lines section with _pvc_, _picc_, _uvc_, _uac_, _pac_ subsections
- inotropes_* for inotrope drugs
- skin_*, rop_* for skin and ROP
- antibiotics_list, transfusions_list, fluids_list for arrays
{medicine_list_section}
{investigation_list_section}

Return ONLY the JSON object. No markdown, no explanations."""

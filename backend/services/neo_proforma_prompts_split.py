"""
Split NEO_PROFORMA Schema for Gemini API Compatibility

Even the flattened schema (185 properties) exceeds Gemini's constraint limits.
This module splits the extraction into TWO separate API calls:

PART 1 (70 fields): BABY VITALS & IMMEDIATE CARE
- Baby demographics, APGAR scores (totals auto-calculated), birth vitals
- dateTime auto-filled from current timestamp
- Resuscitation details, delivery room procedures
- Medical problems, initial examination

PART 2 (109 fields): MATERNAL HISTORY & PREGNANCY
- Maternal demographics, previous births
- Pregnancy complications, antenatal scans
- Labour and delivery details, maternal health

The neo_proforma_formatter.py service merges both results into the final nested structure.
"""

from google import genai
from google.genai import types

# ============================================================================
# PART 1: BABY VITALS & IMMEDIATE CARE (76 fields)
# ============================================================================

NEO_PROFORMA_PART1_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== BABY IDENTIFICATION & BIRTH DETAILS ==========
        "uhid": types.Schema(type=types.Type.STRING, description="Patient unique hospital ID or empty string"),
        # dateTime - AUTO-FILLED from current timestamp, removed from schema
        "babyName": types.Schema(type=types.Type.STRING, description="Baby name (e.g., B/O Nithya) or empty string"),
        "dob": types.Schema(type=types.Type.STRING, description="Date of birth in YYYY-MM-DD format or empty string"),
        "tob": types.Schema(type=types.Type.STRING, description="Time of birth in HH:MM format or empty string"),
        "birthStatus": types.Schema(type=types.Type.STRING, description="Inborn, Outborn, or empty string"),
        "birthWeight": types.Schema(type=types.Type.STRING, description="Birth weight in grams as string (e.g., '2400') or empty string"),
        "gestationWeeks": types.Schema(type=types.Type.STRING, description="Gestational age weeks part (e.g., '34') or empty string"),
        "gestationDays": types.Schema(type=types.Type.STRING, description="Gestational age days part (e.g., '1') or empty string"),
        "babyBloodGroup": types.Schema(type=types.Type.STRING, description="Baby's blood group with full text (e.g., 'A Positive', 'O Negative') or empty string"),
        "birthOrder": types.Schema(type=types.Type.STRING, description="Birth order - CRITICAL: '1' for first child/primigravida, '2' for second child, '1st of twins'/'Twin A' for multiples. ALWAYS extract, use '1' if primigravida or single baby"),
        "sex": types.Schema(type=types.Type.STRING, description="Male, Female, Ambiguous, or empty string"),
        "birthLength": types.Schema(type=types.Type.STRING, description="Birth length in cm as string (e.g., '45') or empty string"),
        "birthHeadCircunference": types.Schema(type=types.Type.STRING, description="Head circumference in cm as string (e.g., '36') or empty string"),
        "transferStatus": types.Schema(type=types.Type.STRING, description="Transfer destination: NICU, Ward, Special Care, Observation, or empty string"),

        # ========== MATERNAL MEDICAL PROBLEMS (FLATTENED) ==========
        "medicalProblemIDs": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.INTEGER),
            description="Array of MATERNAL medical problem IDs: 1=RHD, 2=Chronic Hypertension, 3=Type 1 DM, 4=Type 2 DM, 5=Hypothyroidism, 6=UTI, 7=Chronic Renal Failure, 8=Anemia, 9=Bronchial Asthma, 10=Epilepsy, 11=TB, 12=Syphilis, 13=Viral Hepatitis, 14=Septicemia, 15=Varicella, 16=SLE, 23=Thyroid disorders, 24=PIH, 27=Retroviral disease, 30=ITP, 33=PCOD, 37=Overt diabetes, 45=Obesity, 54=Thalassemic trait, 55=GDM, 57=Endometriosis, 77=Pulmonary hypertension, 86=Rheumatoid arthritis, 90=Sickle cell disease"
        ),
        "medicalProblemMedications": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Array of medications for each maternal medical problem (same order as IDs) or empty strings"
        ),

        # ========== APGAR SCORES (26 fields - totals auto-calculated) ==========
        "apgar_status": types.Schema(type=types.Type.STRING, description="'known' or 'unknown'"),

        # Minute 1
        "apgar_minute1_color": types.Schema(type=types.Type.INTEGER, nullable=True, description="Color score (0-2) at 1 minute or null"),
        "apgar_minute1_heartRate": types.Schema(type=types.Type.INTEGER, nullable=True, description="Heart rate score (0-2) at 1 minute or null"),
        "apgar_minute1_reflex": types.Schema(type=types.Type.INTEGER, nullable=True, description="Reflex score (0-2) at 1 minute or null"),
        "apgar_minute1_tone": types.Schema(type=types.Type.INTEGER, nullable=True, description="Muscle tone score (0-2) at 1 minute or null"),
        "apgar_minute1_respiration": types.Schema(type=types.Type.INTEGER, nullable=True, description="Respiration score (0-2) at 1 minute or null"),
        # apgar_minute1_total - AUTO-CALCULATED from individual scores

        # Minute 5
        "apgar_minute5_color": types.Schema(type=types.Type.INTEGER, nullable=True, description="Color score (0-2) at 5 minutes or null"),
        "apgar_minute5_heartRate": types.Schema(type=types.Type.INTEGER, nullable=True, description="Heart rate score (0-2) at 5 minutes or null"),
        "apgar_minute5_reflex": types.Schema(type=types.Type.INTEGER, nullable=True, description="Reflex score (0-2) at 5 minutes or null"),
        "apgar_minute5_tone": types.Schema(type=types.Type.INTEGER, nullable=True, description="Muscle tone score (0-2) at 5 minutes or null"),
        "apgar_minute5_respiration": types.Schema(type=types.Type.INTEGER, nullable=True, description="Respiration score (0-2) at 5 minutes or null"),
        # apgar_minute5_total - AUTO-CALCULATED from individual scores

        # Minute 10
        "apgar_minute10_color": types.Schema(type=types.Type.INTEGER, nullable=True, description="Color score (0-2) at 10 minutes or null"),
        "apgar_minute10_heartRate": types.Schema(type=types.Type.INTEGER, nullable=True, description="Heart rate score (0-2) at 10 minutes or null"),
        "apgar_minute10_reflex": types.Schema(type=types.Type.INTEGER, nullable=True, description="Reflex score (0-2) at 10 minutes or null"),
        "apgar_minute10_tone": types.Schema(type=types.Type.INTEGER, nullable=True, description="Muscle tone score (0-2) at 10 minutes or null"),
        "apgar_minute10_respiration": types.Schema(type=types.Type.INTEGER, nullable=True, description="Respiration score (0-2) at 10 minutes or null"),
        # apgar_minute10_total - AUTO-CALCULATED from individual scores

        # Minute 15
        "apgar_minute15_color": types.Schema(type=types.Type.INTEGER, nullable=True, description="Color score (0-2) at 15 minutes or null"),
        "apgar_minute15_heartRate": types.Schema(type=types.Type.INTEGER, nullable=True, description="Heart rate score (0-2) at 15 minutes or null"),
        "apgar_minute15_reflex": types.Schema(type=types.Type.INTEGER, nullable=True, description="Reflex score (0-2) at 15 minutes or null"),
        "apgar_minute15_tone": types.Schema(type=types.Type.INTEGER, nullable=True, description="Muscle tone score (0-2) at 15 minutes or null"),
        "apgar_minute15_respiration": types.Schema(type=types.Type.INTEGER, nullable=True, description="Respiration score (0-2) at 15 minutes or null"),
        # apgar_minute15_total - AUTO-CALCULATED from individual scores

        # Minute 20
        "apgar_minute20_color": types.Schema(type=types.Type.INTEGER, nullable=True, description="Color score (0-2) at 20 minutes or null"),
        "apgar_minute20_heartRate": types.Schema(type=types.Type.INTEGER, nullable=True, description="Heart rate score (0-2) at 20 minutes or null"),
        "apgar_minute20_reflex": types.Schema(type=types.Type.INTEGER, nullable=True, description="Reflex score (0-2) at 20 minutes or null"),
        "apgar_minute20_tone": types.Schema(type=types.Type.INTEGER, nullable=True, description="Muscle tone score (0-2) at 20 minutes or null"),
        "apgar_minute20_respiration": types.Schema(type=types.Type.INTEGER, nullable=True, description="Respiration score (0-2) at 20 minutes or null"),
        # apgar_minute20_total - AUTO-CALCULATED from individual scores

        # ========== RESUSCITATION DETAILS ==========
        "facialOxygen": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "durationOfFacialOxygen": types.Schema(type=types.Type.STRING, description="Duration of facial oxygen or empty string"),
        "maximumFio2Rquired": types.Schema(type=types.Type.STRING, description="Maximum FiO2 required (e.g., '40%') or empty string"),
        "resuscitation": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "initialSteps": types.Schema(type=types.Type.STRING, description="Initial resuscitation steps taken or empty string"),
        "timeOf1stGasp": types.Schema(type=types.Type.STRING, description="Time of first gasp in HH:MM format or empty string"),
        "timeOf1stGaspInMinutes": types.Schema(type=types.Type.STRING, description="Time of first gasp in minutes or empty string"),
        "regularRespiration": types.Schema(type=types.Type.STRING, description="Time of regular respiration in HH:MM format or empty string"),
        "regularRespirationMinutes": types.Schema(type=types.Type.STRING, description="Time of regular respiration in minutes or empty string"),
        "deliveryRoomCPAP": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "bagMaskVentilation": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "bagMaskVentilationDuration": types.Schema(type=types.Type.STRING, description="Duration of bag mask ventilation or empty string"),
        "bagMaskVentilationDurationMin": types.Schema(type=types.Type.STRING, description="Duration of bag mask ventilation in minutes or empty string"),
        "intubation": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "ETTSizeInMM": types.Schema(type=types.Type.STRING, description="ETT size in mm (e.g., '3.0', '3.5') or empty string"),
        "depthOfInsertion": types.Schema(type=types.Type.STRING, description="Depth of ETT insertion or empty string"),
        "depthOfInsertionLengthInCM": types.Schema(type=types.Type.STRING, description="Depth of ETT insertion in cm or empty string"),
        "PPV": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "durationOfPTV": types.Schema(type=types.Type.STRING, description="Duration of positive pressure ventilation or empty string"),
        "durationOfPTVMinutes": types.Schema(type=types.Type.STRING, description="Duration of PPV in minutes or empty string"),
        "CPR": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "durationOfCPR": types.Schema(type=types.Type.STRING, description="Duration of CPR or empty string"),
        "durationOfCPRMinutes": types.Schema(type=types.Type.STRING, description="Duration of CPR in minutes or empty string"),
        "drugs": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "drugDetails": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="List of drugs administered during resuscitation or empty array"
        ),

        # ========== VITAMIN K & OTHER PROCEDURES ==========
        "vitaminK": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "vitaminKDose": types.Schema(type=types.Type.STRING, description="Vitamin K dose (e.g., '1mg') or empty string"),
        "vitaminKRoute": types.Schema(type=types.Type.STRING, description="Route of vitamin K administration (IM, Oral) or empty string"),

        # ========== INITIAL EXAMINATION & CLINICAL ASSESSMENT ==========
        "initialExaminationSummary": types.Schema(type=types.Type.STRING, description="HIGH PRIORITY - Initial physical examination findings. Extract if ANY examination details mentioned: cry quality ('cried immediately'), tone ('active', 'good tone'), color ('pink'), respiratory effort. NEVER leave empty if examination mentioned"),
        "malformation": types.Schema(type=types.Type.STRING, description="Congenital malformations noted or empty string"),
        "ICT": types.Schema(type=types.Type.STRING, description="ICT (Indirect Coombs Test) result or empty string"),
        "DCT": types.Schema(type=types.Type.STRING, description="DCT (Direct Coombs Test) result or empty string"),
        "backgroundDetails": types.Schema(type=types.Type.STRING, description="Background clinical details or empty string"),
        "plan": types.Schema(type=types.Type.STRING, description="Clinical management plan or empty string"),
    }
)

# ============================================================================
# PART 2: MATERNAL HISTORY & PREGNANCY (109 fields)
# ============================================================================

NEO_PROFORMA_PART2_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # ========== MATERNAL OBSTETRIC HISTORY ==========
        "consanguinity": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "gravida": types.Schema(type=types.Type.STRING, description="HIGH PRIORITY - Total pregnancies including current. Use '1' if primigravida or first pregnancy"),
        "para": types.Schema(type=types.Type.STRING, description="HIGH PRIORITY - Previous deliveries after 20 weeks (EXCLUDES current). CRITICAL: Use '0' if primigravida or first pregnancy, gravida 1 means para MUST be '0'"),
        "liveBirth": types.Schema(type=types.Type.STRING, description="HIGH PRIORITY - Number of previous living children (EXCLUDES current baby). Use '0' if primigravida or no previous children"),
        "abortion": types.Schema(type=types.Type.STRING, description="HIGH PRIORITY - Number of previous abortions/miscarriages. Use '0' if no mention of losses"),

        # ========== PREVIOUS LIVE BIRTH DETAILS (18 fields) ==========
        # Previous Birth 1
        "liveBirth1_birthYear": types.Schema(type=types.Type.STRING, description="Year of birth for first previous baby or empty string"),
        "liveBirth1_place": types.Schema(type=types.Type.STRING, description="Place of birth for first previous baby or empty string"),
        "liveBirth1_typeOfDelivery": types.Schema(type=types.Type.STRING, description="Type of delivery for first previous baby or empty string"),
        "liveBirth1_complications": types.Schema(type=types.Type.STRING, description="Complications for first previous baby or empty string"),
        "liveBirth1_gender": types.Schema(type=types.Type.STRING, description="Gender of first previous baby or empty string"),
        "liveBirth1_gestation": types.Schema(type=types.Type.STRING, description="Gestation of first previous baby or empty string"),
        "liveBirth1_birthWeight": types.Schema(type=types.Type.STRING, description="Birth weight of first previous baby or empty string"),
        "liveBirth1_health": types.Schema(type=types.Type.STRING, description="Health status of first previous baby or empty string"),
        "liveBirth1_details": types.Schema(type=types.Type.STRING, description="Additional details for first previous baby or empty string"),

        # Previous Birth 2
        "liveBirth2_birthYear": types.Schema(type=types.Type.STRING, description="Year of birth for second previous baby or empty string"),
        "liveBirth2_place": types.Schema(type=types.Type.STRING, description="Place of birth for second previous baby or empty string"),
        "liveBirth2_typeOfDelivery": types.Schema(type=types.Type.STRING, description="Type of delivery for second previous baby or empty string"),
        "liveBirth2_complications": types.Schema(type=types.Type.STRING, description="Complications for second previous baby or empty string"),
        "liveBirth2_gender": types.Schema(type=types.Type.STRING, description="Gender of second previous baby or empty string"),
        "liveBirth2_gestation": types.Schema(type=types.Type.STRING, description="Gestation of second previous baby or empty string"),
        "liveBirth2_birthWeight": types.Schema(type=types.Type.STRING, description="Birth weight of second previous baby or empty string"),
        "liveBirth2_health": types.Schema(type=types.Type.STRING, description="Health status of second previous baby or empty string"),
        "liveBirth2_details": types.Schema(type=types.Type.STRING, description="Additional details for second previous baby or empty string"),

        # ========== PREGNANCY DETAILS ==========
        "conception": types.Schema(type=types.Type.STRING, description="Spontaneous, IVF, IUI, Ovulation Induction, or empty string"),
        "lmp": types.Schema(type=types.Type.STRING, description="Last menstrual period in YYYY-MM-DD format or empty string"),
        "EDDByUSG": types.Schema(type=types.Type.STRING, description="Expected delivery date by ultrasound in YYYY-MM-DD format or empty string"),
        "EDDByDate": types.Schema(type=types.Type.STRING, description="Expected delivery date by LMP in YYYY-MM-DD format or empty string"),

        # ========== ANTENATAL SCREENING ==========
        "motherBloodGroup": types.Schema(type=types.Type.STRING, description="Mother's blood group with full text (e.g., 'O Positive', 'A Negative') or empty string"),
        "HIV": types.Schema(type=types.Type.STRING, description="Positive, Negative, Not Tested, or empty string"),
        "HepatitisB": types.Schema(type=types.Type.STRING, description="Positive, Negative, Not Tested, or empty string"),
        "VDRL": types.Schema(type=types.Type.STRING, description="Positive, Negative, Not Tested, or empty string"),
        "booked": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "bookedPlace": types.Schema(type=types.Type.STRING, description="Name of facility where booked or empty string"),
        "pleaceOfBooking": types.Schema(type=types.Type.STRING, description="Place of booking or empty string"),
        "supervised": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "pleaceOfSupervision": types.Schema(type=types.Type.STRING, description="Place of supervision or empty string"),

        # ========== ANTENATAL INVESTIGATIONS ==========
        "adjustedRiskForTrisomiesAvailable": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "adjustedRiskForTrisomy21": types.Schema(type=types.Type.STRING, description="Risk ratio (e.g., '1:150') or empty string"),
        "adjustedRiskForTrisomy18": types.Schema(type=types.Type.STRING, description="Risk ratio (e.g., '1:2500') or empty string"),
        "adjustedRiskForTrisomy13": types.Schema(type=types.Type.STRING, description="Risk ratio (e.g., '1:5000') or empty string"),
        "otherInvestigations": types.Schema(type=types.Type.STRING, description="Other prenatal investigations or empty string"),

        # ========== PREGNANCY COMPLICATIONS (8 fields) ==========
        "multiplePregnancy": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "pregnancyComplications": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),

        # Complication 1
        "complication1_name": types.Schema(type=types.Type.STRING, description="Name of first pregnancy complication or empty string"),
        "complication1_treatment": types.Schema(type=types.Type.STRING, description="Treatment for first complication or empty string"),
        "complication1_duration": types.Schema(type=types.Type.STRING, description="Duration of first complication or empty string"),
        "complication1_durationType": types.Schema(type=types.Type.STRING, description="Duration type (weeks, months) for first complication or empty string"),

        # Complication 2
        "complication2_name": types.Schema(type=types.Type.STRING, description="Name of second pregnancy complication or empty string"),
        "complication2_treatment": types.Schema(type=types.Type.STRING, description="Treatment for second complication or empty string"),
        "complication2_duration": types.Schema(type=types.Type.STRING, description="Duration of second complication or empty string"),
        "complication2_durationType": types.Schema(type=types.Type.STRING, description="Duration type (weeks, months) for second complication or empty string"),

        # ========== ANTENATAL STEROIDS ==========
        "antenatalSteroids": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "typeOfSteriods": types.Schema(type=types.Type.STRING, description="Type of steroids (e.g., Betamethasone, Dexamethasone) or empty string"),
        "lastDoseDeliveryInterval": types.Schema(type=types.Type.STRING, description="Interval between last steroid dose and delivery or empty string"),
        "steroidCourse": types.Schema(type=types.Type.STRING, description="Steroid course details (complete, partial) or empty string"),
        "antenatalMgSO4ForNeuroprotection": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),

        # ========== ANTENATAL SCANS (15 fields) ==========
        # Dating Scan
        "datingScan_date": types.Schema(type=types.Type.STRING, description="Dating scan date in YYYY-MM-DD format or empty string"),
        "datingScan_gestation": types.Schema(type=types.Type.STRING, description="Gestation at dating scan or empty string"),
        "datingScan_findings": types.Schema(type=types.Type.STRING, description="Dating scan findings or empty string"),

        # Anomaly Scan
        "anomalyScan_date": types.Schema(type=types.Type.STRING, description="Anomaly scan date in YYYY-MM-DD format or empty string"),
        "anomalyScan_gestation": types.Schema(type=types.Type.STRING, description="Gestation at anomaly scan or empty string"),
        "anomalyScan_findings": types.Schema(type=types.Type.STRING, description="Anomaly scan findings or empty string"),

        # Other Scan 1
        "otherScan1_date": types.Schema(type=types.Type.STRING, description="Other scan 1 date in YYYY-MM-DD format or empty string"),
        "otherScan1_gestation": types.Schema(type=types.Type.STRING, description="Gestation at other scan 1 or empty string"),
        "otherScan1_findings": types.Schema(type=types.Type.STRING, description="Other scan 1 findings or empty string"),

        # Other Scan 2
        "otherScan2_date": types.Schema(type=types.Type.STRING, description="Other scan 2 date in YYYY-MM-DD format or empty string"),
        "otherScan2_gestation": types.Schema(type=types.Type.STRING, description="Gestation at other scan 2 or empty string"),
        "otherScan2_findings": types.Schema(type=types.Type.STRING, description="Other scan 2 findings or empty string"),

        # Doppler Scan 1
        "dopplerScan1_date": types.Schema(type=types.Type.STRING, description="Doppler scan 1 date in YYYY-MM-DD format or empty string"),
        "dopplerScan1_gestation": types.Schema(type=types.Type.STRING, description="Gestation at Doppler scan 1 or empty string"),
        "dopplerScan1_findings": types.Schema(type=types.Type.STRING, description="Doppler scan 1 findings or empty string"),

        # Doppler Scan 2
        "dopplerScan2_date": types.Schema(type=types.Type.STRING, description="Doppler scan 2 date in YYYY-MM-DD format or empty string"),
        "dopplerScan2_gestation": types.Schema(type=types.Type.STRING, description="Gestation at Doppler scan 2 or empty string"),
        "dopplerScan2_findings": types.Schema(type=types.Type.STRING, description="Doppler scan 2 findings or empty string"),

        # ========== LABOUR & DELIVERY ==========
        "labour": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "natureofLabour": types.Schema(type=types.Type.STRING, description="Spontaneous, Induced, or empty string"),
        "commentOnLiquor": types.Schema(type=types.Type.STRING, description="Liquor comments (Clear, Meconium Stained, etc.) or empty string"),

        # Risk Factors for Sepsis
        "riskFactorsForSepsisInMothers": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "riskFactors": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="List of maternal risk factors for sepsis or empty array"
        ),
        "maternalPyrexia": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "maternalPyrexiaTemperatureFahrenheit": types.Schema(type=types.Type.STRING, description="Maternal pyrexia temperature in Fahrenheit or empty string"),
        "PROM": types.Schema(type=types.Type.STRING, description="Premature rupture of membranes: Yes, No, or empty string"),
        "durationOfPROM": types.Schema(type=types.Type.STRING, description="Duration of PROM in hours or empty string"),

        # Maternal Antibiotics
        "maternalAntibiotics": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "maternalAntibioticsArray": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="List of maternal antibiotics or empty array"
        ),
        "timeOfLastDose": types.Schema(type=types.Type.STRING, description="Time of last antibiotic dose in HH:MM format or empty string"),

        # Mode of Delivery
        "modeOfDelivery": types.Schema(type=types.Type.STRING, description="Mode of delivery (LSCS, Vaginal, Forceps, Vacuum) or empty string"),
        "presentation": types.Schema(type=types.Type.STRING, description="Fetal presentation (Cephalic, Breech, Transverse) or empty string"),
        "indication": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="Indications for mode of delivery or empty array"
        ),

        # Fetal Monitoring
        "fetalDistress": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "CTG": types.Schema(type=types.Type.STRING, description="CTG performed: Yes, No, or empty string"),
        "CTGDetails": types.Schema(type=types.Type.STRING, description="CTG details or empty string"),

        # Cord Blood Gas
        "cordBloodGas": types.Schema(type=types.Type.STRING, description="Cord blood gas done: Yes, No, or empty string"),
        "cordPH": types.Schema(type=types.Type.STRING, description="Cord blood pH value or empty string"),
        "cordHCO3": types.Schema(type=types.Type.STRING, description="Cord blood HCO3 value or empty string"),
        "cordBE": types.Schema(type=types.Type.STRING, description="Cord blood base excess or empty string"),

        # Anesthesia
        "typeofAnesthesia": types.Schema(type=types.Type.STRING, description="Type of anesthesia (General, Spinal, Epidural) or empty string"),

        # Gastric Aspirate
        "gastricAspirate": types.Schema(type=types.Type.STRING, description="Gastric aspirate findings or empty string"),

        # Delayed Cord Clamping
        "delayedCordClamping": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "delayedCordClampingduration": types.Schema(type=types.Type.STRING, description="Duration of delayed cord clamping in seconds or empty string"),
        "reasonForNoDCC": types.Schema(type=types.Type.STRING, description="Reason for not doing delayed cord clamping or empty string"),
        "umbilicalCordMilking": types.Schema(type=types.Type.STRING, description="Yes, No, or empty string"),
        "cutCordMilking": types.Schema(type=types.Type.STRING, description="Cut cord milking details or empty string"),
    }
)

"""
Cardio GKNM Schema - types.Schema format for Gemini API structured output
Matches the GKNM Cardiology consultation output format from Cardio.md
"""

from google.genai import types

# Cardio GKNM Parameters Schema - Matches GKNM Hospital Cardiology format
CARDIO_GKNM_PARAMETERS_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # Section 1: Allergies (separate from history)
        "allergies": types.Schema(
            type=types.Type.STRING,
            description="Known allergies or 'NO KNOWN ALLERGY' if none"
        ),

        # Section 2: Vitals
        "vitals": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "blood_pressure": types.Schema(type=types.Type.STRING, description="Blood pressure in mmHg (e.g., '170/80 mmHg')"),
                "pulse": types.Schema(type=types.Type.STRING, description="Pulse rate in bpm (e.g., '42 bpm')"),
                "temperature": types.Schema(type=types.Type.STRING, description="Temperature in F (e.g., '96.80 F')"),
                "bmi": types.Schema(type=types.Type.STRING, description="BMI in kg/m2 (e.g., '34.63 kg/m2')"),
                "height": types.Schema(type=types.Type.STRING, description="Height in cm (e.g., '155.0 cm')"),
                "weight": types.Schema(type=types.Type.STRING, description="Weight in kg (e.g., '83.20 kg')"),
                "pulse_oximetry": types.Schema(type=types.Type.STRING, description="SpO2 percentage (e.g., '98 percent')"),
                "bsa": types.Schema(type=types.Type.STRING, description="Body Surface Area in m2 (e.g., '1.89 m2')"),
                "respiratory_rate": types.Schema(type=types.Type.STRING, description="Respiratory rate or N/A")
            },
            description="Vital signs measurements"
        ),

        # Section 3: Diagnosis - Table format with Name, Type, Code
        "diagnosis": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Diagnosis name with comments (e.g., 'Heart failure - Comments : with mildly improved EF - ischemic')"),
                    "type": types.Schema(type=types.Type.STRING, description="Primary or Secondary"),
                    "code": types.Schema(type=types.Type.STRING, description="ICD-10 code (e.g., 'I50.9')")
                }
            ),
            description="List of diagnoses with type and ICD-10 codes"
        ),

        # Section 4: Previous Cardiac History
        "previousCardiacHistory": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "primary_consultant": types.Schema(type=types.Type.STRING, description="Primary consultant name (e.g., 'Dr.AP')"),
                "comorbidities": types.Schema(type=types.Type.STRING, description="Comorbidities like Systemic hypertension, Type II diabetes mellitus"),
                "cardiac_conditions": types.Schema(type=types.Type.STRING, description="Cardiac conditions with dates (e.g., 'Atrial fibrillation - 4/25 : ? sick sinus syndrome - on treatment')"),
                "previous_admissions": types.Schema(type=types.Type.STRING, description="Previous admissions with dates and details"),
                "cag_findings": types.Schema(type=types.Type.STRING, description="Coronary Angiography findings with date (e.g., 'CAG : 16/6/25 : Two vessel disease')"),
                "treatment_plan": types.Schema(type=types.Type.STRING, description="Treatment plan (e.g., 'Plan : Medical Management / PCI - OM2 , if angina occurs')"),
                "echo_findings": types.Schema(type=types.Type.STRING, description="Echo findings with date (e.g., '9/9/25 Echo : RWMA with mild LVD (EF-49%)...')"),
                "clinical_notes": types.Schema(type=types.Type.STRING, description="Additional clinical notes (e.g., 'Not a good candidate for SGLT2')")
            },
            description="Previous cardiac history and relevant cardiac workup"
        ),

        # Section 5: History of Present Illness
        "historyOfPresentIllness": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "last_visit": types.Schema(type=types.Type.STRING, description="Last visit date and doctor (e.g., 'Last visit 04/11/2025 under Dr. AP')"),
                "recent_labs": types.Schema(type=types.Type.STRING, description="Recent lab values (e.g., 'cr- 1.0, K+ 5.3, hb- 12.1')"),
                "activity_status": types.Schema(type=types.Type.STRING, description="Activity status (e.g., 'Does not go for walk')"),
                "current_complaints": types.Schema(type=types.Type.STRING, description="Current complaints with details (e.g., 'C/of right lower limb pain yesterday night...')"),
                "negative_symptoms": types.Schema(type=types.Type.STRING, description="Symptoms denied (e.g., 'No dyspnea, palpitation, giddiness')"),
                "adl_status": types.Schema(type=types.Type.STRING, description="Activities of Daily Living status (e.g., 'ADL- Good')"),
                "current_medications": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "name": types.Schema(type=types.Type.STRING, description="Medication name with strength (e.g., 'TAB RIVAFLO 20MG')"),
                            "schedule": types.Schema(type=types.Type.STRING, description="Schedule (e.g., 'OD', 'BD', 'HS', 'SOS')")
                        }
                    ),
                    description="Current medications patient is on ('On drugs' section)"
                ),
                "other_specialty_medications": types.Schema(type=types.Type.STRING, description="Medications from other specialists (e.g., 'Nephro drugs under Dr. Goutam: TAB NACSAVE Q OD')")
            },
            description="History of present illness with current status"
        ),

        # Section 6: Examination
        "examination": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "systemic": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "cns": types.Schema(type=types.Type.STRING, description="CNS findings (e.g., 'NFND')"),
                        "cvs": types.Schema(type=types.Type.STRING, description="CVS findings (e.g., 'S1S2 Heard')"),
                        "respiratory": types.Schema(type=types.Type.STRING, description="RS findings (e.g., 'NVBS')")
                    },
                    description="Systemic examination findings"
                ),
                "cardiac_examination": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "supine_bp": types.Schema(type=types.Type.STRING, description="Supine blood pressure (e.g., '170/80')"),
                        "pulse_rate": types.Schema(type=types.Type.STRING, description="Pulse rate with regularity (e.g., 'Pulse Rate Is Irregular: 42')"),
                        "pedal_edema": types.Schema(type=types.Type.STRING, description="Pedal edema status (e.g., 'No Pedal Edema')")
                    },
                    description="Cardiac examination findings"
                )
            },
            description="Physical examination findings"
        ),

        # Section 7: Ordered Labs
        "orderedLabs": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "test_name": types.Schema(type=types.Type.STRING, description="Test name (e.g., 'POTASSIUM')"),
                    "date": types.Schema(type=types.Type.STRING, description="Order date (e.g., 'Dec 26, 2025')"),
                    "urgency": types.Schema(type=types.Type.STRING, description="Routine or Urgent")
                }
            ),
            description="Labs ordered during this visit"
        ),

        # Section 8: Lab Results - Table format
        "labResults": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "test_name": types.Schema(type=types.Type.STRING, description="Test name with date (e.g., 'POTASSIUM on 2025-11-25 12:11')"),
                    "parameter_name": types.Schema(type=types.Type.STRING, description="Parameter (e.g., 'POTASSIUM')"),
                    "result": types.Schema(type=types.Type.STRING, description="Result with units (e.g., '5.3 - mmol/L')"),
                    "ref_range": types.Schema(type=types.Type.STRING, description="Reference range (e.g., '3.5-5.1')")
                }
            ),
            description="Lab results table"
        ),

        # Section 9: Ordered Radiology
        "orderedRadiology": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "study_name": types.Schema(type=types.Type.STRING, description="Study name (e.g., 'ECG')"),
                    "date": types.Schema(type=types.Type.STRING, description="Order/result date (e.g., 'Dec 26, 2025')"),
                    "status": types.Schema(type=types.Type.STRING, description="routine, resulted, or pending")
                }
            ),
            description="Radiology/imaging orders"
        ),

        # Section 10: Medication Chart - GKNM format
        "medicationChart": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "sr_no": types.Schema(type=types.Type.STRING, description="Serial number"),
                    "generic_name": types.Schema(type=types.Type.STRING, description="Brand name with generic (e.g., 'RIVAFLO 20mg TAB (RIVAROXABAN 20MG TAB)')"),
                    "schedule": types.Schema(type=types.Type.STRING, description="Schedule in 1-0-0-0 format with description (e.g., '1-0-0-0 EVERY MORNING')"),
                    "unit": types.Schema(type=types.Type.STRING, description="Unit (e.g., 'TABLET')"),
                    "route": types.Schema(type=types.Type.STRING, description="Route (e.g., 'ORAL')"),
                    "days": types.Schema(type=types.Type.STRING, description="Duration in days"),
                    "qty": types.Schema(type=types.Type.STRING, description="Total quantity"),
                    "meal_relationship": types.Schema(type=types.Type.STRING, description="Relationship with meal (e.g., 'AFTER MEAL')"),
                    "comment": types.Schema(type=types.Type.STRING, description="Additional comments or '-'")
                }
            ),
            description="Medication chart with GKNM hospital format"
        ),

        # Section 11: Care Plan and Advice
        "carePlanAndAdvice": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "patient_summary": types.Schema(type=types.Type.STRING, description="Brief summary (e.g., 'Patient history noted')"),
                "current_vitals_summary": types.Schema(type=types.Type.STRING, description="Key vitals (e.g., 'BP- 170/80 mmHg')"),
                "ecg_summary": types.Schema(type=types.Type.STRING, description="ECG findings (e.g., 'ECG- AF with SVR, HR - 40bpm')"),
                "labs_summary": types.Schema(type=types.Type.STRING, description="Key lab values (e.g., 'Blood reports:CR- 1.0, K+ 5.3')"),
                "diet_advice": types.Schema(type=types.Type.STRING, description="Dietary advice (e.g., 'Potassium free diet')"),
                "medication_changes": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(type=types.Type.STRING, description="Action: Hold, Decrease, Increase, Continue, Start, Stop"),
                            "medication": types.Schema(type=types.Type.STRING, description="Medication name"),
                            "reason": types.Schema(type=types.Type.STRING, description="Reason for change (e.g., 'due to bradycardia')")
                        }
                    ),
                    description="Medication changes"
                ),
                "other_advice": types.Schema(type=types.Type.STRING, description="Other advice"),
                "assisted_by": types.Schema(type=types.Type.STRING, description="Name of assistant (e.g., 'assisted by Akila')")
            },
            description="Care plan and advice summary"
        ),

        # Section 12: Follow Up and Instructions
        "followUpAndInstructions": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "review_with_reports": types.Schema(type=types.Type.STRING, description="Review date (e.g., '26/12/2025')"),
                "doctor_name": types.Schema(type=types.Type.STRING, description="Doctor to follow up with (e.g., 'Dr.Prabhakaran OPD')"),
                "reports_needed": types.Schema(type=types.Type.STRING, description="Reports to bring (e.g., 'ECG, creatinine, potassium reports')"),
                "timeline": types.Schema(type=types.Type.STRING, description="Timeline (e.g., 'after 1 month')")
            },
            description="Follow up instructions"
        ),

        # Section 13: Emergency Contacts
        "emergencyContacts": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "purpose": types.Schema(type=types.Type.STRING, description="Purpose (e.g., 'For Appointments', 'For Medical Emergency')"),
                    "number": types.Schema(type=types.Type.STRING, description="Contact number(s)")
                }
            ),
            description="Emergency contact list"
        ),

        # Section 14: Signature
        "signature": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "doctor_name": types.Schema(type=types.Type.STRING, description="Doctor's name (e.g., 'DR.CHA R')"),
                "qualifications": types.Schema(type=types.Type.STRING, description="Qualifications (e.g., 'MD, DM, Cardiology')"),
                "date_time": types.Schema(type=types.Type.STRING, description="Date and time of signature (e.g., 'Nov 25, 2025@14:24')")
            },
            description="Doctor signature information"
        )
    },
    required=[
        "allergies",
        "vitals",
        "diagnosis",
        "previousCardiacHistory",
        "historyOfPresentIllness",
        "examination",
        "orderedLabs",
        "labResults",
        "orderedRadiology",
        "medicationChart",
        "carePlanAndAdvice",
        "followUpAndInstructions",
        "emergencyContacts",
        "signature"
    ]
)

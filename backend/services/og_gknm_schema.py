"""
OB-GYN GKNM Schema - types.Schema format for Gemini API structured output
Matches the GKNM Obstetrics & Gynecology consultation output format from OG Casesheet.md
"""

from google.genai import types

# OB-GYN GKNM Parameters Schema - Matches GKNM School OB-GYN format
OG_GKNM_PARAMETERS_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # Section 1: Allergies
        "allergies": types.Schema(
            type=types.Type.STRING,
            description="Known allergies or 'NO KNOWN ALLERGY' if none"
        ),

        # Section 2: Vitals
        "vitals": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "blood_pressure": types.Schema(type=types.Type.STRING, description="Blood pressure in mmHg (e.g., '115/66 mmHg')"),
                "pulse": types.Schema(type=types.Type.STRING, description="Pulse rate in bpm (e.g., '90 bpm')"),
                "respiration": types.Schema(type=types.Type.STRING, description="Respiration rate in bpm (e.g., '18 bpm')"),
                "weight": types.Schema(type=types.Type.STRING, description="Weight in kg (e.g., '53.90 kg')"),
                "height": types.Schema(type=types.Type.STRING, description="Height in cm (e.g., '156 cm')"),
                "temperature": types.Schema(type=types.Type.STRING, description="Temperature in F (e.g., '97 F')"),
                "pulse_oximetry": types.Schema(type=types.Type.STRING, description="SpO2 percentage (e.g., '100 percent')"),
                "bmi": types.Schema(type=types.Type.STRING, description="BMI in kg/m2 (e.g., '22.15 kg/m2')"),
                "bsa": types.Schema(type=types.Type.STRING, description="Body Surface Area in m2 (e.g., '1.53 m2')")
            },
            description="Vital signs measurements"
        ),

        # Section 3: Complaints
        "complaints": types.Schema(
            type=types.Type.STRING,
            description="Chief complaint with ICD code (e.g., 'FIRST ANTENATAL VISIT [ R69. ]')"
        ),

        # Section 4: Diagnosis - Table format
        "diagnosis": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Diagnosis name with comments (e.g., 'LESS THAN 8 WEEKS GESTATION OF PREGNANCY - Comments : PRIMI- 6+ 6 weeks')"),
                    "type": types.Schema(type=types.Type.STRING, description="Primary or Secondary"),
                    "code": types.Schema(type=types.Type.STRING, description="ICD-10 code (e.g., 'Z3A.01')")
                }
            ),
            description="List of diagnoses with type and ICD-10 codes"
        ),

        # Section 5: Obstetrics Assessment
        "obstetricsAssessment": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "obstetric_score": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "gravida": types.Schema(type=types.Type.STRING, description="G (Gravida) - number of pregnancies (e.g., '1')"),
                        "para": types.Schema(type=types.Type.STRING, description="P (Para) - number of deliveries or N/A"),
                        "living": types.Schema(type=types.Type.STRING, description="L (Living) - number of living children or N/A"),
                        "abortion": types.Schema(type=types.Type.STRING, description="A (Abortion) - number of abortions or N/A")
                    },
                    description="Obstetric score (GPLA)"
                ),
                "obstetric_history": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "marital_status": types.Schema(type=types.Type.STRING, description="Married/Unmarried"),
                        "married_life_duration": types.Schema(type=types.Type.STRING, description="Duration of married life (e.g., '2 months')"),
                        "consanguinity": types.Schema(type=types.Type.STRING, description="Consanguineous or Non Consanguineous Marriage"),
                        "menstrual_cycle": types.Schema(type=types.Type.STRING, description="Regular/Irregular"),
                        "cycle_length": types.Schema(type=types.Type.STRING, description="Cycle details (e.g., '6/35')")
                    },
                    description="Obstetric history details"
                )
            },
            description="Obstetrics assessment"
        ),

        # Section 6: Risk Assessment Score
        "riskAssessmentScore": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "gestosis_score": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "factor": types.Schema(type=types.Type.STRING, description="Risk factor (e.g., 'Primigravida')"),
                            "score": types.Schema(type=types.Type.STRING, description="Score value (e.g., '1')")
                        }
                    ),
                    description="Gestosis risk factors"
                ),
                "total_score": types.Schema(type=types.Type.STRING, description="Total risk score (e.g., '2')")
            },
            description="Risk assessment scoring"
        ),

        # Section 7: Antenatal Chart
        "antenatalChart": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "mode_of_conception": types.Schema(type=types.Type.STRING, description="Spontaneous, IVF, IUI, etc."),
                "upt": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "result": types.Schema(type=types.Type.STRING, description="UPT Positive/Negative"),
                        "test_name": types.Schema(type=types.Type.STRING, description="Urine Pregnancy Test"),
                        "rchid": types.Schema(type=types.Type.STRING, description="RCHID status (e.g., 'to get')")
                    },
                    description="Urine Pregnancy Test details"
                ),
                "father_blood_group": types.Schema(type=types.Type.STRING, description="Father's blood group (e.g., 'A positive')"),
                "pregnancy_details": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "lmp": types.Schema(type=types.Type.STRING, description="Last Menstrual Period date (e.g., '9.10.25')"),
                        "edd": types.Schema(type=types.Type.STRING, description="Expected Date of Delivery (e.g., '16.7.26')"),
                        "pre_pregnancy_weight": types.Schema(type=types.Type.STRING, description="Pre-pregnancy weight (e.g., '53 kg')"),
                        "blood_group_mother": types.Schema(type=types.Type.STRING, description="Mother's blood group (e.g., 'B positive')")
                    },
                    description="Pregnancy details"
                ),
                "assessment": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "date_of_visit": types.Schema(type=types.Type.STRING, description="Visit date (e.g., '26.11.25')"),
                            "gestation_in_weeks": types.Schema(type=types.Type.STRING, description="Gestation (e.g., '6 w + 6 d')"),
                            "weight": types.Schema(type=types.Type.STRING, description="Weight at visit (e.g., '53.9 kg')"),
                            "bp": types.Schema(type=types.Type.STRING, description="BP at visit (e.g., '115/ 66 mmHg')")
                        }
                    ),
                    description="Assessment visits table"
                )
            },
            description="Antenatal chart"
        ),

        # Section 8: History of Present Illness
        "historyOfPresentIllness": types.Schema(
            type=types.Type.STRING,
            description="Narrative HPI with age, married duration, gestational age, comorbidities, conception type, LMP, EDD, UPT, complaints, bowel/bladder habits"
        ),

        # Section 9: Past History
        "pastHistory": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "past_medical_history": types.Schema(type=types.Type.STRING, description="Past medical conditions or 'No Past Medical History'"),
                "past_surgical_history": types.Schema(type=types.Type.STRING, description="Past surgeries or 'No Past Surgical History'"),
                "drug_history": types.Schema(type=types.Type.STRING, description="Current/previous medications or 'No Drug History'"),
                "family_history": types.Schema(type=types.Type.STRING, description="Family medical history (e.g., 'Father Has History Of DM')"),
                "personal_history": types.Schema(type=types.Type.STRING, description="Personal history or 'No Personal History'"),
                "occupational_history": types.Schema(type=types.Type.STRING, description="Occupation history or 'No Occupational History'")
            },
            description="Past history sections"
        ),

        # Section 10: Examination
        "examination": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "general": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "general_appearance": types.Schema(type=types.Type.STRING, description="General appearance (e.g., 'General Appearance Normal')"),
                        "piccle": types.Schema(type=types.Type.STRING, description="PICCLE findings (e.g., 'No Pallor, icterus, cyanosis, clubbing, lymphadenopathy, pedal Edema')"),
                        "nutritional_assessment": types.Schema(type=types.Type.STRING, description="Nutritional status (e.g., 'Student Is Moderately Nourished')")
                    },
                    description="General examination"
                ),
                "systemic": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "breast": types.Schema(type=types.Type.STRING, description="Breast examination (e.g., 'Both Breasts Are Normal')"),
                        "cvs": types.Schema(type=types.Type.STRING, description="CVS findings (e.g., 'S1S2 Heard')"),
                        "respiratory": types.Schema(type=types.Type.STRING, description="RS findings (e.g., 'NVBS')")
                    },
                    description="Systemic examination"
                ),
                "obstetric_examination": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "abdominal_examination": types.Schema(type=types.Type.STRING, description="Abdominal findings (e.g., 'Abdomen: Soft')"),
                        "fundal_height": types.Schema(type=types.Type.STRING, description="Fundal height or N/A"),
                        "fetal_heart_rate": types.Schema(type=types.Type.STRING, description="FHR or N/A"),
                        "presentation": types.Schema(type=types.Type.STRING, description="Fetal presentation or N/A"),
                        "per_vaginal": types.Schema(type=types.Type.STRING, description="P/V examination or N/A")
                    },
                    description="Obstetric examination"
                )
            },
            description="Physical examination"
        ),

        # Section 11: Investigation - Ordered Labs
        "orderedLabs": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "sr_no": types.Schema(type=types.Type.STRING, description="Serial number"),
                    "test_name": types.Schema(type=types.Type.STRING, description="Test name (e.g., 'Anti HCV', 'HBsAg', 'COMPLETE BLOOD COUNT (CBC)')"),
                    "date": types.Schema(type=types.Type.STRING, description="Order date (e.g., 'Dec 03, 2025')"),
                    "indication": types.Schema(type=types.Type.STRING, description="Indication (e.g., 'anc' for antenatal care)")
                }
            ),
            description="Ordered laboratory investigations"
        ),

        # Section 12: Investigation - Ordered Radiology
        "orderedRadiology": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "sr_no": types.Schema(type=types.Type.STRING, description="Serial number"),
                    "study_name": types.Schema(type=types.Type.STRING, description="Study name (e.g., 'FIRST TRIMESTER', 'Fetal Heart Study (FHS)')"),
                    "date": types.Schema(type=types.Type.STRING, description="Order date (e.g., 'Dec 03, 2025')"),
                    "indication": types.Schema(type=types.Type.STRING, description="Indication (e.g., 'anc')")
                }
            ),
            description="Ordered radiology/imaging"
        ),

        # Section 13: Medication Chart - GKNM format
        "medicationChart": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "sr_no": types.Schema(type=types.Type.STRING, description="Serial number"),
                    "generic_name": types.Schema(type=types.Type.STRING, description="Brand name with generic (e.g., 'FOLVITE 5mg TAB (FOLIC ACID 5MG TAB)')"),
                    "schedule": types.Schema(type=types.Type.STRING, description="Schedule in 1-0-0-0 format with description (e.g., '1-0-0-0 EVERY MORNING')"),
                    "unit": types.Schema(type=types.Type.STRING, description="Unit (e.g., 'TABLET')"),
                    "route": types.Schema(type=types.Type.STRING, description="Route (e.g., 'ORAL')"),
                    "days": types.Schema(type=types.Type.STRING, description="Duration in days"),
                    "qty": types.Schema(type=types.Type.STRING, description="Total quantity"),
                    "meal_relationship": types.Schema(type=types.Type.STRING, description="Relationship with meal (e.g., 'AFTER MEAL', 'BEFORE MEAL')"),
                    "comment": types.Schema(type=types.Type.STRING, description="Additional comments or '-'")
                }
            ),
            description="Medication chart with GKNM school format"
        ),

        # Section 14: Care Plan and Advice
        "carePlanAndAdvice": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "ultrasound_findings": types.Schema(type=types.Type.STRING, description="USG/TVS findings (e.g., 'TVS : G sac, yolk sac seen , Fetus pole seen')"),
                "viability_assessment": types.Schema(type=types.Type.STRING, description="Viability notes (e.g., 'assess viability after 2 weeks')"),
                "weight_gain_target": types.Schema(type=types.Type.STRING, description="Weight gain recommendation (e.g., 'weight gain10-12 kg')"),
                "supplements": types.Schema(type=types.Type.STRING, description="Supplement advice (e.g., 'To start folic acid supplements')"),
                "investigations_plan": types.Schema(type=types.Type.STRING, description="Investigation plan (e.g., 'First trimester investigations after viability')"),
                "next_visit_plan": types.Schema(type=types.Type.STRING, description="Next visit plan (e.g., 'Diet, physio next visit')"),
                "other_advice": types.Schema(type=types.Type.STRING, description="Additional advice")
            },
            description="Care plan and advice"
        ),

        # Section 15: Follow Up and Instructions
        "followUpAndInstructions": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "follow_up_date": types.Schema(type=types.Type.STRING, description="Follow up date (e.g., '05/12/2025')"),
                "warning_symptoms": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING, description="Warning symptom"),
                    description="Warning symptoms to watch for (e.g., ['Abdominal Pain', 'Bleeding Through Vagina'])"
                ),
                "instructions": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "diet": types.Schema(type=types.Type.STRING, description="Diet instructions (e.g., 'Adequate Hydration, Normal Diet')"),
                        "drugs": types.Schema(type=types.Type.STRING, description="Drug instructions (e.g., 'Continue Folic Acid Supplements')"),
                        "lifestyle": types.Schema(type=types.Type.STRING, description="Lifestyle instructions (e.g., 'Antenatal Exercises, Regular Walking')"),
                        "rchid": types.Schema(type=types.Type.STRING, description="RCHID instruction (e.g., 'Get RCHID')")
                    },
                    description="Student instructions"
                )
            },
            description="Follow up and instructions"
        ),

        # Section 16: Emergency Contact
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

        # Section 17: Signature
        "signature": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "counsellor_name": types.Schema(type=types.Type.STRING, description="Doctor's name (e.g., 'DR.')"),
                "qualifications": types.Schema(type=types.Type.STRING, description="Qualifications (e.g., 'MS OG, DNB OG, MRCOG (UK)')"),
                "date_time": types.Schema(type=types.Type.STRING, description="Date and time of signature (e.g., 'Nov 26, 2025@10:10')")
            },
            description="Counsellor signature information"
        )
    },
    required=[
        "allergies",
        "vitals",
        "complaints",
        "diagnosis",
        "obstetricsAssessment",
        "riskAssessmentScore",
        "antenatalChart",
        "historyOfPresentIllness",
        "pastHistory",
        "examination",
        "orderedLabs",
        "orderedRadiology",
        "medicationChart",
        "carePlanAndAdvice",
        "followUpAndInstructions",
        "emergencyContacts",
        "signature"
    ]
)

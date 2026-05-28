"""
OB-GYN GKNM JSON Schema - JSON Schema format for structured output
Matches the GKNM Obstetrics & Gynecology consultation output format from OG Casesheet.md
"""

OG_JSON_SCHEMA = {
    "type": "object",
    "required": [
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
    ],
    "properties": {
        "allergies": {
            "type": "string",
            "description": "Known allergies or 'NO KNOWN ALLERGY' if none"
        },
        "vitals": {
            "type": "object",
            "properties": {
                "blood_pressure": {"type": "string", "description": "Blood pressure in mmHg"},
                "pulse": {"type": "string", "description": "Pulse rate in bpm"},
                "respiration": {"type": "string", "description": "Respiration rate in bpm"},
                "weight": {"type": "string", "description": "Weight in kg"},
                "height": {"type": "string", "description": "Height in cm"},
                "temperature": {"type": "string", "description": "Temperature in F"},
                "pulse_oximetry": {"type": "string", "description": "SpO2 percentage"},
                "bmi": {"type": "string", "description": "BMI in kg/m2"},
                "bsa": {"type": "string", "description": "Body Surface Area in m2"}
            },
            "description": "Vital signs measurements"
        },
        "complaints": {
            "type": "string",
            "description": "Chief complaint with ICD code"
        },
        "diagnosis": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Diagnosis name with comments"},
                    "type": {"type": "string", "description": "Primary or Secondary"},
                    "code": {"type": "string", "description": "ICD-10 code"}
                }
            },
            "description": "List of diagnoses with type and ICD-10 codes"
        },
        "obstetricsAssessment": {
            "type": "object",
            "properties": {
                "obstetric_score": {
                    "type": "object",
                    "properties": {
                        "gravida": {"type": "string", "description": "G (Gravida) - number of pregnancies"},
                        "para": {"type": "string", "description": "P (Para) - number of deliveries or N/A"},
                        "living": {"type": "string", "description": "L (Living) - number of living children or N/A"},
                        "abortion": {"type": "string", "description": "A (Abortion) - number of abortions or N/A"}
                    },
                    "description": "Obstetric score (GPLA)"
                },
                "obstetric_history": {
                    "type": "object",
                    "properties": {
                        "marital_status": {"type": "string", "description": "Married/Unmarried"},
                        "married_life_duration": {"type": "string", "description": "Duration of married life"},
                        "consanguinity": {"type": "string", "description": "Consanguineous or Non Consanguineous Marriage"},
                        "menstrual_cycle": {"type": "string", "description": "Regular/Irregular"},
                        "cycle_length": {"type": "string", "description": "Cycle details"}
                    },
                    "description": "Obstetric history details"
                }
            },
            "description": "Obstetrics assessment"
        },
        "riskAssessmentScore": {
            "type": "object",
            "properties": {
                "gestosis_score": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "factor": {"type": "string", "description": "Risk factor"},
                            "score": {"type": "string", "description": "Score value"}
                        }
                    },
                    "description": "Gestosis risk factors"
                },
                "total_score": {"type": "string", "description": "Total risk score"}
            },
            "description": "Risk assessment scoring"
        },
        "antenatalChart": {
            "type": "object",
            "properties": {
                "mode_of_conception": {"type": "string", "description": "Spontaneous, IVF, IUI, etc."},
                "upt": {
                    "type": "object",
                    "properties": {
                        "result": {"type": "string", "description": "UPT Positive/Negative"},
                        "test_name": {"type": "string", "description": "Urine Pregnancy Test"},
                        "rchid": {"type": "string", "description": "RCHID status"}
                    },
                    "description": "Urine Pregnancy Test details"
                },
                "father_blood_group": {"type": "string", "description": "Father's blood group"},
                "pregnancy_details": {
                    "type": "object",
                    "properties": {
                        "lmp": {"type": "string", "description": "Last Menstrual Period date"},
                        "edd": {"type": "string", "description": "Expected Date of Delivery"},
                        "pre_pregnancy_weight": {"type": "string", "description": "Pre-pregnancy weight"},
                        "blood_group_mother": {"type": "string", "description": "Mother's blood group"}
                    },
                    "description": "Pregnancy details"
                },
                "assessment": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "date_of_visit": {"type": "string", "description": "Visit date"},
                            "gestation_in_weeks": {"type": "string", "description": "Gestation in weeks + days"},
                            "weight": {"type": "string", "description": "Weight at visit"},
                            "bp": {"type": "string", "description": "BP at visit"}
                        }
                    },
                    "description": "Assessment visits table"
                }
            },
            "description": "Antenatal chart"
        },
        "historyOfPresentIllness": {
            "type": "string",
            "description": "Narrative HPI with age, married duration, gestational age, etc."
        },
        "pastHistory": {
            "type": "object",
            "properties": {
                "past_medical_history": {"type": "string", "description": "Past medical conditions"},
                "past_surgical_history": {"type": "string", "description": "Past surgeries"},
                "drug_history": {"type": "string", "description": "Current/previous medications"},
                "family_history": {"type": "string", "description": "Family medical history"},
                "personal_history": {"type": "string", "description": "Personal history"},
                "occupational_history": {"type": "string", "description": "Occupation history"}
            },
            "description": "Past history sections"
        },
        "examination": {
            "type": "object",
            "properties": {
                "general": {
                    "type": "object",
                    "properties": {
                        "general_appearance": {"type": "string", "description": "General appearance"},
                        "piccle": {"type": "string", "description": "PICCLE findings"},
                        "nutritional_assessment": {"type": "string", "description": "Nutritional status"}
                    },
                    "description": "General examination"
                },
                "systemic": {
                    "type": "object",
                    "properties": {
                        "breast": {"type": "string", "description": "Breast examination"},
                        "cvs": {"type": "string", "description": "CVS findings"},
                        "respiratory": {"type": "string", "description": "RS findings"}
                    },
                    "description": "Systemic examination"
                },
                "obstetric_examination": {
                    "type": "object",
                    "properties": {
                        "abdominal_examination": {"type": "string", "description": "Abdominal findings"},
                        "fundal_height": {"type": "string", "description": "Fundal height or N/A"},
                        "fetal_heart_rate": {"type": "string", "description": "FHR or N/A"},
                        "presentation": {"type": "string", "description": "Fetal presentation or N/A"},
                        "per_vaginal": {"type": "string", "description": "P/V examination or N/A"}
                    },
                    "description": "Obstetric examination"
                }
            },
            "description": "Physical examination"
        },
        "orderedLabs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sr_no": {"type": "string", "description": "Serial number"},
                    "test_name": {"type": "string", "description": "Test name"},
                    "date": {"type": "string", "description": "Order date"},
                    "indication": {"type": "string", "description": "Indication (e.g., 'anc')"}
                }
            },
            "description": "Ordered laboratory investigations"
        },
        "orderedRadiology": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sr_no": {"type": "string", "description": "Serial number"},
                    "study_name": {"type": "string", "description": "Study name"},
                    "date": {"type": "string", "description": "Order date"},
                    "indication": {"type": "string", "description": "Indication (e.g., 'anc')"}
                }
            },
            "description": "Ordered radiology/imaging"
        },
        "medicationChart": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sr_no": {"type": "string", "description": "Serial number"},
                    "generic_name": {"type": "string", "description": "Brand name with generic"},
                    "schedule": {"type": "string", "description": "Schedule in 1-0-0-0 format with description"},
                    "unit": {"type": "string", "description": "Unit (e.g., 'TABLET')"},
                    "route": {"type": "string", "description": "Route (e.g., 'ORAL')"},
                    "days": {"type": "string", "description": "Duration in days"},
                    "qty": {"type": "string", "description": "Total quantity"},
                    "meal_relationship": {"type": "string", "description": "Relationship with meal"},
                    "comment": {"type": "string", "description": "Additional comments or '-'"}
                }
            },
            "description": "Medication chart with GKNM hospital format"
        },
        "carePlanAndAdvice": {
            "type": "object",
            "properties": {
                "ultrasound_findings": {"type": "string", "description": "USG/TVS findings"},
                "viability_assessment": {"type": "string", "description": "Viability notes"},
                "weight_gain_target": {"type": "string", "description": "Weight gain recommendation"},
                "supplements": {"type": "string", "description": "Supplement advice"},
                "investigations_plan": {"type": "string", "description": "Investigation plan"},
                "next_visit_plan": {"type": "string", "description": "Next visit plan"},
                "other_advice": {"type": "string", "description": "Additional advice"}
            },
            "description": "Care plan and advice"
        },
        "followUpAndInstructions": {
            "type": "object",
            "properties": {
                "follow_up_date": {"type": "string", "description": "Follow up date"},
                "warning_symptoms": {
                    "type": "array",
                    "items": {"type": "string", "description": "Warning symptom"},
                    "description": "Warning symptoms to watch for"
                },
                "instructions": {
                    "type": "object",
                    "properties": {
                        "diet": {"type": "string", "description": "Diet instructions"},
                        "drugs": {"type": "string", "description": "Drug instructions"},
                        "lifestyle": {"type": "string", "description": "Lifestyle instructions"},
                        "rchid": {"type": "string", "description": "RCHID instruction"}
                    },
                    "description": "Patient instructions"
                }
            },
            "description": "Follow up and instructions"
        },
        "emergencyContacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "purpose": {"type": "string", "description": "Purpose (e.g., 'For Appointments', 'For Medical Emergency')"},
                    "number": {"type": "string", "description": "Contact number(s)"}
                }
            },
            "description": "Emergency contact list"
        },
        "signature": {
            "type": "object",
            "properties": {
                "doctor_name": {"type": "string", "description": "Doctor's name"},
                "qualifications": {"type": "string", "description": "Qualifications"},
                "date_time": {"type": "string", "description": "Date and time of signature"}
            },
            "description": "Doctor signature information"
        }
    }
}

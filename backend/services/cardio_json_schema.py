"""
Cardio GKNM JSON Schema - JSON Schema format for structured output
Matches the GKNM Cardiology consultation output format from Cardio.md
"""

CARDIO_JSON_SCHEMA = {
    "type": "object",
    "required": [
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
    ],
    "properties": {
        "allergies": {
            "type": "string",
            "description": "Known allergies or 'NO KNOWN ALLERGY' if none"
        },
        "vitals": {
            "type": "object",
            "properties": {
                "blood_pressure": {"type": "string", "description": "Blood pressure in mmHg (e.g., '170/80 mmHg')"},
                "pulse": {"type": "string", "description": "Pulse rate in bpm (e.g., '42 bpm')"},
                "temperature": {"type": "string", "description": "Temperature in F (e.g., '96.80 F')"},
                "bmi": {"type": "string", "description": "BMI in kg/m2 (e.g., '34.63 kg/m2')"},
                "height": {"type": "string", "description": "Height in cm (e.g., '155.0 cm')"},
                "weight": {"type": "string", "description": "Weight in kg (e.g., '83.20 kg')"},
                "pulse_oximetry": {"type": "string", "description": "SpO2 percentage (e.g., '98 percent')"},
                "bsa": {"type": "string", "description": "Body Surface Area in m2 (e.g., '1.89 m2')"},
                "respiratory_rate": {"type": "string", "description": "Respiratory rate or N/A"}
            },
            "description": "Vital signs measurements"
        },
        "diagnosis": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Diagnosis name with comments"},
                    "type": {"type": "string", "description": "Primary or Secondary"},
                    "code": {"type": "string", "description": "ICD-10 code (e.g., 'I50.9')"}
                }
            },
            "description": "List of diagnoses with type and ICD-10 codes"
        },
        "previousCardiacHistory": {
            "type": "object",
            "properties": {
                "primary_consultant": {"type": "string", "description": "Primary consultant name"},
                "comorbidities": {"type": "string", "description": "Comorbidities like Systemic hypertension, Type II diabetes mellitus"},
                "cardiac_conditions": {"type": "string", "description": "Cardiac conditions with dates"},
                "previous_admissions": {"type": "string", "description": "Previous admissions with dates and details"},
                "cag_findings": {"type": "string", "description": "Coronary Angiography findings with date"},
                "treatment_plan": {"type": "string", "description": "Treatment plan"},
                "echo_findings": {"type": "string", "description": "Echo findings with date"},
                "clinical_notes": {"type": "string", "description": "Additional clinical notes"}
            },
            "description": "Previous cardiac history and relevant cardiac workup"
        },
        "historyOfPresentIllness": {
            "type": "object",
            "properties": {
                "last_visit": {"type": "string", "description": "Last visit date and doctor"},
                "recent_labs": {"type": "string", "description": "Recent lab values"},
                "activity_status": {"type": "string", "description": "Activity status"},
                "current_complaints": {"type": "string", "description": "Current complaints with details"},
                "negative_symptoms": {"type": "string", "description": "Symptoms denied"},
                "adl_status": {"type": "string", "description": "Activities of Daily Living status"},
                "current_medications": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Medication name with strength"},
                            "schedule": {"type": "string", "description": "Schedule (e.g., 'OD', 'BD', 'HS', 'SOS')"}
                        }
                    },
                    "description": "Current medications"
                },
                "other_specialty_medications": {"type": "string", "description": "Medications from other specialists"}
            },
            "description": "History of present illness with current status"
        },
        "examination": {
            "type": "object",
            "properties": {
                "systemic": {
                    "type": "object",
                    "properties": {
                        "cns": {"type": "string", "description": "CNS findings"},
                        "cvs": {"type": "string", "description": "CVS findings"},
                        "respiratory": {"type": "string", "description": "RS findings"}
                    },
                    "description": "Systemic examination findings"
                },
                "cardiac_examination": {
                    "type": "object",
                    "properties": {
                        "supine_bp": {"type": "string", "description": "Supine blood pressure"},
                        "pulse_rate": {"type": "string", "description": "Pulse rate with regularity"},
                        "pedal_edema": {"type": "string", "description": "Pedal edema status"}
                    },
                    "description": "Cardiac examination findings"
                }
            },
            "description": "Physical examination findings"
        },
        "orderedLabs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "test_name": {"type": "string", "description": "Test name"},
                    "date": {"type": "string", "description": "Order date"},
                    "urgency": {"type": "string", "description": "Routine or Urgent"}
                }
            },
            "description": "Labs ordered during this visit"
        },
        "labResults": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "test_name": {"type": "string", "description": "Test name with date"},
                    "parameter_name": {"type": "string", "description": "Parameter name"},
                    "result": {"type": "string", "description": "Result with units"},
                    "ref_range": {"type": "string", "description": "Reference range"}
                }
            },
            "description": "Lab results table"
        },
        "orderedRadiology": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "study_name": {"type": "string", "description": "Study name"},
                    "date": {"type": "string", "description": "Order/result date"},
                    "status": {"type": "string", "description": "routine, resulted, or pending"}
                }
            },
            "description": "Radiology/imaging orders"
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
                "patient_summary": {"type": "string", "description": "Brief summary"},
                "current_vitals_summary": {"type": "string", "description": "Key vitals"},
                "ecg_summary": {"type": "string", "description": "ECG findings"},
                "labs_summary": {"type": "string", "description": "Key lab values"},
                "diet_advice": {"type": "string", "description": "Dietary advice"},
                "medication_changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "description": "Action: Hold, Decrease, Increase, Continue, Start, Stop"},
                            "medication": {"type": "string", "description": "Medication name"},
                            "reason": {"type": "string", "description": "Reason for change"}
                        }
                    },
                    "description": "Medication changes"
                },
                "other_advice": {"type": "string", "description": "Other advice"},
                "assisted_by": {"type": "string", "description": "Name of assistant"}
            },
            "description": "Care plan and advice summary"
        },
        "followUpAndInstructions": {
            "type": "object",
            "properties": {
                "review_with_reports": {"type": "string", "description": "Review date"},
                "doctor_name": {"type": "string", "description": "Doctor to follow up with"},
                "reports_needed": {"type": "string", "description": "Reports to bring"},
                "timeline": {"type": "string", "description": "Timeline for follow-up"}
            },
            "description": "Follow up instructions"
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

"""
Differential Diagnosis Trees (MVP)

India-specific differential diagnosis lookup tables for clinical triage.
Provides structured guidance for common presentations including:
- Must-rule-out diagnoses with associated tests
- Red flags requiring immediate attention
- First-line investigations
- Essential history questions

Phase 1 (MVP): Hardcoded trees for common presentations
Phase 3: Will be moved to database with RAG augmentation
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Differential Diagnosis Trees
# =============================================================================

DIFFERENTIAL_TREES: Dict[str, Dict[str, Dict[str, Any]]] = {

    # =========================================================================
    # GENERAL MEDICINE
    # =========================================================================
    "general_medicine": {

        "fever": {
            "age_groups": ["adult"],
            "must_rule_out": [
                {
                    "diagnosis": "Dengue",
                    "features": ["high_fever", "thrombocytopenia", "leucopenia", "retro_orbital_pain", "myalgia", "rash"],
                    "tests": ["NS1_antigen", "Dengue_IgM_IgG", "CBC_with_platelet"],
                    "timeframe": "Day 1-5: NS1 positive, Day 5+: IgM positive",
                    "india_endemic": True
                },
                {
                    "diagnosis": "Malaria",
                    "features": ["fever_with_chills", "periodicity", "splenomegaly", "anemia", "jaundice"],
                    "tests": ["MP_smear_thick_thin", "Malaria_RDT", "CBC"],
                    "high_risk": ["travel_to_endemic_area", "rural_residence"],
                    "india_endemic": True
                },
                {
                    "diagnosis": "Typhoid",
                    "features": ["step_ladder_fever", "relative_bradycardia", "coated_tongue", "hepatosplenomegaly", "rose_spots"],
                    "tests": ["Blood_culture", "Widal_test"],
                    "note": "Widal unreliable in endemic areas; blood culture is gold standard",
                    "india_endemic": True
                },
                {
                    "diagnosis": "Scrub_Typhus",
                    "features": ["eschar", "lymphadenopathy", "hepatosplenomegaly", "maculopapular_rash"],
                    "tests": ["Scrub_typhus_IgM", "Weil_Felix_OXK"],
                    "high_risk": ["rural_exposure", "agricultural_work", "trekking"],
                    "india_endemic": True
                },
                {
                    "diagnosis": "Leptospirosis",
                    "features": ["conjunctival_suffusion", "severe_myalgia_calves", "jaundice", "renal_dysfunction"],
                    "tests": ["Leptospira_IgM", "MAT_test"],
                    "high_risk": ["flood_exposure", "water_contact", "agricultural_work", "monsoon_season"],
                    "india_endemic": True
                },
                {
                    "diagnosis": "Tuberculosis",
                    "features": ["prolonged_fever_>2_weeks", "night_sweats", "weight_loss", "cough", "lymphadenopathy"],
                    "tests": ["Chest_Xray", "Sputum_AFB", "GeneXpert_MTB", "Mantoux_test"],
                    "india_endemic": True
                },
                {
                    "diagnosis": "UTI_Pyelonephritis",
                    "features": ["dysuria", "frequency", "flank_pain", "costovertebral_tenderness"],
                    "tests": ["Urine_routine", "Urine_culture"]
                },
                {
                    "diagnosis": "COVID-19",
                    "features": ["fever", "cough", "breathlessness", "anosmia", "ageusia"],
                    "tests": ["RT_PCR", "Rapid_antigen_test"]
                }
            ],
            "high_probability": [
                {"diagnosis": "Viral_fever", "features": ["self_limiting", "myalgia", "headache", "duration_<5_days"]},
                {"diagnosis": "URTI", "features": ["cough", "cold", "sore_throat", "rhinorrhea"]},
            ],
            "red_flags": [
                "Altered sensorium / confusion",
                "Bleeding manifestations (petechiae, epistaxis, GI bleed)",
                "Hypotension (SBP <90 mmHg)",
                "Respiratory distress (SpO2 <94%)",
                "Platelets <20,000/cumm",
                "Severe dehydration",
                "Oliguria / anuria",
                "Seizures"
            ],
            "first_line_investigations": [
                {"test": "CBC with peripheral smear", "rationale": "Leucocytosis/leucopenia, thrombocytopenia, atypical lymphocytes", "cost": "LOW"},
                {"test": "CRP / ESR", "rationale": "Inflammatory marker - helps differentiate bacterial vs viral", "cost": "LOW"},
                {"test": "Dengue NS1 + IgM/IgG", "rationale": "Endemic area screening - mandatory in monsoon", "cost": "LOW"},
                {"test": "MP smear / Malaria RDT", "rationale": "Rule out malaria in any fever case", "cost": "LOW"},
                {"test": "Urine routine microscopy", "rationale": "Rule out UTI", "cost": "LOW"},
                {"test": "RFT (Creatinine, Urea)", "rationale": "Baseline renal function", "cost": "LOW"}
            ],
            "history_essentials": [
                "Fever duration and pattern (continuous, intermittent, remittent)",
                "Associated symptoms (cough, dysuria, rash, bleeding)",
                "Travel history (endemic areas)",
                "Occupational exposure (agricultural work, water contact)",
                "Recent antibiotic use",
                "Comorbidities (diabetes, CKD, immunosuppression)",
                "Sick contacts",
                "Vaccination status"
            ],
            "source": "ICMR_STG_NVBDCP_Guidelines"
        },

        "chest_pain": {
            "age_groups": ["adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Acute_Coronary_Syndrome",
                    "features": ["retrosternal_chest_pain", "radiation_to_arm_jaw", "sweating", "nausea", "breathlessness"],
                    "tests": ["ECG", "Troponin_I_T", "CK_MB"],
                    "immediate": True
                },
                {
                    "diagnosis": "Pulmonary_Embolism",
                    "features": ["sudden_breathlessness", "pleuritic_chest_pain", "hemoptysis", "tachycardia", "hypoxia"],
                    "tests": ["D_dimer", "CT_Pulmonary_Angiography", "ECG"],
                    "high_risk": ["recent_surgery", "immobilization", "DVT_history", "malignancy"]
                },
                {
                    "diagnosis": "Aortic_Dissection",
                    "features": ["tearing_chest_pain", "radiation_to_back", "BP_difference_arms", "pulse_deficit"],
                    "tests": ["CT_Aortogram", "Chest_Xray", "D_dimer"],
                    "immediate": True
                },
                {
                    "diagnosis": "Tension_Pneumothorax",
                    "features": ["sudden_breathlessness", "unilateral_chest_pain", "tracheal_deviation", "absent_breath_sounds"],
                    "tests": ["Chest_Xray"],
                    "immediate": True
                }
            ],
            "red_flags": [
                "Hemodynamic instability (hypotension, shock)",
                "ST elevation on ECG",
                "Positive troponin",
                "Severe breathlessness",
                "Altered consciousness",
                "New murmur"
            ],
            "first_line_investigations": [
                {"test": "ECG (12-lead)", "rationale": "STEMI/NSTEMI/arrhythmia", "cost": "LOW", "immediate": True},
                {"test": "Troponin I/T", "rationale": "Myocardial injury marker", "cost": "MEDIUM"},
                {"test": "Chest X-ray", "rationale": "Pneumothorax, cardiomegaly, pulmonary edema", "cost": "LOW"},
                {"test": "D-dimer", "rationale": "If PE suspected", "cost": "MEDIUM"}
            ],
            "history_essentials": [
                "Character of pain (crushing, tearing, pleuritic)",
                "Radiation (arm, jaw, back)",
                "Duration and onset",
                "Aggravating/relieving factors",
                "Associated symptoms (sweating, nausea, breathlessness)",
                "Risk factors (diabetes, hypertension, smoking, family history)",
                "Previous cardiac history"
            ],
            "source": "CSI_ACS_Guidelines"
        },

        "hypertension": {
            "age_groups": ["adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Hypertensive_Emergency",
                    "features": ["BP_>180/120", "headache", "visual_disturbance", "chest_pain", "altered_sensorium"],
                    "tests": ["Fundoscopy", "ECG", "RFT", "Urine_routine"],
                    "immediate": True
                },
                {
                    "diagnosis": "Secondary_Hypertension",
                    "features": ["young_onset_<30", "resistant_HTN", "hypokalemia", "renal_bruit"],
                    "tests": ["Renal_artery_Doppler", "Aldosterone_renin_ratio", "24hr_urinary_metanephrines"]
                }
            ],
            "red_flags": [
                "BP >180/120 with target organ damage",
                "Severe headache with visual disturbance",
                "Chest pain",
                "Acute kidney injury",
                "Papilledema",
                "Neurological deficit"
            ],
            "first_line_investigations": [
                {"test": "ECG", "rationale": "LVH, ischemia", "cost": "LOW"},
                {"test": "RFT (Creatinine, Urea)", "rationale": "Renal function", "cost": "LOW"},
                {"test": "Urine routine", "rationale": "Proteinuria", "cost": "LOW"},
                {"test": "Lipid profile", "rationale": "Cardiovascular risk", "cost": "LOW"},
                {"test": "Blood glucose / HbA1c", "rationale": "Diabetes screening", "cost": "LOW"}
            ],
            "source": "CSI_HSI_Hypertension_Guidelines"
        },

        "diabetes_review": {
            "age_groups": ["adult", "elderly"],
            "must_assess": [
                {
                    "domain": "Glycemic_control",
                    "tests": ["HbA1c", "Fasting_blood_glucose", "Post_prandial_glucose"],
                    "target": "HbA1c <7% for most adults"
                },
                {
                    "domain": "Complications_screening",
                    "tests": ["Urine_ACR", "eGFR", "Fundoscopy", "Foot_examination"],
                    "frequency": "Annual"
                }
            ],
            "red_flags": [
                "DKA symptoms (nausea, vomiting, abdominal pain, fruity breath)",
                "Hypoglycemia (sweating, tremors, confusion)",
                "Foot ulcer / infection",
                "Sudden vision loss",
                "New onset proteinuria"
            ],
            "history_essentials": [
                "Current medications and adherence",
                "Hypoglycemia episodes",
                "Diet and exercise",
                "Blood glucose self-monitoring",
                "Symptoms of complications (numbness, vision changes, foot problems)"
            ],
            "source": "RSSDI_Diabetes_Guidelines"
        }
    },

    # =========================================================================
    # PSYCHIATRY
    # =========================================================================
    "psychiatry": {

        "depression": {
            "age_groups": ["adolescent", "adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Major_Depressive_Disorder",
                    "features": ["persistent_sadness", "anhedonia", "sleep_disturbance", "appetite_change", "fatigue", "worthlessness", "concentration_difficulty", "psychomotor_changes"],
                    "tests": ["PHQ-9", "HAM-D"],
                    "duration": ">2 weeks of symptoms, most of the day, nearly every day"
                },
                {
                    "diagnosis": "Bipolar_Depression",
                    "features": ["history_of_mania_hypomania", "family_history_bipolar", "early_onset", "antidepressant_induced_mania", "atypical_features"],
                    "tests": ["MDQ", "YMRS_if_manic_features"],
                    "note": "ALWAYS screen for past manic/hypomanic episodes before starting antidepressants"
                },
                {
                    "diagnosis": "Organic_Depression",
                    "features": ["hypothyroidism", "B12_deficiency", "anemia", "chronic_illness", "medication_induced"],
                    "tests": ["TFT", "CBC", "Vitamin_B12", "Blood_glucose", "LFT_RFT"],
                    "note": "Rule out medical causes especially in elderly and atypical presentations"
                },
                {
                    "diagnosis": "Substance_Induced_Depression",
                    "features": ["alcohol_use", "benzodiazepine_use", "steroid_use", "temporal_relationship"],
                    "tests": ["Detailed_substance_history", "UDS_if_indicated"]
                },
                {
                    "diagnosis": "Adjustment_Disorder",
                    "features": ["identifiable_stressor", "symptoms_within_3_months", "resolves_within_6_months"],
                    "tests": ["Clinical_assessment"]
                }
            ],
            "red_flags": [
                "Suicidal ideation (MUST ASK DIRECTLY)",
                "Suicide plan or intent",
                "Access to lethal means (pesticides, medications, weapons)",
                "Recent suicide attempt",
                "Psychotic features (delusions, hallucinations)",
                "Severe functional impairment (not eating, not bathing)",
                "Catatonic features",
                "Command hallucinations"
            ],
            "history_essentials": [
                "Duration and severity of symptoms",
                "Suicidal ideation - MUST ASK DIRECTLY: 'Have you had thoughts of ending your life?'",
                "Past suicide attempts - method, intent, lethality, what stopped them",
                "Past psychiatric history (previous episodes, hospitalizations, ECT)",
                "Family history (depression, bipolar, suicide)",
                "Substance use history (alcohol, drugs)",
                "Medical history (thyroid, chronic illness)",
                "Current medications (steroids, beta-blockers, interferon, OCP)",
                "Psychosocial stressors (financial, relationship, work)",
                "Functional impairment (work, relationships, self-care)",
                "Sleep and appetite changes",
                "Screen for mania (ever had period of elevated mood, decreased sleep, increased energy)"
            ],
            "first_line_investigations": [
                {"test": "PHQ-9", "rationale": "Standardized depression screening and severity", "cost": "FREE"},
                {"test": "TFT (T3, T4, TSH)", "rationale": "Rule out hypothyroidism", "cost": "LOW"},
                {"test": "CBC", "rationale": "Rule out anemia", "cost": "LOW"},
                {"test": "Vitamin B12", "rationale": "Deficiency can mimic/worsen depression", "cost": "LOW"},
                {"test": "Blood glucose / HbA1c", "rationale": "Diabetes comorbidity and treatment planning", "cost": "LOW"},
                {"test": "LFT, RFT", "rationale": "Baseline before starting medications", "cost": "LOW"}
            ],
            "source": "IPS_CPG_Depression_mhGAP"
        },

        "anxiety": {
            "age_groups": ["adolescent", "adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Generalized_Anxiety_Disorder",
                    "features": ["excessive_worry", "multiple_domains", "difficulty_controlling_worry", "restlessness", "muscle_tension", "sleep_disturbance", "irritability"],
                    "tests": ["GAD-7", "HAM-A"],
                    "duration": ">6 months"
                },
                {
                    "diagnosis": "Panic_Disorder",
                    "features": ["recurrent_panic_attacks", "fear_of_future_attacks", "avoidance_behavior", "palpitations", "sweating", "trembling", "chest_pain", "fear_of_dying"],
                    "tests": ["Panic_Disorder_Severity_Scale"],
                    "note": "Rule out cardiac causes if chest pain is prominent"
                },
                {
                    "diagnosis": "Medical_Causes_Anxiety",
                    "features": ["hyperthyroidism", "pheochromocytoma", "cardiac_arrhythmia", "hypoglycemia", "COPD", "asthma"],
                    "tests": ["TFT", "ECG", "Blood_glucose", "CBC"],
                    "note": "New onset anxiety in elderly - always rule out medical cause"
                },
                {
                    "diagnosis": "Substance_Induced_Anxiety",
                    "features": ["caffeine_excess", "stimulant_use", "alcohol_withdrawal", "benzodiazepine_withdrawal"],
                    "tests": ["Substance_history", "UDS"]
                }
            ],
            "red_flags": [
                "Suicidal ideation",
                "Severe panic with cardiovascular symptoms (rule out MI)",
                "New onset in elderly (rule out medical cause)",
                "Psychotic features",
                "Substance withdrawal",
                "Severe functional impairment"
            ],
            "history_essentials": [
                "Nature and duration of anxiety symptoms",
                "Panic attacks - frequency, triggers, symptoms, duration",
                "Avoidance behaviors",
                "Substance use (caffeine, alcohol, drugs)",
                "Medical history (thyroid, cardiac, respiratory)",
                "Current medications",
                "Impact on functioning (work, social, daily activities)",
                "Comorbid depression - ALWAYS SCREEN with PHQ-9",
                "Sleep quality"
            ],
            "first_line_investigations": [
                {"test": "GAD-7", "rationale": "Standardized anxiety screening", "cost": "FREE"},
                {"test": "PHQ-9", "rationale": "Screen for comorbid depression", "cost": "FREE"},
                {"test": "TFT", "rationale": "Rule out hyperthyroidism", "cost": "LOW"},
                {"test": "ECG", "rationale": "If cardiac symptoms present (palpitations, chest pain)", "cost": "LOW"},
                {"test": "Blood glucose", "rationale": "Rule out hypoglycemia", "cost": "LOW"}
            ],
            "source": "IPS_CPG_Anxiety_mhGAP"
        },

        "psychosis": {
            "age_groups": ["adolescent", "adult"],
            "must_rule_out": [
                {
                    "diagnosis": "Schizophrenia",
                    "features": ["delusions", "hallucinations_auditory", "disorganized_speech", "negative_symptoms", "functional_decline"],
                    "tests": ["PANSS", "BPRS"],
                    "duration": ">6 months with >1 month active symptoms"
                },
                {
                    "diagnosis": "Organic_Psychosis_Delirium",
                    "features": ["acute_onset", "visual_hallucinations", "fluctuating_consciousness", "disorientation", "medical_illness"],
                    "tests": ["CBC", "RFT", "LFT", "TFT", "Electrolytes", "Blood_glucose", "CT_head", "Urine_routine"],
                    "note": "ALWAYS rule out delirium in acute psychosis - medical emergency"
                },
                {
                    "diagnosis": "Substance_Induced_Psychosis",
                    "features": ["cannabis_use", "stimulant_use", "alcohol_withdrawal", "temporal_relationship_to_substance"],
                    "tests": ["UDS", "Blood_alcohol"],
                    "note": "Cannabis is common cause in young adults in India"
                },
                {
                    "diagnosis": "Mood_Disorder_with_Psychotic_Features",
                    "features": ["prominent_mood_symptoms", "mood_congruent_delusions"],
                    "tests": ["Detailed_mood_history", "PHQ-9", "MDQ"]
                },
                {
                    "diagnosis": "Autoimmune_Encephalitis",
                    "features": ["young_female", "seizures", "movement_disorder", "rapid_progression", "psychiatric_symptoms_with_neurological"],
                    "tests": ["Anti_NMDA_receptor_antibodies", "CSF_analysis", "MRI_brain"],
                    "note": "Consider in young patients with atypical presentation"
                }
            ],
            "red_flags": [
                "Command hallucinations to harm self/others",
                "Persecutory delusions with identified target",
                "Agitation with risk of violence",
                "Catatonia (mutism, posturing, waxy flexibility)",
                "NMS if on antipsychotics (fever, rigidity, altered consciousness)",
                "Acute onset (consider organic cause)",
                "First episode psychosis (requires full workup)"
            ],
            "history_essentials": [
                "Onset and duration of symptoms (acute vs insidious)",
                "Nature of hallucinations (auditory vs visual - visual suggests organic)",
                "Content of delusions",
                "Substance use history - CRITICAL",
                "Past psychiatric history",
                "Family history of psychosis",
                "Premorbid functioning",
                "Risk assessment (harm to self/others)",
                "Medical history",
                "Recent head injury or CNS infection"
            ],
            "first_line_investigations": [
                {"test": "CBC", "rationale": "Baseline and rule out infection", "cost": "LOW"},
                {"test": "RFT, LFT", "rationale": "Baseline before antipsychotics", "cost": "LOW"},
                {"test": "TFT", "rationale": "Thyroid dysfunction can cause psychosis", "cost": "LOW"},
                {"test": "Blood glucose", "rationale": "Baseline and rule out hypoglycemia", "cost": "LOW"},
                {"test": "Electrolytes", "rationale": "Hyponatremia can cause confusion", "cost": "LOW"},
                {"test": "UDS", "rationale": "Rule out substance-induced", "cost": "MEDIUM"},
                {"test": "CT/MRI brain", "rationale": "First episode or atypical features - rule out organic", "cost": "HIGH"}
            ],
            "source": "IPS_CPG_Schizophrenia_NIMHANS"
        },

        "suicide_risk": {
            "age_groups": ["adolescent", "adult", "elderly"],
            "must_assess": [
                {
                    "domain": "Suicidal_Ideation",
                    "questions": [
                        "Have you had thoughts that life is not worth living?",
                        "Have you wished you were dead?",
                        "Have you had thoughts of ending your life?",
                        "How often do you have these thoughts?",
                        "Can you control these thoughts?"
                    ],
                    "tools": ["Columbia_Suicide_Severity_Rating_Scale", "PHQ-9_item_9"]
                },
                {
                    "domain": "Suicide_Plan",
                    "questions": [
                        "Have you thought about how you would end your life?",
                        "Do you have access to means (pesticides, medications, rope)?",
                        "Have you decided when you would do it?",
                        "Have you made any preparations (writing notes, giving away possessions)?"
                    ]
                },
                {
                    "domain": "Intent",
                    "questions": [
                        "Do you intend to act on these thoughts?",
                        "What are your reasons for living?",
                        "What are your reasons for dying?",
                        "What has stopped you so far?"
                    ]
                },
                {
                    "domain": "Past_Attempts",
                    "questions": [
                        "Have you ever tried to end your life before?",
                        "What method did you use?",
                        "What happened? Did you need medical treatment?",
                        "What were the circumstances?",
                        "What stopped you or saved you?"
                    ]
                }
            ],
            "high_risk_factors": [
                "Previous suicide attempt (STRONGEST predictor)",
                "Access to lethal means (pesticides common in rural India)",
                "Current psychiatric disorder (depression, psychosis, substance use)",
                "Recent discharge from psychiatric facility",
                "Recent loss or humiliation (job loss, relationship breakup, exam failure)",
                "Chronic pain or terminal illness",
                "Social isolation (living alone, no family support)",
                "Male gender + elderly + widowed",
                "Family history of suicide",
                "Recent self-harm",
                "Substance intoxication"
            ],
            "protective_factors": [
                "Strong family/social support",
                "Responsibility for children/dependents",
                "Religious beliefs against suicide",
                "Fear of death/pain",
                "Future orientation (plans, goals)",
                "Therapeutic alliance",
                "Engaged in treatment"
            ],
            "red_flags_immediate_action": [
                "Active suicidal ideation with plan AND intent",
                "Access to means",
                "Command hallucinations to self-harm",
                "Recent serious attempt",
                "Giving away possessions",
                "Saying goodbye to loved ones",
                "Sudden calmness after severe depression (may have made decision)"
            ],
            "immediate_actions": [
                "Do NOT leave patient alone",
                "Remove access to means (secure pesticides, medications, sharp objects)",
                "Involve family/caregivers immediately",
                "Consider psychiatric admission (voluntary or involuntary under MHA 2017)",
                "Safety planning (crisis numbers, coping strategies)",
                "Document risk assessment thoroughly",
                "24-hour supervision if outpatient"
            ],
            "source": "DGHS_Suicide_Prevention_IPS_mhGAP"
        },

        "substance_use": {
            "age_groups": ["adolescent", "adult"],
            "must_rule_out": [
                {
                    "diagnosis": "Alcohol_Dependence",
                    "features": ["tolerance", "withdrawal", "loss_of_control", "continued_use_despite_harm", "craving", "neglect_of_responsibilities"],
                    "tests": ["AUDIT", "CAGE", "LFT_GGT", "MCV"],
                    "withdrawal_features": "Tremors, sweating, anxiety, insomnia, seizures, delirium tremens"
                },
                {
                    "diagnosis": "Alcohol_Withdrawal_DT",
                    "features": ["tremors", "sweating", "tachycardia", "hypertension", "confusion", "visual_hallucinations", "seizures"],
                    "tests": ["CIWA-Ar", "Electrolytes", "Blood_glucose", "LFT", "Magnesium"],
                    "note": "MEDICAL EMERGENCY - can be fatal. Usually 24-72 hours after last drink"
                },
                {
                    "diagnosis": "Opioid_Dependence",
                    "features": ["heroin_use", "prescription_opioid_misuse", "tolerance", "withdrawal", "injection_marks"],
                    "tests": ["UDS", "HIV", "HBsAg", "HCV"],
                    "withdrawal_features": "Myalgia, lacrimation, rhinorrhea, diarrhea, piloerection, anxiety"
                },
                {
                    "diagnosis": "Cannabis_Use_Disorder",
                    "features": ["daily_use", "tolerance", "craving", "continued_use_despite_problems", "withdrawal"],
                    "tests": ["UDS"],
                    "note": "Common in young adults in India, can trigger psychosis"
                },
                {
                    "diagnosis": "Benzodiazepine_Dependence",
                    "features": ["prescribed_or_illicit_use", "tolerance", "withdrawal_symptoms", "doctor_shopping"],
                    "tests": ["UDS", "Prescription_review"],
                    "note": "Withdrawal can cause seizures - taper slowly, never stop abruptly"
                }
            ],
            "red_flags": [
                "Alcohol withdrawal seizures",
                "Delirium tremens (confusion, hallucinations, fever, autonomic instability)",
                "Wernicke's encephalopathy (confusion, ataxia, ophthalmoplegia) - GIVE THIAMINE",
                "Opioid overdose (pinpoint pupils, respiratory depression, unconscious)",
                "Benzodiazepine withdrawal seizures",
                "Suicidal ideation (common in substance use disorders)",
                "Severe malnutrition",
                "Hepatic encephalopathy"
            ],
            "history_essentials": [
                "Substance(s) used - type, amount, frequency, route",
                "Duration of use",
                "Last use (CRITICAL for withdrawal timing)",
                "Previous withdrawal episodes and severity",
                "Previous detoxification/treatment",
                "Comorbid psychiatric disorders",
                "Medical complications (liver disease, HIV, Hepatitis)",
                "Social consequences (job loss, family problems, legal issues)",
                "Motivation for change (precontemplation, contemplation, preparation, action)",
                "Support system"
            ],
            "first_line_investigations": [
                {"test": "LFT (AST, ALT, GGT)", "rationale": "Alcohol-related liver damage, GGT specific for alcohol", "cost": "LOW"},
                {"test": "CBC", "rationale": "Macrocytosis (alcohol), anemia", "cost": "LOW"},
                {"test": "Electrolytes", "rationale": "Derangement common in withdrawal", "cost": "LOW"},
                {"test": "Blood glucose", "rationale": "Hypoglycemia in alcoholics", "cost": "LOW"},
                {"test": "Magnesium", "rationale": "Often low in alcoholics, needed for seizure prevention", "cost": "LOW"},
                {"test": "UDS", "rationale": "Confirm substances used", "cost": "MEDIUM"},
                {"test": "HIV, HBsAg, HCV", "rationale": "If IV drug use history", "cost": "MEDIUM"}
            ],
            "source": "NDDTC_Guidelines_IPS_mhGAP"
        }
    },

    # =========================================================================
    # NEONATOLOGY
    # =========================================================================
    "neonatology": {

        "respiratory_distress": {
            "age_groups": ["neonate"],
            "must_rule_out": [
                {
                    "diagnosis": "RDS_Respiratory_Distress_Syndrome",
                    "features": ["preterm", "grunting", "nasal_flaring", "intercostal_retraction", "cyanosis"],
                    "tests": ["Chest_Xray", "ABG", "SpO2"],
                    "xray_findings": "Ground glass appearance, air bronchogram, reduced lung volume",
                    "note": "Surfactant deficiency - common in preterm <34 weeks"
                },
                {
                    "diagnosis": "TTN_Transient_Tachypnea_Newborn",
                    "features": ["term_or_near_term", "LSCS_delivery", "tachypnea", "mild_distress", "rapid_improvement"],
                    "tests": ["Chest_Xray", "SpO2"],
                    "xray_findings": "Perihilar streaking, fluid in fissures, hyperinflation",
                    "note": "Usually resolves within 24-72 hours"
                },
                {
                    "diagnosis": "MAS_Meconium_Aspiration",
                    "features": ["meconium_stained_liquor", "post_term", "depressed_at_birth", "barrel_chest"],
                    "tests": ["Chest_Xray", "ABG"],
                    "xray_findings": "Patchy infiltrates, hyperinflation, pneumothorax"
                },
                {
                    "diagnosis": "Pneumothorax",
                    "features": ["sudden_deterioration", "asymmetric_chest", "shift_of_apex_beat", "absent_breath_sounds"],
                    "tests": ["Chest_Xray", "Transillumination"],
                    "immediate": True
                },
                {
                    "diagnosis": "Congenital_Heart_Disease",
                    "features": ["cyanosis", "murmur", "poor_response_to_O2", "differential_cyanosis"],
                    "tests": ["Hyperoxia_test", "SpO2_pre_post_ductal", "2D_Echo", "Chest_Xray"],
                    "note": "Cyanosis not improving with O2 suggests cardiac cause"
                },
                {
                    "diagnosis": "Neonatal_Sepsis",
                    "features": ["lethargy", "poor_feeding", "temperature_instability", "respiratory_distress", "poor_perfusion"],
                    "tests": ["Blood_culture", "CBC", "CRP", "Procalcitonin"],
                    "note": "Respiratory distress may be only sign of sepsis in newborn"
                },
                {
                    "diagnosis": "Congenital_Diaphragmatic_Hernia",
                    "features": ["scaphoid_abdomen", "barrel_chest", "absent_breath_sounds", "bowel_sounds_in_chest"],
                    "tests": ["Chest_Xray"],
                    "immediate": True
                }
            ],
            "red_flags": [
                "Severe distress (Downe score >6, Silverman score >7)",
                "Cyanosis not responding to O2 (consider CHD)",
                "Apnea",
                "Bradycardia (<100/min)",
                "Shock (poor perfusion, prolonged CRT, weak pulses)",
                "Sudden deterioration (pneumothorax)",
                "Seizures"
            ],
            "first_line_investigations": [
                {"test": "SpO2 (pre and post ductal)", "rationale": "Hypoxia assessment, differential cyanosis for CHD", "cost": "FREE"},
                {"test": "Chest X-ray", "rationale": "Differentiate RDS, TTN, MAS, pneumothorax", "cost": "LOW"},
                {"test": "ABG", "rationale": "Respiratory vs metabolic acidosis", "cost": "LOW"},
                {"test": "Blood glucose", "rationale": "Hypoglycemia common in sick neonates", "cost": "LOW"},
                {"test": "CBC, CRP", "rationale": "Sepsis screen", "cost": "LOW"},
                {"test": "Blood culture", "rationale": "If sepsis suspected", "cost": "LOW"}
            ],
            "immediate_assessment": [
                "Downe score / Silverman-Anderson score for severity",
                "Pre and post ductal SpO2",
                "Gestational age and birth weight",
                "Mode of delivery (LSCS increases TTN risk)",
                "Meconium staining of liquor",
                "Perinatal history (prolonged rupture of membranes, maternal fever)"
            ],
            "source": "NNF_CPG_Respiratory_Distress"
        },

        "neonatal_sepsis": {
            "age_groups": ["neonate"],
            "must_rule_out": [
                {
                    "diagnosis": "Early_Onset_Sepsis",
                    "features": ["onset_<72_hours", "maternal_risk_factors", "respiratory_distress", "temperature_instability"],
                    "tests": ["Blood_culture", "CBC", "CRP", "Procalcitonin"],
                    "pathogens": "GBS, E.coli, Klebsiella"
                },
                {
                    "diagnosis": "Late_Onset_Sepsis",
                    "features": ["onset_>72_hours", "nosocomial_risk", "catheter_associated", "NEC_features"],
                    "tests": ["Blood_culture", "CBC", "CRP", "CSF_analysis"],
                    "pathogens": "Klebsiella, Staphylococcus, Candida"
                },
                {
                    "diagnosis": "Meningitis",
                    "features": ["bulging_fontanelle", "seizures", "lethargy", "high_pitched_cry"],
                    "tests": ["CSF_analysis", "Blood_culture", "CBC"]
                }
            ],
            "red_flags": [
                "Shock (poor perfusion, CRT >3 sec, weak pulses)",
                "Apnea",
                "Seizures",
                "Sclerema (hardening of skin)",
                "Bleeding manifestations (DIC)",
                "Bulging fontanelle (meningitis)"
            ],
            "first_line_investigations": [
                {"test": "Blood culture", "rationale": "Gold standard - before antibiotics", "cost": "LOW"},
                {"test": "CBC with differential", "rationale": "WBC count, I:T ratio, thrombocytopenia", "cost": "LOW"},
                {"test": "CRP", "rationale": "Rises in 6-8 hours of infection", "cost": "LOW"},
                {"test": "Procalcitonin", "rationale": "Early marker, helps antibiotic decisions", "cost": "MEDIUM"},
                {"test": "CSF analysis", "rationale": "If meningitis suspected or proven sepsis", "cost": "LOW"},
                {"test": "Urine culture", "rationale": "If late onset sepsis", "cost": "LOW"}
            ],
            "risk_factors_early_onset": [
                "Prolonged rupture of membranes >18 hours",
                "Maternal fever during labor",
                "Maternal GBS colonization",
                "Preterm delivery",
                "Foul smelling liquor",
                "Maternal UTI"
            ],
            "source": "NNF_CPG_Sepsis"
        },

        "neonatal_jaundice": {
            "age_groups": ["neonate"],
            "must_rule_out": [
                {
                    "diagnosis": "Physiological_Jaundice",
                    "features": ["onset_after_24_hours", "peaks_day_3-5", "resolves_by_2_weeks", "well_baby"],
                    "tests": ["TSB_or_TcB"]
                },
                {
                    "diagnosis": "Pathological_Jaundice",
                    "features": ["onset_<24_hours", "rapid_rise", "prolonged_>2_weeks", "direct_hyperbilirubinemia"],
                    "tests": ["TSB", "Direct_bilirubin", "Reticulocyte_count", "Coombs_test", "G6PD"]
                },
                {
                    "diagnosis": "Hemolytic_Disease",
                    "features": ["Rh_incompatibility", "ABO_incompatibility", "G6PD_deficiency", "rapid_rise_bilirubin"],
                    "tests": ["Blood_group_mother_baby", "Coombs_test", "G6PD_screen", "Reticulocyte_count"]
                },
                {
                    "diagnosis": "Sepsis",
                    "features": ["jaundice_with_lethargy", "poor_feeding", "temperature_instability"],
                    "tests": ["Sepsis_screen", "Blood_culture"]
                },
                {
                    "diagnosis": "Biliary_Atresia",
                    "features": ["prolonged_jaundice", "direct_hyperbilirubinemia", "pale_stools", "dark_urine"],
                    "tests": ["Direct_bilirubin", "LFT", "USG_abdomen"],
                    "note": "Surgical emergency - refer if direct bilirubin elevated"
                }
            ],
            "red_flags": [
                "Jaundice within 24 hours of birth",
                "Bilirubin rising >5 mg/dL/day",
                "Bilirubin >95th percentile for age (use Bhutani nomogram)",
                "Signs of acute bilirubin encephalopathy (lethargy, hypotonia, high-pitched cry)",
                "Direct hyperbilirubinemia >2 mg/dL",
                "Jaundice beyond 2 weeks"
            ],
            "first_line_investigations": [
                {"test": "Total Serum Bilirubin", "rationale": "Severity assessment, plot on nomogram", "cost": "LOW"},
                {"test": "Direct Bilirubin", "rationale": "Rule out biliary atresia if elevated", "cost": "LOW"},
                {"test": "Blood group (mother and baby)", "rationale": "ABO/Rh incompatibility", "cost": "LOW"},
                {"test": "Coombs test (DAT)", "rationale": "Immune hemolysis", "cost": "LOW"},
                {"test": "Reticulocyte count", "rationale": "Hemolysis", "cost": "LOW"},
                {"test": "G6PD screen", "rationale": "Common cause in India", "cost": "LOW"}
            ],
            "source": "NNF_CPG_Jaundice_AAP"
        }
    },

    # =========================================================================
    # PEDIATRICS
    # =========================================================================
    "pediatrics": {

        "fever": {
            "age_groups": ["infant", "toddler", "child"],
            "must_rule_out": [
                {
                    "diagnosis": "Sepsis_Meningitis",
                    "features": ["lethargy", "poor_feeding", "bulging_fontanelle", "seizures", "neck_stiffness"],
                    "tests": ["Blood_culture", "CBC", "CRP", "CSF_analysis"],
                    "note": "High index of suspicion in infants <3 months"
                },
                {
                    "diagnosis": "Pneumonia",
                    "features": ["tachypnea", "chest_indrawing", "grunting", "nasal_flaring", "crepitations"],
                    "tests": ["Chest_Xray", "SpO2"],
                    "who_criteria": "Tachypnea: <2mo: >60, 2-12mo: >50, 1-5yr: >40/min"
                },
                {
                    "diagnosis": "UTI",
                    "features": ["unexplained_fever", "irritability", "vomiting", "failure_to_thrive"],
                    "tests": ["Urine_routine", "Urine_culture"],
                    "note": "Common cause of unexplained fever in infants"
                },
                {
                    "diagnosis": "Dengue",
                    "features": ["high_fever", "rash", "bleeding", "hepatomegaly", "thrombocytopenia"],
                    "tests": ["Dengue_NS1_IgM", "CBC"],
                    "india_endemic": True
                },
                {
                    "diagnosis": "Malaria",
                    "features": ["fever_with_chills", "splenomegaly", "anemia"],
                    "tests": ["MP_smear", "Malaria_RDT"],
                    "india_endemic": True
                }
            ],
            "red_flags": [
                "Age <3 months with fever >38°C",
                "Lethargy / inconsolable crying",
                "Not feeding / unable to drink",
                "Bulging fontanelle",
                "Seizures",
                "Respiratory distress (chest indrawing, grunting)",
                "Petechiae / purpura",
                "Signs of dehydration"
            ],
            "first_line_investigations": [
                {"test": "CBC", "rationale": "Leucocytosis, thrombocytopenia", "cost": "LOW"},
                {"test": "CRP", "rationale": "Bacterial vs viral differentiation", "cost": "LOW"},
                {"test": "Urine routine + culture", "rationale": "Occult UTI common in infants", "cost": "LOW"},
                {"test": "Dengue NS1/IgM", "rationale": "Endemic area", "cost": "LOW"},
                {"test": "MP smear", "rationale": "Endemic area", "cost": "LOW"}
            ],
            "source": "IAP_IMCI_Guidelines"
        }
    },

    # =========================================================================
    # OBSTETRICS
    # =========================================================================
    "obstetrics": {

        "hypertension_pregnancy": {
            "age_groups": ["adult"],
            "must_rule_out": [
                {
                    "diagnosis": "Preeclampsia",
                    "features": ["BP_>140/90_after_20_weeks", "proteinuria", "edema", "headache"],
                    "tests": ["BP_monitoring", "Urine_protein_creatinine_ratio", "LFT", "RFT", "Platelet_count"]
                },
                {
                    "diagnosis": "Severe_Preeclampsia",
                    "features": ["BP_>160/110", "severe_headache", "visual_disturbances", "epigastric_pain", "oliguria", "pulmonary_edema"],
                    "tests": ["Above_plus_coagulation_profile"],
                    "immediate": True
                },
                {
                    "diagnosis": "HELLP_Syndrome",
                    "features": ["hemolysis", "elevated_liver_enzymes", "low_platelets", "epigastric_pain", "nausea_vomiting"],
                    "tests": ["LDH", "LFT", "Platelet_count", "Peripheral_smear"],
                    "immediate": True
                },
                {
                    "diagnosis": "Eclampsia",
                    "features": ["seizures_in_preeclampsia", "altered_consciousness"],
                    "tests": ["Clinical_diagnosis"],
                    "immediate": True
                }
            ],
            "red_flags": [
                "BP >160/110 mmHg",
                "Severe headache not relieved by analgesics",
                "Visual disturbances (blurring, scotoma)",
                "Epigastric / RUQ pain",
                "Oliguria (<400 ml/24 hours)",
                "Pulmonary edema",
                "Seizures",
                "Platelets <100,000"
            ],
            "first_line_investigations": [
                {"test": "CBC with platelet count", "rationale": "HELLP screening", "cost": "LOW"},
                {"test": "LFT (AST, ALT, LDH)", "rationale": "HELLP screening", "cost": "LOW"},
                {"test": "RFT (Creatinine, Uric acid)", "rationale": "Renal involvement", "cost": "LOW"},
                {"test": "Urine protein:creatinine ratio", "rationale": "Quantify proteinuria", "cost": "LOW"},
                {"test": "Coagulation profile", "rationale": "If severe preeclampsia", "cost": "MEDIUM"}
            ],
            "source": "FOGSI_GCPR_PIH"
        }
    },

    # =========================================================================
    # CARDIOLOGY
    # =========================================================================
    "cardiology": {
        "chest_pain": {
            "age_groups": ["adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Acute_Coronary_Syndrome",
                    "features": ["retrosternal_chest_pain", "radiation_to_arm_jaw", "sweating", "nausea", "breathlessness"],
                    "tests": ["ECG", "Troponin_I_T", "CK_MB"],
                    "immediate": True
                }
            ],
            "red_flags": [
                "ST elevation on ECG",
                "Positive troponin",
                "Hemodynamic instability"
            ],
            "first_line_investigations": [
                {"test": "ECG (12-lead)", "rationale": "STEMI diagnosis", "cost": "LOW", "immediate": True},
                {"test": "Troponin I/T", "rationale": "Myocardial injury", "cost": "MEDIUM"},
                {"test": "Chest X-ray", "rationale": "Cardiomegaly, pulmonary edema", "cost": "LOW"}
            ],
            "source": "CSI_ACS_Guidelines"
        }
    },

    # =========================================================================
    # ORTHOPEDICS
    # =========================================================================
    "orthopedics": {

        "fracture": {
            "age_groups": ["child", "adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Open_Fracture",
                    "features": ["wound_communicating_with_fracture", "bone_visible", "contamination"],
                    "tests": ["X-ray", "Wound_assessment"],
                    "immediate": True,
                    "note": "Gustilo-Anderson classification determines treatment urgency"
                },
                {
                    "diagnosis": "Neurovascular_Injury",
                    "features": ["pulse_deficit", "pallor", "paresthesia", "paralysis", "pain_on_passive_stretch"],
                    "tests": ["Doppler_if_available", "Clinical_5Ps_assessment"],
                    "immediate": True,
                    "note": "Compartment syndrome is limb-threatening emergency"
                },
                {
                    "diagnosis": "Compartment_Syndrome",
                    "features": ["pain_out_of_proportion", "pain_on_passive_stretch", "tense_compartment", "paresthesia"],
                    "tests": ["Compartment_pressure_measurement", "Clinical_diagnosis"],
                    "immediate": True,
                    "note": "6-hour window for fasciotomy to prevent permanent damage"
                },
                {
                    "diagnosis": "Pathological_Fracture",
                    "features": ["minimal_trauma", "bone_lesion_on_xray", "known_malignancy", "elderly_with_spontaneous_fracture"],
                    "tests": ["X-ray", "Bone_profile", "PSA_if_male", "Tumor_markers", "CT_chest_abdomen_pelvis"],
                    "note": "Consider metastatic bone disease, myeloma, osteoporosis"
                },
                {
                    "diagnosis": "Associated_Injuries",
                    "features": ["high_energy_mechanism", "multiple_injuries", "abdominal_tenderness", "head_injury"],
                    "tests": ["FAST_scan", "CT_as_indicated", "Secondary_survey"],
                    "note": "Follow ATLS protocol for polytrauma"
                }
            ],
            "red_flags": [
                "Open fracture (bone exposed, wound at fracture site)",
                "Neurovascular compromise (5 Ps: Pain, Pallor, Pulselessness, Paresthesia, Paralysis)",
                "Compartment syndrome (pain on passive stretch, tense compartment)",
                "Deformity with skin tenting (risk of skin necrosis)",
                "Fat embolism syndrome (petechiae, confusion, hypoxia post long bone fracture)",
                "Associated head/chest/abdominal injury",
                "Bilateral femur fractures (high blood loss)",
                "Pelvic fracture with hemodynamic instability"
            ],
            "first_line_investigations": [
                {"test": "X-ray (2 views minimum)", "rationale": "Confirm fracture, assess displacement, plan treatment", "cost": "LOW"},
                {"test": "CBC", "rationale": "Baseline for surgery, blood loss assessment", "cost": "LOW"},
                {"test": "Coagulation profile", "rationale": "Pre-operative if surgery planned", "cost": "LOW"},
                {"test": "RFT, Blood glucose", "rationale": "Pre-operative workup, diabetic wound healing", "cost": "LOW"},
                {"test": "CT scan", "rationale": "Complex fractures (spine, pelvis, intra-articular)", "cost": "MEDIUM"},
                {"test": "Doppler ultrasound", "rationale": "If vascular injury suspected", "cost": "MEDIUM"}
            ],
            "history_essentials": [
                "Mechanism of injury (fall, RTA, sports, assault)",
                "Time since injury",
                "Previous injuries to same site",
                "Pre-injury ambulatory status and function",
                "Comorbidities (diabetes, osteoporosis, malignancy)",
                "Anticoagulant use (warfarin, DOACs)",
                "Tetanus immunization status (for open fractures)",
                "Last oral intake (for surgery planning)",
                "Occupation and hand dominance (for upper limb)",
                "Smoking status (affects bone healing)"
            ],
            "source": "IOA_Fracture_Guidelines_ATLS"
        },

        "joint_pain": {
            "age_groups": ["adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Septic_Arthritis",
                    "features": ["acute_onset", "single_joint", "fever", "unable_to_bear_weight", "joint_warm_swollen_red"],
                    "tests": ["Joint_aspiration", "Synovial_fluid_analysis", "Blood_culture", "CBC_CRP_ESR"],
                    "immediate": True,
                    "note": "Joint destruction can occur in 24-48 hours if untreated"
                },
                {
                    "diagnosis": "Gout_Acute",
                    "features": ["acute_onset", "severe_pain", "first_MTP_common", "tophi", "podagra"],
                    "tests": ["Serum_uric_acid", "Joint_aspiration_MSU_crystals", "X-ray"],
                    "note": "Uric acid may be normal during acute attack"
                },
                {
                    "diagnosis": "Fracture",
                    "features": ["trauma_history", "deformity", "point_tenderness", "inability_to_bear_weight"],
                    "tests": ["X-ray"],
                    "note": "Ottawa rules for ankle and knee"
                },
                {
                    "diagnosis": "Inflammatory_Arthritis",
                    "features": ["morning_stiffness_>1hr", "multiple_joints", "symmetric", "small_joint_involvement"],
                    "tests": ["RF", "Anti_CCP", "ESR_CRP", "X-ray_hands_feet"],
                    "note": "Rheumatoid arthritis, psoriatic arthritis, ankylosing spondylitis"
                },
                {
                    "diagnosis": "Osteoarthritis",
                    "features": ["gradual_onset", "worse_with_activity", "better_with_rest", "morning_stiffness_<30min", "crepitus", "bony_enlargement"],
                    "tests": ["X-ray"],
                    "high_probability": True
                },
                {
                    "diagnosis": "Referred_Pain",
                    "features": ["hip_pathology_presenting_as_knee_pain", "spine_pathology_presenting_as_leg_pain"],
                    "tests": ["X-ray_hip", "MRI_spine"],
                    "note": "Always examine joint above and below"
                }
            ],
            "red_flags": [
                "Hot swollen joint with fever (septic arthritis until proven otherwise)",
                "Unable to bear weight",
                "Acute monoarthritis (septic arthritis, gout, fracture)",
                "Joint pain with systemic symptoms (fever, weight loss, night sweats)",
                "Progressive pain with weight loss in elderly (malignancy)",
                "Joint pain post-procedure (iatrogenic septic arthritis)"
            ],
            "first_line_investigations": [
                {"test": "X-ray (weight-bearing if lower limb)", "rationale": "OA changes, fracture, erosions, chondrocalcinosis", "cost": "LOW"},
                {"test": "CBC, CRP, ESR", "rationale": "Inflammatory vs mechanical, infection screen", "cost": "LOW"},
                {"test": "Serum uric acid", "rationale": "Gout (may be normal in acute attack)", "cost": "LOW"},
                {"test": "RF, Anti-CCP", "rationale": "If inflammatory arthritis suspected", "cost": "MEDIUM"},
                {"test": "Joint aspiration & synovial fluid analysis", "rationale": "Gold standard for septic arthritis and crystal arthropathy", "cost": "LOW"}
            ],
            "history_essentials": [
                "Onset (acute vs gradual)",
                "Single joint vs multiple joints",
                "Pattern (symmetric, migratory, additive)",
                "Morning stiffness duration (<30 min suggests OA, >1 hr suggests inflammatory)",
                "Aggravating/relieving factors",
                "Trauma history",
                "Previous episodes",
                "Fever, systemic symptoms",
                "Diet and alcohol (gout)",
                "Recent infections (reactive arthritis)",
                "Family history (RA, gout, psoriasis, AS)",
                "Red eye, skin rash, GI symptoms (seronegative arthritis)"
            ],
            "source": "IOA_Guidelines_EULAR"
        },

        "back_pain": {
            "age_groups": ["adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Cauda_Equina_Syndrome",
                    "features": ["saddle_anesthesia", "urinary_retention_incontinence", "fecal_incontinence", "bilateral_leg_weakness"],
                    "tests": ["Urgent_MRI_spine", "Post_void_residual_urine"],
                    "immediate": True,
                    "note": "Surgical emergency - decompression within 24-48 hours"
                },
                {
                    "diagnosis": "Spinal_Infection",
                    "features": ["fever", "night_sweats", "weight_loss", "constant_pain", "IV_drug_use", "immunocompromised"],
                    "tests": ["MRI_spine_with_contrast", "CBC_CRP_ESR", "Blood_culture", "TB_workup"],
                    "note": "Tuberculosis common in India - spinal TB (Pott's spine)"
                },
                {
                    "diagnosis": "Spinal_Malignancy",
                    "features": ["age_>50_or_<20", "known_malignancy", "night_pain", "weight_loss", "progressive_neurological_deficit"],
                    "tests": ["MRI_spine", "X-ray_spine", "PSA", "Tumor_markers", "Bone_scan"],
                    "note": "Metastatic: breast, lung, prostate, kidney, thyroid"
                },
                {
                    "diagnosis": "Vertebral_Fracture",
                    "features": ["trauma", "osteoporosis", "steroid_use", "point_tenderness_over_spine", "kyphosis"],
                    "tests": ["X-ray_spine", "MRI_if_neurological_deficit", "DEXA_scan"],
                    "note": "May occur with minimal trauma in osteoporotic elderly"
                },
                {
                    "diagnosis": "Disc_Herniation_with_Radiculopathy",
                    "features": ["leg_pain_worse_than_back_pain", "dermatomal_distribution", "positive_SLR", "neurological_deficit"],
                    "tests": ["MRI_spine"],
                    "note": "Most resolve with conservative management in 6-12 weeks"
                },
                {
                    "diagnosis": "Spinal_Stenosis",
                    "features": ["neurogenic_claudication", "relieved_by_sitting_leaning_forward", "bilateral_symptoms", "elderly"],
                    "tests": ["MRI_spine", "X-ray_spine"],
                    "note": "Walking limited by leg pain, not cardiac"
                },
                {
                    "diagnosis": "Ankylosing_Spondylitis",
                    "features": ["young_male", "inflammatory_back_pain", "morning_stiffness_>30min", "improves_with_exercise", "reduced_spinal_mobility"],
                    "tests": ["X-ray_SI_joints", "HLA_B27", "MRI_SI_joints", "CRP_ESR"],
                    "note": "Age <40, insidious onset, >3 months duration"
                },
                {
                    "diagnosis": "Mechanical_Back_Pain",
                    "features": ["no_red_flags", "worse_with_activity", "better_with_rest", "localized", "no_neurological_deficit"],
                    "tests": ["Usually_none_in_first_6_weeks"],
                    "high_probability": True,
                    "note": "90% of back pain - reassurance, activity, physiotherapy"
                }
            ],
            "red_flags": [
                "Cauda equina symptoms (saddle anesthesia, bladder/bowel dysfunction, bilateral leg weakness)",
                "Age <20 or >55 with new onset",
                "History of malignancy",
                "Unexplained weight loss",
                "Fever, night sweats (infection, malignancy)",
                "Night pain disturbing sleep",
                "IV drug use (spinal infection)",
                "Immunosuppression (HIV, steroids)",
                "Recent spinal procedure",
                "Progressive neurological deficit",
                "Structural deformity",
                "Trauma in elderly (vertebral fracture)"
            ],
            "first_line_investigations": [
                {"test": "No imaging needed initially for mechanical back pain", "rationale": "Most resolve in 4-6 weeks, imaging changes management only if red flags", "cost": "FREE"},
                {"test": "X-ray spine (AP + Lateral)", "rationale": "If red flags present - fracture, tumor, infection", "cost": "LOW"},
                {"test": "MRI spine", "rationale": "Gold standard if red flags, radiculopathy, or persistent symptoms >6 weeks", "cost": "HIGH"},
                {"test": "CBC, CRP, ESR", "rationale": "If infection or malignancy suspected", "cost": "LOW"},
                {"test": "HLA-B27", "rationale": "If inflammatory back pain in young patient (AS suspected)", "cost": "MEDIUM"}
            ],
            "history_essentials": [
                "Duration (acute <6 weeks, chronic >12 weeks)",
                "Red flag symptoms - MUST ASK",
                "Radiation to legs (dermatomal pattern suggests radiculopathy)",
                "Bladder/bowel symptoms (cauda equina)",
                "Morning stiffness duration (inflammatory vs mechanical)",
                "Night pain (malignancy, infection)",
                "Aggravating factors (flexion/extension)",
                "Previous episodes",
                "Occupation (heavy lifting, prolonged sitting)",
                "Psychosocial factors (yellow flags - important for chronic pain)",
                "Previous surgery",
                "Trauma history"
            ],
            "examination_essentials": [
                "Gait assessment",
                "Spinal inspection (deformity, muscle spasm)",
                "Range of motion",
                "Palpation (point tenderness over vertebra is concerning)",
                "Straight leg raise (SLR) - positive suggests L4/L5/S1 radiculopathy",
                "Femoral stretch test - positive suggests L2/L3/L4 radiculopathy",
                "Neurological examination (power, sensation, reflexes)",
                "Perianal sensation and anal tone (cauda equina)",
                "Peripheral pulses (vascular claudication differential)"
            ],
            "source": "IOA_Spine_Guidelines_NICE"
        },

        "trauma_limb": {
            "age_groups": ["child", "adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Fracture",
                    "features": ["deformity", "swelling", "point_tenderness", "crepitus", "abnormal_mobility", "inability_to_use_limb"],
                    "tests": ["X-ray"],
                    "note": "Include joint above and below in X-ray"
                },
                {
                    "diagnosis": "Dislocation",
                    "features": ["loss_of_joint_contour", "fixed_abnormal_position", "loss_of_movement", "neurovascular_compromise"],
                    "tests": ["X-ray_pre_and_post_reduction"],
                    "immediate": True,
                    "note": "Reduce as soon as possible to prevent AVN and neurovascular damage"
                },
                {
                    "diagnosis": "Ligament_Injury",
                    "features": ["instability", "hemarthrosis", "mechanism_consistent", "positive_stress_tests"],
                    "tests": ["X-ray_to_rule_out_fracture", "MRI_if_indicated"],
                    "note": "ACL, MCL, ankle ligaments common"
                },
                {
                    "diagnosis": "Tendon_Rupture",
                    "features": ["sudden_pain", "palpable_gap", "weakness", "mechanism_consistent"],
                    "tests": ["Clinical_diagnosis", "USG", "MRI"],
                    "note": "Achilles, biceps, rotator cuff common"
                },
                {
                    "diagnosis": "Soft_Tissue_Injury",
                    "features": ["swelling", "bruising", "tenderness", "no_bony_point_tenderness", "normal_xray"],
                    "tests": ["X-ray_if_indicated_by_clinical_rules"],
                    "high_probability": True
                }
            ],
            "red_flags": [
                "Obvious deformity",
                "Open wound over injury site",
                "Neurovascular compromise (5 Ps)",
                "Gross instability",
                "Unable to bear weight (lower limb)",
                "Skin tenting/blanching",
                "High energy mechanism (RTA, fall from height)"
            ],
            "first_line_investigations": [
                {"test": "X-ray (2 views, joint above and below)", "rationale": "Fracture, dislocation", "cost": "LOW"},
                {"test": "Neurovascular examination", "rationale": "Before and after any manipulation", "cost": "FREE"},
                {"test": "MRI", "rationale": "Soft tissue injury, ligament tear, occult fracture", "cost": "HIGH"},
                {"test": "USG", "rationale": "Tendon injury, effusion, foreign body", "cost": "MEDIUM"}
            ],
            "clinical_decision_rules": [
                "Ottawa Ankle Rules - X-ray if: bone tenderness at posterior 6cm of malleoli or navicular/base 5th MT, or unable to bear weight 4 steps",
                "Ottawa Knee Rules - X-ray if: age >55, isolated patella tenderness, fibular head tenderness, unable to flex 90°, unable to bear weight 4 steps",
                "Ottawa Foot Rules - X-ray if: bone tenderness at navicular or base of 5th metatarsal, or unable to bear weight"
            ],
            "source": "ATLS_Ottawa_Rules_IOA"
        },

        "hip_pain": {
            "age_groups": ["child", "adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Septic_Arthritis_Hip",
                    "features": ["fever", "inability_to_bear_weight", "hip_held_in_flexion_abduction_external_rotation", "severe_pain_on_movement"],
                    "tests": ["USG_guided_aspiration", "Synovial_fluid_analysis", "Blood_culture", "CBC_CRP"],
                    "immediate": True,
                    "note": "Kocher criteria in children - fever >38.5, ESR >40, WBC >12000, non-weight bearing"
                },
                {
                    "diagnosis": "Hip_Fracture",
                    "features": ["elderly", "fall", "shortened_externally_rotated_limb", "groin_pain", "unable_to_bear_weight"],
                    "tests": ["X-ray_pelvis_with_both_hips", "MRI_if_X-ray_negative_but_high_suspicion"],
                    "immediate": True,
                    "note": "Surgical emergency in elderly - mortality increases with delay"
                },
                {
                    "diagnosis": "AVN_Hip",
                    "features": ["steroid_use", "alcohol_use", "sickle_cell", "trauma", "progressive_groin_pain", "limited_ROM"],
                    "tests": ["X-ray", "MRI_early_detection"],
                    "note": "Ficat staging determines treatment"
                },
                {
                    "diagnosis": "SCFE_Slipped_Capital_Femoral_Epiphysis",
                    "features": ["adolescent", "obese", "limp", "knee_pain", "limited_internal_rotation", "obligate_external_rotation_on_flexion"],
                    "tests": ["X-ray_frog_lateral_view"],
                    "immediate": True,
                    "age_group": "adolescent",
                    "note": "Check contralateral hip - 30% bilateral"
                },
                {
                    "diagnosis": "Perthes_Disease",
                    "features": ["child_4-10_years", "limp", "groin_knee_thigh_pain", "limited_abduction_internal_rotation"],
                    "tests": ["X-ray", "MRI_for_staging"],
                    "age_group": "child",
                    "note": "AVN of femoral head in children"
                },
                {
                    "diagnosis": "Transient_Synovitis",
                    "features": ["child", "viral_illness_preceding", "mild_pain", "mild_limitation_of_movement", "low_grade_or_no_fever"],
                    "tests": ["X-ray", "USG_hip_effusion", "CBC_CRP_ESR"],
                    "age_group": "child",
                    "note": "Diagnosis of exclusion - must rule out septic arthritis"
                },
                {
                    "diagnosis": "Osteoarthritis_Hip",
                    "features": ["elderly", "groin_pain", "gradual_onset", "worse_with_activity", "limited_ROM", "limp"],
                    "tests": ["X-ray_pelvis"],
                    "high_probability": True
                },
                {
                    "diagnosis": "Referred_Pain_from_Spine",
                    "features": ["back_pain", "dermatomal_distribution", "neurological_signs", "SLR_positive"],
                    "tests": ["Lumbar_spine_X-ray", "MRI_spine"],
                    "note": "L2-L4 radiculopathy can present as hip/thigh pain"
                }
            ],
            "red_flags": [
                "Fever with hip pain (septic arthritis)",
                "Inability to bear weight",
                "Trauma in elderly (hip fracture)",
                "Adolescent with knee pain and limp (SCFE)",
                "Child with limp and fever (septic arthritis vs transient synovitis)",
                "Night pain with weight loss (malignancy)",
                "History of steroid use or alcohol (AVN)"
            ],
            "first_line_investigations": [
                {"test": "X-ray pelvis AP + lateral hip", "rationale": "Fracture, OA, AVN, SCFE, Perthes", "cost": "LOW"},
                {"test": "CBC, CRP, ESR", "rationale": "Infection screen", "cost": "LOW"},
                {"test": "USG hip", "rationale": "Effusion detection, guide aspiration", "cost": "LOW"},
                {"test": "MRI hip", "rationale": "Early AVN, occult fracture, infection, soft tissue", "cost": "HIGH"},
                {"test": "Hip aspiration under USG guidance", "rationale": "If septic arthritis suspected", "cost": "MEDIUM"}
            ],
            "history_essentials": [
                "Age (SCFE in adolescents, Perthes in children, AVN/fracture in elderly)",
                "Onset (acute vs gradual)",
                "Trauma history",
                "Pain location (groin, lateral hip, buttock, knee - referred)",
                "Weight bearing status",
                "Limp",
                "Fever, systemic symptoms",
                "Steroid use, alcohol use, sickle cell disease (AVN risk)",
                "Recent viral illness in child (transient synovitis)",
                "Night pain (malignancy)",
                "Bilateral symptoms (check both hips)"
            ],
            "source": "IOA_Pediatric_Guidelines_NICE"
        },

        "knee_pain": {
            "age_groups": ["child", "adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Septic_Arthritis",
                    "features": ["acute_onset", "fever", "red_hot_swollen_knee", "unable_to_bear_weight", "severe_pain"],
                    "tests": ["Joint_aspiration", "Synovial_fluid_analysis", "Blood_culture", "CBC_CRP"],
                    "immediate": True
                },
                {
                    "diagnosis": "ACL_Tear",
                    "features": ["twisting_injury", "pop_felt", "immediate_swelling", "instability", "positive_Lachman_anterior_drawer"],
                    "tests": ["X-ray", "MRI"],
                    "note": "Hemarthrosis common"
                },
                {
                    "diagnosis": "Meniscal_Tear",
                    "features": ["twisting_injury", "locking", "giving_way", "joint_line_tenderness", "positive_McMurray"],
                    "tests": ["X-ray", "MRI"],
                    "note": "May coexist with ACL tear"
                },
                {
                    "diagnosis": "Fracture",
                    "features": ["trauma", "swelling", "deformity", "unable_to_bear_weight", "bony_tenderness"],
                    "tests": ["X-ray"],
                    "note": "Apply Ottawa Knee Rules"
                },
                {
                    "diagnosis": "Patellar_Dislocation",
                    "features": ["lateral_dislocation", "hemarthrosis", "apprehension_test_positive", "young_female"],
                    "tests": ["X-ray_skyline_view", "MRI_for_osteochondral_injury"]
                },
                {
                    "diagnosis": "Referred_Hip_Pain",
                    "features": ["hip_pathology", "limited_hip_ROM", "no_knee_pathology_on_examination"],
                    "tests": ["Hip_X-ray"],
                    "note": "ALWAYS examine hip in child with knee pain"
                },
                {
                    "diagnosis": "Osteoarthritis",
                    "features": ["elderly", "gradual_onset", "worse_with_stairs", "morning_stiffness_<30min", "crepitus", "bony_enlargement"],
                    "tests": ["X-ray_weight_bearing"],
                    "high_probability": True
                },
                {
                    "diagnosis": "Gout_Pseudogout",
                    "features": ["acute_onset", "red_hot_swollen", "elderly", "chondrocalcinosis_on_xray"],
                    "tests": ["Joint_aspiration", "X-ray", "Serum_uric_acid"]
                }
            ],
            "red_flags": [
                "Hot swollen joint with fever (septic arthritis)",
                "Locked knee (meniscal tear, loose body)",
                "Significant hemarthrosis (ACL tear, fracture)",
                "Inability to bear weight post-injury",
                "Child with knee pain (examine hip - SCFE, Perthes)",
                "Popliteal swelling (Baker's cyst rupture, DVT)"
            ],
            "first_line_investigations": [
                {"test": "X-ray knee (AP, Lateral, Skyline)", "rationale": "Fracture, OA, loose body, chondrocalcinosis", "cost": "LOW"},
                {"test": "MRI knee", "rationale": "Soft tissue - ligaments, meniscus, cartilage", "cost": "HIGH"},
                {"test": "Joint aspiration", "rationale": "If effusion - infection, gout, hemarthrosis", "cost": "LOW"},
                {"test": "CBC, CRP", "rationale": "If septic arthritis suspected", "cost": "LOW"}
            ],
            "history_essentials": [
                "Mechanism of injury (twisting, direct blow, hyperextension)",
                "Swelling - immediate (hemarthrosis) vs delayed (reactive effusion)",
                "Locking (meniscus, loose body)",
                "Giving way/instability (ACL, patellar)",
                "Location of pain (medial, lateral, anterior, posterior)",
                "Stairs difficulty (patellofemoral)",
                "Morning stiffness duration",
                "Previous injuries/surgery",
                "Age (consider referred hip pain in children)"
            ],
            "source": "IOA_Knee_Guidelines_ESSKA"
        },

        "shoulder_pain": {
            "age_groups": ["adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Septic_Arthritis",
                    "features": ["fever", "severe_pain", "swelling", "unable_to_move_shoulder"],
                    "tests": ["Joint_aspiration", "Blood_culture", "CBC_CRP"],
                    "immediate": True
                },
                {
                    "diagnosis": "Shoulder_Dislocation",
                    "features": ["trauma", "loss_of_contour", "arm_held_in_abduction_external_rotation", "axillary_nerve_check"],
                    "tests": ["X-ray_AP_lateral_axillary"],
                    "immediate": True,
                    "note": "Check neurovascular status before and after reduction"
                },
                {
                    "diagnosis": "Rotator_Cuff_Tear",
                    "features": ["age_>40", "weakness", "night_pain", "painful_arc", "positive_drop_arm_test"],
                    "tests": ["X-ray", "USG_shoulder", "MRI"],
                    "note": "Acute tear post-trauma vs chronic degenerative"
                },
                {
                    "diagnosis": "Frozen_Shoulder",
                    "features": ["gradual_onset", "global_restriction_movement", "pain_at_end_range", "diabetes_thyroid_association"],
                    "tests": ["X-ray_usually_normal", "Clinical_diagnosis"],
                    "note": "Adhesive capsulitis - typically self-limiting over 1-3 years"
                },
                {
                    "diagnosis": "Fracture",
                    "features": ["trauma", "swelling", "deformity", "crepitus"],
                    "tests": ["X-ray_shoulder_series"],
                    "note": "Proximal humerus fracture common in elderly after fall"
                },
                {
                    "diagnosis": "Referred_Pain",
                    "features": ["cervical_spine_pathology", "cardiac_pain", "diaphragm_irritation", "apex_lung_tumor"],
                    "tests": ["Cervical_spine_X-ray", "ECG_if_indicated", "Chest_X-ray"],
                    "note": "C5 radiculopathy mimics shoulder pain"
                },
                {
                    "diagnosis": "Impingement_Syndrome",
                    "features": ["painful_arc_60-120_degrees", "positive_Neer_Hawkins_tests", "overhead_activity_aggravates"],
                    "tests": ["X-ray", "USG", "MRI"],
                    "note": "Subacromial bursitis, rotator cuff tendinopathy"
                }
            ],
            "red_flags": [
                "Trauma with deformity (dislocation, fracture)",
                "Fever with joint pain (septic arthritis)",
                "First-time dislocation in age >40 (rotator cuff tear associated)",
                "Weakness without pain (nerve injury, cuff tear)",
                "Chest pain with shoulder pain (cardiac)",
                "Night pain with weight loss (malignancy - Pancoast tumor)"
            ],
            "first_line_investigations": [
                {"test": "X-ray shoulder (AP, Lateral, Axillary)", "rationale": "Fracture, dislocation, OA, calcification", "cost": "LOW"},
                {"test": "USG shoulder", "rationale": "Rotator cuff tear, bursitis, effusion", "cost": "MEDIUM"},
                {"test": "MRI shoulder", "rationale": "Soft tissue detail - cuff, labrum, capsule", "cost": "HIGH"},
                {"test": "Cervical spine X-ray", "rationale": "If referred pain suspected", "cost": "LOW"}
            ],
            "history_essentials": [
                "Onset (acute trauma vs gradual)",
                "Mechanism of injury",
                "Night pain (rotator cuff, frozen shoulder)",
                "Weakness (cuff tear, nerve injury)",
                "Stiffness (frozen shoulder)",
                "Instability (recurrent dislocation)",
                "Occupation (overhead work, sports)",
                "Age (degenerative cuff disease in >40)",
                "Diabetes, thyroid disease (frozen shoulder association)",
                "Previous shoulder problems"
            ],
            "source": "IOA_Shoulder_Guidelines_BESS"
        }
    }
}


# =============================================================================
# Lookup Functions
# =============================================================================

def get_differential(specialty: str, presentation: str) -> Dict[str, Any]:
    """
    Get differential diagnosis data for a specialty and presentation.

    Args:
        specialty: Clinical specialty (e.g., 'general_medicine', 'psychiatry')
        presentation: Clinical presentation (e.g., 'fever', 'depression')

    Returns:
        Dictionary with differential data or empty dict if not found
    """
    return DIFFERENTIAL_TREES.get(specialty, {}).get(presentation, {})


def get_all_presentations(specialty: str) -> List[str]:
    """
    Get all available presentations for a specialty.

    Args:
        specialty: Clinical specialty

    Returns:
        List of presentation names
    """
    return list(DIFFERENTIAL_TREES.get(specialty, {}).keys())


def match_presentations(
    chief_complaints: List[str],
    specialty: str,
    diagnoses: Optional[List[str]] = None
) -> List[str]:
    """
    Match chief complaints to known presentations for a specialty.

    Uses keyword matching to identify relevant differential trees.

    Args:
        chief_complaints: List of chief complaint strings
        specialty: Clinical specialty
        diagnoses: Optional list of diagnoses discussed (for additional matching)

    Returns:
        List of matched presentation names
    """
    available = set(DIFFERENTIAL_TREES.get(specialty, {}).keys())

    if not available:
        return []

    # Keyword mapping for presentations
    keyword_map = {
        # General Medicine
        "fever": ["fever", "temperature", "pyrexia", "febrile", "high temperature"],
        "chest_pain": ["chest pain", "chest discomfort", "angina", "retrosternal"],
        "hypertension": ["hypertension", "high bp", "blood pressure", "htn"],
        "diabetes_review": ["diabetes", "sugar", "dm", "blood glucose", "diabetic"],

        # Psychiatry
        "depression": ["depression", "depressed", "sad", "low mood", "anhedonia", "hopeless", "worthless"],
        "anxiety": ["anxiety", "anxious", "panic", "worry", "nervous", "palpitation"],
        "psychosis": ["psychosis", "hallucination", "delusion", "hearing voices", "paranoid"],
        "suicide_risk": ["suicidal", "suicide", "self harm", "want to die", "end my life", "kill myself"],
        "substance_use": ["alcohol", "drinking", "addiction", "drugs", "withdrawal", "de-addiction"],

        # Neonatology
        "respiratory_distress": ["respiratory distress", "breathing difficulty", "grunting", "retraction", "tachypnea"],
        "neonatal_sepsis": ["sepsis", "infection", "lethargy", "poor feeding", "temperature instability"],
        "neonatal_jaundice": ["jaundice", "yellow", "bilirubin", "icterus"],

        # Pediatrics
        # (uses same fever keywords as general medicine)

        # Obstetrics
        "hypertension_pregnancy": ["preeclampsia", "eclampsia", "pih", "pregnancy induced hypertension", "hellp"],

        # Orthopedics
        "fracture": ["fracture", "broken", "break", "#", "malleolus", "tibia", "fibula", "radius", "ulna",
                     "humerus", "femur", "patella", "clavicle", "scaphoid", "metatarsal", "phalanx",
                     "colles", "smith", "potts", "displaced", "undisplaced", "cast", "plaster"],
        "joint_pain": ["joint pain", "arthritis", "arthralgia", "swollen joint", "stiff joint",
                       "osteoarthritis", "rheumatoid", "gout", "uric acid"],
        "back_pain": ["back pain", "backache", "lumbar", "lumbago", "sciatica", "disc", "spine",
                      "vertebra", "radiculopathy", "slipped disc", "prolapse", "spondylosis",
                      "spondylolisthesis", "stenosis"],
        "trauma_limb": ["trauma", "injury", "fall", "rta", "road traffic", "accident", "sprain",
                        "strain", "ligament", "tendon", "dislocation", "contusion"],
        "hip_pain": ["hip pain", "groin pain", "avascular necrosis", "avn", "hip fracture",
                     "neck of femur", "nof", "total hip", "hip replacement", "limp", "scfe", "perthes"],
        "knee_pain": ["knee pain", "knee injury", "acl", "mcl", "meniscus", "ligament tear",
                      "knee replacement", "tkr", "patella", "knee swelling", "locked knee"],
        "shoulder_pain": ["shoulder pain", "rotator cuff", "frozen shoulder", "shoulder dislocation",
                          "impingement", "adhesive capsulitis", "supraspinatus", "biceps tendon"],
    }

    matched = []
    complaint_text = " ".join(chief_complaints).lower() if chief_complaints else ""
    diagnosis_text = " ".join(diagnoses).lower() if diagnoses else ""
    combined_text = complaint_text + " " + diagnosis_text

    for presentation in available:
        keywords = keyword_map.get(presentation, [presentation.replace("_", " ")])

        for keyword in keywords:
            if keyword.lower() in combined_text:
                if presentation not in matched:
                    matched.append(presentation)
                break

    return matched


def get_red_flags(specialty: str, presentation: str) -> List[str]:
    """
    Get red flags for a specific presentation.

    Args:
        specialty: Clinical specialty
        presentation: Clinical presentation

    Returns:
        List of red flag strings
    """
    diff = get_differential(specialty, presentation)
    return diff.get("red_flags", [])


def get_first_line_investigations(specialty: str, presentation: str) -> List[Dict[str, Any]]:
    """
    Get first-line investigations for a presentation.

    Args:
        specialty: Clinical specialty
        presentation: Clinical presentation

    Returns:
        List of investigation dictionaries
    """
    diff = get_differential(specialty, presentation)
    return diff.get("first_line_investigations", [])


def get_history_essentials(specialty: str, presentation: str) -> List[str]:
    """
    Get essential history questions for a presentation.

    Args:
        specialty: Clinical specialty
        presentation: Clinical presentation

    Returns:
        List of history question strings
    """
    diff = get_differential(specialty, presentation)
    return diff.get("history_essentials", [])

"""
Consultation Insights Extraction Prompts (v1.3.0)

Prompts and schemas for extracting clinical signals needed for:
- Clinical Severity Assessment
- Other Clinical Needs
- Allied Health Needs (all 9 indicators including mental health and education)
- Patient Dropoff Risk (retention risk with 5 churn indicators)

This module uses ICD-10 context validation - the LLM cross-references its own
extracted ICD codes to validate clinical signals, reducing error propagation.

Features:
- 14 signal groups for comprehensive clinical assessment
- ICD code cross-validation for accuracy
- Evidence-based extraction with reasoning trails
- Full priority/severity calculation functions matching original services
- Patient dropoff risk calculation (retention risk)
- Integration with existing assessment services

Author: Claude Code
Date: 2025-12-27
Version: 1.3.0 (Added competitor_signals and access_logistics_signals for retention risk)
"""

import logging
from enum import Enum
from google.genai import types
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


# ============================================================================
# Enums for Priority/Severity Levels
# ============================================================================

class SeverityLevel(Enum):
    """Clinical severity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PriorityLevel(Enum):
    """Priority levels for clinical needs and allied health."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# ============================================================================
# ICD-10 Scoring Configuration (from clinical_severity_service.py)
# ============================================================================

# ICD-10 codes that ALWAYS trigger HIGH severity (hard overrides)
ICD_CRITICAL_PREFIXES = {
    "I21", "I22",  # Acute MI
    "I46",         # Cardiac arrest
    "I60", "I61", "I63",  # Stroke/hemorrhage
    "J96",         # Respiratory failure
    "N17",         # Acute kidney failure
    "K72",         # Hepatic failure
    "E10.1", "E11.1",  # Diabetic ketoacidosis
    "T78.2",       # Anaphylactic shock
    "A41",         # Sepsis
    "R65.2",       # Severe sepsis
    "C",           # All cancers (malignancy)
}

# ICD-10 chapter/prefix to severity score mapping
ICD_CHAPTER_SCORES = {
    # HIGH severity (4 points)
    "C": 4, "D0": 4, "I2": 4, "I5": 4, "I6": 4, "N18": 4, "Z94": 4,
    # MEDIUM-HIGH severity (3 points)
    "E10": 3, "E11": 3, "I1": 3, "I4": 3, "J44": 3, "J45": 3,
    "K70": 3, "K74": 3, "F2": 3, "F3": 3, "B20": 3,
    # MEDIUM severity (2 points)
    "M": 2, "G": 2, "K": 2, "N": 2, "E0": 2, "F": 2, "J": 2, "D5": 2,
    # LOW severity (1 point)
    "H": 1, "L": 1, "R": 1, "Z": 1, "J0": 1,
}

# Specialty to severity score mapping
SPECIALTY_SCORES = {
    # High stakes (3 points)
    "oncology": 3, "cardiology": 3, "cardiac_surgery": 3, "neurology": 3,
    "neurosurgery": 3, "nephrology": 3, "transplant": 3, "critical_care": 3,
    "icu": 3, "hematology": 3, "neonatology": 3,
    # Medium stakes (2 points)
    "endocrinology": 2, "pulmonology": 2, "orthopedics": 2, "orthopedic_surgery": 2,
    "psychiatry": 2, "gastroenterology": 2, "rheumatology": 2, "urology": 2,
    "gynecology": 2, "obstetrics": 2, "infectious_disease": 2, "vascular_surgery": 2,
    "general_surgery": 2,
    # Lower stakes (1 point)
    "dermatology": 1, "ent": 1, "ophthalmology": 1, "general_medicine": 1,
    "family_medicine": 1, "internal_medicine": 1, "pediatrics": 1, "allergy": 1,
    "sports_medicine": 1, "physical_therapy": 1,
}

# ============================================================================
# System Prompt for Consultation Insights Extraction
# ============================================================================

CONSULTATION_INSIGHTS_SYSTEM_PROMPT = """You are a clinical insights extractor. Analyze the medical consultation transcript and extract structured signals for clinical assessment systems.

You will receive the original transcript along with previously extracted segments (DIAGNOSIS with ICD codes, PRESCRIPTION, INVESTIGATIONS, FOLLOW_UP, TREATMENT_PLAN). Use BOTH the transcript AND these extracted segments to generate accurate clinical insights.

Cross-validate your assessments against the ICD codes - if E11.65 (diabetes with CKD) was coded, ensure your signals reflect both diabetes AND renal monitoring needs.

## EXTRACTION RULES

1. **Be Evidence-Based**: Only mark indicators as TRUE if there is clear evidence in the transcript or extracted segments
2. **Cross-Validate with ICD**: Your ICD codes should align with your clinical signals. If there's a mismatch, prefer the more clinically accurate interpretation from the transcript
3. **Quote Evidence**: Include FULL quotes from the transcript as evidence (do NOT truncate with "..." - include the complete sentence/statement)
4. **Age Estimation**: If patient age is mentioned, extract it. If inferable (e.g., "retired", "senior"), estimate. Otherwise mark as unknown
5. **Be Conservative**: When uncertain, lean towards FALSE for boolean indicators

## EXTRACTION GUIDELINES

### Clinical Severity Signals

**is_chronic**
- TRUE if ongoing/long-term condition management discussed or if Diagnosis is a chronic medical condition
- Cross-check ICD: E10-E14, I10-I15, J44-J45, N18 indicate chronic
- Also TRUE if "maintenance", "lifelong", "ongoing", "long-term" mentioned

**is_surgical**
- TRUE if surgery, procedure, or post-operative care mentioned or potential surgery suggested as an alternate after trying current medical management
- Cross-check: ICD codes starting with S, T (injuries), or procedure mentions in TREATMENT_PLAN

**follow_up_urgency**
- "urgent": Immediate/emergency, within 24-48 hours
- "soon": Within 1-2 weeks, priority follow-up
- "routine": Regular scheduled follow-up (monthly, quarterly)
- Cross-check with FOLLOW_UP.review_date and FOLLOW_UP.other_instructions

**is_second_opinion_recommended**
- TRUE if referral to specialist or second opinion explicitly suggested
- Also look for these words: "consult with", "refer to", "specialist opinion", "get another opinion"

**is_alternate_treatment_discussed**
- TRUE if fallback/alternative treatment options discussed
- Also look for these words: "if this doesn't work", "alternative would be", "plan B", "second-line"

**critical_condition_detected**
- TRUE for life-threatening conditions requiring immediate attention
- Cross-check ICD: I21, I60-I64, C*, J96, N17, A41/R65.2

### Diagnostic Needs

**has_ordered_tests**
- TRUE if new tests are ordered during THIS consultation
- Cross-check: INVESTIGATIONS array for ordered tests

**needs_recurring_monitoring**
- TRUE for conditions requiring periodic testing or in cases of chronic disease management
- Cross-check ICD: E10-E11→HbA1c, N18→Renal, E03/E05→Thyroid, I10-I15→BP/Renal, E78→Lipid, B20→Viral load

### Medication Signals

**total_medications_prescribed**
- Count from PRESCRIPTION segment
- Include all medications (not just new ones)

**max_duration_days**
- Longest prescription duration from PRESCRIPTION.durationDays
- Convert text to number if needed ("3 months" = 90)

**has_long_term_medications**
- TRUE if any medication prescribed for >30 days. However don't consider if the medicine if vitamins/supplements with vague durations
- TRUE if keywords: "maintenance", "lifelong", "continue indefinitely", "long-term"
- Cross-check: Chronic ICD codes typically have long-term medications

### Nutritional Signals

**has_metabolic_condition**
- TRUE if diabetes, obesity, cardiac disease, or dyslipidemia present
- Cross-check ICD: E10-E11, E66, E78, I*

**has_detailed_diet_instructions**
- TRUE if TREATMENT_PLAN array contains specific dietary instructions
- Also look for: diet, activity, monitoring instructions in the treatment plan items
- NOT true if just "N/A" or "follow diabetic diet" without specifics

**nutritional_counseling_mentioned**
- TRUE if dietitian, nutritionist, or nutrition counseling explicitly mentioned

**nutritional_counseling_potential**
- TRUE if metabolic condition present but no detailed diet instructions given yet
- Infers potential benefit from nutritional counseling even if not explicitly discussed
- Consider TRUE when: diabetes/obesity/cardiac without specific dietary guidance

### Physiotherapy Signals

**has_musculoskeletal_condition**
- TRUE for back pain, joint pain, arthritis, muscle issues, spine problems
- Cross-check ICD: M* (musculoskeletal), cervical/lumbar conditions

**has_injury**
- TRUE for fractures, sprains, trauma, post-accident conditions
- Cross-check ICD: S* (injuries), T* (trauma)

**physiotherapy_explicitly_mentioned**
- Only TRUE if "physiotherapy", "physical therapy", "PT", or "physio" explicitly mentioned
- NOT true just because there's a musculoskeletal condition

**physiotherapy_potential**
- TRUE if possibility of physiotherapy - even if not discussed based on musculoskeletal condition

### Homecare Signals

**has_mobility_issues**
- TRUE if difficulty walking, wheelchair use, bedridden, needs assistance
- Also look for these words: "can't walk", "difficulty moving", "needs help", "homebound"

**homecare_discussed**
- TRUE if home nursing, home care services, caregiver support mentioned

**homecare_potential**
- TRUE if elderly (>70) with chronic condition OR mobility challenges exist
- Infers potential benefit from home care even if not explicitly discussed
- Consider TRUE when: age >70 + chronic disease, or any mobility limitations without formal homecare discussion

### Sleep Signals

**has_sleep_symptoms**
- TRUE if snoring, sleep apnea, insomnia, chronic fatigue, daytime sleepiness mentioned
- Also look for these words: "can't sleep", "tired all day", "snoring", "waking up at night"

**has_obesity_or_hypertension**
- Cross-check ICD: E66, I10-I15
- Also TRUE if BMI mentioned >30 or "overweight", "obese" in transcript

**sleep_therapy_mentioned**
- TRUE if CPAP, sleep study, polysomnography, sleep specialist mentioned

**sleep_therapy_potential**
- TRUE if sleep symptoms present with obesity/hypertension, even without explicit sleep therapy discussion
- Infers potential benefit from sleep evaluation
- Consider TRUE when: snoring/fatigue + obesity/HTN without sleep study ordered

### Rehabilitation Signals

**has_cardiac_event**
- TRUE for recent MI, ischemic heart disease, post-CABG, stent, angioplasty
- Cross-check ICD: I21, I25, Z95.1, Z95.5

**has_stroke**
- TRUE for recent cerebrovascular event
- Cross-check ICD: I60-I64, I69

**has_orthopedic_surgery**
- TRUE for joint replacement, fracture fixation, spine surgery
- Also look for these words: "post-operative", "surgery recovery", "replacement"

**cardiac_rehab_mentioned / general_rehab_mentioned**
- TRUE only if rehabilitation explicitly discussed

**cardiac_rehab_potential**
- TRUE if cardiac event present (MI, CABG, stent) but cardiac rehab not explicitly discussed
- Infers potential benefit from cardiac rehabilitation program
- Consider TRUE when: recent cardiac procedure/event without rehab referral mentioned

**general_rehab_potential**
- TRUE if stroke or orthopedic surgery present but general rehab not explicitly discussed
- Infers potential benefit from rehabilitation services
- Consider TRUE when: post-stroke or post-surgery recovery without rehab plan discussed

### Wellness Signals

**has_lifestyle_disease**
- TRUE if diabetes, obesity, hypertension, or dyslipidemia present
- Cross-check ICD: E10-E11, E66, I10-I15, E78

**prevention_discussed**
- TRUE if preventive measures, screening, risk reduction discussed
- Also look for these words: "prevent", "avoid complications", "regular check-ups"

**lifestyle_modification_discussed**
- TRUE if diet changes, exercise, smoking cessation, weight management discussed
- Also look for these words: "lose weight", "quit smoking", "exercise more", "change diet"

**wellness_potential**
- TRUE if lifestyle disease present but no prevention/lifestyle discussion occurred
- Infers potential benefit from wellness program even if not explicitly discussed
- Consider TRUE when: diabetes/obesity/HTN without explicit lifestyle counseling

### Mental Health Signals

**anxiety_level**
- Assess from patient behavior and verbal cues: None, Mild, Moderate, Severe
- Severe: Panic, unable to cope, overwhelming worry, physical symptoms (trembling, sweating)
- Moderate: Visible worry, repeated questions about prognosis, difficulty focusing
- Mild: Some concern but generally engaged, minor nervousness
- None: Calm, relaxed demeanor

**depression_indicators_present**
- TRUE if hopelessness, withdrawal, loss of interest, flat affect mentioned
- Also look for these words: "no point", "given up", "don't care anymore", "nothing helps"

**distress_indicators_present**
- TRUE if acute emotional distress: crying, panic, overwhelmed, agitation
- Also look for these words: emotional breakdown, unable to process information

**mental_health_keywords_found**
- TRUE if TREATMENT_PLAN mentions mental health support
- Keywords: counseling, therapy, psychologist, psychiatrist, mental health, emotional support, stress management, relaxation, mindfulness, CBT, cognitive behavioral, anxiety management, depression support

**mental_health_support_potential**
- TRUE if mild/moderate anxiety or emotional concerns present but no mental health support discussed
- Infers potential benefit from mental health services even if not explicitly discussed
- Consider TRUE when: visible worry, stress indicators, or chronic disease burden without emotional support offered

### Education Signals

**is_new_diagnosis**
- TRUE if newly diagnosed condition discussed
- Keywords: "newly diagnosed", "new onset", "first time", "just diagnosed", "recent diagnosis", "diagnosed today", "confirmed today", "initial diagnosis"

**understanding_barrier_present**
- TRUE if patient shows difficulty understanding treatment
- Look for: repeated questions, confusion about medications, "I don't understand", doctor repeating explanations, need for simplification
- Also TRUE if patient asks many clarifying questions about how to take medications or what the disease means

**education_discussed**
- TRUE if patient education, training, or teaching mentioned
- Also look for these words: "let me explain", "you need to understand", "disease education", "self-management training"

**education_potential**
- TRUE if new/complex diagnosis present but no formal education discussion occurred
- Infers potential benefit from patient education even if not explicitly discussed
- Consider TRUE when: new chronic diagnosis (diabetes, HTN, etc.) or complex treatment regimen without education

### Competitor Signals (Retention Risk)

**competitor_intent_detected**
- TRUE if patient mentions considering other healthcare providers
- Look for: mentions of other hospitals, clinics, or doctors by name
- Look for: "second opinion elsewhere", "check with another doctor", "I heard XYZ is better"
- Look for: comparison statements ("the other hospital said...", "at ABC they do it differently")
- Be conservative: Only TRUE if clear intent to seek care elsewhere

**competitor_names_mentioned**
- List specific competitor names if mentioned (hospital names, clinic names, doctor names)
- Empty array if no specific names

**competitor_reason**
- Why patient is considering alternatives: cost, quality, convenience, recommendation, dissatisfaction
- null if no competitor intent

### Access/Logistics Signals (Retention Risk)

**access_barriers_detected**
- TRUE if patient mentions difficulty accessing care
- Look for: distance/travel concerns ("too far", "difficult to come", "long journey")
- Look for: transportation issues ("no vehicle", "can't drive", "need someone to bring me")
- Look for: waiting time complaints ("waited hours", "long queue", "appointment delays")
- Look for: scheduling difficulties ("can't take time off", "work conflicts", "timing issues")
- Look for: parking issues ("no parking", "expensive parking")

**access_barrier_types**
- Array of barrier types: distance, transportation, waiting_time, scheduling, parking, other
- Empty array if no barriers

**access_severity**
- None, Mild, Moderate, Severe based on impact on patient's ability to return
- Severe: Patient explicitly states they may not be able to come back
- Moderate: Significant inconvenience expressed
- Mild: Minor complaint without impact on return likelihood

## OUTPUT FORMAT

Return a valid JSON object matching the schema exactly. All fields are required.
- Use null for unknown numeric values
- Use empty arrays [] for no evidence
- Use false for unconfirmed booleans
- Include evidence strings that reference both transcript quotes AND ICD code validation"""


# ============================================================================
# Gemini Schema for Consultation Insights (v1.1.0)
# ============================================================================

CONSULTATION_INSIGHTS_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # 1. Patient Signals
        "patient_signals": types.Schema(
            type=types.Type.OBJECT,
            description="Patient demographic signals",
            properties={
                "estimated_age_years": types.Schema(
                    type=types.Type.INTEGER,
                    nullable=True,
                    description="Patient's estimated age in years (null if unknown)"
                ),
                "age_source": types.Schema(
                    type=types.Type.STRING,
                    description="How age was determined: mentioned (explicit), inferred (from context like 'retired'), unknown"
                ),
            },
            required=["estimated_age_years", "age_source"]
        ),

        # 2. Clinical Severity Signals
        "clinical_severity_signals": types.Schema(
            type=types.Type.OBJECT,
            description="Clinical severity assessment signals",
            properties={
                "is_chronic": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Ongoing/long-term condition requiring maintenance care"
                ),
                "chronic_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence including ICD codes and transcript quotes"
                ),
                "is_surgical": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Surgery, procedure, or post-operative care involved"
                ),
                "surgical_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence for surgical involvement"
                ),
                "follow_up_urgency": types.Schema(
                    type=types.Type.STRING,
                    description="routine (monthly+), soon (1-2 weeks), urgent (24-48 hours)"
                ),
                "urgency_evidence": types.Schema(
                    type=types.Type.STRING,
                    description="Evidence for urgency assessment"
                ),
                "is_second_opinion_recommended": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Referral to specialist or second opinion suggested"
                ),
                "second_opinion_evidence": types.Schema(
                    type=types.Type.STRING,
                    nullable=True,
                    description="Evidence for second opinion"
                ),
                "is_alternate_treatment_discussed": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Fallback/alternative treatment options discussed"
                ),
                "alternate_treatment_evidence": types.Schema(
                    type=types.Type.STRING,
                    nullable=True,
                    description="Evidence for alternate treatment"
                ),
                "critical_condition_detected": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Life-threatening condition (MI, stroke, cancer, sepsis)"
                ),
                "critical_condition_name": types.Schema(
                    type=types.Type.STRING,
                    nullable=True,
                    description="Name of critical condition if detected"
                ),
                "icd_validation": types.Schema(
                    type=types.Type.STRING,
                    description="Supporting ICD codes"
                ),
            },
            required=[
                "is_chronic", "chronic_evidence", "is_surgical", "surgical_evidence",
                "follow_up_urgency", "urgency_evidence", "is_second_opinion_recommended",
                "second_opinion_evidence", "is_alternate_treatment_discussed",
                "alternate_treatment_evidence", "critical_condition_detected",
                "critical_condition_name", "icd_validation"
            ]
        ),

        # 3. Diagnostic Needs
        "diagnostic_needs": types.Schema(
            type=types.Type.OBJECT,
            description="Diagnostic follow-up signals",
            properties={
                "has_ordered_tests": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="New tests ordered during this consultation"
                ),
                "ordered_tests": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Newly ordered test names"
                ),
                "needs_recurring_monitoring": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Conditions requiring periodic testing"
                ),
                "recurring_monitoring_type": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Types: HbA1c, Thyroid, Renal, Lipid, CBC, LFT, Other"
                ),
                "recurring_monitoring_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence including ICD-based reasoning"
                ),
            },
            required=[
                "has_ordered_tests", "ordered_tests", 
                "needs_recurring_monitoring", "recurring_monitoring_type",
                "recurring_monitoring_evidence"
            ]
        ),

        # 4. Medication Signals
        "medication_signals": types.Schema(
            type=types.Type.OBJECT,
            description="Medication management signals",
            properties={
                "total_medications_prescribed": types.Schema(
                    type=types.Type.INTEGER,
                    description="Total medication count"
                ),
                "max_duration_days": types.Schema(
                    type=types.Type.INTEGER,
                    nullable=True,
                    description="Longest prescription duration in days"
                ),
                "has_long_term_medications": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Any medication >30 days or marked as maintenance"
                ),
                "long_term_medication_names": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Long-term/maintenance medication names"
                ),
                "refill_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence for refill needs"
                ),
            },
            required=[
                "total_medications_prescribed", "max_duration_days",
                "has_long_term_medications", "long_term_medication_names", "refill_evidence"
            ]
        ),

        # 5. Nutritional Signals
        "nutritional_signals": types.Schema(
            type=types.Type.OBJECT,
            description="Nutritional counseling signals",
            properties={
                "has_metabolic_condition": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Diabetes, obesity, cardiac, or dyslipidemia present"
                ),
                "metabolic_conditions": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Conditions: diabetes, obesity, dyslipidemia, cardiac"
                ),
                "has_detailed_diet_instructions": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Specific diet instructions provided (not just generic advice)"
                ),
                "diet_instruction_summary": types.Schema(
                    type=types.Type.STRING,
                    nullable=True,
                    description="Brief diet instruction summary"
                ),
                "nutritional_counseling_mentioned": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Dietitian/nutritionist referral mentioned"
                ),
                "nutritional_counseling_potential": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Metabolic condition present but no diet instructions given"
                ),
                "icd_validation": types.Schema(
                    type=types.Type.STRING,
                    description="Supporting ICD codes"
                ),
            },
            required=[
                "has_metabolic_condition", "metabolic_conditions",
                "has_detailed_diet_instructions", "diet_instruction_summary",
                "nutritional_counseling_mentioned", "nutritional_counseling_potential", "icd_validation"
            ]
        ),

        # 6. Physiotherapy Signals
        "physiotherapy_signals": types.Schema(
            type=types.Type.OBJECT,
            description="Physiotherapy referral signals",
            properties={
                "has_musculoskeletal_condition": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Back/joint pain, arthritis, muscle/spine issues"
                ),
                "has_injury": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Fractures, sprains, trauma, post-accident"
                ),
                "physiotherapy_explicitly_mentioned": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Physiotherapy/PT explicitly mentioned"
                ),
                "physiotherapy_potential": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Possibility of physiotherapy discussed"
                ),
                "mobility_pain_keywords_present": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Mobility/pain keywords found"
                ),
                "physiotherapy_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence for physiotherapy need"
                ),
                "icd_validation": types.Schema(
                    type=types.Type.STRING,
                    description="Supporting ICD codes"
                ),
            },
            required=[
                "has_musculoskeletal_condition", "has_injury",
                "physiotherapy_explicitly_mentioned", "physiotherapy_potential", "mobility_pain_keywords_present",
                "physiotherapy_evidence", "icd_validation"
            ]
        ),

        # 7. Homecare Signals
        "homecare_signals": types.Schema(
            type=types.Type.OBJECT,
            description="Home care service signals",
            properties={
                "has_mobility_issues": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Difficulty walking, wheelchair, bedridden, needs assistance"
                ),
                "mobility_issue_type": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Types: difficulty_walking, bedridden, wheelchair, walker, homebound"
                ),
                "homecare_discussed": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Home nursing/care services discussed"
                ),
                "homecare_potential": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Elderly (>70) with chronic condition or mobility challenges"
                ),
                "mobility_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence for mobility issues"
                ),
            },
            required=[
                "has_mobility_issues", "mobility_issue_type",
                "homecare_discussed", "homecare_potential", "mobility_evidence"
            ]
        ),

        # 8. Sleep Signals
        "sleep_signals": types.Schema(
            type=types.Type.OBJECT,
            description="Sleep therapy signals",
            properties={
                "has_sleep_symptoms": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Snoring, apnea, insomnia, fatigue, daytime sleepiness"
                ),
                "sleep_symptoms": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Types: snoring, apnea, insomnia, fatigue, daytime_sleepiness"
                ),
                "has_obesity_or_hypertension": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="E66 (obesity) or I10-I15 (hypertension) present"
                ),
                "sleep_therapy_mentioned": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="CPAP, sleep study, polysomnography mentioned"
                ),
                "sleep_therapy_potential": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Sleep symptoms + obesity/HTN but no sleep therapy discussed"
                ),
                "sleep_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence for sleep therapy need"
                ),
                "icd_validation": types.Schema(
                    type=types.Type.STRING,
                    description="Supporting ICD codes"
                ),
            },
            required=[
                "has_sleep_symptoms", "sleep_symptoms", "has_obesity_or_hypertension",
                "sleep_therapy_mentioned", "sleep_therapy_potential", "sleep_evidence", "icd_validation"
            ]
        ),

        # 9. Rehabilitation Signals
        "rehabilitation_signals": types.Schema(
            type=types.Type.OBJECT,
            description="Rehabilitation needs signals",
            properties={
                "has_cardiac_event": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="MI, ischemic heart disease, CABG, stent, angioplasty"
                ),
                "cardiac_event_type": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Types: mi, ischemic, cabg, stent, angioplasty"
                ),
                "has_stroke": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Cerebrovascular event (I60-I64)"
                ),
                "has_orthopedic_surgery": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Joint replacement, fracture fixation, spine surgery"
                ),
                "orthopedic_surgery_type": types.Schema(
                    type=types.Type.STRING,
                    nullable=True,
                    description="Type of orthopedic surgery"
                ),
                "cardiac_rehab_mentioned": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Cardiac rehabilitation explicitly discussed"
                ),
                "cardiac_rehab_potential": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Cardiac event present but rehab not discussed"
                ),
                "general_rehab_mentioned": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="General rehabilitation explicitly discussed"
                ),
                "general_rehab_potential": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Stroke/surgery present but rehab not discussed"
                ),
                "rehab_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence for rehabilitation need"
                ),
                "icd_validation": types.Schema(
                    type=types.Type.STRING,
                    description="Supporting ICD codes"
                ),
            },
            required=[
                "has_cardiac_event", "cardiac_event_type", "has_stroke",
                "has_orthopedic_surgery", "orthopedic_surgery_type",
                "cardiac_rehab_mentioned", "cardiac_rehab_potential",
                "general_rehab_mentioned", "general_rehab_potential",
                "rehab_evidence", "icd_validation"
            ]
        ),

        # 10. Wellness Signals
        "wellness_signals": types.Schema(
            type=types.Type.OBJECT,
            description="Wellness program signals",
            properties={
                "has_lifestyle_disease": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Diabetes, obesity, hypertension, or dyslipidemia present"
                ),
                "lifestyle_diseases": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="List: diabetes, obesity, hypertension, dyslipidemia"
                ),
                "prevention_discussed": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Preventive measures or screening discussed"
                ),
                "lifestyle_modification_discussed": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Diet, exercise, smoking cessation discussed"
                ),
                "wellness_potential": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Lifestyle disease present but no prevention discussion"
                ),
                "wellness_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence for wellness need"
                ),
                "icd_validation": types.Schema(
                    type=types.Type.STRING,
                    description="Supporting ICD codes"
                ),
            },
            required=[
                "has_lifestyle_disease", "lifestyle_diseases",
                "prevention_discussed", "lifestyle_modification_discussed",
                "wellness_potential", "wellness_evidence", "icd_validation"
            ]
        ),

        # 11. Mental Health Signals (v1.2.0 - moved from excluded)
        "mental_health_signals": types.Schema(
            type=types.Type.OBJECT,
            description="Mental health support signals",
            properties={
                "anxiety_level": types.Schema(
                    type=types.Type.STRING,
                    description="None, Mild, Moderate, Severe"
                ),
                "anxiety_indicators": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Behavioral/verbal anxiety indicators"
                ),
                "depression_indicators_present": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Signs of depression (hopelessness, withdrawal, loss of interest)"
                ),
                "distress_indicators_present": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Acute distress observed (crying, panic, overwhelmed)"
                ),
                "mental_health_keywords_found": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Mental health treatment keywords in TREATMENT_PLAN"
                ),
                "mental_health_keywords": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Keywords: counseling, therapy, psychologist, psychiatrist, CBT"
                ),
                "mental_health_support_potential": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Anxiety/emotional concerns but no mental health support discussed"
                ),
                "mental_health_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence for mental health need"
                ),
            },
            required=[
                "anxiety_level", "anxiety_indicators", "depression_indicators_present",
                "distress_indicators_present", "mental_health_keywords_found",
                "mental_health_keywords", "mental_health_support_potential", "mental_health_evidence"
            ]
        ),

        # 12. Education Signals (v1.2.0 - moved from excluded)
        "education_signals": types.Schema(
            type=types.Type.OBJECT,
            description="Treatment education signals",
            properties={
                "is_new_diagnosis": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Newly diagnosed condition (first time, new onset)"
                ),
                "new_diagnosis_keywords": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Keywords: newly diagnosed, new onset, first time, just diagnosed"
                ),
                "understanding_barrier_present": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Patient shows difficulty understanding treatment"
                ),
                "understanding_barrier_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence of confusion or need for re-explanation"
                ),
                "education_discussed": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Patient education or training mentioned"
                ),
                "education_potential": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="New/complex diagnosis but no education discussion"
                ),
                "education_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence for education need"
                ),
            },
            required=[
                "is_new_diagnosis", "new_diagnosis_keywords",
                "understanding_barrier_present", "understanding_barrier_evidence",
                "education_discussed", "education_potential", "education_evidence"
            ]
        ),

        # 13. Competitor Signals (v1.3.0 - Retention Risk)
        "competitor_signals": types.Schema(
            type=types.Type.OBJECT,
            description="Competitor consideration signals",
            properties={
                "competitor_intent_detected": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Patient considering other healthcare providers"
                ),
                "competitor_names_mentioned": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Other hospitals/clinics/doctors mentioned"
                ),
                "competitor_reason": types.Schema(
                    type=types.Type.STRING,
                    nullable=True,
                    description="Reason: cost, quality, convenience, recommendation, dissatisfaction"
                ),
                "competitor_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence of competitor consideration"
                ),
            },
            required=["competitor_intent_detected", "competitor_names_mentioned", "competitor_reason", "competitor_evidence"]
        ),

        # 14. Access/Logistics Signals (v1.3.0 - Retention Risk)
        "access_logistics_signals": types.Schema(
            type=types.Type.OBJECT,
            description="Access and logistics barrier signals",
            properties={
                "access_barriers_detected": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Patient mentions difficulty accessing care"
                ),
                "access_barrier_types": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Types: distance, transportation, waiting_time, scheduling, parking, other"
                ),
                "access_severity": types.Schema(
                    type=types.Type.STRING,
                    description="None, Mild, Moderate, Severe"
                ),
                "access_evidence": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Evidence of access barriers"
                ),
            },
            required=["access_barriers_detected", "access_barrier_types", "access_severity", "access_evidence"]
        ),
    },
    required=[
        "patient_signals",
        "clinical_severity_signals",
        "diagnostic_needs",
        "medication_signals",
        "nutritional_signals",
        "physiotherapy_signals",
        "homecare_signals",
        "sleep_signals",
        "rehabilitation_signals",
        "wellness_signals",
        "mental_health_signals",
        "education_signals",
        "competitor_signals",
        "access_logistics_signals"
    ]
)


# ============================================================================
# User Prompt Templates
# ============================================================================

def generate_consultation_insights_prompt(
    transcript: str,
    diagnosis_segment: Optional[Dict[str, Any]] = None,
    prescription_segment: Optional[Dict[str, Any]] = None,
    investigations_segment: Optional[Dict[str, Any]] = None,
    follow_up_segment: Optional[Dict[str, Any]] = None,
    treatment_plan_segment: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate user prompt for consultation insights extraction.

    This is a second-pass extraction that uses previously extracted segments
    as context for ICD code cross-validation.

    Args:
        transcript: Full consultation transcript
        diagnosis_segment: Previously extracted DIAGNOSIS segment (with ICD codes)
        prescription_segment: Previously extracted PRESCRIPTION segment
        investigations_segment: Previously extracted INVESTIGATIONS segment
        follow_up_segment: Previously extracted FOLLOW_UP segment
        treatment_plan_segment: Previously extracted TREATMENT_PLAN segment

    Returns:
        Formatted user prompt with context
    """
    import json

    # Format segments for prompt (handle None gracefully)
    def format_segment(segment: Optional[Dict], default: str = "Not available") -> str:
        if segment is None:
            return default
        return json.dumps(segment, indent=2, default=str)

    return f"""Analyze this medical consultation and extract clinical insights for assessment systems.

## Original Transcript
{transcript}

## Previously Extracted Segments (for ICD cross-validation)

### DIAGNOSIS (ICD-10 Codes)
{format_segment(diagnosis_segment)}

### PRESCRIPTION
{format_segment(prescription_segment)}

### INVESTIGATIONS
{format_segment(investigations_segment)}

### FOLLOW_UP
{format_segment(follow_up_segment)}

### TREATMENT_PLAN
{format_segment(treatment_plan_segment)}

## Your Task

Extract clinical signals for:
1. Clinical Severity Assessment (stakes of non-adherence)
2. Other Clinical Needs (diagnostic follow-up, recurring monitoring, refills)
3. Allied Health Needs (nutritional, physiotherapy, homecare, sleep, rehabilitation, wellness)

**Important:**
- Cross-validate your signals against the extracted ICD codes
- If you coded E11.65 (diabetes with CKD), your signals should reflect chronic=true AND renal monitoring needs
- Include icd_validation explanations showing how ICD codes support your assessments
- Be conservative with boolean flags - only TRUE if clear evidence exists"""


def generate_consultation_insights_standalone_prompt(transcript: str) -> str:
    """
    Generate user prompt for standalone consultation insights extraction.

    Use this when extracted segments are not available. The LLM will infer
    ICD codes from the transcript for self-validation.

    Args:
        transcript: Full consultation transcript

    Returns:
        Formatted user prompt without segment context
    """
    return f"""Analyze this medical consultation and extract clinical insights for assessment systems.

## Transcript
{transcript}

## Your Task

Extract clinical signals for:
1. Clinical Severity Assessment (stakes of non-adherence)
2. Other Clinical Needs (diagnostic follow-up, recurring monitoring, refills)
3. Allied Health Needs (nutritional, physiotherapy, homecare, sleep, rehabilitation, wellness)

**Important:**
- Infer likely ICD-10 codes from the conditions discussed
- Use these inferred codes in your icd_validation explanations
- Be conservative with boolean flags - only TRUE if clear evidence exists
- Include evidence strings with transcript quotes"""


# ============================================================================
# Helper Functions
# ============================================================================

def get_consultation_insights_signal_groups() -> list[str]:
    """Get list of all signal group names in the schema (v1.3.0 - includes all 14 groups)."""
    return [
        "patient_signals",
        "clinical_severity_signals",
        "diagnostic_needs",
        "medication_signals",
        "nutritional_signals",
        "physiotherapy_signals",
        "homecare_signals",
        "sleep_signals",
        "rehabilitation_signals",
        "wellness_signals",
        "mental_health_signals",
        "education_signals",
        "competitor_signals",
        "access_logistics_signals"
    ]


def _get_icd_score(icd_code: str) -> int:
    """
    Calculate severity score for a single ICD-10 code.

    Args:
        icd_code: ICD-10 code string (e.g., "E11.65", "I21.0")

    Returns:
        Severity score (1-4)
    """
    if not icd_code:
        return 0

    code = icd_code.upper().strip()

    # Try progressively shorter prefixes
    for length in [4, 3, 2, 1]:
        prefix = code[:length]
        if prefix in ICD_CHAPTER_SCORES:
            return ICD_CHAPTER_SCORES[prefix]

    return 1  # Default score


def _check_critical_icd(icd_codes: List[str]) -> Tuple[bool, Optional[str]]:
    """
    Check if any ICD code triggers critical override.

    Args:
        icd_codes: List of ICD-10 codes

    Returns:
        Tuple of (is_critical, critical_code)
    """
    for code in icd_codes:
        if not code:
            continue
        code_upper = code.upper().strip()
        for prefix in ICD_CRITICAL_PREFIXES:
            if code_upper.startswith(prefix):
                return True, code
    return False, None


def _calculate_modifier_score(
    is_chronic: bool,
    polypharmacy_count: int,
    follow_up_urgency: str,
    treatment_duration_days: Optional[int],
    is_second_opinion: bool,
    is_alternate_procedure: bool
) -> int:
    """
    Calculate modifier score from clinical factors.

    Scoring:
    - is_chronic: +1
    - polypharmacy (>5 meds): +1
    - follow_up urgency: routine=0, soon=+1, urgent=+2
    - treatment duration >90 days: +1
    - second opinion recommended: +1
    - alternate procedure discussed: +1

    Returns:
        Total modifier score (0-7)
    """
    score = 0

    if is_chronic:
        score += 1

    if polypharmacy_count > 5:
        score += 1

    urgency_scores = {"routine": 0, "soon": 1, "urgent": 2}
    score += urgency_scores.get(follow_up_urgency.lower(), 0)

    if treatment_duration_days and treatment_duration_days > 90:
        score += 1

    if is_second_opinion:
        score += 1

    if is_alternate_procedure:
        score += 1

    return score


def map_insights_to_clinical_severity(
    insights: Dict[str, Any],
    icd_codes: Optional[List[str]] = None,
    specialty: Optional[str] = None
) -> Dict[str, Any]:
    """
    Map consultation insights to clinical severity with FULL calculation.

    Implements the same scoring logic as clinical_severity_service.py:
    - ICD code scoring (highest score from all codes)
    - Specialty scoring
    - Surgical boost (+2)
    - Modifier scores (chronic, polypharmacy, urgency, duration, opinions)
    - Critical override check
    - Final severity: LOW (0-4), MEDIUM (5-8), HIGH (9+)

    Args:
        insights: Extracted consultation insights
        icd_codes: List of ICD-10 codes from DIAGNOSIS segment
        specialty: Doctor specialty (for specialty scoring)

    Returns:
        Dict with severity_level, component scores, and input fields
    """
    severity_signals = insights.get("clinical_severity_signals", {})
    medication = insights.get("medication_signals", {})

    # Extract input fields
    is_chronic = severity_signals.get("is_chronic", False)
    is_surgical = severity_signals.get("is_surgical", False)
    follow_up_urgency = severity_signals.get("follow_up_urgency", "routine")
    is_second_opinion = severity_signals.get("is_second_opinion_recommended", False)
    is_alternate_procedure = severity_signals.get("is_alternate_treatment_discussed", False)
    critical_condition = severity_signals.get("critical_condition_detected", False)
    _raw_duration = medication.get("max_duration_days")
    try:
        treatment_duration_days = int(_raw_duration) if _raw_duration is not None and str(_raw_duration).lower() != "null" else None
    except (ValueError, TypeError):
        logger.warning(f"[SEVERITY] Could not parse max_duration_days: {_raw_duration!r}, defaulting to None")
        treatment_duration_days = None
    _raw_poly = medication.get("total_medications_prescribed", 0)
    try:
        polypharmacy_count = int(_raw_poly) if _raw_poly is not None and str(_raw_poly).lower() != "null" else 0
    except (ValueError, TypeError):
        logger.warning(f"[SEVERITY] Could not parse total_medications_prescribed: {_raw_poly!r}, defaulting to 0")
        polypharmacy_count = 0

    # Get ICD codes from insights if not provided
    if icd_codes is None:
        icd_codes = []

    # Calculate ICD score (use highest score from all codes)
    icd_score = 0
    for code in icd_codes:
        code_score = _get_icd_score(code)
        icd_score = max(icd_score, code_score)

    # Check for critical ICD override
    is_critical, critical_code = _check_critical_icd(icd_codes)

    # Specialty score
    specialty_score = 0
    if specialty:
        specialty_lower = specialty.lower().replace(" ", "_").replace("-", "_")
        specialty_score = SPECIALTY_SCORES.get(specialty_lower, 1)

    # Surgical boost (3 points for surgical intervention)
    surgical_boost = 3 if is_surgical else 0

    # Modifier score
    modifier_score = _calculate_modifier_score(
        is_chronic=is_chronic,
        polypharmacy_count=polypharmacy_count,
        follow_up_urgency=follow_up_urgency,
        treatment_duration_days=treatment_duration_days,
        is_second_opinion=is_second_opinion,
        is_alternate_procedure=is_alternate_procedure
    )

    # Base score = max of ICD or specialty (take the higher stakes indicator)
    base_score = max(icd_score, specialty_score)

    # Total score = base + surgical boost + modifiers
    total_score = base_score + surgical_boost + modifier_score

    # Critical override: immediate HIGH
    # Thresholds adjusted for MAX(icd, specialty) formula (scores ~2 points lower than SUM)
    if is_critical or critical_condition:
        severity_level = SeverityLevel.HIGH
    elif total_score >= 7:
        severity_level = SeverityLevel.HIGH
    elif total_score >= 3:
        severity_level = SeverityLevel.MEDIUM
    else:
        severity_level = SeverityLevel.LOW

    return {
        # Input fields
        "is_chronic": is_chronic,
        "is_surgical": is_surgical,
        "follow_up_urgency": follow_up_urgency,
        "is_second_opinion": is_second_opinion,
        "is_alternate_procedure": is_alternate_procedure,
        "treatment_duration_days": treatment_duration_days,
        "critical_condition": critical_condition or is_critical,
        "critical_code": critical_code,

        # Scoring components
        "icd_score": icd_score,
        "specialty_score": specialty_score,
        "base_score": base_score,  # max(icd, specialty)
        "surgical_boost": surgical_boost,
        "modifier_score": modifier_score,
        "total_score": total_score,

        # Final result
        "severity_level": severity_level.value,

        # Reasons
        "severity_reasons": _build_severity_reasons(
            icd_score, specialty, specialty_score, is_surgical,
            is_chronic, polypharmacy_count, follow_up_urgency,
            treatment_duration_days, is_second_opinion, is_alternate_procedure,
            is_critical, critical_code, severity_level
        )
    }


def _build_severity_reasons(
    icd_score: int,
    specialty: Optional[str],
    specialty_score: int,
    is_surgical: bool,
    is_chronic: bool,
    polypharmacy_count: int,
    follow_up_urgency: str,
    treatment_duration_days: Optional[int],
    is_second_opinion: bool,
    is_alternate_procedure: bool,
    is_critical: bool,
    critical_code: Optional[str],
    severity_level: SeverityLevel
) -> List[str]:
    """Build human-readable severity reasons."""
    reasons = []

    if is_critical and critical_code:
        reasons.append(f"Critical ICD code {critical_code} triggers HIGH severity")

    if icd_score >= 3:
        reasons.append("High-severity diagnosis codes present")
    elif icd_score >= 2:
        reasons.append("Moderate-severity diagnosis codes present")

    if specialty and specialty_score >= 3:
        reasons.append(f"High-stakes specialty: {specialty}")
    elif specialty and specialty_score >= 2:
        reasons.append(f"Moderate-stakes specialty: {specialty}")

    if is_surgical:
        reasons.append("Surgical intervention required")

    if is_chronic:
        reasons.append("Chronic condition requiring ongoing management")

    if polypharmacy_count > 5:
        reasons.append(f"Polypharmacy: {polypharmacy_count} medications")

    if follow_up_urgency == "urgent":
        reasons.append("Urgent follow-up required")
    elif follow_up_urgency == "soon":
        reasons.append("Priority follow-up within 1-2 weeks")

    if treatment_duration_days and treatment_duration_days > 90:
        reasons.append(f"Extended treatment: {treatment_duration_days} days")

    if is_second_opinion:
        reasons.append("Specialist consultation recommended")

    if is_alternate_procedure:
        reasons.append("Alternative treatment options discussed")

    if not reasons:
        reasons.append(f"Standard {severity_level.value} severity assessment")

    return reasons


def map_insights_to_other_clinical_needs(insights: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map consultation insights to Other Clinical Needs with FULL priority calculation.

    Implements the same priority logic as other_clinical_needs_service.py:
    - HIGH: 3 flags TRUE, OR (recurring + refill both TRUE)
    - MEDIUM: 2 flags TRUE, OR recurring alone TRUE
    - LOW: 1 flag TRUE
    - NONE: 0 flags TRUE

    Args:
        insights: Extracted consultation insights

    Returns:
        Dict with indicators, priority_level, and reasons
    """
    diagnostic = insights.get("diagnostic_needs", {})
    medication = insights.get("medication_signals", {})

    # Calculate boolean indicators
    is_followup_diagnostics = diagnostic.get("has_ordered_tests", False)
    is_recurring_diagnostics = diagnostic.get("needs_recurring_monitoring", False)
    is_rx_refill = medication.get("has_long_term_medications", False)

    # Count true indicators
    true_count = sum([is_followup_diagnostics, is_recurring_diagnostics, is_rx_refill])

    # Calculate priority level
    if true_count >= 3:
        priority_level = PriorityLevel.HIGH
    elif is_recurring_diagnostics and is_rx_refill:
        # Special case: recurring + refill = HIGH (chronic patient needing ongoing care)
        priority_level = PriorityLevel.HIGH
    elif true_count == 2:
        priority_level = PriorityLevel.MEDIUM
    elif is_recurring_diagnostics:
        # Recurring alone = MEDIUM (chronic monitoring needs)
        priority_level = PriorityLevel.MEDIUM
    elif true_count == 1:
        priority_level = PriorityLevel.LOW
    else:
        priority_level = PriorityLevel.NONE

    # Build reasons
    reasons = []
    if is_followup_diagnostics:
        ordered_tests = diagnostic.get("ordered_tests", [])        
        reasons.append(f"Follow-up diagnostics ordered: {', '.join(ordered_tests[:3])}")
    if is_recurring_diagnostics:
        monitoring_types = diagnostic.get("recurring_monitoring_type", [])
        reasons.append(f"Recurring monitoring needed: {', '.join(monitoring_types)}")
    if is_rx_refill:
        med_names = medication.get("long_term_medication_names", [])
        reasons.append(f"Medication refill needs: {', '.join(med_names[:3])}")

    return {
        # Indicators
        "is_followup_diagnostics": is_followup_diagnostics,
        "is_recurring_diagnostics": is_recurring_diagnostics,
        "is_rx_refill": is_rx_refill,

        # Priority calculation
        "true_count": true_count,
        "priority_level": priority_level.value,

        # Reasons
        "other_clinical_needs_reasons": reasons if reasons else ["No clinical needs identified"]
    }


def map_insights_to_allied_health_needs(
    insights: Dict[str, Any],
    is_chronic: bool = False,
    patient_age: Optional[int] = None
) -> Dict[str, Any]:
    """
    Map consultation insights to Allied Health Needs with ALL 9 indicators and priority.

    Implements the same priority logic as allied_health_needs_service.py:
    - HIGH: 4+ indicators TRUE, OR (is_mental_health + any other TRUE)
    - MEDIUM: 2-3 indicators TRUE
    - LOW: 1 indicator TRUE
    - NONE: 0 indicators TRUE

    Args:
        insights: Extracted consultation insights
        is_chronic: Whether patient has chronic condition (from clinical severity)
        patient_age: Patient age in years

    Returns:
        Dict with all 9 indicators, priority_level, and reasons
    """
    nutritional = insights.get("nutritional_signals", {})
    physio = insights.get("physiotherapy_signals", {})
    homecare = insights.get("homecare_signals", {})
    sleep = insights.get("sleep_signals", {})
    rehab = insights.get("rehabilitation_signals", {})
    wellness = insights.get("wellness_signals", {})
    mental = insights.get("mental_health_signals", {})
    education = insights.get("education_signals", {})
    patient = insights.get("patient_signals", {})

    # Use provided age or extracted age (cast to int - Gemini may return string or "unknown")
    _raw_age = patient_age or patient.get("estimated_age_years")
    try:
        age = int(_raw_age) if _raw_age is not None else None
    except (ValueError, TypeError):
        logger.warning(f"[ALLIED_HEALTH] Non-numeric age value '{_raw_age}', treating as None")
        age = None

    # =========================================================================
    # Calculate all 9 boolean indicators (with potential fields)
    # =========================================================================

    # 1. Mental Health - explicit OR potential
    is_mental_health_explicit = (
        mental.get("anxiety_level", "None") == "Severe" or
        mental.get("depression_indicators_present", False) or
        mental.get("distress_indicators_present", False) or
        mental.get("mental_health_keywords_found", False)
    )
    is_mental_health_potential = mental.get("mental_health_support_potential", False)
    is_mental_health = is_mental_health_explicit or is_mental_health_potential

    # 2. Nutritional Health - explicit OR potential
    is_nutritional_health_explicit = (
        nutritional.get("has_metabolic_condition", False) and
        nutritional.get("has_detailed_diet_instructions", False)
    )
    is_nutritional_health_potential = nutritional.get("nutritional_counseling_potential", False)
    is_nutritional_health = is_nutritional_health_explicit or is_nutritional_health_potential

    # 3. Physiotherapy - explicit OR potential (with diagnosis guardrail)
    is_physiotherapy_explicit = (
        (physio.get("has_musculoskeletal_condition", False) or physio.get("has_injury", False)) and
        physio.get("physiotherapy_explicitly_mentioned", False)
    )
    is_physiotherapy_potential = physio.get("physiotherapy_potential", False)

    # GUARDRAIL: Suppress physiotherapy_potential when diagnosis is inconclusive
    # Physiotherapy is a treatment, not a diagnostic tool - premature when root cause unknown
    if is_physiotherapy_potential and not is_physiotherapy_explicit:
        diagnostics = insights.get("diagnostic_needs", {})
        severity = insights.get("clinical_severity_signals", {})

        # Check for signs of inconclusive diagnosis:
        # 1. Diagnostic tests ordered (investigation in progress)
        has_pending_diagnostics = diagnostics.get("has_ordered_tests", False)

        # 2. No confirmed musculoskeletal ICD code (empty/None/generic pain)
        icd_validation = physio.get("icd_validation", "") or ""
        has_confirmed_msk_icd = bool(icd_validation.strip()) and icd_validation.lower() not in ("none", "n/a", "")

        # 3. Second opinion recommended (uncertainty about diagnosis)
        needs_second_opinion = severity.get("is_second_opinion_recommended", False)

        # Suppress potential if: diagnostics pending AND no confirmed ICD
        # OR if second opinion is recommended (indicates diagnostic uncertainty)
        diagnosis_inconclusive = (
            (has_pending_diagnostics and not has_confirmed_msk_icd) or
            needs_second_opinion
        )

        if diagnosis_inconclusive:
            logger.info(
                f"[PHYSIO_GUARDRAIL] Suppressing physiotherapy_potential - diagnosis inconclusive "
                f"(pending_diagnostics={has_pending_diagnostics}, confirmed_msk_icd={has_confirmed_msk_icd}, "
                f"second_opinion={needs_second_opinion})"
            )
            is_physiotherapy_potential = False  # Suppress - wait for diagnosis confirmation

    is_physiotherapy = is_physiotherapy_explicit or is_physiotherapy_potential

    # 4. Homecare - explicit OR potential
    is_homecare_explicit = (
        (age is not None and age > 70) and
        is_chronic and
        homecare.get("has_mobility_issues", False)
    )
    is_homecare_potential = homecare.get("homecare_potential", False)
    is_homecare = is_homecare_explicit or is_homecare_potential

    # 5. Sleep Therapy - explicit OR potential (with diagnosis guardrail)
    is_sleep_therapy_explicit = (
        sleep.get("has_sleep_symptoms", False) and
        sleep.get("has_obesity_or_hypertension", False) and
        sleep.get("sleep_therapy_mentioned", False)
    )
    is_sleep_therapy_potential = sleep.get("sleep_therapy_potential", False)

    # GUARDRAIL: Suppress sleep_therapy_potential when diagnosis is pending
    # Sleep symptoms (fatigue, tiredness) could be thyroid, anemia, depression, etc.
    if is_sleep_therapy_potential and not is_sleep_therapy_explicit:
        diagnostics = insights.get("diagnostic_needs", {})
        severity = insights.get("clinical_severity_signals", {})

        has_pending_diagnostics = diagnostics.get("has_ordered_tests", False)
        needs_second_opinion = severity.get("is_second_opinion_recommended", False)

        # For sleep, check if tests ordered could explain sleep symptoms
        # (e.g., thyroid panel, CBC, metabolic panel)
        if has_pending_diagnostics or needs_second_opinion:
            logger.info(
                f"[SLEEP_GUARDRAIL] Suppressing sleep_therapy_potential - diagnosis pending "
                f"(pending_diagnostics={has_pending_diagnostics}, second_opinion={needs_second_opinion})"
            )
            is_sleep_therapy_potential = False  # Suppress - investigate other causes first

    is_sleep_therapy = is_sleep_therapy_explicit or is_sleep_therapy_potential

    # 6. Cardiac Rehabilitation - explicit OR potential
    is_rehab_cardiac_explicit = (
        rehab.get("has_cardiac_event", False) and
        rehab.get("cardiac_rehab_mentioned", False)
    )
    is_rehab_cardiac_potential = rehab.get("cardiac_rehab_potential", False)
    is_rehab_cardiac = is_rehab_cardiac_explicit or is_rehab_cardiac_potential

    # 7. Common Rehabilitation (mutually exclusive with cardiac) - explicit OR potential
    is_rehab_common_explicit = (
        not rehab.get("has_cardiac_event", False) and
        (rehab.get("has_stroke", False) or rehab.get("has_orthopedic_surgery", False)) and
        rehab.get("general_rehab_mentioned", False)
    )
    is_rehab_common_potential = rehab.get("general_rehab_potential", False)
    is_rehab_common = is_rehab_common_explicit or is_rehab_common_potential

    # 8. Treatment Education - explicit OR potential
    is_treatment_education_explicit = (
        education.get("is_new_diagnosis", False) and
        education.get("understanding_barrier_present", False)
    )
    is_treatment_education_potential = education.get("education_potential", False)
    is_treatment_education = is_treatment_education_explicit or is_treatment_education_potential

    # 9. Wellness - explicit OR potential
    is_wellness_explicit = (
        wellness.get("has_lifestyle_disease", False) and
        wellness.get("prevention_discussed", False)
    )
    is_wellness_potential = wellness.get("wellness_potential", False)
    is_wellness = is_wellness_explicit or is_wellness_potential

    # =========================================================================
    # Calculate priority level
    # =========================================================================
    indicators = [
        is_mental_health, is_nutritional_health, is_physiotherapy,
        is_homecare, is_sleep_therapy, is_rehab_cardiac,
        is_rehab_common, is_treatment_education, is_wellness
    ]
    true_count = sum(indicators)

    # Priority calculation
    if true_count >= 4:
        priority_level = PriorityLevel.HIGH
    elif is_mental_health and true_count >= 2:
        # Mental health + any other = HIGH (mental health elevates priority)
        priority_level = PriorityLevel.HIGH
    elif true_count >= 2:
        priority_level = PriorityLevel.MEDIUM
    elif true_count == 1:
        priority_level = PriorityLevel.LOW
    else:
        priority_level = PriorityLevel.NONE

    # =========================================================================
    # Build reasons for each indicator
    # =========================================================================
    reasons = {
        "mental_health_reasons": [],
        "nutritional_health_reasons": [],
        "physiotherapy_reasons": [],
        "homecare_reasons": [],
        "sleep_therapy_reasons": [],
        "rehab_cardiac_reasons": [],
        "rehab_common_reasons": [],
        "treatment_education_reasons": [],
        "wellness_reasons": []
    }

    if is_mental_health:
        if is_mental_health_explicit:
            if mental.get("anxiety_level") == "Severe":
                reasons["mental_health_reasons"].append("Severe anxiety level detected")
            if mental.get("depression_indicators_present"):
                reasons["mental_health_reasons"].append("Depression indicators present")
            if mental.get("distress_indicators_present"):
                reasons["mental_health_reasons"].append("Acute distress observed")
            if mental.get("mental_health_keywords_found"):
                keywords = mental.get("mental_health_keywords", [])
                reasons["mental_health_reasons"].append(f"Mental health keywords: {', '.join(keywords[:3])}")
        elif is_mental_health_potential:
            reasons["mental_health_reasons"].append("[POTENTIAL] Mild/moderate anxiety or emotional concerns - may benefit from mental health support")

    if is_nutritional_health:
        if is_nutritional_health_explicit:
            conditions = nutritional.get("metabolic_conditions", [])
            reasons["nutritional_health_reasons"].append(f"Metabolic conditions: {', '.join(conditions)}")
            reasons["nutritional_health_reasons"].append("Detailed diet instructions provided")
        elif is_nutritional_health_potential:
            conditions = nutritional.get("metabolic_conditions", [])
            reasons["nutritional_health_reasons"].append(f"[POTENTIAL] Metabolic conditions ({', '.join(conditions)}) - may benefit from nutritional counseling")

    if is_physiotherapy:
        if is_physiotherapy_explicit:
            if physio.get("has_musculoskeletal_condition"):
                reasons["physiotherapy_reasons"].append("Musculoskeletal condition present")
            if physio.get("has_injury"):
                reasons["physiotherapy_reasons"].append("Injury/trauma present")
            reasons["physiotherapy_reasons"].append("Physiotherapy explicitly mentioned in treatment plan")
        elif is_physiotherapy_potential:
            reasons["physiotherapy_reasons"].append("[POTENTIAL] Musculoskeletal/injury condition - may benefit from physiotherapy")

    if is_homecare:
        if is_homecare_explicit:
            reasons["homecare_reasons"].append(f"Patient age: {age} years (>70)")
            reasons["homecare_reasons"].append("Chronic condition present")
            mobility_types = homecare.get("mobility_issue_type", [])
            reasons["homecare_reasons"].append(f"Mobility issues: {', '.join(mobility_types)}")
        elif is_homecare_potential:
            reasons["homecare_reasons"].append("[POTENTIAL] Elderly/chronic patient - may benefit from home care services")

    if is_sleep_therapy:
        if is_sleep_therapy_explicit:
            symptoms = sleep.get("sleep_symptoms", [])
            reasons["sleep_therapy_reasons"].append(f"Sleep symptoms: {', '.join(symptoms)}")
            reasons["sleep_therapy_reasons"].append("Sleep therapy explicitly discussed")
        elif is_sleep_therapy_potential:
            symptoms = sleep.get("sleep_symptoms", [])
            reasons["sleep_therapy_reasons"].append(f"[POTENTIAL] Sleep symptoms ({', '.join(symptoms)}) with obesity/HTN - may benefit from sleep evaluation")

    if is_rehab_cardiac:
        if is_rehab_cardiac_explicit:
            event_types = rehab.get("cardiac_event_type", [])
            reasons["rehab_cardiac_reasons"].append(f"Cardiac event: {', '.join(event_types)}")
            reasons["rehab_cardiac_reasons"].append("Cardiac rehabilitation explicitly discussed")
        elif is_rehab_cardiac_potential:
            event_types = rehab.get("cardiac_event_type", [])
            reasons["rehab_cardiac_reasons"].append(f"[POTENTIAL] Cardiac event ({', '.join(event_types)}) - may benefit from cardiac rehabilitation")

    if is_rehab_common:
        if is_rehab_common_explicit:
            if rehab.get("has_stroke"):
                reasons["rehab_common_reasons"].append("Stroke requiring rehabilitation")
            if rehab.get("has_orthopedic_surgery"):
                surgery_type = rehab.get("orthopedic_surgery_type", "unspecified")
                reasons["rehab_common_reasons"].append(f"Orthopedic surgery: {surgery_type}")
            reasons["rehab_common_reasons"].append("General rehabilitation explicitly discussed")
        elif is_rehab_common_potential:
            reasons["rehab_common_reasons"].append("[POTENTIAL] Post-stroke/surgery - may benefit from rehabilitation services")

    if is_treatment_education:
        if is_treatment_education_explicit:
            keywords = education.get("new_diagnosis_keywords", [])
            reasons["treatment_education_reasons"].append(f"New diagnosis: {', '.join(keywords[:2])}")
            reasons["treatment_education_reasons"].append("Understanding barrier identified")
        elif is_treatment_education_potential:
            reasons["treatment_education_reasons"].append("[POTENTIAL] New/complex diagnosis - may benefit from patient education")

    if is_wellness:
        if is_wellness_explicit:
            diseases = wellness.get("lifestyle_diseases", [])
            reasons["wellness_reasons"].append(f"Lifestyle diseases: {', '.join(diseases)}")
            reasons["wellness_reasons"].append("Prevention measures discussed")
        elif is_wellness_potential:
            diseases = wellness.get("lifestyle_diseases", [])
            reasons["wellness_reasons"].append(f"[POTENTIAL] Lifestyle diseases ({', '.join(diseases)}) - may benefit from wellness program")

    return {
        # All 9 indicators
        "is_mental_health": is_mental_health,
        "is_nutritional_health": is_nutritional_health,
        "is_physiotherapy": is_physiotherapy,
        "is_homecare": is_homecare,
        "is_sleep_therapy": is_sleep_therapy,
        "is_rehab_cardiac": is_rehab_cardiac,
        "is_rehab_common": is_rehab_common,
        "is_treatment_education": is_treatment_education,
        "is_wellness": is_wellness,

        # Priority calculation
        "true_count": true_count,
        "priority_level": priority_level.value,

        # All reasons by indicator
        **reasons
    }


def check_missed_allied_health_opportunities(
    insights: Dict[str, Any],
    is_chronic: bool = False,
    patient_age: Optional[int] = None,
    threshold: int = 2
) -> Dict[str, Any]:
    """
    Check if there are missed allied health opportunities where potential
    needs exist but were not explicitly addressed in the consultation.

    This helps identify consultations where proactive referrals might be beneficial.

    Args:
        insights: Extracted consultation insights
        is_chronic: Whether patient has chronic condition
        patient_age: Patient age in years
        threshold: Minimum number of missed opportunities to flag (default: 2)

    Returns:
        Dict with:
        - has_missed_opportunities: TRUE if missed count >= threshold
        - missed_count: Number of potential-only indicators
        - missed_indicators: List of indicator names that were missed
        - missed_details: Details for each missed indicator
    """
    nutritional = insights.get("nutritional_signals", {})
    physio = insights.get("physiotherapy_signals", {})
    homecare = insights.get("homecare_signals", {})
    sleep = insights.get("sleep_signals", {})
    rehab = insights.get("rehabilitation_signals", {})
    wellness = insights.get("wellness_signals", {})
    mental = insights.get("mental_health_signals", {})
    education = insights.get("education_signals", {})
    patient = insights.get("patient_signals", {})

    _raw_age = patient_age or patient.get("estimated_age_years")
    try:
        age = int(_raw_age) if _raw_age is not None else None
    except (ValueError, TypeError):
        logger.warning(f"[ALLIED_HEALTH] Non-numeric age value '{_raw_age}', treating as None")
        age = None

    missed_indicators = []
    missed_details = {}

    # 1. Mental Health - check if potential but not explicit
    is_mental_health_explicit = (
        mental.get("anxiety_level", "None") == "Severe" or
        mental.get("depression_indicators_present", False) or
        mental.get("distress_indicators_present", False) or
        mental.get("mental_health_keywords_found", False)
    )
    is_mental_health_potential = mental.get("mental_health_support_potential", False)
    if is_mental_health_potential and not is_mental_health_explicit:
        missed_indicators.append("mental_health")
        missed_details["mental_health"] = "Mild/moderate anxiety detected but no mental health support discussed"

    # 2. Nutritional Health
    is_nutritional_health_explicit = (
        nutritional.get("has_metabolic_condition", False) and
        nutritional.get("has_detailed_diet_instructions", False)
    )
    is_nutritional_health_potential = nutritional.get("nutritional_counseling_potential", False)
    if is_nutritional_health_potential and not is_nutritional_health_explicit:
        missed_indicators.append("nutritional_health")
        conditions = nutritional.get("metabolic_conditions", [])
        missed_details["nutritional_health"] = f"Metabolic conditions ({', '.join(conditions)}) but no detailed diet counseling"

    # 3. Physiotherapy (with diagnosis guardrail - same as map_insights_to_allied_health_needs)
    is_physiotherapy_explicit = (
        (physio.get("has_musculoskeletal_condition", False) or physio.get("has_injury", False)) and
        physio.get("physiotherapy_explicitly_mentioned", False)
    )
    is_physiotherapy_potential = physio.get("physiotherapy_potential", False)

    # GUARDRAIL: Don't flag as missed opportunity if diagnosis is inconclusive
    if is_physiotherapy_potential and not is_physiotherapy_explicit:
        diagnostics = insights.get("diagnostic_needs", {})
        severity = insights.get("clinical_severity_signals", {})

        has_pending_diagnostics = diagnostics.get("has_ordered_tests", False)
        icd_validation = physio.get("icd_validation", "") or ""
        has_confirmed_msk_icd = bool(icd_validation.strip()) and icd_validation.lower() not in ("none", "n/a", "")
        needs_second_opinion = severity.get("is_second_opinion_recommended", False)

        diagnosis_inconclusive = (
            (has_pending_diagnostics and not has_confirmed_msk_icd) or
            needs_second_opinion
        )

        if not diagnosis_inconclusive:
            # Only flag as missed if diagnosis is confirmed
            missed_indicators.append("physiotherapy")
            missed_details["physiotherapy"] = "Musculoskeletal/injury condition but physiotherapy not explicitly mentioned"

    # 4. Homecare
    is_homecare_explicit = (
        (age is not None and age > 70) and
        is_chronic and
        homecare.get("has_mobility_issues", False)
    )
    is_homecare_potential = homecare.get("homecare_potential", False)
    if is_homecare_potential and not is_homecare_explicit:
        missed_indicators.append("homecare")
        missed_details["homecare"] = "Elderly/chronic patient may benefit from home care services"

    # 5. Sleep Therapy (with diagnosis guardrail - same as map_insights_to_allied_health_needs)
    is_sleep_therapy_explicit = (
        sleep.get("has_sleep_symptoms", False) and
        sleep.get("has_obesity_or_hypertension", False) and
        sleep.get("sleep_therapy_mentioned", False)
    )
    is_sleep_therapy_potential = sleep.get("sleep_therapy_potential", False)

    # GUARDRAIL: Don't flag as missed opportunity if diagnosis is pending
    if is_sleep_therapy_potential and not is_sleep_therapy_explicit:
        diagnostics = insights.get("diagnostic_needs", {})
        severity = insights.get("clinical_severity_signals", {})

        has_pending_diagnostics = diagnostics.get("has_ordered_tests", False)
        needs_second_opinion = severity.get("is_second_opinion_recommended", False)

        if not (has_pending_diagnostics or needs_second_opinion):
            # Only flag as missed if not investigating other causes
            missed_indicators.append("sleep_therapy")
            symptoms = sleep.get("sleep_symptoms", [])
            missed_details["sleep_therapy"] = f"Sleep symptoms ({', '.join(symptoms)}) with obesity/HTN but no sleep evaluation discussed"

    # 6. Cardiac Rehabilitation
    is_rehab_cardiac_explicit = (
        rehab.get("has_cardiac_event", False) and
        rehab.get("cardiac_rehab_mentioned", False)
    )
    is_rehab_cardiac_potential = rehab.get("cardiac_rehab_potential", False)
    if is_rehab_cardiac_potential and not is_rehab_cardiac_explicit:
        missed_indicators.append("rehab_cardiac")
        event_types = rehab.get("cardiac_event_type", [])
        missed_details["rehab_cardiac"] = f"Cardiac event ({', '.join(event_types)}) but cardiac rehab not discussed"

    # 7. General Rehabilitation
    is_rehab_common_explicit = (
        not rehab.get("has_cardiac_event", False) and
        (rehab.get("has_stroke", False) or rehab.get("has_orthopedic_surgery", False)) and
        rehab.get("general_rehab_mentioned", False)
    )
    is_rehab_common_potential = rehab.get("general_rehab_potential", False)
    if is_rehab_common_potential and not is_rehab_common_explicit:
        missed_indicators.append("rehab_common")
        missed_details["rehab_common"] = "Post-stroke/surgery but rehabilitation not discussed"

    # 8. Treatment Education
    is_treatment_education_explicit = (
        education.get("is_new_diagnosis", False) and
        education.get("understanding_barrier_present", False)
    )
    is_treatment_education_potential = education.get("education_potential", False)
    if is_treatment_education_potential and not is_treatment_education_explicit:
        missed_indicators.append("treatment_education")
        missed_details["treatment_education"] = "New/complex diagnosis but formal patient education not discussed"

    # 9. Wellness
    is_wellness_explicit = (
        wellness.get("has_lifestyle_disease", False) and
        wellness.get("prevention_discussed", False)
    )
    is_wellness_potential = wellness.get("wellness_potential", False)
    if is_wellness_potential and not is_wellness_explicit:
        missed_indicators.append("wellness")
        diseases = wellness.get("lifestyle_diseases", [])
        missed_details["wellness"] = f"Lifestyle diseases ({', '.join(diseases)}) but no prevention/wellness discussion"

    missed_count = len(missed_indicators)

    return {
        "has_missed_opportunities": missed_count >= threshold,
        "missed_count": missed_count,
        "threshold": threshold,
        "missed_indicators": missed_indicators,
        "missed_details": missed_details
    }


# ============================================================================
# Risk Level Enum for Dropoff Risk
# ============================================================================

class DropoffRiskLevel(Enum):
    """Patient dropoff risk levels."""
    LOW = "LOW"           # 5-29%
    MEDIUM = "MEDIUM"     # 30-49%
    HIGH = "HIGH"         # 50-69%
    CRITICAL = "CRITICAL" # 70-95%


# ============================================================================
# Dropoff Risk Mappings (Combined Mode Only)
# ============================================================================

ANXIETY_LEVEL_SCORES = {
    "None": 0,
    "Mild": 2,
    "Moderate": 5,
    "Severe": 8
}

COMPLIANCE_SCORES = {
    "Very Low": 10,   # 0-19% compliance expected
    "Low": 35,        # 20-49% compliance expected
    "Moderate": 65,   # 50-79% compliance expected
    "High": 90        # 80-100% compliance expected
}

DROPOFF_INDICATOR_WEIGHTS = {
    "financial_risk": 25,        # C1 - Financial + Price Sensitivity
    "competitor_risk": 10,       # C2 - Considering alternatives
    "dissatisfaction_risk": 25,  # C3 - Rapport + Dissatisfaction
    "access_risk": 10,           # C4 - Logistics barriers
    "compliance_risk": 30        # C5 - Dropout + Confusion
}


def map_insights_to_dropoff_risk(
    insights: Dict[str, Any],
    emotional_segments: Optional[Dict[str, Any]] = None,
    follow_up_segment: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Map consultation insights + emotional segments to patient dropoff risk.

    Calculates 5 churn indicators:
    - C1: Financial Risk (25%) - Financial concerns, price sensitivity
    - C2: Competitor Risk (10%) - Considering other providers
    - C3: Dissatisfaction Risk (25%) - Anxiety worsened, weak rapport
    - C4: Access Risk (10%) - Logistics barriers
    - C5: Compliance Risk (30%) - Low compliance likelihood, treatment confusion

    Uses Combined Mode schema only (trajectory.trajectory instead of change_from_pre).

    Args:
        insights: Extracted consultation insights (includes competitor_signals, access_logistics_signals)
        emotional_segments: Dict of emotional segment data keyed by segment name:
            - ANXIETY_POST_CONSULTATION
            - FINANCIAL_CONCERNS
            - OTHER_EMOTIONS_DETECTED
            - TREATMENT_COMPLIANCE_LIKELIHOOD
            - DOCTOR_COMMUNICATION_STYLE
            - INTERACTION_DYNAMICS
            - CONGRUENCE_SUMMARY
        follow_up_segment: FOLLOW_UP segment data

    Returns:
        Dict with dropoff_probability, risk_level, indicators, reasons, modifiers
    """
    emotional_segments = emotional_segments or {}
    follow_up_segment = follow_up_segment or {}

    # Extract emotional segments
    anxiety_seg = emotional_segments.get("ANXIETY_POST_CONSULTATION", {})
    financial_seg = emotional_segments.get("FINANCIAL_CONCERNS", {})
    other_emotions_seg = emotional_segments.get("OTHER_EMOTIONS_DETECTED", {})
    compliance_seg = emotional_segments.get("TREATMENT_COMPLIANCE_LIKELIHOOD", {})
    doctor_comm_seg = emotional_segments.get("DOCTOR_COMMUNICATION_STYLE", {})
    congruence_seg = emotional_segments.get("CONGRUENCE_SUMMARY", {})

    # Extract consultation insights signals
    competitor_signals = insights.get("competitor_signals", {})
    access_signals = insights.get("access_logistics_signals", {})
    medication_signals = insights.get("medication_signals", {})

    # =========================================================================
    # C1: Financial Risk (25%)
    # =========================================================================
    c1_reasons = []
    c1_is_true = False

    financial_severity = financial_seg.get("severity", "None")
    if financial_severity in ["Severe", "High"]:
        c1_is_true = True
        c1_reasons.append(f"Patient has {financial_severity.lower()} financial concerns")

    if financial_seg.get("alternative_treatment_requested", False):
        c1_is_true = True
        c1_reasons.append("Patient requested alternative treatment due to cost")

    # Check for Financial barrier in compliance
    key_barriers = compliance_seg.get("key_barriers", [])
    for barrier in key_barriers:
        if isinstance(barrier, dict) and barrier.get("barrier_type") == "Financial":
            barrier_severity = barrier.get("severity", "Minor")
            if barrier_severity in ["Major", "Moderate"]:
                c1_is_true = True
                c1_reasons.append(f"Patient has {barrier_severity.lower()} financial barrier to treatment")

    specific_concerns = financial_seg.get("specific_concerns", [])
    cost_concerns = ["Treatment cost", "Medication cost", "Test/procedure cost"]
    matched_concerns = [c for c in specific_concerns if c in cost_concerns]
    if matched_concerns:
        c1_is_true = True
        c1_reasons.append(f"Patient expressed concerns about: {', '.join(matched_concerns).lower()}")

    # =========================================================================
    # C2: Competitor Risk (10%)
    # =========================================================================
    c2_reasons = []
    c2_is_true = False

    if competitor_signals.get("competitor_intent_detected", False):
        c2_is_true = True

        names = competitor_signals.get("competitor_names_mentioned", [])
        reason = competitor_signals.get("competitor_reason")
        evidence = competitor_signals.get("competitor_evidence", [])

        # Build human-readable reason (no technical codes)
        if names:
            c2_reasons.append(f"Patient mentioned other providers: {', '.join(names[:3])}")
        if reason:
            c2_reasons.append(reason)
        if evidence:
            # Include patient quote if available
            for quote in evidence[:1]:
                if quote and len(quote) > 10:
                    c2_reasons.append(f'Patient states: "{quote}"')
        if not c2_reasons:
            c2_reasons.append("Patient considering alternative healthcare providers")

    # =========================================================================
    # C3: Dissatisfaction & Rapport Risk (25%)
    # =========================================================================
    c3_reasons = []
    c3_is_true = False

    # Combined mode: Use trajectory.trajectory
    trajectory_data = anxiety_seg.get("trajectory", {})
    anxiety_trajectory = trajectory_data.get("trajectory", "Unable to determine")
    anxiety_post_level = anxiety_seg.get("level", "None")
    anxiety_pre_level = anxiety_seg.get("pre_consultation", {}).get("level", "None")

    if anxiety_trajectory == "Worsened":
        c3_is_true = True
        c3_reasons.append(f"Patient anxiety worsened during consultation (from {anxiety_pre_level} to {anxiety_post_level})")

    # Anxiety stable AND post_level >= Moderate
    if anxiety_trajectory == "Stable" and anxiety_post_level in ["Moderate", "Severe"]:
        c3_is_true = True
        c3_reasons.append(f"Patient shows persistent {anxiety_post_level.lower()} anxiety level")

    # Doctor increased anxiety
    if doctor_comm_seg.get("patient_anxiety_impact") == "Increased":
        c3_is_true = True
        c3_reasons.append("Doctor communication may have increased patient anxiety")

    # Check for negative emotions in OTHER_EMOTIONS_DETECTED
    emotions_detected = other_emotions_seg.get("emotions_detected", [])
    for emotion in emotions_detected:
        if isinstance(emotion, dict):
            emotion_name = emotion.get("emotion", "")
            severity = emotion.get("severity", "")
            clinical_sig = emotion.get("clinical_significance", "")

            if emotion_name in ["Anger", "Frustration"] and severity in ["Moderate", "Severe"]:
                c3_is_true = True
                c3_reasons.append(f"Patient showed {severity.lower()} {emotion_name.lower()}")

            if emotion_name == "Distress" and clinical_sig == "High":
                c3_is_true = True
                c3_reasons.append("Patient showed significant distress during consultation")

    # Low congruence score
    _raw_cong = congruence_seg.get("congruence_score")
    congruence_score = float(_raw_cong) if _raw_cong is not None else None
    if congruence_score is not None and congruence_score < 0.5:
        c3_is_true = True
        c3_reasons.append("Patient's emotional response did not match expected reaction to consultation")

    # =========================================================================
    # C4: Access/Logistics Risk (10%)
    # Only for TRUE logistics barriers (distance, transportation, language, scheduling)
    # "cost" is a FINANCIAL barrier, not a logistics barrier - handled in C1
    # =========================================================================
    c4_reasons = []
    c4_is_true = False

    # Financial barriers that should NOT trigger access risk (handled in C1)
    FINANCIAL_BARRIER_TYPES = {"cost", "financial", "money", "payment", "expense", "afford"}

    if access_signals.get("access_barriers_detected", False):
        barrier_types = access_signals.get("access_barrier_types", [])

        # Filter out financial barriers - they belong in C1, not C4
        logistics_barriers = [
            b for b in barrier_types
            if b.lower() not in FINANCIAL_BARRIER_TYPES
        ]

        # Only trigger access risk if there are TRUE logistics barriers
        if logistics_barriers:
            c4_is_true = True
            c4_reasons.append(f"Patient faces logistics barriers: {', '.join(logistics_barriers)}")

            access_severity = access_signals.get("access_severity", "None")
            if access_severity in ["Moderate", "Severe"]:
                c4_reasons.append(f"Access severity: {access_severity}")
        elif barrier_types:
            # Log that we filtered out financial-only barriers
            logger.debug(
                f"[DROPOFF_RISK] Filtered out financial-only barriers from access risk: {barrier_types}"
            )

    # Check for Logistical barrier in compliance
    for barrier in key_barriers:
        if isinstance(barrier, dict) and barrier.get("barrier_type") == "Logistical":
            c4_is_true = True
            barrier_severity = barrier.get("severity", "Minor")
            c4_reasons.append(f"Patient has {barrier_severity.lower()} logistical barrier to treatment compliance")

    # =========================================================================
    # C5: Compliance Risk (30%)
    # =========================================================================
    c5_reasons = []
    c5_is_true = False

    compliance_likelihood = compliance_seg.get("likelihood", "Moderate")
    if compliance_likelihood in ["Very Low", "Low"]:
        c5_is_true = True
        c5_reasons.append(f"Patient has {compliance_likelihood.lower()} likelihood of following treatment plan")

    # Vague follow-up timeline
    # IMPORTANT: A timeline like "After 5 days, if symptoms persist" is NOT vague
    # because it has a specific time period (5 days). Only consider vague if NO specific time.
    timeline = follow_up_segment.get("review_date", "") or follow_up_segment.get("other_instructions", "")
    timeline_lower = timeline.lower().strip() if timeline else ""

    # Check if timeline has a SPECIFIC time period (e.g., "5 days", "1 week", "2 months")
    has_specific_time = False
    if timeline_lower:
        import re
        specific_patterns = [
            r'\d+\s*days?', r'\d+\s*weeks?', r'\d+\s*months?', r'\d+\s*hours?',
            r'\d+\s*-\s*\d+\s*days?', r'\d+\s*-\s*\d+\s*weeks?',
            r'tomorrow', r'next\s+week', r'next\s+month',
            r'after\s+\d+', r'in\s+\d+', r'within\s+\d+'
        ]
        for pattern in specific_patterns:
            if re.search(pattern, timeline_lower):
                has_specific_time = True
                break

    # Only mark as vague if NO specific time exists
    vague_terms = ["as needed", "prn", "when required", "if necessary", "sos"]
    if not timeline_lower or timeline_lower in ["n/a", "none", "not specified", "-"]:
        c5_is_true = True
        c5_reasons.append("No follow-up timeline was specified during consultation")
    elif not has_specific_time and any(term in timeline_lower for term in vague_terms):
        # Only vague if it has conditional terms BUT no specific time
        c5_is_true = True
        c5_reasons.append(f"Follow-up timeline is vague: '{timeline}'")

    # 3+ barriers
    if len(key_barriers) >= 3:
        c5_is_true = True
        barrier_types = [b.get("barrier_type", "Unknown") for b in key_barriers if isinstance(b, dict)]
        c5_reasons.append(f"{len(key_barriers)} barriers identified: {', '.join(barrier_types)}")

    # Understanding barrier present
    for barrier in key_barriers:
        if isinstance(barrier, dict) and barrier.get("barrier_type") == "Understanding":
            c5_is_true = True
            c5_reasons.append("Understanding barrier present")
            break

    # Complex treatment: 3+ medications
    total_meds = int(medication_signals.get("total_medications_prescribed", 0))
    if total_meds >= 3:
        c5_is_true = True
        c5_reasons.append(f"Complex treatment: {total_meds} medications prescribed")

    # =========================================================================
    # Calculate Base Probability from Indicators
    # =========================================================================
    active_indicators = []
    if c1_is_true:
        active_indicators.append("financial_risk")
    if c2_is_true:
        active_indicators.append("competitor_risk")
    if c3_is_true:
        active_indicators.append("dissatisfaction_risk")
    if c4_is_true:
        active_indicators.append("access_risk")
    if c5_is_true:
        active_indicators.append("compliance_risk")

    base_probability = sum(DROPOFF_INDICATOR_WEIGHTS[ind] for ind in active_indicators)

    # =========================================================================
    # Apply Anxiety Trajectory Modifier
    # =========================================================================
    anxiety_pre_score = ANXIETY_LEVEL_SCORES.get(anxiety_pre_level, 0)
    anxiety_post_score = ANXIETY_LEVEL_SCORES.get(anxiety_post_level, 0)
    anxiety_delta = anxiety_post_score - anxiety_pre_score

    if anxiety_trajectory == "Worsened":
        if anxiety_delta >= 3:  # Significantly worsened
            anxiety_modifier = 1.3
        else:
            anxiety_modifier = 1.15
    elif anxiety_trajectory == "Stable":
        anxiety_modifier = 1.0
    elif anxiety_trajectory == "Improved":
        if anxiety_delta <= -3:  # Significantly improved
            anxiety_modifier = 0.75
        else:
            anxiety_modifier = 0.9
    else:  # Unable to determine
        anxiety_modifier = 1.0

    # =========================================================================
    # Apply Compliance Likelihood Modifier
    # =========================================================================
    compliance_score = COMPLIANCE_SCORES.get(compliance_likelihood, 65)

    if compliance_score < 20:      # Very Low
        compliance_modifier = 1.25
    elif compliance_score < 50:    # Low
        compliance_modifier = 1.1
    elif compliance_score < 80:    # Moderate
        compliance_modifier = 1.0
    else:                          # High
        compliance_modifier = 0.85

    # =========================================================================
    # Calculate Final Probability
    # =========================================================================
    raw_probability = base_probability * anxiety_modifier * compliance_modifier
    final_probability = min(95.0, max(5.0, raw_probability))

    # =========================================================================
    # Determine Risk Level
    # =========================================================================
    if final_probability >= 70:
        risk_level = DropoffRiskLevel.CRITICAL
    elif final_probability >= 50:
        risk_level = DropoffRiskLevel.HIGH
    elif final_probability >= 30:
        risk_level = DropoffRiskLevel.MEDIUM
    else:
        risk_level = DropoffRiskLevel.LOW

    # =========================================================================
    # Determine Primary Risk Driver
    # =========================================================================
    primary_risk_driver = None
    if active_indicators:
        # Find the indicator with highest weight that's TRUE
        max_weight = 0
        for ind in active_indicators:
            if DROPOFF_INDICATOR_WEIGHTS[ind] > max_weight:
                max_weight = DROPOFF_INDICATOR_WEIGHTS[ind]
                primary_risk_driver = ind

    return {
        # Probability and risk level
        "dropoff_probability": round(final_probability, 2),
        "risk_level": risk_level.value,

        # 5 churn indicators
        "is_financial_risk": c1_is_true,
        "is_competitor_risk": c2_is_true,
        "is_dissatisfaction_risk": c3_is_true,
        "is_access_risk": c4_is_true,
        "is_compliance_risk": c5_is_true,

        # Reasons for each indicator
        "financial_risk_reasons": c1_reasons,
        "competitor_risk_reasons": c2_reasons,
        "dissatisfaction_risk_reasons": c3_reasons,
        "access_risk_reasons": c4_reasons,
        "compliance_risk_reasons": c5_reasons,

        # Anxiety trajectory data
        "anxiety_pre_level": anxiety_pre_level,
        "anxiety_post_level": anxiety_post_level,
        "anxiety_trajectory": anxiety_trajectory,
        "anxiety_modifier": round(anxiety_modifier, 2),

        # Compliance data
        "compliance_likelihood": compliance_likelihood,
        "compliance_modifier": round(compliance_modifier, 2),

        # Score breakdown
        "base_probability": round(base_probability, 2),
        "indicator_count": len(active_indicators),
        "primary_risk_driver": primary_risk_driver,

        # Metadata
        "calculation_version": "1.0.0"
    }

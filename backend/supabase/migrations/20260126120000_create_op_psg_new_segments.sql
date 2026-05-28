-- OP_PSG_NEW Segments Implementation
-- This migration:
-- 1. Links CONSUMABLES to OP_PSG consultation_type_segments
-- 2. Creates 10 new segment definitions for PSG workflow
-- 3. Links CONSUMABLES and 10 new segments to OP_PSG_NEW consultation_type_segments
-- 4. Updates display orders for existing OP_PSG_NEW segments

-- ========================================
-- TASK 1: Link CONSUMABLES to OP_PSG
-- ========================================
INSERT INTO consultation_type_segments (
    id,
    consultation_type_id,
    segment_code,
    segment_id,
    default_category,
    default_display_order,
    default_brevity_level,
    default_terminology_style,
    is_required_for_type,
    created_at,
    consultation_type_name
) VALUES (
    gen_random_uuid(),
    '93552782-b1d1-415a-ab4a-0449fca6b6fb',  -- OP_PSG consultation type
    'CONSUMABLES',
    '3a449fb4-d94f-43eb-931e-a1d9e465a020',  -- CONSUMABLES segment ID
    'core',
    14,
    'balanced',
    'medical_terms',
    false,
    NOW(),
    'OP_PSG'
) ON CONFLICT DO NOTHING;

-- ========================================
-- TASK 2: Create 10 NEW Segment Definitions
-- ========================================

-- 1. ALLERGY (PSG Allergy)
INSERT INTO segment_definitions (
    id,
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    is_required,
    display_order,
    default_brevity_level,
    default_terminology_style,
    description,
    is_active,
    segment_type,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'ALLERGY',
    'PSG Allergy',
    '**ALLERGY:**
Extract patient''s allergy information.

**Required Fields:**
- has_allergy: "Yes" or "No Known Allergy"
- allergy_type: "Drugs" / "Food" / "Others" (if has_allergy is Yes)
- details: Specific allergy details (if has_allergy is Yes)

***Example:***
```json
{
  "has_allergy": "Yes",
  "allergy_type": "Drugs",
  "details": "Allergic to Penicillin - causes skin rash"
}
```

**Extraction Rules:**
- If no allergies mentioned, set has_allergy to "No Known Allergy"
- If allergies present, capture type and specific details',
    '{
        "type": "object",
        "properties": {
            "has_allergy": { "type": "string", "description": "Yes or No Known Allergy" },
            "allergy_type": { "type": "string", "description": "Drugs / Food / Others" },
            "details": { "type": "string", "description": "Specific allergy details" }
        }
    }'::jsonb,
    'core',
    false,
    2,
    'balanced',
    'medical_terms',
    'Patient allergy information including drug, food, and other allergies',
    true,
    'system',
    NOW(),
    NOW()
);

-- 2. TB_SCREENING (PSG TB Screening)
INSERT INTO segment_definitions (
    id,
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    is_required,
    display_order,
    default_brevity_level,
    default_terminology_style,
    description,
    is_active,
    segment_type,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'TB_SCREENING',
    'PSG TB Screening',
    '**TB_SCREENING:**
Extract Four Symptom Screening for TB findings.

**Required Fields:**
- symptoms: Array of symptoms present (from: "Cough for more than 2 weeks", "Fever for more than 2 weeks", "Significant Weight Loss", "Night Sweats", "Nil")
- remarks: Additional remarks for symptoms if any

***Example:***
```json
{
  "symptoms": ["Cough for more than 2 weeks", "Night Sweats"],
  "remarks": "Patient reports dry cough since 3 weeks, occasional night sweats"
}
```

**Extraction Rules:**
- If no TB symptoms present, set symptoms to ["Nil"]
- Capture any relevant remarks about the symptoms',
    '{
        "type": "object",
        "properties": {
            "symptoms": {
                "type": "array",
                "items": { "type": "string" },
                "description": "TB screening symptoms: Cough >2 weeks, Fever >2 weeks, Significant Weight Loss, Night Sweats, or Nil"
            },
            "remarks": { "type": "string", "description": "Additional remarks about symptoms" }
        }
    }'::jsonb,
    'core',
    false,
    3,
    'balanced',
    'medical_terms',
    'Four Symptom Screening for TB - mandatory screening for all patients',
    true,
    'system',
    NOW(),
    NOW()
);

-- 3. CHIEF_COMPLAINTS (PSG Chief Complaints)
INSERT INTO segment_definitions (
    id,
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    is_required,
    display_order,
    default_brevity_level,
    default_terminology_style,
    description,
    is_active,
    segment_type,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'CHIEF_COMPLAINTS',
    'PSG Chief Complaints',
    '**CHIEF_COMPLAINTS:**
Extract presenting complaints with duration and severity.

**Required Fields (for each complaint):**
- complaint_name: Name of the complaint
- since_value: Duration number
- since_unit: "Days" / "Weeks" / "Months" / "Years"
- severity: "Mild" / "Moderate" / "Severe" / "None"
- notes: Additional notes about the complaint

***Example:***
```json
[
  {
    "complaint_name": "Chest pain",
    "since_value": 3,
    "since_unit": "Days",
    "severity": "Moderate",
    "notes": "Pain increases on exertion"
  },
  {
    "complaint_name": "Breathlessness",
    "since_value": 1,
    "since_unit": "Weeks",
    "severity": "Mild",
    "notes": "On climbing stairs"
  }
]
```

**Extraction Rules:**
- Extract all complaints mentioned by the patient
- Estimate severity based on patient''s description
- Include any aggravating/relieving factors in notes',
    '{
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "complaint_name": { "type": "string", "description": "Name of complaint" },
                "since_value": { "type": "number", "description": "Duration value" },
                "since_unit": { "type": "string", "description": "Days / Weeks / Months / Years" },
                "severity": { "type": "string", "description": "Mild / Moderate / Severe / None" },
                "notes": { "type": "string", "description": "Additional notes" }
            }
        }
    }'::jsonb,
    'core',
    false,
    4,
    'balanced',
    'medical_terms',
    'Patient presenting complaints with duration and severity',
    true,
    'system',
    NOW(),
    NOW()
);

-- 4. GENERAL_HISTORY (PSG General History)
INSERT INTO segment_definitions (
    id,
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    is_required,
    display_order,
    default_brevity_level,
    default_terminology_style,
    description,
    is_active,
    segment_type,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'GENERAL_HISTORY',
    'PSG General History',
    '**GENERAL_HISTORY:**
Extract comprehensive medical, personal, and family history.

**Required Fields:**
- known_medical_problems: Array of conditions with duration and details
- detailed_medical_history: Free text medical history
- previous_medicines: Current/previous medications
- personal_history: General personal history notes
- sleep: "Nil" / "Disturbed" / "Increased"
- sleep_details: Details if not normal
- bowel_habit: "Nil" / "Loose Stools" / "Bleeding" / "Diarrhea" / "Constipation"
- bowel_details: Details if not normal
- bladder: "Nil" / "Incontinence" / "Dysuria" / "Uria" / "Others"
- bladder_details: Details if not normal
- significant_weight_change: "Weight Gain" / "Weight Loss" / "No Change"
- weight_change_details: Details if weight changed
- diet: "Veg" / "Non-Veg" / "Mixed" / "Others"
- habitual_risk_factors: "Smoker" / "Ex-Smoker" / "Alcoholic" / "Tobacco" / "Substance" / "Others" / "No Addiction"
- addiction_since_value, addiction_since_unit, addiction_details: If any addiction
- physical_activity: "Sedentary" / "Moderately Active" / "Active"
- occupation_info: Occupation and related information
- marital_history: "Single" / "Married" / "Divorce" / "Widow" / "Living Together"
- menstrual_cycle: "Regular" / "Irregular" (for female patients)
- menstrual_details, menopause: Related details
- family_history: Array of family conditions with relative and details
- psychological_assessment: "Medical Treatment" / "Follow-up with Psychiatrist" or null
- other_relevant_history: Any other relevant history
- previous_hospitalization: Array of past hospitalizations

***Example:***
```json
{
  "known_medical_problems": [
    { "condition": "Hypertension", "since_value": 5, "since_unit": "Years", "details": "On medication" },
    { "condition": "Diabetes", "since_value": 3, "since_unit": "Years", "details": "Type 2, controlled" }
  ],
  "detailed_medical_history": "Known case of HTN and DM, on regular medication",
  "previous_medicines": "Amlodipine 5mg, Metformin 500mg",
  "sleep": "Disturbed",
  "sleep_details": "Difficulty falling asleep",
  "bowel_habit": "Nil",
  "bladder": "Nil",
  "significant_weight_change": "No Change",
  "diet": "Mixed",
  "habitual_risk_factors": "Ex-Smoker",
  "addiction_since_value": 10,
  "addiction_since_unit": "Years",
  "addiction_details": "Quit smoking 2 years ago",
  "physical_activity": "Sedentary",
  "occupation_info": "Office worker, desk job",
  "marital_history": "Married",
  "family_history": [
    { "morbidity": "Diabetes", "relative": "Father", "details": "Type 2 DM" }
  ],
  "previous_hospitalization": [
    { "type": "Medical", "hospital_name": "City Hospital", "reason": "Pneumonia", "conclusion": "Recovered" }
  ]
}
```

**Extraction Rules:**
- Extract all mentioned medical conditions with durations
- Capture lifestyle factors (diet, smoking, alcohol, exercise)
- Include family history of relevant conditions
- Note any previous hospitalizations or surgeries',
    '{
        "type": "object",
        "properties": {
            "known_medical_problems": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "condition": { "type": "string" },
                        "since_value": { "type": "number" },
                        "since_unit": { "type": "string" },
                        "details": { "type": "string" }
                    }
                }
            },
            "detailed_medical_history": { "type": "string" },
            "previous_medicines": { "type": "string" },
            "personal_history": { "type": "string" },
            "sleep": { "type": "string" },
            "sleep_details": { "type": "string" },
            "bowel_habit": { "type": "string" },
            "bowel_details": { "type": "string" },
            "bladder": { "type": "string" },
            "bladder_details": { "type": "string" },
            "significant_weight_change": { "type": "string" },
            "weight_change_details": { "type": "string" },
            "diet": { "type": "string" },
            "habitual_risk_factors": { "type": "string" },
            "addiction_since_value": { "type": "number" },
            "addiction_since_unit": { "type": "string" },
            "addiction_details": { "type": "string" },
            "physical_activity": { "type": "string" },
            "occupation_info": { "type": "string" },
            "marital_history": { "type": "string" },
            "menstrual_cycle": { "type": "string" },
            "menstrual_details": { "type": "string" },
            "menopause": { "type": "string" },
            "family_history": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "morbidity": { "type": "string" },
                        "relative": { "type": "string" },
                        "details": { "type": "string" }
                    }
                }
            },
            "psychological_assessment": { "type": "string" },
            "other_relevant_history": { "type": "string" },
            "previous_hospitalization": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": { "type": "string" },
                        "hospital_name": { "type": "string" },
                        "reason": { "type": "string" },
                        "conclusion": { "type": "string" }
                    }
                }
            }
        }
    }'::jsonb,
    'core',
    false,
    6,
    'balanced',
    'medical_terms',
    'Comprehensive medical, personal, family history and lifestyle factors',
    true,
    'system',
    NOW(),
    NOW()
);

-- 5. SURGICAL_HISTORY (PSG Surgical History)
INSERT INTO segment_definitions (
    id,
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    is_required,
    display_order,
    default_brevity_level,
    default_terminology_style,
    description,
    is_active,
    segment_type,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'SURGICAL_HISTORY',
    'PSG Surgical History',
    '**SURGICAL_HISTORY:**
Extract surgical history and related conditions.

**Required Fields (for each entry):**
- type_system: Type/system affected (Lump/Ulcer/Sinus/Fistula/Varicose Veins/Peripheral Vascular Disease/Lymphatic/Head & Neck/Thyroid/Breast/Abdomen/Hernia/Others)
- onset: "Insidious" / "Sudden"
- duration: Duration of condition
- site: Location/site of the condition
- progress: Progression details
- pain_severity: Severity of pain if any
- aggravating_factors: Factors that worsen the condition

***Example:***
```json
[
  {
    "type_system": "Hernia",
    "onset": "Insidious",
    "duration": "6 months",
    "site": "Right inguinal region",
    "progress": "Gradually increasing in size",
    "pain_severity": "Mild discomfort",
    "aggravating_factors": "Straining, heavy lifting"
  }
]
```

**Extraction Rules:**
- Extract all surgical conditions mentioned
- Capture onset pattern and progression
- Note any pain or aggravating factors',
    '{
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "type_system": { "type": "string", "description": "Lump/Ulcer/Sinus/Fistula/Varicose Veins/Peripheral Vascular Disease/Lymphatic/Head & Neck/Thyroid/Breast/Abdomen/Hernia/Others" },
                "onset": { "type": "string", "description": "Insidious / Sudden" },
                "duration": { "type": "string" },
                "site": { "type": "string" },
                "progress": { "type": "string" },
                "pain_severity": { "type": "string" },
                "aggravating_factors": { "type": "string" }
            }
        }
    }'::jsonb,
    'core',
    false,
    7,
    'balanced',
    'medical_terms',
    'Surgical history including lumps, ulcers, hernias, and other surgical conditions',
    true,
    'system',
    NOW(),
    NOW()
);

-- 6. GENERAL_EXAMINATION (PSG General Examination)
INSERT INTO segment_definitions (
    id,
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    is_required,
    display_order,
    default_brevity_level,
    default_terminology_style,
    description,
    is_active,
    segment_type,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'GENERAL_EXAMINATION',
    'PSG General Examination',
    '**GENERAL_EXAMINATION:**
Extract general physical examination findings.

**Required Fields:**
- level_of_consciousness: Conscious/Alert/Oriented to time, person and place/Drowsy/Disoriented/Dizziness/Unresponsive
- general_appearance: Healthy/Ill looking/Comfortable/Distressed
- general_findings: Pallor/Icterus/Cyanosis/Clubbing/Lymphadenopathy/Pedal Edema/JVP/Goitre/Others
- general_systemic_examination: Free text findings
- ecog_score: 0/1/2/3/4 (ECOG Performance Score)
- lansky_score: 10/20/30/40/50/60/70/80/90/100 (Lansky Play-Performance Score)
- jugular_vein_pressure: JVP findings
- hydration: Hydration status
- speech: Speech assessment
- personal_hygiene: Hygiene assessment
- breath_odor: Any breath odor noted
- other_relevant_finding: Any other relevant findings

***Example:***
```json
{
  "level_of_consciousness": "Conscious and oriented to time, person and place",
  "general_appearance": "Comfortable",
  "general_findings": "No pallor, No icterus, No cyanosis, No clubbing, No lymphadenopathy, Mild pedal edema",
  "ecog_score": 1,
  "lansky_score": 90,
  "jugular_vein_pressure": "Normal",
  "hydration": "Adequate",
  "speech": "Normal",
  "personal_hygiene": "Good",
  "other_relevant_finding": "Mild bilateral pedal edema noted"
}
```

**Extraction Rules:**
- Extract all general examination findings
- Use appropriate scores if mentioned
- Note any abnormal findings',
    '{
        "type": "object",
        "properties": {
            "level_of_consciousness": { "type": "string" },
            "general_appearance": { "type": "string" },
            "general_findings": { "type": "string" },
            "general_systemic_examination": { "type": "string" },
            "ecog_score": { "type": "number" },
            "lansky_score": { "type": "number" },
            "jugular_vein_pressure": { "type": "string" },
            "hydration": { "type": "string" },
            "speech": { "type": "string" },
            "personal_hygiene": { "type": "string" },
            "breath_odor": { "type": "string" },
            "other_relevant_finding": { "type": "string" }
        }
    }'::jsonb,
    'core',
    false,
    8,
    'balanced',
    'medical_terms',
    'General physical examination including consciousness, appearance, and standard clinical findings',
    true,
    'system',
    NOW(),
    NOW()
);

-- 7. SYSTEMIC_EXAMINATION (PSG Systemic Examination)
INSERT INTO segment_definitions (
    id,
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    is_required,
    display_order,
    default_brevity_level,
    default_terminology_style,
    description,
    is_active,
    segment_type,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'SYSTEMIC_EXAMINATION',
    'PSG Systemic Examination',
    '**SYSTEMIC_EXAMINATION:**
Extract system-wise examination findings.

**Required Fields (for each system examined):**
- system_type: Respiratory/Cardio Vascular/Abdomen & Perineum/Endocrine/Central Nervous/Cutaneous/Muscoskeletal/Psychiatry/O&G/ENT/Others
- examination: Examination findings for that system

***Example:***
```json
[
  {
    "system_type": "Respiratory",
    "examination": "Bilateral air entry equal, no added sounds, chest clear"
  },
  {
    "system_type": "Cardio Vascular",
    "examination": "S1 S2 heard, no murmurs, regular rhythm"
  },
  {
    "system_type": "Abdomen & Perineum",
    "examination": "Soft, non-tender, no organomegaly, bowel sounds present"
  }
]
```

**Extraction Rules:**
- Extract findings for each system examined
- Include both normal and abnormal findings
- Use standard medical terminology',
    '{
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "system_type": { "type": "string", "description": "Respiratory/Cardio Vascular/Abdomen & Perineum/Endocrine/Central Nervous/Cutaneous/Muscoskeletal/Psychiatry/O&G/ENT/Others" },
                "examination": { "type": "string" }
            }
        }
    }'::jsonb,
    'core',
    false,
    9,
    'balanced',
    'medical_terms',
    'System-wise examination findings for respiratory, cardiovascular, abdominal, and other systems',
    true,
    'system',
    NOW(),
    NOW()
);

-- 8. SURGICAL_EXAMINATION (PSG Surgical Examination)
INSERT INTO segment_definitions (
    id,
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    is_required,
    display_order,
    default_brevity_level,
    default_terminology_style,
    description,
    is_active,
    segment_type,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'SURGICAL_EXAMINATION',
    'PSG Surgical Examination',
    '**SURGICAL_EXAMINATION:**
Extract surgical examination findings by system.

**Required Fields (for each system examined):**
- system_type: Respiratory/Cardio Vascular/Abdomen & Perineum/Endocrine/Central Nervous/Cutaneous/Muscoskeletal/Psychiatry/O&G/ENT/Others
- examination: Surgical examination findings for that system

***Example:***
```json
[
  {
    "system_type": "Abdomen & Perineum",
    "examination": "Swelling in right inguinal region, 5x4 cm, reducible, cough impulse positive"
  },
  {
    "system_type": "Cutaneous",
    "examination": "No skin changes over the swelling, no signs of inflammation"
  }
]
```

**Extraction Rules:**
- Extract surgical examination findings for each system
- Include inspection, palpation, percussion findings where relevant
- Note any surgical signs or tests performed',
    '{
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "system_type": { "type": "string", "description": "Respiratory/Cardio Vascular/Abdomen & Perineum/Endocrine/Central Nervous/Cutaneous/Muscoskeletal/Psychiatry/O&G/ENT/Others" },
                "examination": { "type": "string" }
            }
        }
    }'::jsonb,
    'core',
    false,
    10,
    'balanced',
    'medical_terms',
    'Surgical examination findings including inspection, palpation, and specific surgical signs',
    true,
    'system',
    NOW(),
    NOW()
);

-- 9. PROCEDURE_NOTES (PSG Procedure Notes)
INSERT INTO segment_definitions (
    id,
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    is_required,
    display_order,
    default_brevity_level,
    default_terminology_style,
    description,
    is_active,
    segment_type,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'PROCEDURE_NOTES',
    'PSG Procedure Notes',
    '**PROCEDURE_NOTES:**
Extract procedure details if any procedure was performed.

**Required Fields:**
- procedure_date_time: Date and time of procedure
- consent_tag: "Availed" / "Not"
- procedure_done_by: Name of person who performed procedure
- procedure_name: Name of the procedure
- findings: Procedure findings
- notes: Additional notes
- post_procedure_instructions: Instructions given after procedure

***Example:***
```json
{
  "procedure_date_time": "26-01-2026 10:30 AM",
  "consent_tag": "Availed",
  "procedure_done_by": "Dr. Kumar",
  "procedure_name": "Fine Needle Aspiration Cytology",
  "findings": "Aspirate sent for cytology",
  "notes": "Procedure completed without complications",
  "post_procedure_instructions": "Apply pressure for 5 minutes, avoid strenuous activity for 24 hours"
}
```

**Extraction Rules:**
- Extract all procedure details if mentioned
- If no procedure performed, leave fields empty
- Include any complications or observations',
    '{
        "type": "object",
        "properties": {
            "procedure_date_time": { "type": "string" },
            "consent_tag": { "type": "string", "description": "Availed / Not" },
            "procedure_done_by": { "type": "string" },
            "procedure_name": { "type": "string" },
            "findings": { "type": "string" },
            "notes": { "type": "string" },
            "post_procedure_instructions": { "type": "string" }
        }
    }'::jsonb,
    'additional',
    false,
    11,
    'balanced',
    'medical_terms',
    'Procedure details including consent, findings, and post-procedure instructions',
    true,
    'system',
    NOW(),
    NOW()
);

-- 10. VISIT_SUMMARY (PSG Visit Summary)
INSERT INTO segment_definitions (
    id,
    segment_code,
    segment_name,
    prompt_section_text,
    schema_definition_json,
    default_category,
    is_required,
    display_order,
    default_brevity_level,
    default_terminology_style,
    description,
    is_active,
    segment_type,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'VISIT_SUMMARY',
    'PSG Visit Summary',
    '**VISIT_SUMMARY:**
Extract a concise summary of the entire visit.

**Required Fields:**
- visit_summary: A brief summary of the visit including chief complaints, key findings, diagnosis, and plan

***Example:***
```json
{
  "visit_summary": "45-year-old male presented with chest pain for 3 days. Known hypertensive on regular medication. Examination revealed stable vitals, mild pedal edema. Advised ECG and Echo. Continued on anti-hypertensives with addition of aspirin. Follow-up in 1 week."
}
```

**Extraction Rules:**
- Summarize the key points of the consultation
- Include demographics, chief complaints, relevant findings, and plan
- Keep it concise but comprehensive',
    '{
        "type": "object",
        "properties": {
            "visit_summary": { "type": "string", "description": "Summary of the visit" }
        }
    }'::jsonb,
    'additional',
    false,
    12,
    'balanced',
    'medical_terms',
    'Concise summary of the entire consultation visit',
    true,
    'system',
    NOW(),
    NOW()
);

-- ========================================
-- TASK 3: Update OP_PSG_NEW existing segment orders
-- ========================================

-- Update VITALS to order 1
UPDATE consultation_type_segments
SET default_display_order = 1
WHERE consultation_type_id = '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c'
  AND segment_code = 'VITALS';

-- Update DIAGNOSIS to order 5
UPDATE consultation_type_segments
SET default_display_order = 5
WHERE consultation_type_id = '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c'
  AND segment_code = 'DIAGNOSIS';

-- PRESCRIPTION stays at 13 (no change needed)

-- Update FOLLOW_UP to order 15
UPDATE consultation_type_segments
SET default_display_order = 15
WHERE consultation_type_id = '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c'
  AND segment_code = 'FOLLOW_UP';

-- CLINICAL_NOTES stays at 999 (no change needed)

-- ========================================
-- TASK 4: Link CONSUMABLES to OP_PSG_NEW
-- ========================================
INSERT INTO consultation_type_segments (
    id,
    consultation_type_id,
    segment_code,
    segment_id,
    default_category,
    default_display_order,
    default_brevity_level,
    default_terminology_style,
    is_required_for_type,
    created_at,
    consultation_type_name
) VALUES (
    gen_random_uuid(),
    '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c',  -- OP_PSG_NEW consultation type
    'CONSUMABLES',
    '3a449fb4-d94f-43eb-931e-a1d9e465a020',  -- CONSUMABLES segment ID
    'core',
    14,
    'balanced',
    'medical_terms',
    false,
    NOW(),
    'OP_PSG_NEW'
) ON CONFLICT DO NOTHING;

-- ========================================
-- TASK 5: Link 10 new segments to OP_PSG_NEW
-- ========================================

-- Link ALLERGY (order 2)
INSERT INTO consultation_type_segments (
    id,
    consultation_type_id,
    segment_code,
    segment_id,
    default_category,
    default_display_order,
    default_brevity_level,
    default_terminology_style,
    is_required_for_type,
    created_at,
    consultation_type_name
)
SELECT
    gen_random_uuid(),
    '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c',
    'ALLERGY',
    sd.id,
    'core',
    2,
    'balanced',
    'medical_terms',
    false,
    NOW(),
    'OP_PSG_NEW'
FROM segment_definitions sd
WHERE sd.segment_code = 'ALLERGY'
  AND sd.segment_type = 'system'
  AND sd.doctor_id IS NULL
ON CONFLICT DO NOTHING;

-- Link TB_SCREENING (order 3)
INSERT INTO consultation_type_segments (
    id,
    consultation_type_id,
    segment_code,
    segment_id,
    default_category,
    default_display_order,
    default_brevity_level,
    default_terminology_style,
    is_required_for_type,
    created_at,
    consultation_type_name
)
SELECT
    gen_random_uuid(),
    '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c',
    'TB_SCREENING',
    sd.id,
    'core',
    3,
    'balanced',
    'medical_terms',
    false,
    NOW(),
    'OP_PSG_NEW'
FROM segment_definitions sd
WHERE sd.segment_code = 'TB_SCREENING'
  AND sd.segment_type = 'system'
  AND sd.doctor_id IS NULL
ON CONFLICT DO NOTHING;

-- Link CHIEF_COMPLAINTS (order 4)
INSERT INTO consultation_type_segments (
    id,
    consultation_type_id,
    segment_code,
    segment_id,
    default_category,
    default_display_order,
    default_brevity_level,
    default_terminology_style,
    is_required_for_type,
    created_at,
    consultation_type_name
)
SELECT
    gen_random_uuid(),
    '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c',
    'CHIEF_COMPLAINTS',
    sd.id,
    'core',
    4,
    'balanced',
    'medical_terms',
    false,
    NOW(),
    'OP_PSG_NEW'
FROM segment_definitions sd
WHERE sd.segment_code = 'CHIEF_COMPLAINTS'
  AND sd.segment_type = 'system'
  AND sd.doctor_id IS NULL
ON CONFLICT DO NOTHING;

-- Link GENERAL_HISTORY (order 6)
INSERT INTO consultation_type_segments (
    id,
    consultation_type_id,
    segment_code,
    segment_id,
    default_category,
    default_display_order,
    default_brevity_level,
    default_terminology_style,
    is_required_for_type,
    created_at,
    consultation_type_name
)
SELECT
    gen_random_uuid(),
    '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c',
    'GENERAL_HISTORY',
    sd.id,
    'core',
    6,
    'balanced',
    'medical_terms',
    false,
    NOW(),
    'OP_PSG_NEW'
FROM segment_definitions sd
WHERE sd.segment_code = 'GENERAL_HISTORY'
  AND sd.segment_type = 'system'
  AND sd.doctor_id IS NULL
ON CONFLICT DO NOTHING;

-- Link SURGICAL_HISTORY (order 7)
INSERT INTO consultation_type_segments (
    id,
    consultation_type_id,
    segment_code,
    segment_id,
    default_category,
    default_display_order,
    default_brevity_level,
    default_terminology_style,
    is_required_for_type,
    created_at,
    consultation_type_name
)
SELECT
    gen_random_uuid(),
    '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c',
    'SURGICAL_HISTORY',
    sd.id,
    'core',
    7,
    'balanced',
    'medical_terms',
    false,
    NOW(),
    'OP_PSG_NEW'
FROM segment_definitions sd
WHERE sd.segment_code = 'SURGICAL_HISTORY'
  AND sd.segment_type = 'system'
  AND sd.doctor_id IS NULL
ON CONFLICT DO NOTHING;

-- Link GENERAL_EXAMINATION (order 8)
INSERT INTO consultation_type_segments (
    id,
    consultation_type_id,
    segment_code,
    segment_id,
    default_category,
    default_display_order,
    default_brevity_level,
    default_terminology_style,
    is_required_for_type,
    created_at,
    consultation_type_name
)
SELECT
    gen_random_uuid(),
    '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c',
    'GENERAL_EXAMINATION',
    sd.id,
    'core',
    8,
    'balanced',
    'medical_terms',
    false,
    NOW(),
    'OP_PSG_NEW'
FROM segment_definitions sd
WHERE sd.segment_code = 'GENERAL_EXAMINATION'
  AND sd.segment_type = 'system'
  AND sd.doctor_id IS NULL
ON CONFLICT DO NOTHING;

-- Link SYSTEMIC_EXAMINATION (order 9)
INSERT INTO consultation_type_segments (
    id,
    consultation_type_id,
    segment_code,
    segment_id,
    default_category,
    default_display_order,
    default_brevity_level,
    default_terminology_style,
    is_required_for_type,
    created_at,
    consultation_type_name
)
SELECT
    gen_random_uuid(),
    '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c',
    'SYSTEMIC_EXAMINATION',
    sd.id,
    'core',
    9,
    'balanced',
    'medical_terms',
    false,
    NOW(),
    'OP_PSG_NEW'
FROM segment_definitions sd
WHERE sd.segment_code = 'SYSTEMIC_EXAMINATION'
  AND sd.segment_type = 'system'
  AND sd.doctor_id IS NULL
ON CONFLICT DO NOTHING;

-- Link SURGICAL_EXAMINATION (order 10)
INSERT INTO consultation_type_segments (
    id,
    consultation_type_id,
    segment_code,
    segment_id,
    default_category,
    default_display_order,
    default_brevity_level,
    default_terminology_style,
    is_required_for_type,
    created_at,
    consultation_type_name
)
SELECT
    gen_random_uuid(),
    '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c',
    'SURGICAL_EXAMINATION',
    sd.id,
    'core',
    10,
    'balanced',
    'medical_terms',
    false,
    NOW(),
    'OP_PSG_NEW'
FROM segment_definitions sd
WHERE sd.segment_code = 'SURGICAL_EXAMINATION'
  AND sd.segment_type = 'system'
  AND sd.doctor_id IS NULL
ON CONFLICT DO NOTHING;

-- Link PROCEDURE_NOTES (order 11)
INSERT INTO consultation_type_segments (
    id,
    consultation_type_id,
    segment_code,
    segment_id,
    default_category,
    default_display_order,
    default_brevity_level,
    default_terminology_style,
    is_required_for_type,
    created_at,
    consultation_type_name
)
SELECT
    gen_random_uuid(),
    '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c',
    'PROCEDURE_NOTES',
    sd.id,
    'additional',
    11,
    'balanced',
    'medical_terms',
    false,
    NOW(),
    'OP_PSG_NEW'
FROM segment_definitions sd
WHERE sd.segment_code = 'PROCEDURE_NOTES'
  AND sd.segment_type = 'system'
  AND sd.doctor_id IS NULL
ON CONFLICT DO NOTHING;

-- Link VISIT_SUMMARY (order 12)
INSERT INTO consultation_type_segments (
    id,
    consultation_type_id,
    segment_code,
    segment_id,
    default_category,
    default_display_order,
    default_brevity_level,
    default_terminology_style,
    is_required_for_type,
    created_at,
    consultation_type_name
)
SELECT
    gen_random_uuid(),
    '5dfb8801-6a81-4b1e-8e44-5873e97c1f1c',
    'VISIT_SUMMARY',
    sd.id,
    'additional',
    12,
    'balanced',
    'medical_terms',
    false,
    NOW(),
    'OP_PSG_NEW'
FROM segment_definitions sd
WHERE sd.segment_code = 'VISIT_SUMMARY'
  AND sd.segment_type = 'system'
  AND sd.doctor_id IS NULL
ON CONFLICT DO NOTHING;

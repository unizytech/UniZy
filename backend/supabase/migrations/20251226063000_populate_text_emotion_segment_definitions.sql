-- Migration: Populate TEXT_EMOTION_ segment definitions with full prompts and schemas
-- These prompts were previously hardcoded in backend/services/emotion_prompts.py
-- Now they are stored in segment_definitions for database-driven assembly
-- Note: segment_code is NOT unique, so we use WHERE NOT EXISTS for idempotency

-- =============================================================================
-- TEXT_EMOTION_ANXIETY_PRE_CONSULTATION
-- =============================================================================
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    description,
    prompt_section_text,
    schema_definition_json,
    is_active,
    display_order,
    segment_type
)
SELECT
    'TEXT_EMOTION_ANXIETY_PRE_CONSULTATION',
    'Pre-Consultation Anxiety (Text)',
    'Analyze patient anxiety levels at the start of the consultation based on transcript text',
    '### Pre-Consultation Anxiety Assessment

Analyze the patient''s anxiety level at the **beginning** of the consultation (first 2-3 minutes of transcript).

**What to Look For:**
- Speech patterns: rapid, hesitant, repetitive questioning
- Excessive reassurance-seeking ("Is it serious?", "Will I be okay?")
- Tone indicators in word choice (worried, concerned, scared)
- Physical symptoms mentioned (trembling, can''t sleep, palpitations)
- Worry expressions about diagnosis, treatment, or outcomes

**Severity Levels (use exactly):**
- **None**: Calm, confident, well-prepared patient
- **Mild**: Slight nervousness but composed and functional
- **Moderate**: Noticeable anxiety requiring reassurance, may affect communication
- **Severe**: High distress, difficulty focusing, overwhelming worry

**Required Output:**
- `level`: Severity (None/Mild/Moderate/Severe)
- `indicators`: Array of specific quotes or behaviors from transcript
- `timestamp_start`: Approximate time range analyzed (e.g., "00:00-02:00")
- `confidence`: Your confidence in this assessment (Low/Medium/High)
- `notes`: Any additional clinical observations',
    '{
        "type": "object",
        "properties": {
            "level": {
                "type": "string",
                "description": "Anxiety severity at consultation start (None, Mild, Moderate, Severe)"
            },
            "indicators": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific behaviors or statements indicating anxiety"
            },
            "timestamp_start": {
                "type": "string",
                "description": "Approximate timestamp when assessment begins (e.g., 00:00-02:00)"
            },
            "confidence": {
                "type": "string",
                "description": "Confidence in this assessment (Low, Medium, High)"
            },
            "notes": {
                "type": "string",
                "description": "Additional clinical observations"
            }
        },
        "required": ["level", "indicators", "confidence"]
    }'::jsonb,
    true,
    101,
    'system'
WHERE NOT EXISTS (
    SELECT 1 FROM segment_definitions WHERE segment_code = 'TEXT_EMOTION_ANXIETY_PRE_CONSULTATION'
);

-- =============================================================================
-- TEXT_EMOTION_ANXIETY_POST_CONSULTATION
-- =============================================================================
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    description,
    prompt_section_text,
    schema_definition_json,
    is_active,
    display_order,
    segment_type
)
SELECT
    'TEXT_EMOTION_ANXIETY_POST_CONSULTATION',
    'Post-Consultation Anxiety (Text)',
    'Analyze patient anxiety levels at the end of the consultation and track trajectory',
    '### Post-Consultation Anxiety Assessment

Analyze the patient''s anxiety level at the **end** of the consultation (last 2-3 minutes of transcript).

**What to Look For:**
- Same indicators as pre-consultation, but focus on the ending
- Signs of resolution: calmer language, fewer questions, expression of relief
- Signs of escalation: new worries, unresolved concerns, confusion
- Response to doctor''s reassurances or explanations

**Severity Levels (use exactly):**
- **None**: Calm, confident, questions resolved
- **Mild**: Slight residual nervousness but manageable
- **Moderate**: Still anxious despite consultation
- **Severe**: Leaving more distressed than when they arrived

**Trajectory Assessment:**
Compare to pre-consultation and determine:
- **Improved**: Anxiety decreased during consultation
- **Stable**: Anxiety remained about the same
- **Worsened**: Anxiety increased during consultation

**Required Output:**
- `level`: Severity (None/Mild/Moderate/Severe)
- `indicators`: Array of specific quotes or behaviors from transcript end
- `timestamp_end`: Approximate time range analyzed
- `confidence`: Your confidence in this assessment (Low/Medium/High)
- `change_from_pre`: Trajectory (Improved/Stable/Worsened)
- `notes`: Any additional clinical observations',
    '{
        "type": "object",
        "properties": {
            "level": {
                "type": "string",
                "description": "Anxiety severity at consultation end (None, Mild, Moderate, Severe)"
            },
            "indicators": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific behaviors or statements indicating anxiety"
            },
            "timestamp_end": {
                "type": "string",
                "description": "Approximate timestamp when assessment ends"
            },
            "confidence": {
                "type": "string",
                "description": "Confidence in this assessment (Low, Medium, High)"
            },
            "change_from_pre": {
                "type": "string",
                "description": "How anxiety changed from pre to post consultation (Improved, Stable, Worsened)"
            },
            "notes": {
                "type": "string",
                "description": "Additional clinical observations"
            }
        },
        "required": ["level", "indicators", "confidence", "change_from_pre"]
    }'::jsonb,
    true,
    102,
    'system'
WHERE NOT EXISTS (
    SELECT 1 FROM segment_definitions WHERE segment_code = 'TEXT_EMOTION_ANXIETY_POST_CONSULTATION'
);

-- =============================================================================
-- TEXT_EMOTION_OTHER_EMOTIONS_DETECTED
-- =============================================================================
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    description,
    prompt_section_text,
    schema_definition_json,
    is_active,
    display_order,
    segment_type
)
SELECT
    'TEXT_EMOTION_OTHER_EMOTIONS_DETECTED',
    'Other Emotions Detected (Text)',
    'Detect medically relevant emotions beyond anxiety from transcript text',
    '### Other Medically Relevant Emotions

Identify emotions beyond anxiety that may impact clinical care.

**Emotion Categories (use these exact names):**
- **Fear**: Phobias (needles, procedures, hospitalization), fear of death/disability/chronic illness, panic about symptoms
- **Anger**: Frustration with healthcare system, costs, access barriers, prior treatment failures, symptom progression
- **Sadness**: Flat affect, hopelessness, loss of interest in treatment, withdrawal from care decisions. **Flag suicidal ideation as CRITICAL if present.**
- **Distress**: Emotional suffering beyond normal concern, difficulty coping, feeling overwhelmed
- **Relief**: After reassurance or diagnosis, gratitude for care
- **Hope**: Optimism about recovery, positive outlook on treatment

**For Each Emotion Found:**
- Identify the specific emotion from the list above
- Rate severity: Mild, Moderate, or Severe
- Provide evidence (quotes or behaviors)
- Assess clinical significance:
  - **High**: Directly impacts treatment decisions or compliance
  - **Medium**: May affect outcomes, worth monitoring
  - **Low**: Present but unlikely to affect care

**Required Output:**
- `emotions_detected`: Array of emotion objects with emotion/severity/evidence/clinical_significance
- `dominant_emotion`: Most prominent emotion throughout consultation
- `notes`: Any additional observations',
    '{
        "type": "object",
        "properties": {
            "emotions_detected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "emotion": {
                            "type": "string",
                            "description": "Emotion name (Fear, Anger, Sadness, Distress, Relief, Hope)"
                        },
                        "severity": {
                            "type": "string",
                            "description": "Severity of this emotion (Mild, Moderate, Severe)"
                        },
                        "evidence": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific statements or behaviors"
                        },
                        "clinical_significance": {
                            "type": "string",
                            "description": "Impact on treatment compliance or outcomes (High, Medium, Low)"
                        }
                    },
                    "required": ["emotion", "severity", "evidence", "clinical_significance"]
                },
                "description": "List of all emotions detected with evidence"
            },
            "dominant_emotion": {
                "type": "string",
                "description": "Most prominent emotion throughout consultation"
            },
            "notes": {
                "type": "string",
                "description": "Additional observations"
            }
        },
        "required": ["emotions_detected"]
    }'::jsonb,
    true,
    103,
    'system'
WHERE NOT EXISTS (
    SELECT 1 FROM segment_definitions WHERE segment_code = 'TEXT_EMOTION_OTHER_EMOTIONS_DETECTED'
);

-- =============================================================================
-- TEXT_EMOTION_FINANCIAL_CONCERNS
-- =============================================================================
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    description,
    prompt_section_text,
    schema_definition_json,
    is_active,
    display_order,
    segment_type
)
SELECT
    'TEXT_EMOTION_FINANCIAL_CONCERNS',
    'Financial Concerns (Text)',
    'Identify financial barriers to treatment from transcript text',
    '### Financial Concerns Assessment

Identify barriers to treatment due to cost concerns.

**Direct Indicators:**
- Explicit questions about cost ("How much will this cost?")
- Requests for generic medications
- Concerns about insurance coverage
- Mentions of financial hardship

**Indirect Indicators:**
- Hesitation when expensive treatment mentioned
- Questions about necessity of tests ("Do I really need this?")
- Delaying care decisions
- Seeking payment plans or installment options

**Alternative Treatment Requests:**
- Asking for cheaper options
- Questioning if less expensive alternatives exist
- Willing to skip recommended procedures due to cost

**Severity Levels (use exactly):**
- **None**: No financial concerns expressed or indicated
- **Mild**: Minor concerns but unlikely to affect treatment decisions
- **Moderate**: Noticeable financial stress, may affect some treatment choices
- **Severe**: Likely to skip or delay essential treatment due to cost

**Required Output:**
- `concerns_present`: Boolean - were any concerns detected?
- `severity`: None/Mild/Moderate/Severe
- `specific_concerns`: Array of concern objects with type/evidence/impact
- `alternative_treatment_requested`: Did patient ask for cheaper options?
- `notes`: Additional context',
    '{
        "type": "object",
        "properties": {
            "concerns_present": {
                "type": "boolean",
                "description": "Were any financial concerns detected?"
            },
            "severity": {
                "type": "string",
                "description": "Severity of financial concerns (None, Mild, Moderate, Severe)"
            },
            "specific_concerns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "concern_type": {
                            "type": "string",
                            "description": "Type of financial concern (Treatment cost, Medication cost, Test/procedure cost, Insurance coverage, Alternative options, Payment plans, Other)"
                        },
                        "evidence": {
                            "type": "string",
                            "description": "Patient statement or behavior indicating concern"
                        },
                        "impact_on_compliance": {
                            "type": "string",
                            "description": "Likelihood of affecting treatment adherence (High risk, Moderate risk, Low risk)"
                        }
                    },
                    "required": ["concern_type", "evidence"]
                },
                "description": "List of specific financial concerns"
            },
            "alternative_treatment_requested": {
                "type": "boolean",
                "description": "Did patient request cheaper alternatives?"
            },
            "notes": {
                "type": "string",
                "description": "Additional context"
            }
        },
        "required": ["concerns_present", "severity"]
    }'::jsonb,
    true,
    104,
    'system'
WHERE NOT EXISTS (
    SELECT 1 FROM segment_definitions WHERE segment_code = 'TEXT_EMOTION_FINANCIAL_CONCERNS'
);

-- =============================================================================
-- TEXT_EMOTION_TREATMENT_COMPLIANCE_LIKELIHOOD
-- =============================================================================
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    description,
    prompt_section_text,
    schema_definition_json,
    is_active,
    display_order,
    segment_type
)
SELECT
    'TEXT_EMOTION_TREATMENT_COMPLIANCE_LIKELIHOOD',
    'Treatment Compliance Likelihood (Text)',
    'Predict likelihood of following treatment plan based on transcript indicators',
    '### Treatment Compliance Likelihood Assessment

Predict likelihood of patient following the complete treatment plan.

**Positive Factors (supporting compliance):**
- Understanding of treatment importance demonstrated
- Explicit commitment to follow instructions
- Questions about proper adherence ("How exactly should I take this?")
- Support system mentioned (family helping)
- Financial resources appear adequate
- Clear follow-up scheduled and acknowledged

**Negative Factors (barriers to compliance):**
- Resistance or skepticism about treatment
- Expressed doubts about necessity
- Financial barriers identified
- Logistical challenges mentioned (work, transportation, childcare)
- Poor understanding of instructions evident
- History of non-compliance mentioned
- No follow-up arranged or declined

**Key Barrier Types:**
- **Financial**: Cannot afford treatment
- **Logistical**: Practical challenges accessing care
- **Understanding**: Doesn''t comprehend importance
- **Motivation**: Lacks belief in treatment efficacy
- **Fear/Anxiety**: Too anxious about treatment side effects
- **Social Support**: Lacks help with care management

**Assessment Levels (use exactly):**
- **High**: Strong commitment, resources available, good understanding
- **Moderate**: Some concerns but likely to comply with most recommendations
- **Low**: Multiple barriers, significant doubts about following through
- **Very Low**: Unlikely to follow plan without significant intervention

**Required Output:**
- `likelihood`: High/Moderate/Low/Very Low
- `positive_factors`: Array of supporting factors
- `negative_factors`: Array of barriers
- `key_barriers`: Array of barrier objects with type/severity/evidence
- `recommendations`: Suggestions to improve compliance
- `confidence`: Your confidence (Low/Medium/High)
- `notes`: Additional observations',
    '{
        "type": "object",
        "properties": {
            "likelihood": {
                "type": "string",
                "description": "Overall likelihood of treatment compliance (High, Moderate, Low, Very Low)"
            },
            "positive_factors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Factors supporting compliance"
            },
            "negative_factors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Barriers to compliance"
            },
            "key_barriers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "barrier_type": {
                            "type": "string",
                            "description": "Type of barrier (Financial, Logistical, Understanding, Motivation, Fear/Anxiety, Social support, Other)"
                        },
                        "severity": {
                            "type": "string",
                            "description": "Impact of this barrier (Minor, Moderate, Major)"
                        },
                        "evidence": {
                            "type": "string",
                            "description": "Specific evidence from consultation"
                        }
                    },
                    "required": ["barrier_type", "severity"]
                },
                "description": "Primary barriers to compliance"
            },
            "recommendations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Suggestions to improve compliance (e.g., follow-up call, financial assistance referral)"
            },
            "confidence": {
                "type": "string",
                "description": "Confidence in this assessment (Low, Medium, High)"
            },
            "notes": {
                "type": "string",
                "description": "Additional observations"
            }
        },
        "required": ["likelihood", "positive_factors", "negative_factors", "confidence"]
    }'::jsonb,
    true,
    105,
    'system'
WHERE NOT EXISTS (
    SELECT 1 FROM segment_definitions WHERE segment_code = 'TEXT_EMOTION_TREATMENT_COMPLIANCE_LIKELIHOOD'
);

-- =============================================================================
-- TEXT_EMOTION_DOCTOR_COMMUNICATION_STYLE
-- =============================================================================
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    description,
    prompt_section_text,
    schema_definition_json,
    is_active,
    display_order,
    segment_type
)
SELECT
    'TEXT_EMOTION_DOCTOR_COMMUNICATION_STYLE',
    'Doctor Communication Style (Text)',
    'Analyze doctor communication approach and its impact on patient',
    '### Doctor Communication Style Assessment

Analyze the doctor''s communication approach throughout the consultation.

**Style Categories (use these exact terms):**

*Positive Styles:*
- **Empathetic**: Warm, validating, emotionally attuned, acknowledges feelings, uses statements like "I understand", "That must be difficult"
- **Collaborative**: Shared decision-making, patient-centered, asks for input, encourages questions

*Neutral Styles:*
- **Clinical**: Professional, information-focused, efficient, fact-based, neutral tone
- **Authoritative**: Directive, confident, decision-maker, leads conversation (can be reassuring in appropriate contexts)

*Negative Styles:*
- **Rushed**: Time-pressured, abbreviated explanations, limited engagement, interrupts patient
- **Dismissive**: Minimizes patient concerns, interrupts frequently, doesn''t acknowledge emotions, condescending tone
- **Detached**: Emotionally unavailable, no warmth, mechanical delivery, patient feels uncared for
- **Evasive**: Avoids direct answers, deflects questions, vague explanations, increases patient anxiety through uncertainty

**Key Indicators to Assess:**
- Use of empathetic statements vs dismissive responses
- Medical jargon level and explanation quality
- Active listening signals (reflecting back, summarizing) vs interrupting
- Reassurance timing and effectiveness
- Response to patient concerns and questions
- Time given for patient to ask questions
- Explanation of treatment rationale vs vague answers

**Impact Assessment:**
- How doctor''s style affected patient anxiety (Reduced, No effect, Increased)
- Clarity of treatment plan communication
- Trust-building effectiveness
- Whether patient concerns were adequately addressed

**Required Output:**
- `primary_style`: Dominant style from list above
- `secondary_style`: Secondary style if applicable
- `empathy_indicators`: Specific empathetic statements observed
- `communication_strengths`: Positive aspects
- `areas_for_improvement`: What could be better
- `patient_anxiety_impact`: Reduced/No effect/Increased
- `clarity_rating`: Excellent/Good/Fair/Poor
- `active_listening_rating`: Excellent/Good/Fair/Poor
- `reassurance_effectiveness`: High/Medium/Low/None attempted
- `patient_concerns_addressed`: Fully/Mostly/Partially/Not addressed
- `style_consistency`: Highly consistent/Mostly consistent/Variable
- `evidence`: Specific quotes demonstrating style
- `clinical_significance`: High/Medium/Low
- `recommendations`: Improvement suggestions if applicable
- `confidence`: Your confidence (Low/Medium/High)',
    '{
        "type": "object",
        "properties": {
            "primary_style": {
                "type": "string",
                "description": "Dominant communication style (Empathetic, Collaborative, Clinical, Authoritative, Rushed, Dismissive, Detached, Evasive)"
            },
            "secondary_style": {
                "type": "string",
                "description": "Secondary communication style if applicable"
            },
            "empathy_indicators": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific empathetic statements or behaviors observed"
            },
            "communication_strengths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Positive aspects of doctor''s communication"
            },
            "areas_for_improvement": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Communication aspects that could be enhanced"
            },
            "patient_anxiety_impact": {
                "type": "string",
                "description": "How doctor''s style affected patient anxiety (Reduced, No effect, Increased)"
            },
            "clarity_rating": {
                "type": "string",
                "description": "Medical explanation clarity (Excellent, Good, Fair, Poor)"
            },
            "active_listening_rating": {
                "type": "string",
                "description": "Active listening quality (Excellent, Good, Fair, Poor)"
            },
            "reassurance_effectiveness": {
                "type": "string",
                "description": "How effective were reassurance attempts (High, Medium, Low, None attempted)"
            },
            "patient_concerns_addressed": {
                "type": "string",
                "description": "Were patient concerns adequately addressed (Fully, Mostly, Partially, Not addressed)"
            },
            "style_consistency": {
                "type": "string",
                "description": "Was communication style consistent (Highly consistent, Mostly consistent, Variable)"
            },
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific quotes or behaviors demonstrating communication style"
            },
            "clinical_significance": {
                "type": "string",
                "description": "Impact on patient care (High, Medium, Low)"
            },
            "recommendations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Suggestions for communication improvement if applicable"
            },
            "confidence": {
                "type": "string",
                "description": "Confidence in this assessment (Low, Medium, High)"
            }
        },
        "required": ["primary_style", "empathy_indicators", "patient_anxiety_impact", "clarity_rating", "confidence"]
    }'::jsonb,
    true,
    106,
    'system'
WHERE NOT EXISTS (
    SELECT 1 FROM segment_definitions WHERE segment_code = 'TEXT_EMOTION_DOCTOR_COMMUNICATION_STYLE'
);

-- Log completion
DO $$
BEGIN
    RAISE NOTICE 'TEXT_EMOTION segment definitions populated successfully';
END $$;

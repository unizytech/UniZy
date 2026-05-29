-- Migration: Populate AUDIO_ segment definitions with full prompts and schemas
-- These prompts were previously hardcoded in backend/services/audio_emotion_prompts.py

-- =============================================================================
-- AUDIO_PATIENT_ANXIETY
-- =============================================================================
UPDATE segment_definitions
SET
    prompt_section_text = '### Patient Voice Anxiety Analysis

Assess anxiety levels based on voice characteristics:

**Severity Levels:**
- **None**: Calm, steady voice, normal pace
- **Mild**: Slight tension, occasional hesitation
- **Moderate**: Noticeable voice changes, frequent pace shifts
- **Severe**: Significant tremor, voice breaks, extreme pace changes

**Key Indicators to Listen For:**
- Voice tremor or shakiness
- Pitch variations (higher pitch = stress)
- Speech rate changes (rushed = anxiety, slowed = processing)
- Breath patterns (shallow, sighing, catching breath)
- Voice breaks or emotional catches

**Trajectory Assessment:**
- Compare voice in first 2-3 minutes vs last 2-3 minutes
- Determine if anxiety: Improved, Stable, or Worsened

**Output Requirements:**
- initial_anxiety_level: Anxiety from voice at consultation start (None, Mild, Moderate, Severe)
- final_anxiety_level: Anxiety from voice at consultation end (None, Mild, Moderate, Severe)
- anxiety_trajectory: How anxiety changed (Improved, Stable, Worsened)
- rationale: One-line explanation of voice evidence supporting this assessment
- confidence: Confidence in voice-based assessment (Low, Medium, High)',

    schema_definition_json = '{
        "type": "object",
        "description": "Patient anxiety assessment from voice analysis",
        "properties": {
            "initial_anxiety_level": {
                "type": "string",
                "description": "Anxiety level from voice at consultation start (None, Mild, Moderate, Severe)",
                "enum": ["None", "Mild", "Moderate", "Severe"]
            },
            "final_anxiety_level": {
                "type": "string",
                "description": "Anxiety level from voice at consultation end (None, Mild, Moderate, Severe)",
                "enum": ["None", "Mild", "Moderate", "Severe"]
            },
            "anxiety_trajectory": {
                "type": "string",
                "description": "How anxiety changed from start to end (Improved, Stable, Worsened)",
                "enum": ["Improved", "Stable", "Worsened"]
            },
            "rationale": {
                "type": "string",
                "description": "One-line explanation of voice evidence supporting this assessment"
            },
            "confidence": {
                "type": "string",
                "description": "Confidence in voice-based assessment (Low, Medium, High)",
                "enum": ["Low", "Medium", "High"]
            }
        },
        "required": ["initial_anxiety_level", "final_anxiety_level", "anxiety_trajectory", "rationale", "confidence"]
    }'::jsonb,
    updated_at = NOW()
WHERE segment_code = 'AUDIO_PATIENT_ANXIETY';

-- =============================================================================
-- AUDIO_DOCTOR_STYLE
-- =============================================================================
UPDATE segment_definitions
SET
    prompt_section_text = '### Doctor Voice Communication Style

**Primary Style Categories (use these exact terms):**

*Positive Styles:*
- **Empathetic**: Soft tone, slower pace, voice matching patient distress, warm delivery
- **Collaborative**: Questioning tone, pauses for patient input, encouraging responses

*Neutral Styles:*
- **Clinical**: Neutral tone, efficient pace, information-focused, professional
- **Authoritative**: Confident tone, directive language (can be reassuring)

*Negative Styles:*
- **Rushed**: Fast pace, incomplete explanations, interrupts patient
- **Dismissive**: Dismisses concerns in tone, sighs, condescending voice, talks over patient
- **Detached**: Cold/mechanical tone, emotionally unavailable, no warmth in voice
- **Evasive**: Hesitant answers, vague tone, avoids direct responses

**Voice Warmth Levels:**
- Cold, Neutral, Warm, Very Warm

**Key Indicators:**
- Tone consistency throughout consultation
- Voice softening when patient shows distress
- Pace appropriateness for patient comprehension
- Reassurance delivery effectiveness

**Output Requirements:**
- primary_style: Dominant voice-based communication style
- voice_warmth: Overall warmth in voice (Cold, Neutral, Warm, Very Warm)
- tone_consistency: How consistent was the tone
- rationale: One-line explanation of voice evidence supporting this assessment
- confidence: Confidence in voice-based assessment (Low, Medium, High)',

    schema_definition_json = '{
        "type": "object",
        "description": "Doctor communication style assessment from voice analysis",
        "properties": {
            "primary_style": {
                "type": "string",
                "description": "Dominant voice-based communication style",
                "enum": ["Empathetic", "Collaborative", "Clinical", "Authoritative", "Rushed", "Dismissive", "Detached", "Evasive"]
            },
            "voice_warmth": {
                "type": "string",
                "description": "Overall warmth in voice",
                "enum": ["Cold", "Neutral", "Warm", "Very Warm"]
            },
            "tone_consistency": {
                "type": "string",
                "description": "How consistent was the tone throughout consultation",
                "enum": ["Highly consistent", "Mostly consistent", "Variable", "Inconsistent"]
            },
            "rationale": {
                "type": "string",
                "description": "One-line explanation of voice evidence supporting this assessment"
            },
            "confidence": {
                "type": "string",
                "description": "Confidence in voice-based assessment (Low, Medium, High)",
                "enum": ["Low", "Medium", "High"]
            }
        },
        "required": ["primary_style", "voice_warmth", "tone_consistency", "rationale", "confidence"]
    }'::jsonb,
    updated_at = NOW()
WHERE segment_code = 'AUDIO_DOCTOR_STYLE';

-- =============================================================================
-- AUDIO_INTERACTION_DYNAMICS
-- =============================================================================
UPDATE segment_definitions
SET
    prompt_section_text = '### Voice Interaction Dynamics

**Turn-Taking Balance:**
- Doctor-dominated, Balanced, or Patient-dominated
- Assess if balance is appropriate for the consultation type

**Conversation Flow:**
- Natural: Smooth transitions, appropriate pauses
- Mostly natural: Minor hesitations but generally flows well
- Somewhat stilted: Noticeable awkward pauses or interruptions
- Stilted: Frequent interruptions, long awkward silences

**Mutual Engagement:**
- High: Both parties actively engaged, responsive
- Medium: Adequate engagement with some disengagement moments
- Low: One or both parties seem disengaged

**Output Requirements:**
- turn_taking_balance: Balance assessment (Doctor-dominated, Balanced, Patient-dominated)
- conversation_flow: Overall conversation flow quality
- mutual_engagement: Level of mutual engagement (High, Medium, Low)
- rationale: One-line explanation of interaction patterns observed
- confidence: Confidence in assessment (Low, Medium, High)',

    schema_definition_json = '{
        "type": "object",
        "description": "Interaction dynamics assessment from voice analysis",
        "properties": {
            "turn_taking_balance": {
                "type": "string",
                "description": "Balance assessment of who dominated the conversation",
                "enum": ["Doctor-dominated", "Balanced", "Patient-dominated"]
            },
            "conversation_flow": {
                "type": "string",
                "description": "Overall conversation flow quality",
                "enum": ["Natural", "Mostly natural", "Somewhat stilted", "Stilted"]
            },
            "mutual_engagement": {
                "type": "string",
                "description": "Level of mutual engagement between doctor and patient",
                "enum": ["High", "Medium", "Low"]
            },
            "rationale": {
                "type": "string",
                "description": "One-line explanation of interaction patterns observed"
            },
            "confidence": {
                "type": "string",
                "description": "Confidence in assessment (Low, Medium, High)",
                "enum": ["Low", "Medium", "High"]
            }
        },
        "required": ["turn_taking_balance", "conversation_flow", "mutual_engagement", "rationale", "confidence"]
    }'::jsonb,
    updated_at = NOW()
WHERE segment_code = 'AUDIO_INTERACTION_DYNAMICS';

-- =============================================================================
-- AUDIO_FINANCIAL_CONCERNS
-- =============================================================================
UPDATE segment_definitions
SET
    prompt_section_text = '### Financial Concern Voice Indicators

Detect financial anxiety through voice prosody when cost/payment topics arise:

**Severity Levels:**
- **None**: No voice change when financial topics discussed
- **Mild**: Subtle hesitation or slight pitch change
- **Moderate**: Clear voice stress indicators, noticeable pauses
- **Severe**: Significant voice changes, audible distress, avoidance patterns

**Key Voice Indicators:**
- Pitch elevation when cost mentioned
- Hesitation before responding to cost questions
- Increased filler words ("um", "uh") during payment discussions
- Voice tension or quieting when finances arise
- Avoidance of direct cost questions

**Output Requirements:**
- severity: Overall severity of financial concern from voice (None, Mild, Moderate, Severe)
- rationale: One-line explanation of voice evidence (e.g., "Voice tensed and pace slowed when medication cost mentioned")
- confidence: Confidence in assessment (Low, Medium, High)',

    schema_definition_json = '{
        "type": "object",
        "description": "Financial concern indicators detected from voice prosody",
        "properties": {
            "severity": {
                "type": "string",
                "description": "Overall severity of financial concern from voice",
                "enum": ["None", "Mild", "Moderate", "Severe"]
            },
            "rationale": {
                "type": "string",
                "description": "One-line explanation of voice evidence supporting this assessment"
            },
            "confidence": {
                "type": "string",
                "description": "Confidence in assessment (Low, Medium, High)",
                "enum": ["Low", "Medium", "High"]
            }
        },
        "required": ["severity", "rationale", "confidence"]
    }'::jsonb,
    updated_at = NOW()
WHERE segment_code = 'AUDIO_FINANCIAL_CONCERNS';

-- =============================================================================
-- AUDIO_COMPLIANCE_INDICATORS
-- =============================================================================
UPDATE segment_definitions
SET
    prompt_section_text = '### Treatment Compliance Voice Indicators

Assess compliance likelihood from voice confidence:

**Likelihood Levels (use these exact terms):**
- **High**: Confident voice, immediate agreement, engaged tone
- **Moderate**: Some hesitation but generally positive
- **Low**: Frequent hesitation, flat responses, voice stress
- **Very Low**: Consistent reluctance signals, disengagement

**Key Indicators:**
- Firm vs hesitant agreement voice
- Immediate vs delayed acknowledgment
- Engaged vs flat tone when discussing treatment
- Voice trailing off or sighing when plan mentioned
- Enthusiasm vs reluctance in voice

**Output Requirements:**
- likelihood: Overall treatment compliance likelihood from voice (High, Moderate, Low, Very Low)
- rationale: One-line explanation of voice evidence (e.g., "Hesitant tone and delayed responses when agreeing to treatment plan")
- confidence: Confidence in assessment (Low, Medium, High)',

    schema_definition_json = '{
        "type": "object",
        "description": "Treatment compliance likelihood indicators from voice confidence analysis",
        "properties": {
            "likelihood": {
                "type": "string",
                "description": "Overall treatment compliance likelihood from voice",
                "enum": ["High", "Moderate", "Low", "Very Low"]
            },
            "rationale": {
                "type": "string",
                "description": "One-line explanation of voice evidence supporting this assessment"
            },
            "confidence": {
                "type": "string",
                "description": "Confidence in assessment (Low, Medium, High)",
                "enum": ["Low", "Medium", "High"]
            }
        },
        "required": ["likelihood", "rationale", "confidence"]
    }'::jsonb,
    updated_at = NOW()
WHERE segment_code = 'AUDIO_COMPLIANCE_INDICATORS';

-- =============================================================================
-- AUDIO_OTHER_EMOTIONS
-- =============================================================================
UPDATE segment_definitions
SET
    prompt_section_text = '### Other Emotions Voice Detection

Detect medically relevant emotions through voice prosody:

**Emotions to Detect (use these exact names):**
- **Fear**: Voice tremor, higher pitch, rushed speech
- **Anger**: Increased volume, faster pace, clipped responses
- **Sadness**: Flat affect, slower pace, soft voice, sighing
- **Relief**: Audible exhale, voice softening, pace normalization
- **Distress**: Voice cracking, irregular breathing, pitch instability
- **Hope**: Voice brightening, increased energy
- **None**: No dominant emotion detected, neutral throughout

**Identify the dominant emotion and the emotional trajectory: Improved, Stable, or Worsened.**

**Output Requirements:**
- dominant_emotion: Most prominent emotion throughout consultation (Fear, Anger, Sadness, Relief, Distress, Hope, or None if neutral)
- emotional_trajectory: How emotions changed from start to end (Improved, Stable, Worsened)
- rationale: One-line explanation of voice evidence for dominant emotion and trajectory
- confidence: Confidence in assessment (Low, Medium, High)',

    schema_definition_json = '{
        "type": "object",
        "description": "Other medically relevant emotions detected from voice prosody",
        "properties": {
            "dominant_emotion": {
                "type": "string",
                "description": "Most prominent emotion throughout consultation",
                "enum": ["Fear", "Anger", "Sadness", "Relief", "Distress", "Hope", "None"]
            },
            "emotional_trajectory": {
                "type": "string",
                "description": "How emotions changed from start to end",
                "enum": ["Improved", "Stable", "Worsened"]
            },
            "rationale": {
                "type": "string",
                "description": "One-line explanation of voice evidence for dominant emotion and trajectory"
            },
            "confidence": {
                "type": "string",
                "description": "Confidence in assessment (Low, Medium, High)",
                "enum": ["Low", "Medium", "High"]
            }
        },
        "required": ["dominant_emotion", "emotional_trajectory", "rationale", "confidence"]
    }'::jsonb,
    updated_at = NOW()
WHERE segment_code = 'AUDIO_OTHER_EMOTIONS';

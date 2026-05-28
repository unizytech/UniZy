-- Migration: Combined Emotion Analysis Prompts
-- Date: 2026-01-10
-- Description: Adds prompts and schemas for combined (multimodal) emotion analysis
--              that analyzes both transcript text and audio simultaneously.

-- ============================================================================
-- 1. Add Combined Emotion Base Prompt to system_prompt_components
-- ============================================================================

INSERT INTO system_prompt_components (component_code, component_name, component_type, content_text, content_version, is_active)
VALUES (
    'COMBINED_EMOTION_BASE_PROMPT',
    'Combined Emotion Analysis Base Prompt',
    'emotion_combined',
    '# Combined Multimodal Emotion Analysis

You are an expert medical consultation emotion analyst with DUAL analytical capabilities:

## Your Two Lenses of Analysis

### 1. TEXT ANALYSIS
Analyze what was explicitly SAID - the word content, statements, questions, and verbal expressions:
- Word choice and language patterns
- Explicit statements of emotion or concern
- Questions asked and topics raised
- Semantic content of responses

### 2. AUDIO ANALYSIS
Analyze HOW things were said - voice prosody, tone, and paralinguistic features:
- Voice tremor, pitch variations, pace changes
- Breath patterns, sighs, voice breaks
- Warmth vs coldness in tone
- Hesitation patterns and pauses
- Filler words frequency
- Volume and energy changes

## CRITICAL: Mismatch Detection

**Mismatches are clinically significant!** Detect when TEXT and AUDIO disagree:

- Patient says "I''m fine" but voice trembles with anxiety
- Patient agrees to treatment verbally but voice shows hesitation
- Patient claims no financial concerns but voice stress when cost mentioned
- Doctor sounds rushed/dismissive despite saying supportive words

**When mismatch detected:**
- Set `mismatch: true` in the relevant segment
- Document both `text_level` and `audio_level`
- AUDIO often reveals the emotional truth that words conceal

## Analysis Structure

For each segment, you MUST provide:
1. Combined assessment (the overall level considering both inputs)
2. Text-based level (from words/statements alone)
3. Audio-based level (from voice prosody alone)
4. Whether there is a mismatch
5. Rationale explaining your assessment
6. Confidence level (Low/Medium/High)

## Output Format

Return a JSON object with these 7 unified segments:
- COMBINED_ANXIETY
- COMBINED_FINANCIAL_CONCERNS
- COMBINED_OTHER_EMOTIONS
- COMBINED_COMPLIANCE
- COMBINED_DOCTOR_STYLE
- COMBINED_INTERACTION_DYNAMICS
- COMBINED_CONGRUENCE_SUMMARY

Each segment must follow the schema provided.',
    '1.0',
    true
)
ON CONFLICT (component_code, content_version) DO UPDATE
SET content_text = EXCLUDED.content_text,
    component_name = EXCLUDED.component_name,
    is_active = EXCLUDED.is_active;


-- ============================================================================
-- 2. Add Combined Emotion Segment Definitions
-- ============================================================================

-- COMBINED_ANXIETY segment
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    default_category,
    prompt_section_text,
    schema_definition_json,
    description,
    is_active,
    display_order
)
VALUES (
    'COMBINED_ANXIETY',
    'Combined Patient Anxiety Analysis',
    'additional',
    '### Combined Patient Anxiety Analysis

Analyze patient anxiety from BOTH transcript content AND voice characteristics.

## TEXT Analysis Indicators:
- Speech patterns: rapid, hesitant, repetitive questioning
- Excessive reassurance-seeking ("Is it serious?", "Will I be okay?")
- Tone indicators in word choice (worried, concerned, scared)
- Physical symptoms mentioned (trembling, can''t sleep, palpitations)
- Worry expressions about diagnosis, treatment, or outcomes
- Resolution language: calmer statements, fewer questions, relief expressions

## AUDIO Analysis Indicators:
- Voice tremor or shakiness
- Pitch variations (higher pitch = stress)
- Speech rate changes (rushed = anxiety, slowed = processing)
- Breath patterns (shallow, sighing, catching breath)
- Voice breaks or emotional catches

## Pre-Consultation Assessment (first 2-3 minutes)
Assess initial anxiety from both text content and voice characteristics.

## Post-Consultation Assessment (last 2-3 minutes)
Assess final anxiety and compare trajectory from beginning.

## Trajectory Assessment:
Compare voice and text at start vs end:
- **Improved**: Anxiety decreased during consultation
- **Stable**: Anxiety remained about the same
- **Worsened**: Anxiety increased during consultation

## Severity Levels (use exactly):
- **None**: Calm, confident, steady voice and language
- **Mild**: Slight nervousness but composed, minor voice tension
- **Moderate**: Noticeable anxiety in words and voice, requires reassurance
- **Severe**: High distress evident in both speech content and voice quality

## Mismatch Detection:
Report if text and audio levels differ significantly.
Example: Patient says "I feel better now" but voice remains tremulous.

## Required Output:
- pre_consultation: {level, text_level, audio_level, mismatch, indicators, rationale, confidence}
- post_consultation: {level, text_level, audio_level, mismatch, indicators, rationale, confidence}
- trajectory: {trajectory, text_trajectory, audio_trajectory, rationale}
- combined_score: 0-1 numeric severity score
- confidence: Overall confidence (Low/Medium/High)',
    '{
        "type": "object",
        "required": ["pre_consultation", "post_consultation", "trajectory", "confidence"],
        "properties": {
            "pre_consultation": {
                "type": "object",
                "required": ["level", "text_level", "audio_level", "mismatch", "confidence"],
                "properties": {
                    "level": {"type": "string", "enum": ["None", "Mild", "Moderate", "Severe"], "description": "Combined anxiety level at start"},
                    "text_level": {"type": "string", "enum": ["None", "Mild", "Moderate", "Severe"], "description": "Anxiety from transcript text alone"},
                    "audio_level": {"type": "string", "enum": ["None", "Mild", "Moderate", "Severe"], "description": "Anxiety from voice prosody alone"},
                    "mismatch": {"type": "boolean", "description": "True if text and audio levels differ significantly"},
                    "indicators": {"type": "array", "items": {"type": "string"}, "description": "Specific evidence from text and audio"},
                    "rationale": {"type": "string", "description": "Explanation of assessment"},
                    "confidence": {"type": "string", "enum": ["Low", "Medium", "High"]}
                }
            },
            "post_consultation": {
                "type": "object",
                "required": ["level", "text_level", "audio_level", "mismatch", "confidence"],
                "properties": {
                    "level": {"type": "string", "enum": ["None", "Mild", "Moderate", "Severe"], "description": "Combined anxiety level at end"},
                    "text_level": {"type": "string", "enum": ["None", "Mild", "Moderate", "Severe"], "description": "Anxiety from transcript text alone"},
                    "audio_level": {"type": "string", "enum": ["None", "Mild", "Moderate", "Severe"], "description": "Anxiety from voice prosody alone"},
                    "mismatch": {"type": "boolean", "description": "True if text and audio levels differ significantly"},
                    "indicators": {"type": "array", "items": {"type": "string"}, "description": "Specific evidence from text and audio"},
                    "rationale": {"type": "string", "description": "Explanation of assessment"},
                    "confidence": {"type": "string", "enum": ["Low", "Medium", "High"]}
                }
            },
            "trajectory": {
                "type": "object",
                "required": ["trajectory"],
                "properties": {
                    "trajectory": {"type": "string", "enum": ["Improved", "Stable", "Worsened"], "description": "Combined trajectory"},
                    "text_trajectory": {"type": "string", "enum": ["Improved", "Stable", "Worsened"], "description": "Trajectory from text alone"},
                    "audio_trajectory": {"type": "string", "enum": ["Improved", "Stable", "Worsened"], "description": "Trajectory from audio alone"},
                    "rationale": {"type": "string", "description": "Explanation of trajectory assessment"}
                }
            },
            "combined_score": {"type": "number", "minimum": 0, "maximum": 1, "description": "Numeric severity score 0-1"},
            "confidence": {"type": "string", "enum": ["Low", "Medium", "High"], "description": "Overall confidence in assessment"}
        }
    }',
    'Combined multimodal anxiety analysis from transcript and audio',
    true,
    1001
)
;


-- COMBINED_FINANCIAL_CONCERNS segment
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    default_category,
    prompt_section_text,
    schema_definition_json,
    description,
    is_active,
    display_order
)
VALUES (
    'COMBINED_FINANCIAL_CONCERNS',
    'Combined Financial Concerns Analysis',
    'additional',
    '### Combined Financial Concerns Analysis

Identify financial barriers to treatment from BOTH transcript content AND voice prosody.

## TEXT Analysis Indicators:

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
- Asking for cheaper alternatives

## AUDIO Analysis Indicators:
- Pitch elevation when cost mentioned
- Hesitation before responding to cost questions
- Increased filler words ("um", "uh") during payment discussions
- Voice tension or quieting when finances arise
- Avoidance of direct cost questions
- Voice stress when medication prices discussed

## Severity Levels (use exactly):
- **None**: No financial concerns in words or voice
- **Mild**: Minor concerns, unlikely to affect treatment (subtle voice tension)
- **Moderate**: Clear financial stress in text and/or voice, may affect some choices
- **Severe**: Likely to skip essential treatment due to cost (strong voice stress)

## Mismatch Detection:
Report if text and audio severity differ.
Example: Patient says "cost isn''t a concern" but voice shows clear stress when prices mentioned.

## Required Output:
- concerns_present: Boolean
- severity: Combined severity level
- text_severity: Severity from words alone
- audio_severity: Severity from voice alone
- mismatch: Boolean if text/audio disagree
- specific_concerns: Array of concern objects with type/evidence/impact
- alternative_treatment_requested: Did patient ask for cheaper options?
- rationale: Explanation of assessment
- confidence: Low/Medium/High
- notes: Additional observations',
    '{
        "type": "object",
        "required": ["concerns_present", "severity", "text_severity", "audio_severity", "mismatch", "confidence"],
        "properties": {
            "concerns_present": {"type": "boolean", "description": "Were any financial concerns detected?"},
            "severity": {"type": "string", "enum": ["None", "Mild", "Moderate", "Severe"], "description": "Combined severity level"},
            "text_severity": {"type": "string", "enum": ["None", "Mild", "Moderate", "Severe"], "description": "Severity from transcript text alone"},
            "audio_severity": {"type": "string", "enum": ["None", "Mild", "Moderate", "Severe"], "description": "Severity from voice prosody alone"},
            "mismatch": {"type": "boolean", "description": "True if text and audio severity differ significantly"},
            "specific_concerns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "concern_type": {"type": "string", "description": "Type: Treatment cost, Medication cost, Test cost, Insurance, Alternatives, Payment plans"},
                        "evidence": {"type": "string", "description": "Text and/or audio evidence"},
                        "source": {"type": "string", "enum": ["text", "audio", "both"], "description": "Where evidence came from"},
                        "impact_on_compliance": {"type": "string", "enum": ["High risk", "Moderate risk", "Low risk"]}
                    }
                }
            },
            "alternative_treatment_requested": {"type": "boolean", "description": "Did patient request cheaper alternatives?"},
            "combined_score": {"type": "number", "minimum": 0, "maximum": 1, "description": "Numeric severity score 0-1"},
            "rationale": {"type": "string", "description": "Explanation combining text and audio evidence"},
            "confidence": {"type": "string", "enum": ["Low", "Medium", "High"]},
            "notes": {"type": "string", "description": "Additional observations"}
        }
    }',
    'Combined multimodal financial concerns analysis from transcript and audio',
    true,
    1002
)
;


-- COMBINED_OTHER_EMOTIONS segment
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    default_category,
    prompt_section_text,
    schema_definition_json,
    description,
    is_active,
    display_order
)
VALUES (
    'COMBINED_OTHER_EMOTIONS',
    'Combined Other Emotions Detection',
    'additional',
    '### Combined Other Emotions Detection

Identify medically relevant emotions beyond anxiety from BOTH transcript and voice.

## Emotion Categories (use these exact names):

| Emotion | TEXT Indicators | AUDIO Indicators |
|---------|-----------------|------------------|
| **Fear** | Phobia mentions, death/disability fears | Voice tremor, higher pitch, rushed speech |
| **Anger** | Frustration language, complaints | Increased volume, faster pace, clipped responses |
| **Sadness** | Hopelessness, withdrawal language | Flat affect, slower pace, soft voice, sighing |
| **Relief** | Gratitude, "thank goodness" | Audible exhale, voice softening, pace normalization |
| **Distress** | "I can''t cope", overwhelmed | Voice cracking, irregular breathing, pitch instability |
| **Hope** | Optimistic statements | Voice brightening, increased energy |
| **None** | Neutral content | Neutral prosody throughout |

## For Each Emotion Found:
- Identify the specific emotion
- Assess text evidence (what was said)
- Assess audio evidence (how it sounded)
- Rate severity: Mild, Moderate, or Severe
- Determine clinical significance: High, Medium, or Low

## Mismatch Detection:
Report if text and audio emotions conflict.
Example: Patient uses positive words but voice shows sadness.

## CRITICAL: Flag suicidal ideation as CRITICAL if present (from text or audio)

## Required Output:
- emotions_detected: Array with emotion/severity/text_evidence/audio_evidence/clinical_significance
- dominant_emotion: Most prominent emotion (text + audio combined)
- text_emotions: Array of emotions detected from text alone
- audio_dominant: Dominant emotion from audio alone
- emotional_trajectory: How emotions changed (Improved/Stable/Worsened)
- mismatch: Boolean if text/audio emotions conflict
- rationale: Explanation of combined assessment
- confidence: Low/Medium/High
- notes: Additional observations',
    '{
        "type": "object",
        "required": ["emotions_detected", "dominant_emotion", "mismatch", "confidence"],
        "properties": {
            "emotions_detected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["emotion", "severity", "clinical_significance"],
                    "properties": {
                        "emotion": {"type": "string", "enum": ["Fear", "Anger", "Sadness", "Relief", "Distress", "Hope", "None"]},
                        "severity": {"type": "string", "enum": ["Mild", "Moderate", "Severe"]},
                        "text_evidence": {"type": "array", "items": {"type": "string"}, "description": "Evidence from transcript"},
                        "audio_evidence": {"type": "string", "description": "Evidence from voice"},
                        "clinical_significance": {"type": "string", "enum": ["High", "Medium", "Low"]}
                    }
                }
            },
            "dominant_emotion": {"type": "string", "enum": ["Fear", "Anger", "Sadness", "Relief", "Distress", "Hope", "None"], "description": "Combined dominant emotion"},
            "text_emotions": {"type": "array", "items": {"type": "string"}, "description": "Emotions from text alone"},
            "audio_dominant": {"type": "string", "description": "Dominant emotion from audio alone"},
            "emotional_trajectory": {"type": "string", "enum": ["Improved", "Stable", "Worsened"]},
            "mismatch": {"type": "boolean", "description": "True if text and audio emotions conflict"},
            "combined_score": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "confidence": {"type": "string", "enum": ["Low", "Medium", "High"]},
            "notes": {"type": "string"}
        }
    }',
    'Combined multimodal detection of medically relevant emotions',
    true,
    1003
)
;


-- COMBINED_COMPLIANCE segment
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    default_category,
    prompt_section_text,
    schema_definition_json,
    description,
    is_active,
    display_order
)
VALUES (
    'COMBINED_COMPLIANCE',
    'Combined Treatment Compliance Likelihood',
    'additional',
    '### Combined Treatment Compliance Likelihood Assessment

Predict compliance likelihood from BOTH verbal commitment AND voice confidence.

## TEXT Analysis - Positive Factors:
- Understanding of treatment importance demonstrated
- Explicit commitment to follow instructions
- Questions about proper adherence ("How exactly should I take this?")
- Support system mentioned (family helping)
- Financial resources appear adequate
- Clear follow-up scheduled and acknowledged

## TEXT Analysis - Negative Factors:
- Resistance or skepticism about treatment
- Expressed doubts about necessity
- Financial barriers identified
- Logistical challenges mentioned (work, transportation, childcare)
- Poor understanding of instructions evident
- History of non-compliance mentioned
- No follow-up arranged or declined

## AUDIO Analysis Indicators:
| Voice Pattern | Indicates |
|---------------|-----------|
| Firm, confident voice | High compliance likely |
| Immediate agreement | Genuine commitment |
| Engaged, responsive tone | Active buy-in |
| Hesitant agreement | Uncertainty, may not comply |
| Delayed responses | Processing/resistance |
| Flat tone discussing treatment | Disengagement |
| Voice trailing off | Low motivation |
| Sighing when plan mentioned | Reluctance |

## Key Barrier Types:
- **Financial**: Cannot afford treatment
- **Logistical**: Practical challenges accessing care
- **Understanding**: Doesn''t comprehend importance
- **Motivation**: Lacks belief in treatment efficacy
- **Fear/Anxiety**: Too anxious about side effects
- **Social Support**: Lacks help with care management

## Likelihood Levels:
- **High**: Strong verbal + voice commitment, resources available
- **Moderate**: Some concerns but likely to comply with most
- **Low**: Multiple barriers, voice hesitation, doubts expressed
- **Very Low**: Unlikely without intervention (text + audio signals)

## Mismatch Detection:
Report if verbal agreement contradicts voice confidence.
Example: "Yes, I''ll take it" but voice shows clear hesitation/reluctance.

## Required Output:
- likelihood: Combined assessment (High/Moderate/Low/Very Low)
- text_likelihood: From verbal content alone
- audio_likelihood: From voice confidence alone
- mismatch: Boolean if verbal agreement contradicts voice
- positive_factors: Array of supporting factors
- negative_factors: Array of barriers
- key_barriers: Array with type/severity/evidence/source
- recommendations: Suggestions to improve compliance
- combined_score: 0-1 numeric score
- rationale: Explanation of combined assessment
- confidence: Low/Medium/High
- notes: Additional observations',
    '{
        "type": "object",
        "required": ["likelihood", "text_likelihood", "audio_likelihood", "mismatch", "positive_factors", "negative_factors", "confidence"],
        "properties": {
            "likelihood": {"type": "string", "enum": ["High", "Moderate", "Low", "Very Low"], "description": "Combined likelihood"},
            "text_likelihood": {"type": "string", "enum": ["High", "Moderate", "Low", "Very Low"], "description": "From verbal content"},
            "audio_likelihood": {"type": "string", "enum": ["High", "Moderate", "Low", "Very Low"], "description": "From voice confidence"},
            "mismatch": {"type": "boolean", "description": "True if verbal and voice signals disagree"},
            "positive_factors": {"type": "array", "items": {"type": "string"}, "description": "Factors supporting compliance"},
            "negative_factors": {"type": "array", "items": {"type": "string"}, "description": "Barriers to compliance"},
            "key_barriers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "barrier_type": {"type": "string"},
                        "severity": {"type": "string", "enum": ["Minor", "Moderate", "Major"]},
                        "evidence": {"type": "string"},
                        "source": {"type": "string", "enum": ["text", "audio", "both"]}
                    }
                }
            },
            "recommendations": {"type": "array", "items": {"type": "string"}},
            "combined_score": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "confidence": {"type": "string", "enum": ["Low", "Medium", "High"]},
            "notes": {"type": "string"}
        }
    }',
    'Combined multimodal treatment compliance likelihood assessment',
    true,
    1004
)
;


-- COMBINED_DOCTOR_STYLE segment
INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    default_category,
    prompt_section_text,
    schema_definition_json,
    description,
    is_active,
    display_order
)
VALUES (
    'COMBINED_DOCTOR_STYLE',
    'Combined Doctor Communication Style',
    'additional',
    '### Combined Doctor Communication Style Assessment

Analyze doctor''s communication from BOTH what they say AND how they sound.

## Style Categories (use these exact terms):

| Style | TEXT Indicators | AUDIO Indicators |
|-------|-----------------|------------------|
| **Empathetic** | Validating statements, "I understand" | Soft tone, voice matching patient distress, warm delivery |
| **Collaborative** | Asks for input, shared decisions | Questioning tone, pauses for patient, encouraging responses |
| **Clinical** | Professional, fact-based | Neutral tone, efficient pace, information-focused |
| **Authoritative** | Directive language, confident | Confident tone, clear instructions |
| **Rushed** | Abbreviated explanations, interrupts | Fast pace, talks over patient, incomplete sentences |
| **Dismissive** | Minimizes concerns, condescending | Sighs, condescending voice, talks over patient |
| **Detached** | Emotionally unavailable language | Cold/mechanical tone, no warmth in voice |
| **Evasive** | Vague answers, deflects | Hesitant answers, avoids direct responses |

## Voice Warmth Levels:
- Cold, Neutral, Warm, Very Warm

## Key Assessment Areas:
1. **Use of empathetic statements** vs dismissive responses
2. **Medical jargon level** and explanation quality
3. **Active listening signals** (reflecting back, summarizing) vs interrupting
4. **Reassurance timing and effectiveness**
5. **Response to patient concerns** and questions
6. **Time given for patient** to ask questions
7. **Tone consistency** throughout consultation

## Impact Assessment:
- How doctor''s style affected patient anxiety (Reduced/No effect/Increased)
- Clarity of treatment plan communication
- Trust-building effectiveness

## Mismatch Detection:
Report if verbal content contradicts voice tone.
Example: Uses empathetic words but sounds rushed/dismissive in tone.

## Required Output:
- primary_style: Dominant combined style
- secondary_style: Secondary style if applicable
- text_style: Style from words alone
- audio_style: Style from voice alone
- voice_warmth: Cold/Neutral/Warm/Very Warm
- tone_consistency: How consistent was the tone
- mismatch: Boolean if words and tone contradict
- empathy_indicators: Specific empathetic behaviors (text + audio)
- communication_strengths: Positive aspects
- areas_for_improvement: What could be better
- patient_anxiety_impact: Reduced/No effect/Increased
- clarity_rating: Excellent/Good/Fair/Poor
- rationale: Explanation of combined assessment
- confidence: Low/Medium/High',
    '{
        "type": "object",
        "required": ["primary_style", "voice_warmth", "mismatch", "patient_anxiety_impact", "confidence"],
        "properties": {
            "primary_style": {"type": "string", "enum": ["Empathetic", "Collaborative", "Clinical", "Authoritative", "Rushed", "Dismissive", "Detached", "Evasive"]},
            "secondary_style": {"type": "string", "enum": ["Empathetic", "Collaborative", "Clinical", "Authoritative", "Rushed", "Dismissive", "Detached", "Evasive"]},
            "text_style": {"type": "string", "description": "Style from verbal content alone"},
            "audio_style": {"type": "string", "description": "Style from voice tone alone"},
            "voice_warmth": {"type": "string", "enum": ["Cold", "Neutral", "Warm", "Very Warm"]},
            "tone_consistency": {"type": "string", "enum": ["Highly consistent", "Mostly consistent", "Variable", "Inconsistent"]},
            "mismatch": {"type": "boolean", "description": "True if words and tone contradict"},
            "empathy_indicators": {"type": "array", "items": {"type": "string"}},
            "communication_strengths": {"type": "array", "items": {"type": "string"}},
            "areas_for_improvement": {"type": "array", "items": {"type": "string"}},
            "patient_anxiety_impact": {"type": "string", "enum": ["Reduced", "No effect", "Increased"]},
            "clarity_rating": {"type": "string", "enum": ["Excellent", "Good", "Fair", "Poor"]},
            "rationale": {"type": "string"},
            "confidence": {"type": "string", "enum": ["Low", "Medium", "High"]},
            "notes": {"type": "string"}
        }
    }',
    'Combined multimodal doctor communication style assessment',
    true,
    1005
)
;


-- ============================================================================
-- 3. Add template columns for pre-assembled combined emotion prompts
-- ============================================================================

ALTER TABLE templates ADD COLUMN IF NOT EXISTS assembled_combined_emotion_prompt TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS assembled_combined_emotion_schema_json JSONB;


-- ============================================================================
-- 4. Migrate existing emotion_extraction_mode to enable_emotion_analysis
-- ============================================================================

-- Set enable_emotion_analysis based on existing emotion_extraction_mode
UPDATE consultation_types
SET enable_emotion_analysis = CASE
    WHEN emotion_extraction_mode IN ('text_only', 'audio_only', 'both') THEN true
    ELSE false
END
WHERE emotion_extraction_mode IS NOT NULL;


-- ============================================================================
-- 5. Create function to assemble combined emotion prompt for a template
-- ============================================================================

CREATE OR REPLACE FUNCTION assemble_combined_emotion_prompt(p_template_id UUID)
RETURNS TABLE(prompt TEXT, schema_json JSONB) AS $$
DECLARE
    v_base_prompt TEXT;
    v_segment_prompts TEXT := '';
    v_schema JSONB := '{"type": "object", "required": [], "properties": {}}'::jsonb;
    v_seg RECORD;
BEGIN
    -- Get base prompt from system_prompt_components
    SELECT content INTO v_base_prompt
    FROM system_prompt_components
    WHERE component_code = 'COMBINED_EMOTION_BASE_PROMPT'
    AND is_active = true;

    IF v_base_prompt IS NULL THEN
        RETURN;
    END IF;

    -- Get all combined emotion segments
    FOR v_seg IN
        SELECT segment_code, prompt_section_text, schema_definition_json
        FROM segment_definitions
        WHERE segment_code LIKE 'COMBINED_%'
        AND is_active = true
        ORDER BY segment_code
    LOOP
        -- Append segment prompt
        v_segment_prompts := v_segment_prompts || E'\n\n' || v_seg.prompt_section_text;

        -- Add to schema properties
        v_schema := jsonb_set(
            v_schema,
            ARRAY['properties', v_seg.segment_code],
            v_seg.schema_definition_json
        );

        -- Add to required array
        v_schema := jsonb_set(
            v_schema,
            '{required}',
            (v_schema->'required') || to_jsonb(v_seg.segment_code)
        );
    END LOOP;

    -- Combine base prompt with segment prompts
    prompt := v_base_prompt || E'\n\n## Segment-Specific Instructions\n' || v_segment_prompts;
    schema_json := v_schema;

    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- 6. Create trigger to update assembled prompts when segments change
-- ============================================================================

CREATE OR REPLACE FUNCTION notify_emotion_prompt_change()
RETURNS TRIGGER AS $$
DECLARE
    v_segment_code TEXT;
    v_is_combined BOOLEAN := false;
BEGIN
    -- Get the segment code (handle DELETE case)
    IF TG_OP = 'DELETE' THEN
        v_segment_code := OLD.segment_code;
    ELSE
        v_segment_code := NEW.segment_code;
    END IF;

    -- Only act on COMBINED_* segments or base prompt component
    IF v_segment_code LIKE 'COMBINED_%' OR v_segment_code = 'COMBINED_EMOTION_BASE_PROMPT' THEN
        v_is_combined := true;
    END IF;

    IF NOT v_is_combined THEN
        -- Not a combined emotion segment, do nothing
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;

    -- Clear assembled prompts cache to force reassembly
    UPDATE templates
    SET assembled_combined_emotion_prompt = NULL,
        assembled_combined_emotion_schema_json = NULL
    WHERE id IN (
        SELECT DISTINCT t.id
        FROM templates t
        JOIN consultation_types ct ON t.consultation_type_id = ct.id
        WHERE ct.enable_emotion_analysis = true
    );

    -- Notify application of prompt change (for cache invalidation)
    PERFORM pg_notify('emotion_prompt_changed', json_build_object(
        'segment_code', v_segment_code,
        'changed_at', NOW()
    )::text);

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Trigger on segment_definitions changes (COMBINED_* segments only)
-- Note: Trigger fires for all rows, function checks if it's a COMBINED_* segment
DROP TRIGGER IF EXISTS trg_emotion_prompt_changed ON segment_definitions;
CREATE TRIGGER trg_emotion_prompt_changed
AFTER INSERT OR UPDATE OR DELETE ON segment_definitions
FOR EACH ROW
EXECUTE FUNCTION notify_emotion_prompt_change();

-- Trigger on system_prompt_components changes
DROP TRIGGER IF EXISTS trg_base_emotion_prompt_changed ON system_prompt_components;
CREATE TRIGGER trg_base_emotion_prompt_changed
AFTER INSERT OR UPDATE OR DELETE ON system_prompt_components
FOR EACH ROW
EXECUTE FUNCTION notify_emotion_prompt_change();


-- ============================================================================
-- 7. Add endpoint for emotion analysis toggle
-- ============================================================================

-- This is handled in the API, but we ensure the column exists
ALTER TABLE consultation_types ADD COLUMN IF NOT EXISTS enable_emotion_analysis BOOLEAN DEFAULT false;


-- ============================================================================
-- 8. Add COMBINED_CONGRUENCE_SUMMARY segment for overall mismatch analysis
-- ============================================================================

INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    default_category,
    prompt_section_text,
    schema_definition_json,
    description,
    is_active,
    display_order
)
VALUES (
    'COMBINED_CONGRUENCE_SUMMARY',
    'Combined Congruence Summary',
    'additional',
    '### Congruence Analysis Summary

After analyzing all segments, provide a comprehensive summary of TEXT vs AUDIO congruence.

## Purpose of Congruence Analysis
Detect when what a patient SAYS differs from how they SOUND - this reveals hidden concerns, masked emotions, or unexpressed distress that impacts clinical care.

## Synthesize Findings From All Segments

Review mismatches detected in:
- COMBINED_ANXIETY: Did text and audio anxiety levels match?
- COMBINED_FINANCIAL_CONCERNS: Did expressed concerns match voice stress?
- COMBINED_OTHER_EMOTIONS: Did stated emotions match voice prosody?
- COMBINED_COMPLIANCE: Did verbal agreement match voice confidence?
- COMBINED_DOCTOR_STYLE: Did doctor''s words match their tone?

## Calculate Overall Congruence Score

Score from 0.0 to 1.0:
- **1.0**: Perfect alignment - text and audio agree on all segments
- **0.75-0.99**: High congruence - minor mismatches, clinically insignificant
- **0.50-0.74**: Moderate congruence - some notable mismatches
- **0.25-0.49**: Low congruence - significant mismatches, hidden concerns likely
- **0.0-0.24**: Very low congruence - major mismatches, patient masking significant distress

## Identify Incongruent Moments

For each significant mismatch, document:
- **Segment**: Which area showed the mismatch
- **Text finding**: What was expressed verbally
- **Audio finding**: What voice revealed
- **Timestamp reference**: When this occurred (if identifiable)
- **Clinical significance**: High/Medium/Low impact on care
- **Interpretation**: What the mismatch might mean clinically

Example:
```
"Patient said ''I feel much better now'' at consultation end,
but voice remained tremulous with elevated pitch.
This suggests patient may be minimizing ongoing distress
to avoid concerning the doctor or appearing weak."
```

## Generate Clinical Recommendations

Based on congruence findings, recommend specific actions:

**Critical (Score < 0.3):**
- Urgent mental health referral
- Direct follow-up from doctor
- Care coordinator involvement

**High Priority (Score 0.3-0.5):**
- Schedule early follow-up call
- Financial counseling if financial mismatch detected
- Treatment adherence support if compliance mismatch

**Medium Priority (Score 0.5-0.7):**
- Emotional support resources
- Patient feedback collection
- Family involvement consideration

**Low Priority (Score > 0.7):**
- Standard follow-up appropriate
- Telehealth option for convenience

## Required Output:
- overall_congruence_score: 0.0-1.0 numeric score
- congruence_level: Very Low/Low/Moderate/High/Very High
- total_mismatches: Count of segments with significant mismatches
- mismatch_summary: Brief text summary of key mismatches
- incongruent_moments: Array of detailed mismatch objects
- clinical_recommendations: Array of prioritized recommendations
- intervention_priority: CRITICAL/HIGH/MEDIUM/LOW/NONE
- key_findings: Most important congruence insights
- confidence: Low/Medium/High',
    '{
        "type": "object",
        "required": ["overall_congruence_score", "congruence_level", "total_mismatches", "intervention_priority", "confidence"],
        "properties": {
            "overall_congruence_score": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Overall text-audio congruence score from 0.0 to 1.0"
            },
            "congruence_level": {
                "type": "string",
                "enum": ["Very Low", "Low", "Moderate", "High", "Very High"],
                "description": "Categorical congruence level"
            },
            "total_mismatches": {
                "type": "integer",
                "minimum": 0,
                "description": "Count of segments with significant text-audio mismatches"
            },
            "mismatch_summary": {
                "type": "string",
                "description": "Brief text summary of key mismatches found"
            },
            "incongruent_moments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["segment", "text_finding", "audio_finding", "clinical_significance"],
                    "properties": {
                        "segment": {"type": "string", "description": "Which segment showed mismatch"},
                        "text_finding": {"type": "string", "description": "What was expressed verbally"},
                        "audio_finding": {"type": "string", "description": "What voice revealed"},
                        "timestamp_reference": {"type": "string", "description": "When this occurred if identifiable"},
                        "clinical_significance": {"type": "string", "enum": ["High", "Medium", "Low"]},
                        "interpretation": {"type": "string", "description": "Clinical meaning of this mismatch"}
                    }
                },
                "description": "Detailed list of incongruent moments"
            },
            "clinical_recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["recommendation", "priority", "reason"],
                    "properties": {
                        "recommendation": {"type": "string", "description": "Specific recommended action"},
                        "priority": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
                        "reason": {"type": "string", "description": "Why this is recommended based on findings"},
                        "source_mismatches": {"type": "array", "items": {"type": "string"}, "description": "Which mismatches triggered this"}
                    }
                },
                "description": "Prioritized clinical recommendations"
            },
            "intervention_priority": {
                "type": "string",
                "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE"],
                "description": "Highest priority intervention level needed"
            },
            "key_findings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Most important congruence insights"
            },
            "areas_of_concern": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific areas requiring attention"
            },
            "confidence": {
                "type": "string",
                "enum": ["Low", "Medium", "High"],
                "description": "Confidence in congruence analysis"
            }
        }
    }',
    'Comprehensive summary of text-audio congruence with clinical recommendations',
    true,
    1006
)
;


-- ============================================================================
-- 9. Add COMBINED_INTERACTION_DYNAMICS segment
-- ============================================================================

INSERT INTO segment_definitions (
    segment_code,
    segment_name,
    default_category,
    prompt_section_text,
    schema_definition_json,
    description,
    is_active,
    display_order
)
VALUES (
    'COMBINED_INTERACTION_DYNAMICS',
    'Combined Interaction Dynamics',
    'additional',
    '### Combined Interaction Dynamics Analysis

Assess the doctor-patient interaction quality from BOTH conversation content AND voice dynamics.

## TEXT Analysis Indicators:

**Turn-Taking Patterns:**
- Who initiates topics and questions
- Frequency of interruptions (noted in transcript)
- Distribution of speaking turns
- Patient given opportunity to ask questions

**Engagement Signals:**
- Questions asked by patient (shows engagement)
- Clarification requests from either party
- Active listening phrases ("I see", "Tell me more")
- Follow-up questions showing attention
- Acknowledgment of concerns

**Communication Quality:**
- Clear explanations vs confusion
- Medical jargon explained or not
- Patient understanding verified
- Shared decision-making language

## AUDIO Analysis Indicators:

**Voice Turn-Taking:**
- Overlapping speech patterns
- Pause length between speakers
- Natural vs forced transitions
- Interruption frequency and nature

**Engagement Markers:**
- Responsive tone (engaged) vs flat (disengaged)
- Energy levels of both parties
- Attention signals in voice
- Mutual responsiveness

**Flow Quality:**
- Natural rhythm vs stilted
- Appropriate pauses for comprehension
- Awkward silences indicating discomfort
- Smooth topic transitions

## Assessment Categories:

**Turn-Taking Balance:**
- **Doctor-dominated**: Doctor speaks significantly more, limited patient input
- **Balanced**: Appropriate back-and-forth for consultation type
- **Patient-dominated**: Patient speaks most (may indicate anxiety or doctor passivity)

**Conversation Flow:**
- **Natural**: Smooth transitions, appropriate pauses, comfortable rhythm
- **Mostly natural**: Minor hesitations but generally flows well
- **Somewhat stilted**: Noticeable awkward pauses or interruptions
- **Stilted**: Frequent interruptions, long awkward silences, uncomfortable

**Mutual Engagement:**
- **High**: Both parties actively engaged, responsive, good rapport
- **Medium**: Adequate engagement with some disengagement moments
- **Low**: One or both parties seem disengaged, perfunctory

## Mismatch Detection:
Report if text engagement signals differ from audio engagement.
Example: Patient asks many questions (text shows engagement) but voice is flat and disengaged.

## Required Output:
- turn_taking_balance: Doctor-dominated/Balanced/Patient-dominated
- text_turn_pattern: Turn pattern from transcript analysis
- audio_turn_pattern: Turn pattern from voice analysis
- conversation_flow: Natural/Mostly natural/Somewhat stilted/Stilted
- text_flow: Flow quality from transcript
- audio_flow: Flow quality from voice dynamics
- mutual_engagement: High/Medium/Low
- text_engagement: Engagement from transcript
- audio_engagement: Engagement from voice
- mismatch: Boolean if text/audio engagement signals differ
- rapport_quality: Excellent/Good/Fair/Poor
- rationale: Explanation combining text and audio evidence
- confidence: Low/Medium/High
- notes: Additional observations',
    '{
        "type": "object",
        "required": ["turn_taking_balance", "conversation_flow", "mutual_engagement", "mismatch", "confidence"],
        "properties": {
            "turn_taking_balance": {
                "type": "string",
                "enum": ["Doctor-dominated", "Balanced", "Patient-dominated"],
                "description": "Combined turn-taking balance assessment"
            },
            "text_turn_pattern": {
                "type": "string",
                "description": "Turn pattern from transcript analysis"
            },
            "audio_turn_pattern": {
                "type": "string",
                "description": "Turn pattern from voice analysis"
            },
            "conversation_flow": {
                "type": "string",
                "enum": ["Natural", "Mostly natural", "Somewhat stilted", "Stilted"],
                "description": "Combined conversation flow quality"
            },
            "text_flow": {
                "type": "string",
                "description": "Flow quality from transcript"
            },
            "audio_flow": {
                "type": "string",
                "description": "Flow quality from voice dynamics"
            },
            "mutual_engagement": {
                "type": "string",
                "enum": ["High", "Medium", "Low"],
                "description": "Combined mutual engagement level"
            },
            "text_engagement": {
                "type": "string",
                "description": "Engagement level from transcript"
            },
            "audio_engagement": {
                "type": "string",
                "description": "Engagement level from voice"
            },
            "mismatch": {
                "type": "boolean",
                "description": "True if text and audio engagement signals differ"
            },
            "rapport_quality": {
                "type": "string",
                "enum": ["Excellent", "Good", "Fair", "Poor"],
                "description": "Overall doctor-patient rapport quality"
            },
            "rationale": {
                "type": "string",
                "description": "Explanation combining text and audio evidence"
            },
            "confidence": {
                "type": "string",
                "enum": ["Low", "Medium", "High"],
                "description": "Confidence in assessment"
            },
            "notes": {
                "type": "string",
                "description": "Additional observations"
            }
        }
    }',
    'Combined multimodal interaction dynamics assessment from transcript and audio',
    true,
    1007
)
;


COMMENT ON TABLE segment_definitions IS 'Segment definitions including combined emotion analysis segments (COMBINED_ANXIETY, COMBINED_FINANCIAL_CONCERNS, COMBINED_OTHER_EMOTIONS, COMBINED_COMPLIANCE, COMBINED_DOCTOR_STYLE, COMBINED_INTERACTION_DYNAMICS, COMBINED_CONGRUENCE_SUMMARY)';

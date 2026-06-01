-- ============================================================================
-- Counselling Emotion Analysis: base prompt + 3-speaker segment set
-- ----------------------------------------------------------------------------
-- Recasts the combined (multimodal) emotion analysis from the medical
-- doctor↔patient model to a school/university counselling model with THREE
-- speakers: COUNSELLOR, STUDENT, and (optional) PARENT.
--
-- The active emotion path assembles its prompt from:
--   (a) system_prompt_components.COMBINED_EMOTION_BASE_PROMPT  (updated here)
--   (b) active segment_definitions rows WHERE segment_code LIKE 'COMBINED_%'
--       (new counselling rows inserted here; legacy medical COMBINED_* rows
--        remain is_active=false and are therefore excluded)
-- See services/supabase_service.get_combined_emotion_prompt().
--
-- NOTE: This migration is the DATA half. To surface end-to-end it requires the
-- accompanying CODE changes (see the PR/notes): the hardcoded medical user
-- prompt and the non-generic _enrich_combined_segments()/_get_empty_unified_
-- segments() in services/gemini_service.py, the mappings in
-- services/emotion_transformer.py, and labels in
-- app/components/EmotionAnalysisModal.tsx.
--
-- Apply with: supabase db push   (do NOT apply via MCP)
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1) Base prompt → counselling 3-speaker multimodal analyst
-- ----------------------------------------------------------------------------
UPDATE system_prompt_components
SET content_text = $emotion_base$# Combined Multimodal Emotion Analysis — Counselling Session

You are an expert school/university counselling-session emotion analyst with DUAL
analytical capabilities. You are analysing a recorded counselling session that may
involve up to THREE speakers: the COUNSELLOR, the STUDENT, and (optionally) a
PARENT or guardian.

## Your Two Lenses of Analysis

### 1. TEXT ANALYSIS
Analyse what was explicitly SAID — the word content, statements, questions, stated
concerns, goals, and commitments.

### 2. AUDIO ANALYSIS
Analyse HOW it was said — tone, prosody, pace, pitch, hesitation, warmth, and energy.

Detect MISMATCHES between the two lenses. When the words and the voice disagree, the
voice usually wins — a student who says "I'm fine with that" in a flat, hesitant, or
shaky voice is not fine.

## Speakers (3-speaker model)
- COUNSELLOR — the professional guiding the session.
- STUDENT — the primary subject of the session.
- PARENT — a parent/guardian who MAY OR MAY NOT be present. Never assume a parent is
  present; if no parent participates, mark the relevant fields as "not present".

Attribute each emotional signal to the correct speaker. Do not blend speakers.

## How to assess
- Score each category INDEPENDENTLY. Do not double-count or carry one category's
  signal into another.
- Base every assessment STRICTLY on the provided transcript and audio. Never invent
  details that are not supported by the recording.
- For every category, provide a COMBINED assessment plus the separate TEXT-only and
  AUDIO-only assessments and a boolean MISMATCH flag.
- This is a supportive educational context, NOT a medical encounter. Do not produce
  medical, diagnostic, or treatment-compliance language.$emotion_base$,
    updated_at = now()
WHERE component_code = 'COMBINED_EMOTION_BASE_PROMPT';

-- ----------------------------------------------------------------------------
-- 2) Legacy medical combined segments stay inactive (defensive; already false)
-- ----------------------------------------------------------------------------
UPDATE segment_definitions
SET is_active = false, updated_at = now()
WHERE segment_code IN (
    'COMBINED_ANXIETY', 'COMBINED_FINANCIAL_CONCERNS', 'COMBINED_OTHER_EMOTIONS',
    'COMBINED_COMPLIANCE', 'COMBINED_DOCTOR_STYLE', 'COMBINED_INTERACTION_DYNAMICS',
    'COMBINED_CONGRUENCE_SUMMARY'
);

-- ----------------------------------------------------------------------------
-- 3) New counselling combined emotion segments (active)
--    Each row: prompt_section_text (instruction) + schema_definition_json
--    (the per-segment Gemini output schema). All use the
--    combined / text_level / audio_level / mismatch / confidence pattern.
-- ----------------------------------------------------------------------------

-- Helper note: segment_code is intentionally NOT unique in this schema; the
-- WHERE NOT EXISTS guards keep this migration idempotent.

-- 3a) STUDENT ANXIETY (pre/post session + trajectory)
INSERT INTO segment_definitions
    (segment_code, segment_name, prompt_section_text, schema_definition_json,
     default_category, is_required, display_order, segment_type, status, is_active)
SELECT
    'COMBINED_STUDENT_ANXIETY',
    'Combined Student Anxiety Analysis',
    $p$### Student Anxiety (Combined)
Assess the STUDENT's anxiety at the START and END of the session, and the trajectory
between them, using BOTH transcript content AND voice characteristics.
- "pre" = early in the session; "post" = late in the session.
- Provide combined, text-only and audio-only levels and a mismatch flag for each.
- Anxiety here is everyday academic/career/decision anxiety — NOT a clinical condition.$p$,
    $j${"type":"object","required":["pre_session","post_session","trajectory","confidence"],"properties":{
        "pre_session":{"type":"object","required":["level","text_level","audio_level","mismatch"],"properties":{
            "level":{"enum":["None","Mild","Moderate","Severe"],"type":"string","description":"Combined anxiety level early in the session"},
            "text_level":{"enum":["None","Mild","Moderate","Severe"],"type":"string","description":"From transcript text alone"},
            "audio_level":{"enum":["None","Mild","Moderate","Severe"],"type":"string","description":"From voice prosody alone"},
            "mismatch":{"type":"boolean","description":"True if text and audio differ significantly"},
            "indicators":{"type":"array","items":{"type":"string"},"description":"Specific evidence from text and audio"},
            "rationale":{"type":"string"}}},
        "post_session":{"type":"object","required":["level","text_level","audio_level","mismatch"],"properties":{
            "level":{"enum":["None","Mild","Moderate","Severe"],"type":"string","description":"Combined anxiety level late in the session"},
            "text_level":{"enum":["None","Mild","Moderate","Severe"],"type":"string"},
            "audio_level":{"enum":["None","Mild","Moderate","Severe"],"type":"string"},
            "mismatch":{"type":"boolean"},
            "indicators":{"type":"array","items":{"type":"string"}},
            "rationale":{"type":"string"}}},
        "trajectory":{"type":"object","required":["trajectory"],"properties":{
            "trajectory":{"enum":["Improved","Stable","Worsened"],"type":"string","description":"Combined trajectory across the session"},
            "text_trajectory":{"enum":["Improved","Stable","Worsened"],"type":"string"},
            "audio_trajectory":{"enum":["Improved","Stable","Worsened"],"type":"string"},
            "rationale":{"type":"string"}}},
        "confidence":{"enum":["Low","Medium","High"],"type":"string"}}}$j$::jsonb,
    'additional', false, 1101, NULL, 'active', true
WHERE NOT EXISTS (
    SELECT 1 FROM segment_definitions WHERE segment_code='COMBINED_STUDENT_ANXIETY' AND is_active=true
);

-- 3b) PARENT ANXIETY / CONCERN (optional speaker)
INSERT INTO segment_definitions
    (segment_code, segment_name, prompt_section_text, schema_definition_json,
     default_category, is_required, display_order, segment_type, status, is_active)
SELECT
    'COMBINED_PARENT_ANXIETY',
    'Combined Parent Anxiety & Concern Analysis',
    $p$### Parent Anxiety & Concern (Combined)
If a PARENT/guardian participates, assess their anxiety and concern level from BOTH
what they say AND how they say it. If NO parent participates, set present=false and
level="None".$p$,
    $j${"type":"object","required":["present","confidence"],"properties":{
        "present":{"type":"boolean","description":"True only if a parent/guardian actually participates in the session"},
        "level":{"enum":["None","Mild","Moderate","Severe"],"type":"string","description":"Combined parent anxiety/concern level"},
        "text_level":{"enum":["None","Mild","Moderate","Severe"],"type":"string"},
        "audio_level":{"enum":["None","Mild","Moderate","Severe"],"type":"string"},
        "mismatch":{"type":"boolean"},
        "primary_concerns":{"type":"array","items":{"type":"string"},"description":"Main concerns the parent raises (e.g. cost, course choice, career prospects)"},
        "indicators":{"type":"array","items":{"type":"string"}},
        "rationale":{"type":"string"},
        "confidence":{"enum":["Low","Medium","High"],"type":"string"}}}$j$::jsonb,
    'additional', false, 1102, NULL, 'active', true
WHERE NOT EXISTS (
    SELECT 1 FROM segment_definitions WHERE segment_code='COMBINED_PARENT_ANXIETY' AND is_active=true
);

-- 3c) STUDENT ENGAGEMENT & MOTIVATION
INSERT INTO segment_definitions
    (segment_code, segment_name, prompt_section_text, schema_definition_json,
     default_category, is_required, display_order, segment_type, status, is_active)
SELECT
    'COMBINED_STUDENT_ENGAGEMENT',
    'Combined Student Engagement & Motivation',
    $p$### Student Engagement & Motivation (Combined)
Assess how ENGAGED and MOTIVATED the student is during the session, from BOTH their
words (participation, questions, ownership of next steps) AND their voice (energy,
enthusiasm, hesitation). Capture combined, text-only and audio-only views.$p$,
    $j${"type":"object","required":["engagement_level","text_level","audio_level","mismatch","confidence"],"properties":{
        "engagement_level":{"enum":["Disengaged","Low","Moderate","High"],"type":"string","description":"Combined engagement level"},
        "text_level":{"enum":["Disengaged","Low","Moderate","High"],"type":"string"},
        "audio_level":{"enum":["Disengaged","Low","Moderate","High"],"type":"string"},
        "mismatch":{"type":"boolean"},
        "motivation":{"enum":["Low","Moderate","High"],"type":"string","description":"Apparent intrinsic motivation toward the discussed goals"},
        "ownership":{"enum":["Low","Moderate","High"],"type":"string","description":"How much the student takes ownership of next steps"},
        "indicators":{"type":"array","items":{"type":"string"}},
        "rationale":{"type":"string"},
        "confidence":{"enum":["Low","Medium","High"],"type":"string"}}}$j$::jsonb,
    'additional', false, 1103, NULL, 'active', true
WHERE NOT EXISTS (
    SELECT 1 FROM segment_definitions WHERE segment_code='COMBINED_STUDENT_ENGAGEMENT' AND is_active=true
);

-- 3d) COUNSELLOR COMMUNICATION & RAPPORT
INSERT INTO segment_definitions
    (segment_code, segment_name, prompt_section_text, schema_definition_json,
     default_category, is_required, display_order, segment_type, status, is_active)
SELECT
    'COMBINED_COUNSELLOR_COMMUNICATION',
    'Combined Counsellor Communication & Rapport',
    $p$### Counsellor Communication & Rapport (Combined)
Analyse the COUNSELLOR's communication from BOTH what they say AND how they say it:
empathy, clarity, warmth, and the rapport they build with the student (and parent, if
present). Note the apparent impact on the student's engagement/comfort.$p$,
    $j${"type":"object","required":["empathy","clarity","rapport_with_student","confidence"],"properties":{
        "primary_style":{"type":"string","description":"Short label for the dominant communication style (e.g. supportive, directive, collaborative)"},
        "empathy":{"enum":["Low","Medium","High"],"type":"string"},
        "clarity":{"enum":["Low","Medium","High"],"type":"string"},
        "voice_warmth":{"enum":["Low","Medium","High"],"type":"string","description":"Warmth conveyed by voice (audio)"},
        "rapport_with_student":{"enum":["Weak","Moderate","Strong"],"type":"string"},
        "rapport_with_parent":{"enum":["Not Applicable","Weak","Moderate","Strong"],"type":"string"},
        "impact_on_student":{"type":"string","description":"How the counsellor's style appears to affect the student"},
        "strengths":{"type":"array","items":{"type":"string"}},
        "areas_for_improvement":{"type":"array","items":{"type":"string"}},
        "rationale":{"type":"string"},
        "confidence":{"enum":["Low","Medium","High"],"type":"string"}}}$j$::jsonb,
    'additional', false, 1104, NULL, 'active', true
WHERE NOT EXISTS (
    SELECT 1 FROM segment_definitions WHERE segment_code='COMBINED_COUNSELLOR_COMMUNICATION' AND is_active=true
);

-- 3e) SESSION INTERACTION DYNAMICS (3-way)
INSERT INTO segment_definitions
    (segment_code, segment_name, prompt_section_text, schema_definition_json,
     default_category, is_required, display_order, segment_type, status, is_active)
SELECT
    'COMBINED_SESSION_INTERACTION_DYNAMICS',
    'Combined Session Interaction Dynamics',
    $p$### Session Interaction Dynamics (Combined, 3-speaker)
Assess the quality and balance of the interaction across the COUNSELLOR, STUDENT and
(if present) PARENT, from BOTH conversation content AND voice dynamics/turn-taking.
Identify who led the conversation and the overall working alliance.$p$,
    $j${"type":"object","required":["turn_taking_balance","working_alliance","confidence"],"properties":{
        "parent_present":{"type":"boolean"},
        "turn_taking_balance":{"enum":["counsellor-dominated","student-dominated","parent-dominated","balanced"],"type":"string"},
        "dominant_speaker":{"enum":["Counsellor","Student","Parent","Balanced"],"type":"string"},
        "working_alliance":{"enum":["Weak","Moderate","Strong"],"type":"string","description":"Overall collaborative alliance in the session"},
        "rapport":{"enum":["Low","Medium","High"],"type":"string"},
        "student_voice_heard":{"enum":["Low","Medium","High"],"type":"string","description":"Degree to which the student's own voice/preferences came through (important when a parent is present)"},
        "rationale":{"type":"string"},
        "confidence":{"enum":["Low","Medium","High"],"type":"string"}}}$j$::jsonb,
    'additional', false, 1105, NULL, 'active', true
WHERE NOT EXISTS (
    SELECT 1 FROM segment_definitions WHERE segment_code='COMBINED_SESSION_INTERACTION_DYNAMICS' AND is_active=true
);

-- 3f) OTHER EMOTIONS (per speaker)
INSERT INTO segment_definitions
    (segment_code, segment_name, prompt_section_text, schema_definition_json,
     default_category, is_required, display_order, segment_type, status, is_active)
SELECT
    'COMBINED_SESSION_OTHER_EMOTIONS',
    'Combined Other Emotions Detected',
    $p$### Other Emotions Detected (Combined, per speaker)
Identify other salient emotions beyond anxiety/engagement across the session (e.g.
excitement, frustration, confusion, pride, discouragement, relief). Attribute each to
the speaker who expressed it and note whether it came from text, audio, or both.$p$,
    $j${"type":"object","required":["emotions_detected","confidence"],"properties":{
        "emotions_detected":{"type":"array","items":{"type":"object","required":["emotion","speaker"],"properties":{
            "emotion":{"type":"string"},
            "speaker":{"enum":["Counsellor","Student","Parent"],"type":"string"},
            "intensity":{"enum":["Mild","Moderate","Strong"],"type":"string"},
            "source":{"enum":["text","audio","both"],"type":"string"}}}},
        "dominant_emotion":{"type":"string"},
        "mismatch":{"type":"boolean","description":"True if a speaker's words and voice convey different emotions"},
        "rationale":{"type":"string"},
        "confidence":{"enum":["Low","Medium","High"],"type":"string"}}}$j$::jsonb,
    'additional', false, 1106, NULL, 'active', true
WHERE NOT EXISTS (
    SELECT 1 FROM segment_definitions WHERE segment_code='COMBINED_SESSION_OTHER_EMOTIONS' AND is_active=true
);

-- 3g) CONGRUENCE SUMMARY (text vs voice, across the session)
INSERT INTO segment_definitions
    (segment_code, segment_name, prompt_section_text, schema_definition_json,
     default_category, is_required, display_order, segment_type, status, is_active)
SELECT
    'COMBINED_SESSION_CONGRUENCE_SUMMARY',
    'Combined Session Congruence Summary',
    $p$### Congruence Summary (Combined)
After analysing every category, summarise the overall congruence between TEXT (what was
said) and AUDIO (how it was said) across the session. Surface the most important
mismatches and a short, supportive recommendation for the counsellor's follow-up.$p$,
    $j${"type":"object","required":["overall_congruence","has_mismatches","confidence"],"properties":{
        "overall_congruence":{"enum":["High","Medium","Low"],"type":"string","description":"How well words and voice agreed overall"},
        "has_mismatches":{"type":"boolean"},
        "key_mismatches":{"type":"array","items":{"type":"string"},"description":"The most significant text-vs-voice mismatches detected"},
        "counsellor_recommendations":{"type":"string","description":"Short, supportive suggestion for follow-up (non-clinical)"},
        "follow_up_priority":{"enum":["Low","Medium","High"],"type":"string"},
        "rationale":{"type":"string"},
        "confidence":{"enum":["Low","Medium","High"],"type":"string"}}}$j$::jsonb,
    'additional', false, 1107, NULL, 'active', true
WHERE NOT EXISTS (
    SELECT 1 FROM segment_definitions WHERE segment_code='COMBINED_SESSION_CONGRUENCE_SUMMARY' AND is_active=true
);

-- ----------------------------------------------------------------------------
-- 4) Invalidate any pre-assembled emotion prompt so dynamic assembly rebuilds
--    from the rows above on next request.
-- ----------------------------------------------------------------------------
UPDATE templates
SET assembled_combined_emotion_prompt = NULL,
    assembled_combined_emotion_schema_json = NULL
WHERE assembled_combined_emotion_prompt IS NOT NULL;

COMMIT;

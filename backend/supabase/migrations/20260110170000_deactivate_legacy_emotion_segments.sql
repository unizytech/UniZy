-- Migration: Deactivate Legacy Emotion Segments and Prompts
-- Date: 2026-01-10
-- Description: Deactivates old AUDIO_* and TEXT_EMOTION_* segments and base prompts
--              as part of the combined-only emotion analysis simplification.
--              These are replaced by COMBINED_* segments and COMBINED_EMOTION_BASE_PROMPT.

-- ============================================================================
-- Deactivate old segment_definitions
-- ============================================================================

-- Deactivate AUDIO_* segments (6 segments)
-- These were used by extract_audio_emotions_standalone() and transcribe_audio_with_emotions()
UPDATE segment_definitions
SET is_active = false
WHERE segment_code LIKE 'AUDIO_%';

-- Deactivate TEXT_EMOTION_* segments (6 segments)
-- These were used by extract_emotion_analysis()
UPDATE segment_definitions
SET is_active = false
WHERE segment_code LIKE 'TEXT_EMOTION_%';

-- ============================================================================
-- Deactivate old system_prompt_components
-- ============================================================================

-- Temporarily disable trigger that references segment_code (not applicable to this table)
ALTER TABLE system_prompt_components DISABLE TRIGGER trg_base_emotion_prompt_changed;

-- Deactivate old emotion base prompts (3 prompts)
UPDATE system_prompt_components
SET is_active = false
WHERE component_code IN (
    'AUDIO_EMOTION_BASE_PROMPT_COMBINED',    -- Used by transcribe_audio_with_emotions()
    'AUDIO_EMOTION_BASE_PROMPT_STANDALONE',  -- Used by extract_audio_emotions_standalone()
    'TEXT_EMOTION_BASE_PROMPT'               -- Used by extract_emotion_analysis()
);

-- Re-enable trigger
ALTER TABLE system_prompt_components ENABLE TRIGGER trg_base_emotion_prompt_changed;

-- ============================================================================
-- Verification: Show what's now active for emotion analysis
-- ============================================================================
-- After this migration, only COMBINED_* segments and COMBINED_EMOTION_BASE_PROMPT
-- should be active for emotion analysis.

-- Note: The following queries are for verification only (results not persisted):
-- SELECT segment_code, is_active FROM segment_definitions WHERE segment_code LIKE 'COMBINED_%';
-- SELECT component_code, is_active FROM system_prompt_components WHERE component_code = 'COMBINED_EMOTION_BASE_PROMPT';

-- Add `extraction_includes_audio` flag to consultation_types
-- When true, the main extraction call (skip_transcription=false path) will also
-- attach the audio bytes alongside the transcript so Gemini can reason over both.
-- Use this for templates whose prompts depend on voice cues (e.g. psychology
-- screenings that judge tremor / pitch / hesitation, with voice-override-applied
-- decisions). Default false preserves current behavior for every other type.

ALTER TABLE consultation_types
  ADD COLUMN IF NOT EXISTS extraction_includes_audio BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN consultation_types.extraction_includes_audio IS
  'When true, the main extraction call attaches the audio bytes alongside the transcript so Gemini can reason over both. Use only for templates whose prompts depend on voice cues. Adds latency.';

-- Enable for the three psychology consultation types whose prompts require voice reasoning.
UPDATE consultation_types
SET extraction_includes_audio = true,
    updated_at = NOW()
WHERE type_code IN ('PSYCHOLOGY_OMH', 'PSYCHOLOGY_IP_ASSESS', 'PSYCHOLOGY_ONCO_ASSESS');

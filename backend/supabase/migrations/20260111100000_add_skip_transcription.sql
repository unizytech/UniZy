-- Add skip_transcription column to consultation_types
-- When true, skip transcription and extract insights directly from audio

ALTER TABLE consultation_types
ADD COLUMN IF NOT EXISTS skip_transcription BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN consultation_types.skip_transcription IS
'When true, skip transcription and extract insights directly from audio. Auto-disables emotion/triage/insights.';

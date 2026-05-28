-- Migration: Add audio_quality_json column to recording_sessions
-- Stores comprehensive audio quality analysis result

ALTER TABLE recording_sessions
ADD COLUMN IF NOT EXISTS audio_quality_json JSONB DEFAULT NULL;

COMMENT ON COLUMN recording_sessions.audio_quality_json IS
'Audio quality analysis result containing: overall_quality (good/fair/poor), is_acceptable (bool), issues[] (list of detected problems), metrics{} (snr_db, rms_db, peak_db, clipping_ratio, silence_ratio, speech_detected, duration_seconds), and summary_message (human-readable)';

-- Create an index for querying by quality level
CREATE INDEX IF NOT EXISTS idx_recording_sessions_audio_quality
ON recording_sessions ((audio_quality_json->>'overall_quality'))
WHERE audio_quality_json IS NOT NULL;

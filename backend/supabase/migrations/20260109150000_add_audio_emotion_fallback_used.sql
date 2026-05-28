-- Add fallback_used tracking for audio emotion extraction
-- When audio emotion JSON parsing fails, we fall back to transcript-only mode
-- This flag tracks when that fallback was used (completed=true but with empty emotions)

ALTER TABLE medical_extractions
ADD COLUMN IF NOT EXISTS audio_emotion_extraction_fallback_used BOOLEAN DEFAULT FALSE;

-- Add a comment explaining the column
COMMENT ON COLUMN medical_extractions.audio_emotion_extraction_fallback_used IS
'True when audio emotion extraction completed via fallback (empty emotions due to JSON parse failure)';

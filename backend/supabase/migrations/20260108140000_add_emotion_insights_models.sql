-- Add emotion_model and insights_model columns to processing_modes table
-- These allow configuring models for emotion analysis and consultation insights extraction

-- emotion_model: Used for both text and audio emotion analysis
-- (extract_emotion_analysis and extract_audio_emotions_standalone)
-- Default: gemini-3-flash-preview (fast, suitable for emotion analysis)
ALTER TABLE processing_modes ADD COLUMN IF NOT EXISTS emotion_model VARCHAR(100) DEFAULT 'gemini-3-flash-preview';

-- insights_model: Used for consultation insights extraction (14 signal groups for interventions)
-- (extract_consultation_insights)
-- Default: gemini-3-flash-preview (fast, suitable for structured extraction)
ALTER TABLE processing_modes ADD COLUMN IF NOT EXISTS insights_model VARCHAR(100) DEFAULT 'gemini-3-flash-preview';

-- Update existing rows to have explicit values
UPDATE processing_modes SET emotion_model = 'gemini-3-flash-preview' WHERE emotion_model IS NULL;
UPDATE processing_modes SET insights_model = 'gemini-3-flash-preview' WHERE insights_model IS NULL;

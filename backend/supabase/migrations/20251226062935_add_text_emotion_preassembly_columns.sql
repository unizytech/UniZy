-- Migration: Add text emotion pre-assembly columns to templates table
-- This enables pre-assembled text emotion prompts and schemas similar to audio emotion prompts
-- Text emotion analysis uses transcript text to detect anxiety, emotions, financial concerns, etc.

-- Add text emotion prompt pre-assembly columns
ALTER TABLE templates ADD COLUMN IF NOT EXISTS assembled_text_emotion_prompt TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS text_emotion_prompt_assembled_at TIMESTAMPTZ;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS text_emotion_prompt_trigger_source TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS text_emotion_prompt_assembly_hash VARCHAR(64);

-- Add text emotion schema pre-assembly columns
ALTER TABLE templates ADD COLUMN IF NOT EXISTS assembled_text_emotion_schema_json JSONB;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS text_emotion_schema_assembled_at TIMESTAMPTZ;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS text_emotion_schema_trigger_source TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS text_emotion_schema_assembly_hash VARCHAR(64);

-- Add comments for documentation
COMMENT ON COLUMN templates.assembled_text_emotion_prompt IS 'Pre-assembled text emotion analysis system prompt (combines base + TEXT_EMOTION_ segment instructions)';
COMMENT ON COLUMN templates.text_emotion_prompt_assembled_at IS 'Timestamp when text emotion prompt was last assembled';
COMMENT ON COLUMN templates.text_emotion_prompt_trigger_source IS 'What triggered the last text emotion prompt assembly (e.g., segment:uuid:update, manual)';
COMMENT ON COLUMN templates.text_emotion_prompt_assembly_hash IS 'SHA256 hash of assembled_text_emotion_prompt for change detection';
COMMENT ON COLUMN templates.assembled_text_emotion_schema_json IS 'Pre-assembled JSON schema for text emotion extraction (combines TEXT_EMOTION_ segment schemas)';
COMMENT ON COLUMN templates.text_emotion_schema_assembled_at IS 'Timestamp when text emotion schema was last assembled';
COMMENT ON COLUMN templates.text_emotion_schema_trigger_source IS 'What triggered the last text emotion schema assembly';
COMMENT ON COLUMN templates.text_emotion_schema_assembly_hash IS 'SHA256 hash of assembled_text_emotion_schema_json for change detection';

-- Migration: Add audio emotion pre-assembly columns to templates table
-- This enables pre-assembled audio emotion prompts and schemas similar to extraction prompts

-- Add audio prompt pre-assembly columns
ALTER TABLE templates ADD COLUMN IF NOT EXISTS assembled_audio_prompt TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS audio_prompt_assembled_at TIMESTAMPTZ;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS audio_prompt_trigger_source TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS audio_prompt_assembly_hash VARCHAR(64);

-- Add audio schema pre-assembly columns
ALTER TABLE templates ADD COLUMN IF NOT EXISTS assembled_audio_schema_json JSONB;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS audio_schema_assembled_at TIMESTAMPTZ;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS audio_schema_trigger_source TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS audio_schema_assembly_hash VARCHAR(64);

-- Add comments for documentation
COMMENT ON COLUMN templates.assembled_audio_prompt IS 'Pre-assembled audio emotion analysis system prompt (combines base + AUDIO_ segment instructions)';
COMMENT ON COLUMN templates.audio_prompt_assembled_at IS 'Timestamp when audio prompt was last assembled';
COMMENT ON COLUMN templates.audio_prompt_trigger_source IS 'What triggered the last audio prompt assembly (e.g., segment:uuid:update, manual)';
COMMENT ON COLUMN templates.audio_prompt_assembly_hash IS 'SHA256 hash of assembled_audio_prompt for change detection';
COMMENT ON COLUMN templates.assembled_audio_schema_json IS 'Pre-assembled JSON schema for audio emotion extraction (combines AUDIO_ segment schemas)';
COMMENT ON COLUMN templates.audio_schema_assembled_at IS 'Timestamp when audio schema was last assembled';
COMMENT ON COLUMN templates.audio_schema_trigger_source IS 'What triggered the last audio schema assembly';
COMMENT ON COLUMN templates.audio_schema_assembly_hash IS 'SHA256 hash of assembled_audio_schema_json for change detection';

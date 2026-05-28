-- Add hospital-level toggle to enable/disable audio validation
-- Default TRUE means all existing hospitals keep audio validation ON
ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS enable_audio_validation BOOLEAN DEFAULT TRUE;

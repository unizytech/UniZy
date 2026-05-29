-- Migration: Add triage and consultation insights toggles to consultation_types
-- These allow enabling/disabling triage analysis and consultation insights per consultation type
-- Similar to existing enable_emotion_analysis toggle

-- Add enable_triage_analysis column (defaults to TRUE for backward compatibility)
ALTER TABLE consultation_types ADD COLUMN IF NOT EXISTS enable_triage_analysis BOOLEAN DEFAULT TRUE;

-- Add enable_consultation_insights column (defaults to TRUE for backward compatibility)
ALTER TABLE consultation_types ADD COLUMN IF NOT EXISTS enable_consultation_insights BOOLEAN DEFAULT TRUE;

-- Add comments for documentation
COMMENT ON COLUMN consultation_types.enable_triage_analysis IS 'Enable/disable triage suggestions generation for this consultation type. Default TRUE.';
COMMENT ON COLUMN consultation_types.enable_consultation_insights IS 'Enable/disable consultation insights extraction and all downstream assessments (severity, allied health, dropoff risk, quality, interventions). Default TRUE.';

-- Ensure existing consultation types have both flags enabled
UPDATE consultation_types
SET
    enable_triage_analysis = COALESCE(enable_triage_analysis, TRUE),
    enable_consultation_insights = COALESCE(enable_consultation_insights, TRUE)
WHERE enable_triage_analysis IS NULL OR enable_consultation_insights IS NULL;

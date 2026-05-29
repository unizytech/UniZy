-- Add triage_model column to processing_modes table
-- Model values already updated manually, this just adds the new column

ALTER TABLE processing_modes ADD COLUMN IF NOT EXISTS triage_model VARCHAR(100) DEFAULT 'gemini-3-flash-preview';

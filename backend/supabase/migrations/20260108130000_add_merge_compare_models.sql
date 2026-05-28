-- Add merge_model and compare_model columns to processing_modes table
-- These allow configuring models for segment merge and transcript comparison utilities

-- merge_model: Used for AI-powered segment merging (combine_segments endpoint)
-- Default: gemini-3-pro-preview (higher quality for merging)
ALTER TABLE processing_modes ADD COLUMN IF NOT EXISTS merge_model VARCHAR(100) DEFAULT 'gemini-3-pro-preview';

-- compare_model: Used for WER comparison analysis (compare_transcripts endpoint)
-- Default: gemini-3-flash-preview (fast, suitable for comparison)
ALTER TABLE processing_modes ADD COLUMN IF NOT EXISTS compare_model VARCHAR(100) DEFAULT 'gemini-3-flash-preview';

-- Update existing rows to have explicit values
UPDATE processing_modes SET merge_model = 'gemini-3-pro-preview' WHERE merge_model IS NULL;
UPDATE processing_modes SET compare_model = 'gemini-3-flash-preview' WHERE compare_model IS NULL;

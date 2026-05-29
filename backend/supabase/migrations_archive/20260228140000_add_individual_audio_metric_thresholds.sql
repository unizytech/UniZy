-- Add individual audio metric threshold columns to hospitals table
-- These replace the aggregate audio_quality_block_threshold for more granular control
-- Each metric can be configured per-hospital to block recordings that fail specific checks

ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS min_snr_db FLOAT DEFAULT 10.0;
ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS min_rms_db FLOAT DEFAULT -40.0;
ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS min_speech_ratio FLOAT DEFAULT 0.10;

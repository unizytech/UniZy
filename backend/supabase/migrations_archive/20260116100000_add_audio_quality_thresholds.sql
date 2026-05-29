-- Migration: Add audio quality validation thresholds to hospitals
-- Date: 2026-01-16
-- Purpose: Enable per-hospital configuration of audio quality blocking thresholds

-- ============================================================================
-- Part 1: Add quality threshold columns to hospitals table
-- ============================================================================

ALTER TABLE hospitals
ADD COLUMN IF NOT EXISTS audio_quality_block_threshold TEXT DEFAULT 'poor',
ADD COLUMN IF NOT EXISTS min_transcript_length INTEGER DEFAULT 20,
ADD COLUMN IF NOT EXISTS max_silence_ratio NUMERIC(3,2) DEFAULT 0.90;

-- Add comments
COMMENT ON COLUMN hospitals.audio_quality_block_threshold IS
'Block processing if audio quality is at or below this level. Options: poor, fair, none (never block). Default: poor.';

COMMENT ON COLUMN hospitals.min_transcript_length IS
'Minimum transcript length (characters) to proceed with extraction. Blocks if transcript is shorter. Default: 20.';

COMMENT ON COLUMN hospitals.max_silence_ratio IS
'Block if silence ratio exceeds this threshold (0.0 to 1.0). Default: 0.90 (90% silence).';

-- ============================================================================
-- Part 2: Add validation_failed status to recording_sessions (if not exists)
-- This allows tracking sessions that failed validation for debugging
-- ============================================================================

-- Note: recording_sessions.status is likely a TEXT column, no enum update needed
-- Just ensure validation_failed is documented as a valid status

COMMENT ON TABLE recording_sessions IS
'Recording sessions table. Status values: pending, processing, completed, failed, validation_failed.';

-- ============================================================================
-- Part 3: Add keep_chunks flag to processing_jobs error_details
-- (Already JSONB, no schema change needed - just documentation)
-- ============================================================================

COMMENT ON COLUMN processing_jobs.error_details IS
'JSON object with error details. May include: exception_type (str), keep_chunks (bool for validation failures).';

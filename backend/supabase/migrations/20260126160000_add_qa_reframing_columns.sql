-- Migration: Add query reframing columns to qa_query_history
-- Version: 1.0.0
-- Description: Adds columns to track how user queries are reframed before classification
--
-- New columns:
-- - reframed_query: The reframed/normalized version of the original query
-- - reframe_expansions: JSON array of abbreviations/terms that were expanded
-- - reframe_corrections: JSON array of typos/terms that were corrected
-- - reframe_confidence: Confidence score of the reframing (0.0-1.0)
-- - reframe_time_ms: Time taken for reframing in milliseconds

-- =============================================================================
-- Add reframing columns to qa_query_history
-- =============================================================================

ALTER TABLE qa_query_history
ADD COLUMN IF NOT EXISTS reframed_query TEXT,
ADD COLUMN IF NOT EXISTS reframe_expansions JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS reframe_corrections JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS reframe_confidence DECIMAL(3, 2),
ADD COLUMN IF NOT EXISTS reframe_time_ms INTEGER;

-- =============================================================================
-- Add comments for documentation
-- =============================================================================

COMMENT ON COLUMN qa_query_history.reframed_query IS 'The reframed/normalized version of the original query after preprocessing';
COMMENT ON COLUMN qa_query_history.reframe_expansions IS 'JSON array of expansions applied, e.g., [{"original": "BP", "expanded": "blood pressure"}]';
COMMENT ON COLUMN qa_query_history.reframe_corrections IS 'JSON array of corrections applied, e.g., [{"original": "diabeties", "corrected": "diabetes"}]';
COMMENT ON COLUMN qa_query_history.reframe_confidence IS 'Confidence score of the reframing (0.0-1.0)';
COMMENT ON COLUMN qa_query_history.reframe_time_ms IS 'Time taken for query reframing in milliseconds';

-- =============================================================================
-- Index for analyzing reframing patterns (optional, for analytics)
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_qa_query_history_reframed
ON qa_query_history (hospital_id, created_at DESC)
WHERE reframed_query IS NOT NULL;

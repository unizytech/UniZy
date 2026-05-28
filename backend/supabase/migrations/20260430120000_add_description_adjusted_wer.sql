-- =============================================================================
-- Add description-adjusted WER column
--
-- The original "overall_wer_adjusted" subtracts clinical paraphrases only.
-- This new column subtracts deletion errors as well — deletions are mostly
-- doctors trimming verbose AI prose in description-style free-text fields
-- (e.g. chiefComplaints[*].description), not real STT errors.
--
-- Formula:
--   overall_wer_adjusted_descriptions =
--       max(0, total_errors - total_paraphrases - total_deletion_errors)
--       / total_words_ai_original
-- =============================================================================

ALTER TABLE extraction_accuracy_metrics
    ADD COLUMN IF NOT EXISTS overall_wer_adjusted_descriptions NUMERIC(5,4);

COMMENT ON COLUMN extraction_accuracy_metrics.overall_wer_adjusted_descriptions IS
    'WER after subtracting clinical paraphrases AND deletion errors. Deletions in description-style free-text fields (chiefComplaints, etc.) are typically doctor trims, not AI errors.';

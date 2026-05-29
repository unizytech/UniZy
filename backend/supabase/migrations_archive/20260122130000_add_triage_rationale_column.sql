-- Migration: Add rationale column to triage_suggestion_log
-- Description: Adds rationale column to store explanation for each triage suggestion
-- This column was previously added manually to dev DB without a migration

ALTER TABLE triage_suggestion_log
ADD COLUMN IF NOT EXISTS rationale TEXT;

COMMENT ON COLUMN triage_suggestion_log.rationale IS 'Explanation/reasoning for the triage suggestion';

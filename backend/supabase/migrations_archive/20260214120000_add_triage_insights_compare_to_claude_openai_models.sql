-- Add triage, insights, compare to use_for arrays for Claude and OpenAI models
-- This enables these models to appear in processing mode dropdowns for those functions

UPDATE models_master
SET use_for = array_cat(use_for, '{triage,insights,compare}')
WHERE provider IN ('anthropic', 'openai')
  AND NOT use_for @> '{triage}';

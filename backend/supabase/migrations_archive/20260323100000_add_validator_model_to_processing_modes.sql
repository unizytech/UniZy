-- Add validator_model column to processing_modes table
-- Used by the continuation merge micro-validator (cross-segment consistency check)
ALTER TABLE processing_modes
ADD COLUMN IF NOT EXISTS validator_model VARCHAR(100);

-- Set default value for existing rows
UPDATE processing_modes SET validator_model = 'gemini-2.5-flash' WHERE validator_model IS NULL;

-- Add 'validator' to use_for array for all Gemini models that support it
-- (same models that support triage/compare — text-only, no special capabilities needed)
UPDATE models_master
SET use_for = array_append(use_for, 'validator')
WHERE provider = 'gemini'
  AND NOT ('validator' = ANY(use_for))
  AND is_active = true
  AND model_id NOT LIKE '%live%'
  AND model_id NOT LIKE '%audio%';

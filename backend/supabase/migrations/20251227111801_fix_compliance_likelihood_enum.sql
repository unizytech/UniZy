-- Migration: Remove percentage suffixes from compliance likelihood enum values
-- This fixes the likelihood enum to use clean values without percentages
-- e.g., "Very Low" instead of "Very Low (0-19%)"

-- Update TEXT_EMOTION_TREATMENT_COMPLIANCE_LIKELIHOOD
UPDATE segment_definitions
SET schema_definition_json = jsonb_set(
    schema_definition_json,
    '{properties,likelihood,enum}',
    '["Very Low", "Low", "Moderate", "High"]'::jsonb
)
WHERE segment_code = 'TEXT_EMOTION_TREATMENT_COMPLIANCE_LIKELIHOOD'
  AND schema_definition_json->'properties'->'likelihood'->'enum' IS NOT NULL;

-- Update TREATMENT_COMPLIANCE_LIKELIHOOD (unified segment)
UPDATE segment_definitions
SET schema_definition_json = jsonb_set(
    schema_definition_json,
    '{properties,likelihood,enum}',
    '["Very Low", "Low", "Moderate", "High"]'::jsonb
)
WHERE segment_code = 'TREATMENT_COMPLIANCE_LIKELIHOOD'
  AND schema_definition_json->'properties'->'likelihood'->'enum' IS NOT NULL;

-- Update AUDIO_COMPLIANCE_INDICATORS
UPDATE segment_definitions
SET schema_definition_json = jsonb_set(
    schema_definition_json,
    '{properties,likelihood,enum}',
    '["Very Low", "Low", "Moderate", "High"]'::jsonb
)
WHERE segment_code = 'AUDIO_COMPLIANCE_INDICATORS'
  AND schema_definition_json->'properties'->'likelihood'->'enum' IS NOT NULL;

-- Log the migration
DO $$
BEGIN
    RAISE NOTICE 'Migration complete: Compliance likelihood enum values updated to remove percentage suffixes';
END $$;

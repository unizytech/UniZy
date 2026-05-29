-- Add flag columns to clinical_severity_assessments for easier querying
-- These duplicate values from input_data JSONB for direct SQL filtering

ALTER TABLE clinical_severity_assessments
ADD COLUMN IF NOT EXISTS is_surgical BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_chronic BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_second_opinion BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_alternate_procedure BOOLEAN DEFAULT FALSE;

-- Add indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_severity_is_surgical
ON clinical_severity_assessments(is_surgical) WHERE is_surgical = TRUE;

CREATE INDEX IF NOT EXISTS idx_severity_is_chronic
ON clinical_severity_assessments(is_chronic) WHERE is_chronic = TRUE;

CREATE INDEX IF NOT EXISTS idx_severity_is_second_opinion
ON clinical_severity_assessments(is_second_opinion) WHERE is_second_opinion = TRUE;

CREATE INDEX IF NOT EXISTS idx_severity_is_alternate_procedure
ON clinical_severity_assessments(is_alternate_procedure) WHERE is_alternate_procedure = TRUE;

-- Backfill existing records from input_data JSONB
UPDATE clinical_severity_assessments
SET
    is_surgical = COALESCE((input_data->>'is_surgical')::boolean, FALSE),
    is_chronic = COALESCE((input_data->>'is_chronic')::boolean, FALSE),
    is_second_opinion = COALESCE((input_data->>'is_second_opinion')::boolean, FALSE),
    is_alternate_procedure = COALESCE((input_data->>'is_alternate_procedure')::boolean, FALSE)
WHERE input_data IS NOT NULL AND input_data != '{}'::jsonb;

COMMENT ON COLUMN clinical_severity_assessments.is_surgical IS 'Whether treatment involves surgery (duplicated from input_data for querying)';
COMMENT ON COLUMN clinical_severity_assessments.is_chronic IS 'Whether condition is chronic (duplicated from input_data for querying)';
COMMENT ON COLUMN clinical_severity_assessments.is_second_opinion IS 'Whether doctor recommends specialist consultation (duplicated from input_data for querying)';
COMMENT ON COLUMN clinical_severity_assessments.is_alternate_procedure IS 'Whether alternate treatment is suggested if first fails (duplicated from input_data for querying)';

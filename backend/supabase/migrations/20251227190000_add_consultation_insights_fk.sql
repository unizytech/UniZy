-- Add consultation_insights_id foreign key to assessment tables
-- This enables analytics joins without duplicating raw signals in input_data
-- Raw AI signals are now stored in consultation_insights, assessments store only calculated values

-- 1. clinical_severity_assessments
ALTER TABLE clinical_severity_assessments
    ADD COLUMN IF NOT EXISTS consultation_insights_id UUID REFERENCES consultation_insights(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_severity_consultation_insights
    ON clinical_severity_assessments(consultation_insights_id);

COMMENT ON COLUMN clinical_severity_assessments.consultation_insights_id IS
    'Reference to consultation_insights for raw AI signals (analytics joins)';

-- 2. other_clinical_needs
ALTER TABLE other_clinical_needs
    ADD COLUMN IF NOT EXISTS consultation_insights_id UUID REFERENCES consultation_insights(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_clinical_needs_consultation_insights
    ON other_clinical_needs(consultation_insights_id);

COMMENT ON COLUMN other_clinical_needs.consultation_insights_id IS
    'Reference to consultation_insights for raw AI signals (analytics joins)';

-- 3. allied_health_needs
ALTER TABLE allied_health_needs
    ADD COLUMN IF NOT EXISTS consultation_insights_id UUID REFERENCES consultation_insights(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_allied_health_consultation_insights
    ON allied_health_needs(consultation_insights_id);

COMMENT ON COLUMN allied_health_needs.consultation_insights_id IS
    'Reference to consultation_insights for raw AI signals (analytics joins)';

-- 4. patient_dropoff_risk
ALTER TABLE patient_dropoff_risk
    ADD COLUMN IF NOT EXISTS consultation_insights_id UUID REFERENCES consultation_insights(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_dropoff_consultation_insights
    ON patient_dropoff_risk(consultation_insights_id);

COMMENT ON COLUMN patient_dropoff_risk.consultation_insights_id IS
    'Reference to consultation_insights for raw AI signals (analytics joins)';

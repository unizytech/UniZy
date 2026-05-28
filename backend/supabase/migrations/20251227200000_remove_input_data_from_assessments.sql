-- Remove input_data column from assessment tables
-- Raw AI signals are now stored in consultation_insights table
-- Assessment tables only store calculated values + consultation_insights_id FK

-- 1. clinical_severity_assessments
ALTER TABLE clinical_severity_assessments
    DROP COLUMN IF EXISTS input_data;

-- 2. other_clinical_needs
ALTER TABLE other_clinical_needs
    DROP COLUMN IF EXISTS input_data;

-- 3. allied_health_needs
ALTER TABLE allied_health_needs
    DROP COLUMN IF EXISTS input_data;

-- 4. patient_dropoff_risk
ALTER TABLE patient_dropoff_risk
    DROP COLUMN IF EXISTS input_data;

-- Add comments to document the change
COMMENT ON TABLE clinical_severity_assessments IS
    'Clinical severity scores. Raw AI signals in consultation_insights (join via consultation_insights_id)';

COMMENT ON TABLE other_clinical_needs IS
    'Other clinical needs assessment. Raw AI signals in consultation_insights (join via consultation_insights_id)';

COMMENT ON TABLE allied_health_needs IS
    'Allied health referral needs. Raw AI signals in consultation_insights (join via consultation_insights_id)';

COMMENT ON TABLE patient_dropoff_risk IS
    'Patient dropoff/churn risk. Raw AI signals in consultation_insights (join via consultation_insights_id)';

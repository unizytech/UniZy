-- Add consolidated 'reasons' field to clinical_severity_assessments and patient_dropoff_risk tables
-- This provides a human-readable summary similar to other_clinical_needs and allied_health_needs

-- =============================================================================
-- 1. Add 'reasons' to clinical_severity_assessments
-- =============================================================================
ALTER TABLE clinical_severity_assessments
ADD COLUMN IF NOT EXISTS reasons TEXT[] DEFAULT '{}';

COMMENT ON COLUMN clinical_severity_assessments.reasons IS
'Human-readable array of reasons explaining the severity assessment';

-- =============================================================================
-- 2. Add 'reasons' to patient_dropoff_risk
-- =============================================================================
ALTER TABLE patient_dropoff_risk
ADD COLUMN IF NOT EXISTS reasons TEXT[] DEFAULT '{}';

COMMENT ON COLUMN patient_dropoff_risk.reasons IS
'Consolidated human-readable array of all triggered risk indicator reasons';

-- =============================================================================
-- 3. Backfill existing clinical_severity_assessments records
-- =============================================================================
UPDATE clinical_severity_assessments
SET reasons = contributing_factors
WHERE reasons = '{}' AND contributing_factors IS NOT NULL AND contributing_factors != '{}';

-- =============================================================================
-- 4. Backfill existing patient_dropoff_risk records
-- =============================================================================
UPDATE patient_dropoff_risk
SET reasons = (
    SELECT array_agg(reason)
    FROM (
        SELECT unnest(
            COALESCE(financial_risk_reasons, '{}') ||
            COALESCE(competitor_risk_reasons, '{}') ||
            COALESCE(dissatisfaction_risk_reasons, '{}') ||
            COALESCE(access_risk_reasons, '{}') ||
            COALESCE(compliance_risk_reasons, '{}')
        ) AS reason
    ) subq
    WHERE reason IS NOT NULL
)
WHERE reasons = '{}';

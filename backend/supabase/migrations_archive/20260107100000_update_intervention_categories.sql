-- Migration: Update intervention categories from 3 to 7 categories
-- Version: 2.0.0
--
-- This migration replaces the old 3-category system (REVENUE, RETENTION, QUALITY)
-- with a new 7-category system designed for the hospital management dashboard:
--
-- OLD: REVENUE | RETENTION | QUALITY (with sub_types)
-- NEW: OP_TO_IP | FOLLOWUP_DUE | RX_REFILL | DIAGNOSTICS_DUE | ALLIED_HEALTH | RETENTION_RISK | QUALITY_RISK
--
-- Category Mapping:
-- OP_TO_IP: SURGICAL_CONSULTATION
-- FOLLOWUP_DUE: SECOND_OPINION_CONSULT, ALTERNATIVE_TREATMENT_CONSULT, FOLLOW_UP_REMINDER, URGENT_FOLLOWUP_NEEDED, SPECIALIST_REFERRAL_NEEDED
-- RX_REFILL: PRESCRIPTION_REFILL_REMINDER
-- DIAGNOSTICS_DUE: HOME_DIAGNOSTIC_COLLECTION, RECURRING_TEST_SCHEDULE
-- ALLIED_HEALTH: 10 referral types including CHRONIC_CARE_PROGRAM
-- RETENTION_RISK: 7 retention interventions
-- QUALITY_RISK: 7 quality interventions

-- =============================================================================
-- 1. Drop existing constraints FIRST (before any data changes)
-- =============================================================================

ALTER TABLE intervention_definitions
DROP CONSTRAINT IF EXISTS intervention_definitions_category_check;

ALTER TABLE patient_interventions
DROP CONSTRAINT IF EXISTS patient_interventions_intervention_category_check;

-- =============================================================================
-- 2. Update intervention_definitions data with new categories
-- =============================================================================

-- OP_TO_IP
UPDATE intervention_definitions
SET category = 'OP_TO_IP', updated_at = NOW()
WHERE intervention_code = 'SURGICAL_CONSULTATION';

-- FOLLOWUP_DUE
UPDATE intervention_definitions
SET category = 'FOLLOWUP_DUE', updated_at = NOW()
WHERE intervention_code IN (
    'SECOND_OPINION_CONSULT',
    'ALTERNATIVE_TREATMENT_CONSULT',
    'FOLLOW_UP_REMINDER',
    'URGENT_FOLLOWUP_NEEDED',
    'SPECIALIST_REFERRAL_NEEDED'
);

-- RX_REFILL
UPDATE intervention_definitions
SET category = 'RX_REFILL', updated_at = NOW()
WHERE intervention_code = 'PRESCRIPTION_REFILL_REMINDER';

-- DIAGNOSTICS_DUE
UPDATE intervention_definitions
SET category = 'DIAGNOSTICS_DUE', updated_at = NOW()
WHERE intervention_code IN (
    'HOME_DIAGNOSTIC_COLLECTION',
    'RECURRING_TEST_SCHEDULE'
);

-- ALLIED_HEALTH
UPDATE intervention_definitions
SET category = 'ALLIED_HEALTH', updated_at = NOW()
WHERE intervention_code IN (
    'NUTRITIONAL_REFERRAL',
    'PHYSIOTHERAPY_REFERRAL',
    'MENTAL_HEALTH_REFERRAL',
    'SLEEP_CLINIC_REFERRAL',
    'CARDIAC_REHAB_REFERRAL',
    'GENERAL_REHAB_REFERRAL',
    'HOMECARE_SERVICES',
    'WELLNESS_PROGRAM',
    'TREATMENT_EDUCATION_PROGRAM',
    'CHRONIC_CARE_PROGRAM'
);

-- RETENTION_RISK
UPDATE intervention_definitions
SET category = 'RETENTION_RISK', updated_at = NOW()
WHERE intervention_code IN (
    'COMPETITOR_COUNTEROFFER',
    'ACCESS_BARRIER_RESOLUTION',
    'FINANCIAL_ASSISTANCE',
    'COMPLIANCE_SUPPORT',
    'SATISFACTION_RECOVERY',
    'EMOTIONAL_SUPPORT',
    'PATIENT_EDUCATION_GAP'
);

-- QUALITY_RISK (all 7 quality interventions)
UPDATE intervention_definitions
SET category = 'QUALITY_RISK', updated_at = NOW()
WHERE intervention_code IN (
    'CONTRAINDICATION_ALERT',
    'DRUG_INTERACTION_REVIEW',
    'POLYPHARMACY_REVIEW',
    'DOSAGE_VERIFICATION',
    'MISSING_DIAGNOSIS_ALERT',
    'PROTOCOL_DEVIATION_REVIEW',
    'INCOMPLETE_WORKUP_ALERT'
);

-- Handle legacy/inactive interventions - map based on old category
-- Former RETENTION interventions → RETENTION_RISK
UPDATE intervention_definitions
SET category = 'RETENTION_RISK', updated_at = NOW()
WHERE category = 'RETENTION';

-- Former QUALITY interventions → QUALITY_RISK
UPDATE intervention_definitions
SET category = 'QUALITY_RISK', updated_at = NOW()
WHERE category = 'QUALITY';

-- Former REVENUE interventions → ALLIED_HEALTH (default bucket for uncategorized revenue)
UPDATE intervention_definitions
SET category = 'ALLIED_HEALTH', updated_at = NOW()
WHERE category = 'REVENUE';

-- Any remaining with 'general' or other categories → RETENTION_RISK as fallback
UPDATE intervention_definitions
SET category = 'RETENTION_RISK', updated_at = NOW()
WHERE category NOT IN ('OP_TO_IP', 'FOLLOWUP_DUE', 'RX_REFILL', 'DIAGNOSTICS_DUE', 'ALLIED_HEALTH', 'RETENTION_RISK', 'QUALITY_RISK');

-- =============================================================================
-- 3. Update patient_interventions data with new categories
-- =============================================================================

-- OP_TO_IP
UPDATE patient_interventions
SET intervention_category = 'OP_TO_IP'
WHERE intervention_code = 'SURGICAL_CONSULTATION';

-- FOLLOWUP_DUE
UPDATE patient_interventions
SET intervention_category = 'FOLLOWUP_DUE'
WHERE intervention_code IN (
    'SECOND_OPINION_CONSULT',
    'ALTERNATIVE_TREATMENT_CONSULT',
    'FOLLOW_UP_REMINDER',
    'URGENT_FOLLOWUP_NEEDED',
    'SPECIALIST_REFERRAL_NEEDED'
);

-- RX_REFILL
UPDATE patient_interventions
SET intervention_category = 'RX_REFILL'
WHERE intervention_code = 'PRESCRIPTION_REFILL_REMINDER';

-- DIAGNOSTICS_DUE
UPDATE patient_interventions
SET intervention_category = 'DIAGNOSTICS_DUE'
WHERE intervention_code IN (
    'HOME_DIAGNOSTIC_COLLECTION',
    'RECURRING_TEST_SCHEDULE'
);

-- ALLIED_HEALTH
UPDATE patient_interventions
SET intervention_category = 'ALLIED_HEALTH'
WHERE intervention_code IN (
    'NUTRITIONAL_REFERRAL',
    'PHYSIOTHERAPY_REFERRAL',
    'MENTAL_HEALTH_REFERRAL',
    'SLEEP_CLINIC_REFERRAL',
    'CARDIAC_REHAB_REFERRAL',
    'GENERAL_REHAB_REFERRAL',
    'HOMECARE_SERVICES',
    'WELLNESS_PROGRAM',
    'TREATMENT_EDUCATION_PROGRAM',
    'CHRONIC_CARE_PROGRAM'
);

-- RETENTION_RISK
UPDATE patient_interventions
SET intervention_category = 'RETENTION_RISK'
WHERE intervention_code IN (
    'COMPETITOR_COUNTEROFFER',
    'ACCESS_BARRIER_RESOLUTION',
    'FINANCIAL_ASSISTANCE',
    'COMPLIANCE_SUPPORT',
    'SATISFACTION_RECOVERY',
    'EMOTIONAL_SUPPORT',
    'PATIENT_EDUCATION_GAP'
);

-- QUALITY_RISK
UPDATE patient_interventions
SET intervention_category = 'QUALITY_RISK'
WHERE intervention_code IN (
    'CONTRAINDICATION_ALERT',
    'DRUG_INTERACTION_REVIEW',
    'POLYPHARMACY_REVIEW',
    'DOSAGE_VERIFICATION',
    'MISSING_DIAGNOSIS_ALERT',
    'PROTOCOL_DEVIATION_REVIEW',
    'INCOMPLETE_WORKUP_ALERT'
);

-- Handle legacy patient_interventions - map based on old category
UPDATE patient_interventions
SET intervention_category = 'RETENTION_RISK'
WHERE intervention_category = 'RETENTION';

UPDATE patient_interventions
SET intervention_category = 'QUALITY_RISK'
WHERE intervention_category = 'QUALITY';

UPDATE patient_interventions
SET intervention_category = 'ALLIED_HEALTH'
WHERE intervention_category = 'REVENUE';

-- Any remaining unmapped → RETENTION_RISK as fallback
UPDATE patient_interventions
SET intervention_category = 'RETENTION_RISK'
WHERE intervention_category IS NOT NULL
  AND intervention_category NOT IN ('OP_TO_IP', 'FOLLOWUP_DUE', 'RX_REFILL', 'DIAGNOSTICS_DUE', 'ALLIED_HEALTH', 'RETENTION_RISK', 'QUALITY_RISK');

-- =============================================================================
-- 4. Add new constraints AFTER data is updated
-- =============================================================================

ALTER TABLE intervention_definitions
ADD CONSTRAINT intervention_definitions_category_check
CHECK (category IN ('OP_TO_IP', 'FOLLOWUP_DUE', 'RX_REFILL', 'DIAGNOSTICS_DUE', 'ALLIED_HEALTH', 'RETENTION_RISK', 'QUALITY_RISK'));

ALTER TABLE patient_interventions
ADD CONSTRAINT patient_interventions_intervention_category_check
CHECK (intervention_category IN ('OP_TO_IP', 'FOLLOWUP_DUE', 'RX_REFILL', 'DIAGNOSTICS_DUE', 'ALLIED_HEALTH', 'RETENTION_RISK', 'QUALITY_RISK'));

-- =============================================================================
-- 5. Add comments for documentation
-- =============================================================================

COMMENT ON COLUMN intervention_definitions.category IS
'Dashboard category: OP_TO_IP (surgical), FOLLOWUP_DUE (return visits), RX_REFILL (prescriptions), DIAGNOSTICS_DUE (tests), ALLIED_HEALTH (referrals), RETENTION_RISK (dropoff prevention), QUALITY_RISK (safety alerts)';

COMMENT ON COLUMN patient_interventions.intervention_category IS
'Dashboard category: OP_TO_IP (surgical), FOLLOWUP_DUE (return visits), RX_REFILL (prescriptions), DIAGNOSTICS_DUE (tests), ALLIED_HEALTH (referrals), RETENTION_RISK (dropoff prevention), QUALITY_RISK (safety alerts)';

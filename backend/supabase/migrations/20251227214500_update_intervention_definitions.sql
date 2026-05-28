-- Migration: Update intervention_definitions with new REVENUE, RETENTION, QUALITY categories
-- This replaces the old emotion-based interventions with the new categorized system

-- Step 0: Drop the old category check constraint and create new one
ALTER TABLE public.intervention_definitions
DROP CONSTRAINT IF EXISTS intervention_definitions_category_check;

ALTER TABLE public.intervention_definitions
ADD CONSTRAINT intervention_definitions_category_check
CHECK (category IN ('REVENUE', 'RETENTION', 'QUALITY', 'access', 'care_coordination', 'compliance', 'doctor_followup', 'emotional', 'family', 'feedback', 'financial', 'mental_health'));

-- Step 1: Deactivate old intervention definitions (keep for historical reference)
UPDATE public.intervention_definitions
SET is_active = false,
    updated_at = NOW()
WHERE category NOT IN ('REVENUE', 'RETENTION', 'QUALITY');

-- Step 2: Insert new REVENUE interventions (16 types)

-- Allied Health Services (9)
INSERT INTO public.intervention_definitions (
    intervention_code, intervention_name, description, priority_level, priority_score, category, trigger_conditions, is_active
) VALUES
('NUTRITIONAL_REFERRAL', 'Nutritional Counseling Referral', 'Patient has condition requiring dietary guidance', 'HIGH', 80, 'REVENUE', '{"sub_type": "allied_health", "trigger": "is_nutritional_health"}', true),
('PHYSIOTHERAPY_REFERRAL', 'Physiotherapy Referral', 'Patient has condition that would benefit from physiotherapy', 'HIGH', 80, 'REVENUE', '{"sub_type": "allied_health", "trigger": "is_physiotherapy"}', true),
('MENTAL_HEALTH_REFERRAL', 'Mental Health Specialist Referral', 'Patient shows signs requiring mental health support', 'HIGH', 80, 'REVENUE', '{"sub_type": "allied_health", "trigger": "is_mental_health"}', true),
('SLEEP_CLINIC_REFERRAL', 'Sleep Study Consultation', 'Patient reports symptoms suggesting sleep disorder', 'MEDIUM', 60, 'REVENUE', '{"sub_type": "allied_health", "trigger": "is_sleep_therapy"}', true),
('CARDIAC_REHAB_REFERRAL', 'Cardiac Rehabilitation Program', 'Patient would benefit from cardiac rehabilitation', 'HIGH', 80, 'REVENUE', '{"sub_type": "allied_health", "trigger": "is_rehab_cardiac"}', true),
('GENERAL_REHAB_REFERRAL', 'General Rehabilitation Assessment', 'Patient requires rehabilitation following condition', 'MEDIUM', 60, 'REVENUE', '{"sub_type": "allied_health", "trigger": "is_rehab_common"}', true),
('HOMECARE_SERVICES', 'Home Healthcare Services', 'Patient needs home-based care support', 'MEDIUM', 60, 'REVENUE', '{"sub_type": "allied_health", "trigger": "is_homecare"}', true),
('WELLNESS_PROGRAM', 'Wellness and Prevention Program', 'Patient has lifestyle risk factors for chronic conditions', 'LOW', 40, 'REVENUE', '{"sub_type": "allied_health", "trigger": "is_wellness"}', true),
('TREATMENT_EDUCATION_PROGRAM', 'Patient Education Session', 'Patient shows difficulty understanding treatment aspects', 'LOW', 40, 'REVENUE', '{"sub_type": "allied_health", "trigger": "is_treatment_education"}', true)
ON CONFLICT (intervention_code) DO UPDATE SET
    intervention_name = EXCLUDED.intervention_name,
    description = EXCLUDED.description,
    priority_level = EXCLUDED.priority_level,
    priority_score = EXCLUDED.priority_score,
    category = EXCLUDED.category,
    trigger_conditions = EXCLUDED.trigger_conditions,
    is_active = true,
    updated_at = NOW();

-- Clinical Upsell (4)
INSERT INTO public.intervention_definitions (
    intervention_code, intervention_name, description, priority_level, priority_score, category, trigger_conditions, is_active
) VALUES
('SURGICAL_CONSULTATION', 'Surgical Consultation', 'Patient condition may require surgical intervention', 'HIGH', 80, 'REVENUE', '{"sub_type": "clinical_upsell", "trigger": "is_surgical"}', true),
('SECOND_OPINION_CONSULT', 'Second Opinion Consultation', 'Complex diagnosis warrants second opinion', 'HIGH', 80, 'REVENUE', '{"sub_type": "clinical_upsell", "trigger": "is_second_opinion"}', true),
('ALTERNATIVE_TREATMENT_CONSULT', 'Alternative Treatment Review', 'Alternative treatment options available for condition', 'MEDIUM', 60, 'REVENUE', '{"sub_type": "clinical_upsell", "trigger": "is_alternate_procedure"}', true),
('CHRONIC_CARE_PROGRAM', 'Chronic Care Management Program', 'Patient has chronic condition requiring ongoing management', 'MEDIUM', 60, 'REVENUE', '{"sub_type": "clinical_upsell", "trigger": "is_chronic"}', true)
ON CONFLICT (intervention_code) DO UPDATE SET
    intervention_name = EXCLUDED.intervention_name,
    description = EXCLUDED.description,
    priority_level = EXCLUDED.priority_level,
    priority_score = EXCLUDED.priority_score,
    category = EXCLUDED.category,
    trigger_conditions = EXCLUDED.trigger_conditions,
    is_active = true,
    updated_at = NOW();

-- Diagnostics & Rx (3)
INSERT INTO public.intervention_definitions (
    intervention_code, intervention_name, description, priority_level, priority_score, category, trigger_conditions, is_active
) VALUES
('HOME_DIAGNOSTIC_COLLECTION', 'Home Sample Collection', 'Patient requires diagnostics - home collection available', 'MEDIUM', 60, 'REVENUE', '{"sub_type": "diagnostics_rx", "trigger": "is_followup_diagnostics"}', true),
('PRESCRIPTION_REFILL_REMINDER', 'Prescription Refill Service', 'Patient on medications needs refill coordination', 'LOW', 40, 'REVENUE', '{"sub_type": "diagnostics_rx", "trigger": "is_rx_refill"}', true),
('RECURRING_TEST_SCHEDULE', 'Scheduled Lab Panel', 'Patient needs periodic monitoring for condition', 'LOW', 40, 'REVENUE', '{"sub_type": "diagnostics_rx", "trigger": "is_recurring_diagnostics"}', true)
ON CONFLICT (intervention_code) DO UPDATE SET
    intervention_name = EXCLUDED.intervention_name,
    description = EXCLUDED.description,
    priority_level = EXCLUDED.priority_level,
    priority_score = EXCLUDED.priority_score,
    category = EXCLUDED.category,
    trigger_conditions = EXCLUDED.trigger_conditions,
    is_active = true,
    updated_at = NOW();

-- Step 3: Insert new RETENTION interventions (7 types)
INSERT INTO public.intervention_definitions (
    intervention_code, intervention_name, description, priority_level, priority_score, category, trigger_conditions, is_active
) VALUES
('COMPETITOR_COUNTEROFFER', 'Competitive Retention Outreach', 'Patient mentioned considering other healthcare providers', 'CRITICAL', 95, 'RETENTION', '{"sub_type": "retention", "trigger": "is_competitor_risk"}', true),
('ACCESS_BARRIER_RESOLUTION', 'Access Barrier Resolution', 'Patient faces barriers to accessing care', 'HIGH', 80, 'RETENTION', '{"sub_type": "retention", "trigger": "is_access_risk"}', true),
('FINANCIAL_ASSISTANCE', 'Financial Assistance Connection', 'Patient expressed financial concerns with high dropoff risk', 'HIGH', 80, 'RETENTION', '{"sub_type": "retention", "trigger": "is_financial_risk"}', true),
('COMPLIANCE_SUPPORT', 'Treatment Adherence Support', 'Patient shows low treatment adherence likelihood', 'MEDIUM', 60, 'RETENTION', '{"sub_type": "retention", "trigger": "is_compliance_risk"}', true),
('FOLLOW_UP_REMINDER', 'Follow-up Reminder Call', 'No specific follow-up scheduled with retention risk', 'LOW', 40, 'RETENTION', '{"sub_type": "retention", "trigger": "vague_followup"}', true),
('SATISFACTION_RECOVERY', 'Service Recovery Callback', 'Patient dissatisfaction detected during consultation', 'HIGH', 80, 'RETENTION', '{"sub_type": "retention", "trigger": "is_dissatisfaction_risk"}', true),
('EMOTIONAL_SUPPORT', 'Emotional Support Follow-up', 'Patient showed elevated anxiety or emotional distress', 'MEDIUM', 60, 'RETENTION', '{"sub_type": "emotional", "trigger": "anxiety_elevated_or_worsened"}', true)
ON CONFLICT (intervention_code) DO UPDATE SET
    intervention_name = EXCLUDED.intervention_name,
    description = EXCLUDED.description,
    priority_level = EXCLUDED.priority_level,
    priority_score = EXCLUDED.priority_score,
    category = EXCLUDED.category,
    trigger_conditions = EXCLUDED.trigger_conditions,
    is_active = true,
    updated_at = NOW();

-- Step 4: Insert new QUALITY interventions (10 types)

-- Medication Safety (4)
INSERT INTO public.intervention_definitions (
    intervention_code, intervention_name, description, priority_level, priority_score, category, trigger_conditions, is_active
) VALUES
('CONTRAINDICATION_ALERT', 'Contraindication Alert', 'Potential contraindication detected requiring urgent review', 'CRITICAL', 95, 'QUALITY', '{"sub_type": "medication_safety", "trigger": "is_contraindication_risk"}', true),
('DRUG_INTERACTION_REVIEW', 'Drug Interaction Review', 'Potential drug interaction between medications', 'HIGH', 80, 'QUALITY', '{"sub_type": "medication_safety", "trigger": "is_drug_interaction_risk"}', true),
('POLYPHARMACY_REVIEW', 'Polypharmacy Review', 'Patient on multiple medications - reconciliation needed', 'MEDIUM', 60, 'QUALITY', '{"sub_type": "medication_safety", "trigger": "is_polypharmacy_risk"}', true),
('DOSAGE_VERIFICATION', 'Dosage Verification', 'Dosage concern requires verification with physician', 'HIGH', 80, 'QUALITY', '{"sub_type": "medication_safety", "trigger": "is_dosage_risk"}', true)
ON CONFLICT (intervention_code) DO UPDATE SET
    intervention_name = EXCLUDED.intervention_name,
    description = EXCLUDED.description,
    priority_level = EXCLUDED.priority_level,
    priority_score = EXCLUDED.priority_score,
    category = EXCLUDED.category,
    trigger_conditions = EXCLUDED.trigger_conditions,
    is_active = true,
    updated_at = NOW();

-- Documentation & Protocol (3)
INSERT INTO public.intervention_definitions (
    intervention_code, intervention_name, description, priority_level, priority_score, category, trigger_conditions, is_active
) VALUES
('MISSING_DIAGNOSIS_ALERT', 'Missing Diagnosis Alert', 'Treatment prescribed without documented diagnosis', 'HIGH', 80, 'QUALITY', '{"sub_type": "documentation", "trigger": "is_diagnosis_risk"}', true),
('PROTOCOL_DEVIATION_REVIEW', 'Protocol Deviation Review', 'Treatment deviates from standard protocol', 'MEDIUM', 60, 'QUALITY', '{"sub_type": "documentation", "trigger": "is_protocol_risk"}', true),
('INCOMPLETE_WORKUP_ALERT', 'Incomplete Workup Alert', 'Recommended investigations not ordered', 'HIGH', 80, 'QUALITY', '{"sub_type": "documentation", "trigger": "is_workup_risk"}', true)
ON CONFLICT (intervention_code) DO UPDATE SET
    intervention_name = EXCLUDED.intervention_name,
    description = EXCLUDED.description,
    priority_level = EXCLUDED.priority_level,
    priority_score = EXCLUDED.priority_score,
    category = EXCLUDED.category,
    trigger_conditions = EXCLUDED.trigger_conditions,
    is_active = true,
    updated_at = NOW();

-- Follow-up Quality (3)
INSERT INTO public.intervention_definitions (
    intervention_code, intervention_name, description, priority_level, priority_score, category, trigger_conditions, is_active
) VALUES
('URGENT_FOLLOWUP_NEEDED', 'Urgent Follow-up Required', 'Urgent follow-up needed for condition within specific timeframe', 'HIGH', 80, 'QUALITY', '{"sub_type": "followup", "trigger": "is_followup_risk"}', true),
('SPECIALIST_REFERRAL_NEEDED', 'Specialist Referral Needed', 'Patient condition warrants specialist referral', 'MEDIUM', 60, 'QUALITY', '{"sub_type": "followup", "trigger": "is_referral_risk"}', true),
('PATIENT_EDUCATION_GAP', 'Patient Education Gap', 'Patient lacks understanding of treatment plan', 'LOW', 40, 'QUALITY', '{"sub_type": "followup", "trigger": "is_education_risk"}', true)
ON CONFLICT (intervention_code) DO UPDATE SET
    intervention_name = EXCLUDED.intervention_name,
    description = EXCLUDED.description,
    priority_level = EXCLUDED.priority_level,
    priority_score = EXCLUDED.priority_score,
    category = EXCLUDED.category,
    trigger_conditions = EXCLUDED.trigger_conditions,
    is_active = true,
    updated_at = NOW();

-- Step 5: Add unique constraint if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'intervention_definitions_code_unique'
    ) THEN
        ALTER TABLE public.intervention_definitions
        ADD CONSTRAINT intervention_definitions_code_unique UNIQUE (intervention_code);
    END IF;
END $$;

-- Summary comment
COMMENT ON TABLE public.intervention_definitions IS 'Master list of interventions - REVENUE (16), RETENTION (7), QUALITY (10) = 33 total active types';

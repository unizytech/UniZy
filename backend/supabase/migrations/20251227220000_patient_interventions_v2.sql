-- Patient Interventions v2: Expand for REVENUE, RETENTION, QUALITY categories
-- Removes EMOTIONAL category (replaced by the new 3 categories)
-- Adds new columns for category, sub-type, assessment linking, and revenue

-- ============================================================================
-- 1. Add new columns to patient_interventions
-- ============================================================================

-- Intervention category: REVENUE, RETENTION, or QUALITY
ALTER TABLE public.patient_interventions
ADD COLUMN IF NOT EXISTS intervention_category VARCHAR(20)
    CHECK (intervention_category IN ('REVENUE', 'RETENTION', 'QUALITY'));

COMMENT ON COLUMN public.patient_interventions.intervention_category IS 'High-level category: REVENUE (upsell), RETENTION (prevent dropoff), QUALITY (care gaps)';

-- Intervention sub-type for finer categorization
ALTER TABLE public.patient_interventions
ADD COLUMN IF NOT EXISTS intervention_sub_type VARCHAR(30);

COMMENT ON COLUMN public.patient_interventions.intervention_sub_type IS 'Sub-category: allied_health, clinical_upsell, diagnostics_rx, medication_safety, documentation, followup, retention';

-- Link to consultation_insights for traceability
ALTER TABLE public.patient_interventions
ADD COLUMN IF NOT EXISTS consultation_insights_id UUID
    REFERENCES public.consultation_insights(id) ON DELETE SET NULL;

COMMENT ON COLUMN public.patient_interventions.consultation_insights_id IS 'FK to consultation_insights that generated this intervention';

-- Revenue estimate (looked up from hospital_intervention_pricing)
ALTER TABLE public.patient_interventions
ADD COLUMN IF NOT EXISTS revenue_estimate DECIMAL(10,2);

COMMENT ON COLUMN public.patient_interventions.revenue_estimate IS 'Estimated revenue for REVENUE category interventions (from hospital pricing)';

-- Simple action statement
ALTER TABLE public.patient_interventions
ADD COLUMN IF NOT EXISTS action TEXT;

COMMENT ON COLUMN public.patient_interventions.action IS 'Simple action statement: what should be done';

-- Link to the assessment that triggered this intervention
ALTER TABLE public.patient_interventions
ADD COLUMN IF NOT EXISTS linked_assessment_type VARCHAR(50);

COMMENT ON COLUMN public.patient_interventions.linked_assessment_type IS 'Assessment type that triggered: allied_health_needs, clinical_severity, other_clinical_needs, patient_dropoff_risk, care_quality_risk';

ALTER TABLE public.patient_interventions
ADD COLUMN IF NOT EXISTS linked_assessment_id UUID;

COMMENT ON COLUMN public.patient_interventions.linked_assessment_id IS 'UUID of the assessment record that triggered this intervention';

-- ============================================================================
-- 2. Create indexes for new columns
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_patient_interventions_category
    ON public.patient_interventions(intervention_category);

CREATE INDEX IF NOT EXISTS idx_patient_interventions_sub_type
    ON public.patient_interventions(intervention_sub_type);

CREATE INDEX IF NOT EXISTS idx_patient_interventions_insights_id
    ON public.patient_interventions(consultation_insights_id);

CREATE INDEX IF NOT EXISTS idx_patient_interventions_assessment
    ON public.patient_interventions(linked_assessment_type, linked_assessment_id);

-- ============================================================================
-- 3. Backfill existing interventions as legacy (no category)
-- ============================================================================
-- Note: Existing emotional interventions will have NULL category
-- They can be cleaned up later or kept for historical reference
-- New interventions will always have a category set

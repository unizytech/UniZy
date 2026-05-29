-- Migration: Add take_up_likelihood column to patient_interventions
-- Description: Stores predicted likelihood (0-100) that patient will accept/follow intervention
-- Based on clinical severity, anxiety, financial concerns, compliance, and fear/distress signals

-- Add take_up_likelihood column
ALTER TABLE public.patient_interventions
ADD COLUMN IF NOT EXISTS take_up_likelihood SMALLINT
    CHECK (take_up_likelihood >= 0 AND take_up_likelihood <= 100);

-- Add comment explaining the column
COMMENT ON COLUMN public.patient_interventions.take_up_likelihood IS
    'Predicted likelihood (0-100) that patient will accept/follow this intervention. Calculated from clinical severity, anxiety (post-level + trajectory), financial concerns, compliance likelihood, and fear/distress emotions.';

-- Index for filtering/sorting by take-up likelihood (descending for "most likely" queries)
CREATE INDEX IF NOT EXISTS idx_patient_interventions_take_up
    ON public.patient_interventions(take_up_likelihood DESC)
    WHERE take_up_likelihood IS NOT NULL;

-- Composite index for category + take-up queries (e.g., "highest take-up REVENUE interventions")
CREATE INDEX IF NOT EXISTS idx_patient_interventions_category_take_up
    ON public.patient_interventions(intervention_category, take_up_likelihood DESC)
    WHERE take_up_likelihood IS NOT NULL;

-- Composite index for extraction + take-up queries (e.g., "interventions for this extraction sorted by likelihood")
CREATE INDEX IF NOT EXISTS idx_patient_interventions_extraction_take_up
    ON public.patient_interventions(extraction_id, take_up_likelihood DESC)
    WHERE take_up_likelihood IS NOT NULL;

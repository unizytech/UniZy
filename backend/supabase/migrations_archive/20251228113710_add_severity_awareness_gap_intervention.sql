-- Migration: Add SEVERITY_AWARENESS_GAP intervention definition
-- This intervention triggers when clinical severity is HIGH/CRITICAL but patient shows
-- LOW anxiety or LOW/MODERATE compliance (patient may not understand gravity of condition)

INSERT INTO public.intervention_definitions (
    intervention_code, intervention_name, description, priority_level, priority_score, category, trigger_conditions, is_active
) VALUES
('SEVERITY_AWARENESS_GAP', 'Severity Awareness Counseling', 'Patient may not understand gravity of condition - clinical severity is high but emotional response suggests low awareness', 'HIGH', 80, 'RETENTION', '{"sub_type": "education", "trigger": "severity_awareness_mismatch"}', true)
ON CONFLICT (intervention_code) DO UPDATE SET
    intervention_name = EXCLUDED.intervention_name,
    description = EXCLUDED.description,
    priority_level = EXCLUDED.priority_level,
    priority_score = EXCLUDED.priority_score,
    category = EXCLUDED.category,
    trigger_conditions = EXCLUDED.trigger_conditions,
    is_active = true,
    updated_at = NOW();

-- Update comment on table
COMMENT ON TABLE public.intervention_definitions IS 'Master list of interventions - REVENUE (16), RETENTION (8), QUALITY (10) = 34 total active types';

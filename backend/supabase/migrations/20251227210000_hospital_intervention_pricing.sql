-- Hospital Intervention Pricing Table
-- Hospital-specific pricing for revenue interventions
-- Part of the expanded patient interventions system (REVENUE, RETENTION, QUALITY)

-- ============================================================================
-- 1. Create hospital_intervention_pricing table
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.hospital_intervention_pricing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hospital_id UUID NOT NULL REFERENCES public.hospitals(id) ON DELETE CASCADE,
    intervention_type VARCHAR(50) NOT NULL,  -- e.g., "NUTRITIONAL_REFERRAL"
    service_name VARCHAR(100) NOT NULL,      -- Display name
    revenue_estimate DECIMAL(10,2) NOT NULL, -- Hospital-specific pricing
    currency VARCHAR(3) DEFAULT 'INR',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_hospital_intervention UNIQUE (hospital_id, intervention_type)
);

-- Add comments for documentation
COMMENT ON TABLE public.hospital_intervention_pricing IS 'Hospital-specific pricing catalog for revenue interventions';
COMMENT ON COLUMN public.hospital_intervention_pricing.intervention_type IS 'Intervention type code: NUTRITIONAL_REFERRAL, PHYSIOTHERAPY_REFERRAL, etc.';
COMMENT ON COLUMN public.hospital_intervention_pricing.service_name IS 'Human-readable service name for display';
COMMENT ON COLUMN public.hospital_intervention_pricing.revenue_estimate IS 'Estimated revenue in hospital currency';

-- Create indexes for lookups
CREATE INDEX IF NOT EXISTS idx_hospital_intervention_pricing_hospital_id
    ON public.hospital_intervention_pricing(hospital_id);
CREATE INDEX IF NOT EXISTS idx_hospital_intervention_pricing_type
    ON public.hospital_intervention_pricing(intervention_type);
CREATE INDEX IF NOT EXISTS idx_hospital_intervention_pricing_active
    ON public.hospital_intervention_pricing(hospital_id, is_active) WHERE is_active = true;

-- ============================================================================
-- 2. Sample data for Guru Hospital (16 revenue intervention types)
-- ============================================================================

-- Allied Health Services (9 types)
INSERT INTO public.hospital_intervention_pricing (hospital_id, intervention_type, service_name, revenue_estimate) VALUES
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'NUTRITIONAL_REFERRAL', 'Nutritional Counseling Session', 1500.00),
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'PHYSIOTHERAPY_REFERRAL', 'Physiotherapy Evaluation', 2000.00),
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'MENTAL_HEALTH_REFERRAL', 'Mental Health Consultation', 2500.00),
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'SLEEP_CLINIC_REFERRAL', 'Sleep Study Package', 8000.00),
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'CARDIAC_REHAB_REFERRAL', 'Cardiac Rehabilitation Program', 15000.00),
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'GENERAL_REHAB_REFERRAL', 'General Rehabilitation Package', 12000.00),
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'HOMECARE_SERVICES', 'Home Healthcare Package (Monthly)', 25000.00),
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'WELLNESS_PROGRAM', 'Wellness Program Enrollment', 5000.00),
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'TREATMENT_EDUCATION_PROGRAM', 'Patient Education Session', 500.00),

-- Clinical Upsell (4 types)
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'SURGICAL_CONSULTATION', 'Surgical Consultation', 3000.00),
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'SECOND_OPINION_CONSULT', 'Second Opinion Consultation', 2000.00),
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'ALTERNATIVE_TREATMENT_CONSULT', 'Alternative Treatment Review', 1500.00),
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'CHRONIC_CARE_PROGRAM', 'Chronic Care Management (Monthly)', 3500.00),

-- Diagnostics & Rx (3 types)
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'HOME_DIAGNOSTIC_COLLECTION', 'Home Sample Collection', 300.00),
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'PRESCRIPTION_REFILL_REMINDER', 'Pharmacy Refill Service', 100.00),
('44cc627a-320e-4c0e-bfa6-ec3c04168747', 'RECURRING_TEST_SCHEDULE', 'Scheduled Lab Panel', 1200.00);

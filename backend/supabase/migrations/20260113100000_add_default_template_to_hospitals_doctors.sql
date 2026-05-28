-- Add default_template_id to hospitals and doctors tables
-- This allows setting a default template per hospital and per doctor
-- Priority: Doctor default > Hospital default > null

-- Add default_template_id to hospitals table
ALTER TABLE public.hospitals
ADD COLUMN IF NOT EXISTS default_template_id UUID REFERENCES public.templates(id) ON DELETE SET NULL;

-- Add default_template_id to doctors table
ALTER TABLE public.doctors
ADD COLUMN IF NOT EXISTS default_template_id UUID REFERENCES public.templates(id) ON DELETE SET NULL;

-- Add indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_hospitals_default_template ON public.hospitals(default_template_id);
CREATE INDEX IF NOT EXISTS idx_doctors_default_template ON public.doctors(default_template_id);

COMMENT ON COLUMN public.hospitals.default_template_id IS 'Default template for all doctors in this hospital';
COMMENT ON COLUMN public.doctors.default_template_id IS 'Doctor-specific default template (overrides hospital default)';

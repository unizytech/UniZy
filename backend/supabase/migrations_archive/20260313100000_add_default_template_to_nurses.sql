-- Add default_template_id to nurses table
-- This allows setting a default template per nurse
-- Priority: Nurse default > PRESCREEN > Nurse active > Linked doctor default > Hospital default

ALTER TABLE public.nurses
ADD COLUMN IF NOT EXISTS default_template_id UUID REFERENCES public.templates(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_nurses_default_template ON public.nurses(default_template_id);

COMMENT ON COLUMN public.nurses.default_template_id IS 'Nurse-specific default template (used in nurse fallback chain)';

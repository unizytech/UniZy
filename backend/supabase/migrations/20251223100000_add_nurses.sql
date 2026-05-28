-- Add nurses support: nurses table, nurse_doctors junction, nurse_templates junction
-- Also adds edited_by_type to medical_extractions and nurse_id to recording_sessions

-- ============================================================================
-- 1. Create nurses table (similar to doctors)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.nurses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    qualification VARCHAR(100),  -- RN, LPN, BSN, etc.
    hospital_id UUID REFERENCES public.hospitals(id),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Add comments for documentation
COMMENT ON TABLE public.nurses IS 'Nurse users who can perform recording and extraction operations under doctor supervision';
COMMENT ON COLUMN public.nurses.qualification IS 'Nursing qualification: RN (Registered Nurse), LPN (Licensed Practical Nurse), BSN (Bachelor of Science in Nursing), etc.';

-- Create index for hospital lookup
CREATE INDEX IF NOT EXISTS idx_nurses_hospital_id ON public.nurses(hospital_id);
CREATE INDEX IF NOT EXISTS idx_nurses_email ON public.nurses(email);

-- ============================================================================
-- 2. Create nurse_doctors junction table
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.nurse_doctors (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nurse_id UUID NOT NULL REFERENCES public.nurses(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES public.doctors(id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE(nurse_id, doctor_id)
);

COMMENT ON TABLE public.nurse_doctors IS 'Junction table linking nurses to their supervising doctors';

-- Create indexes for lookups
CREATE INDEX IF NOT EXISTS idx_nurse_doctors_nurse_id ON public.nurse_doctors(nurse_id);
CREATE INDEX IF NOT EXISTS idx_nurse_doctors_doctor_id ON public.nurse_doctors(doctor_id);

-- ============================================================================
-- 3. Create nurse_templates junction table
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.nurse_templates (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nurse_id UUID NOT NULL REFERENCES public.nurses(id) ON DELETE CASCADE,
    template_id UUID NOT NULL REFERENCES public.templates(id) ON DELETE CASCADE,
    template_code VARCHAR(50) NOT NULL,  -- Denormalized for readability
    access_level VARCHAR(10) DEFAULT 'use' CHECK (access_level IN ('view', 'use')),
    is_active BOOLEAN DEFAULT false,
    activated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE(nurse_id, template_id)
);

COMMENT ON TABLE public.nurse_templates IS 'Junction table controlling which templates nurses can access';
COMMENT ON COLUMN public.nurse_templates.template_code IS 'Denormalized template_code for easy readability in database queries';
COMMENT ON COLUMN public.nurse_templates.access_level IS 'view = read-only, use = can use for extractions';
COMMENT ON COLUMN public.nurse_templates.is_active IS 'Whether this template is currently activated for the nurse';

-- Create indexes for lookups
CREATE INDEX IF NOT EXISTS idx_nurse_templates_nurse_id ON public.nurse_templates(nurse_id);
CREATE INDEX IF NOT EXISTS idx_nurse_templates_template_id ON public.nurse_templates(template_id);

-- ============================================================================
-- 4. Add edited_by_type to medical_extractions
-- ============================================================================
ALTER TABLE public.medical_extractions
ADD COLUMN IF NOT EXISTS edited_by_type VARCHAR(10) CHECK (edited_by_type IN ('doctor', 'nurse'));

COMMENT ON COLUMN public.medical_extractions.edited_by_type IS 'Type of user who edited: doctor or nurse';

-- ============================================================================
-- 5. Add nurse_id to recording_sessions
-- ============================================================================
ALTER TABLE public.recording_sessions
ADD COLUMN IF NOT EXISTS nurse_id UUID REFERENCES public.nurses(id);

COMMENT ON COLUMN public.recording_sessions.nurse_id IS 'Nurse who initiated/managed the recording session (if any)';

-- Create index for nurse lookup
CREATE INDEX IF NOT EXISTS idx_recording_sessions_nurse_id ON public.recording_sessions(nurse_id);

-- Doctor-to-doctor sharing (single table, two modes via patient_ids array)
-- patient_ids NULL  = share ALL patients (practice-wide, e.g., oncology)
-- patient_ids set   = share only those specific patients (selective handoff)
-- Bidirectional: both rows (A→B and B→A) stored for query simplicity
CREATE TABLE IF NOT EXISTS public.doctor_doctor_patients (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    doctor_id UUID NOT NULL REFERENCES public.doctors(id) ON DELETE CASCADE,
    linked_doctor_id UUID NOT NULL REFERENCES public.doctors(id) ON DELETE CASCADE,
    patient_ids UUID[] DEFAULT NULL,  -- NULL = all patients, array = specific patients
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    CHECK (doctor_id != linked_doctor_id)
);

-- Unique constraint: one row per doctor pair direction
CREATE UNIQUE INDEX idx_ddp_unique_pair
ON public.doctor_doctor_patients(doctor_id, linked_doctor_id);

-- Query index: find all linked doctors for a given doctor
CREATE INDEX IF NOT EXISTS idx_ddp_doctor_id
ON public.doctor_doctor_patients(doctor_id) WHERE is_active = true;

COMMENT ON TABLE public.doctor_doctor_patients
IS 'Doctor-to-doctor patient sharing. patient_ids=NULL shares all patients (practice-wide). '
   'patient_ids=[uuid,...] shares only those patients (selective handoff). '
   'Bidirectional: both rows (A→B and B→A) stored on link creation.';

-- Add doctor_ids array column to patients table
-- Allows linking a patient to multiple doctors within the same hospital

ALTER TABLE patients
ADD COLUMN doctor_ids uuid[] DEFAULT '{}';

-- Create index for efficient lookups by doctor_id
CREATE INDEX idx_patients_doctor_ids ON patients USING GIN (doctor_ids);

-- Add comment explaining the field
COMMENT ON COLUMN patients.doctor_ids IS 'Array of doctor UUIDs that this patient is linked to. Used for doctor-specific patient lists.';

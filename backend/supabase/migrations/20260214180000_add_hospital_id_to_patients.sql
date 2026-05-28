-- Add hospital_id to patients table for hospital-scoped patient isolation
-- Two hospitals with the same MRN (e.g., "1234") should NOT collide

-- Step 1: Add hospital_id column (nullable for backward compatibility)
ALTER TABLE patients ADD COLUMN IF NOT EXISTS hospital_id UUID REFERENCES hospitals(id);

-- Step 2: Drop old standalone unique constraint on patient_id
ALTER TABLE patients DROP CONSTRAINT IF EXISTS patients_patient_id_key;

-- Step 3: Create composite unique index
-- COALESCE handles NULL hospital_id so two patients with same MRN and no hospital don't collide
CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_patient_id_hospital
ON patients (patient_id, COALESCE(hospital_id, '00000000-0000-0000-0000-000000000000'));

-- Step 4: Index for hospital_id lookups
CREATE INDEX IF NOT EXISTS idx_patients_hospital_id ON patients (hospital_id) WHERE hospital_id IS NOT NULL;

-- Step 5: Backfill hospital_id from extraction history
-- patients → medical_extractions (patient_id) → doctors (doctor_id) → hospital_id
UPDATE patients p
SET hospital_id = sub.hospital_id
FROM (
    SELECT DISTINCT ON (me.patient_id) me.patient_id, d.hospital_id
    FROM medical_extractions me
    JOIN doctors d ON d.id = me.doctor_id
    WHERE d.hospital_id IS NOT NULL
    ORDER BY me.patient_id, me.created_at DESC
) sub
WHERE p.id = sub.patient_id
  AND p.hospital_id IS NULL;

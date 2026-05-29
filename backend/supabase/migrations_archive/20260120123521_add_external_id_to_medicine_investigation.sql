-- Add external_id column to doctor_medicines and doctor_investigations
-- This stores external system IDs (BrandID, TestID) from alternate CSV formats

-- Add external_id column to doctor_medicines
ALTER TABLE doctor_medicines
ADD COLUMN IF NOT EXISTS external_id VARCHAR(100);

-- Add external_id column to doctor_investigations
ALTER TABLE doctor_investigations
ADD COLUMN IF NOT EXISTS external_id VARCHAR(100);

-- Add external_id column to hospital_medicine_lists (for consistency)
ALTER TABLE hospital_medicine_lists
ADD COLUMN IF NOT EXISTS external_id VARCHAR(100);

-- Add external_id column to hospital_investigation_lists (for consistency)
ALTER TABLE hospital_investigation_lists
ADD COLUMN IF NOT EXISTS external_id VARCHAR(100);

-- Add index for lookups by external_id (doctor medicines)
CREATE INDEX IF NOT EXISTS idx_doctor_medicines_external_id
ON doctor_medicines(doctor_id, external_id) WHERE external_id IS NOT NULL;

-- Add index for lookups by external_id (doctor investigations)
CREATE INDEX IF NOT EXISTS idx_doctor_investigations_external_id
ON doctor_investigations(doctor_id, external_id) WHERE external_id IS NOT NULL;

-- Add index for lookups by external_id (hospital medicines)
CREATE INDEX IF NOT EXISTS idx_hospital_medicine_lists_external_id
ON hospital_medicine_lists(hospital_id, external_id) WHERE external_id IS NOT NULL;

-- Add index for lookups by external_id (hospital investigations)
CREATE INDEX IF NOT EXISTS idx_hospital_investigation_lists_external_id
ON hospital_investigation_lists(hospital_id, external_id) WHERE external_id IS NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN doctor_medicines.external_id IS 'External system ID (e.g., BrandID from EHR systems)';
COMMENT ON COLUMN doctor_investigations.external_id IS 'External system ID (e.g., TestID from EHR systems)';
COMMENT ON COLUMN hospital_medicine_lists.external_id IS 'External system ID (e.g., BrandID from EHR systems)';
COMMENT ON COLUMN hospital_investigation_lists.external_id IS 'External system ID (e.g., TestID from EHR systems)';

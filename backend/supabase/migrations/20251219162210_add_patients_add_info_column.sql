-- Add add_info JSONB column to patients table for storing additional hospital data
ALTER TABLE patients ADD COLUMN IF NOT EXISTS add_info JSONB DEFAULT NULL;

-- Add comment for documentation
COMMENT ON COLUMN patients.add_info IS 'Additional info from external hospital systems (e.g., NICU data: visitNumber, roomNo, bedNo, gestation)';

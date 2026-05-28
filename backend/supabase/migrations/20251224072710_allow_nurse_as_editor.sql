-- Migration: Allow nurses to be editors of extractions
-- The last_edited_by column needs to store either doctor_id OR nurse_id
-- We rely on edited_by_type column to know which table to look up

-- Drop the foreign key constraint that requires last_edited_by to reference doctors table
ALTER TABLE medical_extractions
DROP CONSTRAINT IF EXISTS medical_extractions_last_edited_by_fkey;

-- Add a comment to clarify the column usage
COMMENT ON COLUMN medical_extractions.last_edited_by IS
'UUID of the user who last edited. Check edited_by_type to determine if this is a doctor_id or nurse_id.';

-- Ensure edited_by_type column exists with proper constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'medical_extractions' AND column_name = 'edited_by_type'
    ) THEN
        ALTER TABLE medical_extractions
        ADD COLUMN edited_by_type VARCHAR(10) DEFAULT 'doctor';
    END IF;
END $$;

-- Add check constraint for edited_by_type values
ALTER TABLE medical_extractions
DROP CONSTRAINT IF EXISTS medical_extractions_edited_by_type_check;

ALTER TABLE medical_extractions
ADD CONSTRAINT medical_extractions_edited_by_type_check
CHECK (edited_by_type IN ('doctor', 'nurse'));

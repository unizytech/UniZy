-- Add 'validation_failed' as a valid status for recording_sessions
-- This status is used when audio quality validation fails but we want to preserve chunks for debugging

-- Drop the existing constraint
ALTER TABLE recording_sessions DROP CONSTRAINT IF EXISTS recording_sessions_status_check;

-- Add the new constraint with 'validation_failed' included
ALTER TABLE recording_sessions ADD CONSTRAINT recording_sessions_status_check
CHECK (status IN ('RECORDING', 'SUBMITTED', 'PROCESSING', 'COMPLETED', 'CANCELLED', 'ERROR', 'validation_failed'));

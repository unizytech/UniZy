-- Add error_message column to recording_sessions table
-- This column stores the error message when a recording session fails (e.g., audio quality validation failure)

ALTER TABLE recording_sessions
ADD COLUMN IF NOT EXISTS error_message TEXT;

-- Add comment for documentation
COMMENT ON COLUMN recording_sessions.error_message IS 'Error message when session fails (e.g., audio quality validation failure)';

-- Add validation_status column to recording_sessions
-- Supports deferred validation in /start API for faster response times.
-- Default 'completed' ensures backward compat with existing sessions.
ALTER TABLE recording_sessions
ADD COLUMN IF NOT EXISTS validation_status VARCHAR(20) DEFAULT 'completed';

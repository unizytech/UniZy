-- Add 'CHUNK_TIMEOUT' as a valid status for recording_sessions
--
-- The chunk-completion timeout (chunk_memory_store.start_completion_timeout)
-- writes status='CHUNK_TIMEOUT' from recording_session.py:1563 when chunks
-- fail to arrive within 120s after is_last. The status string was introduced
-- in commit 010f235 (2026-01-22) but the constraint migration that followed
-- on 2026-01-25 (20260125170400_add_validation_failed_status.sql) only added
-- 'validation_failed', leaving CHUNK_TIMEOUT unallowed. Affected sessions are
-- silently stranded in SUBMITTED with no error_message because the timeout
-- handler's status-write fails the check constraint and the except branch
-- only logs.

ALTER TABLE recording_sessions DROP CONSTRAINT IF EXISTS recording_sessions_status_check;

ALTER TABLE recording_sessions ADD CONSTRAINT recording_sessions_status_check
CHECK (status IN (
  'RECORDING',
  'SUBMITTED',
  'PROCESSING',
  'COMPLETED',
  'CANCELLED',
  'ERROR',
  'validation_failed',
  'CHUNK_TIMEOUT'
));

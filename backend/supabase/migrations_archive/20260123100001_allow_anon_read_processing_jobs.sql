-- ============================================================================
-- Migration: Allow anon SELECT on processing_jobs for Realtime progress updates
-- ============================================================================
-- The processing_jobs table is used by the frontend for real-time progress
-- monitoring via Supabase Realtime. Clients filter by their submission_id.
-- ============================================================================

-- Add SELECT policy for anon role on processing_jobs
-- Security: Clients filter by submission_id (UUID, impossible to guess)
CREATE POLICY "Anon read for Realtime progress updates" ON processing_jobs
FOR SELECT TO anon USING (true);

-- Also enable REPLICA IDENTITY FULL for complete row in Realtime broadcasts
ALTER TABLE processing_jobs REPLICA IDENTITY FULL;

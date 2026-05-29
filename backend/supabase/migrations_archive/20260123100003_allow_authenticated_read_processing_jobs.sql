-- ============================================================================
-- Migration: Allow authenticated users to SELECT from processing_jobs
-- ============================================================================
-- The frontend uses Supabase Auth for login. After login, the client uses
-- the 'authenticated' role, NOT 'anon'. The existing anon policy doesn't
-- apply to authenticated users, causing Realtime subscriptions to fail.
-- ============================================================================

-- Allow authenticated users to SELECT from processing_jobs for Realtime progress
CREATE POLICY "Authenticated users can read processing jobs" ON processing_jobs
FOR SELECT TO authenticated
USING (true);

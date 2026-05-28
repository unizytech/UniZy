-- ============================================================================
-- Migration: Allow authenticated users to SELECT from realtime_extraction_responses
-- ============================================================================
-- The frontend uses Supabase Auth for login. After login, the client uses
-- the 'authenticated' role, NOT 'anon'. The existing anon policy doesn't
-- apply to authenticated users, causing Realtime subscriptions to fail.
-- ============================================================================

-- Allow authenticated users to SELECT from realtime_extraction_responses for Realtime
CREATE POLICY "Authenticated users can read realtime extraction responses" ON realtime_extraction_responses
FOR SELECT TO authenticated
USING (true);

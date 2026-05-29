-- ============================================================================
-- Migration: Allow authenticated users to check their admin status
-- ============================================================================
-- The frontend uses Supabase Auth to login, then checks admin_users table
-- to verify if the user is an admin. This requires authenticated users to
-- be able to SELECT their own record from admin_users.
-- ============================================================================

-- Allow authenticated users to SELECT their own admin record
CREATE POLICY "Authenticated users can read own admin record" ON admin_users
FOR SELECT TO authenticated
USING (auth.uid() = auth_user_id);

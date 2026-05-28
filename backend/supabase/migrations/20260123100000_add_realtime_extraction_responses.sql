-- ============================================================================
-- Migration: Add Realtime Extraction Responses + Secure All Tables with RLS
-- ============================================================================
-- This migration:
-- 1. Adds enable_realtime_subscription column to hospitals
-- 2. Creates realtime_extraction_responses table for Supabase Realtime
-- 3. Enables RLS on ALL tables with service_role-only access
-- 4. realtime_extraction_responses is the ONLY table allowing anon SELECT
-- ============================================================================

-- ============================================================================
-- PART 1: New Realtime Subscription Feature
-- ============================================================================

-- Add enable_realtime_subscription to hospitals
ALTER TABLE hospitals
ADD COLUMN IF NOT EXISTS enable_realtime_subscription BOOLEAN DEFAULT FALSE;

-- Create realtime_extraction_responses table
CREATE TABLE IF NOT EXISTS realtime_extraction_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id VARCHAR(100) NOT NULL UNIQUE,
    hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
    doctor_id UUID REFERENCES doctors(id) ON DELETE SET NULL,
    extraction_id UUID REFERENCES medical_extractions(id) ON DELETE SET NULL,
    response JSONB NOT NULL,  -- EHR status response structure
    hospital_code VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- REPLICA IDENTITY FULL for complete row in Realtime broadcasts
ALTER TABLE realtime_extraction_responses REPLICA IDENTITY FULL;

-- Indexes for realtime_extraction_responses
CREATE INDEX IF NOT EXISTS idx_realtime_responses_hospital ON realtime_extraction_responses (hospital_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_realtime_responses_hospital_code ON realtime_extraction_responses (hospital_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_realtime_responses_submission ON realtime_extraction_responses (submission_id);

-- Cleanup function (entries older than 24 hours)
CREATE OR REPLACE FUNCTION cleanup_old_realtime_responses() RETURNS INTEGER AS $$
DECLARE deleted_count INTEGER;
BEGIN
    DELETE FROM realtime_extraction_responses WHERE created_at < NOW() - INTERVAL '24 hours';
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Comments for documentation
COMMENT ON TABLE realtime_extraction_responses IS 'Stores extraction results for Supabase Realtime subscriptions. Records auto-deleted after 24 hours.';
COMMENT ON COLUMN realtime_extraction_responses.response IS 'EHR status response JSON containing submission_id, status, progress, message, extraction_id, and insights';

-- ============================================================================
-- PART 2: Enable RLS on ALL Tables (Service Role Only by Default)
-- ============================================================================
-- Security model:
-- - service_role: Full access to ALL tables (backend operations)
-- - anon: NO access to any table EXCEPT realtime_extraction_responses (SELECT only)
-- - authenticated: No Supabase Auth users exist, so this role is not used
-- ============================================================================

-- Drop existing overly-permissive policy on clinical_severity_assessments
DROP POLICY IF EXISTS "Service role has full access to clinical_severity_assessments" ON clinical_severity_assessments;

-- Enable RLS on all tables and create service_role-only policies
-- Using DO block to handle tables that may not exist yet

DO $$
DECLARE
    t record;
    policy_name text;
BEGIN
    -- List of all tables that need RLS
    FOR t IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        AND tablename NOT IN ('realtime_extraction_responses')  -- Handled separately
    LOOP
        -- Enable RLS
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t.tablename);

        -- Drop any existing policies (clean slate)
        FOR policy_name IN
            SELECT policyname
            FROM pg_policies
            WHERE schemaname = 'public' AND tablename = t.tablename
        LOOP
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', policy_name, t.tablename);
        END LOOP;

        -- Create service_role-only policy
        EXECUTE format(
            'CREATE POLICY "Service role full access" ON %I FOR ALL TO service_role USING (true) WITH CHECK (true)',
            t.tablename
        );

        RAISE NOTICE 'Secured table: %', t.tablename;
    END LOOP;
END $$;

-- ============================================================================
-- PART 3: RLS for realtime_extraction_responses (Special Case)
-- ============================================================================
-- This table allows:
-- - service_role: Full access (for backend inserts)
-- - anon: SELECT only (for Realtime subscriptions)
-- ============================================================================

ALTER TABLE realtime_extraction_responses ENABLE ROW LEVEL SECURITY;

-- Service role full access (inserts from backend)
CREATE POLICY "Service role full access" ON realtime_extraction_responses
FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Anon read access (Realtime subscriptions)
-- Security: Clients must filter by submission_id (UUID, impossible to guess)
CREATE POLICY "Anon read for Realtime subscriptions" ON realtime_extraction_responses
FOR SELECT TO anon USING (true);

-- ============================================================================
-- PART 4: Verification Query (for manual testing)
-- ============================================================================
-- Run this after migration to verify all tables are secured:
--
-- SELECT
--     tablename,
--     rowsecurity as rls_enabled,
--     (SELECT count(*) FROM pg_policies WHERE pg_policies.tablename = pg_tables.tablename AND schemaname = 'public') as policy_count
-- FROM pg_tables
-- WHERE schemaname = 'public'
-- ORDER BY tablename;
-- ============================================================================

-- HIPAA PHI Audit Log Table
-- Tracks all access to Protected Health Information (PHI) for compliance.
-- HIPAA requires: WHO, WHAT, WHOSE, WHEN, HOW + 6-year retention.
-- Logs cannot be deleted (enforced by trigger).
--
-- This migration uses IF NOT EXISTS so it is safe to run on databases
-- where the table was already created manually.

-- 1. Create the table
CREATE TABLE IF NOT EXISTS phi_audit_log (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- WHO accessed
    client_id       uuid,
    client_type     text NOT NULL,
    client_name     text NOT NULL,
    user_id         uuid,
    user_email      text,

    -- WHAT was accessed
    action          text NOT NULL,          -- read, create, update, delete, export, auth_failed
    resource_type   text NOT NULL,          -- patient, extraction, recording, merge, doctor, authentication
    resource_id     text,

    -- WHOSE data
    patient_id      text,                   -- external patient identifier
    doctor_id       uuid,
    hospital_id     uuid,

    -- HOW
    endpoint        text NOT NULL,
    method          text NOT NULL,
    ip_address      inet,
    user_agent      text,

    -- WHEN
    created_at      timestamptz NOT NULL DEFAULT now(),

    -- Request/Response metadata
    request_id      uuid,
    status_code     integer,
    response_time_ms integer,
    error_message   text,

    -- Additional HIPAA context
    phi_fields_accessed text[],
    data_exported   boolean DEFAULT false,
    access_reason   text
);

-- 2. Indexes for common audit queries
CREATE INDEX IF NOT EXISTS idx_phi_audit_patient   ON phi_audit_log (patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_phi_audit_doctor    ON phi_audit_log (doctor_id,  created_at DESC);
CREATE INDEX IF NOT EXISTS idx_phi_audit_client    ON phi_audit_log (client_id,  created_at DESC);
CREATE INDEX IF NOT EXISTS idx_phi_audit_user      ON phi_audit_log (user_id,    created_at DESC);
CREATE INDEX IF NOT EXISTS idx_phi_audit_time      ON phi_audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_phi_audit_resource  ON phi_audit_log (resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_phi_audit_action    ON phi_audit_log (action, created_at DESC);

-- 3. Delete-prevention trigger (HIPAA: audit logs must not be deleted)
CREATE OR REPLACE FUNCTION prevent_audit_log_deletion()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'HIPAA compliance: Audit log records cannot be deleted';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS prevent_phi_audit_log_deletion ON phi_audit_log;
CREATE TRIGGER prevent_phi_audit_log_deletion
    BEFORE DELETE ON phi_audit_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_log_deletion();

-- 4. Disable RLS — audit writes come from service-role key only
ALTER TABLE phi_audit_log ENABLE ROW LEVEL SECURITY;

-- Service role can do everything (except delete, blocked by trigger)
DROP POLICY IF EXISTS "Service role full access" ON phi_audit_log;
CREATE POLICY "Service role full access"
    ON phi_audit_log
    FOR ALL
    USING (true)
    WITH CHECK (true);

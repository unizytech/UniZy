-- Admin Action Audit Log
-- Forensic record of every config-mutating action performed by admin users
-- via the admin UI. Distinct from phi_audit_log (which is HIPAA PHI access).
--
-- Populated automatically by AuthMiddleware for non-PHI admin writes
-- (POST/PUT/PATCH/DELETE). Endpoints may also call audit_service.log_admin_action
-- directly to record richer context (before/after values, resource_id).

CREATE TABLE IF NOT EXISTS admin_action_log (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- WHO performed the action
    admin_id        uuid NOT NULL,           -- references admin_users.id (no FK to keep log immutable across deletes)
    admin_email     text NOT NULL,           -- denormalized snapshot
    admin_role      text,                    -- super_admin | admin | viewer

    -- WHAT was done
    action          text NOT NULL,           -- create | update | delete
    resource_type   text,                    -- inferred from path (template, system_prompt_component, ...)
    resource_id     text,                    -- PK of affected row when known (string; some PKs are codes)

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

    -- Optional richer context (set by endpoints that capture diffs)
    before_value    jsonb,
    after_value     jsonb,
    request_body    jsonb                    -- redacted snapshot when captured
);

-- Indexes for common forensic queries
CREATE INDEX IF NOT EXISTS idx_admin_action_admin    ON admin_action_log (admin_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_action_email    ON admin_action_log (admin_email, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_action_resource ON admin_action_log (resource_type, resource_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_action_time     ON admin_action_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_action_action   ON admin_action_log (action, created_at DESC);

-- Delete-prevention trigger (forensic integrity)
-- Reuses the prevent_audit_log_deletion function created by 20260226120000_create_phi_audit_log.sql.
DROP TRIGGER IF EXISTS prevent_admin_action_log_deletion ON admin_action_log;
CREATE TRIGGER prevent_admin_action_log_deletion
    BEFORE DELETE ON admin_action_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_log_deletion();

-- RLS: service-role-only writes/reads (matches project convention)
ALTER TABLE admin_action_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access" ON admin_action_log;
CREATE POLICY "Service role full access"
    ON admin_action_log
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

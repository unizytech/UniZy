-- Add OAuth 2.0 Client Credentials auth mode for EHR clients
-- Allows EHRs to choose between static API keys and short-lived token-based auth

-- Add auth_mode and client_secret_hash to api_clients
ALTER TABLE api_clients ADD COLUMN auth_mode TEXT NOT NULL DEFAULT 'api_key';
ALTER TABLE api_clients ADD CONSTRAINT api_clients_auth_mode_check CHECK (auth_mode IN ('api_key', 'token'));
ALTER TABLE api_clients ADD COLUMN client_secret_hash TEXT;

-- Refresh tokens table (rotation-based)
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES api_clients(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ
);
CREATE INDEX idx_refresh_tokens_client_id ON refresh_tokens(client_id);
CREATE INDEX idx_refresh_tokens_lookup ON refresh_tokens(token_hash) WHERE is_revoked = FALSE;

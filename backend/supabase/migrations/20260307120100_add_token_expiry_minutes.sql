-- Add configurable token expiry per client (for token-mode EHR clients)
-- Default 60 minutes (1 hour). Range: 1-1440 (24 hours max).
ALTER TABLE api_clients ADD COLUMN token_expiry_minutes INTEGER NOT NULL DEFAULT 60;
ALTER TABLE api_clients ADD CONSTRAINT api_clients_token_expiry_check CHECK (token_expiry_minutes >= 1 AND token_expiry_minutes <= 1440);

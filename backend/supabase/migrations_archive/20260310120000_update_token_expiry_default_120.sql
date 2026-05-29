-- Change default token expiry from 60 to 120 minutes
ALTER TABLE api_clients ALTER COLUMN token_expiry_minutes SET DEFAULT 120;
-- Update existing clients that still have the old default
UPDATE api_clients SET token_expiry_minutes = 120 WHERE token_expiry_minutes = 60;

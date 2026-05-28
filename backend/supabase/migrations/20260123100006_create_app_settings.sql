-- Create app_settings table for runtime configuration
-- Allows toggling settings (e.g., use_vertex_ai) without redeployment

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed with use_vertex_ai setting
INSERT INTO app_settings (key, value, description)
VALUES ('use_vertex_ai', 'false', 'Use Vertex AI instead of Gemini API for batch operations')
ON CONFLICT (key) DO NOTHING;

-- Add comment
COMMENT ON TABLE app_settings IS 'Runtime application settings that can be toggled without redeployment';

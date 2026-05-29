-- Hospital EHR Integration Configuration
-- Allows configuring multiple EHR integrations per hospital (e.g., Aosta, Raster, Epic)

CREATE TABLE hospital_ehr (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
    ehr_integration_type VARCHAR(50) NOT NULL,  -- 'aosta', 'raster', 'epic', etc.
    api_url TEXT,                                -- Configurable endpoint URL
    api_key TEXT,                                -- Per-hospital API key (plain text)
    is_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- One config per EHR type per hospital
    UNIQUE(hospital_id, ehr_integration_type)
);

-- Add comment for documentation
COMMENT ON TABLE hospital_ehr IS 'Junction table for hospital EHR integrations. Each hospital can have multiple EHR systems configured.';
COMMENT ON COLUMN hospital_ehr.ehr_integration_type IS 'EHR system identifier: aosta, raster, epic, etc.';
COMMENT ON COLUMN hospital_ehr.api_url IS 'EHR API endpoint URL. If NULL, integration is disabled.';
COMMENT ON COLUMN hospital_ehr.api_key IS 'Optional API key for authentication. If NULL, sends without auth.';

-- Indexes for efficient lookups
CREATE INDEX idx_hospital_ehr_hospital ON hospital_ehr(hospital_id);
CREATE INDEX idx_hospital_ehr_type ON hospital_ehr(ehr_integration_type);
CREATE INDEX idx_hospital_ehr_enabled ON hospital_ehr(hospital_id, ehr_integration_type) WHERE is_enabled = true;

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_hospital_ehr_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER hospital_ehr_updated_at
    BEFORE UPDATE ON hospital_ehr
    FOR EACH ROW
    EXECUTE FUNCTION update_hospital_ehr_updated_at();

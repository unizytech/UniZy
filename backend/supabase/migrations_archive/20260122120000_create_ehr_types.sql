-- =============================================================================
-- Dynamic EHR Types with Doctor-Based Routing
-- =============================================================================
-- This migration creates:
-- 1. ehr_types master table - stores all EHR providers
-- 2. template_ehr junction table - template-specific URL suffixes per EHR
-- 3. Modifies hospital_ehr - adds ehr_type_id FK and is_default flag
-- 4. Modifies doctors - adds ehr_type_id for doctor-based routing
-- 5. get_doctor_ehr_config function - single query for routing info
-- =============================================================================

-- =============================================================================
-- STEP 1: Create ehr_types Master Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS ehr_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ehr_code VARCHAR(50) NOT NULL UNIQUE,  -- 'aosta', 'raster', 'neopead', etc.
    ehr_name VARCHAR(100) NOT NULL,         -- Display name
    default_api_url TEXT,                   -- Default URL (can be overridden per hospital)
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add comment for documentation
COMMENT ON TABLE ehr_types IS 'Master table for EHR providers. Each row represents an EHR system like Aosta, Raster, Neopead.';
COMMENT ON COLUMN ehr_types.ehr_code IS 'Unique identifier code: aosta, raster, neopead, etc.';
COMMENT ON COLUMN ehr_types.default_api_url IS 'Default API URL. Hospital config can override this.';

-- Index for efficient lookups
CREATE INDEX IF NOT EXISTS idx_ehr_types_code ON ehr_types(ehr_code);
CREATE INDEX IF NOT EXISTS idx_ehr_types_active ON ehr_types(is_active) WHERE is_active = true;

-- Seed data with default URLs
INSERT INTO ehr_types (ehr_code, ehr_name, default_api_url, description) VALUES
    ('aosta', 'Aosta', 'https://bbavav2.aostasoftware.com/api/v2/save', 'Aosta Software EHR integration'),
    ('raster', 'Raster', 'http://117.247.185.219:121/rasterihmsapi/onehat_integration.php', 'Raster General EMR integration'),
    ('neopead', 'Neopead', 'http://117.247.185.219:121/neopaed_transcribtion_integration', 'Neopead neonatal care system'),
    ('akhil', 'Akhil', NULL, 'Akhil EHR system'),
    ('iqvia', 'IQVIA', NULL, 'IQVIA clinical data platform'),
    ('karexpert', 'KareXpert', NULL, 'KareXpert hospital management'),
    ('uhiapp', 'UHIApp', NULL, 'UHI App integration'),
    ('kg_ehr', 'KG EHR', NULL, 'KG Hospital EHR'),
    ('kauvery_ehr', 'Kauvery EHR', NULL, 'Kauvery Hospital EHR'),
    ('gknm_ehr', 'GKNM EHR', NULL, 'GKNM Hospital EHR'),
    ('rits', 'RITS', NULL, 'RITS EHR system')
ON CONFLICT (ehr_code) DO NOTHING;


-- =============================================================================
-- STEP 2: Create template_ehr Junction Table
-- =============================================================================
-- Junction table: same template can have different URL suffixes per EHR type
-- URL Construction: final_url = base_url + template_ehr.url_suffix

CREATE TABLE IF NOT EXISTS template_ehr (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    ehr_type_id UUID NOT NULL REFERENCES ehr_types(id) ON DELETE CASCADE,
    url_suffix VARCHAR(255),  -- e.g., '/store-daycare-transcribed-data'
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(template_id, ehr_type_id)  -- One suffix per template-ehr combo
);

-- Add comments
COMMENT ON TABLE template_ehr IS 'Junction table for template-specific EHR URL suffixes. Used for Neopead templates that need different endpoints.';
COMMENT ON COLUMN template_ehr.url_suffix IS 'URL suffix appended to base URL. E.g., /store-daycare-transcribed-data for NEO_DAILY';

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_template_ehr_template ON template_ehr(template_id);
CREATE INDEX IF NOT EXISTS idx_template_ehr_ehr_type ON template_ehr(ehr_type_id);


-- =============================================================================
-- STEP 3: Seed template_ehr for Neopead Templates
-- =============================================================================
-- Map neonatal templates to their specific Neopead API endpoints

-- NEO_DAILY → /store-daycare-transcribed-data
INSERT INTO template_ehr (template_id, ehr_type_id, url_suffix)
SELECT t.id, et.id, '/store-daycare-transcribed-data'
FROM templates t, ehr_types et
WHERE UPPER(t.template_code) IN ('NEO_DAILY', 'NEONATAL_DAILY') AND et.ehr_code = 'neopead'
ON CONFLICT (template_id, ehr_type_id) DO NOTHING;

-- NEO_PROFORMA → /store-neonatal-proforma-transcribed-data
INSERT INTO template_ehr (template_id, ehr_type_id, url_suffix)
SELECT t.id, et.id, '/store-neonatal-proforma-transcribed-data'
FROM templates t, ehr_types et
WHERE UPPER(t.template_code) IN ('NEO_PROFORMA', 'NEONATAL_PROFORMA') AND et.ehr_code = 'neopead'
ON CONFLICT (template_id, ehr_type_id) DO NOTHING;

-- NEO_OP → /store-op-neonatal-transcribed-data
INSERT INTO template_ehr (template_id, ehr_type_id, url_suffix)
SELECT t.id, et.id, '/store-op-neonatal-transcribed-data'
FROM templates t, ehr_types et
WHERE UPPER(t.template_code) IN ('NEO_OP', 'NEONATAL_OP') AND et.ehr_code = 'neopead'
ON CONFLICT (template_id, ehr_type_id) DO NOTHING;

-- NEO_DISCHARGE → /store-nicu-discharge-transcribed-data
INSERT INTO template_ehr (template_id, ehr_type_id, url_suffix)
SELECT t.id, et.id, '/store-nicu-discharge-transcribed-data'
FROM templates t, ehr_types et
WHERE UPPER(t.template_code) IN ('NEO_DISCHARGE', 'NEONATAL_DISCHARGE') AND et.ehr_code = 'neopead'
ON CONFLICT (template_id, ehr_type_id) DO NOTHING;

-- NEO_ADMISSION → /store-nicu-admission-transcribed-data
INSERT INTO template_ehr (template_id, ehr_type_id, url_suffix)
SELECT t.id, et.id, '/store-nicu-admission-transcribed-data'
FROM templates t, ehr_types et
WHERE UPPER(t.template_code) IN ('NEO_ADMISSION', 'NEONATAL_ADMISSION') AND et.ehr_code = 'neopead'
ON CONFLICT (template_id, ehr_type_id) DO NOTHING;


-- =============================================================================
-- STEP 4: Modify hospital_ehr Table
-- =============================================================================
-- Add ehr_type_id foreign key and is_default flag

-- Add ehr_type_id column (nullable initially for migration)
ALTER TABLE hospital_ehr
    ADD COLUMN IF NOT EXISTS ehr_type_id UUID REFERENCES ehr_types(id);

-- Add is_default flag (one default per hospital)
ALTER TABLE hospital_ehr
    ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT false;

-- Add comments
COMMENT ON COLUMN hospital_ehr.ehr_type_id IS 'Foreign key to ehr_types. Replaces ehr_integration_type string.';
COMMENT ON COLUMN hospital_ehr.is_default IS 'If true, new doctors in this hospital are auto-assigned this EHR type.';

-- Migrate existing data: populate ehr_type_id from ehr_integration_type
UPDATE hospital_ehr he
SET ehr_type_id = et.id
FROM ehr_types et
WHERE he.ehr_integration_type = et.ehr_code
  AND he.ehr_type_id IS NULL;

-- Create partial unique index: only one default per hospital
-- Use DO block to handle IF NOT EXISTS for index
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_hospital_ehr_one_default') THEN
        CREATE UNIQUE INDEX idx_hospital_ehr_one_default
            ON hospital_ehr(hospital_id) WHERE is_default = true;
    END IF;
END$$;

-- Create index for ehr_type_id lookups
CREATE INDEX IF NOT EXISTS idx_hospital_ehr_ehr_type_id ON hospital_ehr(ehr_type_id);


-- =============================================================================
-- STEP 5: Modify doctors Table
-- =============================================================================
-- Add ehr_type_id column for doctor-based routing

ALTER TABLE doctors
    ADD COLUMN IF NOT EXISTS ehr_type_id UUID REFERENCES ehr_types(id);

-- Add comment
COMMENT ON COLUMN doctors.ehr_type_id IS 'Which EHR this doctor uses. NULL = no EHR sync. Determines routing on extraction.';

-- Index for efficient lookups
CREATE INDEX IF NOT EXISTS idx_doctors_ehr_type ON doctors(ehr_type_id);


-- =============================================================================
-- STEP 6: Create get_doctor_ehr_config Function
-- =============================================================================
-- Single query to get all routing info for a doctor
-- Returns: ehr_code, hospital_id, api_url, api_key, url_suffix

CREATE OR REPLACE FUNCTION get_doctor_ehr_config(p_doctor_id UUID, p_template_code VARCHAR DEFAULT NULL)
RETURNS TABLE(
    ehr_code VARCHAR,
    hospital_id UUID,
    api_url TEXT,
    api_key TEXT,
    url_suffix VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        et.ehr_code,
        d.hospital_id,
        COALESCE(he.api_url, et.default_api_url) as api_url,  -- Hospital overrides default
        he.api_key,
        te.url_suffix  -- Template + EHR specific suffix (e.g., neo_daily + neopead)
    FROM doctors d
    JOIN ehr_types et ON et.id = d.ehr_type_id
    JOIN hospital_ehr he ON he.hospital_id = d.hospital_id AND he.ehr_type_id = d.ehr_type_id
    LEFT JOIN templates t ON UPPER(t.template_code) = UPPER(p_template_code)
    LEFT JOIN template_ehr te ON te.template_id = t.id AND te.ehr_type_id = d.ehr_type_id
    WHERE d.id = p_doctor_id
      AND he.is_enabled = true
      AND COALESCE(he.api_url, et.default_api_url) IS NOT NULL;
END;
$$ LANGUAGE plpgsql;

-- Add comment
COMMENT ON FUNCTION get_doctor_ehr_config IS 'Single query for EHR routing. Returns NULL if doctor has no EHR or config is incomplete.';


-- =============================================================================
-- STEP 7: Create Helper Function to Get Hospital Default EHR
-- =============================================================================

CREATE OR REPLACE FUNCTION get_hospital_default_ehr_type_id(p_hospital_id UUID)
RETURNS UUID AS $$
DECLARE
    v_ehr_type_id UUID;
BEGIN
    SELECT ehr_type_id INTO v_ehr_type_id
    FROM hospital_ehr
    WHERE hospital_id = p_hospital_id
      AND is_default = true
      AND is_enabled = true
    LIMIT 1;

    RETURN v_ehr_type_id;
END;
$$ LANGUAGE plpgsql;

-- Add comment
COMMENT ON FUNCTION get_hospital_default_ehr_type_id IS 'Returns the default EHR type ID for a hospital (for auto-assigning to new doctors).';

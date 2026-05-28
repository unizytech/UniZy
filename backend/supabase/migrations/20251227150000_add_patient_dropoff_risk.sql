-- Migration: Add patient_dropoff_risk table
-- Purpose: Store patient drop-off probability calculations based on emotional, financial, and communication signals
-- Version: 1.0.0

CREATE TABLE patient_dropoff_risk (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    patient_id UUID,
    doctor_id UUID,

    -- Main output
    dropoff_probability DECIMAL(5,2) NOT NULL,  -- 0.00 to 100.00
    risk_level TEXT NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),

    -- 5 churn indicators (consolidated)
    is_financial_risk BOOLEAN DEFAULT FALSE,
    is_competitor_risk BOOLEAN DEFAULT FALSE,
    is_dissatisfaction_risk BOOLEAN DEFAULT FALSE,
    is_access_risk BOOLEAN DEFAULT FALSE,
    is_compliance_risk BOOLEAN DEFAULT FALSE,

    -- Reasons for each indicator
    financial_risk_reasons TEXT[] DEFAULT '{}',
    competitor_risk_reasons TEXT[] DEFAULT '{}',
    dissatisfaction_risk_reasons TEXT[] DEFAULT '{}',
    access_risk_reasons TEXT[] DEFAULT '{}',
    compliance_risk_reasons TEXT[] DEFAULT '{}',

    -- Anxiety trajectory data (Combined Mode)
    anxiety_pre_level TEXT,
    anxiety_post_level TEXT,
    anxiety_trajectory TEXT,  -- "Improved", "Stable", "Worsened", "Unable to determine"
    anxiety_modifier DECIMAL(3,2),

    -- Compliance data
    compliance_likelihood TEXT,
    compliance_modifier DECIMAL(3,2),

    -- Score breakdown
    base_probability DECIMAL(5,2),
    indicator_count INTEGER,
    primary_risk_driver TEXT,  -- The indicator with highest weight that's TRUE

    -- Input data for audit
    input_data JSONB DEFAULT '{}',

    -- Metadata
    calculation_version TEXT DEFAULT '1.0.0',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_dropoff_extraction UNIQUE (extraction_id)
);

-- Indexes for common queries
CREATE INDEX idx_dropoff_extraction ON patient_dropoff_risk(extraction_id);
CREATE INDEX idx_dropoff_patient ON patient_dropoff_risk(patient_id);
CREATE INDEX idx_dropoff_doctor ON patient_dropoff_risk(doctor_id);
CREATE INDEX idx_dropoff_risk_level ON patient_dropoff_risk(risk_level);
CREATE INDEX idx_dropoff_probability ON patient_dropoff_risk(dropoff_probability DESC);
CREATE INDEX idx_dropoff_created_at ON patient_dropoff_risk(created_at DESC);

-- Partial index for high-risk patients (common query)
CREATE INDEX idx_dropoff_high_critical ON patient_dropoff_risk(risk_level, created_at DESC)
    WHERE risk_level IN ('HIGH', 'CRITICAL');

-- Comments for documentation
COMMENT ON TABLE patient_dropoff_risk IS 'Patient drop-off probability (retention risk) calculations based on emotional, financial, and communication signals from consultations';
COMMENT ON COLUMN patient_dropoff_risk.dropoff_probability IS 'Probability (0-100%) that patient will not return for follow-up or abandon treatment';
COMMENT ON COLUMN patient_dropoff_risk.risk_level IS 'Risk category: LOW (5-29%), MEDIUM (30-49%), HIGH (50-69%), CRITICAL (70-95%)';
COMMENT ON COLUMN patient_dropoff_risk.is_financial_risk IS 'C1: Financial concerns or price sensitivity detected (25% weight)';
COMMENT ON COLUMN patient_dropoff_risk.is_competitor_risk IS 'C2: Patient considering other healthcare providers (10% weight)';
COMMENT ON COLUMN patient_dropoff_risk.is_dissatisfaction_risk IS 'C3: Dissatisfaction or weak rapport with doctor (25% weight)';
COMMENT ON COLUMN patient_dropoff_risk.is_access_risk IS 'C4: Access or logistics barriers to care (10% weight)';
COMMENT ON COLUMN patient_dropoff_risk.is_compliance_risk IS 'C5: Compliance concerns or treatment confusion (30% weight)';
COMMENT ON COLUMN patient_dropoff_risk.anxiety_modifier IS 'Multiplier based on anxiety trajectory: 0.75 (improved) to 1.30 (worsened)';
COMMENT ON COLUMN patient_dropoff_risk.compliance_modifier IS 'Multiplier based on compliance likelihood: 0.85 (high) to 1.25 (very low)';
COMMENT ON COLUMN patient_dropoff_risk.primary_risk_driver IS 'The highest-weighted TRUE indicator driving the risk score';

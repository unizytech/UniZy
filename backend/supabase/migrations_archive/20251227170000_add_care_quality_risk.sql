-- Care Quality Risk Score Table
-- Identifies potential quality gaps in clinical care delivery

CREATE TABLE care_quality_risk (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    patient_id UUID,
    doctor_id UUID,

    -- Main output
    care_quality_score DECIMAL(5,2) NOT NULL,  -- 0.00 to 100.00
    risk_level TEXT NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),

    -- 4 quality indicators
    is_medication_issue BOOLEAN DEFAULT FALSE,
    is_missed_red_flag BOOLEAN DEFAULT FALSE,
    is_incomplete_treatment BOOLEAN DEFAULT FALSE,
    is_followup_gap BOOLEAN DEFAULT FALSE,

    -- Reasons for each indicator (human-readable)
    medication_issue_reasons TEXT[] DEFAULT '{}',
    missed_red_flag_reasons TEXT[] DEFAULT '{}',
    incomplete_treatment_reasons TEXT[] DEFAULT '{}',
    followup_gap_reasons TEXT[] DEFAULT '{}',

    -- Severities for each indicator
    medication_issue_severity TEXT,
    missed_red_flag_severity TEXT,
    incomplete_treatment_severity TEXT,
    followup_gap_severity TEXT,

    -- Consolidated reasons (similar to other_clinical_needs, allied_health_needs)
    reasons TEXT[] DEFAULT '{}',

    -- Score breakdown
    base_score DECIMAL(5,2),
    indicator_count INTEGER,
    primary_risk_driver TEXT,

    -- Input data for audit
    input_data JSONB DEFAULT '{}',

    -- Metadata
    calculation_version TEXT DEFAULT '1.0.0',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_care_quality_extraction UNIQUE (extraction_id)
);

-- Comments
COMMENT ON TABLE care_quality_risk IS 'Care quality risk assessment identifying medication issues, missed red flags, incomplete treatment plans, and follow-up gaps';
COMMENT ON COLUMN care_quality_risk.care_quality_score IS 'Risk score 0-100% indicating care quality concerns';
COMMENT ON COLUMN care_quality_risk.reasons IS 'Consolidated human-readable array of all triggered indicator reasons';

-- Indexes
CREATE INDEX idx_care_quality_extraction ON care_quality_risk(extraction_id);
CREATE INDEX idx_care_quality_patient ON care_quality_risk(patient_id);
CREATE INDEX idx_care_quality_doctor ON care_quality_risk(doctor_id);
CREATE INDEX idx_care_quality_risk_level ON care_quality_risk(risk_level);
CREATE INDEX idx_care_quality_score ON care_quality_risk(care_quality_score DESC);
CREATE INDEX idx_care_quality_critical ON care_quality_risk(risk_level) WHERE risk_level IN ('HIGH', 'CRITICAL');
CREATE INDEX idx_care_quality_created ON care_quality_risk(created_at DESC);

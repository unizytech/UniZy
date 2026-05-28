-- Create other_clinical_needs table for tracking additional care requirements
-- Calculated automatically after each extraction, runs after clinical_severity

CREATE TABLE other_clinical_needs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    patient_id UUID,
    doctor_id UUID,

    -- Three boolean indicators
    is_followup_diagnostics BOOLEAN DEFAULT FALSE,
    is_recurring_diagnostics BOOLEAN DEFAULT FALSE,
    is_rx_refill BOOLEAN DEFAULT FALSE,

    -- Reasoning/evidence for each flag
    followup_diagnostics_reasons TEXT[] DEFAULT '{}',
    recurring_diagnostics_reasons TEXT[] DEFAULT '{}',
    rx_refill_reasons TEXT[] DEFAULT '{}',

    -- Input data used for detection (for debugging)
    input_data JSONB DEFAULT '{}',

    -- Link to clinical severity for is_chronic reference
    clinical_severity_id UUID REFERENCES clinical_severity_assessments(id),

    -- Metadata
    calculation_version TEXT DEFAULT '1.0.0',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_needs_extraction UNIQUE (extraction_id)
);

-- Indexes for common queries
CREATE INDEX idx_needs_extraction ON other_clinical_needs(extraction_id);
CREATE INDEX idx_needs_patient ON other_clinical_needs(patient_id);

-- Partial indexes for flag columns (only index TRUE values)
CREATE INDEX idx_needs_followup_diag ON other_clinical_needs(is_followup_diagnostics) WHERE is_followup_diagnostics = TRUE;
CREATE INDEX idx_needs_recurring_diag ON other_clinical_needs(is_recurring_diagnostics) WHERE is_recurring_diagnostics = TRUE;
CREATE INDEX idx_needs_rx_refill ON other_clinical_needs(is_rx_refill) WHERE is_rx_refill = TRUE;

-- Comments
COMMENT ON TABLE other_clinical_needs IS 'Tracks additional clinical care requirements identified from each extraction';
COMMENT ON COLUMN other_clinical_needs.is_followup_diagnostics IS 'TRUE if patient needs diagnostic tests before/at next visit';
COMMENT ON COLUMN other_clinical_needs.is_recurring_diagnostics IS 'TRUE if patient needs periodic/recurring tests based on chronic conditions';
COMMENT ON COLUMN other_clinical_needs.is_rx_refill IS 'TRUE if patient will need prescription refill (duration >30 days or chronic)';
COMMENT ON COLUMN other_clinical_needs.clinical_severity_id IS 'Reference to clinical severity assessment for is_chronic flag access';

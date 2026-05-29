-- Clinical Severity Assessments Table
-- Stores calculated clinical severity for each extraction
-- Based on ICD-10 codes, specialty, surgical status, and modifiers

CREATE TABLE IF NOT EXISTS clinical_severity_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    patient_id UUID,
    doctor_id UUID,

    -- Severity Result
    severity_level TEXT NOT NULL CHECK (severity_level IN ('LOW', 'MEDIUM', 'HIGH')),
    total_score INTEGER NOT NULL,

    -- Override Info (for critical conditions like cancer, MI, stroke)
    was_overridden BOOLEAN DEFAULT FALSE,
    override_reason TEXT,

    -- Score Breakdown (for transparency/auditing)
    score_breakdown JSONB NOT NULL DEFAULT '{}',
    -- Example: {"icd_score": 4, "specialty_score": 3, "surgical_score": 3, "modifier_score": 2, "base_score": 7}

    contributing_factors TEXT[] DEFAULT '{}',
    -- Example: ["ICD: I25.1 (Ischemic heart disease)", "Specialty: cardiology", "Polypharmacy: 5 meds"]

    -- Input Data (for debugging/auditing)
    input_data JSONB DEFAULT '{}',
    -- Stores the clinical input used for calculation

    -- Metadata
    calculation_version TEXT DEFAULT '1.0.0',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- One assessment per extraction
    CONSTRAINT unique_severity_extraction UNIQUE (extraction_id)
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_severity_extraction ON clinical_severity_assessments(extraction_id);
CREATE INDEX IF NOT EXISTS idx_severity_patient ON clinical_severity_assessments(patient_id);
CREATE INDEX IF NOT EXISTS idx_severity_doctor ON clinical_severity_assessments(doctor_id);
CREATE INDEX IF NOT EXISTS idx_severity_level ON clinical_severity_assessments(severity_level);
CREATE INDEX IF NOT EXISTS idx_severity_created_at ON clinical_severity_assessments(created_at DESC);

-- Enable RLS
ALTER TABLE clinical_severity_assessments ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Service role has full access
CREATE POLICY "Service role has full access to clinical_severity_assessments"
    ON clinical_severity_assessments
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Add comment for documentation
COMMENT ON TABLE clinical_severity_assessments IS 'Stores clinical severity calculations for medical extractions. Severity is calculated from ICD-10 codes, specialty, surgical status, and modifiers.';
COMMENT ON COLUMN clinical_severity_assessments.severity_level IS 'LOW (0-4 pts), MEDIUM (5-8 pts), HIGH (9+ pts or override)';
COMMENT ON COLUMN clinical_severity_assessments.was_overridden IS 'True if severity was auto-set to HIGH due to critical conditions (cancer, MI, stroke, etc.)';
COMMENT ON COLUMN clinical_severity_assessments.score_breakdown IS 'JSON breakdown of score components: icd_score, specialty_score, surgical_score, modifier_score';

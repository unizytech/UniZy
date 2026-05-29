-- Consultation Insights Table
-- Stores raw AI-extracted signals from Gemini (14 signal groups)
-- Used for clinical severity, other clinical needs, allied health needs, dropoff risk, care quality scoring
-- Also enables hospital management analytics on raw signals

CREATE TABLE consultation_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    patient_id UUID,
    doctor_id UUID,

    -- 14 Signal Groups (JSONB for flexibility + GIN indexes for analytics)
    patient_signals JSONB NOT NULL DEFAULT '{}',
    clinical_severity_signals JSONB NOT NULL DEFAULT '{}',
    diagnostic_needs JSONB NOT NULL DEFAULT '{}',
    medication_signals JSONB NOT NULL DEFAULT '{}',
    nutritional_signals JSONB NOT NULL DEFAULT '{}',
    physiotherapy_signals JSONB NOT NULL DEFAULT '{}',
    homecare_signals JSONB NOT NULL DEFAULT '{}',
    sleep_signals JSONB NOT NULL DEFAULT '{}',
    rehabilitation_signals JSONB NOT NULL DEFAULT '{}',
    wellness_signals JSONB NOT NULL DEFAULT '{}',
    mental_health_signals JSONB NOT NULL DEFAULT '{}',
    education_signals JSONB NOT NULL DEFAULT '{}',
    competitor_signals JSONB NOT NULL DEFAULT '{}',
    access_logistics_signals JSONB NOT NULL DEFAULT '{}',

    -- Metadata
    model_used VARCHAR(50) DEFAULT 'gemini-2.5-flash',
    extraction_version VARCHAR(20) DEFAULT '1.0.0',
    extraction_duration_ms INTEGER,
    raw_response JSONB,  -- Full Gemini response for debugging

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_extraction_insights UNIQUE (extraction_id)
);

-- Comments
COMMENT ON TABLE consultation_insights IS 'Raw AI-extracted clinical signals from Gemini (14 signal groups) for analytics and downstream scoring';
COMMENT ON COLUMN consultation_insights.patient_signals IS 'Age, demographics from consultation';
COMMENT ON COLUMN consultation_insights.clinical_severity_signals IS 'ICD codes, specialty, surgical, chronic flags for severity scoring';
COMMENT ON COLUMN consultation_insights.diagnostic_needs IS 'Followup tests, recurring diagnostics, refill needs';
COMMENT ON COLUMN consultation_insights.medication_signals IS 'Medication count, complexity, injection needed, controlled substances';
COMMENT ON COLUMN consultation_insights.competitor_signals IS 'Second opinion mentions, competitor hospital references, price sensitivity';
COMMENT ON COLUMN consultation_insights.access_logistics_signals IS 'Travel barriers, time constraints, pharmacy access issues';

-- Indexes for analytics queries
CREATE INDEX idx_consultation_insights_extraction ON consultation_insights(extraction_id);
CREATE INDEX idx_consultation_insights_patient ON consultation_insights(patient_id);
CREATE INDEX idx_consultation_insights_doctor ON consultation_insights(doctor_id);
CREATE INDEX idx_consultation_insights_created ON consultation_insights(created_at DESC);

-- GIN indexes for JSONB signal queries (hospital analytics)
CREATE INDEX idx_insights_severity_signals ON consultation_insights USING GIN (clinical_severity_signals);
CREATE INDEX idx_insights_competitor_signals ON consultation_insights USING GIN (competitor_signals);
CREATE INDEX idx_insights_access_signals ON consultation_insights USING GIN (access_logistics_signals);
CREATE INDEX idx_insights_medication_signals ON consultation_insights USING GIN (medication_signals);

-- Allied Health Needs Assessment Table
-- Identifies referral needs for allied health services based on emotional and medical extraction data
-- Triggered after emotional analysis completes

CREATE TABLE allied_health_needs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    patient_id UUID,
    doctor_id UUID,

    -- Consolidated priority level
    priority_level TEXT DEFAULT 'NONE'
        CHECK (priority_level IN ('NONE', 'LOW', 'MEDIUM', 'HIGH')),

    -- 9 boolean indicators for allied health services
    is_mental_health BOOLEAN DEFAULT FALSE,
    is_nutritional_health BOOLEAN DEFAULT FALSE,
    is_physiotherapy BOOLEAN DEFAULT FALSE,
    is_homecare BOOLEAN DEFAULT FALSE,
    is_sleep_therapy BOOLEAN DEFAULT FALSE,
    is_rehab_cardiac BOOLEAN DEFAULT FALSE,
    is_rehab_common BOOLEAN DEFAULT FALSE,
    is_treatment_education BOOLEAN DEFAULT FALSE,
    is_wellness BOOLEAN DEFAULT FALSE,

    -- Reasoning/evidence for each indicator
    mental_health_reasons TEXT[] DEFAULT '{}',
    nutritional_health_reasons TEXT[] DEFAULT '{}',
    physiotherapy_reasons TEXT[] DEFAULT '{}',
    homecare_reasons TEXT[] DEFAULT '{}',
    sleep_therapy_reasons TEXT[] DEFAULT '{}',
    rehab_cardiac_reasons TEXT[] DEFAULT '{}',
    rehab_common_reasons TEXT[] DEFAULT '{}',
    treatment_education_reasons TEXT[] DEFAULT '{}',
    wellness_reasons TEXT[] DEFAULT '{}',

    -- Input data used for detection (for debugging)
    input_data JSONB DEFAULT '{}',

    -- References to related assessments
    clinical_severity_id UUID REFERENCES clinical_severity_assessments(id),
    other_clinical_needs_id UUID REFERENCES other_clinical_needs(id),

    -- Metadata
    calculation_version TEXT DEFAULT '1.0.0',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_allied_needs_extraction UNIQUE (extraction_id)
);

-- Indexes for common queries
CREATE INDEX idx_allied_extraction ON allied_health_needs(extraction_id);
CREATE INDEX idx_allied_patient ON allied_health_needs(patient_id);
CREATE INDEX idx_allied_doctor ON allied_health_needs(doctor_id);
CREATE INDEX idx_allied_created ON allied_health_needs(created_at DESC);

-- Partial indexes for priority-based queries
CREATE INDEX idx_allied_priority ON allied_health_needs(priority_level)
    WHERE priority_level != 'NONE';

-- Partial indexes for each indicator (for filtering patients needing specific services)
CREATE INDEX idx_allied_mental ON allied_health_needs(is_mental_health)
    WHERE is_mental_health = TRUE;
CREATE INDEX idx_allied_nutrition ON allied_health_needs(is_nutritional_health)
    WHERE is_nutritional_health = TRUE;
CREATE INDEX idx_allied_physio ON allied_health_needs(is_physiotherapy)
    WHERE is_physiotherapy = TRUE;
CREATE INDEX idx_allied_homecare ON allied_health_needs(is_homecare)
    WHERE is_homecare = TRUE;
CREATE INDEX idx_allied_sleep ON allied_health_needs(is_sleep_therapy)
    WHERE is_sleep_therapy = TRUE;
CREATE INDEX idx_allied_rehab_cardiac ON allied_health_needs(is_rehab_cardiac)
    WHERE is_rehab_cardiac = TRUE;
CREATE INDEX idx_allied_rehab_common ON allied_health_needs(is_rehab_common)
    WHERE is_rehab_common = TRUE;
CREATE INDEX idx_allied_education ON allied_health_needs(is_treatment_education)
    WHERE is_treatment_education = TRUE;
CREATE INDEX idx_allied_wellness ON allied_health_needs(is_wellness)
    WHERE is_wellness = TRUE;

-- Comments for documentation
COMMENT ON TABLE allied_health_needs IS 'Allied health service referral needs assessment - triggered after emotional analysis';
COMMENT ON COLUMN allied_health_needs.priority_level IS 'Consolidated priority: HIGH (4+ or mental_health+any), MEDIUM (2-3), LOW (1), NONE (0)';
COMMENT ON COLUMN allied_health_needs.is_mental_health IS 'Needs mental health support (severe anxiety, depression, distress)';
COMMENT ON COLUMN allied_health_needs.is_nutritional_health IS 'Needs nutritional counseling (diabetes/obesity/cardiac + diet instructions)';
COMMENT ON COLUMN allied_health_needs.is_physiotherapy IS 'Needs physiotherapy (musculoskeletal/injury + PT mentioned)';
COMMENT ON COLUMN allied_health_needs.is_homecare IS 'Needs home care (age>70 + chronic + mobility issues)';
COMMENT ON COLUMN allied_health_needs.is_sleep_therapy IS 'Needs sleep therapy (snoring/apnea/fatigue + obesity/HTN)';
COMMENT ON COLUMN allied_health_needs.is_rehab_cardiac IS 'Needs cardiac rehabilitation (MI/ischemic/post-CABG)';
COMMENT ON COLUMN allied_health_needs.is_rehab_common IS 'Needs general rehabilitation (ortho surgery/stroke)';
COMMENT ON COLUMN allied_health_needs.is_treatment_education IS 'Needs treatment education (new diagnosis + understanding barrier)';
COMMENT ON COLUMN allied_health_needs.is_wellness IS 'Needs wellness program (lifestyle disease + prevention discussion)';

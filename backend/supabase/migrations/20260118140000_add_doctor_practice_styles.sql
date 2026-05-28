-- Migration: Add doctor practice style learning tables and triage layer configuration
-- Version: 1.0.0
-- Description: Phase 1 of Triage Engine Multi-Layer - Doctor Practice Style Learning
--
-- Tables created:
-- 1. triage_layer_config - Global configuration for triage layers (enable/disable)
-- 2. doctor_practice_styles - Aggregated doctor practice characteristics
--
-- Functions created:
-- 1. compute_doctor_practice_style - Computes practice style from feedback data
-- 2. get_doctor_practice_style - Get cached or compute fresh

-- =============================================================================
-- 0. triage_layer_config - Global configuration for triage layers
-- =============================================================================

CREATE TABLE IF NOT EXISTS triage_layer_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    layer_code VARCHAR(50) NOT NULL UNIQUE,
    layer_name VARCHAR(100) NOT NULL,
    description TEXT,

    -- Enable/disable flag
    is_enabled BOOLEAN DEFAULT FALSE,

    -- Layer weight for conflict resolution (0.0 - 1.0)
    weight NUMERIC(3,2) DEFAULT 1.0 CHECK (weight >= 0 AND weight <= 1),

    -- Layer-specific configuration (JSONB for flexibility)
    config JSONB DEFAULT '{}',

    -- Display order in admin UI
    display_order INT DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for enabled layers lookup
CREATE INDEX IF NOT EXISTS idx_triage_layer_config_enabled
ON triage_layer_config (is_enabled) WHERE is_enabled = TRUE;

COMMENT ON TABLE triage_layer_config IS 'Configuration for triage engine layers - controls which layers are active';
COMMENT ON COLUMN triage_layer_config.layer_code IS 'Unique code: base_mvp, doctor_practice, hospital_intelligence, rag_guidelines';
COMMENT ON COLUMN triage_layer_config.weight IS 'Layer weight for conflict resolution scoring (0.0-1.0)';
COMMENT ON COLUMN triage_layer_config.config IS 'Layer-specific JSON configuration (e.g., min_confidence, cache_hours)';

-- Seed default layer configurations (all OFF by default except base MVP)
INSERT INTO triage_layer_config (layer_code, layer_name, description, is_enabled, weight, display_order, config)
VALUES
    ('base_mvp', 'Base Triage (MVP)', 'Core triage engine with differential trees and Gemini AI gap analysis. Always active.', TRUE, 1.0, 1, '{"always_enabled": true}'),
    ('doctor_practice', 'Doctor Practice Style', 'Learn individual doctor investigation preferences and practice intensity (conservative/moderate/aggressive).', FALSE, 0.8, 2, '{"min_feedback_entries": 10, "cache_hours": 24}'),
    ('hospital_intelligence', 'Hospital/Peer Intelligence', 'Leverage patterns from same-specialty doctors across the hospital for peer benchmarking.', FALSE, 0.7, 3, '{"min_doctors_for_benchmark": 3, "aggregation_frequency": "daily"}'),
    ('rag_guidelines', 'Clinical Guidelines (RAG)', 'Evidence-based recommendations from medical society guidelines via RAG search.', FALSE, 0.9, 4, '{"max_guidelines_per_suggestion": 3, "min_similarity": 0.7}')
ON CONFLICT (layer_code) DO NOTHING;

-- Updated at trigger for triage_layer_config
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'triage_layer_config_updated_at') THEN
        CREATE TRIGGER triage_layer_config_updated_at
            BEFORE UPDATE ON triage_layer_config
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END
$$;

-- =============================================================================
-- 1. doctor_practice_styles - Aggregated doctor practice characteristics
-- =============================================================================

CREATE TABLE IF NOT EXISTS doctor_practice_styles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,

    -- Doctor specialty (denormalized for query efficiency)
    specialty TEXT,

    -- Practice style metrics (computed from suggestion patterns)
    practice_intensity TEXT CHECK (practice_intensity IN ('conservative', 'moderate', 'aggressive')),

    -- Investigation ordering patterns
    avg_investigations_per_extraction NUMERIC(5,2),
    avg_suggestions_accepted_per_extraction NUMERIC(5,2),

    -- Preferred patterns (JSONB for flexibility)
    -- Example: {"CBC": 45, "LFT": 32, "RFT": 28, "Thyroid": 15}
    preferred_investigation_types JSONB DEFAULT '{}',

    -- Example: {"infectious": 25, "metabolic": 18, "cardiac": 12}
    preferred_diagnosis_categories JSONB DEFAULT '{}',

    -- First-line approaches when encountering presentations
    -- Example: {"fever": ["CBC", "Dengue NS1"], "chest_pain": ["ECG", "Troponin"]}
    first_line_by_presentation JSONB DEFAULT '{}',

    -- Common rejection patterns
    -- Example: [{"pattern": "liver function", "reason": "not_relevant", "count": 5}]
    common_rejection_reasons JSONB DEFAULT '[]',

    -- Stats
    total_extractions_analyzed INT DEFAULT 0,
    total_suggestions_generated INT DEFAULT 0,
    total_feedback_entries INT DEFAULT 0,
    acceptance_rate NUMERIC(5,2),  -- Percentage

    -- Confidence level based on data volume
    confidence_level TEXT DEFAULT 'low' CHECK (confidence_level IN ('low', 'medium', 'high')),

    -- Timestamps
    last_computed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_doctor_practice_style UNIQUE(doctor_id)
);

-- Index for specialty-based queries
CREATE INDEX IF NOT EXISTS idx_doctor_practice_styles_specialty
ON doctor_practice_styles (specialty);

-- Index for practice intensity analysis
CREATE INDEX IF NOT EXISTS idx_doctor_practice_styles_intensity
ON doctor_practice_styles (practice_intensity);

COMMENT ON TABLE doctor_practice_styles IS 'Aggregated practice characteristics learned from doctor feedback on triage suggestions';
COMMENT ON COLUMN doctor_practice_styles.practice_intensity IS 'Overall practice style: conservative (fewer investigations), moderate, or aggressive (more investigations)';
COMMENT ON COLUMN doctor_practice_styles.preferred_investigation_types IS 'JSON map of investigation types to acceptance counts';
COMMENT ON COLUMN doctor_practice_styles.first_line_by_presentation IS 'JSON map of presentations to commonly accepted first-line investigations';
COMMENT ON COLUMN doctor_practice_styles.confidence_level IS 'low (<20 feedback), medium (20-100 feedback), high (>100 feedback)';

-- =============================================================================
-- 2. compute_doctor_practice_style - RPC function to compute practice style
-- =============================================================================

CREATE OR REPLACE FUNCTION compute_doctor_practice_style(p_doctor_id UUID)
RETURNS doctor_practice_styles AS $$
DECLARE
    v_result doctor_practice_styles%ROWTYPE;
    v_total_feedback INT;
    v_accepted_count INT;
    v_rejected_count INT;
    v_total_extractions INT;
    v_avg_inv_per_ext NUMERIC(5,2);
    v_avg_accepted_per_ext NUMERIC(5,2);
    v_acceptance_rate NUMERIC(5,2);
    v_specialty TEXT;
    v_confidence TEXT;
    v_practice_intensity TEXT;
    v_preferred_investigations JSONB;
    v_rejection_reasons JSONB;
    v_first_line JSONB;
BEGIN
    -- Get doctor's specialty
    SELECT d.specialization INTO v_specialty
    FROM doctors d
    WHERE d.id = p_doctor_id;

    -- Get total feedback entries
    SELECT COUNT(*) INTO v_total_feedback
    FROM triage_feedback tf
    WHERE tf.doctor_id = p_doctor_id;

    -- Get accepted and rejected counts
    SELECT
        COUNT(*) FILTER (WHERE feedback_type = 'accepted') as accepted,
        COUNT(*) FILTER (WHERE feedback_type = 'rejected') as rejected
    INTO v_accepted_count, v_rejected_count
    FROM triage_feedback tf
    WHERE tf.doctor_id = p_doctor_id;

    -- Get total unique extractions analyzed
    SELECT COUNT(DISTINCT tsl.extraction_id) INTO v_total_extractions
    FROM triage_suggestion_log tsl
    WHERE tsl.doctor_id = p_doctor_id;

    -- Calculate average investigations per extraction
    SELECT COALESCE(AVG(inv_count), 0) INTO v_avg_inv_per_ext
    FROM (
        SELECT tsl.extraction_id, COUNT(*) as inv_count
        FROM triage_suggestion_log tsl
        WHERE tsl.doctor_id = p_doctor_id
        AND tsl.suggestion_type = 'investigation'
        GROUP BY tsl.extraction_id
    ) subq;

    -- Calculate average accepted suggestions per extraction
    SELECT COALESCE(AVG(accepted_count), 0) INTO v_avg_accepted_per_ext
    FROM (
        SELECT tsl.extraction_id, COUNT(*) as accepted_count
        FROM triage_suggestion_log tsl
        JOIN triage_feedback tf ON tf.suggestion_id = tsl.id
        WHERE tsl.doctor_id = p_doctor_id
        AND tf.feedback_type = 'accepted'
        GROUP BY tsl.extraction_id
    ) subq;

    -- Calculate acceptance rate
    IF v_total_feedback > 0 THEN
        v_acceptance_rate := ROUND((v_accepted_count::NUMERIC / v_total_feedback::NUMERIC) * 100, 2);
    ELSE
        v_acceptance_rate := NULL;
    END IF;

    -- Determine confidence level
    IF v_total_feedback >= 100 THEN
        v_confidence := 'high';
    ELSIF v_total_feedback >= 20 THEN
        v_confidence := 'medium';
    ELSE
        v_confidence := 'low';
    END IF;

    -- Determine practice intensity based on investigation ordering
    IF v_avg_inv_per_ext >= 5 THEN
        v_practice_intensity := 'aggressive';
    ELSIF v_avg_inv_per_ext >= 2 THEN
        v_practice_intensity := 'moderate';
    ELSE
        v_practice_intensity := 'conservative';
    END IF;

    -- Get preferred investigation types (accepted investigations)
    SELECT COALESCE(jsonb_object_agg(inv_type, inv_count), '{}') INTO v_preferred_investigations
    FROM (
        SELECT
            LOWER(SUBSTRING(tsl.suggestion_text FROM 'Consider ordering: (.+)$')) as inv_type,
            COUNT(*) as inv_count
        FROM triage_suggestion_log tsl
        JOIN triage_feedback tf ON tf.suggestion_id = tsl.id
        WHERE tsl.doctor_id = p_doctor_id
        AND tf.feedback_type = 'accepted'
        AND tsl.suggestion_type = 'investigation'
        GROUP BY LOWER(SUBSTRING(tsl.suggestion_text FROM 'Consider ordering: (.+)$'))
        HAVING COUNT(*) >= 2
        ORDER BY inv_count DESC
        LIMIT 20
    ) subq
    WHERE inv_type IS NOT NULL;

    -- Get common rejection reasons
    SELECT COALESCE(jsonb_agg(rejection_data), '[]') INTO v_rejection_reasons
    FROM (
        SELECT jsonb_build_object(
            'pattern', LOWER(SUBSTRING(tsl.suggestion_text, 1, 50)),
            'reason', tf.rejection_reason,
            'count', COUNT(*)
        ) as rejection_data
        FROM triage_suggestion_log tsl
        JOIN triage_feedback tf ON tf.suggestion_id = tsl.id
        WHERE tsl.doctor_id = p_doctor_id
        AND tf.feedback_type = 'rejected'
        AND tf.rejection_reason IS NOT NULL
        GROUP BY LOWER(SUBSTRING(tsl.suggestion_text, 1, 50)), tf.rejection_reason
        HAVING COUNT(*) >= 2
        ORDER BY COUNT(*) DESC
        LIMIT 10
    ) subq;

    -- Build first-line by presentation (placeholder - needs more data)
    v_first_line := '{}';

    -- Upsert into doctor_practice_styles
    INSERT INTO doctor_practice_styles (
        doctor_id,
        specialty,
        practice_intensity,
        avg_investigations_per_extraction,
        avg_suggestions_accepted_per_extraction,
        preferred_investigation_types,
        common_rejection_reasons,
        first_line_by_presentation,
        total_extractions_analyzed,
        total_suggestions_generated,
        total_feedback_entries,
        acceptance_rate,
        confidence_level,
        last_computed_at,
        updated_at
    ) VALUES (
        p_doctor_id,
        v_specialty,
        v_practice_intensity,
        v_avg_inv_per_ext,
        v_avg_accepted_per_ext,
        v_preferred_investigations,
        v_rejection_reasons,
        v_first_line,
        v_total_extractions,
        (SELECT COUNT(*) FROM triage_suggestion_log WHERE doctor_id = p_doctor_id),
        v_total_feedback,
        v_acceptance_rate,
        v_confidence,
        NOW(),
        NOW()
    )
    ON CONFLICT (doctor_id) DO UPDATE SET
        specialty = EXCLUDED.specialty,
        practice_intensity = EXCLUDED.practice_intensity,
        avg_investigations_per_extraction = EXCLUDED.avg_investigations_per_extraction,
        avg_suggestions_accepted_per_extraction = EXCLUDED.avg_suggestions_accepted_per_extraction,
        preferred_investigation_types = EXCLUDED.preferred_investigation_types,
        common_rejection_reasons = EXCLUDED.common_rejection_reasons,
        first_line_by_presentation = EXCLUDED.first_line_by_presentation,
        total_extractions_analyzed = EXCLUDED.total_extractions_analyzed,
        total_suggestions_generated = EXCLUDED.total_suggestions_generated,
        total_feedback_entries = EXCLUDED.total_feedback_entries,
        acceptance_rate = EXCLUDED.acceptance_rate,
        confidence_level = EXCLUDED.confidence_level,
        last_computed_at = EXCLUDED.last_computed_at,
        updated_at = EXCLUDED.updated_at
    RETURNING * INTO v_result;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION compute_doctor_practice_style IS 'Computes and caches aggregated practice style metrics from triage feedback data';

-- =============================================================================
-- 3. get_doctor_practice_style - Get cached or compute fresh
-- =============================================================================

CREATE OR REPLACE FUNCTION get_doctor_practice_style(
    p_doctor_id UUID,
    p_max_age_hours INT DEFAULT 24
)
RETURNS doctor_practice_styles AS $$
DECLARE
    v_result doctor_practice_styles%ROWTYPE;
    v_last_computed TIMESTAMPTZ;
BEGIN
    -- Check for existing cached style
    SELECT * INTO v_result
    FROM doctor_practice_styles
    WHERE doctor_id = p_doctor_id;

    -- If no cache or cache is stale, recompute
    IF v_result IS NULL OR
       v_result.last_computed_at < NOW() - (p_max_age_hours || ' hours')::INTERVAL THEN
        v_result := compute_doctor_practice_style(p_doctor_id);
    END IF;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_doctor_practice_style IS 'Returns cached practice style or computes fresh if stale';

-- =============================================================================
-- 4. Updated at trigger
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'doctor_practice_styles_updated_at') THEN
        CREATE TRIGGER doctor_practice_styles_updated_at
            BEFORE UPDATE ON doctor_practice_styles
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END
$$;

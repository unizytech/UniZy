-- Migration: Add hospital and peer intelligence tables
-- Version: 1.0.0
-- Description: Phase 2 of Triage Engine Multi-Layer - Hospital/Peer Intelligence
--
-- Tables created:
-- 1. hospital_specialty_patterns - Aggregated patterns by hospital + specialty
-- 2. specialty_benchmarks - Cross-hospital specialty benchmarks
--
-- Functions created:
-- 1. compute_hospital_specialty_patterns - Aggregates patterns for a hospital/specialty
-- 2. get_peer_comparison - Compare doctor against peers
-- 3. compute_all_hospital_patterns - Background job to update all patterns

-- =============================================================================
-- 1. hospital_specialty_patterns - Aggregated patterns by hospital + specialty
-- =============================================================================

CREATE TABLE IF NOT EXISTS hospital_specialty_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
    specialty TEXT NOT NULL,

    -- Aggregated metrics
    doctor_count INT DEFAULT 0,
    total_extractions INT DEFAULT 0,
    total_suggestions INT DEFAULT 0,
    total_feedback INT DEFAULT 0,

    -- Pattern data (JSONB for flexibility)
    -- Example: {"CBC": 0.85, "LFT": 0.72, "RFT": 0.65}
    common_investigations JSONB DEFAULT '{}',

    -- Example: {"infectious": 0.35, "metabolic": 0.22, "cardiac": 0.18}
    common_diagnoses JSONB DEFAULT '{}',

    -- Average metrics
    avg_suggestions_per_extraction NUMERIC(5,2),
    avg_acceptance_rate NUMERIC(5,2),

    -- Percentile thresholds for outlier detection
    -- Example: {"CBC": 0.60, "LFT": 0.45} - 25th percentile
    investigation_frequency_p25 JSONB DEFAULT '{}',
    -- Example: {"CBC": 0.95, "LFT": 0.85} - 75th percentile
    investigation_frequency_p75 JSONB DEFAULT '{}',

    -- Practice intensity distribution
    -- Example: {"conservative": 3, "moderate": 8, "aggressive": 2}
    intensity_distribution JSONB DEFAULT '{}',

    -- Timestamps
    last_computed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_hospital_specialty UNIQUE(hospital_id, specialty)
);

-- Index for specialty-wide queries
CREATE INDEX IF NOT EXISTS idx_hospital_specialty_patterns_specialty
ON hospital_specialty_patterns (specialty);

-- Index for hospital queries
CREATE INDEX IF NOT EXISTS idx_hospital_specialty_patterns_hospital
ON hospital_specialty_patterns (hospital_id);

COMMENT ON TABLE hospital_specialty_patterns IS 'Aggregated triage patterns by hospital and specialty for peer intelligence';
COMMENT ON COLUMN hospital_specialty_patterns.common_investigations IS 'Investigation name -> frequency (0.0-1.0) showing how often each is ordered';
COMMENT ON COLUMN hospital_specialty_patterns.investigation_frequency_p25 IS '25th percentile frequencies for outlier detection (below = conservative)';
COMMENT ON COLUMN hospital_specialty_patterns.investigation_frequency_p75 IS '75th percentile frequencies for outlier detection (above = aggressive)';

-- =============================================================================
-- 2. specialty_benchmarks - Cross-hospital specialty benchmarks
-- =============================================================================

CREATE TABLE IF NOT EXISTS specialty_benchmarks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    specialty TEXT NOT NULL UNIQUE,

    -- Aggregated across all hospitals
    total_doctors INT DEFAULT 0,
    total_hospitals INT DEFAULT 0,
    total_extractions INT DEFAULT 0,

    -- Benchmark metrics
    avg_investigations_ordered NUMERIC(5,2),
    avg_acceptance_rate NUMERIC(5,2),

    -- Common patterns across all hospitals
    -- Example: ["fever", "cough", "abdominal_pain"]
    common_presentations JSONB DEFAULT '[]',

    -- Example: ["Hypoxia", "Tachycardia", "Severe Anemia"]
    common_red_flags_detected JSONB DEFAULT '[]',

    -- Example: {"CBC": 0.88, "LFT": 0.65}
    benchmark_investigation_rates JSONB DEFAULT '{}',

    -- Timestamps
    last_computed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE specialty_benchmarks IS 'Cross-hospital specialty benchmarks for national/regional comparisons';
COMMENT ON COLUMN specialty_benchmarks.benchmark_investigation_rates IS 'National/regional benchmark rates for common investigations';

-- =============================================================================
-- 3. compute_hospital_specialty_patterns - RPC to compute patterns
-- =============================================================================

CREATE OR REPLACE FUNCTION compute_hospital_specialty_patterns(
    p_hospital_id UUID,
    p_specialty TEXT
)
RETURNS hospital_specialty_patterns AS $$
DECLARE
    v_result hospital_specialty_patterns%ROWTYPE;
    v_doctor_count INT;
    v_total_extractions INT;
    v_total_suggestions INT;
    v_total_feedback INT;
    v_common_investigations JSONB;
    v_avg_suggestions NUMERIC(5,2);
    v_avg_acceptance NUMERIC(5,2);
    v_intensity_dist JSONB;
BEGIN
    -- Count doctors with this specialty in hospital
    SELECT COUNT(DISTINCT d.id) INTO v_doctor_count
    FROM doctors d
    WHERE d.hospital_id = p_hospital_id
    AND d.specialization = p_specialty;

    -- If no doctors, return NULL
    IF v_doctor_count = 0 THEN
        RETURN NULL;
    END IF;

    -- Count total extractions for this specialty
    SELECT COUNT(DISTINCT me.id) INTO v_total_extractions
    FROM medical_extractions me
    JOIN doctors d ON me.doctor_id = d.id
    WHERE d.hospital_id = p_hospital_id
    AND d.specialization = p_specialty;

    -- Count total suggestions
    SELECT COUNT(*) INTO v_total_suggestions
    FROM triage_suggestion_log tsl
    JOIN doctors d ON tsl.doctor_id = d.id
    WHERE d.hospital_id = p_hospital_id
    AND d.specialization = p_specialty;

    -- Count total feedback
    SELECT COUNT(*) INTO v_total_feedback
    FROM triage_feedback tf
    JOIN doctors d ON tf.doctor_id = d.id
    WHERE d.hospital_id = p_hospital_id
    AND d.specialization = p_specialty;

    -- Calculate average suggestions per extraction
    IF v_total_extractions > 0 THEN
        v_avg_suggestions := v_total_suggestions::NUMERIC / v_total_extractions::NUMERIC;
    ELSE
        v_avg_suggestions := 0;
    END IF;

    -- Calculate average acceptance rate
    SELECT COALESCE(
        ROUND(
            (COUNT(*) FILTER (WHERE tf.feedback_type = 'accepted')::NUMERIC /
            NULLIF(COUNT(*), 0)::NUMERIC) * 100, 2
        ), 0
    ) INTO v_avg_acceptance
    FROM triage_feedback tf
    JOIN doctors d ON tf.doctor_id = d.id
    WHERE d.hospital_id = p_hospital_id
    AND d.specialization = p_specialty;

    -- Get common investigations (aggregated acceptance rates)
    SELECT COALESCE(jsonb_object_agg(inv_type, acceptance_rate), '{}') INTO v_common_investigations
    FROM (
        SELECT
            LOWER(SUBSTRING(tsl.suggestion_text FROM 'Consider ordering: (.+)$')) as inv_type,
            ROUND(
                COUNT(*) FILTER (WHERE tf.feedback_type = 'accepted')::NUMERIC /
                NULLIF(COUNT(*), 0)::NUMERIC, 2
            ) as acceptance_rate
        FROM triage_suggestion_log tsl
        JOIN doctors d ON tsl.doctor_id = d.id
        LEFT JOIN triage_feedback tf ON tf.suggestion_id = tsl.id
        WHERE d.hospital_id = p_hospital_id
        AND d.specialization = p_specialty
        AND tsl.suggestion_type = 'investigation'
        GROUP BY LOWER(SUBSTRING(tsl.suggestion_text FROM 'Consider ordering: (.+)$'))
        HAVING COUNT(*) >= 3
        ORDER BY COUNT(*) DESC
        LIMIT 20
    ) subq
    WHERE inv_type IS NOT NULL;

    -- Get practice intensity distribution
    SELECT COALESCE(jsonb_object_agg(practice_intensity, doctor_count), '{}') INTO v_intensity_dist
    FROM (
        SELECT practice_intensity, COUNT(*) as doctor_count
        FROM doctor_practice_styles dps
        JOIN doctors d ON dps.doctor_id = d.id
        WHERE d.hospital_id = p_hospital_id
        AND d.specialization = p_specialty
        GROUP BY practice_intensity
    ) subq;

    -- Upsert into hospital_specialty_patterns
    INSERT INTO hospital_specialty_patterns (
        hospital_id,
        specialty,
        doctor_count,
        total_extractions,
        total_suggestions,
        total_feedback,
        common_investigations,
        avg_suggestions_per_extraction,
        avg_acceptance_rate,
        intensity_distribution,
        last_computed_at,
        updated_at
    ) VALUES (
        p_hospital_id,
        p_specialty,
        v_doctor_count,
        v_total_extractions,
        v_total_suggestions,
        v_total_feedback,
        v_common_investigations,
        v_avg_suggestions,
        v_avg_acceptance,
        v_intensity_dist,
        NOW(),
        NOW()
    )
    ON CONFLICT (hospital_id, specialty) DO UPDATE SET
        doctor_count = EXCLUDED.doctor_count,
        total_extractions = EXCLUDED.total_extractions,
        total_suggestions = EXCLUDED.total_suggestions,
        total_feedback = EXCLUDED.total_feedback,
        common_investigations = EXCLUDED.common_investigations,
        avg_suggestions_per_extraction = EXCLUDED.avg_suggestions_per_extraction,
        avg_acceptance_rate = EXCLUDED.avg_acceptance_rate,
        intensity_distribution = EXCLUDED.intensity_distribution,
        last_computed_at = EXCLUDED.last_computed_at,
        updated_at = EXCLUDED.updated_at
    RETURNING * INTO v_result;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION compute_hospital_specialty_patterns IS 'Computes aggregated triage patterns for a hospital/specialty combination';

-- =============================================================================
-- 4. get_peer_comparison - Compare doctor against peers
-- =============================================================================

CREATE OR REPLACE FUNCTION get_peer_comparison(p_doctor_id UUID)
RETURNS TABLE (
    metric TEXT,
    doctor_value NUMERIC,
    peer_avg NUMERIC,
    peer_p25 NUMERIC,
    peer_p75 NUMERIC,
    is_outlier BOOLEAN,
    outlier_direction TEXT
) AS $$
DECLARE
    v_hospital_id UUID;
    v_specialty TEXT;
    v_doctor_style doctor_practice_styles%ROWTYPE;
    v_hospital_patterns hospital_specialty_patterns%ROWTYPE;
BEGIN
    -- Get doctor's hospital and specialty
    SELECT d.hospital_id, d.specialization INTO v_hospital_id, v_specialty
    FROM doctors d
    WHERE d.id = p_doctor_id;

    IF v_hospital_id IS NULL OR v_specialty IS NULL THEN
        RETURN;
    END IF;

    -- Get doctor's practice style
    SELECT * INTO v_doctor_style
    FROM doctor_practice_styles
    WHERE doctor_id = p_doctor_id;

    -- Get hospital patterns for this specialty
    SELECT * INTO v_hospital_patterns
    FROM hospital_specialty_patterns
    WHERE hospital_id = v_hospital_id AND specialty = v_specialty;

    IF v_hospital_patterns IS NULL THEN
        -- Try to compute patterns
        v_hospital_patterns := compute_hospital_specialty_patterns(v_hospital_id, v_specialty);
    END IF;

    IF v_hospital_patterns IS NULL THEN
        RETURN;
    END IF;

    -- Return comparison metrics
    -- 1. Investigations per extraction
    metric := 'investigations_per_extraction';
    doctor_value := COALESCE(v_doctor_style.avg_investigations_per_extraction, 0);
    peer_avg := COALESCE(v_hospital_patterns.avg_suggestions_per_extraction, 0);
    peer_p25 := peer_avg * 0.7;  -- Approximation
    peer_p75 := peer_avg * 1.3;  -- Approximation
    is_outlier := (doctor_value < peer_p25 OR doctor_value > peer_p75);
    outlier_direction := CASE
        WHEN doctor_value < peer_p25 THEN 'below'
        WHEN doctor_value > peer_p75 THEN 'above'
        ELSE NULL
    END;
    RETURN NEXT;

    -- 2. Acceptance rate
    metric := 'acceptance_rate';
    doctor_value := COALESCE(v_doctor_style.acceptance_rate, 0);
    peer_avg := COALESCE(v_hospital_patterns.avg_acceptance_rate, 0);
    peer_p25 := GREATEST(peer_avg - 15, 0);
    peer_p75 := LEAST(peer_avg + 15, 100);
    is_outlier := (doctor_value < peer_p25 OR doctor_value > peer_p75);
    outlier_direction := CASE
        WHEN doctor_value < peer_p25 THEN 'below'
        WHEN doctor_value > peer_p75 THEN 'above'
        ELSE NULL
    END;
    RETURN NEXT;

    -- 3. Feedback engagement
    metric := 'feedback_engagement';
    doctor_value := COALESCE(v_doctor_style.total_feedback_entries, 0);
    peer_avg := CASE WHEN v_hospital_patterns.doctor_count > 0
        THEN v_hospital_patterns.total_feedback::NUMERIC / v_hospital_patterns.doctor_count
        ELSE 0 END;
    peer_p25 := peer_avg * 0.5;
    peer_p75 := peer_avg * 1.5;
    is_outlier := (doctor_value < peer_p25);
    outlier_direction := CASE WHEN doctor_value < peer_p25 THEN 'below' ELSE NULL END;
    RETURN NEXT;

    RETURN;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_peer_comparison IS 'Returns peer comparison metrics for a doctor against same-specialty colleagues';

-- =============================================================================
-- 5. compute_all_hospital_patterns - Background job function
-- =============================================================================

CREATE OR REPLACE FUNCTION compute_all_hospital_patterns()
RETURNS TABLE (
    hospital_id UUID,
    specialty TEXT,
    doctor_count INT,
    success BOOLEAN
) AS $$
DECLARE
    r RECORD;
    v_result hospital_specialty_patterns%ROWTYPE;
BEGIN
    -- Iterate through all unique hospital/specialty combinations
    FOR r IN (
        SELECT DISTINCT d.hospital_id, d.specialization
        FROM doctors d
        WHERE d.hospital_id IS NOT NULL
        AND d.specialization IS NOT NULL
    ) LOOP
        BEGIN
            v_result := compute_hospital_specialty_patterns(r.hospital_id, r.specialization);

            hospital_id := r.hospital_id;
            specialty := r.specialization;
            doctor_count := COALESCE(v_result.doctor_count, 0);
            success := (v_result IS NOT NULL);
            RETURN NEXT;

        EXCEPTION WHEN OTHERS THEN
            hospital_id := r.hospital_id;
            specialty := r.specialization;
            doctor_count := 0;
            success := FALSE;
            RETURN NEXT;
        END;
    END LOOP;

    RETURN;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION compute_all_hospital_patterns IS 'Background job to recompute all hospital specialty patterns. Run daily.';

-- =============================================================================
-- 6. Updated at triggers
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'hospital_specialty_patterns_updated_at') THEN
        CREATE TRIGGER hospital_specialty_patterns_updated_at
            BEFORE UPDATE ON hospital_specialty_patterns
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'specialty_benchmarks_updated_at') THEN
        CREATE TRIGGER specialty_benchmarks_updated_at
            BEFORE UPDATE ON specialty_benchmarks
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END
$$;

-- Migration: Add multi-layer orchestrator support
-- Version: 1.0.0
-- Description: Phase 4 of Triage Engine Multi-Layer - Orchestrator Support
--
-- Tables modified:
-- 1. triage_suggestion_log - Add layer_sources column
--
-- Tables created:
-- 1. doctor_layer_preferences - Per-doctor layer configuration
-- 2. triage_conflict_log - Log layer conflicts for debugging

-- =============================================================================
-- 1. Modify triage_suggestion_log to track layer sources
-- =============================================================================

-- Add column to track which layers contributed to each suggestion
ALTER TABLE triage_suggestion_log
ADD COLUMN IF NOT EXISTS layer_sources JSONB DEFAULT '[]';

COMMENT ON COLUMN triage_suggestion_log.layer_sources IS 'Array of layer codes that contributed to this suggestion (e.g., ["base_mvp", "doctor_practice", "rag_guideline:ICMR_STG"])';

-- =============================================================================
-- 2. doctor_layer_preferences - Per-doctor layer configuration
-- =============================================================================

CREATE TABLE IF NOT EXISTS doctor_layer_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,

    -- Layer toggles (override global config)
    enable_doctor_practice_layer BOOLEAN DEFAULT TRUE,
    enable_hospital_intelligence_layer BOOLEAN DEFAULT TRUE,
    enable_rag_guidelines_layer BOOLEAN DEFAULT TRUE,

    -- Layer weights (for conflict resolution scoring)
    weight_base_mvp NUMERIC(3,2) DEFAULT 1.0 CHECK (weight_base_mvp >= 0 AND weight_base_mvp <= 1),
    weight_doctor_practice NUMERIC(3,2) DEFAULT 0.8 CHECK (weight_doctor_practice >= 0 AND weight_doctor_practice <= 1),
    weight_hospital_intelligence NUMERIC(3,2) DEFAULT 0.7 CHECK (weight_hospital_intelligence >= 0 AND weight_hospital_intelligence <= 1),
    weight_rag_guidelines NUMERIC(3,2) DEFAULT 0.9 CHECK (weight_rag_guidelines >= 0 AND weight_rag_guidelines <= 1),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_doctor_layer_prefs UNIQUE(doctor_id)
);

CREATE INDEX IF NOT EXISTS idx_doctor_layer_preferences_doctor
ON doctor_layer_preferences (doctor_id);

COMMENT ON TABLE doctor_layer_preferences IS 'Per-doctor layer enable/disable and weight configuration';
COMMENT ON COLUMN doctor_layer_preferences.weight_rag_guidelines IS 'RAG guidelines get high weight (0.9) as they are evidence-based';

-- =============================================================================
-- 3. triage_conflict_log - Log layer conflicts for debugging/tuning
-- =============================================================================

CREATE TABLE IF NOT EXISTS triage_conflict_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,

    -- Conflict details
    conflict_type TEXT NOT NULL,  -- priority_disagreement, contradiction, duplicate
    layer_1 TEXT NOT NULL,
    layer_1_suggestion TEXT,
    layer_1_priority TEXT,
    layer_2 TEXT NOT NULL,
    layer_2_suggestion TEXT,
    layer_2_priority TEXT,

    -- Resolution
    resolution_strategy TEXT,  -- patient_safety_first, evidence_over_opinion, doctor_preference
    final_suggestion TEXT,
    final_priority TEXT,

    -- Metadata
    resolution_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_triage_conflict_log_extraction
ON triage_conflict_log (extraction_id);

CREATE INDEX IF NOT EXISTS idx_triage_conflict_log_type
ON triage_conflict_log (conflict_type, created_at DESC);

COMMENT ON TABLE triage_conflict_log IS 'Log of conflicts between triage layers for debugging and tuning resolution rules';

-- =============================================================================
-- 4. RPC: Get enabled layers for triage
-- =============================================================================

CREATE OR REPLACE FUNCTION get_enabled_triage_layers(p_doctor_id UUID DEFAULT NULL)
RETURNS TABLE (
    layer_code TEXT,
    layer_name TEXT,
    is_enabled BOOLEAN,
    weight NUMERIC(3,2),
    config JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        tlc.layer_code::TEXT,
        tlc.layer_name::TEXT,
        -- Check global enable first, then doctor preference if exists
        CASE
            WHEN tlc.layer_code = 'base_mvp' THEN TRUE  -- Base layer always enabled
            WHEN dlp.id IS NOT NULL THEN
                CASE tlc.layer_code
                    WHEN 'doctor_practice' THEN COALESCE(dlp.enable_doctor_practice_layer, TRUE)
                    WHEN 'hospital_intelligence' THEN COALESCE(dlp.enable_hospital_intelligence_layer, TRUE)
                    WHEN 'rag_guidelines' THEN COALESCE(dlp.enable_rag_guidelines_layer, TRUE)
                    ELSE tlc.is_enabled
                END
            ELSE tlc.is_enabled
        END as is_enabled,
        -- Get weight from doctor preferences if available, otherwise global config
        CASE
            WHEN dlp.id IS NOT NULL THEN
                CASE tlc.layer_code
                    WHEN 'base_mvp' THEN COALESCE(dlp.weight_base_mvp, tlc.weight)
                    WHEN 'doctor_practice' THEN COALESCE(dlp.weight_doctor_practice, tlc.weight)
                    WHEN 'hospital_intelligence' THEN COALESCE(dlp.weight_hospital_intelligence, tlc.weight)
                    WHEN 'rag_guidelines' THEN COALESCE(dlp.weight_rag_guidelines, tlc.weight)
                    ELSE tlc.weight
                END
            ELSE tlc.weight
        END as weight,
        tlc.config
    FROM triage_layer_config tlc
    LEFT JOIN doctor_layer_preferences dlp ON dlp.doctor_id = p_doctor_id
    ORDER BY tlc.display_order;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_enabled_triage_layers IS 'Returns all triage layers with enable status and weights, respecting doctor preferences';

-- =============================================================================
-- 5. RPC: Update layer config
-- =============================================================================

CREATE OR REPLACE FUNCTION update_triage_layer_config(
    p_layer_code TEXT,
    p_is_enabled BOOLEAN DEFAULT NULL,
    p_weight NUMERIC(3,2) DEFAULT NULL
)
RETURNS triage_layer_config AS $$
DECLARE
    v_result triage_layer_config%ROWTYPE;
BEGIN
    UPDATE triage_layer_config
    SET
        is_enabled = COALESCE(p_is_enabled, is_enabled),
        weight = COALESCE(p_weight, weight),
        updated_at = NOW()
    WHERE layer_code = p_layer_code
    RETURNING * INTO v_result;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION update_triage_layer_config IS 'Update global triage layer configuration';

-- =============================================================================
-- 6. Updated at triggers
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'doctor_layer_preferences_updated_at') THEN
        CREATE TRIGGER doctor_layer_preferences_updated_at
            BEFORE UPDATE ON doctor_layer_preferences
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END
$$;

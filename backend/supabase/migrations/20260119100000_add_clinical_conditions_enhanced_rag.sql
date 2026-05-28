-- Migration: Add enhanced clinical conditions RAG schema
-- Version: 1.0.0
-- Description: Enhanced clinical triage RAG with condition-centric structure,
--              semantic chunking, numeric thresholds, and comorbidity pathways
--
-- Tables created:
-- 1. clinical_conditions - Master condition registry
-- 2. clinical_chunks - Semantic chunks for RAG retrieval
-- 3. clinical_chunk_embeddings - Vector embeddings for chunks
--
-- This replaces the simpler clinical_guidelines approach with a more robust
-- structure supporting narrative guidelines, visual workflows, and step protocols.

-- =============================================================================
-- 1. clinical_conditions - Master condition registry
-- =============================================================================

CREATE TABLE IF NOT EXISTS clinical_conditions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    condition_id TEXT UNIQUE NOT NULL,          -- "cardio_htn_001", "ent_epistaxis_001"
    name TEXT NOT NULL,                          -- "Primary Hypertension"
    aliases TEXT[] DEFAULT '{}',                 -- ["Essential Hypertension", "High BP"]
    icd_codes TEXT[] DEFAULT '{}',               -- ["I10", "I11.9"]

    -- Document metadata
    source_name TEXT NOT NULL,                   -- "Ministry of Health STG"
    specialty TEXT NOT NULL,                     -- "cardiology", "ent", "obstetrics_gynaecology"
    document_type TEXT NOT NULL CHECK (document_type IN ('narrative_guideline', 'visual_workflow', 'step_protocol')),
    version TEXT,                                -- "2024", "October 2019"
    language TEXT DEFAULT 'en',

    -- Classification (for graded conditions like HTN)
    -- Example: {type: "graded", grades: [{grade: "Grade 1", criteria: {sbp_range: [140,159]}, default_urgency: "routine"}]}
    classification JSONB,

    -- Triage metadata (TOP PRIORITY for retrieval)
    -- Contains: urgency_levels, default_urgency, emergency_triggers, red_flags, referral_triggers
    triage_metadata JSONB NOT NULL DEFAULT '{}',

    -- Clinical content (JSONB for flexibility)
    clinical_presentation JSONB,                 -- {symptoms: [...], examination_findings: [...], when_to_suspect}
    differential_diagnosis JSONB,                -- [{condition, distinguishing_feature, causes}]
    investigations JSONB,                        -- {essential: {...}, desirable: {...}, comprehensive: {...}}

    -- Treatment (structured by care level)
    treatment_by_care_level JSONB,               -- {phc_primary: {...}, district_hospital: {...}, tertiary: {...}}

    -- Comorbidity pathways (critical for personalized triage)
    -- [{comorbidity, preferred_drugs, avoid, target_bp, special_notes}]
    comorbidity_pathways JSONB,

    -- Drug formulary
    -- [{drug_class, representative, initial_dose, max_dose, side_effects, contraindications}]
    drug_formulary JSONB,

    -- Step-wise management (for protocols)
    -- {description, steps: [{step, action, duration_before_escalation}]}
    step_wise_management JSONB,

    -- Emergency protocols
    -- {hypertensive_emergency: {...}, stroke_specific: {...}}
    emergency_protocols JSONB,

    -- Follow-up and quality
    follow_up JSONB,                             -- {frequency, annual_review_components, quality_metrics}
    patient_education JSONB,                     -- {key_messages, self_monitoring}

    -- Full original JSON (for reference/debugging)
    full_json JSONB,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,           -- Reviewed by medical expert

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for clinical_conditions
CREATE INDEX IF NOT EXISTS idx_conditions_specialty ON clinical_conditions (specialty) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_conditions_document_type ON clinical_conditions (document_type);
CREATE INDEX IF NOT EXISTS idx_conditions_icd ON clinical_conditions USING GIN (icd_codes);
CREATE INDEX IF NOT EXISTS idx_conditions_aliases ON clinical_conditions USING GIN (aliases);
CREATE INDEX IF NOT EXISTS idx_conditions_name_search ON clinical_conditions USING GIN (to_tsvector('english', name));

COMMENT ON TABLE clinical_conditions IS 'Master registry of clinical conditions with structured treatment guidelines';
COMMENT ON COLUMN clinical_conditions.condition_id IS 'Unique condition identifier (e.g., cardio_htn_001)';
COMMENT ON COLUMN clinical_conditions.document_type IS 'STG format: narrative_guideline, visual_workflow, or step_protocol';
COMMENT ON COLUMN clinical_conditions.triage_metadata IS 'Critical triage info: urgency_levels, emergency_triggers, red_flags, referral_triggers';
COMMENT ON COLUMN clinical_conditions.comorbidity_pathways IS 'Condition-specific management for common comorbidities';

-- =============================================================================
-- 2. clinical_chunks - Semantic chunks for RAG retrieval
-- =============================================================================

CREATE TABLE IF NOT EXISTS clinical_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Link to parent condition
    condition_id UUID NOT NULL REFERENCES clinical_conditions(id) ON DELETE CASCADE,

    -- Chunk identity
    chunk_type TEXT NOT NULL CHECK (chunk_type IN (
        'triage_criteria',       -- Red flags, emergency triggers, urgency thresholds
        'classification',        -- Grades, staging, severity criteria
        'presentation',          -- Symptoms, when to suspect, exam findings
        'differential',          -- DDx with distinguishing features
        'investigation',         -- Labs, imaging by tier
        'treatment_primary',     -- PHC-level management
        'treatment_district',    -- District hospital options
        'treatment_tertiary',    -- Tertiary/referral options
        'treatment_escalation',  -- Step-wise escalation protocol
        'comorbidity_pathway',   -- Per-comorbidity drug preferences
        'drug_formulary',        -- Dosing, contraindications, monitoring
        'emergency_protocol',    -- Urgency/emergency handling
        'follow_up',             -- Monitoring frequency, quality metrics
        'patient_education',     -- Key messages, self-monitoring
        'step_protocol',         -- Ordered steps (epistaxis management)
        'decision_node'          -- Flowchart decision points
    )),
    chunk_index INT DEFAULT 0,                   -- Order within same chunk_type

    -- Content
    content_json JSONB NOT NULL,                 -- Structured content for this chunk
    content_text TEXT NOT NULL,                  -- Flattened text for embedding search

    -- Triage-critical filters (denormalized for fast filtering)
    urgency_default TEXT CHECK (urgency_default IN ('routine', 'urgent', 'emergency')),
    has_emergency_triggers BOOLEAN DEFAULT FALSE,
    has_red_flags BOOLEAN DEFAULT FALSE,
    care_levels TEXT[] DEFAULT '{}',             -- ['phc', 'district', 'tertiary']

    -- Comorbidity context (for pathway chunks)
    comorbidity TEXT,                            -- 'diabetes', 'ckd', 'heart_failure', NULL

    -- Numeric thresholds (for quantitative triage)
    -- Example: {"sbp_min": 180, "dbp_min": 110, "hb_max": 7}
    numeric_thresholds JSONB,

    -- Drug context (for formulary chunks)
    drug_classes TEXT[] DEFAULT '{}',            -- ['CCB', 'ACE_inhibitor', 'thiazide']
    drug_names TEXT[] DEFAULT '{}',              -- ['amlodipine', 'enalapril']
    contraindications TEXT[] DEFAULT '{}',       -- ['pregnancy', 'bilateral_renal_artery_stenosis']

    -- Source tracking
    source_section TEXT,                         -- Original section name in document

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for clinical_chunks
CREATE INDEX IF NOT EXISTS idx_chunks_condition ON clinical_chunks (condition_id);
CREATE INDEX IF NOT EXISTS idx_chunks_type ON clinical_chunks (chunk_type);
CREATE INDEX IF NOT EXISTS idx_chunks_urgency ON clinical_chunks (urgency_default) WHERE urgency_default IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chunks_comorbidity ON clinical_chunks (comorbidity) WHERE comorbidity IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chunks_care_levels ON clinical_chunks USING GIN (care_levels);
CREATE INDEX IF NOT EXISTS idx_chunks_drug_classes ON clinical_chunks USING GIN (drug_classes);
CREATE INDEX IF NOT EXISTS idx_chunks_drug_names ON clinical_chunks USING GIN (drug_names);
CREATE INDEX IF NOT EXISTS idx_chunks_contraindications ON clinical_chunks USING GIN (contraindications);
CREATE INDEX IF NOT EXISTS idx_chunks_red_flags ON clinical_chunks (has_red_flags) WHERE has_red_flags = TRUE;
CREATE INDEX IF NOT EXISTS idx_chunks_emergency ON clinical_chunks (has_emergency_triggers) WHERE has_emergency_triggers = TRUE;

-- Full-text search fallback
CREATE INDEX IF NOT EXISTS idx_chunks_fts ON clinical_chunks USING GIN (to_tsvector('english', content_text));

COMMENT ON TABLE clinical_chunks IS 'Semantic chunks of clinical conditions for RAG retrieval';
COMMENT ON COLUMN clinical_chunks.chunk_type IS 'Semantic type: triage_criteria, treatment_primary, comorbidity_pathway, etc.';
COMMENT ON COLUMN clinical_chunks.numeric_thresholds IS 'Quantitative thresholds for direct matching (BP, Hb, etc.)';
COMMENT ON COLUMN clinical_chunks.care_levels IS 'Healthcare facility levels where this applies: phc, district, tertiary';

-- =============================================================================
-- 3. clinical_chunk_embeddings - Vector embeddings for chunks
-- =============================================================================

CREATE TABLE IF NOT EXISTS clinical_chunk_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL REFERENCES clinical_chunks(id) ON DELETE CASCADE,

    -- Vector (1536 dims for Cohere compatibility)
    embedding vector(1536),

    -- Model info
    embedding_model TEXT DEFAULT 'cohere-embed-english-v3.0',
    embedding_model_id UUID REFERENCES embedding_models(id),

    -- Change detection
    content_hash TEXT,                           -- SHA256 of content_text

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_chunk_embedding UNIQUE(chunk_id, embedding_model)
);

-- HNSW index for fast semantic search
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_hnsw
ON clinical_chunk_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Model lookup
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_model ON clinical_chunk_embeddings (embedding_model);

COMMENT ON TABLE clinical_chunk_embeddings IS 'Vector embeddings for clinical chunks (semantic search)';

-- =============================================================================
-- 4. RPC: Hybrid search for clinical chunks
-- =============================================================================

CREATE OR REPLACE FUNCTION search_clinical_chunks_hybrid(
    query_embedding vector(1536),
    query_text TEXT DEFAULT NULL,

    -- Filters
    filter_specialty TEXT DEFAULT NULL,
    filter_chunk_types TEXT[] DEFAULT NULL,
    filter_urgency TEXT DEFAULT NULL,
    filter_comorbidity TEXT DEFAULT NULL,
    filter_care_level TEXT DEFAULT NULL,
    filter_drug_class TEXT DEFAULT NULL,

    -- Numeric context (for threshold matching)
    patient_sbp INT DEFAULT NULL,
    patient_dbp INT DEFAULT NULL,
    patient_hb NUMERIC DEFAULT NULL,

    -- Limits
    match_count INT DEFAULT 10,
    min_similarity FLOAT DEFAULT 0.4
)
RETURNS TABLE (
    chunk_id UUID,
    condition_id UUID,
    condition_name TEXT,
    condition_code TEXT,
    specialty TEXT,
    chunk_type TEXT,
    content_json JSONB,
    content_text TEXT,
    urgency_default TEXT,
    care_levels TEXT[],
    comorbidity TEXT,
    numeric_thresholds JSONB,
    similarity FLOAT,
    threshold_match BOOLEAN,
    match_source TEXT
) AS $$
BEGIN
    RETURN QUERY
    WITH semantic_matches AS (
        SELECT
            ch.id AS chunk_id,
            cc.id AS condition_id,
            cc.name AS condition_name,
            cc.condition_id AS condition_code,
            cc.specialty,
            ch.chunk_type,
            ch.content_json,
            ch.content_text,
            ch.urgency_default,
            ch.care_levels,
            ch.comorbidity,
            ch.numeric_thresholds,
            1 - (ce.embedding <=> query_embedding) AS similarity,
            -- Check numeric threshold match
            CASE
                WHEN patient_sbp IS NOT NULL AND ch.numeric_thresholds ? 'sbp_min'
                     AND patient_sbp >= (ch.numeric_thresholds->>'sbp_min')::INT THEN TRUE
                WHEN patient_dbp IS NOT NULL AND ch.numeric_thresholds ? 'dbp_min'
                     AND patient_dbp >= (ch.numeric_thresholds->>'dbp_min')::INT THEN TRUE
                WHEN patient_hb IS NOT NULL AND ch.numeric_thresholds ? 'hb_max'
                     AND patient_hb <= (ch.numeric_thresholds->>'hb_max')::NUMERIC THEN TRUE
                ELSE FALSE
            END AS threshold_match,
            'semantic'::TEXT AS match_source
        FROM clinical_chunks ch
        JOIN clinical_conditions cc ON ch.condition_id = cc.id
        JOIN clinical_chunk_embeddings ce ON ch.id = ce.chunk_id
        WHERE cc.is_active = TRUE
        -- Apply filters
        AND (filter_specialty IS NULL OR cc.specialty = filter_specialty)
        AND (filter_chunk_types IS NULL OR ch.chunk_type = ANY(filter_chunk_types))
        AND (filter_urgency IS NULL OR ch.urgency_default = filter_urgency)
        AND (filter_comorbidity IS NULL OR ch.comorbidity = filter_comorbidity)
        AND (filter_care_level IS NULL OR filter_care_level = ANY(ch.care_levels))
        AND (filter_drug_class IS NULL OR filter_drug_class = ANY(ch.drug_classes))
        -- Similarity threshold
        AND (1 - (ce.embedding <=> query_embedding)) >= min_similarity
        ORDER BY ce.embedding <=> query_embedding
        LIMIT match_count
    ),
    -- Add threshold-triggered results (even if semantic similarity is low)
    threshold_matches AS (
        SELECT
            ch.id AS chunk_id,
            cc.id AS condition_id,
            cc.name AS condition_name,
            cc.condition_id AS condition_code,
            cc.specialty,
            ch.chunk_type,
            ch.content_json,
            ch.content_text,
            ch.urgency_default,
            ch.care_levels,
            ch.comorbidity,
            ch.numeric_thresholds,
            0.3::FLOAT AS similarity,
            TRUE AS threshold_match,
            'threshold'::TEXT AS match_source
        FROM clinical_chunks ch
        JOIN clinical_conditions cc ON ch.condition_id = cc.id
        WHERE cc.is_active = TRUE
        AND ch.numeric_thresholds IS NOT NULL
        AND (filter_specialty IS NULL OR cc.specialty = filter_specialty)
        AND (
            (patient_sbp IS NOT NULL AND ch.numeric_thresholds ? 'sbp_min'
             AND patient_sbp >= (ch.numeric_thresholds->>'sbp_min')::INT)
            OR
            (patient_dbp IS NOT NULL AND ch.numeric_thresholds ? 'dbp_min'
             AND patient_dbp >= (ch.numeric_thresholds->>'dbp_min')::INT)
            OR
            (patient_hb IS NOT NULL AND ch.numeric_thresholds ? 'hb_max'
             AND patient_hb <= (ch.numeric_thresholds->>'hb_max')::NUMERIC)
        )
        AND ch.id NOT IN (SELECT sm.chunk_id FROM semantic_matches sm)
        LIMIT 5
    )
    SELECT * FROM semantic_matches
    UNION ALL
    SELECT * FROM threshold_matches;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION search_clinical_chunks_hybrid IS 'Hybrid search combining semantic similarity with numeric threshold matching';

-- =============================================================================
-- 5. RPC: Get chunks by condition
-- =============================================================================

CREATE OR REPLACE FUNCTION get_condition_chunks(
    p_condition_id UUID DEFAULT NULL,
    p_condition_code TEXT DEFAULT NULL,
    p_chunk_types TEXT[] DEFAULT NULL
)
RETURNS TABLE (
    chunk_id UUID,
    chunk_type TEXT,
    chunk_index INT,
    content_json JSONB,
    content_text TEXT,
    urgency_default TEXT,
    care_levels TEXT[],
    comorbidity TEXT,
    numeric_thresholds JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ch.id,
        ch.chunk_type,
        ch.chunk_index,
        ch.content_json,
        ch.content_text,
        ch.urgency_default,
        ch.care_levels,
        ch.comorbidity,
        ch.numeric_thresholds
    FROM clinical_chunks ch
    JOIN clinical_conditions cc ON ch.condition_id = cc.id
    WHERE cc.is_active = TRUE
    AND (p_condition_id IS NULL OR cc.id = p_condition_id)
    AND (p_condition_code IS NULL OR cc.condition_id = p_condition_code)
    AND (p_chunk_types IS NULL OR ch.chunk_type = ANY(p_chunk_types))
    ORDER BY ch.chunk_type, ch.chunk_index;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_condition_chunks IS 'Get all chunks for a specific condition, optionally filtered by chunk type';

-- =============================================================================
-- 6. RPC: Get red flags by specialty
-- =============================================================================

CREATE OR REPLACE FUNCTION get_red_flags_by_specialty(
    p_specialty TEXT,
    p_include_emergency_triggers BOOLEAN DEFAULT TRUE
)
RETURNS TABLE (
    condition_name TEXT,
    condition_code TEXT,
    chunk_type TEXT,
    content_json JSONB,
    urgency_default TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cc.name,
        cc.condition_id,
        ch.chunk_type,
        ch.content_json,
        ch.urgency_default
    FROM clinical_chunks ch
    JOIN clinical_conditions cc ON ch.condition_id = cc.id
    WHERE cc.is_active = TRUE
    AND cc.specialty = p_specialty
    AND (
        ch.has_red_flags = TRUE
        OR (p_include_emergency_triggers AND ch.has_emergency_triggers = TRUE)
    )
    ORDER BY cc.name, ch.chunk_type;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_red_flags_by_specialty IS 'Get all red flags and emergency triggers for a specialty';

-- =============================================================================
-- 7. RPC: Get comorbidity pathways
-- =============================================================================

CREATE OR REPLACE FUNCTION get_comorbidity_pathway(
    p_condition_code TEXT,
    p_comorbidity TEXT
)
RETURNS TABLE (
    condition_name TEXT,
    comorbidity TEXT,
    content_json JSONB,
    content_text TEXT,
    drug_classes TEXT[],
    contraindications TEXT[]
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cc.name,
        ch.comorbidity,
        ch.content_json,
        ch.content_text,
        ch.drug_classes,
        ch.contraindications
    FROM clinical_chunks ch
    JOIN clinical_conditions cc ON ch.condition_id = cc.id
    WHERE cc.is_active = TRUE
    AND cc.condition_id = p_condition_code
    AND ch.chunk_type = 'comorbidity_pathway'
    AND ch.comorbidity = p_comorbidity;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_comorbidity_pathway IS 'Get specific comorbidity pathway for a condition (e.g., HTN + diabetes)';

-- =============================================================================
-- 8. RPC: Search by ICD code
-- =============================================================================

CREATE OR REPLACE FUNCTION search_by_icd_code(
    p_icd_code TEXT
)
RETURNS TABLE (
    condition_id UUID,
    condition_code TEXT,
    condition_name TEXT,
    specialty TEXT,
    icd_codes TEXT[],
    triage_metadata JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cc.id,
        cc.condition_id,
        cc.name,
        cc.specialty,
        cc.icd_codes,
        cc.triage_metadata
    FROM clinical_conditions cc
    WHERE cc.is_active = TRUE
    AND p_icd_code = ANY(cc.icd_codes);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION search_by_icd_code IS 'Find conditions by ICD-10 code';

-- =============================================================================
-- 9. Updated at triggers
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'clinical_conditions_updated_at') THEN
        CREATE TRIGGER clinical_conditions_updated_at
            BEFORE UPDATE ON clinical_conditions
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'clinical_chunk_embeddings_updated_at') THEN
        CREATE TRIGGER clinical_chunk_embeddings_updated_at
            BEFORE UPDATE ON clinical_chunk_embeddings
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END
$$;

-- =============================================================================
-- 10. Ingestion tracking table
-- =============================================================================

CREATE TABLE IF NOT EXISTS clinical_condition_ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Job info
    file_name TEXT NOT NULL,
    file_path TEXT,
    source_name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    document_type TEXT NOT NULL,

    -- Status
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'validating', 'processing', 'embedding', 'completed', 'failed')),
    error_message TEXT,
    validation_errors JSONB,

    -- Progress
    total_conditions INT DEFAULT 0,
    processed_conditions INT DEFAULT 0,
    total_chunks INT DEFAULT 0,
    embedded_chunks INT DEFAULT 0,

    -- Timestamps
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_condition_ingestion_status
ON clinical_condition_ingestion_jobs (status, created_at DESC);

COMMENT ON TABLE clinical_condition_ingestion_jobs IS 'Track clinical condition JSON ingestion jobs';

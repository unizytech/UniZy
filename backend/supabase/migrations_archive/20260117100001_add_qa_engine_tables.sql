-- Migration: Add Q&A Engine tables for RAG-based medical query system
-- Version: 1.0.0
-- Description: Creates tables for embedding storage, query history, and patient sharing
--
-- Tables created:
-- 1. embedding_models - Available embedding model configurations
-- 2. extraction_embeddings - Document-level vectors (full extraction)
-- 3. segment_embeddings - Segment-level vectors (individual segments)
-- 4. qa_engine_settings - Per-hospital model configuration
-- 5. qa_query_history - Query audit trail
-- 6. patient_sharing - Doctor-to-doctor patient sharing

-- =============================================================================
-- 1. embedding_models - Available embedding model configurations
-- =============================================================================

CREATE TABLE IF NOT EXISTS embedding_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_code VARCHAR(50) NOT NULL UNIQUE,
    model_name VARCHAR(100) NOT NULL,
    provider VARCHAR(50) NOT NULL,  -- cohere, openai, gemini
    dimensions INTEGER NOT NULL,
    description TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    -- Pricing info (per 1M tokens)
    price_per_million_tokens DECIMAL(10, 6),
    -- Configuration
    max_tokens INTEGER DEFAULT 8192,
    supports_batching BOOLEAN DEFAULT TRUE,
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Only one default model at a time
CREATE UNIQUE INDEX IF NOT EXISTS idx_embedding_models_default
ON embedding_models (is_default)
WHERE is_default = TRUE;

-- Index for active models lookup
CREATE INDEX IF NOT EXISTS idx_embedding_models_active
ON embedding_models (is_active, provider);

COMMENT ON TABLE embedding_models IS 'Available embedding model configurations for Q&A Engine vector generation';
COMMENT ON COLUMN embedding_models.model_code IS 'Unique identifier used in API calls (e.g., cohere_v4, openai_large)';
COMMENT ON COLUMN embedding_models.dimensions IS 'Vector dimensions for this model (768, 1536, 3072)';

-- =============================================================================
-- 2. extraction_embeddings - Document-level vectors
-- =============================================================================

CREATE TABLE IF NOT EXISTS extraction_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    model_id UUID NOT NULL REFERENCES embedding_models(id),
    -- The embedding vector (using pgvector type)
    -- We use 3072 to support all model sizes (768, 1536, 3072)
    embedding vector(3072),
    -- What was embedded
    embedded_content TEXT NOT NULL,  -- Transcript + all segment values
    content_hash VARCHAR(64),  -- SHA256 hash for change detection
    -- Denormalized for efficient queries
    hospital_id UUID REFERENCES hospitals(id),
    doctor_id UUID REFERENCES doctors(id),
    patient_id UUID REFERENCES patients(id),
    consultation_type_id UUID REFERENCES consultation_types(id),
    -- Metadata
    token_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Each extraction has one embedding per model
CREATE UNIQUE INDEX IF NOT EXISTS idx_extraction_embeddings_unique
ON extraction_embeddings (extraction_id, model_id);

-- Efficient vector similarity search with filtering
CREATE INDEX IF NOT EXISTS idx_extraction_embeddings_hospital
ON extraction_embeddings (hospital_id, model_id);

CREATE INDEX IF NOT EXISTS idx_extraction_embeddings_doctor
ON extraction_embeddings (doctor_id, model_id);

-- NOTE: Vector indexes (HNSW, IVFFlat) limited to 2000 dimensions in pgvector
-- Since we support models up to 3072 dims (OpenAI large), skip index creation here
-- For production with specific model, add index manually:
--   For dims <= 2000: CREATE INDEX USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)
--   For exact search (any dims): Use <=> operator without index (slower but accurate)
-- Exact search is acceptable for small-medium datasets (<100k rows)

COMMENT ON TABLE extraction_embeddings IS 'Document-level embeddings for full medical extractions (transcript + all segments)';
COMMENT ON COLUMN extraction_embeddings.embedding IS 'Vector embedding using pgvector. Size varies by model (768-3072 dims)';
COMMENT ON COLUMN extraction_embeddings.content_hash IS 'SHA256 hash of embedded_content for detecting when re-embedding is needed';

-- =============================================================================
-- 3. segment_embeddings - Segment-level vectors
-- =============================================================================

CREATE TABLE IF NOT EXISTS segment_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    segment_id UUID REFERENCES extraction_segments(id) ON DELETE CASCADE,
    model_id UUID NOT NULL REFERENCES embedding_models(id),
    -- Segment identification
    segment_code VARCHAR(100) NOT NULL,
    segment_name VARCHAR(200),
    -- The embedding vector
    embedding vector(3072),
    -- What was embedded
    embedded_content TEXT NOT NULL,
    content_hash VARCHAR(64),
    -- Denormalized for efficient queries
    hospital_id UUID REFERENCES hospitals(id),
    doctor_id UUID REFERENCES doctors(id),
    patient_id UUID REFERENCES patients(id),
    -- Metadata
    token_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Each segment has one embedding per model
CREATE UNIQUE INDEX IF NOT EXISTS idx_segment_embeddings_unique
ON segment_embeddings (extraction_id, segment_code, model_id);

-- Efficient filtering by segment code
CREATE INDEX IF NOT EXISTS idx_segment_embeddings_segment_code
ON segment_embeddings (segment_code, hospital_id, model_id);

-- NOTE: Vector indexes skipped - see extraction_embeddings comment for details
-- Exact search used for segment-level queries (typically smaller result sets)

COMMENT ON TABLE segment_embeddings IS 'Segment-level embeddings for individual extraction segments (e.g., CHIEF_COMPLAINT, DIAGNOSIS)';
COMMENT ON COLUMN segment_embeddings.segment_code IS 'Segment code for filtering (e.g., CHIEF_COMPLAINT, PRESCRIPTION)';

-- =============================================================================
-- 4. qa_engine_settings - Per-hospital model configuration
-- =============================================================================

CREATE TABLE IF NOT EXISTS qa_engine_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
    -- Active embedding model
    embedding_model_id UUID NOT NULL REFERENCES embedding_models(id),
    -- Feature flags
    is_enabled BOOLEAN DEFAULT TRUE,
    allow_analytics_queries BOOLEAN DEFAULT TRUE,  -- SQL analytics
    allow_cross_doctor_search BOOLEAN DEFAULT FALSE,  -- Search across doctors
    -- Limits
    max_results_per_query INTEGER DEFAULT 20,
    max_queries_per_day INTEGER DEFAULT 1000,
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- One setting per hospital
CREATE UNIQUE INDEX IF NOT EXISTS idx_qa_engine_settings_hospital
ON qa_engine_settings (hospital_id);

COMMENT ON TABLE qa_engine_settings IS 'Per-hospital Q&A Engine configuration including embedding model selection';
COMMENT ON COLUMN qa_engine_settings.allow_cross_doctor_search IS 'When true, doctors can search across all doctors in the hospital';

-- =============================================================================
-- 5. qa_query_history - Query audit trail
-- =============================================================================

CREATE TABLE IF NOT EXISTS qa_query_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Who queried
    hospital_id UUID NOT NULL REFERENCES hospitals(id),
    doctor_id UUID REFERENCES doctors(id),
    user_role VARCHAR(50),  -- doctor, admin, nurse
    -- Query details
    query_text TEXT NOT NULL,
    query_intent VARCHAR(50),  -- semantic, hybrid, sql
    search_level VARCHAR(50),  -- document, segment
    -- Results
    result_count INTEGER DEFAULT 0,
    response_format VARCHAR(50),  -- narrative, table, chart
    -- Performance
    embedding_time_ms INTEGER,
    search_time_ms INTEGER,
    synthesis_time_ms INTEGER,
    total_time_ms INTEGER,
    -- Model info
    embedding_model_id UUID REFERENCES embedding_models(id),
    synthesis_model VARCHAR(100),
    -- LLM usage tracking
    total_tokens INTEGER,
    total_cost_usd DECIMAL(10, 6),
    -- Error tracking
    error_message TEXT,
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for analytics and history lookup
CREATE INDEX IF NOT EXISTS idx_qa_query_history_hospital
ON qa_query_history (hospital_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_qa_query_history_doctor
ON qa_query_history (doctor_id, created_at DESC);

-- Index for query pattern analysis
CREATE INDEX IF NOT EXISTS idx_qa_query_history_intent
ON qa_query_history (query_intent, created_at DESC);

COMMENT ON TABLE qa_query_history IS 'Audit trail for Q&A Engine queries with performance metrics and cost tracking';

-- =============================================================================
-- 6. patient_sharing - Doctor-to-doctor patient sharing
-- =============================================================================

CREATE TABLE IF NOT EXISTS patient_sharing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Source doctor (who is sharing)
    source_doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    -- Target doctor (who receives access)
    target_doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    -- Patient being shared
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    -- Sharing permissions
    access_level VARCHAR(20) DEFAULT 'read',  -- read, read_write
    -- Time bounds
    shared_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,  -- NULL = no expiration
    revoked_at TIMESTAMPTZ,  -- Set when sharing is revoked
    -- Reason for sharing
    reason TEXT,
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ensure unique active sharing (not revoked)
CREATE UNIQUE INDEX IF NOT EXISTS idx_patient_sharing_unique_active
ON patient_sharing (source_doctor_id, target_doctor_id, patient_id)
WHERE revoked_at IS NULL;

-- Index for target doctor lookups (who has access to what)
CREATE INDEX IF NOT EXISTS idx_patient_sharing_target
ON patient_sharing (target_doctor_id, revoked_at)
WHERE revoked_at IS NULL;

-- Index for source doctor lookups (what have I shared)
CREATE INDEX IF NOT EXISTS idx_patient_sharing_source
ON patient_sharing (source_doctor_id, revoked_at)
WHERE revoked_at IS NULL;

COMMENT ON TABLE patient_sharing IS 'Doctor-to-doctor patient sharing for cross-doctor Q&A Engine access';
COMMENT ON COLUMN patient_sharing.access_level IS 'Permission level: read (view only) or read_write (can add notes)';

-- =============================================================================
-- 7. Update triggers for updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add triggers if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'embedding_models_updated_at') THEN
        CREATE TRIGGER embedding_models_updated_at
            BEFORE UPDATE ON embedding_models
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'extraction_embeddings_updated_at') THEN
        CREATE TRIGGER extraction_embeddings_updated_at
            BEFORE UPDATE ON extraction_embeddings
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'segment_embeddings_updated_at') THEN
        CREATE TRIGGER segment_embeddings_updated_at
            BEFORE UPDATE ON segment_embeddings
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'qa_engine_settings_updated_at') THEN
        CREATE TRIGGER qa_engine_settings_updated_at
            BEFORE UPDATE ON qa_engine_settings
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'patient_sharing_updated_at') THEN
        CREATE TRIGGER patient_sharing_updated_at
            BEFORE UPDATE ON patient_sharing
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END
$$;

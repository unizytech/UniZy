-- Migration: Add clinical guidelines RAG tables
-- Version: 1.0.0
-- Description: Phase 3 of Triage Engine Multi-Layer - RAG Guidelines Layer
--
-- Tables created:
-- 1. clinical_guidelines - Clinical guidelines library
-- 2. clinical_guideline_embeddings - Vector embeddings for guidelines
--
-- Functions created:
-- 1. match_clinical_guidelines - Semantic search for relevant guidelines

-- =============================================================================
-- 1. clinical_guidelines - Clinical guidelines library
-- =============================================================================

CREATE TABLE IF NOT EXISTS clinical_guidelines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source information
    source_name TEXT NOT NULL,            -- "ICMR STG", "IAP Guidelines", "NNF Guidelines"
    source_organization TEXT,             -- "ICMR", "IAP", "NNF", "FOGSI", "IAPSM"
    source_url TEXT,                      -- Link to original document
    document_title TEXT NOT NULL,

    -- Classification
    specialty TEXT NOT NULL,              -- general_medicine, pediatrics, obstetrics, etc.
    topics TEXT[] DEFAULT '{}',           -- ["fever", "dengue", "thrombocytopenia"]
    presentations TEXT[] DEFAULT '{}',    -- ["fever", "bleeding", "altered_sensorium"]
    icd_codes TEXT[] DEFAULT '{}',        -- Related ICD-10 codes

    -- Content
    full_text TEXT,                       -- Complete guideline text (for reference)
    chunk_text TEXT NOT NULL,             -- Chunked text for embedding
    chunk_index INT DEFAULT 0,            -- Chunk sequence number within document

    -- Metadata
    publication_year INT,
    version TEXT,                         -- "2023 Revision", "v2.1"
    evidence_level TEXT,                  -- "Level A", "Level B", "Expert Consensus"
    region TEXT DEFAULT 'India',          -- Geographic relevance

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,    -- Has been reviewed by medical expert

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for specialty-based searches
CREATE INDEX IF NOT EXISTS idx_clinical_guidelines_specialty
ON clinical_guidelines (specialty) WHERE is_active = TRUE;

-- Index for topic searches (GIN for array)
CREATE INDEX IF NOT EXISTS idx_clinical_guidelines_topics
ON clinical_guidelines USING GIN (topics) WHERE is_active = TRUE;

-- Index for presentation searches
CREATE INDEX IF NOT EXISTS idx_clinical_guidelines_presentations
ON clinical_guidelines USING GIN (presentations) WHERE is_active = TRUE;

-- Index for source lookups
CREATE INDEX IF NOT EXISTS idx_clinical_guidelines_source
ON clinical_guidelines (source_name, source_organization);

-- Full-text search index
CREATE INDEX IF NOT EXISTS idx_clinical_guidelines_fts
ON clinical_guidelines USING GIN (to_tsvector('english', chunk_text));

COMMENT ON TABLE clinical_guidelines IS 'Clinical guidelines library for RAG-based triage recommendations';
COMMENT ON COLUMN clinical_guidelines.chunk_text IS 'Chunked text (800-1000 tokens) optimized for embedding';
COMMENT ON COLUMN clinical_guidelines.topics IS 'Array of topic keywords for filtering (fever, infection, etc.)';
COMMENT ON COLUMN clinical_guidelines.evidence_level IS 'Evidence quality: Level A (high), Level B (moderate), Expert Consensus';

-- =============================================================================
-- 2. clinical_guideline_embeddings - Vector embeddings for guidelines
-- =============================================================================

CREATE TABLE IF NOT EXISTS clinical_guideline_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guideline_id UUID NOT NULL REFERENCES clinical_guidelines(id) ON DELETE CASCADE,

    -- Embedding vector (1536 dims for compatibility with existing infrastructure)
    embedding vector(1536),

    -- Model info
    embedding_model TEXT DEFAULT 'cohere-embed-english-v3.0',
    embedding_model_id UUID REFERENCES embedding_models(id),

    -- Change detection
    content_hash TEXT,  -- SHA256 of chunk_text for detecting stale embeddings

    -- Metadata
    token_count INT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- One embedding per guideline per model
    CONSTRAINT unique_guideline_embedding UNIQUE(guideline_id, embedding_model)
);

-- HNSW index for fast similarity search
CREATE INDEX IF NOT EXISTS idx_guideline_embeddings_hnsw
ON clinical_guideline_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Index for model lookups
CREATE INDEX IF NOT EXISTS idx_guideline_embeddings_model
ON clinical_guideline_embeddings (embedding_model);

COMMENT ON TABLE clinical_guideline_embeddings IS 'Vector embeddings for clinical guidelines RAG search';
COMMENT ON COLUMN clinical_guideline_embeddings.embedding IS '1536-dim vector for semantic similarity search (cosine)';

-- =============================================================================
-- 3. match_clinical_guidelines - Semantic search RPC
-- =============================================================================

CREATE OR REPLACE FUNCTION match_clinical_guidelines(
    query_embedding vector(1536),
    match_specialty TEXT DEFAULT NULL,
    match_topics TEXT[] DEFAULT NULL,
    match_count INT DEFAULT 5,
    similarity_threshold FLOAT DEFAULT 0.5
)
RETURNS TABLE (
    id UUID,
    source_name TEXT,
    source_organization TEXT,
    document_title TEXT,
    chunk_text TEXT,
    topics TEXT[],
    presentations TEXT[],
    evidence_level TEXT,
    publication_year INT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        g.id,
        g.source_name,
        g.source_organization,
        g.document_title,
        g.chunk_text,
        g.topics,
        g.presentations,
        g.evidence_level,
        g.publication_year,
        1 - (ge.embedding <=> query_embedding) as similarity
    FROM clinical_guidelines g
    JOIN clinical_guideline_embeddings ge ON g.id = ge.guideline_id
    WHERE g.is_active = TRUE
    -- Optional specialty filter
    AND (match_specialty IS NULL OR g.specialty = match_specialty)
    -- Optional topics filter (match any topic)
    AND (match_topics IS NULL OR g.topics && match_topics)
    -- Similarity threshold
    AND (1 - (ge.embedding <=> query_embedding)) >= similarity_threshold
    ORDER BY ge.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION match_clinical_guidelines IS 'Semantic search for clinical guidelines using cosine similarity';

-- =============================================================================
-- 4. search_guidelines_by_keywords - Keyword-based search (backup)
-- =============================================================================

CREATE OR REPLACE FUNCTION search_guidelines_by_keywords(
    search_query TEXT,
    match_specialty TEXT DEFAULT NULL,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    source_name TEXT,
    document_title TEXT,
    chunk_text TEXT,
    topics TEXT[],
    evidence_level TEXT,
    rank REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        g.id,
        g.source_name,
        g.document_title,
        g.chunk_text,
        g.topics,
        g.evidence_level,
        ts_rank(to_tsvector('english', g.chunk_text), plainto_tsquery('english', search_query)) as rank
    FROM clinical_guidelines g
    WHERE g.is_active = TRUE
    AND (match_specialty IS NULL OR g.specialty = match_specialty)
    AND to_tsvector('english', g.chunk_text) @@ plainto_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION search_guidelines_by_keywords IS 'Full-text keyword search for guidelines (fallback when embeddings unavailable)';

-- =============================================================================
-- 5. guideline_ingestion_status - Track ingestion progress
-- =============================================================================

CREATE TABLE IF NOT EXISTS guideline_ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Job info
    file_name TEXT NOT NULL,
    file_path TEXT,
    source_name TEXT NOT NULL,
    source_organization TEXT,
    specialty TEXT NOT NULL,

    -- Status
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    error_message TEXT,

    -- Progress
    total_chunks INT DEFAULT 0,
    processed_chunks INT DEFAULT 0,
    embedded_chunks INT DEFAULT 0,

    -- Timestamps
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_guideline_ingestion_status
ON guideline_ingestion_jobs (status, created_at DESC);

COMMENT ON TABLE guideline_ingestion_jobs IS 'Track clinical guideline PDF ingestion jobs';

-- =============================================================================
-- 6. Seed example guideline sources (metadata only - no actual content)
-- =============================================================================

-- This is just metadata about available guideline sources
-- Actual ingestion will be done via the GuidelineIngestionService
INSERT INTO clinical_guidelines (
    source_name,
    source_organization,
    document_title,
    specialty,
    topics,
    presentations,
    chunk_text,
    chunk_index,
    publication_year,
    evidence_level,
    is_active
) VALUES
    -- Placeholder entries showing available guideline sources
    -- These will be replaced with actual chunked content after ingestion
    (
        'ICMR STG',
        'ICMR',
        'Standard Treatment Guidelines - General Medicine',
        'general_medicine',
        ARRAY['fever', 'infection', 'hypertension', 'diabetes'],
        ARRAY['fever', 'cough', 'chest_pain', 'breathlessness'],
        'This is a placeholder entry for ICMR Standard Treatment Guidelines. Actual content will be ingested via the GuidelineIngestionService.',
        0,
        2017,
        'Level A',
        FALSE  -- Inactive until actual content is ingested
    ),
    (
        'IAP Guidelines',
        'Indian Academy of Pediatrics',
        'IAP Textbook of Pediatrics',
        'pediatrics',
        ARRAY['fever', 'vaccination', 'growth', 'nutrition'],
        ARRAY['fever', 'diarrhea', 'respiratory_distress'],
        'This is a placeholder entry for IAP Guidelines. Actual content will be ingested via the GuidelineIngestionService.',
        0,
        2022,
        'Level B',
        FALSE
    ),
    (
        'NNF Guidelines',
        'National Neonatology Forum',
        'Evidence-Based Clinical Practice Guidelines',
        'neonatology',
        ARRAY['sepsis', 'jaundice', 'respiratory_distress', 'feeding'],
        ARRAY['neonatal_sepsis', 'jaundice', 'respiratory_distress'],
        'This is a placeholder entry for NNF Guidelines. Actual content will be ingested via the GuidelineIngestionService.',
        0,
        2021,
        'Level A',
        FALSE
    )
ON CONFLICT DO NOTHING;

-- =============================================================================
-- 7. Updated at triggers
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'clinical_guidelines_updated_at') THEN
        CREATE TRIGGER clinical_guidelines_updated_at
            BEFORE UPDATE ON clinical_guidelines
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'clinical_guideline_embeddings_updated_at') THEN
        CREATE TRIGGER clinical_guideline_embeddings_updated_at
            BEFORE UPDATE ON clinical_guideline_embeddings
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END
$$;

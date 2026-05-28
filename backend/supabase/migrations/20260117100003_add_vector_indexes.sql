-- Migration: Add vector indexes for Q&A Engine
-- Version: 1.0.1
-- Description: Reduce vector dimensions to 1536 and add HNSW indexes for fast similarity search
--
-- Changes:
-- 1. Alter extraction_embeddings.embedding from vector(3072) to vector(1536)
-- 2. Alter segment_embeddings.embedding from vector(3072) to vector(1536)
-- 3. Add HNSW indexes for fast approximate nearest neighbor search
-- 4. Mark openai_large model as inactive (3072 dims exceeds limit)

-- =============================================================================
-- 1. Mark openai_large as inactive (dimensions exceed 2000 limit)
-- =============================================================================

UPDATE embedding_models
SET is_active = FALSE,
    description = 'Disabled: 3072 dimensions exceeds pgvector HNSW index limit of 2000'
WHERE model_code = 'openai_large';

-- =============================================================================
-- 2. Alter extraction_embeddings vector column
-- =============================================================================

-- Drop any existing data (embeddings need to be regenerated anyway)
TRUNCATE TABLE extraction_embeddings CASCADE;

-- Alter column to 1536 dimensions
ALTER TABLE extraction_embeddings
ALTER COLUMN embedding TYPE vector(1536);

-- =============================================================================
-- 3. Alter segment_embeddings vector column
-- =============================================================================

-- Drop any existing data
TRUNCATE TABLE segment_embeddings CASCADE;

-- Alter column to 1536 dimensions
ALTER TABLE segment_embeddings
ALTER COLUMN embedding TYPE vector(1536);

-- =============================================================================
-- 4. Add HNSW indexes for fast approximate nearest neighbor search
-- =============================================================================

-- HNSW index on extraction_embeddings
-- m = 16: connections per node (higher = more accurate, more memory)
-- ef_construction = 64: build-time search depth (higher = better quality index)
CREATE INDEX IF NOT EXISTS idx_extraction_embeddings_vector_hnsw
ON extraction_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- HNSW index on segment_embeddings
CREATE INDEX IF NOT EXISTS idx_segment_embeddings_vector_hnsw
ON segment_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- =============================================================================
-- 5. Add comments documenting the constraints
-- =============================================================================

COMMENT ON COLUMN extraction_embeddings.embedding IS 'Vector embedding (1536 dims max). Supports Cohere v4, OpenAI small, Gemini. HNSW indexed for fast search.';
COMMENT ON COLUMN segment_embeddings.embedding IS 'Vector embedding (1536 dims max). Supports Cohere v4, OpenAI small, Gemini. HNSW indexed for fast search.';

-- Migration: Enable pgvector extension for vector similarity search
-- Version: 1.0.0
-- Description: Prerequisite for Q&A Engine RAG-based search
--
-- pgvector enables efficient storage and similarity search for embedding vectors
-- Used by the Q&A Engine to find semantically similar medical extractions

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify extension is installed (this will error if not available)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'pgvector extension is required but not installed';
    END IF;
END
$$;

-- Add comment for documentation
COMMENT ON EXTENSION vector IS 'pgvector: Vector similarity search for embeddings. Used by Q&A Engine for semantic search over medical extractions.';

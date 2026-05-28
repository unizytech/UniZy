-- Migration: Seed embedding models for Q&A Engine
-- Version: 1.0.0
-- Description: Populates embedding_models table with available providers
--
-- Models:
-- 1. cohere_v4 (DEFAULT) - Healthcare fine-tuned, 1536 dims
-- 2. openai_large - Highest accuracy, 3072 dims
-- 3. openai_small - Cost-effective, 1536 dims
-- 4. gemini - Already integrated in codebase, 768 dims

INSERT INTO embedding_models (
    model_code,
    model_name,
    provider,
    dimensions,
    description,
    is_default,
    is_active,
    price_per_million_tokens,
    max_tokens,
    supports_batching
)
VALUES
    -- Cohere embed-v4 (DEFAULT) - Healthcare fine-tuned
    (
        'cohere_v4',
        'Cohere Embed v4',
        'cohere',
        1536,
        'Healthcare fine-tuned embedding model. Excellent for medical terminology and clinical concepts. Supports search_document and search_query input types.',
        TRUE,  -- Default model
        TRUE,
        0.10,  -- $0.10 per 1M tokens
        8192,
        TRUE
    ),
    -- OpenAI text-embedding-3-large - Highest accuracy
    (
        'openai_large',
        'OpenAI Embedding 3 Large',
        'openai',
        3072,
        'Highest accuracy embedding model from OpenAI. 3072 dimensions for maximum semantic precision. Best for complex medical queries.',
        FALSE,
        TRUE,
        0.13,  -- $0.13 per 1M tokens
        8191,
        TRUE
    ),
    -- OpenAI text-embedding-3-small - Cost-effective
    (
        'openai_small',
        'OpenAI Embedding 3 Small',
        'openai',
        1536,
        'Cost-effective embedding model from OpenAI. Good balance of accuracy and cost. Suitable for high-volume use cases.',
        FALSE,
        TRUE,
        0.02,  -- $0.02 per 1M tokens
        8191,
        TRUE
    ),
    -- Google Gemini - Already integrated
    (
        'gemini',
        'Gemini Embedding',
        'gemini',
        768,
        'Google Gemini text embedding model. Already integrated in the codebase. Lower dimensions but fast and cost-effective.',
        FALSE,
        TRUE,
        0.00,  -- Free tier available (pay-as-you-go pricing varies)
        2048,
        TRUE
    )
ON CONFLICT (model_code) DO UPDATE SET
    model_name = EXCLUDED.model_name,
    provider = EXCLUDED.provider,
    dimensions = EXCLUDED.dimensions,
    description = EXCLUDED.description,
    price_per_million_tokens = EXCLUDED.price_per_million_tokens,
    max_tokens = EXCLUDED.max_tokens,
    supports_batching = EXCLUDED.supports_batching,
    updated_at = NOW();

-- Verify the default model is set
DO $$
DECLARE
    default_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO default_count FROM embedding_models WHERE is_default = TRUE;
    IF default_count = 0 THEN
        -- Set cohere_v4 as default if none is set
        UPDATE embedding_models SET is_default = TRUE WHERE model_code = 'cohere_v4';
    END IF;
END
$$;

-- Add comment for documentation
COMMENT ON TABLE embedding_models IS 'Available embedding models for Q&A Engine. Cohere v4 is the recommended default for healthcare applications.';

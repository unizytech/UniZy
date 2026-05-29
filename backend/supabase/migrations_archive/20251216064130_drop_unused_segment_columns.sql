-- Migration: Drop unused columns from segment_definitions
-- Date: 2025-12-16
-- Description: Remove complexity_level, estimated_tokens, and example_output columns
--              that are never actively used in the application.
--
-- Analysis:
-- - complexity_level: Only copied during cloning, never queried
-- - estimated_tokens: API calculates on-the-fly (len/4), column unused
-- - example_output: Only copied during cloning, never queried

-- Drop the unused columns
ALTER TABLE segment_definitions
DROP COLUMN IF EXISTS complexity_level,
DROP COLUMN IF EXISTS estimated_tokens,
DROP COLUMN IF EXISTS example_output;

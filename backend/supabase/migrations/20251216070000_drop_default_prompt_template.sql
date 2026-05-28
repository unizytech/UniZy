-- Migration: Drop unused column from doctors table
-- Date: 2025-12-16
-- Description: Remove default_prompt_template column that is not used in code.
--              Testing GitHub integration auto-apply.

ALTER TABLE doctors
DROP COLUMN IF EXISTS default_prompt_template;

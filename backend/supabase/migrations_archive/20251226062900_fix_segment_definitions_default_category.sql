-- Migration: Fix corrupted default_category default value in segment_definitions
-- The default value was corrupted to '''core''::character varying'::character varying
-- which produces a 22-character string, exceeding the varchar(20) limit

-- Fix the default value
ALTER TABLE segment_definitions
ALTER COLUMN default_category SET DEFAULT 'core'::varchar;

-- Log the fix
DO $$
BEGIN
    RAISE NOTICE 'Fixed segment_definitions.default_category default value';
END $$;

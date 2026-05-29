-- Add visit tracking columns to bills
ALTER TABLE bills ADD COLUMN IF NOT EXISTS visit_id VARCHAR(255);
ALTER TABLE bills ADD COLUMN IF NOT EXISTS visit_date TIMESTAMPTZ;
ALTER TABLE bills ADD COLUMN IF NOT EXISTS billed_by VARCHAR(255);

-- Index on visit_id for lookups
CREATE INDEX IF NOT EXISTS idx_bills_visit_id ON bills(visit_id) WHERE visit_id IS NOT NULL;

-- Make extraction_id nullable to support standalone bills
ALTER TABLE bills ALTER COLUMN extraction_id DROP NOT NULL;

-- Drop existing unique constraint on extraction_id if any, then add partial unique index
-- This enforces one active bill per extraction while allowing NULL extraction_id
DROP INDEX IF EXISTS idx_bills_extraction_unique;
CREATE UNIQUE INDEX idx_bills_extraction_unique
    ON bills(extraction_id)
    WHERE extraction_id IS NOT NULL AND bill_status != 'superseded';

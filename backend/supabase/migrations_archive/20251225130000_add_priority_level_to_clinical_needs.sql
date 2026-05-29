-- Add priority_level column to other_clinical_needs table
-- Priority levels: NONE, LOW, MEDIUM, HIGH
-- Consolidates the three boolean indicators into a single priority assessment

ALTER TABLE other_clinical_needs
ADD COLUMN IF NOT EXISTS priority_level TEXT DEFAULT 'NONE'
CHECK (priority_level IN ('NONE', 'LOW', 'MEDIUM', 'HIGH'));

-- Add index for priority-based queries
CREATE INDEX IF NOT EXISTS idx_needs_priority_level
ON other_clinical_needs(priority_level)
WHERE priority_level != 'NONE';

-- Comment for documentation
COMMENT ON COLUMN other_clinical_needs.priority_level IS
'Consolidated priority: HIGH (all 3 flags or recurring+refill), MEDIUM (2 flags or recurring alone), LOW (1 flag), NONE (0 flags)';

-- Migration: Add intervention_outcomes table for tracking intervention status and ROI
-- Version: 1.0.0
--
-- This table tracks the lifecycle of patient interventions:
-- - Status progression: PENDING -> CONTACTED -> ACCEPTED/DECLINED -> COMPLETED/EXPIRED
-- - Time-to-action metrics for performance tracking
-- - Actual revenue capture for ROI measurement
--
-- Used by:
-- - Coordinators: Update intervention status and add notes
-- - Dashboard: Display outcome metrics and conversion rates
-- - Analytics: Track time-to-action and revenue capture

-- =============================================================================
-- 1. Create intervention_outcomes table
-- =============================================================================

CREATE TABLE IF NOT EXISTS intervention_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Link to patient intervention
    intervention_id UUID NOT NULL REFERENCES patient_interventions(id) ON DELETE CASCADE,

    -- Status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'CONTACTED', 'ACCEPTED', 'DECLINED', 'COMPLETED', 'EXPIRED')),

    -- Timestamps for time-to-action metrics
    generated_at TIMESTAMPTZ NOT NULL,          -- Copy from intervention created_at
    first_contact_at TIMESTAMPTZ,               -- When staff first contacted patient
    status_updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,                   -- When intervention was completed
    expired_at TIMESTAMPTZ,                     -- When intervention expired (if applicable)

    -- Outcome data
    actual_revenue DECIMAL(12,2),               -- Actual revenue if completed
    decline_reason VARCHAR(100),                -- Reason if declined
    notes TEXT,                                 -- Staff notes

    -- Actor tracking
    updated_by_user_id UUID,                    -- Who updated the status
    updated_by_user_type VARCHAR(20),           -- 'coordinator', 'nurse', 'admin'

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Ensure one outcome record per intervention
    CONSTRAINT unique_intervention_outcome UNIQUE (intervention_id)
);

-- =============================================================================
-- 2. Create indexes for dashboard queries
-- =============================================================================

-- Index for filtering by status
CREATE INDEX idx_outcomes_status ON intervention_outcomes(status);

-- Index for time-based queries (recent updates)
CREATE INDEX idx_outcomes_status_updated ON intervention_outcomes(status, status_updated_at DESC);

-- Index for pending interventions (coordinator worklist)
CREATE INDEX idx_outcomes_pending ON intervention_outcomes(status) WHERE status = 'PENDING';

-- Index for completed interventions (revenue tracking)
CREATE INDEX idx_outcomes_completed ON intervention_outcomes(status, completed_at) WHERE status = 'COMPLETED';

-- Index for time-to-action analysis
CREATE INDEX idx_outcomes_generated ON intervention_outcomes(generated_at DESC);

-- =============================================================================
-- 3. Add trigger for updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION update_intervention_outcomes_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_intervention_outcomes_updated_at
    BEFORE UPDATE ON intervention_outcomes
    FOR EACH ROW
    EXECUTE FUNCTION update_intervention_outcomes_updated_at();

-- =============================================================================
-- 4. Create initial outcome records for existing interventions
-- =============================================================================

-- Insert PENDING outcome records for all existing interventions that don't have one
INSERT INTO intervention_outcomes (intervention_id, status, generated_at, created_at)
SELECT
    pi.id,
    'PENDING',
    pi.created_at,
    NOW()
FROM patient_interventions pi
WHERE NOT EXISTS (
    SELECT 1 FROM intervention_outcomes io WHERE io.intervention_id = pi.id
);

-- =============================================================================
-- 5. Add comments for documentation
-- =============================================================================

COMMENT ON TABLE intervention_outcomes IS
'Tracks intervention lifecycle: status progression, time-to-action, and revenue capture for ROI measurement';

COMMENT ON COLUMN intervention_outcomes.status IS
'Intervention status: PENDING (not started), CONTACTED (staff reached out), ACCEPTED (patient agreed), DECLINED (patient refused), COMPLETED (action taken), EXPIRED (time limit passed)';

COMMENT ON COLUMN intervention_outcomes.generated_at IS
'When the intervention was generated (copied from patient_interventions.created_at for time-to-action calculations)';

COMMENT ON COLUMN intervention_outcomes.first_contact_at IS
'When staff first contacted the patient about this intervention (for time-to-contact metrics)';

COMMENT ON COLUMN intervention_outcomes.actual_revenue IS
'Actual revenue captured when intervention is COMPLETED (for ROI calculation)';

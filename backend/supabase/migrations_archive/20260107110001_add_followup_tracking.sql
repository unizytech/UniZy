-- Migration: Add followup_tracking table for tracking patient follow-up dates
-- Version: 1.0.0
--
-- This table tracks expected follow-up dates and detects missed follow-ups:
-- - Parses follow-up text from FOLLOW_UP segment to calculate expected date
-- - Tracks whether patient returned for follow-up
-- - Enables "Missed Follow-up" alerts on dashboard
--
-- Used by:
-- - Dashboard: Show upcoming and missed follow-ups
-- - Retention tracking: Identify patients who didn't return
-- - Analytics: Follow-up completion rates by doctor/department

-- =============================================================================
-- 1. Create followup_tracking table
-- =============================================================================

CREATE TABLE IF NOT EXISTS followup_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Link to extraction and patient
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL,
    doctor_id UUID,
    hospital_id UUID,

    -- Consultation context
    consultation_date DATE NOT NULL,                -- Date of original consultation
    consultation_type_id UUID,

    -- Follow-up details (parsed from FOLLOW_UP segment)
    expected_followup_date DATE,                    -- Calculated from consultation_date + duration
    followup_window_start DATE,                     -- expected_date - grace_days
    followup_window_end DATE,                       -- expected_date + grace_days
    followup_window_days INTEGER DEFAULT 7,         -- Grace period in days (configurable)

    -- Source information
    followup_source VARCHAR(50) DEFAULT 'FOLLOW_UP_segment',  -- Where the follow-up was specified
    followup_text TEXT,                             -- Original text from FOLLOW_UP segment
    parsed_duration_days INTEGER,                   -- Parsed duration in days (e.g., "2 weeks" = 14)

    -- Tracking status
    status VARCHAR(20) DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RETURNED', 'MISSED', 'RESCHEDULED', 'CANCELLED', 'NO_FOLLOWUP')),

    -- Return visit linking
    return_extraction_id UUID,                      -- Link to return visit extraction if RETURNED
    return_date DATE,                               -- When patient actually returned

    -- Staff actions
    contacted_at TIMESTAMPTZ,                       -- When staff contacted patient about follow-up
    contacted_by_user_id UUID,
    notes TEXT,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- One tracking record per extraction
    CONSTRAINT unique_extraction_followup UNIQUE (extraction_id)
);

-- =============================================================================
-- 2. Create indexes for dashboard queries
-- =============================================================================

-- Index for filtering by status
CREATE INDEX idx_followup_status ON followup_tracking(status);

-- Index for upcoming follow-ups (date range queries)
CREATE INDEX idx_followup_expected_date ON followup_tracking(expected_followup_date)
    WHERE status = 'PENDING' AND expected_followup_date IS NOT NULL;

-- Index for missed follow-ups
CREATE INDEX idx_followup_missed ON followup_tracking(status, expected_followup_date)
    WHERE status = 'MISSED';

-- Index for doctor-specific queries
CREATE INDEX idx_followup_doctor ON followup_tracking(doctor_id, status);

-- Index for hospital-wide queries
CREATE INDEX idx_followup_hospital ON followup_tracking(hospital_id, status);

-- Index for patient lookup
CREATE INDEX idx_followup_patient ON followup_tracking(patient_id);

-- =============================================================================
-- 3. Add trigger for updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION update_followup_tracking_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_followup_tracking_updated_at
    BEFORE UPDATE ON followup_tracking
    FOR EACH ROW
    EXECUTE FUNCTION update_followup_tracking_updated_at();

-- =============================================================================
-- 4. Add trigger to auto-detect missed follow-ups
-- =============================================================================

-- This function marks follow-ups as MISSED when window_end has passed
-- Should be called by a scheduled job (e.g., daily cron)
CREATE OR REPLACE FUNCTION mark_missed_followups()
RETURNS INTEGER AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE followup_tracking
    SET
        status = 'MISSED',
        updated_at = NOW()
    WHERE status = 'PENDING'
      AND followup_window_end IS NOT NULL
      AND followup_window_end < CURRENT_DATE;

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- 5. Add comments for documentation
-- =============================================================================

COMMENT ON TABLE followup_tracking IS
'Tracks expected patient follow-up dates and detects missed follow-ups for dashboard alerts';

COMMENT ON COLUMN followup_tracking.expected_followup_date IS
'Calculated date when patient should return (consultation_date + parsed_duration_days)';

COMMENT ON COLUMN followup_tracking.followup_window_days IS
'Grace period in days - patient is considered on-time if they return within this window';

COMMENT ON COLUMN followup_tracking.status IS
'Follow-up status: PENDING (waiting), RETURNED (patient came back), MISSED (window passed), RESCHEDULED (new date set), CANCELLED (no longer needed), NO_FOLLOWUP (no follow-up specified)';

COMMENT ON COLUMN followup_tracking.parsed_duration_days IS
'Duration parsed from followup_text (e.g., "2 weeks" = 14, "1 month" = 30, "5 days" = 5)';

COMMENT ON FUNCTION mark_missed_followups() IS
'Call this function daily to automatically mark PENDING follow-ups as MISSED when their window has passed';

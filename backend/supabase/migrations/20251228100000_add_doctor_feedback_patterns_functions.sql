-- Migration: Add doctor feedback patterns functions for triage learning
-- These functions aggregate feedback data to help the triage engine learn from doctor preferences

-- Function to get aggregated feedback patterns for a doctor
-- Used by triage engine to learn from past feedback
CREATE OR REPLACE FUNCTION get_doctor_feedback_patterns(p_doctor_id UUID)
RETURNS TABLE (
    suggestion_text TEXT,
    suggestion_type TEXT,
    source_layer TEXT,
    total_shown INT,
    accepted_count INT,
    rejected_count INT,
    modified_count INT,
    rejection_reasons TEXT[],
    modified_versions TEXT[],
    acceptance_rate NUMERIC,
    last_feedback_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        tsl.suggestion_text,
        tsl.suggestion_type,
        tsl.source_layer,
        COUNT(DISTINCT tsl.id)::INT as total_shown,
        COUNT(tf.id) FILTER (WHERE tf.feedback_type = 'accepted')::INT as accepted_count,
        COUNT(tf.id) FILTER (WHERE tf.feedback_type = 'rejected')::INT as rejected_count,
        COUNT(tf.id) FILTER (WHERE tf.feedback_type = 'modified')::INT as modified_count,
        ARRAY_AGG(DISTINCT tf.rejection_reason) FILTER (WHERE tf.rejection_reason IS NOT NULL) as rejection_reasons,
        ARRAY_AGG(DISTINCT tf.modified_text) FILTER (WHERE tf.modified_text IS NOT NULL) as modified_versions,
        CASE
            WHEN COUNT(tf.id) > 0
            THEN ROUND(
                COUNT(tf.id) FILTER (WHERE tf.feedback_type = 'accepted')::NUMERIC /
                COUNT(tf.id)::NUMERIC * 100, 1
            )
            ELSE NULL
        END as acceptance_rate,
        MAX(tf.feedback_at) as last_feedback_at
    FROM triage_suggestion_log tsl
    LEFT JOIN triage_feedback tf ON tsl.id = tf.suggestion_id
    WHERE tsl.doctor_id = p_doctor_id
    GROUP BY tsl.suggestion_text, tsl.suggestion_type, tsl.source_layer
    HAVING COUNT(tf.id) > 0  -- Only return suggestions that have feedback
    ORDER BY COUNT(tf.id) DESC;  -- Most feedback first
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get rejection patterns (suggestions rejected 2+ times)
CREATE OR REPLACE FUNCTION get_doctor_rejection_patterns(p_doctor_id UUID)
RETURNS TABLE (
    suggestion_pattern TEXT,
    suggestion_type TEXT,
    rejection_count INT,
    common_reasons TEXT[]
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        -- Normalize suggestion text for pattern matching (first 100 chars, lowercase)
        LOWER(LEFT(tsl.suggestion_text, 100)) as suggestion_pattern,
        tsl.suggestion_type,
        COUNT(*)::INT as rejection_count,
        ARRAY_AGG(DISTINCT tf.rejection_reason) FILTER (WHERE tf.rejection_reason IS NOT NULL) as common_reasons
    FROM triage_feedback tf
    JOIN triage_suggestion_log tsl ON tf.suggestion_id = tsl.id
    WHERE tsl.doctor_id = p_doctor_id
      AND tf.feedback_type = 'rejected'
    GROUP BY LOWER(LEFT(tsl.suggestion_text, 100)), tsl.suggestion_type
    HAVING COUNT(*) >= 2  -- Only patterns rejected 2+ times
    ORDER BY COUNT(*) DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get preference patterns (suggestions accepted 3+ times)
CREATE OR REPLACE FUNCTION get_doctor_preference_patterns(p_doctor_id UUID)
RETURNS TABLE (
    suggestion_pattern TEXT,
    suggestion_type TEXT,
    acceptance_count INT,
    avg_priority_rank NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        LOWER(LEFT(tsl.suggestion_text, 100)) as suggestion_pattern,
        tsl.suggestion_type,
        COUNT(*)::INT as acceptance_count,
        ROUND(AVG(tsl.priority_rank), 1) as avg_priority_rank
    FROM triage_feedback tf
    JOIN triage_suggestion_log tsl ON tf.suggestion_id = tsl.id
    WHERE tsl.doctor_id = p_doctor_id
      AND tf.feedback_type = 'accepted'
    GROUP BY LOWER(LEFT(tsl.suggestion_text, 100)), tsl.suggestion_type
    HAVING COUNT(*) >= 3  -- Only patterns accepted 3+ times
    ORDER BY COUNT(*) DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION get_doctor_feedback_patterns IS 'Aggregates all feedback for a doctor to learn suggestion preferences';
COMMENT ON FUNCTION get_doctor_rejection_patterns IS 'Returns suggestions rejected 2+ times by a doctor for filtering';
COMMENT ON FUNCTION get_doctor_preference_patterns IS 'Returns suggestions accepted 3+ times by a doctor for boosting';

-- Migration: Add usage aggregation support
-- Adds api_client_id to llm_usage_log and recording_sessions, creates aggregation views

-- ============================================================================
-- 1. Add api_client_id column to llm_usage_log
-- ============================================================================

ALTER TABLE llm_usage_log
ADD COLUMN IF NOT EXISTS api_client_id UUID REFERENCES api_clients(id);

-- Index for efficient aggregation queries
CREATE INDEX IF NOT EXISTS idx_llm_usage_log_api_client_id
ON llm_usage_log(api_client_id);

-- Composite indexes for common aggregation patterns
CREATE INDEX IF NOT EXISTS idx_llm_usage_log_api_client_created
ON llm_usage_log(api_client_id, created_at);

CREATE INDEX IF NOT EXISTS idx_llm_usage_log_doctor_created
ON llm_usage_log(doctor_id, created_at);

-- ============================================================================
-- 1b. Add api_client_id column to recording_sessions
-- ============================================================================

ALTER TABLE recording_sessions
ADD COLUMN IF NOT EXISTS api_client_id UUID REFERENCES api_clients(id);

CREATE INDEX IF NOT EXISTS idx_recording_sessions_api_client_id
ON recording_sessions(api_client_id);

COMMENT ON COLUMN recording_sessions.api_client_id IS 'Reference to the API client that started this recording session. NULL for admin users.';

-- ============================================================================
-- 2. Create API Client Usage Summary View
-- ============================================================================

CREATE OR REPLACE VIEW v_api_client_usage_summary AS
SELECT
    ac.id AS api_client_id,
    ac.client_name,
    ac.client_type,
    ac.hospital_id,
    h.hospital_name,
    COUNT(DISTINCT l.id) AS total_api_calls,
    COUNT(DISTINCT l.session_id) AS total_sessions,
    COALESCE(SUM(l.total_cost_usd), 0) AS total_cost_usd,
    COALESCE(SUM(l.cache_savings_usd), 0) AS total_cache_savings_usd,
    COALESCE(SUM(l.prompt_token_count), 0) AS total_input_tokens,
    COALESCE(SUM(l.candidates_token_count), 0) AS total_output_tokens,
    COALESCE(SUM(l.cached_content_token_count), 0) AS total_cached_tokens,
    -- Recording hours from recording_sessions
    COALESCE(
        (SELECT SUM(rs.total_duration_seconds) / 3600.0
         FROM recording_sessions rs
         WHERE rs.id IN (SELECT DISTINCT session_id FROM llm_usage_log WHERE api_client_id = ac.id)
        ), 0
    ) AS total_recording_hours,
    -- Also aggregate audio_duration_seconds from transcription calls
    COALESCE(SUM(CASE WHEN l.call_type = 'transcription' THEN l.audio_duration_seconds ELSE 0 END) / 3600.0, 0) AS total_transcription_hours,
    AVG(CASE WHEN l.cache_hit THEN l.cache_hit_ratio ELSE NULL END) AS avg_cache_hit_ratio,
    COUNT(CASE WHEN l.response_status = 'error' THEN 1 END) AS error_count,
    MIN(l.created_at) AS first_usage_at,
    MAX(l.created_at) AS last_usage_at
FROM api_clients ac
LEFT JOIN llm_usage_log l ON l.api_client_id = ac.id
LEFT JOIN hospitals h ON ac.hospital_id = h.id
GROUP BY ac.id, ac.client_name, ac.client_type, ac.hospital_id, h.hospital_name;

-- ============================================================================
-- 3. Create Hospital Usage Summary View
-- ============================================================================

CREATE OR REPLACE VIEW v_hospital_usage_summary AS
SELECT
    h.id AS hospital_id,
    h.hospital_name,
    h.hospital_code,
    COUNT(DISTINCT l.id) AS total_api_calls,
    COUNT(DISTINCT l.session_id) AS total_sessions,
    COUNT(DISTINCT l.doctor_id) AS unique_doctors,
    COUNT(DISTINCT l.api_client_id) AS unique_api_clients,
    COALESCE(SUM(l.total_cost_usd), 0) AS total_cost_usd,
    COALESCE(SUM(l.cache_savings_usd), 0) AS total_cache_savings_usd,
    COALESCE(SUM(l.prompt_token_count), 0) AS total_input_tokens,
    COALESCE(SUM(l.candidates_token_count), 0) AS total_output_tokens,
    COALESCE(SUM(l.cached_content_token_count), 0) AS total_cached_tokens,
    -- Recording hours from recording_sessions via doctor
    COALESCE(
        (SELECT SUM(rs.total_duration_seconds) / 3600.0
         FROM recording_sessions rs
         INNER JOIN doctors d ON rs.doctor_id = d.id
         WHERE d.hospital_id = h.id
        ), 0
    ) AS total_recording_hours,
    -- Transcription hours from llm_usage_log
    COALESCE(SUM(CASE WHEN l.call_type = 'transcription' THEN l.audio_duration_seconds ELSE 0 END) / 3600.0, 0) AS total_transcription_hours,
    AVG(CASE WHEN l.cache_hit THEN l.cache_hit_ratio ELSE NULL END) AS avg_cache_hit_ratio,
    COUNT(CASE WHEN l.response_status = 'error' THEN 1 END) AS error_count,
    MIN(l.created_at) AS first_usage_at,
    MAX(l.created_at) AS last_usage_at
FROM hospitals h
LEFT JOIN doctors d ON d.hospital_id = h.id
LEFT JOIN llm_usage_log l ON l.doctor_id = d.id
GROUP BY h.id, h.hospital_name, h.hospital_code;

-- ============================================================================
-- 4. Enhanced Doctor Usage Summary View (v2 with recording hours)
-- ============================================================================

CREATE OR REPLACE VIEW v_doctor_usage_summary_v2 AS
SELECT
    d.id AS doctor_id,
    d.full_name AS doctor_name,
    d.specialization,
    d.hospital_id,
    h.hospital_name,
    COUNT(DISTINCT l.id) AS total_api_calls,
    COUNT(DISTINCT l.session_id) AS total_sessions,
    COALESCE(SUM(l.total_cost_usd), 0) AS total_cost_usd,
    COALESCE(SUM(l.cache_savings_usd), 0) AS total_cache_savings_usd,
    COALESCE(SUM(l.prompt_token_count), 0) AS total_input_tokens,
    COALESCE(SUM(l.candidates_token_count), 0) AS total_output_tokens,
    COALESCE(SUM(l.cached_content_token_count), 0) AS total_cached_tokens,
    -- Recording hours from recording_sessions
    COALESCE(
        (SELECT SUM(rs.total_duration_seconds) / 3600.0
         FROM recording_sessions rs
         WHERE rs.doctor_id = d.id
        ), 0
    ) AS total_recording_hours,
    -- Transcription hours from llm_usage_log
    COALESCE(SUM(CASE WHEN l.call_type = 'transcription' THEN l.audio_duration_seconds ELSE 0 END) / 3600.0, 0) AS total_transcription_hours,
    AVG(CASE WHEN l.cache_hit THEN l.cache_hit_ratio ELSE NULL END) AS avg_cache_hit_ratio,
    COUNT(CASE WHEN l.response_status = 'error' THEN 1 END) AS error_count,
    -- Cost per session
    CASE
        WHEN COUNT(DISTINCT l.session_id) > 0
        THEN COALESCE(SUM(l.total_cost_usd), 0) / COUNT(DISTINCT l.session_id)
        ELSE 0
    END AS avg_cost_per_session,
    MIN(l.created_at) AS first_usage_at,
    MAX(l.created_at) AS last_usage_at
FROM doctors d
LEFT JOIN llm_usage_log l ON l.doctor_id = d.id
LEFT JOIN hospitals h ON d.hospital_id = h.id
GROUP BY d.id, d.full_name, d.specialization, d.hospital_id, h.hospital_name;

-- ============================================================================
-- 5. Create RPC function for flexible usage aggregation with date filters
-- ============================================================================

CREATE OR REPLACE FUNCTION get_usage_summary(
    p_group_by TEXT DEFAULT 'doctor',  -- 'api_client', 'hospital', 'doctor'
    p_date_from TIMESTAMPTZ DEFAULT NULL,
    p_date_to TIMESTAMPTZ DEFAULT NULL,
    p_api_client_id UUID DEFAULT NULL,
    p_hospital_id UUID DEFAULT NULL,
    p_doctor_id UUID DEFAULT NULL,
    p_limit INT DEFAULT 100,
    p_offset INT DEFAULT 0
)
RETURNS TABLE (
    group_id UUID,
    group_name TEXT,
    group_type TEXT,
    hospital_id UUID,
    hospital_name TEXT,
    total_api_calls BIGINT,
    total_sessions BIGINT,
    total_cost_usd NUMERIC,
    total_cache_savings_usd NUMERIC,
    total_input_tokens BIGINT,
    total_output_tokens BIGINT,
    total_cached_tokens BIGINT,
    total_recording_hours NUMERIC,
    total_transcription_hours NUMERIC,
    avg_cache_hit_ratio NUMERIC,
    error_count BIGINT,
    first_usage_at TIMESTAMPTZ,
    last_usage_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    IF p_group_by = 'api_client' THEN
        RETURN QUERY
        SELECT
            ac.id AS group_id,
            ac.client_name::TEXT AS group_name,
            ac.client_type::TEXT AS group_type,
            ac.hospital_id,
            h.hospital_name::TEXT,
            COUNT(DISTINCT l.id)::BIGINT AS total_api_calls,
            COUNT(DISTINCT l.session_id)::BIGINT AS total_sessions,
            COALESCE(SUM(l.total_cost_usd), 0)::NUMERIC AS total_cost_usd,
            COALESCE(SUM(l.cache_savings_usd), 0)::NUMERIC AS total_cache_savings_usd,
            COALESCE(SUM(l.prompt_token_count), 0)::BIGINT AS total_input_tokens,
            COALESCE(SUM(l.candidates_token_count), 0)::BIGINT AS total_output_tokens,
            COALESCE(SUM(l.cached_content_token_count), 0)::BIGINT AS total_cached_tokens,
            COALESCE(
                (SELECT SUM(rs.total_duration_seconds) / 3600.0
                 FROM recording_sessions rs
                 WHERE rs.id IN (
                     SELECT DISTINCT ll.session_id FROM llm_usage_log ll
                     WHERE ll.api_client_id = ac.id
                     AND (p_date_from IS NULL OR ll.created_at >= p_date_from)
                     AND (p_date_to IS NULL OR ll.created_at < p_date_to)
                 )
                ), 0
            )::NUMERIC AS total_recording_hours,
            COALESCE(SUM(CASE WHEN l.call_type = 'transcription' THEN l.audio_duration_seconds ELSE 0 END) / 3600.0, 0)::NUMERIC AS total_transcription_hours,
            AVG(CASE WHEN l.cache_hit THEN l.cache_hit_ratio ELSE NULL END)::NUMERIC AS avg_cache_hit_ratio,
            COUNT(CASE WHEN l.response_status = 'error' THEN 1 END)::BIGINT AS error_count,
            MIN(l.created_at) AS first_usage_at,
            MAX(l.created_at) AS last_usage_at
        FROM api_clients ac
        LEFT JOIN llm_usage_log l ON l.api_client_id = ac.id
            AND (p_date_from IS NULL OR l.created_at >= p_date_from)
            AND (p_date_to IS NULL OR l.created_at < p_date_to)
        LEFT JOIN hospitals h ON ac.hospital_id = h.id
        WHERE (p_api_client_id IS NULL OR ac.id = p_api_client_id)
          AND (p_hospital_id IS NULL OR ac.hospital_id = p_hospital_id)
        GROUP BY ac.id, ac.client_name, ac.client_type, ac.hospital_id, h.hospital_name
        ORDER BY COALESCE(SUM(l.total_cost_usd), 0) DESC
        LIMIT p_limit OFFSET p_offset;

    ELSIF p_group_by = 'hospital' THEN
        RETURN QUERY
        SELECT
            h.id AS group_id,
            h.hospital_name::TEXT AS group_name,
            'hospital'::TEXT AS group_type,
            h.id AS hospital_id,
            h.hospital_name::TEXT,
            COUNT(DISTINCT l.id)::BIGINT AS total_api_calls,
            COUNT(DISTINCT l.session_id)::BIGINT AS total_sessions,
            COALESCE(SUM(l.total_cost_usd), 0)::NUMERIC AS total_cost_usd,
            COALESCE(SUM(l.cache_savings_usd), 0)::NUMERIC AS total_cache_savings_usd,
            COALESCE(SUM(l.prompt_token_count), 0)::BIGINT AS total_input_tokens,
            COALESCE(SUM(l.candidates_token_count), 0)::BIGINT AS total_output_tokens,
            COALESCE(SUM(l.cached_content_token_count), 0)::BIGINT AS total_cached_tokens,
            COALESCE(
                (SELECT SUM(rs.total_duration_seconds) / 3600.0
                 FROM recording_sessions rs
                 INNER JOIN doctors dd ON rs.doctor_id = dd.id
                 WHERE dd.hospital_id = h.id
                 AND (p_date_from IS NULL OR rs.created_at >= p_date_from)
                 AND (p_date_to IS NULL OR rs.created_at < p_date_to)
                ), 0
            )::NUMERIC AS total_recording_hours,
            COALESCE(SUM(CASE WHEN l.call_type = 'transcription' THEN l.audio_duration_seconds ELSE 0 END) / 3600.0, 0)::NUMERIC AS total_transcription_hours,
            AVG(CASE WHEN l.cache_hit THEN l.cache_hit_ratio ELSE NULL END)::NUMERIC AS avg_cache_hit_ratio,
            COUNT(CASE WHEN l.response_status = 'error' THEN 1 END)::BIGINT AS error_count,
            MIN(l.created_at) AS first_usage_at,
            MAX(l.created_at) AS last_usage_at
        FROM hospitals h
        LEFT JOIN doctors d ON d.hospital_id = h.id
        LEFT JOIN llm_usage_log l ON l.doctor_id = d.id
            AND (p_date_from IS NULL OR l.created_at >= p_date_from)
            AND (p_date_to IS NULL OR l.created_at < p_date_to)
        WHERE (p_hospital_id IS NULL OR h.id = p_hospital_id)
        GROUP BY h.id, h.hospital_name
        ORDER BY COALESCE(SUM(l.total_cost_usd), 0) DESC
        LIMIT p_limit OFFSET p_offset;

    ELSE  -- Default: doctor
        RETURN QUERY
        SELECT
            d.id AS group_id,
            d.full_name::TEXT AS group_name,
            COALESCE(d.specialization, 'General')::TEXT AS group_type,
            d.hospital_id,
            h.hospital_name::TEXT,
            COUNT(DISTINCT l.id)::BIGINT AS total_api_calls,
            COUNT(DISTINCT l.session_id)::BIGINT AS total_sessions,
            COALESCE(SUM(l.total_cost_usd), 0)::NUMERIC AS total_cost_usd,
            COALESCE(SUM(l.cache_savings_usd), 0)::NUMERIC AS total_cache_savings_usd,
            COALESCE(SUM(l.prompt_token_count), 0)::BIGINT AS total_input_tokens,
            COALESCE(SUM(l.candidates_token_count), 0)::BIGINT AS total_output_tokens,
            COALESCE(SUM(l.cached_content_token_count), 0)::BIGINT AS total_cached_tokens,
            COALESCE(
                (SELECT SUM(rs.total_duration_seconds) / 3600.0
                 FROM recording_sessions rs
                 WHERE rs.doctor_id = d.id
                 AND (p_date_from IS NULL OR rs.created_at >= p_date_from)
                 AND (p_date_to IS NULL OR rs.created_at < p_date_to)
                ), 0
            )::NUMERIC AS total_recording_hours,
            COALESCE(SUM(CASE WHEN l.call_type = 'transcription' THEN l.audio_duration_seconds ELSE 0 END) / 3600.0, 0)::NUMERIC AS total_transcription_hours,
            AVG(CASE WHEN l.cache_hit THEN l.cache_hit_ratio ELSE NULL END)::NUMERIC AS avg_cache_hit_ratio,
            COUNT(CASE WHEN l.response_status = 'error' THEN 1 END)::BIGINT AS error_count,
            MIN(l.created_at) AS first_usage_at,
            MAX(l.created_at) AS last_usage_at
        FROM doctors d
        LEFT JOIN llm_usage_log l ON l.doctor_id = d.id
            AND (p_date_from IS NULL OR l.created_at >= p_date_from)
            AND (p_date_to IS NULL OR l.created_at < p_date_to)
        LEFT JOIN hospitals h ON d.hospital_id = h.id
        WHERE (p_doctor_id IS NULL OR d.id = p_doctor_id)
          AND (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
        GROUP BY d.id, d.full_name, d.specialization, d.hospital_id, h.hospital_name
        ORDER BY COALESCE(SUM(l.total_cost_usd), 0) DESC
        LIMIT p_limit OFFSET p_offset;
    END IF;
END;
$$;

-- ============================================================================
-- 6. Create RPC function for usage totals (for summary cards)
-- ============================================================================

CREATE OR REPLACE FUNCTION get_usage_totals(
    p_date_from TIMESTAMPTZ DEFAULT NULL,
    p_date_to TIMESTAMPTZ DEFAULT NULL,
    p_api_client_id UUID DEFAULT NULL,
    p_hospital_id UUID DEFAULT NULL,
    p_doctor_id UUID DEFAULT NULL
)
RETURNS TABLE (
    total_api_calls BIGINT,
    total_sessions BIGINT,
    total_cost_usd NUMERIC,
    total_cache_savings_usd NUMERIC,
    total_input_tokens BIGINT,
    total_output_tokens BIGINT,
    total_recording_hours NUMERIC,
    unique_doctors BIGINT,
    unique_hospitals BIGINT,
    unique_api_clients BIGINT
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(DISTINCT l.id)::BIGINT AS total_api_calls,
        COUNT(DISTINCT l.session_id)::BIGINT AS total_sessions,
        COALESCE(SUM(l.total_cost_usd), 0)::NUMERIC AS total_cost_usd,
        COALESCE(SUM(l.cache_savings_usd), 0)::NUMERIC AS total_cache_savings_usd,
        COALESCE(SUM(l.prompt_token_count), 0)::BIGINT AS total_input_tokens,
        COALESCE(SUM(l.candidates_token_count), 0)::BIGINT AS total_output_tokens,
        COALESCE(
            (SELECT SUM(rs.total_duration_seconds) / 3600.0
             FROM recording_sessions rs
             WHERE rs.id IN (
                 SELECT DISTINCT ll.session_id FROM llm_usage_log ll
                 WHERE (p_date_from IS NULL OR ll.created_at >= p_date_from)
                 AND (p_date_to IS NULL OR ll.created_at < p_date_to)
                 AND (p_api_client_id IS NULL OR ll.api_client_id = p_api_client_id)
                 AND (p_doctor_id IS NULL OR ll.doctor_id = p_doctor_id)
             )
            ), 0
        )::NUMERIC AS total_recording_hours,
        COUNT(DISTINCT l.doctor_id)::BIGINT AS unique_doctors,
        COUNT(DISTINCT d.hospital_id)::BIGINT AS unique_hospitals,
        COUNT(DISTINCT l.api_client_id)::BIGINT AS unique_api_clients
    FROM llm_usage_log l
    LEFT JOIN doctors d ON l.doctor_id = d.id
    WHERE (p_date_from IS NULL OR l.created_at >= p_date_from)
      AND (p_date_to IS NULL OR l.created_at < p_date_to)
      AND (p_api_client_id IS NULL OR l.api_client_id = p_api_client_id)
      AND (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
      AND (p_doctor_id IS NULL OR l.doctor_id = p_doctor_id);
END;
$$;

-- Grant execute permissions
GRANT EXECUTE ON FUNCTION get_usage_summary TO authenticated;
GRANT EXECUTE ON FUNCTION get_usage_summary TO service_role;
GRANT EXECUTE ON FUNCTION get_usage_totals TO authenticated;
GRANT EXECUTE ON FUNCTION get_usage_totals TO service_role;

-- ============================================================================
-- 7. Comment on new column
-- ============================================================================

COMMENT ON COLUMN llm_usage_log.api_client_id IS 'Reference to the API client that made this request. NULL for admin users.';

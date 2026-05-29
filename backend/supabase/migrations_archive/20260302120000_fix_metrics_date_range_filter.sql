-- Fix date_to filter across all metrics RPCs
-- Problem: p_date_to as a date resolves to midnight (00:00:00), excluding all
-- timestamps from that day. Fix: use < p_date_to + interval '1 day' instead of <= p_date_to.
-- Same fix applied to medical_extractions.created_at and extraction_accuracy_metrics.computed_at.

-- =============================================================================
-- Fix: get_ai_acceptance_metrics
-- =============================================================================
CREATE OR REPLACE FUNCTION get_ai_acceptance_metrics(
    p_hospital_id UUID DEFAULT NULL,
    p_doctor_id UUID DEFAULT NULL,
    p_date_from TIMESTAMPTZ DEFAULT NULL,
    p_date_to TIMESTAMPTZ DEFAULT NULL,
    p_group_by TEXT DEFAULT 'total'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSONB;
BEGIN
    IF p_group_by = 'total' THEN
        SELECT jsonb_build_object(
            'total_extractions', COUNT(*),
            'unchanged_count', COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL),
            'edited_count', COUNT(*) FILTER (WHERE me.edit_count > 0),
            'acceptance_rate_pct', ROUND(
                COALESCE(
                    COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL)::NUMERIC
                    / NULLIF(COUNT(*), 0) * 100,
                0), 2
            ),
            'avg_edit_count', ROUND(COALESCE(AVG(me.edit_count)::numeric, 0), 2)
        ) INTO result
        FROM medical_extractions me
        JOIN doctors d ON d.id = me.doctor_id
        WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
          AND (p_doctor_id IS NULL OR me.doctor_id = p_doctor_id)
          AND (p_date_from IS NULL OR me.created_at >= p_date_from)
          AND (p_date_to IS NULL OR me.created_at < p_date_to + interval '1 day');

    ELSIF p_group_by = 'daily' THEN
        SELECT COALESCE(jsonb_agg(row_data ORDER BY day), '[]'::jsonb) INTO result
        FROM (
            SELECT jsonb_build_object(
                'date', me.created_at::date,
                'total', COUNT(*),
                'unchanged', COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL),
                'edited', COUNT(*) FILTER (WHERE me.edit_count > 0),
                'acceptance_rate_pct', ROUND(
                    COALESCE(
                        COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL)::NUMERIC
                        / NULLIF(COUNT(*), 0) * 100,
                    0), 2
                )
            ) AS row_data, me.created_at::date AS day
            FROM medical_extractions me
            JOIN doctors d ON d.id = me.doctor_id
            WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
              AND (p_doctor_id IS NULL OR me.doctor_id = p_doctor_id)
              AND (p_date_from IS NULL OR me.created_at >= p_date_from)
              AND (p_date_to IS NULL OR me.created_at < p_date_to + interval '1 day')
            GROUP BY me.created_at::date
        ) sub;

    ELSIF p_group_by = 'doctor' THEN
        SELECT COALESCE(jsonb_agg(row_data ORDER BY doctor_name), '[]'::jsonb) INTO result
        FROM (
            SELECT jsonb_build_object(
                'doctor_id', d.id,
                'doctor_name', d.full_name,
                'total', COUNT(*),
                'unchanged', COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL),
                'edited', COUNT(*) FILTER (WHERE me.edit_count > 0),
                'acceptance_rate_pct', ROUND(
                    COALESCE(
                        COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL)::NUMERIC
                        / NULLIF(COUNT(*), 0) * 100,
                    0), 2
                ),
                'avg_edit_count', ROUND(COALESCE(AVG(me.edit_count)::numeric, 0), 2)
            ) AS row_data, d.full_name AS doctor_name
            FROM medical_extractions me
            JOIN doctors d ON d.id = me.doctor_id
            WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
              AND (p_doctor_id IS NULL OR me.doctor_id = p_doctor_id)
              AND (p_date_from IS NULL OR me.created_at >= p_date_from)
              AND (p_date_to IS NULL OR me.created_at < p_date_to + interval '1 day')
            GROUP BY d.id, d.full_name
        ) sub;

    ELSIF p_group_by = 'doctor_daily' THEN
        SELECT COALESCE(jsonb_agg(row_data ORDER BY doctor_name, day), '[]'::jsonb) INTO result
        FROM (
            SELECT jsonb_build_object(
                'doctor_id', d.id,
                'doctor_name', d.full_name,
                'date', me.created_at::date,
                'total', COUNT(*),
                'unchanged', COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL),
                'edited', COUNT(*) FILTER (WHERE me.edit_count > 0),
                'acceptance_rate_pct', ROUND(
                    COALESCE(
                        COUNT(*) FILTER (WHERE me.edit_count = 0 OR me.edit_count IS NULL)::NUMERIC
                        / NULLIF(COUNT(*), 0) * 100,
                    0), 2
                )
            ) AS row_data, d.full_name AS doctor_name, me.created_at::date AS day
            FROM medical_extractions me
            JOIN doctors d ON d.id = me.doctor_id
            WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
              AND (p_doctor_id IS NULL OR me.doctor_id = p_doctor_id)
              AND (p_date_from IS NULL OR me.created_at >= p_date_from)
              AND (p_date_to IS NULL OR me.created_at < p_date_to + interval '1 day')
            GROUP BY d.id, d.full_name, me.created_at::date
        ) sub;
    END IF;

    RETURN COALESCE(result, '{}'::jsonb);
END;
$$;

-- =============================================================================
-- Fix: get_notes_per_doctor_per_day
-- =============================================================================
CREATE OR REPLACE FUNCTION get_notes_per_doctor_per_day(
    p_hospital_id UUID DEFAULT NULL,
    p_doctor_id UUID DEFAULT NULL,
    p_date_from TIMESTAMPTZ DEFAULT NULL,
    p_date_to TIMESTAMPTZ DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT COALESCE(jsonb_agg(row_data ORDER BY doctor_name, day), '[]'::jsonb) INTO result
    FROM (
        SELECT jsonb_build_object(
            'doctor_id', d.id,
            'doctor_name', d.full_name,
            'date', me.created_at::date,
            'note_count', COUNT(*)
        ) AS row_data, d.full_name AS doctor_name, me.created_at::date AS day
        FROM medical_extractions me
        JOIN doctors d ON d.id = me.doctor_id
        WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
          AND (p_doctor_id IS NULL OR me.doctor_id = p_doctor_id)
          AND (p_date_from IS NULL OR me.created_at >= p_date_from)
          AND (p_date_to IS NULL OR me.created_at < p_date_to + interval '1 day')
        GROUP BY d.id, d.full_name, me.created_at::date
    ) sub;

    RETURN result;
END;
$$;

-- =============================================================================
-- Fix: get_avg_pipeline_timing
-- =============================================================================
CREATE OR REPLACE FUNCTION get_avg_pipeline_timing(
    p_hospital_id UUID DEFAULT NULL,
    p_doctor_id UUID DEFAULT NULL,
    p_date_from TIMESTAMPTZ DEFAULT NULL,
    p_date_to TIMESTAMPTZ DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'count', COUNT(*),
        'stitching', jsonb_build_object(
            'avg', ROUND(COALESCE(AVG(me.stitching_time_seconds), 0)::numeric, 2),
            'p50', ROUND(COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY me.stitching_time_seconds), 0)::numeric, 2),
            'p95', ROUND(COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY me.stitching_time_seconds), 0)::numeric, 2),
            'p99', ROUND(COALESCE(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY me.stitching_time_seconds), 0)::numeric, 2)
        ),
        'transcription', jsonb_build_object(
            'avg', ROUND(COALESCE(AVG(me.transcription_time_seconds), 0)::numeric, 2),
            'p50', ROUND(COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY me.transcription_time_seconds), 0)::numeric, 2),
            'p95', ROUND(COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY me.transcription_time_seconds), 0)::numeric, 2),
            'p99', ROUND(COALESCE(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY me.transcription_time_seconds), 0)::numeric, 2)
        ),
        'extraction', jsonb_build_object(
            'avg', ROUND(COALESCE(AVG(me.extraction_time_seconds), 0)::numeric, 2),
            'p50', ROUND(COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY me.extraction_time_seconds), 0)::numeric, 2),
            'p95', ROUND(COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY me.extraction_time_seconds), 0)::numeric, 2),
            'p99', ROUND(COALESCE(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY me.extraction_time_seconds), 0)::numeric, 2)
        ),
        'total', jsonb_build_object(
            'avg', ROUND(COALESCE(AVG(me.total_processing_time_seconds), 0)::numeric, 2),
            'p50', ROUND(COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY me.total_processing_time_seconds), 0)::numeric, 2),
            'p95', ROUND(COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY me.total_processing_time_seconds), 0)::numeric, 2),
            'p99', ROUND(COALESCE(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY me.total_processing_time_seconds), 0)::numeric, 2)
        )
    ) INTO result
    FROM medical_extractions me
    JOIN doctors d ON d.id = me.doctor_id
    WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
      AND (p_doctor_id IS NULL OR me.doctor_id = p_doctor_id)
      AND (p_date_from IS NULL OR me.created_at >= p_date_from)
      AND (p_date_to IS NULL OR me.created_at < p_date_to + interval '1 day')
      AND me.total_processing_time_seconds IS NOT NULL;

    RETURN COALESCE(result, '{}'::jsonb);
END;
$$;

-- =============================================================================
-- Fix: get_accuracy_metrics
-- =============================================================================
CREATE OR REPLACE FUNCTION get_accuracy_metrics(
    p_hospital_id UUID DEFAULT NULL,
    p_doctor_id UUID DEFAULT NULL,
    p_date_from TIMESTAMPTZ DEFAULT NULL,
    p_date_to TIMESTAMPTZ DEFAULT NULL,
    p_group_by TEXT DEFAULT 'total'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSONB;
BEGIN
    IF p_group_by = 'total' THEN
        SELECT jsonb_build_object(
            'count', COUNT(*),
            'avg_wer', ROUND(COALESCE(AVG(eam.overall_wer), 0)::numeric, 4),
            'median_wer', ROUND(COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY eam.overall_wer), 0)::numeric, 4),
            'p95_wer', ROUND(COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY eam.overall_wer), 0)::numeric, 4),
            'avg_entity_error_rate', ROUND(COALESCE(AVG(eam.entity_error_rate), 0)::numeric, 4),
            'avg_segments_unchanged', ROUND(COALESCE(AVG(eam.segments_unchanged), 0)::numeric, 1),
            'avg_segments_modified', ROUND(COALESCE(AVG(eam.segments_modified), 0)::numeric, 1),
            'avg_doctor_additions', ROUND(COALESCE(AVG(eam.doctor_additions_count), 0)::numeric, 1)
        ) INTO result
        FROM extraction_accuracy_metrics eam
        JOIN doctors d ON d.id = eam.doctor_id
        WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
          AND (p_doctor_id IS NULL OR eam.doctor_id = p_doctor_id)
          AND (p_date_from IS NULL OR eam.computed_at >= p_date_from)
          AND (p_date_to IS NULL OR eam.computed_at < p_date_to + interval '1 day');

    ELSIF p_group_by = 'doctor' THEN
        SELECT COALESCE(jsonb_agg(row_data ORDER BY doctor_name), '[]'::jsonb) INTO result
        FROM (
            SELECT jsonb_build_object(
                'doctor_id', d.id,
                'doctor_name', d.full_name,
                'count', COUNT(*),
                'avg_wer', ROUND(COALESCE(AVG(eam.overall_wer), 0)::numeric, 4),
                'avg_entity_error_rate', ROUND(COALESCE(AVG(eam.entity_error_rate), 0)::numeric, 4),
                'avg_segments_modified', ROUND(COALESCE(AVG(eam.segments_modified), 0)::numeric, 1)
            ) AS row_data, d.full_name AS doctor_name
            FROM extraction_accuracy_metrics eam
            JOIN doctors d ON d.id = eam.doctor_id
            WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
              AND (p_doctor_id IS NULL OR eam.doctor_id = p_doctor_id)
              AND (p_date_from IS NULL OR eam.computed_at >= p_date_from)
              AND (p_date_to IS NULL OR eam.computed_at < p_date_to + interval '1 day')
            GROUP BY d.id, d.full_name
        ) sub;

    ELSIF p_group_by = 'weekly' THEN
        SELECT COALESCE(jsonb_agg(row_data ORDER BY week_start), '[]'::jsonb) INTO result
        FROM (
            SELECT jsonb_build_object(
                'week_start', date_trunc('week', eam.computed_at)::date,
                'count', COUNT(*),
                'avg_wer', ROUND(COALESCE(AVG(eam.overall_wer), 0)::numeric, 4),
                'avg_entity_error_rate', ROUND(COALESCE(AVG(eam.entity_error_rate), 0)::numeric, 4)
            ) AS row_data, date_trunc('week', eam.computed_at)::date AS week_start
            FROM extraction_accuracy_metrics eam
            JOIN doctors d ON d.id = eam.doctor_id
            WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
              AND (p_doctor_id IS NULL OR eam.doctor_id = p_doctor_id)
              AND (p_date_from IS NULL OR eam.computed_at >= p_date_from)
              AND (p_date_to IS NULL OR eam.computed_at < p_date_to + interval '1 day')
            GROUP BY date_trunc('week', eam.computed_at)::date
        ) sub;

    ELSIF p_group_by = 'monthly' THEN
        SELECT COALESCE(jsonb_agg(row_data ORDER BY month_start), '[]'::jsonb) INTO result
        FROM (
            SELECT jsonb_build_object(
                'month_start', date_trunc('month', eam.computed_at)::date,
                'count', COUNT(*),
                'avg_wer', ROUND(COALESCE(AVG(eam.overall_wer), 0)::numeric, 4),
                'avg_entity_error_rate', ROUND(COALESCE(AVG(eam.entity_error_rate), 0)::numeric, 4)
            ) AS row_data, date_trunc('month', eam.computed_at)::date AS month_start
            FROM extraction_accuracy_metrics eam
            JOIN doctors d ON d.id = eam.doctor_id
            WHERE (p_hospital_id IS NULL OR d.hospital_id = p_hospital_id)
              AND (p_doctor_id IS NULL OR eam.doctor_id = p_doctor_id)
              AND (p_date_from IS NULL OR eam.computed_at >= p_date_from)
              AND (p_date_to IS NULL OR eam.computed_at < p_date_to + interval '1 day')
            GROUP BY date_trunc('month', eam.computed_at)::date
        ) sub;
    END IF;

    RETURN COALESCE(result, '{}'::jsonb);
END;
$$;

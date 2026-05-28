-- Dashboard Summary RPC Function
-- Performs all aggregation in a single optimized SQL query
-- Replaces multiple API calls with one efficient database call

CREATE OR REPLACE FUNCTION get_dashboard_summary(
    p_hospital_id UUID DEFAULT NULL,
    p_doctor_id UUID DEFAULT NULL,
    p_start_date DATE DEFAULT NULL,
    p_end_date DATE DEFAULT NULL,
    p_min_priority_score INT DEFAULT 50
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_doctor_ids UUID[];
    v_result JSON;
BEGIN
    -- Get doctor IDs for hospital filter (done once, reused)
    IF p_hospital_id IS NOT NULL THEN
        SELECT ARRAY_AGG(id) INTO v_doctor_ids
        FROM doctors
        WHERE hospital_id = p_hospital_id AND is_active = TRUE;

        -- If no doctors found, return empty result
        IF v_doctor_ids IS NULL OR array_length(v_doctor_ids, 1) IS NULL THEN
            RETURN json_build_object(
                'total_patients', 0,
                'patients_with_interventions', 0,
                'revenue_potential', 0,
                'by_category', '[]'::json,
                'by_department', '[]'::json,
                'by_doctor', '[]'::json
            );
        END IF;
    END IF;

    -- If specific doctor_id provided, use that
    IF p_doctor_id IS NOT NULL THEN
        v_doctor_ids := ARRAY[p_doctor_id];
    END IF;

    -- Single aggregated query
    WITH filtered_interventions AS (
        -- Base filtered data
        SELECT
            pi.id,
            pi.intervention_code,
            pi.intervention_category,
            pi.priority_score,
            pi.take_up_likelihood,
            pi.revenue_estimate,
            pi.created_at,
            me.patient_id,
            me.doctor_id,
            d.full_name as doctor_name,
            d.specialization
        FROM patient_interventions pi
        INNER JOIN medical_extractions me ON pi.extraction_id = me.id
        INNER JOIN doctors d ON me.doctor_id = d.id
        WHERE pi.priority_score >= p_min_priority_score
          AND pi.created_at >= COALESCE(p_start_date, CURRENT_DATE - INTERVAL '1 year')
          AND pi.created_at < COALESCE(p_end_date, CURRENT_DATE) + INTERVAL '1 day'
          AND (v_doctor_ids IS NULL OR me.doctor_id = ANY(v_doctor_ids))
    ),
    -- Category aggregation
    category_stats AS (
        SELECT
            intervention_category as category,
            COUNT(DISTINCT patient_id) as patient_count,
            COUNT(*) as intervention_count,
            COALESCE(SUM(revenue_estimate), 0) as revenue_potential,
            -- Aggregate risk score: 100 - weighted avg take_up_likelihood
            CASE
                WHEN SUM(priority_score) > 0 THEN
                    100 - (SUM(COALESCE(take_up_likelihood, 50) * priority_score) / SUM(priority_score))
                ELSE 50
            END as aggregate_risk_score
        FROM filtered_interventions
        GROUP BY intervention_category
    ),
    -- Department (specialization) aggregation
    dept_stats AS (
        SELECT
            COALESCE(specialization, 'General') as dept_name,
            intervention_category,
            COUNT(DISTINCT patient_id) as patient_count
        FROM filtered_interventions
        GROUP BY COALESCE(specialization, 'General'), intervention_category
    ),
    dept_summary AS (
        SELECT
            dept_name,
            json_object_agg(intervention_category, patient_count) as by_category,
            SUM(patient_count) as total_at_risk
        FROM dept_stats
        GROUP BY dept_name
    ),
    -- Doctor aggregation
    doctor_stats AS (
        SELECT
            doctor_id,
            doctor_name,
            specialization,
            intervention_category,
            COUNT(DISTINCT patient_id) as patient_count
        FROM filtered_interventions
        GROUP BY doctor_id, doctor_name, specialization, intervention_category
    ),
    doctor_summary AS (
        SELECT
            doctor_id::text as id,
            doctor_name as name,
            specialization,
            json_object_agg(intervention_category, patient_count) as by_category,
            SUM(patient_count) as total_at_risk
        FROM doctor_stats
        GROUP BY doctor_id, doctor_name, specialization
    ),
    -- Overall totals
    totals AS (
        SELECT
            COUNT(DISTINCT patient_id) as patients_with_interventions,
            COALESCE(SUM(revenue_estimate), 0) as revenue_potential
        FROM filtered_interventions
    ),
    -- Total patients (from medical_extractions in the period)
    total_patients AS (
        SELECT COUNT(DISTINCT patient_id) as total
        FROM medical_extractions me
        WHERE me.created_at >= COALESCE(p_start_date, CURRENT_DATE - INTERVAL '1 year')
          AND me.created_at < COALESCE(p_end_date, CURRENT_DATE) + INTERVAL '1 day'
          AND (v_doctor_ids IS NULL OR me.doctor_id = ANY(v_doctor_ids))
    )
    SELECT json_build_object(
        'total_patients', (SELECT total FROM total_patients),
        'patients_with_interventions', (SELECT patients_with_interventions FROM totals),
        'revenue_potential', (SELECT revenue_potential FROM totals),
        'by_category', COALESCE((
            SELECT json_agg(json_build_object(
                'category', category,
                'patient_count', patient_count,
                'intervention_count', intervention_count,
                'revenue_potential', revenue_potential,
                'aggregate_risk_score', ROUND(aggregate_risk_score::numeric, 1),
                'risk_band', CASE
                    WHEN aggregate_risk_score >= 60 THEN 'HIGH'
                    WHEN aggregate_risk_score >= 40 THEN 'MEDIUM'
                    ELSE 'LOW'
                END
            ) ORDER BY patient_count DESC)
            FROM category_stats
        ), '[]'::json),
        'by_department', COALESCE((
            SELECT json_agg(json_build_object(
                'id', dept_name,
                'name', dept_name,
                'by_category', by_category,
                'total_at_risk', total_at_risk
            ) ORDER BY total_at_risk DESC)
            FROM dept_summary
        ), '[]'::json),
        'by_doctor', COALESCE((
            SELECT json_agg(json_build_object(
                'id', id,
                'name', name,
                'specialization', specialization,
                'by_category', by_category,
                'total_at_risk', total_at_risk
            ) ORDER BY total_at_risk DESC)
            FROM doctor_summary
        ), '[]'::json)
    ) INTO v_result;

    RETURN v_result;
END;
$$;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION get_dashboard_summary(UUID, UUID, DATE, DATE, INT) TO authenticated;
GRANT EXECUTE ON FUNCTION get_dashboard_summary(UUID, UUID, DATE, DATE, INT) TO service_role;

COMMENT ON FUNCTION get_dashboard_summary IS 'Optimized dashboard summary aggregation - single query replaces multiple API calls';

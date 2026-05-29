-- Dashboard Summary RPC v2
-- Restructures 7 intervention categories → 5 dashboard metrics
-- Two score-based metrics (Treatment Compliance, Drop-off Risk) using patient_dropoff_risk table
-- Three intervention-based metrics (Health Services, Surgery Candidate, Quality & Safety)
-- Adds by_patient array for per-patient clinical metrics

CREATE OR REPLACE FUNCTION get_dashboard_summary_v2(
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
                'by_doctor', '[]'::json,
                'by_patient', '[]'::json
            );
        END IF;
    END IF;

    -- If specific doctor_id provided, use that
    IF p_doctor_id IS NOT NULL THEN
        v_doctor_ids := ARRAY[p_doctor_id];
    END IF;

    -- Single aggregated query
    WITH filtered_interventions AS (
        -- Base filtered data with category remapping: 7 DB categories → 5 dashboard categories
        SELECT
            pi.id,
            pi.intervention_code,
            pi.intervention_category AS db_category,
            CASE pi.intervention_category
                WHEN 'FOLLOWUP_DUE' THEN 'TREATMENT_COMPLIANCE'
                WHEN 'RETENTION_RISK' THEN 'DROP_OFF_RISK'
                WHEN 'RX_REFILL' THEN 'HEALTH_SERVICES'
                WHEN 'DIAGNOSTICS_DUE' THEN 'HEALTH_SERVICES'
                WHEN 'ALLIED_HEALTH' THEN 'HEALTH_SERVICES'
                WHEN 'OP_TO_IP' THEN 'SURGERY_CANDIDATE'
                WHEN 'QUALITY_RISK' THEN 'QUALITY_RISK'
                ELSE 'QUALITY_RISK'
            END AS dashboard_category,
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
    -- Score-based metrics from patient_dropoff_risk (for TREATMENT_COMPLIANCE and DROP_OFF_RISK)
    dropoff_scores AS (
        SELECT
            AVG(
                CASE pdr.compliance_likelihood
                    WHEN 'Very Low' THEN 10
                    WHEN 'Low' THEN 35
                    WHEN 'Moderate' THEN 65
                    WHEN 'High' THEN 90
                    ELSE 50
                END
            ) AS avg_compliance_score,
            AVG(pdr.dropoff_probability) AS avg_dropoff_probability,
            COUNT(DISTINCT pdr.patient_id) FILTER (WHERE pdr.compliance_likelihood IN ('Very Low', 'Low')) AS low_compliance_count,
            COUNT(DISTINCT pdr.patient_id) FILTER (WHERE pdr.dropoff_probability >= 40) AS high_dropoff_count
        FROM patient_dropoff_risk pdr
        INNER JOIN medical_extractions me ON pdr.extraction_id = me.id
        WHERE pdr.created_at >= COALESCE(p_start_date, CURRENT_DATE - INTERVAL '1 year')
          AND pdr.created_at < COALESCE(p_end_date, CURRENT_DATE) + INTERVAL '1 day'
          AND (v_doctor_ids IS NULL OR me.doctor_id = ANY(v_doctor_ids))
    ),
    -- Category aggregation using 5 dashboard categories
    category_stats AS (
        SELECT
            dashboard_category as category,
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
        GROUP BY dashboard_category
    ),
    -- Enrich category stats with score-based metrics
    enriched_categories AS (
        SELECT
            cs.category,
            cs.patient_count,
            cs.intervention_count,
            cs.revenue_potential,
            cs.aggregate_risk_score,
            CASE
                WHEN cs.aggregate_risk_score >= 60 THEN 'HIGH'
                WHEN cs.aggregate_risk_score >= 40 THEN 'MEDIUM'
                ELSE 'LOW'
            END AS risk_band,
            CASE WHEN cs.category = 'TREATMENT_COMPLIANCE' THEN (SELECT avg_compliance_score FROM dropoff_scores) ELSE NULL END AS avg_compliance_score,
            CASE WHEN cs.category = 'DROP_OFF_RISK' THEN (SELECT avg_dropoff_probability FROM dropoff_scores) ELSE NULL END AS avg_dropoff_probability
        FROM category_stats cs
    ),
    -- Department (specialization) aggregation with 5 categories
    dept_stats AS (
        SELECT
            COALESCE(specialization, 'General') as dept_name,
            dashboard_category,
            COUNT(DISTINCT patient_id) as patient_count
        FROM filtered_interventions
        GROUP BY COALESCE(specialization, 'General'), dashboard_category
    ),
    dept_summary AS (
        SELECT
            dept_name,
            json_object_agg(dashboard_category, patient_count) as by_category,
            SUM(patient_count) as total_at_risk
        FROM dept_stats
        GROUP BY dept_name
    ),
    -- Doctor aggregation with 5 categories
    doctor_stats AS (
        SELECT
            doctor_id,
            doctor_name,
            specialization,
            dashboard_category,
            COUNT(DISTINCT patient_id) as patient_count
        FROM filtered_interventions
        GROUP BY doctor_id, doctor_name, specialization, dashboard_category
    ),
    doctor_summary AS (
        SELECT
            doctor_id::text as id,
            doctor_name as name,
            specialization,
            json_object_agg(dashboard_category, patient_count) as by_category,
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
    ),
    -- Per-patient metrics (by_patient array)
    patient_dropoff AS (
        -- Get latest dropoff risk per patient in the period
        SELECT DISTINCT ON (pdr.patient_id)
            pdr.patient_id,
            pdr.compliance_likelihood,
            pdr.dropoff_probability
        FROM patient_dropoff_risk pdr
        INNER JOIN medical_extractions me ON pdr.extraction_id = me.id
        WHERE pdr.created_at >= COALESCE(p_start_date, CURRENT_DATE - INTERVAL '1 year')
          AND pdr.created_at < COALESCE(p_end_date, CURRENT_DATE) + INTERVAL '1 day'
          AND (v_doctor_ids IS NULL OR me.doctor_id = ANY(v_doctor_ids))
        ORDER BY pdr.patient_id, pdr.created_at DESC
    ),
    patient_intervention_flags AS (
        SELECT
            fi.patient_id,
            BOOL_OR(fi.db_category = 'OP_TO_IP') AS is_surgery_candidate,
            COUNT(*) FILTER (WHERE fi.db_category IN ('RX_REFILL', 'DIAGNOSTICS_DUE', 'ALLIED_HEALTH')) AS health_service_count
        FROM filtered_interventions fi
        GROUP BY fi.patient_id
    ),
    patient_metrics AS (
        SELECT
            COALESCE(pd.patient_id, pif.patient_id) AS patient_id,
            p.full_name AS patient_name,
            p.patient_id AS mrn,
            pd.compliance_likelihood,
            pd.dropoff_probability,
            COALESCE(pif.is_surgery_candidate, FALSE) AS is_surgery_candidate,
            COALESCE(pif.health_service_count, 0) AS health_service_count,
            CASE
                WHEN COALESCE(pif.health_service_count, 0) >= 2 THEN 'High'
                WHEN COALESCE(pif.health_service_count, 0) = 1 THEN 'Medium'
                ELSE 'Low'
            END AS health_service_level
        FROM patient_dropoff pd
        FULL OUTER JOIN patient_intervention_flags pif ON pd.patient_id = pif.patient_id
        LEFT JOIN patients p ON COALESCE(pd.patient_id, pif.patient_id) = p.id
        WHERE pd.patient_id IS NOT NULL OR pif.patient_id IS NOT NULL
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
                'risk_band', risk_band,
                'avg_compliance_score', ROUND(avg_compliance_score::numeric, 1),
                'avg_dropoff_probability', ROUND(avg_dropoff_probability::numeric, 1)
            ) ORDER BY patient_count DESC)
            FROM enriched_categories
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
        ), '[]'::json),
        'by_patient', COALESCE((
            SELECT json_agg(json_build_object(
                'patient_id', patient_id,
                'patient_name', COALESCE(patient_name, 'Unknown'),
                'mrn', mrn,
                'compliance_likelihood', compliance_likelihood,
                'dropoff_probability', dropoff_probability,
                'is_surgery_candidate', is_surgery_candidate,
                'health_service_count', health_service_count,
                'health_service_level', health_service_level
            ) ORDER BY dropoff_probability DESC NULLS LAST)
            FROM patient_metrics
        ), '[]'::json)
    ) INTO v_result;

    RETURN v_result;
END;
$$;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION get_dashboard_summary_v2(UUID, UUID, DATE, DATE, INT) TO authenticated;
GRANT EXECUTE ON FUNCTION get_dashboard_summary_v2(UUID, UUID, DATE, DATE, INT) TO service_role;

COMMENT ON FUNCTION get_dashboard_summary_v2 IS 'Dashboard summary v2 - 5 dashboard categories with score-based metrics from patient_dropoff_risk';

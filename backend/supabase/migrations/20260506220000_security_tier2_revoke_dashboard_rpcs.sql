-- Tier 2 fix #2: revoke anon/authenticated EXECUTE on 12 SECURITY DEFINER
-- analytics RPCs. These are owner-elevation functions intended for backend
-- consumption only — frontend audit (2026-05-06) confirmed no direct calls.
-- The backend uses service_role which has its own grant chain and is
-- unaffected by these revokes (service_role retains EXECUTE).
--
-- Same pattern as exec_sql in 20260506190000. Reversible by re-granting
-- EXECUTE if any consumer turns out to need it.

REVOKE EXECUTE ON FUNCTION public.get_accuracy_metrics(
  p_hospital_id uuid,
  p_doctor_id uuid,
  p_date_from timestamp with time zone,
  p_date_to timestamp with time zone,
  p_group_by text
) FROM anon, authenticated, PUBLIC;

REVOKE EXECUTE ON FUNCTION public.get_ai_acceptance_metrics(
  p_hospital_id uuid,
  p_doctor_id uuid,
  p_date_from timestamp with time zone,
  p_date_to timestamp with time zone,
  p_group_by text
) FROM anon, authenticated, PUBLIC;

REVOKE EXECUTE ON FUNCTION public.get_avg_pipeline_timing(
  p_hospital_id uuid,
  p_doctor_id uuid,
  p_date_from timestamp with time zone,
  p_date_to timestamp with time zone
) FROM anon, authenticated, PUBLIC;

REVOKE EXECUTE ON FUNCTION public.get_dashboard_summary(
  p_hospital_id uuid,
  p_doctor_id uuid,
  p_start_date date,
  p_end_date date,
  p_min_priority_score integer
) FROM anon, authenticated, PUBLIC;

REVOKE EXECUTE ON FUNCTION public.get_dashboard_summary_v2(
  p_hospital_id uuid,
  p_doctor_id uuid,
  p_start_date date,
  p_end_date date,
  p_min_priority_score integer
) FROM anon, authenticated, PUBLIC;

REVOKE EXECUTE ON FUNCTION public.get_doctor_feedback_patterns(p_doctor_id uuid)
  FROM anon, authenticated, PUBLIC;

REVOKE EXECUTE ON FUNCTION public.get_doctor_preference_patterns(p_doctor_id uuid)
  FROM anon, authenticated, PUBLIC;

REVOKE EXECUTE ON FUNCTION public.get_doctor_rejection_patterns(p_doctor_id uuid)
  FROM anon, authenticated, PUBLIC;

REVOKE EXECUTE ON FUNCTION public.get_notes_per_doctor_per_day(
  p_hospital_id uuid,
  p_doctor_id uuid,
  p_date_from timestamp with time zone,
  p_date_to timestamp with time zone
) FROM anon, authenticated, PUBLIC;

REVOKE EXECUTE ON FUNCTION public.get_template_by_code_unified(
  p_doctor_id uuid,
  p_template_code text
) FROM anon, authenticated, PUBLIC;

REVOKE EXECUTE ON FUNCTION public.get_usage_summary(
  p_group_by text,
  p_date_from timestamp with time zone,
  p_date_to timestamp with time zone,
  p_api_client_id uuid,
  p_hospital_id uuid,
  p_doctor_id uuid,
  p_limit integer,
  p_offset integer
) FROM anon, authenticated, PUBLIC;

REVOKE EXECUTE ON FUNCTION public.get_usage_totals(
  p_date_from timestamp with time zone,
  p_date_to timestamp with time zone,
  p_api_client_id uuid,
  p_hospital_id uuid,
  p_doctor_id uuid
) FROM anon, authenticated, PUBLIC;

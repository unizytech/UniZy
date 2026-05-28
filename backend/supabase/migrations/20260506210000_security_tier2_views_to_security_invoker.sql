-- Tier 2 fix part of "fix #1": flip the 15 SECURITY DEFINER views to
-- SECURITY INVOKER. PG 15+ exposes this as the `security_invoker` reloption,
-- so we can flip in place without dropping or recreating — preserves the view
-- bodies, GRANTs, and dependencies (intervention_summary_stats depends on
-- intervention_analytics; the dependency stays intact because both flip in
-- the same migration without DROPs).
--
-- After this, queries against these views run with the QUERYING user's
-- permissions / RLS context instead of the owner's (postgres). For our setup:
--   * Backend uses service_role (BYPASSRLS) — unaffected.
--   * Frontend goes through backend api (no direct view calls — audit 2026-05-06).
--   * Anon / authenticated REST callers would no longer see rows their RLS
--     denies — which is the intended fix.
--
-- Rollback: ALTER VIEW <name> SET (security_invoker = false);

ALTER VIEW public.current_extraction_state         SET (security_invoker = true);
ALTER VIEW public.extraction_segment_comparison    SET (security_invoker = true);
ALTER VIEW public.intervention_analytics           SET (security_invoker = true);
ALTER VIEW public.intervention_summary_stats       SET (security_invoker = true);
ALTER VIEW public.triage_doctor_stats              SET (security_invoker = true);
ALTER VIEW public.triage_suggestion_analytics      SET (security_invoker = true);
ALTER VIEW public.v_api_client_usage_summary       SET (security_invoker = true);
ALTER VIEW public.v_consultation_type_summary      SET (security_invoker = true);
ALTER VIEW public.v_daily_usage_summary            SET (security_invoker = true);
ALTER VIEW public.v_doctor_usage_summary           SET (security_invoker = true);
ALTER VIEW public.v_doctor_usage_summary_v2        SET (security_invoker = true);
ALTER VIEW public.v_hospital_accuracy_metrics      SET (security_invoker = true);
ALTER VIEW public.v_hospital_usage_summary         SET (security_invoker = true);
ALTER VIEW public.v_session_usage_summary          SET (security_invoker = true);
ALTER VIEW public.v_template_configurations        SET (security_invoker = true);

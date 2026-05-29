-- Tier 1 security hardening from Supabase advisor.
--
-- Two changes:
--
-- 1. exec_sql is SECURITY DEFINER and was callable by anon AND authenticated
--    roles. That means any signed-in (or unauthenticated, depending on policy)
--    Supabase client could run arbitrary SQL with the function owner's rights.
--    We revoke EXECUTE from anon, authenticated, and PUBLIC. The backend uses
--    the service_role key, which bypasses these grants and is unaffected.
--    Frontend audit (2026-05-06) confirmed no direct frontend calls to exec_sql.
--
-- 2. 77 functions in public have a mutable search_path. We set
--    `search_path = public, pg_temp` on each so the function resolves names
--    deterministically and isn't influenced by the caller's session settings.
--    This is a hardening change, not a behavior change — every flagged function
--    already references unqualified objects that live in `public`.
--
-- Both changes are safe for the recording / transcription / extraction /
-- reprocess / webhooks pipelines (backend uses service_role).

-- ============================================================================
-- 1. Revoke exec_sql from non-service roles
-- ============================================================================

REVOKE EXECUTE ON FUNCTION public.exec_sql(text) FROM anon, authenticated, PUBLIC;

-- ============================================================================
-- 2. Set explicit search_path on flagged functions
-- ============================================================================

DO $migration$
DECLARE
    func_rec RECORD;
    target_funcs TEXT[] := ARRAY[
        'activate_config_for_consultation_type_rpc',
        'assemble_combined_emotion_prompt',
        'assemble_system_prompt_rpc',
        'can_doctor_access_template',
        'check_rate_limit',
        'cleanup_chunks_after_processing',
        'cleanup_old_realtime_responses',
        'cleanup_old_sessions',
        'compute_all_hospital_patterns',
        'compute_doctor_practice_style',
        'compute_hospital_specialty_patterns',
        'copy_hospital_investigation_to_doctor_rpc',
        'copy_hospital_medicine_to_doctor_rpc',
        'exec_sql',
        'get_accuracy_metrics',
        'get_active_system_prompt_rpc',
        'get_active_template_for_doctor',
        'get_ai_acceptance_metrics',
        'get_avg_pipeline_timing',
        'get_client_request_count_last_hour',
        'get_comorbidity_pathway',
        'get_condition_chunks',
        'get_dashboard_summary',
        'get_dashboard_summary_v2',
        'get_doctor_ehr_config',
        'get_doctor_feedback_patterns',
        'get_doctor_practice_style',
        'get_doctor_preference_patterns',
        'get_doctor_rejection_patterns',
        'get_doctor_segment_configuration',
        'get_enabled_triage_layers',
        'get_hospital_default_ehr_type_id',
        'get_intervention_stats_by_doctor',
        'get_investigation_feedback_history_rpc',
        'get_medicine_feedback_history_rpc',
        'get_merge_lineage',
        'get_notes_per_doctor_per_day',
        'get_patient_extraction_timeline',
        'get_patient_triage_context',
        'get_peer_comparison',
        'get_pending_feedback_count_rpc',
        'get_pending_investigation_feedback_count_rpc',
        'get_processing_mode_config',
        'get_red_flags_by_specialty',
        'get_session_with_job',
        'get_template_by_code_unified',
        'get_template_performance_stats',
        'get_usage_summary',
        'get_usage_totals',
        'mark_missed_followups',
        'match_clinical_guidelines',
        'notify_emotion_prompt_change',
        'prevent_audit_log_deletion',
        'record_template_performance',
        'save_patient_interventions',
        'save_triage_suggestions',
        'search_by_icd_code',
        'search_clinical_chunks_hybrid',
        'search_guidelines_by_keywords',
        'search_investigations_rpc',
        'search_medicines_rpc',
        'update_client_last_used',
        'update_customers_updated_at',
        'update_doctor_templates_updated_at',
        'update_extraction_metrics_rpc',
        'update_financial_extractions_updated_at',
        'update_financial_intervention_outcomes_updated_at',
        'update_financial_interventions_updated_at',
        'update_followup_tracking_updated_at',
        'update_hospital_ehr_updated_at',
        'update_intervention_outcomes_updated_at',
        'update_intervention_updated_at',
        'update_job_progress',
        'update_triage_layer_config',
        'update_updated_at_column',
        'validate_merge_sources',
        'validate_segment_configuration'
    ];
BEGIN
    FOR func_rec IN
        SELECT
            p.proname AS name,
            pg_get_function_identity_arguments(p.oid) AS args
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND p.proname = ANY(target_funcs)
    LOOP
        EXECUTE format(
            'ALTER FUNCTION public.%I(%s) SET search_path = public, pg_temp',
            func_rec.name,
            func_rec.args
        );
    END LOOP;
END
$migration$;

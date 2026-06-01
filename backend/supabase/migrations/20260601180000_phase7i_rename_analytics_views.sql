-- Phase 7I: clean the analytics views — rename the views whose NAME carries an entity token and
-- fix the output column ALIASES that still used old vocab (e.g. AS doctor_id, AS hospital_name).
-- The view bodies already reference the renamed base tables/columns (auto-followed); only the
-- output aliases (and 5 view names) needed cleaning. security_invoker is preserved.
--
-- NOTE: this also fixes a latent bug — triage_doctor_stats exposed a column "doctor_id" while the
-- application (after Phase 7D) queries it via .eq("counsellor_id"); the recreated view exposes
-- counsellor_id so the query works.

begin;

drop view if exists public.intervention_summary_stats;
drop view if exists public.intervention_analytics;
create view public.intervention_analytics with (security_invoker = true) as
 select pi.id, pi.extraction_id, pi.intervention_code, pi.intervention_id,
    idef.intervention_name, idef.category as intervention_category,
    pi.priority_level, pi.priority_score, pi.trigger_reason, pi.analysis_mode,
    pi.recommendation_rank, pi.is_top_recommendation, pi.status, pi.outcome,
    pi.created_at as recommended_at, pi.status_updated_at,
    me.session_id, me.counsellor_id, me.consultation_type_id,
    me.created_at as extraction_created_at,
    rs.student_id, rs.template_code,
    d.full_name as counsellor_name, d.specialization as counsellor_specialty,
    ct.type_code as consultation_type_code, ct.type_name as consultation_type_name
   from student_interventions pi
     join intervention_definitions idef on pi.intervention_id = idef.id
     join medical_extractions me on pi.extraction_id = me.id
     left join recording_sessions rs on me.session_id = rs.id
     left join counsellors d on me.counsellor_id = d.id
     left join consultation_types ct on me.consultation_type_id = ct.id;

create view public.intervention_summary_stats with (security_invoker = true) as
 select intervention_code, intervention_name, intervention_category, priority_level,
    count(*) as total_recommendations,
    count(*) filter (where is_top_recommendation) as top_3_recommendations,
    count(*) filter (where status = 'completed'::text) as completed_count,
    count(*) filter (where status = 'declined'::text) as declined_count,
    count(*) filter (where status = 'in_progress'::text) as in_progress_count,
    count(*) filter (where outcome = 'effective'::text) as effective_count,
    count(*) filter (where outcome = 'partially_effective'::text) as partial_effective_count,
    count(*) filter (where outcome = 'not_effective'::text) as not_effective_count,
    case when count(*) filter (where outcome is not null) > 0 then round(count(*) filter (where outcome = 'effective'::text)::numeric / count(*) filter (where outcome is not null)::numeric * 100::numeric, 1) else null::numeric end as effectiveness_rate_pct,
    min(recommended_at) as first_recommendation,
    max(recommended_at) as latest_recommendation
   from intervention_analytics ia
  group by intervention_code, intervention_name, intervention_category, priority_level
  order by (count(*)) desc;

drop view if exists public.triage_doctor_stats;
create view public.triage_counsellor_stats with (security_invoker = true) as
 select d.id as counsellor_id, d.full_name, d.specialization, d.school_id,
    count(distinct tsl.extraction_id) as extractions_with_suggestions,
    count(tsl.id) as total_suggestions,
    count(tf.id) as total_feedback_given,
    count(tf.id) filter (where tf.feedback_type = 'accepted'::text) as accepted_count,
    count(tf.id) filter (where tf.feedback_type = 'rejected'::text) as rejected_count,
    count(tf.id) filter (where tf.feedback_type = 'modified'::text) as modified_count,
    case when count(tf.id) > 0 then round(count(tf.id) filter (where tf.feedback_type = 'accepted'::text)::numeric / count(tf.id)::numeric * 100::numeric, 1) else null::numeric end as acceptance_rate_pct,
    max(tsl.created_at) as last_suggestion_at
   from counsellors d
     left join triage_suggestion_log tsl on d.id = tsl.counsellor_id
     left join triage_feedback tf on tsl.id = tf.suggestion_id
  where d.is_active = true
  group by d.id, d.full_name, d.specialization, d.school_id;

drop view if exists public.triage_suggestion_analytics;
create view public.triage_suggestion_analytics with (security_invoker = true) as
 select tsl.id, tsl.extraction_id, tsl.counsellor_id, tsl.suggestion_category,
    tsl.suggestion_type, tsl.suggestion_text, tsl.source_layer, tsl.confidence_score,
    tsl.priority_rank, tsl.created_at as suggested_at,
    tf.id as feedback_id, tf.feedback_type, tf.rejection_reason, tf.feedback_at,
    me.session_id, me.consultation_type_id, rs.student_id,
    d.full_name as counsellor_name, d.specialization as counsellor_specialty, d.school_id
   from triage_suggestion_log tsl
     left join triage_feedback tf on tsl.id = tf.suggestion_id
     left join medical_extractions me on tsl.extraction_id = me.id
     left join recording_sessions rs on me.session_id = rs.id
     left join counsellors d on tsl.counsellor_id = d.id;

drop view if exists public.v_doctor_usage_summary;
create view public.v_counsellor_usage_summary with (security_invoker = true) as
 select l.counsellor_id, d.full_name as counsellor_name, d.specialization,
    count(*) as total_calls, sum(l.total_cost_usd) as total_cost_usd,
    sum(l.cache_savings_usd) as total_cache_savings_usd, avg(l.cache_hit_ratio) as avg_cache_hit_ratio,
    count(distinct l.session_id) as total_sessions,
    sum(l.total_cost_usd) / nullif(count(distinct l.session_id), 0)::numeric as avg_cost_per_session
   from llm_usage_log l
     left join counsellors d on l.counsellor_id = d.id
  where l.counsellor_id is not null
  group by l.counsellor_id, d.full_name, d.specialization;

drop view if exists public.v_doctor_usage_summary_v2;
create view public.v_counsellor_usage_summary_v2 with (security_invoker = true) as
 select d.id as counsellor_id, d.full_name as counsellor_name, d.specialization,
    d.school_id, h.school_name,
    count(distinct l.id) as total_api_calls, count(distinct l.session_id) as total_sessions,
    coalesce(sum(l.total_cost_usd), 0::numeric) as total_cost_usd,
    coalesce(sum(l.cache_savings_usd), 0::numeric) as total_cache_savings_usd,
    coalesce(sum(l.prompt_token_count), 0::bigint) as total_input_tokens,
    coalesce(sum(l.candidates_token_count), 0::bigint) as total_output_tokens,
    coalesce(sum(l.cached_content_token_count), 0::bigint) as total_cached_tokens,
    coalesce(( select sum(rs.total_duration_seconds) / 3600.0 from recording_sessions rs where rs.counsellor_id = d.id), 0::numeric) as total_recording_hours,
    coalesce(sum(case when l.call_type::text = 'transcription'::text then l.audio_duration_seconds else 0::numeric end) / 3600.0, 0::numeric) as total_transcription_hours,
    avg(case when l.cache_hit then l.cache_hit_ratio else null::numeric end) as avg_cache_hit_ratio,
    count(case when l.response_status::text = 'error'::text then 1 else null::integer end) as error_count,
    case when count(distinct l.session_id) > 0 then coalesce(sum(l.total_cost_usd), 0::numeric) / count(distinct l.session_id)::numeric else 0::numeric end as avg_cost_per_session,
    min(l.created_at) as first_usage_at, max(l.created_at) as last_usage_at
   from counsellors d
     left join llm_usage_log l on l.counsellor_id = d.id
     left join schools h on d.school_id = h.id
  group by d.id, d.full_name, d.specialization, d.school_id, h.school_name;

drop view if exists public.v_hospital_accuracy_metrics;
create view public.v_school_accuracy_metrics with (security_invoker = true) as
 select d.school_id, d.id as counsellor_id, d.full_name as counsellor_name,
    count(*) as total_extractions,
    round(avg(eam.overall_wer), 4) as avg_wer,
    round(percentile_cont(0.5::double precision) within group (order by (eam.overall_wer::double precision))::numeric, 4) as median_wer,
    round(avg(eam.entity_error_rate), 4) as avg_entity_error_rate,
    round(avg(eam.segments_modified), 1) as avg_segments_modified,
    round(avg(eam.segments_unchanged), 1) as avg_segments_unchanged,
    round(avg(eam.counsellor_additions_count), 1) as avg_counsellor_additions,
    max(eam.computed_at) as last_computed_at
   from extraction_accuracy_metrics eam
     join counsellors d on d.id = eam.counsellor_id
  group by d.school_id, d.id, d.full_name;

drop view if exists public.v_hospital_usage_summary;
create view public.v_school_usage_summary with (security_invoker = true) as
 select h.id as school_id, h.school_name, h.school_code,
    count(distinct l.id) as total_api_calls, count(distinct l.session_id) as total_sessions,
    count(distinct l.counsellor_id) as unique_counsellors,
    count(distinct l.api_client_id) as unique_api_clients,
    coalesce(sum(l.total_cost_usd), 0::numeric) as total_cost_usd,
    coalesce(sum(l.cache_savings_usd), 0::numeric) as total_cache_savings_usd,
    coalesce(sum(l.prompt_token_count), 0::bigint) as total_input_tokens,
    coalesce(sum(l.candidates_token_count), 0::bigint) as total_output_tokens,
    coalesce(sum(l.cached_content_token_count), 0::bigint) as total_cached_tokens,
    coalesce(( select sum(rs.total_duration_seconds) / 3600.0 from recording_sessions rs join counsellors d_1 on rs.counsellor_id = d_1.id where d_1.school_id = h.id), 0::numeric) as total_recording_hours,
    coalesce(sum(case when l.call_type::text = 'transcription'::text then l.audio_duration_seconds else 0::numeric end) / 3600.0, 0::numeric) as total_transcription_hours,
    avg(case when l.cache_hit then l.cache_hit_ratio else null::numeric end) as avg_cache_hit_ratio,
    count(case when l.response_status::text = 'error'::text then 1 else null::integer end) as error_count,
    min(l.created_at) as first_usage_at, max(l.created_at) as last_usage_at
   from schools h
     left join counsellors d on d.school_id = h.id
     left join llm_usage_log l on l.counsellor_id = d.id
  group by h.id, h.school_name, h.school_code;

notify pgrst, 'reload schema';

commit;

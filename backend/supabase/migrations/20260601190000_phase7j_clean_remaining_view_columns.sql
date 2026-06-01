-- Phase 7J: clean the last entity-vocab output aliases on two analytics/config views
-- (v_api_client_usage_summary, v_template_configurations). Names already neutral; only the
-- hospital_id / hospital_name aliases remained. No dependents. security_invoker preserved.

begin;

drop view if exists public.v_api_client_usage_summary;
create view public.v_api_client_usage_summary with (security_invoker = true) as
 select ac.id as api_client_id, ac.client_name, ac.client_type,
    ac.school_id, h.school_name,
    count(distinct l.id) as total_api_calls, count(distinct l.session_id) as total_sessions,
    coalesce(sum(l.total_cost_usd), 0::numeric) as total_cost_usd,
    coalesce(sum(l.cache_savings_usd), 0::numeric) as total_cache_savings_usd,
    coalesce(sum(l.prompt_token_count), 0::bigint) as total_input_tokens,
    coalesce(sum(l.candidates_token_count), 0::bigint) as total_output_tokens,
    coalesce(sum(l.cached_content_token_count), 0::bigint) as total_cached_tokens,
    coalesce(( select sum(rs.total_duration_seconds) / 3600.0 from recording_sessions rs
          where rs.id in ( select distinct llm_usage_log.session_id from llm_usage_log where llm_usage_log.api_client_id = ac.id)), 0::numeric) as total_recording_hours,
    coalesce(sum(case when l.call_type::text = 'transcription'::text then l.audio_duration_seconds else 0::numeric end) / 3600.0, 0::numeric) as total_transcription_hours,
    avg(case when l.cache_hit then l.cache_hit_ratio else null::numeric end) as avg_cache_hit_ratio,
    count(case when l.response_status::text = 'error'::text then 1 else null::integer end) as error_count,
    min(l.created_at) as first_usage_at, max(l.created_at) as last_usage_at
   from api_clients ac
     left join llm_usage_log l on l.api_client_id = ac.id
     left join schools h on ac.school_id = h.id
  group by ac.id, ac.client_name, ac.client_type, ac.school_id, h.school_name;

drop view if exists public.v_template_configurations;
create view public.v_template_configurations with (security_invoker = true) as
 select t.id as template_id, t.template_code, t.template_name,
    t.description as template_description, t.consultation_type_id, t.specialization,
    t.school_id, t.is_active,
    tsc.id as config_id, tsc.segment_code, tsc.display_order, tsc.category,
    tsc.brevity_level, tsc.terminology_style,
    sd.segment_name, sd.description as segment_description, sd.default_category,
    sd.default_brevity_level, sd.default_terminology_style
   from templates t
     left join template_segments tsc on t.id = tsc.template_id
     left join segment_definitions sd on tsc.segment_code::text = sd.segment_code::text
  where t.is_active = true
  order by t.template_code, tsc.display_order;

notify pgrst, 'reload schema';

commit;

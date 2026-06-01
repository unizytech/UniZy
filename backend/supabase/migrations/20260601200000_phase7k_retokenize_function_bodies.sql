-- Phase 7K: retokenize stored function (RPC) BODIES to the school vocabulary.
--
-- The 7A-7J migrations renamed columns/tables, but Postgres does NOT auto-update function bodies
-- on a rename, so any RPC whose body referenced doctor_id / hospital_id / doctor_templates / etc.
-- now errors at runtime (e.g. "column t.doctor_id does not exist"). This migration rebuilds each
-- affected function from pg_get_functiondef() with WORD-BOUNDARY (\m..\M) token replacement, so:
--   * column/table/view references are updated to the new names,
--   * function NAMES and parameter names like p_doctor_id are preserved (word boundary protects
--     them), keeping the .rpc("name", {...}) contract intact,
--   * it is idempotent (only functions still containing old tokens are processed), so it is safe
--     to run on main AFTER 7A-7J have renamed the columns there.

do $$
declare fn record; r record; newdef text;
begin
  for fn in
    select p.oid, pg_get_functiondef(p.oid) as def,
           p.proname, pg_get_function_identity_arguments(p.oid) as idargs
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.prosrc ~ '(\mdoctor_id\M|\mhospital_id\M|\mpatient_id\M|\mnurse_id\M|\mdoctor_ids\M|\mhospital_name\M|\mhospital_code\M|\mdoctors\M|\mhospitals\M|\mpatients\M|\mnurses\M|doctor_templates|doctor_medicines|doctor_investigations|doctor_layer_preferences|doctor_practice_styles|doctor_doctor_patients|doctor_segment_configurations_backup_014|nurse_doctors|nurse_templates|hospital_ehr|hospital_intervention_pricing|hospital_investigation_lists|hospital_medicine_lists|hospital_specialty_patterns|patient_sharing|patient_dropoff_risk|patient_interventions|triage_doctor_stats|v_doctor_usage_summary|v_hospital_accuracy_metrics|v_hospital_usage_summary|allowed_doctor_ids|patient_education|patient_signals|visible_to_doctors|visible_to_hospitals|enable_doctor_practice_layer|enable_hospital_intelligence_layer|weight_doctor_practice|weight_hospital_intelligence|doctor_additions_count|total_words_doctor_edit|doctor_count|matched_hospital_investigation_id|matched_hospital_medicine_id|allow_cross_doctor_search|patient_identifier|total_doctors|total_hospitals|patient_context_applied|linked_doctor_id|source_doctor_id|target_doctor_id)'
  loop
    newdef := fn.def;
    for r in select * from (values
      -- distinct / compound columns first (longest), word-boundary makes order non-critical
      ('allowed_doctor_ids','allowed_counsellor_ids'),
      ('enable_doctor_practice_layer','enable_counsellor_practice_layer'),
      ('enable_hospital_intelligence_layer','enable_school_intelligence_layer'),
      ('weight_doctor_practice','weight_counsellor_practice'),
      ('weight_hospital_intelligence','weight_school_intelligence'),
      ('doctor_additions_count','counsellor_additions_count'),
      ('total_words_doctor_edit','total_words_counsellor_edit'),
      ('matched_hospital_investigation_id','matched_school_investigation_id'),
      ('matched_hospital_medicine_id','matched_school_medicine_id'),
      ('allow_cross_doctor_search','allow_cross_counsellor_search'),
      ('patient_context_applied','student_context_applied'),
      ('patient_education','student_education'),
      ('patient_signals','student_signals'),
      ('patient_identifier','student_identifier'),
      ('visible_to_doctors','visible_to_counsellors'),
      ('visible_to_hospitals','visible_to_schools'),
      ('total_doctors','total_counsellors'),
      ('total_hospitals','total_schools'),
      ('doctor_count','counsellor_count'),
      ('linked_doctor_id','linked_counsellor_id'),
      ('source_doctor_id','source_counsellor_id'),
      ('target_doctor_id','target_counsellor_id'),
      -- view names
      ('triage_doctor_stats','triage_counsellor_stats'),
      ('v_doctor_usage_summary_v2','v_counsellor_usage_summary_v2'),
      ('v_doctor_usage_summary','v_counsellor_usage_summary'),
      ('v_hospital_accuracy_metrics','v_school_accuracy_metrics'),
      ('v_hospital_usage_summary','v_school_usage_summary'),
      -- junction / child tables
      ('doctor_templates','counsellor_templates'),
      ('doctor_medicines','counsellor_medicines'),
      ('doctor_investigations','counsellor_investigations'),
      ('doctor_layer_preferences','counsellor_layer_preferences'),
      ('doctor_practice_styles','counsellor_practice_styles'),
      ('doctor_doctor_patients','counsellor_counsellor_students'),
      ('doctor_segment_configurations_backup_014','counsellor_segment_configurations_backup_014'),
      ('nurse_doctors','assistant_counsellors'),
      ('nurse_templates','assistant_templates'),
      ('hospital_ehr','school_ehr'),
      ('hospital_intervention_pricing','school_intervention_pricing'),
      ('hospital_investigation_lists','school_investigation_lists'),
      ('hospital_medicine_lists','school_medicine_lists'),
      ('hospital_specialty_patterns','school_specialty_patterns'),
      ('patient_sharing','student_sharing'),
      ('patient_dropoff_risk','student_dropoff_risk'),
      ('patient_interventions','student_interventions'),
      -- FK / id columns
      ('doctor_ids','counsellor_ids'),
      ('doctor_id','counsellor_id'),
      ('patient_id','student_id'),
      ('hospital_id','school_id'),
      ('nurse_id','assistant_id'),
      ('hospital_name','school_name'),
      ('hospital_code','school_code'),
      -- entity tables (bare; word boundary protects junction names)
      ('doctors','counsellors'),
      ('hospitals','schools'),
      ('patients','students'),
      ('nurses','assistants')
    ) as t(o,n) loop
      newdef := regexp_replace(newdef, '\m' || r.o || '\M', r.n, 'g');
    end loop;
    -- CREATE OR REPLACE works when only the body changed; if a RETURNS/OUT column was renamed
    -- (return-type change), fall back to DROP + CREATE.
    begin
      execute newdef;
    exception when others then
      execute 'drop function if exists public.' || quote_ident(fn.proname) || '(' || fn.idargs || ')';
      execute newdef;
    end;
  end loop;
end $$;

-- Ensure the app roles retain EXECUTE on any function that was DROP+CREATEd.
grant execute on all functions in schema public to anon, authenticated, service_role;

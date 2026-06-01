-- Phase 7L: rename stored function NAMES and trigger NAMES to the school vocabulary, and fix
-- internal (plpgsql) call sites that reference the renamed functions by name. Function PARAMETER
-- names (p_doctor_id, ...) are intentionally left unchanged so the existing .rpc("fn", {p_..})
-- kwargs keep matching. Backend .rpc("old_name") call strings are updated in the same change set.

do $$
declare m record; f record; def text;
begin
  -- Step 1: rename the function names (ALTER ... RENAME; triggers referencing trigger-functions
  -- by OID auto-follow; grants preserved).
  for m in select * from (values
    ('can_doctor_access_template','can_counsellor_access_template'),
    ('compute_all_hospital_patterns','compute_all_school_patterns'),
    ('compute_doctor_practice_style','compute_counsellor_practice_style'),
    ('compute_hospital_specialty_patterns','compute_school_specialty_patterns'),
    ('copy_hospital_investigation_to_doctor_rpc','copy_school_investigation_to_counsellor_rpc'),
    ('copy_hospital_medicine_to_doctor_rpc','copy_school_medicine_to_counsellor_rpc'),
    ('get_active_template_for_doctor','get_active_template_for_counsellor'),
    ('get_doctor_ehr_config','get_counsellor_ehr_config'),
    ('get_doctor_feedback_patterns','get_counsellor_feedback_patterns'),
    ('get_doctor_practice_style','get_counsellor_practice_style'),
    ('get_doctor_preference_patterns','get_counsellor_preference_patterns'),
    ('get_doctor_rejection_patterns','get_counsellor_rejection_patterns'),
    ('get_doctor_segment_configuration','get_counsellor_segment_configuration'),
    ('get_hospital_default_ehr_type_id','get_school_default_ehr_type_id'),
    ('get_intervention_stats_by_doctor','get_intervention_stats_by_counsellor'),
    ('get_notes_per_doctor_per_day','get_notes_per_counsellor_per_day'),
    ('get_patient_extraction_timeline','get_student_extraction_timeline'),
    ('get_patient_triage_context','get_student_triage_context'),
    ('save_patient_interventions','save_student_interventions'),
    ('update_doctor_templates_updated_at','update_counsellor_templates_updated_at'),
    ('update_hospital_ehr_updated_at','update_school_ehr_updated_at')
  ) as t(o,n) loop
    for f in select pg_get_function_identity_arguments(p.oid) as args
             from pg_proc p join pg_namespace ns on ns.oid=p.pronamespace
             where ns.nspname='public' and p.proname = m.o loop
      execute format('alter function public.%I(%s) rename to %I', m.o, f.args, m.n);
    end loop;
  end loop;

  -- Step 2: recreate any function whose BODY still references a renamed function by its old name.
  for f in select p.oid, pg_get_functiondef(p.oid) as def
           from pg_proc p join pg_namespace ns on ns.oid=p.pronamespace
           where ns.nspname='public'
             and p.prosrc ~ '(can_doctor_access_template|compute_all_hospital_patterns|compute_doctor_practice_style|compute_hospital_specialty_patterns|copy_hospital_investigation_to_doctor_rpc|copy_hospital_medicine_to_doctor_rpc|get_active_template_for_doctor|get_doctor_ehr_config|get_doctor_feedback_patterns|get_doctor_practice_style|get_doctor_preference_patterns|get_doctor_rejection_patterns|get_doctor_segment_configuration|get_hospital_default_ehr_type_id|get_intervention_stats_by_doctor|get_notes_per_doctor_per_day|get_patient_extraction_timeline|get_patient_triage_context|save_patient_interventions|update_doctor_templates_updated_at|update_hospital_ehr_updated_at)'
  loop
    def := f.def;
    for m in select * from (values
      ('can_doctor_access_template','can_counsellor_access_template'),
      ('compute_all_hospital_patterns','compute_all_school_patterns'),
      ('compute_doctor_practice_style','compute_counsellor_practice_style'),
      ('compute_hospital_specialty_patterns','compute_school_specialty_patterns'),
      ('copy_hospital_investigation_to_doctor_rpc','copy_school_investigation_to_counsellor_rpc'),
      ('copy_hospital_medicine_to_doctor_rpc','copy_school_medicine_to_counsellor_rpc'),
      ('get_active_template_for_doctor','get_active_template_for_counsellor'),
      ('get_doctor_ehr_config','get_counsellor_ehr_config'),
      ('get_doctor_feedback_patterns','get_counsellor_feedback_patterns'),
      ('get_doctor_practice_style','get_counsellor_practice_style'),
      ('get_doctor_preference_patterns','get_counsellor_preference_patterns'),
      ('get_doctor_rejection_patterns','get_counsellor_rejection_patterns'),
      ('get_doctor_segment_configuration','get_counsellor_segment_configuration'),
      ('get_hospital_default_ehr_type_id','get_school_default_ehr_type_id'),
      ('get_intervention_stats_by_doctor','get_intervention_stats_by_counsellor'),
      ('get_notes_per_doctor_per_day','get_notes_per_counsellor_per_day'),
      ('get_patient_extraction_timeline','get_student_extraction_timeline'),
      ('get_patient_triage_context','get_student_triage_context'),
      ('save_patient_interventions','save_student_interventions'),
      ('update_doctor_templates_updated_at','update_counsellor_templates_updated_at'),
      ('update_hospital_ehr_updated_at','update_school_ehr_updated_at')
    ) as t(o,n) loop
      def := replace(def, m.o, m.n);
    end loop;
    execute def;
  end loop;
end $$;

-- Step 3: rename triggers (name only; ON the already-renamed tables).
alter trigger doctor_layer_preferences_updated_at on public.counsellor_layer_preferences rename to counsellor_layer_preferences_updated_at;
alter trigger doctor_practice_styles_updated_at on public.counsellor_practice_styles rename to counsellor_practice_styles_updated_at;
alter trigger hospital_ehr_updated_at on public.school_ehr rename to school_ehr_updated_at;
alter trigger hospital_specialty_patterns_updated_at on public.school_specialty_patterns rename to school_specialty_patterns_updated_at;
alter trigger patient_sharing_updated_at on public.student_sharing rename to student_sharing_updated_at;
alter trigger trigger_patient_interventions_updated_at on public.student_interventions rename to trigger_student_interventions_updated_at;
alter trigger trigger_update_doctor_templates_timestamp on public.counsellor_templates rename to trigger_update_counsellor_templates_timestamp;
alter trigger update_doctor_investigations_updated_at on public.counsellor_investigations rename to update_counsellor_investigations_updated_at;
alter trigger update_doctor_medicines_updated_at on public.counsellor_medicines rename to update_counsellor_medicines_updated_at;
alter trigger update_doctors_updated_at on public.counsellors rename to update_counsellors_updated_at;
alter trigger update_hospital_investigation_lists_updated_at on public.school_investigation_lists rename to update_school_investigation_lists_updated_at;
alter trigger update_hospital_medicine_lists_updated_at on public.school_medicine_lists rename to update_school_medicine_lists_updated_at;
alter trigger update_patients_updated_at on public.students rename to update_students_updated_at;

-- Phase 7H: rename the junction / child tables whose NAMES still carry an entity token to the
-- school-counselling vocabulary, then fix the constraint/index names that carried the old table
-- prefix. Behaviour-neutral rename (table identity + names only).
--
--   doctor_*  -> counsellor_*      nurse_*   -> assistant_*
--   patient_* -> student_*         hospital_*-> school_*
--   doctor_doctor_patients -> counsellor_counsellor_students
--   nurse_doctors          -> assistant_counsellors

begin;

alter table public.doctor_templates                        rename to counsellor_templates;
alter table public.doctor_medicines                        rename to counsellor_medicines;
alter table public.doctor_investigations                   rename to counsellor_investigations;
alter table public.doctor_layer_preferences                rename to counsellor_layer_preferences;
alter table public.doctor_practice_styles                  rename to counsellor_practice_styles;
alter table public.doctor_doctor_patients                  rename to counsellor_counsellor_students;
alter table public.doctor_segment_configurations_backup_014 rename to counsellor_segment_configurations_backup_014;
alter table public.nurse_doctors                           rename to assistant_counsellors;
alter table public.nurse_templates                         rename to assistant_templates;
alter table public.hospital_ehr                            rename to school_ehr;
alter table public.hospital_intervention_pricing           rename to school_intervention_pricing;
alter table public.hospital_investigation_lists            rename to school_investigation_lists;
alter table public.hospital_medicine_lists                 rename to school_medicine_lists;
alter table public.hospital_specialty_patterns             rename to school_specialty_patterns;
alter table public.patient_sharing                         rename to student_sharing;
alter table public.patient_dropoff_risk                    rename to student_dropoff_risk;
alter table public.patient_interventions                   rename to student_interventions;

-- Clean ALL constraint + index names that still contain an entity token. Safe to do generically
-- now that every entity-named TABLE has been renamed: the only remaining doctor/nurse/patient/
-- hospital substrings in object names are entity references (table prefixes, abbreviated forms,
-- trailing tokens, and names lagging the 7G column renames). Plural forms are handled by the
-- singular replace (doctor->counsellor leaves the trailing 's': doctors->counsellors).
do $$
declare r record;
begin
  for r in
    select rel.relname as tbl, con.conname as oldname,
      replace(replace(replace(replace(con.conname,'doctor','counsellor'),'nurse','assistant'),'patient','student'),'hospital','school') as newname
    from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    join pg_namespace n on n.oid = rel.relnamespace
    where n.nspname='public' and con.conname ~ '(doctor|nurse|patient|hospital)'
  loop
    execute format('alter table public.%I rename constraint %I to %I', r.tbl, r.oldname, r.newname);
  end loop;
  for r in
    select i.relname as oldname,
      replace(replace(replace(replace(i.relname,'doctor','counsellor'),'nurse','assistant'),'patient','student'),'hospital','school') as newname
    from pg_index idx
    join pg_class i on i.oid = idx.indexrelid
    join pg_namespace n on n.oid = i.relnamespace
    where n.nspname='public'
      and not exists (select 1 from pg_constraint c2 where c2.conindid = i.oid)
      and i.relname ~ '(doctor|nurse|patient|hospital)'
  loop
    execute format('alter index public.%I rename to %I', r.oldname, r.newname);
  end loop;
end $$;

notify pgrst, 'reload schema';

commit;

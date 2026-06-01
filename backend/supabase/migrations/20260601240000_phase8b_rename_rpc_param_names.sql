-- Phase 8B: rename the stored-function INPUT PARAMETER names to school vocabulary
-- (p_doctor_id->p_counsellor_id, p_hospital_id->p_school_id, p_patient_*->p_student_*, plus the two
-- copy-list RPC params). These were intentionally preserved through 7K/7L so the .rpc() kwargs kept
-- matching; the backend .rpc() call sites are renamed in lockstep in the same change set.
--
-- Postgres CANNOT rename a function parameter in place (CREATE OR REPLACE rejects param-name changes),
-- so each affected function is DROP+CREATEd from its retokenised definition. Word-boundary (\m..\M)
-- replacement renames the param in BOTH the signature and the body references; it does NOT touch the
-- clinical-vital inputs patient_sbp/patient_dbp/patient_hb (search_clinical_chunks_hybrid), which are
-- retained clinical content, because those tokens are not in the map below.

begin;

do $$
declare fn record; r record; newdef text;
begin
  for fn in
    select p.oid, pg_get_functiondef(p.oid) as def, p.proname,
           pg_get_function_identity_arguments(p.oid) as idargs
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proargnames && array[
        'p_doctor_id','p_hospital_id','p_patient_id','p_patient_identifier',
        'p_patient_context','p_hospital_investigation_id','p_hospital_medicine_id'
      ]
  loop
    newdef := fn.def;
    for r in select * from (values
      ('p_hospital_investigation_id','p_school_investigation_id'),
      ('p_hospital_medicine_id','p_school_medicine_id'),
      ('p_patient_identifier','p_student_identifier'),
      ('p_patient_context','p_student_context'),
      ('p_hospital_id','p_school_id'),
      ('p_patient_id','p_student_id'),
      ('p_doctor_id','p_counsellor_id')
    ) as t(o,n) loop
      newdef := regexp_replace(newdef, '\m' || r.o || '\M', r.n, 'g');
    end loop;
    -- param-name change => must drop then recreate (identity args unchanged, so the DROP is exact)
    execute 'drop function if exists public.' || quote_ident(fn.proname) || '(' || fn.idargs || ')';
    execute newdef;
  end loop;
end $$;

-- recreated functions lose grants; restore for the app roles.
grant execute on all functions in schema public to anon, authenticated, service_role;

notify pgrst, 'reload schema';

commit;

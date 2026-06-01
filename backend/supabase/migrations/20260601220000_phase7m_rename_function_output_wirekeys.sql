-- Phase 7M: rename the entity wire-key OUTPUT columns inside RPC function bodies/RETURNS to match
-- the coordinated backend+frontend rename (doctor_name->counsellor_name, unique_doctors->
-- unique_counsellors, total_patients->total_students, etc.). 7K only covered *_id/table tokens;
-- these denormalised name/count output columns were missed and would otherwise return under the
-- old key while the app reads the new one. Word-boundary replacement; DROP+CREATE fallback for
-- functions whose RETURNS row type changes; EXECUTE re-granted.

do $$
declare fn record; r record; newdef text;
begin
  for fn in
    select p.oid, pg_get_functiondef(p.oid) as def, p.proname, pg_get_function_identity_arguments(p.oid) as idargs
    from pg_proc p join pg_namespace ns on ns.oid = p.pronamespace
    where ns.nspname = 'public'
      and pg_get_functiondef(p.oid) ~ '\m(doctor_name|doctor_email|linked_doctor_name|linked_doctor_email|nurse_name|sharing_doctor_id|unique_doctors|unique_hospitals|total_patients|patient_count|patient_external_id|hospital_ids)\M'
  loop
    newdef := fn.def;
    for r in select * from (values
      ('linked_doctor_name','linked_counsellor_name'),
      ('linked_doctor_email','linked_counsellor_email'),
      ('doctor_name','counsellor_name'),
      ('doctor_email','counsellor_email'),
      ('nurse_name','assistant_name'),
      ('sharing_doctor_id','sharing_counsellor_id'),
      ('unique_doctors','unique_counsellors'),
      ('unique_hospitals','unique_schools'),
      ('total_patients','total_students'),
      ('patient_count','student_count'),
      ('patient_external_id','student_external_id'),
      ('hospital_ids','school_ids')
    ) as t(o,n) loop
      newdef := regexp_replace(newdef, '\m' || r.o || '\M', r.n, 'g');
    end loop;
    begin
      execute newdef;
    exception when others then
      execute 'drop function if exists public.' || quote_ident(fn.proname) || '(' || fn.idargs || ')';
      execute newdef;
    end;
  end loop;
end $$;

grant execute on all functions in schema public to anon, authenticated, service_role;

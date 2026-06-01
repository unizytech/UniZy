-- Phase 7F: rename FK constraints, unique/PK constraints, and indexes so their NAMES match the
-- school-counselling vocabulary (cosmetic / semantic cleanliness only — no behavioural change).
--
-- Auto-generated constraint/index names still carry the OLD tokens (e.g.
-- medical_extractions_doctor_id_fkey, doctors_pkey, idx_patients_patient_id). This migration
-- recomputes each name with a TABLE-AWARE rule:
--   * the entity-table prefix is swapped ONLY for objects on the 4 renamed tables
--     (counsellors/schools/students/assistants) — kept junction tables such as nurse_doctors,
--     doctor_templates, hospital_ehr retain their prefix;
--   * column tokens (doctor_id->counsellor_id, patient_id->student_id, hospital_id->school_id,
--     nurse_id->assistant_id, hospital_name->school_name, hospital_code->school_code) are swapped
--     everywhere in the name.
-- Renaming a unique/PK constraint also renames its backing index, so standalone indexes are only
-- renamed when not backing a constraint.

begin;

-- Constraints (FK / UNIQUE / PK)
do $$
declare r record;
begin
  for r in
    select rel.relname as tbl, con.conname as oldname,
      replace(replace(replace(replace(replace(replace(
        case rel.relname
          when 'counsellors' then replace(con.conname,'doctors','counsellors')
          when 'schools'     then replace(con.conname,'hospitals','schools')
          when 'students'    then replace(con.conname,'patients','students')
          when 'assistants'  then replace(con.conname,'nurses','assistants')
          else con.conname end,
        'doctor_id','counsellor_id'),'patient_id','student_id'),'hospital_id','school_id'),
        'nurse_id','assistant_id'),'hospital_name','school_name'),'hospital_code','school_code') as newname
    from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    join pg_namespace n on n.oid = rel.relnamespace
    where n.nspname = 'public'
  loop
    if r.newname <> r.oldname then
      execute format('alter table public.%I rename constraint %I to %I', r.tbl, r.oldname, r.newname);
    end if;
  end loop;
end $$;

-- Standalone indexes (not backing a constraint)
do $$
declare r record;
begin
  for r in
    select i.relname as oldname,
      replace(replace(replace(replace(replace(replace(
        case t.relname
          when 'counsellors' then replace(i.relname,'doctors','counsellors')
          when 'schools'     then replace(i.relname,'hospitals','schools')
          when 'students'    then replace(i.relname,'patients','students')
          when 'assistants'  then replace(i.relname,'nurses','assistants')
          else i.relname end,
        'doctor_id','counsellor_id'),'patient_id','student_id'),'hospital_id','school_id'),
        'nurse_id','assistant_id'),'hospital_name','school_name'),'hospital_code','school_code') as newname
    from pg_index idx
    join pg_class i on i.oid = idx.indexrelid
    join pg_class t on t.oid = idx.indrelid
    join pg_namespace n on n.oid = i.relnamespace
    where n.nspname = 'public'
      and not exists (select 1 from pg_constraint con where con.conindid = i.oid)
  loop
    if r.newname <> r.oldname then
      execute format('alter index public.%I rename to %I', r.oldname, r.newname);
    end if;
  end loop;
end $$;

-- One composite index keeps a bare "_hospital" suffix (shorthand for the school FK column);
-- rename it explicitly for full semantic cleanliness.
alter index if exists public.idx_students_student_id_hospital rename to idx_students_student_id_school;

commit;

-- Phase 7B: rename column patient_id -> student_id (student entity column family).
--
-- Part of the per-entity DB+code cutover (healthcare->schools). Unlike Phase 7A, `patient_id`
-- exists BOTH as a child FK column (16 base tables) AND as a real varchar column (the external
-- id / MRN) on the entity table itself (`students`, formerly `patients`). Renaming the entity
-- column means the `patients` backward-compat view must be recreated to expose `student_id AS
-- patient_id` so un-migrated code reading `patients.patient_id` keeps working.
--
-- FK constraints and indexes auto-follow the column rename (metadata-only). No RLS policy
-- references patient_id (verified). The `session_extractions` / analytics views over the renamed
-- tables are `select *`-style and auto-follow; only the `patients` compat view needs an explicit
-- alias (its purpose is to preserve the OLD column name).
--
-- Code referencing these columns, the `patients` table name, `/api/v1/patients` routes, and the
-- `patients(...)` embeds is migrated to the student vocabulary in the SAME change set.

begin;

-- 1. Drop the patients compat view (recreated with an explicit alias after the rename, so the
--    OLD column name `patient_id` is preserved on the view rather than following the rename).
drop view if exists public.patients;

-- 2. Rename the FK column on every base table that carries it.
alter table public.allied_health_needs          rename column patient_id to student_id;
alter table public.api_client_usage             rename column patient_id to student_id;
alter table public.bills                         rename column patient_id to student_id;
alter table public.care_quality_risk            rename column patient_id to student_id;
alter table public.clinical_severity_assessments rename column patient_id to student_id;
alter table public.consultation_insights        rename column patient_id to student_id;
alter table public.extraction_embeddings        rename column patient_id to student_id;
alter table public.followup_tracking            rename column patient_id to student_id;
alter table public.medical_extractions          rename column patient_id to student_id;
alter table public.other_clinical_needs         rename column patient_id to student_id;
alter table public.patient_dropoff_risk         rename column patient_id to student_id;
alter table public.patient_sharing              rename column patient_id to student_id;
alter table public.phi_audit_log                rename column patient_id to student_id;
alter table public.recording_sessions           rename column patient_id to student_id;
alter table public.segment_embeddings           rename column patient_id to student_id;

-- 3. Entity table's own external-id (MRN) column.
alter table public.students rename column patient_id to student_id;

-- 4. Plural array column (list of student UUIDs on the link table).
alter table public.doctor_doctor_patients rename column patient_ids to student_ids;

-- 5. Recreate the patients compat view exposing student_id under the OLD name patient_id.
create view public.patients with (security_invoker = true) as
  select id,
         student_id as patient_id,
         full_name, date_of_birth, gender, is_anonymized,
         created_at, updated_at, add_info, ip_id, op_id,
         doctor_ids, hospital_id, preferred_language
  from public.students;

grant select, insert, update, delete on public.patients to anon, authenticated, service_role;

notify pgrst, 'reload schema';

commit;

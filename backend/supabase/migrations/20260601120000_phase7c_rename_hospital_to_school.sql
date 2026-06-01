-- Phase 7C: rename column hospital_id -> school_id and the school entity's identity
-- columns hospital_name/hospital_code -> school_name/school_code (school entity column family).
--
-- Part of the per-entity DB+code cutover (healthcare->schools). hospital_id is an FK on 22 base
-- tables, INCLUDING the entity tables (counsellors/students/assistants reference their school).
-- The `doctors` compat view is still in use by un-migrated counsellor code (until Phase 7D); a
-- plain `select *` view preserves the OLD column name after a base rename, so we DROP+recreate it
-- fresh so it exposes the NEW name (`school_id`) to match the code being renamed in this slice.
-- (Verified behaviour: a freshly recreated `select *` view exposes the current/new column names.)
-- The other compat views (hospitals/patients/nurses) are no longer queried by live code (their
-- entities already moved to base-table access in Phases 7A/7B or in this slice) and auto-follow.
--
-- FK constraints/indexes auto-follow the rename (metadata-only). No RLS policy references
-- hospital_id (verified). Analytics views (v_hospital_usage_summary, ...) are not referenced in
-- application code and auto-follow.

begin;

-- 1. hospital_id -> school_id on every base table that carries it (incl. entity tables).
alter table public.admin_users                    rename column hospital_id to school_id;
alter table public.api_clients                    rename column hospital_id to school_id;
alter table public.assistants                     rename column hospital_id to school_id;
alter table public.bills                          rename column hospital_id to school_id;
alter table public.counsellors                    rename column hospital_id to school_id;
alter table public.extraction_embeddings          rename column hospital_id to school_id;
alter table public.followup_tracking              rename column hospital_id to school_id;
alter table public.hospital_ehr                   rename column hospital_id to school_id;
alter table public.hospital_intervention_pricing  rename column hospital_id to school_id;
alter table public.hospital_investigation_lists   rename column hospital_id to school_id;
alter table public.hospital_medicine_lists        rename column hospital_id to school_id;
alter table public.hospital_specialty_patterns    rename column hospital_id to school_id;
alter table public.investigation_list_uploads     rename column hospital_id to school_id;
alter table public.phi_audit_log                  rename column hospital_id to school_id;
alter table public.procedure_fee_master           rename column hospital_id to school_id;
alter table public.qa_engine_settings             rename column hospital_id to school_id;
alter table public.qa_query_history               rename column hospital_id to school_id;
alter table public.realtime_extraction_responses  rename column hospital_id to school_id;
alter table public.room_rate_master               rename column hospital_id to school_id;
alter table public.segment_embeddings             rename column hospital_id to school_id;
alter table public.students                       rename column hospital_id to school_id;
alter table public.templates                      rename column hospital_id to school_id;

-- 2. School entity's identity columns.
alter table public.schools rename column hospital_name to school_name;
alter table public.schools rename column hospital_code to school_code;

-- 3. Denormalized code column on realtime_extraction_responses.
alter table public.realtime_extraction_responses rename column hospital_code to school_code;

-- 4. Recreate the `doctors` compat view fresh so it exposes school_id (used by un-migrated
--    counsellor-entity code until Phase 7D).
drop view if exists public.doctors;
create view public.doctors with (security_invoker = true) as select * from public.counsellors;
grant select, insert, update, delete on public.doctors to anon, authenticated, service_role;

notify pgrst, 'reload schema';

commit;

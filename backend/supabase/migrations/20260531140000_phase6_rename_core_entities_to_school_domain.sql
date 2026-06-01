-- Phase 6: Physical rename of core entity tables to the school-counselling domain.
--
-- Inverts the Phase 1 alias views (20260530120000_phase1_school_alias_views.sql):
-- the NEW names become the real base tables; the OLD names are recreated as
-- backward-compatibility views so the existing (~5,900) code references keep working
-- until application code is migrated to the new names in a later phase.
--
-- SCOPE (per repurposing plan):
--   * TABLE-layer rename only for the 4 core entities.
--   * Cross-cutting FK COLUMN renames (hospital_id->school_id, doctor_id->counsellor_id,
--     patient_id->student_id, nurse_id->assistant_id) and identity columns
--     (hospital_name->school_name, hospital_code->school_code) are intentionally DEFERRED
--     to a later phase, once code consumes the new names. A view renames the table layer
--     only, so the compat views below keep exposing the original column names.
--   * Healthcare-only tables (billing / EHR / medicines / investigations / radiology /
--     clinical KB / triage) are left untouched this round ("repurpose later").
--
-- SAFETY: ALTER TABLE ... RENAME is metadata-only (no data rewrite). Indexes, constraints,
-- foreign keys, RLS policies and triggers all follow the table automatically. Dependent
-- analytics views (v_*, triage_*, intervention_analytics) reference the base tables by OID
-- and auto-follow the rename.

begin;

-- 1. Drop the Phase 1 forward alias views (their names are about to become real tables).
drop view if exists public.schools;
drop view if exists public.counsellors;
drop view if exists public.assistants;
drop view if exists public.students;

-- 2. Physically rename the core entity tables.
alter table public.hospitals rename to schools;
alter table public.doctors   rename to counsellors;
alter table public.patients  rename to students;
alter table public.nurses    rename to assistants;

-- 3. Recreate the OLD names as backward-compatibility views (the inverse of Phase 1).
--    security_invoker = true preserves base-table RLS for the querying role.
create view public.hospitals with (security_invoker = true) as select * from public.schools;
create view public.doctors   with (security_invoker = true) as select * from public.counsellors;
create view public.patients  with (security_invoker = true) as select * from public.students;
create view public.nurses    with (security_invoker = true) as select * from public.assistants;

-- 4. Replicate the DML privileges the base tables carried so the live app keeps
--    reading AND writing through the old names (compat views are auto-updatable).
grant select, insert, update, delete on public.hospitals to anon, authenticated, service_role;
grant select, insert, update, delete on public.doctors   to anon, authenticated, service_role;
grant select, insert, update, delete on public.patients  to anon, authenticated, service_role;
grant select, insert, update, delete on public.nurses    to anon, authenticated, service_role;

comment on view public.hospitals is 'Back-compat alias of public.schools (Phase 6 physical rename). Drop after code migration.';
comment on view public.doctors   is 'Back-compat alias of public.counsellors (Phase 6 physical rename). Drop after code migration.';
comment on view public.patients  is 'Back-compat alias of public.students (Phase 6 physical rename). Drop after code migration.';
comment on view public.nurses    is 'Back-compat alias of public.assistants (Phase 6 physical rename). Drop after code migration.';

commit;

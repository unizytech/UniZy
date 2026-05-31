-- Phase 1: School-context alias views (healthcare -> schools counselling repurposing)
--
-- Non-breaking / additive: base tables are unchanged. These views simply expose the
-- existing entity tables under the new counselling vocabulary so new code/UI can adopt
-- the names incrementally without renaming base tables (physical rename deferred to Phase 6).
--
-- security_invoker = true: each view runs with the privileges/RLS of the querying role,
-- so row-level security on the base tables is respected (no privilege escalation).
--
-- NOTE: FK *column* names (doctor_id, hospital_id, patient_id, nurse_id) intentionally
-- stay as-is in Phase 1 — a view renames the table layer only, not columns. Column renames
-- and role GRANTs on these views are deferred until code begins consuming them.

create or replace view public.schools
  with (security_invoker = true) as
  select * from public.hospitals;

create or replace view public.counsellors
  with (security_invoker = true) as
  select * from public.doctors;

create or replace view public.assistants
  with (security_invoker = true) as
  select * from public.nurses;

create or replace view public.students
  with (security_invoker = true) as
  select * from public.patients;

create or replace view public.session_extractions
  with (security_invoker = true) as
  select * from public.medical_extractions;

comment on view public.schools             is 'Alias of public.hospitals (schools-context repurposing, Phase 1).';
comment on view public.counsellors         is 'Alias of public.doctors (schools-context repurposing, Phase 1).';
comment on view public.assistants          is 'Alias of public.nurses (schools-context repurposing, Phase 1).';
comment on view public.students            is 'Alias of public.patients (schools-context repurposing, Phase 1).';
comment on view public.session_extractions is 'Alias of public.medical_extractions (schools-context repurposing, Phase 1).';

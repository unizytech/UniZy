-- Phase 7E: drop the backward-compatibility views.
--
-- After Phases 7A–7D, ALL application code references the base-table names
-- (schools / counsellors / students / assistants) and the new column names. The temporary
-- compat views (old healthcare names) are verified unused — zero `.table("...")`, `.from("...")`,
-- or embed references remain in backend or frontend — and nothing in the database depends on
-- them. This migration removes them so the schema reflects only the school-counselling vocabulary.
--
-- NOTE: apply this only AFTER the renamed code is deployed/restarted and runtime-tested. Until
-- then these views are a harmless safety net (any missed reference would silently resolve through
-- them instead of erroring). They are trivially recreatable if needed.

begin;

drop view if exists public.session_extractions;
drop view if exists public.hospitals;
drop view if exists public.doctors;
drop view if exists public.patients;
drop view if exists public.nurses;

notify pgrst, 'reload schema';

commit;

-- Phase 7A: rename column nurse_id -> assistant_id (assistant entity column family).
--
-- Part of the per-entity DB+code cutover (healthcare->schools). `nurse_id` is a child
-- foreign-key column on exactly 3 tables; the entity table (`assistants`, formerly `nurses`)
-- has NO `nurse_id` column of its own, so the `nurses` backward-compat view is unaffected and
-- needs no rewrite this phase. FK constraints and indexes auto-follow the column rename
-- (metadata-only). No RLS policy references nurse_id (verified).
--
-- Code referencing these columns (and the `nurses` table name / `/api/v1/nurses` routes) is
-- migrated to the assistant vocabulary in the SAME change set.

begin;

alter table public.nurse_doctors      rename column nurse_id to assistant_id;
alter table public.nurse_templates    rename column nurse_id to assistant_id;
alter table public.recording_sessions rename column nurse_id to assistant_id;

notify pgrst, 'reload schema';

commit;

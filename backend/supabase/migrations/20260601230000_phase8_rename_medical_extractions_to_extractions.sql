-- Phase 8: rename the core table medical_extractions -> extractions (de-medicalise; aligns with the
-- existing /api/v1/extractions route and the extraction_* child tables). The FK columns that point
-- here are already the neutral `extraction_id` (self-ref `merged_into_extraction_id`), so NO column
-- rename is needed. Dependent VIEWS (intervention_analytics, triage_suggestion_analytics) auto-follow
-- a table rename; stored FUNCTION bodies do NOT, so the 10 that reference the old name are retokenised.
-- Constraints / indexes / the updated_at trigger carrying the old table name are renamed for semantic
-- cleanliness (consistent with phase 7F). Idempotent-ish: re-running is safe (filters on old names).

begin;

-- 1. the table
alter table public.medical_extractions rename to extractions;

-- 2. the updated_at trigger name (the trigger FUNCTION it calls is generic/shared and carries no
--    entity vocab, so only the trigger name is renamed).
alter trigger update_medical_extractions_updated_at on public.extractions
  rename to update_extractions_updated_at;

-- 3. constraints: medical_extractions_* -> extractions_*  (renaming the pkey/unique constraint also
--    renames its backing index, so those are handled here and skipped in step 4).
do $$
declare c record;
begin
  for c in
    select con.conname
    from pg_constraint con
      join pg_class r on r.oid = con.conrelid
      join pg_namespace n on n.oid = r.relnamespace
    where n.nspname = 'public' and r.relname = 'extractions'
      and con.conname like 'medical_extractions_%'
  loop
    execute format('alter table public.extractions rename constraint %I to %I',
      c.conname, replace(c.conname, 'medical_extractions_', 'extractions_'));
  end loop;
end $$;

-- 4. remaining (non-constraint) indexes: idx_medical_extractions_* -> idx_extractions_*
do $$
declare i record;
begin
  for i in
    select ic.relname
    from pg_index ix
      join pg_class ic on ic.oid = ix.indexrelid
      join pg_class tc on tc.oid = ix.indrelid
      join pg_namespace n on n.oid = ic.relnamespace
    where n.nspname = 'public' and tc.relname = 'extractions'
      and ic.relname like '%medical_extractions%'
  loop
    execute format('alter index public.%I rename to %I',
      i.relname, replace(i.relname, 'medical_extractions', 'extractions'));
  end loop;
end $$;

-- 5. retokenise stored function bodies that still reference the old table name by string. Word-boundary
--    replacement; CREATE OR REPLACE works (no return-type change) with DROP+CREATE fallback for safety.
do $$
declare fn record; newdef text;
begin
  for fn in
    select p.oid, pg_get_functiondef(p.oid) as def, p.proname,
           pg_get_function_identity_arguments(p.oid) as idargs
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.prosrc ~ '\mmedical_extractions\M'
  loop
    newdef := regexp_replace(fn.def, '\mmedical_extractions\M', 'extractions', 'g');
    begin
      execute newdef;
    exception when others then
      execute 'drop function if exists public.' || quote_ident(fn.proname) || '(' || fn.idargs || ')';
      execute newdef;
    end;
  end loop;
end $$;

-- functions that were DROP+CREATEd lose grants; restore for the app roles.
grant execute on all functions in schema public to anon, authenticated, service_role;

notify pgrst, 'reload schema';

commit;

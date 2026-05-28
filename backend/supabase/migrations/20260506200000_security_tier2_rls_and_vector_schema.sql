-- Tier 2 security hardening (fixes 3, 4, 5 from advisor follow-up).
--
-- Fix 3 — `extraction_photos` RLS not enabled.
--   Two backend endpoints (POST/GET) operate on this table; both use the
--   service_role key, which bypasses RLS. Frontend never accesses this table
--   directly (verified via audit on 2026-05-06). Enabling RLS without policies
--   yields a service-role-only access pattern by default.
--
-- Fix 4 — `extraction_translations` and `phi_audit_log` had `USING (true)`
--   policies named "Service role full access" but applied to PUBLIC. Net effect:
--   anon and authenticated could read/write these tables. Drop the bad
--   policies; service_role bypasses RLS so the backend pipeline is unaffected.
--   Frontend has no direct calls to either table.
--
-- Fix 5 — `vector` extension is in `public` schema. Moving to dedicated
--   `extensions` schema. Pre-checks confirmed:
--     * `extensions` schema already exists with USAGE granted to all roles
--     * postgres role's default search_path already includes `extensions`
--     * Three functions reference unqualified `vector` in args/body —
--       `match_clinical_guidelines`, `search_clinical_chunks_hybrid`,
--       `search_guidelines_by_keywords`. We update their search_path to
--       include `extensions` BEFORE moving the extension so the type still
--       resolves.
--   Vector-typed columns and HNSW indexes are bound to the type by OID and
--   continue to work after the schema move. Backend Python code that issued
--   raw `::vector` casts has been updated to use `::extensions.vector`
--   (semantic_search_service.py).

-- ============================================================================
-- Fix 4: drop overly permissive RLS policies
-- ============================================================================

DROP POLICY IF EXISTS "Service role full access on extraction_translations"
  ON public.extraction_translations;

DROP POLICY IF EXISTS "Service role full access"
  ON public.phi_audit_log;

-- ============================================================================
-- Fix 3: enable RLS on extraction_photos (no policies — service_role bypass)
-- ============================================================================

ALTER TABLE public.extraction_photos ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Fix 5: move pgvector extension to `extensions` schema
-- ============================================================================

-- Update search_path on the 3 functions that use unqualified `vector`.
-- Done first, while `vector` still resolves in the migration's own session.

ALTER FUNCTION public.match_clinical_guidelines(
  query_embedding vector,
  match_specialty text,
  match_topics text[],
  match_count integer,
  similarity_threshold double precision
) SET search_path = public, extensions, pg_temp;

ALTER FUNCTION public.search_clinical_chunks_hybrid(
  query_embedding vector,
  query_text text,
  filter_specialty text,
  filter_chunk_types text[],
  filter_urgency text,
  filter_comorbidity text,
  filter_care_level text,
  filter_drug_class text,
  patient_sbp integer,
  patient_dbp integer,
  patient_hb numeric,
  match_count integer,
  min_similarity double precision
) SET search_path = public, extensions, pg_temp;

ALTER FUNCTION public.search_guidelines_by_keywords(
  search_query text,
  match_specialty text,
  match_count integer
) SET search_path = public, extensions, pg_temp;

-- Move the extension. Type and operator OIDs do not change — vector columns,
-- HNSW indexes, and operator-class references continue to resolve.
ALTER EXTENSION vector SET SCHEMA extensions;

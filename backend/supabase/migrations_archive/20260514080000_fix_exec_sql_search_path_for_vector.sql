-- Restore vector-operator resolution inside exec_sql.
--
-- Tier 1 hardening (20260506190000) pinned exec_sql to
-- `search_path = public, pg_temp`. Tier 2 (20260506200000) moved the
-- pgvector extension from public to the `extensions` schema and added
-- `extensions` to the search_path of the three RPCs that reference
-- `vector` directly. exec_sql was missed because its body never names
-- vector — it just runs whatever SQL the caller passes in.
--
-- Q&A semantic search (services/qa/semantic_search_service.py) builds
-- raw SQL with `<=>` and casts to `::extensions.vector`, then dispatches
-- via supabase.rpc("exec_sql", ...). The cast is fully qualified, but
-- the operator is not — and operator resolution uses the executing
-- function's search_path. Without `extensions` on exec_sql, the `<=>`
-- operator between two extensions.vector operands can't be resolved,
-- yielding: `operator does not exist: extensions.vector <=> extensions.vector`.
--
-- Fix: add `extensions` to exec_sql's search_path, matching what tier 2
-- already did for match_clinical_guidelines / search_clinical_chunks_hybrid /
-- search_guidelines_by_keywords. EXECUTE is still revoked from anon /
-- authenticated / PUBLIC (tier 1), so this widens lookup only for
-- service_role-driven backend calls.

ALTER FUNCTION public.exec_sql(text)
  SET search_path = public, extensions, pg_temp;

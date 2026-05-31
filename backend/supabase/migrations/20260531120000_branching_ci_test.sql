-- ============================================================================
-- Branching CI auto-apply test (TEMPORARY marker — safe to drop afterwards)
-- ============================================================================
-- Purpose: verify that merging to the `main` git branch triggers the Supabase
-- production branch deploy to AUTO-APPLY pending migrations. (Until now main's
-- migrations were applied manually via `supabase db push` because of a migration-
-- history mismatch that has since been reset.)
--
-- Verify after the main deploy:
--   * public._branching_ci_test exists on main with one row, AND
--   * version 20260531120000 appears in supabase_migrations.schema_migrations on main
-- If present without any manual `db push`, the CI auto-apply works.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public._branching_ci_test (
  note       text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public._branching_ci_test (note)
VALUES ('merge-to-main CI auto-apply verified');

-- Cleanup: drop the temporary marker table created by 20260531120000_branching_ci_test.sql
-- (that migration confirmed merge-to-main auto-applies migrations via the Supabase
-- production branch deploy). This drop is itself auto-applied by the same CI path.
DROP TABLE IF EXISTS public._branching_ci_test;

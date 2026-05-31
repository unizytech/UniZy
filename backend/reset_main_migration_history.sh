#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One-off: reset MAIN's Supabase migration HISTORY to the squashed baseline
# (so it matches dev's lineage), then apply the 3 pending migrations.
#
# SAFETY: `supabase migration repair` only edits the schema_migrations tracking
# table — it does NOT run down-migrations or alter your tables/data. Main's
# actual schema stays byte-for-byte identical; only the recorded history changes.
#
# Run from anywhere:   ! bash backend/reset_main_migration_history.sh
# Review it first. Delete it afterward if you like — it's a one-off.
# ---------------------------------------------------------------------------
cd "$(dirname "$0")" || exit 1   # -> backend/ (where supabase/ lives)

MAIN=yvpyqnkxxgyzaapozafg
DEV=oepojxrximnmqwvnpoiu

relink_dev() { supabase link --project-ref "$DEV" >/dev/null 2>&1 && echo "   (relinked CLI to dev)"; }

echo "==> 1/5 linking CLI to MAIN ($MAIN)"
supabase link --project-ref "$MAIN" >/dev/null 2>&1 || { echo "ABORT: link to main failed"; exit 1; }

echo "==> 2/5 deriving revert list from db push (CLI-authoritative)"
OUT=$(supabase db push --yes 2>&1)
LIST=$(printf '%s\n' "$OUT" \
        | grep -oE '20[0-9]{12}' | sort -u \
        | grep -vE '^(20260530120000|20260530140000|20260530150000)$' \
        | tr '\n' ' ')
N=$(printf '%s' "$LIST" | wc -w | tr -d ' ')
echo "    versions to mark reverted: $N (expected 140)"
if [ "$N" != "140" ]; then
  echo "ABORT: expected 140 versions, got $N — no changes made."
  relink_dev; exit 1
fi

echo "==> 3/5 repairing history -> baseline only (tracking table only, NO schema change)"
# shellcheck disable=SC2086
supabase migration repair --status reverted $LIST || { echo "ABORT: repair failed"; relink_dev; exit 1; }

echo "==> 4/5 migration list after repair (expect baseline synced + 3 pending)"
supabase migration list

echo "==> 5/5 applying pending migrations to main (phase1 + career + inactivate)"
supabase db push --yes || { echo "WARNING: db push failed after repair — investigate"; relink_dev; exit 1; }

relink_dev
echo "DONE: main history reset to baseline + 3 migrations applied; CLI back on dev."

#!/usr/bin/env python3
"""
Backfill extraction_accuracy_metrics for historical extractions.

Finds extractions rows missing an extraction_accuracy_metrics row
(or all of them with --force) and computes metrics via
compute_and_save_accuracy_metrics() (same logic the live pipeline uses).

By default includes BOTH edited (edit_count > 0) and unedited rows so
unedited records also seed a 0-error row that contributes to the WER
denominator. For unedited rows, edited_extraction_json is treated as
identical to original_extraction_json. Use --edited-only to restore the
old behaviour of only backfilling rows the counsellor edited.

Usage (from repo root):
    cd backend && source venv/bin/activate
    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \\
    python scripts/backfill_accuracy_metrics.py [--school-id UUID] \\
        [--counsellor-id UUID] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] \\
        [--days N] [--dry-run] [--limit N] [--edited-only] [--force]

Options:
    --school-id UUID    Restrict to one school's counsellors.
    --counsellor-id UUID      Restrict to one counsellor.
    --start-date DATE     Only rows created on/after this UTC date (inclusive).
    --end-date DATE       Only rows created strictly before this UTC date.
    --days N              Only backfill rows from the last N days.
    --dry-run             Count what would be backfilled, don't write.
    --limit N             Max extractions to process (default: no limit).
    --edited-only         Old behaviour: skip rows with edit_count = 0.
    --force               Recompute even if an accuracy row already exists.
"""

import argparse
import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.supabase_service import supabase
from services.accuracy_metrics_service import compute_and_save_accuracy_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _find_candidates(
    school_id: Optional[str],
    counsellor_id: Optional[str],
    since_iso: Optional[str],
    until_iso: Optional[str],
    limit: Optional[int],
    edited_only: bool = False,
    force: bool = False,
) -> list[dict]:
    """Find extractions to backfill. If force=True, include those that already
    have an accuracy row (rows will be upserted). If edited_only=True, restrict
    to rows the counsellor edited."""
    # 1. Pick counsellors in the filter scope
    counsellor_ids: Optional[list[str]] = None
    if school_id and not counsellor_id:
        res = supabase.table("counsellors").select("id").eq("school_id", school_id).execute()
        counsellor_ids = [d["id"] for d in (res.data or [])]
        if not counsellor_ids:
            return []

    # 2. Fetch extractions in scope
    q = supabase.table("extractions")\
        .select("id, session_id, counsellor_id, edit_count, original_extraction_json, edited_extraction_json, created_at")
    if edited_only:
        q = q.gt("edit_count", 0)
    if counsellor_id:
        q = q.eq("counsellor_id", counsellor_id)
    elif counsellor_ids is not None:
        q = q.in_("counsellor_id", counsellor_ids)
    if since_iso:
        q = q.gte("created_at", since_iso)
    if until_iso:
        q = q.lt("created_at", until_iso)
    q = q.order("created_at", desc=True)
    if limit:
        q = q.limit(limit * 3)  # fetch extra to offset those already covered
    extractions = q.execute().data or []
    if not extractions:
        return []

    # 3. Remove those that already have an accuracy row (unless force)
    if force:
        missing = extractions
    else:
        ext_ids = [e["id"] for e in extractions]
        existing = supabase.table("extraction_accuracy_metrics")\
            .select("extraction_id")\
            .in_("extraction_id", ext_ids)\
            .execute().data or []
        covered = {row["extraction_id"] for row in existing}
        missing = [e for e in extractions if e["id"] not in covered]

    if limit:
        missing = missing[:limit]
    return missing


async def _process_one(extraction: dict) -> bool:
    """Run compute_and_save_accuracy_metrics for a single extraction. Returns True on success."""
    orig = extraction.get("original_extraction_json")
    edited = extraction.get("edited_extraction_json")
    if not isinstance(orig, dict):
        logger.warning(f"[BACKFILL] Skip {extraction['id']}: non-dict original (orig={type(orig).__name__})")
        return False
    # Unedited rows: compare original to itself so the row contributes
    # 0 errors and the AI word count to the WER denominator.
    if not isinstance(edited, dict):
        edited = orig
    try:
        await compute_and_save_accuracy_metrics(
            extraction_id=uuid.UUID(extraction["id"]),
            original_json=orig,
            edited_json=edited,
            counsellor_id=extraction.get("counsellor_id"),
        )
        return True
    except Exception as e:
        logger.error(f"[BACKFILL] Failed {extraction['id']}: {e}")
        return False


async def main(args: argparse.Namespace) -> None:
    since_iso = None
    until_iso = None
    if args.start_date:
        since_iso = datetime.fromisoformat(args.start_date).replace(tzinfo=timezone.utc).isoformat()
    elif args.days:
        since_iso = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    if args.end_date:
        until_iso = datetime.fromisoformat(args.end_date).replace(tzinfo=timezone.utc).isoformat()

    candidates = _find_candidates(
        args.school_id, args.counsellor_id, since_iso, until_iso, args.limit,
        edited_only=args.edited_only, force=args.force,
    )
    logger.info(f"[BACKFILL] Candidates: {len(candidates)} (edited_only={args.edited_only}, force={args.force})")

    if args.dry_run:
        for c in candidates[:10]:
            logger.info(f"  would process: {c['id']} (counsellor={c.get('counsellor_id')}, created={c['created_at']})")
        if len(candidates) > 10:
            logger.info(f"  ... and {len(candidates) - 10} more")
        return

    succeeded = 0
    failed = 0
    for i, ext in enumerate(candidates, 1):
        ok = await _process_one(ext)
        if ok:
            succeeded += 1
        else:
            failed += 1
        if i % 10 == 0:
            logger.info(f"[BACKFILL] Progress: {i}/{len(candidates)} (ok={succeeded}, fail={failed})")
    logger.info(f"[BACKFILL] Done. Total: {len(candidates)}, ok={succeeded}, fail={failed}")


if __name__ == "__main__":
    for var in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY"):
        if not os.getenv(var):
            print(f"ERROR: {var} is required")
            sys.exit(1)

    p = argparse.ArgumentParser()
    p.add_argument("--school-id", help="Restrict to one school's counsellors")
    p.add_argument("--counsellor-id", help="Restrict to one counsellor")
    p.add_argument("--start-date", help="Inclusive start date YYYY-MM-DD (UTC)")
    p.add_argument("--end-date", help="Exclusive end date YYYY-MM-DD (UTC)")
    p.add_argument("--days", type=int, help="Only backfill rows from the last N days")
    p.add_argument("--limit", type=int, help="Max extractions to process")
    p.add_argument("--dry-run", action="store_true", help="Count only, don't write")
    p.add_argument("--edited-only", action="store_true", help="Skip rows where edit_count = 0")
    p.add_argument("--force", action="store_true", help="Recompute even if an accuracy row already exists (upsert)")
    args = p.parse_args()
    asyncio.run(main(args))

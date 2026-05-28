#!/usr/bin/env python3
"""
Normalize historical iframe-shaped prescription edits back to the AI's
original schema.

Background
----------
The KG hospital edit iframe historically saved prescription edits in
M-N-E-N quantity schema (morning_qty / noon_qty / evening_qty / night_qty /
durationDays / remarks / timeToTake) even when the AI emitted them in the
KG Cardio schema (dose / intake / intake_period / duration / duration_unit /
instructions). Forward-looking edits are now normalized at PUT time
(routers/ehr_integration.py + services/iframe_edit_normalizer.py), but rows
already saved before that fix still have the schema mismatch. This script
walks those rows and applies the same normalizer.

Scope
-----
Only touches rows where:
  - original_extraction_json.prescription[0] looks like KG Cardio (has 'dose')
  - edited_extraction_json.prescription[0] looks like iframe M-N-E-N (has
    'morning_qty')
  - both arrays are non-empty

Usage (from repo root)::

    cd backend && source venv/bin/activate
    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \\
    python scripts/_run_normalize.py [--doctor-id UUID] [--limit N] [--dry-run]

Options:
    --doctor-id UUID   Restrict to one doctor.
    --limit N          Max rows to update (default: no limit).
    --dry-run          Report what would change but do not write.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

# Bypass services/__init__.py's eager gemini_service import. Same trick as
# scripts/_run_backfill.py — inject an empty `services` package so that
# `from services.iframe_edit_normalizer import ...` finds the submodule
# without running the package init.
_BACKEND_DIR = Path(__file__).parent.parent
_services_stub = types.ModuleType("services")
_services_stub.__path__ = [str(_BACKEND_DIR / "services")]
sys.modules.setdefault("services", _services_stub)
sys.path.insert(0, str(_BACKEND_DIR))

from supabase import create_client, Client

from services.iframe_edit_normalizer import normalize_iframe_edit_payload

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise SystemExit("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _looks_like_iframe_drift(orig_pres: Any, edit_pres: Any) -> bool:
    if not isinstance(orig_pres, list) or not orig_pres:
        return False
    if not isinstance(edit_pres, list) or not edit_pres:
        return False
    first_orig = next((x for x in orig_pres if isinstance(x, dict)), None)
    first_edit = next((x for x in edit_pres if isinstance(x, dict)), None)
    if not first_orig or not first_edit:
        return False
    return ("dose" in first_orig) and ("morning_qty" in first_edit)


def _find_candidates(
    sb: Client,
    doctor_id: Optional[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    q = sb.table("medical_extractions").select(
        "id, doctor_id, original_extraction_json, edited_extraction_json, edit_count, created_at"
    )
    if doctor_id:
        q = q.eq("doctor_id", doctor_id)
    # Only rows that have an edit at all
    q = q.gt("edit_count", 0)
    q = q.order("created_at", desc=True)
    rows = q.execute().data or []

    out: List[Dict[str, Any]] = []
    for r in rows:
        orig = r.get("original_extraction_json") or {}
        edit = r.get("edited_extraction_json") or {}
        if not isinstance(orig, dict) or not isinstance(edit, dict):
            continue
        if _looks_like_iframe_drift(orig.get("prescription"), edit.get("prescription")):
            out.append(r)
            if limit and len(out) >= limit:
                break
    return out


def _normalize_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the normalized edited_extraction_json, or None if unchanged."""
    edit = row.get("edited_extraction_json") or {}
    orig = row.get("original_extraction_json") or {}
    new_edit = normalize_iframe_edit_payload(edit, orig)
    if new_edit is edit or new_edit == edit:
        return None
    return new_edit


def main(args: argparse.Namespace) -> None:
    sb = _get_supabase()
    candidates = _find_candidates(sb, args.doctor_id, args.limit)
    logger.info(
        f"[NORMALIZE] Found {len(candidates)} candidate(s) "
        f"(doctor_id={args.doctor_id or 'all'}, dry_run={args.dry_run})"
    )

    updated = 0
    skipped_no_diff = 0
    failed = 0
    for i, row in enumerate(candidates, 1):
        ext_id = row["id"]
        try:
            new_edit = _normalize_row(row)
            if new_edit is None:
                skipped_no_diff += 1
                logger.info(f"  {i}/{len(candidates)} {ext_id}: no diff after normalize, skipped")
                continue

            old_keys = sorted((row["edited_extraction_json"].get("prescription") or [{}])[0].keys()) if (row["edited_extraction_json"].get("prescription") or []) else []
            new_keys = sorted((new_edit.get("prescription") or [{}])[0].keys()) if (new_edit.get("prescription") or []) else []
            logger.info(
                f"  {i}/{len(candidates)} {ext_id}: prescription keys "
                f"{old_keys} -> {new_keys}"
            )

            if args.dry_run:
                continue

            sb.table("medical_extractions").update(
                {"edited_extraction_json": new_edit}
            ).eq("id", ext_id).execute()
            updated += 1
        except Exception as e:
            failed += 1
            logger.error(f"  {i}/{len(candidates)} {ext_id}: failed: {e}")

    logger.info(
        f"[NORMALIZE] Done. updated={updated}, skipped_no_diff={skipped_no_diff}, failed={failed}, "
        f"total={len(candidates)} (dry_run={args.dry_run})"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--doctor-id", help="Restrict to one doctor")
    p.add_argument("--limit", type=int, help="Max rows to update")
    p.add_argument("--dry-run", action="store_true", help="Report only, don't write")
    args = p.parse_args()
    main(args)

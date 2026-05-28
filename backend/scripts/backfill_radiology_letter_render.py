"""Backfill: re-render `consult_letter` for radiology extractions.

Fix context: `_flatten_insights` previously didn't expose top-level camelCase
scalar segments (e.g. `presentingComplaints`) under their snake_case alias,
so layout placeholders like `{{ presenting_complaints }}` rendered empty.

This script picks up every medical_extractions row whose template has a
`letter_template_jinja` (radiology RS_*) and re-runs `attach_letter_artifacts`
against `original_extraction_json`. `edited_extraction_json` is left untouched
to preserve manual edits.

Run:
    cd backend && source venv/bin/activate && python -m scripts.backfill_radiology_letter_render
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backfill_letter_render")

from services.letter_render_service import attach_letter_artifacts  # noqa: E402
from services.supabase_service import supabase  # noqa: E402


def _fetch_template_map() -> dict[str, str]:
    """Return template_code → template_id for all templates with a layout."""
    rows = (
        supabase.table("templates")
        .select("id, template_code, letter_template_jinja")
        .not_.is_("letter_template_jinja", "null")
        .execute()
        .data
        or []
    )
    return {r["template_code"]: r["id"] for r in rows if r.get("letter_template_jinja")}


def _iter_extractions(template_codes: list[str]):
    """Stream extractions whose recording_session used one of the radiology templates."""
    page = 0
    page_size = 100
    while True:
        sessions = (
            supabase.table("recording_sessions")
            .select("id, template_code, patient_id")
            .in_("template_code", template_codes)
            .range(page * page_size, (page + 1) * page_size - 1)
            .execute()
            .data
            or []
        )
        if not sessions:
            return
        sess_by_id = {s["id"]: s for s in sessions}
        ext_rows = (
            supabase.table("medical_extractions")
            .select("id, session_id, patient_id, original_extraction_json")
            .in_("session_id", list(sess_by_id.keys()))
            .execute()
            .data
            or []
        )
        for row in ext_rows:
            sess = sess_by_id.get(row["session_id"]) or {}
            yield row, sess
        if len(sessions) < page_size:
            return
        page += 1


def main() -> None:
    template_map = _fetch_template_map()
    radiology_codes = [c for c in template_map if c.startswith("RS_")]
    if not radiology_codes:
        logger.warning("No radiology templates with letter_template_jinja found.")
        return

    logger.info(f"Backfilling for templates: {sorted(radiology_codes)}")

    seen = updated = skipped = failed = 0
    for ext, sess in _iter_extractions(radiology_codes):
        seen += 1
        ext_id = ext["id"]
        insights = ext.get("original_extraction_json") or {}
        if not isinstance(insights, dict):
            logger.warning(f"[{ext_id}] original_extraction_json not a dict; skipping")
            skipped += 1
            continue

        template_id = template_map.get(sess.get("template_code"))
        if not template_id:
            skipped += 1
            continue

        patient_id = ext.get("patient_id") or sess.get("patient_id")
        old_letter = insights.get("consult_letter") or ""

        try:
            attach_letter_artifacts(
                insights,
                template_id,
                patient_id,
                session_record=sess,
            )
        except Exception as e:
            logger.warning(f"[{ext_id}] attach_letter_artifacts raised: {e}")
            failed += 1
            continue

        new_letter = insights.get("consult_letter") or ""
        if new_letter == old_letter:
            skipped += 1
            continue

        try:
            supabase.table("medical_extractions").update(
                {"original_extraction_json": insights}
            ).eq("id", ext_id).execute()
            updated += 1
            logger.info(
                f"[{ext_id}] {sess.get('template_code')} letter "
                f"{len(old_letter)} → {len(new_letter)} chars"
            )
        except Exception as e:
            logger.warning(f"[{ext_id}] DB update failed: {e}")
            failed += 1

    logger.info(
        f"Done. Seen={seen}, Updated={updated}, Skipped(no-change)={skipped}, Failed={failed}"
    )


if __name__ == "__main__":
    main()

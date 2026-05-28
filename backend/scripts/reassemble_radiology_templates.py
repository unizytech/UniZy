"""One-off reassembly trigger for the 5 radiology templates.

Run after seeding the plan/toxicity libraries so that
templates.assembled_full_prompt has the {{LIBRARY_PLAN}} / {{LIBRARY_TOXICITY}}
placeholders substituted with the seeded content.

    cd backend && source venv/bin/activate && python -m scripts.reassemble_radiology_templates
"""

import asyncio
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from services.supabase_service import supabase  # noqa: E402
from services.template_assembly_service import trigger_reassembly_async  # noqa: E402

RADIOLOGY_TEMPLATE_CODES = ["RS_BREAST", "RS_GYN", "RS_HN", "RS_PROSTATE", "RS_RECTUM"]


async def main() -> None:
    rows = (
        supabase.table("templates")
        .select("id, template_code")
        .in_("template_code", RADIOLOGY_TEMPLATE_CODES)
        .execute()
        .data
        or []
    )
    if not rows:
        print("No radiology templates found.")
        return

    template_ids = [uuid.UUID(r["id"]) for r in rows]
    print(f"Reassembling {len(template_ids)} templates: {[r['template_code'] for r in rows]}")
    await trigger_reassembly_async(
        template_ids,
        trigger_source="radiology_seed_initial",
        include_audio=False,
    )
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Backfill Embeddings Script

One-time script to embed all existing extractions for the Q&A Engine.
Run this after enabling the Q&A feature to populate the embedding tables.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/backfill_embeddings.py [--school-id UUID] [--batch-size N] [--dry-run]

Options:
    --school-id UUID    Only process extractions for this school
    --batch-size N        Number of extractions to process per batch (default: 50)
    --dry-run             Count extractions without processing
    --force               Re-embed even if embedding already exists
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime
from uuid import UUID

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.supabase_service import supabase
from services.qa.embedding_service import embedding_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def count_extractions(school_id: UUID = None, exclude_embedded: bool = True) -> dict:
    """Count extractions to process"""

    # Count total extractions
    query = supabase.table("extractions").select("id", count="exact")
    if school_id:
        query = query.eq("school_id", str(school_id))

    total_result = query.execute()
    total_count = total_result.count or 0

    # Count already embedded
    embedded_query = supabase.table("extraction_embeddings").select("extraction_id", count="exact")
    if school_id:
        # Join with extractions to filter by school
        embedded_result = supabase.rpc(
            "count_embedded_extractions_for_hospital",
            {"p_hospital_id": str(school_id)}
        ).execute()
        embedded_count = embedded_result.data if embedded_result.data else 0
    else:
        embedded_result = embedded_query.execute()
        embedded_count = embedded_result.count or 0

    pending_count = max(0, total_count - embedded_count) if exclude_embedded else total_count

    return {
        "total": total_count,
        "already_embedded": embedded_count,
        "pending": pending_count
    }


async def fetch_extraction_ids(
    school_id: UUID = None,
    exclude_embedded: bool = True,
    batch_size: int = 50,
    offset: int = 0
) -> list:
    """Fetch extraction IDs to process"""

    if exclude_embedded:
        # Get IDs not in extraction_embeddings
        # Using a raw query approach since Supabase Python client doesn't support NOT IN directly
        query = supabase.table("extractions").select("id")
        if school_id:
            query = query.eq("school_id", str(school_id))

        query = query.order("created_at", desc=True).range(offset, offset + batch_size - 1)
        result = query.execute()

        all_ids = [row["id"] for row in (result.data or [])]

        # Filter out already embedded
        if all_ids:
            embedded_result = supabase.table("extraction_embeddings")\
                .select("extraction_id")\
                .in_("extraction_id", all_ids)\
                .execute()

            embedded_ids = set(row["extraction_id"] for row in (embedded_result.data or []))
            return [id for id in all_ids if id not in embedded_ids]
        return []
    else:
        query = supabase.table("extractions").select("id")
        if school_id:
            query = query.eq("school_id", str(school_id))

        query = query.order("created_at", desc=True).range(offset, offset + batch_size - 1)
        result = query.execute()

        return [row["id"] for row in (result.data or [])]


async def backfill_embeddings(
    school_id: UUID = None,
    batch_size: int = 50,
    force: bool = False,
    dry_run: bool = False
):
    """Main backfill function"""

    logger.info("=" * 60)
    logger.info("Q&A Engine Embedding Backfill")
    logger.info("=" * 60)

    # Count extractions
    counts = await count_extractions(school_id, exclude_embedded=not force)

    logger.info(f"Total extractions: {counts['total']}")
    logger.info(f"Already embedded: {counts['already_embedded']}")
    logger.info(f"Pending: {counts['pending']}")

    if school_id:
        logger.info(f"Filtering by school: {school_id}")

    if dry_run:
        logger.info("DRY RUN - No embeddings will be generated")
        return

    if counts['pending'] == 0:
        logger.info("No extractions to process. Exiting.")
        return

    # Process in batches
    processed = 0
    succeeded = 0
    failed = 0
    offset = 0

    start_time = datetime.now()

    while True:
        # Fetch batch
        extraction_ids = await fetch_extraction_ids(
            school_id=school_id,
            exclude_embedded=not force,
            batch_size=batch_size,
            offset=offset
        )

        if not extraction_ids:
            break

        logger.info(f"Processing batch of {len(extraction_ids)} extractions...")

        for ext_id in extraction_ids:
            try:
                result = await embedding_service.embed_extraction(
                    extraction_id=UUID(ext_id),
                    force=force
                )

                if result and not result.get("error"):
                    succeeded += 1
                    if succeeded % 10 == 0:
                        logger.info(f"Progress: {succeeded} succeeded, {failed} failed")
                else:
                    failed += 1
                    logger.warning(f"Failed to embed {ext_id}: {result.get('error', 'Unknown error')}")

            except Exception as e:
                failed += 1
                logger.error(f"Exception embedding {ext_id}: {e}")

            processed += 1

            # Rate limiting delay
            await asyncio.sleep(0.2)

        offset += batch_size

        # Safety check to prevent infinite loop
        if offset > counts['total']:
            break

    # Summary
    elapsed = (datetime.now() - start_time).total_seconds()

    logger.info("=" * 60)
    logger.info("BACKFILL COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total processed: {processed}")
    logger.info(f"Succeeded: {succeeded}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Time elapsed: {elapsed:.1f} seconds")
    logger.info(f"Rate: {processed / elapsed:.2f} extractions/second" if elapsed > 0 else "N/A")


def main():
    parser = argparse.ArgumentParser(
        description="Backfill embeddings for existing extractions"
    )
    parser.add_argument(
        "--school-id",
        type=str,
        help="Only process extractions for this school UUID"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of extractions to process per batch (default: 50)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count extractions without processing"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed even if embedding already exists"
    )

    args = parser.parse_args()

    school_id = UUID(args.school_id) if args.school_id else None

    asyncio.run(backfill_embeddings(
        school_id=school_id,
        batch_size=args.batch_size,
        force=args.force,
        dry_run=args.dry_run
    ))


if __name__ == "__main__":
    main()

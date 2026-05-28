"""
Embedding Job Service

Background job management for embedding operations:
- Queue re-embedding for hospital
- Embed single extraction
- Track embedding progress
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class EmbeddingJobService:
    """
    Manages background embedding jobs.

    Usage:
        service = EmbeddingJobService()

        # Queue re-embedding for hospital
        job_id = await service.queue_reembedding_job(hospital_id)

        # Embed single extraction
        await service.reembed_single_extraction(extraction_id)
    """

    # Track running jobs
    _running_jobs: Dict[str, Dict[str, Any]] = {}

    def __init__(self):
        from .embedding_service import embedding_service
        self._embedding_service = embedding_service

    async def queue_reembedding_job(
        self,
        hospital_id: UUID,
        model_code: Optional[str] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Queue a background job to re-embed all extractions for a hospital.

        Args:
            hospital_id: Hospital ID
            model_code: Optional specific model to use
            force: If True, re-embed even if hash unchanged

        Returns:
            Dict with job_id and status
        """
        from services.supabase_service import supabase

        job_id = f"reembed_{hospital_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        # Check if job already running for this hospital
        for existing_job_id, job in self._running_jobs.items():
            if job.get("hospital_id") == str(hospital_id) and job.get("status") == "running":
                return {
                    "success": False,
                    "message": "Re-embedding job already in progress for this hospital",
                    "existing_job_id": existing_job_id
                }

        # Count extractions to process
        count_result = supabase.table("medical_extractions")\
            .select("id", count="exact")\
            .eq("hospital_id", str(hospital_id))\
            .execute()

        extraction_count = count_result.count or 0

        if extraction_count == 0:
            return {
                "success": True,
                "message": "No extractions to embed",
                "extraction_count": 0
            }

        # Create job record
        self._running_jobs[job_id] = {
            "hospital_id": str(hospital_id),
            "model_code": model_code,
            "status": "running",
            "total": extraction_count,
            "completed": 0,
            "failed": 0,
            "started_at": datetime.now(timezone.utc).isoformat()
        }

        # Start background task
        asyncio.create_task(
            self._run_reembedding_job(job_id, hospital_id, model_code, force)
        )

        return {
            "success": True,
            "job_id": job_id,
            "message": f"Re-embedding job started for {extraction_count} extractions",
            "extraction_count": extraction_count
        }

    async def _run_reembedding_job(
        self,
        job_id: str,
        hospital_id: UUID,
        model_code: Optional[str],
        force: bool
    ):
        """Run the re-embedding job in background"""
        from services.supabase_service import supabase

        try:
            # Fetch all extraction IDs
            result = supabase.table("medical_extractions")\
                .select("id")\
                .eq("hospital_id", str(hospital_id))\
                .execute()

            extraction_ids = [row["id"] for row in (result.data or [])]

            for ext_id in extraction_ids:
                try:
                    await self._embedding_service.embed_extraction(
                        extraction_id=UUID(ext_id),
                        force=force
                    )
                    self._running_jobs[job_id]["completed"] += 1
                except Exception as e:
                    logger.error(f"Failed to embed extraction {ext_id}: {e}")
                    self._running_jobs[job_id]["failed"] += 1

                # Small delay to avoid rate limiting
                await asyncio.sleep(0.1)

            self._running_jobs[job_id]["status"] = "completed"
            self._running_jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

            logger.info(
                f"Re-embedding job {job_id} completed: "
                f"{self._running_jobs[job_id]['completed']} succeeded, "
                f"{self._running_jobs[job_id]['failed']} failed"
            )

        except Exception as e:
            logger.error(f"Re-embedding job {job_id} failed: {e}", exc_info=True)
            self._running_jobs[job_id]["status"] = "failed"
            self._running_jobs[job_id]["error"] = str(e)

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a re-embedding job"""
        return self._running_jobs.get(job_id)

    def list_jobs(self, hospital_id: Optional[UUID] = None) -> List[Dict[str, Any]]:
        """List all jobs, optionally filtered by hospital"""
        jobs = []
        for job_id, job in self._running_jobs.items():
            if hospital_id and job.get("hospital_id") != str(hospital_id):
                continue
            jobs.append({"job_id": job_id, **job})
        return jobs


async def reembed_single_extraction(extraction_id: UUID) -> Optional[Dict[str, Any]]:
    """
    Convenience function to embed a single extraction.

    Called after extraction save to update embeddings.

    Args:
        extraction_id: The extraction UUID to embed

    Returns:
        Embedding result or None if failed
    """
    from .embedding_service import embedding_service

    try:
        result = await embedding_service.embed_extraction(extraction_id, force=False)
        if result and not result.get("error"):
            logger.info(f"Successfully embedded extraction {extraction_id}")
        return result
    except Exception as e:
        logger.error(f"Failed to embed extraction {extraction_id}: {e}")
        return {"error": str(e)}


async def schedule_extraction_embedding(extraction_id: UUID) -> None:
    """
    Schedule embedding generation for an extraction (fire-and-forget).

    Waits for extraction to exist in DB before generating embeddings,
    since extraction save is also fire-and-forget.

    This is designed to be called via asyncio.create_task() for zero latency impact.

    Args:
        extraction_id: The extraction UUID to embed
    """
    from services.supabase_service import supabase
    from .embedding_service import embedding_service

    # Wait for extraction to exist (max 30 seconds with exponential backoff)
    max_retries = 10
    base_delay = 0.5  # Start with 500ms

    for attempt in range(max_retries):
        try:
            result = supabase.table("medical_extractions")\
                .select("id")\
                .eq("id", str(extraction_id))\
                .single()\
                .execute()

            if result.data:
                # Extraction exists, generate embedding
                break
        except Exception:
            pass

        # Exponential backoff: 0.5s, 1s, 2s, 4s, ...
        delay = base_delay * (2 ** attempt)
        if delay > 5:
            delay = 5  # Cap at 5 seconds
        await asyncio.sleep(delay)
    else:
        logger.warning(
            f"[EMBEDDING_JOB] Extraction {extraction_id} not found after {max_retries} retries, skipping embedding"
        )
        return

    # Small delay to ensure all segments are saved
    await asyncio.sleep(0.5)

    # Generate embedding (fire-and-forget style - errors logged but not raised)
    try:
        result = await embedding_service.embed_extraction(extraction_id, force=False)
        if result and not result.get("error"):
            logger.info(f"[EMBEDDING_JOB] Successfully embedded extraction {extraction_id}")
        elif result and result.get("error"):
            logger.warning(f"[EMBEDDING_JOB] Embedding failed for {extraction_id}: {result.get('error')}")
    except Exception as e:
        logger.error(f"[EMBEDDING_JOB] Failed to embed extraction {extraction_id}: {e}")


# Singleton instance
embedding_job_service = EmbeddingJobService()

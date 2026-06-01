"""
Nudge API Service for sending extraction data to the Nudge /api/v1/ingest endpoint.

After extraction, emotion analysis, and intervention generation complete in the pipeline,
this service sends each result as a fire-and-forget POST. Nudge accumulates data per
extraction_id server-side, so three separate calls (medical_records, emotions, interventions)
merge automatically.

All calls are async and fail-silent to avoid any pipeline latency impact.
"""

import os
import asyncio
import logging
import uuid as uuid_module
from typing import Dict, Any, Optional
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


class NudgeApiService:
    """Service for sending data to the Nudge API ingest endpoint."""

    def __init__(self):
        self.api_url = os.getenv("NUDGE_API_URL", "")
        self.api_token = os.getenv("NUDGE_API_TOKEN", "")
        self.enabled = os.getenv("NUDGE_API_ENABLED", "false").lower() == "true"
        self.timeout = int(os.getenv("NUDGE_API_TIMEOUT", "10"))

        if self.enabled and not self.api_url:
            logger.warning("[NUDGE] Enabled but NUDGE_API_URL not configured — disabling")
            self.enabled = False

        if self.enabled:
            logger.info(
                f"[NUDGE] Service initialized: url={self.api_url}, "
                f"token={'configured' if self.api_token else 'not configured'}, "
                f"timeout={self.timeout}s"
            )
        else:
            logger.info("[NUDGE] Service disabled")

    async def _send_to_nudge(self, payload: Dict[str, Any], source: str) -> bool:
        """POST payload to Nudge /api/v1/ingest with retry logic. Returns True on 2xx."""
        if not self.enabled:
            return False

        url = f"{self.api_url.rstrip('/')}/api/v1/ingest"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AI-Live-Recorder/3.1.0",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        extraction_id = payload.get("extraction_id")
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        url,
                        json=payload,
                        timeout=self.timeout,
                        headers=headers,
                    )
                    response.raise_for_status()
                    logger.info(
                        f"[NUDGE] Accepted ({source}) — "
                        f"extraction_id={extraction_id}, "
                        f"status={response.status_code}, "
                        f"attempt={attempt}/{max_retries}"
                    )
                    return True
            except Exception as e:
                logger.warning(
                    f"[NUDGE] Failed ({source}) — "
                    f"extraction_id={extraction_id}, "
                    f"attempt={attempt}/{max_retries}: {e}"
                )
                if attempt < max_retries:
                    wait_time = 5 * attempt  # 5s, 10s
                    logger.debug(f"[NUDGE] Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)

        logger.warning(
            f"[NUDGE] All {max_retries} attempts failed ({source}) — "
            f"extraction_id={extraction_id}"
        )
        return False

    def _build_common_fields(
        self,
        extraction_id: str,
        student_id: Optional[str] = None,
        counsellor_id: Optional[str] = None,
        patient_name: Optional[str] = None,
        counsellor_name: Optional[str] = None,
        preferred_language: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build the common fields shared across all Nudge payloads."""
        fields: Dict[str, Any] = {"extraction_id": extraction_id}
        if student_id:
            fields["student_id"] = student_id
        if counsellor_id:
            fields["counsellor_id"] = counsellor_id
        if patient_name:
            fields["patient_name"] = patient_name
        if counsellor_name:
            fields["counsellor_name"] = counsellor_name
        if preferred_language:
            fields["preferred_language"] = preferred_language
        if metadata:
            fields["metadata"] = metadata
        return fields

    # ------------------------------------------------------------------
    # Payload builders
    # ------------------------------------------------------------------

    async def send_medical_records(
        self,
        extraction_id: str,
        full_extraction: Dict[str, Any],
        student_id: Optional[str] = None,
        counsellor_id: Optional[str] = None,
        template_code: Optional[str] = None,
        submission_id: Optional[str] = None,
    ) -> bool:
        """Send medical_records (full extraction JSON) to Nudge."""
        if not self.enabled:
            return False

        patient_name, counsellor_name, preferred_language = await _lookup_names(student_id, counsellor_id)

        payload = self._build_common_fields(
            extraction_id=extraction_id,
            student_id=student_id,
            counsellor_id=counsellor_id,
            patient_name=patient_name,
            counsellor_name=counsellor_name,
            preferred_language=preferred_language,
            metadata={
                "template_code": template_code,
                "source": "extraction",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )
        payload["medical_records"] = full_extraction
        if submission_id:
            payload["submission_id"] = submission_id

        return await self._send_to_nudge(payload, source="medical_records")

    async def send_emotions(
        self,
        extraction_id: str,
    ) -> bool:
        """Fetch unified emotion segments from DB and send to Nudge."""
        if not self.enabled:
            return False

        from services.supabase_service import get_extraction_by_id, supabase

        extraction = get_extraction_by_id(uuid_module.UUID(extraction_id))
        if not extraction:
            logger.warning(f"[NUDGE] Extraction not found for emotions: {extraction_id}")
            return False

        student_id = extraction.get("student_id")
        counsellor_id = extraction.get("counsellor_id")
        patient_name, counsellor_name, preferred_language = await _lookup_names(student_id, counsellor_id)

        # Fetch the unified emotion segment codes (counselling 3-speaker model) — single source
        from services.supabase_service import UNIFIED_EMOTION_SEGMENT_CODES as unified_emotion_codes

        segments_response = (
            supabase.table("extraction_segments")
            .select("segment_code, segment_value")
            .eq("extraction_id", extraction_id)
            .in_("segment_code", unified_emotion_codes)
            .execute()
        )

        emotions_data: Dict[str, Any] = {}
        for seg in segments_response.data or []:
            code = seg.get("segment_code")
            value = seg.get("segment_value")
            if code and value:
                emotions_data[code] = value

        if not emotions_data:
            logger.warning(f"[NUDGE] No emotion segments found for {extraction_id}")
            return False

        payload = self._build_common_fields(
            extraction_id=extraction_id,
            student_id=student_id,
            counsellor_id=counsellor_id,
            patient_name=patient_name,
            counsellor_name=counsellor_name,
            preferred_language=preferred_language,
            metadata={
                "source": "emotion_analysis",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )
        payload["emotions"] = emotions_data

        return await self._send_to_nudge(payload, source="emotions")

    async def send_interventions(
        self,
        extraction_id: str,
    ) -> bool:
        """Fetch categorized interventions from DB and send to Nudge."""
        if not self.enabled:
            return False

        from services.supabase_service import get_extraction_by_id, get_categorized_interventions

        extraction = get_extraction_by_id(uuid_module.UUID(extraction_id))
        if not extraction:
            logger.warning(f"[NUDGE] Extraction not found for interventions: {extraction_id}")
            return False

        student_id = extraction.get("student_id")
        counsellor_id = extraction.get("counsellor_id")
        patient_name, counsellor_name, preferred_language = await _lookup_names(student_id, counsellor_id)

        interventions = get_categorized_interventions(uuid_module.UUID(extraction_id))
        if not interventions:
            logger.warning(f"[NUDGE] No interventions found for {extraction_id}")
            return False

        # Map to Nudge format
        nudge_interventions = []
        for iv in interventions:
            nudge_interventions.append({
                "name": iv.get("intervention_code") or iv.get("intervention_name", ""),
                "priority": iv.get("priority_label", "MEDIUM"),
                "category": iv.get("intervention_category"),
                "action": iv.get("action_summary"),
                "reason": iv.get("reason"),
            })

        payload = self._build_common_fields(
            extraction_id=extraction_id,
            student_id=student_id,
            counsellor_id=counsellor_id,
            patient_name=patient_name,
            counsellor_name=counsellor_name,
            preferred_language=preferred_language,
            metadata={
                "source": "interventions",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )
        payload["interventions"] = nudge_interventions

        return await self._send_to_nudge(payload, source="interventions")


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

async def _lookup_names(
    student_id: Optional[str],
    counsellor_id: Optional[str],
) -> tuple:
    """Lookup student/counsellor display names + student preferred_language.

    Returns (patient_name, counsellor_name, preferred_language).
    """
    from services.supabase_service import supabase

    patient_name = None
    counsellor_name = None
    preferred_language = None

    try:
        if counsellor_id:
            doc_res = (
                supabase.table("counsellors")
                .select("full_name")
                .eq("id", counsellor_id)
                .limit(1)
                .execute()
            )
            if doc_res.data:
                counsellor_name = doc_res.data[0].get("full_name")
    except Exception as e:
        logger.debug(f"[NUDGE] Counsellor name lookup failed: {e}")

    try:
        if student_id:
            pat_res = (
                supabase.table("students")
                .select("full_name, preferred_language")
                .eq("id", student_id)
                .limit(1)
                .execute()
            )
            if pat_res.data:
                patient_name = pat_res.data[0].get("full_name")
                preferred_language = pat_res.data[0].get("preferred_language")
    except Exception as e:
        logger.debug(f"[NUDGE] Student name lookup failed: {e}")

    return patient_name, counsellor_name, preferred_language


# ------------------------------------------------------------------
# Global singleton
# ------------------------------------------------------------------

nudge_service = NudgeApiService()


# ------------------------------------------------------------------
# Fire-and-forget wrappers (called from hook points)
# ------------------------------------------------------------------

def send_nudge_medical_records(
    extraction_id: str,
    full_extraction: Dict[str, Any],
    student_id: Optional[str] = None,
    counsellor_id: Optional[str] = None,
    template_code: Optional[str] = None,
    submission_id: Optional[str] = None,
) -> None:
    """Fire-and-forget: send medical_records to Nudge after extraction."""
    if not nudge_service.enabled:
        return
    try:
        asyncio.create_task(
            nudge_service.send_medical_records(
                extraction_id=extraction_id,
                full_extraction=full_extraction,
                student_id=student_id,
                counsellor_id=counsellor_id,
                template_code=template_code,
                submission_id=submission_id,
            )
        )
        logger.debug(f"[NUDGE] Scheduled medical_records send for {extraction_id}")
    except Exception as e:
        logger.warning(f"[NUDGE] Failed to schedule medical_records: {e}")


def send_nudge_emotions(extraction_id: str) -> None:
    """Fire-and-forget: send emotions to Nudge after emotion analysis."""
    if not nudge_service.enabled:
        return
    try:
        asyncio.create_task(
            nudge_service.send_emotions(extraction_id=extraction_id)
        )
        logger.debug(f"[NUDGE] Scheduled emotions send for {extraction_id}")
    except Exception as e:
        logger.warning(f"[NUDGE] Failed to schedule emotions: {e}")


def send_nudge_interventions(extraction_id: str) -> None:
    """Fire-and-forget: send interventions to Nudge after intervention generation."""
    if not nudge_service.enabled:
        return
    try:
        asyncio.create_task(
            nudge_service.send_interventions(extraction_id=extraction_id)
        )
        logger.debug(f"[NUDGE] Scheduled interventions send for {extraction_id}")
    except Exception as e:
        logger.warning(f"[NUDGE] Failed to schedule interventions: {e}")

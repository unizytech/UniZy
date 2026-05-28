"""
Temporal Resolution Service

Resolves temporal references in user queries to actual dates and extraction IDs.
Examples:
- "last visit" -> most recent extraction for patient
- "January 15th" -> calculate date (current or previous year)
- "3 months ago" -> date arithmetic
- "first visit" -> patient's earliest extraction
"""

import logging
import re
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser
from dateutil.relativedelta import relativedelta

from models.qa_models import TemporalReference, TemporalReferenceType

logger = logging.getLogger(__name__)


class TemporalResolutionService:
    """
    Resolves temporal references to actual dates and extraction IDs.

    Usage:
        service = TemporalResolutionService()

        resolved = await service.resolve_references(
            references=[TemporalReference(type=TemporalReferenceType.RELATIVE_VISIT, raw_text="last visit", visit_offset=-1)],
            patient_id=patient_uuid,
            hospital_id=hospital_uuid
        )

        # resolved[0].resolved_date = datetime of last visit
        # resolved[0].resolved_extraction_id = UUID of that extraction
    """

    def __init__(self):
        self._supabase = None

    def _get_supabase(self):
        """Lazy load Supabase client"""
        if self._supabase is None:
            from services.supabase_service import supabase
            self._supabase = supabase
        return self._supabase

    async def resolve_references(
        self,
        references: List[TemporalReference],
        patient_id: UUID,
        hospital_id: UUID,
        doctor_id: Optional[UUID] = None,
        current_extraction_id: Optional[UUID] = None
    ) -> List[TemporalReference]:
        """
        Resolve temporal references to actual dates/extraction IDs.

        Args:
            references: List of temporal references to resolve
            patient_id: Patient UUID for visit lookups
            hospital_id: Hospital UUID for scoping
            doctor_id: Optional doctor filter
            current_extraction_id: Current extraction context (for "previous" resolution)

        Returns:
            List of TemporalReference with resolved_date and resolved_extraction_id populated
        """
        if not references:
            return []

        # Fetch patient visits for resolution
        visits = await self._get_patient_visits(
            patient_id=patient_id,
            hospital_id=hospital_id,
            doctor_id=doctor_id,
            limit=50  # Get enough history for most queries
        )

        resolved = []
        for ref in references:
            try:
                resolved_ref = await self._resolve_single_reference(
                    ref=ref,
                    visits=visits,
                    current_extraction_id=current_extraction_id
                )
                resolved.append(resolved_ref)
            except Exception as e:
                logger.warning(f"Failed to resolve temporal reference '{ref.raw_text}': {e}")
                resolved.append(ref)  # Return unresolved

        return resolved

    async def _get_patient_visits(
        self,
        patient_id: UUID,
        hospital_id: UUID,
        doctor_id: Optional[UUID] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Fetch patient's consultations ordered by date DESC.

        Returns list of dicts with:
        - extraction_id, created_at, consultation_type_name, doctor_name

        Note: medical_extractions doesn't have hospital_id column.
        Filters by hospital through doctors.hospital_id join.
        """
        try:
            supabase = self._get_supabase()

            query = supabase.table("medical_extractions")\
                .select(
                    "id, created_at, consultation_type_id, doctor_id, "
                    "consultation_types(type_name), doctors!inner(full_name, hospital_id)"
                )\
                .eq("patient_id", str(patient_id))\
                .eq("doctors.hospital_id", str(hospital_id))\
                .order("created_at", desc=True)\
                .limit(limit)

            if doctor_id:
                query = query.eq("doctor_id", str(doctor_id))

            result = query.execute()

            visits = []
            for row in (result.data or []):
                visits.append({
                    "extraction_id": row["id"],
                    "created_at": row["created_at"],
                    "consultation_type_name": row.get("consultation_types", {}).get("type_name") if row.get("consultation_types") else None,
                    "doctor_name": row.get("doctors", {}).get("full_name") if row.get("doctors") else None,
                    "doctor_id": row.get("doctor_id"),
                    "consultation_type_id": row.get("consultation_type_id")
                })

            return visits

        except Exception as e:
            logger.error(f"Failed to fetch patient visits: {e}")
            return []

    async def _resolve_single_reference(
        self,
        ref: TemporalReference,
        visits: List[Dict[str, Any]],
        current_extraction_id: Optional[UUID] = None
    ) -> TemporalReference:
        """Resolve a single temporal reference."""

        # Create a copy to avoid mutating the original
        resolved = TemporalReference(
            type=ref.type,
            raw_text=ref.raw_text,
            visit_offset=ref.visit_offset,
            resolved_date=ref.resolved_date,
            resolved_extraction_id=ref.resolved_extraction_id
        )

        if ref.type == TemporalReferenceType.RELATIVE_VISIT:
            # "last visit", "previous consultation"
            resolved = self._resolve_relative_visit(resolved, visits, current_extraction_id)

        elif ref.type == TemporalReferenceType.VISIT_NUMBER:
            # "first visit", "visit 3"
            resolved = self._resolve_visit_number(resolved, visits)

        elif ref.type == TemporalReferenceType.ABSOLUTE_DATE:
            # "January 15th", "2024-01-15"
            resolved = self._resolve_absolute_date(resolved, visits)

        elif ref.type == TemporalReferenceType.RELATIVE_TIME:
            # "last week", "3 months ago"
            resolved = self._resolve_relative_time(resolved, visits)

        elif ref.type == TemporalReferenceType.COMPARISON:
            # "compare with previous" - resolve to the comparison baseline
            resolved = self._resolve_comparison(resolved, visits, current_extraction_id)

        return resolved

    def _resolve_relative_visit(
        self,
        ref: TemporalReference,
        visits: List[Dict[str, Any]],
        current_extraction_id: Optional[UUID] = None
    ) -> TemporalReference:
        """Resolve relative visit references like 'last visit', 'previous consultation'."""

        if not visits:
            return ref

        offset = ref.visit_offset or -1  # Default to last visit

        # If we have a current extraction, find visits relative to it
        if current_extraction_id:
            current_idx = None
            for i, v in enumerate(visits):
                if str(v["extraction_id"]) == str(current_extraction_id):
                    current_idx = i
                    break

            if current_idx is not None:
                # Offset from current: -1 means the visit before current
                target_idx = current_idx - offset  # visits are DESC, so subtract offset
                if 0 <= target_idx < len(visits):
                    visit = visits[target_idx]
                    ref.resolved_extraction_id = UUID(visit["extraction_id"])
                    ref.resolved_date = datetime.fromisoformat(visit["created_at"].replace('Z', '+00:00'))
                return ref

        # No current context - resolve from most recent
        # offset -1 = index 0 (most recent)
        # offset -2 = index 1 (second most recent)
        target_idx = (-offset) - 1

        if 0 <= target_idx < len(visits):
            visit = visits[target_idx]
            ref.resolved_extraction_id = UUID(visit["extraction_id"])
            ref.resolved_date = datetime.fromisoformat(visit["created_at"].replace('Z', '+00:00'))

        return ref

    def _resolve_visit_number(
        self,
        ref: TemporalReference,
        visits: List[Dict[str, Any]]
    ) -> TemporalReference:
        """Resolve visit number references like 'first visit', 'visit 3'."""

        if not visits:
            return ref

        offset = ref.visit_offset or 1  # Default to first visit

        # visits are in DESC order, so reverse for numbered access
        # offset 1 = first visit (oldest) = last in DESC list
        # offset 2 = second visit = second to last
        if offset > 0:
            # Positive offset from oldest
            reversed_visits = list(reversed(visits))
            target_idx = offset - 1
            if 0 <= target_idx < len(reversed_visits):
                visit = reversed_visits[target_idx]
                ref.resolved_extraction_id = UUID(visit["extraction_id"])
                ref.resolved_date = datetime.fromisoformat(visit["created_at"].replace('Z', '+00:00'))
        else:
            # Negative offset from newest (same as relative visit)
            target_idx = (-offset) - 1
            if 0 <= target_idx < len(visits):
                visit = visits[target_idx]
                ref.resolved_extraction_id = UUID(visit["extraction_id"])
                ref.resolved_date = datetime.fromisoformat(visit["created_at"].replace('Z', '+00:00'))

        return ref

    def _resolve_absolute_date(
        self,
        ref: TemporalReference,
        visits: List[Dict[str, Any]]
    ) -> TemporalReference:
        """Resolve absolute date references like 'January 15th', '2024-01-15'."""

        try:
            # Parse the date from raw_text
            parsed_date = self._parse_date_text(ref.raw_text)
            if parsed_date:
                ref.resolved_date = parsed_date

                # Find the closest visit to this date
                closest_visit = self._find_closest_visit(parsed_date, visits)
                if closest_visit:
                    ref.resolved_extraction_id = UUID(closest_visit["extraction_id"])
        except Exception as e:
            logger.warning(f"Failed to parse absolute date '{ref.raw_text}': {e}")

        return ref

    def _resolve_relative_time(
        self,
        ref: TemporalReference,
        visits: List[Dict[str, Any]]
    ) -> TemporalReference:
        """Resolve relative time references like 'last week', '3 months ago'."""

        try:
            now = datetime.now(timezone.utc)
            parsed_date = self._parse_relative_time(ref.raw_text, now)

            if parsed_date:
                ref.resolved_date = parsed_date

                # Find visits on or after this date
                matching_visits = [
                    v for v in visits
                    if datetime.fromisoformat(v["created_at"].replace('Z', '+00:00')) >= parsed_date
                ]

                # Return the oldest matching (closest to the reference date)
                if matching_visits:
                    oldest_matching = min(
                        matching_visits,
                        key=lambda v: datetime.fromisoformat(v["created_at"].replace('Z', '+00:00'))
                    )
                    ref.resolved_extraction_id = UUID(oldest_matching["extraction_id"])
        except Exception as e:
            logger.warning(f"Failed to parse relative time '{ref.raw_text}': {e}")

        return ref

    def _resolve_comparison(
        self,
        ref: TemporalReference,
        visits: List[Dict[str, Any]],
        current_extraction_id: Optional[UUID] = None
    ) -> TemporalReference:
        """Resolve comparison references like 'compare with previous'."""

        # Typically resolves to the comparison baseline (previous visit)
        # Use relative visit resolution with offset -1
        ref.visit_offset = ref.visit_offset or -1
        return self._resolve_relative_visit(ref, visits, current_extraction_id)

    def _parse_date_text(self, text: str) -> Optional[datetime]:
        """Parse a date from natural language text."""

        text = text.lower().strip()
        now = datetime.now(timezone.utc)

        # Try dateutil parser first
        try:
            # Handle cases like "January 15th", "Jan 15"
            parsed = dateparser.parse(text, fuzzy=True)
            if parsed:
                # If no year specified and date is in future, assume previous year
                if parsed.year == now.year and parsed > now:
                    parsed = parsed.replace(year=now.year - 1)
                return parsed.replace(tzinfo=timezone.utc)
        except Exception:
            pass

        return None

    def _parse_relative_time(self, text: str, now: datetime) -> Optional[datetime]:
        """Parse relative time expressions like 'last week', '3 months ago'."""

        text = text.lower().strip()

        # Patterns for relative time
        patterns = [
            # "X days/weeks/months/years ago"
            (r'(\d+)\s*(day|days)\s*ago', lambda m: now - timedelta(days=int(m.group(1)))),
            (r'(\d+)\s*(week|weeks)\s*ago', lambda m: now - timedelta(weeks=int(m.group(1)))),
            (r'(\d+)\s*(month|months)\s*ago', lambda m: now - relativedelta(months=int(m.group(1)))),
            (r'(\d+)\s*(year|years)\s*ago', lambda m: now - relativedelta(years=int(m.group(1)))),

            # "last week/month/year"
            (r'last\s*week', lambda m: now - timedelta(weeks=1)),
            (r'last\s*month', lambda m: now - relativedelta(months=1)),
            (r'last\s*year', lambda m: now - relativedelta(years=1)),

            # "yesterday"
            (r'yesterday', lambda m: now - timedelta(days=1)),

            # "this week/month/year" - start of period
            (r'this\s*week', lambda m: now - timedelta(days=now.weekday())),
            (r'this\s*month', lambda m: now.replace(day=1)),
            (r'this\s*year', lambda m: now.replace(month=1, day=1)),
        ]

        for pattern, resolver in patterns:
            match = re.search(pattern, text)
            if match:
                return resolver(match)

        return None

    def _find_closest_visit(
        self,
        target_date: datetime,
        visits: List[Dict[str, Any]],
        tolerance_days: int = 3
    ) -> Optional[Dict[str, Any]]:
        """Find the visit closest to a target date within tolerance."""

        if not visits:
            return None

        closest = None
        min_diff = None

        for visit in visits:
            visit_date = datetime.fromisoformat(visit["created_at"].replace('Z', '+00:00'))
            diff = abs((visit_date - target_date).days)

            if diff <= tolerance_days:
                if min_diff is None or diff < min_diff:
                    min_diff = diff
                    closest = visit

        return closest


# Singleton instance
temporal_resolution_service = TemporalResolutionService()

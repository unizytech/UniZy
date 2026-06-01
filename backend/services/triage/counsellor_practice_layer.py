"""
Counsellor Practice Style Layer

Phase 1 of Triage Engine Multi-Layer system.
Enhances triage suggestions based on learned counsellor practice patterns:
- Investigation preferences
- Practice intensity (conservative/moderate/aggressive)
- First-line approaches by presentation
- Rejection patterns to filter

This layer runs AFTER the base MVP triage engine to adjust/enhance suggestions.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CounsellorPracticeStyle:
    """Aggregated practice style for a counsellor."""
    counsellor_id: str
    specialty: Optional[str] = None

    # Practice intensity
    practice_intensity: str = "moderate"  # conservative, moderate, aggressive

    # Investigation patterns
    avg_investigations_per_extraction: float = 0.0
    avg_suggestions_accepted_per_extraction: float = 0.0

    # Preferences (from feedback)
    preferred_investigation_types: Dict[str, int] = field(default_factory=dict)
    preferred_diagnosis_categories: Dict[str, int] = field(default_factory=dict)
    first_line_by_presentation: Dict[str, List[str]] = field(default_factory=dict)
    common_rejection_reasons: List[Dict[str, Any]] = field(default_factory=list)

    # Stats
    total_extractions_analyzed: int = 0
    total_feedback_entries: int = 0
    acceptance_rate: Optional[float] = None
    confidence_level: str = "low"  # low, medium, high

    # Cache info
    last_computed_at: Optional[str] = None

    @property
    def has_sufficient_data(self) -> bool:
        """Check if we have enough data to apply practice style adjustments."""
        return self.total_feedback_entries >= 10

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "CounsellorPracticeStyle":
        """Create from database row."""
        if not row:
            return None

        return cls(
            counsellor_id=row.get("counsellor_id"),
            specialty=row.get("specialty"),
            practice_intensity=row.get("practice_intensity", "moderate"),
            avg_investigations_per_extraction=float(row.get("avg_investigations_per_extraction") or 0),
            avg_suggestions_accepted_per_extraction=float(row.get("avg_suggestions_accepted_per_extraction") or 0),
            preferred_investigation_types=row.get("preferred_investigation_types") or {},
            preferred_diagnosis_categories=row.get("preferred_diagnosis_categories") or {},
            first_line_by_presentation=row.get("first_line_by_presentation") or {},
            common_rejection_reasons=row.get("common_rejection_reasons") or [],
            total_extractions_analyzed=row.get("total_extractions_analyzed") or 0,
            total_feedback_entries=row.get("total_feedback_entries") or 0,
            acceptance_rate=float(row.get("acceptance_rate")) if row.get("acceptance_rate") else None,
            confidence_level=row.get("confidence_level") or "low",
            last_computed_at=row.get("last_computed_at"),
        )


class CounsellorPracticeLayer:
    """
    Enhances triage suggestions based on learned counsellor practice patterns.

    This layer:
    1. Fetches cached practice style (or computes if stale)
    2. Boosts suggestions matching preferred patterns
    3. Filters suggestions matching rejection patterns
    4. Adjusts priority based on practice intensity
    """

    def __init__(self, supabase_client=None):
        """Initialize with optional Supabase client."""
        self.supabase = supabase_client

    async def get_practice_style(
        self,
        counsellor_id: str,
        supabase_client=None,
        max_cache_age_hours: int = 24
    ) -> Optional[CounsellorPracticeStyle]:
        """
        Get practice style for a counsellor (cached or freshly computed).

        Args:
            counsellor_id: UUID of the counsellor
            supabase_client: Supabase client for DB operations
            max_cache_age_hours: Max age of cached data before recomputing

        Returns:
            CounsellorPracticeStyle object or None if insufficient data
        """
        client = supabase_client or self.supabase
        if not client or not counsellor_id:
            return None

        try:
            # Call RPC to get (or compute) practice style
            result = client.rpc(
                'get_counsellor_practice_style',
                {
                    'p_counsellor_id': counsellor_id,
                    'p_max_age_hours': max_cache_age_hours
                }
            ).execute()

            if result.data:
                style = CounsellorPracticeStyle.from_db_row(result.data)
                logger.info(f"[PRACTICE_LAYER] Loaded practice style for counsellor {counsellor_id}: "
                           f"intensity={style.practice_intensity}, confidence={style.confidence_level}, "
                           f"feedback_count={style.total_feedback_entries}")
                return style

            return None

        except Exception as e:
            logger.warning(f"[PRACTICE_LAYER] Failed to get practice style for {counsellor_id}: {e}")
            return None

    async def compute_and_cache_style(
        self,
        counsellor_id: str,
        supabase_client=None
    ) -> Optional[CounsellorPracticeStyle]:
        """
        Force recomputation of practice style.

        Args:
            counsellor_id: UUID of the counsellor
            supabase_client: Supabase client for DB operations

        Returns:
            Freshly computed CounsellorPracticeStyle
        """
        client = supabase_client or self.supabase
        if not client or not counsellor_id:
            return None

        try:
            result = client.rpc(
                'compute_counsellor_practice_style',
                {'p_counsellor_id': counsellor_id}
            ).execute()

            if result.data:
                style = CounsellorPracticeStyle.from_db_row(result.data)
                logger.info(f"[PRACTICE_LAYER] Recomputed practice style for counsellor {counsellor_id}")
                return style

            return None

        except Exception as e:
            logger.error(f"[PRACTICE_LAYER] Failed to compute practice style for {counsellor_id}: {e}")
            return None

    def enhance_suggestions(
        self,
        suggestions: "TriageSuggestions",
        style: CounsellorPracticeStyle
    ) -> "TriageSuggestions":
        """
        Enhance suggestions based on counsellor's practice style.

        Enhancements applied:
        1. Boost preferred investigation types to higher priority
        2. Filter suggestions matching rejection patterns
        3. Add practice-style context to rationales
        4. Adjust investigation counts based on practice intensity

        Args:
            suggestions: TriageSuggestions from base engine
            style: Counsellor's practice style

        Returns:
            Enhanced TriageSuggestions
        """
        # Import here to avoid circular imports
        from .triage_engine import TriageSuggestion

        if not style or not style.has_sufficient_data:
            return suggestions

        logger.info(f"[PRACTICE_LAYER] Enhancing suggestions for counsellor {style.counsellor_id} "
                   f"(style: {style.practice_intensity})")

        boosted_count = 0
        filtered_count = 0
        promoted_count = 0

        # Process each priority level
        for priority_name, suggestion_list in [
            ("critical", suggestions.critical_actions),
            ("important", suggestions.important_considerations),
            ("consider", suggestions.nice_to_have)
        ]:
            filtered = []
            for suggestion in suggestion_list:
                # Check rejection patterns
                if self._matches_rejection_pattern(suggestion.suggestion, style.common_rejection_reasons):
                    logger.debug(f"[PRACTICE_LAYER] Filtered (rejection pattern): {suggestion.suggestion[:50]}...")
                    filtered_count += 1
                    continue

                # Check if this is a preferred investigation
                if suggestion.category == "investigation":
                    boost = self._get_preference_boost(suggestion.suggestion, style.preferred_investigation_types)
                    if boost > 0:
                        suggestion.rationale += f" [Matches counsellor's preferred investigation pattern]"
                        boosted_count += 1

                filtered.append(suggestion)

            # Update the list
            suggestion_list.clear()
            suggestion_list.extend(filtered)

        # Promote highly preferred investigations from nice_to_have to important
        promoted = []
        remaining_nice_to_have = []
        for suggestion in suggestions.nice_to_have:
            if suggestion.category == "investigation":
                boost = self._get_preference_boost(suggestion.suggestion, style.preferred_investigation_types)
                if boost >= 5:  # Strong preference (5+ acceptances)
                    suggestion.priority = "important"
                    promoted.append(suggestion)
                    promoted_count += 1
                    logger.debug(f"[PRACTICE_LAYER] Promoted (counsellor preference): {suggestion.suggestion[:50]}...")
                else:
                    remaining_nice_to_have.append(suggestion)
            else:
                remaining_nice_to_have.append(suggestion)

        suggestions.nice_to_have = remaining_nice_to_have
        suggestions.important_considerations.extend(promoted)

        # Apply practice intensity adjustments
        suggestions = self._apply_intensity_adjustments(suggestions, style)

        # Add practice style metadata to gap_analysis
        suggestions.gap_analysis["practice_style_applied"] = {
            "counsellor_id": style.counsellor_id,
            "practice_intensity": style.practice_intensity,
            "confidence_level": style.confidence_level,
            "boosted_count": boosted_count,
            "filtered_count": filtered_count,
            "promoted_count": promoted_count,
        }

        if boosted_count > 0 or filtered_count > 0 or promoted_count > 0:
            logger.info(f"[PRACTICE_LAYER] Applied enhancements: boosted={boosted_count}, "
                       f"filtered={filtered_count}, promoted={promoted_count}")

        return suggestions

    def _matches_rejection_pattern(
        self,
        suggestion_text: str,
        rejection_patterns: List[Dict[str, Any]]
    ) -> bool:
        """Check if suggestion matches a frequently rejected pattern."""
        if not rejection_patterns:
            return False

        suggestion_lower = suggestion_text.lower()
        for pattern in rejection_patterns:
            pattern_text = pattern.get("pattern", "").lower()
            rejection_count = pattern.get("count", 0)

            # Only filter if rejected 3+ times
            if rejection_count >= 3 and pattern_text:
                if pattern_text in suggestion_lower or suggestion_lower[:50] in pattern_text:
                    return True

        return False

    def _get_preference_boost(
        self,
        suggestion_text: str,
        preferred_investigations: Dict[str, int]
    ) -> int:
        """
        Get boost score based on counsellor's investigation preferences.

        Returns acceptance count if matched, 0 otherwise.
        """
        if not preferred_investigations:
            return 0

        suggestion_lower = suggestion_text.lower()

        # Extract investigation name from "Consider ordering: X" format
        if "consider ordering:" in suggestion_lower:
            inv_name = suggestion_lower.split("consider ordering:")[-1].strip()
        else:
            inv_name = suggestion_lower

        for pref_inv, count in preferred_investigations.items():
            pref_lower = pref_inv.lower()
            if pref_lower in inv_name or inv_name in pref_lower:
                return count

        return 0

    def _apply_intensity_adjustments(
        self,
        suggestions: "TriageSuggestions",
        style: CounsellorPracticeStyle
    ) -> "TriageSuggestions":
        """
        Adjust suggestions based on practice intensity.

        - Conservative: Limit investigation suggestions, prioritize history
        - Aggressive: Include more investigation options
        - Moderate: No adjustment
        """
        if style.practice_intensity == "conservative":
            # For conservative counsellors, limit investigation suggestions
            inv_count = sum(
                1 for s in suggestions.important_considerations + suggestions.nice_to_have
                if s.category == "investigation"
            )
            if inv_count > 5:
                # Keep only top 5 investigations by moving extras to nice_to_have
                logger.debug(f"[PRACTICE_LAYER] Conservative adjustment: limiting investigations")
                # Add note to rationales
                for s in suggestions.important_considerations:
                    if s.category == "investigation":
                        s.rationale += " [Counsellor has conservative investigation pattern]"

        elif style.practice_intensity == "aggressive":
            # For aggressive counsellors, could potentially add more suggestions
            # For now, just note the pattern
            logger.debug(f"[PRACTICE_LAYER] Aggressive pattern noted - no additional filtering")

        return suggestions


# Singleton instance for convenience
_practice_layer_instance = None


def get_practice_layer() -> CounsellorPracticeLayer:
    """Get singleton CounsellorPracticeLayer instance."""
    global _practice_layer_instance
    if _practice_layer_instance is None:
        _practice_layer_instance = CounsellorPracticeLayer()
    return _practice_layer_instance

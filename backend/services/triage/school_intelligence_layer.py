"""
School/Peer Intelligence Layer

Phase 2 of Triage Engine Multi-Layer system.
Provides peer intelligence and school-level pattern analysis:
- Same-specialty peer comparison
- School investigation patterns
- Outlier detection
- Benchmark recommendations

This layer runs AFTER the counsellor practice layer to add peer context.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SchoolPatterns:
    """Aggregated patterns for a school/specialty combination."""
    school_id: str
    specialty: str

    # Aggregated stats
    counsellor_count: int = 0
    total_extractions: int = 0
    total_suggestions: int = 0
    total_feedback: int = 0

    # Pattern data
    common_investigations: Dict[str, float] = field(default_factory=dict)
    common_diagnoses: Dict[str, float] = field(default_factory=dict)

    # Averages
    avg_suggestions_per_extraction: float = 0.0
    avg_acceptance_rate: float = 0.0

    # Percentile thresholds
    investigation_frequency_p25: Dict[str, float] = field(default_factory=dict)
    investigation_frequency_p75: Dict[str, float] = field(default_factory=dict)

    # Intensity distribution
    intensity_distribution: Dict[str, int] = field(default_factory=dict)

    # Cache info
    last_computed_at: Optional[str] = None

    @property
    def has_sufficient_data(self) -> bool:
        """Check if we have enough data for meaningful comparisons."""
        return self.counsellor_count >= 3 and self.total_feedback >= 20

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> Optional["SchoolPatterns"]:
        """Create from database row."""
        if not row:
            return None

        return cls(
            school_id=row.get("school_id"),
            specialty=row.get("specialty"),
            counsellor_count=row.get("counsellor_count") or 0,
            total_extractions=row.get("total_extractions") or 0,
            total_suggestions=row.get("total_suggestions") or 0,
            total_feedback=row.get("total_feedback") or 0,
            common_investigations=row.get("common_investigations") or {},
            common_diagnoses=row.get("common_diagnoses") or {},
            avg_suggestions_per_extraction=float(row.get("avg_suggestions_per_extraction") or 0),
            avg_acceptance_rate=float(row.get("avg_acceptance_rate") or 0),
            investigation_frequency_p25=row.get("investigation_frequency_p25") or {},
            investigation_frequency_p75=row.get("investigation_frequency_p75") or {},
            intensity_distribution=row.get("intensity_distribution") or {},
            last_computed_at=row.get("last_computed_at"),
        )


@dataclass
class PeerComparison:
    """Comparison metrics against peers."""
    counsellor_id: str
    metrics: List[Dict[str, Any]] = field(default_factory=list)
    outliers: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def has_outliers(self) -> bool:
        """Check if counsellor has any outlier metrics."""
        return len(self.outliers) > 0

    @classmethod
    def from_db_rows(cls, counsellor_id: str, rows: List[Dict[str, Any]]) -> "PeerComparison":
        """Create from database rows."""
        comparison = cls(counsellor_id=counsellor_id)

        for row in rows or []:
            metric_data = {
                "metric": row.get("metric"),
                "doctor_value": float(row.get("doctor_value") or 0),
                "peer_avg": float(row.get("peer_avg") or 0),
                "peer_p25": float(row.get("peer_p25") or 0),
                "peer_p75": float(row.get("peer_p75") or 0),
                "is_outlier": row.get("is_outlier", False),
                "outlier_direction": row.get("outlier_direction"),
            }
            comparison.metrics.append(metric_data)

            if metric_data["is_outlier"]:
                comparison.outliers.append(metric_data)

        return comparison


@dataclass
class OutlierFlag:
    """Flag for unusual pattern detected."""
    flag_type: str  # "below_peers", "above_peers", "missing_common_investigation"
    metric: str
    doctor_value: float
    peer_avg: float
    message: str
    severity: str = "info"  # info, warning, alert


class SchoolIntelligenceLayer:
    """
    Provides peer intelligence and school-level patterns.

    This layer:
    1. Fetches school patterns for counsellor's specialty
    2. Compares counsellor's patterns against peers
    3. Flags outlier behaviors (not necessarily bad)
    4. Adds peer context to suggestions
    """

    def __init__(self, supabase_client=None):
        """Initialize with optional Supabase client."""
        self.supabase = supabase_client

    async def get_school_patterns(
        self,
        school_id: str,
        specialty: str,
        supabase_client=None,
        force_recompute: bool = False
    ) -> Optional[SchoolPatterns]:
        """
        Get school patterns for a specialty.

        Args:
            school_id: UUID of the school
            specialty: Counsellor specialty (e.g., "general_medicine")
            supabase_client: Supabase client for DB operations
            force_recompute: Force fresh computation

        Returns:
            SchoolPatterns object or None
        """
        client = supabase_client or self.supabase
        if not client or not school_id or not specialty:
            return None

        try:
            if force_recompute:
                # Force recompute
                result = client.rpc(
                    'compute_school_specialty_patterns',
                    {
                        'p_school_id': school_id,
                        'p_specialty': specialty
                    }
                ).execute()
            else:
                # Try to get cached patterns
                result = client.table("school_specialty_patterns").select("*").eq(
                    "school_id", school_id
                ).eq("specialty", specialty).single().execute()

            if result.data:
                patterns = SchoolPatterns.from_db_row(result.data)
                logger.info(f"[HOSPITAL_LAYER] Loaded patterns for {school_id}/{specialty}: "
                           f"counsellors={patterns.counsellor_count}, extractions={patterns.total_extractions}")
                return patterns

            # No cached data - try to compute
            result = client.rpc(
                'compute_school_specialty_patterns',
                {
                    'p_school_id': school_id,
                    'p_specialty': specialty
                }
            ).execute()

            if result.data:
                return SchoolPatterns.from_db_row(result.data)

            return None

        except Exception as e:
            logger.warning(f"[HOSPITAL_LAYER] Failed to get school patterns: {e}")
            return None

    async def get_peer_comparison(
        self,
        counsellor_id: str,
        supabase_client=None
    ) -> Optional[PeerComparison]:
        """
        Get peer comparison metrics for a counsellor.

        Args:
            counsellor_id: UUID of the counsellor
            supabase_client: Supabase client for DB operations

        Returns:
            PeerComparison object or None
        """
        client = supabase_client or self.supabase
        if not client or not counsellor_id:
            return None

        try:
            result = client.rpc(
                'get_peer_comparison',
                {'p_counsellor_id': counsellor_id}
            ).execute()

            if result.data:
                comparison = PeerComparison.from_db_rows(counsellor_id, result.data)
                if comparison.has_outliers:
                    logger.info(f"[HOSPITAL_LAYER] Counsellor {counsellor_id} has {len(comparison.outliers)} outlier metrics")
                return comparison

            return None

        except Exception as e:
            logger.warning(f"[HOSPITAL_LAYER] Failed to get peer comparison: {e}")
            return None

    def detect_outliers(
        self,
        suggestions: "TriageSuggestions",
        patterns: SchoolPatterns,
        counsellor_style: Optional["CounsellorPracticeStyle"] = None
    ) -> List[OutlierFlag]:
        """
        Detect outlier patterns in suggestions compared to school norms.

        Args:
            suggestions: Current triage suggestions
            patterns: School patterns for comparison
            counsellor_style: Optional counsellor's practice style

        Returns:
            List of OutlierFlag objects
        """
        flags = []

        if not patterns or not patterns.has_sufficient_data:
            return flags

        # Count investigation suggestions
        inv_count = sum(
            1 for s in (
                suggestions.critical_actions +
                suggestions.important_considerations +
                suggestions.nice_to_have
            )
            if s.category == "investigation"
        )

        # Check if investigation count is outlier
        avg = patterns.avg_suggestions_per_extraction
        if avg > 0:
            if inv_count < avg * 0.5:
                flags.append(OutlierFlag(
                    flag_type="below_peers",
                    metric="investigation_count",
                    doctor_value=inv_count,
                    peer_avg=avg,
                    message=f"Fewer investigations ({inv_count}) than peer average ({avg:.1f})",
                    severity="info"
                ))
            elif inv_count > avg * 1.5:
                flags.append(OutlierFlag(
                    flag_type="above_peers",
                    metric="investigation_count",
                    doctor_value=inv_count,
                    peer_avg=avg,
                    message=f"More investigations ({inv_count}) than peer average ({avg:.1f})",
                    severity="info"
                ))

        # Check for commonly ordered investigations that are missing
        current_investigations = {
            s.suggestion.lower() for s in (
                suggestions.critical_actions +
                suggestions.important_considerations +
                suggestions.nice_to_have
            )
            if s.category == "investigation"
        }

        for inv_name, freq in patterns.common_investigations.items():
            if freq >= 0.7:  # 70%+ of peers order this
                # Check if this investigation is in current suggestions
                inv_lower = inv_name.lower()
                if not any(inv_lower in s for s in current_investigations):
                    flags.append(OutlierFlag(
                        flag_type="missing_common_investigation",
                        metric=f"investigation_{inv_name}",
                        doctor_value=0,
                        peer_avg=freq * 100,
                        message=f"{inv_name} ordered by {freq*100:.0f}% of peers but not suggested here",
                        severity="info"
                    ))

        return flags

    def enhance_with_peer_context(
        self,
        suggestions: "TriageSuggestions",
        patterns: SchoolPatterns,
        outlier_flags: Optional[List[OutlierFlag]] = None
    ) -> "TriageSuggestions":
        """
        Enhance suggestions with peer context information.

        Adds:
        1. Peer adoption rates to rationales for common investigations
        2. Notes about outlier patterns
        3. Peer comparison metadata in gap_analysis

        Args:
            suggestions: Current triage suggestions
            patterns: School patterns
            outlier_flags: Optional pre-computed outlier flags

        Returns:
            Enhanced TriageSuggestions
        """
        if not patterns or not patterns.has_sufficient_data:
            return suggestions

        enhanced_count = 0

        # Add peer adoption rates to investigation rationales
        for suggestion_list in [
            suggestions.critical_actions,
            suggestions.important_considerations,
            suggestions.nice_to_have
        ]:
            for suggestion in suggestion_list:
                if suggestion.category == "investigation":
                    # Check if this investigation has peer data
                    inv_name = self._extract_investigation_name(suggestion.suggestion)
                    if inv_name:
                        inv_lower = inv_name.lower()
                        for common_inv, freq in patterns.common_investigations.items():
                            if common_inv.lower() in inv_lower or inv_lower in common_inv.lower():
                                if freq >= 0.5:  # 50%+ peers use this
                                    suggestion.rationale += f" [Ordered by {freq*100:.0f}% of peers in this specialty]"
                                    enhanced_count += 1
                                break

        # Add peer intelligence metadata to gap_analysis
        suggestions.gap_analysis["hospital_intelligence_applied"] = {
            "school_id": patterns.school_id,
            "specialty": patterns.specialty,
            "peer_doctor_count": patterns.counsellor_count,
            "peer_avg_acceptance_rate": patterns.avg_acceptance_rate,
            "enhanced_count": enhanced_count,
            "outlier_flags": [
                {
                    "type": f.flag_type,
                    "metric": f.metric,
                    "message": f.message,
                    "severity": f.severity
                }
                for f in (outlier_flags or [])
            ]
        }

        if enhanced_count > 0:
            logger.info(f"[HOSPITAL_LAYER] Enhanced {enhanced_count} suggestions with peer context")

        return suggestions

    def _extract_investigation_name(self, suggestion_text: str) -> Optional[str]:
        """Extract investigation name from suggestion text."""
        if "consider ordering:" in suggestion_text.lower():
            return suggestion_text.split(":")[-1].strip()
        return None


class SchoolPatternAggregator:
    """
    Background job service for aggregating school patterns.

    Should be run periodically (daily) to update patterns.
    """

    def __init__(self, supabase_client=None):
        """Initialize with Supabase client."""
        self.supabase = supabase_client

    async def aggregate_all_patterns(
        self,
        supabase_client=None
    ) -> Dict[str, Any]:
        """
        Run aggregation for all school/specialty combinations.

        Args:
            supabase_client: Supabase client for DB operations

        Returns:
            Aggregation report
        """
        client = supabase_client or self.supabase
        if not client:
            return {"error": "No Supabase client available"}

        try:
            result = client.rpc('compute_all_school_patterns').execute()

            success_count = 0
            failure_count = 0
            total_counsellors = 0

            for row in result.data or []:
                if row.get("success"):
                    success_count += 1
                    total_counsellors += row.get("counsellor_count", 0)
                else:
                    failure_count += 1

            report = {
                "success": True,
                "patterns_computed": success_count,
                "patterns_failed": failure_count,
                "total_doctors_covered": total_counsellors,
                "details": result.data
            }

            logger.info(f"[HOSPITAL_AGGREGATOR] Completed: {success_count} success, {failure_count} failed, "
                       f"{total_counsellors} counsellors covered")

            return report

        except Exception as e:
            logger.error(f"[HOSPITAL_AGGREGATOR] Aggregation failed: {e}")
            return {"error": str(e), "success": False}


# Singleton instances for convenience
_hospital_layer_instance = None
_aggregator_instance = None


def get_school_intelligence_layer() -> SchoolIntelligenceLayer:
    """Get singleton SchoolIntelligenceLayer instance."""
    global _hospital_layer_instance
    if _hospital_layer_instance is None:
        _hospital_layer_instance = SchoolIntelligenceLayer()
    return _hospital_layer_instance


def get_school_aggregator() -> SchoolPatternAggregator:
    """Get singleton SchoolPatternAggregator instance."""
    global _aggregator_instance
    if _aggregator_instance is None:
        _aggregator_instance = SchoolPatternAggregator()
    return _aggregator_instance

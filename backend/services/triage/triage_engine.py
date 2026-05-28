"""
Triage Suggestion Engine

Main engine that generates clinical triage suggestions using:
1. StructuredInsights from extraction data
2. Differential diagnosis trees for clinical context
3. Gemini AI for gap analysis and prioritization

MVP: Uses hardcoded differential trees + configurable Gemini model
Phase 3: Will integrate RAG for evidence-based recommendations
"""

import os
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime

from google import genai
from google.genai import types
from dotenv import load_dotenv

from .structured_insights import StructuredInsights, map_extraction_with_patient_history
from .differential_trees import (
    get_differential,
    match_presentations,
    get_red_flags,
    get_first_line_investigations,
    get_history_essentials,
)

load_dotenv()
logger = logging.getLogger(__name__)

# Initialize Gemini client using factory (supports both Gemini API and Vertex AI)
try:
    from services.gemini_client_factory import get_gemini_client
    gemini_client = get_gemini_client()
except Exception as e:
    logger.warning(f"Gemini client initialization failed - triage engine will use fallback mode: {e}")
    gemini_client = None

# Default triage model (used as fallback if DB config unavailable)
DEFAULT_TRIAGE_MODEL = "gemini-2.5-flash"


# =============================================================================
# Triage Suggestions Dataclass
# =============================================================================

@dataclass
class TriageSuggestion:
    """A single triage suggestion with priority and rationale."""

    category: str  # "investigation", "history_question", "examination", "red_flag", "diagnosis_consider"
    suggestion: str  # The actual suggestion text
    priority: str  # "critical", "important", "consider"
    rationale: str  # Why this is suggested
    source: str  # "differential_tree", "gemini_analysis", "red_flag_match"
    related_presentation: Optional[str] = None  # Which presentation triggered this
    id: Optional[str] = None  # Suggestion ID from triage_suggestion_log (for feedback)


@dataclass
class TriageSuggestions:
    """
    Complete triage suggestions for a consultation.

    Organized by priority:
    - critical_actions: Must be done immediately (red flags, safety concerns)
    - important_considerations: Should be done (missing investigations, history gaps)
    - nice_to_have: Optional but recommended

    Also includes:
    - matched_presentations: Which differential trees were matched
    - identified_red_flags: Any red flags detected in the consultation
    - gap_analysis: What's missing from the ideal workup
    """

    # Priority-organized suggestions
    critical_actions: List[TriageSuggestion] = field(default_factory=list)
    important_considerations: List[TriageSuggestion] = field(default_factory=list)
    nice_to_have: List[TriageSuggestion] = field(default_factory=list)

    # Analysis results
    matched_presentations: List[str] = field(default_factory=list)
    identified_red_flags: List[str] = field(default_factory=list)
    differential_context: Dict[str, Any] = field(default_factory=dict)

    # Gap analysis from Gemini
    gap_analysis: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    specialty: str = ""
    consultation_type: str = ""
    generated_at: str = ""
    model_used: str = ""
    processing_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "critical_actions": [
                {
                    "category": s.category,
                    "suggestion": s.suggestion,
                    "priority": s.priority,
                    "rationale": s.rationale,
                    "source": s.source,
                    "related_presentation": s.related_presentation,
                }
                for s in self.critical_actions
            ],
            "important_considerations": [
                {
                    "category": s.category,
                    "suggestion": s.suggestion,
                    "priority": s.priority,
                    "rationale": s.rationale,
                    "source": s.source,
                    "related_presentation": s.related_presentation,
                }
                for s in self.important_considerations
            ],
            "nice_to_have": [
                {
                    "category": s.category,
                    "suggestion": s.suggestion,
                    "priority": s.priority,
                    "rationale": s.rationale,
                    "source": s.source,
                    "related_presentation": s.related_presentation,
                }
                for s in self.nice_to_have
            ],
            "matched_presentations": self.matched_presentations,
            "identified_red_flags": self.identified_red_flags,
            "differential_context": self.differential_context,
            "gap_analysis": self.gap_analysis,
            "specialty": self.specialty,
            "consultation_type": self.consultation_type,
            "generated_at": self.generated_at,
            "model_used": self.model_used,
            "processing_time_ms": self.processing_time_ms,
        }

    @property
    def total_suggestions(self) -> int:
        """Total number of suggestions across all priorities."""
        return len(self.critical_actions) + len(self.important_considerations) + len(self.nice_to_have)


# =============================================================================
# Doctor Preferences (Learned from Feedback)
# =============================================================================

@dataclass
class DoctorPreferences:
    """
    Learned preferences from doctor feedback on triage suggestions.

    Used to personalize suggestions:
    - Filter out frequently rejected suggestions
    - Boost frequently accepted suggestions
    - Apply modified text patterns
    """
    doctor_id: Optional[str] = None

    # Patterns to filter (rejected 2+ times)
    rejection_patterns: List[Dict[str, Any]] = field(default_factory=list)

    # Patterns to boost (accepted 3+ times)
    preference_patterns: List[Dict[str, Any]] = field(default_factory=list)

    # Full feedback history for fine-grained adjustments
    feedback_history: List[Dict[str, Any]] = field(default_factory=list)

    # Stats
    total_feedback_count: int = 0
    has_sufficient_data: bool = False  # True if 10+ feedback entries

    def should_filter(self, suggestion_text: str) -> bool:
        """Check if suggestion matches a rejection pattern."""
        if not self.rejection_patterns:
            return False

        normalized = suggestion_text.lower()[:100]
        for pattern in self.rejection_patterns:
            if pattern.get("suggestion_pattern", "") in normalized or normalized in pattern.get("suggestion_pattern", ""):
                # Check rejection count - filter if rejected 3+ times
                if pattern.get("rejection_count", 0) >= 3:
                    return True
        return False

    def get_boost_score(self, suggestion_text: str) -> int:
        """
        Get priority boost score for suggestion.
        Returns 0-20 based on acceptance history.
        """
        if not self.preference_patterns:
            return 0

        normalized = suggestion_text.lower()[:100]
        for pattern in self.preference_patterns:
            if pattern.get("suggestion_pattern", "") in normalized or normalized in pattern.get("suggestion_pattern", ""):
                acceptance_count = pattern.get("acceptance_count", 0)
                # 3-5 accepts = +5, 6-10 accepts = +10, 10+ accepts = +15
                if acceptance_count >= 10:
                    return 15
                elif acceptance_count >= 6:
                    return 10
                elif acceptance_count >= 3:
                    return 5
        return 0


async def fetch_doctor_preferences(doctor_id: str, supabase_client) -> DoctorPreferences:
    """
    Fetch learned preferences for a doctor from feedback history.

    Calls database functions:
    - get_doctor_rejection_patterns: Suggestions rejected 2+ times
    - get_doctor_preference_patterns: Suggestions accepted 3+ times
    - get_doctor_feedback_patterns: Full feedback history

    Args:
        doctor_id: UUID of the doctor
        supabase_client: Supabase client for DB operations

    Returns:
        DoctorPreferences object with learned patterns
    """
    preferences = DoctorPreferences(doctor_id=doctor_id)

    if not doctor_id or not supabase_client:
        return preferences

    try:
        # Fetch rejection patterns (suggestions to filter)
        rejection_result = supabase_client.rpc(
            'get_doctor_rejection_patterns',
            {'p_doctor_id': doctor_id}
        ).execute()

        if rejection_result.data:
            preferences.rejection_patterns = rejection_result.data
            logger.info(f"[TRIAGE_LEARN] Loaded {len(rejection_result.data)} rejection patterns for doctor {doctor_id}")

        # Fetch preference patterns (suggestions to boost)
        preference_result = supabase_client.rpc(
            'get_doctor_preference_patterns',
            {'p_doctor_id': doctor_id}
        ).execute()

        if preference_result.data:
            preferences.preference_patterns = preference_result.data
            logger.info(f"[TRIAGE_LEARN] Loaded {len(preference_result.data)} preference patterns for doctor {doctor_id}")

        # Fetch full feedback history for stats
        feedback_result = supabase_client.rpc(
            'get_doctor_feedback_patterns',
            {'p_doctor_id': doctor_id}
        ).execute()

        if feedback_result.data:
            preferences.feedback_history = feedback_result.data
            preferences.total_feedback_count = len(feedback_result.data)
            preferences.has_sufficient_data = preferences.total_feedback_count >= 10
            logger.info(f"[TRIAGE_LEARN] Doctor {doctor_id} has {preferences.total_feedback_count} feedback entries")

    except Exception as e:
        logger.warning(f"[TRIAGE_LEARN] Failed to fetch doctor preferences: {e}")

    return preferences


# =============================================================================
# Triage Suggestion Engine
# =============================================================================

class TriageSuggestionEngine:
    """
    Main engine for generating clinical triage suggestions.

    Process:
    1. Match chief complaints to known presentations
    2. Extract relevant differential trees
    3. Check for red flags in current data
    4. Identify gaps in history/investigations
    5. Use Gemini for intelligent prioritization
    """

    def __init__(self, gemini_client_override=None):
        """
        Initialize engine.

        Args:
            gemini_client_override: Optional Gemini client for testing
        """
        self.client = gemini_client_override or gemini_client

    def generate_tree_suggestions(
        self,
        insights: StructuredInsights,
    ) -> TriageSuggestions:
        """
        Generate triage suggestions using ONLY differential trees (fast cache layer).

        This method provides instant suggestions (~5ms) without any LLM calls.
        Used as the first layer in the multi-layer pipeline.

        Key outputs:
        - Red flags from tree matching (ALWAYS safety-critical)
        - Missing investigations based on presentation
        - Missing history questions

        Args:
            insights: StructuredInsights object from extraction

        Returns:
            TriageSuggestions from tree-based analysis only
        """
        import time
        start_time = time.time()

        suggestions = TriageSuggestions(
            specialty=insights.specialty,
            consultation_type=insights.consultation_type_code,
            generated_at=datetime.utcnow().isoformat(),
            model_used="differential_tree_cache",
        )

        # Step 1: Match presentations from chief complaints
        diagnoses_list = [
            d.get("diagnosis", "") if isinstance(d, dict) else str(d)
            for d in insights.diagnoses_discussed
        ]

        matched = match_presentations(
            chief_complaints=insights.chief_complaints,
            specialty=insights.specialty,
            diagnoses=diagnoses_list
        )
        suggestions.matched_presentations = matched

        logger.debug(f"[TRIAGE_TREE] Matched presentations for {insights.specialty}: {matched}")

        # Step 2: Build differential context from matched presentations
        differential_context = {}
        all_red_flags = []
        all_investigations = []
        all_history_questions = []

        for presentation in matched:
            diff_data = get_differential(insights.specialty, presentation)
            if diff_data:
                differential_context[presentation] = diff_data
                all_red_flags.extend(get_red_flags(insights.specialty, presentation))
                all_investigations.extend(get_first_line_investigations(insights.specialty, presentation))
                all_history_questions.extend(get_history_essentials(insights.specialty, presentation))

        suggestions.differential_context = differential_context

        # Step 3: Check for red flags in current data (SAFETY-CRITICAL)
        identified_red_flags = self._check_red_flags(insights, all_red_flags)
        suggestions.identified_red_flags = identified_red_flags

        # Build patient context string for rationales
        patient_context_parts = []
        if insights.patient_age:
            patient_context_parts.append(f"{insights.patient_age}")
        if insights.patient_gender:
            patient_context_parts.append(insights.patient_gender.lower())
        patient_desc = " ".join(patient_context_parts) if patient_context_parts else "patient"

        cc_summary = ", ".join(insights.chief_complaints[:2]) if insights.chief_complaints else "current symptoms"
        diagnoses_summary = ", ".join([
            d.get("diagnosis", str(d)) if isinstance(d, dict) else str(d)
            for d in insights.diagnoses_discussed[:2]
        ]) if insights.diagnoses_discussed else None

        # Add critical actions for identified red flags
        for red_flag in identified_red_flags:
            rationale = f"Red flag in {patient_desc} with {cc_summary}. Immediate assessment needed."
            suggestions.critical_actions.append(TriageSuggestion(
                category="red_flag",
                suggestion=f"RED FLAG DETECTED: {red_flag}",
                priority="critical",
                rationale=rationale,
                source="differential_tree_cache",
            ))

        # Step 4: Identify missing investigations
        missing_investigations = self._identify_missing_investigations(
            insights, all_investigations, matched
        )

        for inv in missing_investigations[:5]:  # Limit to top 5 investigations
            priority = "important" if inv.get("cost", "LOW") == "LOW" else "consider"
            # Build concise rationale
            base_rationale = inv.get("rationale", "")
            presentation = inv.get("presentation", "").replace("_", " ")
            if base_rationale:
                rationale = f"{patient_desc} with {cc_summary}: {base_rationale}"
            elif presentation:
                rationale = f"Evaluate differentials for {presentation}"
            else:
                rationale = f"Recommended for {cc_summary}"

            suggestions.important_considerations.append(TriageSuggestion(
                category="investigation",
                suggestion=f"Consider ordering: {inv['test']}",
                priority=priority,
                rationale=rationale,
                source="differential_tree_cache",
                related_presentation=inv.get("presentation"),
            ))

        # Step 5: Identify missing history elements
        missing_history = self._identify_missing_history(insights, all_history_questions)

        for question in missing_history[:3]:  # Limit to top 3
            rationale = f"Helps differentiate diagnoses for {cc_summary}"
            suggestions.nice_to_have.append(TriageSuggestion(
                category="history_question",
                suggestion=f"Ask about: {question}",
                priority="consider",
                rationale=rationale,
                source="differential_tree_cache",
            ))

        # Calculate processing time
        suggestions.processing_time_ms = int((time.time() - start_time) * 1000)

        # Deduplicate
        self._deduplicate_suggestions(suggestions)

        logger.info(f"[TRIAGE_TREE] Generated {suggestions.total_suggestions} tree suggestions in {suggestions.processing_time_ms}ms")

        return suggestions

    async def generate_suggestions(
        self,
        insights: StructuredInsights,
        include_gemini_analysis: bool = True,
        extraction_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        skip_trees: bool = False,
        rag_context: Optional[Dict[str, Any]] = None,
    ) -> TriageSuggestions:
        """
        Generate triage suggestions for a consultation.

        Args:
            insights: StructuredInsights object from extraction
            include_gemini_analysis: Whether to use Gemini for gap analysis (default True)
            extraction_id: Optional extraction UUID for usage logging
            doctor_id: Optional doctor UUID for usage logging
            skip_trees: If True, skip tree-based suggestions (used when orchestrator handles trees separately)
            rag_context: Optional RAG matches to pass to Gemini for context-aware analysis

        Returns:
            TriageSuggestions object with prioritized recommendations
        """
        import time
        start_time = time.time()

        # If skip_trees is True, start with empty suggestions (orchestrator handles trees separately)
        if skip_trees:
            suggestions = TriageSuggestions(
                specialty=insights.specialty,
                consultation_type=insights.consultation_type_code,
                generated_at=datetime.utcnow().isoformat(),
            )
            # Still need differential context for Gemini
            diagnoses_list = [
                d.get("diagnosis", "") if isinstance(d, dict) else str(d)
                for d in insights.diagnoses_discussed
            ]
            matched = match_presentations(
                chief_complaints=insights.chief_complaints,
                specialty=insights.specialty,
                diagnoses=diagnoses_list
            )
            suggestions.matched_presentations = matched

            differential_context = {}
            for presentation in matched:
                diff_data = get_differential(insights.specialty, presentation)
                if diff_data:
                    differential_context[presentation] = diff_data
            suggestions.differential_context = differential_context
        else:
            # Use tree-based suggestions as the base
            suggestions = self.generate_tree_suggestions(insights)

        # Step 6: Use Gemini for intelligent gap analysis (if enabled)
        if include_gemini_analysis and self.client:
            try:
                # Get triage model from database config
                from services.supabase_service import get_triage_model_by_mode
                triage_model = get_triage_model_by_mode("default")

                gemini_suggestions = await self._llm_gap_analysis(
                    insights, suggestions.differential_context, suggestions.matched_presentations,
                    extraction_id=extraction_id,
                    doctor_id=doctor_id,
                    triage_model=triage_model,
                    rag_context=rag_context,
                )
                suggestions.gap_analysis = gemini_suggestions
                suggestions.model_used = triage_model

                # Add Gemini suggestions to appropriate priority lists
                self._integrate_gemini_suggestions(suggestions, gemini_suggestions)

            except Exception as e:
                logger.error(f"[TRIAGE] Gemini analysis failed: {e}")
                suggestions.gap_analysis = {"error": str(e)}

        # Calculate processing time
        suggestions.processing_time_ms = int((time.time() - start_time) * 1000)

        # Deduplicate and sort suggestions
        self._deduplicate_suggestions(suggestions)

        return suggestions

    async def generate_suggestions_v2(
        self,
        extraction: Dict[str, Any],
        patient_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        consultation_type_code: Optional[str] = None,
        include_gemini_analysis: bool = True,
        log_suggestions: bool = True,
        supabase_client=None,
        skip_trees: bool = False,
        rag_context: Optional[Dict[str, Any]] = None,
        pre_mapped_insights=None,
    ) -> TriageSuggestions:
        """
        Enhanced triage with patient context awareness and doctor preference learning.

        This method:
        1. Fetches doctor preferences learned from past feedback
        2. Fetches patient historical context (allergies, chronic conditions, etc.)
        3. Generates base suggestions using existing MVP logic (or skips if orchestrator handles)
        4. Applies patient-specific filters (allergy vetos, cost sensitivity, etc.)
        5. Applies doctor preference filters (removes rejected, boosts accepted)
        6. Optionally logs suggestions to database for learning

        Args:
            extraction: Extraction record from database
            patient_id: Optional patient UUID for historical context
            doctor_id: Optional doctor UUID for suggestion logging and learning
            consultation_type_code: Optional consultation type code
            include_gemini_analysis: Whether to use Gemini AI for gap analysis
            log_suggestions: Whether to log suggestions to triage_suggestion_log
            supabase_client: Supabase client for DB operations
            skip_trees: If True, skip tree-based suggestions (orchestrator handles separately)
            rag_context: Optional RAG matches to pass to Gemini for context-aware analysis
            pre_mapped_insights: Optional pre-computed StructuredInsights (avoids duplicate DB call
                when orchestrator already fetched patient history in fast cache layer)

        Returns:
            TriageSuggestions with patient context and doctor preferences applied
        """
        import time
        start_time = time.time()

        # Step 0: Fetch doctor preferences (learned from feedback)
        doctor_preferences = None
        if doctor_id and supabase_client:
            doctor_preferences = await fetch_doctor_preferences(doctor_id, supabase_client)
            if doctor_preferences.has_sufficient_data:
                logger.info(f"[TRIAGE_V2] Using learned preferences for doctor {doctor_id} "
                           f"({doctor_preferences.total_feedback_count} feedback entries)")

        # Use pre-mapped insights if provided (from orchestrator's fast cache layer)
        if pre_mapped_insights is not None:
            insights = pre_mapped_insights
            logger.info(f"[TRIAGE_V2] Using pre-mapped insights (cached from fast cache layer)")
        elif patient_id and supabase_client:
            insights = await map_extraction_with_patient_history(
                extraction=extraction,
                patient_id=patient_id,
                supabase_client=supabase_client,
                consultation_type_code=consultation_type_code
            )
            logger.info(f"[TRIAGE_V2] Using patient history context for {patient_id}")
        else:
            # Fall back to basic mapping
            from .structured_insights import StructuredInsightsMapper
            mapper = StructuredInsightsMapper()
            insights = mapper.map_extraction(extraction, consultation_type_code)
            logger.info("[TRIAGE_V2] No patient_id provided, using basic insights")

        # Generate base suggestions using existing MVP logic
        suggestions = await self.generate_suggestions(
            insights=insights,
            include_gemini_analysis=include_gemini_analysis,
            extraction_id=extraction.get('id'),
            doctor_id=doctor_id,
            skip_trees=skip_trees,
            rag_context=rag_context,
        )

        # Apply patient context filters
        if patient_id and insights.patient_id:
            suggestions = self._apply_patient_context_filters(suggestions, insights)

        # Apply doctor preference learning (filter rejected, boost accepted)
        if doctor_preferences and doctor_preferences.has_sufficient_data:
            suggestions = self._apply_doctor_preferences(suggestions, doctor_preferences)

        # Update processing time
        suggestions.processing_time_ms = int((time.time() - start_time) * 1000)

        # Log suggestions to database if enabled
        if log_suggestions and supabase_client:
            await self._log_suggestions_to_db(
                suggestions=suggestions,
                extraction_id=extraction.get('id'),
                doctor_id=doctor_id,
                patient_context=insights.to_dict() if insights.patient_id else {},
                supabase_client=supabase_client
            )

        return suggestions

    def _apply_patient_context_filters(
        self,
        suggestions: TriageSuggestions,
        insights: StructuredInsights
    ) -> TriageSuggestions:
        """
        Filter/modify suggestions based on patient context.

        Applies:
        1. VETO: Skip suggestions mentioning drugs patient is allergic to
        2. Cost sensitivity notes for patients with financial concerns
        3. Anxiety-aware notes for patients with concerning anxiety patterns
        4. Compliance notes for patients with low compliance history
        5. Flag prior ineffective interventions
        """
        # Process each suggestion list
        suggestions.critical_actions = self._filter_suggestion_list(
            suggestions.critical_actions, insights, "critical"
        )
        suggestions.important_considerations = self._filter_suggestion_list(
            suggestions.important_considerations, insights, "important"
        )
        suggestions.nice_to_have = self._filter_suggestion_list(
            suggestions.nice_to_have, insights, "consider"
        )

        # Add psychosocial recommendations based on patient context
        psychosocial = self._generate_psychosocial_suggestions(insights)
        if psychosocial:
            suggestions.nice_to_have.extend(psychosocial)

        return suggestions

    def _apply_doctor_preferences(
        self,
        suggestions: TriageSuggestions,
        preferences: DoctorPreferences
    ) -> TriageSuggestions:
        """
        Apply learned doctor preferences to filter and prioritize suggestions.

        Learning logic:
        1. FILTER: Remove suggestions the doctor has rejected 3+ times
        2. BOOST: Promote suggestions the doctor frequently accepts to higher priority
        3. REORDER: Sort within each priority level by acceptance history

        Args:
            suggestions: Generated triage suggestions
            preferences: Doctor's learned preferences from feedback

        Returns:
            TriageSuggestions with preferences applied
        """
        if not preferences or not preferences.has_sufficient_data:
            return suggestions

        filtered_count = 0
        boosted_count = 0

        # Process each priority level
        for priority_name, suggestion_list in [
            ("critical", suggestions.critical_actions),
            ("important", suggestions.important_considerations),
            ("consider", suggestions.nice_to_have)
        ]:
            filtered = []
            for suggestion in suggestion_list:
                # Check if this suggestion should be filtered (rejected 3+ times)
                if preferences.should_filter(suggestion.suggestion):
                    logger.info(f"[TRIAGE_LEARN] Filtered suggestion (frequently rejected): {suggestion.suggestion[:50]}...")
                    filtered_count += 1
                    continue

                # Check if this suggestion should be boosted
                boost_score = preferences.get_boost_score(suggestion.suggestion)
                if boost_score > 0:
                    # Add note about doctor preference
                    suggestion.rationale += f" [Doctor frequently accepts similar suggestions]"
                    boosted_count += 1

                filtered.append(suggestion)

            # Update the list
            suggestion_list.clear()
            suggestion_list.extend(filtered)

        # Promote highly boosted suggestions from nice_to_have to important
        promoted = []
        remaining_nice_to_have = []
        for suggestion in suggestions.nice_to_have:
            boost_score = preferences.get_boost_score(suggestion.suggestion)
            if boost_score >= 10:  # Strong preference - promote to important
                suggestion.priority = "important"
                promoted.append(suggestion)
                logger.info(f"[TRIAGE_LEARN] Promoted suggestion (doctor preference): {suggestion.suggestion[:50]}...")
            else:
                remaining_nice_to_have.append(suggestion)

        suggestions.nice_to_have = remaining_nice_to_have
        suggestions.important_considerations.extend(promoted)

        if filtered_count > 0 or boosted_count > 0 or len(promoted) > 0:
            logger.info(f"[TRIAGE_LEARN] Applied preferences: filtered={filtered_count}, boosted={boosted_count}, promoted={len(promoted)}")

        return suggestions

    def _filter_suggestion_list(
        self,
        suggestion_list: List[TriageSuggestion],
        insights: StructuredInsights,
        priority: str
    ) -> List[TriageSuggestion]:
        """Filter a list of suggestions based on patient context."""
        filtered = []

        for suggestion in suggestion_list:
            # VETO: Skip if drug mentioned and patient has allergy
            if self._conflicts_with_allergy(suggestion.suggestion, insights.known_allergies):
                logger.info(f"[TRIAGE_V2] VETOED suggestion due to allergy conflict: {suggestion.suggestion[:50]}...")
                continue

            # Modify: Add cost note if patient has recurring financial concerns
            if insights.financial_concerns_history == 'recurring':
                suggestion = self._add_cost_sensitivity_note(suggestion)

            # Modify: Add anxiety-aware note if patient has concerning anxiety pattern
            if (insights.historical_anxiety_pattern and
                insights.historical_anxiety_pattern.get('trend') == 'concerning'):
                suggestion = self._add_anxiety_aware_note(suggestion)

            # Modify: Add compliance note if patient has low compliance history
            if insights.compliance_history and 'low' in insights.compliance_history.lower():
                suggestion = self._add_compliance_note(suggestion)

            filtered.append(suggestion)

        return filtered

    def _conflicts_with_allergy(self, suggestion_text: str, known_allergies: List[str]) -> bool:
        """Check if suggestion mentions a drug the patient is allergic to."""
        if not known_allergies:
            return False

        suggestion_lower = suggestion_text.lower()

        # Common drug class patterns
        for allergy in known_allergies:
            allergy_lower = allergy.lower()

            # Direct match
            if allergy_lower in suggestion_lower:
                return True

            # Check common drug class relationships
            drug_classes = {
                'penicillin': ['amoxicillin', 'ampicillin', 'penicillin', 'amoxyclav', 'augmentin', 'piperacillin'],
                'sulfa': ['sulfonamide', 'sulfamethoxazole', 'trimethoprim', 'cotrimoxazole', 'bactrim', 'septran'],
                'nsaid': ['ibuprofen', 'diclofenac', 'naproxen', 'aspirin', 'piroxicam', 'ketorolac'],
                'cephalosporin': ['ceftriaxone', 'cefixime', 'cephalexin', 'cefuroxime', 'ceftazidime'],
                'fluoroquinolone': ['ciprofloxacin', 'levofloxacin', 'ofloxacin', 'moxifloxacin'],
            }

            for class_name, drugs in drug_classes.items():
                if class_name in allergy_lower or allergy_lower in drugs:
                    for drug in drugs:
                        if drug in suggestion_lower:
                            return True

        return False

    def _add_cost_sensitivity_note(self, suggestion: TriageSuggestion) -> TriageSuggestion:
        """Add note about cost-conscious alternatives."""
        if 'investigation' in suggestion.category.lower():
            suggestion.rationale += " [Cost-sensitive patient]"
        return suggestion

    def _add_anxiety_aware_note(self, suggestion: TriageSuggestion) -> TriageSuggestion:
        """Add note about patient anxiety."""
        suggestion.rationale += " [Anxiety trend noted]"
        return suggestion

    def _add_compliance_note(self, suggestion: TriageSuggestion) -> TriageSuggestion:
        """Add note about compliance concerns."""
        suggestion.rationale += " [Low compliance history]"
        return suggestion

    def _generate_psychosocial_suggestions(self, insights: StructuredInsights) -> List[TriageSuggestion]:
        """Generate psychosocial recommendations based on patient context."""
        suggestions = []

        # Anxiety-related
        if (insights.historical_anxiety_pattern and
            insights.historical_anxiety_pattern.get('trend') == 'concerning'):
            suggestions.append(TriageSuggestion(
                category="psychosocial",
                suggestion="Consider anxiety assessment - patient shows concerning anxiety trend across consultations",
                priority="consider",
                rationale="Historical data shows worsening anxiety pattern",
                source="patient_context",
            ))

        # Financial concerns
        if insights.financial_concerns_history == 'recurring':
            suggestions.append(TriageSuggestion(
                category="psychosocial",
                suggestion="Financial counseling may be beneficial - patient has recurring financial concerns",
                priority="consider",
                rationale="Multiple consultations have flagged financial concerns",
                source="patient_context",
            ))

        # Compliance issues
        if insights.compliance_history and 'low' in insights.compliance_history.lower():
            suggestions.append(TriageSuggestion(
                category="psychosocial",
                suggestion="Consider treatment adherence support - patient has history of low compliance",
                priority="consider",
                rationale="Historical compliance likelihood is low - may benefit from simplified regimens or support",
                source="patient_context",
            ))

        # Prior ineffective interventions
        ineffective = [i for i in insights.prior_intervention_outcomes
                      if i.get('outcome') == 'not_effective']
        if ineffective:
            interventions_list = ', '.join([i.get('name', i.get('code', '')) for i in ineffective[:3]])
            suggestions.append(TriageSuggestion(
                category="psychosocial",
                suggestion=f"Note: Prior interventions were not effective: {interventions_list}",
                priority="consider",
                rationale="Consider alternative approaches as previous interventions did not achieve desired outcomes",
                source="patient_context",
            ))

        return suggestions

    async def _log_suggestions_to_db(
        self,
        suggestions: TriageSuggestions,
        extraction_id: str,
        doctor_id: Optional[str],
        patient_context: Dict[str, Any],
        supabase_client
    ):
        """Log suggestions to triage_suggestion_log table and update suggestion objects with IDs."""
        try:
            # Build suggestion list for batch insert
            suggestion_records = []

            # Process all suggestion categories
            for priority, suggestion_list in [
                ('critical', suggestions.critical_actions),
                ('important', suggestions.important_considerations),
                ('consider', suggestions.nice_to_have)
            ]:
                for suggestion in suggestion_list:
                    suggestion_records.append({
                        'category': suggestion.category,
                        'type': suggestion.category,  # Use category as type for now
                        'suggestion': suggestion.suggestion,
                        'source': suggestion.source,
                        'confidence': None,  # Will be populated by Gemini in future
                        'priority': priority,
                        'rationale': suggestion.rationale,  # Store patient-specific rationale
                    })

            if not suggestion_records:
                logger.info(f"[TRIAGE_V2] No suggestions to log for extraction {extraction_id}")
                return

            # Call RPC to save suggestions
            result = supabase_client.rpc(
                'save_triage_suggestions',
                {
                    'p_extraction_id': extraction_id,
                    'p_doctor_id': doctor_id,
                    'p_suggestions': suggestion_records,
                    'p_patient_context': patient_context
                }
            ).execute()

            logger.info(f"[TRIAGE_V2] Logged {len(suggestion_records)} suggestions for extraction {extraction_id}")

            # Fetch back the saved suggestions to get their IDs
            saved_result = supabase_client.table("triage_suggestion_log").select(
                "id, suggestion_text, suggestion_category"
            ).eq("extraction_id", extraction_id).order("priority_rank").execute()

            if saved_result.data:
                # Create a map of suggestion text -> id
                text_to_id = {s.get("suggestion_text"): s.get("id") for s in saved_result.data}

                # Update suggestion objects with their IDs
                for suggestion_list in [suggestions.critical_actions, suggestions.important_considerations, suggestions.nice_to_have]:
                    for suggestion in suggestion_list:
                        if suggestion.suggestion in text_to_id:
                            suggestion.id = text_to_id[suggestion.suggestion]

                logger.info(f"[TRIAGE_V2] Updated {len(text_to_id)} suggestions with IDs")

        except Exception as e:
            logger.error(f"[TRIAGE_V2] Failed to log suggestions: {e}")
            # Don't fail the request - logging is optional

    def _check_red_flags(
        self,
        insights: StructuredInsights,
        known_red_flags: List[str]
    ) -> List[str]:
        """
        Check if any known red flags are present in the consultation data.

        Uses keyword matching across all relevant segments including:
        - Chief complaints
        - History of present illness
        - Examination findings
        - Vital signs
        - Investigation results (lab values, imaging findings)
        - Warnings/cautions

        Also performs numeric checks on vital signs and lab values.
        """
        identified = []

        # Build searchable text from consultation (with existence checks)
        text_parts = []

        # Chief complaints
        if insights.chief_complaints:
            text_parts.append(" ".join(insights.chief_complaints))

        # History of present illness
        if insights.history_of_present_illness:
            text_parts.append(str(insights.history_of_present_illness))

        # Examination findings
        if insights.examination_findings:
            text_parts.append(str(insights.examination_findings))

        # Vital signs (as text for keyword search)
        if insights.vital_signs:
            text_parts.append(str(insights.vital_signs))

        # Investigation results - IMPORTANT for lab/imaging red flags
        if insights.investigations_results:
            for result in insights.investigations_results:
                if isinstance(result, dict):
                    text_parts.append(str(result))
                else:
                    text_parts.append(str(result))

        # Also check investigations_ordered field (may contain inline results)
        if insights.investigations_ordered:
            text_parts.append(" ".join(insights.investigations_ordered))

        # Caution/warnings
        if insights.caution:
            text_parts.append(insights.caution)

        if insights.warnings:
            text_parts.append(str(insights.warnings))

        # Past medical history (for comorbidities that increase risk)
        if insights.past_medical_history:
            text_parts.append(" ".join(insights.past_medical_history))

        # Summary may contain important findings
        if insights.summary:
            text_parts.append(insights.summary)

        search_text = " ".join(text_parts).lower()

        # =====================================================================
        # VITAL SIGNS - Numeric Red Flags
        # =====================================================================
        vitals = insights.vital_signs or {}

        # Check for hypotension
        sbp = vitals.get("systolic_bp") or vitals.get("sbp") or vitals.get("systolic")
        if not sbp:
            # Try to extract from blood_pressure field (e.g., "120/80")
            bp = str(vitals.get("blood_pressure", ""))
            if "/" in bp:
                sbp = bp.split("/")[0]
        if sbp:
            sbp_val = self._extract_numeric(sbp)
            if sbp_val and sbp_val < 90:
                identified.append("Hypotension (SBP <90 mmHg)")
            elif sbp_val and sbp_val > 180:
                identified.append("Severe Hypertension (SBP >180 mmHg)")

        # Check for hypoxia
        spo2 = vitals.get("spo2") or vitals.get("oxygen_saturation") or vitals.get("SpO2") or vitals.get("pulse_oximetry")
        if spo2:
            spo2_val = self._extract_numeric(spo2)
            if spo2_val and spo2_val < 94:
                identified.append("Hypoxia (SpO2 <94%)")
            if spo2_val and spo2_val < 90:
                identified.append("Severe Hypoxia (SpO2 <90%)")

        # Check for tachycardia/bradycardia
        hr = vitals.get("heart_rate") or vitals.get("pulse") or vitals.get("hr") or vitals.get("pulse_rate")
        if hr:
            hr_val = self._extract_numeric(hr)
            if hr_val:
                if hr_val > 120:
                    identified.append("Tachycardia (HR >120/min)")
                elif hr_val < 50:
                    identified.append("Bradycardia (HR <50/min)")

        # Check for fever
        temp = vitals.get("temperature") or vitals.get("temp")
        if temp:
            temp_val = self._extract_numeric(temp)
            if temp_val:
                # Handle both Celsius and Fahrenheit
                if temp_val > 39 or (temp_val > 102 and temp_val < 110):  # >39°C or >102°F
                    identified.append("High Fever (>39°C / >102°F)")

        # Check for tachypnea
        rr = vitals.get("respiratory_rate") or vitals.get("rr")
        if rr:
            rr_val = self._extract_numeric(rr)
            if rr_val and rr_val > 24:
                identified.append("Tachypnea (RR >24/min)")

        # =====================================================================
        # LAB VALUES - Numeric Red Flags (from investigation results)
        # =====================================================================
        inv_text = search_text  # Already includes investigations

        # Thrombocytopenia - critical for dengue, sepsis
        if any(kw in inv_text for kw in ["platelet", "plt"]):
            platelet_val = self._extract_lab_value(inv_text, ["platelet", "plt"])
            if platelet_val:
                if platelet_val < 20000:
                    identified.append("Severe Thrombocytopenia (Platelets <20,000)")
                elif platelet_val < 50000:
                    identified.append("Thrombocytopenia (Platelets <50,000)")

        # Anemia
        if any(kw in inv_text for kw in ["hemoglobin", "hb", "hgb"]):
            hb_val = self._extract_lab_value(inv_text, ["hemoglobin", "hb", "hgb"])
            if hb_val and hb_val < 7:
                identified.append("Severe Anemia (Hb <7 g/dL)")

        # Renal dysfunction
        if any(kw in inv_text for kw in ["creatinine", "creat"]):
            creat_val = self._extract_lab_value(inv_text, ["creatinine", "creat"])
            if creat_val and creat_val > 3:
                identified.append("Acute Kidney Injury (Creatinine >3 mg/dL)")

        # Hyperglycemia / DKA
        if any(kw in inv_text for kw in ["glucose", "sugar", "rbs", "fbs"]):
            glucose_val = self._extract_lab_value(inv_text, ["glucose", "sugar", "rbs", "fbs"])
            if glucose_val and glucose_val > 400:
                identified.append("Severe Hyperglycemia (>400 mg/dL)")

        # Elevated liver enzymes
        if any(kw in inv_text for kw in ["sgpt", "alt", "sgot", "ast", "transaminase"]):
            # Try multiple patterns for AST/SGOT
            ast_val = self._extract_lab_value(inv_text, ["sgot", "ast"])
            if ast_val is None:
                # Try extracting from "SGOT (AST): value" pattern
                ast_val = self._extract_liver_enzyme(inv_text, "sgot")

            # Try multiple patterns for ALT/SGPT
            alt_val = self._extract_lab_value(inv_text, ["sgpt", "alt"])
            if alt_val is None:
                # Try extracting from "SGPT (ALT): value" pattern
                alt_val = self._extract_liver_enzyme(inv_text, "sgpt")

            if (ast_val and ast_val > 1000) or (alt_val and alt_val > 1000):
                identified.append("Severe Hepatitis (Transaminases >1000)")

        # Positive troponin
        if "troponin" in inv_text and any(kw in inv_text for kw in ["positive", "elevated", "raised", "high"]):
            identified.append("Positive Troponin (Myocardial Injury)")

        # =====================================================================
        # IMAGING Red Flags
        # =====================================================================
        imaging_red_flags = {
            "pneumothorax": "Pneumothorax on Imaging",
            "pulmonary embolism": "Pulmonary Embolism",
            "aortic dissection": "Aortic Dissection",
            "intracranial hemorrhage": "Intracranial Hemorrhage",
            "midline shift": "Midline Shift (Raised ICP)",
            "bowel obstruction": "Bowel Obstruction",
            "free air": "Pneumoperitoneum (Free Air)",
            "perforation": "Visceral Perforation",
            "fracture dislocation": "Fracture-Dislocation",
            "spinal cord compression": "Spinal Cord Compression",
        }

        for finding, flag_name in imaging_red_flags.items():
            if finding in inv_text:
                identified.append(flag_name)

        # =====================================================================
        # KEYWORD-BASED Red Flags
        # =====================================================================
        red_flag_keywords = {
            "altered sensorium": ["altered sensorium", "confusion", "disoriented", "gcs <15", "gcs 14", "gcs 13", "unconscious", "unresponsive"],
            "bleeding": ["bleeding", "petechiae", "purpura", "hematemesis", "melena", "hematuria", "hemoptysis", "epistaxis"],
            "severe dehydration": ["severe dehydration", "dry mucosa", "sunken eyes", "poor skin turgor", "capillary refill >3"],
            "seizure": ["seizure", "convulsion", "fit", "tonic clonic", "status epilepticus"],
            "suicidal ideation": ["suicidal", "suicide", "want to die", "kill myself", "self harm", "overdose"],
            "respiratory distress": ["respiratory distress", "stridor", "wheeze severe", "accessory muscles", "intercostal retraction", "gasping"],
            "shock": ["shock", "cold peripheries", "mottled skin", "crt >3", "capillary refill prolonged"],
            "meningism": ["neck stiffness", "meningism", "kernig", "brudzinski", "photophobia with fever"],
            "anaphylaxis": ["anaphylaxis", "angioedema", "stridor with rash", "hypotension with rash"],
            "acute abdomen": ["acute abdomen", "rigid abdomen", "guarding", "rebound tenderness", "board-like rigidity"],
            "ectopic pregnancy": ["ectopic", "positive upt with pain", "adnexal mass with pain"],
            "compartment syndrome": ["compartment syndrome", "pain on passive stretch", "tense compartment"],
            "cauda equina": ["cauda equina", "saddle anesthesia", "urinary retention", "bilateral leg weakness", "bowel incontinence"],
        }

        for flag_name, keywords in red_flag_keywords.items():
            for keyword in keywords:
                if keyword in search_text:
                    identified.append(flag_name.replace("_", " ").title())
                    break

        return list(set(identified))  # Deduplicate

    def _extract_numeric(self, value: Any) -> Optional[float]:
        """
        Extract numeric value from a string that may contain units.
        E.g., "120 mmHg" -> 120, "98%" -> 98, "37.5°C" -> 37.5
        """
        if value is None:
            return None

        try:
            # If already numeric
            if isinstance(value, (int, float)):
                return float(value)

            # Convert to string and extract first number
            import re
            value_str = str(value).strip()

            # Handle N/A, unknown, etc.
            if value_str.lower() in ("n/a", "na", "unknown", "not recorded", ""):
                return None

            # Extract first number (including decimals)
            match = re.search(r'(\d+\.?\d*)', value_str)
            if match:
                return float(match.group(1))

            return None
        except (ValueError, TypeError):
            return None

    def _extract_liver_enzyme(self, text: str, enzyme: str) -> Optional[float]:
        """
        Extract liver enzyme value from complex patterns.
        Handles: "SGPT (ALT): 1500 U/L" or "AST/SGOT: 1200"
        """
        import re

        patterns = [
            # "SGPT (ALT): 1500" or "SGOT (AST): 1200"
            rf'{enzyme}\s*\([^)]*\)\s*[:\-=]\s*(\d+\.?\d*)',
            # "ALT/SGPT: 1500" or "AST/SGOT: 1200"
            rf'\w+/{enzyme}\s*[:\-=]\s*(\d+\.?\d*)',
            # Just "enzyme: value"
            rf'{enzyme}\s*[:\-=]\s*(\d+\.?\d*)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, IndexError):
                    continue

        return None

    def _extract_lab_value(self, text: str, keywords: List[str]) -> Optional[float]:
        """
        Extract a lab value from text given possible keywords.
        E.g., "Platelet count: 45000/cumm" -> 45000
        """
        import re

        for keyword in keywords:
            # Escape special regex characters in keyword
            escaped_keyword = re.escape(keyword)

            # Look for patterns like "keyword: value" or "keyword - value" or "keyword = value"
            # Also handle multi-word variants like "platelet count: 45000"
            patterns = [
                rf'{escaped_keyword}\s*(?:count)?\s*[:\-=]\s*(\d+\.?\d*)',
                rf'{escaped_keyword}\s*(?:count)?\s+(\d+\.?\d*)',
                rf'(\d+\.?\d*)\s*(?:/\w+)?\s*{escaped_keyword}',
                # Handle patterns like "SGPT (ALT): 1500"
                rf'{escaped_keyword}\s*\([^)]*\)\s*[:\-=]\s*(\d+\.?\d*)',
            ]

            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        return float(match.group(1))
                    except (ValueError, IndexError):
                        continue

        return None

    def _identify_missing_investigations(
        self,
        insights: StructuredInsights,
        recommended: List[Dict[str, Any]],
        presentations: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Identify which recommended investigations are missing.
        """
        ordered = [inv.lower() for inv in insights.investigations_ordered]
        ordered_text = " ".join(ordered)

        missing = []
        seen_tests = set()

        for inv in recommended:
            test_name = inv.get("test", "")
            if not test_name or test_name in seen_tests:
                continue

            # Check if test was ordered (fuzzy match)
            test_keywords = test_name.lower().replace("_", " ").split()

            # Check if any keyword matches ordered investigations
            found = any(keyword in ordered_text for keyword in test_keywords if len(keyword) > 3)

            if not found:
                missing.append({
                    **inv,
                    "presentation": presentations[0] if presentations else "",
                })
                seen_tests.add(test_name)

        return missing

    def _identify_missing_history(
        self,
        insights: StructuredInsights,
        essential_questions: List[str]
    ) -> List[str]:
        """
        Identify which essential history questions may not have been asked.
        """
        # Build text of what we have
        history_text = " ".join([
            " ".join(insights.chief_complaints),
            str(insights.history_of_present_illness),
            " ".join(insights.past_medical_history),
            insights.family_history,
            str(insights.social_history),
        ]).lower()

        missing = []

        for question in essential_questions:
            # Extract key concepts from question
            question_lower = question.lower()

            # Skip if it's about duration and we have duration info
            if "duration" in question_lower and ("day" in history_text or "week" in history_text or "month" in history_text):
                continue

            # Skip if question keywords appear in history
            keywords = [w for w in question_lower.split() if len(w) > 4]
            if any(kw in history_text for kw in keywords[:3]):  # Check first 3 significant words
                continue

            missing.append(question)

        return missing

    async def _llm_gap_analysis(
        self,
        insights: StructuredInsights,
        differential_context: Dict[str, Any],
        matched_presentations: List[str],
        extraction_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        triage_model: Optional[str] = None,
        rag_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Use LLM (Gemini/Claude/OpenAI) to perform intelligent gap analysis.

        Returns structured suggestions based on:
        - What's documented vs what should be documented
        - Risk stratification
        - Clinical decision support
        - RAG-matched guidelines (when provided)

        Args:
            triage_model: Model to use (default: from DB config or fallback)
            rag_context: Optional RAG matches to include in prompt for context-aware analysis
        """
        # Use provided model or fallback to default
        model = triage_model or DEFAULT_TRIAGE_MODEL
        import time
        import asyncio
        import uuid as uuid_module
        start_time = time.time()

        # Build the prompt
        system_prompt = self._build_triage_system_prompt()
        user_prompt = self._build_triage_user_prompt(
            insights, differential_context, matched_presentations, rag_context
        )

        # Route through LLM factory (supports Gemini/Claude/OpenAI)
        from services.llm_client_factory import generate_json_output

        from services.llm_usage_service import get_thinking_budget
        llm_result = await generate_json_output(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=0.3,
            thinking_budget=get_thinking_budget(model, "triage"),
        )

        # Log LLM usage (fire-and-forget)
        api_duration = time.time() - start_time
        try:
            from services.llm_usage_service import extract_usage_from_response, log_llm_usage
            usage_data = extract_usage_from_response(
                response=llm_result.raw_response,
                call_type="triage",
                call_subtype="gap_analysis",
                model=model,
                api_duration_seconds=api_duration,
                extraction_id=uuid_module.UUID(extraction_id) if extraction_id else None,
                doctor_id=uuid_module.UUID(doctor_id) if doctor_id else None,
            )
            asyncio.create_task(log_llm_usage(usage_data))
        except Exception as usage_err:
            logger.warning(f"[TRIAGE] Failed to log usage: {usage_err}")

        # Data is already parsed by the factory
        return llm_result.data

    def _build_triage_system_prompt(self) -> str:
        """Build system prompt for Gemini triage analysis."""
        return """You are an expert clinical triage assistant for Indian healthcare settings.

Your role is to:
1. Analyze consultation data and identify gaps in workup
2. Suggest additional investigations or history questions
3. Flag any safety concerns
4. Prioritize suggestions by clinical importance

Context:
- You're reviewing extractions from doctor-patient consultations in India
- Consider resource constraints and cost-effectiveness
- Focus on must-not-miss diagnoses common in India (dengue, malaria, typhoid, TB, etc.)

BREVITY RULES (CRITICAL - follow strictly):
- Each "suggestion" field MUST be 30 words or fewer. Be direct and specific.
- Each "rationale" field MUST be 1 short sentence (under 25 words). Reference the patient's key finding.
- Do NOT repeat the suggestion text in the rationale.
- Do NOT list drug classes or parenthetical alternatives in suggestions. Name the single best action.
- Limit: maximum 3 critical_suggestions and 4 additional_suggestions. Only include truly actionable items.

Example GOOD suggestion: "Order high-sensitivity Troponin"
Example BAD suggestion: "Detailed medication reconciliation, specifically asking about recent doses of rate-limiting agents (beta-blockers, calcium channel blockers, digoxin) and drugs affecting potassium"

Example GOOD rationale: "New chest pain with HR 42 and CAD history needs ACS rule-out."
Example BAD rationale: "Given the 45-year-old male with fever and abdominal pain, CBC with platelets is essential to rule out dengue which is endemic in this region and should be considered urgently"

Output format (JSON):
{
    "risk_level": "low|moderate|high|critical",
    "risk_factors": ["brief risk factor"],
    "critical_suggestions": [
        {
            "type": "investigation|history|examination|referral",
            "suggestion": "specific action (max 30 words)",
            "urgency": "immediate|within_24h|routine",
            "rationale": "one short patient-specific sentence (max 25 words)"
        }
    ],
    "additional_suggestions": [
        {
            "type": "investigation|history|examination|follow_up",
            "suggestion": "specific action (max 30 words)",
            "rationale": "one short patient-specific sentence (max 25 words)"
        }
    ],
    "differential_considerations": ["diagnoses to keep in mind"],
    "safety_netting": "brief advice on when to return"
}"""

    def _build_triage_user_prompt(
        self,
        insights: StructuredInsights,
        differential_context: Dict[str, Any],
        matched_presentations: List[str],
        rag_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build user prompt with consultation data and RAG context."""

        # Format chief complaints
        cc_text = ", ".join(insights.chief_complaints) if insights.chief_complaints else "Not documented"

        # Format diagnoses
        diagnoses_text = ", ".join([
            d.get("diagnosis", str(d)) if isinstance(d, dict) else str(d)
            for d in insights.diagnoses_discussed
        ]) if insights.diagnoses_discussed else "Not documented"

        # Format investigations
        inv_text = ", ".join(insights.investigations_ordered) if insights.investigations_ordered else "None ordered"

        # Format differential context
        diff_summary = []
        for pres, data in differential_context.items():
            must_rule_out = data.get("must_rule_out", [])
            if must_rule_out:
                diagnoses = [d.get("diagnosis", "") for d in must_rule_out[:3]]
                diff_summary.append(f"{pres}: {', '.join(diagnoses)}")
        diff_text = "; ".join(diff_summary) if diff_summary else "No specific differentials matched"

        # Format RAG context (guideline matches)
        rag_section = ""
        if rag_context:
            rag_matches = rag_context.get("matches", [])
            if rag_matches:
                rag_lines = []
                for match in rag_matches[:5]:  # Limit to top 5
                    condition = match.get("condition_name", match.get("source_name", "Unknown"))
                    chunk_type = match.get("chunk_type", "guideline")
                    similarity = match.get("similarity", 0)
                    content = match.get("content_text", match.get("chunk_text", ""))[:300]
                    rag_lines.append(f"- [{condition}] ({chunk_type}, sim={similarity:.2f}): {content}...")

                rag_section = f"""

**RAG-Retrieved Clinical Guidelines (Already Applied - Focus on Gaps):**
{chr(10).join(rag_lines)}

IMPORTANT: The above guidelines have ALREADY been used to generate suggestions.
Your role is to:
1. DO NOT duplicate suggestions already covered by the guidelines above
2. FILL GAPS: Identify what the guidelines missed for this specific patient
3. SYNTHESIZE: Combine guideline knowledge with patient-specific factors
4. PRIORITIZE: Help rank suggestions based on this patient's context
"""

        return f"""Analyze this consultation and provide triage suggestions:

**Patient Profile:**
- Age: {insights.patient_age or 'Unknown'}
- Gender: {insights.patient_gender or 'Unknown'}
- Age Group: {insights.age_group}

**Chief Complaints:**
{cc_text}

**Vital Signs:**
{json.dumps(insights.vital_signs, indent=2) if insights.vital_signs else 'Not documented'}

**History:**
- HPI: {json.dumps(insights.history_of_present_illness) if insights.history_of_present_illness else 'Not documented'}
- Past Medical: {', '.join(insights.past_medical_history) if insights.past_medical_history else 'None'}
- Drug Allergies: {', '.join(insights.drug_allergies) if insights.drug_allergies else 'NKDA'}

**Examination Findings:**
{json.dumps(insights.examination_findings, indent=2) if insights.examination_findings else 'Not documented'}

**Investigations Ordered:**
{inv_text}

**Diagnoses Discussed:**
{diagnoses_text}

**Matched Clinical Presentations:**
{', '.join(matched_presentations) if matched_presentations else 'None matched'}

**Relevant Differentials to Consider:**
{diff_text}

**Warnings/Cautions in Record:**
{insights.caution if insights.caution else 'None'}
{rag_section}
Please analyze this consultation and provide prioritized triage suggestions in JSON format."""

    def _integrate_gemini_suggestions(
        self,
        suggestions: TriageSuggestions,
        gemini_result: Dict[str, Any]
    ):
        """
        Integrate Gemini suggestions into the appropriate priority lists.
        """
        # Add critical suggestions
        for item in gemini_result.get("critical_suggestions", []):
            urgency = item.get("urgency", "routine")
            priority = "critical" if urgency == "immediate" else "important"

            suggestion = TriageSuggestion(
                category=item.get("type", "investigation"),
                suggestion=item.get("suggestion", ""),
                priority=priority,
                rationale=item.get("rationale", ""),
                source="gemini_analysis",
            )

            if priority == "critical":
                suggestions.critical_actions.append(suggestion)
            else:
                suggestions.important_considerations.append(suggestion)

        # Add additional suggestions
        for item in gemini_result.get("additional_suggestions", []):
            suggestions.nice_to_have.append(TriageSuggestion(
                category=item.get("type", "investigation"),
                suggestion=item.get("suggestion", ""),
                priority="consider",
                rationale=item.get("rationale", ""),
                source="gemini_analysis",
            ))

    def _deduplicate_suggestions(self, suggestions: TriageSuggestions):
        """
        Remove duplicate suggestions across priority levels.
        Higher priority takes precedence.
        """
        seen = set()

        # Process in priority order - critical first
        for suggestion_list in [
            suggestions.critical_actions,
            suggestions.important_considerations,
            suggestions.nice_to_have
        ]:
            unique = []
            for s in suggestion_list:
                key = s.suggestion.lower()[:50]  # First 50 chars as key
                if key not in seen:
                    seen.add(key)
                    unique.append(s)
            suggestion_list.clear()
            suggestion_list.extend(unique)


# =============================================================================
# Convenience Functions
# =============================================================================

async def generate_triage_suggestions(
    insights: StructuredInsights,
    include_gemini: bool = True
) -> TriageSuggestions:
    """
    Convenience function to generate triage suggestions.

    Args:
        insights: StructuredInsights object
        include_gemini: Whether to use Gemini AI analysis

    Returns:
        TriageSuggestions object
    """
    engine = TriageSuggestionEngine()
    return await engine.generate_suggestions(insights, include_gemini)


async def generate_triage_from_extraction(
    extraction: Dict[str, Any],
    consultation_type_code: Optional[str] = None,
    include_gemini: bool = True
) -> TriageSuggestions:
    """
    Generate triage suggestions directly from an extraction record.

    Args:
        extraction: Extraction record from database
        consultation_type_code: Optional consultation type code
        include_gemini: Whether to use Gemini AI analysis

    Returns:
        TriageSuggestions object
    """
    from .structured_insights import StructuredInsightsMapper

    mapper = StructuredInsightsMapper()
    insights = mapper.map_extraction(extraction, consultation_type_code)

    engine = TriageSuggestionEngine()
    return await engine.generate_suggestions(insights, include_gemini)


async def generate_triage_from_extraction_v2(
    extraction: Dict[str, Any],
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    consultation_type_code: Optional[str] = None,
    include_gemini: bool = True,
    log_suggestions: bool = True,
    supabase_client=None
) -> TriageSuggestions:
    """
    Generate triage suggestions with patient context (Phase 0.5).

    Args:
        extraction: Extraction record from database
        patient_id: Optional patient UUID for historical context
        doctor_id: Optional doctor UUID for suggestion logging
        consultation_type_code: Optional consultation type code
        include_gemini: Whether to use Gemini AI analysis
        log_suggestions: Whether to log suggestions to database
        supabase_client: Supabase client for DB operations

    Returns:
        TriageSuggestions object with patient context applied
    """
    engine = TriageSuggestionEngine()
    return await engine.generate_suggestions_v2(
        extraction=extraction,
        patient_id=patient_id,
        doctor_id=doctor_id,
        consultation_type_code=consultation_type_code,
        include_gemini_analysis=include_gemini,
        log_suggestions=log_suggestions,
        supabase_client=supabase_client
    )

"""
Triage Multi-Layer Orchestrator

Phase 4 of Triage Engine Multi-Layer system.
Orchestrates all triage layers with intelligent conflict resolution:
- Base MVP (always active)
- Doctor Practice Style Layer (Phase 1)
- Hospital/Peer Intelligence Layer (Phase 2)
- RAG Guidelines Layer (Phase 3)

Conflict Resolution Rules:
1. Patient Safety First: Allergies, contraindications always override
2. Evidence Over Opinion: RAG guidelines > doctor patterns when conflicting
3. Doctor Preference for Ties: When confidence is equal, respect doctor preference
4. Layer Weights: Use configured weights for final scoring
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from copy import deepcopy

logger = logging.getLogger(__name__)


@dataclass
class LayerConfig:
    """Configuration for a single triage layer."""
    layer_code: str
    layer_name: str
    is_enabled: bool = False
    weight: float = 1.0
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LayerResult:
    """
    Result from a triage layer with confidence tracking.

    Used for intelligent merging and override decisions:
    - Fast cache (trees) results have lower weight when RAG matches
    - RAG results can override trees when confidence > threshold
    - Safety (red flags) always preserved regardless of source
    """
    suggestions: List[Any]  # List of TriageSuggestion
    confidence: float  # 0-1, based on match quality
    source: str  # Layer identifier
    matches_found: int  # Number of matches/hits
    can_override_cache: bool = False  # True if confidence > threshold (0.75)

    # Detailed match info for Gemini context
    match_details: List[Dict[str, Any]] = field(default_factory=list)

    # Cached StructuredInsights from patient history mapping (avoids duplicate DB calls)
    cached_insights: Any = None

    @property
    def has_high_confidence(self) -> bool:
        """Check if this result should override cache."""
        return self.confidence >= 0.75 and self.matches_found > 0


@dataclass
class ConflictRecord:
    """Record of a conflict between layers."""
    conflict_type: str  # priority_disagreement, contradiction, duplicate
    layer_1: str
    layer_1_suggestion: str
    layer_1_priority: str
    layer_2: str
    layer_2_suggestion: str
    layer_2_priority: str
    resolution_strategy: str
    final_suggestion: str
    final_priority: str
    resolution_notes: Optional[str] = None


class TriageMultiLayerOrchestrator:
    """
    Orchestrates all triage layers with conflict resolution.

    Usage:
        orchestrator = TriageMultiLayerOrchestrator()
        suggestions = await orchestrator.generate_suggestions(
            extraction=extraction_data,
            patient_id=patient_uuid,
            doctor_id=doctor_uuid,
            hospital_id=hospital_uuid,
            supabase_client=supabase
        )
    """

    def __init__(self, supabase_client=None):
        """Initialize with optional Supabase client."""
        self.supabase = supabase_client

        # Lazy-loaded layer instances
        self._base_engine = None
        self._practice_layer = None
        self._hospital_layer = None
        self._rag_layer = None

    @property
    def base_engine(self):
        """Lazy load base triage engine."""
        if self._base_engine is None:
            from .triage_engine import TriageSuggestionEngine
            self._base_engine = TriageSuggestionEngine()
        return self._base_engine

    @property
    def practice_layer(self):
        """Lazy load doctor practice layer."""
        if self._practice_layer is None:
            from .doctor_practice_layer import DoctorPracticeLayer
            self._practice_layer = DoctorPracticeLayer()
        return self._practice_layer

    @property
    def hospital_layer(self):
        """Lazy load hospital intelligence layer."""
        if self._hospital_layer is None:
            from .hospital_intelligence_layer import HospitalIntelligenceLayer
            self._hospital_layer = HospitalIntelligenceLayer()
        return self._hospital_layer

    @property
    def rag_layer(self):
        """Lazy load RAG guidelines layer."""
        if self._rag_layer is None:
            from .rag_guidelines_layer import RAGGuidelinesLayer
            self._rag_layer = RAGGuidelinesLayer()
        return self._rag_layer

    async def get_enabled_layers(
        self,
        doctor_id: Optional[str] = None,
        supabase_client=None
    ) -> List[LayerConfig]:
        """
        Get list of enabled triage layers with their configuration.

        Args:
            doctor_id: Optional doctor UUID for doctor-specific preferences
            supabase_client: Supabase client for DB operations

        Returns:
            List of LayerConfig objects
        """
        client = supabase_client or self.supabase
        if not client:
            # Return default config if no DB available
            return [
                LayerConfig("base_mvp", "Base Triage (MVP)", True, 1.0),
            ]

        try:
            result = client.rpc(
                'get_enabled_triage_layers',
                {'p_doctor_id': doctor_id}
            ).execute()

            layers = []
            for row in result.data or []:
                layers.append(LayerConfig(
                    layer_code=row.get("layer_code"),
                    layer_name=row.get("layer_name"),
                    is_enabled=row.get("is_enabled", False),
                    weight=float(row.get("weight") or 1.0),
                    config=row.get("config") or {},
                ))

            return layers

        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Failed to get layer config: {e}")
            return [
                LayerConfig("base_mvp", "Base Triage (MVP)", True, 1.0),
            ]

    async def generate_suggestions(
        self,
        extraction: Dict[str, Any],
        patient_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        hospital_id: Optional[str] = None,
        consultation_type_code: Optional[str] = None,
        include_gemini_analysis: bool = True,
        log_suggestions: bool = True,
        enabled_layers: Optional[List[str]] = None,
        supabase_client=None
    ) -> "TriageSuggestions":
        """
        Generate suggestions using all enabled layers.

        NEW PIPELINE (Refactored for RAG-first with tree cache):
        1. Fast Cache Layer (Trees) - Instant response (~5ms), red flags always active
        2. RAG Clinical Conditions (Primary) - Semantic search (~500ms), may override trees
        3. Merge with override logic - RAG > Trees when high confidence
        4. Gemini Gap Analysis - Receives RAG context, fills gaps
        5. Personalization Layers - Doctor practice, hospital intelligence
        6. Final conflict resolution and deduplication

        Args:
            extraction: Extraction record from database
            patient_id: Optional patient UUID for historical context
            doctor_id: Optional doctor UUID
            hospital_id: Optional hospital UUID
            consultation_type_code: Optional consultation type code
            include_gemini_analysis: Whether to use Gemini AI for gap analysis
            log_suggestions: Whether to log suggestions to database
            enabled_layers: Optional explicit list of layers to enable
            supabase_client: Supabase client for DB operations

        Returns:
            TriageSuggestions with all layers applied
        """
        import time
        start_time = time.time()

        client = supabase_client or self.supabase

        # Step 1: Get layer configuration
        layer_configs = await self.get_enabled_layers(doctor_id, client)
        layer_map = {lc.layer_code: lc for lc in layer_configs}

        # Override with explicit enabled_layers if provided
        if enabled_layers:
            for lc in layer_configs:
                lc.is_enabled = lc.layer_code in enabled_layers

        active_layers = [lc.layer_code for lc in layer_configs if lc.is_enabled]
        logger.info(f"[ORCHESTRATOR] Active layers: {active_layers}")

        # =========================================================================
        # Step 2: FAST CACHE LAYER (Trees) - Always runs first for instant response
        # =========================================================================
        tree_result = await self._run_fast_cache_layer(
            extraction=extraction,
            patient_id=patient_id,
            doctor_id=doctor_id,
            consultation_type_code=consultation_type_code,
            supabase_client=client
        )

        # Start with tree suggestions as base
        suggestions = tree_result.suggestions
        self._tag_suggestions_with_layer(suggestions, "differential_tree_cache")

        logger.info(f"[ORCHESTRATOR] Fast cache: {suggestions.total_suggestions} suggestions in {suggestions.processing_time_ms}ms")

        # =========================================================================
        # Step 3: RAG CLINICAL CONDITIONS (Primary Source)
        # =========================================================================
        rag_result = None
        condition_matches = []

        if "rag_guidelines" in active_layers:
            rag_result = await self._run_rag_layer(
                extraction=extraction,
                specialty=suggestions.specialty or "general_medicine",
                supabase_client=client
            )

            if rag_result.matches_found > 0:
                condition_matches = rag_result.match_details

                # Apply RAG enhancements to suggestions
                from .rag_guidelines_layer import ExtractionContext, ClinicalConditionMatch
                extraction_context = self.rag_layer.extract_context_from_extraction(extraction)
                extraction_context.specialty = suggestions.specialty or "general_medicine"

                # Convert match details back to ClinicalConditionMatch objects
                rag_matches = [
                    ClinicalConditionMatch.from_db_row(m) for m in rag_result.match_details
                ]

                suggestions = self.rag_layer.enhance_suggestions_with_clinical_conditions(
                    suggestions, rag_matches, extraction_context
                )

                # Step 3.5: MERGE with override logic (RAG > Trees when high confidence)
                suggestions = self._merge_with_rag_priority(
                    tree_suggestions=tree_result.suggestions,
                    rag_result=rag_result,
                    merged_suggestions=suggestions
                )

                self._tag_enhanced_suggestions(suggestions, "rag_clinical_conditions")
                logger.info(f"[ORCHESTRATOR] RAG layer: {rag_result.matches_found} matches, confidence={rag_result.confidence:.2f}")

        # =========================================================================
        # Step 4: GEMINI GAP ANALYSIS (with RAG context)
        # =========================================================================
        if include_gemini_analysis:
            try:
                # Build RAG context for Gemini
                rag_context = None
                if rag_result and rag_result.matches_found > 0:
                    rag_context = {
                        "matches": rag_result.match_details,
                        "confidence": rag_result.confidence,
                        "source": "rag_clinical_conditions",
                    }

                # Run Gemini with RAG context (skip trees since we handle them separately)
                # Pass cached insights from fast cache layer to avoid duplicate DB call
                gemini_suggestions = await self.base_engine.generate_suggestions_v2(
                    extraction=extraction,
                    patient_id=patient_id,
                    doctor_id=doctor_id,
                    consultation_type_code=consultation_type_code,
                    include_gemini_analysis=True,
                    log_suggestions=False,
                    supabase_client=client,
                    skip_trees=True,  # Trees already run in fast cache
                    rag_context=rag_context,
                    pre_mapped_insights=tree_result.cached_insights,
                )

                # Merge Gemini suggestions (they fill gaps, not override)
                self._merge_gemini_suggestions(suggestions, gemini_suggestions)
                self._tag_enhanced_suggestions(suggestions, "gemini_analysis")
                logger.info(f"[ORCHESTRATOR] Gemini gap analysis: +{gemini_suggestions.total_suggestions} suggestions")

            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Gemini analysis failed: {e}")
                suggestions.gap_analysis["gemini_error"] = str(e)

        # =========================================================================
        # Step 5: PERSONALIZATION LAYERS
        # =========================================================================

        # Step 5a: Apply Doctor Practice Layer
        if "doctor_practice" in active_layers and doctor_id:
            try:
                practice_style = await self.practice_layer.get_practice_style(
                    doctor_id, client
                )
                if practice_style and practice_style.has_sufficient_data:
                    suggestions = self.practice_layer.enhance_suggestions(
                        suggestions, practice_style
                    )
                    self._tag_enhanced_suggestions(suggestions, "doctor_practice")
                    logger.info(f"[ORCHESTRATOR] Applied doctor practice layer")
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Doctor practice layer failed: {e}")

        # Step 5b: Apply Hospital Intelligence Layer
        if "hospital_intelligence" in active_layers and hospital_id:
            try:
                specialty = suggestions.specialty or "general_medicine"

                hospital_patterns = await self.hospital_layer.get_hospital_patterns(
                    hospital_id, specialty, client
                )
                if hospital_patterns and hospital_patterns.has_sufficient_data:
                    outlier_flags = self.hospital_layer.detect_outliers(
                        suggestions, hospital_patterns
                    )
                    suggestions = self.hospital_layer.enhance_with_peer_context(
                        suggestions, hospital_patterns, outlier_flags
                    )
                    self._tag_enhanced_suggestions(suggestions, "hospital_intelligence")
                    logger.info(f"[ORCHESTRATOR] Applied hospital intelligence layer")
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Hospital intelligence layer failed: {e}")

        # =========================================================================
        # Step 6: CONFLICT RESOLUTION & DEDUPLICATION
        # =========================================================================
        conflicts = self._resolve_conflicts(suggestions, layer_map)
        if conflicts:
            await self._log_conflicts(extraction.get("id"), conflicts, client)

        # Step 7: Add orchestrator metadata
        processing_time = int((time.time() - start_time) * 1000)
        suggestions.processing_time_ms = processing_time

        suggestions.gap_analysis["orchestrator_metadata"] = {
            "active_layers": active_layers,
            "layer_weights": {lc.layer_code: lc.weight for lc in layer_configs if lc.is_enabled},
            "conflicts_resolved": len(conflicts),
            "total_processing_time_ms": processing_time,
        }

        # Step 8: Log suggestions with layer sources
        if log_suggestions and client:
            await self._log_suggestions_with_layers(
                suggestions=suggestions,
                extraction_id=extraction.get("id"),
                doctor_id=doctor_id,
                supabase_client=client
            )

        return suggestions

    def _extract_chief_complaints(self, extraction: Dict[str, Any]) -> List[str]:
        """Extract chief complaints from extraction data."""
        # Try various field locations
        edited_json = extraction.get("edited_extraction_json") or {}
        original_json = extraction.get("original_extraction_json") or {}
        data = edited_json or original_json

        complaints = []

        # Direct field
        if "CHIEF_COMPLAINT" in data:
            cc = data["CHIEF_COMPLAINT"]
            if isinstance(cc, list):
                complaints.extend(cc)
            elif isinstance(cc, str):
                complaints.append(cc)

        # Nested in segments
        if "segments" in data:
            for segment in data["segments"]:
                if segment.get("code") == "CHIEF_COMPLAINT":
                    value = segment.get("value")
                    if isinstance(value, list):
                        complaints.extend(value)
                    elif isinstance(value, str):
                        complaints.append(value)

        # From segment values directly
        for key, value in data.items():
            if "chief" in key.lower() and "complaint" in key.lower():
                if isinstance(value, list):
                    complaints.extend(value)
                elif isinstance(value, str):
                    complaints.append(value)

        return complaints[:5]  # Limit to top 5

    def _tag_suggestions_with_layer(
        self,
        suggestions: "TriageSuggestions",
        layer_code: str
    ):
        """Tag all suggestions with their source layer."""
        for suggestion_list in [
            suggestions.critical_actions,
            suggestions.important_considerations,
            suggestions.nice_to_have
        ]:
            for suggestion in suggestion_list:
                # Initialize layer_sources if not present
                if not hasattr(suggestion, 'layer_sources'):
                    suggestion.layer_sources = []
                suggestion.layer_sources = [layer_code]

    def _tag_enhanced_suggestions(
        self,
        suggestions: "TriageSuggestions",
        layer_code: str
    ):
        """Add layer code to suggestions that were enhanced by this layer."""
        for suggestion_list in [
            suggestions.critical_actions,
            suggestions.important_considerations,
            suggestions.nice_to_have
        ]:
            for suggestion in suggestion_list:
                if not hasattr(suggestion, 'layer_sources'):
                    suggestion.layer_sources = []
                if layer_code not in suggestion.layer_sources:
                    suggestion.layer_sources.append(layer_code)

    # =========================================================================
    # NEW: Fast Cache and RAG Priority Methods
    # =========================================================================

    async def _run_fast_cache_layer(
        self,
        extraction: Dict[str, Any],
        patient_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        consultation_type_code: Optional[str] = None,
        supabase_client=None
    ) -> LayerResult:
        """
        Run the fast cache layer using differential trees.

        This layer provides instant response (~5ms) with:
        - Red flag detection (ALWAYS safety-critical)
        - Missing investigation suggestions
        - Missing history questions

        Args:
            extraction: Extraction record
            patient_id: Optional patient UUID
            doctor_id: Optional doctor UUID
            consultation_type_code: Optional consultation type
            supabase_client: Supabase client

        Returns:
            LayerResult with tree-based suggestions
        """
        import time
        start_time = time.time()

        try:
            # Get patient-enriched insights if patient_id is provided
            if patient_id and supabase_client:
                from .structured_insights import map_extraction_with_patient_history
                insights = await map_extraction_with_patient_history(
                    extraction=extraction,
                    patient_id=patient_id,
                    supabase_client=supabase_client,
                    consultation_type_code=consultation_type_code
                )
            else:
                from .structured_insights import StructuredInsightsMapper
                mapper = StructuredInsightsMapper()
                insights = mapper.map_extraction(extraction, consultation_type_code)

            # Use tree-based suggestions only (no Gemini)
            suggestions = self.base_engine.generate_tree_suggestions(insights)

            # Calculate confidence based on matched presentations
            matched_count = len(suggestions.matched_presentations)
            confidence = min(0.9, 0.3 + (matched_count * 0.2))  # 0.3-0.9 based on matches

            processing_ms = int((time.time() - start_time) * 1000)
            logger.debug(f"[FAST_CACHE] Generated {suggestions.total_suggestions} suggestions in {processing_ms}ms")

            return LayerResult(
                suggestions=suggestions,
                confidence=confidence,
                source="differential_tree_cache",
                matches_found=matched_count,
                can_override_cache=False,  # Trees are the cache, can't override themselves
                match_details=[
                    {"presentation": p, "specialty": insights.specialty}
                    for p in suggestions.matched_presentations
                ],
                cached_insights=insights,  # Cache for reuse by downstream layers
            )

        except Exception as e:
            logger.error(f"[FAST_CACHE] Failed: {e}")
            # Return empty result on failure
            from .triage_engine import TriageSuggestions
            return LayerResult(
                suggestions=TriageSuggestions(),
                confidence=0.0,
                source="differential_tree_cache",
                matches_found=0,
                can_override_cache=False,
            )

    async def _run_rag_layer(
        self,
        extraction: Dict[str, Any],
        specialty: str,
        supabase_client=None
    ) -> LayerResult:
        """
        Run the RAG clinical conditions layer (primary source).

        This layer:
        - Performs semantic search (~500ms)
        - Returns condition matches with similarity scores
        - Can override tree suggestions when confidence > 0.75

        Args:
            extraction: Extraction record
            specialty: Medical specialty
            supabase_client: Supabase client

        Returns:
            LayerResult with RAG matches and confidence
        """
        try:
            from .rag_guidelines_layer import ExtractionContext

            # Extract context
            extraction_context = self.rag_layer.extract_context_from_extraction(extraction)
            extraction_context.specialty = specialty

            logger.debug(f"[RAG_LAYER] Context: complaints={extraction_context.chief_complaints[:2]}, "
                        f"diagnoses={extraction_context.diagnoses[:2]}, comorbidities={extraction_context.comorbidities}")

            # Search clinical conditions
            condition_matches = await self.rag_layer.search_clinical_conditions(
                context=extraction_context,
                chunk_types=None,
                top_k=10,
                min_similarity=0.4,
                supabase_client=supabase_client
            )

            # Also search comorbidity pathways
            if extraction_context.comorbidities:
                comorbidity_matches = await self.rag_layer.search_comorbidity_pathways(
                    comorbidities=extraction_context.comorbidities,
                    specialty=specialty,
                    supabase_client=supabase_client
                )
                condition_matches.extend(comorbidity_matches)

            if not condition_matches:
                return LayerResult(
                    suggestions=[],
                    confidence=0.0,
                    source="rag_clinical_conditions",
                    matches_found=0,
                    can_override_cache=False,
                )

            # Calculate confidence from best match similarity
            best_similarity = max(m.similarity for m in condition_matches)
            avg_similarity = sum(m.similarity for m in condition_matches) / len(condition_matches)

            # Confidence formula: weight best match heavily
            confidence = (best_similarity * 0.7) + (avg_similarity * 0.3)

            # Convert to dict for match_details
            match_details = [
                {
                    "chunk_id": m.chunk_id,
                    "condition_id": m.condition_id,
                    "condition_name": m.condition_name,
                    "condition_code": m.condition_code,
                    "specialty": m.specialty,
                    "chunk_type": m.chunk_type,
                    "content_text": m.content_text[:300] if m.content_text else "",
                    "content_json": m.content_json,
                    "urgency_default": m.urgency_default,
                    "has_emergency_triggers": m.has_emergency_triggers,
                    "has_red_flags": m.has_red_flags,
                    "care_levels": m.care_levels,
                    "comorbidity": m.comorbidity,
                    "drug_classes": m.drug_classes,
                    "contraindications": m.contraindications,
                    "source_name": m.source_name,
                    "similarity": m.similarity,
                }
                for m in condition_matches
            ]

            return LayerResult(
                suggestions=[],  # RAG enhances, doesn't create base suggestions
                confidence=confidence,
                source="rag_clinical_conditions",
                matches_found=len(condition_matches),
                can_override_cache=confidence >= 0.75,
                match_details=match_details,
            )

        except Exception as e:
            logger.error(f"[RAG_LAYER] Failed: {e}", exc_info=True)
            return LayerResult(
                suggestions=[],
                confidence=0.0,
                source="rag_clinical_conditions",
                matches_found=0,
                can_override_cache=False,
            )

    def _merge_with_rag_priority(
        self,
        tree_suggestions: "TriageSuggestions",
        rag_result: LayerResult,
        merged_suggestions: "TriageSuggestions"
    ) -> "TriageSuggestions":
        """
        Merge tree and RAG suggestions with RAG priority.

        Override Rules:
        1. RED FLAGS from trees ALWAYS kept (safety-critical)
        2. If RAG similarity > 0.75, prefer RAG suggestions for same category
        3. If RAG has comorbidity pathways, they override tree drug suggestions
        4. If no RAG matches, keep tree suggestions as fallback

        Args:
            tree_suggestions: Original tree-based suggestions
            rag_result: RAG layer result with matches and confidence
            merged_suggestions: Suggestions after RAG enhancement

        Returns:
            Merged TriageSuggestions with proper priority
        """
        if not rag_result.can_override_cache:
            # RAG confidence too low - keep tree suggestions as-is
            logger.debug(f"[MERGE] RAG confidence {rag_result.confidence:.2f} < 0.75, using trees as base")
            return merged_suggestions

        logger.info(f"[MERGE] RAG confidence {rag_result.confidence:.2f} >= 0.75, applying override logic")

        # Track which tree suggestions to keep vs override
        # Rule 1: ALWAYS keep red flags from trees (safety-critical)
        tree_red_flags = [
            s for s in tree_suggestions.critical_actions
            if s.category == "red_flag" and "differential_tree" in s.source
        ]

        # Ensure tree red flags are preserved in merged suggestions
        existing_red_flag_texts = {s.suggestion.lower()[:50] for s in merged_suggestions.critical_actions}
        for red_flag in tree_red_flags:
            if red_flag.suggestion.lower()[:50] not in existing_red_flag_texts:
                merged_suggestions.critical_actions.insert(0, red_flag)
                logger.debug(f"[MERGE] Preserved tree red flag: {red_flag.suggestion[:50]}...")

        # Rule 2 & 3: RAG suggestions already added by enhance_suggestions_with_clinical_conditions
        # The merge is implicit - RAG adds new suggestions, trees provide fallback

        # Add metadata about the merge
        merged_suggestions.gap_analysis["merge_metadata"] = {
            "rag_confidence": rag_result.confidence,
            "rag_can_override": rag_result.can_override_cache,
            "rag_matches_found": rag_result.matches_found,
            "tree_red_flags_preserved": len(tree_red_flags),
        }

        return merged_suggestions

    def _merge_gemini_suggestions(
        self,
        base_suggestions: "TriageSuggestions",
        gemini_suggestions: "TriageSuggestions"
    ):
        """
        Merge Gemini gap analysis suggestions into base suggestions.

        Gemini fills gaps - it doesn't override existing suggestions.
        Deduplication happens later in conflict resolution.

        Args:
            base_suggestions: Current suggestions (from trees + RAG)
            gemini_suggestions: Suggestions from Gemini gap analysis
        """
        # Get existing suggestion texts for deduplication
        existing_texts = set()
        for suggestion_list in [
            base_suggestions.critical_actions,
            base_suggestions.important_considerations,
            base_suggestions.nice_to_have
        ]:
            for s in suggestion_list:
                existing_texts.add(s.suggestion.lower()[:50])

        # Add Gemini critical actions (if not duplicates)
        for s in gemini_suggestions.critical_actions:
            if s.suggestion.lower()[:50] not in existing_texts:
                base_suggestions.critical_actions.append(s)
                existing_texts.add(s.suggestion.lower()[:50])

        # Add Gemini important considerations
        for s in gemini_suggestions.important_considerations:
            if s.suggestion.lower()[:50] not in existing_texts:
                base_suggestions.important_considerations.append(s)
                existing_texts.add(s.suggestion.lower()[:50])

        # Add Gemini nice-to-have
        for s in gemini_suggestions.nice_to_have:
            if s.suggestion.lower()[:50] not in existing_texts:
                base_suggestions.nice_to_have.append(s)
                existing_texts.add(s.suggestion.lower()[:50])

        # Merge gap_analysis
        if gemini_suggestions.gap_analysis:
            base_suggestions.gap_analysis.update(gemini_suggestions.gap_analysis)

        # Update model info
        if gemini_suggestions.model_used:
            base_suggestions.model_used = gemini_suggestions.model_used

    def _resolve_conflicts(
        self,
        suggestions: "TriageSuggestions",
        layer_map: Dict[str, LayerConfig]
    ) -> List[ConflictRecord]:
        """
        Resolve conflicts between layer suggestions.

        Resolution Rules:
        1. Patient Safety First: Red flags and allergy vetoes always win
        2. Evidence Over Opinion: RAG guidelines outweigh practice patterns
        3. Doctor Preference for Ties: When equal, respect doctor preference
        4. Deduplication: Remove duplicate suggestions, keep highest priority

        Returns:
            List of conflict records for logging
        """
        conflicts = []

        # Deduplicate by suggestion text similarity
        seen_suggestions = {}

        for priority_level, suggestion_list in [
            ("critical", suggestions.critical_actions),
            ("important", suggestions.important_considerations),
            ("consider", suggestions.nice_to_have)
        ]:
            unique = []
            for suggestion in suggestion_list:
                # Create a normalized key for deduplication
                norm_key = suggestion.suggestion.lower()[:50]

                if norm_key in seen_suggestions:
                    existing = seen_suggestions[norm_key]

                    # Record conflict
                    conflicts.append(ConflictRecord(
                        conflict_type="duplicate",
                        layer_1=existing.get("layer", "unknown"),
                        layer_1_suggestion=existing.get("suggestion", ""),
                        layer_1_priority=existing.get("priority", ""),
                        layer_2=getattr(suggestion, 'layer_sources', ['unknown'])[0] if hasattr(suggestion, 'layer_sources') and suggestion.layer_sources else "unknown",
                        layer_2_suggestion=suggestion.suggestion,
                        layer_2_priority=priority_level,
                        resolution_strategy="keep_higher_priority",
                        final_suggestion=existing.get("suggestion") if self._is_higher_priority(existing.get("priority", ""), priority_level) else suggestion.suggestion,
                        final_priority=existing.get("priority") if self._is_higher_priority(existing.get("priority", ""), priority_level) else priority_level,
                    ))
                else:
                    seen_suggestions[norm_key] = {
                        "suggestion": suggestion.suggestion,
                        "priority": priority_level,
                        "layer": getattr(suggestion, 'layer_sources', ['unknown'])[0] if hasattr(suggestion, 'layer_sources') and suggestion.layer_sources else "unknown",
                    }
                    unique.append(suggestion)

            # Replace list with deduplicated version
            suggestion_list.clear()
            suggestion_list.extend(unique)

        return conflicts

    def _is_higher_priority(self, priority1: str, priority2: str) -> bool:
        """Check if priority1 is higher than priority2."""
        priority_order = {"critical": 3, "important": 2, "consider": 1}
        return priority_order.get(priority1, 0) > priority_order.get(priority2, 0)

    async def _log_conflicts(
        self,
        extraction_id: str,
        conflicts: List[ConflictRecord],
        supabase_client
    ):
        """Log conflict records to database."""
        if not conflicts or not supabase_client or not extraction_id:
            return

        try:
            records = []
            for conflict in conflicts:
                records.append({
                    "extraction_id": extraction_id,
                    "conflict_type": conflict.conflict_type,
                    "layer_1": conflict.layer_1,
                    "layer_1_suggestion": conflict.layer_1_suggestion,
                    "layer_1_priority": conflict.layer_1_priority,
                    "layer_2": conflict.layer_2,
                    "layer_2_suggestion": conflict.layer_2_suggestion,
                    "layer_2_priority": conflict.layer_2_priority,
                    "resolution_strategy": conflict.resolution_strategy,
                    "final_suggestion": conflict.final_suggestion,
                    "final_priority": conflict.final_priority,
                    "resolution_notes": conflict.resolution_notes,
                })

            supabase_client.table("triage_conflict_log").insert(records).execute()
            logger.debug(f"[ORCHESTRATOR] Logged {len(conflicts)} conflicts")

        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Failed to log conflicts: {e}")

    async def _log_suggestions_with_layers(
        self,
        suggestions: "TriageSuggestions",
        extraction_id: str,
        doctor_id: Optional[str],
        supabase_client
    ):
        """Log suggestions with layer_sources metadata."""
        if not supabase_client or not extraction_id:
            return

        try:
            records = []

            for priority, suggestion_list in [
                ('critical_action', suggestions.critical_actions),
                ('important_consideration', suggestions.important_considerations),
                ('nice_to_have', suggestions.nice_to_have)
            ]:
                for idx, suggestion in enumerate(suggestion_list):
                    layer_sources = getattr(suggestion, 'layer_sources', ['base_mvp'])

                    records.append({
                        'extraction_id': extraction_id,
                        'doctor_id': doctor_id,
                        'suggestion_category': priority,
                        'suggestion_type': suggestion.category,
                        'suggestion_text': suggestion.suggestion,
                        'source_layer': suggestion.source,
                        'priority_rank': idx + 1,
                        'rationale': suggestion.rationale,
                        'layer_sources': layer_sources,
                    })

            if records:
                supabase_client.table("triage_suggestion_log").insert(records).execute()
                logger.info(f"[ORCHESTRATOR] Logged {len(records)} suggestions with layer sources")

        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Failed to log suggestions: {e}")


# Singleton instance
_orchestrator_instance = None


def get_triage_orchestrator() -> TriageMultiLayerOrchestrator:
    """Get singleton TriageMultiLayerOrchestrator instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = TriageMultiLayerOrchestrator()
    return _orchestrator_instance

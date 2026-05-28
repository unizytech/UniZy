"""
RAG Guidelines Layer

Phase 3 of Triage Engine Multi-Layer system.
Retrieves relevant clinical guidelines using RAG for triage augmentation:
- Semantic search for relevant guidelines (legacy: clinical_guidelines table)
- Enhanced search for clinical conditions (new: clinical_conditions table)
- Evidence-based recommendation enhancement
- Citation support for suggestions
- Numeric threshold matching (BP, Hb values)

This layer runs AFTER hospital intelligence to add evidence context.

Enhanced v2 (Jan 2026):
- Integrates with clinical_conditions table for structured STG data
- Uses search_clinical_chunks_hybrid RPC for semantic + filter search
- Supports comorbidity-aware treatment recommendations
- Extracts red flags and emergency triggers from chunks
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class GuidelineMatch:
    """A matched clinical guideline from RAG search."""
    id: str
    source_name: str  # "ICMR STG", "IAP Guidelines"
    source_organization: Optional[str] = None
    document_title: Optional[str] = None
    chunk_text: str = ""
    topics: List[str] = field(default_factory=list)
    presentations: List[str] = field(default_factory=list)
    evidence_level: Optional[str] = None  # Level A, Level B, Expert Consensus
    publication_year: Optional[int] = None
    similarity: float = 0.0

    @property
    def citation(self) -> str:
        """Generate citation string."""
        parts = [self.source_name]
        if self.publication_year:
            parts.append(f"({self.publication_year})")
        if self.evidence_level:
            parts.append(f"[{self.evidence_level}]")
        return " ".join(parts)

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "GuidelineMatch":
        """Create from database row."""
        return cls(
            id=row.get("id"),
            source_name=row.get("source_name", "Unknown"),
            source_organization=row.get("source_organization"),
            document_title=row.get("document_title"),
            chunk_text=row.get("chunk_text", ""),
            topics=row.get("topics") or [],
            presentations=row.get("presentations") or [],
            evidence_level=row.get("evidence_level"),
            publication_year=row.get("publication_year"),
            similarity=float(row.get("similarity", 0)),
        )


@dataclass
class ClinicalConditionMatch:
    """
    A matched clinical condition chunk from enhanced RAG search.

    Maps to clinical_chunks table with rich metadata for triage.
    """
    chunk_id: str
    condition_id: str
    condition_name: str
    condition_code: str
    specialty: str
    chunk_type: str  # triage_criteria, treatment_primary, comorbidity_pathway, etc.
    content_text: str
    content_json: Optional[Dict[str, Any]] = None

    # Triage-specific metadata
    urgency_default: Optional[str] = None
    has_emergency_triggers: bool = False
    has_red_flags: bool = False
    care_levels: List[str] = field(default_factory=list)

    # For comorbidity pathways
    comorbidity: Optional[str] = None

    # For drug-related chunks
    drug_classes: List[str] = field(default_factory=list)
    drug_names: List[str] = field(default_factory=list)
    contraindications: List[str] = field(default_factory=list)

    # Numeric thresholds (for BP, Hb matching)
    numeric_thresholds: Optional[Dict[str, Any]] = None

    # Source tracking
    source_section: Optional[str] = None
    source_name: Optional[str] = None

    # Search relevance
    similarity: float = 0.0

    @property
    def citation(self) -> str:
        """Generate citation string."""
        parts = [self.source_name or "Clinical Guidelines"]
        parts.append(f"[{self.condition_name}]")
        if self.chunk_type:
            parts.append(f"({self.chunk_type})")
        return " ".join(parts)

    @property
    def is_high_priority(self) -> bool:
        """Check if this chunk contains high-priority content."""
        return self.has_emergency_triggers or self.has_red_flags or self.urgency_default == "emergency"

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "ClinicalConditionMatch":
        """Create from search_clinical_chunks_hybrid RPC result."""
        return cls(
            chunk_id=row.get("chunk_id", ""),
            condition_id=row.get("condition_id", ""),
            condition_name=row.get("condition_name", "Unknown"),
            condition_code=row.get("condition_code", ""),
            specialty=row.get("specialty", ""),
            chunk_type=row.get("chunk_type", ""),
            content_text=row.get("content_text", ""),
            content_json=row.get("content_json"),
            urgency_default=row.get("urgency_default"),
            has_emergency_triggers=row.get("has_emergency_triggers", False),
            has_red_flags=row.get("has_red_flags", False),
            care_levels=row.get("care_levels") or [],
            comorbidity=row.get("comorbidity"),
            drug_classes=row.get("drug_classes") or [],
            drug_names=row.get("drug_names") or [],
            contraindications=row.get("contraindications") or [],
            numeric_thresholds=row.get("numeric_thresholds"),
            source_section=row.get("source_section"),
            source_name=row.get("source_name"),
            similarity=float(row.get("similarity", 0)),
        )


@dataclass
class ExtractionContext:
    """
    Context extracted from medical extraction for RAG query construction.

    Contains all relevant segments for building intelligent queries.
    """
    chief_complaints: List[str] = field(default_factory=list)
    diagnoses: List[str] = field(default_factory=list)
    history: List[str] = field(default_factory=list)
    comorbidities: List[str] = field(default_factory=list)
    allergies: List[str] = field(default_factory=list)
    current_medications: List[str] = field(default_factory=list)

    # Vitals for numeric threshold matching
    sbp: Optional[int] = None  # Systolic BP
    dbp: Optional[int] = None  # Diastolic BP
    hb: Optional[float] = None  # Hemoglobin

    # Specialty context
    specialty: str = "general_medicine"
    consultation_type: Optional[str] = None

    @property
    def has_vitals(self) -> bool:
        """Check if any vitals are present."""
        return self.sbp is not None or self.dbp is not None or self.hb is not None

    def build_query_text(self) -> str:
        """Build query text from extraction context."""
        parts = []

        # Primary: chief complaints and diagnoses
        if self.chief_complaints:
            parts.extend(self.chief_complaints[:3])
        if self.diagnoses:
            parts.extend(self.diagnoses[:2])

        # Secondary: comorbidities (important for pathway matching)
        if self.comorbidities:
            parts.extend(self.comorbidities[:2])

        return " ".join(parts) if parts else ""


class RAGGuidelinesLayer:
    """
    Retrieves relevant clinical guidelines for triage augmentation.

    This layer:
    1. Generates embedding for chief complaints
    2. Searches clinical_guidelines using cosine similarity
    3. Filters by specialty and topic relevance
    4. Enhances suggestions with evidence citations
    """

    def __init__(self, supabase_client=None):
        """Initialize with optional Supabase client."""
        self.supabase = supabase_client
        self._embedding_service = None

    @property
    def embedding_service(self):
        """Lazy load embedding service."""
        if self._embedding_service is None:
            from services.qa.embedding_service import EmbeddingService
            self._embedding_service = EmbeddingService()
        return self._embedding_service

    async def search_guidelines(
        self,
        chief_complaints: List[str],
        specialty: str,
        topics: Optional[List[str]] = None,
        top_k: int = 5,
        min_similarity: float = 0.5,
        supabase_client=None
    ) -> List[GuidelineMatch]:
        """
        Search for relevant clinical guidelines using semantic similarity.

        Args:
            chief_complaints: List of chief complaints to search for
            specialty: Doctor specialty to filter by
            topics: Optional additional topic keywords
            top_k: Maximum number of results to return
            min_similarity: Minimum similarity threshold (0-1)
            supabase_client: Supabase client for DB operations

        Returns:
            List of GuidelineMatch objects sorted by relevance
        """
        client = supabase_client or self.supabase
        if not client:
            logger.warning("[RAG_LAYER] No Supabase client available")
            return []

        if not chief_complaints:
            logger.debug("[RAG_LAYER] No chief complaints provided")
            return []

        try:
            # Build query text from chief complaints and topics
            query_parts = chief_complaints[:3]  # Limit to top 3 complaints
            if topics:
                query_parts.extend(topics[:3])

            query_text = " ".join(query_parts)
            logger.info(f"[RAG_LAYER] Searching guidelines for: {query_text[:100]}... (specialty: {specialty})")

            # Generate embedding for query
            embeddings, usage = await self.embedding_service.generate_embedding(
                texts=[query_text],
                input_type="search_query",
                use_cache=True
            )

            if not embeddings:
                logger.warning("[RAG_LAYER] Failed to generate query embedding")
                return []

            # Pad embedding to 1536 dimensions if needed
            query_embedding = embeddings[0]
            if len(query_embedding) < 1536:
                query_embedding = query_embedding + [0.0] * (1536 - len(query_embedding))

            # Search using RPC function
            result = client.rpc(
                'match_clinical_guidelines',
                {
                    'query_embedding': query_embedding,
                    'match_specialty': specialty,
                    'match_topics': topics,  # Optional topic filter
                    'match_count': top_k,
                    'similarity_threshold': min_similarity
                }
            ).execute()

            matches = []
            for row in result.data or []:
                match = GuidelineMatch.from_db_row(row)
                matches.append(match)

            logger.info(f"[RAG_LAYER] Found {len(matches)} guideline matches (min_sim: {min_similarity})")
            return matches

        except Exception as e:
            logger.error(f"[RAG_LAYER] Guideline search failed: {e}", exc_info=True)
            return []

    # =========================================================================
    # Enhanced Clinical Conditions Search (v2)
    # =========================================================================

    def extract_context_from_extraction(
        self,
        extraction: Dict[str, Any]
    ) -> ExtractionContext:
        """
        Extract relevant context from a medical extraction for RAG queries.

        Searches for segments using known segment codes:
        - CHIEF_COMPLAINTS, Chief Complaints
        - DIAGNOSIS
        - HISTORY, HISTORY_OF_PRESENT_ILLNESS
        - VITALS
        - ALLERGIES
        - PRESCRIPTION, TREATMENT_PLAN

        Args:
            extraction: Medical extraction record from database

        Returns:
            ExtractionContext with all relevant data
        """
        context = ExtractionContext()

        # Get extraction JSON (prefer edited, fallback to original)
        data = extraction.get("edited_extraction_json") or extraction.get("original_extraction_json") or {}

        # Helper to extract text from a dict (extracts known text fields)
        def extract_text_from_dict(d: Dict[str, Any]) -> List[str]:
            """Extract text values from dict, preferring specific known fields."""
            texts = []
            # Known text fields in order of preference
            text_fields = ['complaint', 'diagnosis', 'medicine', 'medication', 'drug',
                          'allergy', 'finding', 'symptom', 'name', 'condition', 'value', 'description']
            for field in text_fields:
                if field in d and isinstance(d[field], str) and d[field]:
                    texts.append(d[field])
                    break
            else:
                # If no known field found, extract all string values
                for v in d.values():
                    if isinstance(v, str) and v and len(v) > 2:
                        texts.append(v)
            return texts

        # Helper to extract values from segment (with deduplication)
        def get_segment_values(code_patterns: List[str]) -> List[str]:
            values = []
            matched_keys = set()
            for key, value in data.items():
                if key in matched_keys:
                    continue
                key_lower = key.lower().replace("_", "").replace(" ", "")
                for pattern in code_patterns:
                    pattern_lower = pattern.lower().replace("_", "").replace(" ", "")
                    if pattern_lower == key_lower or (len(pattern_lower) > 5 and pattern_lower in key_lower):
                        matched_keys.add(key)
                        if isinstance(value, list):
                            for item in value:
                                if isinstance(item, dict):
                                    values.extend(extract_text_from_dict(item))
                                elif isinstance(item, str) and item:
                                    values.append(item)
                        elif isinstance(value, str) and value:
                            values.append(value)
                        elif isinstance(value, dict):
                            # Handle nested structures like HISTORY: {medical_history: [...]}
                            for sub_key, sub_val in value.items():
                                if isinstance(sub_val, list):
                                    for item in sub_val:
                                        if isinstance(item, dict):
                                            values.extend(extract_text_from_dict(item))
                                        elif isinstance(item, str) and item:
                                            values.append(item)
                                elif isinstance(sub_val, str) and sub_val:
                                    values.append(sub_val)
                        break  # Only match once per key
            return list(dict.fromkeys(values))  # Deduplicate while preserving order

        # Extract chief complaints
        context.chief_complaints = get_segment_values([
            "CHIEF_COMPLAINTS", "Chief Complaints", "chiefComplaints",
            "chief_complaint", "presenting_complaints"
        ])

        # Extract diagnoses
        context.diagnoses = get_segment_values([
            "DIAGNOSIS", "diagnosis", "provisional_diagnosis",
            "final_diagnosis", "working_diagnosis"
        ])

        # Extract history
        context.history = get_segment_values([
            "HISTORY", "history_of_present_illness", "medical_history",
            "past_history", "HISTORY_OF_PRESENT_ILLNESS"
        ])

        # Extract allergies
        context.allergies = get_segment_values([
            "ALLERGIES", "allergy", "drug_allergies", "known_allergies"
        ])

        # Extract current medications
        context.current_medications = get_segment_values([
            "PRESCRIPTION", "current_medications", "medications",
            "TREATMENT_PLAN", "medicines"
        ])

        # Extract comorbidities from history, diagnoses, or separate field
        # Combine all text for comorbidity detection
        all_text = " ".join(
            context.history + context.diagnoses + context.chief_complaints
        ).lower()

        # Comorbidity patterns with their standard names
        comorbidity_patterns = {
            "diabetes": ["diabetes", "diabetic", "dm ", "dm,", "type 2 dm", "type 1 dm", "t2dm", "t1dm"],
            "chronic_kidney_disease": ["ckd", "chronic kidney", "renal failure", "renal disease", "nephropathy"],
            "heart_failure": ["heart failure", "chf", "ccf", "cardiac failure", "hfref", "hfpef"],
            "coronary_artery_disease": ["cad", "coronary", "ihd", "ischemic heart", "mi ", "myocardial infarction", "angina"],
            "previous_stroke": ["stroke", "cva", "cerebrovascular", "hemiplegia", "hemiparesis"],
            "hypertension": ["hypertension", "hypertensive", "htn", "high blood pressure", "elevated bp"],
            "copd": ["copd", "chronic obstructive", "emphysema", "chronic bronchitis"],
            "asthma": ["asthma", "asthmatic", "bronchial asthma"],
            "liver_disease": ["liver disease", "cirrhosis", "hepatitis", "hepatic"],
            "thyroid": ["thyroid", "hypothyroid", "hyperthyroid", "goiter"],
        }

        # Negation patterns to check before adding comorbidity
        negation_patterns = [
            "no history of", "no h/o", "denies", "denied", "negative for",
            "without", "no known", "not known", "rules out", "ruled out",
            "no ", "non-", "never had", "no diagnosis of", "not diagnosed"
        ]

        def is_negated(text: str, pattern: str) -> bool:
            """Check if a pattern is negated in the text."""
            # Find all occurrences of the pattern
            import re
            for match in re.finditer(re.escape(pattern), text):
                start_pos = match.start()
                # Check the 50 characters before the match for negation
                context_before = text[max(0, start_pos - 50):start_pos].lower()
                # Check if any negation pattern appears before this match
                for neg in negation_patterns:
                    if neg in context_before:
                        return True
            return False

        for standard_name, patterns in comorbidity_patterns.items():
            for pattern in patterns:
                if pattern in all_text:
                    # Check if the pattern is negated
                    if not is_negated(all_text, pattern):
                        context.comorbidities.append(standard_name)
                    break  # Only check once per comorbidity type

        context.comorbidities = list(dict.fromkeys(context.comorbidities))  # Deduplicate preserving order

        # Extract vitals
        vitals_data = data.get("VITALS") or data.get("vitals") or {}
        if isinstance(vitals_data, dict):
            # Try to extract BP
            bp = vitals_data.get("blood_pressure") or vitals_data.get("bp") or ""
            if isinstance(bp, str) and "/" in bp:
                try:
                    parts = bp.replace("mmHg", "").strip().split("/")
                    context.sbp = int(parts[0].strip())
                    context.dbp = int(parts[1].strip())
                except (ValueError, IndexError):
                    pass
            elif isinstance(vitals_data.get("sbp"), (int, float)):
                context.sbp = int(vitals_data["sbp"])
            elif isinstance(vitals_data.get("systolic"), (int, float)):
                context.sbp = int(vitals_data["systolic"])

            if isinstance(vitals_data.get("dbp"), (int, float)):
                context.dbp = int(vitals_data["dbp"])
            elif isinstance(vitals_data.get("diastolic"), (int, float)):
                context.dbp = int(vitals_data["diastolic"])

            # Hemoglobin
            hb = vitals_data.get("hemoglobin") or vitals_data.get("hb") or vitals_data.get("Hb")
            if isinstance(hb, (int, float)):
                context.hb = float(hb)
            elif isinstance(hb, str):
                try:
                    context.hb = float(hb.replace("g/dL", "").replace("g/dl", "").strip())
                except ValueError:
                    pass

        # Get specialty from consultation type
        consultation_type = extraction.get("consultation_types", {})
        if isinstance(consultation_type, dict):
            context.consultation_type = consultation_type.get("type_code")

        return context

    async def search_clinical_conditions(
        self,
        context: ExtractionContext,
        chunk_types: Optional[List[str]] = None,
        top_k: int = 10,
        min_similarity: float = 0.4,
        supabase_client=None
    ) -> List[ClinicalConditionMatch]:
        """
        Search clinical conditions using the enhanced hybrid search.

        Uses search_clinical_chunks_hybrid RPC with:
        - Semantic similarity on query text
        - Specialty filtering
        - Comorbidity filtering
        - Numeric threshold matching (BP, Hb)

        Args:
            context: ExtractionContext with patient data
            chunk_types: Optional list of chunk types to filter
            top_k: Maximum results to return
            min_similarity: Minimum similarity threshold
            supabase_client: Supabase client

        Returns:
            List of ClinicalConditionMatch objects
        """
        client = supabase_client or self.supabase
        if not client:
            logger.warning("[RAG_LAYER_V2] No Supabase client available")
            return []

        query_text = context.build_query_text()
        if not query_text:
            logger.debug("[RAG_LAYER_V2] No query text from context")
            return []

        try:
            logger.info(f"[RAG_LAYER_V2] Searching clinical conditions for: {query_text[:100]}...")

            # Generate embedding
            embeddings, _ = await self.embedding_service.generate_embedding(
                texts=[query_text],
                input_type="search_query",
                use_cache=True
            )

            if not embeddings:
                logger.warning("[RAG_LAYER_V2] Failed to generate query embedding")
                return []

            # Pad to 1536 dimensions
            query_embedding = embeddings[0]
            if len(query_embedding) < 1536:
                query_embedding = query_embedding + [0.0] * (1536 - len(query_embedding))

            # Build RPC parameters
            rpc_params = {
                "query_embedding": query_embedding,
                "query_text": query_text,
                "filter_specialty": context.specialty if context.specialty != "general_medicine" else None,
                "filter_chunk_types": chunk_types,
                "filter_urgency": None,
                "filter_comorbidity": context.comorbidities[0] if context.comorbidities else None,
                "filter_care_level": None,
                "filter_drug_class": None,
                "patient_sbp": context.sbp,
                "patient_dbp": context.dbp,
                "patient_hb": context.hb,
                "match_count": top_k,
                "min_similarity": min_similarity,
            }

            logger.debug(f"[RAG_LAYER_V2] RPC params: specialty={context.specialty}, "
                        f"comorbidity={context.comorbidities}, sbp={context.sbp}, dbp={context.dbp}")

            result = client.rpc("search_clinical_chunks_hybrid", rpc_params).execute()

            matches = []
            for row in result.data or []:
                match = ClinicalConditionMatch.from_db_row(row)
                matches.append(match)

            logger.info(f"[RAG_LAYER_V2] Found {len(matches)} clinical condition matches")
            return matches

        except Exception as e:
            logger.error(f"[RAG_LAYER_V2] Clinical condition search failed: {e}", exc_info=True)
            return []

    async def search_comorbidity_pathways(
        self,
        comorbidities: List[str],
        specialty: str,
        supabase_client=None
    ) -> List[ClinicalConditionMatch]:
        """
        Search specifically for comorbidity treatment pathways.

        Uses direct SQL query to find all comorbidity_pathway chunks
        that match the given comorbidities.

        Args:
            comorbidities: List of comorbidities (e.g., ["diabetes", "ckd"])
            specialty: Medical specialty
            supabase_client: Supabase client

        Returns:
            List of comorbidity pathway matches
        """
        client = supabase_client or self.supabase
        if not client or not comorbidities:
            return []

        all_matches = []
        for comorbidity in comorbidities[:3]:  # Limit to 3 comorbidities
            try:
                # Query directly for comorbidity_pathway chunks matching this comorbidity
                result = client.table("clinical_chunks").select(
                    "id, condition_id, chunk_type, content_json, content_text, "
                    "comorbidity, care_levels, drug_classes, contraindications, "
                    "clinical_conditions!inner(id, name, condition_id, specialty, source_name)"
                ).eq("chunk_type", "comorbidity_pathway").eq("comorbidity", comorbidity).execute()

                for row in result.data or []:
                    condition = row.get("clinical_conditions", {})
                    match = ClinicalConditionMatch(
                        chunk_id=row.get("id", ""),
                        condition_id=condition.get("id", ""),
                        condition_name=condition.get("name", ""),
                        condition_code=condition.get("condition_id", ""),
                        specialty=condition.get("specialty", specialty),
                        chunk_type="comorbidity_pathway",
                        content_text=row.get("content_text", ""),
                        content_json=row.get("content_json"),
                        comorbidity=comorbidity,
                        care_levels=row.get("care_levels") or [],
                        drug_classes=row.get("drug_classes") or [],
                        contraindications=row.get("contraindications") or [],
                        source_name=condition.get("source_name"),
                        similarity=1.0,  # Direct match
                    )
                    all_matches.append(match)

                logger.debug(f"[RAG_LAYER_V2] Found {len(result.data or [])} pathways for {comorbidity}")

            except Exception as e:
                logger.warning(f"[RAG_LAYER_V2] Comorbidity pathway search failed for {comorbidity}: {e}")

        return all_matches

    async def search_red_flags(
        self,
        specialty: str,
        supabase_client=None
    ) -> List[Dict[str, Any]]:
        """
        Get all red flags for a specialty.

        Args:
            specialty: Medical specialty
            supabase_client: Supabase client

        Returns:
            List of red flag dictionaries
        """
        client = supabase_client or self.supabase
        if not client:
            return []

        try:
            result = client.rpc("get_red_flags_by_specialty", {
                "p_specialty": specialty
            }).execute()

            return result.data or []

        except Exception as e:
            logger.warning(f"[RAG_LAYER_V2] Red flags search failed: {e}")
            return []

    def enhance_suggestions_with_clinical_conditions(
        self,
        suggestions: "TriageSuggestions",
        condition_matches: List[ClinicalConditionMatch],
        context: ExtractionContext
    ) -> "TriageSuggestions":
        """
        Enhance triage suggestions with clinical condition knowledge.

        Adds:
        1. Red flag warnings from matched conditions
        2. Comorbidity-specific treatment guidance
        3. Drug contraindication checks
        4. Care level recommendations
        5. Citations to matched guidelines

        Args:
            suggestions: Current triage suggestions
            condition_matches: Matched clinical condition chunks
            context: Extraction context with patient data

        Returns:
            Enhanced TriageSuggestions
        """
        if not condition_matches:
            return suggestions

        from .triage_engine import TriageSuggestion

        # Separate matches by type for targeted enhancement
        red_flag_matches = [m for m in condition_matches if m.has_red_flags or m.chunk_type == "red_flags"]
        treatment_matches = [m for m in condition_matches if "treatment" in m.chunk_type]
        comorbidity_matches = [m for m in condition_matches if m.chunk_type == "comorbidity_pathway"]
        drug_matches = [m for m in condition_matches if "drug" in m.chunk_type or "formulary" in m.chunk_type]

        new_critical_actions = []
        new_important_considerations = []

        # 1. Add red flag warnings
        for match in red_flag_matches[:3]:
            if match.content_json and "red_flags" in match.content_json:
                for flag in match.content_json.get("red_flags", [])[:2]:
                    flag_text = flag.get("flag") if isinstance(flag, dict) else str(flag)
                    action = flag.get("action", "") if isinstance(flag, dict) else ""

                    new_critical_actions.append(TriageSuggestion(
                        category="red_flag",
                        suggestion=f"⚠️ Red Flag: {flag_text}",
                        priority="critical",
                        rationale=f"Clinical guideline warning. Action: {action}. {match.citation}",
                        source="rag_clinical_conditions",
                        related_presentation=match.condition_name,
                    ))

        # 2. Add comorbidity-specific guidance
        for match in comorbidity_matches:
            if match.comorbidity and match.comorbidity in [c.lower().replace("_", " ") for c in context.comorbidities]:
                # Extract preferred drugs
                if match.content_json:
                    preferred = match.content_json.get("preferred_drugs", [])
                    avoid = match.content_json.get("avoid", [])
                    special_notes = match.content_json.get("special_notes", "")

                    if preferred:
                        new_important_considerations.append(TriageSuggestion(
                            category="medication",
                            suggestion=f"Consider: {', '.join(preferred[:3])} (preferred for {match.comorbidity})",
                            priority="important",
                            rationale=f"{special_notes} {match.citation}",
                            source="rag_comorbidity_pathway",
                            related_presentation=match.condition_name,
                        ))

                    if avoid:
                        new_important_considerations.append(TriageSuggestion(
                            category="caution",
                            suggestion=f"Avoid: {', '.join(avoid[:3])} (due to {match.comorbidity})",
                            priority="important",
                            rationale=f"Contraindicated or less preferred. {match.citation}",
                            source="rag_comorbidity_pathway",
                            related_presentation=match.condition_name,
                        ))

        # 3. Check drug contraindications against current medications
        if context.current_medications and drug_matches:
            current_meds_lower = [m.lower() for m in context.current_medications]
            for match in drug_matches:
                for contraindication in match.contraindications:
                    if any(contraindication.lower() in med for med in current_meds_lower):
                        new_critical_actions.append(TriageSuggestion(
                            category="contraindication",
                            suggestion=f"⚠️ Review: {contraindication} interaction risk",
                            priority="critical",
                            rationale=f"Patient on medication that may interact. {match.citation}",
                            source="rag_drug_check",
                            related_presentation=match.condition_name,
                        ))

        # 4. Add new suggestions to existing lists
        # Prepend critical actions (they're most important)
        suggestions.critical_actions = new_critical_actions + list(suggestions.critical_actions)
        suggestions.important_considerations = new_important_considerations + list(suggestions.important_considerations)

        # 5. Add citations to existing suggestions
        citation_count = self._add_citations_from_conditions(suggestions, condition_matches)

        # 6. Update metadata
        suggestions.gap_analysis["rag_clinical_conditions_applied"] = {
            "conditions_matched": len(set(m.condition_name for m in condition_matches)),
            "chunks_found": len(condition_matches),
            "red_flags_added": len([m for m in condition_matches if m.has_red_flags]),
            "comorbidity_guidance_added": len(comorbidity_matches),
            "citations_added": citation_count,
            "patient_vitals": {
                "sbp": context.sbp,
                "dbp": context.dbp,
                "hb": context.hb,
            } if context.has_vitals else None,
            "matched_conditions": [
                {
                    "condition": m.condition_name,
                    "chunk_type": m.chunk_type,
                    "similarity": round(m.similarity, 3),
                    "source": m.source_name,
                }
                for m in condition_matches[:10]
            ]
        }

        logger.info(f"[RAG_LAYER_V2] Enhanced suggestions: +{len(new_critical_actions)} critical, "
                   f"+{len(new_important_considerations)} important, {citation_count} citations")

        return suggestions

    def _add_citations_from_conditions(
        self,
        suggestions: "TriageSuggestions",
        condition_matches: List[ClinicalConditionMatch]
    ) -> int:
        """Add citations from matched conditions to relevant suggestions."""
        if not condition_matches:
            return 0

        # Build keyword mapping
        condition_keywords: Dict[str, ClinicalConditionMatch] = {}
        for match in condition_matches:
            # Add condition name words
            for word in match.condition_name.lower().split():
                if len(word) > 3:
                    condition_keywords[word] = match

            # Add drug names and classes
            for drug in match.drug_names:
                condition_keywords[drug.lower()] = match
            for drug_class in match.drug_classes:
                condition_keywords[drug_class.lower()] = match

        citation_count = 0
        for suggestion_list in [
            suggestions.critical_actions,
            suggestions.important_considerations,
            suggestions.nice_to_have
        ]:
            for suggestion in suggestion_list:
                suggestion_text = (suggestion.suggestion + " " + suggestion.rationale).lower()

                # Use dict keyed by chunk_id to deduplicate (dataclasses aren't hashable)
                matched: Dict[str, ClinicalConditionMatch] = {}
                for keyword, match in condition_keywords.items():
                    if keyword in suggestion_text:
                        matched[match.chunk_id] = match

                for match in list(matched.values())[:1]:  # Max 1 citation per suggestion
                    citation = f"[{match.citation}]"
                    if citation not in suggestion.rationale:
                        suggestion.rationale = suggestion.rationale.rstrip() + f" {citation}"
                        citation_count += 1

        return citation_count

    async def search_guidelines_by_keywords(
        self,
        keywords: List[str],
        specialty: str,
        top_k: int = 10,
        supabase_client=None
    ) -> List[GuidelineMatch]:
        """
        Fallback keyword search when embeddings unavailable.

        Args:
            keywords: List of keywords to search for
            specialty: Doctor specialty to filter by
            top_k: Maximum number of results
            supabase_client: Supabase client

        Returns:
            List of GuidelineMatch objects
        """
        client = supabase_client or self.supabase
        if not client or not keywords:
            return []

        try:
            query_text = " ".join(keywords)

            result = client.rpc(
                'search_guidelines_by_keywords',
                {
                    'search_query': query_text,
                    'match_specialty': specialty,
                    'match_count': top_k
                }
            ).execute()

            matches = []
            for row in result.data or []:
                # Keyword search returns slightly different format
                match = GuidelineMatch(
                    id=row.get("id"),
                    source_name=row.get("source_name", "Unknown"),
                    document_title=row.get("document_title"),
                    chunk_text=row.get("chunk_text", ""),
                    topics=row.get("topics") or [],
                    evidence_level=row.get("evidence_level"),
                    similarity=float(row.get("rank", 0)),  # Use FTS rank as similarity
                )
                matches.append(match)

            return matches

        except Exception as e:
            logger.warning(f"[RAG_LAYER] Keyword search failed: {e}")
            return []

    def enhance_gemini_prompt(
        self,
        base_prompt: str,
        guideline_matches: List[GuidelineMatch],
        max_guidelines: int = 3
    ) -> str:
        """
        Enhance Gemini prompt with relevant guideline context.

        Args:
            base_prompt: Original prompt for Gemini
            guideline_matches: Matched guidelines from search
            max_guidelines: Maximum number of guidelines to include

        Returns:
            Enhanced prompt with guideline context
        """
        if not guideline_matches:
            return base_prompt

        # Build guideline context section
        guideline_sections = []
        for i, match in enumerate(guideline_matches[:max_guidelines]):
            section = f"""
**Guideline {i+1}: {match.source_name}**
- Source: {match.source_organization or 'N/A'}
- Evidence Level: {match.evidence_level or 'N/A'}
- Year: {match.publication_year or 'N/A'}
- Relevant Topics: {', '.join(match.topics[:5]) if match.topics else 'N/A'}

Excerpt:
{match.chunk_text[:500]}...
"""
            guideline_sections.append(section)

        guidelines_text = "\n".join(guideline_sections)

        # Insert guideline context before the user data section
        enhanced_prompt = f"""{base_prompt}

**Relevant Clinical Guidelines (Use for evidence-based recommendations):**
{guidelines_text}

When making suggestions, cite relevant guidelines using [Source: Guideline Name] format.
"""

        return enhanced_prompt

    def enhance_suggestions_with_citations(
        self,
        suggestions: "TriageSuggestions",
        guideline_matches: List[GuidelineMatch]
    ) -> "TriageSuggestions":
        """
        Enhance suggestions with guideline citations.

        Adds:
        1. Citation tags to matching suggestions
        2. Guideline matches to gap_analysis metadata
        3. Evidence level annotations

        Args:
            suggestions: Current triage suggestions
            guideline_matches: Matched guidelines from search

        Returns:
            Enhanced TriageSuggestions with citations
        """
        if not guideline_matches:
            return suggestions

        # Build keyword to guideline mapping for citation matching
        guideline_keywords: Dict[str, GuidelineMatch] = {}
        for match in guideline_matches:
            # Extract keywords from topics and chunk text
            for topic in match.topics:
                guideline_keywords[topic.lower()] = match

            # Extract key terms from chunk text
            chunk_words = match.chunk_text.lower().split()
            for word in chunk_words:
                if len(word) > 5:  # Skip short words
                    guideline_keywords[word] = match

        citation_count = 0

        # Process each suggestion
        for suggestion_list in [
            suggestions.critical_actions,
            suggestions.important_considerations,
            suggestions.nice_to_have
        ]:
            for suggestion in suggestion_list:
                suggestion_lower = suggestion.suggestion.lower() + " " + suggestion.rationale.lower()

                # Find matching guidelines
                matched_guidelines = set()
                for keyword, match in guideline_keywords.items():
                    if keyword in suggestion_lower:
                        matched_guidelines.add(match)

                # Add citations for matches
                for match in list(matched_guidelines)[:2]:  # Limit to 2 citations per suggestion
                    citation = f"[Source: {match.citation}]"
                    if citation not in suggestion.rationale:
                        suggestion.rationale += f" {citation}"
                        citation_count += 1

        # Add RAG metadata to gap_analysis
        suggestions.gap_analysis["rag_guidelines_applied"] = {
            "guidelines_found": len(guideline_matches),
            "citations_added": citation_count,
            "sources": [
                {
                    "source_name": m.source_name,
                    "evidence_level": m.evidence_level,
                    "similarity": m.similarity,
                    "topics": m.topics[:5]
                }
                for m in guideline_matches[:5]
            ]
        }

        if citation_count > 0:
            logger.info(f"[RAG_LAYER] Added {citation_count} citations from {len(guideline_matches)} guidelines")

        return suggestions


# Singleton instance
_rag_layer_instance = None


def get_rag_guidelines_layer() -> RAGGuidelinesLayer:
    """Get singleton RAGGuidelinesLayer instance."""
    global _rag_layer_instance
    if _rag_layer_instance is None:
        _rag_layer_instance = RAGGuidelinesLayer()
    return _rag_layer_instance

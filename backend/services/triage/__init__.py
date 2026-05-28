"""
Triage Suggestion Engine

Provides clinical triage suggestions based on extraction data.
Uses Gemini AI + hardcoded differential diagnosis trees (MVP).
Multi-layer architecture with configurable layers (Phases 1-4).

Components:
- structured_insights.py: Dynamic mapper from extraction JSON to triage-ready format
- differential_trees.py: India-specific differential diagnosis trees
- triage_engine.py: Main engine that generates suggestions (MVP)
- doctor_practice_layer.py: Phase 1 - Doctor practice style learning
- hospital_intelligence_layer.py: Phase 2 - Hospital/peer intelligence
- rag_guidelines_layer.py: Phase 3 - RAG clinical guidelines (simple)
- multi_layer_orchestrator.py: Phase 4 - Multi-layer orchestration
- guideline_ingestion_service.py: Phase 3 - Guideline ingestion pipeline (simple)

Enhanced RAG (v2):
- clinical_condition_models.py: Pydantic validators for structured STG JSON
- clinical_chunking_service.py: Semantic chunk extraction
- clinical_condition_ingestion_service.py: Enhanced ingestion pipeline
"""

from .structured_insights import (
    StructuredInsights,
    StructuredInsightsMapper,
    map_extraction_to_insights,
    map_extraction_with_patient_history,
    CONSULTATION_TYPE_TO_SPECIALTY,
)
from .differential_trees import (
    DIFFERENTIAL_TREES,
    get_differential,
    get_all_presentations,
    match_presentations,
    get_red_flags,
    get_first_line_investigations,
    get_history_essentials,
)
from .triage_engine import (
    TriageSuggestionEngine,
    TriageSuggestions,
    TriageSuggestion,
    DoctorPreferences,
    fetch_doctor_preferences,
    generate_triage_suggestions,
    generate_triage_from_extraction,
    generate_triage_from_extraction_v2,
)

# Phase 1: Doctor Practice Style Layer
from .doctor_practice_layer import (
    DoctorPracticeLayer,
    DoctorPracticeStyle,
    get_practice_layer,
)

# Phase 2: Hospital Intelligence Layer
from .hospital_intelligence_layer import (
    HospitalIntelligenceLayer,
    HospitalPatterns,
    PeerComparison,
    OutlierFlag,
    HospitalPatternAggregator,
    get_hospital_intelligence_layer,
    get_hospital_aggregator,
)

# Phase 3: RAG Guidelines Layer
from .rag_guidelines_layer import (
    RAGGuidelinesLayer,
    GuidelineMatch,
    ClinicalConditionMatch,
    ExtractionContext,
    get_rag_guidelines_layer,
)
from .guideline_ingestion_service import (
    GuidelineIngestionService,
    GuidelineMetadata,
    IngestionResult,
    get_guideline_ingestion_service,
)

# Phase 4: Multi-Layer Orchestrator
from .multi_layer_orchestrator import (
    TriageMultiLayerOrchestrator,
    LayerConfig,
    LayerResult,
    ConflictRecord,
    get_triage_orchestrator,
)

# Enhanced RAG v2: Structured Clinical Conditions
from .clinical_condition_models import (
    ClinicalGuidelineDocument,
    ClinicalCondition,
    DocumentType,
    TriageMetadata,
    validate_guideline_json,
    get_validation_errors,
)
from .clinical_chunking_service import (
    ClinicalChunkingService,
    ClinicalChunk,
    ChunkType,
    get_clinical_chunking_service,
)
from .clinical_condition_ingestion_service import (
    ClinicalConditionIngestionService,
    IngestionResult as ConditionIngestionResult,
    get_clinical_condition_ingestion_service,
)

__all__ = [
    # Structured Insights
    'StructuredInsights',
    'StructuredInsightsMapper',
    'map_extraction_to_insights',
    'map_extraction_with_patient_history',
    'CONSULTATION_TYPE_TO_SPECIALTY',
    # Differential Trees
    'DIFFERENTIAL_TREES',
    'get_differential',
    'get_all_presentations',
    'match_presentations',
    'get_red_flags',
    'get_first_line_investigations',
    'get_history_essentials',
    # Triage Engine (MVP)
    'TriageSuggestionEngine',
    'TriageSuggestions',
    'TriageSuggestion',
    'DoctorPreferences',
    'fetch_doctor_preferences',
    'generate_triage_suggestions',
    'generate_triage_from_extraction',
    'generate_triage_from_extraction_v2',
    # Phase 1: Doctor Practice Style
    'DoctorPracticeLayer',
    'DoctorPracticeStyle',
    'get_practice_layer',
    # Phase 2: Hospital Intelligence
    'HospitalIntelligenceLayer',
    'HospitalPatterns',
    'PeerComparison',
    'OutlierFlag',
    'HospitalPatternAggregator',
    'get_hospital_intelligence_layer',
    'get_hospital_aggregator',
    # Phase 3: RAG Guidelines
    'RAGGuidelinesLayer',
    'GuidelineMatch',
    'ClinicalConditionMatch',
    'ExtractionContext',
    'get_rag_guidelines_layer',
    'GuidelineIngestionService',
    'GuidelineMetadata',
    'IngestionResult',
    'get_guideline_ingestion_service',
    # Phase 4: Multi-Layer Orchestrator
    'TriageMultiLayerOrchestrator',
    'LayerConfig',
    'LayerResult',
    'ConflictRecord',
    'get_triage_orchestrator',
    # Enhanced RAG v2: Structured Clinical Conditions
    'ClinicalGuidelineDocument',
    'ClinicalCondition',
    'DocumentType',
    'TriageMetadata',
    'validate_guideline_json',
    'get_validation_errors',
    'ClinicalChunkingService',
    'ClinicalChunk',
    'ChunkType',
    'get_clinical_chunking_service',
    'ClinicalConditionIngestionService',
    'ConditionIngestionResult',
    'get_clinical_condition_ingestion_service',
]

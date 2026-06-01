"""
Triage Suggestion Engine

Provides clinical triage suggestions based on extraction data.
Uses Gemini AI + hardcoded differential diagnosis trees (MVP).
Multi-layer architecture with configurable layers (Phases 1-4).

Components:
- structured_insights.py: Dynamic mapper from extraction JSON to triage-ready format
- differential_trees.py: India-specific differential diagnosis trees
- triage_engine.py: Main engine that generates suggestions (MVP)
- counsellor_practice_layer.py: Phase 1 - Counsellor practice style learning
- school_intelligence_layer.py: Phase 2 - School/peer intelligence
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
    map_extraction_with_student_history,
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
    CounsellorPreferences,
    fetch_counsellor_preferences,
    generate_triage_suggestions,
    generate_triage_from_extraction,
    generate_triage_from_extraction_v2,
)

# Phase 1: Counsellor Practice Style Layer
from .counsellor_practice_layer import (
    CounsellorPracticeLayer,
    CounsellorPracticeStyle,
    get_practice_layer,
)

# Phase 2: School Intelligence Layer
from .school_intelligence_layer import (
    SchoolIntelligenceLayer,
    SchoolPatterns,
    PeerComparison,
    OutlierFlag,
    SchoolPatternAggregator,
    get_school_intelligence_layer,
    get_school_aggregator,
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
    'map_extraction_with_student_history',
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
    'CounsellorPreferences',
    'fetch_counsellor_preferences',
    'generate_triage_suggestions',
    'generate_triage_from_extraction',
    'generate_triage_from_extraction_v2',
    # Phase 1: Counsellor Practice Style
    'CounsellorPracticeLayer',
    'CounsellorPracticeStyle',
    'get_practice_layer',
    # Phase 2: School Intelligence
    'SchoolIntelligenceLayer',
    'SchoolPatterns',
    'PeerComparison',
    'OutlierFlag',
    'SchoolPatternAggregator',
    'get_school_intelligence_layer',
    'get_school_aggregator',
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

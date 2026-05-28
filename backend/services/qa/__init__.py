"""
Q&A Engine Services

RAG-based Q&A system for medical extractions with multi-provider embeddings.

Services:
- embedding_service: Multi-provider embedding generation (Cohere, OpenAI, Gemini)
- semantic_search_service: Vector similarity search with permission filters
- query_classifier_service: Classify query intent (semantic, hybrid, SQL)
- analytics_engine_service: Text-to-SQL for analytics queries
- qa_synthesis_service: Generate narrative responses from search results
- suggested_questions_service: Pre-defined question templates
- embedding_job_service: Background embedding jobs
"""

from .embedding_service import EmbeddingService, embedding_service
from .semantic_search_service import SemanticSearchService, semantic_search_service
from .query_classifier_service import QueryClassifierService, query_classifier_service
from .analytics_engine_service import AnalyticsEngineService, analytics_engine_service
from .qa_synthesis_service import QASynthesisService, qa_synthesis_service
from .suggested_questions_service import SuggestedQuestionsService, suggested_questions_service
from .embedding_job_service import EmbeddingJobService, embedding_job_service

__all__ = [
    "EmbeddingService",
    "embedding_service",
    "SemanticSearchService",
    "semantic_search_service",
    "QueryClassifierService",
    "query_classifier_service",
    "AnalyticsEngineService",
    "analytics_engine_service",
    "QASynthesisService",
    "qa_synthesis_service",
    "SuggestedQuestionsService",
    "suggested_questions_service",
    "EmbeddingJobService",
    "embedding_job_service",
]

"""
Q&A Engine Models

Defines Pydantic models for the RAG-based Q&A Engine:
- Query classification (semantic, hybrid, SQL)
- Search request/response models
- Embedding model configurations
- Suggested questions
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal, Union
from uuid import UUID
from datetime import datetime
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class TemporalReferenceType(str, Enum):
    """Types of temporal references in user queries"""
    RELATIVE_VISIT = "relative_visit"     # "last visit", "previous consultation"
    ABSOLUTE_DATE = "absolute_date"       # "January 15th", "2024-01-15"
    RELATIVE_TIME = "relative_time"       # "last week", "3 months ago"
    VISIT_NUMBER = "visit_number"         # "first visit", "visit 3"
    COMPARISON = "comparison"             # "compare with previous"


class QuestionCategory(str, Enum):
    """Categories for suggested questions"""
    CLINICAL = "clinical"           # Clinical insights, patterns
    RISK = "risk"                   # Risk assessment, severity
    REFERRALS = "referrals"         # Referral patterns, allied health
    INTERVENTIONS = "interventions" # Intervention tracking, outcomes
    TRIAGE = "triage"               # Triage patterns, red flags
    ANALYTICS = "analytics"         # Usage stats, trends, counts


class QueryIntent(str, Enum):
    """Classified intent of a user query"""
    SEMANTIC = "semantic"   # Pattern detection, insights -> Narrative synthesis
    HYBRID = "hybrid"       # Search with filters -> Patient table
    SQL = "sql"             # Analytics, counts -> Charts/stats


class SearchLevel(str, Enum):
    """Level of granularity for search"""
    DOCUMENT = "document"   # Full extraction level
    SEGMENT = "segment"     # Individual segment level


class ResponseFormat(str, Enum):
    """Format for Q&A response"""
    NARRATIVE = "narrative"   # Natural language summary
    TABLE = "table"           # Tabular patient/extraction data
    CHART = "chart"           # Chart visualization data
    STAT_CARD = "stat_card"   # Single metric card


class ChartType(str, Enum):
    """Types of charts for analytics responses"""
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    STAT_CARD = "stat_card"


# ============================================================================
# Embedding Model Models
# ============================================================================

class EmbeddingModelResponse(BaseModel):
    """Response model for embedding model info"""
    id: UUID
    model_code: str
    model_name: str
    provider: str
    dimensions: int
    description: Optional[str] = None
    is_default: bool = False
    is_active: bool = True
    price_per_million_tokens: Optional[float] = None
    max_tokens: Optional[int] = None


class EmbeddingModelsListResponse(BaseModel):
    """Response for listing embedding models"""
    models: List[EmbeddingModelResponse]
    count: int


class SetEmbeddingModelRequest(BaseModel):
    """Request to set the active embedding model for a hospital"""
    model_code: str = Field(..., description="The model_code to set as active")


# ============================================================================
# Suggested Questions
# ============================================================================

class SuggestedQuestion(BaseModel):
    """A pre-defined suggested question"""
    id: str
    question: str
    category: QuestionCategory
    description: Optional[str] = None
    # Hints for the query classifier
    expected_intent: Optional[QueryIntent] = None
    expected_segment_codes: Optional[List[str]] = None


class SuggestedQuestionsResponse(BaseModel):
    """Response for suggested questions"""
    questions: List[SuggestedQuestion]
    category: Optional[QuestionCategory] = None
    count: int


# ============================================================================
# Query Reframing
# ============================================================================

class ReframeExpansion(BaseModel):
    """Record of an abbreviation/term expansion"""
    original: str
    expanded: str
    category: str = "abbreviation"  # abbreviation, colloquial, temporal


class ReframeCorrection(BaseModel):
    """Record of a typo/term correction"""
    original: str
    corrected: str
    category: str = "typo"  # typo, misspelling, normalization


class ReframedQuery(BaseModel):
    """Result of reframing a user query before classification"""
    original_query: str
    reframed_query: str
    expansions: List[ReframeExpansion] = []
    corrections: List[ReframeCorrection] = []
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    reframe_time_ms: Optional[int] = None
    # Flag indicating if any changes were made
    was_modified: bool = False


# ============================================================================
# Temporal Reference Models
# ============================================================================

class TemporalReference(BaseModel):
    """A temporal reference extracted from a query"""
    type: TemporalReferenceType
    raw_text: str  # Original text in query, e.g., "last visit"
    resolved_date: Optional[datetime] = None  # Resolved absolute date
    resolved_extraction_id: Optional[UUID] = None  # Resolved extraction ID
    visit_offset: Optional[int] = None  # -1 = last, -2 = second to last, 1 = first


# ============================================================================
# Query Classification
# ============================================================================

class ClassifiedQuery(BaseModel):
    """Result of classifying a user query"""
    original_query: str
    intent: QueryIntent
    search_level: SearchLevel
    response_format: ResponseFormat
    # Search parameters
    segment_codes: Optional[List[str]] = None  # Filter by segment type
    # SQL parameters
    sql_query: Optional[str] = None  # Generated SQL for analytics
    # Filters extracted from query
    filters: Optional[Dict[str, Any]] = None
    # Confidence
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    # Temporal/longitudinal query support
    temporal_references: Optional[List[TemporalReference]] = None
    requires_patient_history: bool = False  # Query needs patient lookup
    comparison_mode: bool = False  # Query compares visits


# ============================================================================
# Q&A Query Request/Response
# ============================================================================

class QAPriorContext(BaseModel):
    """Previous Q&A exchange for follow-up context resolution"""
    query: str                                       # Previous user query
    narrative: Optional[str] = None                  # Previous assistant narrative response
    intent: Optional[str] = None                     # Previous query intent (semantic/hybrid/sql)
    extraction_id: Optional[str] = None              # Extraction ID if previous answer was from a specific visit


class QAQueryRequest(BaseModel):
    """Request model for Q&A queries"""
    query: str = Field(..., min_length=3, max_length=2000, description="Natural language query")
    # Hospital context (required for admin users without hospital in auth context)
    hospital_id: Optional[UUID] = Field(default=None, description="Hospital ID for query scope")
    hospital_code: Optional[str] = Field(default=None, max_length=50, description="Hospital code (alternative to hospital_id)")
    # Optional filters
    doctor_id: Optional[UUID] = None
    patient_id: Optional[str] = Field(default=None, description="Patient external ID (UHID) or internal UUID")
    consultation_type_id: Optional[UUID] = None
    extraction_id: Optional[UUID] = None  # Reference specific extraction/visit
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    # Conversation context for follow-up queries
    prior_context: Optional[QAPriorContext] = None  # Last Q&A exchange for resolving references
    # Pagination
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchResultItem(BaseModel):
    """Individual search result"""
    extraction_id: UUID
    patient_id: Optional[UUID] = None
    patient_name: Optional[str] = None
    patient_external_id: Optional[str] = None  # UHID
    doctor_id: Optional[UUID] = None
    doctor_name: Optional[str] = None
    consultation_type_name: Optional[str] = None
    created_at: datetime
    # Match info
    similarity_score: float
    matched_segment_code: Optional[str] = None
    matched_content_preview: Optional[str] = None  # First 200 chars of matched content
    # Full extraction data (optional, for detailed view)
    extraction_data: Optional[Dict[str, Any]] = None


class ChartData(BaseModel):
    """Data for chart visualization"""
    chart_type: ChartType
    title: str
    labels: List[str]
    values: List[Union[int, float]]
    # Optional secondary data series
    secondary_values: Optional[List[Union[int, float]]] = None
    secondary_label: Optional[str] = None


class StatCardData(BaseModel):
    """Data for stat card visualization"""
    title: str
    value: Union[int, float, str]
    subtitle: Optional[str] = None
    change_percent: Optional[float] = None  # e.g., +5.2% from last month
    trend: Optional[Literal["up", "down", "neutral"]] = None


class QAQueryResponse(BaseModel):
    """Response model for Q&A queries"""
    success: bool
    query: str
    intent: QueryIntent
    response_format: ResponseFormat
    # Reframing info (shows how query was transformed)
    reframed_query: Optional[str] = None
    reframe_expansions: Optional[List[ReframeExpansion]] = None
    reframe_corrections: Optional[List[ReframeCorrection]] = None
    # For narrative responses
    narrative: Optional[str] = None
    # For table responses
    results: Optional[List[SearchResultItem]] = None
    total_count: Optional[int] = None
    # Referenced extraction IDs (for filtering results to show only relevant ones)
    referenced_extraction_ids: Optional[List[str]] = None
    # For chart responses
    chart: Optional[ChartData] = None
    # For stat card responses
    stat_card: Optional[StatCardData] = None
    # Temporal/longitudinal response data
    temporal_references: Optional[List[TemporalReference]] = None
    longitudinal_data: Optional[Dict[str, Any]] = None  # Comparison/change data
    referenced_visits: Optional[List[Dict[str, Any]]] = None  # Visits referenced in response
    # Performance metrics
    reframe_time_ms: Optional[int] = None
    embedding_time_ms: Optional[int] = None
    search_time_ms: Optional[int] = None
    synthesis_time_ms: Optional[int] = None
    temporal_resolution_time_ms: Optional[int] = None
    longitudinal_time_ms: Optional[int] = None
    total_time_ms: Optional[int] = None
    # Error handling
    error_message: Optional[str] = None


# ============================================================================
# Q&A Settings
# ============================================================================

class QAEngineSettings(BaseModel):
    """Q&A Engine settings for a hospital"""
    hospital_id: UUID
    embedding_model_id: UUID
    embedding_model_code: Optional[str] = None
    embedding_model_name: Optional[str] = None
    is_enabled: bool = True
    allow_analytics_queries: bool = True
    allow_cross_doctor_search: bool = False
    max_results_per_query: int = 20
    max_queries_per_day: int = 1000


class UpdateQASettingsRequest(BaseModel):
    """Request to update Q&A settings"""
    embedding_model_id: Optional[UUID] = None
    is_enabled: Optional[bool] = None
    allow_analytics_queries: Optional[bool] = None
    allow_cross_doctor_search: Optional[bool] = None
    max_results_per_query: Optional[int] = None
    max_queries_per_day: Optional[int] = None


# ============================================================================
# Query History
# ============================================================================

class QueryHistoryItem(BaseModel):
    """Query history entry"""
    id: UUID
    query_text: str
    query_intent: Optional[QueryIntent] = None
    result_count: int = 0
    response_format: Optional[ResponseFormat] = None
    total_time_ms: Optional[int] = None
    created_at: datetime
    # Reframing info
    reframed_query: Optional[str] = None
    reframe_expansions: Optional[List[ReframeExpansion]] = None
    reframe_corrections: Optional[List[ReframeCorrection]] = None
    reframe_confidence: Optional[float] = None
    reframe_time_ms: Optional[int] = None


class QueryHistoryResponse(BaseModel):
    """Response for query history"""
    history: List[QueryHistoryItem]
    total_count: int
    page: int
    page_size: int


# ============================================================================
# Export Models
# ============================================================================

class ExportRequest(BaseModel):
    """Request to export Q&A results"""
    query: str
    results: List[SearchResultItem]
    format: Literal["csv", "pdf"] = "csv"


class ExportResponse(BaseModel):
    """Response with export data"""
    success: bool
    format: str
    filename: str
    # For CSV, the raw content
    content: Optional[str] = None
    # For PDF, base64 encoded
    content_base64: Optional[str] = None
    error_message: Optional[str] = None


# ============================================================================
# Re-embedding Job
# ============================================================================

class ReembeddingJobRequest(BaseModel):
    """Request to trigger re-embedding for a hospital"""
    hospital_id: UUID
    model_code: Optional[str] = None  # If provided, use this model instead of default


class ReembeddingJobResponse(BaseModel):
    """Response for re-embedding job"""
    success: bool
    job_id: Optional[str] = None
    message: str
    extraction_count: Optional[int] = None  # Number of extractions to re-embed

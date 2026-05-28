# Medical Q&A Engine - Implementation Plan

> **Status**: Planned (Not yet implemented)
> **Created**: December 2024
> **Updated**: January 2026
> **Priority**: Future Feature

## Overview

Build a **RAG-based Q&A Engine** for doctors to query medical extractions using natural language. Supports three query types:
- **Semantic queries**: "What was the most common historical pattern in patients I saw last month" → narrative synthesis
- **Filtered search**: "Patients with high cholesterol in last month who got multiple blood tests" → patient list
- **Analytics queries**: "How many prescriptions had amoxicillin antibiotic" → charts/counts

## Requirements Summary

| Requirement | Choice |
|-------------|--------|
| Query Types | Semantic, Hybrid (semantic+filter), SQL analytics |
| Scale | 10,000+ extractions (RAG with pgvector) |
| Permissions | Super admin → Hospital admin → Doctor + sharing |
| Output | Narrative synthesis, Tables, Charts + CSV/PDF export |
| LLM | Gemini (existing integration via `gemini_client_factory.py`) |

---

## Existing Infrastructure to Leverage

The codebase already has robust patterns that the Q&A Engine should integrate with:

| Component | Location | Usage for Q&A Engine |
|-----------|----------|----------------------|
| Gemini Factory | `backend/services/gemini_client_factory.py` | Multi-model client creation for embeddings & synthesis |
| LLM Usage Tracking | `backend/services/llm_usage_service.py` | Track embedding/synthesis costs with cache hit ratio |
| Audit Logging | `backend/services/audit_service.py` | Log Q&A queries for compliance |
| TTL Caching | `cachetools.TTLCache` (pattern in `supabase_service.py`) | Cache frequent queries & embeddings |
| Real-time Progress | Supabase Realtime (pattern in `VHRScreen.tsx`) | Show query processing status |
| Processing Modes | `processing_modes` table | Per-hospital model selection |
| Auth System | `backend/dependencies/auth.py` | `ClientContext` with hospital/doctor scoping |
| Triage Engine | `backend/services/triage/triage_engine.py` | Pattern for context-aware suggestion generation |

---

## Embedding Model Evaluation

### Model Comparison

| Model | Dimensions | Context | Cost | Medical Suitability |
|-------|-----------|---------|------|---------------------|
| **OpenAI text-embedding-3-large** | 3072 | 8K | $0.13/1M tokens | Good - highest general accuracy |
| **Gemini text-embedding-004** | 768 | 2K | Low (existing) | Moderate - already integrated |
| **Cohere Embed v4** | 1536 | **128K** | $0.10/1M | **Excellent** - healthcare fine-tuned |
| **Medical (PubMedBERT/MedTE)** | 768 | 512 | Self-host | Best accuracy but requires hosting |

### Research Findings

1. **OpenAI vs Gemini**: OpenAI text-embedding-3-large has 92 higher ELO rating, nDCG@10: 0.811 vs 0.585
2. **General vs Medical**: Domain-specific models can outperform general by 17% on clinical benchmarks
3. **Surprise finding**: Generalist sentence transformers (jina-v2) outperformed S-PubMedBERT by 6% on short clinical text
4. **Cohere v4**: Fine-tuned for healthcare, handles noisy clinical text (typos, abbreviations), 128K context

### Recommendation

**Primary: Cohere Embed v4** because:
- 128K context handles full extraction documents
- Healthcare fine-tuning out of the box
- Handles noisy clinical text
- Multimodal (future: scanned reports)

**Alternative: OpenAI text-embedding-3-large** if staying with well-benchmarked options

**Future optimization**: Two-stage retrieval with medical reranker (Cohere → PubMedBERT rerank)

---

## Architecture

### Query Router + Response Router Pattern

```
User Query: "What was the most common pattern in diabetic patients last month?"
    ↓
┌────────────────────────────────────────────────────────────┐
│                    QUERY ROUTER (Gemini Flash)             │
│  Classifies: SEMANTIC | HYBRID | SQL                       │
│  Extracts filters: date_range, conditions, medications     │
└────────────────────────────────────────────────────────────┘
    ↓
┌────────────────────────────────────────────────────────────┐
│                    PERMISSION LAYER                        │
│  Uses existing ClientContext from dependencies/auth.py     │
│  super_admin | hospital_admin | doctor + shared patients   │
└────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────┬──────────────────┬───────────────────────┐
│    SEMANTIC     │     HYBRID       │        SQL            │
│    (RAG only)   │  (RAG + Filters) │    (Analytics)        │
├─────────────────┼──────────────────┼───────────────────────┤
│ Vector search   │ Vector search    │ Text-to-SQL           │
│ Pattern detect  │ + SQL filters    │ Aggregations          │
│ "Why" questions │ + Post-filter    │ Counts/Trends         │
│ Insights        │ Exact matching   │ Statistics            │
└─────────────────┴──────────────────┴───────────────────────┘
    ↓
┌────────────────────────────────────────────────────────────┐
│                   RESPONSE ROUTER                          │
│  Determines output format based on query type + results    │
└────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────┬──────────────────┬───────────────────────┐
│   NARRATIVE     │     TABLE        │       CHART           │
│   SYNTHESIS     │   + EXPORT       │     + DATA            │
├─────────────────┼──────────────────┼───────────────────────┤
│ "The most       │ Patient list     │ Bar/Line/Pie          │
│ common pattern  │ with details     │ with numbers          │
│ observed is..." │ CSV/PDF export   │ CSV/PDF export        │
└─────────────────┴──────────────────┴───────────────────────┘
```

### Query Types Explained

| Type | Example Query | Retrieval Strategy | Output |
|------|---------------|-------------------|--------|
| **SEMANTIC** | "What patterns do diabetic patients show?" | Vector similarity → LLM synthesis | Narrative |
| **HYBRID** | "Patients with high cholesterol last month who got blood tests" | Vector search + SQL filters + post-filter | Patient table |
| **SQL** | "How many prescriptions had amoxicillin?" | Text-to-SQL → Execute | Chart/Stat |

### Query Router Implementation

```python
class QueryIntent(Enum):
    SEMANTIC = "semantic"   # Pattern, insight, "why" questions
    HYBRID = "hybrid"       # Search with filters
    SQL = "sql"             # Pure analytics

class SearchLevel(Enum):
    DOCUMENT = "document"   # Search full extractions
    SEGMENT = "segment"     # Search specific segment types

# Segment codes in extraction_segments table
SEGMENT_CODES = [
    "history",        # Chief complaints, medical history
    "examination",    # Physical examination, vitals
    "diagnosis",      # Primary/secondary diagnoses, ICD codes
    "investigations", # Lab tests, imaging
    "prescription",   # Medications, follow-up
]

ROUTER_PROMPT = """
Classify this medical query and determine the best search strategy.

## Query Classification

1. SEMANTIC - Pattern detection, insights, "why" questions, historical analysis
   Examples: "What patterns show in diabetic patients?", "Why are anxiety levels high?"

2. HYBRID - Finding specific patients/records with semantic concepts AND explicit filters
   Examples: "Patients with high cholesterol last month who got blood tests"

3. SQL - Pure counts, aggregations, statistics, trends
   Examples: "How many prescriptions had amoxicillin?", "Top 10 diagnoses"

## Search Level (for SEMANTIC and HYBRID)

- DOCUMENT: Search entire consultation records (transcript + all segments)
  Use for: broad pattern queries, "why" questions, multi-aspect queries
  Examples: "What patterns do diabetic patients show?", "Patients with complex histories"

- SEGMENT: Search specific segment types for precision
  Use for: queries targeting specific medical aspects
  Available segments: history, examination, diagnosis, investigations, prescription

  Examples:
  - "patients diagnosed with diabetes" → segment_codes: ["diagnosis"]
  - "prescriptions containing metformin" → segment_codes: ["prescription"]
  - "abnormal lab results" → segment_codes: ["investigations"]
  - "patients with fever on examination" → segment_codes: ["examination"]

## Extract filters:
- date_range: {start, end}
- conditions: ["diabetes", "hypertension"]
- medications: ["metformin", "amoxicillin"]
- tests: ["blood test", "ECG"]
- doctor_id, patient_id if mentioned

Query: {query}

Return JSON:
{
  "intent": "semantic|hybrid|sql",
  "search_level": "document|segment",
  "segment_codes": ["diagnosis", "prescription"],  // if search_level=segment
  "filters": {...},
  "semantic_query": "..."
}
"""
```

### Response Router Implementation

```python
class ResponseFormat(Enum):
    NARRATIVE = "narrative"  # LLM-synthesized text
    TABLE = "table"          # Structured data
    CHART = "chart"          # Visualization

def infer_response_format(intent: QueryIntent, results: dict) -> ResponseFormat:
    if intent == QueryIntent.SEMANTIC:
        return ResponseFormat.NARRATIVE

    if intent == QueryIntent.HYBRID:
        return ResponseFormat.TABLE

    if intent == QueryIntent.SQL:
        if is_single_value(results):
            return ResponseFormat.CHART  # stat card
        if is_time_series(results):
            return ResponseFormat.CHART  # line chart
        if is_categorical(results):
            return ResponseFormat.CHART  # bar/pie
        return ResponseFormat.TABLE
```

---

## Phase 1: Database Schema

### Current Schema Notes (Verified January 2026)

Before implementing, note these actual column names vs what older documentation may reference:

| Table | Actual Column | Notes |
|-------|---------------|-------|
| `medical_extractions` | `original_extraction_json` | AI-generated extraction (raw) |
| `medical_extractions` | `edited_extraction_json` | **User-corrected data - USE THIS for Q&A** |
| `medical_extractions` | `transcript_text` | Transcript lives HERE (not in recording_sessions) |
| `medical_extractions` | **No `hospital_id`** | Must JOIN via `doctors.hospital_id` |
| `extraction_segments` | `segment_value_text` | Individual segment text - **USE FOR GRANULAR SEARCH** |
| `extraction_segments` | `version_type` | 'original' or 'edited' |
| `patients` | `add_info` | NOT `additional_info` |
| `patients` | `doctor_ids` (ARRAY) | Multiple doctors per patient |
| `processing_modes` | Global only | No hospital_id - use `qa_engine_settings` for per-hospital config |
| `recording_sessions` | `transcript_text` | **NULL/unused** - transcript is in medical_extractions |

### Clinical Intelligence Tables (For Analytics Queries)

These tables contain derived clinical insights that are highly valuable for Q&A queries:

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `clinical_severity_assessments` | Severity scoring per extraction | `severity_level` (LOW/MEDIUM/HIGH), `total_score`, `contributing_factors` TEXT[], `was_overridden`, `score_breakdown` JSONB |
| `patient_dropoff_risk` | Retention/churn risk | `dropoff_probability` (0-100), `risk_level` (LOW/MEDIUM/HIGH/CRITICAL), `is_financial_risk`, `is_competitor_risk`, `is_dissatisfaction_risk`, `is_access_risk`, `is_compliance_risk`, `*_reasons` TEXT[] |
| `care_quality_risk` | Care gap detection | `care_quality_score` (0-100), `risk_level`, `is_medication_issue`, `is_missed_red_flag`, `is_incomplete_treatment`, `is_followup_gap`, `*_reasons` TEXT[], `primary_risk_driver` |
| `allied_health_needs` | Referral recommendations | `priority_level` (NONE/LOW/MEDIUM/HIGH), 9 boolean indicators (`is_mental_health`, `is_nutritional_health`, `is_physiotherapy`, `is_homecare`, `is_sleep_therapy`, `is_rehab_cardiac`, `is_rehab_common`, `is_treatment_education`, `is_wellness`), `*_reasons` TEXT[] |
| `other_clinical_needs` | Follow-up needs | `is_followup_diagnostics`, `is_recurring_diagnostics`, `is_rx_refill`, `*_reasons` TEXT[] |
| `consultation_insights` | Raw AI signals (14 groups) | `patient_signals`, `clinical_severity_signals`, `diagnostic_needs`, `medication_signals`, `nutritional_signals`, `physiotherapy_signals`, `homecare_signals`, `sleep_signals`, `rehabilitation_signals`, `wellness_signals`, `mental_health_signals`, `education_signals`, `competitor_signals`, `access_logistics_signals` (all JSONB) |
| `patient_interventions` | Suggested actions | `intervention_category` (REVENUE/RETENTION/QUALITY), `intervention_sub_type`, `action`, `revenue_estimate`, `linked_assessment_type`, `linked_assessment_id` |
| `intervention_outcomes` | Action tracking & ROI | `status` (PENDING/CONTACTED/ACCEPTED/DECLINED/COMPLETED/EXPIRED), `actual_revenue`, `decline_reason`, `first_contact_at`, `completed_at` |
| `triage_suggestion_log` | Triage suggestions | `suggestion_text`, `suggestion_type`, `suggestion_category`, `priority_rank`, `source_layer`, `rationale` |
| `triage_feedback` | Doctor feedback on triage | `feedback_type` (accepted/rejected/modified), `rejection_reason`, `modified_text`, `feedback_at` |

**Important Relationships:**
- All clinical tables link to `medical_extractions` via `extraction_id`
- All have `patient_id` and `doctor_id` for filtering
- `patient_interventions.linked_assessment_type` references which table triggered it
- `intervention_outcomes.intervention_id` → `patient_interventions.id`
- `triage_feedback.suggestion_id` → `triage_suggestion_log.id`

### Data Flow for Q&A Engine

```
recording_sessions                 medical_extractions              extraction_segments
──────────────────                 ───────────────────              ───────────────────
• full_audio_url            ───►   • session_id (FK)                • extraction_id (FK)
• audio_quality_json               • transcript_text ◄── USE THIS   • segment_code
                                   • edited_extraction_json ◄─┐     • segment_value (JSONB)
                                   • original_extraction_json  │     • segment_value_text ◄── USE THIS
                                                              │     • version_type
                                   USE edited if available ───┘
```

### Embedding Strategy: Two Levels

| Level | Table | What Gets Embedded | Use Case |
|-------|-------|-------------------|----------|
| **Document** | `extraction_embeddings` | transcript + all segments combined | Broad semantic queries |
| **Segment** | `segment_embeddings` | Individual segment_value_text | Granular queries (diagnosis, prescription, etc.) |

### Migration: `20260XXX_add_qa_engine_tables.sql`

```sql
-- Enable pgvector extension (prerequisite - NOT currently installed)
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- 1. EMBEDDING MODELS CONFIGURATION TABLE
-- (Same pattern as processing_modes for frontend config)
-- =====================================================
CREATE TABLE embedding_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_code VARCHAR(50) UNIQUE NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    description TEXT,
    provider VARCHAR(50) NOT NULL,  -- 'cohere', 'openai', 'gemini'
    api_model_name VARCHAR(100) NOT NULL,  -- Actual API model identifier
    dimensions INT NOT NULL,
    max_tokens INT,
    cost_per_million NUMERIC(10,4),  -- For display/estimation
    supports_medical BOOLEAN DEFAULT false,
    display_order INT DEFAULT 999 NOT NULL,
    is_active BOOLEAN DEFAULT true,
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT embedding_models_provider_check
        CHECK (provider IN ('cohere', 'openai', 'gemini'))
);

CREATE INDEX idx_embedding_models_active ON embedding_models(is_active);
CREATE INDEX idx_embedding_models_default ON embedding_models(is_default);
CREATE INDEX idx_embedding_models_code ON embedding_models(model_code);

COMMENT ON TABLE embedding_models IS 'Embedding model configurations for Q&A engine - switchable from frontend';
COMMENT ON COLUMN embedding_models.api_model_name IS 'The exact model name used in API calls (e.g., embed-english-v4.0, text-embedding-3-large)';

-- Trigger for updated_at (reuse existing function)
CREATE TRIGGER update_embedding_models_updated_at
    BEFORE UPDATE ON embedding_models
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- 2. VECTOR EMBEDDINGS TABLE (variable dimensions)
-- NOTE: hospital_id is denormalized here since medical_extractions
-- doesn't have it directly (must be derived via doctors table)
-- =====================================================
CREATE TABLE extraction_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    embedding_type VARCHAR(50) NOT NULL DEFAULT 'full_extraction',
    embedding_model_code VARCHAR(50) NOT NULL REFERENCES embedding_models(model_code),

    -- Store as max dimension (3072 for OpenAI), smaller models zero-pad or we use separate columns
    embedding vector(3072),  -- Max dimensions (OpenAI large)

    -- Denormalized for fast filtering (avoid joins during vector search)
    -- IMPORTANT: hospital_id derived from doctors.hospital_id at embedding time
    patient_id UUID NOT NULL,
    doctor_id UUID,
    hospital_id UUID,  -- Denormalized from doctors table
    consultation_type_id UUID NOT NULL,
    extraction_created_at TIMESTAMPTZ NOT NULL,

    source_text TEXT,
    source_hash VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint to prevent duplicate embeddings per model
    UNIQUE(extraction_id, embedding_model_code)
);

-- Vector index (IVFFlat for 10K+ rows)
CREATE INDEX idx_embeddings_vector ON extraction_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_embeddings_hospital ON extraction_embeddings(hospital_id, extraction_created_at DESC);
CREATE INDEX idx_embeddings_doctor ON extraction_embeddings(doctor_id, extraction_created_at DESC);
CREATE INDEX idx_embeddings_extraction ON extraction_embeddings(extraction_id);

-- =====================================================
-- 3. SEGMENT-LEVEL EMBEDDINGS TABLE
-- For granular queries like "patients diagnosed with X"
-- Sources from extraction_segments.segment_value_text
-- =====================================================
CREATE TABLE segment_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES medical_extractions(id) ON DELETE CASCADE,
    segment_id UUID NOT NULL REFERENCES extraction_segments(id) ON DELETE CASCADE,
    segment_code VARCHAR(50) NOT NULL,  -- 'diagnosis', 'prescription', 'history', etc.
    embedding_model_code VARCHAR(50) NOT NULL REFERENCES embedding_models(model_code),

    -- Vector embedding of segment_value_text
    embedding vector(3072),

    -- Denormalized for fast filtering (avoid joins during vector search)
    patient_id UUID NOT NULL,
    doctor_id UUID,
    hospital_id UUID,  -- Derived from doctors table
    consultation_type_id UUID NOT NULL,
    extraction_created_at TIMESTAMPTZ NOT NULL,

    source_text TEXT,  -- From extraction_segments.segment_value_text
    source_hash VARCHAR(64),
    version_type VARCHAR(20),  -- 'original' or 'edited'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint per segment per model
    UNIQUE(segment_id, embedding_model_code)
);

-- Vector index for segment-level semantic search
CREATE INDEX idx_segment_embeddings_vector ON segment_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Indexes for filtered segment searches
CREATE INDEX idx_segment_embeddings_code ON segment_embeddings(segment_code, hospital_id);
CREATE INDEX idx_segment_embeddings_hospital ON segment_embeddings(hospital_id, extraction_created_at DESC);
CREATE INDEX idx_segment_embeddings_doctor ON segment_embeddings(doctor_id, segment_code);
CREATE INDEX idx_segment_embeddings_extraction ON segment_embeddings(extraction_id);

COMMENT ON TABLE segment_embeddings IS 'Segment-level embeddings for granular Q&A queries (e.g., search only diagnoses)';

-- =====================================================
-- 4. QA ENGINE SETTINGS (per-hospital configuration)
-- NOTE: processing_modes is global-only (no hospital_id),
-- so we use a separate settings table for per-hospital config
-- =====================================================

-- =====================================================
-- 5. PATIENT SHARING (for doctor-level Q&A access)
-- =====================================================
CREATE TABLE patient_sharing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    shared_with_doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    shared_by_doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    shared_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    access_level VARCHAR(20) DEFAULT 'read' CHECK (access_level IN ('read', 'read_write')),
    is_active BOOLEAN DEFAULT true,
    UNIQUE(patient_id, shared_with_doctor_id)
);
CREATE INDEX idx_patient_sharing_doctor ON patient_sharing(shared_with_doctor_id, is_active);
CREATE INDEX idx_patient_sharing_patient ON patient_sharing(patient_id);

-- =====================================================
-- 5. QA QUERY HISTORY (for analytics & debugging)
-- =====================================================
CREATE TABLE qa_query_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_text TEXT NOT NULL,
    query_type VARCHAR(50) NOT NULL,  -- 'semantic', 'hybrid', 'sql'
    response_format VARCHAR(50),  -- 'narrative', 'table', 'chart'

    -- User context (from ClientContext)
    client_type VARCHAR(50),  -- 'admin', 'web_app', 'ehr'
    hospital_id UUID REFERENCES hospitals(id),
    doctor_id UUID REFERENCES doctors(id),

    -- Execution details
    generated_sql TEXT,
    embedding_model_code VARCHAR(50),
    synthesis_model VARCHAR(50),
    result_count INT,
    response_time_ms INT,

    -- For debugging
    filters_applied JSONB,
    error_message TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_qa_queries_hospital ON qa_query_history(hospital_id, created_at DESC);
CREATE INDEX idx_qa_queries_doctor ON qa_query_history(doctor_id, created_at DESC);
CREATE INDEX idx_qa_queries_type ON qa_query_history(query_type);

-- =====================================================
-- 6. QA ENGINE SETTINGS (per-hospital configuration)
-- =====================================================
CREATE TABLE qa_engine_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hospital_id UUID REFERENCES hospitals(id) ON DELETE CASCADE,  -- NULL = global default
    embedding_model_code VARCHAR(50) NOT NULL REFERENCES embedding_models(model_code),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(hospital_id)  -- One setting per hospital (NULL for global)
);

CREATE INDEX idx_qa_settings_hospital ON qa_engine_settings(hospital_id);

COMMENT ON TABLE qa_engine_settings IS 'Per-hospital Q&A engine settings, allows switching embedding models';
```

### Seed Data: `seed_embedding_models.sql`

```sql
-- =====================================================
-- EMBEDDING MODELS SEED DATA
-- =====================================================
INSERT INTO embedding_models (
    id, model_code, model_name, description, provider, api_model_name,
    dimensions, max_tokens, cost_per_million, supports_medical,
    display_order, is_active, is_default
) VALUES
  (
    '850e8400-e29b-41d4-a716-446655440001',
    'cohere_v4',
    'Cohere Embed v4',
    'Healthcare fine-tuned, 128K context, handles noisy clinical text (Recommended)',
    'cohere',
    'embed-english-v4.0',
    1536, 128000, 0.10, true,
    1, true, true  -- DEFAULT
  ),
  (
    '850e8400-e29b-41d4-a716-446655440002',
    'openai_large',
    'OpenAI text-embedding-3-large',
    'Highest general accuracy (nDCG 0.811), 8K context',
    'openai',
    'text-embedding-3-large',
    3072, 8191, 0.13, false,
    2, true, false
  ),
  (
    '850e8400-e29b-41d4-a716-446655440003',
    'openai_small',
    'OpenAI text-embedding-3-small',
    'Cost-effective, good accuracy, 8K context',
    'openai',
    'text-embedding-3-small',
    1536, 8191, 0.02, false,
    3, true, false
  ),
  (
    '850e8400-e29b-41d4-a716-446655440004',
    'gemini',
    'Gemini text-embedding-004',
    'Already integrated, cost-effective, 2K context',
    'gemini',
    'text-embedding-004',
    768, 2048, 0.00, false,
    4, true, false
  )
ON CONFLICT (model_code) DO UPDATE SET
    model_name = EXCLUDED.model_name,
    description = EXCLUDED.description,
    cost_per_million = EXCLUDED.cost_per_million,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- Set global default to Cohere v4
INSERT INTO qa_engine_settings (hospital_id, embedding_model_code)
VALUES (NULL, 'cohere_v4')
ON CONFLICT (hospital_id) DO UPDATE SET
    embedding_model_code = EXCLUDED.embedding_model_code,
    updated_at = NOW();
```

---

## Phase 2: Backend Services

### Dependencies to Add

**Add to `backend/requirements.txt`:**
```
# Q&A Engine - Embeddings
cohere>=5.0.0
pgvector>=0.2.0

# Optional: OpenAI embeddings
openai>=1.0.0
```

### New Files to Create

| File | Purpose |
|------|---------|
| `backend/services/qa/embedding_service.py` | Generate embeddings (multi-provider) |
| `backend/services/qa/qa_service.py` | Main Q&A orchestration |
| `backend/services/qa/semantic_search_service.py` | pgvector search |
| `backend/services/qa/analytics_engine_service.py` | Text-to-SQL |
| `backend/services/qa/query_classifier_service.py` | Classify query type |
| `backend/routers/qa.py` | Q&A API endpoints |
| `backend/routers/qa_settings.py` | Embedding model config API |
| `backend/models/qa_models.py` | Pydantic models for Q&A |

### Key Service: Embedding Service (Multi-Provider)

```python
# backend/services/qa/embedding_service.py
import cohere
import openai
from typing import List, Dict, Optional, Tuple
from uuid import UUID
from abc import ABC, abstractmethod
from cachetools import TTLCache
import hashlib
import os

from services.gemini_client_factory import create_gemini_client
from services.llm_usage_service import track_llm_usage
from services.supabase_service import execute_query

# Cache embeddings for repeated queries (1 hour TTL)
_embedding_cache = TTLCache(maxsize=1000, ttl=3600)


class BaseEmbeddingProvider(ABC):
    """Abstract base for embedding providers"""

    @abstractmethod
    async def generate_embeddings(
        self, texts: List[str], input_type: str
    ) -> List[List[float]]:
        pass


class CohereProvider(BaseEmbeddingProvider):
    def __init__(self, model_name: str):
        self.client = cohere.AsyncClient(api_key=os.getenv("COHERE_API_KEY"))
        self.model = model_name

    async def generate_embeddings(
        self, texts: List[str], input_type: str
    ) -> List[List[float]]:
        response = await self.client.embed(
            texts=texts,
            model=self.model,
            input_type="search_document" if input_type == "document" else "search_query",
            embedding_types=["float"]
        )
        return response.embeddings.float


class OpenAIProvider(BaseEmbeddingProvider):
    def __init__(self, model_name: str):
        self.client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model_name

    async def generate_embeddings(
        self, texts: List[str], input_type: str
    ) -> List[List[float]]:
        response = await self.client.embeddings.create(input=texts, model=self.model)
        return [item.embedding for item in response.data]


class GeminiProvider(BaseEmbeddingProvider):
    def __init__(self, model_name: str):
        self.client = create_gemini_client()
        self.model = model_name

    async def generate_embeddings(
        self, texts: List[str], input_type: str
    ) -> List[List[float]]:
        task_type = "RETRIEVAL_DOCUMENT" if input_type == "document" else "RETRIEVAL_QUERY"
        embeddings = []
        for text in texts:
            response = await self.client.aio.models.embed_content(
                model=self.model, content=text, config={"task_type": task_type}
            )
            embeddings.append(response.embedding)
        return embeddings


# Provider factory
PROVIDERS = {
    "cohere": CohereProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


class EmbeddingService:
    """Configurable embedding service - reads model from database"""

    def __init__(self):
        self._provider_cache: Dict[str, BaseEmbeddingProvider] = {}

    async def get_active_model(self, hospital_id: Optional[UUID] = None) -> dict:
        """Get the active embedding model config from database"""
        # First try hospital-specific setting, then fall back to global
        sql = """
            SELECT em.* FROM qa_engine_settings qs
            JOIN embedding_models em ON qs.embedding_model_code = em.model_code
            WHERE (qs.hospital_id = $1 OR qs.hospital_id IS NULL)
            AND qs.is_active = true
            ORDER BY qs.hospital_id NULLS LAST
            LIMIT 1
        """
        result = await execute_query(sql, [hospital_id])
        return result[0] if result else None

    def _get_provider(self, model_config: dict) -> BaseEmbeddingProvider:
        """Get or create provider instance"""
        model_code = model_config["model_code"]
        if model_code not in self._provider_cache:
            provider_class = PROVIDERS[model_config["provider"]]
            self._provider_cache[model_code] = provider_class(model_config["api_model_name"])
        return self._provider_cache[model_code]

    async def generate_embedding(
        self,
        texts: List[str],
        input_type: str = "document",
        hospital_id: Optional[UUID] = None
    ) -> Tuple[List[List[float]], str]:
        """Generate embeddings using configured model"""
        # Check cache first
        cache_key = hashlib.md5(f"{texts}{input_type}{hospital_id}".encode()).hexdigest()
        if cache_key in _embedding_cache:
            return _embedding_cache[cache_key]

        model_config = await self.get_active_model(hospital_id)
        provider = self._get_provider(model_config)
        embeddings = await provider.generate_embeddings(texts, input_type)

        # Track usage (follows existing llm_usage_service pattern)
        await track_llm_usage(
            model=model_config["api_model_name"],
            input_tokens=sum(len(t.split()) for t in texts),  # Approximate
            output_tokens=0,
            operation="embedding",
            hospital_id=hospital_id
        )

        result = (embeddings, model_config["model_code"])
        _embedding_cache[cache_key] = result
        return result

    async def embed_extraction(
        self, extraction_id: UUID, hospital_id: Optional[UUID] = None
    ) -> None:
        """
        Generate and store embeddings for an extraction.
        Creates BOTH document-level and segment-level embeddings.
        """
        extraction = await self._get_extraction_with_segments(extraction_id)

        # 1. Document-level embedding (transcript + all segments)
        doc_source_text = self._build_document_text(extraction)
        doc_embeddings, model_code = await self.generate_embedding(
            [doc_source_text], "document", hospital_id
        )
        await self._store_document_embedding(
            extraction_id, extraction, doc_embeddings[0], doc_source_text, model_code
        )

        # 2. Segment-level embeddings (individual segments from extraction_segments)
        await self._embed_segments(extraction_id, extraction, model_code, hospital_id)

    async def _get_extraction_with_segments(self, extraction_id: UUID) -> dict:
        """Fetch extraction with all segment data from extraction_segments table"""
        from services.supabase_service import supabase

        # Get extraction
        extraction_result = await supabase.table("medical_extractions") \
            .select("*") \
            .eq("id", str(extraction_id)) \
            .single() \
            .execute()
        extraction = extraction_result.data

        # Get segments - prefer 'edited' version_type, fallback to 'original'
        segments_result = await supabase.table("extraction_segments") \
            .select("*") \
            .eq("extraction_id", str(extraction_id)) \
            .order("segment_code") \
            .execute()

        # Group by segment_code, prefer edited version
        segments_by_code = {}
        for seg in segments_result.data:
            code = seg["segment_code"]
            if code not in segments_by_code or seg.get("version_type") == "edited":
                segments_by_code[code] = seg

        extraction["segments"] = list(segments_by_code.values())
        return extraction

    def _build_document_text(self, extraction: dict) -> str:
        """
        Combine transcript + all segments into searchable document text.
        Uses extraction_segments.segment_value_text for each segment.
        """
        parts = []

        # Add transcript
        transcript = extraction.get('transcript_text', '')
        if transcript:
            parts.append(f"Transcript: {transcript}")

        # Add each segment from extraction_segments table
        for segment in extraction.get("segments", []):
            segment_code = segment.get("segment_code", "")
            # Use segment_value_text (flattened text) for embedding
            segment_text = segment.get("segment_value_text") or json.dumps(segment.get("segment_value", {}))
            parts.append(f"{segment_code}: {segment_text}")

        return "\n\n".join(parts)

    async def _embed_segments(
        self,
        extraction_id: UUID,
        extraction: dict,
        model_code: str,
        hospital_id: Optional[UUID]
    ) -> None:
        """Generate and store segment-level embeddings from extraction_segments"""
        from services.supabase_service import supabase

        # Derive hospital_id from doctor
        derived_hospital_id = await self._get_hospital_id(extraction.get("doctor_id"))

        segments = extraction.get("segments", [])
        if not segments:
            return

        # Batch embed all segments
        segment_texts = []
        for seg in segments:
            text = seg.get("segment_value_text") or json.dumps(seg.get("segment_value", {}))
            segment_texts.append(text)

        embeddings, _ = await self.generate_embedding(segment_texts, "document", hospital_id)

        # Store each segment embedding
        for seg, embedding in zip(segments, embeddings):
            source_text = seg.get("segment_value_text") or json.dumps(seg.get("segment_value", {}))
            source_hash = hashlib.sha256(source_text.encode()).hexdigest()

            await supabase.table("segment_embeddings").upsert({
                "extraction_id": str(extraction_id),
                "segment_id": seg["id"],
                "segment_code": seg["segment_code"],
                "embedding_model_code": model_code,
                "embedding": embedding,
                "patient_id": extraction.get("patient_id"),
                "doctor_id": extraction.get("doctor_id"),
                "hospital_id": derived_hospital_id,
                "consultation_type_id": extraction.get("consultation_type_id"),
                "extraction_created_at": extraction.get("created_at"),
                "source_text": source_text,
                "source_hash": source_hash,
                "version_type": seg.get("version_type", "original")
            }, on_conflict="segment_id,embedding_model_code").execute()

    async def _get_hospital_id(self, doctor_id: Optional[UUID]) -> Optional[str]:
        """Derive hospital_id from doctors table"""
        if not doctor_id:
            return None
        from services.supabase_service import supabase
        doctor_result = await supabase.table("doctors") \
            .select("hospital_id") \
            .eq("id", str(doctor_id)) \
            .single() \
            .execute()
        return doctor_result.data.get("hospital_id") if doctor_result.data else None

    async def _store_document_embedding(
        self,
        extraction_id: UUID,
        extraction: dict,
        embedding: List[float],
        source_text: str,
        model_code: str
    ) -> None:
        """Store document-level embedding in extraction_embeddings table"""
        from services.supabase_service import supabase

        hospital_id = await self._get_hospital_id(extraction.get("doctor_id"))
        source_hash = hashlib.sha256(source_text.encode()).hexdigest()

        await supabase.table("extraction_embeddings").upsert({
            "extraction_id": str(extraction_id),
            "embedding_model_code": model_code,
            "embedding": embedding,
            "patient_id": extraction.get("patient_id"),
            "doctor_id": extraction.get("doctor_id"),
            "hospital_id": hospital_id,
            "consultation_type_id": extraction.get("consultation_type_id"),
            "extraction_created_at": extraction.get("created_at"),
            "source_text": source_text,
            "source_hash": source_hash
        }, on_conflict="extraction_id,embedding_model_code").execute()


# Singleton instance
embedding_service = EmbeddingService()
```

**Environment Variables** (add to `backend/.env`):
```
COHERE_API_KEY=your_cohere_key
OPENAI_API_KEY=your_openai_key  # Optional
# GEMINI_API_KEY already exists
```

### API: Embedding Model Configuration

```python
# backend/routers/qa_settings.py
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from uuid import UUID

from dependencies.auth import get_current_client, require_admin
from models.auth_models import ClientContext
from models.qa_models import EmbeddingModelResponse, SetEmbeddingModelRequest
from services.qa.embedding_service import embedding_service
from services.supabase_service import supabase

router = APIRouter(prefix="/api/v1/qa/settings", tags=["Q&A Settings"])


@router.get("/embedding-models", response_model=List[EmbeddingModelResponse])
async def list_embedding_models(
    client: ClientContext = Depends(get_current_client)
) -> List[EmbeddingModelResponse]:
    """List all available embedding models for frontend dropdown"""
    result = await supabase.table("embedding_models") \
        .select("*") \
        .eq("is_active", True) \
        .order("display_order") \
        .execute()
    return result.data


@router.get("/current-model", response_model=EmbeddingModelResponse)
async def get_current_model(
    hospital_id: Optional[UUID] = None,
    client: ClientContext = Depends(get_current_client)
) -> EmbeddingModelResponse:
    """Get currently active embedding model for hospital"""
    effective_hospital_id = hospital_id or client.hospital_id
    model = await embedding_service.get_active_model(effective_hospital_id)
    if not model:
        raise HTTPException(404, "No embedding model configured")
    return model


@router.post("/embedding-model")
async def set_embedding_model(
    request: SetEmbeddingModelRequest,
    client: ClientContext = Depends(require_admin)
) -> dict:
    """
    Change embedding model for hospital.
    NOTE: This will trigger re-embedding of all extractions!
    """
    # Validate model exists
    model_result = await supabase.table("embedding_models") \
        .select("*") \
        .eq("model_code", request.model_code) \
        .single() \
        .execute()

    if not model_result.data:
        raise HTTPException(404, "Model not found")

    # Update or insert setting
    await supabase.table("qa_engine_settings").upsert({
        "hospital_id": str(request.hospital_id) if request.hospital_id else None,
        "embedding_model_code": request.model_code
    }, on_conflict="hospital_id").execute()

    # Queue re-embedding job if requested
    if request.reembed_existing:
        from services.qa.embedding_job_service import queue_reembedding_job
        await queue_reembedding_job(request.hospital_id, request.model_code)

    return {"success": True, "message": f"Switched to {model_result.data['model_name']}"}


@router.post("/reembed")
async def trigger_reembedding(
    hospital_id: Optional[UUID] = None,
    client: ClientContext = Depends(require_admin)
) -> dict:
    """Manually trigger re-embedding of all extractions"""
    from services.qa.embedding_job_service import queue_reembedding_job
    await queue_reembedding_job(hospital_id)
    return {"success": True, "message": "Re-embedding job queued"}
```

### Important: Re-embedding on Model Switch

When switching embedding models, existing embeddings become incompatible. Options:

1. **Lazy re-embedding**: Re-embed on first search (slow first query)
2. **Background job**: Queue full re-embedding (recommended)
3. **Dual storage**: Keep embeddings from both models temporarily

```python
# backend/services/qa/embedding_job_service.py
from typing import Optional
from uuid import UUID
import logging

from services.supabase_service import supabase
from services.qa.embedding_service import embedding_service

logger = logging.getLogger(__name__)


async def queue_reembedding_job(
    hospital_id: Optional[UUID],
    model_code: Optional[str] = None
) -> None:
    """Queue background job to re-embed all extractions"""
    # Get all extractions for hospital
    query = supabase.table("medical_extractions").select("id, hospital_id")
    if hospital_id:
        query = query.eq("hospital_id", str(hospital_id))

    result = await query.execute()
    extractions = result.data

    # Process in batches
    batch_size = 50
    for i in range(0, len(extractions), batch_size):
        batch = extractions[i:i + batch_size]
        for extraction in batch:
            try:
                await embedding_service.embed_extraction(
                    extraction["id"],
                    extraction.get("hospital_id")
                )
            except Exception as e:
                logger.error(f"Failed to embed extraction {extraction['id']}: {e}")

    logger.info(f"Re-embedded {len(extractions)} extractions")


async def reembed_single_extraction(extraction_id: UUID) -> None:
    """Called after extraction is saved (hook into extraction save flow)"""
    from services.supabase_service import get_extraction_by_id
    extraction = await get_extraction_by_id(extraction_id)
    await embedding_service.embed_extraction(
        extraction_id,
        extraction.get("hospital_id")
    )
```

### Key Service: Semantic Search

```python
# backend/services/qa/semantic_search_service.py
from typing import List, Optional
from uuid import UUID
from enum import Enum

from services.qa.embedding_service import embedding_service
from services.supabase_service import execute_query


class SearchLevel(Enum):
    DOCUMENT = "document"  # Search full extractions (transcript + all segments)
    SEGMENT = "segment"    # Search specific segment types


class SemanticSearchService:
    async def search(
        self,
        query: str,
        hospital_id: Optional[UUID],
        doctor_id: Optional[UUID] = None,
        shared_patient_ids: Optional[List[UUID]] = None,
        limit: int = 20,
        threshold: float = 0.7,
        search_level: SearchLevel = SearchLevel.DOCUMENT,
        segment_codes: Optional[List[str]] = None  # e.g., ['diagnosis', 'prescription']
    ) -> List[dict]:
        """
        Semantic search over extraction embeddings with permission filtering.

        Args:
            search_level: DOCUMENT for broad queries, SEGMENT for granular queries
            segment_codes: When search_level=SEGMENT, filter to specific segment types
        """
        # Generate query embedding
        embeddings, model_code = await embedding_service.generate_embedding(
            [query], "query", hospital_id
        )
        query_embedding = embeddings[0]

        if search_level == SearchLevel.SEGMENT:
            return await self._search_segments(
                query_embedding, model_code, hospital_id, doctor_id,
                shared_patient_ids, limit, threshold, segment_codes
            )
        else:
            return await self._search_documents(
                query_embedding, model_code, hospital_id, doctor_id,
                shared_patient_ids, limit, threshold
            )

    async def _search_documents(
        self,
        query_embedding: List[float],
        model_code: str,
        hospital_id: Optional[UUID],
        doctor_id: Optional[UUID],
        shared_patient_ids: Optional[List[UUID]],
        limit: int,
        threshold: float
    ) -> List[dict]:
        """Search document-level embeddings (full extractions)"""
        sql = """
            SELECT
                ee.extraction_id,
                1 - (ee.embedding <=> $1::vector) AS similarity,
                me.patient_id,
                me.transcript_text,
                p.full_name as patient_name,
                me.created_at as extraction_date,
                'document' as match_level
            FROM extraction_embeddings ee
            JOIN medical_extractions me ON ee.extraction_id = me.id
            JOIN patients p ON me.patient_id = p.id
            WHERE ee.embedding_model_code = $2
              AND (1 - (ee.embedding <=> $1::vector)) >= $3
        """
        params = [query_embedding, model_code, threshold]
        param_idx = 4

        sql, params, param_idx = self._add_permission_filters(
            sql, params, param_idx, hospital_id, doctor_id, shared_patient_ids, "ee"
        )

        sql += f" ORDER BY ee.embedding <=> $1::vector LIMIT ${param_idx}"
        params.append(limit)

        return await execute_query(sql, params)

    async def _search_segments(
        self,
        query_embedding: List[float],
        model_code: str,
        hospital_id: Optional[UUID],
        doctor_id: Optional[UUID],
        shared_patient_ids: Optional[List[UUID]],
        limit: int,
        threshold: float,
        segment_codes: Optional[List[str]] = None
    ) -> List[dict]:
        """
        Search segment-level embeddings for granular queries.
        E.g., "patients diagnosed with diabetes" → search only 'diagnosis' segments
        """
        sql = """
            SELECT
                se.extraction_id,
                se.segment_id,
                se.segment_code,
                1 - (se.embedding <=> $1::vector) AS similarity,
                se.source_text as segment_text,
                me.patient_id,
                me.transcript_text,
                p.full_name as patient_name,
                me.created_at as extraction_date,
                'segment' as match_level,
                se.version_type
            FROM segment_embeddings se
            JOIN medical_extractions me ON se.extraction_id = me.id
            JOIN patients p ON me.patient_id = p.id
            WHERE se.embedding_model_code = $2
              AND (1 - (se.embedding <=> $1::vector)) >= $3
        """
        params = [query_embedding, model_code, threshold]
        param_idx = 4

        # Filter by segment codes if specified
        if segment_codes:
            sql += f" AND se.segment_code = ANY(${param_idx})"
            params.append(segment_codes)
            param_idx += 1

        sql, params, param_idx = self._add_permission_filters(
            sql, params, param_idx, hospital_id, doctor_id, shared_patient_ids, "se"
        )

        sql += f" ORDER BY se.embedding <=> $1::vector LIMIT ${param_idx}"
        params.append(limit)

        return await execute_query(sql, params)

    def _add_permission_filters(
        self, sql: str, params: list, param_idx: int,
        hospital_id, doctor_id, shared_patient_ids, table_alias: str
    ) -> tuple:
        """Add permission filters to SQL query"""
        if hospital_id:
            sql += f" AND {table_alias}.hospital_id = ${param_idx}"
            params.append(str(hospital_id))
            param_idx += 1

        if doctor_id:
            if shared_patient_ids:
                sql += f" AND ({table_alias}.doctor_id = ${param_idx} OR {table_alias}.patient_id = ANY(${param_idx + 1}))"
                params.extend([str(doctor_id), [str(p) for p in shared_patient_ids]])
                param_idx += 2
            else:
                sql += f" AND {table_alias}.doctor_id = ${param_idx}"
                params.append(str(doctor_id))
                param_idx += 1

        return sql, params, param_idx


semantic_search_service = SemanticSearchService()
```

### Key Service: Analytics Engine

```python
# backend/services/qa/analytics_engine_service.py
from typing import Optional
from uuid import UUID

from services.gemini_client_factory import create_gemini_client
from services.supabase_service import execute_query


TEXT_TO_SQL_PROMPT = """
You are a SQL expert. Convert this natural language query to PostgreSQL.

## Available Tables

### Core Tables
- medical_extractions (id, patient_id, doctor_id, consultation_type_id, transcript_text, created_at)
  NOTE: No hospital_id column - must JOIN via doctors.hospital_id
- patients (id, full_name, date_of_birth, gender, add_info JSONB, doctor_ids UUID[])
- doctors (id, full_name, specialization, hospital_id)
- hospitals (id, name)
- consultation_types (id, type_code, type_name)

### Segment Table (USE THIS FOR GRANULAR QUERIES)
- extraction_segments (id, extraction_id, segment_code, segment_value JSONB, segment_value_text TEXT, version_type)
  - segment_code values: 'history', 'examination', 'diagnosis', 'investigations', 'prescription'
  - segment_value_text: Flattened text for searching (USE THIS for text search)
  - version_type: 'original' or 'edited' (prefer 'edited' if available)

### Clinical Intelligence Tables (USE THESE FOR RISK/OUTCOME QUERIES)

**Severity & Risk Assessments:**
- clinical_severity_assessments (id, extraction_id, patient_id, doctor_id, severity_level TEXT, total_score INT, contributing_factors TEXT[], was_overridden BOOLEAN, score_breakdown JSONB, created_at)
  - severity_level: 'LOW', 'MEDIUM', 'HIGH'
  - contributing_factors: Array of human-readable factors like ["ICD: I25.1 (Ischemic heart disease)", "Specialty: cardiology"]

- patient_dropoff_risk (id, extraction_id, patient_id, doctor_id, dropoff_probability DECIMAL, risk_level TEXT, is_financial_risk BOOLEAN, is_competitor_risk BOOLEAN, is_dissatisfaction_risk BOOLEAN, is_access_risk BOOLEAN, is_compliance_risk BOOLEAN, financial_risk_reasons TEXT[], competitor_risk_reasons TEXT[], dissatisfaction_risk_reasons TEXT[], access_risk_reasons TEXT[], compliance_risk_reasons TEXT[], anxiety_trajectory TEXT, compliance_likelihood TEXT, primary_risk_driver TEXT, created_at)
  - risk_level: 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
  - anxiety_trajectory: 'Improved', 'Stable', 'Worsened', 'Unable to determine'

- care_quality_risk (id, extraction_id, patient_id, doctor_id, care_quality_score DECIMAL, risk_level TEXT, is_medication_issue BOOLEAN, is_missed_red_flag BOOLEAN, is_incomplete_treatment BOOLEAN, is_followup_gap BOOLEAN, medication_issue_reasons TEXT[], missed_red_flag_reasons TEXT[], incomplete_treatment_reasons TEXT[], followup_gap_reasons TEXT[], reasons TEXT[], primary_risk_driver TEXT, created_at)
  - risk_level: 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'

**Clinical Needs:**
- allied_health_needs (id, extraction_id, patient_id, doctor_id, priority_level TEXT, is_mental_health BOOLEAN, is_nutritional_health BOOLEAN, is_physiotherapy BOOLEAN, is_homecare BOOLEAN, is_sleep_therapy BOOLEAN, is_rehab_cardiac BOOLEAN, is_rehab_common BOOLEAN, is_treatment_education BOOLEAN, is_wellness BOOLEAN, mental_health_reasons TEXT[], nutritional_health_reasons TEXT[], physiotherapy_reasons TEXT[], homecare_reasons TEXT[], sleep_therapy_reasons TEXT[], rehab_cardiac_reasons TEXT[], rehab_common_reasons TEXT[], treatment_education_reasons TEXT[], wellness_reasons TEXT[], created_at)
  - priority_level: 'NONE', 'LOW', 'MEDIUM', 'HIGH'

- other_clinical_needs (id, extraction_id, patient_id, doctor_id, is_followup_diagnostics BOOLEAN, is_recurring_diagnostics BOOLEAN, is_rx_refill BOOLEAN, followup_diagnostics_reasons TEXT[], recurring_diagnostics_reasons TEXT[], rx_refill_reasons TEXT[], created_at)

**Raw AI Signals:**
- consultation_insights (id, extraction_id, patient_id, doctor_id, patient_signals JSONB, clinical_severity_signals JSONB, diagnostic_needs JSONB, medication_signals JSONB, nutritional_signals JSONB, physiotherapy_signals JSONB, homecare_signals JSONB, sleep_signals JSONB, rehabilitation_signals JSONB, wellness_signals JSONB, mental_health_signals JSONB, education_signals JSONB, competitor_signals JSONB, access_logistics_signals JSONB, created_at)

**Interventions & Outcomes:**
- patient_interventions (id, extraction_id, patient_id, doctor_id, intervention_category VARCHAR, intervention_sub_type VARCHAR, action TEXT, revenue_estimate DECIMAL, linked_assessment_type VARCHAR, linked_assessment_id UUID, created_at)
  - intervention_category: 'REVENUE', 'RETENTION', 'QUALITY'
  - intervention_sub_type: 'allied_health', 'clinical_upsell', 'diagnostics_rx', 'medication_safety', 'documentation', 'followup', 'retention'
  - linked_assessment_type: 'allied_health_needs', 'clinical_severity', 'other_clinical_needs', 'patient_dropoff_risk', 'care_quality_risk'

- intervention_outcomes (id, intervention_id UUID, status VARCHAR, generated_at TIMESTAMPTZ, first_contact_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, actual_revenue DECIMAL, decline_reason VARCHAR, notes TEXT, created_at)
  - status: 'PENDING', 'CONTACTED', 'ACCEPTED', 'DECLINED', 'COMPLETED', 'EXPIRED'

**Triage & Feedback:**
- triage_suggestion_log (id, extraction_id, doctor_id, suggestion_text TEXT, suggestion_type TEXT, suggestion_category TEXT, priority_rank INT, source_layer TEXT, rationale TEXT, created_at)

- triage_feedback (id, suggestion_id UUID, doctor_id UUID, feedback_type TEXT, rejection_reason TEXT, modified_text TEXT, feedback_at TIMESTAMPTZ)
  - feedback_type: 'accepted', 'rejected', 'modified'

## Query Patterns

For diagnosis queries:
```sql
SELECT p.full_name, es.segment_value_text
FROM extraction_segments es
JOIN medical_extractions me ON es.extraction_id = me.id
JOIN patients p ON me.patient_id = p.id
WHERE es.segment_code = 'diagnosis'
AND es.segment_value_text ILIKE '%diabetes%'
```

For prescription queries:
```sql
SELECT COUNT(*) FROM extraction_segments
WHERE segment_code = 'prescription'
AND segment_value_text ILIKE '%amoxicillin%'
```

For high-risk patients (severity):
```sql
SELECT p.full_name, csa.severity_level, csa.contributing_factors
FROM clinical_severity_assessments csa
JOIN patients p ON csa.patient_id = p.id
WHERE csa.severity_level = 'HIGH'
ORDER BY csa.created_at DESC
```

For dropoff risk with specific indicators:
```sql
SELECT p.full_name, pdr.dropoff_probability, pdr.risk_level, pdr.primary_risk_driver
FROM patient_dropoff_risk pdr
JOIN patients p ON pdr.patient_id = p.id
WHERE pdr.is_financial_risk = TRUE
AND pdr.risk_level IN ('HIGH', 'CRITICAL')
```

For care quality issues:
```sql
SELECT p.full_name, cqr.care_quality_score, cqr.reasons
FROM care_quality_risk cqr
JOIN patients p ON cqr.patient_id = p.id
WHERE cqr.is_missed_red_flag = TRUE
ORDER BY cqr.care_quality_score DESC
```

For allied health referrals needed:
```sql
SELECT p.full_name, ahn.priority_level, ahn.mental_health_reasons, ahn.physiotherapy_reasons
FROM allied_health_needs ahn
JOIN patients p ON ahn.patient_id = p.id
WHERE ahn.is_mental_health = TRUE OR ahn.is_physiotherapy = TRUE
AND ahn.priority_level IN ('MEDIUM', 'HIGH')
```

For intervention conversion rates:
```sql
SELECT pi.intervention_category, io.status, COUNT(*) as count
FROM patient_interventions pi
JOIN intervention_outcomes io ON pi.id = io.intervention_id
GROUP BY pi.intervention_category, io.status
ORDER BY pi.intervention_category, count DESC
```

For triage suggestion acceptance rates:
```sql
SELECT tsl.suggestion_type, tf.feedback_type, COUNT(*) as count
FROM triage_suggestion_log tsl
JOIN triage_feedback tf ON tsl.id = tf.suggestion_id
GROUP BY tsl.suggestion_type, tf.feedback_type
```

To filter by hospital, always JOIN:
medical_extractions me JOIN doctors d ON me.doctor_id = d.id WHERE d.hospital_id = ...

User query: {query}

Hospital filter: {hospital_id}
Doctor filter: {doctor_id}

Return ONLY the SQL query, no explanation. Use parameterized queries where needed.
Only SELECT queries are allowed.
"""


class AnalyticsEngineService:
    def __init__(self):
        self.client = create_gemini_client()

    async def analyze(
        self,
        query: str,
        hospital_id: Optional[UUID],
        doctor_id: Optional[UUID] = None
    ) -> dict:
        """Generate and execute analytics SQL"""
        # Generate SQL using Gemini
        prompt = TEXT_TO_SQL_PROMPT.format(
            query=query,
            hospital_id=hospital_id or "NULL (super_admin - all hospitals)",
            doctor_id=doctor_id or "NULL (all doctors)"
        )

        response = await self.client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        generated_sql = response.text.strip()

        # Clean up SQL (remove markdown code blocks if present)
        if generated_sql.startswith("```"):
            generated_sql = generated_sql.split("```")[1]
            if generated_sql.startswith("sql"):
                generated_sql = generated_sql[3:]
            generated_sql = generated_sql.strip()

        # Validate SQL (security)
        validated_sql = self._validate_sql(generated_sql)

        # Execute with permission filters injected
        results = await execute_query(validated_sql, [])

        # Infer chart type
        chart_type = self._infer_chart_type(results)

        return {
            "type": "analytics",
            "data": results,
            "chart_type": chart_type,
            "sql": validated_sql,
            "row_count": len(results)
        }

    def _validate_sql(self, sql: str) -> str:
        """Block dangerous operations"""
        forbidden = ["DELETE", "UPDATE", "DROP", "INSERT", "ALTER", "TRUNCATE", "CREATE", "GRANT"]
        sql_upper = sql.upper()

        for keyword in forbidden:
            if keyword in sql_upper:
                raise ValueError(f"Forbidden SQL keyword: {keyword}")

        if not sql_upper.strip().startswith("SELECT"):
            raise ValueError("Only SELECT queries allowed")

        # Block common SQL injection patterns
        if ";" in sql and sql_upper.count("SELECT") > 1:
            raise ValueError("Multiple statements not allowed")

        return sql

    def _infer_chart_type(self, results: list) -> str:
        """Determine appropriate chart type based on results"""
        if not results:
            return "empty"

        if len(results) == 1 and len(results[0]) == 1:
            return "stat_card"  # Single value

        # Check for time-based data
        first_row = results[0]
        keys = list(first_row.keys()) if isinstance(first_row, dict) else []

        time_columns = ["date", "month", "year", "week", "created_at", "period"]
        if any(col in keys for col in time_columns):
            return "line"

        # Check for categorical data
        if len(results) <= 10 and len(keys) == 2:
            return "bar"

        if len(results) <= 5:
            return "pie"

        return "table"


analytics_engine_service = AnalyticsEngineService()
```

### API Router

```python
# backend/routers/qa.py
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from uuid import UUID

from dependencies.auth import get_current_client
from models.auth_models import ClientContext
from models.qa_models import QAQueryRequest, QAResponse
from services.qa.query_classifier_service import query_classifier
from services.qa.semantic_search_service import semantic_search_service
from services.qa.analytics_engine_service import analytics_engine_service
from services.qa.qa_synthesis_service import qa_synthesis_service
from services.supabase_service import supabase
from services.audit_service import log_audit_event

router = APIRouter(prefix="/api/v1/qa", tags=["Q&A"])


def build_permission_filters(client: ClientContext) -> dict:
    """Build permission filters from ClientContext (existing pattern)"""
    filters = {
        "hospital_id": client.hospital_id,
        "doctor_id": None,
        "shared_patient_ids": None
    }

    # Super admin has no restrictions
    if client.user_role == "super_admin":
        filters["hospital_id"] = None
        return filters

    # Doctor-level access
    if client.allowed_doctor_ids:
        filters["doctor_id"] = client.allowed_doctor_ids[0]  # Primary doctor
        # Get shared patient IDs
        filters["shared_patient_ids"] = await get_shared_patient_ids(filters["doctor_id"])

    return filters


async def get_shared_patient_ids(doctor_id: UUID) -> list:
    """Get patient IDs shared with this doctor"""
    result = await supabase.table("patient_sharing") \
        .select("patient_id") \
        .eq("shared_with_doctor_id", str(doctor_id)) \
        .eq("is_active", True) \
        .execute()
    return [r["patient_id"] for r in result.data]


@router.post("/query", response_model=QAResponse)
async def qa_query(
    request: QAQueryRequest,
    client: ClientContext = Depends(get_current_client)
) -> QAResponse:
    """Natural language Q&A over medical data"""
    import time
    start_time = time.time()

    # Build permission filters from ClientContext
    filters = await build_permission_filters(client)

    # Classify query type
    classification = await query_classifier.classify(request.query)

    try:
        if classification.intent == "semantic":
            # Vector search + LLM synthesis
            search_results = await semantic_search_service.search(
                query=request.query,
                hospital_id=filters["hospital_id"],
                doctor_id=filters["doctor_id"],
                shared_patient_ids=filters["shared_patient_ids"],
                limit=request.limit or 20
            )

            # Synthesize narrative response
            narrative = await qa_synthesis_service.synthesize(
                query=request.query,
                results=search_results,
                hospital_id=filters["hospital_id"]
            )

            response = QAResponse(
                query_type="semantic",
                response_format="narrative",
                narrative=narrative,
                source_count=len(search_results),
                sources=search_results[:5]  # Top 5 sources for citation
            )

        elif classification.intent == "hybrid":
            # Vector search with additional SQL filters
            search_results = await semantic_search_service.search(
                query=classification.semantic_query,
                hospital_id=filters["hospital_id"],
                doctor_id=filters["doctor_id"],
                shared_patient_ids=filters["shared_patient_ids"],
                limit=request.limit or 50
            )

            # Apply extracted filters (date range, conditions, etc.)
            filtered_results = apply_extracted_filters(
                search_results, classification.filters
            )

            response = QAResponse(
                query_type="hybrid",
                response_format="table",
                table_data=filtered_results,
                total_count=len(filtered_results)
            )

        elif classification.intent == "sql":
            # Text-to-SQL analytics
            analytics_result = await analytics_engine_service.analyze(
                query=request.query,
                hospital_id=filters["hospital_id"],
                doctor_id=filters["doctor_id"]
            )

            response = QAResponse(
                query_type="sql",
                response_format="chart" if analytics_result["chart_type"] != "table" else "table",
                chart_type=analytics_result["chart_type"],
                chart_data=analytics_result["data"],
                generated_sql=analytics_result["sql"],
                total_count=analytics_result["row_count"]
            )

        else:
            raise HTTPException(400, f"Unknown query intent: {classification.intent}")

        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)

        # Log query for analytics (async, non-blocking)
        await log_qa_query(
            query=request.query,
            classification=classification,
            response=response,
            client=client,
            response_time_ms=response_time_ms
        )

        return response

    except Exception as e:
        # Log error
        await log_audit_event(
            event_type="qa_query_error",
            details={"query": request.query, "error": str(e)},
            hospital_id=filters["hospital_id"]
        )
        raise HTTPException(500, f"Query failed: {str(e)}")


async def log_qa_query(
    query: str,
    classification,
    response: QAResponse,
    client: ClientContext,
    response_time_ms: int
) -> None:
    """Log query to qa_query_history for analytics"""
    await supabase.table("qa_query_history").insert({
        "query_text": query,
        "query_type": classification.intent,
        "response_format": response.response_format,
        "client_type": client.client_type,
        "hospital_id": str(client.hospital_id) if client.hospital_id else None,
        "doctor_id": str(client.allowed_doctor_ids[0]) if client.allowed_doctor_ids else None,
        "generated_sql": response.generated_sql,
        "result_count": response.total_count,
        "response_time_ms": response_time_ms,
        "filters_applied": classification.filters
    }).execute()


@router.post("/export")
async def export_results(
    request: dict,  # ExportRequest
    client: ClientContext = Depends(get_current_client)
):
    """Export results to CSV or PDF"""
    # Implementation: Use existing patterns from extraction export
    pass


@router.get("/history")
async def get_query_history(
    limit: int = 20,
    client: ClientContext = Depends(get_current_client)
):
    """Get user's query history"""
    query = supabase.table("qa_query_history").select("*")

    if client.hospital_id:
        query = query.eq("hospital_id", str(client.hospital_id))

    result = await query.order("created_at", desc=True).limit(limit).execute()
    return result.data


@router.get("/suggested-questions", response_model=List[SuggestedQuestion])
async def get_suggested_questions(
    category: Optional[str] = None,
    client: ClientContext = Depends(get_current_client)
) -> List[SuggestedQuestion]:
    """
    Get pre-defined suggested questions organized by category.
    Users can pick from these or enter custom questions.

    Categories:
    - clinical: Diagnosis, prescriptions, medical patterns
    - risk: Severity, dropoff risk, care quality
    - referrals: Allied health needs, clinical needs
    - interventions: Intervention status, outcomes, ROI
    - triage: Suggestions, feedback, acceptance rates
    - analytics: Trends, counts, distributions
    """
    from services.qa.suggested_questions_service import get_suggested_questions_list
    return await get_suggested_questions_list(category, client.hospital_id, client.user_role)
```

### Suggested Questions Service

```python
# backend/services/qa/suggested_questions_service.py
from typing import List, Optional
from uuid import UUID

from models.qa_models import SuggestedQuestion, QuestionCategory


# Pre-defined suggested questions organized by category
SUGGESTED_QUESTIONS = {
    QuestionCategory.CLINICAL: [
        # Semantic/Pattern queries
        SuggestedQuestion(
            question="What patterns do my diabetic patients show?",
            category="clinical",
            query_type="semantic",
            description="Analyzes common patterns in diabetic patient consultations"
        ),
        SuggestedQuestion(
            question="What are the most common diagnosis combinations?",
            category="clinical",
            query_type="semantic",
            description="Finds frequently co-occurring diagnoses"
        ),
        # SQL/Analytics queries
        SuggestedQuestion(
            question="Top 10 most prescribed medicines this month",
            category="clinical",
            query_type="sql",
            description="Ranks medications by prescription frequency"
        ),
        SuggestedQuestion(
            question="How many prescriptions contained antibiotics this week?",
            category="clinical",
            query_type="sql",
            description="Counts antibiotic prescriptions"
        ),
        SuggestedQuestion(
            question="Distribution of diagnoses by consultation type",
            category="clinical",
            query_type="sql",
            description="Shows diagnosis breakdown per consultation type"
        ),
        # Hybrid queries
        SuggestedQuestion(
            question="Patients diagnosed with hypertension in the last month",
            category="clinical",
            query_type="hybrid",
            description="Lists patients with hypertension diagnosis"
        ),
    ],

    QuestionCategory.RISK: [
        SuggestedQuestion(
            question="Show all HIGH severity patients this week",
            category="risk",
            query_type="sql",
            description="Lists patients with high clinical severity"
        ),
        SuggestedQuestion(
            question="Patients with CRITICAL dropoff risk",
            category="risk",
            query_type="sql",
            description="Identifies patients at highest risk of not returning"
        ),
        SuggestedQuestion(
            question="Which patients have financial concerns affecting retention?",
            category="risk",
            query_type="sql",
            description="Patients flagged with financial risk indicators"
        ),
        SuggestedQuestion(
            question="Care quality issues - missed red flags this month",
            category="risk",
            query_type="sql",
            description="Cases where potential red flags were not addressed"
        ),
        SuggestedQuestion(
            question="Trend of HIGH severity cases over the last 3 months",
            category="risk",
            query_type="sql",
            description="Shows severity trends over time"
        ),
        SuggestedQuestion(
            question="Why do high-risk patients have compliance concerns?",
            category="risk",
            query_type="semantic",
            description="Analyzes patterns in non-compliant high-risk patients"
        ),
    ],

    QuestionCategory.REFERRALS: [
        SuggestedQuestion(
            question="How many patients need mental health referral?",
            category="referrals",
            query_type="sql",
            description="Count of patients flagged for mental health support"
        ),
        SuggestedQuestion(
            question="List all physiotherapy referrals this week",
            category="referrals",
            query_type="sql",
            description="Patients needing physiotherapy"
        ),
        SuggestedQuestion(
            question="Patients needing cardiac rehabilitation",
            category="referrals",
            query_type="sql",
            description="Post-cardiac event patients for rehab"
        ),
        SuggestedQuestion(
            question="Allied health needs breakdown by service type",
            category="referrals",
            query_type="sql",
            description="Distribution of referral types"
        ),
        SuggestedQuestion(
            question="Patients with recurring diagnostic test needs",
            category="referrals",
            query_type="sql",
            description="Chronic patients needing periodic tests"
        ),
        SuggestedQuestion(
            question="Prescription refills due next month",
            category="referrals",
            query_type="sql",
            description="Patients likely needing refills"
        ),
    ],

    QuestionCategory.INTERVENTIONS: [
        SuggestedQuestion(
            question="Intervention conversion rate by category",
            category="interventions",
            query_type="sql",
            description="Acceptance rates for REVENUE/RETENTION/QUALITY interventions"
        ),
        SuggestedQuestion(
            question="Revenue from COMPLETED interventions this month",
            category="interventions",
            query_type="sql",
            description="Total actual revenue from completed interventions"
        ),
        SuggestedQuestion(
            question="Which intervention types get DECLINED most?",
            category="interventions",
            query_type="sql",
            description="Identifies interventions patients often refuse"
        ),
        SuggestedQuestion(
            question="PENDING interventions requiring action",
            category="interventions",
            query_type="sql",
            description="Interventions not yet contacted"
        ),
        SuggestedQuestion(
            question="Average time from intervention to first contact",
            category="interventions",
            query_type="sql",
            description="Time-to-action metric for staff performance"
        ),
        SuggestedQuestion(
            question="Top decline reasons for interventions",
            category="interventions",
            query_type="sql",
            description="Common reasons patients decline"
        ),
    ],

    QuestionCategory.TRIAGE: [
        SuggestedQuestion(
            question="Which triage suggestions do doctors reject most?",
            category="triage",
            query_type="sql",
            description="Identifies suggestions that need improvement"
        ),
        SuggestedQuestion(
            question="Triage suggestion acceptance rate by type",
            category="triage",
            query_type="sql",
            description="Acceptance rates for different suggestion categories"
        ),
        SuggestedQuestion(
            question="Most common rejection reasons from doctors",
            category="triage",
            query_type="sql",
            description="Why doctors reject suggestions"
        ),
        SuggestedQuestion(
            question="Suggestions doctors frequently modify",
            category="triage",
            query_type="sql",
            description="Suggestions that are partially accepted"
        ),
    ],

    QuestionCategory.ANALYTICS: [
        SuggestedQuestion(
            question="Patient count by consultation type this month",
            category="analytics",
            query_type="sql",
            description="Volume breakdown by consultation type"
        ),
        SuggestedQuestion(
            question="Consultation volume trend over last 6 months",
            category="analytics",
            query_type="sql",
            description="Shows consultation volume over time"
        ),
        SuggestedQuestion(
            question="Average consultations per doctor this week",
            category="analytics",
            query_type="sql",
            description="Doctor workload distribution"
        ),
        SuggestedQuestion(
            question="Most common chief complaints this month",
            category="analytics",
            query_type="sql",
            description="Top reasons patients visit"
        ),
    ],
}


async def get_suggested_questions_list(
    category: Optional[str] = None,
    hospital_id: Optional[UUID] = None,
    user_role: Optional[str] = None
) -> List[SuggestedQuestion]:
    """
    Get suggested questions, optionally filtered by category.

    Role-based filtering:
    - super_admin: All categories
    - hospital_admin: All categories
    - doctor: Clinical, risk, referrals (excludes interventions ROI, triage analytics)
    """
    all_questions = []

    # Determine allowed categories based on role
    allowed_categories = list(SUGGESTED_QUESTIONS.keys())

    # Doctors have limited access to some sensitive analytics
    if user_role not in ("super_admin", "admin"):
        # Remove intervention ROI and triage feedback from non-admin
        pass  # For now, allow all - can restrict later

    # Filter by category if specified
    if category:
        try:
            cat_enum = QuestionCategory(category)
            if cat_enum in allowed_categories:
                all_questions = SUGGESTED_QUESTIONS.get(cat_enum, [])
        except ValueError:
            pass  # Invalid category, return empty
    else:
        # Return all questions from allowed categories
        for cat in allowed_categories:
            all_questions.extend(SUGGESTED_QUESTIONS.get(cat, []))

    return all_questions
```

### Pydantic Models for Suggested Questions

Add to `backend/models/qa_models.py`:

```python
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel


class QuestionCategory(str, Enum):
    CLINICAL = "clinical"
    RISK = "risk"
    REFERRALS = "referrals"
    INTERVENTIONS = "interventions"
    TRIAGE = "triage"
    ANALYTICS = "analytics"


class SuggestedQuestion(BaseModel):
    question: str
    category: str
    query_type: str  # "semantic", "hybrid", "sql"
    description: str
```

---

## Phase 3: Permission Model

### Access Control Matrix

| Role | Scope | Filter Applied |
|------|-------|---------------|
| `super_admin` | All hospitals | None |
| `hospital_admin` | Own hospital | `WHERE hospital_id = $hospital_id` (via doctors table JOIN) |
| `doctor` | Own + shared patients | `WHERE doctor_id = $id OR patient_id IN (shared)` |

### Patient-Doctor Relationship Note

The `patients` table uses `doctor_ids UUID[]` (array) to support multiple doctors per patient.
When checking doctor access to a patient:
```sql
-- Check if doctor has access to patient
WHERE $doctor_id = ANY(p.doctor_ids)
   OR EXISTS (
       SELECT 1 FROM patient_sharing ps
       WHERE ps.patient_id = p.id
       AND ps.shared_with_doctor_id = $doctor_id
       AND ps.is_active = true
   )
```

### Integration with Existing Auth

The Q&A Engine uses the existing `ClientContext` from `backend/dependencies/auth.py`:

```python
# Existing ClientContext (no changes needed)
class ClientContext(BaseModel):
    client_type: Literal["ehr", "mobile_app", "web_app", "admin"]
    client_id: UUID
    hospital_id: Optional[UUID]  # NULL = global access (super_admin)
    allowed_doctor_ids: Optional[List[UUID]]  # NULL = all doctors
    user_role: Optional[Literal["super_admin", "admin", "viewer"]]
```

---

## Phase 4: Frontend Components

### New Files to Create

| File | Purpose |
|------|---------|
| `app/components/QAEngineScreen.tsx` | Main Q&A chat interface |
| `app/components/qa/QAChatMessage.tsx` | Individual message component |
| `app/components/qa/QAResultsTable.tsx` | Table results display |
| `app/components/qa/QAChart.tsx` | Chart visualization (Recharts) |
| `app/components/qa/QAExportButtons.tsx` | CSV/PDF export |
| `app/components/qa/QASuggestedQuestions.tsx` | Suggested questions picker by category |

### Modifications to Existing Files

**`lib/types.ts`** - Add Q&A types:
```typescript
// Add to AppMode enum
export enum AppMode {
  // ... existing modes
  QA_Engine = 'qa_engine',
}

// Q&A specific types
export interface QAQuery {
  query: string;
  limit?: number;
}

export interface QAResponse {
  query_type: 'semantic' | 'hybrid' | 'sql';
  response_format: 'narrative' | 'table' | 'chart';
  narrative?: string;
  table_data?: any[];
  chart_type?: 'bar' | 'line' | 'pie' | 'stat_card';
  chart_data?: any[];
  generated_sql?: string;
  total_count?: number;
  sources?: any[];
}

export interface QAMessage {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  response?: QAResponse;
  timestamp: Date;
}

export interface EmbeddingModel {
  model_code: string;
  model_name: string;
  description: string;
  provider: string;
  dimensions: number;
  cost_per_million: number;
  supports_medical: boolean;
  is_default: boolean;
}

export interface SuggestedQuestion {
  question: string;
  category: string;  // 'clinical' | 'risk' | 'referrals' | 'interventions' | 'triage' | 'analytics'
  query_type: string;  // 'semantic' | 'hybrid' | 'sql'
  description: string;
}

export type QuestionCategory = 'clinical' | 'risk' | 'referrals' | 'interventions' | 'triage' | 'analytics';
```

**`lib/apiClient.ts`** - Add Q&A API methods:
```typescript
// Add to existing apiClient.ts

export const qaApi = {
  query: (auth: AuthState, query: string, limit?: number) =>
    authPost<QAResponse>('/api/v1/qa/query', auth, { query, limit }),

  getHistory: (auth: AuthState, limit?: number) =>
    authGet<QAMessage[]>(`/api/v1/qa/history?limit=${limit || 20}`, auth),

  exportResults: (auth: AuthState, data: any, format: 'csv' | 'pdf') =>
    authPost<Blob>('/api/v1/qa/export', auth, { data, format }),

  getSuggestedQuestions: (auth: AuthState, category?: string) =>
    authGet<SuggestedQuestion[]>(
      `/api/v1/qa/suggested-questions${category ? `?category=${category}` : ''}`,
      auth
    ),
};

export const qaSettingsApi = {
  listEmbeddingModels: (auth: AuthState) =>
    authGet<EmbeddingModel[]>('/api/v1/qa/settings/embedding-models', auth),

  getCurrentModel: (auth: AuthState, hospitalId?: string) =>
    authGet<EmbeddingModel>(
      `/api/v1/qa/settings/current-model${hospitalId ? `?hospital_id=${hospitalId}` : ''}`,
      auth
    ),

  setEmbeddingModel: (auth: AuthState, modelCode: string, hospitalId?: string, reembed?: boolean) =>
    authPost('/api/v1/qa/settings/embedding-model', auth, {
      model_code: modelCode,
      hospital_id: hospitalId,
      reembed_existing: reembed
    }),
};
```

### Suggested Questions Picker Component

```tsx
// app/components/qa/QASuggestedQuestions.tsx
'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/lib/auth';
import { qaApi } from '@/lib/apiClient';
import { SuggestedQuestion, QuestionCategory } from '@/lib/types';

interface QASuggestedQuestionsProps {
  onSelectQuestion: (question: string) => void;
  collapsed?: boolean;
}

const CATEGORY_LABELS: Record<QuestionCategory, { label: string; icon: string; color: string }> = {
  clinical: { label: 'Clinical', icon: '🩺', color: 'bg-blue-100 text-blue-800 border-blue-200' },
  risk: { label: 'Risk & Severity', icon: '⚠️', color: 'bg-red-100 text-red-800 border-red-200' },
  referrals: { label: 'Referrals', icon: '🏥', color: 'bg-green-100 text-green-800 border-green-200' },
  interventions: { label: 'Interventions', icon: '📋', color: 'bg-purple-100 text-purple-800 border-purple-200' },
  triage: { label: 'Triage', icon: '🎯', color: 'bg-orange-100 text-orange-800 border-orange-200' },
  analytics: { label: 'Analytics', icon: '📊', color: 'bg-gray-100 text-gray-800 border-gray-200' },
};

export function QASuggestedQuestions({ onSelectQuestion, collapsed = false }: QASuggestedQuestionsProps) {
  const { auth } = useAuth();
  const [questions, setQuestions] = useState<SuggestedQuestion[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<QuestionCategory | null>(null);
  const [loading, setLoading] = useState(true);
  const [isExpanded, setIsExpanded] = useState(!collapsed);

  useEffect(() => {
    loadQuestions();
  }, [selectedCategory]);

  const loadQuestions = async () => {
    setLoading(true);
    try {
      const data = await qaApi.getSuggestedQuestions(auth, selectedCategory || undefined);
      setQuestions(data);
    } catch (error) {
      console.error('Failed to load suggested questions:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCategoryClick = (category: QuestionCategory) => {
    setSelectedCategory(selectedCategory === category ? null : category);
  };

  const handleQuestionClick = (question: string) => {
    onSelectQuestion(question);
  };

  // Group questions by category for display
  const questionsByCategory = questions.reduce((acc, q) => {
    const cat = q.category as QuestionCategory;
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(q);
    return acc;
  }, {} as Record<QuestionCategory, SuggestedQuestion[]>);

  if (!isExpanded) {
    return (
      <button
        onClick={() => setIsExpanded(true)}
        className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
      >
        <span>💡</span> Show suggested questions
      </button>
    );
  }

  return (
    <div className="border rounded-lg bg-gray-50 p-3">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-700">Suggested Questions</h3>
        <button
          onClick={() => setIsExpanded(false)}
          className="text-gray-400 hover:text-gray-600 text-xs"
        >
          Hide
        </button>
      </div>

      {/* Category Pills */}
      <div className="flex flex-wrap gap-2 mb-3">
        {Object.entries(CATEGORY_LABELS).map(([cat, { label, icon, color }]) => (
          <button
            key={cat}
            onClick={() => handleCategoryClick(cat as QuestionCategory)}
            className={`px-3 py-1 text-xs rounded-full border transition-all ${
              selectedCategory === cat
                ? color + ' ring-2 ring-offset-1'
                : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-100'
            }`}
          >
            {icon} {label}
          </button>
        ))}
      </div>

      {/* Questions List */}
      {loading ? (
        <div className="text-center text-gray-400 py-4">Loading...</div>
      ) : (
        <div className="max-h-64 overflow-y-auto space-y-2">
          {selectedCategory ? (
            // Show questions for selected category
            questionsByCategory[selectedCategory]?.map((q, idx) => (
              <QuestionCard key={idx} question={q} onClick={handleQuestionClick} />
            ))
          ) : (
            // Show a few from each category
            Object.entries(questionsByCategory).map(([cat, qs]) => (
              <div key={cat} className="mb-3">
                <div className="text-xs font-medium text-gray-500 mb-1">
                  {CATEGORY_LABELS[cat as QuestionCategory]?.icon} {CATEGORY_LABELS[cat as QuestionCategory]?.label}
                </div>
                {qs.slice(0, 2).map((q, idx) => (
                  <QuestionCard key={idx} question={q} onClick={handleQuestionClick} />
                ))}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function QuestionCard({
  question,
  onClick,
}: {
  question: SuggestedQuestion;
  onClick: (q: string) => void;
}) {
  return (
    <button
      onClick={() => onClick(question.question)}
      className="w-full text-left p-2 rounded border border-gray-200 bg-white hover:bg-blue-50 hover:border-blue-300 transition-colors"
    >
      <div className="text-sm text-gray-800">{question.question}</div>
      <div className="text-xs text-gray-500 mt-1">{question.description}</div>
    </button>
  );
}
```

### Chat Interface Component

```tsx
// app/components/QAEngineScreen.tsx
'use client';

import { useState, useRef, useEffect } from 'react';
import { useAuth } from '@/lib/auth';
import { qaApi } from '@/lib/apiClient';
import { QAMessage, QAResponse } from '@/lib/types';
import { QAChatMessage } from './qa/QAChatMessage';
import { QAResultsTable } from './qa/QAResultsTable';
import { QAChart } from './qa/QAChart';
import { QASuggestedQuestions } from './qa/QASuggestedQuestions';

export function QAEngineScreen() {
  const { auth } = useAuth();
  const [messages, setMessages] = useState<QAMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSelectSuggestedQuestion = (question: string) => {
    setInput(question);
    // Optionally auto-submit
    // handleSubmit(new Event('submit') as any);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage: QAMessage = {
      id: crypto.randomUUID(),
      type: 'user',
      content: input,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await qaApi.query(auth, input);

      const assistantMessage: QAMessage = {
        id: crypto.randomUUID(),
        type: 'assistant',
        content: response.narrative || '',
        response,
        timestamp: new Date(),
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage: QAMessage = {
        id: crypto.randomUUID(),
        type: 'assistant',
        content: `Error: ${error instanceof Error ? error.message : 'Query failed'}`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-lg shadow">
      {/* Header */}
      <div className="px-4 py-3 border-b">
        <h2 className="text-lg font-semibold">Medical Q&A</h2>
        <p className="text-sm text-gray-500">
          Ask questions about patient data, patterns, and analytics
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="space-y-4">
            {/* Suggested Questions Picker */}
            <QASuggestedQuestions onSelectQuestion={handleSelectSuggestedQuestion} />

            <div className="text-center text-gray-400 text-sm">
              Or type your own question below
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <QAChatMessage key={msg.id} message={msg} />
        ))}

        {loading && (
          <div className="flex items-center space-x-2 text-gray-500">
            <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full" />
            <span>Analyzing...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t">
        {/* Collapsed suggested questions for when there are messages */}
        {messages.length > 0 && (
          <div className="mb-2">
            <QASuggestedQuestions
              onSelectQuestion={handleSelectSuggestedQuestion}
              collapsed={true}
            />
          </div>
        )}
        <div className="flex space-x-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about your patient data..."
            className="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Ask
          </button>
        </div>
      </form>
    </div>
  );
}
```

### Embedding Model Settings (Integrate into ProcessingModesAdminScreen)

Instead of a separate screen, add embedding model selection to the existing `ProcessingModesAdminScreen.tsx`:

```tsx
// Add to existing ProcessingModesAdminScreen.tsx

// In the form, add:
<div className="space-y-2">
  <label className="block text-sm font-medium">Q&A Embedding Model</label>
  <select
    value={formData.qa_embedding_model || ''}
    onChange={(e) => setFormData({ ...formData, qa_embedding_model: e.target.value })}
    className="w-full p-2 border rounded"
  >
    <option value="">Use Default (Cohere v4)</option>
    {embeddingModels.map(model => (
      <option key={model.model_code} value={model.model_code}>
        {model.model_name} {model.supports_medical && '(Medical)'} - ${model.cost_per_million}/1M
      </option>
    ))}
  </select>
  <p className="text-xs text-gray-500">
    Changing this will re-index all extractions for this hospital
  </p>
</div>
```

### Dependencies to Add

**`package.json`:**
```json
{
  "dependencies": {
    "recharts": "^2.10.0",
    "react-markdown": "^9.0.0"
  }
}
```

---

## Phase 5: Embedding Pipeline

### Hook into Extraction Save Flow

Modify `backend/routers/extractions.py` to trigger embedding generation:

```python
# In save_extraction endpoint, after successful save:
from services.qa.embedding_job_service import reembed_single_extraction

# After extraction is saved successfully
background_tasks.add_task(reembed_single_extraction, extraction_id)
```

### Backfill Script

```python
# backend/scripts/backfill_embeddings.py
import asyncio
from services.qa.embedding_job_service import queue_reembedding_job

async def main():
    """Backfill embeddings for all existing extractions"""
    print("Starting embedding backfill...")
    await queue_reembedding_job(hospital_id=None)  # All hospitals
    print("Backfill complete!")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Implementation Order

### Phase 0: Dependencies (1 day)
1. Add `cohere`, `pgvector`, `openai` to `requirements.txt`
2. Add `recharts`, `react-markdown` to `package.json`
3. Add environment variables (`COHERE_API_KEY`, `OPENAI_API_KEY`)

### Phase 1: Database (1-2 days)
1. Create migration `20260XXX_add_qa_engine_tables.sql`
2. Apply migration via `supabase db push`
3. Run seed script for embedding models
4. Verify pgvector extension and indexes

### Phase 2: Embedding Service (2-3 days)
1. Implement `embedding_service.py` with multi-provider support
2. Implement `embedding_job_service.py` for background processing
3. Create backfill script
4. Run backfill on existing extractions
5. Add embedding generation hook to extraction save flow

### Phase 3: Search & Analytics API (2-3 days)
1. Implement `semantic_search_service.py`
2. Implement `query_classifier_service.py`
3. Implement `analytics_engine_service.py` with Text-to-SQL
4. Implement `qa_synthesis_service.py` for narrative generation
5. Create `/api/v1/qa/*` endpoints
6. Test with sample queries

### Phase 4: Frontend (3-4 days)
1. Add `QA_Engine` to `AppMode` enum
2. Add Q&A types to `lib/types.ts`
3. Add Q&A API methods to `lib/apiClient.ts`
4. Build `QAEngineScreen.tsx` chat interface
5. Build result components (table, chart, narrative)
6. Add Q&A tab to navigation
7. Integrate embedding model selector into ProcessingModesAdminScreen

### Phase 5: Testing & Polish (2-3 days)
1. Test permission enforcement across all roles
2. Test all query types (semantic, hybrid, SQL)
3. Add export functionality (CSV/PDF)
4. Add query history
5. Performance testing with 10K+ extractions
6. Final security review

---

## Key Files Summary

### New Backend Files
- `backend/services/qa/embedding_service.py` - Multi-provider embedding service (document + segment level)
- `backend/services/qa/qa_service.py` - Main Q&A orchestration
- `backend/services/qa/semantic_search_service.py` - pgvector search (document + segment level)
- `backend/services/qa/analytics_engine_service.py` - Text-to-SQL (queries extraction_segments + clinical tables)
- `backend/services/qa/query_classifier_service.py` - Query router (determines search level)
- `backend/services/qa/qa_synthesis_service.py` - Narrative generation
- `backend/services/qa/embedding_job_service.py` - Background embedding jobs
- `backend/services/qa/suggested_questions_service.py` - Pre-defined question categories
- `backend/routers/qa.py` - Q&A API endpoints (including `/suggested-questions`)
- `backend/routers/qa_settings.py` - Embedding model config API
- `backend/models/qa_models.py` - Pydantic models (including `SuggestedQuestion`, `QuestionCategory`)
- `backend/scripts/backfill_embeddings.py` - Initial embedding script
- `backend/supabase/migrations/20260XXX_add_qa_engine_tables.sql`

### New Database Tables
- `embedding_models` - Embedding model configurations (Cohere, OpenAI, Gemini)
- `extraction_embeddings` - Document-level embeddings (transcript + all segments)
- `segment_embeddings` - Segment-level embeddings (individual extraction_segments)
- `qa_engine_settings` - Per-hospital embedding model configuration
- `qa_query_history` - Query analytics and debugging
- `patient_sharing` - Doctor-to-doctor patient sharing

### Existing Clinical Tables (Used by Analytics Engine)
- `clinical_severity_assessments` - Severity scoring
- `patient_dropoff_risk` - Retention risk indicators
- `care_quality_risk` - Care gap detection
- `allied_health_needs` - Referral recommendations
- `other_clinical_needs` - Follow-up needs
- `consultation_insights` - Raw AI signals (14 groups)
- `patient_interventions` - Suggested actions
- `intervention_outcomes` - Action tracking & ROI
- `triage_suggestion_log` - Triage suggestions
- `triage_feedback` - Doctor feedback

### New Frontend Files
- `app/components/QAEngineScreen.tsx` - Main chat interface
- `app/components/qa/QAChatMessage.tsx` - Message component
- `app/components/qa/QAResultsTable.tsx` - Table display
- `app/components/qa/QAChart.tsx` - Recharts wrapper
- `app/components/qa/QAExportButtons.tsx` - Export functionality
- `app/components/qa/QASuggestedQuestions.tsx` - Suggested questions picker with categories

### Files to Modify
- `backend/routers/extractions.py` - Add embedding generation hook
- `backend/main.py` - Register new routers (qa, qa_settings)
- `lib/types.ts` - Add Q&A types and AppMode
- `lib/apiClient.ts` - Add Q&A API methods
- `app/page.tsx` - Add Q&A tab to navigation
- `app/components/ProcessingModesAdminScreen.tsx` - Add embedding model selector

---

## Security Checklist

- [ ] SQL injection prevention (validate all generated SQL in `_validate_sql`)
- [ ] Permission enforcement using existing `ClientContext` pattern
- [ ] Audit logging via `audit_service.py` for all Q&A queries
- [ ] Rate limiting on Q&A endpoint (follow existing patterns)
- [ ] LLM cost tracking via `llm_usage_service.py`
- [ ] Query timeout (5s max for SQL, 30s for synthesis)
- [ ] No raw PHI in embeddings (use hashed patient IDs where possible)

---

## Example Queries to Test

### SEMANTIC Queries (→ Narrative Synthesis)

**Document-Level (broad patterns):**
- "What was the most common historical pattern in patients I saw last month?"
- "Why do my diabetic patients tend to have anxiety?"
- "What insights can you give about patients with recurring complaints?"
- "How has patient anxiety changed over time?"

**Segment-Level (targeted insights):**
- "What are the common diagnosis patterns?" → `segment_codes: ["diagnosis"]`
- "What medications are frequently prescribed together?" → `segment_codes: ["prescription"]`
- "What abnormal findings appear in examinations?" → `segment_codes: ["examination"]`

### HYBRID Queries (→ Patient Table)

**Document-Level:**
- "Patients with complex medical histories and multiple comorbidities"
- "Recent consultations mentioning chest pain and shortness of breath"

**Segment-Level:**
- "Patients diagnosed with gastroenteritis" → `segment_codes: ["diagnosis"]`
- "Patients prescribed antibiotics last week" → `segment_codes: ["prescription"]`
- "Patients with abnormal blood pressure on examination" → `segment_codes: ["examination"]`
- "Patients who had blood tests ordered" → `segment_codes: ["investigations"]`
- "Patients over 60 with hypertension diagnosis" → `segment_codes: ["diagnosis"]` + age filter

### SQL/Analytics Queries (→ Charts)

**Extraction Segment Queries:**
- "How many prescriptions had amoxicillin antibiotic in them?"
  ```sql
  SELECT COUNT(*) FROM extraction_segments
  WHERE segment_code = 'prescription'
  AND segment_value_text ILIKE '%amoxicillin%'
  ```
- "Top 10 most prescribed medicines this quarter"
- "Patient count by consultation type per month"
- "Distribution of diagnosis categories"
- "Average number of medications per prescription"

**Clinical Severity & Risk Queries:**
- "How many HIGH severity patients did I see this month?"
- "Show patients with HIGH or CRITICAL dropoff risk"
- "Patients with financial risk who might not return"
- "List care quality issues - missed red flags"
- "Average severity score by consultation type"
- "Trend of HIGH severity cases over time"

**Allied Health & Clinical Needs Queries:**
- "How many patients need mental health referral?"
- "List all physiotherapy referrals this week"
- "Patients needing cardiac rehabilitation"
- "Count of allied health needs by type"
- "Patients with recurring diagnostic needs"
- "Prescription refill reminders for next month"

**Intervention & Outcome Queries:**
- "Intervention conversion rate by category"
- "How much revenue from COMPLETED interventions this month?"
- "Which intervention types get DECLINED most?"
- "Average time from PENDING to CONTACTED"
- "REVENUE interventions pending action"
- "QUALITY interventions with medication safety issues"

**Triage & Feedback Queries:**
- "Which triage suggestions do doctors reject most?"
- "Acceptance rate for investigation suggestions"
- "Most common rejection reasons"
- "Suggestions modified by doctors (what patterns?)"

### Query Classification Examples

| Query | Intent | Search Level | Segment Codes |
|-------|--------|--------------|---------------|
| "What patterns do diabetic patients show?" | SEMANTIC | DOCUMENT | - |
| "Patients diagnosed with diabetes" | HYBRID | SEGMENT | `["diagnosis"]` |
| "Prescriptions containing metformin" | HYBRID | SEGMENT | `["prescription"]` |
| "Why do patients have recurring infections?" | SEMANTIC | DOCUMENT | - |
| "Abnormal lab results last month" | HYBRID | SEGMENT | `["investigations"]` |
| "How many patients had fever?" | SQL | - | - |
| "Top 10 diagnoses this quarter" | SQL | - | - |
| "HIGH severity patients this week" | SQL | - | - |
| "Patients with dropoff risk > 70%" | SQL | - | - |
| "Care quality issues with missed red flags" | SQL | - | - |
| "Mental health referrals needed" | SQL | - | - |
| "Intervention conversion rates" | SQL | - | - |
| "Triage suggestion acceptance rate" | SQL | - | - |
| "Why do HIGH risk patients have financial concerns?" | SEMANTIC | - | - |

---

## Research Sources

- [OpenAI vs Gemini vs Cohere Embedding Comparison](https://research.aimultiple.com/embedding-models/)
- [Generalist vs Specialized Medical Embeddings](https://arxiv.org/html/2401.01943v2)
- [Medical Domain Embedding Study](https://arxiv.org/html/2507.19407v1)
- [Cohere Embed v4 Healthcare Fine-tuning](https://venturebeat.com/ai/cohere-launches-embed-4-new-multimodal-search-model-processes-200-page-documents)
- [Blended RAG Hybrid Search](https://arxiv.org/abs/2404.07220)
- [Query Routing in RAG Applications](https://towardsdatascience.com/routing-in-rag-driven-applications-a685460a7220/)

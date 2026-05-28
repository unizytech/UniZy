# Q&A Engine Microservice Extraction Plan

> **Status:** Saved for future implementation
> **Target:** Separate repository (e.g., `qa-engine-microservice`)

## Overview

Extract the Q&A Engine from Unizy into a standalone, schema-agnostic microservice that can work with any database schema, not just medical extractions.

**Goal:** Create a reusable RAG-based Q&A service that:
- Supports ANY data domain (medical, legal, finance, etc.)
- Auto-generates suggested questions from schema definitions
- Dynamically adapts query classification to the data domain
- Provides pluggable embedding providers (Cohere, OpenAI, Gemini, custom)
- Supports multi-tenant isolation

---

## Current State Analysis

### What Exists in Unizy

**6 Q&A Tables:**
- `embedding_models` - Provider configurations (GENERIC)
- `extraction_embeddings` - Document vectors (COUPLED to `medical_extractions`)
- `segment_embeddings` - Segment vectors (COUPLED)
- `qa_engine_settings` - Per-hospital config (COUPLED to `hospitals`)
- `qa_query_history` - Audit trail (COUPLED)
- `patient_sharing` - Access control (COUPLED)

**8 Service Modules:**
| Service | Coupling Issue |
|---------|----------------|
| `embedding_service.py` | References `medical_extractions` table |
| `query_classifier_service.py` | Hardcoded segment codes (DIAGNOSIS, PRESCRIPTION, etc.) |
| `semantic_search_service.py` | SQL joins to `patients`, `doctors` tables |
| `qa_synthesis_service.py` | Hardcoded field mappings (diagnosis, chiefComplaints) |
| `analytics_engine_service.py` | Hardcoded database schema in prompt |
| `suggested_questions_service.py` | Medical-specific questions |
| `embedding_job_service.py` | Tied to `medical_extractions` |

### Key Abstractions Needed

1. **Schema Registry** - Define embeddable data structure dynamically
2. **Tenant Isolation** - Replace `hospital_id` with generic `tenant_id`
3. **Dynamic Classifier** - Build prompts from schema, not hardcoded codes
4. **Generic Document Model** - Replace `medical_extractions` with `documents`

---

## Microservice Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   Q&A ENGINE MICROSERVICE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Schema    │  │    Data     │  │   Query     │              │
│  │  Registry   │  │  Ingestion  │  │    API      │              │
│  │    API      │  │    API      │  │             │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
│         │                │                │                      │
│         ▼                ▼                ▼                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   CORE SERVICES                           │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │   │
│  │  │ Dynamic  │ │Embedding │ │ Semantic │ │  Response    │ │   │
│  │  │Classifier│ │Generator │ │ Search   │ │ Synthesizer  │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              EMBEDDING PROVIDERS                          │   │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐          │   │
│  │  │ Cohere │  │ OpenAI │  │ Gemini │  │ Custom │          │   │
│  │  └────────┘  └────────┘  └────────┘  └────────┘          │   │
│  └──────────────────────────────────────────────────────────┘   │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            PostgreSQL + pgvector                          │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Database Schema (Generic)

### Core Tables

```sql
-- 1. Multi-tenant isolation
CREATE TABLE tenants (
    id UUID PRIMARY KEY,
    tenant_code VARCHAR(100) UNIQUE,
    tenant_name VARCHAR(255),
    embedding_provider VARCHAR(50) DEFAULT 'gemini',
    embedding_model_id UUID,
    settings JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE
);

-- 2. Schema definitions (the key abstraction)
CREATE TABLE schemas (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    schema_code VARCHAR(100),
    schema_name VARCHAR(255),
    document_definition JSONB,   -- {primary_text_field, metadata_fields, reference_fields}
    segment_definitions JSONB,   -- [{code, name, description, keywords, is_embeddable}]
    UNIQUE(tenant_id, schema_code)
);

-- 3. Generic documents (replaces medical_extractions)
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    schema_id UUID REFERENCES schemas(id),
    external_id VARCHAR(255),
    primary_content TEXT,
    structured_data JSONB,
    -- Denormalized for search
    author_id VARCHAR(255),
    author_name VARCHAR(255),
    category_id VARCHAR(255),
    UNIQUE(tenant_id, external_id)
);

-- 4. Segments extracted from documents
CREATE TABLE segments (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    document_id UUID REFERENCES documents(id),
    segment_code VARCHAR(100),
    content TEXT
);

-- 5. Document-level embeddings
CREATE TABLE document_embeddings (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    document_id UUID REFERENCES documents(id),
    model_id UUID REFERENCES embedding_models(id),
    embedding vector(3072),
    content_hash VARCHAR(64),
    UNIQUE(document_id, model_id)
);

-- 6. Segment-level embeddings
CREATE TABLE segment_embeddings (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    document_id UUID REFERENCES documents(id),
    segment_id UUID REFERENCES segments(id),
    segment_code VARCHAR(100),
    model_id UUID REFERENCES embedding_models(id),
    embedding vector(3072),
    UNIQUE(segment_id, model_id)
);

-- 7. Auto-generated + custom suggested questions
CREATE TABLE suggested_questions (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    schema_id UUID,
    question_text TEXT,
    category VARCHAR(100),
    expected_intent VARCHAR(50),
    expected_segment_codes TEXT[]
);

-- 8. Query audit trail
CREATE TABLE query_history (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    query_text TEXT,
    query_intent VARCHAR(50),
    result_count INT,
    total_time_ms INT
);
```

---

## API Endpoints

### Schema Registry API
```
POST   /api/v1/schemas                    # Register schema for tenant
GET    /api/v1/schemas/{schema_id}        # Get schema definition
GET    /api/v1/tenants/{id}/schemas       # List tenant schemas
PUT    /api/v1/schemas/{schema_id}        # Update schema (new version)
```

### Data Ingestion API
```
POST   /api/v1/documents                  # Ingest single document
POST   /api/v1/documents/batch            # Batch ingest
PUT    /api/v1/documents/{id}             # Update (re-embeds)
DELETE /api/v1/documents/{id}             # Delete
```

### Query API
```
POST   /api/v1/query                      # Execute Q&A query
GET    /api/v1/query/suggestions          # Get suggested questions
GET    /api/v1/query/history              # Query history
```

### Configuration API
```
GET    /api/v1/tenants/{id}/settings      # Get settings
PUT    /api/v1/tenants/{id}/settings      # Update settings
GET    /api/v1/embedding-models           # List available models
POST   /api/v1/embedding-providers/custom # Register custom provider
POST   /api/v1/tenants/{id}/webhooks      # Configure webhooks
```

---

## Key Implementation Changes

### 1. Dynamic Query Classifier

**Before (hardcoded):**
```python
# query_classifier_service.py
segment_mappings = {
    "medication": "PRESCRIPTION",
    "diagnosis": "DIAGNOSIS",
    # ... hardcoded
}
```

**After (schema-driven):**
```python
class DynamicQueryClassifier:
    async def classify(self, query: str, tenant_id: UUID):
        # Load schema from DB
        schema = await self.get_schema(tenant_id)

        # Build prompt dynamically
        segment_descriptions = "\n".join([
            f"- {seg['code']}: {seg['description']}"
            for seg in schema.segment_definitions
        ])

        prompt = f"""
        Classify for {schema.schema_name} domain.
        Available segments: {segment_descriptions}
        Query: "{query}"
        """
        return await self.llm.classify(prompt)
```

### 2. Auto-Generated Questions

```python
class QuestionGenerator:
    def generate(self, schema: Schema) -> List[Question]:
        questions = []
        for segment in schema.segment_definitions:
            questions.append(f"What are common patterns in {segment.name}?")
            questions.append(f"Show documents with specific {segment.name}")
        questions.append("How many documents this month?")
        return questions
```

### 3. Schema Definition Example

```json
{
  "schema_code": "medical_consultation",
  "schema_name": "Medical Consultation",
  "document_definition": {
    "primary_text_field": "transcript",
    "reference_fields": {
      "author": {"label": "Doctor", "name_field": "doctor_name"},
      "category": {"label": "Consultation Type"}
    }
  },
  "segment_definitions": [
    {"code": "diagnosis", "name": "Diagnosis", "keywords": ["diagnosed", "condition"]},
    {"code": "prescription", "name": "Prescription", "keywords": ["prescribed", "medication"]},
    {"code": "chiefComplaints", "name": "Chief Complaints", "keywords": ["complaint", "symptoms"]}
  ]
}
```

---

## Project Structure

```
qa-engine-microservice/
├── main.py
├── config.py
├── requirements.txt
├── Dockerfile
│
├── routers/
│   ├── schema_router.py
│   ├── document_router.py
│   ├── query_router.py
│   └── config_router.py
│
├── services/
│   ├── schema_service.py
│   ├── document_service.py
│   ├── embedding/
│   │   ├── base_provider.py
│   │   ├── cohere_provider.py
│   │   ├── openai_provider.py
│   │   ├── gemini_provider.py
│   │   └── embedding_service.py
│   ├── search/
│   │   ├── semantic_search.py
│   │   └── analytics_search.py
│   └── query/
│       ├── dynamic_classifier.py
│       ├── question_generator.py
│       └── response_synthesizer.py
│
├── models/
│   ├── tenant_models.py
│   ├── schema_models.py
│   ├── document_models.py
│   └── query_models.py
│
└── database/
    └── migrations/
```

---

## Implementation Phases

### Phase 1: Core Microservice Setup
1. Create new FastAPI project structure
2. Implement generic database schema with migrations
3. Create tenant and schema management APIs
4. Port embedding providers (already abstracted)

### Phase 2: Dynamic Classification
1. Build schema-aware query classifier
2. Implement auto-generated questions from schema
3. Create dynamic synthesis prompts

### Phase 3: Data Ingestion
1. Document ingestion API with auto-segmentation
2. Batch ingestion with job tracking
3. Webhook notifications on completion

### Phase 4: Query & Search
1. Port semantic search with generic schema
2. Adapt analytics engine for any schema
3. Build response synthesizer with schema context

### Phase 5: Integration Adapter
1. Create adapter for Unizy
2. Build migration script for existing data
3. Add medical schema pre-configuration

---

## Integration with Unizy

### Option A: Direct API Calls
```python
# After extraction save
await qa_client.ingest_document(
    tenant_id=hospital_id,
    schema_id=MEDICAL_SCHEMA_ID,
    external_id=str(extraction_id),
    primary_content=transcript,
    structured_data=extraction_json
)
```

### Option B: Webhook Events
```python
# QA Engine notifies on embedding complete
@app.post("/webhooks/qa-engine")
async def handle_webhook(event: WebhookEvent):
    if event.event_type == "embedding_complete":
        await mark_extraction_indexed(event.data["external_id"])
```

---

## Verification Plan

### 1. Microservice Health
```bash
curl http://localhost:8001/api/v1/health
```

### 2. Schema Registration
```bash
curl -X POST http://localhost:8001/api/v1/schemas \
  -d '{"tenant_id": "...", "schema_code": "medical", ...}'
```

### 3. Document Ingestion
```bash
curl -X POST http://localhost:8001/api/v1/documents \
  -d '{"tenant_id": "...", "schema_id": "...", "structured_data": {...}}'
```

### 4. Query Execution
```bash
curl -X POST http://localhost:8001/api/v1/query \
  -d '{"tenant_id": "...", "query": "What are common diagnoses?"}'
```

### 5. Auto-Generated Questions
```bash
curl http://localhost:8001/api/v1/query/suggestions?tenant_id=...
```

---

## Files to Extract from Unizy

| Source File | Destination | Changes Needed |
|-------------|-------------|----------------|
| `services/qa/embedding_service.py` | `services/embedding/` | Remove medical_extractions coupling |
| `services/qa/query_classifier_service.py` | `services/query/dynamic_classifier.py` | Make schema-driven |
| `services/qa/semantic_search_service.py` | `services/search/` | Generic document queries |
| `services/qa/qa_synthesis_service.py` | `services/query/response_synthesizer.py` | Schema-aware prompts |
| `services/qa/analytics_engine_service.py` | `services/search/analytics_search.py` | Dynamic schema introspection |
| `models/qa_models.py` | `models/` | Split into domain models |

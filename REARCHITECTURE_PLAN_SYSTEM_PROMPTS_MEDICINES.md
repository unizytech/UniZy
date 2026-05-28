# Rearchitecture Plan: Dynamic System Prompts & Doctor Medicine Lists

**Created:** 2025-11-25
**Status:** Planning Complete - Ready for Implementation

## Overview

Two major enhancements to the extraction pipeline:
1. **Database-driven System Prompts** - Replace hardcoded prompts with composable, versioned components
2. **Doctor Medicine List Integration** - Per-doctor medicine lists with hybrid AI + post-processing matching

---

## Part 1: Dynamic System Prompt Generation

### Current State
- System prompts hardcoded in `segment_registry.py` (lines 72-335)
- Components: Role, Capabilities, Critical Guidelines, Processing Info, Processing Rules, Special Handling, Validation Checklist
- No versioning or A/B testing capability

### Database Schema

#### 1.1 `system_prompt_components` (Reusable Building Blocks)
```sql
CREATE TABLE system_prompt_components (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    component_code VARCHAR(50) NOT NULL,          -- e.g., 'ROLE_MEDICAL_AI'
    component_name VARCHAR(255) NOT NULL,
    component_type VARCHAR(50) NOT NULL,          -- role, capabilities, critical_guidelines, processing_info, processing_rules, special_handling, validation_checklist
    content_text TEXT NOT NULL,
    content_version VARCHAR(20) DEFAULT '1.0.0',
    description TEXT,
    is_base_component BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES doctors(id),
    CONSTRAINT unique_component_code_version UNIQUE (component_code, content_version),
    CONSTRAINT valid_component_type CHECK (component_type IN ('role', 'capabilities', 'critical_guidelines', 'processing_info', 'processing_rules', 'special_handling', 'validation_checklist'))
);

CREATE INDEX idx_spc_component_type ON system_prompt_components(component_type);
CREATE INDEX idx_spc_is_base ON system_prompt_components(is_base_component) WHERE is_base_component = true;
```

#### 1.2 `system_prompt_configurations` (Versioned Assemblies)
```sql
CREATE TABLE system_prompt_configurations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_code VARCHAR(100) NOT NULL,            -- e.g., 'OP_STANDARD_V2'
    config_name VARCHAR(255) NOT NULL,
    config_version VARCHAR(20) DEFAULT '1.0.0',
    is_active BOOLEAN DEFAULT false,
    is_draft BOOLEAN DEFAULT true,
    inherits_from_id UUID REFERENCES system_prompt_configurations(id),
    assembled_system_prompt TEXT,                 -- Materialized/cached prompt
    assembled_at TIMESTAMPTZ,
    assembly_hash VARCHAR(64),
    description TEXT,
    use_case VARCHAR(100),                        -- 'standard', 'concise', 'detailed'
    estimated_token_count INTEGER,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES doctors(id),
    activated_at TIMESTAMPTZ,
    activated_by UUID REFERENCES doctors(id),
    CONSTRAINT unique_config_code_version UNIQUE (config_code, config_version)
);

CREATE INDEX idx_spc_config_active ON system_prompt_configurations(is_active) WHERE is_active = true;
```

#### 1.3 `system_prompt_config_components` (Junction with Ordering)
```sql
CREATE TABLE system_prompt_config_components (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_id UUID NOT NULL REFERENCES system_prompt_configurations(id) ON DELETE CASCADE,
    component_id UUID NOT NULL REFERENCES system_prompt_components(id) ON DELETE RESTRICT,
    display_order INTEGER NOT NULL DEFAULT 0,
    section_separator VARCHAR(50) DEFAULT '---',
    is_override BOOLEAN DEFAULT false,
    overrides_component_type VARCHAR(50),
    is_included BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_config_component UNIQUE (config_id, component_id),
    CONSTRAINT unique_config_order UNIQUE (config_id, display_order)
);

CREATE INDEX idx_spcc_config ON system_prompt_config_components(config_id);
```

#### 1.4 `consultation_type_system_prompts` (Junction with Versioning)
```sql
CREATE TABLE consultation_type_system_prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consultation_type_id UUID NOT NULL REFERENCES consultation_types(id) ON DELETE CASCADE,
    system_prompt_config_id UUID NOT NULL REFERENCES system_prompt_configurations(id) ON DELETE RESTRICT,
    is_active BOOLEAN DEFAULT false,
    activated_at TIMESTAMPTZ DEFAULT NOW(),
    activated_by UUID REFERENCES doctors(id),
    total_extractions INTEGER DEFAULT 0,
    avg_extraction_time_seconds DECIMAL(6,2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_consultation_config UNIQUE (consultation_type_id, system_prompt_config_id)
);

-- Enforce single active config per consultation type
CREATE UNIQUE INDEX idx_ctsp_single_active
    ON consultation_type_system_prompts(consultation_type_id)
    WHERE is_active = true;
```

### Python Service: `system_prompt_service.py`

```python
# Key functions:
def get_system_prompt_for_consultation_type(consultation_type_id: uuid.UUID, force_reassemble: bool = False) -> Optional[str]
def get_system_prompt_with_fallback(consultation_type_id: uuid.UUID, consultation_type_code: str) -> str
def assemble_system_prompt(config_id: uuid.UUID) -> str
def activate_prompt_config(consultation_type_id: uuid.UUID, config_id: uuid.UUID, activated_by: uuid.UUID) -> Dict
def create_prompt_component(...) -> Dict
def create_prompt_configuration(...) -> Dict
```

### Integration Points

1. **`segment_registry.py:generate_system_prompt()`** (lines 465-541)
   - Add `consultation_type_id` parameter
   - Call `get_system_prompt_with_fallback()` first
   - Fallback to hardcoded prompts if database returns None

2. **`segment_registry.py:generate_extraction_artifacts()`** (lines 955-1141)
   - Pass `consultation_type_id` to `generate_system_prompt()`

### Performance Strategy
- **Load at recording start** (parallel with audio setup)
- Materialized prompts stored in `assembled_system_prompt` column (~5ms retrieval)
- Re-assembly only on config changes

---

## Part 2: Doctor Medicine List Integration

### Database Schema

#### 2.1 `doctor_medicines` (Per-Doctor Medicine List)
```sql
CREATE TABLE doctor_medicines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    medicine_name VARCHAR(255) NOT NULL,          -- "AMLODIPINE 5MG"
    common_names TEXT[],                          -- ["Amlong", "Stamlo", "Norvasc"]
    category VARCHAR(100),                        -- "Antihypertensive"
    typical_dosage VARCHAR(255),                  -- "5-10mg once daily"
    normalized_name VARCHAR(255) NOT NULL,        -- "amlodipine 5mg"
    search_tokens TEXT[],                         -- ["amlodipine", "5mg", "amlong"]
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_doctor_medicine UNIQUE(doctor_id, normalized_name)
);

CREATE INDEX idx_doctor_medicines_doctor_id ON doctor_medicines(doctor_id) WHERE is_active = true;
CREATE INDEX idx_doctor_medicines_search ON doctor_medicines USING GIN(search_tokens);
```

#### 2.2 `medicine_list_uploads` (Upload Tracking)
```sql
CREATE TABLE medicine_list_uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_size_bytes INTEGER,
    row_count INTEGER,
    successful_imports INTEGER,
    failed_imports INTEGER,
    error_details JSONB,
    status VARCHAR(20) DEFAULT 'pending',         -- pending, processing, completed, failed
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);
```

#### 2.3 `medicine_match_log` (Audit Trail)
```sql
CREATE TABLE medicine_match_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID REFERENCES medical_extractions(id) ON DELETE CASCADE,
    doctor_id UUID REFERENCES doctors(id) ON DELETE SET NULL,
    original_medicine_name VARCHAR(255) NOT NULL,
    matched_medicine_id UUID REFERENCES doctor_medicines(id) ON DELETE SET NULL,
    matched_medicine_name VARCHAR(255),
    match_confidence DECIMAL(5,4),
    match_method VARCHAR(50),                     -- 'exact', 'fuzzy', 'common_name', 'no_match'
    diagnosis_context TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_medicine_match_log_extraction ON medicine_match_log(extraction_id);
```

#### 2.4 `hospital_medicine_lists` (Hospital-Level Sharing)
```sql
CREATE TABLE hospital_medicine_lists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
    medicine_name VARCHAR(255) NOT NULL,
    common_names TEXT[],
    category VARCHAR(100),
    typical_dosage VARCHAR(255),
    normalized_name VARCHAR(255) NOT NULL,
    search_tokens TEXT[],
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES doctors(id),
    CONSTRAINT uq_hospital_medicine UNIQUE(hospital_id, normalized_name)
);

CREATE INDEX idx_hospital_medicines_hospital_id ON hospital_medicine_lists(hospital_id) WHERE is_active = true;
```

**Sharing Flow:**
1. Admin creates hospital-wide medicine list
2. Doctors can "import" from hospital list to their personal list
3. Matching checks: doctor's list first → hospital list as fallback

### CSV Format
```csv
name,common_name,category,typical_dosage
"AMLODIPINE 5MG","Amlong, Stamlo, Norvasc",Antihypertensive,"5-10mg once daily"
"METFORMIN 500MG","Glycomet, Glucophage",Antidiabetic,"500mg twice daily"
```

### Python Service: `medicine_service.py`

```python
# Key functions:
def normalize_medicine_name(name: str) -> str
def generate_search_tokens(medicine_name: str, common_names: List[str]) -> List[str]
def parse_csv_medicine_list(csv_content: str) -> Tuple[List[Dict], List[Dict]]
def upload_medicine_list(doctor_id: uuid.UUID, csv_content: str, filename: str, replace_existing: bool) -> Dict
def get_medicine_list_for_prompt(doctor_id: uuid.UUID, max_medicines: int = 100) -> str
def match_medicine_name(extracted_name: str, doctor_id: uuid.UUID, diagnosis: str, threshold: float = 0.70) -> Dict
def postprocess_prescription_extraction(extraction_data: Dict, doctor_id: uuid.UUID, extraction_id: uuid.UUID, log_matches: bool) -> Dict
```

### Matching Algorithm (4-Stage)
1. **Stage 1: Exact Match** (confidence: 1.0) - normalized name equality
2. **Stage 2: Common Name Match** (confidence: 0.98) - matches any alias
3. **Stage 3: Fuzzy Match** (confidence: 0.70-0.95) - rapidfuzz ratio score
4. **Stage 4: Token Overlap** (confidence: 0.50-0.70) - intersection over union

**Diagnosis Context Boost:** +10% confidence when diagnosis matches medicine category

### Hybrid Integration

#### A. Prompt Injection (AI-Guided)
Modify `segment_registry.py:generate_user_prompt()` to inject:
```
**DOCTOR'S MEDICINE LIST (Use these exact names when extracting prescriptions):**

Antihypertensive:
  - AMLODIPINE 5MG (also: Amlong, Stamlo, Norvasc)
  - LOSARTAN 50MG (also: Losacar, Cozaar)

Antidiabetic:
  - METFORMIN 500MG (also: Glycomet, Glucophage)
```

#### B. Post-Processing (Validation)
In `extraction_service.py` after extraction:
```python
insights = postprocess_prescription_extraction(
    extraction_data=insights,
    doctor_id=doctor_uuid,
    extraction_id=extraction_id,
    log_matches=True
)
```

### API Endpoints (`routers/medicines.py`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/medicines/{doctor_id}/upload` | Upload CSV |
| GET | `/api/v1/medicines/{doctor_id}` | List medicines |
| POST | `/api/v1/medicines/{doctor_id}` | Add single medicine |
| PUT | `/api/v1/medicines/{doctor_id}/{medicine_id}` | Update |
| DELETE | `/api/v1/medicines/{doctor_id}/{medicine_id}` | Soft delete |
| POST | `/api/v1/medicines/{doctor_id}/test-match` | Test matching |

---

## Implementation Phases

### Phase 1: System Prompt Migration (Day 1)
- Create migration: `20251126000001_dynamic_system_prompts.sql`
- Tables: system_prompt_components, system_prompt_configurations, system_prompt_config_components, consultation_type_system_prompts
- Apply to Supabase, verify indexes

### Phase 2: System Prompt Backend (Day 1-2)
- Create `system_prompt_service.py`
- Implement assembly and fallback logic
- Create `system_prompts.py` router
- Integrate with `segment_registry.py`
- Seed base components from hardcoded prompts

### Phase 3: System Prompt Admin UI (Day 2)
- Create `SystemPromptAdminScreen.tsx`
- Component CRUD (create, edit, delete)
- Configuration assembly UI (drag-and-drop component ordering)
- Version management and activation

### Phase 4: Medicine List Migration (Day 3)
- Create migration: `20251126000002_doctor_medicines.sql`
- Tables: doctor_medicines, medicine_list_uploads, medicine_match_log, hospital_medicine_lists (for sharing)
- Apply to Supabase

### Phase 5: Medicine List Backend (Day 3-4)
- Create `medicine_service.py`
- CSV parsing, fuzzy matching with rapidfuzz
- Hospital-level sharing logic
- Create `medicines.py` router
- Integrate with prompt generation and extraction

### Phase 6: Medicine List Admin UI (Day 4)
- Create `MedicineListManager.tsx` component
- CSV upload with preview and validation
- Medicine list table with edit/delete
- Import from hospital shared list feature

### Phase 7: Testing & Validation (Day 5)
- End-to-end testing
- Verify fallback behavior
- Performance testing

---

## Critical Files to Modify

| File | Changes |
|------|---------|
| `backend/services/segment_registry.py` | Add database prompt lookup, medicine list injection |
| `backend/services/extraction_service.py` | Add post-processing for medicine matching |
| `backend/services/supabase_service.py` | Add new table operations |
| `backend/main.py` | Register new routers |
| `backend/requirements.txt` | Add `rapidfuzz>=3.6.0` |

## New Files to Create

### Backend
| File | Purpose |
|------|---------|
| `backend/services/system_prompt_service.py` | System prompt assembly and retrieval |
| `backend/services/medicine_service.py` | Medicine list management and matching |
| `backend/routers/medicines.py` | Medicine API endpoints |
| `backend/routers/system_prompts.py` | System prompt admin endpoints |
| `backend/supabase/migrations/20251126000001_dynamic_system_prompts.sql` | System prompt tables |
| `backend/supabase/migrations/20251126000002_doctor_medicines.sql` | Medicine list tables |

### Frontend (Admin UI)
| File | Purpose |
|------|---------|
| `app/components/SystemPromptAdminScreen.tsx` | System prompt component & config management |
| `app/components/SystemPromptComponentForm.tsx` | Create/edit prompt components |
| `app/components/SystemPromptConfigBuilder.tsx` | Drag-and-drop config assembly |
| `app/components/MedicineListManager.tsx` | Doctor medicine list management |
| `app/components/MedicineUploadModal.tsx` | CSV upload with preview |
| `app/components/HospitalMedicineListAdmin.tsx` | Hospital-level medicine list (admin) |
| `app/services/systemPromptApi.ts` | System prompt API client |
| `app/services/medicineApi.ts` | Medicine list API client |

---

## Dependencies

```
rapidfuzz>=3.6.0   # Fuzzy string matching (backend)
```

---

## Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Component Storage | Composable records | Maximum flexibility, reuse across configs |
| Medicine Format | CSV with details | Familiar format, supports metadata |
| Medicine Matching | Hybrid (AI + post-process) | Best accuracy with validation |
| Versioning | Multiple versions | A/B testing capability |
| Admin UI | Build screens | Visual management needed |
| Medicine Sharing | Hospital-level | Reduces duplicate work |
| Migrations | Split (2 files) | Independent rollback capability |

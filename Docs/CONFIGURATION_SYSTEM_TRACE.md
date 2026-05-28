# Configuration System: Complete Hierarchy & Trace Documentation

**Date**: 2025-01-08
**Database**: Supabase PostgreSQL
**Project**: Unizy - Medical Summary Extraction

---

## Table of Contents

1. [System Architecture Overview](#system-architecture-overview)
2. [Database Tables & Relationships](#database-tables--relationships)
3. [Configuration Hierarchy](#configuration-hierarchy)
4. [Key Database Functions](#key-database-functions)
5. [API Flow Traces](#api-flow-traces)
6. [Real-World Example Trace](#real-world-example-trace)

---

## System Architecture Overview

### Three-Tier Configuration Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    TIER 1: ADMIN BUILDING BLOCKS                │
│  Defines: Consultation Types + Segment Definitions              │
│  Tables: consultation_types, segment_definitions,               │
│          consultation_type_segment_defaults                      │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    TIER 2: ADMIN TEMPLATES                      │
│  Defines: Reusable template configurations                      │
│  Tables: templates, template_segment_configurations             │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  TIER 3: DOCTOR CUSTOMIZATION                   │
│  Defines: Doctor-specific overrides                             │
│  Tables: doctor_active_templates, doctor_segment_configurations │
└─────────────────────────────────────────────────────────────────┘
```

---

## Database Tables & Relationships

### Primary Tables

#### 1. **consultation_types** (Admin - Tier 1)
```sql
CREATE TABLE consultation_types (
    id UUID PRIMARY KEY,
    type_code VARCHAR(50) UNIQUE NOT NULL,        -- 'OP', 'DISCHARGE', 'RESPIRATORY'
    type_name VARCHAR(255) NOT NULL,              -- 'Outpatient Consultation'
    description TEXT,
    specialty_applicable TEXT[],
    display_order INTEGER NOT NULL,
    icon_name VARCHAR(50),
    color_code VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Purpose**: Define types of medical consultations
**Example Data**:
```
OP         → Outpatient Consultation
DISCHARGE  → Discharge Summary
RESPIRATORY→ Respiratory Monitoring
```

---

#### 2. **segment_definitions** (Admin - Tier 1)
```sql
CREATE TABLE segment_definitions (
    id UUID PRIMARY KEY,
    segment_code VARCHAR(50) NOT NULL,
    segment_name VARCHAR(255) NOT NULL,

    -- Consultation type linkage
    consultation_type_id UUID REFERENCES consultation_types(id),
    is_common BOOLEAN DEFAULT FALSE,

    -- Parent tracking (for segment inheritance)
    parent_segment_code VARCHAR(50),
    is_cloned_from_parent BOOLEAN DEFAULT FALSE,
    cloned_at TIMESTAMP WITH TIME ZONE,
    diverged_from_parent BOOLEAN DEFAULT FALSE,
    last_parent_sync_at TIMESTAMP WITH TIME ZONE,

    -- Prompt and schema
    prompt_section_text TEXT NOT NULL,
    schema_definition_json JSONB NOT NULL,

    -- Default configuration
    default_category VARCHAR(20) NOT NULL DEFAULT 'core',
    is_required BOOLEAN DEFAULT FALSE,
    display_order INTEGER NOT NULL,
    default_brevity_level VARCHAR(20) DEFAULT 'balanced',
    default_terminology_style VARCHAR(20) DEFAULT 'medical_terms',

    -- Metadata
    description TEXT,
    example_output TEXT,
    segment_type VARCHAR(50),
    complexity_level VARCHAR(20),
    estimated_tokens INTEGER,

    -- Approval workflow
    status VARCHAR(20) DEFAULT 'active',
    created_by_doctor_id UUID REFERENCES doctors(id),
    approved_by_admin_id UUID REFERENCES doctors(id),
    approved_at TIMESTAMP WITH TIME ZONE,

    -- Template-specific segments
    template_id UUID REFERENCES templates(id),

    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CHECK (default_category IN ('core', 'additional', 'excluded')),
    CHECK (status IN ('draft', 'pending_approval', 'active', 'rejected')),
    UNIQUE NULLS NOT DISTINCT (segment_code, consultation_type_id)
);
```

**Purpose**: Define all segment types (building blocks for extraction)
**Three Types of Segments**:
1. **Common Segments** (`is_common=TRUE`, `consultation_type_id=NULL`)
   - Shared across ALL consultation types
   - Examples: DIAGNOSIS, PRESCRIPTION, CHIEF_COMPLAINTS

2. **Type-Specific Segments** (`is_common=FALSE`, `consultation_type_id` set)
   - Only for specific consultation type
   - Examples: DISCHARGE_CONDITION (DISCHARGE only), RESPIRATORY_RATE (RESPIRATORY only)

3. **Template-Specific Segments** (`template_id` set)
   - Only for specific template
   - Examples: Custom segments created for specialized workflows

---

#### 3. **consultation_type_segment_defaults** (Admin - Tier 1)
```sql
CREATE TABLE consultation_type_segment_defaults (
    id UUID PRIMARY KEY,
    consultation_type_id UUID NOT NULL REFERENCES consultation_types(id) ON DELETE CASCADE,
    segment_code VARCHAR(50) NOT NULL REFERENCES segment_definitions(segment_code) ON DELETE CASCADE,

    -- Type-specific defaults for common segments
    default_category VARCHAR(20) NOT NULL,
    default_display_order INTEGER NOT NULL,
    default_brevity_level VARCHAR(20) DEFAULT 'balanced',
    default_terminology_style VARCHAR(20) DEFAULT 'medical_terms',
    is_required_for_type BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(consultation_type_id, segment_code),
    CHECK (default_category IN ('core', 'additional', 'excluded'))
);
```

**Purpose**: Override default behavior of COMMON segments per consultation type
**Example**:
```
DIAGNOSIS (common segment):
  - For OP:         category=core, display_order=1
  - For DISCHARGE:  category=additional, display_order=10
  - For RESPIRATORY: category=excluded
```

---

#### 4. **templates** (Admin - Tier 2)
```sql
CREATE TABLE templates (
    id UUID PRIMARY KEY,
    template_code VARCHAR(50) UNIQUE NOT NULL,
    template_name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Consultation type linkage
    consultation_type_id UUID REFERENCES consultation_types(id) ON DELETE CASCADE,

    -- Visibility/filtering
    specialty VARCHAR(100),
    use_case VARCHAR(100),
    specialization VARCHAR(100),
    hospital_id UUID REFERENCES hospitals(id) ON DELETE SET NULL,
    created_by_doctor_id UUID REFERENCES doctors(id) ON DELETE SET NULL,

    -- Metadata
    is_default BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    estimated_extraction_time_seconds DECIMAL(10, 2),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Purpose**: Define reusable template configurations
**Visibility Rules** (from `doctor_visible_templates` view):
1. Platform-wide common (`specialization=NULL`) → All doctors
2. Specialization-specific → Doctors with matching specialization
3. Hospital-specific → Doctors in same hospital

**Example Data**:
```
OP_CORE      → consultation_type_id = OP, is_default=true
DISCHARGE_CORE → consultation_type_id = DISCHARGE
OP_CONCISE   → consultation_type_id = OP
```

---

#### 5. **template_segment_configurations** (Admin - Tier 2)
```sql
CREATE TABLE template_segment_configurations (
    id UUID PRIMARY KEY,
    template_id UUID NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    segment_code VARCHAR(50) NOT NULL REFERENCES segment_definitions(segment_code) ON DELETE CASCADE,

    -- Configuration for this segment in this template
    category VARCHAR(20) NOT NULL,
    display_order INTEGER NOT NULL,
    brevity_level VARCHAR(20) DEFAULT 'balanced',
    terminology_style VARCHAR(20) DEFAULT 'medical_terms',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(template_id, segment_code),
    CHECK (category IN ('core', 'additional', 'excluded'))
);
```

**Purpose**: Define which segments are in each template and their default settings
**Example**:
```
Template: OP_CORE
  DIAGNOSIS           → category=core, display_order=1
  CHIEF_COMPLAINTS    → category=core, display_order=2
  HISTORY             → category=additional, display_order=10
  PHYSICAL_EXAMINATION → category=excluded
```

---

#### 6. **doctor_active_templates** (Doctor - Tier 3)
```sql
CREATE TABLE doctor_active_templates (
    id UUID PRIMARY KEY,                          -- Activation ID (unique instance)
    doctor_id UUID NOT NULL,
    template_id UUID NOT NULL REFERENCES templates(id) ON DELETE CASCADE,

    -- Custom name (REQUIRED, UNIQUE per doctor)
    template_name_override TEXT NOT NULL,

    -- Customization tracking
    has_custom_overrides BOOLEAN DEFAULT FALSE,
    activated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT doctor_active_templates_doctor_name_unique
        UNIQUE(doctor_id, template_name_override),
    CONSTRAINT doctor_active_templates_name_not_empty
        CHECK (length(trim(template_name_override)) > 0)
);
```

**Purpose**: Track doctor's activated template instances
**Key Features**:
- **Multiple activations**: Same template can be activated multiple times with different names
- **template_name_override**: Doctor's custom name (REQUIRED, NOT NULL)
- **Unique per doctor**: Same doctor can't have two templates with same custom name

**Example Data** (from live database):
```
Doctor: Prakash (83b3eb65-6801-4bc5-b565-dd3dee2be70a)
  Activation 1: template_id=DISCHARGE_CORE → "Prakash_Full Discharge Template"
  Activation 2: template_id=OP_CORE       → "Prakash_Outpatient full"
  Activation 3: template_id=OP_CORE       → "Prakash_OP concise" (same template, different name!)
```

---

#### 7. **doctor_segment_configurations** (Doctor - Tier 3)
```sql
CREATE TABLE doctor_segment_configurations (
    id UUID PRIMARY KEY,
    doctor_id UUID NOT NULL,
    segment_code VARCHAR(50) NOT NULL REFERENCES segment_definitions(segment_code) ON DELETE CASCADE,

    -- Template-specific OR global
    active_template_id UUID REFERENCES doctor_active_templates(id) ON DELETE CASCADE,

    -- Doctor's custom configuration
    category VARCHAR(20) NOT NULL,
    display_order INTEGER NOT NULL,
    brevity_level VARCHAR(20) DEFAULT 'balanced',
    terminology_style VARCHAR(20) DEFAULT 'medical_terms',

    -- Advanced overrides (optional)
    custom_prompt_section TEXT,
    custom_schema_json JSONB,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT doctor_segment_configurations_unique
        UNIQUE(doctor_id, segment_code, active_template_id),
    CHECK (category IN ('core', 'additional', 'excluded'))
);
```

**Purpose**: Store doctor's custom segment settings
**Two Scopes**:
1. **Global** (`active_template_id=NULL`)
   - Applies to ALL templates for this doctor
   - Example: "I always want DIAGNOSIS as 'detailed'"

2. **Template-Specific** (`active_template_id` set)
   - Only for specific activated template instance
   - Example: "For my 'Quick OP' template, DIAGNOSIS should be 'excluded'"

**Example Data** (from live database):
```
Doctor: Prakash, Template: "Prakash_Full Discharge Template" (activation_id=1c92f6a7...)
  DIAGNOSIS           → category=excluded
  CHIEF_COMPLAINTS    → category=excluded, brevity_level=concise
  HISTORY             → category=excluded
  DIAGNOSIS_DISCHARGE → category=core
```

---

## Configuration Hierarchy

### Resolution Order (Highest to Lowest Priority)

The system uses **COALESCE** in SQL to resolve configuration in this exact order:

```sql
COALESCE(
    dsc.category,                    -- 1. Doctor's template-specific config
    tsc.category,                    -- 2. Template default
    ctsd.default_category,           -- 3. Consultation type default
    sd.default_category              -- 4. Segment definition default
)
```

### Detailed Hierarchy Breakdown

#### **Priority 1: Doctor's Template-Specific Configuration**
- **Table**: `doctor_segment_configurations`
- **Condition**: `doctor_id` matches AND `active_template_id` matches
- **Example**: "In my 'Quick OP' template, exclude HISTORY"

#### **Priority 2: Template Default Configuration**
- **Table**: `template_segment_configurations`
- **Condition**: `template_id` matches (derived from `doctor_active_templates`)
- **Example**: "OP_CORE template has HISTORY in ADDITIONAL by default"

#### **Priority 3: Consultation Type Default**
- **Table**: `consultation_type_segment_defaults`
- **Condition**: `consultation_type_id` matches AND `segment_code` matches
- **Example**: "For OP consultations, DIAGNOSIS is CORE by default"

#### **Priority 4: Segment Definition Default**
- **Table**: `segment_definitions`
- **Condition**: Always available (fallback)
- **Example**: "DIAGNOSIS segment has default_category='core'"

---

## Key Database Functions

### 1. **get_doctor_segment_configuration()**

**Function Signature**:
```sql
CREATE OR REPLACE FUNCTION get_doctor_segment_configuration(
    p_doctor_id UUID,
    p_consultation_type_id UUID,
    p_active_template_id UUID DEFAULT NULL,
    p_mode VARCHAR DEFAULT 'full'
)
RETURNS TABLE (
    segment_code VARCHAR,
    segment_name VARCHAR,
    prompt_section_text TEXT,
    schema_definition_json JSONB,
    category VARCHAR,
    display_order INTEGER,
    brevity_level VARCHAR,
    terminology_style VARCHAR,
    is_required BOOLEAN
)
```

**Purpose**: Resolve final segment configuration with complete hierarchy

**Detailed Flow**:

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Load Segment Definitions                               │
│ FROM segment_definitions sd                                     │
│ WHERE sd.is_active = TRUE                                       │
│   AND (sd.is_common = TRUE OR sd.consultation_type_id = p_...)  │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Join Doctor Active Template (if p_active_template_id)  │
│ LEFT JOIN doctor_active_templates dat                           │
│   ON dat.id = p_active_template_id                              │
│ Purpose: Get master template_id from activation                 │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Join Doctor Segment Configurations (template-specific)  │
│ LEFT JOIN doctor_segment_configurations dsc                     │
│   ON dsc.segment_code = sd.segment_code                         │
│   AND dsc.doctor_id = p_doctor_id                               │
│   AND dsc.active_template_id = p_active_template_id             │
│ Purpose: Get doctor's custom overrides for THIS template        │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Join Template Segment Configurations                   │
│ LEFT JOIN template_segment_configurations tsc                   │
│   ON tsc.segment_code = sd.segment_code                         │
│   AND tsc.template_id = dat.template_id                         │
│ Purpose: Get template defaults                                  │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Join Consultation Type Segment Defaults (optional)     │
│ LEFT JOIN consultation_type_segment_defaults ctsd               │
│   ON ctsd.segment_code = sd.segment_code                        │
│   AND ctsd.consultation_type_id = p_consultation_type_id        │
│ Purpose: Get consultation type defaults for common segments     │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 6: Apply COALESCE Hierarchy                               │
│ SELECT                                                          │
│   COALESCE(dsc.category, tsc.category, ctsd.default_category,  │
│            sd.default_category) AS category,                    │
│   COALESCE(dsc.brevity_level, tsc.brevity_level,               │
│            sd.default_brevity_level) AS brevity_level,          │
│   ...                                                           │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 7: Filter by Mode                                         │
│ WHERE p_mode = 'full'                                           │
│    OR (p_mode = 'core' AND resolved_category = 'core')         │
│    OR (p_mode = 'additional' AND resolved_category = 'add...')  │
│ AND resolved_category != 'excluded'  ← ALWAYS exclude          │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 8: Return Ordered Results                                 │
│ ORDER BY COALESCE(dsc.display_order, tsc.display_order,        │
│                   sd.display_order)                             │
└─────────────────────────────────────────────────────────────────┘
```

**Why consultation_type_id is Required**:

1. **Filter Common Segments**: Need to know which consultation type to include common segments for
   ```sql
   WHERE (sd.is_common = TRUE OR sd.consultation_type_id = p_consultation_type_id)
   ```

2. **Join Consultation Type Defaults**: Need to apply type-specific defaults
   ```sql
   LEFT JOIN consultation_type_segment_defaults ctsd
     ON ctsd.consultation_type_id = p_consultation_type_id
   ```

3. **Segment Visibility**: Common segments (DIAGNOSIS, PRESCRIPTION) appear for ALL types, but type-specific segments (DISCHARGE_CONDITION) only appear for their type

**Could consultation_type_id be derived from active_template_id?**

**Yes, technically possible but NOT RECOMMENDED** because:
- Would require additional JOIN: `doctor_active_templates → templates → consultation_type_id`
- Function signature would change (breaking change)
- Would prevent calling function without template (global preferences)
- Performance impact (extra JOIN)
- Less explicit (harder to debug)

---

### 2. **apply_template_to_doctor()**

**Function Signature**:
```sql
CREATE OR REPLACE FUNCTION apply_template_to_doctor(
    p_doctor_id UUID,
    p_template_id UUID,
    p_active_template_id UUID
)
RETURNS VOID
```

**Purpose**: Copy template segment configurations to doctor's configuration

**Detailed Flow**:

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Delete Existing Doctor Configurations                  │
│ DELETE FROM doctor_segment_configurations                       │
│ WHERE doctor_id = p_doctor_id                                   │
│   AND active_template_id = p_active_template_id                 │
│ Purpose: Clean slate for this template activation               │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Copy Template Configurations                           │
│ INSERT INTO doctor_segment_configurations                       │
│   (doctor_id, active_template_id, segment_code, category,       │
│    display_order, brevity_level, terminology_style)             │
│ SELECT                                                          │
│   p_doctor_id,                                                  │
│   p_active_template_id,                                         │
│   tsc.segment_code,                                             │
│   tsc.category,                                                 │
│   tsc.display_order,                                            │
│   tsc.brevity_level,                                            │
│   tsc.terminology_style                                         │
│ FROM template_segment_configurations tsc                        │
│ WHERE tsc.template_id = p_template_id                           │
└─────────────────────────────────────────────────────────────────┘
```

**When Called**:
- When doctor activates a template via API: `POST /api/v1/summary/templates/{type_code}/activate/{template_code}`
- Creates initial doctor customizations based on template defaults
- Doctor can then modify these via drag-and-drop UI

---

### 3. **get_active_template_id_by_name()**

**Function Signature**:
```sql
CREATE OR REPLACE FUNCTION get_active_template_id_by_name(
    p_doctor_id UUID,
    p_template_name_override TEXT
)
RETURNS UUID
```

**Purpose**: Lookup activation ID by doctor's custom template name

**Flow**:
```sql
SELECT id
FROM doctor_active_templates
WHERE doctor_id = p_doctor_id
  AND template_name_override = p_template_name_override
LIMIT 1;
```

**Why Needed**:
- Frontend passes `template_name` (the custom name) in APIs
- Backend needs `active_template_id` (UUID) for database operations
- Maps: "Prakash_Full Discharge Template" → `1c92f6a7-76ba-4fba-96ba-c0f8759438db`

---

### 4. **get_default_active_template_id()**

**Function Signature**:
```sql
CREATE OR REPLACE FUNCTION get_default_active_template_id(
    p_doctor_id UUID,
    p_consultation_type_id UUID
)
RETURNS UUID
```

**Purpose**: Auto-activate default template if doctor hasn't activated any

**Detailed Flow**:

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Check if doctor has default template already activated │
│ SELECT dat.id                                                   │
│ FROM doctor_active_templates dat                                │
│ JOIN templates t ON t.id = dat.template_id                      │
│ WHERE dat.doctor_id = p_doctor_id                               │
│   AND t.consultation_type_id = p_consultation_type_id           │
│   AND t.is_default = TRUE                                       │
│ If found → Return existing activation ID                        │
└─────────────────────────────────────────────────────────────────┘
                              ▼ (if not found)
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Find default template for consultation type            │
│ SELECT id, template_name                                        │
│ FROM templates                                                  │
│ WHERE consultation_type_id = p_consultation_type_id             │
│   AND is_default = TRUE                                         │
│   AND is_active = TRUE                                          │
│ If not found → Return NULL                                      │
└─────────────────────────────────────────────────────────────────┘
                              ▼ (if found)
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Auto-activate default template                         │
│ INSERT INTO doctor_active_templates                             │
│   (doctor_id, template_id, template_name_override,              │
│    has_custom_overrides)                                        │
│ VALUES                                                          │
│   (p_doctor_id, v_default_template_id,                          │
│    'Default Template (Auto-Activated)', FALSE)                  │
│ ON CONFLICT (doctor_id, template_name_override) DO UPDATE       │
│ RETURNING id                                                    │
└─────────────────────────────────────────────────────────────────┘
```

**Use Case**: First-time doctor login → Auto-activate OP_CORE template

---

## API Flow Traces

### API 1: Template Activation

**Endpoint**: `POST /api/v1/summary/templates/{consultation_type_code}/activate/{template_code}?doctor_id={doctor_id}`
**Request Body**: `{ "custom_name": "My Custom Template Name" }`

#### Full Trace:

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. API Request Received                                        │
│ URL: /api/v1/summary/templates/OP/activate/OP_CORE             │
│ Query: doctor_id=83b3eb65-6801-4bc5-b565-dd3dee2be70a           │
│ Body: { "custom_name": "Prakash_Quick OP" }                    │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Backend: summary.py → activate_template_endpoint()          │
│ Line 727-799                                                    │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Get Consultation Type                                       │
│ consultation_type = get_consultation_type_by_code('OP')         │
│ Returns: { id: '6af5251b...', type_code: 'OP', ... }           │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Get Template                                                │
│ template = get_template_by_code('OP_CORE')                      │
│ Returns: { id: 'abc123...', template_code: 'OP_CORE', ... }    │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Normalize Doctor ID                                         │
│ doctor_uuid = normalize_doctor_id(doctor_id)                    │
│ Converts string to UUID                                         │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Apply Template (supabase_service.py)                        │
│ active_template = apply_template(                               │
│     doctor_id=doctor_uuid,                                      │
│     template_id=template_id,                                    │
│     custom_name="Prakash_Quick OP"                              │
│ )                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. Check Name Availability                                     │
│ available = check_template_name_available(doctor_uuid, name)    │
│ Query: SELECT COUNT(*) FROM doctor_active_templates            │
│        WHERE doctor_id = doctor_uuid                            │
│          AND template_name_override = "Prakash_Quick OP"        │
│ If count > 0 → Raise ValueError("Name already exists")         │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 8. Insert into doctor_active_templates                         │
│ INSERT INTO doctor_active_templates                             │
│   (doctor_id, template_id, template_name_override,              │
│    has_custom_overrides)                                        │
│ VALUES                                                          │
│   ('83b3eb65...', 'abc123...', 'Prakash_Quick OP', FALSE)       │
│ RETURNING *                                                     │
│                                                                 │
│ Returns: { id: 'xyz789...', ... }  ← NEW activation_id         │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 9. Call Database Function: apply_template_to_doctor()          │
│ SELECT apply_template_to_doctor(                                │
│     '83b3eb65...',  -- doctor_id                                │
│     'abc123...',    -- template_id (master)                     │
│     'xyz789...'     -- active_template_id (new activation)      │
│ )                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 10. Database Function Executes                                 │
│ a) DELETE FROM doctor_segment_configurations                    │
│    WHERE doctor_id='83b3eb65...'                                │
│      AND active_template_id='xyz789...'                         │
│                                                                 │
│ b) INSERT INTO doctor_segment_configurations                    │
│    SELECT '83b3eb65...', 'xyz789...', segment_code, ...         │
│    FROM template_segment_configurations                         │
│    WHERE template_id='abc123...'                                │
│                                                                 │
│ Result: Copies 18 segment configs from template to doctor      │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 11. Return Response to Frontend                                │
│ {                                                               │
│   "success": true,                                              │
│   "message": "Template 'Prakash_Quick OP' activated for OP",   │
│   "template": { template_code: "OP_CORE", ... },                │
│   "active_template": {                                          │
│     id: "xyz789...",                                            │
│     template_name_override: "Prakash_Quick OP",                 │
│     has_custom_overrides: false                                 │
│   }                                                             │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
```

**Key Points**:
- ✅ `consultation_type_code` required in URL (cannot derive from template alone in activation flow)
- ✅ Creates unique activation ID (`doctor_active_templates.id`)
- ✅ Copies template segments to `doctor_segment_configurations` with `active_template_id` set
- ✅ Doctor can now customize THIS specific activation independently

---

### API 2: Move Segment (Doctor Customization)

**Endpoint**: `POST /api/v1/summary/segments/move?doctor_id={doctor_id}&template_name={template_name}`
**Request Body**: `{ "segment_code": "DIAGNOSIS", "new_category": "excluded" }`

#### Full Trace:

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. API Request Received                                        │
│ URL: /api/v1/summary/segments/move                             │
│ Query: doctor_id=83b3eb65..., template_name="Prakash_Quick OP"  │
│ Body: { segment_code: "DIAGNOSIS", new_category: "excluded" }  │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Backend: summary.py → move_segment()                        │
│ Line 550-599                                                    │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Normalize Doctor ID                                         │
│ doctor_uuid = normalize_doctor_id(doctor_id)                    │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Lookup active_template_id by Name                           │
│ active_template_id = get_active_template_id_by_name(           │
│     doctor_uuid,                                                │
│     "Prakash_Quick OP"                                          │
│ )                                                               │
│                                                                 │
│ Query: SELECT id FROM doctor_active_templates                   │
│        WHERE doctor_id='83b3eb65...'                            │
│          AND template_name_override='Prakash_Quick OP'          │
│                                                                 │
│ Returns: 'xyz789...'  ← active_template_id                     │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Update Doctor Segment Configuration                         │
│ result = update_doctor_segment_config(                          │
│     doctor_id=doctor_uuid,                                      │
│     segment_code="DIAGNOSIS",                                   │
│     template_name="Prakash_Quick OP",                           │
│     category="excluded"                                         │
│ )                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Inside update_doctor_segment_config()                       │
│ a) Lookup active_template_id again (internal)                   │
│    active_template_id = get_active_template_id_by_name(...)     │
│                                                                 │
│ b) Check if record exists                                       │
│    SELECT * FROM doctor_segment_configurations                  │
│    WHERE doctor_id='83b3eb65...'                                │
│      AND segment_code='DIAGNOSIS'                               │
│      AND active_template_id='xyz789...'                         │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. UPDATE or INSERT                                            │
│ If exists:                                                      │
│   UPDATE doctor_segment_configurations                          │
│   SET category='excluded', updated_at=NOW()                     │
│   WHERE doctor_id='83b3eb65...'                                 │
│     AND segment_code='DIAGNOSIS'                                │
│     AND active_template_id='xyz789...'                          │
│                                                                 │
│ If not exists:                                                  │
│   INSERT INTO doctor_segment_configurations                     │
│   (doctor_id, segment_code, active_template_id,                 │
│    category, display_order, brevity_level, ...)                 │
│   VALUES ('83b3eb65...', 'DIAGNOSIS', 'xyz789...',              │
│           'excluded', ...)                                      │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 8. Update has_custom_overrides Flag                            │
│ UPDATE doctor_active_templates                                  │
│ SET has_custom_overrides=TRUE, updated_at=NOW()                 │
│ WHERE id='xyz789...'                                            │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 9. Return Response                                             │
│ {                                                               │
│   "success": true,                                              │
│   "message": "Segment 'DIAGNOSIS' moved to EXCLUDED             │
│                (template 'Prakash_Quick OP')",                  │
│   "configuration": { segment_code: "DIAGNOSIS", ... }           │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
```

**Key Points**:
- ✅ `template_name` (custom name) passed in query parameter
- ✅ Backend maps `template_name` → `active_template_id` using `get_active_template_id_by_name()`
- ✅ Stores customization in `doctor_segment_configurations` with `active_template_id` set
- ✅ Marks `has_custom_overrides=TRUE` in `doctor_active_templates`

---

### API 3: Get Segments (for Display)

**Endpoint**: `GET /api/v1/summary/segments/{consultation_type_code}?doctor_id={doctor_id}&template_name={template_name}&mode=full`

#### Full Trace:

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. API Request Received                                        │
│ URL: /api/v1/summary/segments/OP                               │
│ Query: doctor_id=83b3eb65..., template_name="Prakash_Quick OP", │
│        mode=full                                                │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Backend: summary.py → get_segments()                        │
│ Line 432-499                                                    │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Get Consultation Type                                       │
│ consultation_type = get_consultation_type_by_code('OP')         │
│ Returns: { id: '6af5251b...', type_code: 'OP', ... }           │
│ consultation_type_id = UUID('6af5251b...')                      │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Normalize Doctor ID                                         │
│ doctor_uuid = normalize_doctor_id(doctor_id)                    │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Get Segment Definitions (supabase_service.py)               │
│ segments = get_segment_definitions(                             │
│     consultation_type_id='6af5251b...',                         │
│     doctor_id=doctor_uuid,                                      │
│     template_name="Prakash_Quick OP",                           │
│     mode='full'                                                 │
│ )                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Inside get_segment_definitions()                            │
│ a) Lookup active_template_id by name                            │
│    active_template_id = get_active_template_id_by_name(         │
│        doctor_uuid, "Prakash_Quick OP"                          │
│    )                                                            │
│    Returns: 'xyz789...'                                         │
│                                                                 │
│ b) Call Database Function                                       │
│    segments = supabase.rpc(                                     │
│        'get_doctor_segment_configuration',                      │
│        {                                                        │
│            'p_doctor_id': str(doctor_uuid),                     │
│            'p_consultation_type_id': str(consultation_type_id), │
│            'p_active_template_id': str(active_template_id),     │
│            'p_mode': 'full'                                     │
│        }                                                        │
│    ).execute()                                                  │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. Database Function Executes (see detailed flow in section 1) │
│ Returns array of segments with resolved configuration:          │
│ [                                                               │
│   {                                                             │
│     segment_code: "CHIEF_COMPLAINTS",                           │
│     segment_name: "Chief Complaints",                           │
│     category: "core",        ← from template default            │
│     brevity_level: "balanced", ← from template default          │
│     display_order: 2,                                           │
│     prompt_section_text: "...",                                 │
│     schema_definition_json: {...}                               │
│   },                                                            │
│   {                                                             │
│     segment_code: "DIAGNOSIS",                                  │
│     category: "excluded",    ← from doctor's override!          │
│     ...                                                         │
│   },                                                            │
│   ...                                                           │
│ ]                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 8. Return Response to Frontend                                 │
│ {                                                               │
│   "success": true,                                              │
│   "consultation_type_code": "OP",                               │
│   "consultation_type_name": "Outpatient Consultation",          │
│   "mode": "full",                                               │
│   "segments": [ ... ],  ← 18 segments with configs             │
│   "count": 18                                                   │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
```

**Key Points**:
- ✅ `consultation_type_code` required in URL path (OP, DISCHARGE, RESPIRATORY)
- ✅ `template_name` optional in query (if provided, gets template-specific config)
- ✅ Backend maps `template_name` → `active_template_id`
- ✅ Calls `get_doctor_segment_configuration()` with both `consultation_type_id` AND `active_template_id`
- ✅ Returns segments with complete hierarchy resolution

---

## Real-World Example Trace

### Scenario: Dr. Prakash Customizes Discharge Template

**Initial State**:
- Template: `DISCHARGE_CORE` (id: `abc123...`)
- Doctor: Prakash (`83b3eb65-6801-4bc5-b565-dd3dee2be70a`)
- Action: Activate template and customize segments

---

#### Step 1: Activate Template

**Request**:
```http
POST /api/v1/summary/templates/DISCHARGE/activate/DISCHARGE_CORE?doctor_id=83b3eb65-6801-4bc5-b565-dd3dee2be70a
{
  "custom_name": "Prakash_Full Discharge Template"
}
```

**Database Changes**:
```sql
-- 1. Insert into doctor_active_templates
INSERT INTO doctor_active_templates
  (id, doctor_id, template_id, template_name_override, has_custom_overrides)
VALUES
  ('1c92f6a7-76ba-4fba-96ba-c0f8759438db',
   '83b3eb65-6801-4bc5-b565-dd3dee2be70a',
   'abc123...',  -- DISCHARGE_CORE template_id
   'Prakash_Full Discharge Template',
   FALSE);

-- 2. Copy template segments (via apply_template_to_doctor)
INSERT INTO doctor_segment_configurations
  (doctor_id, active_template_id, segment_code, category, display_order, ...)
SELECT
  '83b3eb65-6801-4bc5-b565-dd3dee2be70a',
  '1c92f6a7-76ba-4fba-96ba-c0f8759438db',
  segment_code,
  category,
  display_order,
  ...
FROM template_segment_configurations
WHERE template_id = 'abc123...';

-- Result: 12 discharge segments copied
```

---

#### Step 2: Move DIAGNOSIS to Excluded

**Request**:
```http
POST /api/v1/summary/segments/move?doctor_id=83b3eb65-6801-4bc5-b565-dd3dee2be70a&template_name=Prakash_Full%20Discharge%20Template
{
  "segment_code": "DIAGNOSIS",
  "new_category": "excluded"
}
```

**Database Changes**:
```sql
-- 1. Lookup active_template_id
SELECT id FROM doctor_active_templates
WHERE doctor_id = '83b3eb65-6801-4bc5-b565-dd3dee2be70a'
  AND template_name_override = 'Prakash_Full Discharge Template';
-- Returns: '1c92f6a7-76ba-4fba-96ba-c0f8759438db'

-- 2. Update segment configuration
UPDATE doctor_segment_configurations
SET category = 'excluded', updated_at = NOW()
WHERE doctor_id = '83b3eb65-6801-4bc5-b565-dd3dee2be70a'
  AND segment_code = 'DIAGNOSIS'
  AND active_template_id = '1c92f6a7-76ba-4fba-96ba-c0f8759438db';

-- 3. Mark template as customized
UPDATE doctor_active_templates
SET has_custom_overrides = TRUE, updated_at = NOW()
WHERE id = '1c92f6a7-76ba-4fba-96ba-c0f8759438db';
```

---

#### Step 3: Change CHIEF_COMPLAINTS to Concise

**Request**:
```http
PUT /api/v1/summary/segments/CHIEF_COMPLAINTS?doctor_id=83b3eb65-6801-4bc5-b565-dd3dee2be70a&template_name=Prakash_Full%20Discharge%20Template
{
  "brevity_level": "concise"
}
```

**Database Changes**:
```sql
UPDATE doctor_segment_configurations
SET brevity_level = 'concise', updated_at = NOW()
WHERE doctor_id = '83b3eb65-6801-4bc5-b565-dd3dee2be70a'
  AND segment_code = 'CHIEF_COMPLAINTS'
  AND active_template_id = '1c92f6a7-76ba-4fba-96ba-c0f8759438db';
```

---

#### Step 4: Extract Medical Summary

**Request**:
```http
POST /api/v1/summary/extract
{
  "transcript": "Patient discharged after 3 days...",
  "doctor_id": "83b3eb65-6801-4bc5-b565-dd3dee2be70a",
  "template_name": "Prakash_Full Discharge Template",
  "mode": "full",
  "processing_mode": "default"
}
```

**Configuration Resolution**:

```sql
-- Call: get_doctor_segment_configuration(
--   p_doctor_id = '83b3eb65...',
--   p_consultation_type_id = 'fd38af66...',  -- DISCHARGE
--   p_active_template_id = '1c92f6a7...',
--   p_mode = 'full'
-- )

-- For DIAGNOSIS segment:
SELECT
  'DIAGNOSIS' AS segment_code,
  COALESCE(
    dsc.category,          -- 'excluded' (doctor's override)
    tsc.category,          -- 'core' (template default)
    sd.default_category    -- 'core' (segment default)
  ) AS category
FROM segment_definitions sd
LEFT JOIN doctor_segment_configurations dsc
  ON dsc.segment_code = 'DIAGNOSIS'
  AND dsc.active_template_id = '1c92f6a7...'
LEFT JOIN template_segment_configurations tsc
  ON tsc.segment_code = 'DIAGNOSIS'
  AND tsc.template_id = 'abc123...'
WHERE sd.segment_code = 'DIAGNOSIS';

-- Result: category = 'excluded' (from doctor's customization)
-- This segment will NOT be extracted!

-- For CHIEF_COMPLAINTS segment:
-- Result: category = 'core', brevity_level = 'concise'
-- This segment WILL be extracted with concise verbosity
```

**Final Extraction**:
- ❌ DIAGNOSIS excluded (doctor moved to excluded)
- ✅ CHIEF_COMPLAINTS extracted (concise brevity from doctor's override)
- ✅ DIAGNOSIS_DISCHARGE extracted (discharge-specific segment, core category)
- ✅ 10 other segments extracted with their configured settings

---

## Summary: Why consultation_type_id is Required

### Technical Reasons:

1. **Segment Filtering**:
   ```sql
   WHERE (sd.is_common = TRUE OR sd.consultation_type_id = p_consultation_type_id)
   ```
   - Need to know WHICH consultation type to filter segments for
   - Common segments (DIAGNOSIS) appear for ALL types
   - Type-specific segments (DISCHARGE_CONDITION) only for their type

2. **Type-Specific Defaults**:
   ```sql
   LEFT JOIN consultation_type_segment_defaults ctsd
     ON ctsd.consultation_type_id = p_consultation_type_id
   ```
   - Common segment DIAGNOSIS may have different defaults for OP vs DISCHARGE
   - Need consultation_type_id to apply correct defaults

3. **Performance**:
   - Deriving from `active_template_id` requires extra JOIN chain
   - Current approach is more direct and efficient

4. **API Design**:
   - Explicit parameters are clearer than implicit derivation
   - Easier to debug and maintain
   - Prevents errors when template references are broken

### Why template_name vs template_name_override:

**In APIs**:
- **Frontend passes**: `template_name` (query parameter)
- **Backend interprets**: `template_name` = `template_name_override` (the doctor's custom name)
- **Database stores**: `template_name_override` (actual column name in `doctor_active_templates`)

**Mapping**:
```
API Parameter         Database Column           Example Value
--------------        ----------------          -----------------------
template_name    →    template_name_override    "Prakash_Full Discharge Template"
```

**Why this design**:
- Frontend uses generic "template_name" (user-friendly)
- Backend knows it's an override/custom name (implementation detail)
- Database explicitly tracks it's an override of original template name
- Allows system to preserve original template name while showing custom name

---

## End of Document

**Last Updated**: 2025-01-08
**Verified Against**: Live Supabase Database (xyhzvokuxzwcmdefbhcn.supabase.co)

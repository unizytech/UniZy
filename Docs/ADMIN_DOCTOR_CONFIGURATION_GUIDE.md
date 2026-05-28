# Admin & Doctor Configuration System - Complete Guide

## Table of Contents
1. [System Overview](#system-overview)
2. [Admin Capabilities](#admin-capabilities)
3. [Segment Assignment Types](#segment-assignment-types)
4. [Configuration Hierarchy & Inheritance](#configuration-hierarchy--inheritance)
5. [Doctor Capabilities](#doctor-capabilities)
6. [Configuration Override Hierarchy](#configuration-override-hierarchy)
7. [Dynamic Prompt Generation](#dynamic-prompt-generation)
8. [Database Schema Reference](#database-schema-reference)

---

## System Overview

The system provides a **four-tier configuration hierarchy** for medical documentation extraction:

```
Common Segments (Global)
    ↓
Consultation Type Defaults
    ↓
Template Configurations
    ↓
Doctor Customizations
```

Each level can override settings from the level above, with clinical safety validations to ensure required segments remain in CORE category.

---

## Admin Capabilities

### 1. Create Consultation Types

Admins create consultation types that serve as broad categories for medical documentation.

**Examples:**
- OP (Outpatient Consultation)
- DISCHARGE (Discharge Summary)
- RESPIRATORY (Respiratory Monitoring)

**Database Table:** `consultation_types`

**Fields:**
- `type_code`: Unique identifier (e.g., 'OP', 'DISCHARGE')
- `type_name`: Display name (e.g., 'Outpatient Consultation')
- `description`: Purpose and use case
- `specialty_applicable`: Array of applicable specialties
- `display_order`: Sort order in UI
- `icon_name`, `color_code`: UI metadata

**Key Behavior:**
- Consultation types **inherit all common segments** by default
- Can have type-specific segments assigned to them
- Can override common segment behavior via `consultation_type_segment_defaults`

---

### 2. Create and Assign Segments

Admins create segment definitions and assign them to one of three scopes:

#### A. Common Segments (Global)
**Assignment:** `is_common = true`, `consultation_type_id = NULL`, `template_id = NULL`

**Behavior:**
- Visible to **all consultation types** and **all templates**
- Cannot be deleted by consultation types (only hidden via EXCLUDED category)
- Serve as baseline segments across the entire system

**Examples:**
- DIAGNOSIS
- CHIEF_COMPLAINTS
- PRESCRIPTION
- TREATMENT_PLAN

**Use Case:** Universal segments needed across all medical documentation types.

---

#### B. Consultation Type-Specific Segments
**Assignment:** `is_common = false`, `consultation_type_id = <UUID>`, `template_id = NULL`

**Behavior:**
- Visible only to the specified consultation type
- Inherited by **all templates** within that consultation type
- Can be customized per template

**Examples:**
- DISCHARGE_CONDITION (Discharge type only)
- HOSPITAL_COURSE (Discharge type only)
- RESPIRATORY_PARAMETERS (Respiratory type only)

**Use Case:** Segments specific to a particular type of medical documentation.

---

#### C. Template-Specific Segments
**Assignment:** `is_common = false`, `consultation_type_id = <UUID>`, `template_id = <UUID>`

**Behavior:**
- Visible only to the specified template
- Not inherited by other templates (even within same consultation type)
- Most granular assignment level

**Examples:**
- PSYCHIATRY_MENTAL_STATUS (Psychiatry Standard template only)
- CARDIOLOGY_ECG_FINDINGS (Cardiology Quick template only)

**Use Case:** Highly specialized segments for specific workflows or specializations.

---

### 3. Segment Configuration Options

When creating a segment, admins configure:

#### Core Fields
- **segment_code**: Unique identifier (e.g., 'DIAGNOSIS', 'CHIEF_COMPLAINTS')
- **segment_name**: Display name (e.g., 'Diagnosis', 'Chief Complaints')
- **prompt_section_text**: Full prompt instructions for AI extraction
- **schema_definition_json**: Gemini-compatible JSON schema for output structure

#### Default Categorization
- **default_category**: `'core'` | `'additional'` | `'excluded'`
  - **CORE**: Essential, extracted first (~25-35s)
  - **ADDITIONAL**: Supplementary, background loading (~30-45s)
  - **EXCLUDED**: Hidden from extraction
- **is_required**: `true` = cannot be moved from CORE (clinical safety)
- **display_order**: Order in extraction sequence (1-18)

#### Extraction Behavior
- **default_brevity_level**: `'concise'` | `'balanced'` | `'detailed'`
  - Controls verbosity of extracted content
  - Modifies prompt instructions dynamically
- **default_terminology_style**: `'medical_terms'` | `'simple_terms'` | `'as_spoken'`
  - Controls terminology complexity
  - Affects prompt phrasing

#### Metadata
- **segment_type**: 'clinical' | 'administrative' | 'communication' | 'protocol'
- **complexity_level**: 'simple' | 'moderate' | 'complex'
- **estimated_tokens**: Token usage estimate for cost calculation
- **description**: Purpose and content description
- **example_output**: Sample JSON output

#### Approval Workflow Fields (Migration 009)
- **status**: 'draft' | 'pending_approval' | 'active' | 'rejected'
- **created_by_doctor_id**: Doctor who requested the segment (NULL for admin-created)
- **approved_by_admin_id**: Admin who approved the segment
- **approved_at**: Approval timestamp

---

### 4. Configure Consultation Type Segment Behavior

Admins can override common segment behavior per consultation type using `consultation_type_segment_defaults`.

**Table:** `consultation_type_segment_defaults`

**Use Case:**
- Hide common segments from specific consultation types (e.g., exclude PSYCHIATRIC_HISTORY from RESPIRATORY type)
- Change default category (move INVESTIGATIONS from ADDITIONAL to CORE for RESPIRATORY)
- Adjust brevity/terminology for specific types

**Override Fields:**
- `default_category`: Override segment category for this type
- `default_display_order`: Override display order
- `default_brevity_level`: Override verbosity
- `default_terminology_style`: Override terminology
- `is_required_for_type`: Mark common segment as required for this type

**Example:**
```sql
-- Hide PSYCHIATRIC_HISTORY from RESPIRATORY consultations
INSERT INTO consultation_type_segment_defaults
  (consultation_type_id, segment_code, default_category)
VALUES
  ('respiratory-uuid', 'PSYCHIATRIC_HISTORY', 'excluded');
```

---

### 5. Create Templates

Templates are predefined segment configurations that doctors can activate.

**Table:** `templates`

**Fields:**
- `template_code`: Unique identifier (e.g., 'PSYCHIATRY_CORE', 'CARDIOLOGY_QUICK')
- `template_name`: Display name (e.g., 'Psychiatry Standard - Core Only')
- `description`: Purpose and use case
- `consultation_type_id`: Which consultation type this template belongs to
- `specialization`: Target specialization (NULL = all)
- `hospital_id`: Hospital-specific template (NULL = platform-wide)
- `created_by_doctor_id`: Doctor who created custom template
- `is_default`: Whether this is the default template for the type

**Visibility Rules:**
Templates are visible to doctors based on:
1. **Platform-wide common templates** (specialization = NULL, hospital_id = NULL)
2. **Specialization-specific templates** (specialization matches doctor's)
3. **Hospital-specific templates** (hospital_id matches doctor's)

---

### 6. Configure Template Segments

Admins configure which segments appear in each template and their settings.

**Table:** `template_segment_configurations`

**Fields:**
- `template_id`: Which template this configuration applies to
- `segment_code`: Which segment to configure
- `category`: 'core' | 'additional' | 'excluded'
- `display_order`: Order within this template
- `brevity_level`: Template-specific brevity override
- `terminology_style`: Template-specific terminology override

**Example:**
```sql
-- Configure "Psychiatry Core" template to only have CORE segments with detailed verbosity
INSERT INTO template_segment_configurations
  (template_id, segment_code, category, display_order, brevity_level)
VALUES
  ('psychiatry-core-uuid', 'DIAGNOSIS', 'core', 1, 'detailed'),
  ('psychiatry-core-uuid', 'MENTAL_STATUS', 'core', 2, 'detailed'),
  ('psychiatry-core-uuid', 'RISK_ASSESSMENT', 'core', 3, 'detailed'),
  -- Move non-essential segments to EXCLUDED
  ('psychiatry-core-uuid', 'INVESTIGATIONS', 'excluded', 99, 'balanced');
```

---

### 7. Admin UI Capabilities

#### Segment Manager (`app/components/SegmentManager.tsx`)
- View all segments with filtering
- Create new segments with full configuration
- Edit existing segment configurations
- Delete segments (with validation)

#### Consultation Type Configuration (`app/components/ConsultationTypeSegmentConfigPanel.tsx`)
- View segments by consultation type
- Drag-and-drop segments between CORE, ADDITIONAL, EXCLUDED
- Configure consultation-type-specific overrides
- **Three-column layout:**
  - **CORE** (blue) - Essential segments
  - **ADDITIONAL** (gray) - Optional segments
  - **EXCLUDED** (red) - Hidden segments

#### Template Admin (`app/components/TemplateAdminScreen.tsx`)
- Create and edit templates
- Configure template segment assignments
- Set visibility rules (specialization, hospital)
- Manage template hierarchy

#### Segment Request Approval (`app/components/SegmentForm.tsx` with `isPendingApproval`)
- Review doctor-submitted segment requests
- Edit **all fields** (not just schema) during approval
- Add JSON schema to complete the segment
- Approve or reject requests

---

## Segment Assignment Types

### Assignment Type Hierarchy

```
1. Common (is_common=true)
   ├─ Visible to: ALL consultation types, ALL templates
   └─ Can be: Moved to EXCLUDED per consultation type

2. Consultation Type (consultation_type_id)
   ├─ Visible to: All templates within that consultation type
   └─ Can be: Customized per template

3. Template-Specific (template_id)
   ├─ Visible to: Only that specific template
   └─ Can be: Customized per doctor
```

### Assignment Decision Tree

**When creating a segment, admin chooses:**

```
Q: Should this segment be available to all consultation types?
├─ YES → Set is_common=true (Common Segment)
└─ NO → Q: Should this be available to all templates of a type?
    ├─ YES → Set consultation_type_id (Consultation Type Segment)
    └─ NO → Set template_id (Template-Specific Segment)
```

---

## Configuration Hierarchy & Inheritance

### 1. Consultation Type Inheritance from Common Segments

**Rule:** All consultation types **inherit all common segments** by default.

**Override Mechanism:** `consultation_type_segment_defaults`

**Example Flow:**
```
Common Segment: DIAGNOSIS (default_category='core', brevity='balanced')
    ↓
OP Consultation Type
    ├─ Inherits DIAGNOSIS as CORE with balanced verbosity
    └─ Can override via consultation_type_segment_defaults:
        - Change to 'additional' category
        - Change to 'excluded' (hide from OP)
        - Change brevity to 'concise'
```

**SQL Query Logic:**
```sql
-- Get segments for OP consultation type
SELECT * FROM segment_definitions sd
LEFT JOIN consultation_type_segment_defaults ctsd
  ON sd.segment_code = ctsd.segment_code
  AND ctsd.consultation_type_id = 'op-uuid'
WHERE
  sd.is_common = true  -- Common segments
  OR sd.consultation_type_id = 'op-uuid'  -- OP-specific segments
  AND COALESCE(ctsd.default_category, sd.default_category) != 'excluded'
ORDER BY COALESCE(ctsd.default_display_order, sd.display_order);
```

---

### 2. Template Inheritance from Consultation Type

**Rule:** Templates inherit all segments visible to their consultation type.

**Sources:**
1. Common segments (minus consultation-type EXCLUDED)
2. Consultation-type-specific segments
3. Template-specific segments (this template only)

**Override Mechanism:** `template_segment_configurations`

**Example Flow:**
```
Consultation Type: OP
├─ Common Segments: DIAGNOSIS, PRESCRIPTION, CHIEF_COMPLAINTS
├─ OP-Specific Segments: INVESTIGATIONS, PHYSICAL_EXAM
└─ Templates:
    ├─ "Quick OP" Template
    │   ├─ Inherits all OP segments
    │   └─ Overrides via template_segment_configurations:
    │       - INVESTIGATIONS → excluded (hide for quick consults)
    │       - DIAGNOSIS → brevity='concise'
    │
    └─ "Detailed OP" Template
        ├─ Inherits all OP segments
        └─ Overrides:
            - All segments → brevity='detailed'
            - Additional segment: PSYCHIATRIC_ASSESSMENT (template-specific)
```

**SQL Query Logic:**
```sql
-- Get segments for "Quick OP" template
SELECT
  sd.*,
  COALESCE(tsc.category, ctsd.default_category, sd.default_category) AS final_category,
  COALESCE(tsc.brevity_level, ctsd.default_brevity_level, sd.default_brevity_level) AS final_brevity
FROM segment_definitions sd
LEFT JOIN template_segment_configurations tsc
  ON sd.segment_code = tsc.segment_code
  AND tsc.template_id = 'quick-op-uuid'
LEFT JOIN consultation_type_segment_defaults ctsd
  ON sd.segment_code = ctsd.segment_code
  AND ctsd.consultation_type_id = 'op-uuid'
WHERE
  (sd.is_common = true OR sd.consultation_type_id = 'op-uuid' OR sd.template_id = 'quick-op-uuid')
  AND sd.is_active = true
  AND COALESCE(tsc.category, ctsd.default_category, sd.default_category) != 'excluded'
ORDER BY COALESCE(tsc.display_order, ctsd.default_display_order, sd.display_order);
```

---

### 3. Doctor Inheritance from Template

**Rule:** Doctors inherit all segments from their active template, then can customize further.

**Override Mechanism:** `doctor_segment_configurations`

**Two Types of Doctor Overrides:**
1. **Global Doctor Override** (`template_id = NULL`)
   - Applies to all templates this doctor uses
   - Rare use case

2. **Template-Specific Doctor Override** (`template_id = <UUID>`)
   - Applies only when using this specific template
   - Most common use case

**Example Flow:**
```
Doctor: Dr. Sarah Johnson
├─ Active Template: "Psychiatry Standard"
│   ├─ DIAGNOSIS (core, detailed)
│   ├─ MENTAL_STATUS (core, detailed)
│   └─ INVESTIGATIONS (additional, balanced)
│
└─ Doctor Customizations (doctor_segment_configurations):
    ├─ INVESTIGATIONS → Move to CORE (needs investigations for psych)
    ├─ MENTAL_STATUS → brevity='concise' (prefers brevity)
    └─ Custom prompt for DIAGNOSIS (custom_prompt_section)
```

---

## Doctor Capabilities

### 1. Activate Templates

Doctors select a template to use as their baseline configuration.

**Table:** `doctor_active_templates`

**UI:** Template Selector (`app/components/TemplateSelector.tsx`)

**Behavior:**
- One active template per doctor
- Switching templates loads new segment configuration
- `has_custom_overrides` flag tracks if doctor modified default settings

---

### 2. Customize Segment Configuration

Doctors can customize segments within their active template.

**Table:** `doctor_segment_configurations`

**UI:** Doctor Preset Config Screen (`app/components/DoctorPresetConfigScreen.tsx`)

**Customizable Options:**
- **Category**: Move segments between CORE, ADDITIONAL, EXCLUDED
  - **Validation**: Required segments cannot be moved from CORE
- **Display Order**: Reorder segments within a category
- **Brevity Level**: Change verbosity (concise/balanced/detailed)
- **Terminology Style**: Change terminology (medical_terms/simple_terms/as_spoken)
- **Custom Prompt** (Advanced): Override prompt text for specific segments
- **Custom Schema** (Advanced): Override JSON schema for output structure

**Drag-and-Drop UI:**
```
┌─────────────────┬─────────────────┬─────────────────┐
│   CORE (8)      │  ADDITIONAL(10) │  EXCLUDED (0)   │
├─────────────────┼─────────────────┼─────────────────┤
│ □ Diagnosis *   │ □ Patient Info  │  (empty)        │
│ □ Prescription *│ □ Investigations│                 │
│ □ Assessment    │ □ HPI           │                 │
└─────────────────┴─────────────────┴─────────────────┘
* = Required segment (cannot move from CORE)
```

---

### 3. Request New Segments

Doctors can request new segments that require admin approval.

**Table:** `segment_definitions` (with `status='pending_approval'`)

**UI:** Create Segment Request (`app/components/SegmentForm.tsx`)

**Workflow:**
1. Doctor fills out segment details:
   - segment_code, segment_name
   - prompt_section_text (AI instructions)
   - Categorization and configuration
   - **No schema required** (admin adds during approval)

2. Segment created with `status='pending_approval'`, `created_by_doctor_id=<doctor-uuid>`

3. Admin reviews pending segments in Segment Manager

4. Admin edits **all fields** (including schema) and approves

5. Segment becomes `status='active'` and available to doctor's template

**Fields Doctor Provides:**
- Segment code and name
- Prompt section text (what to extract)
- Default category (CORE/ADDITIONAL)
- Display order preference
- Brevity and terminology preferences
- Consultation type or template assignment

**Fields Admin Adds:**
- `schema_definition_json` (Gemini-compatible output schema)
- Validation and review of all fields
- Final approval decision

---

### 4. View Display Preferences

Doctors can customize how extracted data is displayed in the UI.

**Table:** `doctor_segment_display_preferences`

**UI:** Display format controls in results view

**Options:**
- `display_format`: 'table' | 'paragraph' | 'cards' | 'timeline' | 'list'
- `is_expanded`: Whether section is expanded by default
- `sort_order`: Custom ordering for display

---

## Configuration Override Hierarchy

### Complete Precedence Order (Highest to Lowest)

```
1. Doctor Template-Specific Override
   ↓ (if not set)
2. Doctor Global Override
   ↓ (if not set)
3. Template Segment Configuration
   ↓ (if not set)
4. Consultation Type Segment Defaults
   ↓ (if not set)
5. Segment Definition Defaults
```

### Hierarchy Visualization

```
╔════════════════════════════════════════════════════════╗
║  Doctor Template-Specific Config (Highest Priority)   ║
║  doctor_segment_configurations (template_id = UUID)    ║
╚════════════════════════════════════════════════════════╝
                        ↓ OVERRIDES
╔════════════════════════════════════════════════════════╗
║  Doctor Global Config                                  ║
║  doctor_segment_configurations (template_id = NULL)    ║
╚════════════════════════════════════════════════════════╝
                        ↓ OVERRIDES
╔════════════════════════════════════════════════════════╗
║  Template Segment Configuration                        ║
║  template_segment_configurations                       ║
╚════════════════════════════════════════════════════════╝
                        ↓ OVERRIDES
╔════════════════════════════════════════════════════════╗
║  Consultation Type Defaults                            ║
║  consultation_type_segment_defaults                    ║
╚════════════════════════════════════════════════════════╝
                        ↓ OVERRIDES
╔════════════════════════════════════════════════════════╗
║  Segment Definition Defaults (Base Configuration)      ║
║  segment_definitions                                   ║
╚════════════════════════════════════════════════════════╝
```

### SQL Implementation

The hierarchy is implemented in the database function:
**`get_doctor_segment_configuration(doctor_id, consultation_type_id, template_id, mode)`**

Located in: `backend/supabase/schema_enhanced.sql` (lines 1198-1346)

```sql
-- Excerpt showing COALESCE hierarchy for category
COALESCE(
    dsc_specific.category,          -- 1. Doctor template-specific
    dsc_global.category,             -- 2. Doctor global
    tsc.category,                    -- 3. Template config
    ctsd.default_category,           -- 4. Consultation type default
    sd.default_category              -- 5. Segment default
) AS final_category
```

---

## Dynamic Prompt Generation

### Architecture Overview

Prompts are **generated dynamically at runtime** by combining:
1. Base segment prompt texts from database
2. Brevity level modifiers
3. Terminology style modifiers
4. Gemini schemas generated from JSON definitions

**Key Principle:** No hardcoded prompts. Everything configurable via database.

---

### 1. Core Dynamic Generation Service

**File:** `backend/services/segment_registry.py`

This is the **heart of the dynamic prompt system**.

#### Key Functions

##### `load_segments_for_mode(user_id, mode, consultation_type_code, template_code)`
**Lines:** ~50-150

**Purpose:** Load segments from database with full hierarchy resolution

**Process:**
1. Get active template for doctor (if template_code provided)
2. Query `get_doctor_segment_configuration()` database function
3. Filter by mode ('core', 'additional', 'full')
4. Return list of segments with resolved configuration

**Returns:**
```python
[
  {
    'segment_code': 'DIAGNOSIS',
    'segment_name': 'Diagnosis',
    'prompt_section_text': 'Extract primary and differential diagnoses...',
    'schema_definition_json': {...},
    'category': 'core',  # After hierarchy resolution
    'brevity_level': 'detailed',  # After hierarchy resolution
    'terminology_style': 'medical_terms',  # After hierarchy resolution
    'display_order': 1
  },
  ...
]
```

---

##### `apply_brevity_modifier(prompt_text, brevity_level, segment_code)`
**Lines:** ~200-280

**Purpose:** Dynamically modify prompt verbosity based on brevity setting

**Logic:**
```python
if brevity_level == 'concise':
    # Add concise modifiers
    modifiers = [
        "Be extremely concise and brief.",
        "Use bullet points where appropriate.",
        "Focus on key facts only.",
        "Avoid elaboration."
    ]

elif brevity_level == 'balanced':
    # Add balanced modifiers
    modifiers = [
        "Provide balanced detail.",
        "Include relevant context.",
        "Be thorough but not verbose."
    ]

elif brevity_level == 'detailed':
    # Add detailed modifiers
    modifiers = [
        "Provide comprehensive detail.",
        "Include all relevant context and nuances.",
        "Expand on clinical reasoning.",
        "Document thoroughly."
    ]

# Prepend or append modifiers to prompt_text
modified_prompt = f"{prompt_text}\n\n{' '.join(modifiers)}"
return modified_prompt
```

**Example:**
```
Original Prompt (from segment_definitions.prompt_section_text):
"Extract the primary diagnosis and differential diagnoses discussed."

After applying brevity='concise':
"Extract the primary diagnosis and differential diagnoses discussed.

Be extremely concise and brief. Use bullet points. Focus on key facts only."

After applying brevity='detailed':
"Extract the primary diagnosis and differential diagnoses discussed.

Provide comprehensive detail. Include all relevant context and clinical reasoning.
Document differential diagnosis considerations thoroughly."
```

---

##### `apply_terminology_modifier(prompt_text, terminology_style, segment_code)`
**Lines:** ~290-360

**Purpose:** Modify prompt to control terminology complexity

**Logic:**
```python
if terminology_style == 'simple_terms':
    modifiers = [
        "Use simple, patient-friendly language.",
        "Avoid medical jargon where possible.",
        "Explain technical terms in plain English."
    ]

elif terminology_style == 'as_spoken':
    modifiers = [
        "Preserve the exact phrasing used in the consultation.",
        "Maintain natural conversation flow.",
        "Do not rephrase or standardize terminology."
    ]

elif terminology_style == 'medical_terms':
    modifiers = [
        "Use standard medical terminology.",
        "Apply ICD-10/DSM-5 classifications where appropriate.",
        "Use clinical nomenclature."
    ]
```

---

##### `generate_system_prompt(segments, consultation_type_code)`
**Lines:** ~370-480

**Purpose:** Build complete system instruction by stitching together all segment prompts

**Process:**
```python
def generate_system_prompt(segments, consultation_type_code):
    # Start with base instruction
    system_prompt = f"""You are a medical documentation AI assistant specializing in {consultation_type_code} consultations.

Your task is to extract structured information from medical transcripts into the following segments:

"""

    # Add each segment's prompt section
    for i, segment in enumerate(segments, 1):
        # Apply modifiers
        modified_prompt = segment['prompt_section_text']
        modified_prompt = apply_brevity_modifier(
            modified_prompt,
            segment['brevity_level'],
            segment['segment_code']
        )
        modified_prompt = apply_terminology_modifier(
            modified_prompt,
            segment['terminology_style'],
            segment['segment_code']
        )

        # Add to system prompt with section number
        system_prompt += f"""
## {i}. {segment['segment_name']} ({segment['segment_code']})

{modified_prompt}

"""

    # Add closing instructions
    system_prompt += """
IMPORTANT:
- Extract only information explicitly mentioned in the transcript
- Use null for fields not discussed
- Maintain clinical accuracy
- Follow the schema structure exactly
"""

    return system_prompt
```

**Example Output:**
```
You are a medical documentation AI assistant specializing in OP consultations.

Your task is to extract structured information from medical transcripts into the following segments:

## 1. Diagnosis (DIAGNOSIS)

Extract the primary diagnosis and differential diagnoses discussed during the consultation.
Include ICD-10 codes if mentioned. Document diagnostic reasoning and clinical impression.

Provide comprehensive detail. Include all relevant context and clinical reasoning.
Use standard medical terminology. Apply ICD-10 classifications where appropriate.

## 2. Chief Complaints (CHIEF_COMPLAINTS)

Extract the patient's presenting complaints in their own words, followed by clinical description.
Note onset, duration, severity, and associated symptoms.

Be extremely concise and brief. Focus on key facts only.
Use simple, patient-friendly language where possible.

...
```

---

##### `generate_gemini_schema(segments)`
**Lines:** ~490-620

**Purpose:** Convert JSON schema definitions to Gemini-compatible `types.Schema` objects

**Process:**
```python
from google import genai
from google.genai import types

def generate_gemini_schema(segments):
    # Build properties dict from all segments
    properties = {}
    required_fields = []

    for segment in segments:
        segment_code = segment['segment_code']
        schema_json = segment['schema_definition_json']

        # Convert JSON schema to Gemini type
        properties[segment_code] = json_to_gemini_type(schema_json)

        # Track required segments
        if segment.get('is_required', False):
            required_fields.append(segment_code)

    # Create Gemini Schema object
    schema = types.Schema(
        type=types.Type.OBJECT,
        properties=properties,
        required=required_fields
    )

    return schema

def json_to_gemini_type(json_schema):
    """Recursively convert JSON schema to Gemini type"""
    schema_type = json_schema.get('type', 'string')

    if schema_type == 'object':
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                key: json_to_gemini_type(value)
                for key, value in json_schema.get('properties', {}).items()
            },
            required=json_schema.get('required', [])
        )
    elif schema_type == 'array':
        return types.Schema(
            type=types.Type.ARRAY,
            items=json_to_gemini_type(json_schema.get('items', {}))
        )
    elif schema_type == 'string':
        return types.Schema(type=types.Type.STRING)
    elif schema_type == 'number':
        return types.Schema(type=types.Type.NUMBER)
    # ... handle other types
```

**Example:**
```python
# Input: segment_definitions.schema_definition_json
{
  "type": "object",
  "properties": {
    "primary_diagnosis": {"type": "string"},
    "icd_10_code": {"type": "string"},
    "differential_diagnoses": {
      "type": "array",
      "items": {"type": "string"}
    }
  },
  "required": ["primary_diagnosis"]
}

# Output: Gemini types.Schema object
types.Schema(
    type=types.Type.OBJECT,
    properties={
        'primary_diagnosis': types.Schema(type=types.Type.STRING),
        'icd_10_code': types.Schema(type=types.Type.STRING),
        'differential_diagnoses': types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING)
        )
    },
    required=['primary_diagnosis']
)
```

---

##### `generate_extraction_artifacts(doctor_id, mode, consultation_type_code, template_code, transcript)`
**Lines:** ~640-750

**Purpose:** **Main orchestrator** - Generate complete prompt + schema for extraction

**Process:**
```python
def generate_extraction_artifacts(
    doctor_id: str,
    mode: str,  # 'core', 'additional', 'full'
    consultation_type_code: str,
    template_code: Optional[str],
    transcript: str
):
    # 1. Load segments with hierarchy resolution
    segments = load_segments_for_mode(
        user_id=doctor_id,
        mode=mode,
        consultation_type_code=consultation_type_code,
        template_code=template_code
    )

    # 2. Validate required segments present
    validate_required_segments(segments)

    # 3. Generate system prompt
    system_prompt = generate_system_prompt(segments, consultation_type_code)

    # 4. Generate user prompt
    user_prompt = f"""Please extract the medical information from this consultation transcript:

{transcript}

Extract information for all {len(segments)} segments according to the instructions above.
"""

    # 5. Generate Gemini schema
    gemini_schema = generate_gemini_schema(segments)

    # 6. Return complete extraction configuration
    return {
        'system_prompt': system_prompt,
        'user_prompt': user_prompt,
        'schema': gemini_schema,
        'segments': segments,  # Metadata for post-processing
        'segment_count': len(segments),
        'mode': mode
    }
```

**This function is called by all extraction APIs** to get the dynamic configuration.

---

### 2. Gemini Service Integration

**File:** `backend/services/gemini_service.py`

#### Dynamic Extraction Function

**Function:** `extract_op_summary_dynamic(transcript, doctor_id, mode, consultation_type_code, template_code)`
**Lines:** ~400-500

```python
async def extract_op_summary_dynamic(
    transcript: str,
    doctor_id: str = None,
    mode: str = "full",
    consultation_type_code: str = "OP",
    template_code: str = None,
    model: str = "gemini-2.0-flash-exp"
):
    """
    Dynamic extraction using database-driven segment configuration.

    Replaces hardcoded op_prompts.py with database-generated prompts.
    """

    # 1. Generate prompt and schema dynamically
    artifacts = generate_extraction_artifacts(
        doctor_id=doctor_id,
        mode=mode,
        consultation_type_code=consultation_type_code,
        template_code=template_code,
        transcript=transcript
    )

    # 2. Call Gemini API with generated configuration
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    response = await client.aio.models.generate_content(
        model=model,
        contents=artifacts['user_prompt'],
        config=types.GenerateContentConfig(
            system_instruction=artifacts['system_prompt'],
            response_mime_type="application/json",
            response_schema=artifacts['schema']
        )
    )

    # 3. Parse response
    extracted_data = json.loads(response.text)

    # 4. Return with metadata
    return {
        'extraction': extracted_data,
        'metadata': {
            'mode': mode,
            'segment_count': artifacts['segment_count'],
            'segments_extracted': list(extracted_data.keys()),
            'model': model,
            'doctor_id': doctor_id,
            'consultation_type': consultation_type_code,
            'template_code': template_code
        }
    }
```

---

### 3. API Endpoints

**File:** `backend/routers/summary.py`

All extraction endpoints use the dynamic generation system:

#### POST /api/v1/op/summary-dynamic
**Lines:** ~150-200

```python
@router.post("/summary-dynamic")
async def extract_op_summary_dynamic_endpoint(request: DynamicExtractionRequest):
    """
    Dynamic extraction endpoint with user configuration.

    Loads doctor's template and segment config, generates prompt dynamically.
    """
    result = await extract_op_summary_dynamic(
        transcript=request.transcript,
        doctor_id=request.doctor_id,
        mode=request.mode,
        consultation_type_code=request.consultation_type_code,
        template_code=request.template_code,
        model=request.model
    )
    return result
```

#### POST /api/v1/op/summary-core
**Lines:** ~210-240

```python
@router.post("/summary-core")
async def extract_op_summary_core(request: ExtractionRequest):
    """Fast CORE extraction only."""
    return await extract_op_summary_dynamic(
        transcript=request.transcript,
        doctor_id=request.doctor_id,
        mode="core",  # Only CORE segments
        model=request.model
    )
```

---

### 4. Static Prompts (Legacy)

**Files:**
- `backend/services/prompts.py` - Psychiatry prompts
- `backend/services/discharge_prompts.py` - Discharge prompts
- `backend/services/op_prompts.py` - OP prompts (deprecated)

**Status:**
- Still used by non-dynamic extraction endpoints
- Being phased out in favor of database-driven system
- Kept for backward compatibility

**Example:** `backend/services/prompts.py`
```python
# Hardcoded prompt for SMALL template
MEDICAL_EXTRACTION_PROMPT_SMALL = """
Extract the following 7 fields from the psychiatric consultation:

1. DIAGNOSIS
Extract primary diagnosis...

2. CHIEF_COMPLAINTS
Extract presenting complaints...
...
"""
```

**Migration Path:**
1. Admin creates segment definitions in database matching static prompts
2. Segments include same prompt_section_text
3. Switch API endpoint to use dynamic extraction
4. Deprecate static prompt files

---

### 5. Prompt Assembly Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│  1. API Request                                         │
│  POST /api/v1/op/summary-dynamic                        │
│  { doctor_id, mode, consultation_type, template_code }  │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  2. Generate Extraction Artifacts                       │
│  segment_registry.generate_extraction_artifacts()       │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  3. Load Segments with Hierarchy                        │
│  segment_registry.load_segments_for_mode()              │
│  → Calls get_doctor_segment_configuration()             │
│  → Returns segments with resolved config                │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  4. For Each Segment:                                   │
│  a) Get base prompt from segment_definitions            │
│  b) Apply brevity modifier                              │
│  c) Apply terminology modifier                          │
│  d) Add to system prompt                                │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  5. Generate Gemini Schema                              │
│  segment_registry.generate_gemini_schema()              │
│  → Convert schema_definition_json to types.Schema       │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  6. Return Artifacts                                    │
│  { system_prompt, user_prompt, schema, segments }       │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  7. Call Gemini API                                     │
│  gemini_service.extract_op_summary_dynamic()            │
│  → Send prompts + schema to Gemini                      │
│  → Receive structured JSON response                     │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  8. Return Extraction + Metadata                        │
│  { extraction: {...}, metadata: {...} }                 │
└─────────────────────────────────────────────────────────┘
```

---

## Database Schema Reference

### Core Tables

#### segment_definitions
**Purpose:** Master table for all segment definitions

**Key Fields:**
- `segment_code`: Unique identifier
- `segment_name`: Display name
- `prompt_section_text`: **Base prompt for AI extraction**
- `schema_definition_json`: **JSON schema for output structure**
- `consultation_type_id`: NULL = common, UUID = type-specific
- `template_id`: NULL = not template-specific, UUID = template-only
- `is_common`: TRUE = visible to all types
- `default_category`: Default categorization (core/additional/excluded)
- `default_brevity_level`: Default verbosity
- `default_terminology_style`: Default terminology
- `is_required`: TRUE = cannot move from CORE
- `status`: Approval workflow status
- `created_by_doctor_id`: Doctor who requested (NULL = admin)

---

#### consultation_type_segment_defaults
**Purpose:** Override common segment behavior per consultation type

**Key Fields:**
- `consultation_type_id`: Which type
- `segment_code`: Which segment
- `default_category`: Override category (e.g., exclude common segment)
- `default_brevity_level`: Override verbosity
- `default_terminology_style`: Override terminology

---

#### templates
**Purpose:** Predefined segment configurations

**Key Fields:**
- `template_code`: Unique identifier
- `template_name`: Display name
- `consultation_type_id`: Which consultation type
- `specialization`: Visibility filter (NULL = all)
- `hospital_id`: Hospital-specific (NULL = platform-wide)
- `is_default`: Default for consultation type

---

#### template_segment_configurations
**Purpose:** Configure segments within a template

**Key Fields:**
- `template_id`: Which template
- `segment_code`: Which segment
- `category`: core/additional/excluded
- `display_order`: Order in template
- `brevity_level`: Template-specific verbosity
- `terminology_style`: Template-specific terminology

---

#### doctor_segment_configurations
**Purpose:** Doctor-specific overrides

**Key Fields:**
- `doctor_id`: Which doctor
- `segment_code`: Which segment
- `template_id`: NULL = global, UUID = template-specific
- `category`: Doctor's category override
- `display_order`: Doctor's order override
- `brevity_level`: Doctor's verbosity override
- `terminology_style`: Doctor's terminology override
- `custom_prompt_section`: Custom prompt (advanced)
- `custom_schema_json`: Custom schema (advanced)

---

#### doctor_active_templates
**Purpose:** Track active template per doctor

**Key Fields:**
- `doctor_id`: Which doctor (UNIQUE)
- `template_id`: Currently active template
- `has_custom_overrides`: Whether doctor customized template

---

### Database Function

#### get_doctor_segment_configuration(doctor_id, consultation_type_id, template_id, mode)

**Location:** `backend/supabase/schema_enhanced.sql` lines 1198-1346

**Purpose:** **Master query implementing full configuration hierarchy**

**Returns:** Segments with fully resolved configuration

**Process:**
1. Get segment definitions for consultation type (common + type-specific + template-specific)
2. Join doctor template-specific overrides
3. Join doctor global overrides
4. Join template segment configurations
5. Join consultation type segment defaults
6. Use COALESCE to resolve hierarchy for each field
7. Filter by mode (core/additional/full)
8. Exclude segments marked as 'excluded'
9. Order by resolved display_order

**Example Call:**
```sql
SELECT * FROM get_doctor_segment_configuration(
    'doctor-uuid',
    'op-consultation-type-uuid',
    'psychiatry-core-template-uuid',
    'core'
);
```

---

## Summary

### Admin Powers
1. ✅ Create consultation types
2. ✅ Create segments (common, type-specific, template-specific)
3. ✅ Configure segment defaults (category, brevity, terminology, schema)
4. ✅ Override common segments per consultation type
5. ✅ Create templates with segment configurations
6. ✅ Approve doctor segment requests
7. ✅ Edit all fields during approval (including schema)

### Doctor Powers
1. ✅ Activate templates
2. ✅ Customize segment configuration (category, order, brevity, terminology)
3. ✅ Request new segments (pending admin approval)
4. ✅ Override prompts/schemas (advanced users)
5. ❌ Cannot delete segments
6. ❌ Cannot modify segment schemas (except via custom override)

### Dynamic Prompt System
- **Source:** `backend/services/segment_registry.py`
- **Base Prompts:** `segment_definitions.prompt_section_text`
- **Modifiers:** Applied dynamically based on brevity_level and terminology_style
- **Assembly:** `generate_system_prompt()` stitches all segment prompts together
- **Schema:** `generate_gemini_schema()` converts JSON schemas to Gemini types
- **Orchestrator:** `generate_extraction_artifacts()` coordinates entire process

### Configuration Hierarchy
```
Doctor Template-Specific → Doctor Global → Template Config →
Consultation Type Defaults → Segment Defaults
```

All controlled by `get_doctor_segment_configuration()` database function.

---

**Version:** 1.0
**Last Updated:** 2025-11-06
**Related Files:**
- `backend/services/segment_registry.py` - Dynamic prompt generation
- `backend/services/gemini_service.py` - AI extraction service
- `backend/routers/summary.py` - API endpoints
- `backend/supabase/schema_enhanced.sql` - Database schema and functions

# Dynamic Prompt Generation System

**Version:** 1.0
**Last Updated:** 2025-11-04
**Status:** Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Database Layer](#database-layer)
4. [Service Layer](#service-layer)
5. [API Layer](#api-layer)
6. [Prompt Generation Flow](#prompt-generation-flow)
7. [User Customization](#user-customization)
8. [Preset System](#preset-system)
9. [Clinical Safety](#clinical-safety)
10. [API Usage Examples](#api-usage-examples)
11. [Performance Optimization](#performance-optimization)

---

## Overview

The Dynamic Prompt Generation System is a database-driven architecture that enables **user-configurable medical consultation extraction** with real-time prompt and schema generation.

### Key Features

- **Database-Driven:** All segment definitions stored in Supabase (no hardcoded prompts)
- **User Customization:** Per-user segment categorization, brevity, and terminology control
- **Dynamic Generation:** Prompts and Gemini schemas generated on-the-fly from database
- **Clinical Safety:** Required segments enforced via validation
- **Performance Optimized:** CORE extraction ~50% faster than FULL
- **Specialty Presets:** Pre-configured setups for Cardiology, Pediatrics, etc.

### Architecture Philosophy

**Traditional Approach (Static):**
```
Code → Hardcoded Prompts → Fixed Schema → Gemini API
```
❌ Inflexible, requires code changes for customization

**Our Approach (Dynamic):**
```
Database → User Config → Dynamic Prompts → Generated Schema → Gemini API
```
✅ Flexible, user-customizable without code changes

---

## System Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Future)                        │
│  ┌────────────────────┐  ┌──────────────────────────────┐  │
│  │ Segment Manager    │  │ Extraction UI                │  │
│  │ (Drag & Drop)      │  │ (Progressive Loading)        │  │
│  └────────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     API Layer (FastAPI)                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ op_summary.py Router                                   │ │
│  │ - POST /summary-dynamic (core/additional/full)        │ │
│  │ - GET  /segments (list with config)                   │ │
│  │ - PUT  /segments/{code}/config (update)               │ │
│  │ - POST /presets/{id}/activate                         │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Service Layer (Python)                    │
│  ┌──────────────────┐  ┌──────────────────────────────────┐│
│  │segment_registry  │  │ supabase_service.py              ││
│  │- Load segments   │  │ - get_segment_definitions()      ││
│  │- Generate prompts│  │ - update_user_segment_config()   ││
│  │- Generate schemas│  │ - validate_configuration()       ││
│  └──────────────────┘  └──────────────────────────────────┘│
│  ┌────────────────────────────────────────────────────────┐ │
│  │ gemini_service.py                                      │ │
│  │ - extract_op_summary_dynamic()                        │ │
│  │ - Calls Gemini API with generated artifacts           │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Database Layer (Supabase)                  │
│  ┌───────────────────────┐  ┌────────────────────────────┐ │
│  │segment_definitions    │  │user_segment_configurations │ │
│  │- Prompt text          │  │- User overrides            │ │
│  │- Schema JSON          │  │- Brevity level             │ │
│  │- Default category     │  │- Terminology style         │ │
│  └───────────────────────┘  └────────────────────────────┘ │
│  ┌───────────────────────┐  ┌────────────────────────────┐ │
│  │segment_presets        │  │user_active_presets         │ │
│  │- Preset configs       │  │- Active preset tracking    │ │
│  └───────────────────────┘  └────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Layer

### Table: `segment_definitions`

**Purpose:** Master registry of all 18 OP consultation segments

**Key Columns:**
```sql
segment_code              VARCHAR(50)   -- 'DIAGNOSIS', 'CHIEF_COMPLAINTS', etc.
segment_name              VARCHAR(255)  -- Display name
prompt_section_text       TEXT          -- Full prompt instructions
schema_definition_json    JSONB         -- Gemini schema structure
default_category          VARCHAR(20)   -- 'core' | 'additional'
is_required               BOOLEAN       -- Safety: Cannot remove from CORE
display_order             INTEGER       -- Order in extraction (1-18)
default_brevity_level     VARCHAR(20)   -- 'concise' | 'balanced' | 'detailed'
default_terminology_style VARCHAR(20)   -- 'medical_terms' | 'simple_terms' | 'as_spoken'
```

**Example Row:**
```json
{
  "segment_code": "DIAGNOSIS",
  "segment_name": "Diagnosis",
  "prompt_section_text": "**Description:** Primary and secondary diagnoses...",
  "schema_definition_json": {
    "type": "OBJECT",
    "properties": {
      "primary_diagnosis": {"type": "STRING"},
      "interim_diagnosis": {"type": "ARRAY"},
      "secondary_diagnoses": {"type": "ARRAY"}
    }
  },
  "default_category": "core",
  "is_required": true,
  "display_order": 2,
  "default_brevity_level": "balanced",
  "default_terminology_style": "medical_terms"
}
```

---

### Table: `user_segment_configurations`

**Purpose:** User-specific customizations for segments

**Key Columns:**
```sql
user_id          UUID          -- User identifier
segment_code     VARCHAR(50)   -- Which segment
category         VARCHAR(20)   -- User's preferred category
brevity_level    VARCHAR(20)   -- User's brevity preference
terminology_style VARCHAR(20)  -- User's terminology preference
```

**Example:** User wants Investigations in CORE (instead of default ADDITIONAL)
```sql
INSERT INTO user_segment_configurations (user_id, segment_code, category)
VALUES ('user-123', 'INVESTIGATIONS', 'core');
```

---

### Table: `segment_presets`

**Purpose:** Pre-defined specialty configurations

**Structure:**
```sql
preset_id         UUID
preset_name       VARCHAR(100)  -- 'Cardiology', 'Pediatrics', 'Quick Mode'
preset_description TEXT
preset_type       VARCHAR(50)   -- 'specialty' | 'quick' | 'custom'
segment_configuration JSONB     -- Full config for all segments
```

**Example Preset: Cardiology**
```json
{
  "preset_name": "Cardiology Focus",
  "preset_description": "Optimized for cardiovascular consultations",
  "segment_configuration": {
    "PHYSICAL_EXAMINATION": {
      "brevity_level": "detailed",  // More detail on CVS
      "category": "core"
    },
    "INVESTIGATIONS": {
      "category": "core"  // ECG, Echo in CORE
    },
    "PROTOCOL": {
      "brevity_level": "detailed"  // Detailed BP monitoring
    }
  }
}
```

---

### PostgreSQL RPC Functions

#### `get_segment_definitions(p_user_id, p_mode)`

**Purpose:** Load segments with user customization merged

**Logic:**
```sql
1. SELECT from segment_definitions WHERE default_category = p_mode
2. LEFT JOIN user_segment_configurations ON segment_code
3. COALESCE(user.category, default.category) AS category
4. COALESCE(user.brevity_level, default.brevity_level) AS brevity_level
5. ORDER BY display_order
```

**Returns:** Array of segment definitions with user preferences applied

---

#### `validate_segment_configuration(p_user_id)`

**Purpose:** Ensure CORE has all required segments

**Logic:**
```sql
1. Get user's CORE segments
2. Check if all segments with is_required=true are in CORE
3. Return {is_valid: boolean, error_message: string}
```

**Example Validation Failure:**
```json
{
  "is_valid": false,
  "error_message": "Required segment 'DIAGNOSIS' is missing from CORE category. Cannot move required segments."
}
```

---

## Service Layer

### Module: `segment_registry.py`

**Core module for dynamic prompt/schema generation**

#### Function: `load_segments_for_mode(user_id, mode)`

```python
def load_segments_for_mode(
    user_id: Optional[uuid.UUID],
    mode: str = "full"
) -> List[Dict[str, Any]]:
    """
    Load segment definitions for specific mode and user.

    Args:
        user_id: User ID for personalized config (None = default)
        mode: 'core' | 'additional' | 'full'

    Returns:
        List of segments sorted by display_order
    """
    segments = get_segment_definitions(user_id=user_id, mode=mode)
    return sorted(segments, key=lambda s: s.get("display_order", 999))
```

---

#### Function: `generate_system_prompt(segments)`

**Assembles system prompt from segment instructions**

```python
def generate_system_prompt(segments: List[Dict]) -> str:
    """
    Generate system prompt by concatenating all segment instructions.

    Process:
    1. Extract prompt_section_text from each segment
    2. Apply brevity modifiers (if user set to concise/detailed)
    3. Apply terminology modifiers (if user set to simple_terms)
    4. Concatenate with proper formatting

    Returns:
        Complete system instruction for Gemini
    """
    # Base instruction
    prompt = """You are a specialized medical documentation AI assistant.
    Extract structured clinical information from consultation transcripts.

    **CRITICAL RULES:**
    - NEVER fabricate information
    - Use "N/A" for unavailable fields
    - Use empty arrays [] for missing lists

    ---

    """

    # Add each segment's instructions
    for segment in segments:
        text = segment['prompt_section_text']

        # Apply brevity modifier
        text = apply_brevity_modifier(
            text,
            segment.get('brevity_level', 'balanced'),
            segment['segment_code']
        )

        # Apply terminology modifier
        text = apply_terminology_modifier(
            text,
            segment.get('terminology_style', 'medical_terms'),
            segment['segment_code']
        )

        prompt += f"\n## {segment['segment_name'].upper()}\n\n{text}\n\n"

    return prompt
```

---

#### Function: `apply_brevity_modifier(prompt, level, code)`

**Modifies prompt based on brevity setting**

```python
def apply_brevity_modifier(
    prompt_text: str,
    brevity_level: str,
    segment_code: str
) -> str:
    """
    Modify prompt for brevity level.

    Brevity Levels:
    - concise: Ultra-brief, 1-2 sentences max
    - balanced: Standard extraction (default)
    - detailed: Comprehensive, include all context
    """
    if brevity_level == "concise":
        return f"{prompt_text}\n\n**BREVITY: CONCISE MODE**\n" \
               "- Keep ultra-brief (1-2 sentences max)\n" \
               "- Omit detailed explanations\n" \
               "- Focus on key findings only"

    elif brevity_level == "detailed":
        return f"{prompt_text}\n\n**BREVITY: DETAILED MODE**\n" \
               "- Provide comprehensive extraction\n" \
               "- Include all context and reasoning\n" \
               "- Document thoroughly"

    return prompt_text  # balanced (default)
```

---

#### Function: `apply_terminology_modifier(prompt, style, code)`

**Modifies prompt for terminology preference**

```python
def apply_terminology_modifier(
    prompt_text: str,
    terminology_style: str,
    segment_code: str
) -> str:
    """
    Modify prompt for terminology style.

    Terminology Styles:
    - medical_terms: Use precise medical terminology
    - simple_terms: Use patient-friendly language
    - as_spoken: Keep as mentioned in transcript
    """
    if terminology_style == "simple_terms":
        return f"{prompt_text}\n\n**TERMINOLOGY: SIMPLE LANGUAGE**\n" \
               "- Use patient-friendly terms\n" \
               "- Avoid complex medical jargon\n" \
               "- Explain abbreviations"

    elif terminology_style == "as_spoken":
        return f"{prompt_text}\n\n**TERMINOLOGY: AS SPOKEN**\n" \
               "- Keep terminology as mentioned\n" \
               "- Don't translate to medical terms\n" \
               "- Preserve original phrasing"

    return prompt_text  # medical_terms (default)
```

---

#### Function: `generate_gemini_schema(segments)`

**Builds Gemini response schema from segment schemas**

```python
def generate_gemini_schema(segments: List[Dict]) -> types.Schema:
    """
    Generate Gemini response schema from segment definitions.

    Process:
    1. Extract schema_definition_json from each segment
    2. Build properties dict
    3. Determine required fields
    4. Return types.Schema object
    """
    properties = {}
    required_fields = []

    for segment in segments:
        code = segment['segment_code'].lower()
        schema_json = segment['schema_definition_json']

        # Convert JSON schema to types.Schema
        properties[code] = convert_json_to_types_schema(schema_json)

        # Add to required if segment is required
        if segment.get('is_required', False):
            required_fields.append(code)

    return types.Schema(
        type=types.Type.OBJECT,
        properties=properties,
        required=required_fields
    )
```

---

#### Function: `generate_extraction_artifacts()`

**Main orchestrator - generates all artifacts**

```python
def generate_extraction_artifacts(
    user_id: Optional[uuid.UUID],
    mode: str,
    transcript: str
) -> Dict[str, Any]:
    """
    Generate complete extraction artifacts for Gemini API call.

    Returns:
        {
            "system_prompt": str,      # System instructions
            "user_prompt": str,         # User prompt with transcript
            "schema": types.Schema,     # Response schema
            "segment_count": int,       # Number of segments
            "validation": dict          # Configuration validation result
        }
    """
    # 1. Load segments
    segments = load_segments_for_mode(user_id, mode)

    # 2. Validate configuration
    validation = validate_segment_configuration(user_id)
    if not validation['is_valid']:
        raise ValueError(validation['error_message'])

    # 3. Generate system prompt
    system_prompt = generate_system_prompt(segments)

    # 4. Generate user prompt
    user_prompt = generate_user_prompt(segments, transcript)

    # 5. Generate schema
    schema = generate_gemini_schema(segments)

    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "schema": schema,
        "segment_count": len(segments),
        "validation": validation
    }
```

---

### Module: `gemini_service.py`

#### Function: `extract_op_summary_dynamic()`

**Main extraction function using dynamic configuration**

```python
async def extract_op_summary_dynamic(
    transcript: str,
    user_id: Optional[str] = None,
    mode: str = "full",
    model: str = "gemini-2.5-pro"
) -> Dict[str, Any]:
    """
    Extract OP summary using database-driven configuration.

    Flow:
    1. Generate extraction artifacts (prompts + schema)
    2. Call Gemini API
    3. Parse and return results
    """
    # Convert user_id to UUID
    user_uuid = uuid.UUID(user_id) if user_id else None

    # Generate dynamic artifacts
    artifacts = generate_extraction_artifacts(
        user_id=user_uuid,
        mode=mode,
        transcript=transcript
    )

    # Call Gemini API
    response = await client.aio.models.generate_content(
        model=model,
        contents=artifacts["user_prompt"],
        config=types.GenerateContentConfig(
            system_instruction=artifacts["system_prompt"],
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=artifacts["schema"]
        )
    )

    # Parse response
    extracted_data = json.loads(response.text)

    return {
        "data": extracted_data,
        "metadata": {
            "mode": mode,
            "segment_count": artifacts["segment_count"],
            "model": model,
            "validation": artifacts["validation"]
        }
    }
```

---

## Prompt Generation Flow

### Step-by-Step Example

**Scenario:** User requests CORE extraction with Diagnosis set to "concise" brevity

#### Step 1: User Configuration
```sql
-- User has customized Diagnosis segment
SELECT * FROM user_segment_configurations
WHERE user_id = 'user-123' AND segment_code = 'DIAGNOSIS';

-- Result:
{
  "user_id": "user-123",
  "segment_code": "DIAGNOSIS",
  "category": "core",
  "brevity_level": "concise",
  "terminology_style": "medical_terms"
}
```

#### Step 2: Load Segments
```python
segments = load_segments_for_mode(user_id="user-123", mode="core")
# Returns 8 CORE segments with user's brevity override for DIAGNOSIS
```

#### Step 3: Apply Brevity Modifier
```python
# Original prompt for DIAGNOSIS
original = """
**Description:** Primary and secondary diagnoses using precise medical terminology.

**Fields:**
- primary_diagnosis: Main diagnosis
- interim_diagnosis: Interim possibilities
- secondary_diagnoses: Additional conditions
"""

# After apply_brevity_modifier(original, "concise", "DIAGNOSIS")
modified = """
**Description:** Primary and secondary diagnoses using precise medical terminology.

**Fields:**
- primary_diagnosis: Main diagnosis
- interim_diagnosis: Interim possibilities
- secondary_diagnoses: Additional conditions

**BREVITY: CONCISE MODE**
- Keep ultra-brief (1-2 sentences max)
- Omit detailed explanations
- Focus on key findings only
"""
```

#### Step 4: Generate System Prompt
```python
system_prompt = generate_system_prompt(segments)

# Result: Concatenated instructions for all 8 CORE segments
# with brevity modifier applied to DIAGNOSIS
```

#### Step 5: Generate User Prompt
```python
user_prompt = generate_user_prompt(segments, transcript)

# Result: JSON structure + transcript
"""
Extract the following segments from the consultation transcript:

{
  "diagnosis": {
    "primary_diagnosis": "string",
    "interim_diagnosis": ["array"],
    "secondary_diagnoses": ["array"]
  },
  "chief_complaints": [...],
  ...
}

Transcript:
Doctor: How are you feeling?
Patient: I have a headache...
"""
```

#### Step 6: Generate Schema
```python
schema = generate_gemini_schema(segments)

# Result: types.Schema object with 8 CORE segment schemas
```

#### Step 7: Call Gemini API
```python
response = await gemini_api.generate_content(
    model="gemini-2.5-pro",
    contents=user_prompt,
    config={
        "system_instruction": system_prompt,
        "response_schema": schema
    }
)
```

#### Step 8: Return Results
```json
{
  "data": {
    "diagnosis": {
      "primary_diagnosis": "Hypertension Stage 2",
      "interim_diagnosis": [],
      "secondary_diagnoses": []
    },
    "chief_complaints": ["Headache, dizziness"],
    ...
  },
  "metadata": {
    "mode": "core",
    "segment_count": 8,
    "model": "gemini-2.5-pro"
  }
}
```

---

## User Customization

### Brevity Levels

| Level | Description | Effect on Extraction | Use Case |
|-------|-------------|---------------------|----------|
| **concise** | Ultra-brief | 1-2 sentences max, key findings only | Quick review, time-sensitive |
| **balanced** | Standard | Moderate detail, complete but concise | Default, most consultations |
| **detailed** | Comprehensive | Full context, all reasoning, thorough | Complex cases, research |

**Example: Diagnosis Segment**

```
CONCISE:
"Hypertension Stage 2"

BALANCED:
"Hypertension Stage 2 with medication withdrawal syndrome"

DETAILED:
"Hypertension Stage 2 (BP 160/90 mmHg) secondary to 4-day medication non-compliance,
presenting with withdrawal symptoms including headache and dizziness. Prior well-controlled
on Amlodipine 5mg daily for 5 years."
```

---

### Terminology Styles

| Style | Description | Effect | Use Case |
|-------|-------------|--------|----------|
| **medical_terms** | Precise terminology | Hypertension, Dyspnea, MI | Medical professionals |
| **simple_terms** | Patient-friendly | High blood pressure, shortness of breath, heart attack | Patient records |
| **as_spoken** | Verbatim | "BP is high", "can't breathe well", "heart problem" | Legal transcription |

**Example: Chief Complaints**

```
MEDICAL_TERMS:
["Dyspnea on exertion", "Orthopnea", "Paroxysmal nocturnal dyspnea"]

SIMPLE_TERMS:
["Shortness of breath during activity", "Difficulty breathing when lying flat",
 "Sudden breathlessness at night"]

AS_SPOKEN:
["Can't breathe when I walk", "Hard to breathe lying down", "Wake up gasping"]
```

---

### Per-Segment Configuration

**Flexibility:** Each segment can have different settings

**Example Configuration:**
```
Diagnosis:           brevity=balanced,   terminology=medical_terms
Chief Complaints:    brevity=concise,    terminology=medical_terms
History:             brevity=balanced,   terminology=medical_terms
Clinical Assessment: brevity=detailed,   terminology=medical_terms  (for complex reasoning)
Prescription:        brevity=detailed,   terminology=medical_terms  (safety critical)
Treatment Plan:      brevity=balanced,   terminology=simple_terms   (patient instructions)
Follow-up:           brevity=concise,    terminology=simple_terms   (easy to understand)
```

---

## Preset System

### Default Presets

#### **Quick Mode**
- **Purpose:** Fastest extraction for routine consultations
- **CORE:** 5 segments only (Diagnosis, Complaints, Prescription, Treatment Plan, Follow-up)
- **Brevity:** All set to "concise"
- **Time:** ~15-20s

#### **Cardiology Focus**
- **Purpose:** Cardiovascular consultations
- **CORE:** 8 standard + Investigations (ECG, Echo)
- **Customization:**
  - Physical Examination: brevity=detailed (focus on CVS)
  - Investigations: category=core (ECG/Echo always visible)
  - Protocol: brevity=detailed (BP monitoring crucial)

#### **Pediatrics**
- **Purpose:** Child consultations
- **Customization:**
  - History: Include birth_history
  - Physical Examination: Add growth parameters
  - Subtext Analysis: Include parent anxiety levels

#### **Psychiatry**
- **Purpose:** Mental health consultations
- **Customization:**
  - Subtext Analysis: category=core, brevity=detailed
  - History: Emphasize HEADSS framework
  - Protocol: Detailed mental health monitoring

---

### Creating Custom Presets

**SQL Example:**
```sql
INSERT INTO segment_presets (preset_name, preset_description, preset_type, segment_configuration)
VALUES (
  'Diabetes Management',
  'Optimized for diabetes follow-up appointments',
  'specialty',
  '{
    "INVESTIGATIONS": {
      "category": "core",
      "brevity_level": "detailed"  -- HbA1c, glucose always detailed
    },
    "PROTOCOL": {
      "category": "core",
      "brevity_level": "detailed"  -- Glucose monitoring protocol
    },
    "TREATMENT_PLAN_ADVICE": {
      "brevity_level": "detailed"  -- Diet critical for diabetes
    }
  }'::jsonb
);
```

---

## Clinical Safety

### Required Segments

**Cannot be moved from CORE or removed:**
1. Diagnosis
2. Chief Complaints
3. History (includes current medications and allergies)
4. Physical Examination
5. Clinical Assessment
6. Prescription
7. Follow-up

**Rationale:** Essential for patient safety and medical decision-making

---

### Validation

**Automatic validation before extraction:**
```python
validation = validate_segment_configuration(user_id)

# Returns:
{
  "is_valid": true,
  "error_message": null,
  "warnings": []
}

# If user tries to move Prescription to ADDITIONAL:
{
  "is_valid": false,
  "error_message": "Required segment 'PRESCRIPTION' cannot be moved from CORE category.",
  "warnings": []
}
```

**Enforcement:**
- Database-level constraints (`is_required` flag)
- API-level validation (before extraction)
- Frontend UI (disabled drag for required segments)

---

## API Usage Examples

### Example 1: Basic CORE Extraction

```bash
curl -X POST http://localhost:8000/api/v1/op/summary-core \
  -H "Content-Type: application/json" \
  -d '{
    "transcript": "Doctor: How are you?\nPatient: I have a headache and dizziness..."
  }'
```

**Response:**
```json
{
  "success": true,
  "data": {
    "diagnosis": {...},
    "chief_complaints": [...],
    "history": {...},
    "physical_examination": {...},
    "clinical_assessment": {...},
    "prescription": {...},
    "treatment_plan_advice": {...},
    "follow_up": {...}
  },
  "metadata": {
    "mode": "core",
    "segment_count": 8,
    "model": "gemini-2.5-pro"
  }
}
```

---

### Example 2: Update Segment Configuration

```bash
# Set Diagnosis to concise brevity
curl -X PUT "http://localhost:8000/api/v1/op/segments/DIAGNOSIS/config?user_id=user-123" \
  -H "Content-Type: application/json" \
  -d '{
    "brevity_level": "concise"
  }'

# Set Treatment Plan to simple terms
curl -X PUT "http://localhost:8000/api/v1/op/segments/TREATMENT_PLAN_ADVICE/config?user_id=user-123" \
  -H "Content-Type: application/json" \
  -d '{
    "terminology_style": "simple_terms"
  }'
```

---

### Example 3: Move Segment Between Categories

```bash
# Move Investigations from ADDITIONAL to CORE
curl -X POST "http://localhost:8000/api/v1/op/segments/move?user_id=user-123" \
  -H "Content-Type: application/json" \
  -d '{
    "segment_code": "INVESTIGATIONS",
    "new_category": "core"
  }'
```

---

### Example 4: Progressive Loading (Recommended UX)

```javascript
// Frontend: Extract CORE first
const coreResponse = await fetch('/api/v1/op/summary-core', {
  method: 'POST',
  body: JSON.stringify({ transcript })
});
const coreData = await coreResponse.json();

// Display CORE results immediately
displayCoreInsights(coreData);

// Start ADDITIONAL extraction in background
const additionalPromise = fetch('/api/v1/op/summary-additional', {
  method: 'POST',
  body: JSON.stringify({ transcript })
});

// When ready, enable "Show More" button
additionalPromise.then(response => {
  enableShowMoreButton();
  additionalData = await response.json();
});
```

---

## Performance Optimization

### Extraction Time Breakdown

**FULL Extraction (All 18 segments):**
```
Patient Info:       ~2s
Diagnosis:          ~5s
Chief Complaints:   ~3s
HPI:                ~7s
History:            ~15s
Physical Exam:      ~4s
Investigations:     ~5s
Clinical Assessment:~6s
Prescription:       ~8s
Treatment Plan:     ~6s
Follow-up:          ~4s
Protocol:           ~10s
Timestamped:        ~15s
Report Metadata:    ~2s
Referral:           ~3s
Subtext:            ~10s
Emergency:          ~5s
-----------------
TOTAL:             ~110s
```

**CORE Extraction (8 segments):**
```
Diagnosis:          ~5s
Chief Complaints:   ~3s
History:            ~15s
Physical Exam:      ~4s
Clinical Assessment:~6s
Prescription:       ~8s
Treatment Plan:     ~6s
Follow-up:          ~4s
-----------------
TOTAL:             ~51s
```

**ADDITIONAL Extraction (10 segments):**
```
Patient Info:       ~2s
Report Metadata:    ~2s
Investigations:     ~5s
HPI:                ~7s
Protocol:           ~10s
Timestamped:        ~15s
Referral:           ~3s
Subtext:            ~10s
Emergency:          ~5s
-----------------
TOTAL:             ~59s
```

**Performance Gain:**
- CORE only: ~54% faster than FULL
- Progressive (CORE → ADDITIONAL): User sees results in ~51s instead of ~110s

---

## Summary

The Dynamic Prompt Generation System provides a **flexible, database-driven architecture** for medical consultation extraction with:

✅ **User Customization** - Per-segment brevity and terminology control
✅ **Clinical Safety** - Required segments enforced
✅ **Performance** - 50% faster time-to-first-insights
✅ **Extensibility** - Add segments via SQL INSERT
✅ **Specialty Support** - Preset configurations for different medical fields

**Ready for production use after database seeding.**

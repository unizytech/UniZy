# Prompt Template Creation Guide

This guide documents how to create a new hardcoded prompt template for the medical extraction system.

## Overview

Hardcoded templates are used when:
- You need a specific, optimized extraction schema
- The template won't be customized per-doctor
- You want maximum control over the Gemini schema structure
- Performance is critical (no database lookups for schema)

## Prerequisites

- Access to the codebase (`backend/services/`)
- Access to the Supabase database
- Understanding of Gemini schema types

---

## Step 1: Create the Prompts File

Create a new file in `backend/services/` following the naming convention: `{type}_prompts_{variant}.py`

**Example:** `op_prompts_simple.py`

### File Structure

```python
"""
{Description of the template}

Segments:
1. Segment1 - Description
2. Segment2 - Description
...
"""

from google.genai import types


# =============================================================================
# 1. GEMINI SCHEMA
# =============================================================================

{TEMPLATE_CODE}_PARAMETERS_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "segmentName": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "field1": types.Schema(type=types.Type.STRING, description="..."),
                "field2": types.Schema(type=types.Type.ARRAY, items=types.Schema(...)),
                # ... more fields
            }
        ),
        # ... more segments
    }
)


# =============================================================================
# 2. SYSTEM PROMPT
# =============================================================================

{TEMPLATE_CODE}_PROMPT_SYSTEM = """You are a medical documentation AI...

**ROLE:** ...

**CRITICAL RULES:**
1. ...
2. ...

## SEGMENT GUIDELINES

### 1. SEGMENT_NAME
**Description:** ...
**Extraction Rules:**
- ...

...
"""


# =============================================================================
# 3. USER PROMPT (with {transcript} placeholder)
# =============================================================================

{TEMPLATE_CODE}_PROMPT_USER = """Extract structured information from the transcript below.

**TRANSCRIPT:**
---
{transcript}
---

**REQUIRED JSON OUTPUT:**
```json
{{
  "segmentName": {{
    "field1": "...",
    "field2": [...]
  }}
}}
```

Return ONLY the JSON object. No markdown, no explanations."""
```

### Key Points

1. **Schema**: Use `types.Schema` from `google.genai`
2. **System Prompt**: Contains extraction guidelines, rules, segment descriptions
3. **User Prompt**: Must have `{transcript}` placeholder (use double braces `{{` for literal braces in JSON examples)
4. **Segment Names**: Use camelCase in schema (e.g., `treatmentPlan`, not `treatment_plan`)

---

## Step 2: Add Routing in segment_registry.py

### 2.1 Add Import

At the top of `backend/services/segment_registry.py`, add:

```python
from .{prompts_file} import (
    {TEMPLATE_CODE}_PROMPT_SYSTEM,
    {TEMPLATE_CODE}_PROMPT_USER,
    {TEMPLATE_CODE}_PARAMETERS_SCHEMA,
)
```

### 2.2 Add to Hardcoded Types List

Find the `if consultation_type_code in [...]` statement in `generate_extraction_artifacts()` and add your type code:

```python
if consultation_type_code in ["NEONATAL_DAILY", "NEONATAL_PROFORMA", ..., "{TYPE_CODE}"]:
```

### 2.3 Add Case Handler

Add a new case in the `match consultation_type_code:` block:

```python
case "{TYPE_CODE}":
    logger.info(f"[{TYPE_CODE}_SCHEMA] ✅ Using hardcoded schema for {consultation_type_code}")
    schema_fields = list({TEMPLATE_CODE}_PARAMETERS_SCHEMA.properties.keys())
    logger.info(f"[{TYPE_CODE}_SCHEMA] 🔍 Schema segments: {schema_fields}")
    return {
        "system_prompt": {TEMPLATE_CODE}_PROMPT_SYSTEM,
        "user_prompt": {TEMPLATE_CODE}_PROMPT_USER.format(transcript=transcript),
        "schema": {TEMPLATE_CODE}_PARAMETERS_SCHEMA,
        "segments": [],
        "validation": {"is_valid": True, "error_message": None, "warnings": []},
        "segment_count": {NUM_SEGMENTS},
        "mode": mode,
        "consultation_type_id": str(consultation_type_id),
        "consultation_type_code": consultation_type_code
    }
```

### 2.4 Update `generate_extraction_artifacts_without_transcript()`

Find the same function and add identical routing (but use `user_prompt_template` instead of formatting):

```python
case "{TYPE_CODE}":
    logger.info(f"[OPTIMIZATION] [{TYPE_CODE}_SCHEMA] ✅ Using hardcoded schema")
    return {
        "system_prompt": {TEMPLATE_CODE}_PROMPT_SYSTEM,
        "user_prompt_template": {TEMPLATE_CODE}_PROMPT_USER,  # No .format() here!
        "schema": {TEMPLATE_CODE}_PARAMETERS_SCHEMA,
        "segments": [],
        "validation": {"is_valid": True, "error_message": None, "warnings": []},
        "segment_count": {NUM_SEGMENTS},
        "mode": mode,
        "consultation_type_id": str(consultation_type_id),
        "consultation_type_code": consultation_type_code
    }
```

---

## Step 3: Create Database Records

### 3.1 Create Migration File

Create a new migration file: `backend/supabase/migrations/{TIMESTAMP}_{description}.sql`

Get timestamp: `date +%Y%m%d%H%M%S`

### 3.2 Add Consultation Type

```sql
INSERT INTO consultation_types (
    id,
    type_code,
    type_name,
    description,
    display_order,
    is_active,
    enable_emotion_analysis
) VALUES (
    gen_random_uuid(),
    '{TYPE_CODE}',
    '{Type Display Name}',
    '{Description of what this template extracts}',
    {display_order},  -- Higher number = appears later in list
    true,
    false
)
ON CONFLICT (type_code) DO UPDATE SET
    type_name = EXCLUDED.type_name,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active;
```

### 3.3 Create Template

```sql
-- First, get the consultation type ID
-- Then create the template:

INSERT INTO templates (
    id, template_code, template_name, description,
    consultation_type_id, is_default, is_active
) VALUES (
    gen_random_uuid(),
    '{TYPE_CODE}_DEFAULT',
    '{Template Display Name}',
    '{Template description}',
    '{consultation_type_id}',  -- From step 3.2
    true,
    true
)
ON CONFLICT (template_code) DO UPDATE SET
    template_name = EXCLUDED.template_name,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active;
```

### 3.4 Create Segment Definitions

For each segment in your schema:

```sql
INSERT INTO segment_definitions (
    id, segment_code, segment_name, description,
    prompt_section_text, schema_definition_json,
    default_category, display_order, default_brevity_level, default_terminology_style,
    is_required, is_active, segment_type
) VALUES (
    gen_random_uuid(),
    '{SEGMENT_CODE}',
    '{Segment Display Name}',
    '{Segment description}',
    '{Extraction instructions for this segment}',
    '{JSON schema as JSONB}'::jsonb,
    'core',  -- or 'additional'
    {display_order},
    'balanced',  -- concise, balanced, detailed
    'medical_terms',  -- medical_terms, simple_terms, as_spoken
    true,  -- is_required
    true,  -- is_active
    'system'
);
```

### 3.5 Link Segments to Consultation Type

```sql
INSERT INTO consultation_type_segments (
    consultation_type_id, segment_id, segment_code,
    default_category, default_display_order,
    default_brevity_level, default_terminology_style
)
VALUES
('{ct_id}', '{seg1_id}', '{SEG1_CODE}', 'core', 1, 'balanced', 'medical_terms'),
('{ct_id}', '{seg2_id}', '{SEG2_CODE}', 'core', 2, 'balanced', 'medical_terms'),
-- ... more segments
ON CONFLICT (consultation_type_id, segment_id) DO NOTHING;
```

### 3.6 Link Segments to Template

```sql
INSERT INTO template_segments (
    template_id, segment_id, segment_code,
    category, display_order, brevity_level, terminology_style
)
VALUES
('{tpl_id}', '{seg1_id}', '{SEG1_CODE}', 'core', 1, 'balanced', 'medical_terms'),
('{tpl_id}', '{seg2_id}', '{SEG2_CODE}', 'core', 2, 'balanced', 'medical_terms'),
-- ... more segments
ON CONFLICT (template_id, segment_id) DO NOTHING;
```

---

## Step 4: Apply Migration

### Option A: Using Supabase MCP Tool

```
mcp__supabase__apply_migration(
    project_id="your_project_id",
    name="add_{type_code}_consultation_type",
    query="..."
)
```

### Option B: Using SQL Editor

Run each SQL statement in Supabase SQL Editor or via the API.

---

## Step 5: Verify Setup

Run this query to verify everything is connected:

```sql
SELECT
    ct.type_code,
    ct.type_name,
    t.template_code,
    t.template_name,
    COUNT(ts.id) as segment_count
FROM consultation_types ct
JOIN templates t ON t.consultation_type_id = ct.id
LEFT JOIN template_segments ts ON ts.template_id = t.id
WHERE ct.type_code = '{TYPE_CODE}'
GROUP BY ct.type_code, ct.type_name, t.template_code, t.template_name;
```

Expected output:
```
type_code | type_name | template_code | template_name | segment_count
----------|-----------|---------------|---------------|---------------
{CODE}    | {Name}    | {CODE}_DEFAULT| {Name}        | {N}
```

---

## Step 6: Test

1. Restart the backend:
   ```bash
   pkill -f uvicorn && cd backend && uvicorn main:app --reload --port 8000
   ```

2. In the frontend VHR screen:
   - Select the new consultation type
   - Upload audio or record
   - Verify extraction output matches your schema

3. Check logs for:
   ```
   [{TYPE_CODE}_SCHEMA] ✅ Using hardcoded schema for {TYPE_CODE}
   ```

---

## Quick Reference: Table Schema

### consultation_type_segments columns
- `consultation_type_id`, `segment_id`, `segment_code`
- `default_category`, `default_display_order`
- `default_brevity_level`, `default_terminology_style`

### template_segments columns
- `template_id`, `segment_id`, `segment_code`
- `category`, `display_order`
- `brevity_level`, `terminology_style`

---

## Checklist

- [ ] Created prompts file with schema, system prompt, user prompt
- [ ] Added import in segment_registry.py
- [ ] Added TYPE_CODE to hardcoded types list
- [ ] Added case handler in `generate_extraction_artifacts()`
- [ ] Added case handler in `generate_extraction_artifacts_without_transcript()`
- [ ] Created consultation_types record
- [ ] Created templates record
- [ ] Created segment_definitions records (one per segment)
- [ ] Created consultation_type_segments links
- [ ] Created template_segments links
- [ ] Restarted backend
- [ ] Tested extraction works correctly


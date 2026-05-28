# Multi-LLM Support for Extraction & Merge Pipeline

**Created:** 2026-01-22
**Status:** Planned (not implemented)

## Overview
Add support for Claude Sonnet 3.5 and GPT-4o alongside existing Gemini models for extraction and merge operations. Provider is inferred from model name prefix (no DB schema changes).

## Provider Detection Strategy
```python
def get_provider(model: str) -> str:
    if model.startswith("claude-"):
        return "anthropic"
    elif model.startswith("gpt-"):
        return "openai"
    else:
        return "gemini"  # default
```

## Files to Modify/Create

### 1. New File: `backend/services/llm_client_factory.py`
Create unified LLM client factory with provider-specific implementations.

```python
# Provider detection
# Client initialization for each provider
# Common interface: async def generate_json(system_prompt, user_prompt, schema, model, temperature)
```

**Key Components:**
- `get_provider(model: str) -> str` - Detect provider from model name
- `GeminiClient` - Existing logic from gemini_client_factory.py
- `AnthropicClient` - New client using `anthropic` SDK
- `OpenAIClient` - New client using `openai` SDK
- `generate_structured_output()` - Unified interface

### 2. New File: `backend/services/schema_adapter.py`
Handle schema conversion per provider.

| Provider | Structured Output Method |
|----------|-------------------------|
| Gemini | `response_schema` with `types.Schema` object |
| OpenAI | `response_format={"type": "json_schema", "json_schema": {...}}` |
| Claude | Tool use with JSON Schema OR prompt engineering + JSON parse |

**Functions:**
- `adapt_schema_for_gemini(json_schema)` - Move existing `_json_schema_to_gemini_schema()` here
- `adapt_schema_for_openai(json_schema)` - Wrap in OpenAI's format
- `adapt_schema_for_claude(json_schema)` - Create tool definition

### 3. Modify: `backend/services/gemini_service.py`
Update `extract_summary_dynamic()` (line 3510) to route to correct provider.

**Changes:**
- Import `llm_client_factory`
- At line ~3798, replace direct Gemini call with:
```python
provider = get_provider(model)
if provider == "gemini":
    # existing Gemini logic
elif provider == "anthropic":
    result = await anthropic_extract(system_prompt, user_prompt, schema, model)
elif provider == "openai":
    result = await openai_extract(system_prompt, user_prompt, schema, model)
```

### 4. Modify: `backend/services/merge_service.py`
Update merge calls to support multi-LLM.

**Affected functions:**
- `perform_ai_merge()` - Add provider routing
- `perform_split_ai_merge()` - Add provider routing

### 5. New: Environment Variables
Add to `backend/.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

### 6. New: Dependencies
Add to `backend/requirements.txt`:
```
anthropic>=0.34.0
openai>=1.50.0
```

## Implementation Details

### Anthropic/Claude Integration
```python
from anthropic import AsyncAnthropic

async def claude_extract(system_prompt, user_prompt, schema, model, temperature=0.2):
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Option A: Tool use for structured output
    response = await client.messages.create(
        model=model,
        max_tokens=8192,
        system=system_prompt,
        tools=[{
            "name": "extract_medical_data",
            "description": "Extract structured medical data",
            "input_schema": schema  # Standard JSON Schema works
        }],
        tool_choice={"type": "tool", "name": "extract_medical_data"},
        messages=[{"role": "user", "content": user_prompt}]
    )
    return response.content[0].input  # Tool call returns JSON
```

### OpenAI/GPT-4o Integration
```python
from openai import AsyncOpenAI

async def openai_extract(system_prompt, user_prompt, schema, model, temperature=0.2):
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = await client.chat.completions.create(
        model=model,
        temperature=temperature,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "medical_extraction",
                "strict": True,
                "schema": schema
            }
        },
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    return json.loads(response.choices[0].message.content)
```

## Processing Modes Configuration
Users can now set extraction_model to any of:
- `gemini-2.5-flash`, `gemini-2.5-pro` (existing)
- `claude-3-5-sonnet-20241022`, `claude-3-opus-20240229`
- `gpt-4o`, `gpt-4o-mini`

## Prompt/Schema Compatibility
**No changes needed to templates table.** The existing:
- `assembled_full_prompt` (text) - Works as-is for all providers
- `assembled_schema_json` (JSON Schema) - Works for OpenAI/Claude directly; converted for Gemini at runtime

## Verification Plan
1. Add new environment variables and install dependencies
2. Update a processing mode to use `claude-3-5-sonnet-20241022` for extraction_model
3. Run extraction via VHR screen
4. Verify JSON output matches schema
5. Repeat for `gpt-4o`
6. Test merge with non-Gemini model

## Risk Mitigation
- **Latency**: Claude/GPT may have different latencies - monitor via existing timing logs
- **Schema constraints**: Claude tool use is strict; OpenAI json_schema is strict - may need to relax some constraints
- **Cost**: Claude/GPT pricing differs - usage logging already in place
- **Fallback**: If non-Gemini fails, can fall back to Gemini default

## Estimated Scope
| File | Change Type | Complexity |
|------|-------------|------------|
| `llm_client_factory.py` | New | Medium |
| `schema_adapter.py` | New | Low |
| `gemini_service.py` | Modify | Medium |
| `merge_service.py` | Modify | Low |
| `requirements.txt` | Modify | Trivial |
| `.env` | Modify | Trivial |

## Key Files Reference
- `backend/services/gemini_service.py:3510` - `extract_summary_dynamic()` main extraction function
- `backend/services/gemini_service.py:3798` - Gemini API call location
- `backend/services/segment_registry.py:923` - `_json_schema_to_gemini_schema()` schema converter
- `backend/services/merge_service.py` - Merge operations
- `backend/services/gemini_client_factory.py` - Current Gemini client factory
- `backend/routers/processing_modes.py` - Processing modes CRUD

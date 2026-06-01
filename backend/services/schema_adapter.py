"""
Schema Adapter for Multi-LLM Support

Handles schema format conversion between providers:
- Gemini: Uses google.genai types.Schema objects (existing conversion in segment_registry.py)
- OpenAI: Wraps JSON Schema in response_format structure with strict mode
- Claude: Uses JSON Schema as tool input_schema for structured output via tool use

Also provides utility to convert Gemini Schema objects back to standard JSON Schema
for use with non-Gemini providers.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def adapt_schema_for_openai(json_schema: Dict[str, Any], name: str = "extraction") -> Dict[str, Any]:
    """
    Wrap a standard JSON Schema in OpenAI's response_format structure.

    OpenAI structured outputs require:
    - type: "json_schema"
    - json_schema.name: identifier for the schema
    - json_schema.strict: True for guaranteed schema adherence
    - json_schema.schema: the actual JSON Schema

    Args:
        json_schema: Standard JSON Schema dict
        name: Name identifier for the schema (default: "extraction")

    Returns:
        OpenAI response_format dict
    """
    # Clean schema for OpenAI strict mode compatibility
    cleaned_schema = _clean_schema_for_openai_strict(json_schema)

    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": cleaned_schema
        }
    }


def adapt_schema_for_claude(json_schema: Dict[str, Any], name: str = "extract_medical_data") -> Dict[str, Any]:
    """
    Create a Claude tool definition for structured output via tool use.

    Claude enforces structured output by forcing a specific tool call.
    The tool's input_schema is a standard JSON Schema.

    Args:
        json_schema: Standard JSON Schema dict
        name: Tool name (default: "extract_medical_data")

    Returns:
        Tool definition dict for Claude's tools parameter
    """
    return {
        "name": name,
        "description": "Extract structured medical data from the consultation transcript",
        "input_schema": json_schema
    }


def gemini_schema_to_json_schema(gemini_schema) -> Dict[str, Any]:
    """
    Convert a Gemini types.Schema object back to standard JSON Schema dict.

    This is needed when merge_service has a Gemini Schema (from generate_merge_artifacts)
    but needs to route to a non-Gemini provider.

    Args:
        gemini_schema: google.genai.types.Schema object

    Returns:
        Standard JSON Schema dict
    """
    from google.genai import types

    if gemini_schema is None:
        return {"type": "object", "properties": {}}

    schema_type = gemini_schema.type if hasattr(gemini_schema, 'type') else None

    # Map Gemini types back to JSON Schema types
    type_mapping = {
        types.Type.STRING: "string",
        types.Type.NUMBER: "number",
        types.Type.INTEGER: "integer",
        types.Type.BOOLEAN: "boolean",
        types.Type.ARRAY: "array",
        types.Type.OBJECT: "object",
    }

    json_type = type_mapping.get(schema_type, "string")
    result = {"type": json_type}

    # Add description if present
    if hasattr(gemini_schema, 'description') and gemini_schema.description:
        result["description"] = gemini_schema.description

    # Handle object properties
    if json_type == "object" and hasattr(gemini_schema, 'properties') and gemini_schema.properties:
        result["properties"] = {}
        for prop_name, prop_schema in gemini_schema.properties.items():
            result["properties"][prop_name] = gemini_schema_to_json_schema(prop_schema)
        # All properties required (matches Gemini behavior)
        result["required"] = list(result["properties"].keys())

    # Handle array items
    if json_type == "array" and hasattr(gemini_schema, 'items') and gemini_schema.items:
        result["items"] = gemini_schema_to_json_schema(gemini_schema.items)

    return result


def _clean_schema_for_openai_strict(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean a JSON Schema for OpenAI strict mode compatibility.

    OpenAI strict mode requirements:
    - All objects must have "additionalProperties": false
    - All properties must be listed in "required"
    - No unsupported keywords (pattern, format, minimum, maximum, etc.)

    Args:
        schema: Standard JSON Schema dict

    Returns:
        Cleaned schema compatible with OpenAI strict mode
    """
    if not isinstance(schema, dict):
        return schema

    result = {}
    schema_type = schema.get("type", "string")

    # Copy type
    result["type"] = schema_type

    # Copy description if present
    if "description" in schema:
        result["description"] = schema["description"]

    if schema_type == "object":
        properties = schema.get("properties", {})
        if properties:
            result["properties"] = {}
            for prop_name, prop_schema in properties.items():
                result["properties"][prop_name] = _clean_schema_for_openai_strict(prop_schema)
            # OpenAI strict mode: all properties required
            result["required"] = list(result["properties"].keys())
        # OpenAI strict mode: must have additionalProperties: false
        result["additionalProperties"] = False

    elif schema_type == "array":
        if "items" in schema:
            result["items"] = _clean_schema_for_openai_strict(schema["items"])

    # Skip unsupported keywords: enum, pattern, format, minimum, maximum, minItems, maxItems
    # These are already stripped by _json_schema_to_gemini_schema for Gemini,
    # and OpenAI strict mode also doesn't support them well

    return result

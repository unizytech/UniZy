"""
Template Assembly Service - Pre-assembled Extraction Guidelines & Schema

This module handles:
- Assembly of complete extraction prompts (base system prompt + segment guidelines)
- Assembly of combined JSON schemas for all segments
- Async triggers for re-assembly when source data changes
- Helper functions to find affected templates

The assembled artifacts are stored in the templates table and used during extraction
to avoid runtime prompt/schema generation overhead.

Fallback behavior:
- If assembled_full_prompt is NULL → dynamically generate using segment_registry.py
- If assembled_schema_json is NULL → dynamically generate using segment_registry.py
"""

import uuid
import asyncio
import logging
import json
import re
import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from .supabase_service import supabase

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================

def _to_camel_case(snake_str: str) -> str:
    """Convert snake_case or space-separated string to camelCase"""
    # Split on underscores or spaces
    components = re.split(r'[_\s]+', snake_str.lower())
    # Filter out empty strings from consecutive delimiters
    components = [c for c in components if c]
    if not components:
        return snake_str.lower()
    return components[0] + ''.join(x.title() for x in components[1:])


def get_templates_using_segment(segment_id: uuid.UUID) -> List[uuid.UUID]:
    """
    Find all templates that include a specific segment.

    Args:
        segment_id: The segment definition ID

    Returns:
        List of template IDs that use this segment
    """
    try:
        result = supabase.table("template_segments").select(
            "template_id"
        ).eq("segment_id", str(segment_id)).execute()

        if not result.data:
            return []

        # Deduplicate template IDs
        template_ids = list(set(uuid.UUID(row["template_id"]) for row in result.data))
        logger.debug(f"[ASSEMBLY] Found {len(template_ids)} templates using segment {segment_id}")
        return template_ids
    except Exception as e:
        logger.error(f"[ASSEMBLY] Error finding templates for segment {segment_id}: {e}")
        return []


def get_templates_for_consultation_type(consultation_type_id: uuid.UUID) -> List[uuid.UUID]:
    """
    Find all templates for a consultation type.

    Args:
        consultation_type_id: The consultation type ID

    Returns:
        List of template IDs for this consultation type
    """
    try:
        result = supabase.table("templates").select(
            "id"
        ).eq("consultation_type_id", str(consultation_type_id)).eq("is_active", True).execute()

        if not result.data:
            return []

        template_ids = [uuid.UUID(row["id"]) for row in result.data]
        logger.debug(f"[ASSEMBLY] Found {len(template_ids)} templates for consultation type {consultation_type_id}")
        return template_ids
    except Exception as e:
        logger.error(f"[ASSEMBLY] Error finding templates for consultation type {consultation_type_id}: {e}")
        return []


def get_template_by_id(template_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get template record by ID.

    Args:
        template_id: Template UUID

    Returns:
        Template record or None
    """
    try:
        result = supabase.table("templates").select("*").eq("id", str(template_id)).single().execute()
        return result.data
    except Exception as e:
        logger.error(f"[ASSEMBLY] Error getting template {template_id}: {e}")
        return None


# ============================================================================
# Prompt Modifiers (replicated from segment_registry.py for standalone use)
# ============================================================================

def apply_brevity_modifier(prompt_text: str, brevity_level: str) -> str:
    """Apply brevity level modifier to prompt text."""
    if brevity_level == "concise":
        return f"""
{prompt_text}

**BREVITY OVERRIDE (USER PREFERENCE): CONCISE MODE**
- Keep this segment ultra-brief (1-2 sentences or bullet points maximum)
- Omit detailed explanations unless clinically critical
- Focus on key findings only
"""
    elif brevity_level == "detailed":
        return f"""
{prompt_text}

**VERBOSITY OVERRIDE (USER PREFERENCE): DETAILED MODE**
- Provide comprehensive details for this segment
- Include clinical reasoning, context, and relevant background
- Expand on key findings with supporting information
"""
    else:  # balanced (default)
        return prompt_text


def apply_terminology_modifier(prompt_text: str, terminology_style: str) -> str:
    """Apply terminology style modifier to prompt text."""
    if terminology_style == "simple_terms":
        return f"""
{prompt_text}

**TERMINOLOGY OVERRIDE (USER PREFERENCE): SIMPLE/STUDENT-FRIENDLY TERMS**
- Use simple, student-friendly language instead of medical jargon
- Examples: "stomach pain" instead of "abdominal pain", "breathlessness" instead of "dyspnea"
- Avoid complex medical abbreviations (explain them if used)
- This segment should be easily understandable by students
"""
    elif terminology_style == "as_spoken":
        return f"""
{prompt_text}

**TERMINOLOGY OVERRIDE (USER PREFERENCE): AS SPOKEN IN TRANSCRIPT**
- Report terms exactly as spoken in the conversation
- Do NOT translate lay terms to medical terminology
- Examples: If student says "stomach", write "stomach" (not "abdomen")
- Preserve the original language style and phrasing
"""
    else:  # medical_terms (default)
        return prompt_text


# ============================================================================
# Core Assembly Functions
# ============================================================================

def assemble_template_full_prompt(
    template_id: uuid.UUID,
    trigger_source: str = "manual"
) -> Dict[str, Any]:
    """
    Assemble complete extraction prompt for a template.

    Steps:
    1. Load template to get consultation_type_id (error if NULL)
    2. Get active system_prompt_configuration for that consultation type
    3. Load template_segments joined with segment_definitions
    4. Filter: is_active=True (include ALL categories including 'excluded')
    5. Sort by display_order
    6. For each segment: apply brevity + terminology modifiers
    7. Concatenate: base_system_prompt + segment_guidelines
    8. Update templates table with assembled result

    Note: Excluded segments ARE included in pre-assembled prompts so they're
    available if category is changed later. Runtime filtering in get_segment_definitions
    handles actual exclusion during extraction.

    Args:
        template_id: Template UUID to assemble
        trigger_source: What triggered this assembly (for tracking)

    Returns:
        Dict with assembled_full_prompt, prompt_assembled_at, prompt_trigger_source, system_prompt_config_id

    Raises:
        ValueError: If template has no consultation_type_id or no active system prompt config
    """
    logger.debug(f"[PROMPT_ASSEMBLY] Starting assembly for template {template_id}")

    # Step 1: Load template
    template = get_template_by_id(template_id)
    if not template:
        raise ValueError(f"Template {template_id} not found")

    consultation_type_id = template.get("consultation_type_id")
    if not consultation_type_id:
        raise ValueError(f"Template {template_id} has no consultation_type_id - templates cannot exist without a consultation type")

    template_code = template.get("template_code", "UNKNOWN")
    logger.debug(f"[PROMPT_ASSEMBLY] Template: {template_code}, consultation_type_id: {consultation_type_id}")

    # Step 2: Get consultation type code and active system prompt config
    ct_result = supabase.table("consultation_types").select(
        "type_code"
    ).eq("id", str(consultation_type_id)).single().execute()

    if not ct_result.data:
        raise ValueError(f"Consultation type {consultation_type_id} not found")

    consultation_type_code = ct_result.data["type_code"]

    # Get active system prompt configuration
    config_result = supabase.table('consultation_type_system_prompts').select(
        '*, system_prompt_configurations(*)'
    ).eq('consultation_type_code', consultation_type_code).eq('is_active', True).single().execute()

    if not config_result.data:
        raise ValueError(f"No active system prompt configuration for consultation type '{consultation_type_code}'")

    config_data = config_result.data.get('system_prompt_configurations', {})
    base_system_prompt = config_data.get('assembled_system_prompt')
    system_prompt_config_id = config_data.get('id')

    if not base_system_prompt:
        raise ValueError(f"Active system prompt configuration for '{consultation_type_code}' has no assembled_system_prompt")

    logger.debug(f"[PROMPT_ASSEMBLY] Using system prompt config: {config_data.get('config_name', 'Unknown')}")

    # Step 3: Load template_segments joined with segment_definitions
    segments_result = supabase.table("template_segments").select(
        "*, segment_definitions!inner(*)"
    ).eq("template_id", str(template_id)).execute()

    if not segments_result.data:
        logger.warning(f"[PROMPT_ASSEMBLY] No segments found for template {template_id}")
        # Still assemble with just the base prompt
        assembled_full_prompt = base_system_prompt
    else:
        # Step 4 & 5: Filter and sort segments
        segments = []
        for row in segments_result.data:
            segment_def = row.get("segment_definitions", {})

            # Filter: is_active=True only (include all categories including 'excluded')
            # Excluded segments are included in pre-assembled prompts so they're available
            # if category is changed later. Runtime filtering handles actual exclusion.
            if not segment_def.get("is_active", True):
                continue

            segments.append({
                "segment_name": segment_def.get("segment_name", "Unknown Segment"),
                "segment_code": segment_def.get("segment_code", "UNKNOWN"),
                "prompt_section_text": segment_def.get("prompt_section_text", "Extract relevant data for this segment."),
                "brevity_level": row.get("brevity_level") or segment_def.get("default_brevity_level", "balanced"),
                "terminology_style": row.get("terminology_style") or segment_def.get("default_terminology_style", "medical_terms"),
                "display_order": row.get("display_order", 999),
            })

        # Sort by display_order
        segments.sort(key=lambda s: s.get("display_order", 999))

        logger.debug(f"[PROMPT_ASSEMBLY] Processing {len(segments)} segments")

        # Step 6: Build segment guidelines
        segment_guidelines = "\n## EXTRACTION GUIDELINES BY SEGMENT\n\n"

        for idx, segment in enumerate(segments, 1):
            segment_name = segment["segment_name"]
            prompt_text = segment["prompt_section_text"]
            brevity_level = segment["brevity_level"]
            terminology_style = segment["terminology_style"]

            # Apply modifiers
            prompt_text = apply_brevity_modifier(prompt_text, brevity_level)
            prompt_text = apply_terminology_modifier(prompt_text, terminology_style)

            # Substitute radiology library placeholders. Done at assembly time
            # so the cached assembled_full_prompt is complete and there is zero
            # extraction-time string-scan cost.
            if "{{LIBRARY_PLAN}}" in prompt_text or "{{LIBRARY_TOXICITY}}" in prompt_text:
                from .radiology_library_service import (
                    render_plan_library_block,
                    render_toxicity_library_block,
                )
                if "{{LIBRARY_PLAN}}" in prompt_text:
                    prompt_text = prompt_text.replace(
                        "{{LIBRARY_PLAN}}",
                        render_plan_library_block(template_id),
                    )
                if "{{LIBRARY_TOXICITY}}" in prompt_text:
                    prompt_text = prompt_text.replace(
                        "{{LIBRARY_TOXICITY}}",
                        render_toxicity_library_block(template_id),
                    )

            segment_guidelines += f"### {idx}. {segment_name.upper()}\n\n{prompt_text}\n\n---\n\n"

        # Step 7: Concatenate
        assembled_full_prompt = base_system_prompt + segment_guidelines

    # Step 8: Compute hash for change detection
    prompt_assembly_hash = hashlib.sha256(assembled_full_prompt.encode()).hexdigest()

    # Step 9: Update templates table
    now = datetime.now(timezone.utc).isoformat()

    update_result = supabase.table("templates").update({
        "assembled_full_prompt": assembled_full_prompt,
        "prompt_assembled_at": now,
        "prompt_trigger_source": trigger_source,
        "system_prompt_config_id": system_prompt_config_id,
        "prompt_assembly_hash": prompt_assembly_hash,
    }).eq("id", str(template_id)).execute()

    logger.info(f"[PROMPT_ASSEMBLY] ✅ Assembled prompt for template {template_code} ({len(assembled_full_prompt)} chars, hash={prompt_assembly_hash[:12]}...)")

    return {
        "assembled_full_prompt": assembled_full_prompt,
        "prompt_assembled_at": now,
        "prompt_trigger_source": trigger_source,
        "system_prompt_config_id": system_prompt_config_id,
        "prompt_assembly_hash": prompt_assembly_hash,
        "template_id": str(template_id),
        "template_code": template_code,
    }


def assemble_template_schema(
    template_id: uuid.UUID,
    trigger_source: str = "manual"
) -> Dict[str, Any]:
    """
    Assemble combined JSON schema for a template.

    Steps:
    1. Load template to get consultation_type_id (error if NULL)
    2. Load template_segments joined with segment_definitions
    3. Filter: is_active=True (include ALL categories including 'excluded')
    4. Sort by display_order
    5. For each segment: get schema_definition_json, convert to camelCase property name
    6. Build final schema object (type=object, properties, required)
    7. Update templates.assembled_schema_json with result

    Note: Excluded segments ARE included in pre-assembled schemas so they're
    available if category is changed later. Runtime filtering handles actual exclusion.

    Args:
        template_id: Template UUID to assemble
        trigger_source: What triggered this assembly (for tracking)

    Returns:
        Dict with assembled_schema_json, schema_assembled_at, schema_trigger_source

    Raises:
        ValueError: If template has no consultation_type_id
    """
    logger.debug(f"[SCHEMA_ASSEMBLY] Starting assembly for template {template_id}")

    # Step 1: Load template
    template = get_template_by_id(template_id)
    if not template:
        raise ValueError(f"Template {template_id} not found")

    consultation_type_id = template.get("consultation_type_id")
    if not consultation_type_id:
        raise ValueError(f"Template {template_id} has no consultation_type_id - templates cannot exist without a consultation type")

    template_code = template.get("template_code", "UNKNOWN")
    logger.debug(f"[SCHEMA_ASSEMBLY] Template: {template_code}")

    # Step 2: Load template_segments joined with segment_definitions
    segments_result = supabase.table("template_segments").select(
        "*, segment_definitions!inner(*)"
    ).eq("template_id", str(template_id)).execute()

    properties = {}
    excluded_segment_codes = []  # Track segments with category='excluded'

    if segments_result.data:
        # Step 3 & 4: Filter and sort segments
        segments = []
        for row in segments_result.data:
            segment_def = row.get("segment_definitions", {})

            # Filter: is_active=True only (include all categories including 'excluded')
            # Excluded segments are included in pre-assembled schemas so they're available
            # if category is changed later. Runtime filtering handles actual exclusion.
            if not segment_def.get("is_active", True):
                continue

            # Get category from template_segments (priority) or segment_definitions (fallback)
            category = row.get("category") or segment_def.get("default_category", "additional")
            segment_code = segment_def.get("segment_code", "UNKNOWN")

            # Track excluded segments for response filtering
            if category == "excluded":
                excluded_segment_codes.append(segment_code)

            segments.append({
                "segment_code": segment_code,
                "schema_definition_json": segment_def.get("schema_definition_json", {}),
                "display_order": row.get("display_order", 999),
            })

        # Sort by display_order
        segments.sort(key=lambda s: s.get("display_order", 999))

        logger.debug(f"[SCHEMA_ASSEMBLY] Processing {len(segments)} segments")

        # Step 5: Build properties
        for segment in segments:
            segment_code = segment["segment_code"]
            schema_json = segment["schema_definition_json"]

            # Handle string schema_json
            if isinstance(schema_json, str):
                try:
                    schema_json = json.loads(schema_json)
                except json.JSONDecodeError as e:
                    logger.warning(f"[SCHEMA_ASSEMBLY] Failed to parse schema_json for {segment_code}: {e}")
                    schema_json = {"type": "string", "description": f"Segment data for {segment_code}"}

            # Convert segment_code to camelCase for property name
            field_name = _to_camel_case(segment_code)

            # Add segment schema to properties
            properties[field_name] = schema_json

    # Step 6: Build combined schema (JSON representation)
    assembled_schema_json = {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys())
    }

    # Step 7: Compute hash for change detection
    schema_json_str = json.dumps(assembled_schema_json, sort_keys=True)
    schema_assembly_hash = hashlib.sha256(schema_json_str.encode()).hexdigest()

    # Step 8: Update templates table
    now = datetime.now(timezone.utc).isoformat()

    update_result = supabase.table("templates").update({
        "assembled_schema_json": assembled_schema_json,
        "schema_assembled_at": now,
        "schema_trigger_source": trigger_source,
        "schema_assembly_hash": schema_assembly_hash,
        "excluded_segment_codes": excluded_segment_codes,  # Pre-computed for zero-latency filtering
    }).eq("id", str(template_id)).execute()

    logger.info(f"[SCHEMA_ASSEMBLY] ✅ Assembled schema for template {template_code} ({len(properties)} properties, hash={schema_assembly_hash[:12]}...)")

    return {
        "assembled_schema_json": assembled_schema_json,
        "schema_assembled_at": now,
        "schema_trigger_source": trigger_source,
        "schema_assembly_hash": schema_assembly_hash,
        "template_id": str(template_id),
        "template_code": template_code,
        "property_count": len(properties),
    }


# ============================================================================
# Async Trigger Function
# ============================================================================

async def trigger_reassembly_async(
    template_ids: List[uuid.UUID],
    trigger_source: str,
    include_audio: bool = True
) -> None:
    """
    Asynchronously reassemble prompt, schema, and optionally audio artifacts for templates.

    Uses the same trigger for all change types - simplifies hook integration.
    All hooks call this single function regardless of what changed.

    Args:
        template_ids: List of template UUIDs to reassemble
        trigger_source: What triggered this assembly (for tracking)
        include_audio: Whether to also reassemble audio prompts/schemas (default: True)
    """
    if not template_ids:
        logger.debug(f"[ASSEMBLY] No templates to reassemble for trigger: {trigger_source}")
        return

    logger.info(f"[ASSEMBLY] Starting async reassembly for {len(template_ids)} templates (trigger: {trigger_source})")

    async def reassemble_single_template(template_id: uuid.UUID) -> None:
        """Reassemble a single template - runs in thread pool for parallelism."""
        try:
            # Assemble extraction prompt and schema (run in thread to not block)
            await asyncio.to_thread(assemble_template_full_prompt, template_id, trigger_source)
            await asyncio.to_thread(assemble_template_schema, template_id, trigger_source)

            # Assemble audio emotion prompt and schema (if enabled for this template)
            if include_audio:
                try:
                    await asyncio.to_thread(assemble_template_audio_prompt, template_id, trigger_source)
                    await asyncio.to_thread(assemble_template_audio_schema, template_id, trigger_source)
                except Exception as audio_e:
                    # Audio assembly failure shouldn't block standard assembly
                    logger.warning(f"[ASSEMBLY] Audio assembly failed for {template_id}: {audio_e}")

            logger.debug(f"[ASSEMBLY] Reassembled template {template_id} (prompt + schema + audio)")
        except Exception as e:
            logger.error(f"[ASSEMBLY] ❌ Failed to reassemble template {template_id}: {e}")

    # Run all template assemblies in parallel
    await asyncio.gather(*[reassemble_single_template(tid) for tid in template_ids])


# ============================================================================
# Initial Population / Bulk Operations
# ============================================================================

async def assemble_all_templates() -> Dict[str, Any]:
    """
    Assemble BOTH prompt and schema for all active templates.
    Run once after migration or for bulk refresh.

    Returns:
        Dict with success count, failed count, and error details
    """
    logger.info("[ASSEMBLY] Starting bulk assembly for all active templates")

    templates_result = supabase.table("templates").select(
        "id, template_code"
    ).eq("is_active", True).execute()

    if not templates_result.data:
        logger.debug("[ASSEMBLY] No active templates found")
        return {"success": 0, "failed": 0, "errors": [], "message": "No active templates found"}

    results = {"success": 0, "failed": 0, "errors": []}

    for template in templates_result.data:
        try:
            template_id = uuid.UUID(template["id"])
            template_code = template.get("template_code", "UNKNOWN")

            assemble_template_full_prompt(template_id, "initial_population")
            assemble_template_schema(template_id, "initial_population")

            results["success"] += 1
            logger.debug(f"[ASSEMBLY] Assembled template: {template_code}")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "template_id": template["id"],
                "template_code": template.get("template_code", "UNKNOWN"),
                "error": str(e)
            })
            logger.error(f"[ASSEMBLY] ❌ Failed to assemble template {template['id']}: {e}")

    logger.info(f"[ASSEMBLY] Bulk assembly complete: {results['success']} success, {results['failed']} failed")

    return results


def assemble_single_template(template_id: uuid.UUID, trigger_source: str = "manual") -> Dict[str, Any]:
    """
    Assemble both prompt and schema for a single template (synchronous).

    Args:
        template_id: Template UUID
        trigger_source: What triggered this assembly

    Returns:
        Combined result from both assemblies
    """
    prompt_result = assemble_template_full_prompt(template_id, trigger_source)
    schema_result = assemble_template_schema(template_id, trigger_source)

    return {
        "template_id": str(template_id),
        "template_code": prompt_result.get("template_code"),
        "prompt_assembled_at": prompt_result.get("prompt_assembled_at"),
        "schema_assembled_at": schema_result.get("schema_assembled_at"),
        "property_count": schema_result.get("property_count", 0),
        "trigger_source": trigger_source,
    }


# ============================================================================
# Audio Emotion Prompt Assembly Functions
# ============================================================================
# NOTE: Audio emotion base prompts (AUDIO_EMOTION_BASE_PROMPT_STANDALONE and
# AUDIO_EMOTION_BASE_PROMPT_COMBINED) have been moved to the database.
# They are stored in system_prompt_components table and retrieved via
# system_prompt_configurations. See migration:
# 20251226090000_add_audio_emotion_base_prompt_components.sql
# ============================================================================


def assemble_template_audio_prompt(
    template_id: uuid.UUID,
    trigger_source: str = "manual"
) -> Dict[str, Any]:
    """
    Assemble audio emotion analysis prompt for a template.

    Steps:
    1. Load template to get consultation_type_id
    2. Check if consultation type has emotion analysis enabled
    3. Load all AUDIO_ segments from segment_definitions
    4. Build combined system prompt (base + segment instructions)
    5. Store in templates.assembled_audio_prompt

    Args:
        template_id: Template UUID to assemble
        trigger_source: What triggered this assembly (for tracking)

    Returns:
        Dict with assembled_audio_prompt, audio_prompt_assembled_at, etc.

    Raises:
        ValueError: If template not found or consultation type invalid
    """
    logger.debug(f"[AUDIO_PROMPT_ASSEMBLY] Starting assembly for template {template_id}")

    # Step 1: Load template
    template = get_template_by_id(template_id)
    if not template:
        raise ValueError(f"Template {template_id} not found")

    consultation_type_id = template.get("consultation_type_id")
    if not consultation_type_id:
        raise ValueError(f"Template {template_id} has no consultation_type_id")

    template_code = template.get("template_code", "UNKNOWN")

    # Step 2: Check if emotion analysis is enabled for this consultation type
    ct_result = supabase.table("consultation_types").select(
        "type_code, enable_emotion_analysis"
    ).eq("id", str(consultation_type_id)).single().execute()

    if not ct_result.data:
        raise ValueError(f"Consultation type {consultation_type_id} not found")

    emotion_enabled = ct_result.data.get("enable_emotion_analysis", False)

    # Assemble audio prompts if emotion analysis is enabled
    # Audio prompts are used when skip_transcription=true (audio-only mode)
    if not emotion_enabled:
        logger.debug(
            f"[AUDIO_PROMPT_ASSEMBLY] Skipping - emotion analysis not enabled "
            f"for consultation type {ct_result.data.get('type_code')}"
        )
        return {
            "assembled_audio_prompt": None,
            "audio_prompt_assembled_at": None,
            "audio_prompt_trigger_source": trigger_source,
            "template_id": str(template_id),
            "template_code": template_code,
            "skipped": True,
            "reason": "Emotion analysis not enabled"
        }

    # Step 3: Load all AUDIO_ segments from segment_definitions
    segments_result = supabase.table("segment_definitions").select(
        "segment_code, segment_name, prompt_section_text, display_order"
    ).like("segment_code", "AUDIO_%").eq("is_active", True).order("display_order").execute()

    if not segments_result.data:
        logger.warning(f"[AUDIO_PROMPT_ASSEMBLY] No AUDIO_ segments found in segment_definitions")
        return {
            "assembled_audio_prompt": None,
            "audio_prompt_assembled_at": None,
            "audio_prompt_trigger_source": trigger_source,
            "template_id": str(template_id),
            "template_code": template_code,
            "skipped": True,
            "reason": "No AUDIO_ segments found"
        }

    # Step 4: Build combined prompt
    segment_guidelines = ""
    for idx, segment in enumerate(segments_result.data, 1):
        segment_name = segment.get("segment_name", segment["segment_code"])
        prompt_text = segment.get("prompt_section_text", "")

        if prompt_text:
            segment_guidelines += f"{prompt_text}\n\n---\n\n"

    # Store only the segment-specific guidelines (base prompt will be prepended at runtime)
    assembled_audio_prompt = segment_guidelines

    # Step 5: Compute hash for change detection
    audio_prompt_hash = hashlib.sha256(assembled_audio_prompt.encode()).hexdigest()

    # Step 6: Update templates table
    now = datetime.now(timezone.utc).isoformat()

    supabase.table("templates").update({
        "assembled_audio_prompt": assembled_audio_prompt,
        "audio_prompt_assembled_at": now,
        "audio_prompt_trigger_source": trigger_source,
        "audio_prompt_assembly_hash": audio_prompt_hash,
    }).eq("id", str(template_id)).execute()

    logger.info(
        f"[AUDIO_PROMPT_ASSEMBLY] ✅ Assembled audio prompt for template {template_code} "
        f"({len(assembled_audio_prompt)} chars, hash={audio_prompt_hash[:12]}...)"
    )

    return {
        "assembled_audio_prompt": assembled_audio_prompt,
        "audio_prompt_assembled_at": now,
        "audio_prompt_trigger_source": trigger_source,
        "audio_prompt_assembly_hash": audio_prompt_hash,
        "template_id": str(template_id),
        "template_code": template_code,
    }


def assemble_template_audio_schema(
    template_id: uuid.UUID,
    trigger_source: str = "manual"
) -> Dict[str, Any]:
    """
    Assemble audio emotion JSON schema for a template.

    Steps:
    1. Load template to get consultation_type_id
    2. Check if consultation type has emotion analysis enabled
    3. Load all AUDIO_ segments from segment_definitions
    4. Build combined JSON schema from schema_definition_json
    5. Store in templates.assembled_audio_schema_json

    Args:
        template_id: Template UUID to assemble
        trigger_source: What triggered this assembly (for tracking)

    Returns:
        Dict with assembled_audio_schema_json, audio_schema_assembled_at, etc.
    """
    logger.debug(f"[AUDIO_SCHEMA_ASSEMBLY] Starting assembly for template {template_id}")

    # Step 1: Load template
    template = get_template_by_id(template_id)
    if not template:
        raise ValueError(f"Template {template_id} not found")

    consultation_type_id = template.get("consultation_type_id")
    if not consultation_type_id:
        raise ValueError(f"Template {template_id} has no consultation_type_id")

    template_code = template.get("template_code", "UNKNOWN")

    # Step 2: Check if emotion analysis is enabled
    ct_result = supabase.table("consultation_types").select(
        "type_code, enable_emotion_analysis"
    ).eq("id", str(consultation_type_id)).single().execute()

    if not ct_result.data:
        raise ValueError(f"Consultation type {consultation_type_id} not found")

    emotion_enabled = ct_result.data.get("enable_emotion_analysis", False)

    # Assemble audio schema if emotion analysis is enabled
    # Audio schema is used when skip_transcription=true (audio-only mode)
    if not emotion_enabled:
        logger.debug(
            f"[AUDIO_SCHEMA_ASSEMBLY] Skipping - emotion analysis not enabled "
            f"for consultation type {ct_result.data.get('type_code')}"
        )
        return {
            "assembled_audio_schema_json": None,
            "audio_schema_assembled_at": None,
            "audio_schema_trigger_source": trigger_source,
            "template_id": str(template_id),
            "template_code": template_code,
            "skipped": True,
            "reason": "Emotion analysis not enabled"
        }

    # Step 3: Load all AUDIO_ segments from segment_definitions
    segments_result = supabase.table("segment_definitions").select(
        "segment_code, segment_name, schema_definition_json, display_order"
    ).like("segment_code", "AUDIO_%").eq("is_active", True).order("display_order").execute()

    if not segments_result.data:
        logger.warning(f"[AUDIO_SCHEMA_ASSEMBLY] No AUDIO_ segments found in segment_definitions")
        return {
            "assembled_audio_schema_json": None,
            "audio_schema_assembled_at": None,
            "audio_schema_trigger_source": trigger_source,
            "template_id": str(template_id),
            "template_code": template_code,
            "skipped": True,
            "reason": "No AUDIO_ segments found"
        }

    # Step 4: Build combined schema
    properties = {}
    required_fields = []

    for segment in segments_result.data:
        segment_code = segment["segment_code"]
        schema_json = segment.get("schema_definition_json", {})

        # Handle string schema_json
        if isinstance(schema_json, str):
            try:
                schema_json = json.loads(schema_json)
            except json.JSONDecodeError as e:
                logger.warning(f"[AUDIO_SCHEMA_ASSEMBLY] Failed to parse schema for {segment_code}: {e}")
                schema_json = {"type": "object", "description": f"Audio emotion data for {segment_code}"}

        # Use segment_code directly as property name (already SCREAMING_SNAKE_CASE)
        properties[segment_code] = schema_json
        required_fields.append(segment_code)

    assembled_audio_schema_json = {
        "type": "object",
        "description": "Audio-based emotion analysis from voice prosody",
        "properties": properties,
        "required": required_fields
    }

    # Step 5: Compute hash for change detection
    schema_json_str = json.dumps(assembled_audio_schema_json, sort_keys=True)
    audio_schema_hash = hashlib.sha256(schema_json_str.encode()).hexdigest()

    # Step 6: Update templates table
    now = datetime.now(timezone.utc).isoformat()

    supabase.table("templates").update({
        "assembled_audio_schema_json": assembled_audio_schema_json,
        "audio_schema_assembled_at": now,
        "audio_schema_trigger_source": trigger_source,
        "audio_schema_assembly_hash": audio_schema_hash,
    }).eq("id", str(template_id)).execute()

    logger.info(
        f"[AUDIO_SCHEMA_ASSEMBLY] ✅ Assembled audio schema for template {template_code} "
        f"({len(properties)} properties, hash={audio_schema_hash[:12]}...)"
    )

    return {
        "assembled_audio_schema_json": assembled_audio_schema_json,
        "audio_schema_assembled_at": now,
        "audio_schema_trigger_source": trigger_source,
        "audio_schema_assembly_hash": audio_schema_hash,
        "template_id": str(template_id),
        "template_code": template_code,
        "property_count": len(properties),
    }


def assemble_single_template_with_audio(
    template_id: uuid.UUID,
    trigger_source: str = "manual"
) -> Dict[str, Any]:
    """
    Assemble ALL artifacts for a single template: prompt, schema, audio prompt, audio schema.

    Args:
        template_id: Template UUID
        trigger_source: What triggered this assembly

    Returns:
        Combined result from all assemblies
    """
    # Standard extraction assemblies
    prompt_result = assemble_template_full_prompt(template_id, trigger_source)
    schema_result = assemble_template_schema(template_id, trigger_source)

    # Audio emotion assemblies (may skip if not enabled)
    audio_prompt_result = assemble_template_audio_prompt(template_id, trigger_source)
    audio_schema_result = assemble_template_audio_schema(template_id, trigger_source)

    return {
        "template_id": str(template_id),
        "template_code": prompt_result.get("template_code"),
        "prompt_assembled_at": prompt_result.get("prompt_assembled_at"),
        "schema_assembled_at": schema_result.get("schema_assembled_at"),
        "property_count": schema_result.get("property_count", 0),
        "audio_prompt_assembled_at": audio_prompt_result.get("audio_prompt_assembled_at"),
        "audio_schema_assembled_at": audio_schema_result.get("audio_schema_assembled_at"),
        "audio_skipped": audio_prompt_result.get("skipped", False),
        "trigger_source": trigger_source,
    }


async def trigger_audio_reassembly_async(
    template_ids: List[uuid.UUID],
    trigger_source: str
) -> None:
    """
    Asynchronously reassemble ONLY audio prompts and schemas for templates.

    Use this when only AUDIO_ segments changed (more efficient than full reassembly).

    Args:
        template_ids: List of template UUIDs to reassemble
        trigger_source: What triggered this assembly (for tracking)
    """
    if not template_ids:
        logger.debug(f"[AUDIO_ASSEMBLY] No templates to reassemble for trigger: {trigger_source}")
        return

    logger.info(f"[AUDIO_ASSEMBLY] Starting async audio reassembly for {len(template_ids)} templates")

    async def reassemble_single_audio(template_id: uuid.UUID) -> None:
        try:
            await asyncio.to_thread(assemble_template_audio_prompt, template_id, trigger_source)
            await asyncio.to_thread(assemble_template_audio_schema, template_id, trigger_source)
            logger.debug(f"[AUDIO_ASSEMBLY] Reassembled audio for template {template_id}")
        except Exception as e:
            logger.error(f"[AUDIO_ASSEMBLY] ❌ Failed to reassemble audio for template {template_id}: {e}")

    # Run all audio assemblies in parallel
    await asyncio.gather(*[reassemble_single_audio(tid) for tid in template_ids])


async def assemble_all_audio_prompts() -> Dict[str, Any]:
    """
    Assemble audio prompts and schemas for all active templates.

    Run once after migration or for bulk refresh.

    Returns:
        Dict with success count, failed count, skipped count, and error details
    """
    logger.info("[AUDIO_ASSEMBLY] Starting bulk audio assembly for all active templates")

    templates_result = supabase.table("templates").select(
        "id, template_code"
    ).eq("is_active", True).execute()

    if not templates_result.data:
        logger.debug("[AUDIO_ASSEMBLY] No active templates found")
        return {"success": 0, "failed": 0, "skipped": 0, "errors": []}

    results = {"success": 0, "failed": 0, "skipped": 0, "errors": []}

    for template in templates_result.data:
        try:
            template_id = uuid.UUID(template["id"])
            template_code = template.get("template_code", "UNKNOWN")

            prompt_result = assemble_template_audio_prompt(template_id, "initial_population")
            assemble_template_audio_schema(template_id, "initial_population")

            if prompt_result.get("skipped"):
                results["skipped"] += 1
                logger.debug(f"[AUDIO_ASSEMBLY] Skipped template: {template_code} ({prompt_result.get('reason')})")
            else:
                results["success"] += 1
                logger.debug(f"[AUDIO_ASSEMBLY] Assembled audio for template: {template_code}")

        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "template_id": template["id"],
                "template_code": template.get("template_code", "UNKNOWN"),
                "error": str(e)
            })
            logger.error(f"[AUDIO_ASSEMBLY] ❌ Failed to assemble audio for template {template['id']}: {e}")

    logger.info(
        f"[AUDIO_ASSEMBLY] Bulk assembly complete: "
        f"{results['success']} success, {results['skipped']} skipped, {results['failed']} failed"
    )

    return results


# ============================================================================
# COMBINED_ Emotion Prompt/Schema Assembly Functions
# ============================================================================

def assemble_template_combined_emotion_prompt(
    template_id: uuid.UUID,
    trigger_source: str = "manual"
) -> Dict[str, Any]:
    """
    Assemble combined (multimodal) emotion analysis prompt for a template.

    Combined emotion analysis extracts emotions from BOTH transcript text AND audio
    in a single Gemini call. Used when skip_transcription=False (normal pipeline).

    Steps:
    1. Load template to get consultation_type_id
    2. Check if emotion analysis is enabled for consultation type
    3. Load COMBINED_EMOTION_BASE_PROMPT from system_prompt_components
    4. Load all COMBINED_* segments from segment_definitions
    5. Build combined system prompt (base + segment instructions)
    6. Store in templates.assembled_combined_emotion_prompt

    Args:
        template_id: Template UUID to assemble
        trigger_source: What triggered this assembly (for tracking)

    Returns:
        Dict with assembled_combined_emotion_prompt, assembled_at, etc.
    """
    logger.debug(f"[COMBINED_EMOTION_PROMPT_ASSEMBLY] Starting assembly for template {template_id}")

    # Step 1: Load template
    template = get_template_by_id(template_id)
    if not template:
        raise ValueError(f"Template {template_id} not found")

    consultation_type_id = template.get("consultation_type_id")
    if not consultation_type_id:
        raise ValueError(f"Template {template_id} has no consultation_type_id")

    template_code = template.get("template_code", "UNKNOWN")

    # Step 2: Check if emotion analysis is enabled for this consultation type
    ct_result = supabase.table("consultation_types").select(
        "type_code, enable_emotion_analysis"
    ).eq("id", str(consultation_type_id)).single().execute()

    if not ct_result.data:
        raise ValueError(f"Consultation type {consultation_type_id} not found")

    emotion_enabled = ct_result.data.get("enable_emotion_analysis", False)

    # Assemble combined emotion prompts if emotion analysis is enabled
    # Combined prompts are used when skip_transcription=false (normal pipeline)
    if not emotion_enabled:
        logger.debug(
            f"[COMBINED_EMOTION_PROMPT_ASSEMBLY] Skipping - emotion analysis not enabled "
            f"for consultation type {ct_result.data.get('type_code')}"
        )
        return {
            "assembled_combined_emotion_prompt": None,
            "combined_emotion_prompt_assembled_at": None,
            "combined_emotion_prompt_trigger_source": trigger_source,
            "template_id": str(template_id),
            "template_code": template_code,
            "skipped": True,
            "reason": "Emotion analysis not enabled"
        }

    # Step 3: Load base prompt from system_prompt_components
    base_result = supabase.table("system_prompt_components").select(
        "content_text"
    ).eq("component_code", "COMBINED_EMOTION_BASE_PROMPT").eq("is_active", True).single().execute()

    base_prompt = ""
    if base_result.data and base_result.data.get("content_text"):
        base_prompt = base_result.data["content_text"]
    else:
        logger.warning(f"[COMBINED_EMOTION_PROMPT_ASSEMBLY] Base prompt not found, using segments only")

    # Step 4: Load all COMBINED_ segments from segment_definitions
    segments_result = supabase.table("segment_definitions").select(
        "segment_code, segment_name, prompt_section_text, display_order"
    ).like("segment_code", "COMBINED_%").eq("is_active", True).order("display_order").execute()

    if not segments_result.data:
        logger.warning(f"[COMBINED_EMOTION_PROMPT_ASSEMBLY] No COMBINED_ segments found in segment_definitions")
        return {
            "assembled_combined_emotion_prompt": None,
            "combined_emotion_prompt_assembled_at": None,
            "combined_emotion_prompt_trigger_source": trigger_source,
            "template_id": str(template_id),
            "template_code": template_code,
            "skipped": True,
            "reason": "No COMBINED_ segments found"
        }

    # Step 5: Build combined prompt
    segment_guidelines = ""
    for idx, segment in enumerate(segments_result.data, 1):
        segment_name = segment.get("segment_name", segment["segment_code"])
        prompt_text = segment.get("prompt_section_text", "")

        if prompt_text:
            segment_guidelines += f"{prompt_text}\n\n---\n\n"

    # Combine base prompt with segment guidelines
    if base_prompt:
        assembled_combined_emotion_prompt = f"{base_prompt}\n\n{segment_guidelines}"
    else:
        assembled_combined_emotion_prompt = segment_guidelines

    # Step 6: Compute hash for change detection
    combined_emotion_prompt_hash = hashlib.sha256(assembled_combined_emotion_prompt.encode()).hexdigest()

    # Step 7: Update templates table
    now = datetime.now(timezone.utc).isoformat()

    supabase.table("templates").update({
        "assembled_combined_emotion_prompt": assembled_combined_emotion_prompt,
    }).eq("id", str(template_id)).execute()

    logger.info(
        f"[COMBINED_EMOTION_PROMPT_ASSEMBLY] ✅ Assembled combined emotion prompt for template {template_code} "
        f"({len(assembled_combined_emotion_prompt)} chars, hash={combined_emotion_prompt_hash[:12]}...)"
    )

    return {
        "assembled_combined_emotion_prompt": assembled_combined_emotion_prompt,
        "combined_emotion_prompt_assembled_at": now,
        "combined_emotion_prompt_trigger_source": trigger_source,
        "combined_emotion_prompt_assembly_hash": combined_emotion_prompt_hash,
        "template_id": str(template_id),
        "template_code": template_code,
    }


def assemble_template_combined_emotion_schema(
    template_id: uuid.UUID,
    trigger_source: str = "manual"
) -> Dict[str, Any]:
    """
    Assemble combined (multimodal) emotion JSON schema for a template.

    Steps:
    1. Load template to get consultation_type_id
    2. Check if emotion analysis is enabled for consultation type
    3. Load all COMBINED_* segments from segment_definitions
    4. Build combined JSON schema from schema_definition_json
    5. Store in templates.assembled_combined_emotion_schema_json

    Args:
        template_id: Template UUID to assemble
        trigger_source: What triggered this assembly (for tracking)

    Returns:
        Dict with assembled_combined_emotion_schema_json, assembled_at, etc.
    """
    logger.debug(f"[COMBINED_EMOTION_SCHEMA_ASSEMBLY] Starting assembly for template {template_id}")

    # Step 1: Load template
    template = get_template_by_id(template_id)
    if not template:
        raise ValueError(f"Template {template_id} not found")

    consultation_type_id = template.get("consultation_type_id")
    if not consultation_type_id:
        raise ValueError(f"Template {template_id} has no consultation_type_id")

    template_code = template.get("template_code", "UNKNOWN")

    # Step 2: Check if emotion analysis is enabled
    ct_result = supabase.table("consultation_types").select(
        "type_code, enable_emotion_analysis"
    ).eq("id", str(consultation_type_id)).single().execute()

    if not ct_result.data:
        raise ValueError(f"Consultation type {consultation_type_id} not found")

    emotion_enabled = ct_result.data.get("enable_emotion_analysis", False)

    # Assemble combined emotion schema if emotion analysis is enabled
    if not emotion_enabled:
        logger.debug(
            f"[COMBINED_EMOTION_SCHEMA_ASSEMBLY] Skipping - emotion analysis not enabled "
            f"for consultation type {ct_result.data.get('type_code')}"
        )
        return {
            "assembled_combined_emotion_schema_json": None,
            "combined_emotion_schema_assembled_at": None,
            "combined_emotion_schema_trigger_source": trigger_source,
            "template_id": str(template_id),
            "template_code": template_code,
            "skipped": True,
            "reason": "Emotion analysis not enabled"
        }

    # Step 3: Load all COMBINED_ segments from segment_definitions
    segments_result = supabase.table("segment_definitions").select(
        "segment_code, segment_name, schema_definition_json, display_order"
    ).like("segment_code", "COMBINED_%").eq("is_active", True).order("display_order").execute()

    if not segments_result.data:
        logger.warning(f"[COMBINED_EMOTION_SCHEMA_ASSEMBLY] No COMBINED_ segments found in segment_definitions")
        return {
            "assembled_combined_emotion_schema_json": None,
            "combined_emotion_schema_assembled_at": None,
            "combined_emotion_schema_trigger_source": trigger_source,
            "template_id": str(template_id),
            "template_code": template_code,
            "skipped": True,
            "reason": "No COMBINED_ segments found"
        }

    # Step 4: Build combined schema
    properties = {}
    required = []

    for segment in segments_result.data:
        segment_code = segment.get("segment_code")
        schema_def = segment.get("schema_definition_json")

        if segment_code and schema_def:
            properties[segment_code] = schema_def
            required.append(segment_code)

    combined_schema = {
        "type": "object",
        "properties": properties,
        "required": required
    }

    # Step 5: Compute hash for change detection
    schema_str = json.dumps(combined_schema, sort_keys=True)
    combined_emotion_schema_hash = hashlib.sha256(schema_str.encode()).hexdigest()

    # Step 6: Update templates table
    now = datetime.now(timezone.utc).isoformat()

    supabase.table("templates").update({
        "assembled_combined_emotion_schema_json": combined_schema,
    }).eq("id", str(template_id)).execute()

    logger.info(
        f"[COMBINED_EMOTION_SCHEMA_ASSEMBLY] ✅ Assembled combined emotion schema for template {template_code} "
        f"({len(properties)} segments, hash={combined_emotion_schema_hash[:12]}...)"
    )

    return {
        "assembled_combined_emotion_schema_json": combined_schema,
        "combined_emotion_schema_assembled_at": now,
        "combined_emotion_schema_trigger_source": trigger_source,
        "combined_emotion_schema_assembly_hash": combined_emotion_schema_hash,
        "template_id": str(template_id),
        "template_code": template_code,
        "segment_count": len(properties),
    }


async def trigger_combined_emotion_reassembly_async(
    template_ids: List[uuid.UUID],
    trigger_source: str
) -> None:
    """
    Asynchronously reassemble ONLY combined emotion prompts and schemas for templates.

    Use this when only COMBINED_* segments changed (more efficient than full reassembly).

    Args:
        template_ids: List of template UUIDs to reassemble
        trigger_source: What triggered this assembly (for tracking)
    """
    if not template_ids:
        logger.debug(f"[COMBINED_EMOTION_ASSEMBLY] No templates to reassemble for trigger: {trigger_source}")
        return

    logger.info(f"[COMBINED_EMOTION_ASSEMBLY] Starting async combined emotion reassembly for {len(template_ids)} templates")

    async def reassemble_single_combined_emotion(template_id: uuid.UUID) -> None:
        try:
            await asyncio.to_thread(assemble_template_combined_emotion_prompt, template_id, trigger_source)
            await asyncio.to_thread(assemble_template_combined_emotion_schema, template_id, trigger_source)
            logger.debug(f"[COMBINED_EMOTION_ASSEMBLY] Reassembled combined emotion for template {template_id}")
        except Exception as e:
            logger.error(f"[COMBINED_EMOTION_ASSEMBLY] ❌ Failed to reassemble combined emotion for template {template_id}: {e}")

    # Run all combined emotion assemblies in parallel
    await asyncio.gather(*[reassemble_single_combined_emotion(tid) for tid in template_ids])


async def trigger_combined_emotion_reassembly_for_segment_change(
    segment_code: str,
    segment_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Trigger combined emotion prompt/schema reassembly when a COMBINED_* segment changes.

    This should be called whenever:
    - A COMBINED_* segment's prompt_section_text is updated
    - A COMBINED_* segment's schema_definition_json is updated
    - A COMBINED_* segment is activated/deactivated

    Args:
        segment_code: The segment code that changed (e.g., 'COMBINED_ANXIETY')
        segment_id: Optional segment UUID for tracking

    Returns:
        Dict with reassembly results
    """
    if not segment_code.startswith("COMBINED_"):
        logger.warning(f"[COMBINED_TRIGGER] Ignoring non-COMBINED segment change: {segment_code}")
        return {"skipped": True, "reason": "Not a COMBINED_ segment"}

    logger.debug(f"[COMBINED_TRIGGER] COMBINED_ segment changed: {segment_code}")

    # Get all templates with emotion enabled
    template_ids = get_all_templates_with_emotion_enabled()

    if not template_ids:
        logger.debug("[COMBINED_TRIGGER] No templates with emotion enabled")
        return {"skipped": True, "reason": "No templates with emotion enabled"}

    # Trigger async reassembly
    trigger_source = f"combined_segment:{segment_code}:update"
    if segment_id:
        trigger_source = f"combined_segment:{segment_id}:update"

    await trigger_combined_emotion_reassembly_async(template_ids, trigger_source)

    # Also invalidate the runtime cache in supabase_service
    try:
        from services.supabase_service import invalidate_combined_emotion_prompt_cache
        invalidate_combined_emotion_prompt_cache()
        logger.debug("[COMBINED_TRIGGER] Invalidated combined emotion prompt cache")
    except ImportError:
        pass

    return {
        "success": True,
        "template_count": len(template_ids),
        "trigger_source": trigger_source
    }


def on_combined_segment_updated(segment_code: str, action: str = "update"):
    """
    Code trigger for COMBINED_* segment updates.

    Call this from segment update endpoints after COMBINED_* segment changes.
    Creates async task to reassemble all templates with emotion enabled.

    Args:
        segment_code: The segment code that changed (e.g., 'COMBINED_ANXIETY')
        action: 'update', 'create', or 'delete'
    """
    if not segment_code.startswith("COMBINED_"):
        return

    logger.debug(f"[COMBINED_TRIGGER] Segment {segment_code} {action}d, triggering reassembly")

    try:
        loop = asyncio.get_running_loop()
        asyncio.create_task(
            trigger_combined_emotion_reassembly_for_segment_change(segment_code)
        )
    except RuntimeError:
        # No running event loop, run in thread
        import threading
        def run_async():
            asyncio.run(trigger_combined_emotion_reassembly_for_segment_change(segment_code))
        thread = threading.Thread(target=run_async, daemon=True)
        thread.start()


async def assemble_all_combined_emotion_prompts() -> Dict[str, Any]:
    """
    Assemble combined emotion prompts and schemas for all active templates.

    Run once after migration or for bulk refresh.

    Returns:
        Dict with success count, failed count, skipped count, and error details
    """
    logger.info("[COMBINED_EMOTION_ASSEMBLY] Starting bulk combined emotion assembly for all active templates")

    templates_result = supabase.table("templates").select(
        "id, template_code"
    ).eq("is_active", True).execute()

    if not templates_result.data:
        logger.debug("[COMBINED_EMOTION_ASSEMBLY] No active templates found")
        return {"success": 0, "failed": 0, "skipped": 0, "errors": []}

    results = {"success": 0, "failed": 0, "skipped": 0, "errors": []}

    for template in templates_result.data:
        try:
            template_id = uuid.UUID(template["id"])
            template_code = template.get("template_code", "UNKNOWN")

            prompt_result = assemble_template_combined_emotion_prompt(template_id, "initial_population")
            assemble_template_combined_emotion_schema(template_id, "initial_population")

            if prompt_result.get("skipped"):
                results["skipped"] += 1
                logger.debug(f"[COMBINED_EMOTION_ASSEMBLY] Skipped template: {template_code} ({prompt_result.get('reason')})")
            else:
                results["success"] += 1
                logger.debug(f"[COMBINED_EMOTION_ASSEMBLY] Assembled combined emotion for template: {template_code}")

        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "template_id": template.get("id"),
                "template_code": template.get("template_code", "UNKNOWN"),
                "error": str(e)
            })
            logger.error(f"[COMBINED_EMOTION_ASSEMBLY] ❌ Failed to assemble combined emotion for template {template['id']}: {e}")

    logger.info(
        f"[COMBINED_EMOTION_ASSEMBLY] Bulk assembly complete: "
        f"{results['success']} success, {results['skipped']} skipped, {results['failed']} failed"
    )

    return results


# ============================================================================
# AUDIO_ Segment Change Triggers
# ============================================================================

def get_all_templates_with_emotion_enabled() -> List[uuid.UUID]:
    """
    Get all templates that have emotion analysis enabled.

    Used for both audio-only (skip_transcription) and combined (normal) emotion analysis.
    The mode (audio vs combined) is determined at runtime based on skip_transcription flag.

    Returns:
        List of template UUIDs with emotion analysis enabled
    """
    try:
        # Get consultation types with emotion analysis enabled
        ct_result = supabase.table("consultation_types").select(
            "id"
        ).eq("enable_emotion_analysis", True).execute()

        if not ct_result.data:
            return []

        consultation_type_ids = [row["id"] for row in ct_result.data]

        # Get templates for these consultation types
        templates_result = supabase.table("templates").select(
            "id"
        ).in_("consultation_type_id", consultation_type_ids).eq("is_active", True).execute()

        if not templates_result.data:
            return []

        return [uuid.UUID(row["id"]) for row in templates_result.data]

    except Exception as e:
        logger.error(f"[EMOTION_TRIGGER] Error getting templates with emotion enabled: {e}")
        return []




async def trigger_audio_reassembly_for_segment_change(
    segment_code: str,
    segment_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Trigger audio prompt/schema reassembly when an AUDIO_ segment changes.

    This should be called whenever:
    - An AUDIO_ segment's prompt_section_text is updated
    - An AUDIO_ segment's schema_definition_json is updated
    - An AUDIO_ segment is activated/deactivated

    Args:
        segment_code: The segment code that changed (e.g., 'AUDIO_PATIENT_ANXIETY')
        segment_id: Optional segment UUID for tracking

    Returns:
        Dict with reassembly results
    """
    if not segment_code.startswith("AUDIO_"):
        logger.warning(f"[AUDIO_TRIGGER] Ignoring non-AUDIO segment change: {segment_code}")
        return {"skipped": True, "reason": "Not an AUDIO_ segment"}

    logger.debug(f"[AUDIO_TRIGGER] AUDIO_ segment changed: {segment_code}")

    # Get all templates with audio emotion enabled
    template_ids = get_all_templates_with_emotion_enabled()

    if not template_ids:
        logger.debug("[AUDIO_TRIGGER] No templates with audio emotion enabled")
        return {"skipped": True, "reason": "No templates with audio emotion enabled"}

    # Trigger async reassembly
    trigger_source = f"audio_segment:{segment_code}:update"
    if segment_id:
        trigger_source = f"audio_segment:{segment_id}:update"

    await trigger_audio_reassembly_async(template_ids, trigger_source)

    # Also invalidate the runtime cache in supabase_service
    try:
        from services.supabase_service import invalidate_audio_emotion_prompt_cache
        invalidate_audio_emotion_prompt_cache()
        logger.debug("[AUDIO_TRIGGER] Invalidated audio emotion prompt cache")
    except ImportError:
        pass

    return {
        "success": True,
        "template_count": len(template_ids),
        "trigger_source": trigger_source
    }


def on_audio_segment_updated(segment_code: str, segment_id: Optional[uuid.UUID] = None) -> None:
    """
    Synchronous wrapper to trigger audio reassembly (fire-and-forget).

    Call this from segment_definitions update handlers.

    Args:
        segment_code: The segment code that changed
        segment_id: Optional segment UUID for tracking
    """
    if not segment_code.startswith("AUDIO_"):
        return

    logger.debug(f"[AUDIO_TRIGGER] Scheduling audio reassembly for segment change: {segment_code}")

    # Fire-and-forget async task
    try:
        asyncio.create_task(
            trigger_audio_reassembly_for_segment_change(segment_code, segment_id)
        )
    except RuntimeError:
        # No event loop running - run synchronously in a new thread
        import threading

        def run_async():
            import asyncio
            asyncio.run(trigger_audio_reassembly_for_segment_change(segment_code, segment_id))

        thread = threading.Thread(target=run_async, daemon=True)
        thread.start()
        logger.debug(f"[AUDIO_TRIGGER] Started background thread for audio reassembly")


# ============================================================================
# Text Emotion Prompt Assembly Functions
# ============================================================================
# NOTE: Text emotion base prompt (TEXT_EMOTION_BASE_PROMPT) has been moved to
# the database. It is stored in system_prompt_components table and retrieved
# via system_prompt_configurations. See migration:
# 20251226072000_add_text_emotion_base_prompt_component.sql
# ============================================================================


def assemble_template_text_emotion_prompt(
    template_id: uuid.UUID,
    trigger_source: str = "manual"
) -> Dict[str, Any]:
    """
    Assemble text emotion analysis prompt for a template.

    Steps:
    1. Load template to get consultation_type_id
    2. Check if consultation type has text emotion analysis enabled
    3. Load all TEXT_EMOTION_ segments from segment_definitions
    4. Build combined system prompt (base + segment instructions)
    5. Store in templates.assembled_text_emotion_prompt

    Args:
        template_id: Template UUID to assemble
        trigger_source: What triggered this assembly (for tracking)

    Returns:
        Dict with assembled_text_emotion_prompt, text_emotion_prompt_assembled_at, etc.

    Raises:
        ValueError: If template not found or consultation type invalid
    """
    logger.debug(f"[TEXT_EMOTION_PROMPT_ASSEMBLY] Starting assembly for template {template_id}")

    # Step 1: Load template
    template = get_template_by_id(template_id)
    if not template:
        raise ValueError(f"Template {template_id} not found")

    consultation_type_id = template.get("consultation_type_id")
    if not consultation_type_id:
        raise ValueError(f"Template {template_id} has no consultation_type_id")

    template_code = template.get("template_code", "UNKNOWN")

    # Step 2: Check if emotion analysis is enabled for this consultation type
    ct_result = supabase.table("consultation_types").select(
        "type_code, enable_emotion_analysis"
    ).eq("id", str(consultation_type_id)).single().execute()

    if not ct_result.data:
        raise ValueError(f"Consultation type {consultation_type_id} not found")

    emotion_enabled = ct_result.data.get("enable_emotion_analysis", False)

    # Assemble text emotion prompts if emotion analysis is enabled
    # Note: TEXT_EMOTION_* segments are legacy - COMBINED_* segments are preferred
    if not emotion_enabled:
        logger.debug(
            f"[TEXT_EMOTION_PROMPT_ASSEMBLY] Skipping - emotion analysis not enabled "
            f"for consultation type {ct_result.data.get('type_code')}"
        )
        return {
            "assembled_text_emotion_prompt": None,
            "text_emotion_prompt_assembled_at": None,
            "text_emotion_prompt_trigger_source": trigger_source,
            "template_id": str(template_id),
            "template_code": template_code,
            "skipped": True,
            "reason": "Emotion analysis not enabled"
        }

    # Step 3: Load all TEXT_EMOTION_ segments from segment_definitions
    segments_result = supabase.table("segment_definitions").select(
        "segment_code, segment_name, prompt_section_text, display_order"
    ).like("segment_code", "TEXT_EMOTION_%").eq("is_active", True).order("display_order").execute()

    if not segments_result.data:
        logger.warning(f"[TEXT_EMOTION_PROMPT_ASSEMBLY] No TEXT_EMOTION_ segments found in segment_definitions")
        return {
            "assembled_text_emotion_prompt": None,
            "text_emotion_prompt_assembled_at": None,
            "text_emotion_prompt_trigger_source": trigger_source,
            "template_id": str(template_id),
            "template_code": template_code,
            "skipped": True,
            "reason": "No TEXT_EMOTION_ segments found"
        }

    # Step 4: Build combined prompt
    segment_guidelines = ""
    for idx, segment in enumerate(segments_result.data, 1):
        segment_name = segment.get("segment_name", segment["segment_code"])
        prompt_text = segment.get("prompt_section_text", "")

        if prompt_text:
            segment_guidelines += f"{prompt_text}\n\n---\n\n"

    # Store only the segment-specific guidelines (base prompt will be prepended at runtime)
    assembled_text_emotion_prompt = segment_guidelines

    # Step 5: Compute hash for change detection
    text_emotion_prompt_hash = hashlib.sha256(assembled_text_emotion_prompt.encode()).hexdigest()

    # Step 6: Update templates table
    now = datetime.now(timezone.utc).isoformat()

    supabase.table("templates").update({
        "assembled_text_emotion_prompt": assembled_text_emotion_prompt,
        "text_emotion_prompt_assembled_at": now,
        "text_emotion_prompt_trigger_source": trigger_source,
        "text_emotion_prompt_assembly_hash": text_emotion_prompt_hash,
    }).eq("id", str(template_id)).execute()

    logger.info(
        f"[TEXT_EMOTION_PROMPT_ASSEMBLY] ✅ Assembled text emotion prompt for template {template_code} "
        f"({len(assembled_text_emotion_prompt)} chars, hash={text_emotion_prompt_hash[:12]}...)"
    )

    return {
        "assembled_text_emotion_prompt": assembled_text_emotion_prompt,
        "text_emotion_prompt_assembled_at": now,
        "text_emotion_prompt_trigger_source": trigger_source,
        "text_emotion_prompt_assembly_hash": text_emotion_prompt_hash,
        "template_id": str(template_id),
        "template_code": template_code,
    }


def assemble_template_text_emotion_schema(
    template_id: uuid.UUID,
    trigger_source: str = "manual"
) -> Dict[str, Any]:
    """
    Assemble text emotion JSON schema for a template.

    Steps:
    1. Load template to get consultation_type_id
    2. Check if consultation type has text emotion analysis enabled
    3. Load all TEXT_EMOTION_ segments from segment_definitions
    4. Build combined JSON schema from schema_definition_json
    5. Store in templates.assembled_text_emotion_schema_json

    Args:
        template_id: Template UUID to assemble
        trigger_source: What triggered this assembly (for tracking)

    Returns:
        Dict with assembled_text_emotion_schema_json, text_emotion_schema_assembled_at, etc.
    """
    logger.debug(f"[TEXT_EMOTION_SCHEMA_ASSEMBLY] Starting assembly for template {template_id}")

    # Step 1: Load template
    template = get_template_by_id(template_id)
    if not template:
        raise ValueError(f"Template {template_id} not found")

    consultation_type_id = template.get("consultation_type_id")
    if not consultation_type_id:
        raise ValueError(f"Template {template_id} has no consultation_type_id")

    template_code = template.get("template_code", "UNKNOWN")

    # Step 2: Check if emotion analysis is enabled
    ct_result = supabase.table("consultation_types").select(
        "type_code, enable_emotion_analysis"
    ).eq("id", str(consultation_type_id)).single().execute()

    if not ct_result.data:
        raise ValueError(f"Consultation type {consultation_type_id} not found")

    emotion_enabled = ct_result.data.get("enable_emotion_analysis", False)

    # Assemble text emotion schema if emotion analysis is enabled
    # Note: TEXT_EMOTION_* segments are legacy - COMBINED_* segments are preferred
    if not emotion_enabled:
        logger.debug(
            f"[TEXT_EMOTION_SCHEMA_ASSEMBLY] Skipping - emotion analysis not enabled "
            f"for consultation type {ct_result.data.get('type_code')}"
        )
        return {
            "assembled_text_emotion_schema_json": None,
            "text_emotion_schema_assembled_at": None,
            "text_emotion_schema_trigger_source": trigger_source,
            "template_id": str(template_id),
            "template_code": template_code,
            "skipped": True,
            "reason": "Emotion analysis not enabled"
        }

    # Step 3: Load all TEXT_EMOTION_ segments from segment_definitions
    segments_result = supabase.table("segment_definitions").select(
        "segment_code, segment_name, schema_definition_json, display_order"
    ).like("segment_code", "TEXT_EMOTION_%").eq("is_active", True).order("display_order").execute()

    if not segments_result.data:
        logger.warning(f"[TEXT_EMOTION_SCHEMA_ASSEMBLY] No TEXT_EMOTION_ segments found in segment_definitions")
        return {
            "assembled_text_emotion_schema_json": None,
            "text_emotion_schema_assembled_at": None,
            "text_emotion_schema_trigger_source": trigger_source,
            "template_id": str(template_id),
            "template_code": template_code,
            "skipped": True,
            "reason": "No TEXT_EMOTION_ segments found"
        }

    # Step 4: Build combined schema
    properties = {}
    required_fields = []

    for segment in segments_result.data:
        segment_code = segment["segment_code"]
        schema_json = segment.get("schema_definition_json", {})

        # Handle string schema_json
        if isinstance(schema_json, str):
            try:
                schema_json = json.loads(schema_json)
            except json.JSONDecodeError as e:
                logger.warning(f"[TEXT_EMOTION_SCHEMA_ASSEMBLY] Failed to parse schema for {segment_code}: {e}")
                schema_json = {"type": "object", "description": f"Text emotion data for {segment_code}"}

        # Use segment_code directly as property name (keep TEXT_EMOTION_ prefix)
        # This matches the database segment_definitions table
        properties[segment_code] = schema_json
        required_fields.append(segment_code)

    assembled_text_emotion_schema_json = {
        "type": "object",
        "description": "Text-based emotion analysis from transcript content",
        "properties": properties,
        "required": required_fields
    }

    # Step 5: Compute hash for change detection
    schema_json_str = json.dumps(assembled_text_emotion_schema_json, sort_keys=True)
    text_emotion_schema_hash = hashlib.sha256(schema_json_str.encode()).hexdigest()

    # Step 6: Update templates table
    now = datetime.now(timezone.utc).isoformat()

    supabase.table("templates").update({
        "assembled_text_emotion_schema_json": assembled_text_emotion_schema_json,
        "text_emotion_schema_assembled_at": now,
        "text_emotion_schema_trigger_source": trigger_source,
        "text_emotion_schema_assembly_hash": text_emotion_schema_hash,
    }).eq("id", str(template_id)).execute()

    logger.info(
        f"[TEXT_EMOTION_SCHEMA_ASSEMBLY] ✅ Assembled text emotion schema for template {template_code} "
        f"({len(properties)} properties, hash={text_emotion_schema_hash[:12]}...)"
    )

    return {
        "assembled_text_emotion_schema_json": assembled_text_emotion_schema_json,
        "text_emotion_schema_assembled_at": now,
        "text_emotion_schema_trigger_source": trigger_source,
        "text_emotion_schema_assembly_hash": text_emotion_schema_hash,
        "template_id": str(template_id),
        "template_code": template_code,
        "property_count": len(properties),
    }


# ============================================================================
# TEXT_EMOTION_ Segment Change Triggers
# ============================================================================



async def trigger_text_emotion_reassembly_async(
    template_ids: List[uuid.UUID],
    trigger_source: str
) -> None:
    """
    Asynchronously reassemble ONLY text emotion prompts and schemas for templates.

    Use this when only TEXT_EMOTION_ segments changed (more efficient than full reassembly).

    Args:
        template_ids: List of template UUIDs to reassemble
        trigger_source: What triggered this assembly (for tracking)
    """
    if not template_ids:
        logger.debug(f"[TEXT_EMOTION_ASSEMBLY] No templates to reassemble for trigger: {trigger_source}")
        return

    logger.info(f"[TEXT_EMOTION_ASSEMBLY] Starting async text emotion reassembly for {len(template_ids)} templates")

    async def reassemble_single_text_emotion(template_id: uuid.UUID) -> None:
        try:
            await asyncio.to_thread(assemble_template_text_emotion_prompt, template_id, trigger_source)
            await asyncio.to_thread(assemble_template_text_emotion_schema, template_id, trigger_source)
            logger.debug(f"[TEXT_EMOTION_ASSEMBLY] Reassembled text emotion for template {template_id}")
        except Exception as e:
            logger.error(f"[TEXT_EMOTION_ASSEMBLY] ❌ Failed to reassemble text emotion for template {template_id}: {e}")

    # Run all text emotion assemblies in parallel
    await asyncio.gather(*[reassemble_single_text_emotion(tid) for tid in template_ids])


async def trigger_text_emotion_reassembly_for_segment_change(
    segment_code: str,
    segment_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Trigger text emotion prompt/schema reassembly when a TEXT_EMOTION_ segment changes.

    This should be called whenever:
    - A TEXT_EMOTION_ segment's prompt_section_text is updated
    - A TEXT_EMOTION_ segment's schema_definition_json is updated
    - A TEXT_EMOTION_ segment is activated/deactivated

    Args:
        segment_code: The segment code that changed (e.g., 'TEXT_EMOTION_ANXIETY_PRE_CONSULTATION')
        segment_id: Optional segment UUID for tracking

    Returns:
        Dict with reassembly results
    """
    if not segment_code.startswith("TEXT_EMOTION_"):
        logger.warning(f"[TEXT_EMOTION_TRIGGER] Ignoring non-TEXT_EMOTION segment change: {segment_code}")
        return {"skipped": True, "reason": "Not a TEXT_EMOTION_ segment"}

    logger.debug(f"[TEXT_EMOTION_TRIGGER] TEXT_EMOTION_ segment changed: {segment_code}")

    # Get all templates with text emotion enabled
    template_ids = get_all_templates_with_emotion_enabled()

    if not template_ids:
        logger.debug("[TEXT_EMOTION_TRIGGER] No templates with text emotion enabled")
        return {"skipped": True, "reason": "No templates with text emotion enabled"}

    # Trigger async reassembly
    trigger_source = f"text_emotion_segment:{segment_code}:update"
    if segment_id:
        trigger_source = f"text_emotion_segment:{segment_id}:update"

    await trigger_text_emotion_reassembly_async(template_ids, trigger_source)

    return {
        "success": True,
        "template_count": len(template_ids),
        "trigger_source": trigger_source
    }


def on_text_emotion_segment_updated(segment_code: str, segment_id: Optional[uuid.UUID] = None) -> None:
    """
    Synchronous wrapper to trigger text emotion reassembly (fire-and-forget).

    Call this from segment_definitions update handlers.

    Args:
        segment_code: The segment code that changed
        segment_id: Optional segment UUID for tracking
    """
    if not segment_code.startswith("TEXT_EMOTION_"):
        return

    logger.debug(f"[TEXT_EMOTION_TRIGGER] Scheduling text emotion reassembly for segment change: {segment_code}")

    # Fire-and-forget async task
    try:
        asyncio.create_task(
            trigger_text_emotion_reassembly_for_segment_change(segment_code, segment_id)
        )
    except RuntimeError:
        # No event loop running - run synchronously in a new thread
        import threading

        def run_async():
            import asyncio
            asyncio.run(trigger_text_emotion_reassembly_for_segment_change(segment_code, segment_id))

        thread = threading.Thread(target=run_async, daemon=True)
        thread.start()
        logger.debug(f"[TEXT_EMOTION_TRIGGER] Started background thread for text emotion reassembly")


async def assemble_all_text_emotion_prompts() -> Dict[str, Any]:
    """
    Assemble text emotion prompts and schemas for all active templates.

    Run once after migration or for bulk refresh.

    Returns:
        Dict with success count, failed count, skipped count, and error details
    """
    logger.info("[TEXT_EMOTION_ASSEMBLY] Starting bulk text emotion assembly for all active templates")

    templates_result = supabase.table("templates").select(
        "id, template_code"
    ).eq("is_active", True).execute()

    if not templates_result.data:
        logger.debug("[TEXT_EMOTION_ASSEMBLY] No active templates found")
        return {"success": 0, "failed": 0, "skipped": 0, "errors": []}

    results = {"success": 0, "failed": 0, "skipped": 0, "errors": []}

    for template in templates_result.data:
        try:
            template_id = uuid.UUID(template["id"])
            template_code = template.get("template_code", "UNKNOWN")

            prompt_result = assemble_template_text_emotion_prompt(template_id, "initial_population")
            assemble_template_text_emotion_schema(template_id, "initial_population")

            if prompt_result.get("skipped"):
                results["skipped"] += 1
                logger.debug(f"[TEXT_EMOTION_ASSEMBLY] Skipped template: {template_code} ({prompt_result.get('reason')})")
            else:
                results["success"] += 1
                logger.debug(f"[TEXT_EMOTION_ASSEMBLY] Assembled text emotion for template: {template_code}")

        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "template_id": template["id"],
                "template_code": template.get("template_code", "UNKNOWN"),
                "error": str(e)
            })
            logger.error(f"[TEXT_EMOTION_ASSEMBLY] ❌ Failed to assemble text emotion for template {template['id']}: {e}")

    logger.info(
        f"[TEXT_EMOTION_ASSEMBLY] Bulk assembly complete: "
        f"{results['success']} success, {results['skipped']} skipped, {results['failed']} failed"
    )

    return results

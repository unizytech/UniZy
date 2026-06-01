"""
System Prompt Service - Database-driven System Prompt Management

This module handles:
- Retrieval of pre-assembled system prompts from database
- Assembly of prompts from composable components
- 3-level fallback (pre-assembled → assemble from components → hardcoded)
- CRUD operations for components and configurations
- Activation/deactivation of configs for consultation types
- Extraction metrics tracking

Usage:
    # During extraction (fast path):
    prompt = get_system_prompt_with_fallback("OP")

    # Admin operations:
    create_prompt_component(...)
    assign_component_to_config(...)
    activate_config_for_consultation_type(...)
"""

import uuid
import logging
import hashlib
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime

from .supabase_service import supabase

# Configure logging
logger = logging.getLogger(__name__)

# ============================================================================
# Hardcoded Fallback Prompt (Last Resort)
# ============================================================================

BASE_SYSTEM_PROMPT_OP = """You are a specialized medical documentation AI assistant extracting structured clinical information from counsellor-student conversation transcripts.

**ROLE:** Extract outpatient consultation data into standardized JSON with SELECTIVE VERBOSITY: ultra-concise for routine data, detailed for critical clinical decisions.

**CAPABILITIES:** Process multilingual conversations (English, Tamil, Hindi, Telugu, Malayalam, Kannada, Bengali) | Adapt detail by consultation complexity | Generate monitoring protocols | Handle missing data with ""

**CRITICAL RULES:**
1. ❌ NEVER fabricate clinical information
2. ✅ "" (empty string) for unavailable fields | [] for empty lists
3. ✅ Flag abnormal vitals | Generate conservative assessments
4. ✅ NO information duplication across segments, except in Diagnosis and Chief Complaints where the same information can be repeated if chief complaint is the diagnosis by counsellor
5. ✅ Use most recent mention for contradictions
6. ✅ Distinguish subjective symptoms from objective findings
7. ❌ **HIPAA COMPLIANCE**: NEVER include any Protected Health Information (PHI) in the output. This includes: student names, dates of birth, phone numbers, email addresses, physical addresses, Social Security numbers, medical record numbers (MRN/UHID), IP numbers, registration numbers, health plan numbers, account numbers, passwords, or any other unique identifying information. Use "the student" instead of any student names throughout all output.

---

## CONSULTATION TYPE DETECTION (Affects History Depth)

Analyze the transcript to determine consultation type:

### **COMPLEX CONSULTATIONS (Require Detailed History):**
- Psychiatric/psychological consultations
- Chronic disease management
- Multi-system complaints (3+ organ systems involved)
- Post-hospitalization follow-up
- Medication adjustments/tapering

### **ROUTINE CONSULTATIONS (Brief History Acceptable):**
- Acute infections (fever, cold, cough <7 days)
- Minor injuries
- Vaccination visits
- Routine check-ups
- Single symptom, clear diagnosis

---

## HOW TO PROCESS INFORMATION

Information falls into these structural patterns:

**Type 1: Simple Fields** (Student Information, Report Metadata)
- Direct extraction, no categorization required
- Use "" (empty string) for missing values, [] for empty lists

**Type 2: Categorized Segments** (Chief Complaints → HPI → History → Physical Exam → Clinical Assessment)
- Information must flow logically through clinical narrative
- Example: "Headache × 2d" → Chief Complaints | "Started after stopping medication" → HPI | "BP 160/90" → Physical Exam | "Withdrawal symptoms correlate with medication gap" → Clinical Assessment

---

### **CORE PROCESSING RULES:**

**1. Field Type Handling:**
- **Strings** → "" (empty string) if missing. Use comma-separated format for multiple items
- **Arrays** → ONLY for: chief_complaints, current_medications, medications, timestamped_transcription, icd10_codes, when_to_seek_care, contact_numbers (array of objects)
- **Objects** → Nested structures: student_factors
- **Dates** → Convert to DD-MM-YYYY format

**2. Categorization Logic:**
- Use explicit segment names from transcript when available
- For ambiguous statements, use Decision Tree below
- Split compound information: "Diabetes for 5 years, on Metformin" → Past Medical History + Current Medications

**3. Language Handling:**
- Recognize common medical terms: Tamil (இரத்த அழுத்தம் = BP), Hindi (रक्तचाप = BP), Telugu (రక్తపోటు = BP)
- Translate ALL dialogue and terminology to English
- Use ICD-10 codes and international medical nomenclature

**4. Decision Tree:**
```
WHAT student complains of? → Chief Complaints | Diagnosis (if chief complaint is the diagnosis by counsellor)
HOW symptoms developed/changed? → History of Present Illness
WHAT student HAS (background)? → History (past medical, surgical, family)
WHAT was OBSERVED? → Physical Examination
WHAT tests ordered/results? → Investigations
COUNSELLOR'S assessment/conclusion? → Clinical Assessment
WHAT was diagnosed? → Diagnosis (or pick up from Chief Complaints if it is the diagnosis by counsellor)
WHAT medicines to take? -> Prescription
What instructions to follow(treatment)? → Treatment Plan & Advice
WHAT to do NEXT? → Follow-up
```

**5. Elimination of Redundancy:**
❌ **BAD:** "Headache × 2d" repeated in Chief Complaints, HPI, Clinical Assessment
✅ **GOOD:** Chief Complaints: "Headache × 2d" | HPI: "Started after stopping medication, gradually worsening" | Clinical Assessment: "Withdrawal symptoms (↑BP 160/90) correlate with 4-day medication gap"

---

### **SPECIAL SCENARIO:**

**Medication in Multiple Contexts:** "Student on Amlodipine 5mg for 2 years but stopped last week. Restarting today."

→ **History** → past_medical_history: "Hypertension (previously on Amlodipine 5mg, discontinued 1 week ago)"
→ **History** → current_medications: [] (stopped, so not current)
→ **Prescription** → medications: [{"name": "TAB. AMLODIPINE 5MG", "durationDays": "5.00", "morning_qty": "1.00", "noon_qty": "0.00", "evening_qty": "0.00", "night_qty": "0.00", ...}]
→ **Follow-up** → special_instructions: "Start Amlodipine 5mg today morning, Monitor BP at home daily"

---
"""


# ============================================================================
# RETRIEVAL FUNCTIONS (Used During Extraction)
# ============================================================================

def get_system_prompt_for_consultation_type(consultation_type_code: str) -> Optional[str]:
    """
    Get active pre-assembled system prompt for a consultation type (~5ms).

    This is the fast path - retrieves the materialized/cached prompt directly.

    Args:
        consultation_type_code: Consultation type code ('OP', 'DISCHARGE', etc.)

    Returns:
        Pre-assembled system prompt string, or None if not found
    """
    try:
        # Use RPC function for optimal performance
        result = supabase.rpc(
            'get_active_system_prompt_rpc',
            {'p_consultation_type_code': consultation_type_code}
        ).execute()

        if result.data:
            logger.info(f"[SystemPrompt] Retrieved pre-assembled prompt for {consultation_type_code}")
            return result.data

        # Fallback to direct query if RPC not available
        result = supabase.table('consultation_type_system_prompts').select(
            'system_prompt_configurations!inner(assembled_system_prompt, is_draft)'
        ).eq('consultation_type_code', consultation_type_code).eq('is_active', True).single().execute()

        if result.data and not result.data['system_prompt_configurations']['is_draft']:
            return result.data['system_prompt_configurations']['assembled_system_prompt']

        return None

    except Exception as e:
        logger.warning(f"[SystemPrompt] Failed to retrieve prompt for {consultation_type_code}: {e}")
        return None


def get_system_prompt_with_fallback(consultation_type_code: str) -> str:
    """
    Get system prompt with 3-level fallback.

    Level 1: Pre-assembled prompt from database (~5ms)
    Level 2: Assemble from components (~50ms)
    Level 3: Hardcoded BASE_SYSTEM_PROMPT_OP (instant)

    Args:
        consultation_type_code: Consultation type code ('OP', 'DISCHARGE', etc.)

    Returns:
        System prompt string (always returns a valid prompt)
    """
    # Level 1: Try pre-assembled prompt
    prompt = get_system_prompt_for_consultation_type(consultation_type_code)
    if prompt:
        logger.info(f"[SystemPrompt] Level 1: Using pre-assembled prompt for {consultation_type_code}")
        return prompt

    # Level 2: Try assembling from components
    config_id = get_active_config_id_for_consultation_type(consultation_type_code)
    if config_id:
        prompt = assemble_system_prompt(config_id)
        if prompt:
            logger.info(f"[SystemPrompt] Level 2: Assembled prompt from components for {consultation_type_code}")
            return prompt

    # Level 3: Hardcoded fallback
    logger.warning(f"[SystemPrompt] Level 3: Using hardcoded fallback for {consultation_type_code}")
    return BASE_SYSTEM_PROMPT_OP


def get_active_config_id_for_consultation_type(consultation_type_code: str) -> Optional[uuid.UUID]:
    """
    Get the active config ID for a consultation type.

    Args:
        consultation_type_code: Consultation type code

    Returns:
        UUID of active config, or None if not found
    """
    try:
        result = supabase.table('consultation_type_system_prompts').select(
            'system_prompt_config_id'
        ).eq('consultation_type_code', consultation_type_code).eq('is_active', True).single().execute()

        if result.data:
            return uuid.UUID(result.data['system_prompt_config_id'])
        return None

    except Exception as e:
        logger.warning(f"[SystemPrompt] Failed to get active config for {consultation_type_code}: {e}")
        return None


# ============================================================================
# ASSEMBLY FUNCTIONS
# ============================================================================

def assemble_system_prompt(config_id: uuid.UUID) -> Optional[str]:
    """
    Assemble system prompt from components.

    Components are joined with '\n\n' separator in display_order.
    Updates the materialized prompt in database on success.

    Args:
        config_id: Configuration ID to assemble

    Returns:
        Assembled prompt string, or None on failure
    """
    try:
        # Get all included components ordered by display_order
        result = supabase.table('system_prompt_config_components').select(
            'component_id, display_order, system_prompt_components!inner(content_text)'
        ).eq('config_id', str(config_id)).eq('is_included', True).order('display_order').execute()

        if not result.data:
            logger.warning(f"[SystemPrompt] No components found for config {config_id}")
            return None

        # Assemble prompt
        components = [item['system_prompt_components']['content_text'] for item in result.data]
        assembled_prompt = '\n\n'.join(components)

        # Calculate hash for change detection
        assembly_hash = hashlib.sha256(assembled_prompt.encode()).hexdigest()

        # Update materialized prompt in database
        supabase.table('system_prompt_configurations').update({
            'assembled_system_prompt': assembled_prompt,
            'assembled_at': datetime.utcnow().isoformat(),
            'assembly_hash': assembly_hash,
            'estimated_token_count': len(assembled_prompt) // 4  # Rough estimate
        }).eq('id', str(config_id)).execute()

        logger.info(f"[SystemPrompt] Assembled prompt for config {config_id} ({len(components)} components, {len(assembled_prompt)} chars)")

        # HOOK: Trigger reassembly for all templates using this system prompt config
        try:
            # Find consultation types using this config
            ct_result = supabase.table('consultation_type_system_prompts').select(
                'consultation_type_id, consultation_type_code'
            ).eq('system_prompt_config_id', str(config_id)).eq('is_active', True).execute()

            if ct_result.data:
                from .template_assembly_service import trigger_reassembly_async, get_templates_for_consultation_type

                all_template_ids = []
                consultation_type_codes = []
                for ct in ct_result.data:
                    ct_id = uuid.UUID(ct['consultation_type_id'])
                    template_ids = get_templates_for_consultation_type(ct_id)
                    all_template_ids.extend(template_ids)
                    consultation_type_codes.append(ct.get('consultation_type_code', 'unknown'))

                if all_template_ids:
                    trigger_source = f"system_prompt_config:{config_id}:update"
                    asyncio.create_task(trigger_reassembly_async(all_template_ids, trigger_source))
                    logger.info(f"[SystemPrompt] Triggered reassembly for {len(all_template_ids)} templates (consultation types: {consultation_type_codes})")
        except Exception as hook_error:
            logger.error(f"[SystemPrompt] Failed to trigger reassembly hook: {hook_error}")

        return assembled_prompt

    except Exception as e:
        logger.error(f"[SystemPrompt] Failed to assemble prompt for config {config_id}: {e}")
        return None


def _trigger_reassembly(config_id: uuid.UUID) -> None:
    """
    Trigger reassembly of a config (internal helper).

    Called automatically after component changes.
    """
    try:
        assemble_system_prompt(config_id)
    except Exception as e:
        logger.error(f"[SystemPrompt] Auto-reassembly failed for config {config_id}: {e}")


# ============================================================================
# CRUD - COMPONENTS
# ============================================================================

def create_prompt_component(
    component_code: str,
    component_name: str,
    component_type: str,
    content_text: str,
    content_version: str = "1.0.0",
    description: Optional[str] = None,
    is_base_component: bool = False
) -> Dict[str, Any]:
    """
    Create a new prompt component.

    Args:
        component_code: Unique code (e.g., 'ROLE_MEDICAL_AI')
        component_name: Display name
        component_type: Type (role, capabilities, critical_guidelines, etc.)
        content_text: The actual prompt text
        content_version: Version string (default: '1.0.0')
        description: Optional description
        is_base_component: Whether this is a template/base component

    Returns:
        Created component record
    """
    result = supabase.table('system_prompt_components').insert({
        'component_code': component_code,
        'component_name': component_name,
        'component_type': component_type,
        'content_text': content_text,
        'content_version': content_version,
        'description': description,
        'is_base_component': is_base_component,
        'is_active': True  # Components are active by default
    }).execute()

    logger.info(f"[SystemPrompt] Created component: {component_code} (type: {component_type})")
    return result.data[0] if result.data else {}


def update_prompt_component(
    component_id: uuid.UUID,
    **kwargs
) -> Dict[str, Any]:
    """
    Update a prompt component.

    Args:
        component_id: Component ID
        **kwargs: Fields to update (component_name, content_text, etc.)

    Returns:
        Updated component record
    """
    # Filter out None values
    update_data = {k: v for k, v in kwargs.items() if v is not None}

    if not update_data:
        return {}

    result = supabase.table('system_prompt_components').update(
        update_data
    ).eq('id', str(component_id)).execute()

    logger.info(f"[SystemPrompt] Updated component: {component_id}")

    # Trigger reassembly for all configs using this component
    _reassemble_configs_using_component(component_id)

    return result.data[0] if result.data else {}


def delete_prompt_component(component_id: uuid.UUID) -> bool:
    """
    Delete a prompt component.

    Note: Will fail if component is in use (ON DELETE RESTRICT).

    Args:
        component_id: Component ID

    Returns:
        True if deleted, False otherwise
    """
    try:
        supabase.table('system_prompt_components').delete().eq(
            'id', str(component_id)
        ).execute()
        logger.info(f"[SystemPrompt] Deleted component: {component_id}")
        return True
    except Exception as e:
        logger.error(f"[SystemPrompt] Failed to delete component {component_id}: {e}")
        return False


def list_prompt_components(component_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List all prompt components, optionally filtered by type.

    Args:
        component_type: Filter by type (optional)

    Returns:
        List of component records
    """
    query = supabase.table('system_prompt_components').select('*')

    if component_type:
        query = query.eq('component_type', component_type)

    result = query.order('component_type').order('component_code').execute()
    return result.data or []


def get_prompt_component(component_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get a single prompt component by ID.

    Args:
        component_id: Component ID

    Returns:
        Component record or None
    """
    try:
        result = supabase.table('system_prompt_components').select(
            '*'
        ).eq('id', str(component_id)).single().execute()
        return result.data
    except Exception:
        return None


def clone_prompt_component(
    source_component_id: uuid.UUID,
    new_component_code: str,
    new_version: str = "1.0.0"
) -> Dict[str, Any]:
    """
    Clone an existing component with a new code/version.

    Args:
        source_component_id: Source component to clone
        new_component_code: New code for the cloned component
        new_version: New version string

    Returns:
        Created component record
    """
    source = get_prompt_component(source_component_id)
    if not source:
        raise ValueError(f"Source component not found: {source_component_id}")

    return create_prompt_component(
        component_code=new_component_code,
        component_name=f"{source['component_name']} (Clone)",
        component_type=source['component_type'],
        content_text=source['content_text'],
        content_version=new_version,
        description=f"Cloned from {source['component_code']}",
        is_base_component=False
    )


def _reassemble_configs_using_component(component_id: uuid.UUID) -> None:
    """
    Reassemble all configs that use a specific component.
    """
    try:
        result = supabase.table('system_prompt_config_components').select(
            'config_id'
        ).eq('component_id', str(component_id)).execute()

        config_ids = set(item['config_id'] for item in (result.data or []))
        for config_id in config_ids:
            _trigger_reassembly(uuid.UUID(config_id))

    except Exception as e:
        logger.error(f"[SystemPrompt] Failed to reassemble configs using component {component_id}: {e}")


# ============================================================================
# CRUD - CONFIGURATIONS
# ============================================================================

def create_prompt_configuration(
    config_code: str,
    config_name: str,
    config_version: str = "1.0.0",
    description: Optional[str] = None,
    is_draft: bool = True,
    inherits_from_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Create a new prompt configuration.

    Args:
        config_code: Unique code (e.g., 'OP_STANDARD_V2')
        config_name: Display name
        config_version: Version string (default: '1.0.0')
        description: Optional description
        is_draft: Whether this is a draft (not used in production)
        inherits_from_id: Optional parent config to inherit from

    Returns:
        Created configuration record
    """
    data = {
        'config_code': config_code,
        'config_name': config_name,
        'config_version': config_version,
        'description': description,
        'is_draft': is_draft,
        'is_active': True  # Default active
    }

    if inherits_from_id:
        data['inherits_from_id'] = str(inherits_from_id)

    result = supabase.table('system_prompt_configurations').insert(data).execute()

    logger.info(f"[SystemPrompt] Created configuration: {config_code} v{config_version}")
    return result.data[0] if result.data else {}


def update_prompt_configuration(
    config_id: uuid.UUID,
    **kwargs
) -> Dict[str, Any]:
    """
    Update a prompt configuration.

    Args:
        config_id: Configuration ID
        **kwargs: Fields to update

    Returns:
        Updated configuration record
    """
    # Filter out None values
    update_data = {k: v for k, v in kwargs.items() if v is not None}

    if not update_data:
        return {}

    result = supabase.table('system_prompt_configurations').update(
        update_data
    ).eq('id', str(config_id)).execute()

    logger.info(f"[SystemPrompt] Updated configuration: {config_id}")
    return result.data[0] if result.data else {}


def delete_prompt_configuration(config_id: uuid.UUID) -> bool:
    """
    Delete a prompt configuration.

    Note: Will fail if config is assigned to a consultation type (ON DELETE RESTRICT).

    Args:
        config_id: Configuration ID

    Returns:
        True if deleted, False otherwise
    """
    try:
        supabase.table('system_prompt_configurations').delete().eq(
            'id', str(config_id)
        ).execute()
        logger.info(f"[SystemPrompt] Deleted configuration: {config_id}")
        return True
    except Exception as e:
        logger.error(f"[SystemPrompt] Failed to delete configuration {config_id}: {e}")
        return False


def list_prompt_configurations() -> List[Dict[str, Any]]:
    """
    List all prompt configurations with component counts.

    Returns:
        List of configuration records with component_count
    """
    result = supabase.table('system_prompt_configurations').select(
        '*, system_prompt_config_components(count)'
    ).order('config_code').execute()

    # Process to add component_count
    configs = []
    for item in (result.data or []):
        config = {k: v for k, v in item.items() if k != 'system_prompt_config_components'}
        component_data = item.get('system_prompt_config_components', [])
        config['component_count'] = component_data[0]['count'] if component_data else 0
        configs.append(config)

    return configs


def get_prompt_configuration(config_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get a single prompt configuration by ID.

    Args:
        config_id: Configuration ID

    Returns:
        Configuration record or None
    """
    try:
        result = supabase.table('system_prompt_configurations').select(
            '*'
        ).eq('id', str(config_id)).single().execute()
        return result.data
    except Exception:
        return None


def clone_prompt_configuration(
    source_config_id: uuid.UUID,
    new_config_code: str,
    new_version: str = "1.0.0"
) -> Dict[str, Any]:
    """
    Clone a configuration with all its component assignments.

    Args:
        source_config_id: Source config to clone
        new_config_code: New code for the cloned config
        new_version: New version string

    Returns:
        Created configuration record
    """
    source = get_prompt_configuration(source_config_id)
    if not source:
        raise ValueError(f"Source configuration not found: {source_config_id}")

    # Create new config
    new_config = create_prompt_configuration(
        config_code=new_config_code,
        config_name=f"{source['config_name']} (Clone)",
        config_version=new_version,
        description=f"Cloned from {source['config_code']}",
        is_draft=True,
        inherits_from_id=source_config_id
    )

    # Copy component assignments
    components = get_config_components(source_config_id)
    for comp in components:
        assign_component_to_config(
            config_id=uuid.UUID(new_config['id']),
            component_id=uuid.UUID(comp['component_id']),
            display_order=comp['display_order'],
            is_included=comp['is_included']
        )

    # Trigger assembly
    _trigger_reassembly(uuid.UUID(new_config['id']))

    return new_config


# ============================================================================
# JUNCTION: Config <-> Components
# ============================================================================

def assign_component_to_config(
    config_id: uuid.UUID,
    component_id: uuid.UUID,
    display_order: int,
    is_included: bool = True
) -> Dict[str, Any]:
    """
    Assign a component to a configuration.

    Triggers auto-reassembly on success.

    Args:
        config_id: Configuration ID
        component_id: Component ID
        display_order: Order in prompt assembly
        is_included: Whether to include in assembly

    Returns:
        Created junction record
    """
    # Get codes for readability
    config = get_prompt_configuration(config_id)
    component = get_prompt_component(component_id)

    if not config or not component:
        raise ValueError("Config or component not found")

    result = supabase.table('system_prompt_config_components').insert({
        'config_id': str(config_id),
        'component_id': str(component_id),
        'config_code': config['config_code'],
        'component_code': component['component_code'],
        'display_order': display_order,
        'is_included': is_included
    }).execute()

    logger.info(f"[SystemPrompt] Assigned component {component['component_code']} to config {config['config_code']} at order {display_order}")

    # Trigger reassembly
    _trigger_reassembly(config_id)

    return result.data[0] if result.data else {}


def remove_component_from_config(config_id: uuid.UUID, component_id: uuid.UUID) -> bool:
    """
    Remove a component from a configuration.

    Triggers auto-reassembly on success.

    Args:
        config_id: Configuration ID
        component_id: Component ID

    Returns:
        True if removed, False otherwise
    """
    try:
        supabase.table('system_prompt_config_components').delete().eq(
            'config_id', str(config_id)
        ).eq('component_id', str(component_id)).execute()

        logger.info(f"[SystemPrompt] Removed component {component_id} from config {config_id}")

        # Trigger reassembly
        _trigger_reassembly(config_id)

        return True
    except Exception as e:
        logger.error(f"[SystemPrompt] Failed to remove component: {e}")
        return False


def reorder_config_components(
    config_id: uuid.UUID,
    component_orders: List[Dict[str, Any]]
) -> bool:
    """
    Reorder components in a configuration.

    Triggers auto-reassembly on success.

    Args:
        config_id: Configuration ID
        component_orders: List of {component_id, display_order} dicts

    Returns:
        True if successful, False otherwise
    """
    try:
        for item in component_orders:
            supabase.table('system_prompt_config_components').update({
                'display_order': item['display_order']
            }).eq('config_id', str(config_id)).eq(
                'component_id', str(item['component_id'])
            ).execute()

        logger.info(f"[SystemPrompt] Reordered {len(component_orders)} components in config {config_id}")

        # Trigger reassembly
        _trigger_reassembly(config_id)

        return True
    except Exception as e:
        logger.error(f"[SystemPrompt] Failed to reorder components: {e}")
        return False


def get_config_components(config_id: uuid.UUID) -> List[Dict[str, Any]]:
    """
    Get all components assigned to a configuration.

    Args:
        config_id: Configuration ID

    Returns:
        List of component assignments ordered by display_order
    """
    result = supabase.table('system_prompt_config_components').select(
        '*, system_prompt_components(*)'
    ).eq('config_id', str(config_id)).order('display_order').execute()

    return result.data or []


def toggle_component_inclusion(
    config_id: uuid.UUID,
    component_id: uuid.UUID,
    is_included: bool
) -> bool:
    """
    Toggle the is_included flag for a component in a configuration.

    Triggers auto-reassembly on success.

    Args:
        config_id: Configuration ID
        component_id: Component ID
        is_included: New inclusion status

    Returns:
        True if successful, False otherwise
    """
    try:
        supabase.table('system_prompt_config_components').update({
            'is_included': is_included
        }).eq('config_id', str(config_id)).eq(
            'component_id', str(component_id)
        ).execute()

        logger.info(f"[SystemPrompt] Toggled component {component_id} inclusion to {is_included}")

        # Trigger reassembly
        _trigger_reassembly(config_id)

        return True
    except Exception as e:
        logger.error(f"[SystemPrompt] Failed to toggle component inclusion: {e}")
        return False


# ============================================================================
# JUNCTION: Consultation Type <-> Config
# ============================================================================

def assign_config_to_consultation_type(
    consultation_type_code: str,
    config_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Assign a configuration to a consultation type.
    Replaces any existing assignment and sets the new one as active.

    Args:
        consultation_type_code: Consultation type code
        config_id: Configuration ID

    Returns:
        Created junction record
    """
    # Get consultation_type_id
    ct_result = supabase.table('consultation_types').select(
        'id'
    ).eq('type_code', consultation_type_code).single().execute()

    if not ct_result.data:
        raise ValueError(f"Consultation type not found: {consultation_type_code}")

    # Get config code
    config = get_prompt_configuration(config_id)
    if not config:
        raise ValueError(f"Configuration not found: {config_id}")

    # Delete any existing assignment for this consultation type
    supabase.table('consultation_type_system_prompts').delete().eq(
        'consultation_type_code', consultation_type_code
    ).execute()
    logger.info(f"[SystemPrompt] Cleared existing assignment for {consultation_type_code}")

    # Create new assignment as active
    result = supabase.table('consultation_type_system_prompts').insert({
        'consultation_type_id': ct_result.data['id'],
        'system_prompt_config_id': str(config_id),
        'consultation_type_code': consultation_type_code,
        'config_code': config['config_code'],
        'is_active': True  # Active when assigned via dropdown
    }).execute()

    logger.info(f"[SystemPrompt] Assigned config {config['config_code']} to consultation type {consultation_type_code} (active)")
    return result.data[0] if result.data else {}


def remove_config_from_consultation_type(
    consultation_type_code: str,
    config_id: uuid.UUID
) -> bool:
    """
    Remove a config assignment from a consultation type.

    Args:
        consultation_type_code: Consultation type code
        config_id: Configuration ID

    Returns:
        True if removed, False otherwise
    """
    try:
        supabase.table('consultation_type_system_prompts').delete().eq(
            'consultation_type_code', consultation_type_code
        ).eq('system_prompt_config_id', str(config_id)).execute()

        logger.info(f"[SystemPrompt] Removed config {config_id} from consultation type {consultation_type_code}")
        return True
    except Exception as e:
        logger.error(f"[SystemPrompt] Failed to remove config assignment: {e}")
        return False


def toggle_assignment_active(
    consultation_type_code: str,
    config_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Toggle the is_active status of a consultation type assignment.

    Args:
        consultation_type_code: Consultation type code
        config_id: Configuration ID

    Returns:
        Updated assignment record
    """
    # First get current status
    current = supabase.table('consultation_type_system_prompts').select(
        'id, is_active'
    ).eq('consultation_type_code', consultation_type_code).eq(
        'system_prompt_config_id', str(config_id)
    ).single().execute()

    if not current.data:
        raise ValueError(f"Assignment not found for {consultation_type_code} / {config_id}")

    new_status = not current.data['is_active']

    # Update the status
    result = supabase.table('consultation_type_system_prompts').update({
        'is_active': new_status
    }).eq('id', current.data['id']).execute()

    logger.info(f"[SystemPrompt] Toggled assignment {consultation_type_code}/{config_id} to is_active={new_status}")
    return result.data[0] if result.data else {'is_active': new_status}


def get_configs_for_consultation_type(consultation_type_code: str) -> List[Dict[str, Any]]:
    """
    Get all configs assigned to a consultation type.

    Args:
        consultation_type_code: Consultation type code

    Returns:
        List of config assignments with config details
    """
    result = supabase.table('consultation_type_system_prompts').select(
        '*, system_prompt_configurations(*)'
    ).eq('consultation_type_code', consultation_type_code).order('created_at', desc=True).execute()

    return result.data or []


def get_active_config_for_consultation_type(consultation_type_code: str) -> Optional[Dict[str, Any]]:
    """
    Get the currently active config for a consultation type.

    Args:
        consultation_type_code: Consultation type code

    Returns:
        Config assignment with config details, or None
    """
    try:
        result = supabase.table('consultation_type_system_prompts').select(
            '*, system_prompt_configurations(*)'
        ).eq('consultation_type_code', consultation_type_code).eq('is_active', True).single().execute()
        return result.data
    except Exception:
        return None


# ============================================================================
# ACTIVATION
# ============================================================================

def activate_config_for_consultation_type(
    consultation_type_code: str,
    config_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Activate a config for a consultation type.

    DEACTIVATES any existing active config first (enforces single active).

    Args:
        consultation_type_code: Consultation type code
        config_id: Configuration ID to activate

    Returns:
        Updated assignment record
    """
    try:
        # Use RPC function if available (atomic operation)
        result = supabase.rpc(
            'activate_config_for_consultation_type_rpc',
            {
                'p_consultation_type_code': consultation_type_code,
                'p_config_id': str(config_id)
            }
        ).execute()

        if result.data:
            logger.info(f"[SystemPrompt] Activated config {config_id} for {consultation_type_code}")
            return get_active_config_for_consultation_type(consultation_type_code) or {}

    except Exception as e:
        logger.warning(f"[SystemPrompt] RPC activation failed, using fallback: {e}")

    # Fallback to manual deactivate + activate
    # Deactivate all existing active configs
    supabase.table('consultation_type_system_prompts').update({
        'is_active': False
    }).eq('consultation_type_code', consultation_type_code).eq('is_active', True).execute()

    # Activate the specified config
    result = supabase.table('consultation_type_system_prompts').update({
        'is_active': True
    }).eq('consultation_type_code', consultation_type_code).eq(
        'system_prompt_config_id', str(config_id)
    ).execute()

    logger.info(f"[SystemPrompt] Activated config {config_id} for {consultation_type_code}")
    return result.data[0] if result.data else {}


def deactivate_config_for_consultation_type(consultation_type_code: str) -> bool:
    """
    Deactivate the current active config for a consultation type.

    Args:
        consultation_type_code: Consultation type code

    Returns:
        True if deactivated, False otherwise
    """
    try:
        supabase.table('consultation_type_system_prompts').update({
            'is_active': False
        }).eq('consultation_type_code', consultation_type_code).eq('is_active', True).execute()

        logger.info(f"[SystemPrompt] Deactivated active config for {consultation_type_code}")
        return True
    except Exception as e:
        logger.error(f"[SystemPrompt] Failed to deactivate config: {e}")
        return False


# ============================================================================
# METRICS
# ============================================================================

def update_extraction_metrics(
    consultation_type_code: str,
    extraction_time_seconds: float
) -> None:
    """
    Update extraction metrics after each extraction.

    Updates total_extractions and running average of extraction time.

    Args:
        consultation_type_code: Consultation type code
        extraction_time_seconds: Time taken for extraction
    """
    try:
        # Use RPC function for atomic update with running average
        supabase.rpc(
            'update_extraction_metrics_rpc',
            {
                'p_consultation_type_code': consultation_type_code,
                'p_extraction_time_seconds': extraction_time_seconds
            }
        ).execute()

        logger.debug(f"[SystemPrompt] Updated metrics for {consultation_type_code}: {extraction_time_seconds:.2f}s")

    except Exception as e:
        # Non-critical - log warning and continue
        logger.warning(f"[SystemPrompt] Failed to update metrics: {e}")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def list_component_types() -> List[str]:
    """
    Get all unique component types in use.

    Returns:
        List of component type strings
    """
    result = supabase.table('system_prompt_components').select(
        'component_type'
    ).execute()

    types = set(item['component_type'] for item in (result.data or []))
    return sorted(list(types))


def preview_assembled_prompt(config_id: uuid.UUID) -> str:
    """
    Preview what the assembled prompt would look like.

    Does NOT save to database - useful for preview before activation.

    Args:
        config_id: Configuration ID

    Returns:
        Assembled prompt string
    """
    # Get all included components ordered by display_order
    result = supabase.table('system_prompt_config_components').select(
        'component_id, display_order, system_prompt_components!inner(content_text)'
    ).eq('config_id', str(config_id)).eq('is_included', True).order('display_order').execute()

    if not result.data:
        return "(No components assigned)"

    components = [item['system_prompt_components']['content_text'] for item in result.data]
    return '\n\n'.join(components)


def get_consultation_type_prompt_status() -> List[Dict[str, Any]]:
    """
    Get prompt status for all consultation types.

    Returns:
        List of consultation types with their active config status
    """
    # Get all consultation types
    ct_result = supabase.table('consultation_types').select('id, type_code, type_name').execute()

    statuses = []
    for ct in (ct_result.data or []):
        # Get active config for this type
        active = get_active_config_for_consultation_type(ct['type_code'])

        statuses.append({
            'consultation_type_code': ct['type_code'],
            'consultation_type_name': ct['type_name'],
            'has_active_config': active is not None,
            'active_config_code': active['config_code'] if active else None,
            'total_extractions': active['total_extractions'] if active else 0,
            'avg_extraction_time': active['avg_extraction_time_seconds'] if active else None
        })

    return statuses


def get_all_consultation_type_assignments() -> List[Dict[str, Any]]:
    """
    Get all consultation type to system prompt config assignments.

    Returns:
        List of all assignments with consultation type and config details
    """
    try:
        result = supabase.table('consultation_type_system_prompts').select(
            '*, system_prompt_configurations(id, config_code, config_name, description, is_draft)'
        ).order('consultation_type_code').execute()

        assignments = []
        for row in (result.data or []):
            config = row.get('system_prompt_configurations', {}) or {}
            assignments.append({
                'id': row['id'],
                'consultation_type_code': row['consultation_type_code'],
                'consultation_type_id': row.get('consultation_type_id'),
                'config_id': row['system_prompt_config_id'],
                'config_code': row.get('config_code') or config.get('config_code'),
                'config_name': config.get('config_name'),
                'config_description': config.get('description'),
                'is_active': row['is_active'],
                'is_draft': config.get('is_draft', False),
                'total_extractions': row.get('total_extractions', 0),
                'avg_extraction_time_seconds': row.get('avg_extraction_time_seconds'),
                'created_at': row.get('created_at'),
                'updated_at': row.get('updated_at'),
            })

        return assignments

    except Exception as e:
        logger.error(f"[SystemPrompt] Failed to get all assignments: {e}")
        return []

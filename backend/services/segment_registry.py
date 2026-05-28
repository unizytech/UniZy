"""
Segment Registry - Dynamic Prompt and Schema Generation

This module handles dynamic generation of prompts and Gemini schemas
based on user-configurable segment definitions stored in the database.

Features:
- Load segment configurations from database (with user customization)
- Generate dynamic system prompts based on selected segments
- Generate dynamic user prompts with JSON structure examples
- Generate dynamic Gemini response schemas
- Apply brevity level modifications to prompts
- Apply terminology style modifications to prompts
- Validate segment configurations for clinical safety
"""

import uuid
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from google.genai import types

from .supabase_service import get_segment_definitions, validate_segment_configuration, get_consultation_type_by_code, get_template_by_code
from .system_prompt_service import get_active_config_for_consultation_type
# Neonatal Daily (non-split extraction)
from .neonatal_prompts import (
    NEO_DAILY_PROMPT_SYSTEM,
    NEO_DAILY_PROMPT_USER,
    NEO_DAILY_PARAMETERS_SCHEMA,
)
# Optometry (non-split extraction)
from .optometrist_prompt import (
    OPTO_SYSTEM_PROMPT,
    OPTO_USER_PROMPT,
    OPTO_PARAMETERS_SCHEMA,
)
# Import Ophthalmology Prescription prompts (code-based, no segments)
from .ophthal_prescription_prompt import (
    OPHTHAL_PRESCRIPTION_SYSTEM_PROMPT,
    OPHTHAL_PRESCRIPTION_USER_PROMPT,
    OPHTHAL_PRESCRIPTION_SCHEMA,
)
# Import Ophthalmology Post-Op Rx prompts (code-based, no segments)
from .ophthal_postop_rx_prompt import (
    OPHTHAL_POSTOP_RX_SYSTEM_PROMPT,
    OPHTHAL_POSTOP_RX_USER_PROMPT,
    OPHTHAL_POSTOP_RX_SCHEMA,
)

# Configure logging
logger = logging.getLogger(__name__)

# Consultation types that do NOT benefit from doctor/hospital medicine + investigation
# lists or from the OP-shaped patient context block (past prescriptions, summaries,
# merge principles). Skipping keeps the prompt lean and prevents priming the LLM
# toward OP-style segments that don't exist in these templates. Continuation merge
# for these types is handled post-extraction in extraction_service._smart_merge_continuation.
_SKIP_DOCTOR_LISTS_AND_CONTEXT_TYPES = {"RADIOLOGY"}


def _should_skip_doctor_lists_and_context(consultation_type_code: Optional[str]) -> bool:
    return (consultation_type_code or "").upper() in _SKIP_DOCTOR_LISTS_AND_CONTEXT_TYPES


def _build_radiology_continuation_context(
    consultation_type_code: Optional[str],
    is_continuation: bool,
    parent_extraction_ids: Optional[List[str]],
) -> str:
    """Compact prior-visit snapshot for RADIOLOGY continuations.

    Surfaces just enough parent context (PLAN identity + additional_phases +
    patient-specific modifications + toxicity library_ids) so the LLM
    re-emits prior phases rather than dropping them, and treats a
    plan_template_id change as a deliberate full replacement instead of a
    field-level refinement. Returns "" when not applicable. Stays small
    (typically <1 KB) to avoid the prompt bloat that the OP-style patient
    context block would have introduced.
    """
    if (consultation_type_code or "").upper() != "RADIOLOGY":
        return ""
    if not is_continuation or not parent_extraction_ids:
        return ""

    try:
        from .supabase_service import supabase
        from .history_extraction_utils import get_extraction_data

        result = (
            supabase.table("medical_extractions")
            .select("id, original_extraction_json, edited_extraction_json")
            .in_("id", list(parent_extraction_ids))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            return ""

        parent_data = get_extraction_data(result.data[0]) or {}
        if not isinstance(parent_data, dict):
            return ""

        plan = parent_data.get("PLAN") or {}
        if not isinstance(plan, dict):
            plan = {}
        toxicity = parent_data.get("TOXICITY") or {}
        if not isinstance(toxicity, dict):
            toxicity = {}

        plan_template_id = (plan.get("plan_template_id") or "").strip()
        additional_phases = plan.get("additional_phases") or []
        if not isinstance(additional_phases, list):
            additional_phases = []
        patient_specific_modifications = (plan.get("patient_specific_modifications") or "").strip()

        def _ids(arr: Any) -> List[str]:
            if not isinstance(arr, list):
                return []
            ids = []
            for item in arr:
                if isinstance(item, dict):
                    lid = (item.get("library_id") or "").strip()
                    if lid:
                        ids.append(lid)
            return ids

        early_ids = _ids(toxicity.get("early_toxicities"))
        late_ids = _ids(toxicity.get("late_toxicities"))

        # Bail out early if there's nothing actually worth showing.
        if not (plan_template_id or additional_phases or patient_specific_modifications or early_ids or late_ids):
            return ""

        phases_repr = json.dumps(additional_phases, ensure_ascii=False) if additional_phases else "[]"
        early_repr = json.dumps(early_ids, ensure_ascii=False) if early_ids else "[]"
        late_repr = json.dumps(late_ids, ensure_ascii=False) if late_ids else "[]"

        return f"""

**RADIOLOGY CONTINUATION SNAPSHOT — PRIOR VISIT:**

Prior PLAN:
- plan_template_id: "{plan_template_id}"
- additional_phases: {phases_repr}
- patient_specific_modifications: "{patient_specific_modifications}"

Prior TOXICITY library ids:
- early: {early_repr}
- late:  {late_repr}

CARRY-FORWARD INSTRUCTIONS:
1. PLAN.additional_phases — RE-EMIT all prior phases verbatim unless the doctor explicitly cancels, replaces, or completes a phase. Adding new phases is allowed.
2. PLAN.patient_specific_modifications — carry forward unless the doctor revokes it.
3. PLAN.plan_template_id — if you change this, treat it as a deliberate swap. Emit the NEW plan's full parameters from scratch (rt_intent, rt_dose_gy, rt_fractions, rt_dose_per_fraction_gy, rt_weeks, rt_technique, concurrent_systemic_therapy). Do NOT carry over dose/fractions from the prior plan.
4. TOXICITY — prior toxicity library_ids will be carried forward by the post-extraction merge. Emit only NEW toxicities the doctor mentioned, or omit ids the doctor explicitly disclaimed.
5. Conditional toxicities (id prefixes GY_BR_, BR_SCF_, BR_LH_) — omit prior items if their trigger condition (brachytherapy planned, SCF/IMC field, left-sided RT) is no longer present in this visit. The doctor saying "skipping brachy" or "no longer including SCF" is a deliberate removal.
"""
    except Exception as e:
        logger.warning(f"[RADIOLOGY_CONTINUATION_CONTEXT] Failed to build snapshot: {e}")
        return ""


# ============================================================================
# Consultation-Type-Specific Base Prompts
# ============================================================================

# Base prompt for OP (Outpatient) consultations
# Preserves unique design: selective verbosity, consultation type detection, adaptive behavior
BASE_SYSTEM_PROMPT_OP_CONCISE = """You are a specialized medical documentation AI assistant extracting structured clinical information from doctor-patient conversation transcripts.

**ROLE:** Extract outpatient consultation data into standardized JSON with CONCISE LANGUAGE.

**CAPABILITIES:** Process multilingual conversations (English, Tamil, Hindi, Telugu, Malayalam, Kannada, Bengali)

**CRITICAL RULES:**
1. ❌ NEVER fabricate clinical information
2. ✅ "" (empty string) for unavailable fields | [] for empty lists
3. ✅ Flag abnormal vitals | Generate conservative assessments
4. ✅ NO information duplication across segments, except in Diagnosis and Chief Complaints where the same information can be repeated if chief complaint is the diagnosis by doctor
5. ✅ Use most recent mention for contradictions
6. ✅ Distinguish subjective symptoms from objective findings
7. ❌ NEVER include any sensitive non-clinical information such as passwords, phone numbers, addresses, etc.

---

## HOW TO PROCESS INFORMATION

Information falls into these structural patterns:

**Type 1: Simple Fields** (Patient Information, Report Metadata)
- Direct extraction, no categorization required

**Type 2: Categorized Segments** (Chief Complaints → HPI → History → Physical Exam → Clinical Assessment)
- Information must flow logically through clinical narrative
- Example: "Headache × 2d" → Chief Complaints | "Started after stopping medication" → HPI | "BP 160/90" → Physical Exam | "Withdrawal symptoms correlate with medication gap" → Clinical Assessment

---

### **CORE PROCESSING RULES:**

**1. Field Type Handling:**
- **Strings** → "" (empty string) if missing. Use comma-separated format for multiple items
- **Arrays** → ONLY for: chief_complaints, current_medications, medications, timestamped_transcription, icd10_codes, when_to_seek_care, contact_numbers (array of objects)
- **Objects** → Nested structures: patient_factors
- **Dates** → Convert to DD-MM-YYYY format

**2. Language Handling:**
- Recognize common medical terms: Tamil (இரத்த அழுத்தம் = BP), Hindi (रक्तचाप = BP), Telugu (రక్తపోటు = BP)
- Translate ALL dialogue and terminology to English only
- Use ICD-10 codes and international medical nomenclature

**3. Categorization Logic:**
- Use explicit segment names from transcript when available. If doctor says "The Diagnosis is Diabetes", use "Diagnosis" segment
- For ambiguous statements, use Decision Tree below
- Split compound information: "Diabetes for 5 years, on Metformin" → Past Medical History + Current Medications

**4. Decision Tree:**
```
WHAT was diagnosed, observed or concluded? → Diagnosis (include ICD-10 coding where it is clear) - Diagnosis could be the chief complaint itself. 
WHAT does the patient complain of? → Chief Complaints | History
WHAT medicines should the patient take? → Prescription
WHAT should the patient do next (non-medicine plans)? → Treatment Plan & Advice | Follow-up
WHAT was the doctor's assessment? -> Examination | Clinical Assessment
```

**5. Elimination of Redundancy:**
❌ **BAD:** "Headache × 2d" repeated in Chief Complaints, HPI, Clinical Assessment
✅ **GOOD:** Chief Complaints: "Headache × 2d" | HPI: "Started after stopping medication, gradually worsening" | Clinical Assessment: "Withdrawal symptoms (↑BP 160/90) correlate with 4-day medication gap"

---
"""

BASE_SYSTEM_PROMPT_OP = """You are a specialized medical documentation AI assistant extracting structured clinical information from doctor-patient conversation transcripts.

**ROLE:** Extract outpatient consultation data into standardized JSON with SELECTIVE VERBOSITY: ultra-concise for routine data, detailed for critical clinical decisions.

**CAPABILITIES:** Process multilingual conversations (English, Tamil, Hindi, Telugu, Malayalam, Kannada, Bengali) | Adapt detail by consultation complexity | Generate monitoring protocols | Handle missing data with ""

**CRITICAL RULES:**
1. ❌ NEVER fabricate clinical information
2. ✅ "" (empty string) for unavailable fields | [] for empty lists
3. ✅ Flag abnormal vitals | Generate conservative assessments
4. ✅ NO information duplication across segments, except in Diagnosis and Chief Complaints where the same information can be repeated if chief complaint is the diagnosis by doctor
5. ✅ Use most recent mention for contradictions
6. ✅ Distinguish subjective symptoms from objective findings
7. ❌ NEVER include any sensitive non-clinical information such as passwords, phone numbers, addresses, etc.

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

**Type 1: Simple Fields** (Patient Information, Report Metadata)
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
- **Objects** → Nested structures: patient_factors
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
WHAT patient complains of? → Chief Complaints | Diagnosis (if chief complaint is the diagnosis by doctor)
HOW symptoms developed/changed? → History of Present Illness
WHAT patient HAS (background)? → History (past medical, surgical, family)
WHAT was OBSERVED? → Physical Examination
WHAT tests ordered/results? → Investigations
DOCTOR'S assessment/conclusion? → Clinical Assessment
WHAT was diagnosed? → Diagnosis (or pick up from Chief Complaints if it is the diagnosis by doctor)
WHAT medicines to take? -> Prescription
What instructions to follow(treatment)? → Treatment Plan & Advice
WHAT to do NEXT? → Follow-up
```

**5. Elimination of Redundancy:**
❌ **BAD:** "Headache × 2d" repeated in Chief Complaints, HPI, Clinical Assessment
✅ **GOOD:** Chief Complaints: "Headache × 2d" | HPI: "Started after stopping medication, gradually worsening" | Clinical Assessment: "Withdrawal symptoms (↑BP 160/90) correlate with 4-day medication gap"

---

### **SPECIAL SCENARIO:**

**Medication in Multiple Contexts:** "Patient on Amlodipine 5mg for 2 years but stopped last week. Restarting today."

→ **History** → past_medical_history: "Hypertension (previously on Amlodipine 5mg, discontinued 1 week ago)"
→ **History** → current_medications: [] (stopped, so not current)
→ **Prescription** → medications: [{"name": "TAB. AMLODIPINE 5MG", "durationDays": "5.00", "morning_qty": "1.00", "noon_qty": "0.00", "evening_qty": "0.00", "night_qty": "0.00", ...}]
→ **Follow-up** → special_instructions: "Start Amlodipine 5mg today morning, Monitor BP at home daily"

---
"""

# Base prompt for DISCHARGE consultations
# Preserves unique design: redundancy elimination, information distribution, sub-segment processing
BASE_SYSTEM_PROMPT_DISCHARGE = """You are a specialized medical data extraction AI for discharge summary documentation.

**YOUR ROLE AND CAPABILITIES:**
Extract structured information from medical discharge summary transcriptions and return it in a standardized JSON format following the segment structure defined below. Process multilingual medical conversations in: English, Tamil (தமிழ்), Hindi (हिंदी), Telugu (తెలుగు), Malayalam (മലയാളം), Kannada (ಕನ್ನಡ), Bengali (বাংলা)


**CRITICAL RULES:**
1. ❌ NEVER fabricate medical information or assume data not explicitly stated
2. ✅ Use "" for any field not mentioned in the transcription
3. ✅ Use empty arrays [] for list fields with no data
4. ✅ Extract information exactly as stated in the transcription
5. ✅ Preserve medical terminology and abbreviations as they appear
6. ✅ Convert all dates to DD-MM-YYYY format
7. ✅ If contradictory information exists, use the most recent or final mention
8. ✅ Use concise medical terminology (e.g., "sleepless nights" → "Insomnia")
9. ✅ Distinguish between subjective symptoms (patient-reported) and objective findings (examination-based)
10. ✅ Translate all dialogue to English in Timestamped Transcription segment
11. ✅ NO information duplication across segments - distribute information appropriately
12. ✅ NEVER include any sensitive non-clinical information such as passwords, phone numbers, addresses, etc.

---

## ELIMINATION OF REDUNDANCY

**CRITICAL PRINCIPLE:** Each piece of information should appear in ONLY ONE segment. Never repeat the same information across multiple segments.

### **INFORMATION DISTRIBUTION RULES:**

1. **Chief Complaints** → Ultra-brief symptom names only (e.g., "Chest pain, Shortness of breath")
2. **History of Present Illness** → Details about symptom characteristics (onset, duration, progression) - do NOT repeat the complaint itself
3. **Treatment Summary** → What was DONE, not what the problem WAS (e.g., "Managed with medications X, Y, Z")
4. **Hospital Course** → Daily progression, not diagnosis repetition (e.g., "POD 1: Stable, pain improved")
5. **Discharge Condition** → Current state, not admission diagnosis (e.g., "Stable, pain-free, ambulatory")

### **COMMON REDUNDANCY PATTERNS TO AVOID:**

| Pattern | Solution |
|---------|----------|
| Repeating diagnosis | State diagnosis once in Diagnosis, refer to it as "the condition" elsewhere |
| Repeating chief complaint | State complaint once, expand details in HPI |
| Repeating procedure name | State procedure once in Treatment Details, use "the procedure" elsewhere |
| Repeating vital signs | Full vitals in Physical Exam, only changes in Hospital Course |

---

## HOW TO PROCESS SUB-SEGMENTS AND FIELDS

The segments have 3 structural types:

**Type 1: Simple Segments** (Patient Information, Medical Team, Report Metadata)
- Direct field extraction, no sub-categorization required
- Use "" (empty string) for missing single values, empty arrays [] for missing lists

**Type 2: Categorized Segments** (Diagnosis, History, Treatment Details, Treatment Plan & Advice)
- Information must be categorized into correct sub-segment field
- Example: "Diabetes since 2010. Father had heart disease." → `{"past_medical_history": "Diabetes since 2010", "family_history": "Father had heart disease"}`

**Type 3: Complex Nested** (Physical Examination with system findings, Prescription with medication arrays)
- Multi-level nested objects with distinct sub-categories
- Example: "Heart S1, S2 present. Lungs clear." → `{"cardiovascular_system": "S1, S2 present", "respiratory_system": "Lungs clear"}`

---

### **CORE PROCESSING RULES:**

**1. Field Type Handling:**
- **Strings** → "" (empty string) if missing. Use comma-separated format for multiple items
- **Arrays** → ONLY for: medications, current_medications, chief_complaints. All other multi-value fields are comma-separated STRINGS
- **Objects** → Extract nested fields (e.g., patient_factors)
- **Dates** → Convert to DD-MM-YYYY

**2. Categorization Logic:**
- Use explicit segment names from transcript when available
- For ambiguous statements, use Decision Tree below
- Split compound statements: "Diabetes for 5 years, on insulin" → Past Medical History + Current Medications

**3. Common Inference Patterns:**
- "Had surgery in 2015" → Past Surgical History (past tense)
- "Currently taking medication" → Current Medications (present tense)
- "Mother has diabetes" → Family History (family member)

**4. Decision Tree:**
```
WHAT the patient has? → Past Medical History / Diagnosis
WHAT was DONE? → Treatment Details / Procedures
HOW the patient FEELS? → Complaints / History of Present Illness
WHAT was OBSERVED? → Physical Examination / Investigations
WHAT to DO NEXT? → Treatment Plan & Advice / Prescription / Follow-up
```

### **SPECIAL SCENARIO:**

Medication in multiple contexts: "Had hypertension, was on Amlodipine but stopped. Currently taking Losartan 50mg."
→ Past Medical History: "Hypertension" | Current Medications: "Losartan 50mg"

---
"""

# ============================================================================
# Segment Loading
# ============================================================================

def load_segments_for_mode(
    consultation_type_id: uuid.UUID,
    doctor_id: Optional[uuid.UUID] = None,
    template_code: Optional[str] = None,
    mode: str = "full",
) -> List[Dict[str, Any]]:
    """
    Load segment definitions for a specific consultation type, mode, and user.

    Args:
        consultation_type_id: Consultation type ID (OP, DISCHARGE, etc.)
        doctor_id: Doctor ID for personalized configuration (None = default)
        template_code: Template code for template-specific configuration (optional, unique identifier)
        mode: 'core' | 'additional' | 'full'

    Returns:
        List of segment configurations sorted by display_order
    """
    result = get_segment_definitions(
        consultation_type_id=consultation_type_id,
        doctor_id=doctor_id,
        template_code=template_code,
        mode=mode
    )

    segments = result.get("segments", [])
    excluded_segment_codes = result.get("excluded_segment_codes", set())

    if not segments:
        # For 'additional' mode, it's valid to have no segments (user might have moved all to CORE)
        # Return empty dict instead of raising error - caller should handle gracefully
        logger.warning(f"No segments found for consultation_type_id={consultation_type_id}, mode={mode}")
        return {"segments": [], "excluded_segment_codes": set()}

    return {
        "segments": sorted(segments, key=lambda s: s.get("display_order", 999)),
        "excluded_segment_codes": excluded_segment_codes
    }


# ============================================================================
# Prompt Modification Based on Brevity Level
# ============================================================================

def apply_brevity_modifier(
    prompt_text: str,
    brevity_level: str,
    segment_code: str
) -> str:
    """
    Modify prompt text based on brevity level setting.

    Args:
        prompt_text: Original prompt section text
        brevity_level: 'concise' | 'balanced' | 'detailed'
        segment_code: Segment identifier for context

    Returns:
        Modified prompt text with brevity instructions
    """
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


# ============================================================================
# Prompt Modification Based on Terminology Style
# ============================================================================

def apply_terminology_modifier(
    prompt_text: str,
    terminology_style: str,
    segment_code: str
) -> str:
    """
    Modify prompt text based on terminology style setting.

    Args:
        prompt_text: Original prompt section text
        terminology_style: 'medical_terms' | 'simple_terms' | 'as_spoken'
        segment_code: Segment identifier for context

    Returns:
        Modified prompt text with terminology instructions
    """
    if terminology_style == "simple_terms":
        return f"""
{prompt_text}

**TERMINOLOGY OVERRIDE (USER PREFERENCE): SIMPLE/PATIENT-FRIENDLY TERMS**
- Use simple, patient-friendly language instead of medical jargon
- Examples: "stomach pain" instead of "abdominal pain", "breathlessness" instead of "dyspnea"
- Avoid complex medical abbreviations (explain them if used)
- This segment should be easily understandable by patients
"""
    elif terminology_style == "as_spoken":
        return f"""
{prompt_text}

**TERMINOLOGY OVERRIDE (USER PREFERENCE): AS SPOKEN IN TRANSCRIPT**
- Report terms exactly as spoken in the conversation
- Do NOT translate lay terms to medical terminology
- Examples: If patient says "stomach", write "stomach" (not "abdomen")
- Preserve the original language style and phrasing
"""
    else:  # medical_terms (default)
        return prompt_text


# ============================================================================
# Dynamic System Prompt Generation
# ============================================================================

def generate_system_prompt(
    segments: List[Dict[str, Any]],
    consultation_type_code: str,
    base_system_prompt: Optional[str] = None,
    template_id: Optional[uuid.UUID] = None
) -> str:
    """
    Generate complete system prompt from segment list.

    NEW: If template_id is provided, tries to use pre-assembled prompt first.
    Falls back to dynamic generation if assembled_full_prompt is NULL.

    Args:
        segments: List of segment configurations
        consultation_type_code: Consultation type code ('OP', 'DISCHARGE', 'RESPIRATORY')
        base_system_prompt: Optional base system prompt (overrides consultation-type-specific prompt)
        template_id: Optional template ID to check for pre-assembled prompt

    Returns:
        Complete system prompt string
    """
    # NEW: Try pre-assembled prompt first if template_id is provided
    if template_id:
        try:
            from .template_assembly_service import get_template_by_id
            template = get_template_by_id(template_id)
            if template and template.get("assembled_full_prompt"):
                logger.debug(f"[SYSTEM_PROMPT] ✅ Using pre-assembled prompt for template {template_id} (assembled at: {template.get('prompt_assembled_at')})")
                return template["assembled_full_prompt"]
            else:
                logger.warning(f"[SYSTEM_PROMPT] No pre-assembled prompt for template {template_id}, falling back to dynamic generation")
        except Exception as e:
            logger.warning(f"[SYSTEM_PROMPT] Error checking pre-assembled prompt for template {template_id}: {e}, falling back to dynamic generation")

    # FALLBACK: Dynamic prompt generation from database configuration
    # First, try to get the assigned system prompt configuration from database
    if not base_system_prompt:
        active_config = get_active_config_for_consultation_type(consultation_type_code)
        if active_config:
            # Get the assembled prompt from the nested system_prompt_configurations
            config_data = active_config.get('system_prompt_configurations', {})
            if config_data and config_data.get('assembled_system_prompt'):
                base_system_prompt = config_data['assembled_system_prompt']
                config_name = config_data.get('config_name', 'Unknown')
                logger.debug(f"[SYSTEM_PROMPT] ✅ Using assigned prompt config '{config_name}' for {consultation_type_code}")
            else:
                logger.warning(f"[SYSTEM_PROMPT] Active config found but no assembled_system_prompt for {consultation_type_code}")

    # Raise error if no assigned config found - no silent fallback
    if not base_system_prompt:
        error_msg = f"No active system prompt configuration found for consultation type '{consultation_type_code}'. Please assign a prompt configuration in Admin > Prompts > Assignments."
        logger.error(f"[SYSTEM_PROMPT] ❌ {error_msg}")
        raise ValueError(error_msg)

    # Build segment-specific extraction guidelines
    segment_guidelines = "\n## EXTRACTION GUIDELINES BY SEGMENT\n\n"

    for idx, segment in enumerate(segments, 1):
        # DEFENSIVE: Handle non-dict segments
        if isinstance(segment, str):
            logger.warning(f"[SYSTEM_PROMPT] Segment at index {idx} is a string: '{segment[:100]}...'")
            segment_guidelines += f"### {idx}. SEGMENT_{idx}\n\nExtract data for this segment.\n\n---\n\n"
            continue
        if not isinstance(segment, dict):
            logger.warning(f"[SYSTEM_PROMPT] Segment at index {idx} is unexpected type: {type(segment).__name__}")
            segment_guidelines += f"### {idx}. SEGMENT_{idx}\n\nExtract data for this segment.\n\n---\n\n"
            continue

        segment_name = segment.get("segment_name", f"Segment_{idx}")
        prompt_text = segment.get("prompt_section_text", "Extract relevant data for this segment.")
        brevity_level = segment.get("brevity_level") or segment.get("default_brevity_level", "balanced")
        terminology_style = segment.get("terminology_style") or segment.get("default_terminology_style", "medical_terms")

        # Apply modifiers
        segment_code = segment.get("segment_code", f"SEGMENT_{idx}")
        prompt_text = apply_brevity_modifier(prompt_text, brevity_level, segment_code)
        prompt_text = apply_terminology_modifier(prompt_text, terminology_style, segment_code)

        segment_guidelines += f"### {idx}. {segment_name.upper()}\n\n{prompt_text}\n\n---\n\n"

    return base_system_prompt + segment_guidelines


# ============================================================================
# Dynamic User Prompt Generation
# ============================================================================

def generate_user_prompt(
    segments: List[Dict[str, Any]],
    consultation_type_code: str,
    transcript: str,
    doctor_id: Optional[uuid.UUID] = None,
    patient_id: Optional[str] = None,
    has_medicine_list: bool = True,
    has_investigation_list: bool = True,
    is_continuation: bool = False,
    parent_extraction_ids: Optional[List[str]] = None,
) -> str:
    """
    Generate complete user prompt with transcript and JSON structure.

    Args:
        segments: List of segment configurations
        consultation_type_code: Consultation type code ('OP', 'DISCHARGE', 'RESPIRATORY')
        transcript: Consultation transcript text
        doctor_id: Doctor ID for medicine list injection (optional)
        patient_id: Patient ID for history context injection (optional)
        has_medicine_list: Whether doctor/hospital has medicine lists (skip injection if False)
        has_investigation_list: Whether doctor/hospital has investigation lists (skip injection if False)

    Returns:
        Complete user prompt string with transcript and required JSON structure
    """
    # NOTE: JSON schema example generation commented out - redundant since response_schema
    # is already used in gemini_service.py's generate_content call. The schema constrains
    # Gemini's output directly, making the example in the prompt unnecessary.
    #
    # # Build JSON structure example from segments
    # json_structure = {}
    #
    # for segment in segments:
    #     segment_code = segment.get("segment_code", "")
    #     schema_json = segment.get("schema_definition_json", {})
    #
    #     # Convert schema to example structure
    #     if isinstance(schema_json, str):
    #         schema_json = json.loads(schema_json)
    #
    #     # Create example based on schema type
    #     if schema_json.get("type") == "object":
    #         json_structure[_to_camel_case(segment_code)] = _schema_to_example(schema_json)
    #     elif schema_json.get("type") == "array":
    #         json_structure[_to_camel_case(segment_code)] = [_schema_to_example(schema_json.get("items", {}))]
    #     else:
    #         json_structure[_to_camel_case(segment_code)] = "string or appropriate type"
    #
    # # Format JSON structure for display
    # json_example = json.dumps(json_structure, indent=2)
    #
    # # ⚠️ CRITICAL: Escape braces for Python's .format() method
    # json_example = json_example.replace('{', '{{').replace('}', '}}')

    header = "**CONSULTATION TRANSCRIPT:**"
    extract_instruction = "Extract structured information from the consultation transcript below."
    special_instructions = "9. Follow the segment structure defined in the system prompt carefully"

    # Some consultation types (e.g. RADIOLOGY) skip doctor/hospital list injection
    # and the OP-shaped patient context block — see _SKIP_DOCTOR_LISTS_AND_CONTEXT_TYPES.
    _skip_doctor_artifacts = _should_skip_doctor_lists_and_context(consultation_type_code)
    if _skip_doctor_artifacts:
        logger.debug(
            f"[USER_PROMPT] Skipping medicine/investigation list + patient context "
            f"for consultation_type_code={consultation_type_code}"
        )

    # Medicine list injection for prescription matching (only if lists exist)
    medicine_list_section = ""
    if doctor_id and has_medicine_list and not _skip_doctor_artifacts:
        try:
            from .medicine_service import get_medicine_list_for_prompt
            medicine_list = get_medicine_list_for_prompt(doctor_id, transcript_text=transcript)
            if medicine_list:
                medicine_list_section = f"""

**MEDICINE MATCHING (CRITICAL):**
When extracting medicines for the prescription segment, follow these rules:

1. **MATCH FROM LIST FIRST**: For each medicine mentioned, find the closest match from the doctor's medicine list below. Account for:
   - Pronunciation variations (e.g., "amlo" → "AMLODIPINE", "glycomet" → "METFORMIN")
   - Abbreviated names (e.g., "telmi 40" → "TELMISARTAN 40MG")
   - Brand vs generic names (listed as "also:" alternatives)
   - Phonetic similarities (e.g., "azithro" → "AZITHROMYCIN")

2. **MATCH BOTH BRAND NAME AND FORM**: Each medicine entry has a `[Form]` tag (e.g., `[Tablet]`, `[Syrup]`, `[Capsule]`) indicating its dosage form. You MUST match based on BOTH the brand name AND the form mentioned by the doctor. Use the `[Form]` tag to disambiguate entries with the same brand. For example:
   - Doctor says "Dolo 650 tablet" → pick "DOLO 650 [Tablet]", NOT "DOLO 100 ML SYRUP [Syrup]"
   - Doctor says "Crocin syrup" → if no entry has a matching `[Syrup]` form for Crocin, output the spoken name "Crocin Syrup" verbatim. Do NOT pick "CROCIN 500 MG TABLETS [Tablet]" when the doctor clearly said syrup.
   - The form spoken by the doctor MUST match the `[Form]` tag of the selected entry. NEVER substitute a tablet for a syrup or vice versa.

3. **USE EXACT NAME FROM LIST**: If a close match is found, copy the COMPLETE medicine name exactly as it appears in the list — include everything before the `[Form]` tag and "(also:" part. Do NOT include the `[Form]` tag in the output. Do NOT truncate or remove any suffixes like "Kg TABLET" or "ML LIQUID". For example, if the list shows "T - CALPOL 650MG TAB  Kg TABLET [Tablet] (also: CALPOL, ...)", output exactly: "T - CALPOL 650MG TAB  Kg TABLET"

4. **NEW MEDICINES ONLY IF NO MATCH**: Only use the spoken medicine name verbatim if there is NO reasonable match in the list below. This includes cases where the brand exists but the form does not match (e.g., doctor says "syrup" but only a `[Tablet]` entry exists).

5. **FORM SELF-CHECK (MANDATORY)**: After selecting a medicine from the list, verify the `[Form]` tag matches what the doctor said:
   - Doctor said "syrup" but you picked a `[Tablet]` entry? WRONG — output the spoken name verbatim instead.
   - Doctor said "tablet" but you picked a `[Syrup]` entry? WRONG — output the spoken name verbatim instead.
   - If the form doesn't match ANY entry for that brand, output the spoken name verbatim.
   Also set the `dosage_form` field to what the doctor ACTUALLY SAID (e.g., "Syrup"), regardless of which list entry you matched.

{medicine_list}

**FORM REMINDER: A syrup is NEVER a tablet. A tablet is NEVER a syrup. The [Form] tag MUST match the form the doctor said. If in doubt, output the spoken name verbatim.**
"""
                logger.debug(f"[USER_PROMPT] Injected medicine list for doctor {doctor_id} ({len(medicine_list)} chars)")
            else:
                logger.debug(f"[USER_PROMPT] No medicine list found for doctor {doctor_id}")
        except Exception as e:
            logger.warning(f"[USER_PROMPT] Failed to get medicine list for doctor {doctor_id}: {e}")
    elif doctor_id and not has_medicine_list:
        logger.debug(f"[USER_PROMPT] Skipping medicine list injection - no lists for doctor {doctor_id}")

    # Investigation list injection for investigation matching (only if lists exist)
    investigation_list_section = ""
    if doctor_id and has_investigation_list and not _skip_doctor_artifacts:
        try:
            from .investigation_service import get_investigation_list_for_prompt
            investigation_list = get_investigation_list_for_prompt(doctor_id)
            if investigation_list:
                investigation_list_section = f"""

**INVESTIGATION MATCHING (CRITICAL):**
When extracting investigations, follow these rules:

1. **MATCH FROM LIST FIRST**: For each investigation mentioned, find the closest match from the doctor's investigation list below. Account for:
   - Abbreviations (e.g., "CBC" → "Complete Blood Count", "LFT" → "Liver Function Test")
   - Common names (e.g., "blood count" → "Complete Blood Count", "chest x-ray" → "X-Ray Chest PA View")
   - Phonetic similarities (e.g., "hemogram" → "Complete Blood Count")

2. **USE EXACT NAME FROM LIST**: If a close match is found, copy the COMPLETE investigation name exactly as it appears in the list - include everything before the "(also:" part. Do NOT truncate or modify the name. For example, if the list shows "Complete Blood Count (also: CBC, ...)", output exactly: "Complete Blood Count"

3. **NEW INVESTIGATIONS ONLY IF NO MATCH**: Only use the spoken investigation name verbatim if there is NO reasonable match in the list below.

{investigation_list}
"""
                logger.debug(f"[USER_PROMPT] Injected investigation list for doctor {doctor_id} ({len(investigation_list)} chars)")
            else:
                logger.debug(f"[USER_PROMPT] No investigation list found for doctor {doctor_id}")
        except Exception as e:
            logger.warning(f"[USER_PROMPT] Failed to get investigation list for doctor {doctor_id}: {e}")
    elif doctor_id and not has_investigation_list:
        logger.debug(f"[USER_PROMPT] Skipping investigation list injection - no lists for doctor {doctor_id}")

    # Patient history context injection (prescriptions, summaries, caution)
    patient_context_section = ""
    if patient_id and not _skip_doctor_artifacts:
        try:
            from .patient_context_service import (
                get_patient_context_for_extraction,
                format_patient_context_for_prompt
            )
            doctor_id_str = str(doctor_id) if doctor_id else None
            patient_context = get_patient_context_for_extraction(
                patient_id=patient_id,
                doctor_id=doctor_id_str,
                num_past_consultations=3,
                is_continuation=is_continuation,
                parent_extraction_ids=parent_extraction_ids,
            )
            if patient_context.get("has_context"):
                patient_context_section = format_patient_context_for_prompt(patient_context, is_continuation=is_continuation)
                caution_agg = patient_context.get('caution_aggregated')
                caution_info = f"Yes ({caution_agg.get('source_count', 0)} sources)" if caution_agg else 'No'
                logger.debug(
                    f"[USER_PROMPT] Injected patient context for patient {patient_id}: "
                    f"prescriptions={len(patient_context.get('past_prescriptions', []))}, "
                    f"summaries={len(patient_context.get('past_summaries', []))}, "
                    f"caution_aggregated={caution_info}, "
                    f"is_continuation={is_continuation}"
                )
            else:
                logger.debug(f"[USER_PROMPT] No patient context found for patient {patient_id}")
        except Exception as e:
            logger.warning(f"[USER_PROMPT] Failed to get patient context for patient {patient_id}: {e}")

    # Radiology-specific continuation snapshot — injected only for RADIOLOGY
    # is_continuation visits to keep prior PLAN phases / toxicity ids in the
    # LLM's view without re-introducing the OP-style merge principles.
    radiology_continuation_section = _build_radiology_continuation_context(
        consultation_type_code, is_continuation, parent_extraction_ids
    )

    todays_date_dd_mm_yyyy = datetime.now().strftime("%d-%m-%Y")

    user_prompt = f"""{extract_instruction}

**TODAY'S DATE:** {todays_date_dd_mm_yyyy} (DD-MM-YYYY). Use this as the anchor to resolve any relative time expressions (e.g., "in 10 days", "after 2 weeks", "next month") into explicit DD-MM-YYYY dates.

{header}
---
{transcript}
---

**EXTRACTION INSTRUCTIONS:**

1. Extract ALL information from the transcript following the segment structure defined in the system prompt
2. Use medical terminology appropriately (convert lay terms to medical terms unless configured otherwise)
3. Preserve all medical abbreviations as they appear
4. Use DD-MM-YYYY format for all dates. Convert relative expressions into explicit DD-MM-YYYY dates using TODAY'S DATE above as the anchor.
5. Include units with all numerical values
6. Use "" for single-value fields with no data
7. Use empty arrays [] for list fields with no data
8. DO NOT fabricate any information not present in the transcript
{special_instructions}
{medicine_list_section}
{investigation_list_section}
{patient_context_section}
{radiology_continuation_section}
Return ONLY the JSON object. No markdown, no explanations, no additional text.
"""

    return user_prompt


def _to_camel_case(snake_str: str) -> str:
    """Convert snake_case or space-separated string to camelCase"""
    import re
    # Split on underscores or spaces
    components = re.split(r'[_\s]+', snake_str.lower())
    # Filter out empty strings from consecutive delimiters
    components = [c for c in components if c]
    if not components:
        return snake_str.lower()
    return components[0] + ''.join(x.title() for x in components[1:])


def _schema_to_example(schema: Dict[str, Any]) -> Any:
    """Convert JSON schema to example structure.

    Handles edge cases where schema might be a string instead of dict
    (malformed database entries or shorthand type definitions).
    """
    # DEFENSIVE: Handle string inputs (e.g., "string" shorthand in DB)
    if isinstance(schema, str):
        logger.warning(f"[SCHEMA_TO_EXAMPLE] Received string instead of dict: '{schema}'. Treating as type shorthand.")
        return schema if schema in ("string", "number", "boolean", "array") else "value"

    # DEFENSIVE: Handle non-dict inputs
    if not isinstance(schema, dict):
        logger.warning(f"[SCHEMA_TO_EXAMPLE] Received unexpected type: {type(schema).__name__}. Returning 'value'.")
        return "value"

    schema_type = schema.get("type", "string")
    description = schema.get("description", "")

    if schema_type == "object":
        properties = schema.get("properties", {})
        example_obj = {}
        for prop_name, prop_schema in properties.items():
            # DEFENSIVE: Handle string property schemas
            if isinstance(prop_schema, str):
                logger.warning(f"[SCHEMA_TO_EXAMPLE] Property '{prop_name}' has string schema: '{prop_schema}'")
                example_obj[prop_name] = prop_schema
            else:
                example_obj[prop_name] = _schema_to_example(prop_schema)
        return example_obj

    elif schema_type == "array":
        items_schema = schema.get("items", {})
        # DEFENSIVE: Handle string items schema
        if isinstance(items_schema, str):
            return [items_schema]
        return [_schema_to_example(items_schema)] if items_schema else []

    elif schema_type == "string":
        if description:
            return f"string - {description[:50]}..." if len(description) > 50 else f"string - {description}"
        return "string"

    elif schema_type == "number":
        return "number"

    elif schema_type == "boolean":
        return "boolean"

    else:
        return "value"


# ============================================================================
# Dynamic Gemini Schema Generation
# ============================================================================

def generate_gemini_schema(
    segments: List[Dict[str, Any]],
    template_id: Optional[uuid.UUID] = None
) -> types.Schema:
    """
    Generate Gemini response_schema from segment list.

    NEW: If template_id is provided, tries to use pre-assembled schema first.
    Falls back to dynamic generation if assembled_schema_json is NULL.

    Args:
        segments: List of segment configurations with schema_definition_json
        template_id: Optional template ID to check for pre-assembled schema

    Returns:
        Gemini Schema object for use in GenerateContentConfig
    """
    # NEW: Try pre-assembled schema first if template_id is provided
    if template_id:
        try:
            from .template_assembly_service import get_template_by_id
            template = get_template_by_id(template_id)
            if template and template.get("assembled_schema_json"):
                logger.debug(f"[SCHEMA_GENERATION] ✅ Using pre-assembled schema for template {template_id} (assembled at: {template.get('schema_assembled_at')})")
                # Convert stored JSON to Gemini types.Schema
                assembled_json = template["assembled_schema_json"]
                return _json_schema_to_gemini_schema(assembled_json)
            else:
                logger.warning(f"[SCHEMA_GENERATION] No pre-assembled schema for template {template_id}, falling back to dynamic generation")
        except Exception as e:
            logger.warning(f"[SCHEMA_GENERATION] Error checking pre-assembled schema for template {template_id}: {e}, falling back to dynamic generation")

    # FALLBACK: Dynamic schema generation from segment definitions
    properties = {}

    logger.debug(f"[SCHEMA_GENERATION] Generating schema for {len(segments)} segments")

    # Log all segment codes being included (with defensive handling)
    segment_codes = []
    for s in segments:
        if isinstance(s, dict):
            segment_codes.append(s.get("segment_code", "UNKNOWN"))
        elif isinstance(s, str):
            segment_codes.append(f"STRING:{s[:20]}")
        else:
            segment_codes.append(f"TYPE:{type(s).__name__}")
    logger.debug(f"[SCHEMA_GENERATION] Segments to extract: {', '.join(segment_codes)}")

    total_schema_complexity = 0  # Track total complexity
    segment_details = []  # Track per-segment details for debugging

    for idx, segment in enumerate(segments):
        # DEFENSIVE: Handle non-dict segments
        if isinstance(segment, str):
            logger.warning(f"[SCHEMA_GENERATION] Segment at index {idx} is a string: '{segment[:100]}...'")
            field_name = f"segment_{idx}"
            properties[field_name] = types.Schema(type=types.Type.STRING, description=f"Segment data (from string: {segment[:50]})")
            continue
        if not isinstance(segment, dict):
            logger.warning(f"[SCHEMA_GENERATION] Segment at index {idx} is unexpected type: {type(segment).__name__}")
            field_name = f"segment_{idx}"
            properties[field_name] = types.Schema(type=types.Type.STRING, description="Segment data")
            continue

        segment_code = segment.get("segment_code", f"segment_{idx}")
        segment_category = segment.get("category", segment.get("default_category", "unknown"))
        schema_json = segment.get("schema_definition_json", {})

        if isinstance(schema_json, str):
            try:
                schema_json = json.loads(schema_json)
            except json.JSONDecodeError as e:
                logger.warning(f"[SCHEMA_GENERATION] Failed to parse schema_json for {segment_code}: {e}")
                field_name = _to_camel_case(segment_code)
                properties[field_name] = types.Schema(type=types.Type.STRING, description="Segment data (parse error)")
                continue

        # Log schema complexity for debugging
        schema_str = json.dumps(schema_json)
        schema_size = len(schema_str)
        total_schema_complexity += schema_size

        # Track details for summary
        segment_details.append({
            "code": segment_code,
            "category": segment_category,
            "size": schema_size
        })

        logger.debug(f"[SCHEMA_GENERATION] Segment: {segment_code} (category: {segment_category}, size: {schema_size} chars)")

        # Check for problematic patterns
        if "enum" in schema_str:
            logger.warning(f"[SCHEMA_GENERATION] Segment {segment_code} contains 'enum' - this may cause Gemini errors")
        if "pattern" in schema_str:
            logger.warning(f"[SCHEMA_GENERATION] Segment {segment_code} contains 'pattern' - this may cause Gemini errors")
        if "minimum" in schema_str or "maximum" in schema_str:
            logger.warning(f"[SCHEMA_GENERATION] Segment {segment_code} contains min/max constraints - this may cause Gemini errors")

        # Convert JSON schema to Gemini Schema
        field_name = _to_camel_case(segment_code)
        properties[field_name] = _json_schema_to_gemini_schema(schema_json)

    logger.debug(f"[SCHEMA_GENERATION] Generated schema with {len(properties)} properties, total complexity: {total_schema_complexity} chars")

    # Log detailed segment breakdown
    logger.debug("[SCHEMA_GENERATION] Segment breakdown by category:")
    category_summary = {}
    for detail in segment_details:
        cat = detail["category"]
        if cat not in category_summary:
            category_summary[cat] = {"count": 0, "total_size": 0}
        category_summary[cat]["count"] += 1
        category_summary[cat]["total_size"] += detail["size"]

    for cat, stats in category_summary.items():
        logger.debug(f"[SCHEMA_GENERATION]   {cat.upper()}: {stats['count']} segments, {stats['total_size']} chars")

    # Warn if schema is extremely complex (empirical limit around 50-60 segments with complex schemas)
    if total_schema_complexity > 50000:
        logger.warning(f"[SCHEMA_GENERATION] Schema complexity ({total_schema_complexity} chars) may exceed Gemini limits!")
        logger.warning("[SCHEMA_GENERATION] Consider using 'core' or 'additional' mode instead of 'full' for better performance")
    elif total_schema_complexity > 8000:
        logger.warning(f"[SCHEMA_GENERATION] Schema complexity ({total_schema_complexity} chars) is high - monitor for Gemini errors")

    return types.Schema(
        type=types.Type.OBJECT,
        properties=properties,
        required=list(properties.keys())  # All segments are required in output
    )


def _build_combined_json_schema(segments: list) -> Dict[str, Any]:
    """
    Build a combined JSON Schema dict from segment definitions.

    This provides the raw JSON Schema (standard format) for use with
    non-Gemini providers (Claude/OpenAI) that accept JSON Schema directly.

    Args:
        segments: List of segment configurations with schema_definition_json

    Returns:
        Combined JSON Schema dict with all segment properties
    """
    properties = {}

    for idx, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue

        segment_code = segment.get("segment_code", f"segment_{idx}")
        schema_json = segment.get("schema_definition_json", {})

        if isinstance(schema_json, str):
            try:
                schema_json = json.loads(schema_json)
            except json.JSONDecodeError:
                schema_json = {"type": "string"}

        field_name = _to_camel_case(segment_code)
        properties[field_name] = schema_json

    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys())
    }


def _gemini_schema_to_json_schema(gemini_schema: types.Schema) -> Dict[str, Any]:
    """
    Convert a Gemini types.Schema object to standard JSON Schema dict.

    Used to provide json_schema for non-Gemini providers when hardcoded
    Gemini schemas are used (NEONATAL_DAILY, OPTOMETRY, etc.).
    """
    raw = gemini_schema.to_json_dict()

    def _fix_types(obj):
        if isinstance(obj, dict):
            if "type" in obj and isinstance(obj["type"], str):
                obj["type"] = obj["type"].lower()
            for v in obj.values():
                _fix_types(v)
        elif isinstance(obj, list):
            for item in obj:
                _fix_types(item)

    _fix_types(raw)
    return raw


def _json_schema_to_gemini_schema(json_schema: Dict[str, Any]) -> types.Schema:
    """
    Convert JSON schema dict to Gemini Schema object recursively.

    Strips out constraints that can cause Gemini's "too many states" error:
    - enum values
    - minimum/maximum bounds
    - pattern constraints
    - format specifications
    - array length limits (minItems, maxItems)

    Handles edge cases where schema might be a string instead of dict.
    """
    # DEFENSIVE: Handle string inputs (e.g., "string" shorthand in DB)
    if isinstance(json_schema, str):
        logger.warning(f"[JSON_TO_GEMINI] Received string instead of dict: '{json_schema}'. Converting to STRING schema.")
        return types.Schema(type=types.Type.STRING, description=f"(from shorthand: {json_schema})")

    # DEFENSIVE: Handle non-dict inputs
    if not isinstance(json_schema, dict):
        logger.warning(f"[JSON_TO_GEMINI] Received unexpected type: {type(json_schema).__name__}. Returning STRING schema.")
        return types.Schema(type=types.Type.STRING)

    schema_type = json_schema.get("type", "string")
    description = json_schema.get("description", "")

    if schema_type == "object":
        properties = json_schema.get("properties", {})
        gemini_properties = {}
        for prop_name, prop_schema in properties.items():
            # DEFENSIVE: Handle string property schemas
            if isinstance(prop_schema, str):
                logger.warning(f"[JSON_TO_GEMINI] Property '{prop_name}' has string schema: '{prop_schema}'")
                gemini_properties[prop_name] = types.Schema(type=types.Type.STRING, description=f"(from shorthand: {prop_schema})")
            else:
                gemini_properties[prop_name] = _json_schema_to_gemini_schema(prop_schema)

        required_fields = json_schema.get("required", [])
        return types.Schema(
            type=types.Type.OBJECT,
            properties=gemini_properties,
            required=required_fields if required_fields else None,
            description=description if description else None
        )

    elif schema_type == "array":
        items_schema = json_schema.get("items", {})
        # DEFENSIVE: Handle string items schema
        if isinstance(items_schema, str):
            logger.warning(f"[JSON_TO_GEMINI] Array items has string schema: '{items_schema}'")
            items_gemini = types.Schema(type=types.Type.STRING, description=f"(from shorthand: {items_schema})")
        else:
            items_gemini = _json_schema_to_gemini_schema(items_schema)
        # Note: Intentionally NOT passing minItems/maxItems to avoid "too many states" error
        # Gemini will still generate arrays, just without length constraints
        return types.Schema(
            type=types.Type.ARRAY,
            items=items_gemini,
            description=description if description else None
        )

    elif schema_type == "string":
        # Note: Intentionally NOT passing enum, pattern, format, minLength, maxLength
        # to avoid "too many states" error. Gemini will still generate valid strings.
        return types.Schema(
            type=types.Type.STRING,
            description=description if description else None
        )

    elif schema_type == "number":
        # Note: Intentionally NOT passing minimum, maximum, multipleOf
        # to avoid "too many states" error. Gemini will still generate valid numbers.
        return types.Schema(
            type=types.Type.NUMBER,
            description=description if description else None
        )

    elif schema_type == "boolean":
        return types.Schema(
            type=types.Type.BOOLEAN,
            description=description if description else None
        )

    else:
        # Default to STRING for unknown types
        return types.Schema(
            type=types.Type.STRING,
            description=description if description else None
        )


# ============================================================================
# Configuration Validation
# ============================================================================

def validate_segments_for_extraction(
    segments: List[Dict[str, Any]],
    doctor_id: Optional[uuid.UUID] = None
) -> Dict[str, Any]:
    """
    Validate segment configuration before extraction.

    Args:
        segments: List of segment configurations
        doctor_id: Doctor ID for database validation (optional)

    Returns:
        Dict with 'is_valid' (bool), 'error_message' (str or None), 'warnings' (list)
    """
    errors = []
    warnings = []

    # Check that required segments are present
    required_segments = [s for s in segments if s.get("is_required", False)]
    if not required_segments:
        warnings.append("No required segments found - extraction may be incomplete")

    # Check for at least one segment
    if len(segments) == 0:
        errors.append("No segments configured for extraction")

    # Validate with database if doctor_id provided
    if doctor_id:
        db_validation = validate_segment_configuration(doctor_id)
        if not db_validation.get("is_valid", False):
            errors.append(db_validation.get("error_message", "Database validation failed"))

    return {
        "is_valid": len(errors) == 0,
        "error_message": "; ".join(errors) if errors else None,
        "warnings": warnings
    }


# ============================================================================
# Convenience Functions
# ============================================================================

def generate_extraction_artifacts(
    consultation_type_id: uuid.UUID,
    doctor_id: Optional[uuid.UUID],
    template_code: Optional[str],
    mode: str,
    transcript: str,
    patient_id: Optional[str] = None,
    has_medicine_list: bool = True,
    has_investigation_list: bool = True,
    is_continuation: bool = False,
    parent_extraction_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generate all extraction artifacts (prompts + schema) in one call.

    Args:
        consultation_type_id: Consultation type ID (OP, DISCHARGE, etc.)
        doctor_id: Doctor ID for personalized configuration
        template_code: Template code for template-specific configuration (optional, unique identifier)
        mode: 'core' | 'additional' | 'full'
        transcript: Consultation transcript
        patient_id: Patient ID for history context injection (optional)
        has_medicine_list: Whether doctor/hospital has medicine lists (skip injection if False)
        has_investigation_list: Whether doctor/hospital has investigation lists (skip injection if False)

    Returns:
        Dict with keys: system_prompt, user_prompt, schema, segments, validation
    """
    import time
    artifacts_start = time.time()

    # Resolve actual consultation type code from consultation_type_id
    # template_code is used for routing (split types, hardcoded schemas)
    # but prompt config lookups need the real type_code from consultation_types table
    from .supabase_service import get_consultation_type_by_id_cached
    ct_data = get_consultation_type_by_id_cached(consultation_type_id)
    consultation_type_code = ct_data["type_code"] if ct_data else template_code
    lookup_duration = 0.0

    logger.debug(f"[EXTRACTION_ARTIFACTS] Starting generation for template_code={template_code}, consultation_type_code={consultation_type_code}, mode={mode}, doctor_id={doctor_id}")

    # =========================================================================
    # OPTIMIZATION: Check for pre-assembled content FIRST (before loading segments)
    # This saves 3-5 database queries (~100-300ms) when pre-assembled exists
    # =========================================================================
    if template_code:
        try:
            from .supabase_service import get_template_by_code
            from .template_assembly_service import get_template_by_id

            template = get_template_by_code(template_code)
            if template:
                template_id = uuid.UUID(template["id"])
                template_full = get_template_by_id(template_id)

                if template_full and template_full.get("assembled_full_prompt") and template_full.get("assembled_schema_json"):
                    logger.debug(f"[EXTRACTION_ARTIFACTS] ⚡ FAST PATH: Using pre-assembled content for template '{template_code}'")

                    # Get pre-assembled system prompt
                    system_prompt = template_full["assembled_full_prompt"]

                    # Convert pre-assembled schema JSON to Gemini Schema
                    schema_convert_start = time.time()
                    assembled_schema = _json_schema_to_gemini_schema(template_full["assembled_schema_json"])
                    schema_convert_duration = time.time() - schema_convert_start
                    logger.info(f"[TIMING_ARTIFACTS] schema conversion: {schema_convert_duration:.3f}s")

                    # Generate user prompt with medicine list and patient context injection
                    user_prompt_start = time.time()
                    user_prompt = generate_user_prompt([], consultation_type_code, transcript, doctor_id=doctor_id, patient_id=patient_id, has_medicine_list=has_medicine_list, has_investigation_list=has_investigation_list, is_continuation=is_continuation, parent_extraction_ids=parent_extraction_ids)
                    user_prompt_duration = time.time() - user_prompt_start
                    logger.info(f"[TIMING_ARTIFACTS] user_prompt generation: {user_prompt_duration:.3f}s")

                    # Derive segment_count from schema properties
                    schema_segment_count = len(assembled_schema.properties) if hasattr(assembled_schema, 'properties') else 0

                    # Get pre-computed excluded segment codes (populated during assembly)
                    excluded_segment_codes = set(template_full.get("excluded_segment_codes") or [])

                    total_artifacts_duration = time.time() - artifacts_start
                    logger.info(f"[TIMING_ARTIFACTS] ⚡ FAST PATH total: {total_artifacts_duration:.3f}s (lookup={lookup_duration:.3f}s, schema={schema_convert_duration:.3f}s, user_prompt={user_prompt_duration:.3f}s)")
                    logger.debug(f"[EXTRACTION_ARTIFACTS] ⚡ Pre-assembled prompt: {len(system_prompt)} chars, schema: {schema_segment_count} segments, excluded: {len(excluded_segment_codes)}")

                    return {
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt,
                        "schema": assembled_schema,
                        "json_schema": template_full["assembled_schema_json"],  # Raw JSON Schema for non-Gemini providers
                        "segments": [],  # Not needed - reorder_by_display_order is commented out
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},  # Pre-validated at assembly time
                        "segment_count": schema_segment_count,
                        "mode": mode,
                        "consultation_type_id": str(consultation_type_id),
                        "template_code": template_code,
                        "excluded_segment_codes": excluded_segment_codes  # Pre-computed during assembly
                    }
                else:
                    logger.debug(f"[EXTRACTION_ARTIFACTS] Pre-assembled content not found for template '{template_code}', falling back to dynamic generation")
        except Exception as e:
            logger.warning(f"[EXTRACTION_ARTIFACTS] Error checking pre-assembled content: {e}, falling back to dynamic generation")

    # =========================================================================
    # HARDCODED SCHEMAS (for non-split specialized consultation types)
    # Note: Split extraction types are handled by gemini_service BEFORE calling this function
    # =========================================================================
    if template_code in ["NEO_DAILY", "OPTOMETRY", "OPHTHAL_RX", "OPHTHAL_POSTOP_RX"]:
        match template_code:
            case "NEO_DAILY":
                logger.debug(f"[NEONATAL_SCHEMA] ✅ Using hardcoded NEO_DAILY schema for {template_code}")
                return {
                    "system_prompt": NEO_DAILY_PROMPT_SYSTEM,
                    "user_prompt": NEO_DAILY_PROMPT_USER.format(transcript=transcript),
                    "schema": NEO_DAILY_PARAMETERS_SCHEMA,
                    "json_schema": _gemini_schema_to_json_schema(NEO_DAILY_PARAMETERS_SCHEMA),
                    "segments": [],
                    "validation": {"is_valid": True, "error_message": None, "warnings": []},
                    "segment_count": 1,
                    "mode": mode,
                    "consultation_type_id": str(consultation_type_id),
                    "template_code": template_code
                }
            case "OPTOMETRY":
                logger.debug(f"[OPTOMETRY_SCHEMA] ✅ Using hardcoded NESTED OPTOMETRY schema for {template_code}")
                schema_fields = list(OPTO_PARAMETERS_SCHEMA.properties.keys())[:5]
                logger.debug(f"[OPTOMETRY_SCHEMA] 🔍 First 5 schema fields: {schema_fields}")
                logger.debug(f"[OPTOMETRY_SCHEMA] 🔍 Total schema properties: {len(OPTO_PARAMETERS_SCHEMA.properties)}")
                return {
                    "system_prompt": OPTO_SYSTEM_PROMPT,
                    "user_prompt": OPTO_USER_PROMPT.format(transcript=transcript),
                    "schema": OPTO_PARAMETERS_SCHEMA,
                    "json_schema": _gemini_schema_to_json_schema(OPTO_PARAMETERS_SCHEMA),
                    "segments": [],
                    "validation": {"is_valid": True, "error_message": None, "warnings": []},
                    "segment_count": 1,
                    "mode": mode,
                    "consultation_type_id": str(consultation_type_id),
                    "template_code": template_code
                }
            case "OPHTHAL_RX":
                logger.debug(f"[OPHTHAL_PRESCRIPTION_SCHEMA] ✅ Using hardcoded OPHTHAL_PRESCRIPTION schema for {template_code}")
                schema_fields = list(OPHTHAL_PRESCRIPTION_SCHEMA.properties.keys())[:5]
                logger.debug(f"[OPHTHAL_PRESCRIPTION_SCHEMA] 🔍 First 5 schema fields: {schema_fields}")
                logger.debug(f"[OPHTHAL_PRESCRIPTION_SCHEMA] 🔍 Total schema properties: {len(OPHTHAL_PRESCRIPTION_SCHEMA.properties)}")
                # Get today's date in dd/mm/yy format for the consultation_date placeholder
                consultation_date = datetime.now().strftime("%d/%m/%y")
                return {
                    "system_prompt": OPHTHAL_PRESCRIPTION_SYSTEM_PROMPT,
                    "user_prompt": OPHTHAL_PRESCRIPTION_USER_PROMPT.format(
                        transcript=transcript,
                        consultation_date=consultation_date
                    ),
                    "schema": OPHTHAL_PRESCRIPTION_SCHEMA,
                    "json_schema": _gemini_schema_to_json_schema(OPHTHAL_PRESCRIPTION_SCHEMA),
                    "segments": [],
                    "validation": {"is_valid": True, "error_message": None, "warnings": []},
                    "segment_count": 1,
                    "mode": mode,
                    "consultation_type_id": str(consultation_type_id),
                    "template_code": template_code
                }
            case "OPHTHAL_POSTOP_RX":
                logger.debug(f"[OPHTHAL_POSTOP_RX_SCHEMA] ✅ Using hardcoded OPHTHAL_POSTOP_RX schema for {template_code}")
                schema_fields = list(OPHTHAL_POSTOP_RX_SCHEMA.properties.keys())[:5]
                logger.debug(f"[OPHTHAL_POSTOP_RX_SCHEMA] 🔍 First 5 schema fields: {schema_fields}")
                logger.debug(f"[OPHTHAL_POSTOP_RX_SCHEMA] 🔍 Total schema properties: {len(OPHTHAL_POSTOP_RX_SCHEMA.properties)}")
                # Get today's date in dd/mm/yy format for the consultation_date placeholder
                consultation_date = datetime.now().strftime("%d/%m/%y")
                return {
                    "system_prompt": OPHTHAL_POSTOP_RX_SYSTEM_PROMPT,
                    "user_prompt": OPHTHAL_POSTOP_RX_USER_PROMPT.format(
                        transcript=transcript,
                        consultation_date=consultation_date
                    ),
                    "schema": OPHTHAL_POSTOP_RX_SCHEMA,
                    "json_schema": _gemini_schema_to_json_schema(OPHTHAL_POSTOP_RX_SCHEMA),
                    "segments": [],
                    "validation": {"is_valid": True, "error_message": None, "warnings": []},
                    "segment_count": 1,
                    "mode": mode,
                    "consultation_type_id": str(consultation_type_id),
                    "template_code": template_code
                }

    # Load segments for this consultation type
    segment_result = load_segments_for_mode(
        consultation_type_id=consultation_type_id,
        doctor_id=doctor_id,
        template_code=template_code,
        mode=mode
    )
    segments = segment_result.get("segments", [])
    excluded_segment_codes = segment_result.get("excluded_segment_codes", set())

    logger.debug(f"[EXTRACTION_ARTIFACTS] Loaded {len(segments)} segments for mode='{mode}'")

    # Handle empty segments gracefully (e.g., 'additional' mode with no ADDITIONAL category segments)
    if not segments:
        logger.debug(f"[EXTRACTION] No segments found for mode={mode}, returning empty result")
        return {
            "system_prompt": "",
            "user_prompt": "",
            "schema": None,
            "segments": [],
            "validation": {"is_valid": True, "error_message": None, "warnings": []},
            "segment_count": 0
        }

    # Validate
    validation = validate_segments_for_extraction(segments, doctor_id=doctor_id)

    if not validation["is_valid"]:
        raise ValueError(f"Invalid segment configuration: {validation['error_message']}")

    # Resolve template_id from template_code for pre-assembled prompt/schema lookup
    template_id = None
    if template_code:
        from .supabase_service import get_template_by_code
        template = get_template_by_code(template_code)
        if template:
            template_id = uuid.UUID(template["id"])
            logger.debug(f"[EXTRACTION_ARTIFACTS] Resolved template_code '{template_code}' to template_id {template_id}")

    # Generate prompts and schema with consultation-type-specific prompts
    # Pass template_id to use pre-assembled content when available
    system_prompt = generate_system_prompt(segments, consultation_type_code, template_id=template_id)
    user_prompt = generate_user_prompt(segments, consultation_type_code, transcript, doctor_id=doctor_id, patient_id=patient_id, has_medicine_list=has_medicine_list, has_investigation_list=has_investigation_list, is_continuation=is_continuation, parent_extraction_ids=parent_extraction_ids)
    schema = generate_gemini_schema(segments, template_id=template_id)

    # Build raw JSON schema for non-Gemini providers (Claude/OpenAI)
    json_schema = _build_combined_json_schema(segments)

    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "schema": schema,
        "json_schema": json_schema,  # Raw JSON Schema for non-Gemini providers
        "segments": segments,
        "validation": validation,
        "segment_count": len(segments),
        "mode": mode,
        "consultation_type_id": str(consultation_type_id),
        "template_code": template_code,
        "excluded_segment_codes": excluded_segment_codes  # For response filtering
    }


# ============================================================================
# Parallel Generation Support (for recording workflow optimization)
# ============================================================================

def generate_extraction_artifacts_without_transcript(
    consultation_type_id: uuid.UUID,
    doctor_id: Optional[uuid.UUID],
    template_code: Optional[str],
    mode: str,
    patient_id: Optional[str] = None,
    has_medicine_list: bool = True,
    has_investigation_list: bool = True,
    is_continuation: bool = False,
    parent_extraction_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generate extraction artifacts WITHOUT transcript (for parallel generation during transcription).

    This function generates:
    - System prompt (segment instructions)
    - Gemini schema (output structure)
    - User prompt TEMPLATE (with {transcript} placeholder)

    The user prompt template can be populated later with actual transcript
    for near-zero-cost final prompt generation.

    Args:
        consultation_type_id: Consultation type ID (OP, DISCHARGE, etc.)
        doctor_id: Doctor ID for personalized configuration
        template_code: Template code for template-specific configuration (optional, unique identifier)
        mode: 'core' | 'additional' | 'full'
        patient_id: Patient ID for history context injection (optional)
        has_medicine_list: Whether doctor/hospital has medicine lists (skip injection if False)
        has_investigation_list: Whether doctor/hospital has investigation lists (skip injection if False)

    Returns:
        Dict with keys: system_prompt, user_prompt_template, schema, segments, validation

    Usage:
        # During transcription (parallel):
        artifacts = generate_extraction_artifacts_without_transcript(...)

        # After transcription (instant):
        user_prompt = artifacts['user_prompt_template'].format(transcript=actual_transcript)
    """
    # Resolve actual consultation type code from consultation_type_id
    # template_code is used for routing (split types, hardcoded schemas)
    # but prompt config lookups need the real type_code from consultation_types table
    from .supabase_service import get_consultation_type_by_id_cached
    ct_data = get_consultation_type_by_id_cached(consultation_type_id)
    consultation_type_code = ct_data["type_code"] if ct_data else template_code

    # =========================================================================
    # OPTIMIZATION: Check for pre-assembled content FIRST (before loading segments)
    # This saves 3-5 database queries (~100-300ms) when pre-assembled exists
    # =========================================================================
    if template_code:
        try:
            from .supabase_service import get_template_by_code
            from .template_assembly_service import get_template_by_id

            template = get_template_by_code(template_code)
            if template:
                template_id = uuid.UUID(template["id"])
                template_full = get_template_by_id(template_id)

                if template_full and template_full.get("assembled_full_prompt") and template_full.get("assembled_schema_json"):
                    logger.debug(f"[OPTIMIZATION] ⚡ FAST PATH: Using pre-assembled content for template '{template_code}'")

                    # Get pre-assembled system prompt
                    system_prompt = template_full["assembled_full_prompt"]

                    # Convert pre-assembled schema JSON to Gemini Schema
                    assembled_schema = _json_schema_to_gemini_schema(template_full["assembled_schema_json"])

                    # Generate user prompt TEMPLATE with medicine list and patient context injection
                    user_prompt_template = _generate_user_prompt_template([], consultation_type_code, doctor_id=doctor_id, patient_id=patient_id, has_medicine_list=has_medicine_list, has_investigation_list=has_investigation_list, is_continuation=is_continuation, parent_extraction_ids=parent_extraction_ids)

                    # Derive segment_count from schema properties
                    schema_segment_count = len(assembled_schema.properties) if hasattr(assembled_schema, 'properties') else 0

                    # Get pre-computed excluded segment codes (populated during assembly)
                    excluded_segment_codes = set(template_full.get("excluded_segment_codes") or [])

                    logger.debug("[OPTIMIZATION] ⚡ FAST PATH: Skipped load_segments_for_mode, validate_segments_for_extraction")
                    logger.debug(f"[OPTIMIZATION] ⚡ Pre-assembled prompt: {len(system_prompt)} chars, schema: {schema_segment_count} segments, excluded: {len(excluded_segment_codes)}")

                    return {
                        "system_prompt": system_prompt,
                        "user_prompt_template": user_prompt_template,
                        "schema": assembled_schema,
                        "json_schema": template_full["assembled_schema_json"],  # Raw JSON Schema for non-Gemini providers
                        "segments": [],  # Not needed - reorder_by_display_order is commented out
                        "validation": {"is_valid": True, "error_message": None, "warnings": []},  # Pre-validated at assembly time
                        "segment_count": schema_segment_count,
                        "mode": mode,
                        "consultation_type_id": str(consultation_type_id),
                        "template_code": template_code,
                        "excluded_segment_codes": excluded_segment_codes  # Pre-computed during assembly
                    }
                else:
                    logger.debug(f"[OPTIMIZATION] Pre-assembled content not found for template '{template_code}', falling back to dynamic generation")
        except Exception as e:
            logger.warning(f"[OPTIMIZATION] Error checking pre-assembled content: {e}, falling back to dynamic generation")

    # =========================================================================
    # SPLIT EXTRACTION TYPES (handled by gemini_service with hardcoded two-part extraction)
    # These types have complex schemas that require split extraction calls.
    # Return early with a marker to skip parallel prompt generation - gemini_service
    # will use its own hardcoded prompts during the actual extraction phase.
    # =========================================================================
    SPLIT_EXTRACTION_TYPES = {
        "OPHTHAL_CONSULT_BRIEF", "OPHTHA_DISCHARGE", "OPHTHAL_FULL_CONSULT",
        "NEO_OP", "NEO_PROFORMA", "NEO_DISCHARGE",
        "NEO_ADMISSION", "NEO_DAILY", "NEO_DAILY_FREE",
        "NEO_PROFORMA_FREE", "NEO_DISCHARGE_FREE",
        "NEO_POSTNATAL_DAY_FREE", "NEO_POSTNATAL_DISCHARGE_FREE",
    }
    if template_code in SPLIT_EXTRACTION_TYPES:
        logger.debug(f"[OPTIMIZATION] ⚡ SPLIT EXTRACTION TYPE: {template_code} - skipping parallel prompt generation")
        logger.debug(f"[OPTIMIZATION] ⚡ Prompts will be provided by gemini_service during extraction phase")
        return {
            "system_prompt": None,  # Will be provided by gemini_service
            "user_prompt_template": None,
            "schema": None,
            "segments": [],
            "validation": {"is_valid": True, "error_message": None, "warnings": []},
            "segment_count": 0,  # Marker for split extraction
            "mode": mode,
            "consultation_type_id": str(consultation_type_id),
            "template_code": template_code,
            "is_split_extraction": True  # Marker for recording_processor to skip caching
        }

    # =========================================================================
    # HARDCODED SCHEMAS (for non-split specialized consultation types)
    # These types have hardcoded prompts/schemas but use single-call extraction.
    # =========================================================================
    if template_code in ["NEO_DAILY", "OPTOMETRY", "OPHTHAL_RX", "OPHTHAL_POSTOP_RX"]:
        match template_code:
            case "NEO_DAILY":
                logger.debug(f"[OPTIMIZATION] [NEONATAL_SCHEMA] ✅ Using hardcoded NEO_DAILY schema for {template_code}")
                return {
                    "system_prompt": NEO_DAILY_PROMPT_SYSTEM,
                    "user_prompt_template": NEO_DAILY_PROMPT_USER,
                    "schema": NEO_DAILY_PARAMETERS_SCHEMA,
                    "json_schema": _gemini_schema_to_json_schema(NEO_DAILY_PARAMETERS_SCHEMA),
                    "segments": [],
                    "validation": {"is_valid": True, "error_message": None, "warnings": []},
                    "segment_count": 1,
                    "mode": mode,
                    "consultation_type_id": str(consultation_type_id),
                    "template_code": template_code
                }
            case "OPTOMETRY":
                logger.debug(f"[OPTIMIZATION] [OPTOMETRY_SCHEMA] ✅ Using hardcoded NESTED OPTOMETRY schema for {template_code}")
                schema_fields = list(OPTO_PARAMETERS_SCHEMA.properties.keys())[:5]
                logger.debug(f"[OPTIMIZATION] [OPTOMETRY_SCHEMA] 🔍 First 5 schema fields: {schema_fields}")
                logger.debug(f"[OPTIMIZATION] [OPTOMETRY_SCHEMA] 🔍 Total schema properties: {len(OPTO_PARAMETERS_SCHEMA.properties)}")
                return {
                    "system_prompt": OPTO_SYSTEM_PROMPT,
                    "user_prompt_template": OPTO_USER_PROMPT,
                    "schema": OPTO_PARAMETERS_SCHEMA,
                    "json_schema": _gemini_schema_to_json_schema(OPTO_PARAMETERS_SCHEMA),
                    "segments": [],
                    "validation": {"is_valid": True, "error_message": None, "warnings": []},
                    "segment_count": 1,
                    "mode": mode,
                    "consultation_type_id": str(consultation_type_id),
                    "template_code": template_code
                }
            case "OPHTHAL_RX":
                logger.debug(f"[OPTIMIZATION] [OPHTHAL_PRESCRIPTION_SCHEMA] ✅ Using hardcoded OPHTHAL_PRESCRIPTION schema for {template_code}")
                schema_fields = list(OPHTHAL_PRESCRIPTION_SCHEMA.properties.keys())[:5]
                logger.debug(f"[OPTIMIZATION] [OPHTHAL_PRESCRIPTION_SCHEMA] 🔍 First 5 schema fields: {schema_fields}")
                logger.debug(f"[OPTIMIZATION] [OPHTHAL_PRESCRIPTION_SCHEMA] 🔍 Total schema properties: {len(OPHTHAL_PRESCRIPTION_SCHEMA.properties)}")
                consultation_date = datetime.now().strftime("%d/%m/%y")
                user_prompt_template = OPHTHAL_PRESCRIPTION_USER_PROMPT.replace(
                    "{consultation_date}", consultation_date
                )
                return {
                    "system_prompt": OPHTHAL_PRESCRIPTION_SYSTEM_PROMPT,
                    "user_prompt_template": user_prompt_template,
                    "schema": OPHTHAL_PRESCRIPTION_SCHEMA,
                    "json_schema": _gemini_schema_to_json_schema(OPHTHAL_PRESCRIPTION_SCHEMA),
                    "segments": [],
                    "validation": {"is_valid": True, "error_message": None, "warnings": []},
                    "segment_count": 1,
                    "mode": mode,
                    "consultation_type_id": str(consultation_type_id),
                    "template_code": template_code
                }
            case "OPHTHAL_POSTOP_RX":
                logger.debug(f"[OPTIMIZATION] [OPHTHAL_POSTOP_RX_SCHEMA] ✅ Using hardcoded OPHTHAL_POSTOP_RX schema for {template_code}")
                schema_fields = list(OPHTHAL_POSTOP_RX_SCHEMA.properties.keys())[:5]
                logger.debug(f"[OPTIMIZATION] [OPHTHAL_POSTOP_RX_SCHEMA] 🔍 First 5 schema fields: {schema_fields}")
                logger.debug(f"[OPTIMIZATION] [OPHTHAL_POSTOP_RX_SCHEMA] 🔍 Total schema properties: {len(OPHTHAL_POSTOP_RX_SCHEMA.properties)}")
                consultation_date = datetime.now().strftime("%d/%m/%y")
                user_prompt_template = OPHTHAL_POSTOP_RX_USER_PROMPT.replace(
                    "{consultation_date}", consultation_date
                )
                return {
                    "system_prompt": OPHTHAL_POSTOP_RX_SYSTEM_PROMPT,
                    "user_prompt_template": user_prompt_template,
                    "schema": OPHTHAL_POSTOP_RX_SCHEMA,
                    "json_schema": _gemini_schema_to_json_schema(OPHTHAL_POSTOP_RX_SCHEMA),
                    "segments": [],
                    "validation": {"is_valid": True, "error_message": None, "warnings": []},
                    "segment_count": 1,
                    "mode": mode,
                    "consultation_type_id": str(consultation_type_id),
                    "template_code": template_code
                }
    # Load segments for this consultation type
    segment_result = load_segments_for_mode(
        consultation_type_id=consultation_type_id,
        doctor_id=doctor_id,
        template_code=template_code,
        mode=mode
    )
    segments = segment_result.get("segments", [])
    excluded_segment_codes = segment_result.get("excluded_segment_codes", set())

    # Validate
    validation = validate_segments_for_extraction(segments, doctor_id=doctor_id)

    if not validation["is_valid"]:
        raise ValueError(f"Invalid segment configuration: {validation['error_message']}")

    # Resolve template_id from template_code for pre-assembled prompt/schema lookup
    template_id = None
    if template_code:
        from .supabase_service import get_template_by_code
        template = get_template_by_code(template_code)
        if template:
            template_id = uuid.UUID(template["id"])
            logger.debug(f"[OPTIMIZATION] Resolved template_code '{template_code}' to template_id {template_id}")

    # Generate system prompt and schema (no transcript needed)
    # Pass template_id to use pre-assembled content when available
    system_prompt = generate_system_prompt(segments, consultation_type_code, template_id=template_id)
    schema = generate_gemini_schema(segments, template_id=template_id)

    # Build raw JSON schema for non-Gemini providers (Claude/OpenAI)
    json_schema = _build_combined_json_schema(segments)

    # Generate user prompt TEMPLATE with placeholder, medicine list, and patient context injection
    user_prompt_template = _generate_user_prompt_template(segments, consultation_type_code, doctor_id=doctor_id, patient_id=patient_id, has_medicine_list=has_medicine_list, has_investigation_list=has_investigation_list, is_continuation=is_continuation, parent_extraction_ids=parent_extraction_ids)

    return {
        "system_prompt": system_prompt,
        "user_prompt_template": user_prompt_template,
        "schema": schema,
        "json_schema": json_schema,  # Raw JSON Schema for non-Gemini providers
        "segments": segments,
        "validation": validation,
        "segment_count": len(segments),
        "mode": mode,
        "consultation_type_id": str(consultation_type_id),
        "template_code": template_code,
        "excluded_segment_codes": excluded_segment_codes  # For response filtering
    }


def _generate_user_prompt_template(
    segments: List[Dict[str, Any]],
    consultation_type_code: str,
    doctor_id: Optional[uuid.UUID] = None,
    patient_id: Optional[str] = None,
    has_medicine_list: bool = True,
    has_investigation_list: bool = True,
    is_continuation: bool = False,
    parent_extraction_ids: Optional[List[str]] = None,
) -> str:
    """
    Generate user prompt template with {transcript} placeholder.

    This is identical to generate_user_prompt() but uses a placeholder
    instead of actual transcript text.

    Args:
        segments: List of segment configurations
        consultation_type_code: Consultation type code
        doctor_id: Doctor ID for medicine list injection (optional)
        patient_id: Patient ID for history context injection (optional)
        has_medicine_list: Whether doctor/hospital has medicine lists (skip injection if False)
        has_investigation_list: Whether doctor/hospital has investigation lists (skip injection if False)

    Returns:
        User prompt template string with {transcript} placeholder
    """
    # NOTE: JSON schema example generation commented out - redundant since response_schema
    # is already used in gemini_service.py's generate_content call. The schema constrains
    # Gemini's output directly, making the example in the prompt unnecessary.
    #
    # # Build JSON structure example from segments
    # json_structure = {}
    #
    # for idx, segment in enumerate(segments):
    #     # DEFENSIVE: Handle non-dict segments
    #     if isinstance(segment, str):
    #         logger.warning(f"[USER_PROMPT_TEMPLATE] Segment at index {idx} is a string: '{segment[:100]}...'")
    #         json_structure[f"segment_{idx}"] = "string"
    #         continue
    #     if not isinstance(segment, dict):
    #         logger.warning(f"[USER_PROMPT_TEMPLATE] Segment at index {idx} is unexpected type: {type(segment).__name__}")
    #         json_structure[f"segment_{idx}"] = "value"
    #         continue
    #
    #     segment_code = segment.get("segment_code", f"segment_{idx}")
    #     schema_json = segment.get("schema_definition_json", {})
    #
    #     # Convert schema to example structure
    #     if isinstance(schema_json, str):
    #         try:
    #             schema_json = json.loads(schema_json)
    #         except json.JSONDecodeError as e:
    #             logger.warning(f"[USER_PROMPT_TEMPLATE] Failed to parse schema_json for {segment_code}: {e}")
    #             json_structure[_to_camel_case(segment_code)] = "string"
    #             continue
    #
    #     # DEFENSIVE: Ensure schema_json is a dict after parsing
    #     if not isinstance(schema_json, dict):
    #         logger.warning(f"[USER_PROMPT_TEMPLATE] schema_json for {segment_code} is not a dict: {type(schema_json).__name__}")
    #         json_structure[_to_camel_case(segment_code)] = "value"
    #         continue
    #
    #     # Create example based on schema type
    #     if schema_json.get("type") == "object":
    #         json_structure[_to_camel_case(segment_code)] = _schema_to_example(schema_json)
    #     elif schema_json.get("type") == "array":
    #         json_structure[_to_camel_case(segment_code)] = [_schema_to_example(schema_json.get("items", {}))]
    #     else:
    #         json_structure[_to_camel_case(segment_code)] = "string or appropriate type"
    #
    # # Format JSON structure for display
    # json_example = json.dumps(json_structure, indent=2)
    #
    # # ⚠️ CRITICAL: Escape braces for Python's .format() method
    # json_example = json_example.replace('{', '{{').replace('}', '}}')

    header = "**CONSULTATION TRANSCRIPT:**"
    extract_instruction = "Extract structured information from the consultation transcript below."
    special_instructions = "9. Follow the segment structure defined in the system prompt carefully"

    # Some consultation types (e.g. RADIOLOGY) skip doctor/hospital list injection
    # and the OP-shaped patient context block — see _SKIP_DOCTOR_LISTS_AND_CONTEXT_TYPES.
    _skip_doctor_artifacts = _should_skip_doctor_lists_and_context(consultation_type_code)
    if _skip_doctor_artifacts:
        logger.debug(
            f"[USER_PROMPT_TEMPLATE] Skipping medicine/investigation list + patient context "
            f"for consultation_type_code={consultation_type_code}"
        )

    # Medicine list injection for prescription matching (only if lists exist)
    medicine_list_section = ""
    if doctor_id and has_medicine_list and not _skip_doctor_artifacts:
        try:
            from .medicine_service import get_medicine_list_for_prompt
            medicine_list = get_medicine_list_for_prompt(doctor_id)
            if medicine_list:
                medicine_list_section = f"""

**MEDICINE MATCHING (CRITICAL):**
When extracting medicines for the prescription segment, follow these rules:

1. **MATCH FROM LIST FIRST**: For each medicine mentioned, find the closest match from the doctor's medicine list below. Account for:
   - Pronunciation variations (e.g., "amlo" → "AMLODIPINE", "glycomet" → "METFORMIN")
   - Abbreviated names (e.g., "telmi 40" → "TELMISARTAN 40MG")
   - Brand vs generic names (listed as "also:" alternatives)
   - Phonetic similarities (e.g., "azithro" → "AZITHROMYCIN")

2. **MATCH BOTH BRAND NAME AND FORM**: Each medicine entry has a `[Form]` tag (e.g., `[Tablet]`, `[Syrup]`, `[Capsule]`) indicating its dosage form. You MUST match based on BOTH the brand name AND the form mentioned by the doctor. Use the `[Form]` tag to disambiguate entries with the same brand. For example:
   - Doctor says "Dolo 650 tablet" → pick "DOLO 650 [Tablet]", NOT "DOLO 100 ML SYRUP [Syrup]"
   - Doctor says "Crocin syrup" → if no entry has a matching `[Syrup]` form for Crocin, output the spoken name "Crocin Syrup" verbatim. Do NOT pick "CROCIN 500 MG TABLETS [Tablet]" when the doctor clearly said syrup.
   - The form spoken by the doctor MUST match the `[Form]` tag of the selected entry. NEVER substitute a tablet for a syrup or vice versa.

3. **USE EXACT NAME FROM LIST**: If a close match is found, copy the COMPLETE medicine name exactly as it appears in the list — include everything before the `[Form]` tag and "(also:" part. Do NOT include the `[Form]` tag in the output. Do NOT truncate or remove any suffixes like "Kg TABLET" or "ML LIQUID". For example, if the list shows "T - CALPOL 650MG TAB  Kg TABLET [Tablet] (also: CALPOL, ...)", output exactly: "T - CALPOL 650MG TAB  Kg TABLET"

4. **NEW MEDICINES ONLY IF NO MATCH**: Only use the spoken medicine name verbatim if there is NO reasonable match in the list below. This includes cases where the brand exists but the form does not match (e.g., doctor says "syrup" but only a `[Tablet]` entry exists).

5. **FORM SELF-CHECK (MANDATORY)**: After selecting a medicine from the list, verify the `[Form]` tag matches what the doctor said:
   - Doctor said "syrup" but you picked a `[Tablet]` entry? WRONG — output the spoken name verbatim instead.
   - Doctor said "tablet" but you picked a `[Syrup]` entry? WRONG — output the spoken name verbatim instead.
   - If the form doesn't match ANY entry for that brand, output the spoken name verbatim.
   Also set the `dosage_form` field to what the doctor ACTUALLY SAID (e.g., "Syrup"), regardless of which list entry you matched.

{medicine_list}

**FORM REMINDER: A syrup is NEVER a tablet. A tablet is NEVER a syrup. The [Form] tag MUST match the form the doctor said. If in doubt, output the spoken name verbatim.**
"""
                logger.debug(f"[USER_PROMPT_TEMPLATE] Injected medicine list for doctor {doctor_id} ({len(medicine_list)} chars)")
            else:
                logger.debug(f"[USER_PROMPT_TEMPLATE] No medicine list found for doctor {doctor_id}")
        except Exception as e:
            logger.warning(f"[USER_PROMPT_TEMPLATE] Failed to get medicine list for doctor {doctor_id}: {e}")
    elif doctor_id and not has_medicine_list:
        logger.debug(f"[USER_PROMPT_TEMPLATE] Skipping medicine list injection - no lists for doctor {doctor_id}")

    # Investigation list injection for investigation matching (only if lists exist)
    investigation_list_section = ""
    if doctor_id and has_investigation_list and not _skip_doctor_artifacts:
        try:
            from .investigation_service import get_investigation_list_for_prompt
            investigation_list = get_investigation_list_for_prompt(doctor_id)
            if investigation_list:
                investigation_list_section = f"""

**INVESTIGATION MATCHING (CRITICAL):**
When extracting investigations, follow these rules:

1. **MATCH FROM LIST FIRST**: For each investigation mentioned, find the closest match from the doctor's investigation list below. Account for:
   - Abbreviations (e.g., "CBC" → "Complete Blood Count", "LFT" → "Liver Function Test")
   - Common names (e.g., "blood count" → "Complete Blood Count", "chest x-ray" → "X-Ray Chest PA View")
   - Phonetic similarities (e.g., "hemogram" → "Complete Blood Count")

2. **USE EXACT NAME FROM LIST**: If a close match is found, copy the COMPLETE investigation name exactly as it appears in the list - include everything before the "(also:" part. Do NOT truncate or modify the name. For example, if the list shows "Complete Blood Count (also: CBC, ...)", output exactly: "Complete Blood Count"

3. **NEW INVESTIGATIONS ONLY IF NO MATCH**: Only use the spoken investigation name verbatim if there is NO reasonable match in the list below.

{investigation_list}
"""
                logger.debug(f"[USER_PROMPT_TEMPLATE] Injected investigation list for doctor {doctor_id} ({len(investigation_list)} chars)")
            else:
                logger.debug(f"[USER_PROMPT_TEMPLATE] No investigation list found for doctor {doctor_id}")
        except Exception as e:
            logger.warning(f"[USER_PROMPT_TEMPLATE] Failed to get investigation list for doctor {doctor_id}: {e}")
    elif doctor_id and not has_investigation_list:
        logger.debug(f"[USER_PROMPT_TEMPLATE] Skipping investigation list injection - no lists for doctor {doctor_id}")

    # Patient history context injection (prescriptions, summaries, caution)
    patient_context_section = ""
    if patient_id and not _skip_doctor_artifacts:
        try:
            from .patient_context_service import (
                get_patient_context_for_extraction,
                format_patient_context_for_prompt
            )
            doctor_id_str = str(doctor_id) if doctor_id else None
            patient_context = get_patient_context_for_extraction(
                patient_id=patient_id,
                doctor_id=doctor_id_str,
                num_past_consultations=3,
                is_continuation=is_continuation,
                parent_extraction_ids=parent_extraction_ids,
            )
            if patient_context.get("has_context"):
                patient_context_section = format_patient_context_for_prompt(patient_context, is_continuation=is_continuation)
                caution_agg = patient_context.get('caution_aggregated')
                caution_info = f"Yes ({caution_agg.get('source_count', 0)} sources)" if caution_agg else 'No'
                logger.debug(
                    f"[USER_PROMPT_TEMPLATE] Injected patient context for patient {patient_id}: "
                    f"prescriptions={len(patient_context.get('past_prescriptions', []))}, "
                    f"summaries={len(patient_context.get('past_summaries', []))}, "
                    f"caution_aggregated={caution_info}, "
                    f"is_continuation={is_continuation}"
                )
            else:
                logger.debug(f"[USER_PROMPT_TEMPLATE] No patient context found for patient {patient_id}")
        except Exception as e:
            logger.warning(f"[USER_PROMPT_TEMPLATE] Failed to get patient context for patient {patient_id}: {e}")

    # Radiology-specific continuation snapshot — injected only for RADIOLOGY
    # is_continuation visits to keep prior PLAN phases / toxicity ids in the
    # LLM's view without re-introducing the OP-style merge principles.
    radiology_continuation_section = _build_radiology_continuation_context(
        consultation_type_code, is_continuation, parent_extraction_ids
    )

    # ⭐ Use {transcript} placeholder instead of actual transcript
    user_prompt_template = f"""{extract_instruction}

{header}
---
{{transcript}}
---

**EXTRACTION INSTRUCTIONS:**

1. Extract ALL information from the transcript following the segment structure defined in the system prompt
2. Use medical terminology appropriately (convert lay terms to medical terms unless configured otherwise)
3. Preserve all medical abbreviations as they appear
4. Use DD-MM-YYYY format for all dates
5. Include units with all numerical values
6. Use "" for single-value fields with no data
7. Use empty arrays [] for list fields with no data
8. DO NOT fabricate any information not present in the transcript
{special_instructions}
{medicine_list_section}
{investigation_list_section}
{patient_context_section}
{radiology_continuation_section}
Return ONLY the JSON object. No markdown, no explanations, no additional text.
"""

    return user_prompt_template


# ============================================================================
# Merge Support - Generate Target Schema for Merge
# ============================================================================

async def generate_merge_artifacts(
    template_code: str,
    doctor_id: str,
    consultation_type_code: Optional[str] = None,
    mode: str = 'full'
) -> tuple:
    """
    Generate schema and segments for merge target type using template configuration.

    This function is specifically designed for the merge feature, where we need
    to generate a target schema based on the doctor's template configuration.

    Priority for segment configuration:
    1. template_segments table (template-specific category, brevity, etc.)
    2. consultation_type_segments table (fallback if template not found)

    Always uses 'full' mode to capture all possible fields for comprehensive merging.

    Args:
        template_code: Target template code (e.g., "OP_GENERAL", "OP_SMITH_1225141530")
        doctor_id: Doctor ID for template access validation
        consultation_type_code: Optional consultation type code (derived from template if not provided)
        mode: Extraction mode (default: 'full' for merges)

    Returns:
        Tuple of (schema, segments):
        - schema: Gemini types.Schema object for target type
        - segments: List of segment definitions

    Usage:
        schema, segments = await generate_merge_artifacts(
            template_code="OP_GENERAL",
            doctor_id="abc-123",
            mode="full"
        )
    """
    logger.debug(f"[MergeSupport] Generating merge artifacts for template={template_code}, doctor={doctor_id} (mode={mode})")

    # Resolve consultation_type_code from template if not provided
    if not consultation_type_code:
        template = get_template_by_code(template_code)
        if not template:
            raise ValueError(f"Template '{template_code}' not found in database")
        consultation_type_code = template.get('consultation_type_code')
        if not consultation_type_code:
            raise ValueError(f"Template '{template_code}' has no associated consultation type")
        logger.debug(f"[MergeSupport] Resolved template '{template_code}' to consultation type '{consultation_type_code}'")

    # Force 'full' mode for merges to capture all possible fields
    if mode != 'full':
        logger.warning(f"[MergeSupport] Overriding mode '{mode}' to 'full' for comprehensive merging")
        mode = 'full'

    # Split merge types - return None for schema since merge_service handles split schemas internally
    # NEONATAL_DAILY is now a split type with ~125 fields
    if consultation_type_code in ["NEO_DAILY", "NEONATAL_DAILY"]:
        logger.debug(f"[MergeSupport] ⚡ SPLIT MERGE type: {consultation_type_code} - schema handled by merge_service")
        return None, []

    elif consultation_type_code in ["NEO_PROFORMA", "NEONATAL_PROFORMA"]:
        logger.debug(f"[MergeSupport] ⚡ SPLIT MERGE type: {consultation_type_code} - schema handled by merge_service")
        return None, []

    elif consultation_type_code in ["NEO_OP", "NEONATAL_OP"]:
        logger.debug(f"[MergeSupport] ⚡ SPLIT MERGE type: {consultation_type_code} - schema handled by merge_service")
        return None, []

    elif consultation_type_code == "OPHTHALMOLOGY":
        logger.debug(f"[MergeSupport] ⚡ SPLIT MERGE type: {consultation_type_code} - schema handled by merge_service")
        return None, []

    elif consultation_type_code == "OPTOMETRY":
        logger.debug(f"[MergeSupport] ✅ Using hardcoded NESTED OPTOMETRY schema for {consultation_type_code}")
        return OPTO_PARAMETERS_SCHEMA, []

    elif consultation_type_code == "OPHTHAL_DISCHARGE":
        logger.debug(f"[MergeSupport] ⚡ SPLIT MERGE type: {consultation_type_code} - schema handled by merge_service")
        return None, []

    elif consultation_type_code == "OPHTHAL_FULL":
        logger.debug(f"[MergeSupport] ⚡ SPLIT MERGE type: {consultation_type_code} - schema handled by merge_service")
        return None, []

    elif consultation_type_code == "OPHTHAL_PRESCRIPTION":
        logger.debug(f"[MergeSupport] ✅ Using hardcoded OPHTHAL_PRESCRIPTION schema for {consultation_type_code}")
        return OPHTHAL_PRESCRIPTION_SCHEMA, []

    elif consultation_type_code == "OPHTHAL_POSTOP_RX":
        logger.debug(f"[MergeSupport] ✅ Using hardcoded OPHTHAL_POSTOP_RX schema for {consultation_type_code}")
        return OPHTHAL_POSTOP_RX_SCHEMA, []

    # For dynamic types (OP, DISCHARGE), load from database using template configuration
    else:
        logger.debug(f"[MergeSupport] Loading dynamic schema for template={template_code}, consultation_type={consultation_type_code}")

        # Get consultation_type_id from code
        consultation_type = get_consultation_type_by_code(consultation_type_code)
        if not consultation_type:
            raise ValueError(f"Consultation type '{consultation_type_code}' not found in database")

        consultation_type_id = uuid.UUID(consultation_type['id'])
        logger.debug(f"[MergeSupport] Resolved {consultation_type_code} to ID: {consultation_type_id}")

        # Load segments using template configuration
        # Priority: template_segments table first, fallback to consultation_type_segments
        segment_result = load_segments_for_mode(
            consultation_type_id=consultation_type_id,
            doctor_id=uuid.UUID(doctor_id),  # Enable template lookup
            template_code=template_code,      # Use template-specific config
            mode=mode
        )
        segments = segment_result.get("segments", [])

        if not segments:
            # Fallback: try without doctor/template for consultation_type_segments
            logger.warning(f"[MergeSupport] No segments found with template config, falling back to consultation type defaults")
            segment_result = load_segments_for_mode(
                consultation_type_id=consultation_type_id,
                doctor_id=None,
                template_code=None,
                mode=mode
            )
            segments = segment_result.get("segments", [])

        if not segments:
            raise ValueError(f"No segments found for consultation type '{consultation_type_code}'")

        # Generate schema from segments
        schema = generate_gemini_schema(segments)

        logger.debug(f"[MergeSupport] ✅ Generated dynamic schema with {len(segments)} segments")

        return schema, segments

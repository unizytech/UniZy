"""
Extraction Merge Service

AI-powered contextual merging of multiple medical extractions into a single consolidated output.

Features:
- Validates merge requests (same patient, minimum count)
- Prepares merge context (chronological ordering, conflict detection)
- Generates specialized AI prompts for contextual merging
- Calls Gemini API with merge instructions
- Saves merged extraction with relationship tracking
- Schema transformation for uploaded JSON (OPHTHAL_OCR → OPHTHAL_FULL)

Author: System
Date: 2025-11-19
Updated: 2025-12-02 - Added schema transformation support
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import json
from uuid import UUID, uuid4

from services import gemini_service
from services import segment_registry
from services import supabase_service
from services.schema_transformer import SchemaTransformer, detect_schema_type, transform_for_merge

# Split schema imports for consultation types with large schemas
from services.neo_proforma_prompts_split import NEO_PROFORMA_PART1_SCHEMA, NEO_PROFORMA_PART2_SCHEMA
from services.neo_proforma_formatter import format_neo_proforma_from_parts
from services.neo_op_prompts_split import NEO_OP_PART1_SCHEMA, NEO_OP_PART2_SCHEMA
from services.neo_op_formatter import format_neo_op_from_parts
from services.ophthal_prompt_split import OPHTHAL_PART1_SCHEMA, OPHTHAL_PART2_SCHEMA
from services.ophthal_formatter import format_ophthalmology_from_parts
from services.ophthal_discharge_prompt_split import OPHTHAL_DISCHARGE_PART1_SCHEMA, OPHTHAL_DISCHARGE_PART2_SCHEMA
from services.ophthal_discharge_formatter import format_ophthal_discharge_from_parts
from services.ophthal_consult_prompt_split import OPHTHAL_FULL_PART1_SCHEMA, OPHTHAL_FULL_PART2_SCHEMA
from services.ophthal_consult_formatter import format_ophthal_full_consult_from_parts
from services.neo_discharge_prompts_split import NEO_DISCHARGE_PART1_SCHEMA, NEO_DISCHARGE_PART2_SCHEMA
from services.neo_discharge_formatter import format_neo_discharge_from_parts
from services.neo_admission_prompts_split import NEO_ADMISSION_PART1_SCHEMA, NEO_ADMISSION_PART2_SCHEMA
from services.neo_admission_formatter import format_neo_admission_from_parts

logger = logging.getLogger(__name__)

# Consultation types that require split merge due to Gemini schema limits
SPLIT_MERGE_TYPES = {
    "NEO_PROFORMA": {
        "part1_schema": NEO_PROFORMA_PART1_SCHEMA,
        "part2_schema": NEO_PROFORMA_PART2_SCHEMA,
        "formatter": format_neo_proforma_from_parts,
    },
    "NEO_OP": {
        "part1_schema": NEO_OP_PART1_SCHEMA,
        "part2_schema": NEO_OP_PART2_SCHEMA,
        "formatter": format_neo_op_from_parts,
    },
    "OPHTHAL_CONSULT_BRIEF": {
        "part1_schema": OPHTHAL_PART1_SCHEMA,
        "part2_schema": OPHTHAL_PART2_SCHEMA,
        "formatter": format_ophthalmology_from_parts,
    },
    "OPHTHA_DISCHARGE": {
        "part1_schema": OPHTHAL_DISCHARGE_PART1_SCHEMA,
        "part2_schema": OPHTHAL_DISCHARGE_PART2_SCHEMA,
        "formatter": format_ophthal_discharge_from_parts,
    },
    "OPHTHAL_FULL_CONSULT": {
        "part1_schema": OPHTHAL_FULL_PART1_SCHEMA,
        "part2_schema": OPHTHAL_FULL_PART2_SCHEMA,
        "formatter": format_ophthal_full_consult_from_parts,
    },
    "NEO_DISCHARGE": {
        "part1_schema": NEO_DISCHARGE_PART1_SCHEMA,
        "part2_schema": NEO_DISCHARGE_PART2_SCHEMA,
        "formatter": format_neo_discharge_from_parts,
    },
    "NEO_ADMISSION": {
        "part1_schema": NEO_ADMISSION_PART1_SCHEMA,
        "part2_schema": NEO_ADMISSION_PART2_SCHEMA,
        "formatter": format_neo_admission_from_parts,
    },
}


# =====================================================
# Merge Category Definitions (Pattern-Based)
# =====================================================

# Categories are detected by pattern matching on consultation type codes
# Priority order matters - checked from top to bottom
# NOTE: OPHTHAL takes priority over DISCHARGE, so OPHTHAL_DISCHARGE → OPHTHALMOLOGY_FAMILY
CATEGORY_PATTERNS = [
    # Pattern, Category Name, Description
    ("NEONATAL", "NEONATAL_FAMILY", "Neonatal care documentation"),
    ("OPTOMETRY", "OPHTHALMOLOGY_FAMILY", "Eye care - optometry"),
    ("OPHTHAL", "OPHTHALMOLOGY_FAMILY", "Eye care - ophthalmology (including OPHTHAL_DISCHARGE)"),
    ("GKNM", "GKNM_SPECIALTY", "GKNM hospital specialty consultations"),
    ("DISCHARGE", "DISCHARGE_FAMILY", "General discharge summaries (not ophthalmology)"),
    ("OP", "OP_FAMILY", "Outpatient consultations (general, short, concise)"),
]


def get_merge_category(type_code: str) -> str:
    """
    Get the merge category for a consultation type code using pattern matching.

    Priority order (first match wins):
    1. NEONATAL - Neonatal care types
    2. OPTOMETRY/OPHTHAL - Ophthalmology family (OPHTHAL_DISCHARGE is ophthalmology, not general discharge)
    3. GKNM - GKNM specialty types
    4. DISCHARGE - General discharge summaries (hospital discharge, but not eye-specific)
    5. OP - Outpatient types (OP, OP_SHORT, OP_CONCISE)

    Args:
        type_code: Consultation type code (e.g., "OP", "DISCHARGE", "OPHTHAL_FULL", "OPHTHAL_DISCHARGE")

    Returns:
        Category name (e.g., "OP_FAMILY", "DISCHARGE_FAMILY", "OPHTHALMOLOGY_FAMILY")
    """
    if not type_code:
        return "UNKNOWN"

    type_upper = type_code.upper()

    for pattern, category, _ in CATEGORY_PATTERNS:
        if pattern in type_upper:
            return category

    return "UNKNOWN"


def detect_cross_category_scenario(
    source_types: List[str],
    target_type: str
) -> str:
    """
    Detect the merge scenario based on source and target categories.

    Scenarios:
    - SAME_TYPE: All sources and target are identical type
    - WITHIN_*_FAMILY: Same category, different variants (e.g., OP + OP_SHORT → OP)
    - *_to_*: Cross-category merges (e.g., OP_FAMILY_to_DISCHARGE_FAMILY)
    - MIXED_CATEGORIES: Multiple unrelated categories being merged

    Args:
        source_types: List of source consultation type codes
        target_type: Target consultation type code

    Returns:
        Scenario key for CROSS_CATEGORY_MERGE_INSTRUCTIONS
    """
    source_categories = set(get_merge_category(t) for t in source_types)
    target_category = get_merge_category(target_type)
    all_types = set(source_types + [target_type])

    # =========================================
    # SAME TYPE - Exact match (most common)
    # =========================================
    if len(all_types) == 1:
        return "SAME_TYPE"

    # =========================================
    # WITHIN-FAMILY MERGES (same category, different variants)
    # =========================================
    if len(source_categories) == 1 and list(source_categories)[0] == target_category:
        if target_category == "DISCHARGE_FAMILY":
            return "WITHIN_DISCHARGE_FAMILY"
        elif target_category == "OP_FAMILY":
            return "WITHIN_OP_FAMILY"
        elif target_category == "OPHTHALMOLOGY_FAMILY":
            return "WITHIN_OPHTHALMOLOGY_FAMILY"
        elif target_category == "NEONATAL_FAMILY":
            return "WITHIN_NEONATAL_FAMILY"
        elif target_category == "GKNM_SPECIALTY":
            return "WITHIN_GKNM_SPECIALTY"
        else:
            return "SAME_CATEGORY"

    # =========================================
    # CROSS-CATEGORY MERGES
    # =========================================

    # OP Family → Discharge Family (pre-admission visits → discharge summary)
    if "OP_FAMILY" in source_categories and target_category == "DISCHARGE_FAMILY":
        return "OP_to_DISCHARGE"

    # Discharge Family → OP Family (post-discharge follow-up consolidation)
    if "DISCHARGE_FAMILY" in source_categories and target_category == "OP_FAMILY":
        return "DISCHARGE_to_OP"

    # GKNM Specialty → Discharge Family (specialty admission → discharge)
    if "GKNM_SPECIALTY" in source_categories and target_category == "DISCHARGE_FAMILY":
        return "SPECIALTY_to_DISCHARGE"

    # Discharge Family → GKNM Specialty (discharge → specialty follow-up)
    if "DISCHARGE_FAMILY" in source_categories and target_category == "GKNM_SPECIALTY":
        return "DISCHARGE_to_SPECIALTY"

    # Ophthalmology Family → Discharge (eye surgery discharge)
    if "OPHTHALMOLOGY_FAMILY" in source_categories and target_category == "DISCHARGE_FAMILY":
        return "OPHTHALMOLOGY_to_DISCHARGE"

    # =========================================
    # OPHTHALMOLOGY PRESCRIPTION APPEND MERGES
    # =========================================

    # Check for specific prescription type merges within ophthalmology family
    # These are APPEND merges, not replacement merges
    source_types_upper = [t.upper() for t in source_types]
    target_type_upper = target_type.upper()

    # OPHTHAL_POSTOP_RX + OPHTHAL_DISCHARGE → Append post-op Rx to discharge
    if "OPHTHAL_POSTOP_RX" in source_types_upper and "OPHTHAL_DISCHARGE" in target_type_upper:
        return "POSTOP_RX_to_OPHTHAL_DISCHARGE"

    # OPHTHAL_POSTOP_RX being merged INTO OPHTHAL_DISCHARGE (source contains discharge)
    if "OPHTHAL_POSTOP_RX" in source_types_upper and "OPHTHAL_DISCHARGE" in source_types_upper:
        # Target determines the merge direction
        if "OPHTHAL_DISCHARGE" in target_type_upper:
            return "POSTOP_RX_to_OPHTHAL_DISCHARGE"

    # OPHTHAL_PRESCRIPTION + OPHTHALMOLOGY/OPHTHAL_FULL → Append prescription to consultation
    if "OPHTHAL_PRESCRIPTION" in source_types_upper:
        if any(t in target_type_upper for t in ["OPHTHALMOLOGY", "OPHTHAL_FULL", "OPHTHAL_CONSULT"]):
            return "PRESCRIPTION_to_OPHTHAL_CONSULT"

    # OPHTHAL_PRESCRIPTION being merged with ophthalmology consultation types
    if "OPHTHAL_PRESCRIPTION" in source_types_upper:
        if any("OPHTHALMOLOGY" in t or "OPHTHAL_FULL" in t or "OPHTHAL_CONSULT" in t for t in source_types_upper):
            # Both prescription and consultation in sources
            if any(t in target_type_upper for t in ["OPHTHALMOLOGY", "OPHTHAL_FULL", "OPHTHAL_CONSULT"]):
                return "PRESCRIPTION_to_OPHTHAL_CONSULT"

    # Mixed outpatient specialties (OP + GKNM → combined OP)
    if "OP_FAMILY" in source_categories and "GKNM_SPECIALTY" in source_categories:
        if target_category == "OP_FAMILY":
            return "MIXED_OUTPATIENT_to_OP"
        elif target_category == "GKNM_SPECIALTY":
            return "MIXED_OUTPATIENT_to_SPECIALTY"

    # =========================================
    # FALLBACK SCENARIOS
    # =========================================

    # Multiple unrelated categories
    if len(source_categories) > 1:
        return "MIXED_CATEGORIES"

    # Single source category to different target
    return "CROSS_CATEGORY_GENERIC"


# =====================================================
# Merge Prompt Templates
# =====================================================

MERGE_SYSTEM_PROMPT = """You are a highly skilled medical documentation specialist with expertise in merging multiple consultation records across various medical specialties.

Your task is to create a unified, coherent medical extraction by intelligently merging information from multiple source extractions. The sources may be from the same or different consultation types (OP, Discharge, Specialty consultations).

CORE MERGE PRINCIPLES:

1. **CHRONOLOGICAL AWARENESS**
   - Recognize temporal progression across extractions
   - Show how conditions, diagnoses, or treatments evolved over time
   - Example: "Initially presented with X on [date1], progressed to Y by [date2]"
   - For admissions: Show pre-admission → admission → hospital course → discharge timeline

2. **LATEST-WINS STRATEGY (for current state fields)**
   - For fields representing current state (vital signs, current diagnosis, current medications), use the most recent extraction
   - Rationale: Most recent data is most clinically relevant for current treatment
   - Exception: If latest data is incomplete, supplement with earlier complete data

3. **APPEND-MODE (for historical fields)**
   - For fields representing history (past medications, investigations, timestamped events), combine chronologically
   - Preserve all historical data - never lose information
   - Mark discontinued items clearly with dates

4. **NARRATIVE SYNTHESIS (for text fields)**
   - For narrative fields (HPI, hospital course, clinical notes), create coherent merged narrative
   - Show progression, not just concatenation
   - Example: "Patient initially complained of X, which progressed to Y with additional symptom Z noted during follow-up"

5. **CONFLICT RESOLUTION**
   - If contradictory information exists (e.g., different diagnoses at different times), use latest value
   - However, note previous values in clinical_assessment or appropriate field
   - Example: "Diagnosis revised from 'suspected pneumonia' to 'confirmed bacterial pneumonia' based on lab results"

6. **MEDICATION TRACKING**
   - List all medications from all sources
   - Mark status clearly:
     * "Medication X (discontinued [date])"
     * "Medication Y (started [date])"
     * "Dosage changed from A to B on [date]"
   - Preserve all dosage, frequency, duration information
   - Separate by category if needed: Pre-admission / During hospitalization / Discharge

7. **INVESTIGATION CONSOLIDATION**
   - Append all test results chronologically
   - Format: "[Date] Test Name: Result"
   - Show trends if applicable: "WBC increased from X on [date1] to Y on [date2]"
   - Group by type: Laboratory / Imaging / Special investigations

8. **PRESERVE CLINICAL SPECIFICITY**
   - Never lose important details during merge
   - If a source extraction mentions a specific finding, preserve it
   - Maintain medical terminology accuracy

9. **CONTEXT-AWARE FIELD MAPPING**
   - If source and target schemas differ, intelligently map fields:
     * OP "chief_complaints" → DISCHARGE "presenting_complaints" or "admission_complaints"
     * DISCHARGE "hospital_course" → OP "history_of_present_illness" (summarized)
     * Specialty fields → Map to appropriate general sections or preserve in specialty subsections
   - Drop fields not supported by target schema, but note significant omissions

10. **QUALITY OVER BREVITY**
    - Merged extraction should be comprehensive and clinically useful
    - Don't sacrifice information for conciseness
    - Better to have detailed merged record than sparse summary

SPECIALTY-SPECIFIC CONSIDERATIONS:

**Ophthalmology Merges:**
- Preserve separate OD (right eye) and OS (left eye) measurements
- Vision: VA, refraction, IOP should be tracked per eye
- Combine optometry (refraction) with ophthalmology (pathology) findings

**Neonatal Merges:**
- Track daily progress notes → comprehensive proforma
- Preserve feeding, weight, vital sign trends
- Respiratory support progression is critical

**Obstetrics/Gynecology Merges:**
- Preserve obstetric history (G/P/A)
- Fetal monitoring and delivery details are critical
- Maternal and fetal outcomes should both be documented

**Cardiac Merges:**
- ECG and Echo findings should be tracked with dates
- Intervention details (angiography, stenting) are critical
- Risk stratification (TIMI, GRACE scores) should be preserved

**OP → Discharge Merges:**
- Pre-admission OP visits provide baseline and admission context
- Track what was tried outpatient before admission

**Discharge → OP Merges:**
- Hospital course informs follow-up care
- Track post-discharge compliance and recovery

OUTPUT REQUIREMENTS:
- Must conform exactly to the target schema provided
- All required fields must be populated (use "N/A" if truly no data)
- Use proper medical terminology
- Maintain professional clinical documentation style
- Ensure temporal markers are clear (dates, sequence of events)
- Include source attribution where helpful: "[Per OP visit dated X]", "[Per discharge summary]"
"""

MERGE_USER_PROMPT_TEMPLATE = """Please merge the following {source_count} medical extractions into a single {target_type_name} extraction.

MERGE CONTEXT:
- Patient: {patient_name} (ID: {patient_id})
- Target Output Type: {target_type_name}
- Merge Strategy: AI-powered contextual merge
- Conflict Resolution: Latest extraction wins (validate if reasonable)

SOURCE EXTRACTIONS (chronological order, oldest to newest):

{source_extractions_formatted}

TARGET SCHEMA:
{target_schema_description}

MERGE INSTRUCTIONS:

1. **Create unified patient record**:
   - Use patient demographics from most complete source
   - Preserve patient ID, name, age, contact information

2. **Merge diagnoses**:
   - Primary diagnosis: Use from latest extraction
   - If diagnosis changed over time, note evolution in clinical_assessment
   - Secondary diagnoses: Merge unique values, mark resolved conditions

3. **Merge chief complaints**:
   - If ongoing complaints, consolidate into current chief_complaints
   - If resolved complaints, note in history section
   - Show progression: "Initially X, progressed to Y, currently Z"

4. **Merge history (HPI, past medical/surgical history)**:
   - Create chronological narrative for HPI
   - Combine past medical/surgical history (unique values only)
   - Maintain family history, social history, allergies from most complete source

5. **Merge physical examination**:
   - Vital signs: Use latest measurements
   - If vital signs changed significantly, note trend in clinical_assessment
   - General examination: Merge relevant findings
   - Systemic examination: Combine findings, note changes if applicable

6. **Merge investigations**:
   - List all test results chronologically
   - Format: "[YYYY-MM-DD] Test: Result"
   - Show trends for repeated tests

7. **Merge medications**:
   - Create comprehensive medication list with status
   - Format: "Medication Name (dosage) - Status: [Current/Discontinued on DATE/Started on DATE]"
   - Preserve frequency, duration, route, timing, special instructions

8. **Merge treatment plan and advice**:
   - Combine diet, activity, monitoring instructions
   - Prioritize latest instructions if contradictory
   - Preserve warning signs and contingency plans

9. **Merge follow-up**:
   - Use latest follow-up plan
   - If multiple follow-ups scheduled, list all chronologically

10. **Handle cross-type merges intelligently**:
    {cross_type_instructions}

IMPORTANT:
- Do NOT invent information - only use data from provided source extractions
- If data conflicts, prefer latest extraction but validate clinical reasonability
- Maintain medical accuracy and professional documentation standards
- Output must be valid JSON matching the target schema exactly

Generate the merged extraction now:
"""

# =====================================================
# Cross-Category Merge Instructions
# =====================================================
# Comprehensive instructions for each merge scenario detected by detect_cross_category_scenario()

CROSS_CATEGORY_MERGE_INSTRUCTIONS = {

    # =========================================
    # SAME TYPE MERGES
    # =========================================
    "SAME_TYPE": """
    **SAME TYPE MERGE** - Merging multiple extractions of identical consultation type.

    Strategy:
    - Show temporal progression clearly with dates
    - Latest extraction reflects CURRENT state (vitals, diagnosis, medications)
    - Earlier extractions provide HISTORICAL context
    - Mark changes explicitly: "Improved from X to Y", "New symptom Z appeared on [date]"
    - Medications: Track started/discontinued/dosage changes with dates
    - Investigations: Append chronologically, show trends for repeated tests
    - Follow-up: Use latest scheduled follow-up
    """,

    # =========================================
    # WITHIN-FAMILY MERGES (same category, different variants)
    # =========================================
    "WITHIN_OP_FAMILY": """
    **WITHIN OP FAMILY** - Merging different OP variants (OP, OP_SHORT, OP_CONCISE).

    Strategy:
    - OP_CONCISE/OP_SHORT contain subset of fields - expand to full OP format
    - Preserve all details from detailed OP extractions
    - Fill missing fields from shorter variants with "N/A" or infer from context
    - Chief complaints: Merge unique complaints, show progression
    - Diagnosis: Use most specific/complete diagnosis from any source
    - Prescription: Consolidate all medications with status tracking
    - If target is OP_SHORT/OP_CONCISE: Summarize appropriately, prioritize key findings
    """,

    "WITHIN_DISCHARGE_FAMILY": """
    **WITHIN DISCHARGE FAMILY** - Merging different discharge types (DISCHARGE, OPHTHAL_DISCHARGE, etc.).

    Strategy:
    - All are discharge summaries - merge hospital course chronologically
    - If specialty discharge (OPHTHAL_DISCHARGE): Preserve specialty-specific fields
    - Combine admission complaints and discharge diagnoses
    - Merge procedure lists from all sources
    - Discharge medications: Latest list wins, note any changes
    - Discharge condition: Use latest assessment
    - Follow-up instructions: Combine all specialty-specific instructions
    """,

    "WITHIN_OPHTHALMOLOGY_FAMILY": """
    **WITHIN OPHTHALMOLOGY FAMILY** - Merging eye care records (OPTOMETRY, OPHTHALMOLOGY, OPHTHAL_FULL, OPHTHAL_PRESCRIPTION, OPHTHAL_POSTOP_RX).

    **IMPORTANT: CONTEXTUAL DEEP MERGE - NO SOURCE PRIORITIZATION**
    All sources (including uploaded JSON) are treated EQUALLY. The AI performs intelligent
    contextual merge based on data completeness and recency, NOT source type.

    **DEEP MERGE STRATEGY BY FIELD TYPE:**

    1. **CURRENT STATE FIELDS** (Latest wins):
       - visualAcuityAndRefraction: Use most recent VA/refraction per eye
       - intraocularpressure: Use most recent IOP measurements
       - diagnosis: Use most recent/complete diagnosis
       - doctorRecommendation: Use most recent plan
       If source field is EMPTY, DO NOT override existing data from other extractions.

    2. **HISTORY FIELDS** (Deep merge chronologically):
       - pastOcularHistory: MERGE all unique history items chronologically
       - extendedHistory: COMBINE systemic illness, family history, allergies from all sources
       - currentTreatment: Track treatment changes with dates
       - complaints: Show progression "Initially X, progressed to Y, now Z"

    3. **EXAMINATION FIELDS** (Per-eye merge):
       - slitLampExamination: Merge per-eye findings, note changes with dates
       - fundusExamination: Merge per-eye findings, track progression
       - keratometry: Use most recent K readings per eye
       - gonioscopy: Merge findings if different dates

    4. **ARRAY FIELDS** (Append unique items):
       - prescriptionItems: APPEND all unique medications
       - medications: APPEND with timing preserved
       - procedures: APPEND all procedures with dates
       - investigation: APPEND all test results chronologically

    **OPTOMETRY + OPHTHALMOLOGY MERGE:**
    - OPTOMETRY provides: refraction data, VA measurements, glasses prescription
    - OPHTHALMOLOGY provides: clinical findings (fundus, IOP, slit lamp), diagnosis
    - MERGE both sets of data - neither source is "primary"
    - If same field exists in both, use the MORE COMPLETE or MORE RECENT value

    **PRESCRIPTION MERGES (APPEND MODE):**
    - OPHTHAL_PRESCRIPTION + OPHTHALMOLOGY/OPHTHAL_FULL: APPEND prescription items
      * prescriptionItems: ALWAYS APPEND, never replace
      * Mark medications with source if helpful: "[From dated X]"
      * continuingMedications: MERGE unique items from all sources

    - OPHTHAL_POSTOP_RX + OPHTHAL_DISCHARGE: APPEND post-op medications
      * APPEND medications array to discharge section
      * Preserve timing slots (timing1-timing6)
      * Include tapering schedule rows if present

    **UPLOADED JSON HANDLING:**
    - Uploaded JSON is ONE source among many - NOT prioritized
    - Only fields WITH ACTUAL VALUES are included (sparse mode)
    - Empty/N/A fields from uploaded JSON DO NOT override existing data
    - Merge contextually based on data quality and recency
    """,

    "WITHIN_NEONATAL_FAMILY": """
    **WITHIN NEONATAL FAMILY** - Merging neonatal records (NEONATAL_DAILY, NEONATAL_PROFORMA).

    Strategy:
    - DAILY notes capture day-by-day progress
    - PROFORMA is comprehensive admission/discharge summary
    - If DAILY → PROFORMA: Consolidate daily entries into structured proforma
    - Preserve all vital signs, feeding records, weight trends
    - Merge investigation results chronologically
    - Treatment: Show progression of respiratory support, medications
    - Outcome metrics: Use latest assessments
    """,

    "WITHIN_GKNM_SPECIALTY": """
    **WITHIN GKNM SPECIALTY** - Merging GKNM specialty records (GKNM_OBG, GKNM_CARDIAC, etc.).

    Strategy:
    - Different specialties have specialty-specific fields
    - Map common fields (patient info, vitals, diagnosis, prescription)
    - Preserve specialty-specific data in appropriate sections
    - OBG-specific: Obstetric history, fetal monitoring, delivery notes
    - Cardiac-specific: ECG findings, echo results, cardiac medications
    - If cross-specialty (rare): Create combined record with clear specialty sections
    """,

    "SAME_CATEGORY": """
    **SAME CATEGORY** - Generic within-category merge for unlisted variants.

    Strategy:
    - Apply standard merge principles
    - Latest extraction wins for current state fields
    - Append historical data chronologically
    - Preserve all unique information from each source
    """,

    # =========================================
    # CROSS-CATEGORY MERGES (OP ↔ Discharge)
    # =========================================
    "OP_to_DISCHARGE": """
    **OP TO DISCHARGE** - Pre-admission outpatient visits → Discharge summary.

    This is a common scenario: Patient had OP consultations before hospital admission.

    Strategy:
    - OP chief_complaints → Include in presenting complaints/admission reason
    - OP history → Part of history of present illness (pre-admission course)
    - OP investigations → Add to "Investigations done prior to admission"
    - OP diagnosis → Note as "Pre-admission diagnosis" (may be revised)
    - OP medications → "Pre-admission medications" section
    - Create narrative: "Patient was seen in OPD on [dates] with [complaints].
      Was advised admission for [reason]. Hospital course: ..."
    - OP follow-up instructions → May inform discharge planning
    """,

    "DISCHARGE_to_OP": """
    **DISCHARGE TO OP** - Hospital discharge → Follow-up outpatient consolidation.

    This is for post-discharge follow-up tracking.

    Strategy:
    - Discharge admission_complaints → Include in chief_complaints history
    - Hospital course → Summarize in history_of_present_illness
    - Discharge diagnosis → Primary diagnosis (may be refined in follow-up)
    - Discharge medications → Current prescription baseline
    - Procedures performed → Add to past surgical history
    - Discharge follow-up → Track compliance in current OP notes
    - Create narrative: "Post-discharge follow-up. Patient was admitted on [date]
      for [reason]. Discharged on [date]. Current status: ..."
    """,

    # =========================================
    # SPECIALTY → DISCHARGE MERGES
    # =========================================
    "SPECIALTY_to_DISCHARGE": """
    **SPECIALTY TO DISCHARGE** - GKNM specialty consultation → Discharge summary.

    Strategy:
    - Specialty-specific findings → Relevant discharge sections
    - OBG: Delivery details, maternal/fetal outcomes → Discharge summary
    - Cardiac: Procedure notes, intervention details → Hospital course
    - Preserve specialty-specific sections in discharge format
    - Medications from specialty → Discharge medications
    - Specialty follow-up plan → Discharge follow-up instructions
    """,

    "DISCHARGE_to_SPECIALTY": """
    **DISCHARGE TO SPECIALTY** - Discharge → Specialty follow-up.

    Strategy:
    - Extract specialty-relevant information from discharge
    - Hospital course → Relevant history for specialty follow-up
    - Discharge diagnosis → Current working diagnosis
    - Discharge medications → Current medications
    - Pending investigations → Follow-up investigation planning
    - Focus on specialty-specific aspects in the merged output
    """,

    "OPHTHALMOLOGY_to_DISCHARGE": """
    **OPHTHALMOLOGY TO DISCHARGE** - Eye consultation → Eye surgery discharge.

    Strategy:
    - Pre-operative eye examination → Pre-op assessment section
    - Vision measurements → Document pre-op VA, target post-op VA
    - Surgical procedure → Primary procedure in hospital course
    - Post-op medications → Discharge medications (eye drops, etc.)
    - Follow-up schedule → Discharge follow-up (typically frequent for eye surgery)
    """,

    # =========================================
    # OPHTHALMOLOGY PRESCRIPTION APPEND MERGES
    # =========================================
    "POSTOP_RX_to_OPHTHAL_DISCHARGE": """
    **POST-OP RX TO OPHTHAL DISCHARGE** - Appending post-operative medication schedule to discharge summary.

    This is an APPEND-ONLY merge. The post-op Rx provides detailed medication timing that must be
    ADDED to the discharge summary, not replace existing discharge medications.

    Strategy:
    - PRESERVE all existing discharge summary data (hospital course, procedures, diagnosis)
    - APPEND medications from OPHTHAL_POSTOP_RX to discharge medications section
    - Preserve medication timing structure:
      * timing1 through timing6 slots for each medication
      * durationText and dateRange for each medication
      * serialNumber including tapering sub-rows (2a, 2b, 2c)
    - Merge surgeryDetails from post-op Rx with discharge procedure information
    - APPEND generalInstructions from post-op Rx to discharge advice
    - Use most recent follow-up date from either source

    Medication Format in Discharge:
    - Create "Post-Operative Medication Schedule" subsection
    - Include the full timing table format from OPHTHAL_POSTOP_RX
    - Mark source: "[Post-operative medication schedule dated X]"

    CRITICAL:
    - Do NOT replace existing discharge medications
    - Do NOT lose any timing slot information (timing1-timing6)
    - Do NOT flatten the medication schedule into simple list
    - Preserve tapering schedule rows as separate entries
    """,

    "PRESCRIPTION_to_OPHTHAL_CONSULT": """
    **PRESCRIPTION TO OPHTHAL CONSULTATION** - Appending prescription to ophthalmology consultation.

    This is an APPEND-ONLY merge. The prescription provides detailed medication list that must be
    ADDED to the consultation record, not replace existing prescription data.

    Strategy:
    - PRESERVE all existing consultation data (examination, diagnosis, findings)
    - APPEND prescriptionItems from OPHTHAL_PRESCRIPTION to consultation prescription section
    - For each prescriptionItem, preserve:
      * serialNumber, medicationName, medicationType
      * dosage, frequency, duration
      * eye specification (BOTH EYES, LEFT EYE, RIGHT EYE)
      * specialInstructions
    - MERGE continuingMedications (combine unique items from both sources)
    - APPEND pharmacyNote to advice section if not already present
    - Use most recent follow-up date

    Prescription Format in Consultation:
    - Create clear numbered list format for medications
    - Include continuing medications section separately
    - Mark source: "[Prescription dated X]"

    CRITICAL:
    - Do NOT replace existing consultation prescriptions
    - Do NOT lose dosing or frequency information
    - Preserve medication type classification (CAPSULE, TABLET, EYE_DROP, etc.)
    - Keep eye specification for each medication
    """,

    # =========================================
    # MIXED CATEGORY MERGES
    # =========================================
    "MIXED_OUTPATIENT_to_OP": """
    **MIXED OUTPATIENT TO OP** - Multiple specialty OP visits → Consolidated OP.

    Strategy:
    - Combine chief complaints from all specialties
    - Separate findings by specialty in examination section
    - Merge diagnoses: List all, indicate specialty source
    - Combine prescriptions with specialty attribution
    - Unified follow-up plan considering all specialties
    """,

    "MIXED_OUTPATIENT_to_SPECIALTY": """
    **MIXED OUTPATIENT TO SPECIALTY** - General OP + Specialty → Specialty format.

    Strategy:
    - General OP findings → Background/history section
    - Specialty findings → Primary focus in merged output
    - Common medications from both sources
    - Specialty-specific follow-up takes precedence
    """,

    "MIXED_CATEGORIES": """
    **MIXED CATEGORIES** - Multiple unrelated consultation types.

    Strategy:
    - This is an unusual merge - proceed with caution
    - Map common fields (patient info, vitals, medications)
    - Create clearly labeled sections for each consultation type
    - Preserve all unique information
    - Note in clinical assessment: "This is a consolidated record from multiple consultation types"
    - Target schema determines final structure
    """,

    "CROSS_CATEGORY_GENERIC": """
    **CROSS-CATEGORY GENERIC** - Unspecified cross-category merge.

    Strategy:
    - Apply intelligent field mapping based on field names
    - Common mappings:
      * chief_complaints ↔ presenting_complaints ↔ admission_complaints
      * diagnosis ↔ discharge_diagnosis ↔ final_diagnosis
      * prescription ↔ discharge_medications ↔ medications
      * follow_up ↔ discharge_follow_up ↔ review_date
    - Preserve temporal information
    - Note source consultation type in relevant sections
    - Prioritize clinical safety - don't lose important information
    """,

    # =========================================
    # FALLBACK: UPLOADED JSON (Legacy - rarely used)
    # =========================================
    # NOTE: This scenario is now rarely triggered because uploaded JSON is included
    # in category detection and will use the appropriate family merge strategy.
    # This fallback exists for edge cases where uploaded JSON type cannot be determined.
    "APPEND_JSON": """
    **FALLBACK: UPLOADED JSON MERGE** - Used when uploaded JSON type cannot be categorized.

    NOTE: This is a fallback scenario. In most cases, uploaded JSON will be transformed
    to match the target schema and included in category-based family merge (e.g.,
    WITHIN_OPHTHALMOLOGY_FAMILY for ophthalmology data).

    **SPARSE MODE ACTIVE:**
    - Uploaded JSON only includes fields with actual values
    - Empty fields are omitted and will NOT override existing data

    **MERGE STRATEGY:**
    - Treat uploaded JSON as one source among many
    - Apply standard merge principles: latest wins for current state, append for arrays
    - Deep merge history fields chronologically
    - No source prioritization
    """
}

# =====================================================
# Schema Transformation Functions
# =====================================================

class SchemaCompatibilityError(Exception):
    """Raised when uploaded JSON schema is incompatible with target consultation type."""
    pass


# Schema compatibility rules: which source schemas can merge into which target families
SCHEMA_COMPATIBILITY = {
    "OPHTHAL_OCR": ["OPHTHALMOLOGY_FAMILY"],  # OCR-extracted ophthalmology data → only ophthalmology targets
    "OPHTHAL_FULL": ["OPHTHALMOLOGY_FAMILY"],
    "OPHTHAL_FULL_FLAT": ["OPHTHALMOLOGY_FAMILY"],
    # Add more mappings as needed:
    # "DISCHARGE_EXTERNAL": ["DISCHARGE_FAMILY"],
    # "OP_EXTERNAL": ["OP_FAMILY"],
}


def validate_schema_compatibility(
    source_schema: str,
    target_consultation_type_code: str
) -> Tuple[bool, str]:
    """
    Validate that source schema is compatible with target consultation type.

    Args:
        source_schema: Detected source schema type (e.g., "OPHTHAL_OCR")
        target_consultation_type_code: Target consultation type (e.g., "OPHTHAL_FULL")

    Returns:
        Tuple of (is_compatible, error_message)
    """
    # Get target category
    target_category = get_merge_category(target_consultation_type_code)

    # Check if source schema has compatibility restrictions
    if source_schema in SCHEMA_COMPATIBILITY:
        allowed_categories = SCHEMA_COMPATIBILITY[source_schema]
        if target_category not in allowed_categories:
            return False, (
                f"Schema incompatibility: '{source_schema}' source can only be merged into "
                f"{allowed_categories} targets, but target '{target_consultation_type_code}' "
                f"belongs to '{target_category}' family."
            )

    # UNKNOWN schemas are allowed to merge into any target (pass-through)
    return True, ""


def transform_uploaded_json_for_merge(
    uploaded_json: Dict[str, Any],
    target_consultation_type_code: str
) -> Dict[str, Any]:
    """
    Transform uploaded JSON to match the target consultation type schema.

    This function detects the source schema format and transforms it to the
    target schema format before merge. This is especially useful for:
    - OPHTHAL_OCR format → OPHTHAL_FULL format (OCR-extracted ophthalmology data)
    - External system exports → Internal schema format

    IMPORTANT: Schema compatibility is enforced. OPHTHAL_OCR sources can
    ONLY be merged into OPHTHALMOLOGY_FAMILY targets (OPHTHAL_FULL, OPHTHAL_DISCHARGE, etc.)

    Args:
        uploaded_json: Dict with keys:
            - data: The JSON data to transform
            - source_name: Display name
            - source_type: Type identifier
            - consultation_type_code: Original type code
        target_consultation_type_code: Target schema type (e.g., "OPHTHAL_FULL")

    Returns:
        Updated uploaded_json dict with transformed data and metadata

    Raises:
        SchemaCompatibilityError: If source schema cannot be merged into target type
    """
    try:
        data = uploaded_json.get('data', {})

        if not data:
            logger.warning("[MergeService] No data in uploaded_json to transform")
            return uploaded_json

        # Detect source schema type
        source_schema = detect_schema_type(data)
        logger.debug(f"[MergeService] Detected source schema: {source_schema}")

        # =====================================================
        # SCHEMA COMPATIBILITY VALIDATION
        # =====================================================
        is_compatible, error_message = validate_schema_compatibility(
            source_schema, target_consultation_type_code
        )

        if not is_compatible:
            logger.error(f"[MergeService] ❌ {error_message}")
            raise SchemaCompatibilityError(error_message)

        # Determine if transformation is needed
        needs_transformation = False

        # Transform OPHTHAL_OCR → OPHTHAL_FULL family
        if source_schema == "OPHTHAL_OCR" and "OPHTHAL" in target_consultation_type_code.upper():
            needs_transformation = True
            logger.debug(f"[MergeService] Will transform OPHTHAL_OCR → {target_consultation_type_code}")

        if needs_transformation:
            # Perform transformation (sparse mode by default)
            transformed_data = transform_for_merge(data, target_schema="OPHTHAL_FULL")

            # Update uploaded_json with transformed data
            result = {
                **uploaded_json,
                "data": transformed_data,
                "original_data": data,  # Preserve original for audit
                "transformation_applied": True,
                "source_schema_detected": source_schema,
                "target_schema": target_consultation_type_code
            }

            logger.debug(
                f"[MergeService] Schema transformation complete: "
                f"{source_schema} → {target_consultation_type_code}, "
                f"{len(data)} fields → {len(transformed_data)} fields (sparse mode)"
            )

            return result
        else:
            # No transformation needed (schema already compatible or UNKNOWN)
            logger.debug(f"[MergeService] No transformation needed for {source_schema} → {target_consultation_type_code}")
            return {
                **uploaded_json,
                "transformation_applied": False,
                "source_schema_detected": source_schema
            }

    except SchemaCompatibilityError:
        # Re-raise compatibility errors for caller to handle
        raise
    except Exception as e:
        logger.error(f"[MergeService] ❌ Schema transformation failed: {str(e)}")
        # Return original data on error
        from services.error_utils import sanitize_error_message
        return {
            **uploaded_json,
            "transformation_applied": False,
            "transformation_error": sanitize_error_message(str(e))
        }


# =====================================================
# Core Merge Functions
# =====================================================

async def validate_merge_request(
    source_extraction_ids: List[str],
    target_consultation_type_code: str,
    supabase_client,
    uploaded_json_count: int = 0,
    # Legacy parameter for backward compatibility
    has_uploaded_json: bool = False
) -> Tuple[bool, str, Optional[str]]:
    """
    Validate merge request before processing.

    Checks:
    1. All source extractions exist
    2. All belong to same patient
    3. Minimum sources: 2 total (extractions + JSON uploads combined)
    4. Target consultation type exists

    Args:
        source_extraction_ids: List of extraction UUIDs to merge
        target_consultation_type_code: Target consultation type (e.g., "OP", "DISCHARGE")
        supabase_client: Supabase client instance
        uploaded_json_count: Number of uploaded JSON sources (counts toward total)
        has_uploaded_json: [DEPRECATED] Use uploaded_json_count instead

    Returns:
        Tuple of (is_valid, error_message, patient_id)
    """
    try:
        # Handle legacy has_uploaded_json parameter
        if has_uploaded_json and uploaded_json_count == 0:
            uploaded_json_count = 1

        total_sources = len(source_extraction_ids) + uploaded_json_count
        logger.debug(f"[MergeService] Validating merge request: {len(source_extraction_ids)} DB extractions + {uploaded_json_count} JSON uploads → {target_consultation_type_code}")

        # Check minimum source count (2 total)
        if total_sources < 2:
            return False, f"At least 2 sources required for merge. Got {total_sources}", None

        # If we have at least 1 database extraction, validate it
        if len(source_extraction_ids) >= 1:
            # Use database validation function
            result = supabase_client.rpc(
                'validate_merge_sources',
                {'p_source_extraction_ids': source_extraction_ids}
            ).execute()

            if not result.data or len(result.data) == 0:
                return False, "Validation failed - no result from database", None

            validation = result.data[0]

            # Handle the RPC's "At least 2 extractions required" error specially
            # When we have 1 DB extraction + uploaded JSON(s), this is valid (total_sources >= 2)
            if not validation['is_valid']:
                error_msg = validation['error_message']
                # If the only error is "need 2 extractions" but we have uploaded JSON to make up the difference, allow it
                if 'At least 2 extractions required' in error_msg and uploaded_json_count >= 1 and len(source_extraction_ids) == 1:
                    logger.debug(f"[MergeService] Allowing 1 DB extraction + {uploaded_json_count} JSON uploads merge (bypassing RPC minimum count)")
                else:
                    return False, error_msg, None

            patient_id = validation['patient_id']
        else:
            # No database extractions - JSON-only merge
            # This is handled by the caller (merge_extractions) which requires patient_id
            return False, "No database extractions provided - caller must handle JSON-only merge validation", None

        # Validate target consultation type exists
        consultation_type = supabase_client.table('consultation_types').select('*').eq('type_code', target_consultation_type_code).execute()

        if not consultation_type.data:
            return False, f"Target consultation type '{target_consultation_type_code}' not found", patient_id

        logger.info(f"[MergeService] ✅ Validation passed: {total_sources} total sources for patient {patient_id}")
        return True, "Valid", patient_id

    except Exception as e:
        logger.error(f"[MergeService] ❌ Validation error: {str(e)}")
        return False, f"Validation error: {str(e)}", None


async def prepare_merge_context(
    source_extraction_ids: List[str],
    target_consultation_type_code: str,
    supabase_client,
    uploaded_json_sources: Optional[List[Dict[str, Any]]] = None,
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Prepare merge context by loading and organizing source extractions.

    Steps:
    1. Load all source extractions with full data
    2. Add uploaded JSON sources with their merge strategies
    3. Sort chronologically (oldest → newest)
    4. Extract patient demographics
    5. Build conflict map for overlapping fields
    6. Determine cross-type merge scenario

    Args:
        source_extraction_ids: List of extraction UUIDs
        target_consultation_type_code: Target consultation type
        supabase_client: Supabase client instance
        uploaded_json_sources: List of uploaded JSON source dicts with:
            - data: The JSON data to merge
            - upload_type: Type of data (INVESTIGATION, PRESCRIPTION, OP_SUMMARY, etc.)
            - merge_strategy: DEEP_MERGE or APPEND
            - source_name: Display name
            - source_date: Optional date for chronological ordering
            - consultation_type_code: Optional type code for field mapping
        patient_id: Optional patient_id (required for JSON-only merges)

    Returns:
        Dict with merge context:
        {
            "source_extractions": [...],
            "patient_info": {...},
            "conflict_map": {...},
            "cross_type_scenario": "SAME_TYPE" | "OP_to_DISCHARGE" | "APPEND_JSON" | etc,
            "source_count": int,
            "earliest_date": datetime,
            "latest_date": datetime,
            "uploaded_json_count": int,
            "merge_strategies": {...}  # Per-source merge strategies
        }
    """
    try:
        uploaded_json_sources = uploaded_json_sources or []
        logger.debug(f"[MergeService] Preparing merge context for {len(source_extraction_ids)} extractions + {len(uploaded_json_sources)} JSON uploads")

        # Load all source extractions
        source_extractions = []

        for extraction_id in source_extraction_ids:
            # Get extraction with segments
            extraction_result = supabase_service.get_extraction_by_id(extraction_id)

            if not extraction_result:
                logger.warning(f"[MergeService] Extraction {extraction_id} not found, skipping")
                continue

            # Load full extraction data (edited version if exists, otherwise original)
            extraction_data = extraction_result.get('edited_extraction_json') or extraction_result.get('original_extraction_json')

            # Extract consultation type info from nested structure
            consultation_types = extraction_result.get('consultation_types', {})

            source_extractions.append({
                "extraction_id": extraction_id,
                "consultation_type_code": consultation_types.get('type_code'),
                "consultation_type_name": consultation_types.get('type_name'),
                "created_at": extraction_result['created_at'],
                "doctor_id": extraction_result.get('doctor_id'),
                "doctor_name": extraction_result.get('doctor_name'),
                "extraction_mode": extraction_result.get('extraction_mode'),
                "segment_count": extraction_result.get('segment_count'),
                "data": extraction_data
            })

        # Sort chronologically (oldest → newest)
        source_extractions.sort(key=lambda x: x['created_at'])

        # Track merge strategies per source
        merge_strategies = {}

        # Add uploaded JSON sources with their merge strategies
        for idx, json_source in enumerate(uploaded_json_sources):
            source_id = f"UPLOADED_JSON_{idx}"
            source_name = json_source.get('source_name', f'Uploaded JSON {idx + 1}')
            upload_type = json_source.get('upload_type', 'OTHER')
            merge_strategy = json_source.get('merge_strategy', 'DEEP_MERGE')
            source_date = json_source.get('source_date')

            logger.debug(f"[MergeService] Adding JSON source: {source_name} (type={upload_type}, strategy={merge_strategy})")

            # Track merge strategy for this source
            merge_strategies[source_id] = {
                "strategy": merge_strategy,
                "upload_type": upload_type
            }

            # =====================================================
            # SCHEMA TRANSFORMATION FOR UPLOADED JSON
            # =====================================================
            # Transform uploaded JSON to match target schema if needed
            # This handles OPHTHAL_OCR → OPHTHAL_FULL conversion
            transformed_json = transform_uploaded_json_for_merge(
                json_source,
                target_consultation_type_code
            )

            if transformed_json.get('transformation_applied'):
                logger.debug(
                    f"[MergeService] Schema transformation applied: "
                    f"{transformed_json.get('source_schema_detected')} → {target_consultation_type_code}"
                )

            # Determine timestamp for sorting
            if source_date:
                timestamp = source_date
            else:
                # If no date provided, place after DB extractions
                timestamp = datetime.utcnow().isoformat()

            source_extractions.append({
                "extraction_id": source_id,
                "consultation_type_code": transformed_json.get('consultation_type_code', upload_type),
                "consultation_type_name": source_name,
                "created_at": timestamp,
                "doctor_id": None,
                "doctor_name": None,
                "extraction_mode": "uploaded",
                "segment_count": len(transformed_json.get('data', {})),
                "data": transformed_json.get('data', {}),
                # Additional metadata for uploaded JSON
                "is_uploaded_json": True,
                "upload_type": upload_type,
                "merge_strategy": merge_strategy,
                "source_name": source_name,
                # Transformation metadata
                "transformation_applied": transformed_json.get('transformation_applied', False),
                "source_schema_detected": transformed_json.get('source_schema_detected'),
                "original_data": transformed_json.get('original_data')  # For audit trail
            })

        # Re-sort after adding JSON sources (by date)
        source_extractions.sort(key=lambda x: x['created_at'])

        has_uploaded_json = len(uploaded_json_sources) > 0

        # Extract patient info from most complete source (latest DB extraction, not uploaded JSON)
        # For patient info, prefer DB extractions over uploaded JSON
        db_extractions = [e for e in source_extractions if not e.get('is_uploaded_json')]
        if db_extractions:
            latest_db_extraction = db_extractions[-1]
            patient_info = latest_db_extraction['data'].get('patientInformation') or latest_db_extraction['data'].get('patient_information') or {}
        else:
            patient_info = {}

        # Get patient_id UUID from database
        # For DB extractions: look up from first extraction
        # For JSON-only merges: resolve external patient_id (varchar) to UUID via patients table
        resolved_patient_uuid = None
        if db_extractions:
            # Have DB extractions - get patient_id from first one
            extraction_record = supabase_client.table('medical_extractions').select('patient_id').eq('id', db_extractions[0]['extraction_id']).execute()
            if extraction_record.data:
                resolved_patient_uuid = extraction_record.data[0]['patient_id']
        elif patient_id:
            # JSON-only merge - resolve external patient_id (varchar) to UUID
            # Use create_or_get_patient to auto-create if doesn't exist
            from services.supabase_service import create_or_get_patient, get_doctor_hospital_id_cached
            merge_hospital_id = get_doctor_hospital_id_cached(doctor_id) if doctor_id else None
            patient_record = create_or_get_patient(
                patient_id=patient_id,  # External varchar ID (e.g., "PAT-12345")
                full_name=None,
                hospital_id=merge_hospital_id,
            )
            resolved_patient_uuid = patient_record['id']  # UUID from patients.id
            from services.log_sanitizer import truncate_id as _tid
            logger.debug(f"[MergeService] Resolved external patient_id '{_tid(patient_id)}' to UUID: {_tid(resolved_patient_uuid)}")

        # Determine cross-type merge scenario using pattern-based detection
        # Include uploaded JSON's detected type in the scenario detection
        source_consultation_types = [e['consultation_type_code'] for e in db_extractions]

        # If uploaded JSON was transformed, include its target type in source types for proper category detection
        # This ensures ophthalmology uploaded JSON uses WITHIN_OPHTHALMOLOGY_FAMILY merge strategy
        if has_uploaded_json:
            uploaded_source = next((e for e in source_extractions if e.get('is_uploaded_json')), None)
            if uploaded_source:
                # Use the detected/transformed schema type for category-based merge
                uploaded_type = uploaded_source.get('consultation_type_code', 'EXTERNAL')
                # If transformation was applied, the uploaded JSON now matches target schema
                if uploaded_source.get('transformation_applied'):
                    # Add target type (e.g., OPHTHAL_FULL) to ensure proper category detection
                    source_consultation_types.append(target_consultation_type_code)
                    logger.debug(f"[MergeService] Uploaded JSON transformed to {target_consultation_type_code}, included in category detection")
                elif uploaded_type and uploaded_type != 'EXTERNAL':
                    source_consultation_types.append(uploaded_type)

        unique_types = list(set(source_consultation_types))

        # Always use category-based scenario detection
        # Uploaded JSON is treated as one of the sources, not a special case
        cross_type_scenario = detect_cross_category_scenario(
            source_types=source_consultation_types,
            target_type=target_consultation_type_code
        )

        # Add note if uploaded JSON is present
        if has_uploaded_json:
            logger.debug(f"[MergeService] Uploaded JSON included in {cross_type_scenario} merge (sparse mode - only populated fields)")

        # Log category information for debugging
        source_categories = set(get_merge_category(t) for t in source_consultation_types) if source_consultation_types else set()
        target_category = get_merge_category(target_consultation_type_code)
        logger.debug(f"[MergeService] Source categories: {source_categories}, Target category: {target_category}")

        # Build conflict map (simplified - track fields present in multiple extractions)
        conflict_map = {}
        all_fields = set()

        for extraction in source_extractions:
            data = extraction['data']
            fields = set(data.keys())
            for field in fields:
                if field in all_fields:
                    conflict_map[field] = conflict_map.get(field, 0) + 1
                all_fields.add(field)

        # Get transformation metadata if uploaded JSON was transformed
        transformation_metadata = None
        if has_uploaded_json:
            uploaded_source = next((e for e in source_extractions if e.get('is_uploaded_json')), None)
            if uploaded_source and uploaded_source.get('transformation_applied'):
                transformation_metadata = {
                    "applied": True,
                    "source_schema": uploaded_source.get('source_schema_detected'),
                    "target_schema": target_consultation_type_code,
                    "original_field_count": len(uploaded_source.get('original_data', {})) if uploaded_source.get('original_data') else 0,
                    "transformed_field_count": len(uploaded_source.get('data', {}))
                }

        # Build list of uploaded JSON source names
        uploaded_source_names = [
            e.get('source_name', f"Uploaded JSON {i+1}")
            for i, e in enumerate(source_extractions)
            if e.get('is_uploaded_json')
        ]

        merge_context = {
            "source_extractions": source_extractions,
            "patient_info": patient_info,
            "patient_id": str(resolved_patient_uuid) if resolved_patient_uuid else None,
            "conflict_map": conflict_map,
            "cross_type_scenario": cross_type_scenario,
            "source_count": len(source_extractions),
            "earliest_date": source_extractions[0]['created_at'] if source_extractions else None,
            "latest_date": source_extractions[-1]['created_at'] if source_extractions else None,
            "consultation_types": unique_types,
            # Category information for debugging and logging
            "source_categories": list(source_categories),
            "target_category": target_category,
            "target_consultation_type": target_consultation_type_code,
            # Uploaded JSON tracking
            "has_uploaded_json": has_uploaded_json,
            "uploaded_json_count": len(uploaded_json_sources),
            "uploaded_json_source_names": uploaded_source_names,
            # Merge strategies per source
            "merge_strategies": merge_strategies,
            # Schema transformation metadata
            "schema_transformation": transformation_metadata
        }

        logger.info(f"[MergeService] ✅ Merge context prepared: {len(source_extractions)} sources ({len(db_extractions)} DB + {len(uploaded_json_sources)} uploaded), scenario={cross_type_scenario}")
        return merge_context

    except Exception as e:
        logger.error(f"[MergeService] ❌ Error preparing merge context: {str(e)}")
        raise


def format_source_extractions_for_prompt(source_extractions: List[Dict[str, Any]]) -> str:
    """
    Format source extractions for inclusion in merge prompt.

    Args:
        source_extractions: List of source extraction dicts

    Returns:
        Formatted string for prompt
    """
    formatted = []

    for i, extraction in enumerate(source_extractions, 1):
        created_at = extraction['created_at']
        consultation_type = extraction['consultation_type_name']
        doctor_name = extraction.get('doctor_name', 'Unknown')
        data = extraction['data']

        # Convert data to formatted JSON
        data_json = json.dumps(data, indent=2)

        formatted.append(f"""
{'='*80}
SOURCE EXTRACTION {i} of {len(source_extractions)}
{'='*80}
Date: {created_at}
Type: {consultation_type}
Doctor: {doctor_name}
Extraction ID: {extraction['extraction_id']}

DATA:
{data_json}
""")

    return "\n".join(formatted)


def _build_merge_strategy_instructions(
    source_extractions: List[Dict[str, Any]],
    merge_strategies: Dict[str, Dict[str, str]]
) -> str:
    """
    Build merge strategy instructions for the AI prompt based on uploaded JSON sources.

    Args:
        source_extractions: List of source extraction dicts (includes uploaded JSON)
        merge_strategies: Dict of source_id -> {"strategy": "DEEP_MERGE"|"APPEND", "upload_type": str}

    Returns:
        Formatted string with merge strategy instructions, or empty string if no uploaded JSON
    """
    # Find uploaded JSON sources
    uploaded_sources = [e for e in source_extractions if e.get('is_uploaded_json')]

    if not uploaded_sources:
        return ""

    lines = [
        "**UPLOADED JSON MERGE STRATEGIES:**",
        "",
        "The following uploaded JSON sources have specific merge strategies:"
    ]

    for source in uploaded_sources:
        source_id = source['extraction_id']
        source_name = source.get('source_name', source_id)
        upload_type = source.get('upload_type', 'OTHER')
        merge_strategy = source.get('merge_strategy', 'DEEP_MERGE')

        if merge_strategy == "APPEND":
            lines.append(f"""
- **{source_name}** (Type: {upload_type}) → **APPEND MODE**
  * Array fields (medications, investigations, prescriptionItems, etc.): APPEND all items
  * Do NOT replace existing arrays, ADD to them
  * Preserve all existing data from other sources
  * Mark source with timestamp/date if available
""")
        else:  # DEEP_MERGE
            lines.append(f"""
- **{source_name}** (Type: {upload_type}) → **DEEP MERGE MODE**
  * Current state fields (diagnosis, vitals, etc.): Use latest/most complete value
  * History fields: Merge chronologically
  * Array fields: Merge and deduplicate
  * Empty fields from this source do NOT override existing data
""")

    # Add general reminder about uploaded JSON handling
    lines.append("""
**CRITICAL RULES FOR UPLOADED JSON:**
1. Uploaded JSON sources are treated EQUALLY with database extractions
2. Apply the specified merge strategy (APPEND vs DEEP_MERGE) per source
3. For APPEND sources: Array fields MUST be concatenated, not replaced
4. For DEEP_MERGE sources: Use intelligent merging based on data quality and recency
5. Never lose data during merge - preserve all clinically relevant information
""")

    return "\n".join(lines)


async def generate_merge_prompt(
    merge_context: Dict[str, Any],
    target_consultation_type_code: str,
    target_schema_description: str
) -> Dict[str, str]:
    """
    Generate specialized AI prompt for contextual merging.

    Args:
        merge_context: Prepared merge context
        target_consultation_type_code: Target consultation type
        target_schema_description: Human-readable schema description

    Returns:
        Dict with "system_prompt" and "user_prompt"
    """
    try:
        logger.debug(f"[MergeService] Generating merge prompt for {merge_context['source_count']} sources")

        # Get cross-category merge instructions based on detected scenario
        cross_type_scenario = merge_context['cross_type_scenario']
        cross_type_instructions = CROSS_CATEGORY_MERGE_INSTRUCTIONS.get(
            cross_type_scenario,
            CROSS_CATEGORY_MERGE_INSTRUCTIONS["SAME_TYPE"]  # Fallback to SAME_TYPE
        )

        logger.debug(f"[MergeService] Using merge scenario: {cross_type_scenario}")

        # Get target consultation type name
        target_type_name = target_consultation_type_code  # Simplified, could be enhanced

        # Format source extractions with merge strategy annotations
        source_extractions_formatted = format_source_extractions_for_prompt(
            merge_context['source_extractions']
        )

        # Build merge strategy instructions for uploaded JSON sources
        merge_strategies = merge_context.get('merge_strategies', {})
        merge_strategy_instructions = _build_merge_strategy_instructions(
            merge_context['source_extractions'],
            merge_strategies
        )

        # Append merge strategy instructions to cross_type_instructions
        if merge_strategy_instructions:
            cross_type_instructions = f"{cross_type_instructions}\n\n{merge_strategy_instructions}"

        # Get patient info
        patient_info = merge_context['patient_info']
        patient_name = patient_info.get('name') or patient_info.get('patientName') or 'Unknown'
        patient_id = merge_context.get('patient_id', 'Unknown')

        # Build user prompt
        user_prompt = MERGE_USER_PROMPT_TEMPLATE.format(
            source_count=merge_context['source_count'],
            target_type_name=target_type_name,
            patient_name=patient_name,
            patient_id=patient_id,
            source_extractions_formatted=source_extractions_formatted,
            target_schema_description=target_schema_description,
            cross_type_instructions=cross_type_instructions
        )

        logger.debug(f"[MergeService] Merge prompt generated ({len(user_prompt)} chars)")

        return {
            "system_prompt": MERGE_SYSTEM_PROMPT,
            "user_prompt": user_prompt
        }

    except Exception as e:
        logger.error(f"[MergeService] ❌ Error generating merge prompt: {str(e)}")
        raise


async def perform_ai_merge(
    merge_prompt: Dict[str, str],
    target_schema,
    model: Optional[str] = None,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Call LLM API to perform AI-powered contextual merge.

    Supports multiple providers (Gemini, Claude, OpenAI) based on model name prefix.

    Args:
        merge_prompt: Dict with "system_prompt" and "user_prompt"
        target_schema: Gemini schema object for target type (converted to JSON Schema for non-Gemini)
        model: LLM model to use (defaults to 'thorough' mode from processing_modes)
        session_id: Recording session ID for usage tracking (optional)
        extraction_id: Medical extraction ID for usage tracking (optional)
        doctor_id: Doctor ID for usage tracking (optional)

    Returns:
        Merged extraction data as dict
    """
    import time
    from services.llm_usage_service import log_merge_usage, log_llm_usage, create_error_usage
    from services.llm_client_factory import get_provider, generate_structured_output

    # Use model from 'thorough' processing mode if not specified
    if model is None:
        model = supabase_service.get_extraction_model_by_mode('thorough')

    provider = get_provider(model)

    try:
        logger.info(f"[MergeService] Starting AI merge with model: {model} (provider: {provider})")
        logger.debug(f"[MergeService] System prompt: {len(merge_prompt['system_prompt'])} chars")
        logger.debug(f"[MergeService] User prompt: {len(merge_prompt['user_prompt'])} chars")

        start_time = time.time()

        if provider != "gemini":
            # ===== NON-GEMINI PATH (Claude / OpenAI) =====
            from services.schema_adapter import gemini_schema_to_json_schema

            # Convert Gemini Schema to standard JSON Schema
            json_schema = gemini_schema_to_json_schema(target_schema)

            from services.llm_usage_service import get_thinking_budget
            llm_response = await generate_structured_output(
                system_prompt=merge_prompt['system_prompt'],
                user_prompt=merge_prompt['user_prompt'],
                json_schema=json_schema,
                model=model,
                temperature=0.3,
                thinking_budget=get_thinking_budget(model, "merge"),
            )
            merged_data = llm_response.data
            api_duration = time.time() - start_time

            # Log usage
            usage_data = log_merge_usage(
                response=llm_response.raw_response,
                model=model,
                api_duration_seconds=api_duration,
                session_id=UUID(session_id) if session_id else None,
                extraction_id=UUID(extraction_id) if extraction_id else None,
                doctor_id=UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(usage_data)

        else:
            # ===== GEMINI PATH (existing logic) =====
            merged_data = await gemini_service.generate_content(
                system_prompt=merge_prompt['system_prompt'],
                user_prompt=merge_prompt['user_prompt'],
                response_schema=target_schema,
                model=model,
                temperature=0.3
            )
            api_duration = time.time() - start_time

            usage_data = log_merge_usage(
                response=None,  # Response not available from generate_content
                model=model,
                api_duration_seconds=api_duration,
                session_id=UUID(session_id) if session_id else None,
                extraction_id=UUID(extraction_id) if extraction_id else None,
                doctor_id=UUID(doctor_id) if doctor_id else None,
            )
            await log_llm_usage(usage_data)

        logger.info(f"[MergeService] ✅ AI merge completed: {len(str(merged_data))} chars in {api_duration:.2f}s")
        return merged_data

    except Exception as e:
        logger.error(f"[MergeService] ❌ AI merge failed: {str(e)}")

        # Log error
        error_usage = create_error_usage(
            call_type="merge",
            call_subtype="ai_contextual_merge",
            model=model,
            error_message=str(e),
            session_id=UUID(session_id) if session_id else None,
            extraction_id=UUID(extraction_id) if extraction_id else None,
            doctor_id=UUID(doctor_id) if doctor_id else None,
        )
        await log_llm_usage(error_usage)

        raise


async def perform_merge_from_split(
    merge_prompt: Dict[str, str],
    target_consultation_type_code: str,
    model: Optional[str] = None,
    # Usage tracking context (optional)
    session_id: Optional[str] = None,
    extraction_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Perform AI-powered merge using split schema approach (2 API calls).

    This is used for consultation types with large schemas that exceed
    Gemini's constraint limits (NEONATAL_PROFORMA, OPHTHALMOLOGY,
    OPHTHAL_DISCHARGE, OPHTHAL_FULL).

    Supports multiple providers (Gemini, Claude, OpenAI) based on model name prefix.

    Args:
        merge_prompt: Dict with "system_prompt" and "user_prompt"
        target_consultation_type_code: Target type to determine which split schemas to use
        model: LLM model to use (defaults to 'thorough' mode from processing_modes)
        session_id: Recording session ID for usage tracking
        extraction_id: Medical extraction ID for usage tracking
        doctor_id: Doctor ID for usage tracking

    Returns:
        Merged extraction data as dict (formatted from Part1 + Part2)
    """
    import time
    from services.llm_usage_service import log_merge_usage, log_llm_usage, create_error_usage
    from services.llm_client_factory import get_provider, generate_structured_output

    # Use model from 'thorough' processing mode if not specified
    if model is None:
        model = supabase_service.get_extraction_model_by_mode('thorough')

    provider = get_provider(model)

    # Get split config for this consultation type
    split_config = SPLIT_MERGE_TYPES.get(target_consultation_type_code)
    if not split_config:
        raise ValueError("No split merge configuration found for this consultation type")

    part1_schema = split_config["part1_schema"]
    part2_schema = split_config["part2_schema"]
    formatter = split_config["formatter"]

    try:
        logger.info(f"[MergeService] Starting SPLIT merge for {target_consultation_type_code} (2 API calls, provider: {provider})")
        logger.debug(f"[MergeService] System prompt: {len(merge_prompt['system_prompt'])} chars")
        logger.debug(f"[MergeService] User prompt: {len(merge_prompt['user_prompt'])} chars")

        total_start_time = time.time()

        if provider != "gemini":
            # ===== NON-GEMINI PATH (Claude / OpenAI) =====
            from services.schema_adapter import gemini_schema_to_json_schema

            part1_json_schema = gemini_schema_to_json_schema(part1_schema)
            part2_json_schema = gemini_schema_to_json_schema(part2_schema)

            # ========== PART 1 ==========
            logger.debug(f"[MergeService] Starting PART 1 merge ({provider})...")
            part1_start_time = time.time()

            from services.llm_usage_service import get_thinking_budget
            merge_budget = get_thinking_budget(model, "merge")

            part1_response = await generate_structured_output(
                system_prompt=merge_prompt['system_prompt'],
                user_prompt=merge_prompt['user_prompt'],
                json_schema=part1_json_schema,
                model=model,
                temperature=0.3,
                thinking_budget=merge_budget,
            )
            part1_data = part1_response.data
            part1_duration = time.time() - part1_start_time
            logger.debug(f"[MergeService] Part 1 completed in {part1_duration:.2f}s, {len(str(part1_data))} chars")

            usage_data_p1 = log_merge_usage(
                response=part1_response.raw_response,
                model=model,
                api_duration_seconds=part1_duration,
                session_id=UUID(session_id) if session_id else None,
                extraction_id=UUID(extraction_id) if extraction_id else None,
                doctor_id=UUID(doctor_id) if doctor_id else None,
                call_subtype=f"merge_{target_consultation_type_code.lower()}_part1"
            )
            await log_llm_usage(usage_data_p1)

            # ========== PART 2 ==========
            logger.debug(f"[MergeService] Starting PART 2 merge ({provider})...")
            part2_start_time = time.time()

            part2_response = await generate_structured_output(
                system_prompt=merge_prompt['system_prompt'],
                user_prompt=merge_prompt['user_prompt'],
                json_schema=part2_json_schema,
                model=model,
                temperature=0.3,
                thinking_budget=merge_budget,
            )
            part2_data = part2_response.data
            part2_duration = time.time() - part2_start_time
            logger.debug(f"[MergeService] Part 2 completed in {part2_duration:.2f}s, {len(str(part2_data))} chars")

            usage_data_p2 = log_merge_usage(
                response=part2_response.raw_response,
                model=model,
                api_duration_seconds=part2_duration,
                session_id=UUID(session_id) if session_id else None,
                extraction_id=UUID(extraction_id) if extraction_id else None,
                doctor_id=UUID(doctor_id) if doctor_id else None,
                call_subtype=f"merge_{target_consultation_type_code.lower()}_part2"
            )
            await log_llm_usage(usage_data_p2)

        else:
            # ===== GEMINI PATH (existing logic) =====
            # ========== PART 1 ==========
            logger.debug(f"[MergeService] Starting PART 1 merge...")
            part1_start_time = time.time()

            part1_data = await gemini_service.generate_content(
                system_prompt=merge_prompt['system_prompt'],
                user_prompt=merge_prompt['user_prompt'],
                response_schema=part1_schema,
                model=model,
                temperature=0.3
            )

            part1_duration = time.time() - part1_start_time
            logger.debug(f"[MergeService] Part 1 completed in {part1_duration:.2f}s, {len(str(part1_data))} chars")

            usage_data_p1 = log_merge_usage(
                response=None,
                model=model,
                api_duration_seconds=part1_duration,
                session_id=UUID(session_id) if session_id else None,
                extraction_id=UUID(extraction_id) if extraction_id else None,
                doctor_id=UUID(doctor_id) if doctor_id else None,
                call_subtype=f"merge_{target_consultation_type_code.lower()}_part1"
            )
            await log_llm_usage(usage_data_p1)

            # ========== PART 2 ==========
            logger.debug(f"[MergeService] Starting PART 2 merge...")
            part2_start_time = time.time()

            part2_data = await gemini_service.generate_content(
                system_prompt=merge_prompt['system_prompt'],
                user_prompt=merge_prompt['user_prompt'],
                response_schema=part2_schema,
                model=model,
                temperature=0.3
            )

            part2_duration = time.time() - part2_start_time
            logger.debug(f"[MergeService] Part 2 completed in {part2_duration:.2f}s, {len(str(part2_data))} chars")

            usage_data_p2 = log_merge_usage(
                response=None,
                model=model,
                api_duration_seconds=part2_duration,
                session_id=UUID(session_id) if session_id else None,
                extraction_id=UUID(extraction_id) if extraction_id else None,
                doctor_id=UUID(doctor_id) if doctor_id else None,
                call_subtype=f"merge_{target_consultation_type_code.lower()}_part2"
            )
            await log_llm_usage(usage_data_p2)

        # ========== MERGE PARTS ==========
        logger.debug(f"[MergeService] Merging Part 1 and Part 2 results...")
        merged_data = formatter(part1_data, part2_data)

        total_duration = time.time() - total_start_time
        logger.info(
            f"[MergeService] ✅ SPLIT merge completed for {target_consultation_type_code}: "
            f"{len(str(merged_data))} chars in {total_duration:.2f}s "
            f"(Part1: {part1_duration:.2f}s, Part2: {part2_duration:.2f}s)"
        )

        return merged_data

    except Exception as e:
        logger.error(f"[MergeService] ❌ SPLIT merge failed for {target_consultation_type_code}: {str(e)}")

        # Log error
        error_usage = create_error_usage(
            call_type="merge",
            call_subtype=f"split_merge_{target_consultation_type_code.lower()}",
            model=model,
            error_message=str(e),
            session_id=UUID(session_id) if session_id else None,
            extraction_id=UUID(extraction_id) if extraction_id else None,
            doctor_id=UUID(doctor_id) if doctor_id else None,
        )
        await log_llm_usage(error_usage)

        raise


async def save_merged_extraction(
    merged_data: Dict[str, Any],
    merge_context: Dict[str, Any],
    target_consultation_type_code: str,
    doctor_id: str,
    merge_notes: Optional[str],
    merge_prompt: Dict[str, str],
    supabase_client,
    extraction_id: Optional[str] = None,
    target_template_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Save merged extraction to database with relationship tracking.

    Steps:
    1. INSERT into medical_extractions (is_merged=TRUE)
    2. INSERT into extraction_segments (all segments)
    3. INSERT into extraction_relationships (link sources)
    4. UPDATE source extractions (add merged_into_extraction_id)

    Args:
        merged_data: Merged extraction data
        merge_context: Merge context with source extractions
        target_consultation_type_code: Target consultation type (for internal lookup)
        doctor_id: Doctor who performed merge
        merge_notes: Optional notes about merge
        merge_prompt: Prompts used for merge (for audit)
        supabase_client: Supabase client instance
        target_template_code: Template code used for merge (stored in metadata)

    Returns:
        Dict with merged extraction info:
        {
            "extraction_id": str,
            "is_merged": bool,
            "source_count": int,
            "merge_timestamp": str
        }
    """
    try:
        logger.info(f"[MergeService] Saving merged extraction")

        # Get patient_id from merge context
        patient_id = merge_context.get('patient_id')

        if not patient_id:
            raise ValueError("patient_id not found in merge context")

        # Get consultation_type_id
        consultation_type = supabase_client.table('consultation_types').select('id').eq('type_code', target_consultation_type_code).single().execute()

        if not consultation_type.data:
            raise ValueError("Consultation type not found")

        consultation_type_id = consultation_type.data['id']

        # Build merge metadata
        merge_metadata = {
            "source_count": merge_context['source_count'],
            "target_template_code": target_template_code or target_consultation_type_code,  # Prefer template_code, fallback to type_code
            "merge_timestamp": datetime.utcnow().isoformat(),
            "doctor_confirmed": True,
            "merge_notes": merge_notes or "",
            "conflict_count": len(merge_context.get('conflict_map', {})),
            "conflicts_resolved": list(merge_context.get('conflict_map', {}).keys()),
            "cross_type_scenario": merge_context['cross_type_scenario'],
            "consultation_types_merged": merge_context['consultation_types']
        }

        # Combine system and user prompts for storage
        full_merge_prompt = f"{merge_prompt['system_prompt']}\n\n{'='*80}\n\n{merge_prompt['user_prompt']}"

        # Count segments in merged data
        segment_count = len(merged_data) if isinstance(merged_data, dict) else 0

        # NOTE: Do NOT include submission_id for merged extractions
        # submission_id has a foreign key constraint to processing_jobs table,
        # and merged extractions don't have an associated processing job.
        # Clients should use extraction_id to look up merged extractions.

        # INSERT into medical_extractions
        extraction_record = {
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "consultation_type_id": consultation_type_id,
            # submission_id intentionally omitted - merged extractions have no processing job
            "extraction_mode": "full",  # Merged extractions are always full
            "model_used": supabase_service.get_extraction_model_by_mode('thorough'),  # Model from processing_modes
            "segment_count": segment_count,
            "original_extraction_json": merged_data,  # Store as original (immutable)
            "is_merged": True,
            "merge_metadata": merge_metadata,
            "merge_prompt": full_merge_prompt
        }

        # Use pre-generated extraction_id if provided (for async merge flow)
        if extraction_id:
            extraction_record["id"] = extraction_id
            logger.debug(f"[MergeService] Using pre-generated extraction_id: {extraction_id}")

        result = supabase_client.table('medical_extractions').insert(extraction_record).execute()

        if not result.data:
            raise ValueError("Failed to insert merged extraction")

        merged_extraction_id = result.data[0]['id']

        logger.info(f"[MergeService] ✅ Merged extraction saved: {merged_extraction_id}")

        # INSERT into extraction_relationships (link all DB sources, skip uploaded JSON)
        source_extractions = merge_context['source_extractions']
        relationships = []

        # Filter out uploaded JSON sources - they don't have real extraction IDs in the database
        db_source_extractions = [e for e in source_extractions if not e.get('is_uploaded_json')]

        for i, source_extraction in enumerate(db_source_extractions, 1):
            relationships.append({
                "merged_extraction_id": merged_extraction_id,
                "source_extraction_id": source_extraction['extraction_id'],
                "merge_order": i,  # 1=oldest, N=newest
                "merge_strategy": "ai_contextual",
                "source_metadata": {
                    "consultation_type": source_extraction['consultation_type_code'],
                    "created_at": source_extraction['created_at'],
                    "doctor_id": source_extraction.get('doctor_id')
                }
            })

        if relationships:
            supabase_client.table('extraction_relationships').insert(relationships).execute()
            logger.debug(f"[MergeService] {len(relationships)} relationships created")
        else:
            logger.debug(f"[MergeService] No DB extraction relationships to create (uploaded JSON only merge)")

        # UPDATE source extractions (add merged_into_extraction_id) - only for DB extractions
        for source_extraction in db_source_extractions:
            supabase_client.table('medical_extractions').update({
                "merged_into_extraction_id": merged_extraction_id
            }).eq('id', source_extraction['extraction_id']).execute()

        logger.debug(f"[MergeService] Source extractions updated with merge reference")

        # INSERT into extraction_segments (all segments from merged data)
        # Convert merged_data dict to segments format expected by save_extraction_segments
        # IMPORTANT: Filter out null/empty segment values - database has NOT NULL constraint
        segments_to_save = []
        for segment_code, segment_value in merged_data.items():
            # Skip null, None, or empty values - these violate the NOT NULL constraint
            if segment_value is None:
                logger.debug(f"[MergeService] Skipping null segment: {segment_code}")
                continue
            # Also skip empty strings and empty dicts/lists (optional, for cleaner data)
            if segment_value == "" or segment_value == {} or segment_value == []:
                logger.debug(f"[MergeService] Skipping empty segment: {segment_code}")
                continue
            segments_to_save.append({
                "segment_code": segment_code,
                "segment_value": segment_value
            })

        skipped_count = len(merged_data) - len(segments_to_save)
        if skipped_count > 0:
            logger.debug(f"[MergeService] Skipped {skipped_count} null/empty segments out of {len(merged_data)} total")

        if segments_to_save:
            supabase_service.save_extraction_segments(
                extraction_id=UUID(merged_extraction_id),
                segments=segments_to_save
            )
            logger.debug(f"[MergeService] {len(segments_to_save)} extraction segments saved")
        else:
            logger.warning(f"[MergeService] ⚠️ No segments to save for merged extraction")

        return {
            "extraction_id": merged_extraction_id,
            # submission_id not included - merged extractions don't have processing jobs
            # Use extraction_id for lookups instead
            "is_merged": True,
            "source_count": merge_context['source_count'],
            "merge_timestamp": merge_metadata['merge_timestamp'],
            "merged_data": merged_data
        }

    except Exception as e:
        logger.error(f"[MergeService] ❌ Error saving merged extraction: {str(e)}")
        raise


# =====================================================
# Main Orchestrator Function
# =====================================================

async def merge_extractions(
    source_extraction_ids: List[str],
    target_consultation_type_code: str,
    doctor_id: str,
    merge_notes: Optional[str] = None,
    preview_only: bool = False,
    supabase_client = None,
    uploaded_json_sources: Optional[List[Dict[str, Any]]] = None,
    extraction_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    target_template_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main orchestrator function for extraction merging.

    Complete workflow:
    1. Validate merge request
    2. Prepare merge context (including uploaded JSON sources)
    3. Generate target schema
    4. Generate merge prompt
    5. Perform AI merge
    6. Save merged extraction (if not preview)

    Args:
        source_extraction_ids: List of extraction UUIDs to merge (can be empty for JSON-only merges)
        target_consultation_type_code: Target consultation type (derived from template, for internal logic)
        doctor_id: Doctor performing merge
        merge_notes: Optional notes about merge
        preview_only: If True, don't save (return preview)
        supabase_client: Supabase client instance
        uploaded_json_sources: List of uploaded JSON source dicts with keys:
            - data: The JSON data to merge
            - upload_type: Type of data (INVESTIGATION, PRESCRIPTION, OP_SUMMARY, etc.)
            - merge_strategy: DEEP_MERGE or APPEND
            - source_name: Display name
            - source_date: Optional date for chronological ordering
            - consultation_type_code: Optional type code for field mapping
        extraction_id: Optional pre-generated extraction UUID (for async merge flow)
        patient_id: Optional patient UUID (required for JSON-only merges)
        target_template_code: Optional template code (for metadata storage)

    Returns:
        Dict with merge result:
        {
            "success": bool,
            "extraction_id": str (if saved),
            "merged_data": dict,
            "merge_metadata": dict,
            "preview": bool
        }
    """
    try:
        uploaded_json_sources = uploaded_json_sources or []
        total_sources = len(source_extraction_ids) + len(uploaded_json_sources)
        logger.info(f"[MergeService] ===== Starting merge: {total_sources} sources ({len(source_extraction_ids)} DB + {len(uploaded_json_sources)} uploaded) → {target_consultation_type_code} =====")

        # Step 1: Validate (skip if JSON-only merge with provided patient_id)
        resolved_patient_id = patient_id
        if source_extraction_ids:
            # Have DB extractions - validate them
            is_valid, error_message, db_patient_id = await validate_merge_request(
                source_extraction_ids,
                target_consultation_type_code,
                supabase_client,
                uploaded_json_count=len(uploaded_json_sources)
            )

            if not is_valid:
                logger.error(f"[MergeService] Validation failed: {error_message}")
                return {
                    "success": False,
                    "error": error_message
                }
            resolved_patient_id = db_patient_id
        else:
            # JSON-only merge - validate patient_id was provided and consultation type exists
            if not patient_id:
                logger.error(f"[MergeService] JSON-only merge requires patient_id")
                return {
                    "success": False,
                    "error": "patient_id is required for JSON-only merges"
                }
            # Validate target consultation type exists
            consultation_type = supabase_client.table('consultation_types').select('*').eq('type_code', target_consultation_type_code).execute()
            if not consultation_type.data:
                return {
                    "success": False,
                    "error": f"Target consultation type '{target_consultation_type_code}' not found"
                }
            logger.info(f"[MergeService] JSON-only merge with patient_id: {patient_id}")

        # Step 2: Prepare merge context (pass uploaded JSON sources with merge strategies)
        merge_context = await prepare_merge_context(
            source_extraction_ids,
            target_consultation_type_code,
            supabase_client,
            uploaded_json_sources=uploaded_json_sources,
            patient_id=resolved_patient_id,
            doctor_id=doctor_id
        )

        # Step 3: Generate target schema using template configuration
        # Priority: template_segments first, fallback to consultation_type_segments
        target_schema, target_segments = await segment_registry.generate_merge_artifacts(
            template_code=target_template_code,
            doctor_id=doctor_id,
            consultation_type_code=target_consultation_type_code,  # Pre-resolved for efficiency
            mode='full'
        )

        # Create schema description for prompt
        target_schema_description = f"Target Type: {target_consultation_type_code}\nSegments: {len(target_segments)}\n\nSchema structure will be enforced by the AI model."

        # Step 4: Generate merge prompt
        merge_prompt = await generate_merge_prompt(
            merge_context,
            target_consultation_type_code,
            target_schema_description
        )

        # Step 5: Perform AI merge
        # Route to split merge for consultation types with large schemas
        if target_consultation_type_code in SPLIT_MERGE_TYPES:
            logger.info(f"[MergeService] Routing to SPLIT merge for {target_consultation_type_code}")
            merged_data = await perform_merge_from_split(
                merge_prompt,
                target_consultation_type_code,
                extraction_id=extraction_id,
                doctor_id=doctor_id
            )
        else:
            # Standard single-call merge for smaller schemas
            merged_data = await perform_ai_merge(
                merge_prompt,
                target_schema,
                extraction_id=extraction_id,
                doctor_id=doctor_id
            )

        # Build merge_metadata that matches MergeMetadata model
        merge_metadata_response = {
            "source_count": merge_context['source_count'],
            "target_type_code": target_consultation_type_code,
            "merge_timestamp": datetime.utcnow().isoformat(),
            "doctor_confirmed": not preview_only,  # True when saved, False when preview
            "merge_notes": merge_notes,
            "conflict_count": len(merge_context.get('conflict_map', {})),
            "conflicts_resolved": list(merge_context.get('conflict_map', {}).keys()),
            "cross_type_scenario": merge_context['cross_type_scenario'],
            "consultation_types_merged": merge_context['consultation_types']
        }

        # If preview only, return now
        if preview_only:
            logger.info(f"[MergeService] Preview mode - not saving")
            return {
                "success": True,
                "preview": True,
                "merged_data": merged_data,
                "merge_metadata": merge_metadata_response,
                "source_count": merge_context['source_count']
            }

        # Step 6: Save merged extraction
        save_result = await save_merged_extraction(
            merged_data,
            merge_context,
            target_consultation_type_code,
            doctor_id,
            merge_notes,
            merge_prompt,
            supabase_client,
            extraction_id=extraction_id,  # Pass pre-generated ID for async flow
            target_template_code=target_template_code
        )

        logger.info(f"[MergeService] ===== Merge completed successfully: {save_result['extraction_id']} =====")

        return {
            "success": True,
            "preview": False,
            "extraction_id": save_result['extraction_id'],
            # submission_id not included - merged extractions don't have processing jobs
            "patient_id": merge_context.get('patient_id'),  # For webhook
            "merged_data": merged_data,
            "merge_metadata": merge_metadata_response,
            "source_count": merge_context['source_count']
        }

    except Exception as e:
        logger.error(f"[MergeService] ❌ Merge failed: {type(e).__name__}")
        from services.error_utils import sanitize_error_message
        return {
            "success": False,
            "error": sanitize_error_message(str(e))
        }
